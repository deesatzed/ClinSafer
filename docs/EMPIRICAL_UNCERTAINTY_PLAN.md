# Empirical Uncertainty Plan

## Purpose

This layer parameterizes uncertainty from retrospective data without replacing
the deterministic safety shell.

The question is:

```text
Given the JRE uncertainty graph, Black Swan guardrails, and DHSE score,
what empirical boundary patterns predict PTR-B or review yield?
```

The output is not clinical authorization. It is a calibrated review signal that
can only make the autonomy governor more conservative.

## Implemented Foundation

Primary files:

- `jre/empirical_uncertainty.py`
- `scripts/export_dhse_empirical_features.py`
- `tests/test_empirical_uncertainty.py`

Feature contract:

```text
DHSE-EMPIRICAL-v0.1
```

Export:

```bash
python scripts/export_dhse_empirical_features.py \
  --input data/dhse_synthetic_benchmark.jsonl \
  --input-format jsonl \
  --output-csv artifacts/dhse_empirical_features.csv \
  --manifest-json artifacts/dhse_empirical_features_manifest.json \
  --review-fraction 0.5
```

The export includes:

- DSI and risk score
- encoded DHSE/JRE/BSG states
- JRE score components
- BSG novelty, residual risk, findings, and assumption counts
- uncertainty graph summary metrics
- review-budget curve
- empirical positive-recall floor threshold
- model contract metadata for TabPFN or other tabular learners

It intentionally excludes:

- ED note text
- diagnosis text
- dialogue text
- evidence snippets
- raw answers/questions
- patient-facing free text

## Modeling Stack

Run models in this order:

1. Transparent baselines:
   - calibrated logistic regression
   - class-weighted logistic regression
   - monotone or constrained scorecard where feasible
2. Strong tabular baselines:
   - calibrated gradient boosting
   - balanced random forest
   - XGBoost or LightGBM if available
3. Tabular foundation models:
   - baseline TabPFN
   - TabPFN with metric tuning / HPO
   - fine-tuned TabPFN only after stable schema and enough rows
4. Wrappers:
   - calibration
   - selective prediction
   - conformal or risk-control thresholds

## Imbalanced Data Rules

PTR-B will likely be uncommon. Use metrics that respect rare positives:

- AUPRC
- precision at review budget
- recall at review budget
- capture at top 5%, 10%, and 20%
- false-negative rate among high-acuity states
- calibration in high-risk bins

Do not optimize raw accuracy. A model that calls every case negative may look
accurate and still be clinically useless.

Use oversampling cautiously. Synthetic minority rows can create plausible but
clinically incoherent cases unless constrained by the uncertainty graph and
reviewed by governance.

## TabPFN Role

TabPFN is a candidate empirical learner for small-to-medium tabular DHSE
datasets. Use it as a benchmark and calibration target, not as the safety
authority.

First pass:

```text
export DHSE empirical features
remove case_id and ptr_b from X
train/evaluate TabPFN on temporal or site-held-out splits
compare against calibrated GBDT and logistic baselines
calibrate or conformalize probabilities before use
```

Secret handling:

```text
TABPFN_API_KEY must be set in environment or secret manager.
Never commit a real key.
```

Fine-tuning criteria:

- schema is stable
- at least 1000 rows, preferably more
- validation split respects time/site boundaries
- baseline TabPFN and tuned GBDT have plateaued
- fine-tuning improves AUPRC and recall-at-review-budget without degrading
  calibration or subgroup behavior

## Conformal / Selective Prediction

The goal is not just risk prediction. The goal is knowing when the empirical
model is not allowed to reassure.

Safety rule:

```text
Empirical layer can raise review priority.
Empirical layer cannot clear a deterministic guardrail.
```

Use:

- split calibration sets
- temporal validation
- review threshold calibrated to positive recall
- abstention when prediction sets or risk intervals are too wide
- subgroup calibration checks by input mode, state, age band, and defect family

## Acceptance Gate

The empirical layer is useful only if it shows:

- no leakage from label fields into features
- stable AUPRC across temporal/site splits
- meaningful capture at realistic review budgets
- interpretable false positives and false negatives
- no subgroup where false negatives concentrate silently
- calibration good enough for thresholding

Until then, empirical scores remain research artifacts.
