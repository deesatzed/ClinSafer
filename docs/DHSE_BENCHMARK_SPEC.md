# DHSE Benchmark Specification

## Benchmark Name

Disposition Handoff Sufficiency Benchmark (DHSB)

DHSB is the first implemented benchmark under the broader Any Dispo program.
It measures one direction: ED disposition representation sufficiency for
admitted patients. Separate Any Dispo benchmarks will measure lower-acuity
failure, admission-benefit uncertainty, and level-of-care mismatch.

## Primary Label

Post-Disposition Trajectory Revision with Burden (PTR-B)

PTR-B is positive only when both conditions are met:

1. An objective trajectory revision occurred after ED disposition.
2. The revision carried measurable clinical or resource burden.

This prevents the benchmark from treating ordinary inpatient workup, pending
results, or expected diagnostic refinement as failure.

## Trajectory Revision Events

Count any of:

- ED diagnosis category differs from discharge diagnosis category.
- Floor admission upgraded to stepdown or ICU within 24 hours.
- Rapid response or code within 24 hours.
- Major therapeutic pivot within 24 hours, such as pressors, intubation, insulin
  drip, transfusion, emergent anticoagulation, broad-spectrum antibiotics,
  emergent procedure, cath lab, OR, or stroke pathway.
- Admitting service changed because the initial problem representation was
  wrong or materially incomplete.

## Burden Events

Count any of:

- risk-adjusted LOS at least 1.5x expected and at least 24 hours over expected
- ICU or stepdown transfer within 24 hours
- rapid response within 24 hours
- in-hospital mortality
- major procedure
- delayed definitive therapy of at least 6 hours
- discharge to a higher level of care than baseline
- 30-day readmission

## PTR-B Formula

```text
PTR-B = any(trajectory_revision_events) AND any(burden_events)
```

## Primary Prediction Task

Using only information available at ED disposition, predict PTR-B.

The model input is the ED snapshot. The label is assigned after discharge.

## Scoring Substrate

The primary DHSE score is derived from the expert-system clinical uncertainty
graph, not from subjective reviewer impression.

Implemented graph-derived signal families:

- missingness and objective-data coverage
- source reliability and semantic uncertainty
- contradiction and remote-unobservable load
- expert-defined numeric range risk
- clinical action pressure
- strategic-signal load from game-theory reliability problems
- boundary sensitivity from near-threshold and coupled-instability dynamics

Strategic-signal examples include care avoidance, answer gaming, proxy
misalignment, coercion/observation pressure, defensive minimization, and
documentation closure pressure. Boundary-sensitivity examples include vitals or
labs close to action-changing thresholds and multiple related nodes near worse
bands.

## Primary Metrics

- AUROC for PTR-B
- AUPRC for PTR-B when class imbalance is substantial
- top-decile enrichment
- capture at fixed review budget:

```text
PTR-B cases captured among lowest-DSI X% of admissions / all PTR-B cases
```

Recommended fixed budgets: 5%, 10%, 20%.

## Required Baselines

Minimum baselines:

- structured severity model: age, ESI, Charlson, admission service, level of
  care, abnormal vital/lab flags
- diagnosis-discordance-only model
- ED LOS or boarding-time model
- JRE-only score without Black Swan Guardrails
- Black Swan-only autonomy state without JRE score
- graph family ablations: remove strategic signals; remove boundary
  sensitivity; remove range-risk nodes; remove missingness/objective coverage

The generic LLM risk baseline is optional until the model, prompt, API access,
and governance contract are fixed. The key manuscript claim requires
incremental value over structured severity, not merely a high unadjusted
association.

## Recommended Cohort

Start with adult ED admissions to hospital medicine or observation-to-inpatient
medicine.

Exclude from the primary benchmark:

- direct ICU admissions
- planned procedural admissions
- hospice or comfort-care admissions
- social or placement-only admissions
- pure chest-pain observation pathways where serial testing is the intended
  pathway
- encounters missing the ED disposition timestamp or discharge outcome

## Model Governance Guardrail

The scoring function must never use:

- discharge diagnosis
- inpatient notes
- post-disposition labs or imaging
- ICU transfer result
- LOS
- mortality
- readmission

Those fields are labels only.

## Publication Positioning

The paper should not claim that DHSE proves ED error. It should claim:

> DHSE identifies ED admissions whose disposition representation was
> under-specified or mismatched relative to a materially revised inpatient
> trajectory with measurable burden.
