function Sidebar({
  chatHistory,
  onNewChat,
  onSelectChat,
  activeChatId,
  isOpen,
  onClose
}) {
  // Deduplicate chat history by id
  const uniqueHistory = Array.from(new Map(chatHistory.map(item => [item.id, item])).values());

  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`} style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#111b15', borderRight: '1px solid rgba(255,255,255,0.1)' }}>
      {/* =====================================
          LOGO
      ===================================== */}
      <div className="sidebar-logo" style={{ padding: '24px 20px', borderBottom: '1px solid rgba(255,255,255,0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div className="sidebar-logo-icon" style={{ fontSize: 'var(--text-xl)' }}>☘</div>
          <div>
            <strong style={{ fontSize: 'var(--text-lg)', display: 'block' }}>AyurLex</strong>
            <span style={{ fontSize: 'var(--text-xs)', color: '#a0aec0' }}>Legal AI</span>
          </div>
        </div>
        <button 
          className="sidebar-close-btn" 
          onClick={onClose}
          aria-label="Close sidebar"
        >
          ×
        </button>
      </div>

      {/* =====================================
          NEW CHAT
      ===================================== */}
      <div style={{ padding: '20px' }}>
        <button className="new-chat-button" onClick={onNewChat} style={{ width: '100%', justifyContent: 'center' }}>
          <span style={{ marginRight: '8px' }}>+</span>
          New research
        </button>
      </div>

      {/* =====================================
          HISTORY
      ===================================== */}
      <div className="history-section" style={{ flex: 1, overflowY: 'auto', padding: '0 20px', minHeight: 0 }}>
        <span className="history-title" style={{ fontSize: 'var(--text-xs)', letterSpacing: '0.5px', marginBottom: '12px', display: 'block' }}>RECENT RESEARCH</span>
        <div className="history-list" style={{ display: 'flex', flexDirection: 'column', gap: '8px', minHeight: 0 }}>
          {uniqueHistory.map((chat) => (
            <div key={chat.id} style={{ display: 'flex', alignItems: 'center', background: chat.id === activeChatId ? 'rgba(255,255,255,0.1)' : 'transparent', borderRadius: '6px' }}>
              <button
                className={`history-item ${chat.id === activeChatId ? "active" : ""}`}
                onClick={() => onSelectChat(chat.id)}
                style={{ flex: 1, minWidth: 0, padding: '10px 12px', background: 'transparent', border: 'none', textAlign: 'left' }}
              >
                <span className="history-icon" style={{ marginRight: '8px', opacity: 0.7 }}>◌</span>
                <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 'var(--text-sm)' }}>
                  {chat.title}
                </span>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* =====================================
          SIDEBAR FOOTER
      ===================================== */}
      <div className="sidebar-footer" style={{ padding: '20px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
        <div className="sidebar-status" style={{ marginBottom: '8px' }}>
          <span className="status-dot"></span>
          System Online
        </div>
        <div className="sidebar-footer-text" style={{ opacity: 0.5 }}>
          Sources verified against official legal records from government sites (India Code, WIPO, WTO, USPTO, EPO).
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;