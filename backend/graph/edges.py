"""
Conditional edge functions for the LangGraph StateGraph.

These are pure functions: (AgentState) -> str (next node name).
They contain no side-effects and no LLM calls.
"""

from __future__ import annotations

import re
from graph.state import AgentState


def after_intent(state: AgentState) -> str:
    """
    After detect_intent, route based on query_intent:

    - "informational" → "supervisor"
      Skip the five-gate classification Q&A entirely.
      formulation_category is already set to "informational" so after_classify
      will route onward correctly.

    - "classification" | "unknown" (or anything else) → "auto_classify"
      Proceed through the standard keyword-match → gate tree path.
    """
    intent = state.get("query_intent", "unknown")

    # If detect_intent already resolved to informational, skip classification
    if intent == "informational":
        return "supervisor"

    # For explicit classification requests AND ambiguous queries, run the
    # keyword matcher first — it may shortcut the Q&A for obvious products.
    return "auto_classify"


def after_classify(state: AgentState) -> str:
    """
    After classify_formulation, route to one of three outcomes:

    1. "classification_failed"
       clarification_attempts >= MAX without resolution.
       → END this turn; main.py will return a failure response.

    2. "supervisor"
       formulation_category is a valid leaf enum.
       → proceed to supervisor to decompose the query into tasks.

    3. "__end__" (needs clarification)
       pending_clarification is set; formulation_category is None.
       → END this turn; main.py returns the next gate question to the frontend.
       On the next /chat call, main.py appends the answer and re-invokes the graph —
       this is the "loop" at the conversation level.
    """
    category = state.get("formulation_category")

    if category == "classification_failed":
        return "classification_failed"

    if category is not None:
        return "supervisor"

    # pending_clarification is set — end this turn, frontend asks the user
    return "__end__"


def after_worker(state: AgentState) -> str:
    """
    After a worker executes a task, loop back if more tasks remain,
    otherwise proceed to evidence verification.
    """
    idx = state.get("worker_index", 0)
    tasks = state.get("research_tasks", [])
    
    if idx < len(tasks):
        return "worker"
    return "evidence_verification"


def after_verification(state: AgentState) -> str:
    """
    After evidence_verification:
      - Overall status is ABSTAIN → skip generate & score, go to log_and_serve
      - Coverage sufficient (VERIFIED or PARTIAL):
          - Query requires live factual data? → live_registry_search
          - Otherwise → generate
    """
    if state.get("abstain"):
        return "log_and_serve"
        
    query = state.get("raw_query", "").lower()
    
    # Deterministic heuristic for live connector
    live_keywords = [
        "patent", "trademark", "status", "pending", "live", "recent", 
        "registry", "registered", "application", "search"
    ]
    
    requires_live = any(kw in query for kw in live_keywords) and len(query.split()) > 3
    
    if requires_live:
        return "live_registry_search"
        
    return "generate"
