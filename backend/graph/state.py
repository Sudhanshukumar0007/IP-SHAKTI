"""
AgentState — the shared state object that flows through every node of the
IP-SHAKTI LangGraph pipeline.

Field conventions
-----------------
- Fields set at entry time are never mutated after they're written.
- Jurisdiction-specific fields are always kept separate (national vs international)
  — they are NEVER blended into one field.
- confidence_score and confidence_components are INTERNAL ONLY and must
  never appear in user-facing API responses.
- clarification_history provides a full audit trail of how the system
  reached its routing decision — important for an IP compliance tool.
"""

from __future__ import annotations
from typing import Optional
from typing_extensions import TypedDict


# ── Sub-record types ───────────────────────────────────────────────────────────

class ClarificationEntry(TypedDict):
    """One Q&A turn during formulation classification."""
    question: str
    answer: str          # "yes" | "no"


class ChunkResult(TypedDict):
    """A retrieved chunk with its provenance and similarity score."""
    chunk_id: str
    document_id: str     # stable hash from ingest.py — key for /verify-act lookup
    content: str
    metadata: dict
    similarity: float    # 0–1, higher = more relevant (normalised cosine)


class Citation(TypedDict):
    """
    Provenance record for a single chunk used in the generated answer.
    Uses document_id (not source_pdf_path) so the frontend never sees a filesystem path.
    The backend resolves document_id → PDF via the registry at /pdf/{document_id}.
    """
    document_id: str
    act_name: str
    section_or_article: str
    page_start: int
    page_end: int
    chunk_id: str
    version: str
    jurisdiction: str    # "national" | "international"


class DisclosureFields(TypedDict):
    """
    The six mandatory disclosure fields every generated answer must populate.
    A field may legitimately resolve to 'Not applicable to this category'
    but must never be silently omitted.
    """
    ip_regimes_applicable: str
    patentability_posture: str
    abs_exposure: str
    tkdl_relevance: str
    regulatory_classification: str
    standing_disclaimer: str


# ── Main state ─────────────────────────────────────────────────────────────────

class AgentState(TypedDict):

    # ── Entry (set from the incoming request, never mutated mid-graph) ─────────
    session_id: str
    raw_query: str
    language: str                    # e.g. "en", "hi"
    jurisdiction_mode: str           # "national" | "international" | "both"

    # ── Classification audit trail ─────────────────────────────────────────────
    # Preserved separately so we have a full record of how routing was decided.
    formulation_answers: list        # list[str] — "yes"/"no" answers to Q1–Q5 in order
    clarification_history: list      # list[ClarificationEntry] — full Q&A pairs
    pending_clarification: Optional[str]  # next gate question to show the user, or None
    clarification_attempts: int            # how many times we've returned a clarification question
    formulation_category: Optional[str]   # resolved leaf enum, or None until resolved
                                           # special value: "classification_failed" after max attempts

    # ── Retrieval — jurisdiction-isolated, never merged ────────────────────────
    retrieved_chunks_national: list       # list[ChunkResult]
    retrieved_chunks_international: list  # list[ChunkResult]

    # ── Generation — kept separate per jurisdiction, NEVER blended ─────────────
    # This structural separation (not just a prompt instruction) makes
    # cross-jurisdiction conflation impossible by construction.
    national_answer: Optional[dict]       # DisclosureFields | None
    international_answer: Optional[dict]  # DisclosureFields | None
    national_citations: list              # list[Citation]
    international_citations: list         # list[Citation]

    # ── Confidence (INTERNAL ONLY — stripped before any API response) ──────────
    # Log all components separately so evaluation can tune thresholds empirically.
    confidence_components: dict           # {max_similarity, mean_similarity, relevant_chunk_count, disclosure_fill_rate}
    confidence_score: float               # heuristic composite — NOT a calibrated probability
    abstain: bool
    abstain_reason: Optional[str]

    # ── Live Connector Agentic Pipeline ────────────────────────────────────────
    live_evidence: list                   # list[dict] with source, url, evidence, etc.
    execution_trace: list                 # list[str] actual system events
    connector_used: bool                  
    connector_status: str                 # "skipped" | "success" | "no_results" | "error"

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    llm_calls_made: int
    latency_ms: Optional[float]
    start_time: Optional[float]           # time.time() at request entry, for latency calc

