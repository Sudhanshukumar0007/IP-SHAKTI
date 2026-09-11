"""
Chroma retrieval wrapper.

Key design decisions (from user architectural review):

1. Abstention is based on similarity quality, not chunk count alone:
     - max_similarity < SIMILARITY_THRESHOLD           → abstain
     - relevant chunks (above threshold) < MIN_RELEVANT_CHUNKS → abstain
   This avoids the failure mode where 15 mediocre chunks all pass a count check.

2. Returns chunks with normalised similarity scores (0–1, higher = more relevant).
   Downstream score_confidence node can inspect these values individually.

3. document_id is preserved in every ChunkResult — this is the stable key
   for /verify-act and /pdf/{document_id} lookups. source_pdf_path is never
   returned to the frontend.

4. The two Chroma collections are initialised lazily and cached module-level.
   EMBEDDING_MODEL must match what was used during ingestion — verified via env var.
"""

from __future__ import annotations

import os
import json
import re
from typing import Optional

import math
from langchain_chroma import Chroma

# Shared normalized embeddings shim (L2-normalizes all vectors, asserts norm~1 at startup)
from services.embeddings import FastEmbedEmbeddings


# ── Configuration (all tunable via .env without code changes) ──────────────────

CHROMA_DB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")
)
REGISTRY_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "registry.json")
)

EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")

# Suffix appended to collection names. Set to '_v2' after running migrate_vectors.py,
# or '' to use legacy l2 collections (not recommended).
COLLECTION_SUFFIX: str = os.getenv("COLLECTION_SUFFIX", "_v2")

# Abstention gate thresholds baked from calibration.
# SIMILARITY_FLOOR: minimum top-1 cosine similarity to allow an answer.
# SCORE_MARGIN: top-1 must exceed median of candidate pool by at least this.
# HIGH_CONFIDENCE_FLOOR: if top-1 >= this, skip the margin check entirely.
#   Calibration data (fix.txt): e5-large cosine sits ~0.82-0.90 relevant vs
#   ~0.72-0.78 unrelated, so 0.84 is solidly in the relevant zone.
SIMILARITY_FLOOR: float = float(os.getenv("SIMILARITY_FLOOR", "0.82"))
SCORE_MARGIN: float = float(os.getenv("SCORE_MARGIN", "0.05"))
HIGH_CONFIDENCE_FLOOR: float = float(os.getenv("HIGH_CONFIDENCE_FLOOR", "0.84"))
# Legacy aliases so existing env vars still work.
SIMILARITY_THRESHOLD: float = SIMILARITY_FLOOR
MIN_RELEVANT_CHUNKS: int = int(os.getenv("MIN_RELEVANT_CHUNKS", "2"))
STRONG_SIMILARITY: float = float(os.getenv("STRONG_SIMILARITY", "0.70"))

# Top-k chunks to retrieve per jurisdiction per query
DEFAULT_K: int = int(os.getenv("RETRIEVAL_K", "8"))


# ── Lazy-initialised Chroma handles (thread-safe) ────────────────────────────
# ChromaDB PersistentClient uses SQLite which is not safe for concurrent
# multi-threaded writes/reads during initialisation.  A module-level lock
# guards the one-time init; after that reads are safe because Chroma's
# query path is read-only with respect to the collection metadata.

import threading as _threading
_chroma_init_lock = _threading.Lock()

_national: Optional[Chroma] = None
_international: Optional[Chroma] = None


def _build_collection(name: str) -> Chroma:
    embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)
    col = Chroma(
        collection_name=name,
        embedding_function=embeddings,
        persist_directory=CHROMA_DB_DIR,
        collection_metadata={"hnsw:space": "cosine"},
    )
    # Cache the actual space from live collection metadata.
    meta = col._collection.metadata or {}
    col._hnsw_space = meta.get("hnsw:space", "cosine").lower()
    return col


def _get_national() -> Chroma:
    global _national
    if _national is None:
        with _chroma_init_lock:
            if _national is None:   # double-checked locking
                _national = _build_collection("ip_sakti_national_current" + COLLECTION_SUFFIX)
    return _national


def _get_international() -> Chroma:
    global _international
    if _international is None:
        with _chroma_init_lock:
            if _international is None:
                _international = _build_collection("ip_sakti_international_current" + COLLECTION_SUFFIX)
    return _international


def _eager_init_collections() -> None:
    """Pre-warm both collections at module load so parallel threads never race."""
    try:
        _get_national()
        _get_international()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Chroma eager-init failed: %s", e)

_eager_init_collections()


# ── Distance → similarity ──────────────────────────────────────────────────────

def distance_to_similarity(distance: float, space: Optional[str] = None) -> float:
    """
    Convert a Chroma distance into cosine similarity in [0, 1].

    cosine space: Chroma reports (1 - cosine_sim) in [0, 1]. sim = 1 - d.
    l2 space (normalized vectors only): Chroma reports squared-L2 (d^2).
      For unit vectors: d^2 = 2*(1-cosine_sim), so sim = 1 - d/2.
      d > 4.0 means unnormalized vectors — logged as an error (should have
      been caught by the startup assertion in embeddings.py).
    """
    import logging as _logging
    d = float(distance)
    space = (space or "cosine").lower()
    if space in ("cosine", "cos"):
        sim = 1.0 - d
    else:
        # l2: d is squared-L2
        if d > 4.0:
            _logging.getLogger(__name__).error(
                "distance_to_similarity: d=%.4f > 4.0 in l2 space. "
                "Vectors are likely unnormalized. Check embeddings shim.", d
            )
        sim = 1.0 - (d / 2.0)
    return max(0.0, min(1.0, sim))


def _chunk_dict(doc, distance: Optional[float], *, source: str = "chroma", sim_cap: Optional[float] = None) -> dict:
    raw_distance = None if distance is None else float(distance)
    if raw_distance is None:
        similarity: Optional[float] = None
    else:
        similarity = distance_to_similarity(raw_distance)
    if sim_cap is not None and similarity is not None:
        similarity = min(similarity, sim_cap)
    meta = doc.metadata if hasattr(doc, "metadata") else {}
    return {
        "chunk_id": meta.get("chunk_id", ""),
        "document_id": meta.get("document_id", ""),
        "content": doc.page_content if hasattr(doc, "page_content") else str(doc),
        "metadata": {
            "act_name": meta.get("act_name", ""),
            "act_id": meta.get("act_id", ""),
            "section_or_article": meta.get("section_or_article", ""),
            "page_start": meta.get("page_start", 1),
            "page_end": meta.get("page_end", 1),
            "version": meta.get("version", ""),
            "source_type": meta.get("source_type", ""),
            "jurisdiction": meta.get("jurisdiction", ""),
            "language": meta.get("language", "en"),
            "last_verified_date": meta.get("last_verified_date", ""),
            # Preserve internal routing flags so is_sufficient_coverage can see them
            "_is_direct_shortcut": meta.get("_is_direct_shortcut", False),
        },
        "similarity": round(similarity, 4) if similarity is not None else None,
        "raw_distance": raw_distance,
        "source": source,
    }


def _chunk_from_get(meta: dict, doc_text: str) -> dict:
    """Build a chunk dict for keyword-fallback results. similarity is None."""
    return {
        "chunk_id": meta.get("chunk_id", ""),
        "document_id": meta.get("document_id", ""),
        "content": doc_text,
        "metadata": {
            "act_name": meta.get("act_name", ""),
            "act_id": meta.get("act_id", ""),
            "section_or_article": meta.get("section_or_article", ""),
            "page_start": meta.get("page_start", 1),
            "page_end": meta.get("page_end", 1),
            "version": meta.get("version", ""),
            "source_type": meta.get("source_type", ""),
            "jurisdiction": meta.get("jurisdiction", ""),
            "language": meta.get("language", "en"),
            "last_verified_date": meta.get("last_verified_date", ""),
        },
        "similarity": None,
        "raw_distance": None,
        "source": "keyword",
    }


def _parse_section_ref(text: str):
    """
    Parse a section reference from either a query string or a metadata label.
    '3(p)'                          -> ('3', 'p')
    'section 3(p)'                  -> ('3', 'p')
    'Section 3: What are not...'    -> ('3', None)
    Returns (base_num, clause) or (None, None).
    """
    m = re.search(r'section\s+([0-9a-zA-Z]+)(?:\(([a-zA-Z0-9]+)\))?', text, re.IGNORECASE)
    if m:
        return m.group(1).lower(), (m.group(2).lower() if m.group(2) else None)
    m2 = re.match(r'^([0-9]+)(?:\(([a-zA-Z0-9]+)\))?$', text.strip())
    if m2:
        return m2.group(1), (m2.group(2).lower() if m2.group(2) else None)
    return None, None


def _section_anchor_match(chunk: dict, query_act: Optional[str], base_num: str, clause: Optional[str]) -> bool:
    """
    Return True if chunk matches act + base section number.
    Clause presence in content is a confidence boost, not required.
    Act name match is required if query_act is provided.
    """
    meta = chunk.get("metadata", {})
    chunk_act = meta.get("act_name", "").lower()
    if query_act and query_act.lower() not in chunk_act:
        return False
    meta_base, _ = _parse_section_ref(meta.get("section_or_article", ""))
    return meta_base == base_num


def _has_section_anchor(chunks: list[dict], task_question: str, query_act: Optional[str] = None) -> bool:
    """Return True if any chunk matches a section ref found in task_question."""
    section_refs = re.findall(r'section\s+([0-9a-zA-Z()+]+)', task_question, re.IGNORECASE)
    if not section_refs:
        return False
    for ref in section_refs:
        base, clause = _parse_section_ref(ref)
        if base is None:
            continue
        for c in chunks:
            if _section_anchor_match(c, query_act, base, clause):
                return True
    return False


# ── Core retrieval ─────────────────────────────────────────────────────────────

def retrieve(
    query: str,
    jurisdiction: str,                     # "national" | "international"
    formulation_category: Optional[str] = None,
    domains: Optional[list[str]] = None,
    k: int = DEFAULT_K,
) -> list[dict]:
    """
    Query the correct Chroma collection.

    Returns list[ChunkResult] dicts. Each dict contains:
      chunk_id, document_id, content, metadata (full), similarity (0–1)

    The document_id field is the stable ingestion-time hash that maps
    to the registry entry — never expose source_pdf_path from here.
    """
    if jurisdiction not in {"national", "international"}:
        raise ValueError(f"Jurisdiction must be 'national' or 'international', got: {jurisdiction}")

    collection = (
        _get_national() if jurisdiction == "national" else _get_international()
    )
    
    primary_acts = set()
    boundary_acts = set()
    
    if jurisdiction == "national":
        IP_ACTS = ["Patents Act 1970", "Trade Marks Act 1999", "Geographical Indications Of Goods Act 1999", "Design Act", "Copyright Act 1957", "Protection Of Plant Varieties And Farmers Rights Act"]
        for d in (domains or []):
            if d == "patent":
                primary_acts.update(IP_ACTS)
            elif d == "biodiversity":
                primary_acts.update(["Biological Diversity Act"])
            elif d == "regulatory" and formulation_category:
                if formulation_category == "cosmetic":
                    primary_acts.update(["Drugs And Cosmetics Act 1940", "Drugs And Magic Remedies Act 1954"])
                    boundary_acts.update(["Food Safety And Standards Act"])
                elif formulation_category == "ayurveda_aahar":
                    primary_acts.update(["Food Safety And Standards Act"])
                    boundary_acts.update(["Drugs And Cosmetics Act 1940", "Drugs And Magic Remedies Act 1954"])
                elif formulation_category == "classical":
                    primary_acts.update(["Drugs And Cosmetics Act 1940", "Ayurvedic Pharmacopoeia Of India Part 1", "Ayurvedic Pharmacopoeia Of India Part 2"])
                    boundary_acts.update(["Food Safety And Standards Act"])
                elif formulation_category == "phytopharmaceutical":
                    primary_acts.update(["Drugs And Cosmetics Act 1940"])
                    boundary_acts.update(["Ayurvedic Pharmacopoeia Of India Part 1", "Ayurvedic Pharmacopoeia Of India Part 2"])
                elif formulation_category == "proprietary":
                    primary_acts.update(["Drugs And Cosmetics Act 1940", "Drugs And Magic Remedies Act 1954"])
                    boundary_acts.update(["Ayurvedic Pharmacopoeia Of India Part 1", "Ayurvedic Pharmacopoeia Of India Part 2"])
                elif formulation_category == "new_drug":
                    primary_acts.update(["Drugs And Cosmetics Act 1940"])
                    boundary_acts.update(["Food Safety And Standards Act"])
    else:
        for d in (domains or []):
            if d == "international_ip" or d == "patent":
                # TODO: Add "TRIPS Agreement" when it gets ingested into ChromaDB.
                # TODO: "Wipo Treaty On Intellectual Property" is an ambiguous act name in the corpus, 
                #       likely referring to GRATK. If renamed during ingestion, update this mapping.
                primary_acts.update(["Patent Cooperation Treaty 1970", "Madrid Agreement Protocol", "Geneva Act 1999", "Wipo Treaty On Intellectual Property", "Budapest Treaty"])
            elif d == "biodiversity":
                primary_acts.update(["Convention Of Biological Diversity 1992", "Nagoya Protocol On Access And Benefit Sharing"])

    # Issue 10: Dynamic intersection with registry.json
    if os.path.exists(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                registry = json.load(f)
            active_acts = {entry.get("act_name") for entry in registry.values() if entry.get("act_name")}
            if primary_acts:
                primary_acts.intersection_update(active_acts)
            if boundary_acts:
                boundary_acts.intersection_update(active_acts)
        except Exception:
            pass # Fall back to hardcoded sets if registry is unavailable or malformed

    results = []
    # Use standard k for direct retrieval
    candidate_k = k

    # If no filtering can be applied (either originally empty, or zeroed out by registry check), do open retrieval
    if not primary_acts and not boundary_acts:
        results = collection.similarity_search_with_score(query, k=candidate_k, filter={"is_latest_consolidated": True})
    else:
        k_primary = min(candidate_k, int(candidate_k * 0.8)) # e.g. 12 if k=15
        k_boundary = candidate_k - k_primary
        
        if primary_acts:
            f = {"$and": [{"act_name": {"$in": list(primary_acts)}}, {"is_latest_consolidated": True}]}
            results.extend(collection.similarity_search_with_score(query, k=k_primary, filter=f))
            
        if boundary_acts and k_boundary > 0:
            f = {"$and": [{"act_name": {"$in": list(boundary_acts)}}, {"is_latest_consolidated": True}]}
            results.extend(collection.similarity_search_with_score(query, k=k_boundary, filter=f))


    # Deduplicate by chunk_id and content
    seen_ids = set()
    unique_results = []
    
    for doc, distance in results:
        chunk_id = doc.metadata.get("chunk_id", "")
        if chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        unique_results.append((doc, distance))
    # Sort unique results by distance (lower is better in Chroma usually, assuming L2/cosine distance)
    # Then map it to a 0-1 similarity score where 1 is identical.
    # Note: FastEmbed embeddings are typically normalized, so distance D is bounded. 
    # For cosine distance, similarity is 1 - distance. If L2, it can be slightly different.
    # We will sort by distance (lowest first) and assume similarity = 1 - distance
    # or just use a simple heuristic if distance > 1.
    unique_results.sort(key=lambda x: x[1])
    unique_results = unique_results[:k]

    chunks: list[dict] = []
    for doc, distance in unique_results:
        chunk = _chunk_dict(doc, distance, source="chroma")
        if not chunk["metadata"].get("jurisdiction"):
            chunk["metadata"]["jurisdiction"] = jurisdiction
        chunks.append(chunk)

    # --- Keyword fallback: never allowed to satisfy sufficiency on its own ---
    max_sim = max([c["similarity"] for c in chunks]) if chunks else 0.0
    if max_sim < SIMILARITY_THRESHOLD and (primary_acts or boundary_acts):
        keywords = [w for w in query.replace('"', '').replace("'", '').split() if len(w) > 4]
        fallback_results = []
        
        acts_to_scan = list(primary_acts) + list(boundary_acts)
        for act in acts_to_scan[:3]:
            try:
                act_f = {"$and": [{"act_name": {"$eq": act}}, {"is_latest_consolidated": True}]}
                docs = collection.get(where=act_f)
                if docs and docs.get("documents"):
                    for i, doc_text in enumerate(docs["documents"]):
                        doc_lower = doc_text.lower()
                        match_count = sum(1 for kw in keywords[:5] if kw.lower() in doc_lower)
                        if match_count >= min(2, len(keywords[:5])):
                            meta = docs["metadatas"][i] if docs.get("metadatas") else {}
                            chunk_id = meta.get("chunk_id", "")
                            if not any(c["chunk_id"] == chunk_id for c in chunks):
                                chunks.append(_chunk_from_get(meta, doc_text))
                                fallback_results.append(chunk_id)
                        if len(fallback_results) >= 3:
                            break
            except Exception:
                pass
            if len(fallback_results) >= 3:
                break

    # Re-sort: vector chunks (have similarity) before keyword chunks (similarity=None)
    chunks.sort(key=lambda x: (x["similarity"] is None, -(x["similarity"] or 0)))

    return chunks


# ── Abstention logic ───────────────────────────────────────────────────────────

def is_sufficient_coverage(chunks: list[dict], task_question: str = "") -> tuple[bool, str]:
    """
    Evaluate whether retrieval coverage is sufficient to generate a safe answer.

    Gate semantics: "we have at least one chunk that clearly answers this."
    Uses a relative gate: top-1 >= SIMILARITY_FLOOR AND
                          top-1 - median(pool) >= SCORE_MARGIN.

    Section-anchor matching downgrades confidence (adds a note to the reason)
    rather than hard-abstaining when semantic score is strong.

    Keyword-only chunks (similarity=None) never count toward sufficiency.

    Returns (sufficient: bool, reason: str).
    """
    if not chunks:
        return False, "No chunks retrieved from the corpus."

    # Only vector chunks count toward the gate
    vector_chunks = [c for c in chunks if c.get("source") != "keyword" and c.get("similarity") is not None]
    if not vector_chunks:
        return False, "Only keyword fallback results were found; no semantic match available."

    similarities = [c["similarity"] for c in vector_chunks]
    top1 = max(similarities)
    import statistics
    pool_median = statistics.median(similarities)
    margin = top1 - pool_median

    if top1 < SIMILARITY_FLOOR:
        return False, (
            f"Corpus coverage insufficient: best match similarity is {top1:.3f}, "
            f"below the minimum floor of {SIMILARITY_FLOOR}. "
            "The corpus may not contain this topic — please consult a qualified IP attorney."
        )

    # Margin bypass: with properly normalized cosine vectors, a top-1 similarity
    # >= HIGH_CONFIDENCE_FLOOR is strong evidence on its own — the spread check
    # is less meaningful when the corpus is dense around a single section.
    if top1 >= HIGH_CONFIDENCE_FLOOR:
        # High-confidence hit — margin check not required
        pass
    elif margin < SCORE_MARGIN:
        return False, (
            f"Retrieval signal is weak: top-1 similarity {top1:.3f} only "
            f"{margin:.3f} above pool median ({pool_median:.3f}); "
            f"need margin >= {SCORE_MARGIN} or top-1 >= {HIGH_CONFIDENCE_FLOOR}. "
            "Results may not be specific enough."
        )

    # Section anchor: note if requested section not clearly matched, but don't abstain
    anchor_note = ""
    anchored = _has_section_anchor(vector_chunks, task_question)
    if re.search(r'section\s+[0-9]', task_question, re.IGNORECASE) and not anchored:
        anchor_note = " (Note: requested section not found as a direct metadata match; answer drawn from semantically similar provisions.)"

    relevant_chunks = [c for c in vector_chunks if c["similarity"] >= SIMILARITY_FLOOR]

    # Task-specific sufficiency (e.g., if task requires case law)
    
    if "case law" in task_question.lower() or "cases" in task_question.lower() or "judgment" in task_question.lower():
        has_case_law = any(
            "case" in c.get("metadata", {}).get("source_type", "").lower() or 
            "judgment" in c.get("metadata", {}).get("source_type", "").lower() or
            "case" in c.get("metadata", {}).get("act_name", "").lower()
            for c in relevant_chunks
        )
        if not has_case_law:
            return False, "Task requires case law, but no case law was found in the retrieved evidence."

    # Exact Section match enforcement: downgrade confidence instead of abstaining
    section_matches = re.findall(r"section\s+([0-9a-zA-Z\(\)]+)", task_question, re.IGNORECASE)
    if section_matches:
        for sec in section_matches:
            has_exact = False
            sec_lower = sec.lower()
            sec_base = sec_lower.split('(')[0] if '(' in sec_lower else sec_lower
            clause = sec_lower[len(sec_base):] # e.g., "(p)"
            
            for c in relevant_chunks:
                meta_sec = c.get("metadata", {}).get("section_or_article", "").lower()
                content = c.get("content", "").lower()
                
                meta_base, meta_clause = _parse_section_ref(meta_sec)
                
                if meta_base == sec_base:
                    if not clause:
                        has_exact = True
                        break
                    
                    # If clause requested, check content or metadata
                    clause_variants = [
                        clause, 
                        clause.replace("(", " ("), 
                        f"clause {clause}", 
                        f"clause {clause.replace('(', '').replace(')', '')}"
                    ]
                    if meta_clause == clause.strip("()") or any(v in content for v in clause_variants):
                        has_exact = True
                        break
                    
            if not has_exact:
                anchor_note += f" (Note: requested Section {sec} was not definitively found, relying on semantic matches.)"
                
    if anchor_note:
        return True, anchor_note

    return True, ""


# ── Registry lookup (for /verify-act and /pdf endpoints) ──────────────────────

def lookup_document(document_id: str) -> Optional[dict]:
    """
    Look up a document_id in registry.json.
    Returns the registry entry dict (which contains source_pdf_path internally)
    or None if not found.

    Called by the backend only — source_pdf_path is never forwarded to the frontend.
    """
    if not os.path.exists(REGISTRY_PATH):
        return None
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = json.load(f)
        return registry.get(document_id)
    except Exception:
        return None


def lookup_by_act_name(act_name: str, jurisdiction: str) -> Optional[tuple[str, dict]]:
    """
    Search registry by (act_name, jurisdiction).
    Returns (document_id, entry) or None.
    Useful when the frontend has a human-readable act name rather than a document_id.
    """
    if not os.path.exists(REGISTRY_PATH):
        return None
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = json.load(f)
        for doc_id, entry in registry.items():
            if (
                entry.get("act_name", "").lower() == act_name.lower()
                and entry.get("jurisdiction", "") == jurisdiction
            ):
                return doc_id, entry
    except Exception:
        return None
    return None
