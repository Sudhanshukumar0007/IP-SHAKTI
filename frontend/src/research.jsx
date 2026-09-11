import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft, ArrowRight, ArrowUp, BookOpen,
  ChevronDown, Clock, ExternalLink, FileText, Info,
  Leaf, Menu, MessageCircle, Search, Scale,
  ScrollText, Settings, ShieldCheck, Sparkles, User, Volume2, VolumeX, X
} from "lucide-react";
import api from "./api/client";
import { API_BASE_URL } from "./api/config";

const SERIF = "font-['Newsreader']";
const MONO = "font-['IBM_Plex_Mono']";
const C = {
  ink: "#26312A",
  forest: "#2F6B3E",
  forestHi: "#25552F",
  moss: "#3F6B49",
  brass: "#BB8F42",
  brassLt: "#F4E8CB",
  parchment: "#FAF8F1",
  card: "#FFFFFF",
  line: "#EAE3CE",
  muted: "#9E9679",
  error: "#B3524F",
  warn: "#AD8134",
};

const QUICK_STARTERS = [
  { icon: "🌿", label: "Is my Ayurvedic formulation patentable under Section 3(p)?", tag: "Patents" },
  { icon: "📜", label: "How do I check TKDL for prior art on my formulation?", tag: "TKDL" },
  { icon: "🌾", label: "What ABS approvals do I need for a herbal cosmetic using Neem?", tag: "Biodiversity" },
  { icon: "🏷️", label: "Can I register a Geographical Indication for my regional product?", tag: "GI" },
  { icon: "⚗️", label: "Classical vs proprietary vs phytopharmaceutical — how do I classify?", tag: "Regulatory" },
  { icon: "🌍", label: "How does the WIPO GRATK Treaty 2024 affect my patent filing abroad?", tag: "International" },
];

const JURISDICTIONS = [
  { value: "national", label: "🇮🇳 National" },
  { value: "international", label: "🌍 International" },
  { value: "both", label: "⚖️ Both" },
];

const LANGUAGES = ["English", "Hindi", "Marathi", "Gujarati", "Tamil", "Telugu"];

const PARTNERS = [
  {
    short: "IP INDIA",
    name: "Intellectual Property India",
    href: "https://www.ipindia.gov.in/",
    src: "https://uniquewellnesscare.com/assets/img/ipo-logo-BM9oUnEW.png",
  },
  {
    short: "WIPO",
    name: "World Intellectual Property Organization",
    href: "https://www.wipo.int/portal/en/",
    src: "https://www.avrupapatent.com.tr/media/images/WIPO-E-BLUE_2.jpg",
  },
  {
    short: "AYUSH",
    name: "Ministry of AYUSH",
    href: "https://www.ayush.gov.in/",
    src: "https://i0.wp.com/orissadiary.com/wp-content/uploads/2025/09/1585280-ayush-ministry.webp?fit=1280%2C720&ssl=1",
  },
];

function SealMark({ size = 36 }) {
  return (
    <div
      className="relative flex shrink-0 items-center justify-center rounded-full text-[#FAF8F1]"
      style={{
        width: size, height: size,
        background: "radial-gradient(circle at 32% 28%, #3E7A4C, #23522E 72%)",
        boxShadow: "0 0 0 1px #BB8F4255, 0 0 0 3px #FAF8F1, 0 3px 8px rgba(38,49,42,0.14)"
      }}
    >
      <Leaf size={Math.round(size * .5)} strokeWidth={1.8}/>
    </div>
  );
}

function PartnerLogo({ partner }) {
  const [failed, setFailed] = useState(false);
  return (
    <a href={partner.href} target="_blank" rel="noreferrer" className="flex items-center gap-3 rounded-xl border bg-white px-4 py-3 transition hover:-translate-y-0.5 hover:shadow-sm" style={{ borderColor: C.line }}>
      <div className="flex h-9 w-14 items-center justify-center overflow-hidden rounded-md bg-[#FAFAF7]">
        {!failed ? <img src={partner.src} alt={partner.name} className="max-h-8 max-w-full object-contain" onError={() => setFailed(true)}/> : <span className="text-[9px] font-bold tracking-[.08em]" style={{ color: C.forest }}>{partner.short}</span>}
      </div>
      <div className="min-w-0"><div className="truncate text-xs font-semibold">{partner.short}</div><div className="mt-0.5 text-[9px]" style={{ color: C.muted }}>Official site ↗</div></div>
    </a>
  );
}

function AppTopBar({ account, onMenu }) {
  const navigate = useNavigate();
  const [accountOpen, setAccountOpen] = useState(false);

  const logout = () => {
    localStorage.removeItem("ipshakti_account");
    localStorage.removeItem("ipshakti_verified");
    navigate("/login");
  };

  return (
    <header className="relative z-[100] shrink-0 border-b bg-white/90 px-4 py-3 backdrop-blur-md md:px-6" style={{ borderColor: C.line }}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={onMenu} className="grid h-8 w-8 place-items-center rounded-lg border md:hidden" style={{ borderColor: C.line }}><Menu size={16}/></button>
          <SealMark size={34}/>
          <div className="min-w-0">
            <h1 className={`${SERIF} truncate text-sm font-semibold`}>IP-SHAKTI SAHAYAK</h1>
            <span className={`${MONO} block truncate text-[9px] tracking-wide`} style={{ color: C.muted }}>Legal research assistant · Ayurveda IP</span>
          </div>
        </div>

        <div className="hidden items-center gap-3 lg:flex">
          <SelectDropdown label="Jurisdiction" value={localStorage.getItem("ipshakti_jurisdiction") || "national"} options={JURISDICTIONS} onChange={(v) => localStorage.setItem("ipshakti_jurisdiction", v)}/>
          <SelectDropdown label="Output Language" value={localStorage.getItem("ipshakti_language") || "English"} options={LANGUAGES.map(x => ({ value:x, label:x }))} onChange={(v) => localStorage.setItem("ipshakti_language", v)}/>
          <button onClick={() => navigate("/account")} className="ml-2 grid h-9 w-9 place-items-center rounded-full" style={{ background: C.forest, color: C.parchment }}>
            {(account?.name || "IP").split(" ").map(x => x[0]).join("").slice(0,2).toUpperCase()}
          </button>
          <button onClick={() => setAccountOpen(v => !v)} aria-label="Account menu"><ChevronDown size={15}/></button>
        </div>

        <div className="flex items-center gap-2 lg:hidden">
          <button onClick={() => navigate("/account")} className="grid h-9 w-9 place-items-center rounded-full" style={{ background: C.forest, color: C.parchment }}>
            {(account?.name || "IP").split(" ").map(x => x[0]).join("").slice(0,2).toUpperCase()}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {accountOpen && (
          <motion.div initial={{opacity:0,y:-5,scale:0.98}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,y:-5,scale:0.98}} transition={{duration:0.16}} className="absolute right-4 top-[62px] z-[200] w-56 rounded-2xl border bg-white p-2 shadow-[0_18px_50px_rgba(38,49,42,.14)] md:right-6" style={{ borderColor: C.line }}>
            <button onClick={() => navigate("/account")} className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-sm hover:bg-[#FAF8F1]"><User size={14}/> Account</button>
            <button onClick={() => navigate("/settings")} className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-sm hover:bg-[#FAF8F1]"><Settings size={14}/> Account settings</button>
            <button onClick={logout} className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-sm hover:bg-[#FAF8F1]"><ArrowLeft size={14}/> Logout</button>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}

function SelectDropdown({ label, value, options, onChange }) {
  return (
    <label className="flex flex-col gap-1">
      <span className={`${MONO} text-[9px] font-semibold`} style={{ color: C.muted }}>{label}</span>
      <select value={value} onChange={e => onChange(e.target.value)} className="cursor-pointer rounded-lg border bg-white px-3 py-1.5 text-xs outline-none" style={{ borderColor: C.line }}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

function SideNav({ open, onClose, chats, activeChat, onNew, onSelect }) {
  return (
    <>
      <AnimatePresence>
        {open && <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="fixed inset-0 z-40 bg-[#26312A]/30 md:hidden" onClick={onClose}/>}
      </AnimatePresence>

      <aside className={`fixed inset-y-0 left-0 z-50 flex w-[290px] flex-col border-r bg-[#F8F6EE] transition-transform duration-300 md:static md:z-auto md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`} style={{ borderColor: C.line }}>
        <div className="flex h-16 shrink-0 items-center justify-between border-b px-5" style={{ borderColor: C.line }}>
          <div className="flex items-center gap-2"><SealMark size={30}/><span className={`${SERIF} text-sm font-semibold`}>Research desk</span></div>
          <button onClick={onClose} className="md:hidden"><X size={17}/></button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          <button onClick={onNew} className="flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm font-semibold" style={{ background: C.forest, color: C.parchment }}>
            <MessageCircle size={15}/> New research
          </button>

          <div className="mt-7">
            <div className={`${MONO} px-2 text-[9px] tracking-[.13em]`} style={{ color: C.muted }}>RECENT RESEARCH</div>
            <div className="mt-3 space-y-1">
              {chats.length === 0 && (
                <div className="rounded-xl border border-dashed p-4 text-xs leading-5" style={{ borderColor: C.line, color: C.muted }}>
                  Your saved questions will appear here.
                </div>
              )}
              {chats.map(chat => (
                <button key={chat.id} onClick={() => onSelect(chat.id)} className={`group flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition ${activeChat === chat.id ? "bg-white shadow-sm" : "hover:bg-white/70"}`}>
                  <div className="mt-0.5 grid h-7 w-7 place-items-center rounded-lg" style={{ background: C.brassLt, color: C.brass }}><FileText size={13}/></div>
                  <div className="min-w-0"><div className="truncate text-xs font-medium">{chat.title}</div><div className="mt-1 text-[10px]" style={{ color: C.muted }}>{chat.count} result{chat.count === 1 ? "" : "s"}</div></div>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-8">
            <div className={`${MONO} px-2 text-[9px] tracking-[.13em]`} style={{ color: C.muted }}>RESOURCES</div>
            <div className="mt-2 space-y-1">
              <WorkspaceLink icon={<BookOpen size={14}/>} label="Help & documentation" onClick={() => window.location.href="/help"}/>
            </div>
          </div>
        </div>

        <div className="border-t p-4" style={{ borderColor: C.line }}>
          <div className="rounded-xl border bg-white p-3" style={{ borderColor: C.line }}>
            <div className="flex items-center gap-2 text-[10px] font-semibold"><ShieldCheck size={13} style={{ color: C.forest }}/> Evidence-first workspace</div>
            <p className="mt-2 text-[10px] leading-4" style={{ color: C.muted }}>Use the source panel to verify the underlying document before relying on a result.</p>
          </div>
        </div>
      </aside>
    </>
  );
}

function WorkspaceLink({ icon, label, onClick }) {
  return <button onClick={onClick} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-xs font-medium hover:bg-white">{icon}{label}</button>;
}

function EmptyState({ onSend }) {
  return (
    <div className="relative flex h-full min-h-[540px] flex-col justify-center px-1 py-8 md:px-10">
      <div className="mx-auto grid w-full max-w-6xl gap-10 lg:grid-cols-[.88fr_1.12fr] lg:items-center">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5" style={{ borderColor: "#2F6B3E25", background: "#2F6B3E08", color: C.forest }}>
            <Sparkles size={12}/><span className={`${MONO} text-[9px] font-semibold tracking-wide`}>AI legal research assistant · AYUSH IP</span>
          </div>
          <h2 className={`${SERIF} mt-7 text-6xl leading-[.88] tracking-[-.045em] md:text-7xl`}>IP-SHAKTI<br/><i style={{ color: C.forest }}>Sahayak.</i></h2>
          <p className="mt-6 max-w-xl text-base leading-7" style={{ color: "#6E6852" }}>
            Ayurveda intellectual property and regulatory research — every answer traced to a statute, treaty article or registry record.
          </p>

          <div className="mt-9 grid gap-3 sm:grid-cols-3">
            <TrustPill icon={<ShieldCheck size={14}/>} text="Evidence-first"/>
            <TrustPill icon={<Clock size={14}/>} text="Search in context"/>
            <TrustPill icon={<Scale size={14}/>} text="Not legal advice"/>
          </div>

          <div className="mt-9 grid gap-3 sm:grid-cols-3">
            {PARTNERS.map(p => <PartnerLogo key={p.short} partner={p}/>)}
          </div>
        </div>

        <div>
          <div className={`${MONO} mb-3 px-1 text-[9px] font-semibold tracking-[.15em]`} style={{ color: C.muted }}>SUGGESTED STARTING POINTS</div>
          <div className="grid gap-3 sm:grid-cols-2">
            {QUICK_STARTERS.map((q, i) => (
              <motion.button
                key={q.label}
                initial={{opacity:0,y:12}}
                animate={{opacity:1,y:0}}
                transition={{delay:.07*i}}
                whileHover={{y:-2}}
                whileTap={{scale:.98}}
                onClick={() => onSend(q.label)}
                className="group flex min-h-[155px] flex-col items-start rounded-2xl border bg-white p-5 text-left transition"
                style={{ borderColor: C.line }}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="text-xl">{q.icon}</span>
                  <span className={`${MONO} rounded-full px-2 py-1 text-[8px] font-semibold`} style={{ background: C.brassLt, color: C.brass }}>{q.tag}</span>
                </div>
                <span className="mt-5 text-sm font-medium leading-snug">{q.label}</span>
                <span className="mt-auto inline-flex items-center gap-1 pt-4 text-[10px] font-semibold" style={{ color: C.muted }}>Ask this <ArrowRight size={11}/></span>
              </motion.button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function TrustPill({ icon, text }) {
  return <div className="flex items-center gap-2 text-xs" style={{ color: "#6E6852" }}>{icon}{text}</div>;
}

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-900">
          <h2 className="font-bold">Render Error</h2>
          <pre className="mt-2 text-xs overflow-auto">{this.state.error.message}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

function MessageBubble({ msg, onViewReferences, onListen }) {
  const isUser = msg.role === "user";
  if (msg.type === "research") {
    return (
      <ResearchCard data={msg.researchData} onViewReferences={onViewReferences} onListen={onListen}/>
    );
  }

  return (
    <motion.div initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} className={`mx-auto flex w-full max-w-4xl items-start gap-4 rounded-2xl p-4 md:p-6 ${isUser ? "" : "border bg-white shadow-[0_2px_10px_rgba(38,49,42,.045)]"}`} style={{ borderColor: C.line }}>
      <div className="shrink-0">
        {isUser ? <div className="grid h-8 w-8 place-items-center rounded-full border" style={{ background: C.brassLt, borderColor: "#E6D8AE", color: "#8C6A2A" }}><User size={15}/></div> : <SealMark size={32}/>}
      </div>
      <div className="min-w-0 flex-1">
        <div className={`${MONO} mb-1 text-[9px] font-semibold tracking-wide`} style={{ color: C.muted }}>{isUser ? "YOU" : "IP-SHAKTI SAHAYAK"}</div>
        <div className="whitespace-pre-wrap text-sm leading-7" style={{ color: "#495245" }}>{msg.text}</div>
        {!isUser && msg.text && <button onClick={() => onListen?.(msg.text)} className="mt-3 inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px]" style={{ borderColor: C.line, color: C.muted }}><Volume2 size={12}/> Listen</button>}
      </div>
    </motion.div>
  );
}

function ResearchCard({ data, onViewReferences, onListen }) {
  const [showTrace, setShowTrace] = useState(false);

  if (!data) return null;

  if (data.abstained) {
    return (
      <div className="mx-auto w-full max-w-4xl rounded-2xl border bg-white p-6 shadow-sm" style={{ borderColor: C.line }}>
        <h3 className="text-sm font-semibold mb-2" style={{ color: C.warn }}>Information Not Provided</h3>
        <p className="text-sm text-gray-700">{data.abstain_reason || "The assistant abstained from answering this query."}</p>
        
        {data.execution_trace && data.execution_trace.length > 0 && (
          <div className="mt-4 border-t pt-4" style={{ borderColor: C.line }}>
            <button 
              onClick={() => setShowTrace(!showTrace)} 
              className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium hover:bg-gray-50"
              style={{ borderColor: C.line }}
            >
              <Settings size={14} style={{ color: C.muted }} />
              {showTrace ? "Hide Trace Debug" : "Show Trace Debug"}
            </button>
            {showTrace && (
              <pre className="mt-4 max-h-[300px] overflow-auto whitespace-pre-wrap rounded-xl bg-gray-50 border p-4 text-[10px]" style={{ borderColor: C.line }}>
                {data.execution_trace.join("\n")}
              </pre>
            )}
          </div>
        )}
      </div>
    );
  }

  const hasNational = !!data.national_answer?.answer;
  const hasInternational = !!data.international_answer?.answer;
  const totalCitations = (data.national_citations?.length || 0) + (data.international_citations?.length || 0);

  return (
    <div className="mx-auto w-full max-w-4xl rounded-2xl border bg-white p-6 shadow-sm" style={{ borderColor: C.line }}>
      <div className="flex flex-col gap-6">
        {hasNational && (
          <AnswerSection 
            title="National (India) Perspective" 
            answer={data.national_answer} 
            onListen={onListen} 
            separated={false} 
          />
        )}
        
        {hasInternational && (
          <AnswerSection 
            title="International Perspective" 
            answer={data.international_answer} 
            onListen={onListen} 
            separated={hasNational} 
          />
        )}

        {!hasNational && !hasInternational && (
           <p className="text-sm text-gray-500 italic">No answer was generated.</p>
        )}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3 border-t pt-4" style={{ borderColor: C.line }}>
        {totalCitations > 0 && (
          <button 
            onClick={() => onViewReferences(data)} 
            className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium hover:bg-gray-50"
            style={{ borderColor: C.line }}
          >
            <BookOpen size={14} style={{ color: C.forest }} />
            View {totalCitations} Reference{totalCitations !== 1 && "s"}
          </button>
        )}
        
        {data.execution_trace && data.execution_trace.length > 0 && (
          <button 
            onClick={() => setShowTrace(!showTrace)} 
            className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium hover:bg-gray-50"
            style={{ borderColor: C.line }}
          >
            <Settings size={14} style={{ color: C.muted }} />
            {showTrace ? "Hide Trace Debug" : "Show Trace Debug"}
          </button>
        )}
      </div>
      
      {showTrace && data.execution_trace && data.execution_trace.length > 0 && (
        <div className="mt-4 rounded-xl bg-gray-50 p-4 border" style={{ borderColor: C.line }}>
          <h4 className={`${MONO} text-[9px] font-semibold tracking-wide mb-2`} style={{ color: C.muted }}>EXECUTION TRACE</h4>
          <pre className="max-h-[300px] overflow-auto whitespace-pre-wrap text-[10px] text-gray-700">
            {data.execution_trace.join("\n")}
          </pre>
        </div>
      )}
    </div>
  );
}

function AnswerSection({ title, answer, separated, onListen, playing }) {
  if (!answer || !answer.answer) return null;

  const content = typeof answer.answer === "string" 
    ? answer.answer 
    : JSON.stringify(answer.answer, null, 2);

  return (
    <section
      className={separated ? "mt-6 border-t pt-6" : ""}
      style={{ borderColor: C.line }}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          {title}
        </h3>

        <button
          onClick={() => onListen?.(content)}
          className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px]"
          style={{ borderColor: C.line, color: C.muted }}
        >
          {playing ? <VolumeX size={12} /> : <Volume2 size={12} />}
          {playing ? "Stop" : "Listen"}
        </button>
      </div>

      <p
        className="whitespace-pre-wrap text-sm leading-7"
        style={{ color: "#495245" }}
      >
        {content}
      </p>

      {answer.standing_disclaimer && (
        <div
          className="mt-5 border-t pt-4 text-xs leading-5"
          style={{
            borderColor: C.line,
            color: C.muted
          }}
        >
          {String(answer.standing_disclaimer)}
        </div>
      )}
    </section>
  );
}

function TypingState() {
  return (
    <motion.div initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} className="mx-auto flex w-full max-w-4xl items-center gap-4 rounded-2xl border bg-white p-5" style={{borderColor:C.line}}>
      <SealMark size={32}/>
      <div><div className={`${MONO} text-[9px] font-semibold`} style={{color:C.muted}}>IP-SHAKTI SAHAYAK</div><div className="mt-1 flex items-center gap-2 text-sm italic" style={{color:"#6E6852"}}><span className="h-1.5 w-1.5 animate-pulse rounded-full" style={{background:C.brass}}/> Thinking through sources…</div></div>
    </motion.div>
  );
}

function ClarificationQuestion({ question, onAnswer }) {
  return (
    <motion.div initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} className="mx-auto flex w-full max-w-4xl items-start gap-4">
      <SealMark size={32}/>
      <div className="relative w-full overflow-hidden rounded-2xl border bg-white p-6" style={{borderColor:C.line}}>
        <span className="absolute inset-y-0 left-0 w-1.5" style={{background:C.brass}}/>
        <div className={`${MONO} text-[9px] tracking-wide`} style={{color:C.brass}}>CLARIFICATION NEEDED</div>
        <h2 className={`${SERIF} mt-2 text-xl`}>{question}</h2>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {["Yes","No"].map(v => <button key={v} onClick={() => onAnswer(v)} className="flex items-center justify-between rounded-xl border p-4 text-left transition hover:-translate-y-0.5" style={{borderColor:C.line}}><div><strong className="block text-sm">{v}</strong><span className="text-xs" style={{color:C.muted}}>{v === "Yes" ? "This applies" : "This does not apply"}</span></div><ArrowRight size={14} style={{color:C.muted}}/></button>)}
        </div>
      </div>
    </motion.div>
  );
}

function ReferenceSidebar({ data, onClose }) {
  const [activePdf, setActivePdf] = useState(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const all = [
    ...(data?.national_citations || []).map(x => ({...x, group:"Indian"})),
    ...(data?.international_citations || []).map(x => ({...x, group:"International"})),
  ];
  const filtered = all.filter(ref => `${ref.act_name || ""} ${ref.section_or_article || ""}`.toLowerCase().includes(query.toLowerCase()));
  const pageSize = 4;
  const paginated = filtered.slice((page-1)*pageSize, page*pageSize);
  const pages = Math.max(1, Math.ceil(filtered.length/pageSize));

  return (
    <>
      <div className="fixed inset-0 z-40 bg-[#26312A]/25 backdrop-blur-[2px]" onClick={onClose}/>
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l bg-[#FAF8F1] shadow-2xl sm:w-[460px]" style={{borderColor:C.line}}>
        <div className="flex items-center justify-between border-b bg-white p-5" style={{borderColor:C.line}}>
          <div><h2 className={`${SERIF} text-xl`}>References & Sources</h2><p className="mt-1 text-[10px]" style={{color:C.muted}}>Verify against the underlying document.</p></div>
          <button onClick={onClose} className="rounded-full p-2 hover:bg-[#F4E8CB]/40"><X size={17}/></button>
        </div>

        <div className="border-b bg-white p-4" style={{borderColor:C.line}}>
          <div className="relative"><Search className="absolute left-3 top-1/2 -translate-y-1/2" size={14} style={{color:C.muted}}/><input value={query} onChange={e => {setQuery(e.target.value);setPage(1)}} placeholder="Filter references…" className="w-full rounded-xl border bg-transparent py-2.5 pl-9 pr-3 text-xs outline-none" style={{borderColor:C.line}}/></div>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {paginated.length === 0 && <div className="py-12 text-center text-sm italic" style={{color:C.muted}}>No matching verified sources.</div>}
          {paginated.map((ref, i) => (
            <div key={`${ref.index}-${i}`} className="relative mb-3 rounded-xl border bg-white p-4 pl-5" style={{borderColor:C.line}}>
              <span className="absolute inset-y-0 left-0 w-1.5 rounded-l-xl" style={{background:C.brass}}/>
              <div className="flex items-start gap-3">
                <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full" style={{background:C.brassLt,color:"#8C6A2A"}}><ScrollText size={14}/></div>
                <div className="min-w-0 flex-1">
                  <div className={`${MONO} text-[9px]`} style={{color:C.brass}}>Official source · E{ref.index || i + 1}</div>
                  <div className={`${SERIF} mt-1 text-[15px] font-medium`}>{ref.act_name || ref.title || "Source record"}</div>
                  {ref.section_or_article && <div className="mt-0.5 text-xs font-medium" style={{color:"#6E6852"}}>{ref.section_or_article}</div>}
                  <div className="mt-2 text-[9px] font-semibold" style={{color:C.muted}}>{ref.group}</div>
                  {ref.document_id ? <button onClick={() => setActivePdf(ref)} className="mt-2 inline-flex items-center gap-1 text-xs font-semibold" style={{color:C.forest}}>Verify original document <ArrowRight size={12}/></button> : (
                    <a href={ref.url || "#"} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs font-semibold" style={{color:C.forest}}>Open source <ExternalLink size={12}/></a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between border-t bg-white p-4" style={{borderColor:C.line}}>
          <button disabled={page<=1} onClick={() => setPage(v=>v-1)} className="rounded-lg border px-3 py-2 text-xs disabled:opacity-35" style={{borderColor:C.line}}>Previous</button>
          <span className={`${MONO} text-[9px]`} style={{color:C.muted}}>Page {page} / {pages}</span>
          <button disabled={page>=pages} onClick={() => setPage(v=>v+1)} className="rounded-lg border px-3 py-2 text-xs disabled:opacity-35" style={{borderColor:C.line}}>Next</button>
        </div>

        <AnimatePresence>
          {activePdf && (
            <motion.div initial={{x:"100%"}} animate={{x:0}} exit={{x:"100%"}} className="absolute inset-0 z-10 flex flex-col bg-[#FAF8F1]">
              <div className="flex items-center justify-between border-b bg-white p-4" style={{borderColor:C.line}}>
                <button onClick={() => setActivePdf(null)} className="inline-flex items-center gap-1.5 text-xs font-medium" style={{color:C.muted}}><ArrowLeft size={14}/> Back to sources</button>
                <button onClick={() => setActivePdf(null)}><X size={17}/></button>
              </div>
              <div className="flex-1 p-4">
                {activePdf.document_id ? (
                  <iframe src={`${API_BASE_URL}/pdf/${encodeURIComponent(activePdf.document_id)}#page=${activePdf.page_start || 1}`} title="PDF verification" className="h-full w-full rounded-xl border bg-white" style={{borderColor:C.line}}/>
                ) : (
                  <div className="grid h-full place-items-center rounded-xl border bg-white p-6 text-center" style={{borderColor:C.line}}>
                    <div><FileText className="mx-auto" size={28} style={{color:C.muted}}/><p className="mt-3 text-sm">Wire your PDF route here.</p></div>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </aside>
    </>
  );
}

function Research() {
  const reduceMotion = useReducedMotion();
  const [account] = useState(() => {
    try { return JSON.parse(localStorage.getItem("ipshakti_account") || "null"); } catch { return null; }
  });
  const [menuOpen, setMenuOpen] = useState(false);
  const [messages, setMessages] = useState([
    { id: 1, role: "assistant", type: "text", text: "Welcome to IP-SHAKTI Sahayak.\n\nAsk a question about patents, TKDL, biodiversity, GI, regulatory classification, treaties or formulation research." }
  ]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [pending, setPending] = useState(null);
  const [referenceData, setReferenceData] = useState(null);
  const [chats, setChats] = useState(() => {
    try { return JSON.parse(localStorage.getItem("ipshakti_chats") || "[]"); } catch { return []; }
  });
  const [status, setStatus] = useState("Ready");
  const [sessionId, setSessionId] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" });
  }, [messages, typing, pending, reduceMotion]);

  useEffect(() => {
    localStorage.setItem("ipshakti_chats", JSON.stringify(chats));
  }, [chats]);

  useEffect(() => {
    if (sessionId && messages.length > 0) {
      localStorage.setItem(`ipshakti_msgs_${sessionId}`, JSON.stringify(messages));
    }
  }, [sessionId, messages]);

  const loadChat = (chatId) => {
    if (typing || pending) return;
    const saved = localStorage.getItem(`ipshakti_msgs_${chatId}`);
    if (saved) {
      try {
        let loaded = JSON.parse(saved);
        if (loaded.length > 0 && (!loaded[0].text || !loaded[0].text.includes("Welcome to IP-SHAKTI Sahayak"))) {
          loaded = [{ id: 1, role: "assistant", type: "text", text: "Welcome to IP-SHAKTI Sahayak.\n\nAsk a question about patents, TKDL, biodiversity, GI, regulatory classification, treaties or formulation research." }, ...loaded];
        }
        setMessages(loaded);
        setSessionId(chatId);
        setPending(null);
        setReferenceData(null);
      } catch (error) {
        console.error("Failed to load chat history", error);
      }
    }
    setMenuOpen(false);
  };

  const send = async (text) => {
    const q = text.trim();
    if (!q || typing) return;
    setMessages(prev => [...prev, { id: Date.now(), role: "user", type:"text", text:q }]);
    setInput("");
    setTyping(true);
    setStatus("Analyzing…");

    try {
      let currentSessionId = sessionId;
      const jurisdictionMode = localStorage.getItem("ipshakti_jurisdiction") || "national";
      const language = localStorage.getItem("ipshakti_language") || "English";

      if (!currentSessionId) {
        currentSessionId = await api.createSession(jurisdictionMode, language);
        setSessionId(currentSessionId);
      }

      const rawResponse = await api.sendChatMessage(currentSessionId, q, jurisdictionMode, language);
      const response = rawResponse?.data ?? rawResponse;
      
      console.log("BACKEND RESPONSE:", response);
      
      if (!response || typeof response !== "object") {
        throw new Error("Invalid response received from backend");
      }

      if (response.type === "clarification") {
        setPending(response.question);
        setTyping(false);
        setStatus("Waiting for clarification");
        return;
      }

      const normalizeAnswer = (answer) => {
        if (!answer) return null;
        if (typeof answer === "string") {
          return { answer, standing_disclaimer: null };
        }
        if (typeof answer === "object") {
          let text = answer.answer;
          if (typeof text === "object" && text !== null) {
            text = JSON.stringify(text, null, 2);
          }
          return {
            answer: typeof text === "string" ? text : String(text ?? ""),
            standing_disclaimer: answer.standing_disclaimer ? String(answer.standing_disclaimer) : null
          };
        }
        return { answer: String(answer), standing_disclaimer: null };
      };

      const replyMsg = {
        id: Date.now() + 1,
        type: "research",
        role: "assistant",
        researchData: {
          jurisdiction_mode: response.jurisdiction_mode || jurisdictionMode,
          formulation_category: response.formulation_category || "ayurveda",
          overall_status: response.overall_status || "UNKNOWN",
          abstained: Boolean(response.abstained),
          abstain_reason: response.abstain_reason || null,
          national_answer: normalizeAnswer(response.national_answer),
          international_answer: normalizeAnswer(response.international_answer),
          national_citations: Array.isArray(response.national_citations) ? response.national_citations : [],
          international_citations: Array.isArray(response.international_citations) ? response.international_citations : [],
          execution_trace: Array.isArray(response.execution_trace) ? response.execution_trace : []
        }
      };

      setMessages(prev => [...prev, replyMsg]);
      setChats(prev => {
        if (prev.some(c => c.id === currentSessionId)) return prev;
        return [{ id: currentSessionId, title: q.length > 34 ? q.slice(0,34) + "…" : q, count: 1 }, ...prev].slice(0, 10);
      });
    } catch (error) {
      console.error(error);
      setMessages(prev => [...prev, { id: Date.now() + 1, role: "assistant", type: "text", text: "Sorry, an error occurred while connecting to the server: " + error.message }]);
    } finally {
      setTyping(false);
      setStatus("Ready");
    }
  };

  const onClarification = (answer) => {
    setPending(null);
    send(answer);
  };

  const listenText = (text) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = (localStorage.getItem("ipshakti_language") || "English") === "Hindi" ? "hi-IN" : "en-IN";
    u.rate = .9;
    window.speechSynthesis.speak(u);
  };

  const newResearch = () => {
    setMessages([{ id: 1, role: "assistant", type: "text", text: "Welcome to IP-SHAKTI Sahayak.\n\nAsk a question about patents, TKDL, biodiversity, GI, regulatory classification, treaties or formulation research." }]);
    setSessionId(null);
    setPending(null);
    setInput("");
    setReferenceData(null);
    setTyping(false);
    setStatus("Ready");
  };

  return (
    <ErrorBoundary>
      <div className="flex h-[100dvh] overflow-hidden bg-[#FAF8F1] font-['IBM_Plex_Sans'] antialiased" style={{color:C.ink}}>
      <SideNav open={menuOpen} onClose={() => setMenuOpen(false)} chats={chats} activeChat={sessionId} onNew={newResearch} onSelect={loadChat} />

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <AppTopBar account={account} onMenu={() => setMenuOpen(true)}/>

        <section className="min-h-0 flex-1 overflow-hidden">
          <div className="flex h-full flex-col">
            <div className="flex-1 overflow-y-auto px-3 py-5 md:px-8 md:py-7">
              {messages.length === 1 && !typing && !pending ? (
                <EmptyState onSend={send}/>
              ) : (
                <div className="space-y-4">
                  <AnimatePresence initial={false}>
                    {messages.map(msg => (
                      <ErrorBoundary key={msg.id}>
                        <MessageBubble msg={msg} onViewReferences={setReferenceData} onListen={listenText}/>
                      </ErrorBoundary>
                    ))}
                  </AnimatePresence>

                  {pending && <ClarificationQuestion question={pending} onAnswer={onClarification}/>}
                  {typing && <TypingState/>}
                  <div ref={bottomRef}/>
                </div>
              )}
            </div>

            {!pending && (
              <div className="shrink-0 border-t bg-white/70 px-3 py-4 backdrop-blur-md md:px-8" style={{borderColor:C.line}}>
                <div className="mx-auto max-w-4xl">
                  <div className="flex items-end gap-2 rounded-2xl border bg-white p-2 focus-within:shadow-[0_0_0_3px_rgba(47,107,62,.08)]" style={{borderColor:C.line}}>
                    <textarea
                      value={input}
                      onChange={e => setInput(e.target.value)}
                      onKeyDown={e => { if(e.key==="Enter" && !e.shiftKey){e.preventDefault();send(input)} }}
                      rows={1}
                      placeholder="Ask about patentability, TKDL, ABS compliance, GI, or formulation classification…"
                      className="min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-sm outline-none"
                    />
                    <button disabled={!input.trim() || typing} onClick={() => send(input)} className="grid h-10 w-10 shrink-0 place-items-center rounded-xl disabled:opacity-35" style={{background:C.forest,color:C.parchment}}>
                      <ArrowUp size={17} strokeWidth={2.5}/>
                    </button>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[9px]" style={{color:C.muted}}>
                    <span>{status}</span><span>Information, not legal advice.</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        <div className="shrink-0 border-t bg-white/80 px-4 py-2.5 text-[9px] backdrop-blur-md" style={{borderColor:C.line,color:C.muted}}>
          <div className="mx-auto flex max-w-4xl items-center gap-2"><Info size={12}/><span>Verify the current law and official source before relying on any result.</span></div>
        </div>
      </main>

      {referenceData && <ReferenceSidebar data={referenceData} onClose={() => setReferenceData(null)}/>}
    </div>
    </ErrorBoundary>
  );
}

export default Research;
