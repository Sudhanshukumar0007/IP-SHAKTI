import { useEffect, useRef, useState, useCallback } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import Sidebar from "./components/Sidebar";
import EvalDashboard from "./pages/EvalDashboard";
import EvalList from "./pages/EvalList";

import { t, LANGUAGES } from "./i18n";
import api from "./api/client";
import { API_BASE_URL } from "./api/config";
import "./App.css";

const STORAGE_KEY = "ayurlex_sessions_v2";

/* ===================== STREAMING TEXT (word-by-word reveal) ===================== */
function StreamingText({ text }) {
  const words = text.split(/(\s+)/);

  return (
    <span className="streaming-text">
      {words.map((word, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, y: 3 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: "easeOut" }}
        >
          {word}
        </motion.span>
      ))}
    </span>
  );
}

/* ===================== MESSAGE BUBBLE ===================== */
function MessageBubble({ msg, language, jurisdiction, onViewReferences }) {
  const [playing, setPlaying] = useState(false);

  if (msg.type === "research") return <ResearchCard data={msg.researchData} language={language} onViewReferences={onViewReferences} msgId={msg.id} />;

  const isUser = msg.role === "user";

  const listen = async () => {
    if (playing) { window.speechSynthesis?.cancel(); setPlaying(false); return; }
    setPlaying(true);
    try {
      const langCode = LANGUAGES[language]?.code || "en-IN";
      const blob = await api.textToSpeech({ text: msg.text, language: langCode });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => { setPlaying(false); URL.revokeObjectURL(url); };
      audio.onerror = () => { setPlaying(false); URL.revokeObjectURL(url); fallbackListen(msg.text, langCode); };
      await audio.play();
    } catch { fallbackListen(msg.text, LANGUAGES[language]?.code || "en-IN"); }
  };

  const fallbackListen = (text, langCode) => {
    if (!window.speechSynthesis) { setPlaying(false); return; }
    const u = new SpeechSynthesisUtterance(text);
    u.lang = langCode; u.rate = 0.9;
    u.onend = () => setPlaying(false);
    u.onerror = () => setPlaying(false);
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`chat-row ${isUser ? "user" : "assistant"}`}
    >
      {!isUser && <div className="chat-avatar">☘</div>}
      <div className={isUser ? "user-message" : `assistant-message jurisdiction-${jurisdiction} has-mic`}>
        <div className="message-text-row">
          <span className="message-text">
            {isUser ? msg.text : <TypewriterText text={msg.text || ""} onViewCitation={() => {}} msgId={msg.id} />}
          </span>
          {!isUser && !msg.streaming && msg.text && (
            <button
              className="mic-icon-btn"
              onClick={listen}
              aria-label={playing ? "Stop audio playback" : "Play this message as audio"}
              title={playing ? "Stop" : "Listen"}
            >
              {playing ? "⏹" : "🔊"}
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/* ===================== NATIVE SELECT DROPDOWN ===================== */
const SelectDropdown = ({ label, value, options, onChange }) => {
  return (
    <div className="control-group" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'bold', color: '#666', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
        {label}
      </label>
      <select 
        value={value} 
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: '8px 12px',
          borderRadius: '6px',
          border: '1px solid #ddd',
          background: '#fff',
          fontSize: 'var(--text-sm)',
          cursor: 'pointer',
          outline: 'none',
          boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
        }}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
};

/* ===================== RIGHT SIDEBAR (CITATIONS & PDF) ===================== */
function RightSidebar({ data, onClose }) {
  const [activePdf, setActivePdf] = useState(null);

  useEffect(() => {
    if (data && data.initialActivePdf) {
      const allCitations = [...(data.national_citations || []), ...(data.international_citations || [])];
      const target = allCitations.find(c => c.index === data.initialActivePdf);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (target) setActivePdf(target);
    }
  }, [data]);

  if (!data) return null;
  const { national_citations, international_citations } = data;
  
  const renderCitationCard = (ref, i) => (
    <div className="citation-card" key={i}>
      <div className="citation-icon">📜</div>
      <div className="citation-content">
        <span className="official-source">OFFICIAL SOURCE [E{ref.index}]</span>
        <h4>{ref.act_name}</h4>
        {ref.section_or_article && <strong>{ref.section_or_article}</strong>}
        {ref.document_id && (
          <button 
            className="verify-button" 
            style={{marginTop: 8}}
            onClick={() => setActivePdf(ref)}
          >
            Verify Original Document
          </button>
        )}
      </div>
    </div>
  );

  return (
    <aside className="right-sidebar">
      <div className="right-sidebar-header">
        <h2>References</h2>
        <button className="close-btn" onClick={onClose} aria-label="Close sidebar">×</button>
      </div>
      <div className="right-sidebar-content">
        {activePdf ? (
          <div className="pdf-viewer-overlay">
            <div className="pdf-viewer-header">
               <button className="back-btn" onClick={() => setActivePdf(null)}>← Back to List</button>
               <h4>{activePdf.act_name}</h4>
            </div>
            <iframe 
              src={`${API_BASE_URL}/pdf/${encodeURIComponent(activePdf.document_id)}#page=${activePdf.page_start || 1}`} 
              title={`PDF view`} 
              className="inline-pdf-iframe"
            />
          </div>
        ) : (
          <div className="sidebar-citations-list">
            {!national_citations?.length && !international_citations?.length && (
              <div className="chat-citation-empty">
                <span>ⓘ No verified source found for this specific answer.</span>
              </div>
            )}
            
            {national_citations?.length > 0 && (
              <div className="citation-section">
                <div className="citation-heading"><div><span>SOURCES</span><h3>Indian References</h3></div></div>
                {national_citations.map((c, i) => renderCitationCard(c, i))}
              </div>
            )}

            {international_citations?.length > 0 && (
              <div className="citation-section" style={{marginTop: 20}}>
                <div className="citation-heading"><div><span>SOURCES</span><h3>International References</h3></div></div>
                {international_citations.map((c, i) => renderCitationCard(c, i))}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}


/* ===================== CLASSIFICATION QUESTION (Yes/No) ===================== */
function ClassificationQuestion({ question, onAnswer }) {
  return (
    <div className="chat-row assistant">
      <div className="chat-avatar">☘</div>
      <div className="question-card">
        <span className="question-number">CLARIFICATION NEEDED</span>
        <h2>{question}</h2>
        <div className="yes-no-buttons">
          <button onClick={() => onAnswer("Yes")} aria-label="Yes, this applies">
            <div><strong>Yes</strong><span>This applies</span></div> →
          </button>
          <button onClick={() => onAnswer("No")} aria-label="No, this does not apply">
            <div><strong>No</strong><span>This does not apply</span></div> →
          </button>
        </div>
      </div>
    </div>
  );
}

function parseCitations(text, onViewCitation) {
  if (!text) return null;
  const regex = /\[E(\d+)\]/g;
  const parts = [];
  let lastIndex = 0;
  let match;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }
    const idx = parseInt(match[1], 10);
    parts.push(
      <span 
        key={match.index} 
        className="citation-badge" 
        style={{color: "#4ade80", cursor: "pointer", fontWeight: "bold", textDecoration: "underline", margin: "0 2px"}} 
        onClick={(e) => { e.stopPropagation(); onViewCitation(idx); }}
        title="View Reference"
      >
        [E{idx}]
      </span>
    );
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }
  return parts.length > 0 ? parts : text;
}

function TypewriterText({ text, onViewCitation, msgId }) {
  const [displayedText, setDisplayedText] = useState("");
  const [shouldAnimate] = useState(() => {
    // Only animate if the message was created less than 2 seconds ago
    if (!msgId) return false;
    return (Date.now() - Math.floor(msgId)) < 2000;
  });

  useEffect(() => {
    if (!shouldAnimate || !text) {
      setDisplayedText(text || "");
      return;
    }

    let index = 0;
    const charsPerTick = 5;
    const interval = setInterval(() => {
      index += charsPerTick;
      if (index >= text.length) {
        index = text.length;
        clearInterval(interval);
      }
      setDisplayedText(text.substring(0, index));
    }, 10);
    
    return () => clearInterval(interval);
  }, [text, shouldAnimate]);

  return <>{parseCitations(displayedText, onViewCitation)}</>;
}

function AnswerRenderer({ answer, onViewCitation, msgId }) {
  if (!answer) return null;
  if (typeof answer === 'string') {
    return <p style={{whiteSpace: 'pre-wrap'}}><TypewriterText text={answer} onViewCitation={onViewCitation} msgId={msgId} /></p>;
  }
  if (typeof answer === 'object') {
    if (answer.answer) {
      return <p style={{whiteSpace: 'pre-wrap'}}><TypewriterText text={answer.answer} onViewCitation={onViewCitation} msgId={msgId} /></p>;
    }
    return (
      <div className="disclosure-fields">
        {answer.regulatory_classification && (
          <div className="field" style={{marginTop: 12}}>
            <strong>Regulatory Classification:</strong> 
            <p style={{whiteSpace: 'pre-wrap', marginTop: 4}}><TypewriterText text={answer.regulatory_classification} onViewCitation={onViewCitation} msgId={msgId} /></p>
          </div>
        )}
        {answer.ip_regimes_applicable && (
          <div className="field" style={{marginTop: 12}}>
            <strong>Applicable IP Regimes:</strong> 
            <p style={{whiteSpace: 'pre-wrap', marginTop: 4}}><TypewriterText text={answer.ip_regimes_applicable} onViewCitation={onViewCitation} msgId={msgId} /></p>
          </div>
        )}
        {answer.patentability_posture && (
          <div className="field" style={{marginTop: 12}}>
            <strong>Patentability Posture:</strong> 
            <p style={{whiteSpace: 'pre-wrap', marginTop: 4}}><TypewriterText text={answer.patentability_posture} onViewCitation={onViewCitation} msgId={msgId} /></p>
          </div>
        )}
        {answer.abs_exposure && (
          <div className="field" style={{marginTop: 12}}>
            <strong>ABS & Biodiversity Exposure:</strong> 
            <p style={{whiteSpace: 'pre-wrap', marginTop: 4}}><TypewriterText text={answer.abs_exposure} onViewCitation={onViewCitation} msgId={msgId} /></p>
          </div>
        )}
        {answer.tkdl_relevance && (
          <div className="field" style={{marginTop: 12}}>
            <strong>TKDL Relevance:</strong> 
            <p style={{whiteSpace: 'pre-wrap', marginTop: 4}}><TypewriterText text={answer.tkdl_relevance} onViewCitation={onViewCitation} msgId={msgId} /></p>
          </div>
        )}
      </div>
    );
  }
  return null;
}

/* ===================== SPEAK BUTTON ===================== */
function SpeakButton({ text }) {
  const [isPlaying, setIsPlaying] = useState(false);
  
  const handleToggle = () => {
    if (!('speechSynthesis' in window)) {
      alert("Text-to-speech is not supported in this browser.");
      return;
    }
    
    if (isPlaying) {
      window.speechSynthesis.cancel();
      setIsPlaying(false);
      return;
    }
    
    window.speechSynthesis.cancel();
    
    let textToSpeak = "";
    if (typeof text === 'string') {
        textToSpeak = text;
    } else if (typeof text === 'object') {
        if (text.answer) {
            textToSpeak = text.answer;
        } else {
            textToSpeak = Object.values(text).filter(v => typeof v === 'string').join(". ");
        }
    }
    textToSpeak = textToSpeak.replace(/\[\d+\]/g, "");
    
    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.onend = () => setIsPlaying(false);
    utterance.onerror = () => setIsPlaying(false);
    
    setIsPlaying(true);
    window.speechSynthesis.speak(utterance);
  };
  
  useEffect(() => {
    return () => {
      if (isPlaying) {
        window.speechSynthesis.cancel();
      }
    };
  }, [isPlaying]);

  return (
    <button 
      onClick={handleToggle} 
      title="Tap to listen"
      style={{
        background: isPlaying ? "#d1fae5" : "none", 
        border: `1px solid ${isPlaying ? "#10b981" : "#d1d5db"}`, 
        borderRadius: 4, 
        padding: "4px 8px", 
        cursor: "pointer", 
        fontSize: 12, 
        display: "flex", 
        alignItems: "center", 
        gap: 6, 
        color: isPlaying ? "#065f46" : "#4b5563",
        transition: "all 0.2s"
      }}
    >
      {isPlaying ? "⏹ Stop" : "🔊 Listen"}
    </button>
  );
}

/* ===================== RESEARCH CARD ===================== */
function ResearchCard({ data, onViewReferences, msgId }) {
  const { jurisdiction_mode, formulation_category, abstained, abstain_reason, national_answer, international_answer, national_citations, international_citations, overall_status, execution_trace } = data;
  const hasNational = jurisdiction_mode === "national" || jurisdiction_mode === "both";
  const hasInternational = jurisdiction_mode === "international" || jurisdiction_mode === "both";
  const hasCitations = (national_citations?.length > 0) || (international_citations?.length > 0);
  const [showTrace, setShowTrace] = useState(false);

  const statusColor = overall_status === "VERIFIED" ? "#4ade80" : (overall_status === "PARTIAL" ? "#fbbf24" : "#f87171");
  const statusIcon = overall_status === "VERIFIED" ? "✓" : (overall_status === "PARTIAL" ? "⚠" : "✖");

  const handleCitationClick = (idx) => {
    onViewReferences({ national_citations, international_citations, initialActivePdf: idx });
  };

  return (
    <div className="chat-row assistant">
      <div className="chat-avatar">☘</div>
      <div className="research-body">
        <div className="ai-name">AyurLex <span>Research Assistant</span></div>
        <div className={`research-card jurisdiction-${jurisdiction_mode}`}>
          <div className="research-top">
            <span className="research-label">LEGAL RESEARCH</span>
            <div style={{display: "flex", justifyContent: "space-between", alignItems: "center"}}>
              <h2>Regulatory Assessment</h2>
              {overall_status && (
                <div style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  padding: "4px 10px", borderRadius: 12, border: `1px solid ${statusColor}40`,
                  backgroundColor: `${statusColor}10`, color: statusColor, fontSize: 12, fontWeight: 600
                }}>
                  <span>{statusIcon}</span> {overall_status}
                </div>
              )}
            </div>
          </div>

          <div className="research-meta">
            <div><span>JURISDICTION</span><strong>{jurisdiction_mode.toUpperCase()}</strong></div>
            <div><span>CLASSIFICATION</span><strong>{formulation_category.toUpperCase()}</strong></div>
          </div>

          {abstained ? (
            <section className="research-section">
              <h3>Assessment Abstained</h3>
              <p style={{color: "#f87171"}}>{abstain_reason}</p>
              <div className="chat-citation-empty" style={{marginTop: 10}}>
                <button
                  className="escalate-button"
                  onClick={() => window.open("mailto:ip-support@ayurlex.example?subject=Escalation", "_blank")}
                >
                  🧑‍⚖️ Escalate to Human Facilitator
                </button>
              </div>
            </section>
          ) : (
            <>
              {hasNational && national_answer && (
                <section className="research-section">
                  <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12}}>
                    <h3 style={{margin: 0}}>National (India) Guidance</h3>
                    <SpeakButton text={national_answer} />
                  </div>
                  <AnswerRenderer answer={national_answer} onViewCitation={handleCitationClick} msgId={msgId} />
                </section>
              )}
              {hasInternational && international_answer && (
                <section className="research-section" style={{marginTop: "20px", borderTop: "1px solid #eee", paddingTop: "20px"}}>
                  <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12}}>
                    <h3 style={{margin: 0}}>International Guidance</h3>
                    <SpeakButton text={international_answer} />
                  </div>
                  <AnswerRenderer answer={international_answer} onViewCitation={handleCitationClick} msgId={msgId} />
                </section>
              )}
              {overall_status !== "VERIFIED" && overall_status !== "UNKNOWN" && (
                <div style={{marginTop: "20px", padding: 12, borderRadius: 8, backgroundColor: "#fbbf2410", border: "1px solid #fbbf2440"}}>
                  <h4 style={{margin: "0 0 8px 0", color: "#fbbf24", fontSize: 14}}>⚠ Evidence Gap Notice</h4>
                  <p style={{margin: 0, fontSize: 13, color: "#fff"}}>The research assistant lacked sufficient verified corpus evidence to answer conclusively. Claims should be interpreted cautiously.</p>
                </div>
              )}
              {hasCitations && (
                <div style={{marginTop: "20px"}}>
                  <button 
                    className="escalate-button" 
                    onClick={() => onViewReferences({national_citations, international_citations})}
                  >
                    📜 Check All References
                  </button>
                </div>
              )}
            </>
          )}

          {execution_trace && execution_trace.length > 0 && (
            <div style={{marginTop: "20px", borderTop: "1px solid #333", paddingTop: "16px"}}>
              <button 
                onClick={() => setShowTrace(!showTrace)}
                style={{
                  background: "transparent", border: "none", color: "#888", 
                  fontSize: 13, cursor: "pointer", display: "flex", alignItems: "center", gap: 6, padding: 0
                }}
              >
                <span>{showTrace ? "▼" : "▶"}</span> Research Process
              </button>
              {showTrace && (
                <div style={{
                  marginTop: 12, padding: 12, backgroundColor: "#111", 
                  borderRadius: 6, border: "1px solid #333", maxHeight: 200, overflowY: "auto",
                  fontSize: 12, color: "#aaa", fontFamily: "monospace", whiteSpace: "pre-wrap"
                }}>
                  {execution_trace.join("\n")}
                </div>
              )}
            </div>
          )}

          <div className="research-disclaimer" style={{marginTop: "20px"}}>
            <span>ⓘ</span>
            <div><strong>Information, not legal advice.</strong><p>This result is intended for informational and research purposes only. Verify the applicable law and official source before relying on it.</p></div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============================== APP ============================== */
function App() {
  const [jurisdiction, setJurisdiction] = useState("national"); // "national", "international", "both"
  const [language, setLanguage] = useState("English");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [activeChatId, setActiveChatId] = useState(() => Date.now());
  const [activeSidebarData, setActiveSidebarData] = useState(null);
  
  const [pendingClarification, setPendingClarification] = useState(null);
  const [loadingText, setLoadingText] = useState("Analyzing...");

  useEffect(() => {
    if (!typing) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoadingText("Analyzing...");
      return;
    }
    const t1 = setTimeout(() => setLoadingText("Thinking..."), 2000);
    const t2 = setTimeout(() => setLoadingText("Accumulating..."), 5000);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [typing]);

  /* ---------- SESSION PERSISTENCE ---------- */
  const [sessions, setSessions] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved).sessions || {} : {};
    } catch { return {}; }
  });
  const [chatHistory, setChatHistory] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      const parsed = saved ? JSON.parse(saved) : null;
      return parsed?.chatHistory?.length ? parsed.chatHistory : [];
    } catch { return []; }
  });

  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, typing, pendingClarification]);
  
  // Ensure we have a session on mount or when activeChatId changes
  const initializingRef = useRef(new Set());

  useEffect(() => {
    if (sessions[activeChatId] || initializingRef.current.has(activeChatId)) return;
    
    let isMounted = true;
    const initializeSession = async () => {
      initializingRef.current.add(activeChatId);
      try {
        const sid = await api.createSession(jurisdiction, language);
        if (!isMounted) return;
        
        const welcomeMsg = { 
          id: Date.now(), 
          role: "assistant", 
          type: "text", 
          text: `${t("welcome_1", language)}\n\n${t("welcome_question", language)}`,
          noCitation: true 
        };

        setSessions(prev => ({
          ...prev,
          [activeChatId]: {
            sessionId: sid,
            jurisdiction,
            language,
            messages: [welcomeMsg],
            pendingClarification: null
          }
        }));
        
        setChatHistory(prev => {
          if (prev.find(c => c.id === activeChatId)) return prev;
          return [{ id: activeChatId, backendSessionId: sid, title: "New formulation research" }, ...prev];
        });
        
        setMessages([welcomeMsg]);
      } catch (e) {
        console.error("Failed to initialize session", e);
        if (isMounted) initializingRef.current.delete(activeChatId);
      }
    };
    
    initializeSession();
    return () => { isMounted = false; };
  }, [activeChatId, sessions, jurisdiction, language]);

  /* persist sessions/chatHistory on every change */
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ sessions, chatHistory }));
    } catch { /* storage full */ }
  }, [sessions, chatHistory]);

  const addMsg = useCallback((msg) => {
    const id = Date.now() + Math.random();
    const newMsg = { id, ...msg };
    setMessages(prev => {
      const updated = [...prev, newMsg];
      setSessions(s => ({...s, [activeChatId]: {...s[activeChatId], messages: updated}}));
      return updated;
    });
    return id;
  }, [activeChatId]);

  /* ---------- NEW RESEARCH / SELECT CHAT ---------- */
  const navigate = useNavigate();

  const startNewResearch = async () => {
    const newId = Date.now();
    setActiveChatId(newId);
    setPendingClarification(null);
    setInput("");
    setTyping(false);
    navigate("/");
  };

  const selectChat = useCallback((chatId) => {
    setActiveChatId(chatId);
    const session = sessions[chatId];
    if (session) {
      setMessages(session.messages);
      setJurisdiction(session.jurisdiction || "national");
      if (session.language) setLanguage(session.language);
      setPendingClarification(session.pendingClarification || null);
    }
    navigate("/");
  }, [sessions, navigate]);

  /* ---------- SEND MESSAGE TO BACKEND ---------- */
  const handleChat = async (text) => {
    const normalized = text.trim();
    if (!normalized || typing) return;

    const sessionData = sessions[activeChatId];
    if (!sessionData || !sessionData.sessionId) return;
    
    addMsg({ role: "user", type: "text", text: normalized });
    setInput("");
    setTyping(true);
    setPendingClarification(null);

    // Also update title on first user query
    if (messages.length === 1) {
      setChatHistory(prev => prev.map(c => c.id === activeChatId ? { ...c, title: text.substring(0, 30) + "..." } : c));
    }

    try {
      const result = await api.sendChatMessage(sessionData.sessionId, text, jurisdiction, language);
      
      if (result.type === "clarification") {
        setPendingClarification(result.question);
        setSessions(s => ({...s, [activeChatId]: {...s[activeChatId], pendingClarification: result.question}}));
      } else if (result.type === "answer") {
        addMsg({ role: "assistant", type: "research", researchData: result });
        setSessions(s => ({...s, [activeChatId]: {...s[activeChatId], pendingClarification: null}}));
      } else if (result.type === "classification_failed") {
        addMsg({ role: "assistant", type: "text", text: result.message });
      }
    } catch (err) {
      const errorStr = err.message || "";
      let msg = "An unexpected error occurred. Please try again.";
      if (errorStr.includes("413") || errorStr.includes("429") || errorStr.includes("rate_limit") || errorStr.includes("tokens")) {
         msg = "The system is experiencing high traffic and API rate limits were exceeded. Please wait a moment and try again.";
      } else if (errorStr.includes("500") || errorStr.includes("Internal Server Error")) {
         msg = "The AI processing server encountered an error analyzing your request. Please try again or rephrase.";
      }
      addMsg({ role: "assistant", type: "text", text: msg });
    }
    
    setTyping(false);
  };

  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  /* ---------- RENDER ---------- */
  const showComposer = !pendingClarification;

  return (
    <div className="app">
      {/* Mobile Overlay */}
      {isMobileSidebarOpen && (
        <div 
          className="mobile-overlay" 
          onClick={() => setIsMobileSidebarOpen(false)}
        />
      )}
      
      <Sidebar 
        chatHistory={chatHistory} 
        onNewChat={startNewResearch} 
        onSelectChat={selectChat} 
        activeChatId={activeChatId}
        isOpen={isMobileSidebarOpen}
        onClose={() => setIsMobileSidebarOpen(false)}
      />
      <main className="main-content" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto' }}>
        <Routes>
          <Route path="/eval" element={<EvalList />} />
          <Route path="/" element={
            <>
              <header className="topbar">
                <div className="brand">
                  <button 
                    className="hamburger-btn" 
                    onClick={() => setIsMobileSidebarOpen(true)}
                    aria-label="Open menu"
                  >
                    ☰
                  </button>
                  <div className="brand-logo">☘</div>
                  <div className="brand-text"><h1>AyurLex</h1><span>Legal Research Assistant</span></div>
                </div>
                <div className="top-controls">
                  <SelectDropdown
                    label="JURISDICTION"
                    value={jurisdiction}
                    options={[
                      { value: "national", label: "🇮🇳 National" },
                      { value: "international", label: "🌍 International" },
                      { value: "both", label: "⚖️ Both" }
                    ]}
                    onChange={(val) => {
                      setJurisdiction(val);
                      setSessions(s => ({...s, [activeChatId]: {...s[activeChatId], jurisdiction: val}}));
                    }}
                  />
                  <SelectDropdown
                    label="OUTPUT LANGUAGE"
                    value={language}
                    options={[
                      { value: "English", label: "English" },
                      { value: "Hindi", label: "Hindi" },
                      { value: "Marathi", label: "Marathi" },
                      { value: "Gujarati", label: "Gujarati" },
                      { value: "Tamil", label: "Tamil" },
                      { value: "Telugu", label: "Telugu" }
                    ]}
                    onChange={(val) => {
                      setLanguage(val);
                      setSessions(s => ({...s, [activeChatId]: {...s[activeChatId], language: val}}));
                    }}
                  />
                </div>
              </header>

              <div className={`jurisdiction-banner ${jurisdiction}`}>
                <div className="jurisdiction-icon">{jurisdiction === "national" ? "🇮🇳" : jurisdiction === "international" ? "🌍" : "⚖️"}</div>
                <div>
                  <strong>{jurisdiction === "national" ? "Indian Legal Framework" : jurisdiction === "international" ? "International Framework" : "National & International"}</strong>
                  <span>{jurisdiction === "national" ? "Research will prioritize Indian statutes and rules." : jurisdiction === "international" ? "Research will prioritize international regulations." : "Comparing both national and international frameworks."}</span>
                </div>
              </div>

              <section className={`workspace ${showComposer ? "with-composer" : ""}`}>
                <div className="chat-container">
                  <div className="chat-thread">
                    <AnimatePresence initial={false}>
                      {messages.map((msg) => (
                        <MessageBubble 
                          key={msg.id} 
                          msg={msg} 
                          language={language} 
                          jurisdiction={jurisdiction} 
                          onViewReferences={setActiveSidebarData}
                        />
                      ))}
                    </AnimatePresence>

                    {pendingClarification && (
                      <ClassificationQuestion 
                        question={pendingClarification} 
                        onAnswer={(ans) => handleChat(ans)} 
                      />
                    )}

                    {typing && (
                      <div className="chat-row assistant">
                        <div className="chat-avatar">☘</div>
                        <div className="typing-bubble"><span className="typing-dot" />{loadingText}</div>
                      </div>
                    )}

                    <div ref={bottomRef} />
                  </div>

                  {showComposer && (
                    <div className="chat-composer">
                      <div className="chat-composer-box">
                        <textarea 
                          ref={inputRef} 
                          value={input} 
                          onChange={(e) => setInput(e.target.value)} 
                          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleChat(input); } }} 
                          placeholder="Ask a legal question…" 
                          rows={1} 
                          aria-label="User question" 
                        />
                        <div className="composer-actions">
                          <button 
                            className="chat-send" 
                            disabled={!input.trim() || typing} 
                            onClick={() => handleChat(input)} 
                            aria-label="Send message"
                          >↑</button>
                        </div>
                      </div>
                      <div className="chat-composer-hint">Ask about statutes, regulations, rights, obligations, or legal provisions.</div>
                    </div>
                  )}
                </div>
              </section>

              <div className="permanent-disclaimer">
                <span className="disclaimer-icon">ⓘ</span>
                <div><strong>Information, not legal advice.</strong><span>AyurLex provides legal research and information for reference purposes. Always verify the current law and official sources before relying on any information.</span></div>
              </div>
            </>
          } />
          

          <Route path="/eval/:sessionId" element={<EvalDashboard />} />
        </Routes>
      </main>
      
      {activeSidebarData && (
        <RightSidebar 
          data={activeSidebarData} 
          onClose={() => setActiveSidebarData(null)} 
        />
      )}
    </div>
  );
}

export default App;