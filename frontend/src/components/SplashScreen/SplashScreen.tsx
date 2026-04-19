import { useEffect, useState } from 'react';
import './SplashScreen.css';

interface Props {
  onGetStarted: () => void;
}

const FEATURES = [
  { icon: '🧠', label: 'AI-Powered Insights', desc: 'ML models trained on 380K+ student profiles' },
  { icon: '📊', label: 'Live Wellbeing Score', desc: 'Real-time financial health from your spending' },
  { icon: '🎯', label: 'Spending Archetype', desc: 'Know your patterns: stress, social, or boredom' },
  { icon: '🔮', label: 'Hardship Prediction', desc: 'Get warned before financial difficulty hits' },
];

export default function SplashScreen({ onGetStarted }: Props) {
  const [visible, setVisible] = useState(false);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    // Stagger-in after mount
    const t = setTimeout(() => setVisible(true), 80);
    return () => clearTimeout(t);
  }, []);

  const handleStart = () => {
    setLeaving(true);
    setTimeout(onGetStarted, 600);
  };

  return (
    <div className={`splash-overlay ${visible ? 'splash-in' : ''} ${leaving ? 'splash-out' : ''}`}>
      {/* Ambient background orbs */}
      <div className="splash-orb splash-orb-1" />
      <div className="splash-orb splash-orb-2" />
      <div className="splash-orb splash-orb-3" />

      <div className="splash-content">
        {/* Logo / wordmark */}
        <div className="splash-logo-row">
          <div className="splash-icon-badge">💸</div>
          <div className="splash-wordmark">
            <span className="splash-name">BrokeButThriving</span>
            <span className="splash-tagline">Student Finance Copilot</span>
          </div>
        </div>

        {/* Headline */}
        <h1 className="splash-headline">
          Your money.<br />
          <span className="splash-headline-accent">Understood.</span>
        </h1>

        <p className="splash-sub">
          AI-powered financial insights built specifically for students —
          no jargon, no judgment. Just clarity.
        </p>

        {/* Feature pills */}
        <div className="splash-features">
          {FEATURES.map((f, i) => (
            <div
              key={f.label}
              className="splash-feature-card"
              style={{ animationDelay: `${0.3 + i * 0.1}s` }}
            >
              <span className="sf-icon">{f.icon}</span>
              <div className="sf-text">
                <span className="sf-label">{f.label}</span>
                <span className="sf-desc">{f.desc}</span>
              </div>
            </div>
          ))}
        </div>

        {/* CTA */}
        <button id="splash-get-started" className="splash-cta" onClick={handleStart}>
          <span>Get Started</span>
          <span className="splash-cta-arrow">→</span>
        </button>

        <p className="splash-footnote">
          Powered by CFPB + SHED datasets · 380K+ survey records · trained in-house
        </p>
      </div>
    </div>
  );
}
