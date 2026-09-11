import { useEffect, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { BookOpen } from "lucide-react";

const PHRASES = [
  ["Ask in your language", "English"],
  ["अपनी भाषा में पूछें", "हिंदी"],
  ["உங்கள் மொழியில் கேளுங்கள்", "தமிழ்"],
  ["আপনার ভাষায় জিজ্ঞাসা করুন", "বাংলা"],
  ["तुमच्या भाषेत विचारा", "मराठी"],
  ["તમારી ભાષામાં પૂછો", "ગુજરાતી"],
];

function LanguageCycler() {
  const [index, setIndex] = useState(0);
  const reduce = useReducedMotion();

  useEffect(() => {
    const id = setInterval(() => setIndex(i => (i + 1) % PHRASES.length), 2600);
    return () => clearInterval(id);
  }, []);

  const [text, lang] = PHRASES[index];

  return (
    <div className="relative h-10 overflow-hidden" aria-live="polite">
      <AnimatePresence mode="wait">
        <motion.div
          key={lang}
          initial={reduce ? {opacity:0} : {opacity:0,y:14}}
          animate={{opacity:1,y:0}}
          exit={reduce ? {opacity:0} : {opacity:0,y:-14}}
          transition={{duration:.5,ease:[.22,1,.36,1]}}
          className="absolute inset-0 flex items-baseline gap-3"
        >
          <span className="text-lg font-medium text-[#F7F3E9]">{text}</span>
          <span className="text-xs tracking-wide text-[#9AB08C]">{lang}</span>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

/*
  Same original botanical language, but with the missing bloom added.
  The flower is deliberately drawn as a hand-inked Ayurvedic specimen:
  a saffron flower head, green leaves and a tiny seed pod.
*/
function BotanicalMark() {
  const reduce = useReducedMotion();
  const draw = (delay=0) => ({
    initial: reduce ? false : { pathLength: 0, opacity: 0 },
    animate: { pathLength:1, opacity:1 },
    transition: { duration:1.05, delay, ease:"easeInOut" }
  });

  return (
    <div className="relative">
      <svg viewBox="0 0 240 320" className="h-52 w-44 md:h-60 md:w-48" fill="none">
        <motion.path d="M115 304 C 113 240,122 184,109 126 C 101 91,109 48,128 19" stroke="#9AB08C" strokeWidth="2" strokeLinecap="round" {...draw(0)} />
        <motion.path d="M109 181 C 83 167,59 172,38 147 C 57 141,82 148,101 164" stroke="#C97A2B" strokeWidth="2" strokeLinecap="round" {...draw(.35)} />
        <motion.path d="M113 131 C 139 118,161 120,181 96 C 162 88,138 93,120 112" stroke="#9AB08C" strokeWidth="2" strokeLinecap="round" {...draw(.55)} />
        <motion.path d="M110 225 C 88 213,67 215,50 196" stroke="#9AB08C" strokeWidth="1.6" strokeLinecap="round" {...draw(.7)} />

        {/* Bloom */}
        <motion.g
          initial={reduce ? false : { opacity:0, scale:.55, transformOrigin:"128px 19px" }}
          animate={{ opacity:1, scale:1 }}
          transition={{ duration:.7, delay:1.15, type:"spring", stiffness:180, damping:17 }}
        >
          <path d="M128 19 C119 9 119 1 128 -6 C137 1 138 9 128 19Z" fill="#C97A2B" fillOpacity=".92"/>
          <path d="M128 19 C138 10 146 10 152 18 C145 25 137 26 128 19Z" fill="#D7C18F"/>
          <path d="M128 19 C138 27 140 36 132 42 C124 36 123 28 128 19Z" fill="#A7BC99"/>
          <path d="M128 19 C118 28 109 28 104 20 C111 13 120 13 128 19Z" fill="#C97A2B" fillOpacity=".78"/>
          <circle cx="128" cy="19" r="4" fill="#F4E8CB"/>
          <circle cx="128" cy="19" r="2" fill="#C97A2B"/>
        </motion.g>

        <motion.circle cx="128" cy="19" r="3.5" fill="#C97A2B"
          initial={reduce ? false : {scale:0,opacity:0}} animate={{scale:1,opacity:1}}
          transition={{duration:.4,delay:1.65}}/>
      </svg>

      {/* Ayurveda-inspired ingredient specimen */}
      <motion.div
        initial={{opacity:0,x:-8}}
        animate={{opacity:1,x:0}}
        transition={{delay:1.45,duration:.6}}
        className="absolute -bottom-1 left-32 hidden md:block"
      >
        <div className="relative h-14 w-20">
          <div className="absolute bottom-1 left-1/2 h-7 w-14 -translate-x-1/2 rounded-b-[18px] border-2 border-[#C97A2B]/70" />
          <div className="absolute bottom-6 left-1/2 h-3 w-16 -translate-x-1/2 rounded-full border border-[#C97A2B]/70" />
          <div className="absolute left-1/2 top-0 h-8 w-[2px] -translate-x-1/2 bg-[#9AB08C]/70" />
          <div className="absolute left-1/2 top-1 h-5 w-9 -translate-x-[20%] rounded-full border border-[#9AB08C]/70 rotate-[28deg]" />
        </div>
      </motion.div>
    </div>
  );
}

function Bookshelf() {
  const reduce = useReducedMotion();
  const books = [
    ["PATENTS", "#C97A2B", 62],
    ["RULES", "#7E8E70", 73],
    ["TRADE MARKS", "#E0CFA6", 84],
    ["BIODIVERSITY", "#8CA18A", 68],
    ["GI", "#B06E39", 78],
    ["WIPO", "#506956", 70],
  ];

  return (
    <motion.div
      initial={{opacity:0,y:10}}
      animate={{opacity:1,y:0}}
      transition={{delay:.7,duration:.7}}
      className="absolute bottom-20 right-8 hidden xl:block"
      aria-label="Illustrated bookshelf of Acts and Rules"
    >
      <div className="mb-2 flex items-center gap-2 text-[8px] tracking-[.15em] text-[#9AB08C]">
        <BookOpen size={11}/> ACTS · RULES · TREATIES
      </div>
      <div className="relative w-48 border-x border-[#3A5A42] px-3 pb-3 pt-2">
        <div className="grid h-24 grid-flow-col grid-rows-2 items-end justify-center gap-1.5">
          {books.map(([label, bg, h], i) => (
            <motion.div
              key={label}
              animate={reduce ? undefined : { y:[0,-2,0] }}
              transition={{duration:4+i*.4,repeat:Infinity,ease:"easeInOut"}}
              className="flex items-center justify-center rounded-[2px] px-1 text-[7px] font-semibold text-[#1F3D2B]"
              style={{height:h/2,width:22,background:bg,writingMode:"vertical-rl"}}
            >
              {label}
            </motion.div>
          ))}
        </div>
        <div className="h-1.5 rounded-sm bg-[#6A765F]"/>
        <div className="mt-3 h-1.5 rounded-sm bg-[#6A765F]"/>
      </div>
    </motion.div>
  );
}

function AssistantBot() {
  const reduce = useReducedMotion();

  return (
    <motion.div
      initial={{opacity:0,scale:.9}}
      animate={{opacity:1,scale:1}}
      transition={{delay:1,duration:.7}}
      className="absolute bottom-14 right-[35%] hidden lg:block"
    >
      <motion.div
        animate={reduce ? undefined : {y:[0,-5,0]}}
        transition={{duration:4,repeat:Infinity,ease:"easeInOut"}}
        className="relative"
      >
        <div className="absolute -top-10 left-1/2 -translate-x-1/2 rounded-full border border-[#3A5A42] bg-[#1F3D2B] px-2.5 py-1 text-[8px] tracking-wide text-[#C7D3BE]">
          SAHAYAK
        </div>

        <div className="relative h-28 w-24 rounded-[30px] border border-[#526B55] bg-[#274934] shadow-[0_14px_30px_rgba(0,0,0,.16)]">
          <div className="absolute left-1/2 top-4 flex h-16 w-16 -translate-x-1/2 items-center justify-center rounded-[20px] border border-[#7D9A7C] bg-[#1F3D2B]">
            <div className="flex gap-3">
              <span className="h-2.5 w-2.5 rounded-full bg-[#D7C18F]"/>
              <span className="h-2.5 w-2.5 rounded-full bg-[#D7C18F]"/>
            </div>
            <div className="absolute bottom-2 h-1 w-7 rounded-full bg-[#C97A2B]/80"/>
          </div>

          <div className="absolute -left-2 top-10 h-7 w-2 rounded-full bg-[#516D56]"/>
          <div className="absolute -right-2 top-10 h-7 w-2 rounded-full bg-[#516D56]"/>
          <div className="absolute -bottom-3 left-4 h-5 w-3 rounded-b-md bg-[#516D56]"/>
          <div className="absolute -bottom-3 right-4 h-5 w-3 rounded-b-md bg-[#516D56]"/>
          <div className="absolute -top-2 left-1/2 h-4 w-[2px] -translate-x-1/2 bg-[#7D9A7C]"/>
          <span className="absolute -top-4 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-[#C97A2B]"/>
        </div>

        <div className="absolute -bottom-7 left-1/2 -translate-x-1/2 whitespace-nowrap text-[8px] text-[#7C9473]">
          your research assistant
        </div>
      </motion.div>
    </motion.div>
  );
}

export default function AuthLayout({ children }) {
  return (
    <div className="min-h-screen w-full bg-[#EDE6D6]">
      <div className="grid min-h-screen grid-cols-1 md:grid-cols-2">

        {/* LEFT — retain original composition, add visual depth */}
        <div className="relative hidden overflow-hidden bg-[#1F3D2B] px-10 py-10 md:flex md:flex-col md:justify-between lg:px-12">
          <div className="absolute inset-0 opacity-[.035]" style={{
            backgroundImage:"radial-gradient(#F7F3E9 1px, transparent 1px)",
            backgroundSize:"24px 24px"
          }}/>

          <div className="relative z-10 flex items-center gap-2">
            <span className="font-['Newsreader'] text-xl tracking-tight text-[#F7F3E9]">IP-SAKTI</span>
            <span className="mt-1 text-xs text-[#9AB08C]">सहायक</span>
          </div>

          <div className="relative z-10 flex flex-col gap-5">
            <BotanicalMark/>

            <div className="max-w-sm">
              <h1 className="font-['Newsreader'] text-3xl leading-snug text-[#F7F3E9] xl:text-4xl">
                Every answer, traced to its source.
              </h1>
              <p className="mt-3 text-sm leading-relaxed text-[#C7D3BE]">
                IP and regulatory guidance for Ayurvedic formulations, across
                Indian and international regimes — cited, not guessed.
              </p>
            </div>

            <LanguageCycler/>
          </div>

          <Bookshelf/>
          <AssistantBot/>

          <div className="relative z-10 flex items-end justify-between">
            <p className="text-xs text-[#7C9473]">
              Built for the Ministry of AYUSH · All India Institute of Ayurveda
            </p>

            <div className="grid h-16 w-16 place-items-center rounded-full border border-[#3A5A42]">
              <span className="text-[9px] tracking-widest text-[#7C9473]">§ CITED</span>
            </div>
          </div>
        </div>

        {/* RIGHT — original clean form panel */}
        <div className="flex items-center justify-center px-6 py-14 md:py-0">
          <div className="w-full max-w-sm">
            <div className="md:hidden mb-8 flex items-center gap-2">
              <span className="font-['Newsreader'] text-lg text-[#1F3D2B]">IP-SAKTI</span>
              <span className="text-xs text-[#7C9473]">सहायक</span>
            </div>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
