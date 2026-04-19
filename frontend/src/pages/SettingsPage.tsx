import { useEffect, useState } from 'react';
import type { RecurringEntryRead, ExpenseCategory, RecurrenceFrequency } from '../types/api';
import {
  listRecurring, createRecurring, deleteRecurring, exportCsv, runSimulation,
  upsertSurvey, getParticipant, updateParticipant,
} from '../lib/api';

/* ============================================================
   Settings Page — profile, recurring, simulation, data export, survey
   ============================================================ */

interface Props { participantId: string | null; }

const EXPENSE_CATEGORIES: ExpenseCategory[] = [
  'food', 'transport', 'entertainment', 'shopping', 'education',
  'health', 'utilities', 'subscription', 'travel', 'social', 'emergency', 'other',
];

const EMOJIS = ['😌', '😐', '😰', '😫', '🤯'];

function StarPicker({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="star-rating">
      {[1, 2, 3, 4, 5].map((i) => (
        <button key={i} type="button" className={`star-btn ${i <= value ? 'active' : ''}`}
          onClick={() => onChange(i)}>
          {EMOJIS[i - 1]}
        </button>
      ))}
    </div>
  );
}

export default function SettingsPage({ participantId }: Props) {
  const [tab, setTab] = useState<'recurring' | 'simulation' | 'export' | 'survey' | 'allocations' | 'system'>('recurring');
  const [status, setStatus] = useState('');

  // Allocations
  const [allocations, setAllocations] = useState<Record<string, number>>({});
  const [allocTotal, setAllocTotal] = useState(0);
  const [lockedCats, setLockedCats] = useState<Set<string>>(new Set());

  const handleAllocationChange = (category: string, newAmount: number) => {
    const oldAmount = allocations[category] || 0;
    const diff = newAmount - oldAmount;
    if (diff === 0) return;

    let remainingDiff = diff;
    const newAlloc = { ...allocations };
    newAlloc[category] = newAmount;

    const newLocked = new Set(lockedCats);
    newLocked.add(category);
    setLockedCats(newLocked);

    const nonEssentials = ['entertainment', 'shopping', 'travel'];
    const essentials = ['rent', 'food', 'health', 'utilities'];
    
    // If increased, reduce non-essentials first. If decreased, give back to essentials first.
    const targets = diff > 0 ? [...nonEssentials, ...essentials] : [...essentials, ...nonEssentials];

    for (const target of targets) {
      if (target === category || newLocked.has(target)) continue;
      if (remainingDiff === 0) break;

      if (diff > 0) {
        const available = newAlloc[target] || 0;
        const reduction = Math.min(available, remainingDiff);
        newAlloc[target] -= reduction;
        remainingDiff -= reduction;
      } else {
        newAlloc[target] += Math.abs(remainingDiff);
        remainingDiff = 0;
      }
    }
    
    setAllocations(newAlloc);
    localStorage.setItem(`bbt_alloc_${participantId}`, JSON.stringify(newAlloc));
  };

  // Recurring
  const [recurring, setRecurring] = useState<RecurringEntryRead[]>([]);
  const [recAmount, setRecAmount] = useState('');
  const [recCategory, setRecCategory] = useState<ExpenseCategory>('utilities');
  const [recMerchant, setRecMerchant] = useState('');
  const [recFreq, setRecFreq] = useState<RecurrenceFrequency>('monthly');
  const [recDue, setRecDue] = useState(new Date().toISOString().split('T')[0]);

  // Simulation
  const [simLookback, setSimLookback] = useState('21');
  const [simHorizon, setSimHorizon] = useState('14');
  const [simFood, setSimFood] = useState('0');
  const [simEnt, setSimEnt] = useState('0');
  const [simShop, setSimShop] = useState('0');
  const [simIncome, setSimIncome] = useState('0');
  const [simResult, setSimResult] = useState<any>(null);

  // Survey
  const [survStress, setSurvStress] = useState(3);
  const [survSocial, setSurvSocial] = useState(3);
  const [survBoredom, setSurvBoredom] = useState(3);
  const [survPlanning, setSurvPlanning] = useState(3);
  const [survTrigger, setSurvTrigger] = useState('');

  useEffect(() => {
    if (participantId && tab === 'allocations') {
      getParticipant(participantId).then(p => {
        setAllocTotal(p.monthly_budget);
        const saved = localStorage.getItem(`bbt_alloc_${participantId}`);
        if (saved) {
          setAllocations(JSON.parse(saved));
        } else {
          const b = p.monthly_budget;
          const initialAlloc = {
            rent: b * 0.3, food: b * 0.2, travel: b * 0.1, 
            utilities: b * 0.1, entertainment: b * 0.1, 
            health: b * 0.1, shopping: b * 0.1
          };
          setAllocations(initialAlloc);
          localStorage.setItem(`bbt_alloc_${participantId}`, JSON.stringify(initialAlloc));
        }
      }).catch(console.error);
    }
    if (participantId && tab === 'recurring') {
      listRecurring(participantId).then(setRecurring).catch(console.error);
    }
  }, [participantId, tab]);

  if (!participantId) {
    return (
      <div className="empty-state">
        <p className="empty-state-icon">⚙️</p>
        <h3>Select a participant first</h3>
      </div>
    );
  }

  const flash = (msg: string) => { setStatus(msg); setTimeout(() => setStatus(''), 3000); };

  const handleAddRecurring = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createRecurring(participantId, {
        amount: Number(recAmount), category: recCategory, merchant: recMerchant || undefined,
        frequency: recFreq, next_due: recDue,
      });
      setRecAmount(''); setRecMerchant('');
      listRecurring(participantId).then(setRecurring);
      flash('✅ Recurring entry added!');
    } catch { flash('❌ Failed'); }
  };

  const handleDeleteRecurring = async (id: string) => {
    await deleteRecurring(participantId, id);
    listRecurring(participantId).then(setRecurring);
    flash('✅ Removed');
  };

  const handleSimulation = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const adj: Record<string, number> = {};
      if (Number(simFood)) adj.food = Number(simFood);
      if (Number(simEnt)) adj.entertainment = Number(simEnt);
      if (Number(simShop)) adj.shopping = Number(simShop);
      const res = await runSimulation(participantId, {
        lookback_days: Number(simLookback), horizon_days: Number(simHorizon),
        category_adjustments: adj, additional_income: Number(simIncome),
      });
      setSimResult(res);
    } catch { flash('❌ Simulation failed'); }
  };

  const handleSurvey = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await upsertSurvey(participantId, {
        stress_spending_score: survStress, social_pressure_score: survSocial,
        boredom_spending_score: survBoredom, planning_confidence_score: survPlanning,
        self_described_trigger: survTrigger || undefined,
      });
      flash('✅ Survey saved!');
    } catch { flash('❌ Failed to save survey'); }
  };


  return (
    <div>
      <div className="page-header">
        <h2>Settings</h2>
        <p>Manage recurring expenses, run simulations, export data, and update your behavior survey</p>
      </div>

      {status && (
        <div className="glass-panel" style={{ marginBottom: 16, padding: '12px 18px', textAlign: 'center', fontSize: 14 }}>
          {status}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {[
          { id: 'recurring' as const, label: '🔄 Recurring' },
          { id: 'simulation' as const, label: '🔮 What-If' },
          { id: 'export' as const, label: '📥 Export' },
          { id: 'survey' as const, label: '📋 Survey' },
          { id: 'allocations' as const, label: '💰 Budget Planning' },
          { id: 'system' as const, label: '⚙️ App System' },
        ].map((t) => (
          <button key={t.id} className={`btn ${tab === t.id ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setTab(t.id)} type="button">
            {t.label}
          </button>
        ))}
      </div>

      {/* RECURRING */}
      {tab === 'recurring' && (
        <div className="stack">
          <div className="glass-panel">
            <h3 style={{ marginBottom: 16 }}>Add Recurring Expense</h3>
            <form className="form-grid" onSubmit={handleAddRecurring}>
              <div className="form-group">
                <label className="form-label">Amount (₹)</label>
                <input className="form-input" type="number" min="1" required
                  value={recAmount} onChange={(e) => setRecAmount(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Category</label>
                <select className="form-select" value={recCategory} onChange={(e) => setRecCategory(e.target.value as ExpenseCategory)}>
                  {EXPENSE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Frequency</label>
                <select className="form-select" value={recFreq} onChange={(e) => setRecFreq(e.target.value as RecurrenceFrequency)}>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Next Due</label>
                <input className="form-input" type="date" value={recDue} onChange={(e) => setRecDue(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Merchant</label>
                <input className="form-input" value={recMerchant} onChange={(e) => setRecMerchant(e.target.value)}
                  placeholder="e.g. Netflix" />
              </div>
              <div className="form-group">
                <button className="btn btn-primary" type="submit">Add Recurring</button>
              </div>
            </form>
          </div>

          <div className="glass-panel">
            <h3 style={{ marginBottom: 16 }}>Active Recurring ({recurring.length})</h3>
            {recurring.length === 0 ? (
              <p style={{ color: 'var(--text-tertiary)' }}>No recurring entries yet.</p>
            ) : (
              <div className="stack" style={{ gap: 8 }}>
                {recurring.map((r) => (
                  <div key={r.id} className="timeline-item">
                    <div>
                      <strong style={{ textTransform: 'capitalize' }}>{r.category}</strong>
                      {r.merchant && <span style={{ marginLeft: 8, color: 'var(--text-tertiary)' }}>({r.merchant})</span>}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span>₹{r.amount} / {r.frequency}</span>
                      <button className="btn btn-danger btn-sm" onClick={() => handleDeleteRecurring(r.id)} type="button">
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* SIMULATION */}
      {tab === 'simulation' && (
        <div className="stack">
          <div className="glass-panel">
            <h3 style={{ marginBottom: 16 }}>What-If Simulator</h3>
            <form className="form-grid" onSubmit={handleSimulation}>
              <div className="form-group">
                <label className="form-label">Lookback (days)</label>
                <input className="form-input" type="number" value={simLookback} onChange={(e) => setSimLookback(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Horizon (days)</label>
                <input className="form-input" type="number" value={simHorizon} onChange={(e) => setSimHorizon(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Food Adj (%)</label>
                <input className="form-input" type="number" step="0.05" value={simFood} onChange={(e) => setSimFood(e.target.value)} placeholder="-0.2 = -20%" />
              </div>
              <div className="form-group">
                <label className="form-label">Entertainment Adj (%)</label>
                <input className="form-input" type="number" step="0.05" value={simEnt} onChange={(e) => setSimEnt(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Shopping Adj (%)</label>
                <input className="form-input" type="number" step="0.05" value={simShop} onChange={(e) => setSimShop(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Extra Income (₹)</label>
                <input className="form-input" type="number" value={simIncome} onChange={(e) => setSimIncome(e.target.value)} />
              </div>
              <div className="form-group">
                <button className="btn btn-primary" type="submit">Run Simulation</button>
              </div>
            </form>
          </div>

          {simResult && (
            <div className="glass-panel">
              <h3 style={{ marginBottom: 16 }}>Results</h3>
              <div className="grid-4" style={{ marginBottom: 16 }}>
                <div className="metric-card" style={{ padding: 14 }}>
                  <div className="metric-label" style={{ fontSize: 11 }}>Baseline End</div>
                  <div className="metric-value" style={{ fontSize: 20 }}>₹{simResult.baseline_end_balance.toFixed(0)}</div>
                </div>
                <div className="metric-card" style={{ padding: 14 }}>
                  <div className="metric-label" style={{ fontSize: 11 }}>Adjusted End</div>
                  <div className="metric-value" style={{ fontSize: 20 }}>₹{simResult.adjusted_end_balance.toFixed(0)}</div>
                </div>
                <div className="metric-card" style={{ padding: 14 }}>
                  <div className="metric-label" style={{ fontSize: 11 }}>Delta</div>
                  <div className="metric-value" style={{ fontSize: 20, color: simResult.balance_delta >= 0 ? '#5cd6a0' : '#f5695b' }}>
                    {simResult.balance_delta >= 0 ? '+' : ''}₹{simResult.balance_delta.toFixed(0)}
                  </div>
                </div>
                <div className="metric-card" style={{ padding: 14 }}>
                  <div className="metric-label" style={{ fontSize: 11 }}>Risk Change</div>
                  <div className="metric-value" style={{ fontSize: 20 }}>
                    {Math.round(simResult.baseline_risk_score * 100)}% → {Math.round(simResult.adjusted_risk_score * 100)}%
                  </div>
                </div>
              </div>
              <ul style={{ listStyle: 'none' }}>
                {simResult.key_takeaways.map((t: string, i: number) => (
                  <li key={i} style={{ padding: '6px 0', color: 'var(--text-secondary)', fontSize: 14 }}>• {t}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* EXPORT */}
      {tab === 'export' && (
        <div className="glass-panel" style={{ textAlign: 'center', padding: 48 }}>
          <p style={{ fontSize: 48, marginBottom: 16 }}>📥</p>
          <h3 style={{ marginBottom: 12 }}>Export Your Data</h3>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 24 }}>
            Download all your expenses and income as a CSV file.
          </p>
          <a href={exportCsv(participantId)} className="btn btn-primary" download>
            Download CSV
          </a>
        </div>
      )}

      {/* SURVEY */}
      {tab === 'survey' && (
        <div className="glass-panel">
          <h3 style={{ marginBottom: 20 }}>Behavior Survey</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 24 }}>
            This helps the AI understand your spending triggers and give better advice.
          </p>
          <form className="stack" onSubmit={handleSurvey}>
            <div className="form-group">
              <label className="form-label">Stress Spending Tendency</label>
              <StarPicker value={survStress} onChange={setSurvStress} />
            </div>
            <div className="form-group">
              <label className="form-label">Social Pressure Spending</label>
              <StarPicker value={survSocial} onChange={setSurvSocial} />
            </div>
            <div className="form-group">
              <label className="form-label">Boredom Spending</label>
              <StarPicker value={survBoredom} onChange={setSurvBoredom} />
            </div>
            <div className="form-group">
              <label className="form-label">Planning Confidence</label>
              <StarPicker value={survPlanning} onChange={setSurvPlanning} />
            </div>
            <div className="form-group">
              <label className="form-label">Your Biggest Spending Trigger</label>
              <textarea className="form-textarea" rows={3} value={survTrigger}
                onChange={(e) => setSurvTrigger(e.target.value)}
                placeholder="e.g. I tend to order food when stressed about exams" />
            </div>
            <button className="btn btn-primary" type="submit">Save Survey</button>
          </form>
        </div>
      )}

      {/* ALLOCATIONS (BUDGET PLANNING) */}
      {tab === 'allocations' && (
        <div className="glass-panel">
          <h3 style={{ marginBottom: 16 }}>💰 Budget Planning</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 24 }}>
            Set your total monthly budget and distribute it across categories. 
            Adjusting a category will automatically balance others to keep the total constant. 
            Non-essential categories are reduced first.
          </p>

          <div style={{ marginBottom: 32, padding: 16, background: 'rgba(255,255,255,0.05)', borderRadius: 12 }}>
            <label className="form-label" style={{ fontWeight: 700, fontSize: 16 }}>Total Monthly Budget (₹)</label>
            <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
              <input 
                className="form-input" 
                type="number" 
                value={allocTotal} 
                onChange={(e) => setAllocTotal(parseInt(e.target.value) || 0)}
                style={{ fontSize: 18, fontWeight: 700 }}
              />
              <button 
                className="btn btn-primary"
                onClick={async () => {
                  if (!participantId) return;
                  try {
                    await updateParticipant(participantId, { monthly_budget: allocTotal });
                    // Proportionally scale categories if total changed significantly? 
                    // For now just save the total.
                    flash('✅ Total budget updated!');
                  } catch { flash('❌ Failed to update total'); }
                }}
              >
                Save Total
              </button>
            </div>
          </div>

          <div className="stack" style={{ gap: 20 }}>
            {['rent', 'food', 'travel', 'utilities', 'health', 'entertainment', 'shopping'].map((cat) => (
              <div key={cat} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <button 
                      type="button"
                      style={{ 
                        background: 'none', 
                        border: 'none', 
                        cursor: 'pointer', 
                        padding: 0, 
                        fontSize: 14,
                        opacity: lockedCats.has(cat) ? 1 : 0.4 
                      }}
                      onClick={() => {
                        setLockedCats(prev => {
                          const next = new Set(prev);
                          if (next.has(cat)) next.delete(cat);
                          else next.add(cat);
                          return next;
                        });
                      }}
                    >
                      {lockedCats.has(cat) ? '🔒' : '🔓'}
                    </button>
                    <strong style={{ textTransform: 'capitalize' }}>{cat}</strong>
                  </div>
                  <span>₹{allocations[cat] ? Math.round(allocations[cat]) : 0}</span>
                </div>
                <input 
                  type="range" 
                  min="0" 
                  max={allocTotal} 
                  step="50"
                  value={allocations[cat] || 0}
                  onChange={(e) => handleAllocationChange(cat, parseInt(e.target.value))}
                  style={{ width: '100%', accentColor: 'var(--primary-color)' }}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SYSTEM */}
      {tab === 'system' && (
        <div className="glass-panel" style={{ textAlign: 'center', padding: 48 }}>
          <p style={{ fontSize: 48, marginBottom: 16 }}>🚀</p>
          <h3 style={{ marginBottom: 12 }}>App Experience</h3>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 24, maxWidth: 500, marginInline: 'auto' }}>
            The "Thrilling Experience" (intro scroll) is designed to be seen only once. 
            If you'd like to experience it again, use the button below.
          </p>
          <button 
            className="btn btn-primary" 
            onClick={() => {
              localStorage.removeItem('bbt_seen_thrill');
              window.location.reload();
            }}
          >
            Replay Intro Animation
          </button>
        </div>
      )}
    </div>
  );
}
