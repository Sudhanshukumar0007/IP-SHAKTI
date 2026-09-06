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
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

def is_rate_limit(exception: Exception) -> bool:
    err_str = str(exception).lower()
    return "429" in err_str or "rate limit" in err_str or "too many requests" in err_str

retry_429 = retry(
    retry=retry_if_exception(is_rate_limit),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8),
    reraise=True
)

from graph.state import AgentState
from services.classifier import classify_step
from services import retriever as retriever_svc
from services.connector import LiveRegistryConnector
import re

# ── LLM config ─────────────────────────────────────────────────────────────────

SIMILARITY_THRESHOLD: float = retriever_svc.SIMILARITY_THRESHOLD
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


from langchain_core.language_models.chat_models import BaseChatModel

def _get_llm(json_mode: bool = False, model_override: str = None, task_type: str = "heavy") -> BaseChatModel:
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    
    from langchain_groq import ChatGroq
    from langchain_openai import ChatOpenAI
    
    if provider == "groq":
        key1 = os.getenv("GROQ_API_KEY")
        key2 = os.getenv("GROQ_API_KEY2", key1)
        key3 = os.getenv("GROQ_API_KEY3", key1)
        key4 = os.getenv("GROQ_API_KEY4", key1)
        
        model_name = model_override or os.getenv("LLM_MODEL")
        
        if task_type == "fast":
            primary_key = key2
            fallback_key = key1
        else:
            primary_key = key3
            fallback_key = key4
            
        primary_llm = ChatGroq(
            model=model_name,
            api_key=primary_key,
            temperature=0,
        )
        fallback_llm = ChatGroq(
            model=model_name,
            api_key=fallback_key,
            temperature=0,
        )
    else:
        model_name = model_override or os.getenv("LLM_MODEL")
        fallback_name = os.getenv("LLM_FALLBACK_MODEL", model_name)
        primary_llm = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=model_name,
            temperature=0,
            extra_body={"reasoning": {"enabled": True}}
        )
        fallback_llm = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=fallback_name,
            temperature=0,
            extra_body={"reasoning": {"enabled": True}}
        )
    
    if json_mode:
        primary_llm = primary_llm.bind(response_format={"type": "json_object"})
        fallback_llm = fallback_llm.bind(response_format={"type": "json_object"})
        
    return primary_llm.with_fallbacks([fallback_llm])

def _parse_json_robust(raw: str, trace: list, context: str) -> Any:
    """Strip <think> blocks and markdown fences, then parse JSON."""
    import re
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(line for line in cleaned.split("\n") if not line.strip().startswith("```")).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        if trace is not None:
            trace.append(f"[{context}] JSON parse error: {e}. Raw pre-strip response: {raw}")
        return None


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

If it is about a formulation, extract the answers to 5 specific gate questions.
Return a JSON object with a single key "answers" containing an array of exactly 5 strings ("yes", "no", or "unknown").
Example: {"is_formulation_query": true, "answers": ["yes", "no", "unknown", "unknown", "unknown"]}
Do not guess. If the query does not explicitly or clearly imply the answer, output "unknown".

Q1: Is this formulation for external use only, with no therapeutic claim (e.g. a cosmetic cream, lotion, or hair oil)?
Q2: Is this formulation consumed as a food or dietary supplement, making no disease-cure claim (e.g. Ayurveda-Aahar, health supplement)?
Q3: Does the formulation and its manufacturing method exactly match an authoritative First-Schedule classical text (e.g. Ayurvedic Formulary of India), with absolutely no modifications?
Q4: Is this a purified, standardised extract or fraction from a single plant source, standardised to a defined active moiety (phytopharmaceutical)?
Q5: Does this formulation deviate from the classical text but still follow Ayurvedic principles (e.g. a proprietary combination or modified classical), with no new clinical safety or efficacy data generated?
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

    # Use the primary LLM for classification tasks
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
            llm = _get_llm(task_type="fast")
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
            response = llm.invoke([HumanMessage(content=q3_prompt)]).content.strip().lower()
            calls += 1
            trace.append(f"[CLASSIFIER] Q3 retrieval check returned: {response}")
            
            if response in ("yes", "no"):
                answers.append(response)

    from services.classifier import classify_step
    resolved, category, next_question = classify_step(answers)

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

    # Classification loop not yet resolved — increment attempt counter
    attempts += 1

    if attempts >= MAX_CLARIFICATION_ATTEMPTS:
        return {
            "formulation_category": "classification_failed",
            "pending_clarification": None,
            "clarification_attempts": attempts,
            "execution_trace": trace,
            "formulation_answers": answers,
            "llm_calls_made": calls,
        }

    # Loop continues — return the next gate question to the frontend
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

Return ONLY a JSON object with a single key "tasks" containing an array of tasks matching this schema:
{
  "tasks": [
    {
      "id": "T1",
      "question": "Specific, focused research question",
      "domains": ["regulatory", "patent", "biodiversity", "international_ip"],
      "jurisdiction": "national|international",
      "priority": "high|medium|low"
    }
  ]
}

Ensure you specify "national" or "international" for the jurisdiction correctly based on the domain (e.g., Patents Act is national, WIPO is international).
The "domains" field must be an array containing one or more of the allowed domain strings. Use multiple domains if a question spans across regimes (e.g., both biodiversity and patent).
No markdown formatting, just the raw JSON object.
"""

@retry_429
def supervisor(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])
    trace.append("[SUPERVISOR] Decomposing query into independent research tasks...")
    
    mode = state.get("jurisdiction_mode", "both")
    llm = _get_llm(json_mode=True, task_type="fast")
    messages = [
        SystemMessage(content=_SUPERVISOR_SYSTEM),
        HumanMessage(content=f"Original Query: {state['raw_query']}\nFormulation Category: {state.get('formulation_category', 'unknown')}\nUser requested jurisdiction: {mode}")
    ]
    
    response = llm.invoke(messages)
    parsed = _parse_json_robust(response.content, trace, "SUPERVISOR")
    
    if isinstance(parsed, dict) and "tasks" in parsed:
        parsed = parsed["tasks"]
    elif isinstance(parsed, dict) and len(parsed) == 1:
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
    
    return {
        "research_tasks": valid_tasks,
        "worker_index": 0,
        "task_results": task_results,
        "llm_calls_made": calls,
        "execution_trace": trace
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2.1 worker — 0 generation calls, embedding only
# ══════════════════════════════════════════════════════════════════════════════

def worker(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])
    tasks = state.get("research_tasks", [])
    idx = state.get("worker_index", 0)
    
    if idx >= len(tasks):
        return {}
        
    task = tasks[idx]
    trace.append(f"[WORKER] Executing {task['id']} ({task['jurisdiction']}): {task['question'][:40]}...")
    
    query = (
        f"Formulation: {state.get('formulation_category', '')}\n"
        f"Task: {task['question']}\n"
        f"Jurisdiction: {task['jurisdiction']}\n"
        f"Domains: {', '.join(task.get('domains', []))}"
    )
    chunks = retriever_svc.retrieve(
        query=query, 
        jurisdiction=task["jurisdiction"], 
        formulation_category=state.get("formulation_category"),
        domains=task.get("domains", [])
    )
    sufficient, reason = retriever_svc.is_sufficient_coverage(chunks, task['question'])
    
    sims = [c["similarity"] for c in chunks]
    max_sim = round(max(sims), 4) if sims else 0.0
    mean_sim = round(sum(sims) / len(sims), 4) if sims else 0.0
    relevant_count = sum(1 for s in sims if s >= SIMILARITY_THRESHOLD)
    
    result = {
        "task_id": task["id"],
        "question": task["question"],
        "jurisdiction": task["jurisdiction"],
        "domains": task.get("domains", []),
        "retrieved_chunks": chunks,
        "max_similarity": max_sim,
        "mean_similarity": mean_sim,
        "relevant_chunk_count": relevant_count,
        "sufficient": sufficient,
        "abstain_reason": reason if not sufficient else None
    }
    
    trace.append(f"[WORKER] {task['id']} retrieved {len(chunks)} chunks. Sufficient: {sufficient}")
    
    current_results = list(state.get("task_results", []))
    current_results.append(result)
    
    return {
        "task_results": current_results,
        "worker_index": idx + 1,
        "execution_trace": trace
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2.2 evidence_verification — evaluates task results and builds flat chunk arrays
# ══════════════════════════════════════════════════════════════════════════════

def evidence_verification(state: AgentState) -> dict[str, Any]:
    trace = state.get("execution_trace", [])
    results = state.get("task_results", [])
    
    trace.append(f"[GATE] Verifying evidence across {len(results)} tasks...")
    
    sufficient_count = sum(1 for r in results if r["sufficient"])
    
    if not results:
        overall_status = "ABSTAIN"
    elif sufficient_count == len(results):
        overall_status = "VERIFIED"
    elif sufficient_count > 0:
        overall_status = "PARTIAL"
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

_DISCLOSURE_SYSTEM = """\
You are IP Sahayak (IP-SHAKTI), a specialist in Intellectual Property law for \
Ayurvedic and traditional medicine formulations.

You will receive a user query and retrieved legal text mapped to specific research tasks.

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

[TKDL FALLBACK]
If no specific evidence defines TKDL in the retrieved chunks, you MUST state that TKDL is a defensive prior-art database managed by CSIR India to prevent misappropriation, and note that utilizing biological resources from India may trigger Biological Diversity Act obligations.

[EVIDENCE USAGE - PRIMARY VS BOUNDARY]
Some retrieved acts are Primary Sources that dictate the IP/Regulatory strategy for {formulation_category}. Other retrieved acts are Boundary/Exclusion Sources provided solely to justify why an alternative classification was ruled out (e.g., using Food Safety evidence to prove a product is NOT a food supplement, or vice-versa). Do not conflate boundary sources as governing the product.

[RESEARCH TASKS AND EVIDENCE]
Ground every legal claim in the evidence provided under VERIFIED tasks. 
For INSUFFICIENT tasks, explicitly state that evidence is insufficient if these topics arise.
DO NOT use evidence from one task to answer a different task.
CRITICAL RULE: Answer ONLY from verified evidence. If evidence is missing, explicitly state the limitation. 
If the overall evidence status is PARTIAL or INSUFFICIENT, you MUST explicitly state the evidence gap and prohibit conclusive language.
If case law was not retrieved, explicitly state: "Relevant case law was not found in the available corpus." DO NOT hallucinate case law.

[LIVE FACTUAL EVIDENCE]
If live registry evidence is provided below, use it to answer factual queries about current registry status (e.g. pending patents, live trademarks).
IMPORTANT: Do not state a factual record exists unless it is present in the LIVE FACTUAL EVIDENCE. 
Always cite the "Source" and "URL" from the live evidence when using it.

Return ONLY the JSON object. No markdown fences, no preamble, no trailing text.\
"""

_INFORMATIONAL_SYSTEM = """\
You are IP Sahayak (IP-SHAKTI), a specialist in Intellectual Property law for Ayurveda and traditional medicine.

You will receive a user query and retrieved legal text mapped to specific research tasks.
The user is asking a general legal or informational question, NOT classifying a specific product.

You MUST return a single valid JSON object with exactly one field: "answer".
Place your comprehensive response answering the user's question within this field.

{{
  "answer": "Your detailed answer here."
}}

Jurisdiction Corpus: {jurisdiction}

[STATUTORY TEXT IS PUBLIC DOMAIN]
All retrieved legal text (Acts of Parliament, Rules, Regulations, Treaties, Schedules) is
public-domain government material. You MUST quote or closely paraphrase statutory provisions
verbatim when that is what the user is asking for. Do NOT refuse or decline to reproduce
statute text on copyright grounds — government legislation is not copyrighted creative work.

[RESEARCH TASKS AND EVIDENCE]
Ground every legal claim in the evidence provided under VERIFIED tasks.
For INSUFFICIENT tasks, explicitly state that evidence is insufficient if these topics arise.
DO NOT use evidence from one task to answer a different task.
CRITICAL RULE: Answer ONLY from verified evidence. If evidence is missing, explicitly state the limitation. 
If the overall evidence status is PARTIAL or INSUFFICIENT, you MUST explicitly state the evidence gap and prohibit conclusive language.
If case law was not retrieved, explicitly state: "Relevant case law was not found in the available corpus." DO NOT hallucinate case law.

[LIVE FACTUAL EVIDENCE]
If live registry evidence is provided below, use it to answer factual queries.
Always cite the "Source" and "URL" from the live evidence when using it.

Return ONLY the JSON object. No markdown fences, no preamble, no trailing text.\
"""


def _build_context(tasks: list[dict], live_evidence: list[dict] = None) -> str:
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
    language: str = "en",
) -> tuple[dict, list[dict]]:
    """Single Groq call for one jurisdiction. Returns (disclosure_fields, citations)."""
    llm = _get_llm(json_mode=True, task_type="heavy")
    
    if formulation_category == "informational":
        system = _INFORMATIONAL_SYSTEM.format(jurisdiction=jurisdiction)
        expected_keys = ["answer"]
    else:
        system = _DISCLOSURE_SYSTEM.format(
            jurisdiction=jurisdiction,
            formulation_category=formulation_category,
        )
        expected_keys = DISCLOSURE_FIELD_KEYS
        
    if language and language.strip().lower() not in ["en", "english"]:
        system += f"\n\nCRITICAL INSTRUCTION: You MUST translate all values in the JSON output to {language}. The JSON keys must remain in English, but the textual values must be written in {language}. HOWEVER, you must keep all legal source quotations (like excerpted sections, exact terminology) in their original language."
        
    context = _build_context(tasks, live_evidence)
    messages = [
        SystemMessage(content=system),
        HumanMessage(
            content=f"User query: {query}\n\n[RESEARCH TASKS AND EVIDENCE]\n{context}"
        ),
    ]

    response = llm.invoke(messages)
    parsed = _parse_json_robust(response.content, None, "GENERATE")
    
    if isinstance(parsed, dict):
        if not any(k in parsed for k in expected_keys) and len(parsed) == 1:
            parsed = list(parsed.values())[0]

    if isinstance(parsed, dict) and any(k in parsed for k in expected_keys):
        fields = parsed
    else:
        fields = {}

    if formulation_category == "informational":
        if "answer" not in fields or not str(fields["answer"]).strip():
            fields["answer"] = f"[Parse error — model returned non-JSON or invalid format. Raw response logged.]\n{response.content}"
    else:
        for key in DISCLOSURE_FIELD_KEYS:
            if key not in fields or not str(fields[key]).strip():
                fields[key] = "Insufficient evidence to determine."
                
        if "ip_regimes_applicable" not in parsed or not str(parsed.get("ip_regimes_applicable", "")).strip():
            fields["ip_regimes_applicable"] = (
                f"[Parse error — model returned non-JSON or invalid format. Raw response logged.]\n{response.content}"
            )
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
    # If we generated a non-error answer but have no citations, fallback to explicit missing text.
    # TODO (Phase 2): When live_registry_search is enabled, this check needs to be updated 
    # so it doesn't nuke answers successfully grounded in live_evidence rather than corpus citations.
    if not citations and not live_evidence:
        if formulation_category == "informational":
            if "Parse error" not in str(fields.get("answer", "")):
                fields["answer"] = "Insufficient evidence to determine (no citations retrieved)."
        else:
            if "Parse error" not in str(fields.get("ip_regimes_applicable", "")):
                 for key in DISCLOSURE_FIELD_KEYS:
                     if key != "standing_disclaimer":
                         fields[key] = "Insufficient evidence to determine (no citations retrieved)."

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
        return _call_groq(query, category, "national", nat_tasks, live_ev, language)

    def run_int():
        return _call_groq(query, category, "international", int_tasks, live_ev, language)

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
