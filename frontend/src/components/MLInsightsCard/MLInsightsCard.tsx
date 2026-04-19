import type { MLInsightsResponse } from '../../types/api';
import './MLInsightsCard.css';

interface Props {
  data: MLInsightsResponse | null;
  loading?: boolean;
}

// ── Archetype config ───────────────────────────────────────────────────────
const ARCHETYPE_META: Record<string, { emoji: string; label: string; color: string }> = {
  stress:           { emoji: '😰', label: 'Stress Spender',   color: '#f5695b' },
  social_pressure:  { emoji: '🎉', label: 'Social Spender',   color: '#a78bfa' },
  boredom:          { emoji: '😑', label: 'Boredom Spender',  color: '#f5a65b' },
  balanced:         { emoji: '⚖️', label: 'Balanced Spender', color: '#5cd6a0' },
};

// ── Band color helpers ─────────────────────────────────────────────────────
const WELLBEING_COLORS: Record<string, string> = {
  excellent: '#5cd6a0',
  good:      '#81e6b9',
  moderate:  '#f5d05b',
  low:       '#f5695b',
};

const RISK_COLORS: Record<string, string> = {
  low:      '#5cd6a0',
  moderate: '#f5d05b',
  high:     '#f5a65b',
  critical: '#f5695b',
};

// ── Radial gauge ─────────────────────────────────────────────────────────────
function RadialGauge({ value, max = 100, color, label, sublabel }: {
  value: number; max?: number; color: string; label: string; sublabel?: string;
}) {
  const r = 36;
  const circ = 2 * Math.PI * r;
  const pct = Math.min(value / max, 1);
  const offset = circ * (1 - pct);

  return (
    <div className="ml-gauge">
      <svg viewBox="0 0 90 90" width={90} height={90}>
        <circle cx={45} cy={45} r={r} className="ml-gauge-bg" />
        <circle
          cx={45} cy={45} r={r}
          className="ml-gauge-fill"
          stroke={color}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          transform="rotate(-90 45 45)"
        />
      </svg>
      <div className="ml-gauge-center">
        <span className="ml-gauge-value" style={{ color }}>{label}</span>
        {sublabel && <span className="ml-gauge-sub">{sublabel}</span>}
      </div>
    </div>
  );
}

// ── Risk bar ──────────────────────────────────────────────────────────────────
function RiskBar({ label, value, band, color }: {
  label: string; value: number; band: string; color: string;
}) {
  return (
    <div className="ml-risk-row">
      <div className="ml-risk-header">
        <span className="ml-risk-label">{label}</span>
        <span className="ml-risk-badge" style={{ background: `${color}22`, color, border: `1px solid ${color}44` }}>
          {band}
        </span>
      </div>
      <div className="ml-risk-track">
        <div
          className="ml-risk-fill"
          style={{
            width: `${Math.round(value * 100)}%`,
            background: `linear-gradient(90deg, ${color}99, ${color})`,
            boxShadow: `0 0 8px ${color}44`,
          }}
        />
      </div>
      <span className="ml-risk-pct">{Math.round(value * 100)}%</span>
    </div>
  );
}

// ── Ratio pill ────────────────────────────────────────────────────────────────
function RatioPill({ label, value, threshold, fmt = 'pct' }: {
  label: string; value: number; threshold: number; fmt?: 'pct' | 'ratio';
}) {
  const over = value > threshold;
  const color = over ? '#f5695b' : '#5cd6a0';
  const display = fmt === 'pct' ? `${Math.round(value * 100)}%` : `${value.toFixed(2)}×`;
  return (
    <div className="ml-pill" style={{ borderColor: `${color}40` }}>
      <span className="ml-pill-label">{label}</span>
      <span className="ml-pill-value" style={{ color }}>{display}</span>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MLInsightsCard({ data, loading }: Props) {
  if (loading) {
    return (
      <div className="ml-card ml-loading">
        <div className="ml-shimmer" />
        <div className="ml-shimmer short" />
        <div className="ml-shimmer" />
      </div>
    );
  }

  if (!data || !data.model_available) {
    return (
      <div className="ml-card ml-unavailable">
        <span className="ml-unavail-icon">🧠</span>
        <p className="ml-unavail-text">
          ML models not yet loaded. Train the models and restart the server to enable AI scoring.
        </p>
      </div>
    );
  }

  const archetype = data.spending_archetype
    ? ARCHETYPE_META[data.spending_archetype] ?? ARCHETYPE_META.balanced
    : null;

  const wbColor = data.wellbeing_band ? WELLBEING_COLORS[data.wellbeing_band] : '#5cd6a0';
  const hrColor = data.hardship_band  ? RISK_COLORS[data.hardship_band]        : '#5cd6a0';
  const bdColor = data.bill_difficulty_band ? RISK_COLORS[data.bill_difficulty_band] : '#5cd6a0';

  return (
    <div className="ml-card">
      {/* Header */}
      <div className="ml-header">
        <span className="ml-badge">🤖 AI Scoring</span>
        <span className="ml-hint">Powered by trained ML models</span>
      </div>

      {/* Top row: Wellbeing gauge + Archetype */}
      <div className="ml-top-row">
        {/* Wellbeing Score */}
        <div className="ml-wellbeing">
          {data.wellbeing_score !== null && (
            <RadialGauge
              value={data.wellbeing_score}
              max={100}
              color={wbColor}
              label={`${Math.round(data.wellbeing_score)}`}
              sublabel={data.wellbeing_band ?? ''}
            />
          )}
          <div className="ml-wellbeing-label">
            <span className="ml-section-title">Wellbeing</span>
            <span className="ml-section-sub">Financial health score</span>
          </div>
        </div>

        {/* Divider */}
        <div className="ml-vdivider" />

        {/* Archetype */}
        {archetype && (
          <div className="ml-archetype">
            <div className="ml-archetype-emoji" style={{ background: `${archetype.color}18`, border: `1px solid ${archetype.color}30` }}>
              {archetype.emoji}
            </div>
            <div>
              <div className="ml-archetype-name" style={{ color: archetype.color }}>{archetype.label}</div>
              {data.archetype_confidence !== null && (
                <div className="ml-archetype-conf">
                  Confidence: {Math.round((data.archetype_confidence ?? 0) * 100)}%
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Risk bars */}
      <div className="ml-section">
        <div className="ml-section-title">Risk Signals</div>
        <div className="ml-risks">
          {data.hardship_risk !== null && data.hardship_band && (
            <RiskBar
              label="Hardship Risk"
              value={data.hardship_risk}
              band={data.hardship_band}
              color={hrColor}
            />
          )}
          {data.bill_difficulty_risk !== null && data.bill_difficulty_band && (
            <RiskBar
              label="Bill Difficulty Risk"
              value={data.bill_difficulty_risk}
              band={data.bill_difficulty_band}
              color={bdColor}
            />
          )}
        </div>
      </div>

      {/* Spend ratios */}
      <div className="ml-section">
        <div className="ml-section-title">Financial Ratios</div>
        <div className="ml-pills">
          {data.spend_to_income_ratio !== null && (
            <RatioPill
              label="Spend / Income"
              value={data.spend_to_income_ratio}
              threshold={1.0}
              fmt="ratio"
            />
          )}
          {data.discretionary_ratio !== null && (
            <RatioPill
              label="Discretionary"
              value={data.discretionary_ratio}
              threshold={0.35}
              fmt="pct"
            />
          )}
          {/* Savings rate pill - derived from spend/income */}
          {data.spend_to_income_ratio !== null && data.spend_to_income_ratio < 1.0 && (
            <RatioPill
              label="Savings Rate"
              value={1.0 - data.spend_to_income_ratio}
              threshold={0.0}   /* always green if < 1 */
              fmt="pct"
            />
          )}
        </div>
      </div>

      {/* Benchmark bar */}
      {data.wellbeing_score !== null && (
        <div className="ml-section">
          <div className="ml-section-title">vs National Student Benchmark</div>
          <div className="ml-benchmark-row">
            <div className="ml-benchmark-track">
              <div
                className="ml-benchmark-fill"
                style={{ width: `${data.wellbeing_score}%`, background: wbColor }}
              />
              {/* Median marker at 54 */}
              <div className="ml-benchmark-median" style={{ left: '54%' }} />
            </div>
            <div className="ml-benchmark-labels">
              <span style={{ color: wbColor, fontWeight: 700 }}>You: {data.wellbeing_score.toFixed(0)}</span>
              <span style={{ color: 'rgba(255,255,255,0.3)' }}>Median: 54</span>
              <span style={{ color: 'rgba(255,255,255,0.3)' }}>Top 25%: 70+</span>
            </div>
          </div>
        </div>
      )}

      {/* Insights */}
      {data.insights.length > 0 && (
        <div className="ml-section">
          <div className="ml-section-title">AI Coaching</div>
          <div className="ml-insights-list">
            {data.insights.map((insight, i) => {
              const isRed = insight.includes('🔴') || insight.includes('🚨') || insight.includes('💸') || insight.includes('⚠️');
              const isGreen = insight.includes('✅') || insight.includes('✨') || insight.includes('💪') || insight.includes('🟢');
              const isYellow = insight.includes('🟡') || insight.includes('🛒') || insight.includes('📊');
              const dotColor = isRed ? '#f5695b' : isGreen ? '#5cd6a0' : isYellow ? '#f5d05b' : '#a78bfa';
              return (
                <div key={i} className="ml-insight-item">
                  <span className="ml-insight-dot" style={{ background: dotColor, boxShadow: `0 0 6px ${dotColor}55` }} />
                  <span>{insight}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
