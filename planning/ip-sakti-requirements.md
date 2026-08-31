# IP-SAKTI Sahayak — requirements specification

Ayurveda IPR/regulatory RAG assistant. This document fixes MVP scope so build effort doesn't drift; anything under "extendable" is explicitly out of MVP scope and picked up only if time allows.

---

## Frontend

### MVP (must ship)
- Chat interface (text input, streamed responses)
- Language selector for output (source citations render in English/Hindi; other languages get a translate pass via Bhashini)
- "Tap to listen" audio playback on any assistant message (Bhashini TTS)
- Jurisdiction toggle: India ⟷ International, visibly separating the two answer-sets (not just a filter the user can't see is active)
- Formulation-classification flow rendered as an in-chat guided Q&A (not a free-text ask) before the main answer is generated
- Per-answer citation block: statute/rule/treaty name + article/section, always visible, never optional
- "Verify this act" action on every citation — opens the official source PDF/record for that specific act, rule, or treaty article
- Standing, persistent "information, not legal advice" disclaimer (visible at all times, not a one-time modal)
- No confidence score, model internals, or retrieval debug info shown to the end user under any circumstance

### Extendables (post-MVP, time permitting)
- Voice input (speech-to-text query, not just TTS playback)
- Interactive formulation-classification widget (visual decision tree instead of chat Q&A) — this is the "make it feel less like a plain chatbot" upgrade
- Saved/bookmarked answers and citation history per user session
- Multi-turn comparison view (e.g. "show me classical vs new-drug posture side by side")
- User consent flow + UI for connecting personal paid-database subscriptions
- Admin/internal dashboard surfacing confidence scores, abstention rate, and flagged low-confidence answers for team review (this is where the internal-only confidence metric actually gets used)

---

## Backend

### MVP (must ship)
- FastAPI service exposing chat, jurisdiction-toggle, and citation-lookup endpoints
- Formulation classifier: fixed decision tree across the six categories (classical/generic, patent-or-proprietary, new/non-classical, phytopharmaceutical, Ayurveda-Aahar/nutraceutical, cosmetic) — hardcoded logic, not open LLM inference, since correctness here gates everything downstream
- Jurisdiction router: hard filter on the retrieval layer (metadata/collection split), not a prompt instruction — India and international corpora must never mix in one retrieval call
- RAG retrieval over a curated, version-tracked corpus (statutes, rules, treaties, pharmacopoeial standards, registry records, case law) stored in ChromaDB, with original source documents also kept on disk for the MVP
- Citation-grounded generation: every claim in an answer traceable to a specific retrieved chunk; no answer ships without at least one citation
- Internal confidence scoring per answer, logged server-side only — never returned in the user-facing API response
- "Verify this act" registry: a lookup table built at ingestion time mapping act/rule/treaty name → local PDF path (avoids depending on a live external fetch during answers or demos)
- Free-source ingestion pipeline for the official databases named in the problem statement (TKDL, IP India, WIPO, India Code, etc.) — scheduled batch ingestion, not live connectors
- LangGraph orchestration implementing the flow: classify → route → retrieve → generate → log-confidence-and-serve, as explicit graph nodes/edges
- Multilingual embedding model (open-source) for the retrieval corpus
- Open-source LLM for generation
- Bhashini integration for translation and text-to-speech

### Extendables (post-MVP, time permitting)
- Paid-subscription connectors: OAuth/API-key vault per user, explicit logged consent before every call to a paid source — deliberately deferred, not half-built in MVP
- Relational knowledge graph layer for deeper multi-step/cross-regime reasoning (e.g. linking a GI record to a related patent bar)
- Agentic multi-source orchestration beyond the fixed classify→route→retrieve pipeline
- Corpus auto-refresh / change-detection when an act or rule is amended, instead of manual re-ingestion
- Escalation path to a human IP facilitator when the model abstains or confidence is low
- Voice-mode end-to-end (STT query → RAG → TTS answer) as a fully spoken interaction, not just TTS playback
- Formal evaluation harness: answer accuracy, citation correctness, safe-abstention rate, multilingual quality — needed eventually but not required to demo a working MVP
- Privacy/audit logging aligned to the Digital Personal Data Protection Act, beyond basic request logging

---

## Non-functional (applies to both)
- Never fabricate a citation — abstain rather than guess when the corpus doesn't cover the question
- Corpus entries carry a version/last-verified date so staleness is at least detectable, even if auto-refresh is a later-phase item
- Disclaimer language and confidence-hiding are enforced at the API response layer, not left to the frontend to respect — the API should never send a confidence field in the user-facing payload in the first place
