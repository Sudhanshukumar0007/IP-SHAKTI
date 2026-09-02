"""
Conditional edge functions for the LangGraph StateGraph.

These are pure functions: (AgentState) -> str (next node name).
They contain no side-effects and no LLM calls.
"""

from __future__ import annotations

from graph.state import AgentState


def after_classify(state: AgentState) -> str:
    """
    After classify_formulation, route to one of three outcomes:

    1. "classification_failed"
       clarification_attempts >= MAX without resolution.
       → END this turn; main.py will return a failure response.

    2. "retrieve"
       formulation_category is a valid leaf enum.
       → proceed to retrieve (jurisdiction routing handled inside retrieve node).

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
        return "retrieve"

    # pending_clarification is set — end this turn, frontend asks the user
    return "__end__"



import re

def after_retrieve(state: AgentState) -> str:
    """
    After retrieve:
      - Coverage insufficient (abstain=True) → skip generate & score, go to log_and_serve
      - Coverage sufficient:
          - Query requires live factual data? → live_registry_search
          - Otherwise → generate
    """
    query = state.get("raw_query", "").lower()
    
    # Deterministic heuristic for live connector
    live_keywords = [
        "patent", "trademark", "status", "pending", "live", "recent", 
        "registry", "registered", "application", "search"
    ]
    
    requires_live = any(kw in query for kw in live_keywords) and len(query.split()) > 3
    
    if requires_live:
        return "live_registry_search"
        
    if state.get("abstain"):
        return "log_and_serve"
        
    return "generate"
