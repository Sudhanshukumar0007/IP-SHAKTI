# IP-SAKTI Sahayak — ingestion pipeline

Designed to keep generation-LLM calls at zero during ingestion (BGE-M3 embedding only), and to not bet the MVP timeline on scraping inconsistent government sites — manual ingestion is a first-class path, not a fallback.

---

## Source registry (driver table, separate from Chroma)

| Field | Purpose |
|---|---|
| `source_id`, `act_name`, `jurisdiction` | Identity |
| `fetch_method` | `scrape` \| `manual` |
| `url` (if scrape) | Where to pull from |
| `last_content_hash` | For amendment detection |
| `last_ingested_date` | Freshness tracking |

New sources default to `manual` and only get promoted to `scrape` once a site's structure is confirmed stable enough to automate reliably — most official Indian sources (TKDL, IP India, India Code, treaty texts) don't have clean APIs and aren't worth automating under hackathon time pressure until proven stable.

---

## Pipeline stages (Celery chain, RabbitMQ as broker)

### 1. Fetch — `fetch_task`
- `scrape` sources: Celery task pulls the PDF/HTML from `url`
- `manual` sources: a PDF + metadata sidecar (act_name, jurisdiction, section boundaries) is dropped into a landing folder; a filesystem-watch or trigger endpoint kicks off the same chain from here
- Celery retry with backoff on transient failures

### 2. Parse & chunk — `chunk_task` (0 LLM calls)
- Rule-based, section/article-aware splitting (regex on section headers) — not naive fixed-size or semantic-LLM chunking
- This is what keeps `section_or_article` metadata accurate, which citation correctness depends on directly
- Keeps ingestion cost at zero generation calls, consistent with the rest of the system design

### 3. Embed & store — `embed_task`
- BGE-M3 embeds each chunk
- Upserts into the correct Chroma collection (`ip_sakti_national` or `ip_sakti_international`) using the existing chunk metadata schema: `chunk_id`, `jurisdiction`, `act_name`, `source_type`, `section_or_article`, `version`, `last_verified_date`, `source_pdf_path`, `related_refs`

### 4. Registry update — `registry_task`
- Writes/updates the verify-this-act entry (PDF path, version, ingested date) in the same pass

---

## Amendment detection

- Celery beat runs a periodic job against every `scrape`-type source: re-fetch, hash the content, compare to `last_content_hash`
- Hash changed → re-run the full chain, bump `version`, keep the old PDF under a versioned filename rather than overwriting — preserves an audit trail
- `manual` sources have no automated detection — this is a genuine gap for now, relies on someone noticing an amendment and re-dropping the file. Flagged explicitly rather than assumed away.

## Failure handling

- Retry with backoff on `fetch_task` for transient network/site issues
- Chains that exhaust retries land in a dead-letter queue for manual review — never silently dropped

## Idempotency

- Dedupe on `(act_name, jurisdiction, version)` before writing new chunks — re-running a chain for an unchanged source should not create duplicate entries in Chroma or the registry
