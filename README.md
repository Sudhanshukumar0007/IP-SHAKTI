# IP-SAKTI Sahayak (AyurLex)

**AyurLex** is a multilingual, source-cited RAG (Retrieval-Augmented Generation) assistant built for **SIH26045 (Smart India Hackathon)**. It provides precise Intellectual Property (IP) and regulatory guidance specifically tailored for Ayurveda formulations. 

## 1. Overview
Ayurveda practitioners, researchers, and enterprises often struggle to navigate the complex web of traditional medicine regulations and IP laws. The rules governing a basic cosmetic oil are vastly different from those governing a new phytopharmaceutical drug.

**AyurLex solves this by:**
1. Enforcing a strict classification gate to understand the exact nature of the formulation before giving advice.
2. Grounding all advice strictly in authoritative legal acts and official registries.
3. Keeping national (Indian) and international frameworks completely separate.

**Why jurisdiction-separation matters:** 
Blending national regulations (like India's *Drugs and Cosmetics Act, 1940*) with international treaties (like the *Nagoya Protocol* or *PCT*) in a single LLM prompt frequently causes cross-jurisdictional hallucinations. AyurLex isolates retrieval and generation by jurisdiction to ensure legally sound, context-appropriate advice.

## 2. Key Features
- **Multilingual Chat & Jurisdiction Toggle:** Users can switch between National (India), International, or Both, and interact in English, Hindi, Sanskrit, Bengali, Tamil, or Telugu.
- **Source-Cited Answers & PDF Viewer:** Every claim is backed by inline citations `[E1]`. Clicking a citation opens a "Verify this Act" PDF viewer focused exactly on the relevant page.
- **Formulation Classification Gate:** The assistant asks up to 5 clarifying Yes/No questions (e.g., "Is this for external use only?") to deterministically classify the product before querying the LLM.
- **Evidence Verification & Abstention:** If the retrieved corpus chunks fall below strict similarity thresholds, the assistant explicitly *abstains* rather than hallucinating an answer.
- **Internal Confidence Scoring & Eval Dashboard:** Dev-only dashboards at `/eval` provide deep observability into task coverage, abstention rates, and node execution (hidden from end-users).
- **Session-Based Architecture:** All chat state, execution traces, and clarification histories are stored securely on the backend in a local session store.

## 3. Architecture
AyurLex is powered by a **LangGraph** state machine.

### Pipeline Flow
`detect_intent` → `auto_classify` → `classify_formulation` → `supervisor` → `worker` → `evidence_verification` → `live_registry_search` (stubbed) → `generate` → `score_confidence` → `log_and_serve`

1. **Classification:** Zero-LLM deterministic gate tree categorizes the formulation.
2. **Retrieval (Worker):** Parallel workers query ChromaDB for chunks.
3. **Verification:** Inspects chunk similarities to enforce strict grounding thresholds. Short-circuits to `log_and_serve` if abstention is triggered.
4. **Generation:** Fires **one isolated LLM call per active jurisdiction**. This prevents the LLM from accidentally applying Indian biodiversity laws to a European patent question.
5. **Logging:** Writes comprehensive metrics to a SQLite query log.

## 4. Tech Stack
### Backend
- **Framework:** FastAPI
- **Orchestration:** LangGraph & LangChain Core
- **Embeddings:** BGE-M3 (`intfloat/multilingual-e5-large`) via FastEmbed
- **Vector DB:** ChromaDB (split into `ip_sakti_national` and `ip_sakti_international` collections)
- **Database:** SQLite (`query_log.db`) for evaluation metrics
- **Rate Limiting:** `slowapi`
- **LLM:** `llama-3.3-70b-versatile` (via Groq, configurable)

### Frontend
- **Framework:** React + React Router + Vite
- **Styling:** CSS + Framer Motion (for animations)
- **Data Viz:** Mermaid.js (live orchestration graphs) & Recharts
- **Audio:** Browser native `SpeechSynthesis` API (TTS)

## 5. Directory Structure
```text
IP-SHAKTI/
├── backend/
│   ├── main.py              # FastAPI app, endpoints, rate limits
│   ├── config.py            # Environment configurations (Settings)
│   ├── requirements.txt
│   ├── query_log.db         # SQLite db for eval metrics
│   ├── registry.json        # Mapping of document_ids to source PDFs
│   ├── graph/
│   │   ├── graph.py         # LangGraph StateGraph definition
│   │   ├── state.py         # TypedDict AgentState definition
│   │   ├── nodes.py         # Implementation of graph nodes (generate, verify, etc.)
│   │   └── edges.py         # Conditional routing logic
│   └── services/
│       ├── classifier.py    # Deterministic formulation gate questions
│       ├── retriever.py     # ChromaDB interactions and abstention thresholds
│       ├── session_store.py # In-memory session tracking
│       └── query_log.py     # SQLite persistence for evaluations
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx          # Main chat UI, message mapping, PDF viewer
│       ├── i18n.js          # Hardcoded multilingual strings and TTS mapping
│       ├── api/             # API client wrapper
│       ├── components/      # Sidebar, Layouts
│       └── pages/
│           ├── EvalDashboard.jsx # Individual session graph and chunk data
│           └── EvalList.jsx      # Global evaluation metrics and runs
└── Corpus/                  # Raw PDFs mapped by registry.json
```

## 6. Getting Started
### Prerequisites
- Python 3.10+
- Node.js 18+
- Groq API Key (or OpenAI/Other supported by LangChain)

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```
Create a `.env` file in the `backend` directory (see Section 7).

*To run the server:*
```bash
uvicorn main:app --reload --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## 7. Environment Variables
Backend `.env` configuration:

| Variable | Description | Example |
|---|---|---|
| `ENABLE_DEV_TRACE` | Enables `/eval/summary` and internal logs | `true` |
| `ALLOWED_ORIGINS` | CORS origins | `http://localhost:5173` |
| `HOST` | API host bind | `0.0.0.0` |
| `PORT` | API port | `8000` |
| `SESSION_TTL_SECONDS` | How long to keep server-side chat state | `86400` |
| `GROQ_API_KEY` | Provider key (if using Groq) | `gsk_...` |
| `EMBEDDING_MODEL` | FastEmbed model for Chroma | `intfloat/multilingual-e5-large` |
| `LLM_MODEL` | Primary generation model | `llama-3.3-70b-versatile` |
| `LLM_PROVIDER` | LLM Provider backend | `groq` |
| `SIMILARITY_THRESHOLD` | Min distance to consider chunk relevant | `0.35` |
| `MIN_RELEVANT_CHUNKS` | Minimum chunks required to avoid abstain | `1` |
| `RETRIEVAL_K` | Number of chunks to fetch | `8` |

## 8. API Reference
All endpoints are defined in `backend/main.py`.

- **`POST /session`**: Creates a new chat session. Returns `session_id`.
- **`GET /session/{session_id}`**: Returns public session state (used for UI hydration, omits internal confidences).
- **`POST /chat`**: Main RAG endpoint. Expects `session_id` and `message`. Triggers LangGraph pipeline. Rate-limited to 5/minute.
- **`GET /verify-act`**: Document metadata lookup based on `document_id` or `act_name`. Does not expose filesystem paths.
- **`GET /pdf/{document_id}`**: Serves the actual source PDF file resolved securely via the backend registry.
- **`GET /api/eval/graph`**: Returns Mermaid.js syntax for the orchestration graph.
- **`GET /api/eval/metrics/{session_id}`**: Returns detailed node status, retrieved chunks, and abstention reasons for a specific run.
- **`GET /eval/summary`**: Returns aggregated query log metrics (total queries, abstention rate, avg confidence). Requires `ENABLE_DEV_TRACE=true`.
- **`GET /health`**: Liveness check.

## 9. Formulation Classification Logic
AyurLex uses a strict zero-LLM classification tree to route questions. The user must answer Yes/No to resolve the category:
1. **Cosmetic:** External use only, no therapeutic claim.
2. **Ayurveda-Aahar:** Consumed as food/supplement, no disease-cure claim.
3. **Classical:** Exact match to First-Schedule authoritative text, unmodified.
4. **Phytopharmaceutical:** Purified, standardized extract from a single plant.
5. **Proprietary:** Deviates from classical texts but follows principles.
6. **New Drug:** Deviates and requires new clinical safety/efficacy data.

## 10. Evidence Verification & Abstention
The `evidence_verification` node (and `retriever.py`) enforces strict grounding rules:
- **`VERIFIED`**: Sufficient chunks met the `SIMILARITY_THRESHOLD`.
- **`PARTIAL`**: Some constraints met, but warnings apply (e.g. asking for case law but finding none).
- **`ABSTAINED`**: Best match chunk is below `SIMILARITY_THRESHOLD`, or total relevant chunks < `MIN_RELEVANT_CHUNKS`. The assistant refuses to answer to prevent hallucination.

## 11. Evaluation Dashboard (dev-only)
Accessible via the frontend at `/eval`.
- **Global Metrics:** Shows total queries, safe abstention rate, average latency, and confidence heuristics.
- **Session View (`/eval/:sessionId`):** Renders a live Mermaid graph of the LangGraph execution. Clicking nodes (e.g., `worker`) reveals exact retrieved chunks, similarity scores, and why the system chose to proceed or abstain.

## 12. Data & Corpus
Documents are ingested offline into ChromaDB and mapped via `backend/registry.json`. 
**Current Known Gaps:**
- The *TRIPS Agreement* is not yet ingested into the active ChromaDB collections.
- *Wipo Treaty On Intellectual Property* acts as a loose identifier in the corpus (likely referring to GRATK) and may need re-indexing.

## 13. Internationalization
AyurLex supports UI and LLM output in **English, Hindi, Sanskrit, Bengali, Tamil, and Telugu**.
- **Translation:** Currently handled natively by the LLM prompt.
- **TTS (Text-to-Speech):** Handled via the browser's native `window.speechSynthesis` API based on localized language codes.
- **Bhashini Integration:** Planned for future roadmap to replace browser TTS and LLM translation for higher vernacular accuracy.

## 14. Known Limitations
- **`live_registry_search` is stubbed:** The LangGraph node exists but is currently configured to skip. Live API searches (e.g. to TKDL or IP India) are not yet implemented.
- **`claim_grounding` and `citation_accuracy` metrics are stubbed:** These appear as null/unavailable in the Evaluation Dashboard.
- **Latency tracking:** Granular `duration_ms` per LangGraph node is not yet natively tracked.

## 15. Roadmap
- Integrate **Bhashini APIs** for robust indic language ASR/TTS.
- Implement the **Live Registry Search** node to hit external API endpoints (TKDL/WIPO).
- Ingest remaining international IP treaties (TRIPS) into the vector store.
- Implement LLM-as-a-judge scoring for `claim_grounding`.

## 16. Contributing
Changes should follow standard feature-branch workflows. Ensure you run backend tests (if provided) and verify the LangGraph state machine locally using `ENABLE_DEV_TRACE=true` to monitor node performance.

## 17. Disclaimer
**Information, not legal advice.** 
AyurLex provides legal research and information for reference purposes only. Always verify the current law and official sources before relying on any information.

## 18. License & Credits
Developed for the **Smart India Hackathon (SIH26045)**.
