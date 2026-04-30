# DHSE Research Protocol

## Title

Disposition Handoff Sufficiency: A Retrospective Benchmark for ED Admission
Representation Quality Using Post-Discharge Trajectory Revision With Burden

## Study Type

Retrospective observational benchmark / methods study.

## Core Hypothesis

An ED-disposition-time representation can be scored for sufficiency using a
JRE/Black-Swan-derived Disposition Sufficiency Index (DSI). Lower DSI will
enrich for admissions with post-disposition trajectory revision plus measurable
burden (PTR-B), beyond simple severity or nonspecific-diagnosis heuristics.

## Primary Question

Using only information available at ED disposition, can DHSE identify admissions
whose disposition representation was under-specified or mismatched relative to a
materially revised inpatient trajectory?

## Cohort

Initial recommended cohort:

- adult ED admissions
- admitted to hospital medicine or medicine observation-to-inpatient pathways
- ED disposition timestamp available
- ED note available at or before disposition
- discharge diagnosis and LOS available

## Exclusions

Primary analysis should exclude:

- direct ICU admissions
- planned procedural admissions
- hospice or comfort-care admissions
- social or placement-only admissions
- pure chest-pain observation pathways where serial testing is the intended
  protocol
- encounters missing ED disposition timestamp
- encounters missing discharge outcome fields required for PTR-B

## ED Snapshot Inputs

Allowed scoring inputs:

- ED provider note / MDM available at disposition
- triage note if available before disposition
- key PMH / medication / allergy snapshot
- ED resulted labs and imaging before disposition
- ED vital trend before disposition
- ED treatments before disposition
- disposition diagnosis
- admitting service
- intended level of care
- optional current dialogue transcript if available

## Prohibited Scoring Inputs

These may be used only for labels or downstream analysis:

- inpatient notes
- discharge summary text
- discharge diagnosis
- post-disposition labs/imaging
- ICU transfer outcome
- LOS
- mortality
- readmission
- hospital-course narratives

## Input Modes

Analyze separately when available:

- `notes`: ED disposition documentation and structured ED facts
- `dialogue`: current elicitation transcript plus structured objective data
- `hybrid`: both sources, with source labels preserved

## Primary Label

PTR-B: Post-Disposition Trajectory Revision With Burden.

PTR-B positive requires:

```text
any trajectory revision event
AND
any burden event
```

### Trajectory Revision Events

- ED diagnosis category differs from discharge diagnosis category.
- Floor admission upgrades to stepdown or ICU within 24 hours.
- Rapid response or code within 24 hours.
- Major therapeutic pivot within 24 hours.
- Admitting service changed because the initial problem representation was
  materially wrong or incomplete.

### Burden Events

- risk-adjusted LOS at least 1.5x expected and at least 24 hours over expected
- ICU or stepdown transfer within 24 hours
- rapid response within 24 hours
- in-hospital mortality
- major procedure
- delayed definitive therapy of at least 6 hours
- discharge to higher level of care than baseline
- 30-day readmission

## Primary Predictor

DSI: Disposition Sufficiency Index, 0-100. Lower values represent higher
sufficiency risk.

Primary risk score:

```text
risk = 100 - DSI
```

DSI is generated from an expert-system clinical uncertainty graph rather than a
free-form LLM opinion. The graph contains typed clinical nodes with source
reliability priors, numeric range bands, uncertainty distributions,
dependencies, action implications, strategic-signal reliability modifiers, and
boundary-sensitivity fields.

Implemented graph signal families include missingness/objective coverage,
semantic uncertainty, contradiction, remote unobservability, numeric range risk,
clinical action pressure, game-theory strategic signal load, and dynamical
boundary sensitivity.

## Primary Metrics

- AUROC for PTR-B
- AUPRC for PTR-B
- top-decile enrichment
- capture at fixed review budgets: 5%, 10%, 20%

## Secondary Metrics

- calibration bins
- DSI threshold table
- notes/dialogue/hybrid stratification
- graph-family ablations: remove strategic signals, remove boundary
  sensitivity, remove range-risk nodes, remove missingness/objective coverage
- DHSE state stratification
- defect-family stratification
- false-positive and false-negative error analysis

## Baselines

Implemented baselines:

- structured severity heuristic
- nonspecific diagnosis heuristic
- ED LOS heuristic
- JRE-only risk
- Black Swan-only risk

Future preregistered baselines:

- structured severity logistic model
- generic LLM risk score with fixed model/prompt if the model and governance
  contract are fixed before analysis lock
- diagnosis-category mismatch baseline
- admission service / level-of-care model

## Primary Analysis

1. Build ED-disposition snapshots from the canonical CSV/JSONL contract.
2. Score each snapshot with DHSE.
3. Label PTR-B from discharge/outcome fields.
4. Compare DHSE risk against baselines using AUROC, AUPRC, enrichment, and
   review-budget capture.
5. Report calibration and threshold operating points.
6. Analyze false positives and false negatives at DSI < 75.

## Reproducible Study Packet

For real-data pilots, generate a study packet rather than manually combining
outputs:

```bash
python scripts/create_dhse_study_packet.py \
  --input path/to/canonical_export.csv \
  --input-format csv \
  --output-dir artifacts/dhse_real_pilot_YYYYMMDD
```

The packet writes:

- validation result
- full reports
- compact summary
- case-level CSV
- run manifest with input hash
- methods snapshot

The packet is the auditable unit for collaborator review and manuscript tables.

## Sensitivity Analyses

- exclude observation stays
- exclude 30-day readmission burden from PTR-B
- use 12-hour instead of 24-hour therapeutic-pivot window
- use stricter LOS burden threshold
- compare notes-only against hybrid subset when dialogue exists

## Minimum Pilot

A 50-100 admission pilot is sufficient to test:

- mapping feasibility
- missingness rate
- PTR-B prevalence
- sanity of false positives and false negatives
- whether DSI adds anything beyond simple severity

The pilot should not be presented as clinical validation.

## Reporting Guardrails

Do not claim:

- DHSE proves ED diagnostic error.
- DHSE proves causality.
- DHSE should delay admission for pending results.
- DHSE is a clinical decision tool.

Permitted claim if supported:

> DHSE identifies ED admissions whose disposition representation was
> under-specified or mismatched relative to a materially revised inpatient
> trajectory with measurable burden.
