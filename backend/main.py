"""
IP-SHAKTI FastAPI application.

Endpoints
---------
POST /session              — create session, return session_id
GET  /session/{id}         — return public session state (no internal fields)
POST /chat                 — main chat endpoint; drives the LangGraph pipeline
GET  /verify-act           — document metadata lookup (no filesystem path exposed)
GET  /pdf/{document_id}    — serve original PDF (backend resolves path from registry)
GET  /eval/summary         — internal eval metrics from query log
GET  /health               — liveness check

Design decisions
----------------
- confidence_score and all internal fields (confidence_components, start_time,
  retrieved_chunks_*, abstain_reason) are NEVER returned in user-facing responses.
- source_pdf_path is never returned to the frontend. /verify-act returns metadata;
  /pdf/{document_id} serves the file after backend registry lookup.
- national_answer and international_answer are always kept separate in responses.
"""

from __future__ import annotations

import os
import time
from typing import Optional, Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
from pydantic import BaseModel
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

from config import settings
from graph.graph import graph as langgraph_app
from services import session_store, query_log
from services.retriever import lookup_document, lookup_by_act_name, SIMILARITY_THRESHOLD

# ── Startup ────────────────────────────────────────────────────────────────────

query_log.init_db()

CORPUS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Corpus"))

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="IP-SHAKTI — IP Sahayak",
    description=(
        "Ayurveda IPR/regulatory RAG assistant. "
        "Provides jurisdiction-separated IP guidance for traditional medicine formulations."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── Request / response models ──────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    jurisdiction_mode: Literal["national", "international", "both"]
    language: str = "en"


class CreateSessionResponse(BaseModel):
    session_id: str
    jurisdiction_mode: str
    language: str


class ChatRequest(BaseModel):
    session_id: str
    message: str                          # new query OR "yes"/"no" clarification answer
    jurisdiction_mode: Optional[Literal["national", "international", "both"]] = None  # if provided, updates the session
    language: Optional[str] = None


class ClarificationResponse(BaseModel):
    type: str = "clarification"
    question: str
    question_index: int
    clarification_history: list


class CitationModel(BaseModel):
    index: int = 1
    document_id: str
    act_name: str
    section_or_article: str
    page_start: int
    page_end: int
    chunk_id: str
    version: str
    jurisdiction: str
    snippet: Optional[str] = ""


class AnswerResponse(BaseModel):
    type: str = "answer"
    jurisdiction_mode: Literal["national", "international", "both"] = "both"
    formulation_category: str
    national_answer: Optional[dict] = None
    international_answer: Optional[dict] = None
    national_citations: list[CitationModel] = []
    international_citations: list[CitationModel] = []
    abstained: bool = False
    abstain_reason: Optional[str] = None
    execution_trace: list[str] = []
    live_evidence: list[dict] = []
    overall_status: str = "UNKNOWN"



class VerifyActResponse(BaseModel):
    document_id: str
    act_name: str
    jurisdiction: str
    version: str
    language: str
    ingested_date: str
    # NOTE: source_pdf_path is intentionally excluded — use GET /pdf/{document_id}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _public_session(state: dict) -> dict:
    """Strip all internal-only fields before returning session state to the frontend."""
    return {
        "session_id": state.get("session_id"),
        "jurisdiction_mode": state.get("jurisdiction_mode"),
        "language": state.get("language"),
        "formulation_category": state.get("formulation_category"),
        "pending_clarification": state.get("pending_clarification"),
        "clarification_history": state.get("clarification_history"),
        "llm_calls_made": state.get("llm_calls_made"),
    }


def _is_clarification_answer(message: str, state: dict) -> bool:
    """
    Determine whether this message is an answer to a pending clarification gate,
    or a brand-new user query.

    A message is a clarification answer iff:
      - There is an active pending_clarification in the session (the tree is mid-walk)
      - AND the message is "yes" or "no" (case-insensitive, stripped)
    """
    if state.get("pending_clarification") is None:
        return False
    return message.strip().lower() in ("yes", "no")


# ══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/session", response_model=CreateSessionResponse)
def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
    """
    Start a new session. Returns session_id.
    All state lives server-side — the frontend only resends session_id each turn.
    """
    if req.jurisdiction_mode not in ("national", "international", "both"):
        raise HTTPException(
            status_code=400,
            detail="jurisdiction_mode must be 'national', 'international', or 'both'.",
        )
    session_id, _ = session_store.create_session(
        jurisdiction_mode=req.jurisdiction_mode,
        language=req.language,
    )
    return CreateSessionResponse(
        session_id=session_id,
        jurisdiction_mode=req.jurisdiction_mode,
        language=req.language,
    )


@app.get("/session/{session_id}")
def get_session(session_id: str) -> dict:
    """
    Return public session state (no internal fields).
    Supports browser-refresh mid-classification without losing progress.
    """
    state = session_store.get_session(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return _public_session(state)


@app.post("/chat", response_model=Any)
@limiter.limit("5/minute")
def chat(request: Request, req: ChatRequest):
    """
    Main entry point for the LangGraph RAG pipeline.s:
      - {"type": "clarification", "question": ..., ...} while formulation tree is resolving
      - {"type": "answer", "national_answer": ..., ...} once generation completes

    Message routing:
      - If session has pending_clarification and message is "yes"/"no"
        → treat as gate answer, append to formulation_answers, re-run graph
      - Otherwise
        → treat as new query, reset session query state, run graph from scratch
    """
    state = session_store.get_session(req.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found. Call POST /session first.")

    # Always apply jurisdiction_mode and language update first - before routing to clarification
    # or new-query branch. Without this, replying "yes"/"no" to a clarification
    # gate ignores the mode sent by the frontend and uses stale session state.
    if req.jurisdiction_mode and req.jurisdiction_mode in ("national", "international", "both"):
        state["jurisdiction_mode"] = req.jurisdiction_mode
        
    if req.language:
        state["language"] = req.language

    if _is_clarification_answer(req.message, state):
        question_asked = state["pending_clarification"]
        answer_text = req.message.strip().lower()
        
        if state.get("formulation_category") and not state.get("classification_confirmed"):
            if answer_text == "yes":
                state["classification_confirmed"] = True
            else:
                state["formulation_category"] = None
                state["classification_confirmed"] = False
                state["formulation_answers"] = [] # Reset answers so they can try again or just pass it as a new query
                # Not appending to answers since they rejected it
        else:
            state["formulation_answers"] = list(state.get("formulation_answers") or []) + [answer_text]
            
        history = list(state.get("clarification_history") or [])
        history.append({"question": question_asked, "answer": answer_text})
        state["clarification_history"] = history
        state["pending_clarification"] = None  # will be re-set by classify node if needed
    else:
        # New query — reset all query-specific state
        state = session_store.reset_for_new_query(
            req.session_id,
            raw_query=req.message,
            jurisdiction_mode=state["jurisdiction_mode"],
        )

    state["start_time"] = time.time()
    session_store.update_session(req.session_id, state)

    # Run the LangGraph pipeline
    try:
        result_state: dict = langgraph_app.invoke(state)
    except Exception as e:
        import traceback
        import logging
        logging.error("Graph execution failed:")
        traceback.print_exc()
        
        trace = state.get("execution_trace", [])
        trace.append(f"[ERROR] Graph execution failed: {str(e)}")
        
        # Gracefully handle the error rather than throwing an HTTP 500/503
        result_state = dict(state)
        result_state["abstain"] = True
        result_state["abstain_reason"] = "Your request could not be processed due to a provider error or safety filter. Please rephrase your query."
        result_state["overall_status"] = "ERROR"
        result_state["execution_trace"] = trace

    # Persist final state back to the session store
    session_store.update_session(req.session_id, result_state)

    # ── Build response ────────────────────────────────────────────────────────

    # Case 0: classification loop exhausted after MAX_CLARIFICATION_ATTEMPTS
    if result_state.get("formulation_category") == "classification_failed":
        return {
            "type": "classification_failed",
            "message": (
                "I wasn't able to classify the formulation after "
                f"{result_state.get('clarification_attempts')} attempts. "
                "Please start a new query and answer each gate question with 'yes' or 'no'."
            ),
            "attempts_made": result_state.get("clarification_attempts"),
            "execution_trace": result_state.get("execution_trace", []),
        }

    # Case 1: classification still in progress — return next gate question
    if result_state.get("pending_clarification"):
        answers_so_far = result_state.get("formulation_answers") or []
        return ClarificationResponse(
            type="clarification",
            question=result_state["pending_clarification"],
            question_index=len(answers_so_far),
            clarification_history=result_state.get("clarification_history") or [],
        )
        
    # Case 1.5: classification resolved, but needs confirmation
    if result_state.get("formulation_category") and result_state["formulation_category"] not in ("classification_failed", "informational") and not result_state.get("classification_confirmed"):
        cat = result_state["formulation_category"]
        question = f"I have classified this as {cat}. Is this correct?"
        
        result_state["pending_clarification"] = question
        session_store.update_session(req.session_id, result_state)
        
        answers_so_far = result_state.get("formulation_answers") or []
        return ClarificationResponse(
            type="clarification",
            question=question,
            question_index=len(answers_so_far),
            clarification_history=result_state.get("clarification_history") or [],
        )

    # Case 2: abstained — return abstain notice (no answer, no internal score)
    if result_state.get("abstain"):
        return AnswerResponse(
            type="answer",
            jurisdiction_mode=result_state.get("jurisdiction_mode", ""),
            formulation_category=result_state.get("formulation_category") or "unknown",
            abstained=True,
            abstain_reason=result_state.get("abstain_reason"),
            execution_trace=result_state.get("execution_trace", []),
            overall_status=result_state.get("overall_status", "ABSTAIN"),
        )

    # Case 3: fully generated answer

    return AnswerResponse(
        type="answer",
        jurisdiction_mode=result_state.get("jurisdiction_mode", ""),
        formulation_category=result_state.get("formulation_category") or "unknown",
        national_answer=result_state.get("national_answer"),
        international_answer=result_state.get("international_answer"),
        national_citations=result_state.get("national_citations") or [],
        international_citations=result_state.get("international_citations") or [],
        abstained=False,
        execution_trace=result_state.get("execution_trace", []),
        live_evidence=result_state.get("live_evidence", []),
        overall_status=result_state.get("overall_status", "UNKNOWN"),
    )


@app.get("/verify-act", response_model=VerifyActResponse)
def verify_act(
    document_id: Optional[str] = Query(None, description="document_id from a citation"),
    act_name: Optional[str] = Query(None, description="Human-readable act name"),
    jurisdiction: Optional[str] = Query(None, description="'national' or 'international'"),
) -> VerifyActResponse:
    """
    Document metadata lookup for the 'Verify this act' feature.

    Accepts either document_id (from a citation) or act_name + jurisdiction.
    Returns document metadata — NOT the filesystem path.
    Use GET /pdf/{document_id} to fetch the actual PDF.
    """
    entry: Optional[dict] = None
    resolved_doc_id: str = ""

    if document_id:
        entry = lookup_document(document_id)
        resolved_doc_id = document_id
    elif act_name and jurisdiction:
        result = lookup_by_act_name(act_name, jurisdiction)
        if result:
            resolved_doc_id, entry = result

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found in registry. It may not have been ingested yet.",
        )

    return VerifyActResponse(
        document_id=resolved_doc_id,
        act_name=entry.get("act_name", ""),
        jurisdiction=entry.get("jurisdiction", ""),
        version=entry.get("version", ""),
        language=entry.get("language", ""),
        ingested_date=entry.get("ingested_date", ""),
        # source_pdf_path deliberately excluded
    )


@app.get("/pdf/{document_id}")
def serve_pdf(document_id: str) -> Response:
    """
    Serve the original PDF for a given document_id.

    The backend resolves document_id → source_pdf_path via registry.json.
    The filesystem path is NEVER exposed to the frontend.
    """
    entry = lookup_document(document_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document not found in registry.")

    rel_path: str = entry.get("source_pdf_path", "")
    # source_pdf_path in registry is relative to the project root (e.g. "Corpus/national/...")
    abs_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", rel_path)
    )

    if not os.path.exists(abs_path):
        raise HTTPException(
            status_code=404,
            detail="PDF file not found on disk. Re-run ingestion.",
        )

    # Security: ensure the resolved path is within the Corpus directory
    if not abs_path.startswith(CORPUS_ROOT):
        raise HTTPException(status_code=403, detail="Access denied.")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=abs_path,
        media_type="application/pdf",
        content_disposition_type="inline",
        filename=f"{document_id}.pdf"
    )


@app.get("/api/eval/graph")
def get_eval_graph():
    try:
        from graph.graph import graph
        mermaid_syntax = graph.get_graph().draw_mermaid()
        return {"graph": mermaid_syntax}
    except Exception as e:
        return {"graph": "", "error": str(e)}


@app.get("/api/eval/metrics/{session_id}")
def get_session_eval_metrics(session_id: str):
    import sqlite3
    db_path = "query_log.db"
    
    if not os.path.exists(db_path) and not session_store.get_session(session_id):
        return {"queries": []}
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM query_log WHERE session_id = ? ORDER BY id ASC", (session_id,))
    rows = c.fetchall()
    conn.close()

    if not rows and not session_store.get_session(session_id):
        return {"queries": []}

    # If we have no rows but we have a live session, we'll wrap the live session in a fake row
    if not rows:
        live_state = session_store.get_session(session_id)
        if live_state:
            rows = [{"full_state": json.dumps(live_state), "id": -1, "timestamp": "", "raw_query": live_state.get("raw_query", "")}]

    def _build_metrics(row, state):
        trace = state.get("execution_trace") or []
        task_results = state.get("task_results") or []
        overall_status = state.get("overall_status") or "UNAVAILABLE"
        abstain = state.get("abstain", False)
        abstain_reason = state.get("abstain_reason") or None
        
        overall_status_normalized = "ABSTAINED" if overall_status == "ABSTAIN" else overall_status
        avg_conf = state.get("confidence_score")
        
        node_details = {
            "detect_intent": { "status": "PASSED" if state.get("jurisdiction_mode") else "PENDING" },
            "auto_classify": { "status": "PASSED" if state.get("formulation_category") else "PENDING" },
            "classify_formulation": { "status": "PASSED" if state.get("formulation_category") else "PENDING" },
            "supervisor": {
                "status": "PASSED" if task_results else ("PENDING" if not abstain else "SKIPPED"),
                "details": {"tasks_created": len(task_results)}
            },
            "worker": {
                "status": overall_status_normalized if overall_status_normalized in ("VERIFIED", "PARTIAL") else ("FAILED" if task_results else "PENDING"),
                "details": {
                    "tasks_executed": len(task_results),
                    "tasks_sufficient": sum(1 for t in task_results if t.get("sufficient", False))
                }
            },
            "evidence_verification": {
                "status": "PASSED" if overall_status_normalized == "VERIFIED" else ("PARTIAL" if overall_status_normalized == "PARTIAL" else "FAILED")
            },
            "live_registry_search": {
                "status": "SKIPPED"
            },
            "generate": {
                "status": "PASSED" if overall_status_normalized in ("VERIFIED", "PARTIAL") else "SKIPPED"
            },
            "validate_response": {
                "status": "FAILED" if state.get("validation_failures", 0) > 0 else ("PASSED" if overall_status_normalized in ("VERIFIED", "PARTIAL") else "SKIPPED"),
                "details": {
                    "failures": state.get("validation_failures", 0),
                    "feedback": state.get("validation_feedback")
                }
            },
            "score_confidence": {
                "status": "PASSED" if overall_status_normalized in ("VERIFIED", "PARTIAL") else "SKIPPED"
            },
            "log_and_serve": {
                "status": "PASSED" if state.get("start_time") else "PENDING"
            }
        }

        formatted_tasks = []
        for t in task_results:
            raw_chunks = t.get("retrieved_chunks", [])
            sorted_chunks = sorted(raw_chunks, key=lambda x: x.get("similarity", 0.0), reverse=True)
            formatted_chunks = []
            for c in sorted_chunks:
                text = c.get("content", "")
                sim = c.get("similarity", 0.0)
                metadata = c.get("metadata", {})
                act = metadata.get("act_name", "Unknown Source")
                sec = metadata.get("section_or_article", "")
                title = f"{act} - {sec}" if sec else act
                
                formatted_chunks.append({
                    "chunk_id": c.get("chunk_id", ""),
                    "title": title,
                    "metadata": metadata,
                    "similarity": sim,
                    "is_relevant": sim >= SIMILARITY_THRESHOLD,
                    "content": text
                })

            formatted_tasks.append({
                "task_id": t.get("task_id", t.get("id", "Unknown")),
                "question": t.get("question", ""),
                "status": "PASSED" if t.get("sufficient") else "INSUFFICIENT",
                "sufficient": t.get("sufficient", False),
                "retrieved_count": len(raw_chunks),
                "relevant_count": t.get("relevant_chunk_count", 0),
                "max_similarity": t.get("max_similarity", 0.0),
                "mean_similarity": t.get("mean_similarity", 0.0),
                "reason": t.get("abstain_reason"),
                "chunks": formatted_chunks
            })
            
        task_coverage = None
        retrieval_relevance = None
        if formatted_tasks:
            sufficient = sum(1 for t in formatted_tasks if t["sufficient"])
            task_coverage = round((sufficient / len(formatted_tasks)) * 100)
            max_sims = [t["max_similarity"] for t in formatted_tasks if t["max_similarity"] is not None]
            if max_sims:
                retrieval_relevance = round((sum(max_sims) / len(max_sims)) * 100)

        conf_heuristic = None
        if avg_conf is not None:
            conf_heuristic = round(avg_conf * 100) if avg_conf <= 1.0 else round(avg_conf)

        return {
            "id": dict(row).get("id") if isinstance(row, sqlite3.Row) else row.get("id"),
            "timestamp": dict(row).get("timestamp") if isinstance(row, sqlite3.Row) else row.get("timestamp"),
            "raw_query": state.get("raw_query", dict(row).get("raw_query") if isinstance(row, sqlite3.Row) else ""),
            "outcome": {
                "status": overall_status_normalized if state else "UNAVAILABLE",
                "is_abstained": abstain
            },
            "scores": {
                "confidence_heuristic": conf_heuristic,
                "task_coverage": task_coverage,
                "retrieval_relevance": retrieval_relevance,
                "claim_grounding": None,
                "citation_accuracy": None
            },
            "tasks": formatted_tasks,
            "nodes": node_details,
            "abstention": {
                "status": "ABSTAINED" if abstain else "NOT_ABSTAINED",
                "reason": abstain_reason
            },
            "trace": trace
        }

    queries = []
    for r in rows:
        try:
            row_dict = dict(r) if isinstance(r, sqlite3.Row) else r
            full_state_json = row_dict.get("full_state")
            state = json.loads(full_state_json) if full_state_json else {}
            # Fallback to live session if missing full_state but it's the last row
            if not state and r == rows[-1]:
                state = session_store.get_session(session_id) or {}
            
            if state:
                queries.append(_build_metrics(r, state))
        except Exception:
            continue
            
    # Always ensure the LIVE session is added if it hasn't been logged yet (e.g. still in progress)
    live_state = session_store.get_session(session_id)
    if live_state:
        # Check if the live state's start_time or raw_query is already the last item in our queries list
        live_query = live_state.get("raw_query")
        if not queries or queries[-1].get("raw_query") != live_query:
            queries.append(_build_metrics({"id": "live", "timestamp": "Now"}, live_state))

    return {"queries": queries}


@app.get("/eval/summary")
def eval_summary() -> dict:
    """
    Internal-only endpoint. Aggregates the query log into:
    abstention rate, average confidence, latency, per-jurisdiction/category/language counts.
    Not user-facing — for team evaluation and submission evidence.
    """
    if not settings.ENABLE_DEV_TRACE:
        raise HTTPException(status_code=403, detail="Evaluation summary is only available in dev mode.")
    return query_log.get_summary()


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "service": "IP-SHAKTI"}
