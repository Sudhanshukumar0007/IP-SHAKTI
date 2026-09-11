# IP-SAKTI Sahayak (AyurLex)

**AyurLex** is a multilingual, source-cited RAG (Retrieval-Augmented Generation) assistant built for **SIH26045 (Smart India Hackathon)**. It provides precise Intellectual Property (IP) and regulatory guidance specifically tailored for Ayurveda formulations. 

---

## 1. Overview
Ayurveda practitioners, researchers, and enterprises often struggle to navigate the complex web of traditional medicine regulations and IP laws. The legal and statutory rules governing a basic classical churnam are vastly different from those governing a proprietary cosmetic oil or a novel phytopharmaceutical drug.

**AyurLex solves this by:**
1. **Enforcing a strict formulation classification gate** to understand the exact regulatory classification of the product before issuing legal advice.
2. **Grounding all advice strictly in authoritative legal acts, schedules, and official registries** with verifiable inline citations.
3. **Keeping national (Indian) and international frameworks completely separate** across retrieval and LLM generation.
4. **Providing temporal isolation** to guarantee that superseded amendments and outdated laws are never cited as active statutes.
5. **Integrating live external grounding** via Google Search Grounding to verify recent registry filings or fill vector database gaps before abstaining.

### Why Jurisdiction & Temporal Separation Matters
* **Jurisdiction Blending Hallucinations:** Blending national statutes (e.g., India's *Drugs and Cosmetics Act, 1940*, *Biological Diversity Act, 2002*) with international treaties (e.g., *Nagoya Protocol*, *PCT*, *TRIPS*) in a single LLM prompt frequently causes cross-jurisdictional hallucinations (e.g., applying Indian NBA benefit-sharing penalties to an EPO patent filing). AyurLex executes isolated retrieval and generation pipelines per jurisdiction.
* **Temporal Confusion:** In intellectual property and drug law, old versions of acts remain historically significant but legally obsolete. AyurLex partitions vectors into `current` and `history` collections, ensuring active advice references only current consolidated legislation.

---

## 2. Key Features

- **Multilingual Chat & Jurisdiction Toggle:**
  - Dynamic switching between **National (India)**, **International**, or **Both**.
  - Vernacular interaction and output in **English, Hindi, Sanskrit, Bengali, Tamil, and Telugu**.
  - Verbatim legal citations and section identifiers are preserved in their official authoritative format regardless of language.

- **Source-Cited Answers & In-App PDF Viewer:**
  - Every claim is tied to an inline citation `[E1]`, `[E2]`.
  - Clicking any citation opens a built-in PDF viewer focused directly on the exact verified page of the official source document without exposing local backend server paths.

- **Formulation Classification Gate:**
  - **Auto-Classify:** Skips clarifying questions if the user query explicitly declares its category (e.g., "classical churna", "ayurveda aahara").
  - **Interactive Gate Tree:** For ambiguous queries, the assistant asks targeted Yes/No questions (bounded by `MAX_CLARIFICATION_ATTEMPTS`) to deterministically classify the formulation into one of six statutory categories before retrieval.

- **Informational Query Bypass:**
  - Direct statutory research questions (e.g., *"What is Section 3(p) of the Patents Act?"*) are recognized via a zero-cost rule-based intent gate (`detect_intent`), bypassing the formulation classification gate entirely.

- **Hybrid Dense Retrieval & CrossEncoder Reranking:**
  - Generates sub-queries for parallel legal tasks via a `supervisor` agent.
  - Queries ChromaDB with 1024-dimensional multilingual embeddings (`intfloat/multilingual-e5-large`), followed by reranking using `cross-encoder/ms-marco-MiniLM-L-6-v2`.
  - Enforces database-level temporal separation (`is_latest_consolidated: True`).

- **Live Registry Fallback (Search Grounding):**
  - When internal vector stores lack sufficient evidence, the `LiveRegistryConnector` triggers live patent/regulatory searches using **Gemini 2.5 with Google Search Grounding** (with automatic fallback to DuckDuckGo).

- **Claim-Level Verification & Safe Abstention:**
  - Inspects chunk similarity thresholds (`SIMILARITY_THRESHOLD`) and unresolved legal references.
  - If evidence is below threshold or ungrounded, the assistant explicitly **abstains** with a clear explanation rather than risking legal hallucinations.

- **Automated Validation & Retry Loops:**
  - A dedicated `validate_response` node verifies that generated responses strictly conform to required JSON schemas, disclaimer rules, and legal guardrails.
  - If output validation fails, it triggers an automated retry loop back to `generate` with targeted feedback.

- **Observability & Evaluation Suite:**
  - **Live Runtime Dashboard (`/eval`):** Renders an interactive Mermaid.js diagram of the LangGraph execution, detailing node execution states, task coverage, and chunk-level similarity scores.
  - **Offline Evaluation Benchmark (`evaluate.py`):** Runs an automated test suite featuring LLM-as-a-judge semantic evaluations and deterministic citation verification.

---

## 3. Architecture & Pipeline Flow

AyurLex is powered by a stateful **LangGraph** orchestration graph:

```text
                     [START]
                        │
                  detect_intent          ← Rule-based (0 LLM cost)
                        │                  Informational? → skip Q&A tree
         ┌──────────────┴──────────────┐
         │                             │
  (informational)              (formulation / unknown)
         │                             │
         │                        auto_classify
         │                             │
         │                   classify_formulation (Q&A tree)
         │                             │
         │              ┌──────────────┼──────────────┐
         │              │              │              │
         │      (classification    (resolved)   (needs clarification)
         │        _failed)             │              │
         │              │              │            [END]
         └──────────────┼──────────────┘
                        │
                    supervisor           ← Plans sub-tasks per jurisdiction
                        │
                     worker              ← Parallel retrieval & CrossEncoder rerank
                        │
              evidence_verification      ← Evaluates threshold & grounding
                        │
                ┌───────┴───────┬────────────────────────┐
                │               │                        │
         (live needed)      (verified)               (abstain)
                │               │                        │
       live_registry_search     │                        │
                │               │                        │
                └───────┬───────┘                        │
                        │                                │
                     generate           ← Isolated calls │
                        │                 per jurisdiction│
                        │                                │
                validate_response                        │
                   (retry loop)                          │
                        │                                │
                 score_confidence                        │
                        │                                │
                  log_and_serve ◄────────────────────────┘
                        │
                      [END]
```

### Node Responsibilities
1. **`detect_intent`:** Fast rule-based router that identifies direct statutory questions and routes directly to the supervisor, bypassing formulation questions.
2. **`auto_classify`:** Scans for unambiguous keywords to resolve formulation categories immediately.
3. **`classify_formulation`:** Deterministic, zero-LLM decision tree asking clarifying Yes/No questions when formulation category is ambiguous.
4. **`supervisor`:** Deconstructs the query into domain-specific legal tasks across National (Drugs & Cosmetics, Biodiversity, Patents, FSSAI) and International jurisdictions.
5. **`worker`:** Performs vector retrieval against ChromaDB collections and reranks candidate chunks using `ms-marco-MiniLM-L-6-v2`.
6. **`evidence_verification`:** Evaluates max and mean similarity scores against `SIMILARITY_THRESHOLD`. Routes to `generate`, `live_registry_search`, or short-circuits to `log_and_serve` (abstain).
7. **`live_registry_search`:** Queries Google Search Grounding via Gemini 2.5 (or DuckDuckGo) for missing external registry evidence.
8. **`generate`:** Executes one isolated LLM call per active jurisdiction using multi-key Groq rotation and structured JSON schema enforcement.
9. **`validate_response`:** Audits output against required disclosure fields and regulatory disclaimers; retries generation upon validation failure.
10. **`score_confidence`:** Computes an internal confidence heuristic based on task coverage, chunk relevance, and unresolved references.
11. **`log_and_serve`:** Writes query telemetry to SQLite (`query_log.db`) and sanitizes internal trace data before returning the user-facing response.

---

## 4. Tech Stack

### Backend
- **Framework:** FastAPI
- **Orchestration:** LangGraph & LangChain Core
- **Embeddings:** FastEmbed (`intfloat/multilingual-e5-large`, 1024 dimensions)
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2` via `sentence-transformers`
- **Vector Database:** ChromaDB with 4 temporally separated collections:
  - `ip_sakti_national_current`
  - `ip_sakti_national_history`
  - `ip_sakti_international_current`
  - `ip_sakti_international_history`
- **Primary LLM:** `openai/gpt-oss-20b` (or `llama-3.3-70b-versatile`) via Groq
- **LLM Fallback & Resilience:** Automated multi-key rotation (`GROQ_API_KEY`, `GROQ_API_KEY2`..`10`) and fallback model support (`LLM_FALLBACK_MODEL`); OpenRouter compatibility.
- **Live Search & External Grounding:** Google GenAI SDK (`gemini-2.5-flash` with Google Search Grounding) and DuckDuckGo Search (`duckduckgo-search`).
- **Knowledge Graph & TOC:** Custom graph service (`services/knowledge_graph.py`) linking amended acts and regulatory mappings (`governed_by_map.json`, `toc_map.json`).
- **Telemetry & Logs:** SQLite (`query_log.db`)
- **Rate Limiting:** `slowapi`

### Frontend
- **Framework:** React 18 + React Router + Vite
- **Styling:** CSS + Framer Motion (micro-animations & smooth transitions)
- **Data Visualization & Graphs:** Mermaid.js (live LangGraph visualization) & Recharts
- **Audio / Speech:** Web Speech API (`SpeechSynthesis`) mapped to vernacular language codes

---

## 5. Directory Structure

```text
IP-SHAKTI/
├── backend/
│   ├── main.py                     # FastAPI application, routes, rate limiting
│   ├── config.py                   # Pydantic/Environment settings
│   ├── requirements.txt            # Python dependencies
│   ├── ingest.py                   # PDF parsing, markdown cleaning, chunking & Chroma ingestion
│   ├── registry.json               # Canonical registry mapping document_ids to metadata & hashes
│   ├── governed_by_map.json        # Statutory category-to-act mapping rules
│   ├── toc_map.json                # Table of contents index for structured legal navigation
│   ├── query_log.db                # SQLite database storing execution logs & evaluation metrics
│   ├── evaluate.py                 # Offline evaluation runner (LLM-as-a-judge + citation checks)
│   ├── deterministic_checks.py     # Deterministic evaluation assertions
│   ├── test_cases.json             # SIH evaluation benchmark test suite
│   ├── graph/
│   │   ├── graph.py                # LangGraph StateGraph builder & compiled app
│   │   ├── state.py                # AgentState TypedDict definition
│   │   ├── nodes.py                # Implementations of all 11 pipeline nodes
│   │   └── edges.py                # Conditional routing logic & loop conditions
│   └── services/
│       ├── classifier.py           # Formulation classification decision tree
│       ├── connector.py            # LiveRegistryConnector (Gemini Search Grounding + DDGS)
│       ├── knowledge_graph.py      # Cross-act amendment & statutory resolver
│       ├── retriever.py            # ChromaDB retrieval, CrossEncoder reranking & abstention logic
│       ├── session_store.py        # In-memory session tracking & TTL cleanup
│       └── query_log.py            # SQLite queries and evaluation summary calculations
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx                 # Primary chat interface, message rendering & PDF viewer modal
│       ├── i18n.js                 # Multilingual localization strings & TTS language codes
│       ├── api/                    # Axios API client
│       ├── components/
│       │   └── Sidebar.jsx         # Navigation sidebar & session controls
│       └── pages/
│           ├── EvalDashboard.jsx   # Live session graph inspection & chunk relevance breakdown
│           └── EvalList.jsx        # Global telemetry, abstention metrics & query logs
├── Corpus/                         # Curated legal PDFs (National & International)
└── chroma_db/                      # Local ChromaDB vector storage files
```

---

## 6. Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+
- Groq API Key (one or more keys for rotation)
- Google Gemini API Key (optional, for live search grounding)

### Backend Setup
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows (or: source .venv/bin/activate on Unix)
pip install -r requirements.txt
```

Create a `.env` file in the project root or `backend` folder (see Section 7).

*Run the ingestion pipeline (if populating or updating ChromaDB):*
```powershell
python ingest.py
```

*Start the FastAPI development server:*
```powershell
uvicorn main:app --reload --port 8000
```

### Frontend Setup
```powershell
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 7. Environment Variables

| Variable | Description | Default / Example |
|---|---|---|
| `GROQ_API_KEY` | Primary Groq API key | `gsk_...` |
| `GROQ_API_KEY2`..`10` | Optional pool keys for automated rotation and load balancing | `gsk_...` |
| `GEMINI_API_KEY` | Google Gemini API key for live Search Grounding fallback | `AQ...` |
| `LLM_PROVIDER` | LLM inference backend (`groq` or `openrouter`) | `groq` |
| `LLM_MODEL` | Primary LLM model identifier | `openai/gpt-oss-20b` |
| `LLM_FALLBACK_MODEL` | Fallback model used when primary model hits rate limits | `openai/gpt-oss-20b` |
| `OPENROUTER_API_KEY` | Key if using `LLM_PROVIDER=openrouter` | `sk-or-...` |
| `EMBEDDING_MODEL` | FastEmbed dense embedding model | `intfloat/multilingual-e5-large` |
| `SIMILARITY_THRESHOLD` | Minimum normalised similarity required to treat a chunk as relevant | `0.35` |
| `MIN_RELEVANT_CHUNKS` | Minimum chunks above threshold required to avoid abstention | `1` |
| `RETRIEVAL_K` | Number of candidate chunks retrieved per task before reranking | `8` |
| `MAX_CLARIFICATION_ATTEMPTS` | Maximum clarification turns before terminating classification | `3` |
| `SESSION_TTL_SECONDS` | Server-side session retention duration in seconds | `86400` (24 hrs) |
| `ENABLE_DEV_TRACE` | Enables dev-only evaluation endpoints (`/eval/summary`, `/api/eval/*`) | `true` |
| `ALLOWED_ORIGINS` | Permitted CORS origins | `http://localhost:5173` |
| `JUDGE_GROQ_API_KEY` | Dedicated Groq key for offline evaluation runner (`evaluate.py`) | `gsk_...` |
| `JUDGE_MODEL` | Model used for semantic evaluation judging | `openai/gpt-oss-20b` |

---

## 8. API Reference

All endpoints are hosted on `backend/main.py`:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/session` | Creates a new chat session with specified jurisdiction mode and language. |
| `GET` | `/session/{id}` | Fetches public session state (omits internal confidences and raw traces). |
| `POST` | `/chat` | Core chat endpoint. Drives LangGraph pipeline and returns answer, citations, live evidence, or clarification question. Rate-limited via `slowapi`. |
| `GET` | `/verify-act` | Looks up legal document metadata via `document_id` or `act_name` without exposing server file paths. |
| `GET` | `/pdf/{document_id}` | Securely streams the requested PDF from the Corpus via backend registry lookup. |
| `GET` | `/api/eval/graph` | Returns live Mermaid.js syntax representing the compiled StateGraph. |
| `GET` | `/api/eval/metrics/{session_id}` | Returns granular execution traces, task coverage, retrieved chunk similarities, and abstention reasons for a session. |
| `GET` | `/eval/summary` | Aggregates global query logs (total queries, abstention rates, avg confidence). Requires `ENABLE_DEV_TRACE=true`. |
| `GET` | `/health` | Health check and liveness verification. |

---

## 9. Formulation Classification Logic

When a user query involves formulation-specific advice, the system maps the formulation into one of six statutory categories:

1. **Cosmetic:** External application only with no therapeutic or medicinal claims.
2. **Ayurveda-Aahar:** Consumed as food or nutritional supplement without claiming to prevent or cure specific diseases.
3. **Classical:** Exact, unmodified composition listed in the authoritative First-Schedule texts of the *Drugs and Cosmetics Act, 1940*.
4. **Phytopharmaceutical:** Purified, standardized extract from a single plant part, requiring specific clinical safety and characterization data.
5. **Proprietary (ASU):** Contains ingredients referenced in authoritative texts, but formulated in a non-classical combination or modern dosage form.
6. **New Drug:** Novel formulation requiring full-scale preclinical and clinical trials.

---

## 10. Evidence Verification & Abstention

To prevent hallucinations on legal questions, the pipeline executes strict validation before allowing answer generation:
* **`VERIFIED`**: Candidate chunks exceed `SIMILARITY_THRESHOLD`, cross-references are resolved, and task evidence is complete.
* **`PARTIAL`**: Sufficient evidence was found for primary tasks, but some sub-aspects lacked direct statutory citations (explicitly marked with warnings in the response).
* **`ABSTAINED`**: The system explicitly refuses to generate advice when:
  * Maximum chunk similarity is below `SIMILARITY_THRESHOLD`.
  * Total relevant chunks are less than `MIN_RELEVANT_CHUNKS`.
  * Cross-referenced acts cannot be grounded in the verified registry.

---

## 11. Evaluation Framework

AyurLex provides a two-tier evaluation architecture:

### 1. Live Runtime Dashboard (`/eval` and `/eval/:sessionId`)
Designed for non-blocking observability:
* Visualizes real-time LangGraph execution graphs via Mermaid.js.
* Displays node execution status (`PASSED`, `PARTIAL`, `FAILED`, `SKIPPED`).
* Inspects retrieved chunks, individual similarity scores, and abstention explanations.
* *Note:* Dynamic LLM-as-a-judge scoring is omitted during live chat to maintain sub-second response times.

### 2. Offline Benchmark Suite (`backend/evaluate.py`)
Used for formal verification against SIH test cases (`test_cases.json`):
* **Deterministic Citation Validation:** Asserts that every citation in the response strictly exists in the set of retrieved chunks (guaranteeing no fabricated references).
* **LLM-as-a-Judge:** Uses an independent Groq LLM instance with structured outputs to score task fidelity, jurisdictional boundary preservation, and vernacular accuracy.
* Outputs results directly to `eval_results.csv` and `eval_summary.md`.

---

## 12. Ingestion Pipeline & Corpus

The ingestion system (`backend/ingest.py`) processes legal PDFs into ChromaDB:
* **Layout Parsing:** Converts complex PDF legal layouts to markdown via `pymupdf4llm`.
* **Sanitization:** Cleans `<mark>` tags and collapses artifact whitespace before section splitting.
* **Section-Boundary Chunking:** Splits text based on statutory sections and articles using strict regex patterns so chunk boundaries never split legal sections arbitrarily.
* **Temporal Versioning:** Automatically maps `supersedes` and `superseded_by` relationships based on act effective dates and sets `is_latest_consolidated: True` for current statutes.
* **Resilient Registry Flush:** Progressively writes verified records to `backend/registry.json` only after chunks have been successfully indexed into ChromaDB.

---

## 13. Internationalization (i18n)

* **Supported Languages:** English, Hindi (हिंदी), Sanskrit (संस्कृतम्), Bengali (বাংলা), Tamil (தமிழ்), Telugu (తెలుగు).
* **Decoding Controls:** LLM system prompts strictly enforce that JSON response schemas and technical keys remain in English, while explanatory content and guidance are translated into the requested vernacular.
* **Citation Preservation:** Legal act titles (e.g., *"Drugs and Cosmetics Rules, 1945"*) and statutory section numbers remain verbatim in English to avoid distorted citations in court or regulatory filings.
* **Audio Synthesis:** Browser-native speech synthesis automatically pairs with the active language locale.

---

## 14. Disclaimer

**Information, not legal advice.**  
AyurLex is designed for academic research, preliminary IP exploration, and regulatory guidance. It does not replace formal legal counsel from registered patent attorneys or certified regulatory consultants. Always verify current statutes against the official Gazette of India and relevant IP offices before commercial filing.

---

## 15. Credits

Developed for the **Smart India Hackathon (SIH26045)**.
