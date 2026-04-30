# Disposition Handoff Sufficiency Engine Build Spec

## Thesis

The publishable unit is not subjective handoff quality. It is whether the ED
disposition representation was sufficient for the inpatient trajectory that
actually unfolded.

The Disposition Handoff Sufficiency Engine (DHSE) adapts JRE and Black Swan
Guardrails to ED admissions. It scores only the information available at the
time of ED disposition, then the benchmark labels outcomes retrospectively after
hospital discharge.

## Primary Question

At ED disposition time, did the ED note, key PMH, resulted ED data, treatments,
and disposition diagnosis contain enough actionable information to support the
subsequent inpatient course?

This deliberately avoids penalizing normal accepting flow of care. Pending
tests, serial labs, and inpatient diagnostic workup are not failures by
themselves.

## Inputs

### Notes Mode

Use when the available source is the documented ED disposition representation.

- ED provider note / MDM
- triage note if available
- key PMH, medications, allergies
- ED vital trend
- resulted ED labs and imaging
- ED treatments
- disposition diagnosis
- admitting service
- intended level of care

Notes mode evaluates documentation and structured ED facts. It does not claim to
reconstruct the original conversation.

### Dialogue Mode

Use when the source is current conversation before a note exists.

- patient-clinician or patient-AI dialogue turns
- structured objective ED data supplied separately
- current proposed disposition label, service, and level of care if available

Dialogue mode evaluates elicitation and source reliability. Objective data must
be provided separately or remains absent.

### Hybrid Mode

Use when both dialogue and notes are available. Source labels are preserved so
the engine can detect patient-note or chart-note conflicts instead of silently
merging them.

## Outputs

DHSE returns:

- Disposition Sufficiency Index (DSI), 0-100
- state:
  - `SUFFICIENT`
  - `UNDER_SPECIFIED`
  - `ACUITY_MISMATCH_RISK`
  - `DIAGNOSTIC_PIVOT_RISK`
- JRE state and Black Swan state
- risk factors and protective factors
- input limitations
- optional retrospective PTR-B label when discharge outcome is supplied

## DSI Interpretation

DSI is not a diagnosis score. It is an information sufficiency score.

Low DSI can come from:

- low JRE readiness
- Black Swan assumption failure
- objective instability at floor/observation disposition
- nonspecific disposition label in a high-risk context
- treatment intensity exceeding the problem representation
- high-risk host factors that make generic labels fragile

## Non-Goals

DHSE does not:

- require all pending tests to be resulted before admission
- punish appropriate diagnostic uncertainty
- require a definitive ED diagnosis
- replace inpatient judgment
- infer causality from LOS alone
- use discharge outcome fields while scoring the ED snapshot

## Implemented Build

The implemented build includes:

- `DispositionSnapshot`
- `PostDischargeTrajectory`
- `TrajectoryBurdenLabel`
- `DispositionSufficiencyReport`
- `BenchmarkCase`
- `BenchmarkRun`
- `DispositionHandoffSufficiencyEngine`
- notes/dialogue/hybrid input conversion to JRE case input
- PTR-B retrospective labeler
- JSONL benchmark loader
- canonical flat EHR CSV loader
- benchmark helper for AUROC, AUPRC, top-decile enrichment, and review-budget capture
- deterministic baselines
- paper-facing analysis tables:
  - cohort flow
  - label prevalence
  - calibration
  - threshold table
  - source-mode stratification
  - state stratification
  - defect-family stratification
  - false-positive / false-negative analysis

Implemented files:

```text
jre/disposition_handoff.py
scripts/run_dhse_benchmark.py
data/dhse_synthetic_benchmark.jsonl
tests/test_disposition_handoff.py
docs/DHSE_METHODOLOGY.md
docs/DHSE_BENCHMARK_SPEC.md
docs/DHSE_CANONICAL_CSV_SCHEMA.md
```

Generated example artifacts:

```text
artifacts/dhse_reports.json
artifacts/dhse_summary.json
artifacts/dhse_cases.csv
```
