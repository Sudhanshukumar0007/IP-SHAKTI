import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, ArrowRight, Trash2, Inbox } from 'lucide-react';

const STORAGE_KEY = 'ipshakti_chats';

const listVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.04 } },
};

const rowVariants = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { duration: 0.25 } },
};

function EvalList() {
  const [sessions, setSessions] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed.filter(
            (v, i, a) => a.findIndex((t) => t.id === v.id) === i
          );
        }
      }
    } catch (e) {
      console.error('Failed to load sessions for EvalList', e);
    }
    return [];
  });

  const handleClearData = () => {
    if (window.confirm('Are you sure you want to clear all session history from this browser?')) {
      localStorage.removeItem(STORAGE_KEY);
      setSessions([]);
      alert('Browser session history cleared! Please refresh the page.');
    }
  };

  return (
    <div className="min-h-screen w-full overflow-y-auto bg-[#F2EBDD] text-[#26312A] font-sans">
      <div className="mx-auto max-w-5xl px-6 py-10 lg:px-8">
        {/* HEADER */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <Link
              to="/"
              className="flex items-center justify-center w-9 h-9 rounded-lg border bg-white text-[#26312A] transition hover:bg-[#F4E8CB]"
              style={{ borderColor: "#D8D0BA" }}
              aria-label="Back to research"
            >
              <ArrowLeft size={16} strokeWidth={2} />
            </Link>
            <div className="flex flex-col">
              <div className="mb-1 text-[9px] font-semibold tracking-[.17em] text-[#817A63]">INTERNAL EVALUATION</div>
              <h1 className="font-['Newsreader'] text-2xl font-semibold tracking-tight leading-none text-[#26312A]">
                Research sessions
              </h1>
              <span className="text-[10px] text-[#9C9679] mt-1">
                Session history stored in this browser
              </span>
            </div>
          </div>

          {sessions.length > 0 && (
            <button
              onClick={handleClearData}
              className="flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold text-[#7A2E2E] transition hover:bg-white" style={{ borderColor: "#7A2E2E30" }}
            >
              <Trash2 size={13} /> Clear all sessions
            </button>
          )}
        </div>

        {/* LIST */}
        {sessions.length === 0 ? (
          <div className="mt-12 flex flex-col items-center justify-center gap-3 rounded-3xl border border-dashed bg-[#F7F4EB] py-24" style={{ borderColor: "#D8D0BA" }}>
            <Inbox size={22} className="text-[#2F6B3E]/40" />
            <span className="text-[10px] font-mono tracking-[.16em] text-[#9C9679] uppercase">
              No sessions found
            </span>
          </div>
        ) : (
          <motion.div variants={listVariants} initial="hidden" animate="show" className="flex flex-col gap-2">
            {sessions.map((session) => {
              const usable = Boolean(session.id);
              return (
                <motion.div key={session.id} variants={rowVariants}>
                  <Link
                    to={usable ? `/eval/${session.id}` : '#'}
                    onClick={(e) => {
                      if (!usable) {
                        e.preventDefault();
                        alert('This is an older session without a backend ID and cannot be evaluated.');
                      }
                    }}
                    className={`group flex items-center justify-between gap-4 px-5 py-4 bg-white border border-zinc-200/50 border-l-2 transition-colors ${
                      usable
                        ? 'border-l-transparent hover:border-l-forest hover:bg-forest/5'
                        : 'border-l-transparent opacity-50 cursor-not-allowed'
                    }`}
                  >
                    <div className="min-w-0">
                      <strong className={`block text-sm font-semibold tracking-tight truncate ${usable ? 'text-[#26312A]' : 'text-[#9C9679]'}`}>
                        {session.title || 'Untitled Session'}
                      </strong>
                      <span className="text-[9px] font-mono text-[#9C9679]">
                        ID: {session.id}
                      </span>
                    </div>
                    <div className={`flex items-center gap-1 text-xs font-semibold shrink-0 ${usable ? 'text-[#2F6B3E]' : 'text-[#9C9679]'}`}>
                      View
                      <ArrowRight size={13} className={usable ? 'transition-transform group-hover:translate-x-0.5' : ''} />
                    </div>
                  </Link>
                </motion.div>
              );
            })}
          </motion.div>
        )}
      </div>
    </div>
  );
}

export default EvalList;
