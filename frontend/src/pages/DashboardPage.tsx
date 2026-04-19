import { useEffect, useState } from 'react';
import type {
  AlertItem, DashboardSummary, ExpenseEntryRead, CashflowEntryRead,
  GamificationSummary, SemesterProjectionResponse, MLInsightsResponse,
} from '../types/api';
import {
  getDashboard, getAlerts, listExpenses, listCashflows, getGamification,
  getSemesterProjection, getMLInsights,
} from '../lib/api';
import { MagicBento, BentoCard } from '../components/MagicBento/MagicBento';
import MLInsightsCard from '../components/MLInsightsCard/MLInsightsCard';

import './DashboardPage.css';

/* ============================================================
   Dashboard Page — budget ring, metrics, alerts, recent activity
   ============================================================ */

interface Props {
  participantId: string | null;
  dataVersion?: number;
}

export default function DashboardPage({ participantId, dataVersion = 0 }: Props) {
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [expenses, setExpenses] = useState<ExpenseEntryRead[]>([]);
  const [cashflows, setCashflows] = useState<CashflowEntryRead[]>([]);
  const [gamification, setGamification] = useState<GamificationSummary | null>(null);
  const [projection, setProjection] = useState<SemesterProjectionResponse | null>(null);
  const [mlInsights, setMlInsights] = useState<MLInsightsResponse | null>(null);
  const [mlLoading, setMlLoading] = useState(false);

  useEffect(() => {
    if (!participantId) return;
    getDashboard(participantId).then(setDashboard).catch(console.error);
    getAlerts(participantId).then(setAlerts).catch(console.error);
    listExpenses(participantId, 10).then(setExpenses).catch(console.error);
    listCashflows(participantId, 10).then(setCashflows).catch(console.error);
    getGamification(participantId).then(setGamification).catch(console.error);
    getSemesterProjection(participantId).then(setProjection).catch(console.error);
    setMlLoading(true);
    getMLInsights(participantId)
      .then(setMlInsights)
      .catch(console.error)
      .finally(() => setMlLoading(false));
  }, [participantId, dataVersion]);

  if (!participantId) {
    return (
      <div className="empty-state">
        <p className="empty-state-icon">📊</p>
        <h3>Select a participant</h3>
        <p>Choose a participant from the sidebar or create a new one in Settings.</p>
      </div>
    );
  }

  // Budget ring SVG
  const radius = 75;
  const circumference = 2 * Math.PI * radius;
  const pct = dashboard ? Math.min(dashboard.budget_used_pct, 100) : 0;
  const offset = circumference - (pct / 100) * circumference;
  const ringColor =
    pct >= 100 ? '#f5695b' :
    pct >= 80 ? '#f5a65b' :
    pct >= 60 ? '#f5d05b' : '#5cd6a0';



  return (
    <div className="dashboard-container">
      <div className="page-header">
        <h2>Dashboard</h2>
        <p>Your financial overview at a glance</p>
      </div>

      <MagicBento>
        {/* Row 1: Key Metrics */}
        <BentoCard title="Current Balance" span="small">
          <div className="metric-value big" style={{ color: (dashboard?.current_balance ?? 0) >= 0 ? '#5cd6a0' : '#f5695b' }}>
            ₹{dashboard?.current_balance.toFixed(0) ?? '0'}
          </div>
        </BentoCard>

        <BentoCard title="Tactical Outlook" subtitle="Dynamic safe limits vs Real-time burn" span="medium">
          <div className="stack" style={{ gap: 16, marginTop: 12 }}>
            {/* Today */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span className="metric-subtitle">Today's Allowance</span>
                <span className={`metric-value small ${dashboard && dashboard.today_spend > dashboard.target_daily_budget ? 'text-red' : 'text-green'}`}>
                  ₹{dashboard?.today_spend.toFixed(0) ?? '0'} / ₹{dashboard?.target_daily_budget.toFixed(0) || '0'}
                </span>
              </div>
              <div className="progress-bar-premium">
                <div 
                  className="progress-fill" 
                  style={{ 
                    width: `${Math.min(100, dashboard ? (dashboard.today_spend / (dashboard.target_daily_budget || 1)) * 100 : 0)}%`,
                    background: dashboard && dashboard.today_spend > dashboard.target_daily_budget ? 'var(--accent-red)' : 'linear-gradient(90deg, var(--accent-green), #81e6b9)'
                  }} 
                />
              </div>
            </div>

            {/* Week */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span className="metric-subtitle">Weekly Capacity</span>
                <span className={`metric-value small ${dashboard && dashboard.current_week_spend > dashboard.target_weekly_budget ? 'text-gold' : 'text-green'}`}>
                  ₹{dashboard?.current_week_spend.toFixed(0) ?? '0'} / ₹{dashboard?.target_weekly_budget.toFixed(0) || '0'}
                </span>
              </div>
              <div className="progress-bar-premium">
                <div 
                  className="progress-fill" 
                  style={{ 
                    width: `${Math.min(100, dashboard ? (dashboard.current_week_spend / (dashboard.target_weekly_budget || 1)) * 100 : 0)}%`,
                    background: dashboard && dashboard.current_week_spend > dashboard.target_weekly_budget ? 'var(--accent-gold)' : 'var(--accent-green)'
                  }} 
                />
              </div>
            </div>

            {/* Velocity Indicator */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 8 }}>
              <div style={{ fontSize: '1.2rem' }}>
                {dashboard && dashboard.today_spend > dashboard.target_daily_budget ? '⚠️' : '✅'}
              </div>
              <div style={{ fontSize: 11, lineHeight: 1.3 }}>
                {dashboard && dashboard.today_spend > dashboard.target_daily_budget 
                  ? "Velocity is high. Your EOM runway is shrinking."
                  : "Spending velocity is stable. You're maintaining runway."}
              </div>
            </div>
          </div>
        </BentoCard>

        <BentoCard title="Risk Score" span="small">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="metric-value" style={{
              color: dashboard?.risk_band === 'critical' ? '#f5695b'
                : dashboard?.risk_band === 'elevated' ? '#f5a65b'
                : dashboard?.risk_band === 'watch' ? '#f5d05b' : '#5cd6a0'
            }}>
              {dashboard ? Math.round(dashboard.risk_score * 100) : 0}%
            </div>
            {dashboard && (
              <span className={`risk-badge risk-${dashboard.risk_band}`}>
                {dashboard.risk_band === 'critical' ? '🚨' : dashboard.risk_band === 'elevated' ? '⚠️' : dashboard.risk_band === 'watch' ? '🟡' : '✅'} {dashboard.risk_band}
              </span>
            )}
            {dashboard && (
              <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Runway</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: (dashboard.projected_days_remaining ?? 0) >= (dashboard as any).days_left ? '#5cd6a0' : '#f5695b' }}>
                  {dashboard.projected_days_remaining === 99 ? '∞ days' : `${dashboard.projected_days_remaining}d left`}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                  Burn rate: ₹{dashboard.average_daily_spend_14d.toFixed(0)}/day
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                  Safe limit: ₹{dashboard.target_daily_budget.toFixed(0)}/day
                </div>
              </div>
            )}
          </div>
        </BentoCard>

        <BentoCard title="Savings Potential" span="small">
          {(() => {
            const income = dashboard?.current_month_inflow || 0;
            const spend = dashboard?.current_month_spend || 0;
            const potential = Math.max(0, income - spend);
            return (
              <>
                <div className="metric-value" style={{ color: '#5cd6a0' }}>₹{potential.toFixed(0)}</div>
                <div className="metric-subtitle">Left from Income</div>
              </>
            );
          })()}
        </BentoCard>

        {projection && expenses.length === 0 && (
          <BentoCard title="Day 0 Forecast 🔮" span="large">
            <div style={{ background: 'rgba(92, 214, 160, 0.1)', padding: 12, borderRadius: 8, marginBottom: 8 }}>
              <p style={{ fontSize: 13, marginBottom: 4 }}>
                <strong>No expenses yet!</strong> We ran a baseline predictive model against 12,000 real student profiles based on your living situation and budget.
              </p>
              <div className="metric-value small" style={{ color: 'var(--accent-green)' }}>
                ₹{projection.projected_end_balance.toFixed(0)} <span style={{ fontSize: 12, opacity: 0.6, fontWeight: 'normal' }}>projected EOM</span>
              </div>
            </div>
            <ul style={{ paddingLeft: 20, fontSize: 12, opacity: 0.9, lineHeight: 1.5 }}>
              {projection.recommendations.map((rec, i) => (
                <li key={i}>{rec}</li>
              ))}
            </ul>
          </BentoCard>
        )}

        {/* Row 2: Visual Insights */}
        <BentoCard title="Budget Health" span="large">
          <div className="budget-ring-container bento-center">
            <div className="budget-ring-wrapper">
              <svg className="budget-ring-svg" width="180" height="180" viewBox="0 0 180 180">
                <circle className="budget-ring-bg" cx="90" cy="90" r={radius} />
                <circle
                  className="budget-ring-fill"
                  cx="90" cy="90" r={radius}
                  stroke={ringColor}
                  strokeDasharray={circumference}
                  strokeDashoffset={offset}
                />
              </svg>
              <div className="budget-ring-center">
                <div className="budget-ring-pct" style={{ color: ringColor }}>{pct.toFixed(0)}%</div>
                <div className="budget-ring-label">Used</div>
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
                ₹{dashboard?.budget_remaining.toFixed(0) ?? '0'} remaining
              </div>
            </div>
          </div>
        </BentoCard>

        <BentoCard title="Smart Alerts" span="tall">
          <div className="stack" style={{ gap: 12 }}>
            {alerts.length > 0 ? alerts.map((a) => (
              <div key={a.id} className={`alert-card alert-${a.severity}`} style={{ padding: '12px' }}>
                <span className="alert-icon" style={{ fontSize: '16px' }}>{a.icon}</span>
                <div className="alert-body">
                  <h4 style={{ fontSize: '13px' }}>{a.title}</h4>
                </div>
              </div>
            )) : (
              <p style={{ opacity: 0.4, fontSize: '13px' }}>No active alerts. You're doing great!</p>
            )}
          </div>
        </BentoCard>

        <BentoCard title="Category Budgets" span="tall">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {(() => {
              const savedAlloc = localStorage.getItem(`bbt_alloc_${participantId}`);
              const allocations = savedAlloc ? JSON.parse(savedAlloc) : {};
              
              // We want to show all core categories, even if spend is 0, if they have a budget
              const cats = ['food', 'travel', 'utilities', 'health', 'entertainment', 'shopping'];
              
              return cats.map((cat) => {
                const spend = dashboard?.top_categories.find(c => c.category === cat)?.total_spend || 0;
                const budget = allocations[cat] || 0;
                const pctUsed = budget > 0 ? (spend / budget) * 100 : 0;
                const barColor = pctUsed >= 100 ? '#f5695b' : pctUsed >= 80 ? '#f5a65b' : 'var(--accent-green)';

                return (
                  <div key={cat}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                      <strong style={{ textTransform: 'capitalize' }}>{cat}</strong>
                      <span style={{ opacity: 0.8 }}>
                        ₹{Math.round(spend)} / <span style={{ color: 'var(--text-tertiary)' }}>₹{Math.round(budget)}</span>
                      </span>
                    </div>
                    <div className="progress-bar-subtle">
                      <div 
                        className="progress-fill" 
                        style={{ 
                          width: `${Math.min(100, pctUsed)}%`,
                          background: barColor,
                          boxShadow: pctUsed >= 100 ? '0 0 10px rgba(245, 105, 91, 0.3)' : 'none'
                        }} 
                      />
                    </div>
                  </div>
                );
              });
            })()}
          </div>
        </BentoCard>

        {/* Row 3: Insights & Achievements */}
        <BentoCard title="AI Copilot Insights" span="medium">
          <div className="stack" style={{ gap: 8, overflowY: 'auto', maxHeight: 220 }}>
            {dashboard?.short_term_forecasts.map((m, i) => (
              <div key={`st-${i}`} style={{
                padding: '8px 12px',
                background: 'rgba(245, 166, 91, 0.08)',
                borderLeft: '3px solid var(--accent-orange)',
                borderRadius: 6,
                fontSize: 12,
                lineHeight: 1.5,
              }}>
                ⚡ {m}
              </div>
            ))}
            {dashboard?.highlight_messages.map((m, i) => {
              const isWarning = m.includes('🚨') || m.includes('⚠️') || m.includes('🔴');
              const isGood = m.includes('✅') || m.includes('💚') || m.includes('💪') || m.includes('✨');
              const borderColor = isWarning ? 'var(--accent-red)' : isGood ? 'var(--accent-green)' : 'var(--border-medium)';
              const bg = isWarning ? 'rgba(245,105,91,0.06)' : isGood ? 'rgba(92,214,160,0.06)' : 'rgba(255,255,255,0.02)';
              return (
                <div key={`hi-${i}`} style={{
                  padding: '8px 12px',
                  background: bg,
                  borderLeft: `3px solid ${borderColor}`,
                  borderRadius: 6,
                  fontSize: 12,
                  lineHeight: 1.5,
                }}>
                  {m}
                </div>
              );
            })}
            {(!dashboard?.short_term_forecasts?.length && !dashboard?.highlight_messages?.length) && (
              <div style={{ fontSize: 12, opacity: 0.4, paddingTop: 8 }}>
                Log expenses and check-ins to unlock AI Copilot insights.
              </div>
            )}
          </div>
        </BentoCard>

        <BentoCard title="Recovery Strategy 🛠️" span="medium" subtitle="Tactical adjustments to regain financial health">
          <div className="stack" style={{ gap: 10, overflowY: 'auto', maxHeight: 220 }}>
            {dashboard?.recovery_plan && dashboard.recovery_plan.length > 0 ? (
              dashboard.recovery_plan.map((step, i) => (
                <div key={i} style={{ 
                  padding: '12px 14px', 
                  background: 'rgba(245, 105, 91, 0.05)', 
                  border: '1px solid rgba(245, 105, 91, 0.1)',
                  borderRadius: 12,
                  fontSize: 12.5,
                  lineHeight: 1.5,
                  color: 'rgba(255,255,255,0.95)',
                  display: 'flex',
                  gap: 12,
                  animation: 'fadeIn 0.3s ease forwards'
                }}>
                  <div style={{ flexShrink: 0, fontSize: 18, alignSelf: 'flex-start' }}>
                    {step.includes('🚨') ? '🚨' : step.includes('💪') ? '💪' : step.includes('🧘') ? '🧘' : step.includes('✂️') ? '✂️' : step.includes('🚩') ? '🚩' : '⚡'}
                  </div>
                  <div>{step.replace(/^[🚨💪🧘✂️🚩]\s*/, '')}</div>
                </div>
              ))
            ) : (
              <div style={{ 
                height: 140, 
                display: 'flex', 
                flexDirection: 'column', 
                alignItems: 'center', 
                justifyContent: 'center', 
                opacity: 0.4, 
                fontSize: 13,
                textAlign: 'center'
              }}>
                <div style={{ fontSize: 32, marginBottom: 12 }}>🛡️</div>
                Everything is stable.<br/>No recovery actions needed!
              </div>
            )}
          </div>
        </BentoCard>

        <BentoCard title="Achievements" span="small">
          {gamification && (
            <div style={{ display: 'flex', gap: 20, alignItems: 'center', height: '100%' }}>
              <div className="p-avatar big" style={{ width: 60, height: 60, fontSize: '2rem' }}>
                {gamification.no_spend_streak > 3 ? '🔥' : '🏆'}
              </div>
              <div>
                <div className="metric-value small">{gamification.no_spend_streak} Day Streak</div>
                <div className="metric-subtitle">{gamification.under_budget_days} Days Under Budget</div>
              </div>
            </div>
          )}
        </BentoCard>

        <BentoCard title="Active Challenges 🎯" span="medium">
          <div className="stack" style={{ gap: 8, height: '100%', overflowY: 'auto', paddingRight: '4px' }}>
            {gamification?.active_challenges && gamification.active_challenges.length > 0 ? (
              gamification.active_challenges.map(c => (
                <div key={c.id} style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 8, borderLeft: '3px solid var(--accent-green)' }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{c.title}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2, marginBottom: 6 }}>{c.description}</div>
                  <div className="progress-bar-subtle" style={{ height: 4 }}>
                    <div className="progress-fill" style={{ width: `${Math.min(c.progress_pct, 100)}%`, background: 'var(--accent-green)' }} />
                  </div>
                  <div style={{ fontSize: 10, textAlign: 'right', marginTop: 4, opacity: 0.5 }}>₹{c.target_value.toFixed(0)} Goal</div>
                </div>
              ))
            ) : (
              <div style={{ fontSize: 13, opacity: 0.5, paddingTop: 10 }}>No active challenges. Ask the AI Copilot to set a saving goal!</div>
            )}
          </div>
        </BentoCard>

        {/* Row 4: ML Intelligence */}
        <BentoCard title="AI Intelligence" subtitle="Model-powered scoring from 380K+ survey records" span="full">
          <MLInsightsCard data={mlInsights} loading={mlLoading} />
        </BentoCard>

        {/* Row 5: Timeline */}
        <BentoCard title="Recent Activity" span="full">
          <div className="horizontal-timeline">
            {[...expenses.slice(0, 3), ...cashflows.slice(0, 2)].map((item: any, idx) => (
              <div key={idx} className={`timeline-capsule ${'amount' in item && 'participant_id' in item ? '' : 'cashflow'}`}>
                <strong>{item.category}</strong>
                <span>₹{item.amount.toFixed(0)}</span>
              </div>
            ))}
          </div>
        </BentoCard>
      </MagicBento>
    </div>
  );
}
