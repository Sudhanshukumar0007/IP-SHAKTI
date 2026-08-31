# IP-SAKTI Sahayak — API surface & eval logging (high level)

Kept intentionally loose — this is enough to start wiring frontend ↔ backend, not a locked contract. Field names, exact request/response shapes, and a few sequencing questions are still open by design; revisit once `/chat` is actually being implemented and the LangGraph state object's real shape is known.

---

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /session` | Starts a session, returns `session_id`. All state (classification progress, jurisdiction mode, retrieved context) lives server-side keyed to this — the frontend never resends full conversation history. |
| `GET /session/{id}` | Resume/reload — needed so a browser refresh mid-classification doesn't lose progress, since state is server-side. |
| `POST /chat` | The main endpoint. Takes `session_id` + the user's message or button-tap answer + `jurisdiction_mode`. Returns either a clarification question (still classifying) or a final answer (disclosure draft + citations + disclaimer) — one endpoint, two possible response shapes. |
| `GET /verify-act` | Takes act name + jurisdiction, serves the source PDF for that act (either directly, or via a mounted static route over the corpus directory — pick one, don't leave PDF-serving undecided). |
| `POST /translate` / `POST /tts` (or one `/localize`) | Thin server-side proxy to Bhashini — keeps the API key off the frontend. |
| `GET /eval/summary` | Dev/internal only, not user-facing. Aggregates the query log (below) into abstention rate, average confidence, per-language counts, average latency — the number-backed argument for the submission. |

## Deliberately left open
- Exact request/response field names and types
- Whether changing the jurisdiction toggle mid-conversation resets the session or just re-routes the next `/chat` call
- Whether voice input goes through `/translate` first or needs its own `/stt` step
- Auth/rate-limiting shape (parked with the broader DPDP/security planning item)

---

## Query logging for eval

Every query gets logged to a **queryable structured store** (SQLite is enough for a hackathon build) — not an append-only text file that has to be parsed by hand later. This is what turns "safe abstention," "citation correctness," and "multilingual quality" from claims in the report into numbers pulled from a table.

One row per query:

| Field | Purpose |
|---|---|
| `session_id`, `timestamp` | Identify and order the query |
| `raw_query`, `language`, `jurisdiction_mode` | What was asked, and how |
| `formulation_category` | Which of the six categories it resolved to |
| `retrieved_chunk_ids` + similarity scores | What the retrieval step found, and how confident |
| `citations` | What the answer actually cited |
| `confidence_score`, `abstain` | Internal score and whether the system declined to answer |
| `llm_calls_made`, `latency_ms` | Cost/performance tracking — especially useful given the call-minimization design |

`/eval/summary` queries this table on demand — abstention rate, average confidence, latency distribution, per-language volume — rather than these numbers being assembled manually before a demo.
