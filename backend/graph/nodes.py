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
import hashlib
import logging
import concurrent.futures
from typing import Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

def is_rate_limit(exception: Exception) -> bool:
    err_str = str(exception).lower()
    if "400" in err_str or "json_validate_failed" in err_str:
        return False
    return "429" in err_str or "rate limit" in err_str or "too many requests" in err_str

retry_429 = retry(
    retry=retry_if_exception(is_rate_limit),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8),
    reraise=True
)

from graph.state import AgentState
from services.classifier import classify_step, question_at_index
from services import retriever as retriever_svc
from services.connector import LiveRegistryConnector
from services import llm_pool
from services import mongo_store
from services.llm_pool import parse_json_robust, call_json_with_fallback, record_failure, next_active_key
from services.mongo_store import cache_get, cache_set
import re

logger = logging.getLogger("graph.nodes")

# ── LLM config ─────────────────────────────────────────────────────────────────

SIMILARITY_THRESHOLD: float = retriever_svc.SIMILARITY_THRESHOLD
MAX_CLARIFICATION_ATTEMPTS: int = int(os.getenv("MAX_CLARIFICATION_ATTEMPTS", "2"))

DISCLOSURE_FIELD_KEYS = [
    "ip_regimes_applicable",
    "patentability_posture",
    "abs_exposure",
    "tkdl_relevance",
    "regulatory_classification",
    "standing_disclaimer",
]

_BLANKET_REFUSAL = "insufficient evidence to provide a conclusive answer"

from langchain_core.language_models.chat_models import BaseChatModel

def _get_llm(json_mode: bool = False, model_override: str = None, task_type: str = "heavy") -> BaseChatModel:
    """
    task_type:
      heavy  — Groq (generation)
      fast   — Gemini 3 Flash for classify/expansion; Groq fallback
      light  — Gemini 3 Flash for validator semantic layer
    """
    if task_type in ("fast", "light"):
        # Callers that need a LangChain chat model still get Groq; Gemini is
        # invoked via llm_pool.invoke_gemini_* for extraction tasks.
        llm, _ = llm_pool.get_groq_llm(json_mode=json_mode, model_override=model_override)
        return llm
    llm, _ = llm_pool.get_groq_llm(json_mode=json_mode, model_override=model_override)
    return llm


def _parse_json_robust(raw: str, trace: list, context: str) -> Any:
    return parse_json_robust(raw, trace, context)


# ══════════════════════════════════════════════════════════════════════════════
# 0. detect_intent — 0 LLM calls, rule-based query routing gate
#
#    Runs BEFORE auto_classify. Separates two fundamentally different query
#    types that require different pipeline paths:
#
#    INFORMATIONAL ("what does Section 3(p) say?", "explain the Patents Act")
#       → skip the five-gate classification Q&A entirely
#       → pre-set formulation_category = "informational"
#       → route directly to retrieve → generate
#
#    CLASSIFICATION ("can I patent my chyawanprash formulation?")
#       → proceed through auto_classify → classify_formulation → Q&A tree
#
#    Without this gate every query enters the Q&A tree, which means:
#      (a) informational queries waste 1–5 clarification turns
#      (b) a wrong answer could be a retrieval problem OR a routing problem —
#          impossible to distinguish from the output alone.
# ══════════════════════════════════════════════════════════════════════════════

# Phrases that strongly indicate a plain informational / lookup query.
# Checked as substrings against the lowercased, stripped query.
_INFORMATIONAL_PATTERNS: list[str] = [
    # "what does … say / mean / provide / state"
    "what does",
    "what do",
    # Direct section/article lookups
    "section ",
    "article ",
    "rule ",
    "schedule ",
    # Definitions and explanations
    "what is",
    "what are",
    "define ",
    "definition of",
    "explain ",
    "tell me about",
    "describe ",
    "how does",
    "how do",
    # Requirements / procedure lookups
    "requirements for",
    "procedure for",
    "process for",
    "steps for",
    "what are the conditions",
    "what nba",
    # Act / treaty / law lookups
    "under the patents act",
    "under the trademarks act",
    "under the designs act",
    "under the geographical indications",
    "under the biodiversity act",
    "under the drugs and cosmetics",
    "under trips",
    "under the cbd",
    # Comparison queries
    "difference between",
    "distinguish between",
    "compare ",
    # IP regime lookups that aren't product-classification questions
    "what protection",
    "what ip",
    "which ip",
    "can i get a patent",
    "can i register",
    "how to file",
    "how to register",
    "filing fee",
    "time limit",
    "validity of",
    "duration of",
    "term of",
    # Relevance/applicability lookups (e.g. T1: "Is TKDL relevant for protecting our formulation?")
    "is tkdl",
    "is tkdl relevant",
    "tkdl relevant",
    "relevant for protecting",
    # Hindi script patterns — common informational query endings
    # H1: "पेटेंट अधिनियम की धारा 3 क्या कहती है?" → "kya kahti hai" / "kya kahta hai"
    "क्या कहती है",
    "क्या कहता है",
    "क्या है",
    "धारा ",          # "dhara" = section
    "अनुच्छेद ",      # "anuchched" = article
    "अधिनियम ",       # "adhiniyam" = act
    "क्या बताता है",
    "समझाइए",         # "samjhaiye" = explain
    "बताइए",          # "bataiye" = tell me
]

# Phrases that strongly indicate the user is asking to *classify* a product.
# These take priority — if both pattern sets match, classification wins.
_CLASSIFICATION_PATTERNS: list[str] = [
    "classify",
    "classification",
    "which category",
    "what category",
    "is it a",
    "is this a",
    "should i classify",
    "how should i classify",
    "type of formulation",
    "kind of formulation",
    "formulation type",
]


def detect_intent(state: AgentState) -> dict[str, Any]:
    """
    Zero-cost intent gate: classify the user's query as informational or
    product-classification before any other node runs.

    Returns a partial state update with:
      - query_intent: "informational" | "classification" | "unknown"
      - formulation_category: "informational" if informational (bypasses Q&A)
      - execution_trace: updated

    If the session already has a pending clarification in progress, the intent
    gate is skipped — we're mid-classification and must continue.
    """
    trace = state.get("execution_trace", [])

    # Don't re-run during a clarification loop
    if state.get("pending_clarification") or state.get("formulation_answers"):
        return {}

    query = (state.get("raw_query") or "").strip().lower()

    if not query:
        return {"query_intent": "unknown", "execution_trace": trace}

    # Classification signals take priority (user is explicitly asking to classify)
    if any(pat in query for pat in _CLASSIFICATION_PATTERNS):
        trace.append("[INTENT] Query classified as: product-classification request")
        return {
            "query_intent": "classification",
            "execution_trace": trace,
        }

    # Informational signals — route straight to retrieve, bypass Q&A tree
    if any(pat in query for pat in _INFORMATIONAL_PATTERNS):
        trace.append(
            "[INTENT] Query classified as: informational lookup → "
            "skipping classification Q&A, routing to retrieve"
        )
        return {
            "query_intent": "informational",
            # Pre-set category so after_classify routes to "retrieve" immediately
            "formulation_category": "informational",
            "pending_clarification": None,
            "clarification_attempts": 0,
            "execution_trace": trace,
        }

    # Ambiguous — fall through to auto_classify heuristics
    trace.append("[INTENT] Query intent ambiguous — proceeding to keyword classifier")
    return {
        "query_intent": "unknown",
        "execution_trace": trace,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1a. auto_classify — 0 LLM calls, pure Python keyword matching
#     Detects strong product-type signals in the raw query and pre-fills the
#     gate answers so obvious queries skip the clarification Q&A entirely.
#     Falls through to the Q&A loop when the query is ambiguous.
# ══════════════════════════════════════════════════════════════════════════════

_CLASSIFIER_SYSTEM = """\
You are an expert intent and formulation classifier for IP-SHAKTI.
First, determine if the user's query is about a specific product/formulation (e.g. asking to classify it, patent it, or determine its category) or if it is purely an informational question about IP law/procedures.
If it is purely informational (e.g. "what is a compulsory license", "how long is a patent valid"), return:
{"is_formulation_query": false, "answers": []}

CRITICAL: If the user provides a specific product, hypothetical scenario, or formulation (e.g., "I've isolated a novel compound from Neem", "my new chyawanprash", "this tablet"), it MUST be classified as a formulation query (`is_formulation_query`: true), even if they ask about the "regulatory path" or "IP path".

If it is about a formulation, extract the answers to 5 specific gate questions.
Return a JSON object with a single key "answers" containing an array of exactly 5 strings ("yes", "no", or "unknown").
Example: {"is_formulation_query": true, "answers": ["yes", "no", "unknown", "unknown", "unknown"]}
Do not guess. If the query does not explicitly or clearly imply the answer, output "unknown".

Q1: Is this formulation exclusively for external use (e.g., a cream, lotion, or hair oil) making no therapeutic or disease-curing claims?
Q2: Is this product consumed strictly as a food or dietary supplement (e.g., Ayurveda-Aahar) with no therapeutic claims, and it is NOT a modified classical Ayurvedic drug or proprietary medicine?
Q3: Does this formulation and its manufacturing method exactly match an authoritative First-Schedule classical text (e.g., Ayurvedic Formulary of India) with absolutely NO modifications to ingredients, ratios, or delivery methods?
Q4: Is this a purified, standardised extract or fraction from a single plant source, standardised to a defined active moiety (i.e., a Phytopharmaceutical)?
Q5: Does this formulation deviate from classical texts (e.g., modified ratio, new delivery method) but still follow Ayurvedic principles (Proprietary Ayurvedic Medicine), with NO new clinical safety or efficacy data generated?
"""

@retry_429
def auto_classify(state: AgentState) -> dict[str, Any]:
    """
    Pre-pass: infer formulation category from the raw query using an LLM.
    Extract answers to the 5 gate questions. If the LLM is unsure, it leaves the gate as 'unknown'.
    """
    trace = state.get("execution_trace", [])

    # Skip if detect_intent already resolved the category (informational route)
    if state.get("query_intent") == "informational":
        return {"execution_trace": trace}

    # Skip on clarification turns — user answers are already in formulation_answers
    if state.get("formulation_answers"):
        return {}

    trace.append("[CLASSIFIER] Extracting gate answers from query")
    
    # Short-circuit: if the query is extremely sparse (< 6 meaningful words), the LLM
    # will return all-unknown answers anyway — skip the call and let classify_formulation
    # ask Q1 directly. Saves one Groq call per genuinely ambiguous short query.
    word_count = len((state.get("raw_query") or "").split())
    if word_count < 6:
        trace.append("[CLASSIFIER] Query too short for confident gate inference — skipping LLM pre-pass")
        return {"execution_trace": trace}

    # Use Gemini 3 Flash for extraction; Groq only as fallback.
    parsed = llm_pool.invoke_gemini_json(
        prompt=state.get("raw_query", ""),
        system=_CLASSIFIER_SYSTEM,
    )
    if parsed is None:
        llm = _get_llm(json_mode=True, task_type="fast")
        messages = [
            SystemMessage(content=_CLASSIFIER_SYSTEM),
            HumanMessage(content=state.get("raw_query", ""))
        ]
        response = llm.invoke(messages)
        parsed = _parse_json_robust(response.content, trace, "CLASSIFIER")
    
    if isinstance(parsed, dict):
        if not parsed.get("is_formulation_query", True):
            trace.append("[CLASSIFIER] LLM detected query is purely informational. Bypassing formulation gates.")
            return {
                "query_intent": "informational",
                "formulation_category": "informational",
                "pending_clarification": None,
                "clarification_attempts": 0,
                "execution_trace": trace,
            }
        parsed = parsed.get("answers", [])
    elif isinstance(parsed, list):
        pass # Handle case where LLM just returns the list
    else:
        parsed = []

    if isinstance(parsed, list) and len(parsed) == 5:
        raw_answers = parsed
    else:
        if parsed is not None:
            trace.append(f"[CLASSIFIER] Warning: expected array of 5 answers but got: {parsed}")
        raw_answers = []

    extracted = []
    # Strict fallback validation for Issue 6
    if len(raw_answers) == 5:
        for ans in raw_answers:
            val = str(ans).strip().lower()
            if val in ("yes", "no", "unknown"):
                extracted.append(val)
            else:
                trace.append(f"[CLASSIFIER] LLM hallucinated invalid answer '{val}'. Falling back to deterministic gate.")
                extracted = []
                break
    else:
        trace.append(f"[CLASSIFIER] LLM returned {len(raw_answers)} answers instead of 5. Falling back to deterministic gate.")
        extracted = []

    # Only resolve sequentially up to the first 'unknown'
    valid_prefix = []
    for val in extracted:
        if val in ("yes", "no"):
            valid_prefix.append(val)
        else:
            break
            
    if not valid_prefix:
        return {"execution_trace": trace}

    from services.classifier import classify_step
    resolved, category, _ = classify_step(valid_prefix)

    if resolved:
        trace.append(f"[CLASSIFIER] formulation resolved -> {category}")
        return {
            "formulation_answers": valid_prefix,
            "formulation_category": category,
            "pending_clarification": None,
            "clarification_attempts": 0,
            "execution_trace": trace,
        }

    # Pre-filled answers up to the first unknown
    return {
        "formulation_answers": valid_prefix,
        "execution_trace": trace,
    }



# ══════════════════════════════════════════════════════════════════════════════
# 1b. classify_formulation — 0 LLM calls (gate tree walk)
#     Runs after auto_classify. If auto_classify already resolved the category,
#     this node completes in one step with no questions asked.
# ══════════════════════════════════════════════════════════════════════════════

@retry_429
def classify_formulation(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])

    # If auto_classify already resolved the category, we're done — skip Q&A
    if state.get("formulation_category") and state["formulation_category"] not in (None, "classification_failed"):
        return {"execution_trace": trace}

    answers: list[str] = state.get("formulation_answers") or []
    attempts: int = state.get("clarification_attempts", 0)

    calls = state.get("llm_calls_made", 0)
    
    # Retrieval-backed check for Q3 (Classical Text Match)
    if len(answers) == 2:
        trace.append("[CLASSIFIER] Performing retrieval-backed check for Q3 (Classical Text Match)")
        chunks = retriever_svc.retrieve(
            query=state.get("raw_query", ""),
            jurisdiction="national",
            domains=["regulatory", "patent"],
            k=5
        )
        
        if chunks:
            context = "\n\n".join([c["content"] for c in chunks])
            q3_prompt = f"""
            Does the following formulation query exactly match any of the classical Ayurvedic formulations described in the provided texts?
            Query: {state.get("raw_query", "")}
            
            Classical Texts:
            {context}
            
            Answer ONLY "yes", "no", or "unknown". 
            If it's a proprietary mix or mentions ingredients not in the text, answer "no". 
            If the text clearly describes this exact formulation, answer "yes". 
            If unsure, answer "unknown".
            """
            response = (llm_pool.invoke_gemini_text(q3_prompt) or "").strip().lower()
            if not response:
                llm = _get_llm(task_type="fast")
                response = llm.invoke([HumanMessage(content=q3_prompt)]).content.strip().lower()
            calls += 1
            trace.append(f"[CLASSIFIER] Q3 retrieval check returned: {response}")
            
            if response in ("yes", "no"):
                answers.append(response)

    try:
        resolved, category, next_question = classify_step(answers)
    except ValueError as e:
        attempts += 1
        trace.append(f"[CLASSIFIER] Invalid gate answer ({e}); attempt {attempts}/{MAX_CLARIFICATION_ATTEMPTS}")
        if attempts >= MAX_CLARIFICATION_ATTEMPTS:
            trace.append("[CLASSIFIER] Max invalid answers — defaulting to proprietary")
            return {
                "formulation_category": "proprietary",
                "pending_clarification": None,
                "clarification_attempts": attempts,
                "execution_trace": trace,
                "formulation_answers": answers,
                "llm_calls_made": calls,
            }
        nxt = question_at_index(len(answers)) or "Please answer yes or no."
        return {
            "formulation_category": None,
            "pending_clarification": nxt,
            "clarification_attempts": attempts,
            "execution_trace": trace,
            "formulation_answers": answers,
            "llm_calls_made": calls,
        }

    if resolved:
        trace.append(f"[CLASSIFIER] formulation resolved -> {category}")
        return {
            "formulation_category": category,
            "pending_clarification": None,
            "clarification_attempts": attempts,
            "execution_trace": trace,
            "formulation_answers": answers,
            "llm_calls_made": calls,
        }

    trace.append("[CLASSIFIER] clarification needed")
    return {
        "formulation_category": None,
        "pending_clarification": next_question,
        "clarification_attempts": attempts,
        "execution_trace": trace,
        "formulation_answers": answers,
        "llm_calls_made": calls,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. supervisor — 1 LLM call to decompose query into tasks
# ══════════════════════════════════════════════════════════════════════════════



_SUPERVISOR_SYSTEM = """\
You are the Lead Researcher for IP-SHAKTI.
Decompose the user's complex IP and regulatory query into the minimum number of independent research tasks necessary to answer the query, subject to a maximum of 6 tasks.

If the user's query is inappropriate, violates safety guidelines, or you must refuse the request, you can express this by setting the "status" field to "cannot_process" and providing a "reason".

Return ONLY a JSON object matching this schema:
{
  "status": "ok" | "cannot_process",
  "reason": "If status is cannot_process, state why. Otherwise omit or set to empty.",
  "tasks": [
    {
      "id": "T1",
      "question": "Concise, keyword-heavy search query (e.g., 'criteria for novelty inventive step industrial applicability patent')",
      "domains": ["regulatory", "patent", "biodiversity", "international_ip"],
      "jurisdiction": "national|international",
      "priority": "high|medium|low"
    }
  ]
}

Ensure you specify "national" or "international" for the jurisdiction correctly based on the domain (e.g., Patents Act is national, WIPO is international).
The "domains" field must be an array containing one or more of the allowed domain strings. Use multiple domains if a question spans across regimes (e.g., both biodiversity and patent).
CRITICAL: If the user query mentions herbs, plants, natural ingredients, or Ayurveda (e.g. turmeric, aloe vera, neem), you MUST generate at least one task explicitly searching for "Traditional Knowledge patentability exception Patents Act 1970 Section 3(p)" and another searching for "Biological Diversity Act requirements access to biological resources". Do not just search for the specific plant name, as legal texts use generalized terms.
CRITICAL: If a user asks about a bare section number (e.g. "Section 3(p)") in the context of patentability, you MUST explicitly include "Patents Act 1970" in the question field unless another Act is named.
CRITICAL: The "question" field is passed directly to a semantic vector database. It MUST be a concise string of relevant legal keywords (e.g., 'novelty inventive step section 2(1)(j)'). DO NOT use conversational sentences like 'Is the compound patentable?'.
No markdown formatting, just the raw JSON object.
"""

@retry_429
def supervisor(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])

    # ── Decomposition Cache Check ───────────────────────────────────────────
    raw_query = state.get("raw_query", "")
    jurisdiction = state.get("jurisdiction_mode", "both")
    cache_key = hashlib.sha1(f"{raw_query.strip().lower()}|{jurisdiction}".encode()).hexdigest()

    cached = cache_get("decomposition_cache", cache_key)
    if cached and isinstance(cached, dict) and cached.get("tasks"):
        trace.append(f"[SUPERVISOR] Decomposition cache hit ({cache_key[:8]}). {len(cached['tasks'])} tasks.")
        calls = state.get("llm_calls_made", 0)
        return {
            "research_tasks": cached["tasks"],
            "worker_index": 0,
            "task_results": [],
            "llm_calls_made": calls,
            "execution_trace": trace,
        }
    # ─────────────────────────────────────────────────────────────────────────

    trace.append("[SUPERVISOR] Decomposing query into independent research tasks...")
    
    mode = state.get("jurisdiction_mode", "both")
    llm = _get_llm(json_mode=True, task_type="fast")
    messages = [
        SystemMessage(content=_SUPERVISOR_SYSTEM),
        HumanMessage(content=f"Original Query: {state['raw_query']}\nFormulation Category: {state.get('formulation_category', 'unknown')}\nUser requested jurisdiction: {mode}")
    ]
    
    response = llm.invoke(messages)
    parsed = _parse_json_robust(response.content, trace, "SUPERVISOR")
    
    if isinstance(parsed, dict) and parsed.get("status") == "cannot_process":
        trace.append(f"[SUPERVISOR] Refused to process: {parsed.get('reason')}")
        calls = state.get("llm_calls_made", 0) + 1
        return {
            "abstain": True,
            "abstain_reason": parsed.get("reason", "Cannot process request"),
            "execution_trace": trace,
            "overall_status": "ABSTAIN",
            "research_tasks": [],
            "llm_calls_made": calls
        }
    
    if isinstance(parsed, dict) and "tasks" in parsed:
        parsed = parsed["tasks"]
    elif isinstance(parsed, dict) and len(parsed) == 1 and "status" not in parsed:
        parsed = list(parsed.values())[0]
        
    tasks = parsed if isinstance(parsed, list) else []
        
    valid_tasks = []
    task_results = []
    
    ALLOWED_DOMAINS = {"regulatory", "patent", "biodiversity", "international_ip"}
    
    for i, t in enumerate(tasks):
        if not isinstance(t, dict): continue
        if not t.get("question") or not t.get("jurisdiction"): continue
        
        t["id"] = t.get("id", f"T{i+1}")
        tj = t.get("jurisdiction", "national").lower()
        
        if tj in ["national", "india"]:
            tj = "national"
        elif tj in ["international", "global"]:
            tj = "international"
        else:
            trace.append(f"[SUPERVISOR] Task {t['id']} skipped: unrecognized jurisdiction '{tj}'")
            task_results.append({
                "task_id": t["id"],
                "question": t.get("question", ""),
                "jurisdiction": tj,
                "domains": t.get("domains", []),
                "retrieved_chunks": [],
                "sufficient": False,
                "abstain_reason": f"Task skipped because the LLM assigned an unrecognized jurisdiction '{tj}'."
            })
            continue
            
        t["jurisdiction"] = tj
        
        if mode != "both" and tj != mode:
            trace.append(f"[SUPERVISOR] Task {t['id']} skipped: jurisdiction '{tj}' excluded by user mode '{mode}'")
            task_results.append({
                "task_id": t["id"],
                "question": t.get("question", ""),
                "jurisdiction": tj,
                "domains": t.get("domains", []),
                "retrieved_chunks": [],
                "sufficient": False,
                "abstain_reason": f"Task skipped because it requires {tj} jurisdiction, but user selected {mode} only."
            })
            continue
            
        raw_domains = t.get("domains", [])
        if isinstance(raw_domains, str):
            raw_domains = [raw_domains]
        if not isinstance(raw_domains, list):
            raw_domains = []
            
        valid_domains = [d for d in raw_domains if d in ALLOWED_DOMAINS]
        if not valid_domains:
            trace.append(f"[SUPERVISOR] Task {t['id']} skipped: invalid or empty domains array.")
            task_results.append({
                "task_id": t["id"],
                "question": t.get("question", ""),
                "jurisdiction": tj,
                "domains": [],
                "retrieved_chunks": [],
                "sufficient": False,
                "abstain_reason": "Task skipped because the LLM failed to assign any valid domain tags."
            })
            continue
        elif len(valid_domains) < len(raw_domains):
            # Explicit design choice: If array is partially valid (e.g. ["patent", "garbage"]),
            # we strip the garbage and proceed with the valid tags, rather than abstaining.
            trace.append(f"[SUPERVISOR] Task {t['id']} had invalid domains stripped. Proceeding with: {valid_domains}")
            
        t["domains"] = valid_domains
        t["priority"] = t.get("priority", "medium")
        valid_tasks.append(t)
        
    if not valid_tasks and not task_results:
        trace.append("[SUPERVISOR] Task decomposition failed or empty, using fallback task.")
        valid_tasks = [{
            "id": "T1",
            "question": state["raw_query"],
            # Deliberate fallback: 'general' is not in ALLOWED_DOMAINS and will fall through to open retrieval.
            "domains": ["general"],
            "jurisdiction": mode if mode != "both" else "national",
            "priority": "high"
        }]
        if mode == "both":
            valid_tasks.append({
                "id": "T2",
                "question": state["raw_query"],
                "domains": ["general"],
                "jurisdiction": "international",
                "priority": "high"
            })
            
    trace.append(f"[SUPERVISOR] Generated {len(valid_tasks)} tasks.")
    calls = state.get("llm_calls_made", 0) + 1
    
    if valid_tasks:
        cache_set("decomposition_cache", cache_key, {"tasks": valid_tasks}, ttl_s=86400)
        trace.append(f"[SUPERVISOR] Cached decomposition for {cache_key[:8]}.")

    return {
        "research_tasks": valid_tasks,
        "worker_index": 0,
        "task_results": task_results,
        "llm_calls_made": calls,
        "execution_trace": trace
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2.0  Parallel worker runner — all tasks execute concurrently
# ══════════════════════════════════════════════════════════════════════════════
import concurrent.futures as _cf
import copy

def _run_single_worker(task: dict, base_state: dict) -> dict:
    """
    Execute one research task in isolation. Returns the updated state slice
    so the parallel orchestrator can merge results.
    """
    # Build a minimal per-task state so worker() can read what it needs
    per_state = dict(base_state)
    per_state["research_tasks"] = [task]
    per_state["worker_index"] = 0
    per_state["task_results"] = []
    per_state["execution_trace"] = []
    result = worker(per_state)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 2.1 worker — 0 generation calls, embedding only
# ══════════════════════════════════════════════════════════════════════════════

def worker(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])
    tasks = state.get("research_tasks", [])
    idx = state.get("worker_index", 0)
    calls = state.get("llm_calls_made", 0)
    
    if idx >= len(tasks):
        return {}
        
    task = tasks[idx]
    
    # --- QUERY EXPANSION (Fix 2: expansion_cache + call_json_with_fallback) ---
    exp_cache_key = hashlib.sha1(task['question'].strip().lower().encode()).hexdigest()
    cached_exp = cache_get("expansion_cache", exp_cache_key)
    if cached_exp and isinstance(cached_exp, dict) and cached_exp.get("keywords"):
        expansion_result = cached_exp["keywords"]
        trace.append(f"[WORKER] Expansion cache hit ({exp_cache_key[:8]}).")
    else:
        exp_schema = '{"keywords": "<comma-separated list>"}'
        exp_prompt = (f"You are an expert legal researcher. Expand the following task question into "
                      f"5-8 highly relevant legal concepts, keywords, or section numbers "
                      f"(e.g. 'patentability', 'section 3(p)', 'novelty', 'traditional knowledge') "
                      f"to improve vector retrieval.\n"
                      f"Question: {task['question']}\n"
                      f"Return JSON: {exp_schema}")
        parsed_exp, exp_provider = call_json_with_fallback(
            prompt=exp_prompt,
            schema=exp_schema,
            trace=trace,
            context=f"EXPANSION-{task['id']}",
        )
        if parsed_exp and parsed_exp.get("keywords"):
            expansion_result = parsed_exp["keywords"]
            cache_set("expansion_cache", exp_cache_key, {"keywords": expansion_result}, ttl_s=86400)
            calls += 1
            trace.append(f"[WORKER] Query expansion via {exp_provider}: {expansion_result[:60]}")
        else:
            expansion_result = ""
            trace.append(f"[WORKER] Query expansion skipped (provider={exp_provider}); using raw question.")
    expanded_query = f"{task['question']} {expansion_result}".strip()
    # -------------------------------------------------------------------------
    
    trace.append(f"[WORKER] Executing {task['id']} ({task['jurisdiction']}): {task['question'][:40]}...")
    
    chunks = retriever_svc.retrieve(
        query=expanded_query, 
        jurisdiction=task["jurisdiction"], 
        formulation_category=state.get("formulation_category"),
        domains=task.get("domains", [])
    )
    
    # ── Bounded Agentic Retrieval Sub-Loop ──
    # max_hops=1: hop 0 is the initial retrieval; one follow-up hop is
    # allowed. Hops 2-3 rarely add distinct chunks but always cost an
    # extra Groq call. Cut to 1 to reduce latency by ~12-18 s per request.
    max_hops = 1
    hop = 0
    all_chunks = {c["chunk_id"]: c for c in chunks}
    
    while hop < max_hops:
        hop += 1
        if not all_chunks:
            break
            
        context = "\n\n".join([c["content"] for c in all_chunks.values()])
        
        hop_schema = '{"missing_references": ["<ref1>", "<ref2>"]}'
        hop_prompt = f"""Given the task and current evidence, list any specific legal references (act name + section, or case citation) that are needed but missing. Return JSON only.

Task: {task['question']}
Evidence chunks: {[c.get('metadata', {}).get('act_name', 'Unknown') + ' §' + str(c.get('metadata', {}).get('section_or_article', '')) for c in list(all_chunks.values())[:5]]}

Return JSON: {hop_schema}"""

        parsed, provider = call_json_with_fallback(
            prompt=hop_prompt,
            schema=hop_schema,
            trace=trace,
            context=f"WORKER-{task['id']}-HOP{hop}",
        )
        missing = (parsed or {}).get("missing_references", [])
        trace.append(f"[WORKER] Hop {hop} missing refs via {provider}: {missing}")

        if not missing or provider == "SKIPPED_TRANSIENT":
            break  # do NOT abort task; sub-loop ends cleanly
            
        # Retrieve additional chunks for the missing references
        from services.knowledge_graph import resolve_reference
        new_chunks_found = False
        unresolved = state.get("unresolved_references", [])
        for ref in missing:
            doc_ids = resolve_reference(ref)
            if not doc_ids:
                if ref not in unresolved:
                    unresolved.append(ref)
                continue

            ref_chunks = retriever_svc.retrieve(
                query=ref,
                jurisdiction=task["jurisdiction"],
                formulation_category=state.get("formulation_category"),
                domains=task.get("domains", []),
                k=3 # Only top 3 for specific references
            )
            for rc in ref_chunks:
                # Optional: enforce jurisdiction boundary by checking rc["metadata"]["jurisdiction"] == task["jurisdiction"]
                if rc["metadata"].get("jurisdiction") != task["jurisdiction"]:
                    if ref not in unresolved:
                        unresolved.append(f"{ref} (Cross-jurisdiction)")
                    continue
                    
                if rc["chunk_id"] not in all_chunks:
                    all_chunks[rc["chunk_id"]] = rc
                    new_chunks_found = True
                    
        # Update state with unresolved references
        if "unresolved_references" not in state:
            state["unresolved_references"] = unresolved
        
        if not new_chunks_found:
            trace.append(f"[WORKER] Hop {hop} retrieved no new distinct chunks. Sub-loop terminating.")
            break
            
    final_chunks = list(all_chunks.values())
    
    sufficient, reason = retriever_svc.is_sufficient_coverage(final_chunks, task['question'])
    
    sims = [c["similarity"] for c in final_chunks]
    max_sim = round(max(sims), 4) if sims else 0.0
    mean_sim = round(sum(sims) / len(sims), 4) if sims else 0.0
    relevant_count = sum(1 for s in sims if s >= SIMILARITY_THRESHOLD)
    
    result = {
        "task_id": task["id"],
        "question": task["question"],
        "jurisdiction": task["jurisdiction"],
        "domains": task.get("domains", []),
        "retrieved_chunks": final_chunks,
        "max_similarity": max_sim,
        "mean_similarity": mean_sim,
        "relevant_chunk_count": relevant_count,
        "sufficient": sufficient,
        "abstain_reason": reason if not sufficient else None
    }
    
    trace.append(f"[WORKER] {task['id']} retrieved {len(final_chunks)} chunks (after {hop-1} extra hops). Sufficient: {sufficient}")
    if not sufficient:
        # Fix 2: distinguish zero-content vs errored retrieval
        if len(final_chunks) == 0:
            trace.append(f"[WORKER] {task['id']} — INSUFFICIENT reason: no chunks retrieved at all (corpus gap, not a call error).")
        else:
            trace.append(f"[WORKER] {task['id']} — INSUFFICIENT reason: {reason}")
    
    current_results = list(state.get("task_results", []))
    current_results.append(result)
    
    return {
        "task_results": current_results,
        "worker_index": idx + 1,
        "execution_trace": trace,
        "llm_calls_made": calls
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2.15  parallel_worker — runs ALL tasks concurrently, replaces sequential loop
# ══════════════════════════════════════════════════════════════════════════════

def parallel_worker(state: AgentState) -> dict[str, Any]:
    """
    Fan out all research tasks in parallel (ThreadPoolExecutor) and merge
    results.  Replaces the sequential worker-loop in the LangGraph graph.
    Wall-clock time = slowest single task instead of sum of all tasks.
    """
    tasks = state.get("research_tasks", [])
    trace = list(state.get("execution_trace", []))
    existing_results = list(state.get("task_results", []))  # pre-skipped tasks from supervisor
    total_calls = state.get("llm_calls_made", 0)

    if not tasks:
        trace.append("[PARALLEL_WORKER] No tasks to run.")
        return {"task_results": existing_results, "execution_trace": trace}

    trace.append(f"[PARALLEL_WORKER] Launching {len(tasks)} tasks concurrently.")

    # Build base state without per-run fields
    base_state = dict(state)

    futures_map: dict = {}
    with _cf.ThreadPoolExecutor(max_workers=min(len(tasks), 10)) as pool:
        for task in tasks:
            f = pool.submit(_run_single_worker, task, base_state)
            futures_map[f] = task["id"]

        for f in _cf.as_completed(futures_map):
            task_id = futures_map[f]
            try:
                result = f.result()
                # Merge task_results
                new_results = result.get("task_results", [])
                existing_results.extend(new_results)
                # Merge traces
                trace.extend(result.get("execution_trace", []))
                total_calls += result.get("llm_calls_made", 0)
            except Exception as exc:
                trace.append(f"[PARALLEL_WORKER] Task {task_id} raised exception: {exc}")

    trace.append(f"[PARALLEL_WORKER] All tasks done. {len(existing_results)} results collected.")
    return {
        "task_results": existing_results,
        "worker_index": len(tasks),   # mark loop as complete
        "llm_calls_made": total_calls,
        "execution_trace": trace,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2.2 evidence_verification — evaluates task results and builds flat chunk arrays
# ══════════════════════════════════════════════════════════════════════════════

def evidence_verification(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])
    results = state.get("task_results", [])
    
    trace.append(f"[GATE] Verifying evidence across {len(results)} tasks...")
    
    sufficient_count = sum(1 for r in results if r["sufficient"])
    
    unresolved = state.get("unresolved_references", [])
    if not results:
        overall_status = "ABSTAIN"
    elif sufficient_count == len(results):
        overall_status = "VERIFIED"
        if len(unresolved) > 0:
            overall_status = "PARTIAL"
            trace.append(f"[GATE] Downgraded to PARTIAL: {len(unresolved)} unresolved references found.")
    elif sufficient_count > 0:
        overall_status = "PARTIAL"
        if len(unresolved) > 0:
            trace.append(f"[GATE] Maintained PARTIAL: {len(unresolved)} unresolved references found.")
    else:
        overall_status = "ABSTAIN"
        
    trace.append(f"[GATE] Overall status: {overall_status} ({sufficient_count}/{len(results)} tasks sufficient)")
    
    nat_chunks = []
    int_chunks = []
    seen_ids = set()
    
    for r in results:
        for c in r["retrieved_chunks"]:
            if c["chunk_id"] not in seen_ids:
                seen_ids.add(c["chunk_id"])
                if r["jurisdiction"] == "national":
                    nat_chunks.append(c)
                else:
                    int_chunks.append(c)
                    
    verified_tasks = [r for r in results if r["sufficient"]]
    insufficient_tasks = [r for r in results if not r["sufficient"]]
    
    query = state.get("raw_query", "").lower()
    if "case law" in query or "cases" in query or "judgment" in query:
        has_case_law = any(
            "case" in c.get("metadata", {}).get("source_type", "").lower() or 
            "judgment" in c.get("metadata", {}).get("source_type", "").lower() or
            "case" in c.get("metadata", {}).get("act_name", "").lower()
            for c in nat_chunks + int_chunks
        )
        if not has_case_law and overall_status == "VERIFIED":
            overall_status = "PARTIAL"
            trace.append("[GATE] Downgraded to PARTIAL: Query requires case law, but none was retrieved.")
                    
    return {
        "overall_status": overall_status,
        "abstain": overall_status == "ABSTAIN",
        "abstain_reason": "Failed to retrieve sufficient evidence for any research tasks." if overall_status == "ABSTAIN" else None,
        "verified_tasks": verified_tasks,
        "insufficient_tasks": insufficient_tasks,
        "retrieved_chunks_national": nat_chunks,
        "retrieved_chunks_international": int_chunks,
        "execution_trace": trace
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. generate — 1 Groq call per active jurisdiction, NEVER blended
# ══════════════════════════════════════════════════════════════════════════════

_DISCLOSURE_SYSTEM = """You are IP-SHAKTI, an IP & regulatory research assistant specialising in Indian IP and pharmaceutical law.

You will receive a user's query, an evidence mode (VERIFIED / PARTIAL / ABSTAIN), and per-task evidence blocks.

--- OUTPUT FORMAT (follow exactly) ---

Your final output must be ONLY a valid JSON object matching this schema:
{
  "answer": "Your complete legal analysis and answer here. Use markdown headings and bullet points for readability. Do NOT use boilerplate headers like 'Conclusion'.",
  "follow_up_questions": ["Specific follow-up question 1", "Specific follow-up question 2"]
}

--- EVIDENCE RULES ---

MODE = VERIFIED  (5 or more tasks VERIFIED, or header says VERIFIED)
  - Address every legal issue raised by the query in your `answer`.
  - Every claim MUST cite from the VERIFIED evidence blocks using [act_id:Section N].

MODE = PARTIAL   (1 to 4 tasks VERIFIED)
  - Address VERIFIED issues only.
  - For each INSUFFICIENT task, add one line to your answer: Evidence gap -- <topic>: corpus lacks <what is missing>.
  - FORBIDDEN: blanket refusal or "insufficient evidence to provide conclusive answer".

MODE = ABSTAIN   (0 tasks VERIFIED)
  - Set `answer` to ONLY: "The verified corpus does not contain sufficient evidence to answer this query. Please consult a qualified IP attorney."
  - Set `follow_up_questions` to an empty array [].

General rules:
- Answer ONLY from evidence blocks. Never invent facts or citations.
- Structure sections around the USER'S QUESTION naturally.
- If validation_feedback is provided, remove the flagged claim only. Do not add new claims.
- Do NOT output markdown code fences around the JSON.
"""

_INFORMATIONAL_SYSTEM = """\
You are IP-SHAKTI, a specialist in Intellectual Property and regulatory law for India.

The user is asking an informational or legal question. Answer it directly and helpfully in a natural, cohesive format.

--- OUTPUT FORMAT ---
- Provide a clear and comprehensive legal analysis of the query.
- Use natural paragraphs and logical flow instead of rigid numbering.
- Quote or closely paraphrase statutory text where relevant (government statutes are public domain).
- Cite [act_id:Section N] inline for legal claims.
- Conclude with a brief summary sentence and optionally suggest relevant follow-up questions if helpful.
- DO NOT use boilerplate headers like "1. LEGAL ANALYSIS" or "2. CONCLUSION".

Jurisdiction corpus: {jurisdiction}

Evidence rules:
- Use ONLY evidence from VERIFIED task blocks. Do not hallucinate sections or case law.
- For INSUFFICIENT tasks: state the gap explicitly; do not refuse the whole answer.
- If case law was not retrieved, state: "Relevant case law was not found in the corpus."

Return ONLY a JSON object with a single key. No markdown fences, no preamble:
{{"answer": "Your structured response here."}}\
"""


def _build_context(tasks: list[dict], live_evidence: list[dict] = None, unresolved_references: list[str] = None) -> str:
    parts = []
    global_index = 1
    seen_chunk_ids = set()
    
    for t in tasks:
        task_id = t["task_id"]
        status = "VERIFIED" if t["sufficient"] else "INSUFFICIENT"
        parts.append(f"TASK {task_id} — {status}\nQuestion: {t['question']}\nEvidence:")
        
        if not t["sufficient"]:
            parts.append("  NONE\n")
            continue
            
        for c in t["retrieved_chunks"][:5]:
            chunk_id = c["chunk_id"]
            if chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk_id)
                m = c["metadata"]
                header = (
                    f"  E{global_index} → [{m.get('act_name', 'Unknown Act')} | "
                    f"{m.get('section_or_article', 'Unknown Section')} | "
                    f"Pages {m.get('page_start', '?')}–{m.get('page_end', '?')} | "
                    f"Version: {m.get('version', 'unknown')}]"
                )
                content = "\n".join("    " + line for line in c['content'].split('\n'))
                parts.append(f"{header}\n{content}\n")
                global_index += 1
            
    # Add overall Evidence Status context
    overall_status = "VERIFIED" if all(t["sufficient"] for t in tasks) else ("PARTIAL" if any(t["sufficient"] for t in tasks) else "INSUFFICIENT")
    context = f"=== OVERALL EVIDENCE STATUS: {overall_status} ===\n\n" + "\n".join(parts)
    
    if live_evidence:
        context += "\n\n=== LIVE FACTUAL EVIDENCE ===\n"
        for ev in live_evidence:
            context += f"Source: {ev['source']} (Retrieved: {ev['retrieved_at']})\n"
            context += f"URL: {ev['url']}\n"
            context += f"Title: {ev['title']}\n"
            context += f"Record Evidence:\n{ev['evidence']}\n\n"
            
    if unresolved_references:
        context += "\n=== UNRESOLVED / CROSS-JURISDICTION REFERENCES ===\n"
        context += "The following references were mentioned in the primary texts but could not be retrieved because they are either from a different jurisdiction or missing from the corpus. Acknowledge this limitation if they are required to answer the query.\n"
        for ref in unresolved_references:
            context += f"- {ref}\n"
            
    return context


def _extract_citations(chunks: list[dict], jurisdiction: str) -> list[dict]:
    """Build Citation dicts from retrieved chunks. Uses document_id — never source_pdf_path."""
    toc_map = {}
    toc_path = os.path.join(os.path.dirname(__file__), "..", "toc_map.json")
    if os.path.exists(toc_path):
        try:
            with open(toc_path, "r", encoding="utf-8") as f:
                toc_map = json.load(f)
        except Exception:
            pass

    citations = []
    for c in chunks:
        doc_id = c["document_id"]
        sec = c["metadata"].get("section_or_article", "")
        page_start = c["metadata"].get("page_start", 1)
        
        if doc_id in toc_map and sec in toc_map[doc_id]:
            page_start = toc_map[doc_id][sec]
            
        citations.append({
            "document_id": doc_id,
            "act_id": c["metadata"].get("act_id", ""),
            "act_name": c["metadata"].get("act_name", ""),
            "section_or_article": sec,
            "page_start": page_start,
            "page_end": c["metadata"].get("page_end", 1),
            "chunk_id": c["chunk_id"],
            "version": c["metadata"].get("version", ""),
            "jurisdiction": jurisdiction,
            "snippet": c.get("content", "")[:200].replace("\n", " "),
        })
    return citations


@retry_429
def _call_groq(
    query: str,
    formulation_category: str,
    jurisdiction: str,
    tasks: list[dict],
    live_evidence: list[dict] = None,
    unresolved_references: list[str] = None,
    language: str = "en",
    validation_feedback: str = None,
) -> tuple[dict, list[dict]]:
    """Single Groq call for one jurisdiction. Returns (disclosure_fields, citations)."""
    llm = _get_llm(json_mode=True, task_type="heavy")
    
    if formulation_category == "informational":
        system = _INFORMATIONAL_SYSTEM.format(jurisdiction=jurisdiction)
    else:
        system = _DISCLOSURE_SYSTEM
        
    expected_keys = ["answer"]
    
    if language and language.strip().lower() not in ["en", "english"]:
        system += f"\n\nCRITICAL INSTRUCTION: You MUST translate all generated response values into {language}. Do not drift into other languages. The JSON keys must remain exactly as requested in English, but the textual values must be written strictly in {language}. HOWEVER, you must keep all legal source quotations (like excerpted sections, exact terminology) in their original language."
        
    verified_count = sum(1 for t in tasks if t.get("sufficient"))
    total = len(tasks)
    if verified_count == 0:
        mode = "ABSTAIN"
    elif verified_count >= max(5, total - 1):  # >=5/6 or all-but-one
        mode = "VERIFIED"
    else:
        mode = "PARTIAL"
        
    context = _build_context(tasks, live_evidence, unresolved_references)
    context = f"MODE: {mode}\n" + context

    human_msg = f"User query: {query}\n\n[RESEARCH TASKS AND EVIDENCE]\n{context}"
    if validation_feedback:
        human_msg += f"\n\n[VALIDATION FEEDBACK FROM PREVIOUS ATTEMPT]\nYour previous attempt failed validation for the following reason:\n{validation_feedback}\n\nPlease correct this in your new response."
        
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=human_msg),
    ]

    response = llm.invoke(messages)
    parsed = _parse_json_robust(response.content, None, "GENERATE")
    
    if isinstance(parsed, dict):
        if not any(k in parsed for k in expected_keys) and len(parsed) == 1:
            parsed = list(parsed.values())[0]

    if isinstance(parsed, dict) and any(k in parsed for k in expected_keys):
        fields = parsed
    elif isinstance(parsed, dict):
        fields = parsed
    else:
        fields = {}

    if "answer" not in fields or not str(fields.get("answer", "")).strip():
        if mode == "ABSTAIN":
            fields["answer"] = "The verified corpus does not contain sufficient evidence to answer this query. Consult a qualified IP attorney."
        elif mode == "PARTIAL":
            # Fix 3: PARTIAL must never emit a blanket refusal — emit a partial answer notice instead.
            fields["answer"] = "Partial evidence retrieved. See the ⚠ Evidence gap notices above for topics where the verified corpus is incomplete."

    fields["standing_disclaimer"] = (
        "This information is provided for educational purposes only and does "
        "not constitute legal advice. Consult a qualified IP attorney."
    )

    chunks = []
    seen = set()
    for t in tasks:
        for c in t["retrieved_chunks"][:8]:
            if c["chunk_id"] not in seen:
                seen.add(c["chunk_id"])
                chunks.append(c)

    citations = _extract_citations(chunks, jurisdiction)
    
    # Issue 8: Citation-groundedness enforcement.
    if not citations and not live_evidence and mode == "ABSTAIN":
        if "Parse error" not in str(fields.get("answer", "")):
            fields["answer"] = "The verified corpus does not contain sufficient evidence to answer this query. Consult a qualified IP attorney."

    return fields, citations


def live_registry_search(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])
    trace.append("[CONNECTOR] Live registry-source discovery initiated")

    query = state["raw_query"]

    connector = LiveRegistryConnector()
    result = connector.search_registry(query)

    evidence = result.get("evidence", [])
    status = result.get("status", "error")

    if status == "phase2_not_enabled":
        trace.append(
            "[CONNECTOR] Phase 2 — live registry search not yet enabled "
            "(IP India / WIPO structured API wired in Phase 2)"
        )
    elif evidence:
        trace.append(f"[CONNECTOR] {len(evidence)} records returned ({status})")
        trace.append(f"[VALIDATOR] {len(evidence)} records passed source validation")
    else:
        trace.append(f"[CONNECTOR] No records returned ({status})")

    return {
        "live_evidence": evidence,
        "connector_used": True,
        "connector_status": status,
        "execution_trace": trace,
        "abstain": False,  # Clear abstain so main.py doesn't suppress the answer
        "abstain_reason": None,
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
    
    language = state.get("language", "en")
    validation_feedback = state.get("validation_feedback")

    # Issue 10: Strict isolation of context by jurisdiction.
    
    all_tasks = state.get("task_results", [])
    
    nat_tasks = [
        t for t in all_tasks
        # jurisdiction lives inside t["task"], not at top level of the task_result dict
        if (t.get("jurisdiction") or t.get("task", {}).get("jurisdiction", "")).lower() == "national"
    ]
    
    int_tasks = [
        t for t in all_tasks
        if (t.get("jurisdiction") or t.get("task", {}).get("jurisdiction", "")).lower() == "international"
    ]

    import concurrent.futures

    def run_nat():
        return _call_groq(query, category, "national", nat_tasks, live_ev, language, validation_feedback)

    def run_int():
        return _call_groq(query, category, "international", int_tasks, live_ev, language, validation_feedback)

    if mode == "both":
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_nat = executor.submit(run_nat)
            future_int = executor.submit(run_int)
            
            try:
                nat_answer, nat_citations = future_nat.result()
            except Exception as e:
                trace.append(f"[GENERATOR] National generation failed: {str(e)}")
                raise

            try:
                int_answer, int_citations = future_int.result()
            except Exception as e:
                trace.append(f"[GENERATOR] International generation failed: {str(e)}")
                raise
                
            calls += 2
    elif mode == "national":
        nat_answer, nat_citations = run_nat()
        calls += 1
    elif mode == "international":
        int_answer, int_citations = run_int()
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
    if "answer" in answer:
        ans = answer["answer"]
        return 1.0 if (len(ans) > 20 and not ans.lower().startswith("[parse error")) else 0.0
        
    filled = sum(
        1
        for k in DISCLOSURE_FIELD_KEYS
        if answer.get(k)
        and not answer[k].lower().startswith("not applicable")
        and not answer[k].lower().startswith("[parse error")
        and len(answer[k]) > 5
    )
    return round(filled / len(DISCLOSURE_FIELD_KEYS), 4)


def _deterministic_template_answer(tasks: list[dict], jurisdiction: str = "national") -> tuple[str, list[dict]]:
    """Chunk-grounded template answer used when LLM generation cannot pass validation.
    Produces no free-form claims — only quotes retrieved evidence with citations."""
    sections = []
    citations = []
    for t in tasks:
        if not t.get("sufficient"):
            continue
        heading = t.get("question", f"Task {t.get('task_id')}").strip()
        sections.append(f"### {heading}")
        chunks_list = t.get("retrieved_chunks") or t.get("chunks", [])
        for ch in chunks_list[:3]:
            m = ch.get("metadata", {}) if isinstance(ch.get("metadata"), dict) else {}
            act = ch.get("act_name") or m.get("act_name", "Unknown Act")
            sec = ch.get("section_or_article") or m.get("section_or_article", "")
            act_id = ch.get("act_id") or m.get("act_id", "?")
            text = (ch.get("content") or ch.get("text") or "").strip()
            # first 2 sentences, no rewriting
            snippet = ". ".join(text.split(". ")[:2]).strip()
            if snippet and not snippet.endswith("."):
                snippet += "."
            cite = f"[{act_id}:{sec}]" if sec else f"[{act_id}]"
            sections.append(f"- **{act}** {('§' + sec) if sec else ''}: {snippet} {cite}")
            citations.append({
                "act_id": act_id,
                "act_name": act,
                "section": sec,
                "chunk_id": ch.get("chunk_id"),
            })
    if not sections:
        return ("The verified corpus does not contain sufficient evidence to answer this query.", [])
    sections.append("\n_This is a template answer generated because LLM synthesis failed validation. Verify against the cited primary sources._")
    return ("\n".join(sections), citations)


def validate_response(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])
    category = state.get("formulation_category", "unknown")
    failures = state.get("validation_failures", 0)
    
    # If it's not a formulation, skip validation
    if category in ("informational", "unknown"):
        return {"validation_failures": failures, "validation_feedback": None}



    if failures >= 2:
        trace.append("[VALIDATOR] Max validation failures — switching to deterministic template answer.")
        tasks = state.get("task_results") or state.get("tasks", [])
        template_ans, template_cites = _deterministic_template_answer(tasks, "national")
        # Fix 4: always return execution_trace so accumulated trace mutations are not lost.
        formatted_ans = {"answer": template_ans}
        return {
            "validation_failures": failures,
            "validation_feedback": None,
            "overall_status": "PARTIAL",
            "confidence_band": "LOW",
            "national_answer": formatted_ans,
            "national_citations": template_cites,
            "abstain": False,
            "abstain_reason": None,
            "used_deterministic_fallback": True,
            "execution_trace": trace,  # Fix 4: was missing in original
        }

    gov_map_path = os.path.join(os.path.dirname(__file__), "..", "governed_by_map.json")
    allowed_acts = []
    if os.path.exists(gov_map_path):
        with open(gov_map_path, "r", encoding="utf-8") as f:
            gov_map = json.load(f)
            allowed_acts = gov_map.get(category, [])

    # Layer 1: Deterministic Allowlist
    illegal_citations = []
    citations = state.get("national_citations", []) + state.get("international_citations", [])
    for citation in citations:
        act_id = citation.get("act_id")
        # Treat missing act_id as allowed to prevent false positives on badly metadata'd chunks, 
        # or we strictly reject. Let's be strict if act_id exists and is not allowed.
        if act_id and allowed_acts and act_id not in allowed_acts:
            illegal_citations.append(f"{citation.get('act_name')} ({act_id})")

    if illegal_citations:
        illegal_str = ", ".join(set(illegal_citations))
        trace.append(f"[VALIDATOR] Layer 1 failed: Illegal citations found for {category}: {illegal_str}")
        return {
            "validation_failures": failures + 1,
            "validation_feedback": f"Your response cited acts ({illegal_str}) that do not govern the '{category}' category. The allowed acts are: {', '.join(allowed_acts)}. Please rewrite the response using ONLY the allowed acts.",
            "execution_trace": trace
        }

    trace.append("[VALIDATOR] Layer 1 (Deterministic Allowlist) passed.")

    # Layer 2: LLM Consistency Check — skip on VERIFIED to save 1-2 Groq calls
    # (Layer 1 already confirmed no illegal citations; semantic re-check is only
    # worth the cost when evidence coverage is partial/uncertain).
    overall_status = state.get("overall_status", "")
    if overall_status == "VERIFIED":
        trace.append("[VALIDATOR] Layer 2 skipped — status already VERIFIED by generator.")
        return {"validation_feedback": None, "execution_trace": trace}

    # Layer 2: LLM Consistency Check (Fix 5: use call_json_with_fallback, not raw llm.invoke)
    query = state["raw_query"]

    val_schema = '{"is_accurate": true, "reason": "<explanation>"}'
    val_sys_prefix = (
        "You are a strict legal reviewer. Verify if the response is fully supported by the "
        "retrieved evidence. Extract atomic claims from the response and check each one "
        "against the evidence. If any claim is unsupported, hallucinated, or contradicts "
        "the evidence, return is_accurate=false with a specific reason. "
        f"Return JSON: {val_schema}"
    )

    # Check national answer
    nat_answer = state.get("national_answer")
    if nat_answer:
        nat_context = _build_context(
            [t for t in state.get("task_results", [])
             if (t.get("jurisdiction") or t.get("task", {}).get("jurisdiction", "")).lower() == "national"],
            state.get("live_evidence", [])
        )
        nat_prompt = (f"{val_sys_prefix}\n\nQuery: {query}\n\n"
                      f"Evidence:\n{nat_context}\n\n"
                      f"Response to evaluate:\n{json.dumps(nat_answer, indent=2)}")
        parsed, val_provider = call_json_with_fallback(
            prompt=nat_prompt,
            schema=val_schema,
            trace=trace,
            context="VALIDATE_NAT",
        )
        if isinstance(parsed, dict) and not parsed.get("is_accurate", True):
            trace.append(f"[VALIDATOR] Layer 2 (Semantic) failed for national via {val_provider}: {parsed.get('reason')}")
            return {
                "validation_failures": failures + 1,
                "validation_feedback": (
                    f"Your national response was flagged as inaccurate. "
                    f"Reason: {parsed.get('reason')}. "
                    "Please remove or qualify the unsupported claim and answer with ONLY the supported claims. "
                    "Do not refuse to answer the entire query."
                ),
                "execution_trace": trace,
            }

    # Check international answer
    int_answer = state.get("international_answer")
    if int_answer:
        int_context = _build_context(
            [t for t in state.get("task_results", [])
             if (t.get("jurisdiction") or t.get("task", {}).get("jurisdiction", "")).lower() == "international"],
            state.get("live_evidence", [])
        )
        int_prompt = (f"{val_sys_prefix}\n\nQuery: {query}\n\n"
                      f"Evidence:\n{int_context}\n\n"
                      f"Response to evaluate:\n{json.dumps(int_answer, indent=2)}")
        parsed, val_provider = call_json_with_fallback(
            prompt=int_prompt,
            schema=val_schema,
            trace=trace,
            context="VALIDATE_INT",
        )
        if isinstance(parsed, dict) and not parsed.get("is_accurate", True):
            trace.append(f"[VALIDATOR] Layer 2 (Semantic) failed for international via {val_provider}: {parsed.get('reason')}")
            return {
                "validation_failures": failures + 1,
                "validation_feedback": (
                    f"Your international response was flagged as inaccurate. "
                    f"Reason: {parsed.get('reason')}. "
                    "Please remove or qualify the unsupported claim and answer with ONLY the supported claims. "
                    "Do not refuse to answer the entire query."
                ),
                "execution_trace": trace,
            }
            
    trace.append("[VALIDATOR] Layer 2 (Semantic Consistency) passed.")
    
    return {
        "validation_feedback": None,
        "execution_trace": trace
    }

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

    # Fix 1: Apply deterministic evidence-gate override.
    # The raw similarity score can be high even when most tasks failed retrieval
    # (e.g. one very similar chunk against 5 misses → 84% raw score, 3/6 sufficient).
    # This override ensures band reflects the gate verdict, not just embedding distances.
    overall_status = state.get("overall_status", "VERIFIED")
    task_results = state.get("task_results", [])
    sufficient_count = sum(1 for t in task_results if t.get("sufficient", False))
    total_tasks = len(task_results)
    sufficiency_ratio = sufficient_count / total_tasks if total_tasks > 0 else 0.0

    if overall_status == "ABSTAIN":
        # Gate said nothing was useful — force LOW regardless of embeddings
        band = "LOW"
        score = min(score, 0.35)
    elif overall_status == "PARTIAL":
        if sufficiency_ratio < 0.5:
            # Fewer than half the tasks came back — force LOW
            band = "LOW"
            score = min(score, 0.35)
        else:
            # At least half sufficient — cap at MEDIUM
            band = "MEDIUM"
            score = min(score, 0.65)
    else:
        # VERIFIED — normal band from raw score
        if score >= 0.7:
            band = "HIGH"
        elif score >= 0.4:
            band = "MEDIUM"
        else:
            band = "LOW"

    components = {
        "max_similarity": max_sim,
        "mean_similarity": mean_sim,
        "relevant_chunk_count": relevant_count,
        "disclosure_fill_rate": fill,
    }

    return {"confidence_components": components, "confidence_score": score, "confidence_band": band}


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
    
    # Extract extended logging fields
    session_id = final_state.get("session_id", "unknown")
    raw_query = final_state.get("raw_query", "")
    jurisdiction_mode = final_state.get("jurisdiction_mode", "")
    formulation_category = final_state.get("formulation_category", "")
    confidence_score = final_state.get("confidence_score", 0.0)
    confidence_band = final_state.get("confidence_band", "LOW")
    llm_calls_made = final_state.get("llm_calls_made", 0)
    latency_ms = final_state.get("latency_ms", 0.0)
    
    log_query({
        "session_id": session_id,
        "raw_query": raw_query,
        "jurisdiction_mode": jurisdiction_mode,
        "formulation_category": formulation_category,
        "confidence_score": confidence_score,
        "confidence_band": confidence_band,
        "llm_calls_made": llm_calls_made,
        "latency_ms": latency_ms,
        "full_state": final_state
    })

    return {"latency_ms": latency}
