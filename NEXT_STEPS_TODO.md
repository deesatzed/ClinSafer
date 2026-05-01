# Next Steps TODO

Last updated: 2026-05-01

Current repo state at creation:

```text
origin/main: 73872d5 Add next steps TODO roadmap
checkpoint: checkpoint-empirical-foundation-2026-04-30
tests: 358 passed
```

## Current State

What works:

- JRE deterministic judgment-readiness engine with clinical uncertainty graph.
- Black Swan guardrail layer with autonomy caps and assumption register.
- Interactive demo, transcript intake, input coverage audit, and final recommendations.
- DHSE retrospective disposition-handoff benchmark with PTR-B labels.
- Any Dispo umbrella plan for lower-acuity risk, admission-benefit uncertainty,
  level-of-care mismatch, and uncertainty-preserving review.
- Canonical DHSE CSV contract and leakage validator.
- Study-packet generator with manifest, code/input hashes, and methods snapshot.
- Empirical uncertainty feature export for TabPFN, GBDT, logistic, and conformal modeling.
- Governed medical knowledge plan for source-bound guideline/red-flag acquisition.

What is real now:

- Score synthetic or canonical CSV DHSE data as the first implemented Any Dispo
  head.
- Validate a real EHR export schema.
- Generate a reproducible study packet.
- Export text-free tabular features for downstream imbalanced modeling.
- Deposit and query advisory boundary traces with support, opposition, decay,
  and retraction.
- Recall advisory near-miss patterns from sparse signatures with
  strengthen/weaken feedback.
- Evaluate a proposed disposition with `AnyDispositionReviewEngine`, including
  hard blockers, destination capability gaps, admission-benefit uncertainty,
  trace summaries, and near-miss suggestions.
- Prevent empirical models or LLM-retrieved medical facts from clearing deterministic guardrails without governance.
- Explain why the inverse problem is a review-prioritization and counterfactual
  admission-benefit problem, not a simple flipped label.

## Build TODO

1. Keep DHSE moving as the first Any Dispo head.
   - Compare logistic regression, class-weighted logistic regression, GBDT, balanced random forest, TabPFN, and TabPFN-HPO if available.
   - Optimize/report AUPRC, recall at review budget, precision at review budget, calibration, and subgroup false negatives.
   - Read feature CSV from `scripts/export_dhse_empirical_features.py`.
   - Never require a committed API key; read `TABPFN_API_KEY` from env only.
   - Initial code target: `scripts/benchmark_dhse_models.py`.

2. Integrate the new boundary trace and near-miss recall foundations.
   - Source modules: `jre/boundary_trace.py` and `jre/associative_memory.py`.
   - Advisory trace pressure is now wired into `AnyDispositionReviewReport`.
   - Add API/demo fields for trace deposits, recalled memory IDs, missing
     nodes, falsifiers, and pattern-completion keys.
   - Keep memory output advisory only; no memory-only authorization, no
     automatic downgrade of guardrails.
   - Persistence is a later step after datastore, PHI/deidentification,
     retention, and audit policies are chosen.

3. Define the Any Dispo data contract.
   - Add `docs/ANY_DISPO_CANONICAL_CSV_SCHEMA.md`.
   - Add `jre/any_dispo_contract.py`.
   - Add `data/any_dispo_column_mapping_template.csv`.
   - Add `sql/any_dispo_cohort_extract_template.sql`.
   - Preserve the DHSE leakage rule: decision-time fields are inputs; hospital-course and post-disposition fields are labels only.

4. Expand the admission-benefit uncertainty head.
   - Source module: `jre/any_disposition.py`.
   - Add deterministic blockers for lower-acuity candidate status.
   - Emit labels/signals such as `low_observed_inpatient_need`,
     `admission_benefit_uncertain`, `home_ready_review_candidate`, and
     `level_of_care_mismatch`.
   - Never emit "safe to discharge" or "unnecessary admission".
   - Next: connect this engine to real Any Dispo CSV fixtures, API/demo output,
     and empirical feature export.

5. Add Any Dispo validators and sample fixtures.
   - Add `scripts/validate_any_dispo_export.py`.
   - Add `data/sample_any_dispo_ehr_export.csv`.
   - Validate encounter timing, proposed disposition, actual disposition,
     destination capability, label fields, and adjudication fields.
   - Fail closed on post-decision fields placed in snapshot columns.

6. Export Any Dispo empirical features.
   - Add `scripts/export_any_dispo_features.py`.
   - Include JRE graph summaries, BSG state, destination capability gaps,
     blocker counts, trace pressure summaries, near-miss recall counts, DSI
     where available, and text-free label fields.
   - Exclude raw notes, diagnosis text, evidence snippets, and questions.

7. Benchmark Any Dispo models.
   - Add `scripts/benchmark_any_dispo_models.py`.
   - Compare transparent baselines, imbalanced models, GBDT, balanced forest,
     TabPFN, and later TabPFN-HPO.
   - Report lower-acuity failure capture and low observed inpatient-need review
     yield separately.

8. Add calibration and selective prediction.
   - Add isotonic/Platt calibration where dependencies allow.
   - Add temporal split support.
   - Add review threshold calibrated to positive recall.
   - Add abstention/review output when uncertainty is too wide.

9. Add conformal/risk-control layer.
   - Start with split calibration over PTR-B risk.
   - Report coverage, miss-rate bound, reviewed fraction, and false-negative audit.
   - Preserve invariant: conformal output can raise review priority, not clear guardrails.

10. Add governed medical knowledge registry.
   - Define a structured JSONL or CSV format for candidate clinical facts.
   - Include source citation, model name, prompt hash, answer hash, reviewer status, effective date, rollback notes, and monitoring plan.
   - Keep all candidates non-production until reviewed.

11. Add `scripts/query_medical_knowledge.py`.
   - Atomic clinical/guideline questions only.
   - No PHI.
   - Read model/API key from env (`XAI_API_KEY`, `GROK_MEDICAL_KNOWLEDGE_MODEL`, or OpenRouter equivalent).
   - Store candidate facts with hashes and citations.
   - Do not auto-edit `jre/templates.py` or `jre/black_swan.py`.

12. Add real-data pilot support.
   - Run `scripts/validate_dhse_export.py` on a larger canonical CSV.
   - Generate a study packet with `scripts/create_dhse_study_packet.py`.
   - Export empirical features.
   - Run model benchmarks.
   - Write pilot readout: cohort flow, label prevalence, leakage review, model results, and error analysis.

13. Add browser E2E tests for interactive demo.
   - Transcript paste.
   - Analyze flow.
   - Clinical Uncertainty Graph section rendering.
   - Final Recommendations page.
   - LLM unavailable/retry behavior.

14. Deploy latest app if needed.
   - Confirm local tests.
   - Confirm secrets are present.
   - Deploy to Fly.
   - Smoke `/`, `/demo/analyze`, and any live LLM endpoint if enabled.

## Data Collection TODO

Collect decision-time inputs:

- encounter type, arrival time, disposition decision time, and actual disposition time
- proposed disposition and level of care at the decision point
- actual disposition and accepting/admitting service if applicable
- note/MDM available at or before decision time
- resulted labs/imaging before decision time with timestamps
- vital trend before decision time with timestamps
- oxygen, respiratory support, treatments, response to treatment, consult status,
  pending tests, and unresolved red flags
- baseline risk: age band, comorbidity burden, high-risk host factors, baseline
  oxygen, baseline mobility, residence, caregiver support, medication access,
  transportation, language/cognitive barriers, and follow-up access
- destination capability: serial vitals, oxygen, IV therapy, telemetry, urgent
  reassessment, procedure/imaging access, medication reconciliation, caregiver,
  and confirmed follow-up
- trace keys suitable for deidentified memory: unresolved blockers, source
  conflicts, stale objective data, destination capability gaps, follow-up
  reliability failures, social/communication constraints, and prior near-miss
  analogue IDs when reviewed

Collect post-disposition labels:

- 24-hour, 72-hour, 7-day, and 30-day return events
- 7-day admission and 30-day unplanned readmission
- ICU/stepdown upgrade, rapid response/code, urgent procedure, new oxygen or
  ventilatory support, IV-only therapy, telemetry event, major diagnostic pivot,
  inpatient mortality, LOS, two-midnight crossing, observation conversion,
  discharge disposition, and higher-level-of-care need

Collect adjudication fields:

- reviewer role, review time, label, confidence, reason codes, missing-data
  reason, whether a trace/memory recall was useful or misleading, and whether
  the model signal would have changed review priority

## Test TODO

- Real canonical CSV export from actual EHR-like data.
- Leakage validation against intentionally dirty exports.
- PTR-B label reliability and adjudication consistency.
- Any Dispo schema validation against mixed ED, observation, admitted, transfer,
  and discharge cases.
- Admission-benefit uncertainty label reliability and adjudication consistency.
- Model performance on non-synthetic retrospective cohorts.
- Review-budget capture at 5%, 10%, and 20%.
- Calibration and false-negative concentration by subgroup.
- Review-yield capture for both lower-acuity failures and low observed
  inpatient-need cases.
- Retrieved medical facts for accuracy, source quality, and drift over time.
- New promoted rules for alert fatigue, missed sentinels, and subgroup effects.
- Boundary trace behavior under repeated weak signals, resolved conflicts,
  stale evidence, and retractions.
- Near-miss recall precision, useful-recall rate, rejected-analogue weakening,
  and false analogue audit.

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

Answer to the Any Dispo pivot:

> The system is stronger if it evaluates every proposed disposition, not just
> unsafe discharge. DHSE remains the first implemented head. The next head asks
> whether admitted or observed patients have low observed inpatient-only need and
> should be reviewed for a lower-acuity pathway. Both directions use the same
> uncertainty graph, guardrails, leakage controls, calibration, and human review.

## Immediate Next Command Set

```bash
python -m pytest tests/test_boundary_trace.py tests/test_associative_memory.py -q
python -m pytest tests/test_any_disposition.py -q
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

Then build the first Any Dispo artifacts:

```bash
# planned
python scripts/validate_any_dispo_export.py data/sample_any_dispo_ehr_export.csv --json
python scripts/export_any_dispo_features.py \
  --input data/sample_any_dispo_ehr_export.csv \
  --input-format csv \
  --output-csv artifacts/any_dispo_features.csv \
  --manifest-json artifacts/any_dispo_features_manifest.json
```
