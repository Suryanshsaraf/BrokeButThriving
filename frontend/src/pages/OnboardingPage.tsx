import { useState } from 'react';
import type { LivingSituation, DietPreference } from '../types/api';
import { createParticipant } from '../lib/api';

/* ============================================================
   Onboarding Page — beautiful step-by-step first-time setup
   ============================================================ */

interface Props {
  onComplete: (participantId: string) => void;
}

export default function OnboardingPage({ onComplete }: Props) {
  const [step, setStep] = useState(1);
  const [status, setStatus] = useState('');

  const [code, setCode] = useState('');
  const [firstName, setFirstName] = useState('');
  const [age, setAge] = useState('');
  const [institution, setInstitution] = useState('');
  const [course, setCourse] = useState('');
  const [living, setLiving] = useState<LivingSituation>('hostel');
  const [diet, setDiet] = useState<DietPreference>('veg');
  const [budget, setBudget] = useState('');
  const [income, setIncome] = useState('0');
  const [balance, setBalance] = useState('0');

  const handleSubmit = async () => {
    try {
      const p = await createParticipant({
        participant_code: code,
        first_name: firstName || undefined,
        age: age ? Number(age) : undefined,
        institution: institution || undefined,
        course_name: course || undefined,
        living_situation: living,
        dietary_preference: diet,
        monthly_budget: Number(budget),
        monthly_income: Number(income),
        starting_balance: Number(balance),
      });
      onComplete(p.id);
    } catch (err: any) {
      let msg = 'Please check your inputs and try again.';
      if (err instanceof Error) {
        const text = err.message;
        if (text.includes('409') || text.includes('already exists')) {
          msg = 'That Participant Code is already taken! Try adding some numbers to it.';
        } else if (text.includes('502') || text.includes('Failed to fetch')) {
          msg = 'The backend server is offline or restarting. Please wait a moment and try again.';
        } else if (text.includes('422')) {
          msg = 'Some of your details are invalid. Ensure all fields are correctly filled out.';
        } else {
          msg = 'An unexpected error occurred. Please try again.';
        }
      }
      setStatus(`❌ ${msg}`);
    }
  };

  const canNext = () => {
    if (step === 1) return code.length >= 3;
    if (step === 2) return true;
    if (step === 3) return Number(budget) > 0;
    return true;
  };

  return (
    <div className="onboarding-container">
      <div className="onboarding-card">
        <div className="glass-panel">
          <div className="onboarding-header">
            <div className="onboarding-icon">💰</div>
            <h2>BrokeButThriving</h2>
            <p>Let's set up your financial profile • Step {step} of 3</p>
          </div>

          {/* Progress bar */}
          <div style={{ height: 4, borderRadius: 2, background: 'var(--bg-input)', marginBottom: 32, overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 2, background: 'var(--gradient-accent)',
              width: `${(step / 3) * 100}%`, transition: 'width 0.5s ease',
            }} />
          </div>

          {status && (
            <div style={{ marginBottom: 16, padding: '10px 16px', borderRadius: 'var(--radius-md)', background: 'rgba(245,105,91,0.1)', border: '1px solid rgba(245,105,91,0.3)', fontSize: 14 }}>
              {status}
            </div>
          )}

          {/* Step 1: Identity */}
          {step === 1 && (
            <div className="stack">
              <div className="form-group">
                <label className="form-label">Participant Code *</label>
                <input className="form-input" value={code} onChange={(e) => setCode(e.target.value)}
                  placeholder="e.g. riya_23" minLength={3} />
              </div>
              <div className="form-group">
                <label className="form-label">First Name</label>
                <input className="form-input" value={firstName} onChange={(e) => setFirstName(e.target.value)}
                  placeholder="Your first name" />
              </div>
              <div className="form-group">
                <label className="form-label">Age</label>
                <input className="form-input" type="number" min="16" max="35" value={age} onChange={(e) => setAge(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Institution</label>
                <input className="form-input" value={institution} onChange={(e) => setInstitution(e.target.value)}
                  placeholder="University or college name" />
              </div>
              <div className="form-group">
                <label className="form-label">Course</label>
                <input className="form-input" value={course} onChange={(e) => setCourse(e.target.value)}
                  placeholder="e.g. B.Tech CSE" />
              </div>
            </div>
          )}

          {/* Step 2: Lifestyle */}
          {step === 2 && (
            <div className="stack">
              <div className="form-group">
                <label className="form-label">Living Situation</label>
                <select className="form-select" value={living} onChange={(e) => setLiving(e.target.value as LivingSituation)}>
                  <option value="hostel">Hostel</option>
                  <option value="pg">PG</option>
                  <option value="rental">Shared Flat / Alone</option>
                  <option value="with_family">With Family</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Diet Preference</label>
                <select className="form-select" value={diet} onChange={(e) => setDiet(e.target.value as DietPreference)}>
                  <option value="veg">Vegetarian</option>
                  <option value="non_veg">Non-Vegetarian</option>
                  <option value="vegan">Vegan</option>
                  <option value="eggetarian">Eggetarian</option>
                </select>
              </div>
            </div>
          )}

          {/* Step 3: Finances */}
          {step === 3 && (
            <div className="stack">
              <div className="form-group">
                <label className="form-label">Monthly Budget (₹) *</label>
                <input className="form-input" type="number" min="1" required
                  value={budget} onChange={(e) => setBudget(e.target.value)}
                  placeholder="How much can you spend per month?" />
              </div>
              <div className="form-group">
                <label className="form-label">Monthly Income (₹)</label>
                <input className="form-input" type="number" value={income}
                  onChange={(e) => setIncome(e.target.value)}
                  placeholder="Allowance, part-time, etc." />
              </div>
              <div className="form-group">
                <label className="form-label">Current Balance (₹)</label>
                <input className="form-input" type="number" value={balance}
                  onChange={(e) => setBalance(e.target.value)}
                  placeholder="How much do you have right now?" />
              </div>
            </div>
          )}

          {/* Navigation */}
          <div style={{ display: 'flex', justifyContent: step > 1 ? 'space-between' : 'flex-end', marginTop: 32 }}>
            {step > 1 && (
              <button className="btn btn-secondary" onClick={() => setStep(step - 1)} type="button">← Back</button>
            )}
            {step < 3 ? (
              <button className="btn btn-primary" onClick={() => setStep(step + 1)} disabled={!canNext()} type="button">
                Next →
              </button>
            ) : (
              <button className="btn btn-primary" onClick={handleSubmit} disabled={!canNext()} type="button">
                🚀 Get Started
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
