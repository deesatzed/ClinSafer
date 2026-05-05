# Mitigation Plan: Dynamic Boundary Intelligence

## Purpose

This plan updates the demo and implementation direction after reviewing the
local `rustigmergic-logswarm-engine` stigmergic trace repo and
`Vamplify-Claude` VAMS/action-memory repo.

The mitigation goal is not to make the app a more aggressive AI doctor. The goal is to make the system better at:

- knowing what it does not know,
- separating patient statements from clinical facts,
- remembering prior boundary failures,
- learning which missing facts matter,
- reducing avoidable physician routing and churn,
- and preserving strict governance before learned patterns change production behavior.

## Mitigation Layers

### 1. Current Deterministic Controls

Already active in `ver2`:

- Transcript-first intake for pasted real encounter dialogue.
- Input Coverage Audit proving every submitted line is used, reclassified, or explicitly held for review.
- Concept reclassification for wrong or generic labels, including manual `red_flag`.
- MUD map for missing, uncertain, distorted, contradictory, objective-needed, and remote-unknowable facts.
- CLEAR next-question selection.
- Black Swan Guardrails for assumption failure and autonomy caps.
- Statement-vs-fact display in Interview Mode.
- Autonomy boundary showing allowed and blocked actions.
- Final Recommendations page focused on action, clinician handoff, patient language, and immediate boundaries.
- Bounded multi-role LLM candidate pipeline:
  - extractor,
  - boundary reasoner,
  - adversarial verifier,
  - cognitive bias auditor.
- Reasoning Integrity Check for anchoring, premature closure, confirmation bias, search satisficing, omission bias, diagnostic momentum, framing/ascertainment risk, availability bias, and overconfidence.

Mitigation role:

> Prevent unsafe action in the current case.

Safety boundary:

- LLM roles propose candidate signals only.
- Reasoning-integrity findings are cognitive forcing actions, not claims about clinician character.
- Unknown/unmapped rows are not neutral.
- The most-restrictive governor still decides final autonomy.

### 2. Stigmergic Boundary Trace

Borrowed from `rustigmergic-logswarm-engine`:

- multi-region shared trace field,
- different decay rates by signal type,
- accumulation of repeated weak signals,
- persistence of unresolved source conflict or nonresponse,
- alert-fatigue controls that do not suppress critical events.

Recommended app layer:

```text
BoundaryTraceField
  claims
  objective
  source_conflict
  social_workflow
  temporal_staleness
  outcome_feedback
```

Mitigation role:

> Stop weak but repeated uncertainty signals from disappearing between turns.

Implemented foundation:

- `jre/boundary_trace.py`
- `tests/test_boundary_trace.py`

### 3. Boundary Self-Model

Future related extension, not implemented in this pass:

- online baselines,
- Welford mean/variance,
- deviation and trend detection,
- sparse peak detection.

Recommended app translation:

```text
BoundarySelfModel by pathway:
  refill with chronic disease
  pediatric caregiver report
  chest discomfort with reassurance
  mental-health minimization
  post-discharge drift
  telemedicine-only limitation
```

Mitigation role:

> Detect when a case’s uncertainty shape deviates from the normal safe pathway, even if no single rule screams.

### 4. Falsifier Planning

Future related extension, not implemented in this pass:

- generate dangerous hypothesis,
- generate plausible alternatives,
- ask what evidence would disprove danger,
- ask what evidence would disprove reassurance,
- choose the lowest-burden next test or question.

Mitigation role:

> Convert “we are worried” into “here is what would change the decision.”

Interview Mode display target:

```text
What Would Change The Decision?
```

### 5. VAMS Near-Miss Recall

Borrowed from `Vamplify-Claude`:

- sparse Hopfield attractor memory,
- Hebbian strengthening,
- anti-Hebbian weakening,
- associative recall,
- pattern completion,
- typed memory edges.

Recommended app layer:

```text
ClinicalBoundaryEncoder
  -> sparse case signature
  -> AssociativeCaseMemory
  -> near-miss analogue
  -> missing nodes and falsifiers
  -> deterministic validator
```

Mitigation role:

> Remember the shape of prior near misses from partial cues, especially when the relevant pattern is uncertainty rather than diagnosis.

Safety boundary:

- Memory can propose candidate risks, questions, and falsifiers.
- Memory cannot authorize clinical action.
- Memory-only recall cannot create a T0/T1 hard stop without deterministic support.
- Every recalled analogue needs confidence, evidence, and provenance.
- PHI must be excluded or de-identified.

Implemented foundation:

- `jre/associative_memory.py`
- `tests/test_associative_memory.py`

### 6. Governed Template Promotion

AI and memory can suggest:

- new nodes,
- new node ranges,
- new distributions,
- new expert-system rules,
- new domain templates,
- new near-miss archetypes.

They cannot directly promote themselves into production behavior.

Promotion requires:

- deterministic schema validation,
- source/evidence validation,
- simulation cases,
- clinician/admin review,
- outcome monitoring,
- rollback path.

Mitigation role:

> Let the system learn without turning production medicine into uncontrolled online learning.

### 7. Business And Churn Mitigation

Safety and business goals align when the system knows the specific blocker.

Revenue and churn levers:

- ask one targeted question before expensive routing,
- preserve safe automation when the gap is easy to close,
- explain why a visit or clinician review is needed,
- avoid vague alarming escalation language,
- reduce repetitive low-yield questioning,
- route with a boundary map instead of a raw transcript.

Mitigation role:

> Reduce avoidable friction while increasing persistence around unresolved high-consequence uncertainty.

## Updated Demo Requirements

The interview demo should show:

1. A routine-looking case.
2. Statement-vs-fact separation.
3. Missing, uncertain, stale, contradictory, or socially distorted signals.
4. Autonomy cap.
5. Next best question.
6. Mitigation plan.
7. Foundational memory/tracing layer:
   - implemented stigmergic boundary trace,
   - implemented VAMS-style near-miss recall,
   - governed template promotion.

The app now includes a `Mitigation Plan` analysis section in `interactive_demo.py`.

## Proof Harness

Run:

```bash
python scripts/prove_mitigation_flow.py
```

This uses the same JRE, BSG, and interactive-demo section builders used by the browser demo. It compares:

- `showcase-001-stale-ace-refill-ckd-nsaid`
- `RF-002-good-refill-readyish`

Expected proof behavior:

- the hero refill case is capped, blocks autonomous refill, lights up boundary traces, and recalls a refill near-miss pattern;
- the clean refill control is allowed with audit, has no blocked actions, and recalls a clean refill analogue;
- both cases include the visible mitigation layers:
  - current deterministic controls,
  - stigmergic boundary trace,
  - VAMS near-miss recall,
  - governed template promotion,
  - business mitigation.

The backend now also includes `jre/cognitive_bias_field.py`, which can attach
advisory bias entropy, information-gain ranking, hypothesis survival,
disposition fragility, fresh-eyes payloads, and cognitive friction actions to
JRE/Any Dispo analysis. This layer is not a clinician-bias diagnosis and cannot
authorize care.

## Implementation Order

1. Keep deterministic controls as the production safety base.
2. Add visible mitigation planning to the demo.
3. Add a deterministic `ClinicalBoundaryEncoder`.
4. Seed synthetic near-miss memories for VAMS-style recall in the Any Dispo path.
5. Wire `BoundaryTraceField` into per-case and cross-case review traces.
6. Add backend cognitive-bias field reports for bias entropy, fresh-eyes review,
   disposition fragility, and cognitive friction prompts.
7. Surface cognitive-bias field output in the API/demo UI.
8. Add clinician feedback capture tied to memory acceptance/rejection.
9. Add governance queue for proposed rules/templates.
10. Add dashboard metrics for:
   - avoidable routing,
   - clarification yield,
   - abandonment after risk,
   - confirmed near misses,
   - false-positive recalls,
   - bias-fragility and cognitive-friction triggers,
   - template-promotion outcomes.

## Interview Line

> The learning layer should not learn to practice medicine autonomously. It should learn where interpretation boundaries fail, which missing facts matter, which clarification questions have yield, and which near-miss patterns deserve governed promotion.
