"""
Compiled LangGraph StateGraph for IP-SHAKTI.

Flow:
                     [START]
                        │
              classify_formulation
                        │
         ┌──────────────┼──────────────┐
         │              │              │
  (classification    (resolved)  (needs clarification)
    _failed)             │              │
         │            retrieve       [END] ← return pending_clarification to frontend;
         │               │               user answers → next /chat call re-invokes graph
         │        ┌──────┴───────┐       (this re-invocation IS the clarification loop)
         │        │              │
         │   (sufficient)   (abstain)
         │        │              │
         │     generate    log_and_serve
         │        │              │
         │  score_confidence   [END]
         │        │
         │   log_and_serve
         │        │
         └──────[END]  ← classification_failed also routes here
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    classify_formulation,
    retrieve,
    live_registry_search,
    generate,
    score_confidence,
    log_and_serve,
)
from graph.edges import after_classify, after_retrieve

# ── Build the graph ────────────────────────────────────────────────────────────

builder: StateGraph = StateGraph(AgentState)

# Nodes
builder.add_node("classify_formulation", classify_formulation)
builder.add_node("retrieve", retrieve)
builder.add_node("live_registry_search", live_registry_search)
builder.add_node("generate", generate)
builder.add_node("score_confidence", score_confidence)
builder.add_node("log_and_serve", log_and_serve)

# Entry point
builder.set_entry_point("classify_formulation")

# classify_formulation → three outcomes
builder.add_conditional_edges(
    "classify_formulation",
    after_classify,
    {
        "retrieve": "retrieve",               # classification resolved → retrieve
        "__end__": END,                       # needs clarification → END this turn
        "classification_failed": END,         # loop exhausted → END with failure state
    },
)

# retrieve → generate or abstain short-circuit
builder.add_conditional_edges(
    "retrieve",
    after_retrieve,
    {
        "live_registry_search": "live_registry_search",
        "generate": "generate",
        "log_and_serve": "log_and_serve",     # abstain → skip generate & score
    },
)

builder.add_edge("live_registry_search", "generate")
builder.add_edge("generate", "score_confidence")
builder.add_edge("score_confidence", "log_and_serve")
builder.add_edge("log_and_serve", END)

# ── Compile ────────────────────────────────────────────────────────────────────

graph = builder.compile()
