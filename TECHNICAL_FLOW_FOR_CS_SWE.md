# Technical Flow For CS / SWE Review

## Purpose

This document explains the methodology and technology behind the Judgment Readiness Engine demo at a level suitable for a computer scientist, software engineer, or technical healthcare AI reviewer.

It separates:

- **implemented now**: current `ver2` JRE / BSG / demo behavior,
- **next architecture**: dynamic expert-system software, probabilistic nodes, stigmergic traces, VAMS memory, and governed template promotion.

## 1. Current Input Pipeline

The current app starts with a structured `CaseInput`:

- `PatientContext`: age, domain, chief concern, modality, known conditions, language barrier, caregiver status.
- `Statement[]`: each question/answer pair with optional concept, source, and metadata.
- `ground_truth`: synthetic demo labels.

Current flow:

```text
CaseInput
  -> JudgmentReadinessEngine.evaluate()
  -> BlackSwanGuardrailEngine.evaluate()
  -> most_restrictive(JRE state, BSG state)
  -> interactive demo sections
```

The JRE answers:

> Do we know enough reliable clinical facts to act?

The BSG answers:

> Are we still inside the validated operating envelope where this pathway may act?

## 2. Observation Extraction

Each raw statement becomes an `Observation`:

```python
Observation(
    concept,
    raw_value,
    normalized_value,
    source,
    confidence,
    tags,
    trace,
)
```

Current extraction is deterministic:

1. Infer or use provided concept.
2. Normalize raw answer.
3. Start with source confidence.
4. Apply penalties for vague language.
5. Apply penalties for objective claims without numbers.
6. Apply penalties for adherence without time anchor.
7. Apply known distortion-trap priors.
8. Apply context penalties for low literacy, language barrier, and text modality.
9. Emit trace strings explaining each adjustment.

Example:

```text
Patient: "My BP is normal."
Concept: home_bp_number
Source: patient
Base confidence: patient baseline
Penalty: objective_claim_without_number
Penalty: normal_without_number prior
Result: lower-confidence observation with distortion tags
```

The key design principle:

> Patient language is treated as a measurement, not as a clinical fact.

## 3. Expert-System Nodes Today

In the current implementation, expert-system nodes are mostly `SlotSpec` objects from domain templates.

A `SlotSpec` defines:

```python
SlotSpec(
    name,
    label,
    importance,
    slot_type,
    acceptable_sources,
    clarify_questions,
    why_it_matters,
    critical,
    objective_required,
    remote_unknowable,
    traps,
)
```

These are the current nodes in the expert system.

A node can represent:

- history variable,
- objective variable,
- chart or lab requirement,
- exam-only boundary,
- remote-unknowable condition,
- critical safety slot.

The current node set is hand-authored per domain. This is useful for auditability, but limited for real-world coverage.

## 4. Finding Generation

After extraction, the engine creates findings.

Current finding categories:

```text
missing
uncertain
distorted
contradictory
unknowable_remote
objective_needed
red_flag
known
```

Main passes:

```text
observations
  -> source conflict findings
  -> slot findings
  -> contradiction findings
  -> red flag findings
  -> gestalt findings
  -> optional LLM candidate findings
```

Key mechanisms:

- **Missing slot**: required node absent.
- **Objective needed**: required objective node absent.
- **Distorted**: present but low-confidence or tagged with a trap.
- **Contradictory**: two concepts violate a contradiction rule.
- **Red flag**: regex or gestalt pattern fires.
- **Gestalt**: multi-signal pattern where combined evidence matters more than any one statement.

Example:

```text
"No chest pain, just pressure when walking upstairs"
  -> symptom_quality observation
  -> pain_word_boundary tag
  -> exertional_component signal
  -> GESTALT_ACS may fire
  -> red_flag finding
```

## 5. Scoring / Ensemble Today

The current ensemble is not ML voting. It is a transparent weighted decision ensemble across reasoning lenses.

The score components are:

```text
completeness
reliability
objective_coverage
contradiction_load
distortion_load
red_flag_load
critical_missing_penalty
```

Current readiness formula:

```text
index =
  0.42 * completeness
+ 0.30 * reliability
+ 0.18 * objective_coverage
+ 0.10 * (1 - distortion_load)

index -= 0.25 * contradiction_load
index -= 0.32 * red_flag_load
index -= critical_missing_penalty

JRI = clamp(index * 100, 0, 100)
```

Decision state:

```text
if severe red flag >= 0.85:
    ESCALATE
elif objective_needed >= 0.85:
    NEED_OBJECTIVE_DATA
elif contradiction exists:
    CLARIFY
elif JRI >= 78 and no red flags and few questions:
    READY
else:
    CLARIFY
```

This is an expert-system ensemble:

- slot completeness lens,
- reliability lens,
- objective data lens,
- contradiction lens,
- distortion lens,
- red-flag lens,
- critical missingness lens.

## 6. Black Swan Guardrail Ensemble

The BSG layer is a second ensemble around the JRE.

It scans for:

- wrong patient or proxy,
- prompt injection,
- metric gaming,
- stale data,
- nonresponse after risk,
- off-pathway sentinel symptoms,
- pediatric or unsupported envelope,
- social/coercion channel risk,
- high-risk host factors.

It produces:

```python
GuardrailReport(
    guardrail_state,
    max_autonomy_tier,
    novelty_score,
    residual_risk_budget,
    assumption_register,
    findings,
)
```

Then the combined state is:

```python
most_restrictive(jre_state, bsg_state)
```

Example:

```text
JRE = READY
BSG = FAIL_CLOSED
Final = FAIL_CLOSED
```

This is a safety-critical monotonic constraint: the less permissive layer wins.

## 7. Question Selection

Question selection is currently deterministic plus learned yield priors.

For each finding, the engine builds question candidates using:

```text
slot importance
finding category weight
uncertainty gap
expected question yield
```

Current priority formula:

```text
priority =
  slot.importance * category_weight
+ 0.35 * uncertainty_gap
+ 0.20 * expected_question_yield
```

Then it sorts and selects top questions.

Experience memory provides `expected_question_yield`, seeded and updated by EMA.

## 8. Current Learning

The current learning layer is limited but real.

It has:

- `distortion_priors`,
- `question_yield`,
- `ExperienceEvent`,
- clinician feedback:
  - confirmed,
  - corrected,
  - false positive,
  - missed.

It updates with exponential moving averages.

This is not full reinforcement learning. It is better described as:

```text
governed experiential calibration
```

It changes priors and question yield, not autonomous clinical policy.

## 9. Dynamic ESS Node Creation: Proposed Next Architecture

The next architecture should add an AI-generated expert-system planning layer.

Flow:

```text
Raw encounter
  -> LLM/extractor reads case
  -> proposes case boundary graph
  -> proposes nodes
  -> proposes ranges/distributions
  -> proposes rules/falsifiers
  -> deterministic validator accepts/rejects
  -> expert-system evaluator runs
  -> autonomy governor applies caps
```

Important boundary:

> The LLM proposes structure. It does not decide autonomy.

Example dynamic node:

```json
{
  "node_id": "renal_function_freshness",
  "clinical_question": "Is renal safety known well enough for ACE/ARB refill?",
  "value_type": "ordinal",
  "range": ["unknown", "fresh_normal", "stale", "abnormal", "not_available"],
  "distribution_type": "categorical",
  "prior": {
    "unknown": 0.45,
    "fresh_normal": 0.10,
    "stale": 0.25,
    "abnormal": 0.15,
    "not_available": 0.05
  },
  "required_evidence": ["creatinine/eGFR", "potassium", "lab date"],
  "unsafe_inferences": [
    "Do not infer renal safety from patient reassurance.",
    "Do not infer current renal status from stale chart data."
  ],
  "autonomy_effect": "block_autonomous_refill_if_unknown_or_stale"
}
```

## 10. How To Decide Node Ranges

Node ranges should be chosen by evidence type, not one generic confidence score.

Examples:

```text
Boolean:
  pregnancy_possible = true / false / unknown

Categorical:
  source_status = patient_only / device / chart / clinician / conflicting

Ordinal:
  communication_reliability = low / medium / high

Beta:
  readiness_probability in [0,1]

Time-decay:
  BP freshness, lab freshness, prior reassurance freshness

Mixture:
  competing interpretations, e.g. reflux vs ACS vs anxiety

Hazard-like:
  time-sensitive deterioration, nonresponse after risk, symptom progression

Count / Poisson-like:
  number of repeated failed contact attempts, vomiting episodes, rescue inhaler use
```

CS framing:

```text
Node range = support of the variable.
Distribution type = uncertainty geometry of the evidence.
Autonomy effect = policy constraint induced by unresolved uncertainty.
```

Example:

```text
"BP was normal a few months ago"
  node: current_bp_reliability
  range: current_number / stale_number / vague_reassurance / unknown
  distribution: categorical + time-decay
  autonomy effect: cannot renew autonomously
```

## 11. Distribution Selection Heuristic

A dynamic ESS planner should choose distribution type like this:

```text
if variable is hard-stop presence:
    boolean / ternary unknown
elif variable is discrete source state:
    categorical
elif variable is graded clinical/workflow severity:
    ordinal
elif variable is bounded confidence/readiness:
    beta
elif variable depends on evidence age:
    exponential or piecewise time-decay
elif variable has competing explanations:
    mixture distribution
elif risk changes with delay:
    hazard/survival-style curve
elif repeated events matter:
    count / rate model
```

## 12. Validator Layer

AI-generated nodes and rules need validators.

Validator checks:

```text
schema valid
evidence sources explicit
no unasked variable treated as denied
no stale data treated as current
no LLM-only T0/T1 hard stop
no memory-only clinical authorization
required simulation cases exist
governance status explicit
autonomy effect allowed for pathway
```

Core software safety pattern:

```text
AI creates adaptive structure.
Expert software validates and executes.
Governance promotes or rejects.
```

## 13. Future Ensemble With Dynamic Nodes

The future ensemble should combine several model families:

```text
Extractor ensemble:
  regex + LLM + structured source parsers

Node ensemble:
  static template nodes + AI-proposed dynamic nodes + VAMS-recalled missing nodes

Evidence ensemble:
  patient + caregiver + device + chart + clinician

Risk ensemble:
  JRE readiness + BSG assumption sufficiency + boundary trace instability + VAMS near-miss similarity

Policy ensemble:
  most-restrictive autonomy cap + cost-sensitive routing + fatigue controls
```

Future scoring graph:

```text
Case
  -> observations
  -> static ESS nodes
  -> dynamic ESS nodes
  -> node distributions
  -> findings
  -> JRE score
  -> BSG score
  -> BoundaryTraceField score
  -> VAMS near-miss recall
  -> falsifier plan
  -> autonomy governor
```

Final action remains governed:

```text
ALLOW_WITH_AUDIT
HOLD_AND_VERIFY
NEED_OBJECTIVE_DATA
ROUTE_CLINICIAN
FAIL_CLOSED
ESCALATE
```

## 14. Stigmergic Processing

The proposed stigmergic layer adds memory as a trace field.

Instead of each encounter being stateless text:

```text
statement -> finding -> decision
```

It becomes:

```text
statement -> perturb boundary field -> decay/integrate -> field state influences decision
```

Trace regions:

```text
claims
objective
source_conflict
social_workflow
temporal_staleness
outcome_feedback
```

Example:

```text
Patient says "BP is fine"
  -> claims trace: vague reassurance
  -> objective trace: missing number
  -> temporal trace: stale evidence if "last visit"
  -> source conflict trace: hot if chart/device disagrees
  -> outcome feedback trace: strengthened if clinician confirms near miss
```

This fills the gap where one weak signal is not enough, but multiple weak signals should accumulate.

## 15. VAMS / Hopfield Memory Processing

The proposed VAMS layer is associative memory for near-miss shapes.

Flow:

```text
JRE/BSG report
  -> ClinicalBoundaryEncoder
  -> sparse binary pattern
  -> Hopfield recall
  -> nearest memory / pattern completion
  -> suggested missing nodes and falsifiers
  -> deterministic validator
```

Sparse pattern example:

```text
N = 16,384 bits
k = 256 active bits
```

Features encoded:

```text
domain
missing slots
distortion tags
source conflicts
BSG rule IDs
autonomy tier
objective staleness
social/workflow flags
clinician feedback outcome
```

Important boundary:

```text
VAMS can suggest.
VAMS cannot authorize.
```

If VAMS recalls:

```text
Prior near miss: stale BP + CKD + NSAID + refill request
```

It can propose:

```text
ask current BP
check creatinine/eGFR
check potassium
ask NSAID use
block autonomous refill until verified
```

But deterministic ESS / BSG still enforce the final autonomy cap.

## 16. Falsifier Processing

The falsifier layer answers:

```text
What evidence would change the decision?
```

For each dangerous hypothesis:

```text
hypothesis: autonomous refill unsafe
basis: CKD + NSAID + stale BP/labs
falsifiers:
  current BP with timestamp
  recent creatinine/eGFR
  recent potassium
  no NSAID use
  no dizziness/hypotension
if unresolved:
  clinician review or objective verification
```

This converts safety from vague refusal to operational closure.

## 17. Final System Methodology

A strong final architecture would be:

```text
1. Ingest patient encounter.
2. Extract candidate observations.
3. Assign source-aware confidence.
4. Detect distortion, contradiction, red flags, stale data, social/workflow pressure.
5. Apply static expert-system template.
6. Ask AI planner for dynamic nodes/ranges/distributions.
7. Validate AI-proposed graph.
8. Evaluate node distributions.
9. Run JRE readiness ensemble.
10. Run BSG assumption-sufficiency ensemble.
11. Deposit signals into stigmergic boundary trace.
12. Encode boundary signature for VAMS recall.
13. Recall near-miss analogues and complete missing pattern.
14. Generate falsifiers and next-best questions.
15. Apply most-restrictive autonomy governor.
16. Render provider/executive UX:
    - statement vs fact
    - known unknowns
    - assumption register
    - autonomy boundary
    - next questions
    - operational value
    - mitigation plan
17. Capture clinician feedback.
18. Update experience memory, VAMS acceptance, trace priors.
19. Queue proposed template/rule changes for governance.
```

## Technical Thesis

This is an expert-system safety shell whose nodes represent clinical and operational uncertainty variables.

Today those nodes are static and deterministic.

The next version uses:

- AI to propose case-specific nodes, ranges, and distributions,
- VAMS to recall prior boundary failures,
- stigmergic traces to accumulate weak signals over time,
- deterministic validators and governance to decide what actually changes autonomy.
