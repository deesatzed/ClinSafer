# Methodology Index

This repository now contains eight related but distinct methodology layers.

The public app route (`/`) now presents these layers as a landing page for
testing, promotion, and stakeholder review. The working demo remains available
at `/demo`, so reviewers can move from the methodology narrative into live
case and transcript testing without losing the safety framing.

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

## 3. Any Disposition Judgment Readiness

Primary files:

- `jre/any_disposition.py`
- `docs/ANY_DISPOSITION_MODEL_PLAN.md`
- `ARCHITECTURE.md`
- `README.md`

Planned files:

- `jre/any_dispo_contract.py`
- `scripts/validate_any_dispo_export.py`
- `scripts/export_any_dispo_features.py`
- `scripts/benchmark_any_dispo_models.py`
- `docs/ANY_DISPO_CANONICAL_CSV_SCHEMA.md`
- `docs/ANY_DISPO_ADJUDICATION_CODEBOOK.md`
- `data/any_dispo_column_mapping_template.csv`
- `sql/any_dispo_cohort_extract_template.sql`

Method:

- Treat every proposed disposition as a fit problem between patient state,
  uncertainty, destination capability, follow-up reliability, and monitoring
  need.
- Support lower-acuity risk, admission-benefit uncertainty, level-of-care
  mismatch, and uncertainty-preservation questions under one umbrella.
- Preserve deterministic blockers for unstable, worsening, unresolved, or
  inadequately supported cases.
- Use empirical models only to prioritize review and abstain under uncertainty.
- Avoid claims such as "safe to discharge" or "unnecessary admission"; use
  review labels such as `home_ready_review_candidate`,
  `admission_benefit_uncertain`, and `level_of_care_mismatch`.
- Keep outcome and hospital-course data as labels only.
- Use implemented `AnyDispositionReviewEngine` states to route review:
  `LOWER_ACUITY_BLOCKED`, `ADMISSION_BENEFIT_UNCERTAIN`,
  `LEVEL_OF_CARE_MISMATCH`, `INSUFFICIENT_EVIDENCE`,
  `REVIEW_RECOMMENDED`, or `NO_REVIEW_SIGNAL`.

## 4. Disposition Handoff Sufficiency

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

- Treat DHSE as the first implemented Any Dispo head.
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

## 5. Boundary Trace And Near-Miss Recall

Primary files:

- `jre/boundary_trace.py`
- `jre/associative_memory.py`
- `ARCHITECTURE.md`
- `MITIGATION_PLAN.md`

Method:

- Deposit unresolved claims, constraints, signals, questions, outcomes, and
  retractions into a stigmergic-style trace field.
- Carry symbolic keys, confidence, support, opposition, decay, evidence IDs,
  and status so repeated weak signals do not disappear between turns.
- Recall prior near-miss boundary shapes from sparse signatures using an
  in-memory VAMS-style associative layer.
- Use Hebbian strengthening for confirmed useful recalls and anti-Hebbian
  weakening for rejected recalls.
- Return only advisory missing nodes, falsifiers, review actions, and pattern
  completion keys.
- Keep all memory output downstream of deterministic JRE/BSG/Any Dispo
  validators and governance.

## 6. Cognitive Bias Field

Primary files:

- `jre/cognitive_bias_field.py`
- `jre/reasoning_integrity.py`
- `jre/any_disposition.py`

Method:

- Treat cognitive bias as advisory uncertainty pressure, not as a clinician
  accusation or diagnosis.
- Convert JRE, BSG, reasoning-integrity, Any Dispo, trace, and memory outputs
  into bias entropy, dominant bias factors, information-gain candidates,
  hypothesis survival, disposition fragility, cognitive friction, and fresh-eyes
  payloads.
- Rank next evidence by whether it can change the action or disposition
  boundary, not by whether it confirms the current frame.
- Detect fragile disposition states by perturbing follow-up, caregiver support,
  destination capability, unresolved red flags, and near-threshold vitals.
- Preserve the invariant that this layer can only increase caution or require
  disconfirming evidence; it cannot clear guardrails or order disposition.

## 7. Empirical Boundary Learning

Primary files:

- `jre/empirical_uncertainty.py`
- `scripts/export_dhse_empirical_features.py`
- `docs/EMPIRICAL_UNCERTAINTY_PLAN.md`

Method:

- Convert DHSE/Any Dispo/JRE/BSG reports into stable, text-free tabular feature
  contracts, starting with `DHSE-EMPIRICAL-v0.1`.
- Export DSI, graph summaries, guardrail assumptions, residual-risk fields, and
  PTR-B labels for downstream calibrated models.
- Benchmark imbalanced-data models by AUPRC, recall at review budget, precision
  at review budget, and calibration rather than raw accuracy.
- Treat TabPFN as a candidate empirical learner and not as the safety authority.
- Add selective/conformal thresholds so the empirical layer can say "review" or
  "abstain," but cannot override deterministic guardrails.

## 8. Governed Medical Knowledge Acquisition

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
- Cognitive bias field outputs may require friction or fresh-eyes review; they
  may not diagnose clinicians or authorize care.
- Governance is required before learned rules change production behavior.
- Empirical models and retrieved medical facts can make the system more
  conservative before validation; they cannot loosen autonomy boundaries without
  governance and outcome evidence.
- Any Dispo review signals do not order a disposition. They route cases to the
  right review path and preserve the reason uncertainty remains.
