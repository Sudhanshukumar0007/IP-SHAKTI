"""
Formulation classification decision tree — 0 LLM calls.

Gate sequence (from ip-sakti-formulation-classification.md):

  Q1: Is this formulation exclusively for external use (e.g., a cream, lotion, or hair oil) making no therapeutic or disease-curing claims?
       ├─ Yes → COSMETIC
       └─ No  ↓

  Q2: Is this product consumed strictly as a food or dietary supplement (e.g., Ayurveda-Aahar) with no therapeutic claims, and it is NOT a modified classical Ayurvedic drug or proprietary medicine?
       ├─ Yes → AYURVEDA_AAHAR
       └─ No  ↓

  Q3: Does this formulation and its manufacturing method exactly match an authoritative First-Schedule classical text (e.g., Ayurvedic Formulary of India) with absolutely NO modifications to ingredients, ratios, or delivery methods?
       ├─ Yes → CLASSICAL
       └─ No  ↓

  Q4: Is this a purified, standardised extract or fraction from a single plant source, standardised to a defined active moiety (i.e., a Phytopharmaceutical)?
       ├─ Yes → PHYTOPHARMACEUTICAL
       └─ No  ↓

  Q5: Does this formulation deviate from classical texts (e.g., modified ratio, new delivery method) but still follow Ayurvedic principles (Proprietary Ayurvedic Medicine), with NO new clinical safety or efficacy data generated?
       ├─ Yes → PROPRIETARY
       └─ No  → NEW_DRUG

Each gate has exactly one live branch. The user always answers Yes/No —
the assistant never infers the category from free text.
"""

from __future__ import annotations
from typing import Optional


# Each tuple: (gate_id, question_text, yes_leaf, no_leaf_or_None)
# no_leaf_or_None is None for Q1–Q4 (continue to next gate on "no"),
# and "new_drug" for Q5 (both branches are leaves at Q5).
QUESTIONS: list[tuple[str, str, str, Optional[str]]] = [
    (
        "Q1",
        "Is this formulation exclusively for external use (e.g., a cream, lotion, or hair oil) making no therapeutic or disease-curing claims?",
        "cosmetic",
        None,
    ),
    (
        "Q2",
        "Is this product consumed strictly as a food or dietary supplement (e.g., Ayurveda-Aahar) with no therapeutic claims, and it is NOT a modified classical Ayurvedic drug or proprietary medicine?",
        "ayurveda_aahar",
        None,
    ),
    (
        "Q3",
        "Does this formulation and its manufacturing method exactly match an authoritative First-Schedule classical text (e.g., Ayurvedic Formulary of India) with absolutely NO modifications to ingredients, ratios, or delivery methods?",
        "classical",
        None,
    ),
    (
        "Q4",
        "Is this a purified, standardised extract or fraction from a single plant source, standardised to a defined active moiety (i.e., a Phytopharmaceutical)?",
        "phytopharmaceutical",
        None,
    ),
    (
        "Q5",
        "Does this formulation deviate from classical texts (e.g., modified ratio, new delivery method) but still follow Ayurvedic principles (Proprietary Ayurvedic Medicine), with NO new clinical safety or efficacy data generated?",
        "proprietary",
        "new_drug",   # "no" at Q5 → new_drug (last gate, both branches are leaves)
    ),
]

# All valid leaf category values
FORMULATION_CATEGORIES = frozenset([
    "cosmetic", "ayurveda_aahar", "classical",
    "phytopharmaceutical", "proprietary", "new_drug",
])


def classify_step(
    answers: list[str],
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Walk the gate tree given the answers collected so far.

    Parameters
    ----------
    answers : list of "yes" | "no" strings, one per gate answered so far.

    Returns
    -------
    (resolved, category, next_question)

    - resolved=True  → category is the leaf value; next_question is None.
    - resolved=False → category is None; next_question is the gate text to ask.

    Raises
    ------
    ValueError if any answer is not "yes" or "no".
    """
    for i, (gate_id, question, yes_leaf, no_leaf) in enumerate(QUESTIONS):
        if i >= len(answers):
            # Haven't asked this question yet — return it to the frontend
            return False, None, question

        answer = answers[i].strip().lower()
        if answer not in ("yes", "no"):
            raise ValueError(
                f"Gate {gate_id} answer must be 'yes' or 'no', got: {answer!r}"
            )

        if answer == "yes":
            return True, yes_leaf, None

        # answer == "no"
        if no_leaf is not None:
            # Q5 "no" branch is also a leaf
            return True, no_leaf, None
        # Otherwise continue to the next gate

    # All gates answered "no" — shouldn't normally reach here since Q5 always resolves
    return True, "new_drug", None


def question_at_index(index: int) -> Optional[str]:
    """Return the question text for the gate at position `index`, or None if out of range."""
    if 0 <= index < len(QUESTIONS):
        return QUESTIONS[index][1]
    return None
