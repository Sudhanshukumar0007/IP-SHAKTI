import { useEffect, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  Link,
  useNavigate,
} from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  ExternalLink,
  FileText,
  Globe2,
  Leaf,
  LogIn,
  Search,
  ShieldCheck,
  Sparkles,
  Scale,
  UserPlus,
} from "lucide-react";

import { LoginPage, SignupPage } from "./AuthPage";
import Research from "./research";
import EvalList from "./pages/EvalList";
import EvalDashboard from "./pages/EvalDashboard";

const ACCOUNT_KEY = "ipshakti_account";
const VERIFIED_KEY = "ipshakti_verified";

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.7,
      ease: [0.22, 1, 0.36, 1],
    },
  },
};

function getAccount() {
  try {
    return JSON.parse(localStorage.getItem(ACCOUNT_KEY) || "null");
  } catch {
    return null;
  }
}

export default function App() {
  return (
    <Routes>
      {/* PUBLIC WEBSITE */}
      <Route path="/" element={<LandingPage />} />

      {/* AUTH */}
      <Route
        path="/login"
        element={
          <LoginPage
            onSubmit={(data) => {
              const account = getAccount();

              if (!account || account.email !== data.email) {
                throw new Error(
                  "No account found for this email. Create an account first."
                );
              }

              if (localStorage.getItem(VERIFIED_KEY) !== "true") {
                window.location.href = "/verify";
                return;
              }

              // IMPORTANT:
              // After login, return to the WEBSITE.
              window.location.href = "/";
            }}
            onSwitchMode={(mode) => {
              window.location.href = `/${mode}`;
            }}
          />
        }
      />

      <Route
        path="/signup"
        element={
          <SignupPage
            onSubmit={(data) => {
              const account = {
                name: data.name,
                email: data.email,
                org: data.org || "",
                language: data.language || "English",
                createdAt: new Date().toISOString(),
                verified: false,
              };

              localStorage.setItem(ACCOUNT_KEY, JSON.stringify(account));

              /*
               * FRONTEND DEMO:
               * Real backend should send an email verification token.
               */
              localStorage.setItem(VERIFIED_KEY, "false");

              window.location.href = "/verify";
            }}
            onSwitchMode={(mode) => {
              window.location.href = `/${mode}`;
            }}
          />
        }
      />

      {/* VERIFICATION */}
      <Route path="/verify" element={<VerifyPage />} />

      {/* RESEARCH */}
      <Route
        path="/research"
        element={<Research />}
      />

      {/* EVAL DASHBOARDS */}
      <Route path="/eval" element={<EvalList />} />
      <Route path="/eval/:sessionId" element={<EvalDashboard />} />

      {/* Website Routes */}
      <Route path="/about" element={<AboutPage />} />
      <Route path="/faqs" element={<FAQPage />} />
      <Route path="/terms" element={<TermsPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route path="/cookies" element={<CookiePage />} />
      <Route path="/contact" element={<ContactPage />} />
      <Route path="/help" element={<HelpPage />} />

      {/* FALLBACK */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

/* =========================================================
   LANDING PAGE
   ========================================================= */

function LandingPage() {
  const account = getAccount();
  const navigate = useNavigate();

  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    document.title = "IP-SAKTI — Cited IP & Regulatory Research";

    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);

    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden bg-[#F2EBDD] text-[#26312A]">

      {/* =====================================================
         NAVBAR
      ===================================================== */}

      <motion.header
        initial={{ y: -30, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${
          scrolled
            ? "border-b bg-[#F2EBDD]/90 backdrop-blur-xl"
            : "bg-transparent"
        }`}
        style={{
          borderColor: scrolled ? "#D8D0BA" : "transparent",
        }}
      >
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6 lg:px-10">

          <Link to="/" className="flex items-center gap-3">
            <div className="relative flex h-10 w-10 items-center justify-center">
              <div className="absolute inset-0 rounded-full border border-[#C97A2B]/50" />
              <div className="absolute inset-[4px] rounded-full bg-[#1F3D2B]" />
              <Leaf className="relative text-[#F7F3E9]" size={17} />
            </div>

            <div>
              <div className="font-['Newsreader'] text-xl tracking-tight">
                IP-SAKTI
              </div>
              <div className="text-[8px] tracking-[.18em] text-[#7C9473]">
                सहायक · CITED RESEARCH
              </div>
            </div>
          </Link>

          {/* CENTER NAV */}
          <nav className="hidden items-center gap-8 text-sm md:flex">
            <a href="#what" className="text-[#5B5545] hover:text-[#1F3D2B]">
              What is IP-SAKTI
            </a>
            <a href="#how" className="text-[#5B5545] hover:text-[#1F3D2B]">
              How it works
            </a>
            <a href="#sources" className="text-[#5B5545] hover:text-[#1F3D2B]">
              Sources
            </a>
            <a href="#uses" className="text-[#5B5545] hover:text-[#1F3D2B]">
              Use cases
            </a>
          </nav>

          {/* AUTH */}
          <div className="flex items-center gap-3">
            {account ? (
              <>
                <button
                  onClick={() => navigate("/research")}
                  className="hidden items-center gap-2 rounded-md bg-[#1F3D2B] px-4 py-2.5 text-xs font-semibold text-[#F7F3E9] sm:flex"
                >
                  <Search size={14} />
                  Research assistant
                </button>

                <button
                  onClick={() => {
                    const menu = document.getElementById("account-menu");
                    menu?.classList.toggle("hidden");
                  }}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-[#1F3D2B] text-xs font-bold text-[#F7F3E9]"
                >
                  {(account.name || "IP")
                    .split(" ")
                    .map((x) => x[0])
                    .join("")
                    .slice(0, 2)
                    .toUpperCase()}
                </button>
              </>
            ) : (
              <>
                <Link
                  to="/login"
                  className="hidden items-center gap-2 px-4 py-2 text-sm text-[#5B5545] hover:text-[#1F3D2B] sm:flex"
                >
                  <LogIn size={15} />
                  Sign in
                </Link>

                <Link
                  to="/signup"
                  className="flex items-center gap-2 rounded-md bg-[#C97A2B] px-5 py-2.5 text-sm font-semibold text-[#F7F3E9]"
                >
                  <UserPlus size={15} />
                  Get started
                </Link>
              </>
            )}
          </div>
        </div>
      </motion.header>

      {/* =====================================================
         HERO
      ===================================================== */}

      <section className="relative overflow-hidden bg-[#1F3D2B] text-[#F7F3E9]">

        <div
          className="pointer-events-none absolute inset-0 opacity-[.035]"
          style={{
            backgroundImage:
              "radial-gradient(#F7F3E9 1px, transparent 1px)",
            backgroundSize: "24px 24px",
          }}
        />

        <div className="relative z-10 mx-auto grid min-h-[800px] max-w-7xl items-center gap-14 px-6 pb-20 pt-36 lg:grid-cols-[.95fr_1.05fr] lg:px-10">

          {/* COPY */}
          <motion.div
            variants={fadeUp}
            initial="hidden"
            animate="visible"
          >
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[#9AB08C]/25 px-3 py-1.5 text-xs text-[#C7D3BE]">
              <Sparkles size={12} />
              AI-assisted IP & regulatory research
            </div>

            <h1 className="max-w-3xl font-['Newsreader'] text-6xl leading-[.88] tracking-[-.045em] md:text-7xl lg:text-8xl">
              Intellectual
              <br />
              property,
              <br />
              <i className="text-[#D7C18F]">with evidence.</i>
            </h1>

            <p className="mt-8 max-w-xl text-lg leading-8 text-[#C7D3BE]">
              IP-SAKTI brings patents, laws, treaties and regulatory material
              together into one research assistant built around traceable
              sources.
            </p>

            <div className="mt-9 flex flex-wrap gap-3">
              <motion.button
                type="button"
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => navigate("/research")}
                className="relative z-20 inline-flex cursor-pointer items-center gap-2 rounded-md bg-[#C97A2B] px-6 py-3.5 text-sm font-semibold text-[#F7F3E9]"
              >
                Start researching
                <ArrowUpRight size={16} />
              </motion.button>

              <a
                href="#what"
                className="inline-flex items-center gap-2 rounded-md border border-[#9AB08C]/30 px-6 py-3.5 text-sm"
              >
                Explore IP-SAKTI
                <ArrowRight size={15} />
              </a>
            </div>

            <div className="mt-12 grid grid-cols-3 gap-5 max-w-xl">
              <HeroStat number="01" text="Ask naturally" />
              <HeroStat number="02" text="Find evidence" />
              <HeroStat number="03" text="Verify sources" />
            </div>
          </motion.div>

          {/* VISUAL */}
          <motion.div
            initial={{ opacity: 0, scale: .94 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: .9, delay: .2 }}
            className="relative min-h-[520px]"
          >
            {/* Orbit */}
            <div className="pointer-events-none absolute left-1/2 top-1/2 h-[440px] w-[440px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#9AB08C]/10" />

            <div className="pointer-events-none absolute left-1/2 top-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#C97A2B]/15" />

            {/* Flower */}
            <svg
              viewBox="0 0 220 300"
              className="pointer-events-none absolute right-5 top-2 h-64 w-48"
              fill="none"
            >
              <path
                d="M105 290 C103 230 114 168 104 110 C98 78 106 42 124 12"
                stroke="#9AB08C"
                strokeWidth="2"
              />

              <path
                d="M104 156 C80 143 58 147 37 126 C56 120 79 125 95 141"
                stroke="#C97A2B"
                strokeWidth="2"
              />

              <path
                d="M106 108 C129 95 150 97 168 77 C150 71 130 76 115 93"
                stroke="#9AB08C"
                strokeWidth="2"
              />

              <path
                d="M105 215 C84 204 65 208 49 190"
                stroke="#9AB08C"
                strokeWidth="1.6"
              />

              {/* flower bloom */}
              <path
                d="M124 13 C114 2 114 -5 124 -14 C134 -5 135 3 124 13Z"
                fill="#C97A2B"
              />
              <path
                d="M124 13 C135 4 144 5 151 14 C143 23 134 23 124 13Z"
                fill="#D7C18F"
              />
              <path
                d="M124 13 C134 24 136 33 128 40 C119 34 119 25 124 13Z"
                fill="#A7BC99"
              />
              <path
                d="M124 13 C113 23 104 23 98 15 C105 8 114 8 124 13Z"
                fill="#C97A2B"
              />

              <circle cx="124" cy="13" r="4" fill="#F4E8CB" />
            </svg>

            {/* Research card */}
            <motion.div
              animate={{ y: [0, -7, 0] }}
              transition={{ duration: 5, repeat: Infinity }}
              className="absolute left-1/2 top-1/2 w-[330px] -translate-x-1/2 -translate-y-1/2"
            >
              <div className="rounded-[26px] border border-white/10 bg-[#F7F3E9] p-5 text-[#26312A] shadow-2xl">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="grid h-8 w-8 place-items-center rounded-lg bg-[#1F3D2B] text-[#F7F3E9]">
                      <Sparkles size={14} />
                    </div>
                    <div className="text-xs font-semibold">
                      IP-SHAKTI SAHAYAK
                    </div>
                  </div>
                  <span className="text-[9px] text-[#9E9679]">
                    RESEARCH
                  </span>
                </div>

                <div className="mt-5 rounded-xl border border-[#EAE3CE] bg-white p-4">
                  <div className="text-[9px] tracking-[.1em] text-[#9E9679]">
                    QUESTION
                  </div>

                  <div className="mt-2 text-sm font-medium leading-6">
                    Is this Ayurvedic formulation potentially patentable?
                  </div>
                </div>

                <div className="mt-3 rounded-xl bg-[#E8F0E9] p-4">
                  <div className="flex items-center gap-2 text-xs font-semibold text-[#2F6B3E]">
                    <CheckCircle2 size={14} />
                    Relevant evidence found
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {["Patents", "Section 3", "Prior art", "TKDL"].map(
                      (x) => (
                        <span
                          key={x}
                          className="rounded-md bg-white px-2 py-1 text-[9px] text-[#6E6852]"
                        >
                          {x}
                        </span>
                      )
                    )}
                  </div>
                </div>
              </div>
            </motion.div>

            {/* bookshelf */}
            <div className="absolute bottom-4 left-0 hidden xl:block">
              <div className="mb-2 text-[8px] tracking-[.15em] text-[#9AB08C]">
                KNOWLEDGE SHELF
              </div>

              <div className="flex h-32 items-end gap-1 border-b-4 border-[#65755F] px-4">
                {[
                  ["ACTS", "#C97A2B"],
                  ["RULES", "#8FA67E"],
                  ["GI", "#D7C18F"],
                  ["WIPO", "#6D836B"],
                  ["TKDL", "#B57443"],
                ].map(([label, color]) => (
                  <div
                    key={label}
                    className="flex h-24 w-8 items-center justify-center rounded-sm text-[7px] font-semibold text-[#1F3D2B]"
                    style={{ background: color }}
                  >
                    <span className="rotate-90">{label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* assistant */}
            <motion.div
              animate={{ y: [0, -5, 0] }}
              transition={{ duration: 4, repeat: Infinity }}
              className="absolute bottom-6 right-4 hidden md:block"
            >
              <div className="rounded-[26px] border border-[#61745F] bg-[#274934] p-4 shadow-xl">
                <div className="grid h-16 w-16 place-items-center rounded-[18px] bg-[#1F3D2B]">
                  <div className="flex gap-2">
                    <span className="h-2 w-2 rounded-full bg-[#D7C18F]" />
                    <span className="h-2 w-2 rounded-full bg-[#D7C18F]" />
                  </div>
                </div>

                <div className="mt-2 text-center text-[8px] tracking-[.15em] text-[#9AB08C]">
                  SAHAYAK
                </div>
              </div>
            </motion.div>
          </motion.div>
        </div>

        {/* source ribbon */}
        <div className="border-t border-white/10 bg-[#173323]">
          <div className="mx-auto flex max-w-7xl items-center gap-8 overflow-hidden px-6 py-5 lg:px-10">
            <span className="shrink-0 text-[9px] tracking-[.16em] text-white/30">
              RESEARCH ACROSS
            </span>

            <div className="flex min-w-max gap-10 text-xs text-white/55">
              <span>Patents</span>
              <span>Acts & Rules</span>
              <span>Treaties</span>
              <span>TKDL</span>
              <span>Biodiversity</span>
              <span>Geographical Indications</span>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================
         WHAT IS IP-SAKTI
      ===================================================== */}

      <section id="what" className="px-6 py-28 lg:px-10">
        <div className="mx-auto max-w-7xl">
          <motion.div
            variants={fadeUp}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            className="grid gap-12 lg:grid-cols-[.8fr_1.2fr]"
          >
            <div>
              <div className="text-[9px] tracking-[.18em] text-[#C97A2B]">
                WHAT IS IP-SAKTI?
              </div>

              <h2 className="mt-4 max-w-xl font-['Newsreader'] text-5xl leading-[.95] tracking-[-.04em] lg:text-6xl">
                A research assistant built around the evidence.
              </h2>
            </div>

            <div className="max-w-2xl space-y-6 text-[16px] leading-8 text-[#6E6852]">
              <p>
                Intellectual property research often starts with a simple
                question but ends in scattered Acts, databases, publications
                and international material.
              </p>

              <p>
                IP-SAKTI gives that question a single research surface —
                helping users discover relevant information and trace answers
                back to the source.
              </p>

              <p>
                It is designed particularly around Ayurveda, formulations,
                traditional knowledge and the wider Indian IP and regulatory
                landscape.
              </p>
            </div>
          </motion.div>
        </div>
      </section>

      {/* =====================================================
         HOW IT WORKS
      ===================================================== */}

      <section id="how" className="border-y border-[#DCD4C2] bg-[#E8E0CF] px-6 py-28 lg:px-10">
        <div className="mx-auto max-w-7xl">
          <div className="max-w-2xl">
            <div className="text-[9px] tracking-[.18em] text-[#C97A2B]">
              HOW IT WORKS
            </div>

            <h2 className="mt-4 font-['Newsreader'] text-5xl leading-none lg:text-6xl">
              From question to evidence.
            </h2>
          </div>

          <div className="mt-16 grid gap-4 md:grid-cols-3">
            <ProcessCard
              number="01"
              icon={<Search size={22} />}
              title="Ask"
              text="Describe your IP or regulatory question naturally."
            />

            <ProcessCard
              number="02"
              icon={<Globe2 size={22} />}
              title="Discover"
              text="Find relevant patents, legislation, treaties and publications."
            />

            <ProcessCard
              number="03"
              icon={<ShieldCheck size={22} />}
              title="Verify"
              text="Inspect the underlying sources before relying on the result."
            />
          </div>
        </div>
      </section>

      {/* =====================================================
         SOURCES
      ===================================================== */}

      <section id="sources" className="px-6 py-28 lg:px-10">
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-col justify-between gap-8 md:flex-row md:items-end">
            <div>
              <div className="text-[9px] tracking-[.18em] text-[#C97A2B]">
                SOURCE ECOSYSTEM
              </div>

              <h2 className="mt-4 font-['Newsreader'] text-5xl lg:text-6xl">
                The research trail matters.
              </h2>
            </div>

            <p className="max-w-md text-sm leading-6 text-[#6E6852]">
              IP-SAKTI is designed to keep research connected to the
              organisations, records and legal material behind it.
            </p>
          </div>

          <div className="mt-14 grid gap-4 md:grid-cols-3">
            <SourceCard
              name="Intellectual Property India"
              description="Indian intellectual property resources and public records."
              href="https://www.ipindia.gov.in/"
            />

            <SourceCard
              name="WIPO"
              description="International intellectual property resources and treaties."
              href="https://www.wipo.int/portal/en/"
            />

            <SourceCard
              name="Ministry of AYUSH"
              description="Official source for the wider AYUSH ecosystem."
              href="https://www.ayush.gov.in/"
            />
          </div>
        </div>
      </section>

      {/* =====================================================
         USE CASES
      ===================================================== */}

      <section id="uses" className="bg-[#1F3D2B] px-6 py-28 text-[#F7F3E9] lg:px-10">
        <div className="mx-auto max-w-7xl">
          <div className="text-[9px] tracking-[.18em] text-[#D7C18F]">
            WHO IT IS FOR
          </div>

          <h2 className="mt-4 max-w-3xl font-['Newsreader'] text-5xl leading-[.95] lg:text-6xl">
            Built for people who need to understand what already exists.
          </h2>

          <div className="mt-16 grid gap-px overflow-hidden rounded-3xl border border-white/10 bg-white/10 md:grid-cols-2">
            {[
              [
                "Researchers",
                "Explore prior art, legislation, publications and related material.",
                <FileText size={22} />,
              ],
              [
                "Innovators",
                "Understand the IP landscape before investing in an idea.",
                <Sparkles size={22} />,
              ],
              [
                "Legal professionals",
                "Accelerate research and connect provisions with source material.",
                <Scale size={22} />,
              ],
              [
                "Students",
                "Learn complex IP concepts through questions and evidence.",
                <BookIcon size={22} />,
              ],
            ].map(([title, text, icon]) => (
              <div
                key={title}
                className="bg-[#1F3D2B] p-8 transition hover:bg-[#254733]"
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-full border border-white/15">
                  {icon}
                </div>

                <h3 className="mt-9 font-['Newsreader'] text-3xl">
                  {title}
                </h3>

                <p className="mt-3 max-w-md text-sm leading-6 text-white/55">
                  {text}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* =====================================================
         FINAL CTA
      ===================================================== */}

      <section className="bg-[#C97A2B] px-6 py-24 lg:px-10">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-10 lg:flex-row lg:items-end">
          <div>
            <div className="text-[9px] font-semibold tracking-[.18em] text-[#F7F3E9]/60">
              BEGIN WITH A QUESTION
            </div>

            <h2 className="mt-4 max-w-3xl font-['Newsreader'] text-6xl leading-[.9] text-[#1F3D2B] lg:text-7xl">
              Research IP with a clearer trail.
            </h2>
          </div>

          <Link
            to={account ? "/research" : "/signup"}
            className="inline-flex shrink-0 items-center gap-2 rounded-md bg-[#1F3D2B] px-6 py-4 text-sm font-semibold text-[#F7F3E9]"
          >
            {account ? "Open research assistant" : "Create your account"}
            <ArrowUpRight size={17} />
          </Link>
        </div>
      </section>

      {/* =====================================================
         FOOTER
      ===================================================== */}

      <footer className="bg-[#172C20] px-6 py-12 text-[#F7F3E9] lg:px-10">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-12 lg:grid-cols-[1fr_2fr]">

            <div>
              <div className="font-['Newsreader'] text-2xl">
                IP-SAKTI
              </div>

              <p className="mt-2 max-w-sm text-sm leading-6 text-white/40">
                Cited intellectual property and regulatory research for
                Ayurveda and beyond.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-8 text-xs sm:grid-cols-4">

              <FooterColumn
                title="Product"
                links={[
                  ["Research", "/research"],
                  ["Sign in", "/login"],
                  ["Create account", "/signup"],
                  ["Help", "/help"],
                ]}
              />

              <FooterColumn
                title="Information"
                links={[
                  ["About", "/about"],
                  ["FAQs", "/faqs"],
                  ["Contact", "/contact"],
                ]}
              />

              <FooterColumn
                title="Legal"
                links={[
                  ["Privacy", "/privacy"],
                  ["Terms", "/terms"],
                  ["Cookies", "/cookies"],
                ]}
              />

              <FooterColumn
                title="Sources"
                links={[
                  ["IP India", "https://www.ipindia.gov.in/"],
                  ["WIPO", "https://www.wipo.int/portal/en/"],
                  ["AYUSH", "https://www.ayush.gov.in/"],
                ]}
              />

            </div>
          </div>

          <div className="mt-12 border-t border-white/10 pt-6 text-[10px] leading-5 text-white/30">
            IP-SAKTI provides research and informational assistance and does
            not constitute legal advice. Verify the applicable law and
            official source before relying on any result.
          </div>
        </div>
      </footer>
    </div>
  );
}

/* =========================================================
   VERIFY
========================================================= */

function VerifyPage() {
  const navigate = useNavigate();
  const account = getAccount();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");

  if (!account) return <Navigate to="/signup" replace />;

  const verify = (e) => {
    e.preventDefault();

    if (code !== "123456") {
      setError("For this frontend demo, use 123456.");
      return;
    }

    localStorage.setItem(
      ACCOUNT_KEY,
      JSON.stringify({ ...account, verified: true })
    );

    localStorage.setItem(VERIFIED_KEY, "true");

    /*
     * IMPORTANT:
     * Verification ends at the WEBSITE.
     * Research is a separate destination.
     */
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-[#EDE6D6] px-6 py-12">
      <div className="mx-auto max-w-4xl">

        <Link
          to="/"
          className="font-['Newsreader'] text-2xl text-[#1F3D2B]"
        >
          IP-SAKTI
        </Link>

        <div className="mx-auto mt-24 max-w-xl">
          <div className="text-[9px] tracking-[.18em] text-[#C97A2B]">
            EMAIL VERIFICATION
          </div>

          <h1 className="mt-4 font-['Newsreader'] text-5xl">
            Verify your email.
          </h1>

          <p className="mt-4 text-sm leading-6 text-[#6E6852]">
            Confirm your account before entering your research website.
          </p>

          <form
            onSubmit={verify}
            className="mt-8 rounded-2xl border bg-white p-7"
            style={{ borderColor: "#EAE3CE" }}
          >
            <label className="text-xs text-[#5B5545]">
              Verification code
            </label>

            <input
              value={code}
              onChange={(e) =>
                setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
              }
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="123456"
              className="mt-2 w-full border-b bg-transparent py-4 text-2xl tracking-[.35em] outline-none"
              style={{ borderColor: "#D8D0BA" }}
            />

            {error && (
              <p className="mt-2 text-xs text-[#7A2E2E]">{error}</p>
            )}

            <button className="mt-6 flex w-full items-center justify-center gap-2 rounded-md bg-[#C97A2B] py-3 text-sm font-medium text-[#F7F3E9]">
              Verify and continue
              <ArrowRight size={15} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

/* =========================================================
   SMALL COMPONENTS
========================================================= */

function HeroStat({ number, text }) {
  return (
    <div className="border-l border-white/15 pl-4">
      <div className="text-[10px] text-[#D7C18F]">{number}</div>
      <div className="mt-1 text-xs text-white/55">{text}</div>
    </div>
  );
}

function ProcessCard({ number, icon, title, text }) {
  return (
    <motion.div
      whileHover={{ y: -4 }}
      className="rounded-2xl border bg-[#F7F3E9] p-7"
      style={{ borderColor: "#D8D0BA" }}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-[#9E9679]">{number}</span>

        <div className="grid h-10 w-10 place-items-center rounded-full bg-[#1F3D2B] text-[#F7F3E9]">
          {icon}
        </div>
      </div>

      <h3 className="mt-10 font-['Newsreader'] text-3xl">
        {title}
      </h3>

      <p className="mt-3 text-sm leading-6 text-[#6E6852]">
        {text}
      </p>
    </motion.div>
  );
}

function SourceCard({ name, description, href }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="group rounded-2xl border bg-white p-7 transition hover:-translate-y-1 hover:shadow-lg"
      style={{ borderColor: "#EAE3CE" }}
    >
      <div className="flex items-center justify-between">
        <div className="grid h-11 w-11 place-items-center rounded-full bg-[#EDE6D6] text-[#1F3D2B]">
          <Globe2 size={18} />
        </div>

        <ExternalLink
          size={16}
          className="text-[#9E9679] transition group-hover:text-[#1F3D2B]"
        />
      </div>

      <h3 className="mt-12 text-xl font-semibold">{name}</h3>

      <p className="mt-2 text-sm leading-6 text-[#6E6852]">
        {description}
      </p>

      <div className="mt-6 flex items-center gap-1 text-xs font-semibold text-[#1F3D2B]">
        Visit official source
        <ArrowRight size={13} />
      </div>
    </a>
  );
}

function FooterColumn({ title, links }) {
  return (
    <div>
      <h3 className="mb-4 text-[9px] tracking-[.16em] text-white/30">
        {title}
      </h3>

      <div className="space-y-3">
        {links.map(([label, href]) =>
          href.startsWith("http") ? (
            <a
              key={label}
              href={href}
              target="_blank"
              rel="noreferrer"
              className="block text-white/55 hover:text-white"
            >
              {label}
            </a>
          ) : (
            <Link
              key={label}
              to={href}
              className="block text-white/55 hover:text-white"
            >
              {label}
            </Link>
          )
        )}
      </div>
    </div>
  );
}

function BookIcon(props) {
  return <FileText {...props} />;
}

function LegalSection({ title, children }) {
  return (
    <section>
      <h2 className="font-['Newsreader'] text-2xl text-[#1F3D2B] mb-4">
        {title}
      </h2>
      <div className="text-sm leading-7 text-[#6E6852] space-y-4">
        {children}
      </div>
    </section>
  );
}

function AboutPage() {
  useEffect(() => {
    document.title = "About IP-SAKTI · Cited IP Research";
  }, []);

  return (
    <WebsiteShell>
      <section className="bg-[#1F3D2B] px-6 py-28 text-[#F7F3E9] lg:px-10">
        <div className="mx-auto max-w-6xl">
          <div className="max-w-3xl">
            <div className="text-[9px] tracking-[.18em] text-[#D7C18F]">
              ABOUT IP-SAKTI
            </div>

            <h1 className="mt-5 font-['Newsreader'] text-6xl leading-[.9] tracking-[-.04em] md:text-7xl">
              Making IP research
              <br />
              easier to
              <i className="text-[#D7C18F]"> follow.</i>
            </h1>

            <p className="mt-8 max-w-2xl text-lg leading-8 text-[#C7D3BE]">
              IP-SAKTI is a research assistant designed to help users explore
              intellectual property and regulatory questions through
              connected, source-backed information.
            </p>
          </div>
        </div>
      </section>

      <section className="px-6 py-24 lg:px-10">
        <div className="mx-auto grid max-w-6xl gap-16 lg:grid-cols-2">
          <div>
            <div className="text-[9px] tracking-[.18em] text-[#C97A2B]">
              THE PROBLEM
            </div>
            <h2 className="mt-4 font-['Newsreader'] text-5xl leading-[.95]">
              An IP question rarely lives in one document.
            </h2>
          </div>

          <div className="space-y-6 text-[15px] leading-8 text-[#6E6852]">
            <p>
              A single research question can involve legislation, patent
              records, international treaties, technical publications,
              traditional knowledge and regulatory material.
            </p>
            <p>
              Finding those connections manually takes time and often requires
              moving between different sources and terminology.
            </p>
            <p>
              IP-SAKTI is designed to make that research journey easier to
              navigate while keeping the underlying evidence visible.
            </p>
          </div>
        </div>
      </section>

      <section className="bg-[#E8E0CF] px-6 py-24 lg:px-10">
        <div className="mx-auto max-w-6xl">
          <div className="text-[9px] tracking-[.18em] text-[#C97A2B]">
            WHAT WE FOCUS ON
          </div>

          <div className="mt-12 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {[
              ["Patents", "Patentability, prior art and patent research."],
              ["Traditional knowledge", "TKDL and related knowledge systems."],
              ["Regulation", "Regulatory classification and applicable rules."],
              ["International IP", "Treaties and international IP frameworks."],
            ].map(([title, text]) => (
              <div
                key={title}
                className="rounded-2xl border bg-[#F7F3E9] p-7"
                style={{ borderColor: "#D8D0BA" }}
              >
                <h3 className="font-['Newsreader'] text-3xl">
                  {title}
                </h3>
                <p className="mt-3 text-sm leading-6 text-[#6E6852]">
                  {text}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 py-24 lg:px-10">
        <div className="mx-auto max-w-6xl rounded-3xl bg-[#1F3D2B] p-10 text-[#F7F3E9] md:p-14">
          <div className="max-w-3xl">
            <div className="text-[9px] tracking-[.18em] text-[#D7C18F]">
              OUR PRINCIPLE
            </div>
            <h2 className="mt-4 font-['Newsreader'] text-5xl leading-none md:text-6xl">
              Every answer should leave a trail.
            </h2>
            <p className="mt-6 text-sm leading-7 text-white/60">
              IP-SAKTI is built around a simple idea: research becomes more
              useful when people can inspect the evidence behind it.
            </p>
          </div>
        </div>
      </section>
    </WebsiteShell>
  );
}

function FAQPage() {
  useEffect(() => {
    document.title = "FAQs · IP-SAKTI";
  }, []);

  const faqs = [
    {
      q: "What is IP-SAKTI?",
      a: "IP-SAKTI is an IP and regulatory research assistant designed to help users explore patents, laws, rules, treaties, traditional knowledge and related material through natural-language questions."
    },
    {
      q: "Does IP-SAKTI provide legal advice?",
      a: "No. IP-SAKTI provides research and informational assistance. Users should verify the applicable law and underlying official sources and consult a qualified professional where appropriate."
    },
    {
      q: "What can I research?",
      a: "Examples include patentability questions, prior art, TKDL-related research, biodiversity and ABS questions, geographical indications, formulation classification and international IP frameworks."
    },
    {
      q: "Can I ask questions in Indian languages?",
      a: "The interface is designed for multilingual research. Available languages depend on the current research corpus and backend implementation."
    },
    {
      q: "How are sources shown?",
      a: "Research results can include source references so that users can inspect the underlying material rather than relying only on a generated answer."
    },
    {
      q: "Can I verify the original document?",
      a: "Where a document identifier and PDF route are available, the research workspace can provide an in-product verification view."
    },
    {
      q: "Does IP-SAKTI store my questions?",
      a: "Production storage depends on the backend configuration. The data-handling policy should clearly explain what is collected, why it is processed and how long it is retained."
    },
    {
      q: "How is personal data handled?",
      a: "The production system is intended to use a data-handling approach aligned with the Digital Personal Data Protection Act, 2023 and applicable rules, subject to the final backend implementation."
    },
  ];

  return (
    <WebsiteShell>
      <section className="bg-[#1F3D2B] px-6 py-28 text-[#F7F3E9] lg:px-10">
        <div className="mx-auto max-w-6xl">
          <div className="text-[9px] tracking-[.18em] text-[#D7C18F]">
            QUESTIONS & ANSWERS
          </div>

          <h1 className="mt-5 max-w-3xl font-['Newsreader'] text-6xl leading-[.9] md:text-7xl">
            Frequently
            <br />
            asked
            <i className="text-[#D7C18F]"> questions.</i>
          </h1>
        </div>
      </section>

      <section className="px-6 py-20 lg:px-10">
        <div className="mx-auto max-w-4xl divide-y divide-[#D8D0BA]">
          {faqs.map((item, index) => (
            <details
              key={item.q}
              className="group py-7"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-8 text-left">
                <span className="flex items-start gap-5">
                  <span className="text-[10px] text-[#C97A2B]">
                    0{index + 1}
                  </span>
                  <span className="font-['Newsreader'] text-2xl md:text-3xl">
                    {item.q}
                  </span>
                </span>
                <span className="text-[#9E9679] transition group-open:rotate-45">
                  +
                </span>
              </summary>
              <p className="ml-9 mt-5 max-w-2xl text-sm leading-7 text-[#6E6852]">
                {item.a}
              </p>
            </details>
          ))}
        </div>
      </section>
    </WebsiteShell>
  );
}

function TermsPage() {
  useEffect(() => {
    document.title = "Terms & Conditions · IP-SAKTI";
  }, []);

  return (
    <WebsiteShell>
      <section className="bg-[#1F3D2B] px-6 py-24 text-[#F7F3E9] lg:px-10">
        <div className="mx-auto max-w-5xl">
          <div className="text-[9px] tracking-[.18em] text-[#D7C18F]">
            LEGAL
          </div>
          <h1 className="mt-5 font-['Newsreader'] text-6xl">
            Terms & Conditions
          </h1>
          <p className="mt-4 text-xs text-white/45">
            Last updated: 11 September 2026
          </p>
        </div>
      </section>

      <section className="px-6 py-20 lg:px-10">
        <article className="mx-auto max-w-4xl space-y-12">
          <LegalSection title="1. About IP-SAKTI">
            <p>
              IP-SAKTI is an intellectual property and regulatory research
              platform intended to help users discover, organise and review
              information relating to intellectual property, regulation,
              traditional knowledge and related subjects.
            </p>
          </LegalSection>

          <LegalSection title="2. Research information, not legal advice">
            <p>
              IP-SAKTI does not provide legal representation or professional
              legal advice. Research results are provided for informational
              and research purposes. Users should verify the current law and
              authoritative source before relying on a result.
            </p>
          </LegalSection>

          <LegalSection title="3. Source verification">
            <p>
              The platform may surface information from legislation,
              publications, patent records, treaties and other sources.
              Availability, interpretation and currency of those sources can
              change. Users remain responsible for checking the applicable
              primary source.
            </p>
          </LegalSection>

          <LegalSection title="4. Acceptable use">
            <p>
              Users must not misuse the service, attempt to bypass access
              controls, interfere with platform security, upload unlawful
              material, or use the service in a way that violates applicable
              law.
            </p>
          </LegalSection>

          <LegalSection title="5. Accounts">
            <p>
              Users are responsible for providing accurate account information
              and for protecting their authentication credentials. Production
              authentication, session management and account-security controls
              are implemented server-side.
            </p>
          </LegalSection>

          <LegalSection title="6. Availability and changes">
            <p>
              Features, sources, supported languages and research capabilities
              may change as the platform evolves.
            </p>
          </LegalSection>

          <LegalSection title="7. Intellectual property">
            <p>
              IP-SAKTI branding, interface design and original platform
              material remain subject to applicable intellectual property
              rights. Third-party sources remain subject to their respective
              owners' rights and terms.
            </p>
          </LegalSection>

          <LegalSection title="8. Limitation">
            <p>
              No research result should be treated as a substitute for
              professional legal, regulatory or technical advice.
            </p>
          </LegalSection>

          <LegalSection title="9. Governing law">
            <p>
              The final production version of these terms should specify the
              applicable governing law, jurisdiction and dispute-resolution
              mechanism after legal review.
            </p>
          </LegalSection>

          <div className="mt-12 rounded-2xl border bg-[#F4E8CB]/40 p-6" style={{borderColor:"#D8D0BA"}}>
            <div className="text-sm font-semibold text-[#1F3D2B]">
              Important
            </div>
            <p className="mt-2 text-sm leading-6 text-[#6E6852]">
              This page is a product/frontend draft and should receive legal
              review before production use.
            </p>
          </div>
        </article>
      </section>
    </WebsiteShell>
  );
}

function PrivacyPage() {
  useEffect(() => {
    document.title = "Privacy & Data Handling · IP-SAKTI";
  }, []);

  return (
    <WebsiteShell>
      <section className="bg-[#1F3D2B] px-6 py-24 text-[#F7F3E9] lg:px-10">
        <div className="mx-auto max-w-5xl">
          <div className="text-[9px] tracking-[.18em] text-[#D7C18F]">
            PRIVACY
          </div>
          <h1 className="mt-5 font-['Newsreader'] text-6xl">
            Privacy & Data Handling
          </h1>
          <p className="mt-4 text-xs text-white/45">
            Last updated: 11 September 2026
          </p>
        </div>
      </section>

      <section className="px-6 py-20 lg:px-10">
        <article className="mx-auto max-w-4xl space-y-12">
          <DataSection
            title="Our approach"
            text="IP-SAKTI is designed around a data-minimisation and purpose-based approach to personal data. The final production implementation should collect only the information necessary for account creation, authentication, support, security and requested platform functionality."
          />

          <DataSection
            title="Digital Personal Data Protection"
            text="Our production data-handling architecture is intended to align with the Digital Personal Data Protection Act, 2023 and applicable Digital Personal Data Protection Rules. The Act establishes a framework for processing digital personal data while recognising individuals' rights and lawful processing needs."
          />

          <DataSection
            title="Notice and purpose"
            text="Users should receive clear information about the categories of personal data collected and the purposes for which it is processed. Consent-based processing should use clear, specific and informed consent, and users should have a practical way to withdraw consent where consent is the processing basis."
          />

          <DataSection
            title="Security safeguards"
            text="The production backend should use appropriate technical and organisational safeguards, including access controls, encryption or equivalent protections, monitoring, logging, backups and measures to detect and respond to personal-data breaches."
          />

          <DataSection
            title="Your controls"
            text="Depending on the applicable processing basis and production implementation, users should have appropriate mechanisms for exercising rights provided by applicable data-protection law, including correction, erasure, withdrawal of consent where applicable and grievance handling."
          />

          <DataSection
            title="Data retention"
            text="Personal data should not be retained indefinitely. Retention periods should be defined by purpose, legal requirements and operational necessity, with deletion or anonymisation mechanisms implemented where applicable."
          />

          <DataSection
            title="Data processors and service providers"
            text="Where third-party service providers process personal data on behalf of IP-SAKTI, the production implementation should establish appropriate contractual, technical and organisational controls for the handling of that data."
          />

          <DataSection
            title="Personal-data breaches"
            text="The production incident-response process should provide for timely investigation, remediation and notification in accordance with applicable legal requirements."
          />

          <div className="rounded-2xl border bg-[#E8F0E9] p-6" style={{borderColor:"#2F6B3E35"}}>
            <div className="flex gap-3">
              <ShieldCheck className="mt-0.5 shrink-0 text-[#2F6B3E]" size={19}/>
              <div>
                <h3 className="font-semibold text-[#1F3D2B]">
                  DPDP alignment statement
                </h3>
                <p className="mt-2 text-sm leading-6 text-[#536052]">
                  IP-SAKTI's product design is intended to support privacy,
                  transparency, consent, security and user-control principles
                  reflected in India's Digital Personal Data Protection
                  framework. Final legal compliance depends on the production
                  backend, operational controls, contracts, notices and
                  applicable implementation requirements.
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border bg-[#F4E8CB]/35 p-6" style={{borderColor:"#D8D0BA"}}>
            <p className="text-xs leading-6 text-[#6E6852]">
              This page is a frontend/product draft and is not itself a legal
              determination of compliance. It should be reviewed and completed
              by the organisation responsible for the production service.
            </p>
          </div>
        </article>
      </section>
    </WebsiteShell>
  );
}

function DataSection({ title, text }) {
  return (
    <section>
      <h2 className="font-['Newsreader'] text-3xl text-[#1F3D2B]">
        {title}
      </h2>
      <p className="mt-3 text-sm leading-7 text-[#6E6852]">
        {text}
      </p>
    </section>
  );
}

function CookiePage() {
  return (
    <WebsiteShell>
      <SimpleLegalHero title="Cookie Policy / Cookie Settings" />
      <section className="px-6 py-20 lg:px-10">
        <div className="mx-auto max-w-4xl space-y-10 text-sm leading-7 text-[#6E6852]">
          <DataSection
            title="What we use"
            text="The prototype uses local browser storage for demonstration account state and preferences. Production analytics, consent tools and other tracking technologies should be disclosed here before deployment."
          />
          <DataSection
            title="Your choice"
            text="Users should be given meaningful controls over non-essential cookies or similar technologies where consent is required."
          />
          <DataSection
            title="Cookie settings"
            text="The production application should provide a persistent mechanism to review or change applicable consent choices."
          />
        </div>
      </section>
    </WebsiteShell>
  );
}

function SimpleLegalHero({ title }) {
  return (
    <section className="bg-[#1F3D2B] px-6 py-24 text-[#F7F3E9] lg:px-10">
      <div className="mx-auto max-w-5xl">
        <div className="text-[9px] tracking-[.18em] text-[#D7C18F]">
          LEGAL
        </div>
        <h1 className="mt-5 font-['Newsreader'] text-6xl">
          {title}
        </h1>
        <p className="mt-4 text-xs text-white/45">
          Last updated: 11 September 2026
        </p>
      </div>
    </section>
  );
}

function ContactPage() {
  return (
    <WebsiteShell>
      <SimpleLegalHero title="Contact & Support" />
      <section className="px-6 py-20 lg:px-10">
        <div className="mx-auto max-w-4xl text-[#6E6852]">
          <p>This page is a frontend shell. Replace this content with your approved contact details.</p>
        </div>
      </section>
    </WebsiteShell>
  );
}

function HelpPage() {
  return (
    <WebsiteShell>
      <SimpleLegalHero title="Help & Documentation" />
      <section className="px-6 py-20 lg:px-10">
        <div className="mx-auto max-w-4xl text-[#6E6852]">
          <p>This page is a frontend shell. Replace this content with your approved help documentation.</p>
        </div>
      </section>
    </WebsiteShell>
  );
}

function WebsiteShell({ children }) {
  return (
    <div className="min-h-screen bg-[#F2EBDD] text-[#26312A]">
      <header className="border-b border-[#D8D0BA] bg-[#F2EBDD]/95 backdrop-blur-md">
        <div className="mx-auto flex h-20 max-w-6xl items-center justify-between px-6 lg:px-10">
          <Link
            to="/"
            className="font-['Newsreader'] text-2xl text-[#1F3D2B]"
          >
            IP-SAKTI
          </Link>
          <nav className="hidden items-center gap-7 text-sm md:flex">
            <Link to="/about" className="text-[#5B5545] hover:text-[#1F3D2B]">
              About
            </Link>
            <Link to="/faqs" className="text-[#5B5545] hover:text-[#1F3D2B]">
              FAQs
            </Link>
            <Link to="/login" className="text-[#5B5545] hover:text-[#1F3D2B]">
              Sign in
            </Link>
            <Link
              to="/signup"
              className="rounded-md bg-[#C97A2B] px-5 py-2.5 text-xs font-semibold text-[#F7F3E9]"
            >
              Get started
            </Link>
          </nav>
          <Link
            to="/signup"
            className="rounded-md bg-[#C97A2B] px-4 py-2.5 text-xs font-semibold text-[#F7F3E9] md:hidden"
          >
            Get started
          </Link>
        </div>
      </header>

      {children}

      <footer className="bg-[#172C20] px-6 py-12 text-[#F7F3E9] lg:px-10">
        <div className="mx-auto max-w-6xl">
          <div className="grid gap-10 md:grid-cols-4">
            <div>
              <div className="font-['Newsreader'] text-2xl">
                IP-SAKTI
              </div>
              <p className="mt-3 text-xs leading-5 text-white/40">
                Cited IP and regulatory research.
              </p>
            </div>
            <FooterColumn
              title="Website"
              links={[
                ["About", "/about"],
                ["FAQs", "/faqs"],
                ["Contact", "/contact"],
                ["Help", "/help"],
              ]}
            />
            <FooterColumn
              title="Legal"
              links={[
                ["Terms & Conditions", "/terms"],
                ["Privacy & Data Handling", "/privacy"],
                ["Cookie Policy", "/cookies"],
              ]}
            />
            <FooterColumn
              title="Research"
              links={[
                ["Sign in", "/login"],
                ["Create account", "/signup"],
                ["Research assistant", "/research"],
              ]}
            />
          </div>
          <div className="mt-10 border-t border-white/10 pt-6 text-[10px] leading-5 text-white/30">
            Information, not legal advice. Verify applicable law and official
            sources before relying on research results.
          </div>
        </div>
      </footer>
    </div>
  );
}

function NotFound() {
  return (
    <div className="grid min-h-screen place-items-center bg-[#F2EBDD] px-6">
      <div className="text-center">
        <div className="font-['Newsreader'] text-6xl text-[#1F3D2B]">
          404
        </div>

        <h1 className="mt-4 font-['Newsreader'] text-4xl">
          This page doesn't exist.
        </h1>

        <Link
          to="/"
          className="mt-7 inline-flex rounded-md bg-[#1F3D2B] px-5 py-3 text-sm text-[#F7F3E9]"
        >
          Return to IP-SAKTI
        </Link>
      </div>
    </div>
  );
}
