# IP-SAKTI Sahayak — LangGraph state & node definitions

Designed for minimum LLM generation calls per query, to keep latency and API cost down. Worst case is exactly one generation call per user query, regardless of jurisdiction mode.

---

## Shared state object

| Field | Set by | Description |
|---|---|---|
| `raw_query` | Entry | User's original text/voice input, pre-translation |
| `language` | Entry | Detected/selected input language |
| `jurisdiction_mode` | Entry | `india` \| `international` \| `both` (from the toggle) |
| `formulation_category` | Classify node | One of six enum values, or `null` until resolved |
| `pending_clarification` | Classify node | Next gate question to show, if the tree isn't resolved yet |
| `retrieved_chunks_national` | Retrieve node | Chunk objects (with metadata) from `ip_sakti_national`, if applicable |
| `retrieved_chunks_international` | Retrieve node | Same, from `ip_sakti_international`, if applicable |
| `disclosure_draft` | Generate node | Six-field checklist per jurisdiction section — `{national: {...}, international: {...}}` shape when mode is `both` |
| `citations` | Generate node | Flattened list of {act_name, section, source_pdf_path} used |
| `confidence_score` | Score node | Internal-only, heuristic, never serialized into the user-facing response |
| `abstain` | Retrieve/Score node | Boolean — true if retrieval coverage is too thin to answer safely |

---

## Node-by-node behavior

### 1. `classify_formulation` — 0 LLM calls
- Fixed yes/no gate tree (see formulation-classification doc), rendered as buttons in the UI — no freeform text parsing needed, so no model call at any point
- Reads: `pending_clarification`; writes: `formulation_category` once resolved, or the next `pending_clarification` if not
- This node is re-entered once per user turn until the tree resolves — it's a short loop, not a single pass
- Conditional edge: resolved → `route_jurisdiction`; not resolved → return question, wait for next turn

### 2. `route_jurisdiction` — 0 LLM calls
- Pure routing logic on `jurisdiction_mode`
- Conditional edge: `india` → national retrieve only; `international` → international retrieve only; `both` → fan out to both retrieve paths in parallel

### 3. `retrieve` — 0 generation LLM calls (embedding-model call only)
- Runs once per active jurisdiction (once or twice depending on mode, never more)
- Queries only the correct Chroma collection, biased by `formulation_category`
- Writes `retrieved_chunks_national` and/or `retrieved_chunks_international`
- If coverage is too thin: sets `abstain = true`, short-circuits straight to `log_and_serve` with an "insufficient corpus coverage" response — skips `generate` and `score_confidence` entirely, saving the call

### 4. `generate` — 1 call per active jurisdiction (the only generation calls in the graph)
- Reads: `retrieved_chunks_national` and/or `retrieved_chunks_international`, `formulation_category`
- Runs once per active jurisdiction, each call seeing **only that jurisdiction's retrieved chunks** — never both in one context window
- In `both` mode this means two calls, fired in parallel (not sequential) to keep latency close to the single-jurisdiction case — the cost goes up by one call, but only in `both` mode, and it removes the leakage risk of a shared context entirely rather than relying on output-schema discipline to prevent it
- Each call independently produces its jurisdiction's six-field disclosure object; the two are combined into `disclosure_draft = {national: {...}, international: {...}}` only after both calls return, never blended during generation
- Writes: `disclosure_draft`, `citations`

### 5. `score_confidence` — 0 LLM calls
- Purely heuristic, computed from data already in state: average top-k retrieval similarity, chunk count, and how many of the six disclosure fields resolved to non-empty values
- Writes `confidence_score`
- Deliberately not a second LLM self-eval pass — cheaper, though less nuanced; revisit only if this proves too crude in testing

### 6. `log_and_serve` — 0 LLM calls
- Persists `confidence_score` and full state to the internal log store (for eval/refinement)
- Strips `confidence_score` and all internal fields before building the API response — only `disclosure_draft`, `citations`, and `standing_disclaimer` go out

---

## Call budget summary

| Query type | Embedding calls | Generation LLM calls |
|---|---|---|
| Single jurisdiction (india or international) | 1 | 1 |
| Both jurisdictions | 2 (one per collection) | 2 (isolated per jurisdiction, run in parallel — no shared context, zero leakage risk) |
| Abstained (insufficient coverage) | 1–2 | 0 |

The two-call cost in `both` mode is deliberate, not an oversight: a single combined call risks blending national and international claims through shared context even with a strict output schema, which directly violates the "answers never conflated" requirement. Isolating the calls removes that risk structurally instead of hoping the schema holds. Parallel execution keeps latency close to the single-jurisdiction case even though token/API cost is roughly doubled for `both`-mode queries specifically.

---

## Still open
- Exact heuristic formula/weights for `confidence_score` — deliberately deferred, revisit later

## Resolved
- Session state is held server-side, keyed by a session id — the frontend does not resend the full conversation each turn. This avoids state pile-up during the multi-turn classification loop and keeps request payloads small.
