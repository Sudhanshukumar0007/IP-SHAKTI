# 2026-09-02 — Full LangGraph Architecture Implementation

## What was accomplished

Replaced the vanilla RAG demo (`main.py`, 115 lines) with the complete IP-SHAKTI
LangGraph pipeline architecture as specified in all planning documents, incorporating
7 architectural improvements from user review.

## Files created

| File | Purpose |
|---|---|
| `backend/graph/__init__.py` | Package init |
| `backend/graph/state.py` | `AgentState` TypedDict — all 14 fields |
| `backend/graph/nodes.py` | 5 LangGraph nodes |
| `backend/graph/edges.py` | 2 conditional edge functions |
| `backend/graph/graph.py` | Compiled `StateGraph` |
| `backend/services/__init__.py` | Package init |
| `backend/services/classifier.py` | Q1–Q5 gate tree, 0 LLM calls |
| `backend/services/retriever.py` | Chroma wrapper + abstention logic + registry lookups |
| `backend/services/session_store.py` | In-memory session state |
| `backend/services/query_log.py` | SQLite structured query log |

## Files modified

| File | Change |
|---|---|
| `backend/main.py` | Full rewrite: `/session`, `/chat`, `/verify-act`, `/pdf/{id}`, `/eval/summary` |
| `backend/requirements.txt` | Added `langchain-groq`, bumped `langgraph>=0.2.0`, `langchain>=0.2.0` |
| `.env` | Added `GROQ_API_KEY`, `GROQ_MODEL` |

## Architectural decisions made

### 1. Jurisdiction isolation is structural, not prompt-level
`national_answer` and `international_answer` are separate TypedDict fields.
They cannot be merged in the graph — only the frontend assembles them for display.

### 2. Abstention is similarity-quality-based
Two-gate abstention: `max_similarity < threshold` OR `relevant_chunks < minimum`.
Not a naive chunk count. Thresholds are env-configurable (`SIMILARITY_THRESHOLD`,
`MIN_RELEVANT_CHUNKS`) so they can be tuned with the eval set.

### 3. Confidence logged as components, not just a scalar
`confidence_components = {max_similarity, mean_similarity, relevant_chunk_count, disclosure_fill_rate}`
stored separately in SQLite so `/eval/summary` can expose the distribution for tuning.
Composite score formula: `0.5 × max_sim + 0.3 × mean_sim + 0.2 × fill_rate`.

### 4. document_id as the provenance key throughout the pipeline
Citations carry `document_id` (ingest-time hash), not `source_pdf_path`.
`/verify-act` returns metadata only. `/pdf/{document_id}` serves the file after
backend registry lookup + path traversal guard. Filesystem paths never reach the frontend.

### 5. Full classification audit trail
`clarification_history` (list of `{question, answer}` dicts) and `formulation_answers`
(raw yes/no list) are both preserved in state and logged to SQLite. This gives a
full record of how the routing decision was reached — important for a compliance tool.

### 6. LLM switched to Groq
`ChatGroq` replaces `ChatOpenRouter`. Model configurable via `GROQ_MODEL` env var,
defaulting to `llama-3.3-70b-versatile`. Previous `langchain-openrouter` dependency
kept in requirements for backward compatibility.

### 7. Session state never returned in full
`/session/{id}` returns only public fields. `/chat` response strips `confidence_score`,
`confidence_components`, `start_time`, `retrieved_chunks_*`, and `abstain_reason`
(the last is surfaced only in abstain mode for the user to understand why).

## Verified

- `graph/state.py`, `services/classifier.py`, `graph/edges.py` — all import cleanly.
- Classifier leaf resolution tested for all 5 paths (cosmetic, ayurveda_aahar,
  classical, phytopharmaceutical, proprietary, new_drug). All resolve correctly.

## Known limitations (MVP)

- `both` mode runs national + international Groq calls sequentially, not in parallel.
  Parallel async would require `ainvoke` support in the LangGraph runner + async
  LangChain client — deferred post-MVP.
- In-memory session store is not garbage-collected.
- No Bhashini `/translate` or `/tts` proxy yet (stubs planned in next session).
