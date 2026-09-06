# IP-SAKTI Sahayak — tech stack

Legend: **Decided** = locked in from our discussion. **Open** = not yet chosen, needs a call before build starts on that piece.

---

## Backend

| Layer | Choice | Status |
|---|---|---|
| API framework | FastAPI | Decided — local FastAPI deployment for async streaming + LangGraph agent calls |
| Orchestration | LangChain + LangGraph | Decided — graph nodes for classify → route → retrieve → generate → log |
| Vector DB | ChromaDB | Decided — MVP scale |
| Raw source storage | Original docs kept on disk alongside Chroma, for MVP | Decided |
| Embedding model | intfloat/multilingual-e5-large via FastEmbed | Decided |
| Generation model | llama-3.3-70b-versatile via Groq | Decided |
| Translation / TTS / voice | Bhashini API | Decided — India-first, covers translate + tap-to-listen |
| Task queue / async jobs | Local manual ingestion scripts (python ingest.py) | Decided for MVP |
| Confidence scoring | Logged server-side per answer, excluded from user-facing API payload | Decided (mechanism TBD — e.g. retrieval-score + generation self-eval combo) |

## Frontend

| Layer | Choice | Status |
|---|---|---|
| Framework | Streamlit | Decided — for rapid MVP prototyping |
| Chat/streaming | Streamlit native chat UI | Decided |
| Jurisdiction toggle, "verify this act" PDF viewer, language selector, tap-to-listen | Custom components in Streamlit | Decided as required features |

## Data / corpus

| Layer | Choice | Status |
|---|---|---|
| Corpus scope (national) | Patents Act + 2024 Rules, GI, Trade Marks, Designs, Copyright, Plant-Variety regimes, Biological Diversity Act (2023 amendment + 2024 Rules), Drugs and Cosmetics Act, Drugs and Magic Remedies Act, FSSAI Ayurveda-Aahar regs | Decided — full scope per problem statement |
| Corpus scope (international) | TRIPS, CBD + Nagoya Protocol, WIPO GRATK Treaty, PCT, Madrid System, Hague System, Budapest Treaty, herbal-product market-access regimes of key export markets | Decided — full scope per problem statement |
| Ingestion | Scheduled batch ETL from free official sources (TKDL, IP India, WIPO, India Code, etc.) | Decided as approach; specific scraper/pipeline tooling TBD |
| Jurisdiction separation | Metadata filter or separate Chroma collections, enforced at retrieval time | Decided as approach |
| "Verify this act" registry | Lookup table (act/rule/treaty name → local PDF path), built at ingestion time | Decided |

## Deferred (Phase 2+, not MVP stack decisions yet)
- Paid-source connector auth pattern (OAuth/API-key vault + consent logging)
- Relational knowledge graph store
- Formal eval harness tooling
- Voice STT for query input (TTS-out is MVP; STT-in is not)

---

## Open items to resolve before build starts
1. Frontend framework
2. Exact embedding model and exact generation model (compute-dependent)
3. Task queue for scheduled ingestion jobs
4. Confidence-scoring mechanism (what actually produces the internal score)
