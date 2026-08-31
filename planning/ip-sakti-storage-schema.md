# IP-SAKTI Sahayak — storage schema

Architecture-only doc, no code yet. Covers: collection design, chunk metadata, the "Both" toggle retrieval behavior, the verify-this-act registry, and the on-disk layout for original sources.

---

## 1. Collections

Two Chroma collections, each holding embedded chunks for one jurisdiction only. No chunk ever lives in both.

- `ip_sakti_national` — Patents Act + 2024 Rules, GI, Trade Marks, Designs, Copyright, Plant-Variety regimes, Biological Diversity Act (2023 amendment + 2024 Rules), Drugs and Cosmetics Act, Drugs and Magic Remedies Act, FSSAI Ayurveda-Aahar regs
- `ip_sakti_international` — TRIPS, CBD + Nagoya Protocol, WIPO GRATK Treaty, PCT, Madrid System, Hague System, Budapest Treaty, herbal-product market-access regimes

### Toggle → retrieval behavior

| Toggle state | Collections queried | Answer structure |
|---|---|---|
| India | `ip_sakti_national` only | Single answer, national citations only |
| International | `ip_sakti_international` only | Single answer, international citations only |
| Both | Both, queried separately (two retrieval calls, not one merged call) | Answer rendered as two clearly labeled sections — "Under Indian law" / "Under international regimes" — never blended into one unified claim |

The "Both" mode is the one place conflation risk actually shows up — the retrieval stays separate (two calls), but it's the generation step that has to be constrained to keep the two sets apart in the output. This is a prompt/graph-structure requirement to flag when we design the LangGraph generation node: it must produce two attributed sections, not one paragraph synthesizing both.

---

## 2. Chunk metadata schema

Every chunk in either collection carries the same fields:

| Field | Type | Description |
|---|---|---|
| `chunk_id` | string | Unique id for this chunk |
| `jurisdiction` | enum: `national` \| `international` | Determines which collection the chunk lives in — set once, never mixed |
| `act_name` | string | e.g. "Biological Diversity Act, 2002" |
| `source_type` | enum: `statute` \| `rule` \| `treaty` \| `pharmacopoeial_standard` \| `registry_record` \| `case_law` | |
| `section_or_article` | string | e.g. "Section 3(p)" or "Article 27.3(b)" |
| `version` | string | Amendment year/version this text reflects, e.g. "2024 Rules" |
| `last_verified_date` | date | When this chunk was last checked against the live source — the mechanism for detecting staleness later |
| `source_pdf_path` | string | Path into the disk store (see §4) — feeds "verify this act" directly |
| `related_refs` | list of chunk_id, optional | Points to a corresponding chunk in the *other* collection when a national rule implements an international obligation (e.g. a Biological Diversity Act provision implementing Nagoya). Surfaced as a "see also" citation, never merged into the primary claim. |

---

## 3. Verify-this-act registry

Kept separate from Chroma — this is a simple lookup, not something that needs semantic search. A flat table (JSON or SQLite; pick at build time) keyed by `act_name` (+ `jurisdiction`, since names could collide across regimes):

| Field | Type | Description |
|---|---|---|
| `act_name` | string | Primary key, paired with jurisdiction |
| `jurisdiction` | enum: `national` \| `international` | |
| `source_pdf_path` | string | Local path to the archived official PDF |
| `official_url` | string, optional | Original source URL, kept for reference/re-verification, not depended on live |
| `version` | string | Matches the `version` field on chunks citing this act |
| `ingested_date` | date | When this act was added/last refreshed in the registry |

Built once at ingestion time, read-only at query time — clicking "verify this act" is a direct lookup + serve-the-PDF, never a live fetch.

---

## 4. On-disk layout (MVP)

```
/corpus
  /national
    /biological-diversity-act-2002/
      source.pdf
      2024-rules-amendment.pdf
    /patents-act-1970/
      source.pdf
      2024-rules.pdf
    ...
  /international
    /trips/
      source.pdf
    /nagoya-protocol/
      source.pdf
    ...
```

One folder per act/treaty, named to match `act_name` in the registry. Chunk-level `source_pdf_path` values point into this structure. This also gives a natural place to drop new amendment PDFs without touching the vector DB until the next ingestion pass.

---

## Open questions for this layer
- JSON vs SQLite for the verify-this-act registry (SQLite gives you queryability for free if the registry grows; JSON is simpler for a hackathon MVP)
- Whether `related_refs` needs to be bidirectional (national → international *and* international → national) or one-directional is enough for the MVP
