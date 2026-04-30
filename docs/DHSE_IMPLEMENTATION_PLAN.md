# DHSE Implementation Plan

## Phase 0 - First Build Increment

Status: complete.

Deliverables:

- Add `jre.disposition_handoff`.
- Export DHSE classes from `jre.__init__`.
- Add unit tests for:
  - notes input
  - dialogue input
  - hybrid/source behavior
  - PTR-B label criteria
  - benchmark helper

## Phase 1 - Synthetic Benchmark Harness

Status: complete.

Create a small JSONL fixture with controlled ED-disposition snapshots and
post-discharge trajectories.

Case families:

- sufficient ED disposition, expected inpatient course
- nonspecific disposition with high-risk host and later diagnostic revision
- floor disposition with objective instability and early ICU transfer
- dialogue-only current intake missing objective data
- note-only disposition with adequate objective record
- hybrid conflict between patient dialogue and ED note

Each fixture should include:

- `snapshot`
- `trajectory`
- expected PTR-B
- expected DHSE state
- intended defect family

Implemented fixture:

```text
data/dhse_synthetic_benchmark.jsonl
```

Runnable benchmark:

```bash
python scripts/run_dhse_benchmark.py --review-fraction 0.5
```

## Phase 2 - Retrospective Data Adapter

Status: complete for canonical JSONL and flat CSV inputs.

Build an adapter that creates `DispositionSnapshot` from a real EHR export.

Required fields:

- ED disposition timestamp
- ED note text available before or at disposition
- PMH and medication list snapshot
- ED resulted labs and imaging before disposition
- ED vital trend before disposition
- ED treatments before disposition
- disposition diagnosis, service, and level of care

Outcome adapter fields:

- discharge diagnosis category
- LOS
- expected LOS or DRG/geometric mean LOS
- ICU/stepdown transfer within 24 hours
- rapid response/code within 24 hours
- major procedure
- mortality
- readmission

Implemented entry points:

- `snapshot_from_dict(payload)`
- `trajectory_from_dict(payload)`
- `benchmark_case_from_dict(payload)`
- `load_benchmark_cases(path)`
- `benchmark_case_from_flat_row(row)`
- `load_flat_ehr_csv(path)`

The expected input shape is the same JSONL structure used by the synthetic
fixture. A site-specific EHR export should map into that shape without changing
the scoring engine.

Flat CSV schema:

```text
docs/DHSE_CANONICAL_CSV_SCHEMA.md
```

## Phase 3 - Baseline Models

Status: deterministic first-pass baselines complete.

Add reproducible baselines:

- structured severity logistic model
- diagnosis category mismatch heuristic
- ED LOS heuristic
- JRE-only
- Black Swan-only
- graph-family ablations
- generic LLM risk score only if API access and governance are approved

Implemented dependency-free baselines:

- structured severity heuristic
- nonspecific diagnosis heuristic
- ED LOS heuristic
- JRE-only risk
- Black Swan-only risk
- graph family signals exposed for ablation: missingness/objective coverage,
  numeric range risk, strategic signals, and boundary sensitivity

The generic LLM risk baseline remains intentionally unimplemented until API
access and a fixed prompt/model contract are approved.

## Phase 3b - Foundational Graph Hardening

Status: complete for deterministic expert-system foundation; pending real-cohort
calibration.

Implemented:

- `jre/uncertainty_graph.py` as the first-class scoring substrate.
- Typed clinical nodes with source priors, numeric ranges, discrete uncertainty
  distributions, dependencies, and action implications.
- Game-theory strategic signal nodes for care avoidance, answer gaming, proxy
  misalignment, coercion/observation pressure, defensive minimization, and
  documentation closure pressure.
- Reliability modifiers that prevent strategic reassurance from being treated
  as neutral evidence.
- Dynamical boundary-sensitivity fields: boundary distance, boundary fragility,
  perturbation flip risk, coupled instability load, and boundary sensitivity
  index.
- BSG assumptions for clinical graph pressure, strategic-signal reliability
  games, and boundary fragility.
- DHSE risk factors derived from graph action pressure, objective coverage,
  missingness, range risk, strategic signal load, breached nodes, and fragile
  nodes.

## Phase 4 - Paper-Ready Benchmark

Status: infrastructure complete; pending real retrospective cohort.

Finalize:

- cohort diagram
- label prevalence table
- calibration and AUROC/AUPRC
- top-decile enrichment
- ablations
- source-mode stratification: notes vs dialogue vs hybrid
- error analysis of false positives and false negatives

Implemented paper-facing artifacts:

- cohort flow counts
- label prevalence table with revision and burden event counts
- calibration bins
- threshold table at DSI 50, 65, 75, and 85
- source-mode stratification
- state stratification
- defect-family stratification
- false-positive / false-negative error analysis at DSI 75

The CLI can emit full report JSON, compact summary JSON, and per-case CSV:

```bash
python scripts/run_dhse_benchmark.py \
  --input data/dhse_synthetic_benchmark.jsonl \
  --reports-json artifacts/dhse_reports.json \
  --summary-json artifacts/dhse_summary.json \
  --case-csv artifacts/dhse_cases.csv
```

## Open Design Decisions

- Whether expected LOS comes from DRG, diagnosis group, institutional baseline,
  or a risk-adjusted model.
- Whether diagnosis category should use CCS, ICD chapters, or local service-line
  groupers.
- Whether early therapeutic pivot window is 12 hours or 24 hours.
- Whether observation admissions are analyzed separately.
