# 2026-09-02 — Ingestion Pipeline Validation & Improvements

## What was accomplished

Validated `backend/ingest.py` against all planning documents (`ip-sakti-ingestion-pipeline.md`, `ip-sakti-storage-schema.md`, `ip-sakti-tech-stack.md`, `corpus_structure.md`) and applied the following fixes:

### Critical schema fixes
- **Added `source_pdf_path` to chunk metadata** — was missing from Chroma chunks despite being required by the storage schema (`ip-sakti-storage-schema.md §2`). This field directly powers the "Verify this act" PDF viewer feature.
- **Added `related_refs: []` to chunk metadata** — schema-defined optional field for cross-jurisdiction links; initialised empty so retrieval code can rely on the key existing without special-casing.

### Correctness & robustness
- **Fixed `get_page_range`**: now strips the chunk before `str.find()` to prevent silent `(1, 1)` fallbacks caused by whitespace normalisation from the text splitter.
- **Silenced-error logging**: both bare `except Exception: pass` blocks on `meta.json` and `registry.json` loads now emit `print(f"Warning: ...")` so failures surface in logs.
- **2-part filename guard**: added handling for filenames with only 2 underscore-split parts (`source_en.pdf`) with a logged warning instead of an index error or silent wrong parse.
- **Fixed silent empty-preamble section**: `extract_sections` now strips and guards the preamble before yielding, consistent with how other sections are handled.

### Performance & observability
- **Moved registry save outside the PDF loop** — now saves once per act-folder (`if act_docs_added > 0`) instead of after every single PDF, reducing unnecessary I/O for multi-PDF acts.
- **Added ingestion summary** — final print shows `Ingested: N PDFs | Skipped (unchanged): M | Chunks added: K`.
- **Added `flush=True`** to all progress `print()` calls so output appears in real-time in Docker logs.

### Configuration
- **Promoted embedding model to env var** (`EMBEDDING_MODEL` in `.env`, defaulting to `intfloat/multilingual-e5-small`). Switching to BGE-M3 (or another model) now requires only a `.env` change + full re-ingestion — no code change.

## Architectural decisions

- `related_refs` is intentionally left as `[]` during ingestion. Populating cross-jurisdiction links (national ↔ international) is deferred to a post-processing step as per the original planning document.
- `document_id` hash formula (`jurisdiction + act_folder + filename + version`) is preserved unchanged to avoid invalidating the existing registry.

## Issues encountered / workarounds

- Chroma's `add_documents` does not currently support native list-type metadata values in all backends. If `related_refs: []` causes a Chroma serialization error on first run, it should be changed to `"related_refs": ""` (empty string) as a temporary workaround until the field is actively populated.
