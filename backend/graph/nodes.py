"""
LangGraph node implementations — one function per node.

Each node is: (AgentState) -> dict  (partial state update only).

Call budget (per ip-sakti-langgraph-nodes.md):
  classify_formulation  — 0 LLM calls (pure Python gate tree)
  retrieve              — 0 generation calls (embedding model only)
  generate              — 1 Groq call per active jurisdiction
  score_confidence      — 0 LLM calls (heuristic from state data)
  log_and_serve         — 0 LLM calls (SQLite write + state strip)
"""

from __future__ import annotations

import os
import json
import time
from typing import Any, Optional

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from graph.state import AgentState
from services.classifier import classify_step
from services import retriever as retriever_svc
from services.connector import LiveRegistryConnector
import re

# ── LLM config ─────────────────────────────────────────────────────────────────

GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.45"))
# Maximum clarification rounds before the loop fails and the session is closed.
# After this many unanswered or garbled turns, the graph stops asking and returns
# a classification_failed state. Default 3; set MAX_CLARIFICATION_ATTEMPTS in .env to adjust.
MAX_CLARIFICATION_ATTEMPTS: int = int(os.getenv("MAX_CLARIFICATION_ATTEMPTS", "3"))

DISCLOSURE_FIELD_KEYS = [
    "ip_regimes_applicable",
    "patentability_posture",
    "abs_exposure",
    "tkdl_relevance",
    "regulatory_classification",
    "standing_disclaimer",
]


def _get_llm() -> ChatGroq:
    return ChatGroq(
        model=GROQ_MODEL,
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. classify_formulation — 0 LLM calls
# ══════════════════════════════════════════════════════════════════════════════

def classify_formulation(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])
    trace.append("[CLASSIFIER] Checking formulation logic")
    
    answers: list[str] = state.get("formulation_answers") or []
    attempts: int = state.get("clarification_attempts", 0)

    resolved, category, next_question = classify_step(answers)

    if resolved:
        trace.append(f"[CLASSIFIER] formulation resolved -> {category}")
        return {
            "formulation_category": category,
            "pending_clarification": None,
            "clarification_attempts": attempts,
            "execution_trace": trace,
        }

    # Classification loop not yet resolved — increment attempt counter
    attempts += 1

    if attempts >= MAX_CLARIFICATION_ATTEMPTS:
        # Loop exhausted: stop asking, surface a clear failure rather than
        # silently asking a question the user has repeatedly not answered.
        return {
            "formulation_category": "classification_failed",
            "pending_clarification": None,
            "clarification_attempts": attempts,
            "execution_trace": trace,
        }

    # Loop continues — return the next gate question to the frontend
    trace.append("[CLASSIFIER] clarification needed")
    return {
        "formulation_category": None,
        "pending_clarification": next_question,
        "clarification_attempts": attempts,
        "execution_trace": trace,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. retrieve — embedding calls only, 0 generation LLM calls
# ══════════════════════════════════════════════════════════════════════════════

def retrieve(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])
    mode = state["jurisdiction_mode"]
    trace.append(f"[ROUTER] jurisdiction = {mode}")
    trace.append("[RETRIEVER] Fetching legal corpus...")

    query = state["raw_query"]
    category = state.get("formulation_category")

    nat_chunks: list[dict] = []
    int_chunks: list[dict] = []

    if mode in ("national", "both"):
        nat_chunks = retriever_svc.retrieve(query, "national", category)

    if mode in ("international", "both"):
        int_chunks = retriever_svc.retrieve(query, "international", category)

    all_chunks = nat_chunks + int_chunks
    sufficient, reason = retriever_svc.is_sufficient_coverage(all_chunks)
    
    trace.append(f"[RETRIEVER] {len(all_chunks)} legal chunks retrieved")

    return {
        "retrieved_chunks_national": nat_chunks,
        "retrieved_chunks_international": int_chunks,
        "abstain": not sufficient,
        "abstain_reason": reason if not sufficient else None,
        "execution_trace": trace,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. generate — 1 Groq call per active jurisdiction, NEVER blended
# ══════════════════════════════════════════════════════════════════════════════

_DISCLOSURE_SYSTEM = """\
You are IP Sahayak (IP-SHAKTI), a specialist in Intellectual Property law for \
Ayurveda and traditional medicine formulations.

You will receive a user query and retrieved legal text chunks from the \
{jurisdiction} legal corpus ONLY.

You MUST return a single valid JSON object with EXACTLY these six fields. \
Every field is mandatory — if a field genuinely does not apply, write \
"Not applicable to this formulation category" rather than omitting the field.

{{
  "ip_regimes_applicable": "Which of patent / GI / trademark / design / copyright / trade secret / plant-variety realistically apply to this formulation",
  "patentability_posture": "open | barred | conditional — with the specific statutory basis (e.g. Section 3(p) of the Patents Act, or specific treaty article)",
  "abs_exposure": "Whether Biological Diversity Act prior approval is required before any IP filing using an India-sourced biological resource",
  "tkdl_relevance": "Whether the Traditional Knowledge Digital Library is a relevant prior-art or defensive tool for this formulation",
  "regulatory_classification": "Which act / schedule / rule governs manufacturing approval and licensing for this formulation category",
  "standing_disclaimer": "This information is provided for educational purposes only and does not constitute legal advice. Consult a qualified IP attorney for matters of legal consequence."
}}

Regulatory Classification : {formulation_category}
Jurisdiction Corpus        : {jurisdiction}

[LEGAL CORPUS CONTEXT]
Ground every legal claim in the retrieved chunks provided below. If the corpus does not cover a field, state that explicitly — do NOT fabricate a citation or a statutory basis.

[LIVE FACTUAL EVIDENCE]
If live registry evidence is provided below, use it to answer factual queries about current registry status (e.g. pending patents, live trademarks).
IMPORTANT: Do not state a factual record exists unless it is present in the LIVE FACTUAL EVIDENCE. 
Always cite the "Source" and "URL" from the live evidence when using it.

Return ONLY the JSON object. No markdown fences, no preamble, no trailing text.\
"""


def _build_context(chunks: list[dict], live_evidence: list[dict] = None) -> str:
    parts = []
    for c in chunks:
        m = c["metadata"]
        header = (
            f"[{m.get('act_name', 'Unknown Act')} | "
            f"{m.get('section_or_article', 'Unknown Section')} | "
            f"Pages {m.get('page_start', '?')}–{m.get('page_end', '?')} | "
            f"Version: {m.get('version', 'unknown')}]"
        )
        parts.append(f"{header}\n{c['content']}")
    
    context = "\n\n---\n\n".join(parts)
    
    if live_evidence:
        context += "\n\n=== LIVE FACTUAL EVIDENCE ===\n"
        for ev in live_evidence:
            context += f"Source: {ev['source']} (Retrieved: {ev['retrieved_at']})\n"
            context += f"URL: {ev['url']}\n"
            context += f"Title: {ev['title']}\n"
            context += f"Record Evidence:\n{ev['evidence']}\n\n"
            
    return context


def _extract_citations(chunks: list[dict], jurisdiction: str) -> list[dict]:
    """Build Citation dicts from retrieved chunks. Uses document_id — never source_pdf_path."""
    return [
        {
            "document_id": c["document_id"],
            "act_name": c["metadata"].get("act_name", ""),
            "section_or_article": c["metadata"].get("section_or_article", ""),
            "page_start": c["metadata"].get("page_start", 1),
            "page_end": c["metadata"].get("page_end", 1),
            "chunk_id": c["chunk_id"],
            "version": c["metadata"].get("version", ""),
            "jurisdiction": jurisdiction,
        }
        for c in chunks
    ]


def _call_groq(
    query: str,
    formulation_category: str,
    jurisdiction: str,
    chunks: list[dict],
    live_evidence: list[dict] = None,
) -> tuple[dict, list[dict]]:
    """Single Groq call for one jurisdiction. Returns (disclosure_fields, citations)."""
    llm = _get_llm()
    system = _DISCLOSURE_SYSTEM.format(
        jurisdiction=jurisdiction,
        formulation_category=formulation_category,
    )
    context = _build_context(chunks, live_evidence)
    messages = [
        SystemMessage(content=system),
        HumanMessage(
            content=f"User query: {query}\n\nRetrieved context:\n\n{context}"
        ),
    ]

    response = llm.invoke(messages)
    raw: str = response.content.strip()

    # Strip markdown fences defensively
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    try:
        fields: dict = json.loads(raw)
    except json.JSONDecodeError:
        # Structural fallback — better to surface a clear error than crash
        fields = {k: "" for k in DISCLOSURE_FIELD_KEYS}
        fields["ip_regimes_applicable"] = (
            "[Parse error — model returned non-JSON. Raw response logged.]"
        )
        fields["standing_disclaimer"] = (
            "This information is provided for educational purposes only and does "
            "not constitute legal advice. Consult a qualified IP attorney."
        )

    citations = _extract_citations(chunks, jurisdiction)
    return fields, citations


def live_registry_search(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])
    trace.append("[CONNECTOR] Live registry-source discovery initiated")
    
    query = state["raw_query"]
    
    connector = LiveRegistryConnector()
    result = connector.search_registry(query)
    
    evidence = result.get("evidence", [])
    status = result.get("status", "error")
    
    trace.append(f"[CONNECTOR] {len(evidence)} records returned ({status})")
    if evidence:
        trace.append(f"[VALIDATOR] {len(evidence)} records passed source validation")
        
    return {
        "live_evidence": evidence,
        "connector_used": True,
        "connector_status": status,
        "execution_trace": trace,
        "abstain": False,  # Clear the abstain flag so main.py doesn't ignore the answer
        "abstain_reason": None
    }


def generate(state: AgentState) -> dict[str, Any]:
    """
    Run Groq generation for each active jurisdiction in isolation.

    For 'both' mode: two sequential calls, each seeing ONLY its jurisdiction's
    chunks. Results are stored in separate state fields (national_answer /
    international_answer) — they are NEVER merged in this node.
    """
    query = state["raw_query"]
    category = state.get("formulation_category") or "unknown"
    mode = state["jurisdiction_mode"]
    calls = state.get("llm_calls_made", 0)

    nat_answer: Optional[dict] = None
    int_answer: Optional[dict] = None
    nat_citations: list[dict] = []
    int_citations: list[dict] = []
    live_ev = state.get("live_evidence", [])

    trace = state.get("execution_trace", [])
    trace.append("[GENERATOR] Response synthesis started")

    if mode in ("national", "both"):
        nat_answer, nat_citations = _call_groq(
            query, category, "national", state["retrieved_chunks_national"], live_ev
        )
        calls += 1

    if mode in ("international", "both"):
        int_answer, int_citations = _call_groq(
            query, category, "international", state["retrieved_chunks_international"], live_ev
        )
        calls += 1
        
    trace.append("[GENERATOR] Response synthesized")

    return {
        "national_answer": nat_answer,
        "international_answer": int_answer,
        "national_citations": nat_citations,
        "international_citations": int_citations,
        "llm_calls_made": calls,
        "execution_trace": trace,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. score_confidence — 0 LLM calls, heuristic from state data
# ══════════════════════════════════════════════════════════════════════════════

def _fill_rate(answer: Optional[dict]) -> float:
    if not answer:
        return 0.0
    filled = sum(
        1
        for k in DISCLOSURE_FIELD_KEYS
        if answer.get(k)
        and not answer[k].lower().startswith("not applicable")
        and not answer[k].lower().startswith("[parse error")
        and len(answer[k]) > 5
    )
    return round(filled / len(DISCLOSURE_FIELD_KEYS), 4)


def score_confidence(state: AgentState) -> dict[str, Any]:
    """
    Heuristic confidence score from retrieval signals already in state.

    Deliberately NOT a second LLM call. Logged as components so thresholds
    can be tuned empirically. NEVER returned to the frontend.

    Components:
      max_similarity         — strength of the best match
      mean_similarity        — overall retrieval quality
      relevant_chunk_count   — chunks above the threshold
      disclosure_fill_rate   — fraction of the 6 fields with substantive content

    Composite:  0.5 × max_sim + 0.3 × mean_sim + 0.2 × fill_rate
    (weights are a starting point, not a calibrated probability)
    """
    nat = state.get("retrieved_chunks_national") or []
    intl = state.get("retrieved_chunks_international") or []
    all_chunks = nat + intl

    if not all_chunks:
        return {"confidence_components": {}, "confidence_score": 0.0}

    sims = [c["similarity"] for c in all_chunks]
    max_sim = round(max(sims), 4)
    mean_sim = round(sum(sims) / len(sims), 4)
    relevant_count = sum(1 for s in sims if s >= SIMILARITY_THRESHOLD)

    mode = state["jurisdiction_mode"]
    if mode == "both":
        fill = round(
            (_fill_rate(state.get("national_answer")) +
             _fill_rate(state.get("international_answer"))) / 2,
            4,
        )
    elif mode == "national":
        fill = _fill_rate(state.get("national_answer"))
    else:
        fill = _fill_rate(state.get("international_answer"))

    score = round(0.5 * max_sim + 0.3 * mean_sim + 0.2 * fill, 4)

    components = {
        "max_similarity": max_sim,
        "mean_similarity": mean_sim,
        "relevant_chunk_count": relevant_count,
        "disclosure_fill_rate": fill,
    }

    return {"confidence_components": components, "confidence_score": score}


# ══════════════════════════════════════════════════════════════════════════════
# 5. log_and_serve — 0 LLM calls
# ══════════════════════════════════════════════════════════════════════════════

def log_and_serve(state: AgentState) -> dict[str, Any]:
    """
    Compute final latency, persist to SQLite query log, return latency update.
    The API response is built in main.py from the final state — confidence_score
    and all internal fields are stripped there before being sent to the frontend.
    """
    from services.query_log import log_query

    start = state.get("start_time")
    latency = round((time.time() - start) * 1000, 1) if start else None

    final_state = {**state, "latency_ms": latency}
    log_query(final_state)

    return {"latency_ms": latency}
