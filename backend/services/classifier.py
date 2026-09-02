"""
Formulation classification decision tree — 0 LLM calls.

Gate sequence (from ip-sakti-formulation-classification.md):

  Q1: External use only, no therapeutic claim?
       ├─ Yes → COSMETIC
       └─ No  ↓

  Q2: Consumed as food/supplement, no disease-cure claim?
       ├─ Yes → AYURVEDA_AAHAR
       └─ No  ↓

  Q3: Formulation and method exactly match a First-Schedule
      authoritative text, unmodified?
       ├─ Yes → CLASSICAL
       └─ No  ↓

  Q4: Purified, standardised extract/fraction from a single plant
      source, standardised to a defined active moiety?
       ├─ Yes → PHYTOPHARMACEUTICAL
       └─ No  ↓

  Q5: Deviates from classical text but follows Ayurvedic principles
      (proprietary variant), no new clinical safety/efficacy data?
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
        "Is this formulation for external use only, with no therapeutic claim "
        "(e.g. a cream, lotion, or hair oil)?",
        "cosmetic",
        None,
    ),
    (
        "Q2",
        "Is this formulation consumed as a food or dietary supplement, "
        "making no disease-cure claim (e.g. a health supplement or Ayurveda-Aahar product)?",
        "ayurveda_aahar",
        None,
    ),
    (
        "Q3",
        "Does the formulation and its manufacturing method exactly match an authoritative "
        "First-Schedule classical text (e.g. Ayurvedic Formulary of India), "
        "with absolutely no modifications?",
        "classical",
        None,
    ),
    (
        "Q4",
        "Is this a purified, standardised extract or fraction from a single plant source, "
        "standardised to a defined active moiety (phytopharmaceutical)?",
        "phytopharmaceutical",
        None,
    ),
    (
        "Q5",
        "Does this formulation deviate from the classical text but still follow Ayurvedic "
        "principles (e.g. a proprietary combination or modified classical), "
        "with no new clinical safety or efficacy data generated?",
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
