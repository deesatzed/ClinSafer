# Run Me First

## Judgment Readiness demo

Primary interview demo:

```bash
cd judgment_readiness_engine
python interactive_demo.py
```

Open:

```text
http://localhost:8001
```

Open `FINAL_INTERVIEW_READINESS.md` first for the current talk track.

Recommended live path:

1. Overview.
2. `Show Cost-Fear Case` or `Run Hero Refill Case`.
3. Optional: `Paste Transcript` with real encounter text.
4. `Analyze This Encounter`.
5. `Statement vs Fact`.
6. `Provenance & Authority`.
7. `Known Unknowns Map`.
8. `Autonomy Boundary`.
9. `Final Recommendations`.
10. Governance Review only if there is time.

Classic CLI/static demo:

```bash
cd judgment_readiness_engine
python demo.py --case CP-001-heartburn-pressure
python demo.py --case DY-001-denies-sob-low-ox
python demo.py --case RF-001-bp-normal-no-number
python demo.py --all --html artifacts/provider_dashboard_sample.html --json artifacts/reports.json
```

Open:

```text
artifacts/provider_dashboard_sample.html
```

## Black Swan Guardrail demo

```bash
python black_swan_demo.py --case BS-003-offpath-stroke-in-refill
python black_swan_demo.py --all --html artifacts/black_swan_dashboard.html --json artifacts/black_swan_reports.json --matrix artifacts/black_swan_guardrail_matrix.csv
```

Open:

```text
artifacts/black_swan_dashboard.html
```

## DHSE disposition handoff benchmark

Synthetic benchmark:

```bash
python scripts/run_dhse_benchmark.py --review-fraction 0.5
```

Emit paper-facing artifacts:

```bash
python scripts/run_dhse_benchmark.py \
  --reports-json artifacts/dhse_reports.json \
  --summary-json artifacts/dhse_summary.json \
  --case-csv artifacts/dhse_cases.csv
```

Canonical flat EHR export:

```bash
python scripts/run_dhse_benchmark.py --input path/to/export.csv --input-format csv
```

Validate a real export:

```bash
python scripts/validate_dhse_export.py path/to/export.csv --json
```

Create a full reproducible real-data pilot packet:

```bash
python scripts/create_dhse_study_packet.py \
  --input path/to/export.csv \
  --input-format csv \
  --output-dir artifacts/dhse_real_pilot_YYYYMMDD
```

Open:

```text
artifacts/dhse_summary.json
artifacts/dhse_cases.csv
```

## Empirical uncertainty feature export

```bash
python scripts/export_dhse_empirical_features.py \
  --input data/dhse_synthetic_benchmark.jsonl \
  --input-format jsonl \
  --output-csv artifacts/dhse_empirical_features.csv \
  --manifest-json artifacts/dhse_empirical_features_manifest.json \
  --review-fraction 0.5
```

Open:

```text
artifacts/dhse_empirical_features.csv
artifacts/dhse_empirical_features_manifest.json
```

For TabPFN or medical-knowledge APIs, place keys only in `.env` or deployment
secrets. Do not commit real keys.

## Tests

```bash
python -m pytest -q
```

## Prove the mitigation flow

```bash
python scripts/prove_mitigation_flow.py
```

This should print `proof: PASS` and show that the hero refill case blocks autonomous refill with a near-miss recall while the clean refill control remains allowed with audit.

Main files to show in an interview:

- `FINAL_INTERVIEW_READINESS.md`
- `INTERVIEW_BRIEF.md`
- `MITIGATION_PLAN.md`
- `INTERVIEW_STRATEGY.md`
- `BLACK_SWAN_GUARDRAILS.md`
- `docs/ANY_DISPOSITION_MODEL_PLAN.md`
- `docs/DHSE_METHODOLOGY.md`
- `docs/DHSE_BENCHMARK_SPEC.md`
- `docs/DHSE_CANONICAL_CSV_SCHEMA.md`
- `docs/DHSE_REAL_DATA_PILOT_RUNBOOK.md`
- `docs/DHSE_ADJUDICATION_CODEBOOK.md`
- `docs/EMPIRICAL_UNCERTAINTY_PLAN.md`
- `docs/GOVERNED_MEDICAL_KNOWLEDGE_LAYER.md`
- `interactive_demo.py`
- `artifacts/provider_dashboard_sample.html`
- `artifacts/black_swan_dashboard.html`
- `artifacts/dhse_summary.json`
- `artifacts/dhse_cases.csv`
- `jre/engine.py`
- `jre/black_swan.py`
- `jre/disposition_handoff.py`
- `data/synthetic_jre_cases_flat.csv`
- `data/dhse_synthetic_benchmark.jsonl`
- `data/dhse_column_mapping_template.csv`
- `sql/dhse_cohort_extract_template.sql`
- `artifacts/black_swan_guardrail_matrix.csv`
