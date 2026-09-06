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
from typing import Optional

from langchain_chroma import Chroma

# Using fastembed directly via a minimal shim to avoid deprecation warnings
# and Pydantic validation issues from langchain-community.
from fastembed import TextEmbedding

class FastEmbedEmbeddings:
    def __init__(self, model_name): self._m = TextEmbedding(model_name)
    def embed_documents(self, texts): return list(self._m.embed(texts))
    def embed_query(self, text): return list(self._m.embed([text]))[0]

# ── Configuration (all tunable via .env without code changes) ──────────────────

CHROMA_DB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")
)
REGISTRY_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "registry.json")
)

EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")

# Abstention thresholds — tune empirically with the evaluation set.
# Lowered from 0.45 → 0.35 and 3 → 1 after observing real evaluation scores
# (max_similarity was 0.4084 on a working query, so 0.45 was too strict).
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.35"))
MIN_RELEVANT_CHUNKS: int = int(os.getenv("MIN_RELEVANT_CHUNKS", "1"))

# Top-k chunks to retrieve per jurisdiction per query
DEFAULT_K: int = int(os.getenv("RETRIEVAL_K", "8"))


# ── Lazy-initialised Chroma handles ───────────────────────────────────────────

_national: Optional[Chroma] = None
_international: Optional[Chroma] = None


def _build_collection(name: str) -> Chroma:
    embeddings = FastEmbedEmbeddings(model_name=EMBEDDING_MODEL)
    return Chroma(
        collection_name=name,
        embedding_function=embeddings,
        persist_directory=CHROMA_DB_DIR,
    )


def _get_national() -> Chroma:
    global _national
    if _national is None:
        _national = _build_collection("ip_sakti_national")
    return _national


def _get_international() -> Chroma:
    global _international
    if _international is None:
        _international = _build_collection("ip_sakti_international")
    return _international


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
    # If no filtering can be applied (either originally empty, or zeroed out by registry check), do open retrieval
    if not primary_acts and not boundary_acts:
        results = collection.similarity_search_with_score(query, k=k)
    else:
        k_primary = min(k, int(k * 0.8)) # e.g. 12 if k=15
        k_boundary = k - k_primary
        
        if primary_acts:
            results.extend(collection.similarity_search_with_score(query, k=k_primary, filter={"act_name": {"$in": list(primary_acts)}}))
            
        if boundary_acts and k_boundary > 0:
            results.extend(collection.similarity_search_with_score(query, k=k_boundary, filter={"act_name": {"$in": list(boundary_acts)}}))

    # Deduplicate by chunk_id and content
    seen_ids = set()
    seen_texts = set()
    unique_results = []
    # Sort results by distance (score is distance in Chroma results initially)
    results.sort(key=lambda x: x[1])
    
    for doc, distance in results:
        chunk_id = doc.metadata.get("chunk_id", "")
        content = doc.page_content.strip()
        
        if chunk_id in seen_ids or content in seen_texts:
            continue
            
        seen_ids.add(chunk_id)
        seen_texts.add(content)
        unique_results.append((doc, distance))

    # Slice to top K overall unique
    unique_results = unique_results[:k]

    chunks: list[dict] = []
    for doc, distance in unique_results:
        DISTANCE_METRIC: str = os.getenv("DISTANCE_METRIC", "l2")
        if DISTANCE_METRIC == "cosine":
            similarity = max(0.0, 1.0 - float(distance) / 2.0)
        else:
            L2_SCALE: float = float(os.getenv("L2_DISTANCE_SCALE", "400.0"))
            similarity = max(0.0, 1.0 - float(distance) / L2_SCALE)

        chunks.append({
            "chunk_id": doc.metadata.get("chunk_id", ""),
            "document_id": doc.metadata.get("document_id", ""),
            "content": doc.page_content,
            "metadata": {
                "act_name": doc.metadata.get("act_name", ""),
                "section_or_article": doc.metadata.get("section_or_article", ""),
                "page_start": doc.metadata.get("page_start", 1),
                "page_end": doc.metadata.get("page_end", 1),
                "version": doc.metadata.get("version", ""),
                "source_type": doc.metadata.get("source_type", ""),
                "jurisdiction": doc.metadata.get("jurisdiction", jurisdiction),
                "language": doc.metadata.get("language", "en"),
                "last_verified_date": doc.metadata.get("last_verified_date", ""),
            },
            "similarity": round(similarity, 4),
        })

    return chunks


# ── Abstention logic ───────────────────────────────────────────────────────────

def is_sufficient_coverage(chunks: list[dict], task_question: str = "") -> tuple[bool, str]:
    """
    Evaluate whether retrieval coverage is sufficient to generate a safe answer.

    Returns (sufficient: bool, reason: str).

    Abstain if ANY of:
      - No chunks retrieved at all.
      - max similarity < SIMILARITY_THRESHOLD (best match is too weak).
      - fewer than MIN_RELEVANT_CHUNKS above SIMILARITY_THRESHOLD
        (not enough grounding even if the best match looks okay).

    This avoids the failure mode of 15 mediocre chunks passing a count check,
    as well as the failure mode of one very good chunk being treated as sufficient.
    """
    if not chunks:
        return False, "No chunks retrieved from the corpus."

    similarities = [c["similarity"] for c in chunks]
    max_sim = max(similarities)
    relevant = [s for s in similarities if s >= SIMILARITY_THRESHOLD]

    if max_sim < SIMILARITY_THRESHOLD:
        return False, (
            f"Corpus coverage insufficient: best match similarity is {max_sim:.3f}, "
            f"below the minimum threshold of {SIMILARITY_THRESHOLD}. "
            "The corpus may not contain this topic — please consult a qualified IP attorney."
        )

    if len(relevant) < MIN_RELEVANT_CHUNKS:
        return False, (
            f"Only {len(relevant)} chunk(s) above the relevance threshold "
            f"({SIMILARITY_THRESHOLD}); need at least {MIN_RELEVANT_CHUNKS} for a "
            "grounded answer. The corpus coverage for this specific question is thin."
        )

    # Task-specific sufficiency (e.g., if task requires case law)
    if "case law" in task_question.lower() or "cases" in task_question.lower() or "judgment" in task_question.lower():
        # Iterate over the actual chunk dictionaries that met the relevance threshold
        relevant_chunks = [c for c in chunks if c["similarity"] >= SIMILARITY_THRESHOLD]
        has_case_law = any(
            "case" in c.get("metadata", {}).get("source_type", "").lower() or 
            "judgment" in c.get("metadata", {}).get("source_type", "").lower() or
            "case" in c.get("metadata", {}).get("act_name", "").lower()
            for c in relevant_chunks
        )
        if not has_case_law:
            return False, "Task requires case law, but no case law was found in the retrieved evidence."

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
