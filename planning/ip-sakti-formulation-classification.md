# IP-SAKTI Sahayak — formulation classification tree

Fixed decision tree, not an open LLM guess. Implemented as explicit conditional edges in the LangGraph classify node. Every question is asked directly to the user, since the filer knows their own product and manufacturing process — the assistant never infers this from context.

---

## Gate sequence

```
Q1: External use only, no therapeutic claim?
 ├─ Yes → COSMETIC
 └─ No ↓

Q2: Consumed as food/supplement, no disease-cure claim?
 ├─ Yes → AYURVEDA-AAHAR / NUTRACEUTICAL
 └─ No ↓

Q3: Formulation and method exactly match a First-Schedule
    authoritative text, unmodified?
 ├─ Yes → CLASSICAL / GENERIC MEDICINE
 └─ No ↓

Q4: Purified, standardized extract/fraction from a single plant
    source, standardized to a defined active moiety?
 ├─ Yes → PHYTOPHARMACEUTICAL
 └─ No ↓

Q5: Deviates from the classical text but still follows Ayurvedic
    principles (proprietary variant), with no new clinical
    safety/efficacy data generated?
 ├─ Yes → PATENT-OR-PROPRIETARY MEDICINE
 └─ No → NEW / NON-CLASSICAL DRUG
```

Each gate has exactly one live branch continuing — the tree never asks the user (or the model) to choose between two remaining categories at once.

## Design rationale
- Cosmetic and Ayurveda-Aahar are peeled off first — least ambiguous to answer, lowest risk of a wrong early turn cascading into the harder classical/phytopharma/proprietary/new distinctions.
- Classical vs. phytopharmaceutical vs. proprietary vs. new-drug is the genuinely hard boundary; asking the user directly (they know their own build process) removes the inference risk entirely instead of having the assistant guess from a description.

## UI handling for contested edge cases
- **Same product, cosmetic and internal-use variants** — one classification per product-as-filed, not per ingredient. A dual-use product runs through the tree twice (once per variant), never gets a combined leaf.
- **Classical formulation, modern manufacturing process** (e.g. tablet instead of traditional decoction) — this is the Q3/Q5 boundary and the most likely spot for a contested answer. Add an inline example/tooltip at this exact question in the UI rather than leaving it as a bare yes/no.

## Output of this node
Once a leaf category is reached, it's passed downstream (to the jurisdiction router / retrieval node) as a fixed enum value: `cosmetic | ayurveda_aahar | classical | phytopharmaceutical | proprietary | new_drug`. This value also determines what the generation step must state about IP posture and ABS exposure for that category — that mapping (category → required disclosures) is the next thing to define once this tree is confirmed.
