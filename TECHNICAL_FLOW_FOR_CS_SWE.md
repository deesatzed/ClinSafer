# Technical Flow For CS / SWE Review

## Purpose

This document explains the methodology and technology behind the Judgment Readiness Engine demo at a level suitable for a computer scientist, software engineer, or technical healthcare AI reviewer.

It separates:

- **implemented now**: current `ver2` JRE / BSG / DHSE / demo behavior,
- **next architecture**: dynamic expert-system software, probabilistic nodes, stigmergic traces, VAMS memory, and governed template promotion.

## 1. Current Input Pipeline

The current app can start from either a structured `CaseInput` or a pasted
raw transcript.

- `PatientContext`: age, domain, chief concern, modality, known conditions, language barrier, caregiver status.
- `Statement[]`: each question/answer pair with optional concept, source, and metadata.
- `ground_truth`: synthetic demo labels.

Current flow:

```text
Raw transcript or CaseInput
  -> transcript parser
  -> patient context extraction
  -> concept inference / reclassification
  -> Input Coverage Audit
  -> JudgmentReadinessEngine.evaluate()
  -> BlackSwanGuardrailEngine.evaluate()
  -> most_restrictive(JRE state, BSG state)
  -> ReasoningIntegrityEngine.evaluate()
  -> async multi-role LLM candidate pipeline
  -> interactive demo sections
```

The JRE answers:

> Do we know enough reliable clinical facts to act?

The BSG answers:

> Are we still inside the validated operating envelope where this pathway may act?

The DHSE answers:

> At ED disposition time, was the available representation sufficient for the
> inpatient trajectory that actually unfolded?

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

Current extraction is deterministic and uses concept labels as hints, not
absolute truth:

1. Infer or use provided concept.
2. Normalize raw answer.
3. Start with source confidence.
4. Apply penalties for vague language.
5. Apply penalties for objective claims without numbers.
6. Apply penalties for adherence without time anchor.
7. Apply known distortion-trap priors.
8. Apply context penalties for low literacy, language barrier, and text modality.
9. Emit trace strings explaining each adjustment.

Important mitigation now implemented:

- A manual concept such as `red_flag`, `alarm`, or `urgent` is preserved as a
  safety hint.
- If the text fits a concrete domain slot, the system reclassifies it. Example:
  `red_flag` plus "tingling in my private areas" in a back-pain case becomes
  `neuro_deficit`.
- If a supplied concept belongs to the wrong domain, such as `flank_pain` in a
  musculoskeletal back-pain pathway, the active-domain inference can override it.
- Unknown observations are not neutral. They create review findings and cannot
  support reassurance or closure.

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
  -> unmapped observation review findings
  -> slot findings
  -> contradiction findings
  -> red flag findings
  -> gestalt findings
  -> optional bounded LLM candidate findings
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

## 6. Bounded Multi-Role LLM Pipeline

The deployed app now uses a bounded multi-role LLM design for the optional async
analysis. This is not a voting committee and not an autonomous decision-maker.
It is a candidate-signal pipeline that runs after deterministic analysis is
already available.

Default enabled roles:

```text
extractor
  -> parse raw language into candidate red flags, wrong labels, distortion,
     human disclosure pressure, and coverage gaps

boundary
  -> ask what makes the encounter unsafe for automation and which missing
     falsifiers must be closed

verifier
  -> adversarially audit for ignored lines, false negatives, premature closure,
     and unsafe reassurance

bias_auditor
  -> audit the reasoning path for anchoring, premature closure, confirmation
     bias, search satisficing, omission bias, diagnostic momentum, framing risk,
     and overconfidence
```

Configured but disabled by default:

```text
patient_comm
  -> post-governor patient-facing language only

workflow
  -> post-governor clinician/workflow synthesis only
```

Role-specific model variables:

```text
OPENROUTER_ANALYSIS_ROLES=extractor,boundary,verifier,bias_auditor
OPENROUTER_EXTRACTOR_MODEL=qwen/qwen3.6-flash
OPENROUTER_BOUNDARY_MODEL=qwen/qwen3.6-flash
OPENROUTER_VERIFIER_MODEL=qwen/qwen3.6-flash
OPENROUTER_BIAS_MODEL=qwen/qwen3.6-flash
OPENROUTER_PATIENT_MODEL=qwen/qwen3.6-flash
OPENROUTER_WORKFLOW_MODEL=qwen/qwen3.6-flash
OPENROUTER_MAX_PARALLEL_ROLES=4
```

Authority rule:

```text
LLM role output -> candidate finding only
candidate finding -> review target / missing falsifier / prompt for validator
candidate finding -/-> authorization, prescription, closure, hard-stop downgrade
```

The UI exposes role, model, purpose, and authority. This is intentional: a
reviewer should be able to distinguish "the model noticed this" from "the
governed software is allowed to act on this."

## 7. Reasoning Integrity / Cognitive Bias Guard

The deployed app now includes a deterministic `ReasoningIntegrityEngine`.
It audits the reasoning path rather than the clinician. The output is phrased as
cognitive forcing, not blame.

Initial implemented bias families:

```text
anchoring
premature_closure
confirmation_bias
search_satisficing
availability_bias
omission_bias
diagnostic_momentum
overconfidence
framing_ascertainment
```

Each finding contains:

```text
bias_id
label
severity
evidence
reasoning_failure
cognitive_forcing_action
disconfirming_question
affected_autonomy
authority
```

State behavior:

```text
no finding -> ALLOW_WITH_AUDIT
moderate/high finding -> HOLD_AND_VERIFY
high finding + unresolved safety gap -> ROUTE_CLINICIAN
```

The combined governor now evaluates:

```text
most_restrictive(JRE state, BSG state, Reasoning Integrity state)
```

This is the Croskerry/dual-process support layer: System 1-prone pathways get
explicit forcing functions before closure or reassurance.

Conceptual basis:

- Pat Croskerry's clinical decision-making and cognitive forcing work.
- Dual-process reasoning: fast Type/System 1 pattern matching vs slower
  Type/System 2 analytic verification.
- Telemedicine-specific anchoring risk from asynchronous store-and-forward
  workflows, cue limitation, and information breadth/overload.

## 8. Input Coverage Audit

Every encounter line is audited before the analysis is presented.

For each row, the audit shows:

- supplied concept,
- inferred concept,
- effective concept,
- source,
- whether reclassification occurred,
- which consumers used the row:
  - observation extractor,
  - patient-context extractor,
  - JRE template slot,
  - JRE rules,
  - Black Swan Guard,
  - async LLM extractor payload,
  - concept reclassifier,
- safety effect,
- status.

The invariant is:

> No input line may silently disappear or support reassurance while unmapped.

This is the mitigation for the failure mode where a clinically important line is
added by a user, mislabeled, and then ignored by downstream analysis.
- critical missingness lens.

## 9. Black Swan Guardrail Ensemble

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

## 10. Question Selection

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

## 11. Current Learning

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

## 12. Disposition Handoff Sufficiency Engine

DHSE is the retrospective benchmark layer built on top of JRE and BSG.

It intentionally changes the unit of analysis:

```text
not: live patient-intake autonomy permission
but: ED disposition representation sufficiency
```

Primary input object:

```python
DispositionSnapshot(
    case_id,
    input_mode,              # notes, dialogue, or hybrid
    age,
    chief_concern,
    domain,
    disposition_diagnosis,
    admission_service,
    level_of_care,
    ed_note,
    key_pmh,
    ed_results,
    vital_trend,
    treatments,
    dialogue,
    metadata,
)
```

Input modes:

```text
notes
  -> evaluates ED documentation and structured ED data available at disposition

dialogue
  -> evaluates current elicitation quality before note synthesis

hybrid
  -> evaluates both, preserving source labels and conflicts
```

DHSE converts the snapshot into a `CaseInput`, runs JRE, wraps it with BSG, then
computes:

```text
DSI = Disposition Sufficiency Index, 0-100
state = SUFFICIENT | UNDER_SPECIFIED | ACUITY_MISMATCH_RISK | DIAGNOSTIC_PIVOT_RISK
```

Important distinction:

> DHSE does not punish pending inpatient workup. It only scores the ED
> disposition-time representation and objective data already available before
> the disposition decision.

## 13. PTR-B Retrospective Label

The primary label is:

```text
PTR-B = Post-Disposition Trajectory Revision with Burden
```

PTR-B positive requires both:

```text
objective trajectory revision
AND
measurable clinical/resource burden
```

Revision examples:

- ED diagnosis category differs from discharge diagnosis category.
- Floor admission upgrades to stepdown/ICU within 24 hours.
- Rapid response/code within 24 hours.
- Major therapeutic pivot, such as pressors, intubation, insulin drip,
  transfusion, emergent anticoagulation, broad-spectrum antibiotics, procedure,
  cath lab, OR, or stroke pathway.
- Admitting service changes because the initial problem representation was
  materially wrong or incomplete.

Burden examples:

- risk-adjusted LOS at least 1.5x expected and at least 24 hours over expected
- ICU/stepdown transfer within 24 hours
- rapid response within 24 hours
- in-hospital mortality
- major procedure
- delayed definitive therapy of at least 6 hours
- discharge to higher level of care than baseline
- 30-day readmission

Leakage boundary:

```text
ED snapshot scoring cannot use discharge diagnosis, inpatient notes,
post-disposition labs/imaging, ICU transfer, LOS, mortality, or readmission.
Those fields are labels only.
```

## 14. DHSB Benchmark Flow

Benchmark input can be JSONL or canonical flat CSV.

Flow:

```text
JSONL / canonical CSV
  -> BenchmarkCase[]
  -> DispositionSnapshot + PostDischargeTrajectory
  -> DHSE reports
  -> primary metrics
  -> baseline metrics
  -> paper-facing analysis tables
```

Implemented primary metrics:

```text
AUROC
AUPRC
top-decile enrichment
capture at fixed review fraction
calibration bins
DSI threshold table
```

Implemented stratifications:

```text
input mode: notes / dialogue / hybrid
DHSE state
defect family
```

Implemented error analysis:

```text
false positives at DSI threshold 75
false negatives at DSI threshold 75
```

Implemented baselines:

```text
structured severity heuristic
nonspecific diagnosis heuristic
ED LOS heuristic
JRE-only risk
Black Swan-only risk
```

Runner:

```bash
python scripts/run_dhse_benchmark.py \
  --input data/dhse_synthetic_benchmark.jsonl \
  --reports-json artifacts/dhse_reports.json \
  --summary-json artifacts/dhse_summary.json \
  --case-csv artifacts/dhse_cases.csv
```

## 15. Dynamic ESS Node Creation: Proposed Next Architecture

The next architecture should add an AI-generated expert-system planning layer.

Flow:

```text
Raw encounter
  -> bounded LLM extractor / boundary / verifier roles read case
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

## 16. How To Decide Node Ranges

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

## 17. Distribution Selection Heuristic

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

## 18. Validator Layer

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

## 19. Future Ensemble With Dynamic Nodes

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

## 20. Stigmergic Processing

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

## 21. VAMS / Hopfield Memory Processing

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

## 22. Falsifier Processing

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

## 23. Final System Methodology

A strong final architecture would be:

```text
1. Ingest patient encounter.
2. Parse transcript and extract patient context.
3. Audit every input line for downstream consumers.
4. Extract candidate observations.
5. Reclassify wrong/generic concepts into active-domain slots when supported.
6. Assign source-aware confidence.
7. Detect distortion, contradiction, red flags, stale data, social/workflow pressure.
8. Apply static expert-system template.
9. Run bounded multi-role LLM candidate pipeline:
   - extractor,
   - boundary,
   - verifier,
   - bias_auditor.
10. Run deterministic reasoning-integrity / cognitive-bias guard.
11. Ask AI planner for dynamic nodes/ranges/distributions when static coverage is insufficient.
12. Validate AI-proposed graph.
13. Evaluate node distributions.
14. Run JRE readiness ensemble.
15. Run BSG assumption-sufficiency ensemble.
16. For retrospective ED admissions, run DHSE disposition sufficiency scoring
    and PTR-B benchmark analysis.
17. Export text-free empirical features for imbalanced tabular modeling,
    TabPFN/GBDT benchmarking, calibration, and selective/conformal review
    thresholds.
18. Ask governed medical-knowledge questions only as atomic guideline/red-flag
    candidate retrieval, with citations and human review before promotion.
19. Deposit signals into stigmergic boundary trace.
20. Encode boundary signature for VAMS recall.
21. Recall near-miss analogues and complete missing pattern.
22. Generate falsifiers and next-best questions.
23. Apply most-restrictive autonomy governor.
24. Render provider/executive UX:
    - statement vs fact
    - input coverage audit
    - model/role provenance
    - known unknowns
    - assumption register
    - reasoning integrity check
    - autonomy boundary
    - next questions
    - operational value
    - mitigation plan
25. Capture clinician feedback.
26. Update experience memory, VAMS acceptance, trace priors.
27. Queue proposed template/rule changes for governance.
```

## Technical Thesis

This is an expert-system safety shell whose nodes represent clinical and operational uncertainty variables.

Today those nodes are mostly static and deterministic, with concept
reclassification, input coverage auditing, and bounded multi-role LLM candidate
extraction implemented around them.

DHSE adds a retrospective benchmark methodology around the same safety shell:
score only ED-disposition-time information, label only with post-discharge
trajectory revision plus burden, and report objective metrics instead of
subjective handoff-quality ratings.

The empirical uncertainty layer adds a model-ready tabular contract for
calibrated imbalanced learning. TabPFN, tuned GBDT, and transparent baselines can
estimate PTR-B/review yield, but their outputs only raise review priority or
abstain unless governed evidence promotes them.

The governed medical knowledge layer counters the "you still need medical
expertise" critique by making expert knowledge explicit: atomic model-assisted
guideline questions, source citation, prompt/answer hashing, human review,
versioning, rollback, and monitoring.

The next version uses:

- AI to propose case-specific nodes, ranges, and distributions,
- empirical feature exports to calibrate review thresholds,
- medical-capable models to gather source-bound candidate facts for governance,
- VAMS to recall prior boundary failures,
- stigmergic traces to accumulate weak signals over time,
- deterministic validators and governance to decide what actually changes autonomy.
