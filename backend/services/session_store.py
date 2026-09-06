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
import time
from typing import Optional

from graph.state import AgentState
from config import settings


import os
import json
import logging

_SESSIONS_FILE = os.path.join(os.path.dirname(__file__), "..", ".sessions.json")

# Store tuple of (last_accessed_timestamp, state)
_sessions: dict[str, tuple[float, AgentState]] = {}

def _load_sessions() -> None:
    global _sessions
    if os.path.exists(_SESSIONS_FILE):
        try:
            with open(_SESSIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _sessions = {k: (v[0], v[1]) for k, v in data.items()}
        except Exception as e:
            logging.error(f"Failed to load sessions: {e}")
            _sessions = {}

def _save_sessions() -> None:
    try:
        with open(_SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(_sessions, f)
    except Exception as e:
        logging.error(f"Failed to save sessions: {e}")

_load_sessions()

def _cleanup_expired_sessions() -> None:
    now = time.time()
    expired = [
        sid for sid, (timestamp, _) in _sessions.items()
        if now - timestamp > settings.SESSION_TTL_SECONDS
    ]
    if expired:
        for sid in expired:
            _sessions.pop(sid, None)
        _save_sessions()

def create_session(
    jurisdiction_mode: str = "national",
    language: str = "en",
) -> tuple[str, AgentState]:
    """Create a new blank session. Returns (session_id, initial_state)."""
    _cleanup_expired_sessions()
    session_id = str(uuid.uuid4())
    state: AgentState = {
        "session_id": session_id,
        "raw_query": "",
        "search_query": "",
        "query_rewritten": False,
        "language": language,
        "jurisdiction_mode": jurisdiction_mode,
        "query_intent": None,                 # set by detect_intent node
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
        "live_evidence": [],
        "execution_trace": [],
        "connector_used": False,
        "connector_status": "skipped",
    }
    _sessions[session_id] = (time.time(), state)
    _save_sessions()
    return session_id, state


def get_session(session_id: str) -> Optional[AgentState]:
    if session_id in _sessions:
        timestamp, state = _sessions[session_id]
        if time.time() - timestamp > settings.SESSION_TTL_SECONDS:
            _sessions.pop(session_id, None)
            return None
        _sessions[session_id] = (time.time(), state)
        _save_sessions()
        return state
    return None


def update_session(session_id: str, state: AgentState) -> None:
    _sessions[session_id] = (time.time(), state)
    _save_sessions()


def delete_session(session_id: str) -> None:
    if _sessions.pop(session_id, None):
        _save_sessions()


def reset_for_new_query(session_id: str, raw_query: str, jurisdiction_mode: str) -> Optional[AgentState]:
    """
    Start a fresh query on an existing session.
    Resets classification, retrieval, and generation state while keeping session_id.
    Called when the user sends a new question (not a clarification answer).
    """
    state = get_session(session_id)
    if state is None:
        return None

    state["raw_query"] = raw_query
    state["search_query"] = raw_query
    state["query_rewritten"] = False
    state["jurisdiction_mode"] = jurisdiction_mode
    state["query_intent"] = None          # reset so detect_intent re-runs
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
    state["live_evidence"] = []
    state["execution_trace"] = []
    state["connector_used"] = False
    state["connector_status"] = "skipped"
    update_session(session_id, state)
    return state
