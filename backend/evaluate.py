import json
import os
import csv
import time
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Ensure we're running from backend directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from graph.graph import graph

class JudgeScore(BaseModel):
    score: int = Field(description="1 for Pass, 0 for Fail")
    rationale: str = Field(description="Brief explanation of the score")

from graph.nodes import retry_429, _get_llm

@retry_429
def run_judge(metric: str, query: str, state: dict, expected: str) -> JudgeScore:
    """Uses LLM-as-a-judge to evaluate semantic metrics via Groq."""
    from langchain_groq import ChatGroq
    judge_key = os.getenv("JUDGE_GROQ_API_KEY", os.getenv("GROQ_API_KEY"))
    judge_key_2 = os.getenv("GROQ_API_KEY2", judge_key)
    
    primary_llm = ChatGroq(
        model=os.getenv("JUDGE_MODEL", os.getenv("LLM_MODEL")),
        api_key=judge_key,
        temperature=0,
    )
    fallback_llm = ChatGroq(
        model=os.getenv("JUDGE_MODEL", os.getenv("LLM_MODEL")),
        api_key=judge_key_2,
        temperature=0,
    )
    llm = primary_llm.with_fallbacks([fallback_llm]).with_structured_output(JudgeScore)
    
    prompt = f"""You are an expert legal AI evaluator evaluating an IP/Regulatory RAG pipeline.
    
    Metric to evaluate: {metric}
    
    User Query: {query}
    Expected Behavior: {expected}
    
    Actual System State Output:
    Formulation Category: {state.get('formulation_category')}
    National Answer: {json.dumps(state.get('national_answer', {}), indent=2)}
    International Answer: {json.dumps(state.get('international_answer', {}), indent=2)}
    Clarification Required: {state.get('clarification_required')}
    Pending Clarification Question: {state.get('pending_clarification')}
    Execution Trace: {json.dumps(state.get('execution_trace', []), indent=2)}
    
    Score 1 for Pass (meets expected behavior for this metric), 0 for Fail. Provide a brief rationale.

    CRITICAL EVALUATION RULES:
    1. Vacuous Truth Failure: If the Expected Behavior requires checking a property of a collection (e.g. "no duplicate chunks", "all answers contain X"), and that collection is empty (e.g. 0 retrieved chunks, no answers), you MUST SCORE 0. An empty collection never satisfies a condition meant to evaluate the items within it.
    2. Clarification Is A Valid Output: If 'Pending Clarification Question' is set, the system is mid-classification and returned a gate question. If the Expected Behavior EXPLICITLY says something like "Q2 resolves unknown" or "trigger clarify", then a pending clarification question IS the correct output and you MUST SCORE 1. If the Expected Behavior requires a final answer (not a question), a pending clarification with no answer MUST SCORE 0.
    """
    
    # We use a simple prompt for the LLM-as-a-judge
    try:
        from langchain_core.messages import SystemMessage
        res = llm.invoke([SystemMessage(content=prompt)])
        return res
    except Exception as e:
        return JudgeScore(score=0, rationale=f"Judge failed to evaluate: {str(e)}")

def check_citation_existence(state: dict) -> tuple[int, str]:
    """Deterministic check: do all cited chunks exist in retrieved_chunks?"""
    # Collect all retrieved chunk IDs
    retrieved_ids = set()
    for task_res in state.get("task_results", []):
        for chunk in task_res.get("retrieved_chunks", []):
            retrieved_ids.add(chunk["chunk_id"])
            
    # Check citations
    missing = []
    citations = state.get("national_citations", []) + state.get("international_citations", [])
    if not citations:
        return 0, "Vacuous truth failure: No citations returned by the system to evaluate."

    for cit in citations:
        if cit.get("chunk_id") and cit["chunk_id"] not in retrieved_ids:
            missing.append(cit["chunk_id"])
            
    if missing:
        return 0, f"Found {len(missing)} cited chunks not in retrieval set: {missing[:3]}"
    return 1, "All citations correspond to retrieved chunks."

def evaluate_test(test: dict) -> dict:
    print(f"\n--- Running Test {test['id']} ---")
    
    if test["id"] == "J1":
        start_time = time.time()
        try:
            from fastapi.testclient import TestClient
            from main import app
            client = TestClient(app)
            # Send mode: null to see if FastAPI rejects it
            payload = {}
            if test.get("mode") is not None:
                payload["jurisdiction_mode"] = test["mode"]
                
            res = client.post("/session", json=payload)
            error = f"HTTP {res.status_code}: {res.text}"
            passed = res.status_code in (400, 422)
        except Exception as e:
            error = str(e)
            passed = False
            
        duration = time.time() - start_time
        return {
            "test_id": test["id"],
            "query": test["query"],
            "duration_sec": round(duration, 2),
            "error": error if not passed else None,
            "overall_pass": 1 if passed else 0,
            "rationale": "J1 properly rejected by FastAPI endpoint" if passed else f"J1 failed: {error}"
        }

    state = {
        "raw_query": test["query"],
        "jurisdiction_mode": test["mode"],
        "language": "hi" if test["id"].startswith("H") else "en",
        "session_id": f"eval_{test['id']}",
        "execution_trace": [],
        "is_informational_lookup": False,
        "clarification_history": [],
        "tasks": [],
        "task_results": []
    }
    
    start_time = time.time()
    try:
        final_state = graph.invoke(state)
        error = None
    except Exception as e:
        final_state = state
        error = str(e)
        print(f"Graph execution failed: {error}")
        
    duration = time.time() - start_time
    
    results = {
        "test_id": test["id"],
        "query": test["query"],
        "duration_sec": round(duration, 2),
        "error": error
    }

    # Deterministic checks
    if error:
        if "429" in error or "413" in error:
            results["overall_pass"] = 0
            results["judge_rationale"] = f"Infrastructure Failure: {error}"
            results["citation_existence_score"] = 0
            results["citation_existence_rationale"] = "Skipped due to Infrastructure Failure"
        else:
            results["overall_pass"] = 0
            results["judge_rationale"] = f"Runtime Exception: {error}"
            results["citation_existence_score"] = 0
            results["citation_existence_rationale"] = "Skipped due to Runtime Exception"
            
        time.sleep(2.0)
        return results

    cit_score, cit_rat = check_citation_existence(final_state)
    results["citation_existence_score"] = cit_score
    results["citation_existence_rationale"] = cit_rat
    
    # Specific ID deterministic checks
    if test["id"] in ["L1", "L2"]:
        passed = final_state.get("formulation_category") == "informational"
        ans_nat = final_state.get("national_answer", {})
        ans_int = final_state.get("international_answer", {})
        clar = final_state.get("clarification_required")
        has_answer = bool(ans_nat) or bool(ans_int)
        
        if passed and has_answer and not clar:
            results["routing_integrity_score"] = 1
            results["routing_integrity_rationale"] = "informational lookup flag with answer provided and no clarification requested"
        else:
            results["routing_integrity_score"] = 0
            results["routing_integrity_rationale"] = f"Failed. formulation_category='{final_state.get('formulation_category')}', has_answer={has_answer}, clar={clar}"
    elif test["id"] in ["I1"]:
        # check if section_or_article is not unknown
        passed = True
        chunks_checked = 0
        for task_res in final_state.get("task_results", []):
            for c in task_res.get("retrieved_chunks", []):
                chunks_checked += 1
                if c["metadata"].get("section_or_article") == "Unknown":
                    passed = False
        
        if chunks_checked == 0:
            results["metadata_integrity_score"] = 0
            results["metadata_integrity_rationale"] = "Vacuous truth failure: No chunks retrieved to evaluate."
        else:
            results["metadata_integrity_score"] = 1 if passed else 0
            results["metadata_integrity_rationale"] = "No Unknown sections in amendment retrieval"
    
    # LLM Judge semantic check for expected behavior
    judge_res = run_judge("Expected Behavior / Claim Entailment", test["query"], final_state, test["expected_behavior"])
    results["judge_score"] = judge_res.score
    results["judge_rationale"] = judge_res.rationale
    
    results["overall_pass"] = 1 if judge_res.score == 1 else 0
    time.sleep(2.0)
    return results

def main():
    import json
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Evaluate IP-SHAKTI Pipeline")
    parser.add_argument("--tier", type=str, default="fast", choices=["fast", "periodic", "needs_confirmation", "all"],
                        help="Which tier of tests to run.")
    parser.add_argument("--test", type=str, help="Comma-separated list of specific test IDs to run (overrides --tier)")
    args = parser.parse_args()

    with open("test_cases.json", "r", encoding="utf-8") as f:
        test_cases = json.load(f)
        
    if args.test:
        target_ids = [t.strip() for t in args.test.split(",")]
        filtered_tests = [t for t in test_cases if t["id"] in target_ids]
        print(f"Running specific tests: {target_ids}")
    else:
        if args.tier == "all":
            filtered_tests = test_cases
            print("Running ALL tests.")
        else:
            filtered_tests = [t for t in test_cases if t.get("tier") == args.tier]
            print(f"Running {args.tier} tier tests only. Found {len(filtered_tests)} tests.")

    if not filtered_tests:
        print("No tests matched the criteria.")
        return

    results = []
    for t in filtered_tests:
        res = evaluate_test(t)
        results.append(res)
        # Sleep slightly to avoid rapid-fire rate limits
        time.sleep(2.0)
        
    import csv
    with open("eval_results.csv", "w", newline="", encoding="utf-8") as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
            
    # Write summary
    passed = sum(1 for r in results if r.get("overall_pass") == 1)
    total = len(results)
    with open("eval_summary.md", "w", encoding="utf-8") as f:
        f.write(f"# Eval Summary\n\n**Total:** {total}\n**Passed:** {passed}\n**Failed:** {total - passed}\n")
        f.write("\n## Details\n")
        for r in results:
            f.write(f"- **{r['test_id']}**: {'PASS' if r.get('overall_pass') == 1 else 'FAIL'} - {r.get('judge_rationale', r.get('rationale', ''))}\n")
            
    print(f"\nEval complete. {passed}/{total} passed. Results saved to eval_results.csv and eval_summary.md")

if __name__ == "__main__":
    main()
