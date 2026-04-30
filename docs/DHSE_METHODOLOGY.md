# DHSE Methodology

## Research Object

The Disposition Handoff Sufficiency Engine (DHSE) evaluates whether the ED
disposition representation available at the moment of admission was sufficient
for the inpatient trajectory that actually unfolded.

DHSE is now the first implemented head inside the broader Any Dispo model plan.
It covers the ED admission/handoff direction. The umbrella plan extends the same
uncertainty graph, guardrails, leakage controls, and empirical review metrics to
home, observation, inpatient, transfer, and level-of-care decisions.

The method is retrospective. It uses only ED-disposition-time inputs for scoring
and uses post-discharge facts only for labeling and evaluation.

## Core Methodological Constraint

DHSE does not treat pending inpatient workup as a handoff defect. Admission is
supposed to transfer unresolved work. The failure phenotype is narrower:

```text
under-specified or mismatched ED disposition representation
  + objective post-disposition trajectory revision
  + measurable clinical/resource burden
```

## Input Modes

### Notes Mode

Use this when the source is the ED disposition documentation.

Included:

- ED provider note / MDM
- triage or intake note if available
- key PMH / medications / allergies
- ED resulted labs and imaging before disposition
- ED vital trend before disposition
- ED treatments before disposition
- disposition diagnosis
- admitting service and intended level of care

Notes mode evaluates the documented representation. It does not claim to
reconstruct the original patient-clinician conversation.

### Dialogue Mode

Use this when the source is the live or recorded elicitation dialogue before a
note exists.

Included:

- patient, caregiver, clinician, chart, and device statements
- structured objective data if already available
- proposed disposition diagnosis/service/level of care if known

Dialogue mode evaluates elicitation sufficiency. Objective data must be supplied
separately or remains absent.

### Hybrid Mode

Use this when both dialogue and documentation are available. Source labels are
preserved so disagreement between patient dialogue, clinician note, chart, and
device data remains visible.

## Scoring Output

DHSE produces:

- `DSI`: Disposition Sufficiency Index, 0-100
- state:
  - `SUFFICIENT`
  - `UNDER_SPECIFIED`
  - `ACUITY_MISMATCH_RISK`
  - `DIAGNOSTIC_PIVOT_RISK`
- JRE state
- Black Swan Guardrail state
- risk and protective factors
- optional PTR-B label

DSI is not a diagnosis score. It is an information sufficiency and representation
fit score.

## Foundational Scoring Substrate

DHSE does not score free text directly as a loose LLM judgment. The scoring
substrate is the same expert-system clinical uncertainty graph used by JRE and
Black Swan Guardrails.

Each clinically meaningful fact is converted into a typed node with:

- source and source reliability prior
- observed raw value and normalized numeric value when available
- expert-defined range band and range severity for numeric values
- missingness state
- discrete uncertainty distribution
- dependencies and action implications
- strategic-signal reliability modifiers when incentives may distort the source
- boundary distance, boundary fragility, and perturbation flip risk

Game-theory signals are represented as graph nodes, not prose commentary.
Examples include care-avoidance pressure, answer gaming pressure, proxy
misalignment, coercion or observation pressure, defensive minimization, and
documentation closure pressure. These signals lower trust in affected semantic
reassurance and raise the need for objective verification.

The dynamical-sensitivity layer measures whether small plausible perturbations
could change the action boundary. Examples include a blood pressure near a
hypertensive threshold, oxygen saturation near an escalation threshold, or
several coupled objective variables near worse bands. DHSE carries these as
graph-derived risk factors rather than waiting for a pending result or delaying
routine admission flow.

## Primary Label

The primary benchmark label is PTR-B:

```text
Post-Disposition Trajectory Revision with Burden
```

PTR-B is positive only when both conditions are met:

1. Objective trajectory revision occurred after ED disposition.
2. That revision carried measurable clinical or resource burden.

This keeps the label anchored to hard data and avoids subjective handoff-quality
ratings as the primary endpoint.

## Revision Events

Examples:

- ED diagnosis category differs from discharge diagnosis category.
- Floor admission upgrades to stepdown or ICU within 24 hours.
- Rapid response or code within 24 hours.
- Major therapeutic pivot, such as pressors, intubation, insulin drip,
  transfusion, emergent anticoagulation, broad-spectrum antibiotics, emergent
  procedure, cath lab, OR, or stroke pathway.
- Admitting service changes because the initial problem representation was wrong
  or materially incomplete.

## Burden Events

Examples:

- risk-adjusted LOS at least 1.5x expected and at least 24 hours over expected
- ICU/stepdown transfer within 24 hours
- rapid response within 24 hours
- in-hospital mortality
- major procedure
- delayed definitive therapy of at least 6 hours
- discharge to higher level of care than baseline
- 30-day readmission

## Metrics

Primary metrics:

- AUROC for PTR-B
- AUPRC for PTR-B
- top-decile enrichment
- capture at fixed review budgets: 5%, 10%, 20%
- calibration bins
- threshold table across DSI cutoffs

Secondary analyses:

- notes vs dialogue vs hybrid input-mode stratification
- graph feature family ablations: missingness, range risk, strategic signals,
  and boundary sensitivity
- DHSE state stratification
- defect-family stratification
- false-positive and false-negative error analysis
- baseline comparison

## Baselines

Implemented dependency-free baselines:

- structured severity heuristic
- nonspecific diagnosis heuristic
- ED LOS heuristic
- JRE-only risk
- Black Swan-only risk

The generic LLM risk baseline remains deferred until the model, prompt, API
access, and governance contract are fixed.

## Leakage Boundary

The scoring engine must not use:

- discharge diagnosis
- inpatient notes
- post-disposition labs or imaging
- ICU transfer outcome
- LOS
- mortality
- readmission

Those fields are labels only.

## Data Contracts

Supported benchmark inputs:

- JSONL fixture / canonical retrospective benchmark rows
- canonical flat EHR CSV export

Relevant docs:

- `docs/DHSE_BENCHMARK_SPEC.md`
- `docs/DHSE_CANONICAL_CSV_SCHEMA.md`
- `docs/DHSE_IMPLEMENTATION_PLAN.md`

## Current Implementation

Main code:

- `jre/uncertainty_graph.py`
- `jre/engine.py`
- `jre/black_swan.py`
- `jre/disposition_handoff.py`
- `scripts/run_dhse_benchmark.py`
- `scripts/create_dhse_study_packet.py`
- `scripts/validate_dhse_export.py`
- `data/dhse_synthetic_benchmark.jsonl`
- `tests/test_disposition_handoff.py`

Generated artifacts:

- `artifacts/dhse_reports.json`
- `artifacts/dhse_summary.json`
- `artifacts/dhse_cases.csv`
