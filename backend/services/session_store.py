"""
In-memory server-side session store.

State is held server-side, keyed by session_id (UUID).
The frontend only sends session_id + the current message — it never resends
the full conversation history, which keeps request payloads small and avoids
state pile-up during the multi-turn classification loop.

MVP: plain dict. Replace with Redis for production.
Note: sessions are not garbage-collected in this MVP implementation.
"""

from __future__ import annotations

import uuid
from typing import Optional

from graph.state import AgentState


_sessions: dict[str, AgentState] = {}


def create_session(
    jurisdiction_mode: str = "national",
    language: str = "en",
) -> tuple[str, AgentState]:
    """Create a new blank session. Returns (session_id, initial_state)."""
    session_id = str(uuid.uuid4())
    state: AgentState = {
        "session_id": session_id,
        "raw_query": "",
        "language": language,
        "jurisdiction_mode": jurisdiction_mode,
        "formulation_answers": [],
        "clarification_history": [],
        "pending_clarification": None,
        "clarification_attempts": 0,
        "formulation_category": None,
        "retrieved_chunks_national": [],
        "retrieved_chunks_international": [],
        "national_answer": None,
        "international_answer": None,
        "national_citations": [],
        "international_citations": [],
        "confidence_components": {},
        "confidence_score": 0.0,
        "abstain": False,
        "abstain_reason": None,
        "llm_calls_made": 0,
        "latency_ms": None,
        "start_time": None,
    }
    _sessions[session_id] = state
    return session_id, state


def get_session(session_id: str) -> Optional[AgentState]:
    return _sessions.get(session_id)


def update_session(session_id: str, state: AgentState) -> None:
    _sessions[session_id] = state


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def reset_for_new_query(session_id: str, raw_query: str, jurisdiction_mode: str) -> Optional[AgentState]:
    """
    Start a fresh query on an existing session.
    Resets classification, retrieval, and generation state while keeping session_id.
    Called when the user sends a new question (not a clarification answer).
    """
    state = _sessions.get(session_id)
    if state is None:
        return None

    state["raw_query"] = raw_query
    state["jurisdiction_mode"] = jurisdiction_mode
    state["formulation_answers"] = []
    state["clarification_history"] = []
    state["pending_clarification"] = None
    state["clarification_attempts"] = 0
    state["formulation_category"] = None
    state["retrieved_chunks_national"] = []
    state["retrieved_chunks_international"] = []
    state["national_answer"] = None
    state["international_answer"] = None
    state["national_citations"] = []
    state["international_citations"] = []
    state["confidence_components"] = {}
    state["confidence_score"] = 0.0
    state["abstain"] = False
    state["abstain_reason"] = None
    state["llm_calls_made"] = 0
    state["latency_ms"] = None
    state["start_time"] = None
    return state
