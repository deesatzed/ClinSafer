# JRE Architecture

## Module overview

Primary intake/autonomy path:

```text
Patient conversation / intake form
        ↓
Transcript parser + input coverage audit
        ↓
Observation extractor + concept reclassifier
        ↓
Clinical uncertainty graph
  (typed nodes, source priors, ranges, distributions, dependencies)
        ↓
Graph readiness and node-state scorer
        ↓
MUD classifier: missing / uncertain / distorted / contradictory / unknowable
        ↓
CLEAR next-question selector
        ↓
Black Swan Guardrail assumption layer
        ↓
Most-restrictive autonomy governor
        ↓
Mitigation planner + final recommendations
        ↓
Provider boundary map + patient-safe clarification
```

Any Dispo review path:

```text
Decision-time snapshot
  (ED, observation, inpatient, telehealth, clinic, transfer, or transition)
        ↓
Proposed disposition + destination capability map
  (home, observation, floor, telemetry, stepdown, ICU, transfer, SNF, rehab)
        ↓
AnyDispositionReviewEngine
  (hard blockers, capability gaps, admission-benefit uncertainty)
        ↓
Cognitive bias field
  (bias entropy, hypothesis survival, fragility, cognitive friction)
        ↓
Clinical uncertainty graph
        ↓
Black Swan Guardrail assumption layer
        ↓
Disposition-specific review heads
  (lower-acuity risk, admission-benefit uncertainty, level-of-care mismatch)
        ↓
Most-restrictive disposition governor
        ↓
Candidate review signal, blockers, missing evidence, and safer alternatives
```

Retrospective disposition-handoff benchmark path:

```text
ED disposition-time snapshot
  (notes, dialogue, or hybrid)
        ↓
DispositionSnapshot adapter
        ↓
Judgment Readiness Engine
        ↓
Black Swan Guardrail assumption layer
        ↓
Disposition Sufficiency Index (DSI)
        ↓
Post-discharge PTR-B label
        ↓
DHSB benchmark metrics, stratification, calibration, and error analysis
```

Empirical boundary-learning path:

```text
DHSE/Any Dispo/JRE/BSG reports
        ↓
Text-free empirical feature contract
        ↓
Imbalanced tabular learners
  (calibrated logistic, GBDT, balanced forest, TabPFN)
        ↓
Calibration + selective/conformal threshold
        ↓
Review priority / abstention signal
        ↓
Most-restrictive autonomy governor
```

Governed medical-knowledge acquisition path:

```text
Atomic clinical/guideline question
        ↓
Configured medical-capable model candidate answer
        ↓
Source citation + prompt/answer hash
        ↓
Qualified human review
        ↓
Versioned rule/template candidate
        ↓
Simulation, DHSE outcome checks, monitoring
        ↓
Governance promotion or rejection
```

## Design influence from prior builds

This prototype borrows three patterns from the user’s prior software systems:

### CAM-style pattern memory

- Store reusable patterns.
- Retrieve the most relevant pattern.
- Apply it to the current case.
- Verify result with tests/traces.
- Learn which method worked.

In JRE, the pattern is not code. The pattern is a clarification method:

> “When a respiratory patient says they are not short of breath, ask a functional probe and sentence test before trusting the denial.”

### aXc-style ensemble/meta-reasoning

JRE separates reasoning lenses:

- Slot completeness
- Reliability
- Distortion/health literacy
- Contradiction
- Red-flag safety
- Remote boundary

The final arbiter combines these into a state: `READY`, `CLARIFY`, `NEED_OBJECTIVE_DATA`, or `ESCALATE`.

### Expert-system discipline

Rather than relying on opaque LLM judgment, safety-critical rules are explicit:

- Required slots
- Objective-data requirements
- Red-flag patterns
- Remote-unknowable elements
- Rule traces

### Bounded multi-role LLM pipeline

The deployed interactive demo no longer represents the LLM as one generic
"second opinion." It exposes bounded roles:

- `extractor`: fast semantic extraction of candidate red flags, wrong labels,
  human distortion, and coverage gaps.
- `boundary`: clinical boundary reasoning about what makes automation unsafe and
  which falsifiers are still missing.
- `verifier`: adversarial audit for ignored transcript lines, false negatives,
  and unsafe reassurance.
- `bias_auditor`: cognitive-bias audit for anchoring, premature closure,
  confirmation bias, omission bias, diagnostic momentum, framing risk, and
  overconfidence.
- `patient_comm`: post-governor patient-language drafting only.
- `workflow`: post-governor clinician/workflow synthesis only.

The default async safety pass runs `extractor,boundary,verifier,bias_auditor` in parallel.
All LLM roles are advisory. They can propose review targets and missing
falsifiers, but they cannot authorize care, downgrade a guardrail, prescribe,
close a case, or independently create the final autonomy boundary.

Role-specific model configuration is exposed through environment variables:

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

The UI shows role, model, purpose, and authority so a technical reviewer can see
which layer produced a signal and whether that signal is allowed to affect
automation.

### Stigmergic boundary traces

The implemented foundation borrows from the local
`rustigmergic-logswarm-engine` repo. Instead of treating every encounter as
stateless text, unresolved signals can leave bounded traces:

- patient claims and denials,
- objective evidence and timestamps,
- source conflict,
- social/workflow pressure,
- temporal staleness,
- outcome feedback.

`jre/boundary_trace.py` implements an in-memory `BoundaryTraceField` with typed
patches, symbolic keys, support, opposition, decay, search, retraction, and
risk-pressure summaries. Each trace type can decay at a different rate. Stale
objective evidence can lose force quickly; unresolved source conflict,
nonresponse after risk, and confirmed near-miss feedback can persist longer.

### VAMS-style associative memory

The implemented foundation borrows from the local `Vamplify-Claude` repo:

- Hebbian strengthening for confirmed recalls,
- anti-Hebbian weakening for rejected recalls,
- associative recall from partial cues,
- pattern completion,
- typed memory edges.

`jre/associative_memory.py` implements an in-memory `NearMissMemory` that
recalls near-miss boundary shapes from sparse signatures. A recalled memory can
suggest missing nodes, falsifiers, clarification questions, and pattern
completion keys. Deterministic validators still decide whether autonomy is
capped.

## Core objects

### ClinicalUncertaintyGraph

The explicit expert-system uncertainty substrate. Each report now includes a
machine-readable graph of typed clinical nodes with observed value, source,
source-reliability prior, confidence, range band, range severity, uncertainty
distribution, dependencies, and action implications.

The graph summary feeds JRE scoring, BSG residual-risk/action-pressure logic,
and DHSE disposition-risk features.

### Statement

Raw answer from patient, caregiver, chart, device, or clinician.

### Observation

Normalized statement plus confidence and distortion tags.

### SlotSpec

Safety-relevant clinical variable for a domain.

### Finding

A MUD or safety issue.

### NextQuestion

A selected clarification question with rationale and expected information gain.

### ReadinessReport

Full provider-facing result.

### DispositionSnapshot

ED-disposition-time representation for retrospective handoff evaluation. It is
the first implemented specialization of the broader Any Dispo decision-time
snapshot. It can be built from notes, current dialogue, or a hybrid of both. It
includes ED note text, key PMH, resulted ED data, vital trend, ED treatments,
disposition diagnosis, service, level of care, and optional dialogue statements.

### ProposedDisposition

Future Any Dispo object describing the destination being evaluated:
home, observation, inpatient floor, telemetry, stepdown, ICU, transfer, SNF,
rehab, home health, or other transition path. It should carry the decision
timestamp, proposed service, monitoring level, follow-up plan, and documented
reason for the proposed destination.

### DestinationCapability

Future Any Dispo object describing what the destination can actually provide:
serial vitals, oxygen, IV therapy, telemetry, urgent imaging/procedure access,
nursing checks, rapid reassessment, medication access, caregiver support, and
confirmed follow-up.

### PostDischargeTrajectory

Post-discharge outcome object used only for benchmark labeling. It contains
diagnosis-category revision, LOS/expected LOS, early ICU/stepdown transfer,
rapid response, major procedure, mortality, therapeutic pivots, readmission, and
other objective burden fields.

### DispositionSufficiencyReport

DHSE output containing DSI, DHSE state, JRE state, BSG state, risk/protective
factors, input limitations, and optional PTR-B label.

### AnyDispositionReviewReport

Implemented umbrella report for any proposed disposition. It contains the
proposed destination, deterministic blockers, destination capability gaps,
admission-benefit uncertainty signals, missing evidence, trace summary,
near-miss memory suggestions, signature keys, review priority, and a conservative
review state. It can optionally attach a `cognitive_bias_field` payload.

Implemented states:

- `LOWER_ACUITY_BLOCKED`
- `ADMISSION_BENEFIT_UNCERTAIN`
- `LEVEL_OF_CARE_MISMATCH`
- `INSUFFICIENT_EVIDENCE`
- `REVIEW_RECOMMENDED`
- `NO_REVIEW_SIGNAL`

These states route review. They do not order a destination.

### CognitiveBiasFieldReport

Implemented advisory reasoning-risk layer. It converts JRE, BSG, reasoning
integrity, Any Dispo, trace, and near-miss memory outputs into bias entropy,
dominant bias factors, information-gain candidates, hypothesis-survival ledgers,
disposition-fragility reports, cognitive-friction actions, and fresh-eyes
payloads.

The field does not claim clinician bias, quantum diagnosis, true Monte Carlo
clinical probability, or disposition authority. It can only raise review
pressure, preserve uncertainty, and require disconfirming evidence, objective
data, falsifiers, or a blinded reread.

### BoundaryTraceField

Implemented advisory trace substrate for unresolved boundary signals. It stores
typed patches such as claims, constraints, signals, questions, outcomes, and
retractions. Patches carry symbolic keys, confidence, support mass, opposition
mass, decay rate, evidence IDs, and status. The field can search traces,
reinforce or oppose them, decay stale mass, retract resolved signals, and
summarize residual risk pressure.

### NearMissMemory

Implemented advisory associative memory for deidentified boundary signatures.
It stores sparse signature keys with missing nodes, falsifiers, and recommended
review actions. Partial signatures recall similar near-miss patterns by overlap.
Confirmed useful recalls are strengthened; rejected recalls are weakened.

## Judgment Readiness Index

The prototype combines:

- Completeness
- Reliability
- Objective-data coverage
- Contradiction load
- Distortion load
- Red-flag load
- Critical missingness

The score is intentionally transparent rather than optimized. A production version would calibrate weights through outcomes and governance review.

## Current Guarantees

The deployed app now enforces these demo-level guarantees:

1. Every submitted line appears in the Input Coverage Audit.
2. Wrong or generic concepts, including manual `red_flag`, are treated as hints
   and reclassified into active domain slots when the text supports it.
3. Unknown or unmapped observations are not neutral; they create review findings
   and cannot support closure.
4. Missing data is not treated as absent data.
5. Reasoning-integrity findings create cognitive forcing actions, not clinician-blame labels.
6. Cognitive-bias field outputs are advisory review pressure, not clinician
   diagnosis or disposition authority.
7. LLM findings are candidate signals only.
8. The most-restrictive governor combines JRE, BSG, and reasoning-integrity states before any final
   recommendation is rendered.

## Future extension

1. Add specialty-specific pathway packs.
2. Connect to EHR/pharmacy/device sources to verify objective data.
3. Use outcome feedback to update distortion priors and question-yield estimates.
4. Persist `BoundaryTraceField` and `NearMissMemory` beyond process memory after
   datastore, retention, and deidentification rules are chosen.
5. Wire boundary traces and near-miss recall into Any Dispo review reports,
   API output, and the clinician-facing UI.
6. Surface the cognitive-bias field in API/demo views with fresh-eyes mode,
   disposition fragility, and cognitive friction prompts.
7. Add governed AI-generated dynamic templates: LLM proposes nodes, ranges, distributions, and rules; validators decide what can execute.
8. Add Any Dispo schema and review heads for lower-acuity risk, admission-benefit
   uncertainty, and level-of-care mismatch.
9. Build A/B studies: ordinary intake vs uncertainty-aware intake.

## Any Dispo umbrella

The architecture should now be described as Any Dispo first, DHSE second. DHSE
remains the concrete implemented head for retrospective ED disposition handoff
sufficiency. The umbrella expands the same graph, guardrail, and empirical
boundary-learning substrate to every proposed disposition:

- home or low-monitoring path,
- observation,
- inpatient floor,
- telemetry or monitored bed,
- stepdown or ICU,
- transfer,
- SNF, rehab, home health, or other transition.

Any Dispo outputs a review signal, not an autonomous destination order. It asks
whether the proposed destination has sufficient evidence and capability. The
inverse/admission-benefit head must be especially conservative: it can identify
`admission_benefit_uncertain` or `home_ready_review_candidate`, but it cannot
declare an admission unnecessary.

`jre/any_disposition.py` now implements the first deterministic Any Dispo review
surface. It evaluates proposed destinations against decision-time evidence,
destination capabilities, objective instability, unresolved red flags, source
conflicts, high-risk host factors, follow-up reliability, and documented
inpatient-only needs. It also attaches advisory `BoundaryTraceField` and
`NearMissMemory` outputs for missing nodes and falsifiers.

The planned contract is `ANY-DISPO-CSV-v0.1`. It should preserve the same
leakage invariant used by DHSE: decision-time snapshot fields are inputs;
hospital-course and post-disposition fields are labels only.

See `docs/ANY_DISPOSITION_MODEL_PLAN.md`.

## Black Swan Guardrail Layer extension

The Black Swan Guardrail Layer wraps the JRE. JRE answers, “Do we know enough to act?” The guardrail answers, “Are we still inside the validated operating envelope where this pathway is allowed to act?”

```text
Patient conversation / intake form
        ↓
Judgment Readiness Engine
        ↓
Black Swan Guardrail Layer
        ↓
Assumption register + autonomy-tier cap
        ↓
ALLOW_WITH_AUDIT / HOLD_AND_VERIFY / ROUTE_CLINICIAN / FAIL_CLOSED / ESCALATE
```

The guardrail detects:

- off-pathway sentinel symptoms,
- identity/proxy breaches,
- adversarial or prompt-injection attempts,
- metric-gaming behavior,
- communication reliability failure,
- social-channel/coercion risk,
- stale or conflicting objective data,
- workflow failure such as nonresponse after risk,
- high-risk host factors that invalidate routine thresholds.

This separates model confidence from autonomy permission. A case can look clinically simple but still be non-automatable because a hidden assumption has failed.

## Disposition Handoff Sufficiency extension

The Disposition Handoff Sufficiency Engine (DHSE) adapts JRE/BSG to a
retrospective ED admission benchmark. It is the first implemented Any Dispo
head. The question is not whether the handoff was subjectively good. The
question is:

> Using only information available at ED disposition, was the representation
> sufficient for the inpatient trajectory that actually unfolded?

DHSE supports three source modes:

- `notes`: ED documentation and structured ED data available at disposition.
- `dialogue`: current elicitation transcript plus structured objective data.
- `hybrid`: both notes and dialogue, preserving source conflicts.

It returns:

- Disposition Sufficiency Index (DSI), 0-100.
- state: `SUFFICIENT`, `UNDER_SPECIFIED`, `ACUITY_MISMATCH_RISK`, or
  `DIAGNOSTIC_PIVOT_RISK`.
- JRE and BSG states.
- risk/protective factors and input limitations.
- optional PTR-B label when post-discharge trajectory data is supplied.

The benchmark label is PTR-B: Post-Disposition Trajectory Revision with Burden.
PTR-B is positive only when objective trajectory revision and measurable burden
both occur. Pending results or expected inpatient workup are not failures by
themselves.

Implemented data contracts:

- `data/dhse_synthetic_benchmark.jsonl`
- canonical flat EHR CSV via `docs/DHSE_CANONICAL_CSV_SCHEMA.md`
- machine-readable contract source in `jre/dhse_contract.py`

Implemented runner:

```bash
python scripts/run_dhse_benchmark.py \
  --reports-json artifacts/dhse_reports.json \
  --summary-json artifacts/dhse_summary.json \
  --case-csv artifacts/dhse_cases.csv
```

The safety invariant is a leakage boundary: discharge diagnosis, inpatient
notes, post-disposition labs/imaging, ICU transfer outcome, LOS, mortality, and
readmission are labels only and must not influence ED snapshot scoring.
The CSV validator fails closed on non-canonical post-disposition-looking columns
and on outcome-looking keys hidden inside snapshot JSON fields.

## Empirical uncertainty layer

The empirical layer is implemented as a feature-export foundation, not a
clinical clearance model.

Files:

- `jre/empirical_uncertainty.py`
- `scripts/export_dhse_empirical_features.py`
- `docs/EMPIRICAL_UNCERTAINTY_PLAN.md`

It exports a `DHSE-EMPIRICAL-v0.1` feature contract for imbalanced-data models,
TabPFN, tuned GBDT, and selective/conformal wrappers. The feature contract
excludes raw notes, diagnoses, dialogue text, evidence snippets, questions, and
answers.

The empirical layer can raise review priority, estimate review-budget capture,
and abstain when calibrated uncertainty is too high. It cannot clear a
deterministic guardrail.

## Governed medical knowledge layer

The system acknowledges that red flags, standards, risk thresholds, and
objective-data requirements require medical expert knowledge. The counter is to
make that knowledge path explicit and auditable:

- use medical-capable models only for narrow clinical/guideline questions;
- require citations and prompt/answer hashes;
- require qualified human review before promotion;
- version and monitor every promoted rule;
- allow candidate knowledge to increase caution before validation, not decrease
  it.

See `docs/GOVERNED_MEDICAL_KNOWLEDGE_LAYER.md`.

## Mitigation architecture

The updated mitigation plan is:

```text
Current case
        ↓
Deterministic JRE + BSG controls
        ↓
Mitigation planner
        ↓
Immediate action cap / verification / escalation
        ↓
BoundaryTraceField deposit
        ↓
NearMissMemory advisory recall
        ↓
Candidate missing nodes and falsifiers
        ↓
Template validator + governance queue
```

The safety invariant is that memory and AI planning propose structure; governed expert-system software enforces boundaries.
