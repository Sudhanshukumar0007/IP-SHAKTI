import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

const EvalList = () => {
  const [sessions, setSessions] = useState([]);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("ayurlex_sessions_v2");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.chatHistory && parsed.chatHistory.length > 0) {
          // Filter duplicates just in case
          const uniqueSessions = parsed.chatHistory.filter((v,i,a)=>a.findIndex(t=>(t.id === v.id))===i);
          setSessions(uniqueSessions);
        }
      }
    } catch (e) {
      console.error("Failed to load sessions for EvalList", e);
    }
  }, []);

  const handleClearData = async () => {
    if (window.confirm("Are you sure you want to clear all session history from this browser?")) {
      localStorage.removeItem("ayurlex_sessions_v2");
      setSessions([]);
      // We can also clear the backend database via a quick API call if we wanted, 
      // but the user asked us to delete the DB file which we'll do in the terminal.
      alert("Browser session history cleared! Please refresh the page.");
    }
  };

  return (
    <div style={{ padding: '40px', maxWidth: '800px', margin: '0 auto', fontFamily: 'Inter, sans-serif', overflowY: 'auto', height: '100%', width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '30px' }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <Link to="/" style={{ textDecoration: 'none', color: '#555', marginRight: '20px', fontSize: '20px' }}>&larr;</Link>
          <h1 style={{ fontSize: '28px', color: '#333', margin: 0 }}>Evaluation Directory</h1>
        </div>
        <button 
          onClick={handleClearData}
          style={{ padding: '8px 16px', background: '#ff4d4f', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
        >
          🗑️ Clear All Sessions
        </button>
      </div>
      
      <p style={{ color: '#666', marginBottom: '30px' }}>Select a session below to view its detailed orchestration metrics and evaluation data.</p>

      {sessions.length === 0 ? (
        <div style={{ padding: '20px', background: '#f9f9f9', borderRadius: '8px', color: '#888' }}>
          No sessions found in this browser.
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '12px', paddingBottom: '40px' }}>
          {sessions.map(session => (
            <Link 
              key={session.id} 
              to={session.backendSessionId ? `/eval/${session.backendSessionId}` : '#'}
              onClick={(e) => {
                if (!session.backendSessionId) {
                  e.preventDefault();
                  alert("This is an older session without a backend ID and cannot be evaluated.");
                }
              }}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '16px 20px',
                background: '#fff',
                border: '1px solid #eee',
                borderRadius: '8px',
                textDecoration: 'none',
                color: session.backendSessionId ? '#333' : '#aaa',
                boxShadow: '0 2px 4px rgba(0,0,0,0.02)',
                transition: 'all 0.2s',
                opacity: session.backendSessionId ? 1 : 0.6
              }}
              onMouseEnter={(e) => { 
                if (session.backendSessionId) {
                  e.currentTarget.style.borderColor = '#ccc'; 
                  e.currentTarget.style.transform = 'translateY(-1px)'; 
                }
              }}
              onMouseLeave={(e) => { 
                if (session.backendSessionId) {
                  e.currentTarget.style.borderColor = '#eee'; 
                  e.currentTarget.style.transform = 'none'; 
                }
              }}
            >
              <div>
                <strong style={{ display: 'block', fontSize: '16px', marginBottom: '4px' }}>
                  {session.title || 'Untitled Session'}
                </strong>
                <span style={{ fontSize: '12px', color: '#999' }}>ID: {session.backendSessionId || session.id}</span>
              </div>
              <div style={{ background: '#f0f4f8', padding: '6px 12px', borderRadius: '4px', fontSize: '14px', color: session.backendSessionId ? '#444' : '#999' }}>
                View &rarr;
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};

export default EvalList;
