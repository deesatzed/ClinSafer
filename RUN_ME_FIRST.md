# Run Me First

## Judgment Readiness demo

Primary CEO demo:

```bash
cd judgment_readiness_engine
python interactive_demo.py
```

Open:

```text
http://localhost:8001
```

Show `CEO Mode`, then run the hero refill case through `Business Impact` and `Mitigation Plan`.

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

## Tests

```bash
python -m unittest discover -s tests -v
```

## Prove the mitigation flow

```bash
python scripts/prove_mitigation_flow.py
```

This should print `proof: PASS` and show that the hero refill case blocks autonomous refill with a near-miss recall while the clean refill control remains allowed with audit.

Main files to show in an interview:

- `INTERVIEW_BRIEF.md`
- `MITIGATION_PLAN.md`
- `DOCTRONIC_INTERVIEW_STRATEGY.md`
- `BLACK_SWAN_GUARDRAILS.md`
- `interactive_demo.py`
- `artifacts/provider_dashboard_sample.html`
- `artifacts/black_swan_dashboard.html`
- `jre/engine.py`
- `jre/black_swan.py`
- `data/synthetic_jre_cases_flat.csv`
- `artifacts/black_swan_guardrail_matrix.csv`
