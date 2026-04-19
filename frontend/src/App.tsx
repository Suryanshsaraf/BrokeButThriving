import { useEffect, useState } from 'react';
import { listParticipants, deleteParticipant } from './lib/api';
import type { ParticipantRead } from './types/api';
import DashboardPage from './pages/DashboardPage';
import LogPage from './pages/LogPage';
import InsightsPage from './pages/InsightsPage';
import ChatPage from './pages/ChatPage';
import SettingsPage from './pages/SettingsPage';
import OnboardingPage from './pages/OnboardingPage';
import SplashScreen from './components/SplashScreen/SplashScreen';
import Dock from './components/Dock/Dock';
import './index.css';

/* ============================================================
   App — Sidebar layout with page navigation (no React Router)
   ============================================================ */

type PageId = 'dashboard' | 'log' | 'insights' | 'chat' | 'settings';

const NAV_ITEMS: { id: PageId; icon: string; label: string }[] = [
  { id: 'dashboard', icon: '📊', label: 'Dashboard' },
  { id: 'log', icon: '✏️', label: 'Log Entry' },
  { id: 'insights', icon: '📈', label: 'Insights' },
  { id: 'chat', icon: '🤖', label: 'AI Copilot' },
  { id: 'settings', icon: '⚙️', label: 'Settings' },
];

const SPLASH_KEY = 'bbt_seen_splash';

export default function App() {
  const [participants, setParticipants] = useState<ParticipantRead[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [page, setPage] = useState<PageId>('dashboard');
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showParticipantOverlay, setShowParticipantOverlay] = useState(false);
  const [showSplash, setShowSplash] = useState(!localStorage.getItem(SPLASH_KEY));
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [dataVersion, setDataVersion] = useState(0);

  const handleDataChanged = () => setDataVersion((v) => v + 1);

  useEffect(() => {
    listParticipants()
      .then((list) => {
        setParticipants(list);
        if (list.length > 0) {
          const saved = localStorage.getItem('bbt_pid');
          const found = list.find((p) => p.id === saved);
          setSelectedId(found ? found.id : list[0].id);
        } else {
          setShowOnboarding(true);
        }
      })
      .catch(() => setShowOnboarding(true));
  }, []);

  const handleOnboardingComplete = (id: string) => {
    localStorage.setItem('bbt_pid', id);
    setSelectedId(id);
    setShowOnboarding(false);
    listParticipants().then(setParticipants);
  };

  const handleSplashDone = () => {
    localStorage.setItem(SPLASH_KEY, '1');
    setShowSplash(false);
  };

  const handleSelectParticipant = (id: string) => {
    setSelectedId(id);
    localStorage.setItem('bbt_pid', id);
  };

  const handleDeleteParticipant = async (id: string) => {
    await deleteParticipant(id);
    // Clean up local storage for that participant
    localStorage.removeItem(`bbt_alloc_${id}`);
    const refreshed = await listParticipants();
    setParticipants(refreshed);
    setConfirmDeleteId(null);
    if (selectedId === id) {
      if (refreshed.length > 0) {
        const newId = refreshed[0].id;
        setSelectedId(newId);
        localStorage.setItem('bbt_pid', newId);
      } else {
        setSelectedId(null);
        setShowParticipantOverlay(false);
        setShowOnboarding(true);
      }
    }
  };

  // 1. Splash (first-ever visit)
  if (showSplash) {
    return <SplashScreen onGetStarted={handleSplashDone} />;
  }

  // 2. Onboarding (no participants)
  if (showOnboarding) {
    return <OnboardingPage onComplete={handleOnboardingComplete} />;
  }

  return (
    <div className="app-layout">

      {/* Main content */}
      <main className="main-content">
        {page === 'dashboard' && <DashboardPage participantId={selectedId} dataVersion={dataVersion} />}
        {page === 'log' && <LogPage participantId={selectedId} onDataChanged={handleDataChanged} />}
        {page === 'insights' && <InsightsPage participantId={selectedId} />}
        {page === 'chat' && <ChatPage participantId={selectedId} />}
        {page === 'settings' && <SettingsPage participantId={selectedId} />}
      </main>

      {/* Floating Dock */}
      <Dock 
        items={NAV_ITEMS} 
        activeId={page} 
        onSelect={(id) => setPage(id)} 
        onParticipantClick={() => setShowParticipantOverlay(!showParticipantOverlay)}
      />

      {/* Participant Switcher Overlay */}
      {showParticipantOverlay && (
        <div className="participant-overlay" onClick={() => { setShowParticipantOverlay(false); setConfirmDeleteId(null); }}>
          <div className="participant-card" onClick={(e) => e.stopPropagation()}>
            <h3>Switch Participant</h3>
            <div className="participant-list">
              {participants.map((p) => (
                <div key={p.id} className="participant-row">
                  {confirmDeleteId === p.id ? (
                    /* ── Confirm delete ── */
                    <div className="participant-confirm-delete">
                      <span className="pcd-warning">⚠️ Remove <strong>{p.first_name || p.participant_code}</strong>?</span>
                      <div className="pcd-actions">
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => handleDeleteParticipant(p.id)}
                        >
                          Yes, remove
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => setConfirmDeleteId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* ── Normal row ── */
                    <>
                      <button
                        className={`participant-item ${selectedId === p.id ? 'active' : ''}`}
                        onClick={() => {
                          handleSelectParticipant(p.id);
                          setShowParticipantOverlay(false);
                        }}
                      >
                        <div className="p-avatar">{p.first_name?.[0] || '👤'}</div>
                        <div className="p-info">
                          <span className="p-name">{p.first_name || p.participant_code}</span>
                          <span className="p-budget">Budget: ₹{p.monthly_budget}</span>
                        </div>
                        {selectedId === p.id && <span className="p-active-dot">●</span>}
                      </button>
                      <button
                        className="participant-remove-btn"
                        title="Remove profile"
                        onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(p.id); }}
                      >
                        🗑
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>
            <button
              className="btn btn-secondary"
              style={{ marginTop: 16, width: '100%' }}
              onClick={() => {
                setShowOnboarding(true);
                setShowParticipantOverlay(false);
              }}
            >
              + New Participant
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
