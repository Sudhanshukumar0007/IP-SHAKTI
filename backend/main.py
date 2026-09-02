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
from typing import Optional, Any

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

from graph.graph import graph as langgraph_app
from services import session_store, query_log
from services.retriever import lookup_document, lookup_by_act_name

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
    allow_origins=["*"],
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
    jurisdiction_mode: str = "national"   # "national" | "international" | "both"
    language: str = "en"


class CreateSessionResponse(BaseModel):
    session_id: str
    jurisdiction_mode: str
    language: str


class ChatRequest(BaseModel):
    session_id: str
    message: str                          # new query OR "yes"/"no" clarification answer
    jurisdiction_mode: Optional[str] = None  # if provided, updates the session


class ClarificationResponse(BaseModel):
    type: str = "clarification"
    question: str
    question_index: int
    clarification_history: list


class CitationModel(BaseModel):
    document_id: str
    act_name: str
    section_or_article: str
    page_start: int
    page_end: int
    chunk_id: str
    version: str
    jurisdiction: str


class AnswerResponse(BaseModel):
    type: str = "answer"
    jurisdiction_mode: str
    formulation_category: str
    national_answer: Optional[dict] = None
    international_answer: Optional[dict] = None
    national_citations: list[CitationModel] = []
    international_citations: list[CitationModel] = []
    abstained: bool = False
    abstain_reason: Optional[str] = None
    execution_trace: list[str] = []
    live_evidence: list[dict] = []



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

    # Optionally update jurisdiction_mode if the frontend sends a new one
    if req.jurisdiction_mode and req.jurisdiction_mode in ("national", "international", "both"):
        state["jurisdiction_mode"] = req.jurisdiction_mode

    if _is_clarification_answer(req.message, state):
        # Append gate answer + record in clarification_history
        question_asked = state["pending_clarification"]
        state["formulation_answers"] = list(state.get("formulation_answers") or []) + [
            req.message.strip().lower()
        ]
        history = list(state.get("clarification_history") or [])
        history.append({"question": question_asked, "answer": req.message.strip().lower()})
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
    result_state: dict = langgraph_app.invoke(state)

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

    # Case 2: abstained — return abstain notice (no answer, no internal score)
    if result_state.get("abstain"):
        return AnswerResponse(
            type="answer",
            jurisdiction_mode=result_state.get("jurisdiction_mode", ""),
            formulation_category=result_state.get("formulation_category") or "unknown",
            abstained=True,
            abstain_reason=result_state.get("abstain_reason"),
            execution_trace=result_state.get("execution_trace", []),
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
def serve_pdf(document_id: str) -> FileResponse:
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

    return FileResponse(
        path=abs_path,
        media_type="application/pdf",
        filename=os.path.basename(abs_path),
    )


@app.get("/eval/summary")
def eval_summary() -> dict:
    """
    Internal-only endpoint. Aggregates the query log into:
    abstention rate, average confidence, latency, per-jurisdiction/category/language counts.
    Not user-facing — for team evaluation and submission evidence.
    """
    return query_log.get_summary()


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "service": "IP-SHAKTI"}
