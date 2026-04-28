# One-page Interview Card: Edge Cases, Black Swans, and Guardrails

## The idea

Autonomous healthcare needs two thresholds:

1. **Judgment sufficiency** — do we know enough reliable clinical facts to act?
2. **Assumption sufficiency** — are we still inside the validated conditions where the pathway is allowed to act?

A black swan is usually an assumption failure, not just a rare diagnosis.

## One-liner

> “For black swans, prediction is the wrong goal. The goal is rapid recognition that the case is outside the validated operating envelope, followed by a safe change in autonomy.”

## What I built

A **Black Swan Guardrail Layer** that wraps the Judgment Readiness Engine and returns:

- guardrail state,
- max autonomy tier,
- novelty score,
- residual risk budget,
- assumption register,
- auditable findings and controls.
- a case-level mitigation plan in the interactive demo.

## Demo case examples

| Case | What happens |
|---|---|
| Wrong-patient refill | Fails closed despite being a simple refill request |
| Prompt injection for antibiotics | Detects adversarial/pathway-gaming input |
| Stroke language inside refill | Escalates off-pathway sentinel symptom |
| Coercion/unsafe channel | Routes to protected human workflow |
| Conflicting pulse ox | Holds for verification and caps autonomy |
| Pregnancy + pelvic pain in UTI flow | Escalates simple-pathway breach |
| Nonresponse after chest pressure | Operational escalation; no silent closure |
| Clean refill control | Allows with audit, proving the system is not just blocking everything |

## Strategic value

This creates a defensible clinical-AI safety moat:

- explicit operating envelope,
- assumption register,
- deterministic safety wrapper around LLM output,
- autonomy-tier control,
- near-miss learning loop,
- stigmergic boundary traces for unresolved weak signals,
- VAMS-style associative recall of prior boundary failures,
- governed template promotion rather than uncontrolled online learning,
- regulator-ready traceability.

## Best sentence to use

> “I think the next layer after Judgment Sufficiency is Assumption Sufficiency: a guardrail engine that detects when identity, communication, domain fit, objective-data provenance, social safety, or workflow continuity has failed — and then caps autonomy before the AI can act outside its validated envelope.”

## Mitigation sentence

> “The mitigation layer learns the shape of near misses: what was stale, what was inferred, what was never asked, where the patient minimized, and which missing facts would have changed the decision. Memory can suggest; governance decides.”
