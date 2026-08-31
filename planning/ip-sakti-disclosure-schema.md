# IP-SAKTI Sahayak — IP posture & ABS disclosure schema

Defines what the generation node must state per formulation category. Hardcodes the *dimensions* that must always be addressed, never the *content* — every field's actual value comes from retrieval against the jurisdiction-appropriate corpus, so the answer stays correct as law amends instead of going stale the day an act changes.

This schema is the generation node's output contract — it slots directly into the LangGraph flow after the formulation-classification node and the jurisdiction router.

---

## The six required fields (every category, every jurisdiction)

| # | Field | What it captures |
|---|---|---|
| 1 | `ip_regimes_applicable` | Which of patent / GI / trademark / design / copyright / trade secret / plant-variety realistically apply |
| 2 | `patentability_posture` | open / barred / conditional — with the retrieved basis (e.g. Section 3(p), a specific treaty article) |
| 3 | `abs_exposure` | Whether Biological Diversity Act prior approval is needed before any IP filing using an India-sourced biological resource |
| 4 | `tkdl_relevance` | Whether the Traditional Knowledge Digital Library is a relevant defense/prior-art tool here |
| 5 | `regulatory_classification` | Which act/schedule/rule governs manufacturing and licensing for this category |
| 6 | `standing_disclaimer` | The "information, not legal advice" line — unconditional, present on every answer regardless of category |

**Generation contract**: all six fields must be populated on every answer. A field can legitimately resolve to "not applicable to this category" (e.g. TKDL relevance for a cosmetic is usually low), but it can never be silently omitted — an omitted field is indistinguishable from a forgotten one, and this is exactly the kind of gap that turns into a fabricated-authority risk later.

---

## How weighting differs by category (guidance for prompt design, not fixed content)

| Category | Field that tends to dominate | Why |
|---|---|---|
| Classical | Patentability posture | Usually resolves to "barred" (Section 3(p) territory) — TKDL becomes the main protective lever since the base formulation is largely closed to patenting |
| Patent-or-proprietary | Patentability posture + IP regimes applicable | Posture is genuinely conditional (narrow scope over the specific combination); weight often shifts toward trade secret/trademark alongside any patent claim |
| New/non-classical drug | Patentability posture + regulatory classification | Genuine patent potential, but gated on clinical safety/efficacy data existing; new-drug approval is its own long regulatory track |
| Phytopharmaceutical | ABS exposure | Accessing/standardizing a plant fraction usually requires Biodiversity Board approval *before* any IP filing, not after |
| Ayurveda-Aahar/nutraceutical | IP regimes applicable + regulatory classification | Patent rarely relevant; trademark/design/GI dominate; FSSAI's no-disease-claim restriction is the regulatory constraint that matters most |
| Cosmetic | IP regimes applicable | Similar to Aahar — trademark/design/copyright dominate; ABS still applies if a plant extract was accessed |

---

## Jurisdiction interaction

Every field is generated once per jurisdiction the toggle has selected:
- **India / International**: one full six-field set, sourced only from that jurisdiction's collection
- **Both**: two full six-field sets, rendered as the two labeled sections defined in the storage-schema doc — never merged into one blended set of six values

## Failure mode this prevents
Without this fixed checklist, a generation pass could produce a plausible-sounding answer that happens to skip ABS exposure entirely for a phytopharmaceutical query — the single most consequential omission for that category. Making all six fields mandatory output (not just "topics the model should probably cover") turns that from a prompt-engineering hope into a structural guarantee that can be validated on every response before it's served.
