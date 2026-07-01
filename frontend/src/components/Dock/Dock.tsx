import './Dock.css';

interface DockProps {
  items: { id: string; icon: string; label: string }[];
  activeId: string;
  onSelect: (id: any) => void;
  onParticipantClick?: () => void;
}

export default function Dock({ items, activeId, onSelect, onParticipantClick }: DockProps) {
  return (
    <div className="dock-container">
      {items.map((item) => (
        <button
          key={item.id}
          className={`dock-item ${activeId === item.id ? 'active' : ''}`}
          onClick={() => onSelect(item.id)}
          title={item.label}
        >
          <span className="dock-item-icon">{item.icon}</span>
          <span className="dock-label">{item.label}</span>
          {activeId === item.id && <div className="dock-active-indicator" />}
        </button>
      ))}
      
      <div className="dock-divider" />
      
      <button 
        className="dock-item" 
        onClick={onParticipantClick}
        title="Switch Participant"
      >
        <span className="dock-item-icon">👤</span>
        <span className="dock-label">Participant</span>
      </button>
    </div>
  );
}
