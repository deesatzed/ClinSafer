# Next Steps TODO

Last updated: 2026-04-30

Current repo state at creation:

```text
origin/main: 0b74544 Add empirical uncertainty foundation
tests: 358 passed
```

## Current State

What works:

- JRE deterministic judgment-readiness engine with clinical uncertainty graph.
- Black Swan guardrail layer with autonomy caps and assumption register.
- Interactive demo, transcript intake, input coverage audit, and final recommendations.
- DHSE retrospective disposition-handoff benchmark with PTR-B labels.
- Canonical DHSE CSV contract and leakage validator.
- Study-packet generator with manifest, code/input hashes, and methods snapshot.
- Empirical uncertainty feature export for TabPFN, GBDT, logistic, and conformal modeling.
- Governed medical knowledge plan for source-bound guideline/red-flag acquisition.

What is real now:

- Score synthetic or canonical CSV DHSE data.
- Validate a real EHR export schema.
- Generate a reproducible study packet.
- Export text-free tabular features for downstream imbalanced modeling.
- Prevent empirical models or LLM-retrieved medical facts from clearing deterministic guardrails without governance.

## Build TODO

1. Build `scripts/benchmark_dhse_models.py`.
   - Compare logistic regression, class-weighted logistic regression, GBDT, balanced random forest, TabPFN, and TabPFN-HPO if available.
   - Optimize/report AUPRC, recall at review budget, precision at review budget, calibration, and subgroup false negatives.
   - Read feature CSV from `scripts/export_dhse_empirical_features.py`.
   - Never require a committed API key; read `TABPFN_API_KEY` from env only.

2. Add calibration and selective prediction.
   - Add isotonic/Platt calibration where dependencies allow.
   - Add temporal split support.
   - Add review threshold calibrated to positive recall.
   - Add abstention/review output when uncertainty is too wide.

3. Add conformal/risk-control layer.
   - Start with split calibration over PTR-B risk.
   - Report coverage, miss-rate bound, reviewed fraction, and false-negative audit.
   - Preserve invariant: conformal output can raise review priority, not clear guardrails.

4. Add governed medical knowledge registry.
   - Define a structured JSONL or CSV format for candidate clinical facts.
   - Include source citation, model name, prompt hash, answer hash, reviewer status, effective date, rollback notes, and monitoring plan.
   - Keep all candidates non-production until reviewed.

5. Add `scripts/query_medical_knowledge.py`.
   - Atomic clinical/guideline questions only.
   - No PHI.
   - Read model/API key from env (`XAI_API_KEY`, `GROK_MEDICAL_KNOWLEDGE_MODEL`, or OpenRouter equivalent).
   - Store candidate facts with hashes and citations.
   - Do not auto-edit `jre/templates.py` or `jre/black_swan.py`.

6. Add real-data pilot support.
   - Run `scripts/validate_dhse_export.py` on a larger canonical CSV.
   - Generate a study packet with `scripts/create_dhse_study_packet.py`.
   - Export empirical features.
   - Run model benchmarks.
   - Write pilot readout: cohort flow, label prevalence, leakage review, model results, and error analysis.

7. Add browser E2E tests for interactive demo.
   - Transcript paste.
   - Analyze flow.
   - Clinical Uncertainty Graph section rendering.
   - Final Recommendations page.
   - LLM unavailable/retry behavior.

8. Deploy latest app if needed.
   - Confirm local tests.
   - Confirm secrets are present.
   - Deploy to Fly.
   - Smoke `/`, `/demo/analyze`, and any live LLM endpoint if enabled.

## Test TODO

- Real canonical CSV export from actual EHR-like data.
- Leakage validation against intentionally dirty exports.
- PTR-B label reliability and adjudication consistency.
- Model performance on non-synthetic retrospective cohorts.
- Review-budget capture at 5%, 10%, and 20%.
- Calibration and false-negative concentration by subgroup.
- Retrieved medical facts for accuracy, source quality, and drift over time.
- New promoted rules for alert fatigue, missed sentinels, and subgroup effects.

## Strategic Positioning

Answer to the medical-expertise criticism:

> The system does not deny that red flags, thresholds, and standards require
> medical expertise. It makes that expertise explicit as governed, versioned,
> source-bound software configuration. LLMs may help retrieve candidate facts,
> but deterministic validators, qualified review, outcome testing, and
> governance decide what becomes a rule.

Answer to the empirical-modeling question:

> Imbalanced data science, TabPFN, and conformal methods are useful as empirical
> boundary learners. They can estimate review yield and identify cases where
> uncertainty is too wide. They cannot clear deterministic guardrails or grant
> autonomy without governance and outcome evidence.

## Immediate Next Command Set

```bash
python -m pytest -q
python scripts/export_dhse_empirical_features.py \
  --input data/dhse_synthetic_benchmark.jsonl \
  --input-format jsonl \
  --output-csv artifacts/dhse_empirical_features.csv \
  --manifest-json artifacts/dhse_empirical_features_manifest.json \
  --review-fraction 0.5
python scripts/create_dhse_study_packet.py \
  --input data/sample_dhse_ehr_export.csv \
  --input-format csv \
  --output-dir artifacts/dhse_sample_study_packet_next
```
