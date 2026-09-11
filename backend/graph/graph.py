"""
Compiled LangGraph StateGraph for IP-SHAKTI.

Flow:
                     [START]
                        │
                  detect_intent          ← rule-based, 0 LLM calls
                        │                  informational? → skip Q&A tree, go to retrieve
         ┌──────────────┴──────────────┐
         │                             │
  (informational)              (classification / unknown)
         │                             │
       retrieve              auto_classify + classify_formulation
         │                             │
     [continue]         ┌──────────────┼──────────────┐
                        │              │              │
                (classification    (resolved)  (needs clarification)
                  _failed)             │              │
                        │          supervisor       [END]
                        │              │
                        │      parallel_worker   ← ALL tasks run concurrently
                        │              │
                        │    evidence_verification
                        │              │
                        │        ┌─────┴──────┐
                        │        │            │
                        │  (verified)     (abstain)
                        │        │            │
                        │     generate      [END]
                        │        │
                        │  score_confidence
                        │        │
                        │   log_and_serve
                        │        │
                        └──────[END]
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    detect_intent,
    auto_classify,
    classify_formulation,
    supervisor,
    parallel_worker,
    evidence_verification,
    live_registry_search,
    generate,
    validate_response,
    score_confidence,
    log_and_serve,
)
from graph.edges import after_intent, after_classify, after_verification, after_validate

# ── Build the graph ────────────────────────────────────────────────────────────

builder: StateGraph = StateGraph(AgentState)

# Nodes
builder.add_node("detect_intent", detect_intent)
builder.add_node("auto_classify", auto_classify)
builder.add_node("classify_formulation", classify_formulation)
builder.add_node("supervisor", supervisor)
builder.add_node("parallel_worker", parallel_worker)   # replaces sequential worker loop
builder.add_node("evidence_verification", evidence_verification)
builder.add_node("live_registry_search", live_registry_search)
builder.add_node("generate", generate)
builder.add_node("validate_response", validate_response)
builder.add_node("score_confidence", score_confidence)
builder.add_node("log_and_serve", log_and_serve)

# Entry point: intent gate runs first (free), then keyword matcher, then gate tree
builder.set_entry_point("detect_intent")
builder.add_conditional_edges(
    "detect_intent",
    after_intent,
    {
        "supervisor": "supervisor",        # informational → skip Q&A, go straight to supervisor
        "auto_classify": "auto_classify",  # classification/unknown → normal path
    },
)
builder.add_edge("auto_classify", "classify_formulation")

# classify_formulation → three outcomes
builder.add_conditional_edges(
    "classify_formulation",
    after_classify,
    {
        "supervisor": "supervisor",               # classification resolved → supervisor
        "__end__": END,                       # needs clarification → END this turn
        "classification_failed": END,         # loop exhausted → END with failure state
    },
)

# Supervisor → parallel_worker (single node, all tasks concurrent, no loop)
builder.add_edge("supervisor", "parallel_worker")
builder.add_edge("parallel_worker", "evidence_verification")

# evidence_verification → generate or abstain short-circuit
builder.add_conditional_edges(
    "evidence_verification",
    after_verification,
    {
        "live_registry_search": "live_registry_search",
        "generate": "generate",
        "log_and_serve": "log_and_serve",     # abstain → skip generate & score
    },
)
builder.add_edge("live_registry_search", "generate")
builder.add_edge("generate", "validate_response")

builder.add_conditional_edges(
    "validate_response",
    after_validate,
    {
        "generate": "generate",
        "score_confidence": "score_confidence",
    },
)

builder.add_edge("score_confidence", "log_and_serve")
builder.add_edge("log_and_serve", END)

# ── Compile ────────────────────────────────────────────────────────────────────

graph = builder.compile()
