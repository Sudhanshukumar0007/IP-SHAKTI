# IP-SAKTI Sahayak — evaluation test cases

Each case names what it's actually regression-testing, not just what category it falls in — several of these exist specifically because they broke once already.

---

## 1. Simple lookups (should never enter the classification loop)

| ID | Query | Expected behavior | Regression for |
|---|---|---|---|
| L1 | "What does Section 3 of the Patents Act say?" | Answers directly via retrieve-and-generate. **Must not** trigger `classify_formulation` or ask any gate question. | The original intent-gate bug — this exact query previously got misrouted into the classifier and resolved to `cosmetic`. |
| L2 | "What is the Patent Cooperation Treaty?" (international mode) | Direct answer, `international_ip` domain, no classification loop. | Confirms the intent gate works for international-mode lookups too, not just national. |

## 2. Clean, unambiguous classification

| ID | Query | Expected behavior | Regression for |
|---|---|---|---|
| C1 | "We make a hair oil for external use only, no therapeutic claims." | Resolves to `cosmetic` in one pass, no clarifying questions needed (all gates answerable from the text as given). | Baseline — confirms the classifier still handles the easy case fast after the LLM-extraction rework. |
| C2 | "This is a Chyawanprash made exactly per the Bhaishajya Ratnavali formula, no changes." | Resolves to `classical`, and Q3 specifically shows a retrieval-backed comparison against the pharmacopoeial text in the trace — not a self-reported "yes." | Fix 7b (retrieval-backed Q3). |

## 3. Genuine classification ambiguity — must ask, not guess

| ID | Query | Expected behavior | Regression for |
|---|---|---|---|
| A1 | The full Ashwagandha + black pepper + ginger monster query from earlier testing | Classifier does **not** silently resolve to `ayurveda_aahar`. At minimum, Q2 (disease-cure claim vs. supplement claim) and Q4 (single vs. multi-plant source) come back "unknown" from the extraction pass and trigger the clarifying-question loop. | The exact bug this whole fix cycle started from. |
| A2 | "Our product enhances bioavailability of a known compound by 40%, verified in vitro." (isolated, without the rest of A1's context) | Q2 should resolve "unknown," not a confident yes/no either way — this phrasing is genuinely borderline between a supplement claim and a drug-performance claim. | Checks the extraction pass doesn't overcorrect into false confidence on a narrower version of the same ambiguity. |

## 4. Multi-domain compound queries

| ID | Query | Expected behavior | Regression for |
|---|---|---|---|
| M1 | "What NBA approvals do we need before filing a patent on this formulation?" | Task gets tagged with both `biodiversity` and `patent` domains; retrieved evidence includes both Biological Diversity Act and Patents Act sources; answer addresses both, not just one. | The dual-domain design added specifically for this question shape. |
| M2 | The full four-part monster query (classification + India IP/ABS + international IP + overall assessment) | All four sub-questions produce an executed task — none silently vanish. Task-coverage check confirms 4/4 (or however many the supervisor generates) before the verification gate reports status. | Fix 1/2 — this is the exact query where T4/T5 disappeared and the gate still reported "VERIFIED." |

## 5. Jurisdiction handling

| ID | Query | Expected behavior | Regression for |
|---|---|---|---|
| J1 | Any classification query, `jurisdiction_mode` field omitted entirely | Request rejected with a 400 error — not silently defaulted to `national` or `both`. | The required-field fix for fix 1/2. |
| J2 | Same query, `jurisdiction_mode: both` | Two separate generation calls fire (confirm via timing — should complete in roughly single-call latency, not double, if parallel execution is working), and the response contains distinct `national_answer` / `international_answer` fields, never one blended block. | The isolation + parallel-execution fix. |

## 6. Abstention — must decline, not guess

| ID | Query | Expected behavior | Regression for |
|---|---|---|---|
| O1 | "What's the trademark registration process for this product in Japan?" (a jurisdiction genuinely outside corpus scope) | Explicit abstain with a stated reason — never a fabricated answer about Japanese trademark law. | The core "never fabricate authority" requirement — no prior specific bug, but the most important thing in the whole system to verify works. |
| O2 | A task deliberately constructed to produce an empty/invalid `domains` array (may need a synthetic/forced test rather than a natural query) | Task added to `task_results` with `sufficient=False` and the exact abstain reason for invalid domain tags — visible in the trace, not silently dropped. | The domain-validation fallback fix. |

## 7. TKDL handling

| ID | Query | Expected behavior | Regression for |
|---|---|---|---|
| T1 | "Is TKDL relevant for protecting our formulation?" | Templated, category-aware answer grounded in the fixed TKDL definition plus retrieved Biological Diversity Act provisions — never a bare "insufficient evidence" abstain. | Fix 4. |

## 8. Multilingual — outcome parity, not chunk-ID equality

| ID | Query | Expected behavior | Regression for |
|---|---|---|---|
| H1 | L1's query, submitted in Hindi | Resolves to the same act (Patents Act) and section (Section 3) as L1 — chunk IDs may differ, but the cited act/section and substantive conclusion should match. | Multilingual retrieval quality — also the test to watch for the BM25-dilution risk flagged separately. |
| H2 | C1's query, submitted in Hindi | Same formulation category (`cosmetic`) as C1. | Same as above, applied to the classification path rather than a lookup. |

## 9. Ingestion/citation correctness (deterministic checks, not judge-scored)

| ID | Check | Expected behavior | Regression for |
|---|---|---|---|
| I1 | Query anything that retrieves from a Patents Act amendment document | `section_or_article` metadata resolves to an actual section number, not `Unknown`, and correctly reflects the *target* section being amended (not the amendment act's own internal clause numbering). | Fix 5a — the Section-3-vs-Section-100 misattribution bug specifically. |
| I2 | Query anything likely to retrieve from the duplicated `amendment_2002_en` / `amendment_2002_06_en` files | Retrieved evidence contains no duplicate chunk content. | Corpus dedup cleanup + fix 6. |

---

## Notes for the harness
- L1, L2, C1 should be fast/cheap regression checks run on every change — they catch the two most basic ways this system can silently misbehave (wrong routing, wrong classification) without needing the judge model at all.
- I1 and I2 are pure metadata checks — script these directly against retrieved chunk metadata, no LLM judge involved.
- A1, A2, M1, M2 are the cases most worth watching over time as the corpus grows — these are the ones where "looks right" and "is actually right" diverge most easily.
