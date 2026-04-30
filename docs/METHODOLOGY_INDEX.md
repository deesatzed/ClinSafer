# Methodology Index

This repository now contains five related but distinct methodology layers.

## 1. Judgment Readiness

Primary files:

- `jre/uncertainty_graph.py`
- `jre/engine.py`
- `jre/templates.py`
- `jre/experience.py`
- `docs/CLINICAL_UNCERTAINTY_GRAPH.md`
- `TECHNICAL_FLOW_FOR_CS_SWE.md`
- `ARCHITECTURE.md`

Method:

- Represent clinical facts as typed expert-system nodes with source priors,
  ranges, uncertainty distributions, dependencies, and action implications.
- Treat patient statements as noisy observations, not facts.
- Add game-theory strategic-signal nodes when incentives may distort source
  reliability.
- Add dynamical boundary-sensitivity fields when small value perturbations can
  flip an action threshold.
- Score completeness, reliability, objective coverage, distortion,
  contradiction, red flags, critical missingness, strategic signal load, and
  boundary sensitivity.
- Generate CLEAR questions to reduce actionable uncertainty.
- Return `READY`, `CLARIFY`, `NEED_OBJECTIVE_DATA`, or `ESCALATE`.

## 2. Assumption Sufficiency / Black Swan Guardrails

Primary files:

- `jre/black_swan.py`
- `BLACK_SWAN_GUARDRAILS.md`
- `ARCHITECTURE.md`

Method:

- Ask whether the case remains inside the validated operating envelope.
- Detect assumption breaches: wrong patient/proxy, prompt injection, social
  safety, stale/conflicting objective data, off-pathway sentinel symptoms, and
  workflow failure.
- Return a guardrail state and maximum autonomy tier.

## 3. Disposition Handoff Sufficiency

Primary files:

- `jre/dhse_contract.py`
- `jre/disposition_handoff.py`
- `scripts/run_dhse_benchmark.py`
- `scripts/validate_dhse_export.py`
- `scripts/create_dhse_study_packet.py`
- `docs/DHSE_METHODOLOGY.md`
- `docs/DHSE_BENCHMARK_SPEC.md`
- `docs/DHSE_CANONICAL_CSV_SCHEMA.md`
- `docs/DHSE_REAL_DATA_PILOT_RUNBOOK.md`
- `docs/DHSE_ADJUDICATION_CODEBOOK.md`
- `data/dhse_column_mapping_template.csv`
- `sql/dhse_cohort_extract_template.sql`

Method:

- Score only information available at ED disposition.
- Enforce the `DHSE-CSV-v1.1` contract with explicit snapshot, baseline, label,
  and fixture field roles.
- Fail closed on non-canonical post-disposition-looking fields in snapshot
  exports or snapshot JSON metadata.
- Support notes, dialogue, and hybrid inputs.
- Label outcomes retrospectively with PTR-B: objective trajectory revision plus
  measurable burden.
- Report DSI, AUROC, AUPRC, top-decile enrichment, review-budget capture,
  calibration, threshold tables, stratification, and error analysis.
- Package real-data pilots as reproducible study packets containing validation,
  full reports, compact metrics, case-level outputs, a manifest, and a methods
  snapshot.

## 4. Empirical Boundary Learning

Primary files:

- `jre/empirical_uncertainty.py`
- `scripts/export_dhse_empirical_features.py`
- `docs/EMPIRICAL_UNCERTAINTY_PLAN.md`

Method:

- Convert DHSE/JRE/BSG reports into a stable, text-free tabular feature
  contract: `DHSE-EMPIRICAL-v0.1`.
- Export DSI, graph summaries, guardrail assumptions, residual-risk fields, and
  PTR-B labels for downstream calibrated models.
- Benchmark imbalanced-data models by AUPRC, recall at review budget, precision
  at review budget, and calibration rather than raw accuracy.
- Treat TabPFN as a candidate empirical learner and not as the safety authority.
- Add selective/conformal thresholds so the empirical layer can say "review" or
  "abstain," but cannot override deterministic guardrails.

## 5. Governed Medical Knowledge Acquisition

Primary files:

- `docs/GOVERNED_MEDICAL_KNOWLEDGE_LAYER.md`
- `jre/templates.py`
- `jre/black_swan.py`

Method:

- Accept that red flags, standards, objective-data requirements, and thresholds
  require medical expert knowledge.
- Use medical-capable models only for narrow, atomic guideline questions and
  candidate fact gathering.
- Require source citation, prompt/answer hashing, clinician or qualified-reviewer
  approval, versioning, rollback, and monitoring before any candidate becomes a
  production rule.
- Preserve the invariant that retrieved clinical facts may raise review pressure
  but may not autonomously clear a case.

## Shared Safety Invariants

- The LLM is advisory, not the safety authority.
- Missing data is not treated as absent data.
- Source conflicts remain visible.
- Outcome fields are not allowed to leak into snapshot scoring.
- Memory or prior cases may suggest review targets; they may not authorize care.
- Governance is required before learned rules change production behavior.
- Empirical models and retrieved medical facts can make the system more
  conservative before validation; they cannot loosen autonomy boundaries without
  governance and outcome evidence.
