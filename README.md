# Judgment Readiness Engine (JRE)

Prototype interview artifact for a clinical AI company: an **Unknowns Intelligence Layer** that sits between patient intake, disposition review, and any autonomous or semi-autonomous action.

The core question is not “what is the diagnosis?”

The core question is:

> **Do we have enough reliable information, with acceptable residual uncertainty, to act safely?**

The disposition version of that question is now broader:

> **For any proposed disposition, is the destination and level of monitoring justified by the evidence we have, the uncertainty that remains, and the resources available at that destination?**

This module demonstrates a small, deterministic version of that idea using synthetic data.

---

## What it does

JRE evaluates a clinical intake transcript and returns:

1. **Judgment Readiness Index (JRI)** — 0–100 score for whether the encounter is decision-ready.
2. **State** — `READY`, `CLARIFY`, `NEED_OBJECTIVE_DATA`, or `ESCALATE`.
3. **MUD map** — Missing, Uncertain, Distorted, contradictory, objective-needed, and remote-unknowable information.
4. **CLEAR questions** — highest-yield next questions to reduce uncertainty.
5. **Provider-facing boundary map** — what is known, what is not known, and what cannot be known remotely.
6. **Rule traces** — why the module flagged something, for governance and trust.
7. **Black Swan Guardrail state** — whether assumptions failed and how far autonomy is allowed to proceed.
8. **Mitigation plan** — immediate controls plus implemented advisory boundary traces, VAMS-style near-miss recall, governed template promotion, and churn/routing reduction.

---

## Why this matters

Most AI intake tools treat patient statements as facts. JRE treats them as **noisy observations**.

Example:

> Patient: “No chest pain. It is just pressure after walking upstairs.”

A normal intake may document: “Denies chest pain.”

JRE documents:

> Denies “pain,” but describes exertional pressure/burning. Low reliability because of pain-word boundary. Remote autonomous path is unsafe; clarify and escalate.

---

## Conceptual model

### Clinical uncertainty graph

The core safety object is now an explicit expert-system graph, not a generic AI
opinion. Clinical facts are represented as typed nodes with source reliability,
range bands, uncertainty distributions, dependencies, and action implications.
JRE builds and scores this graph. Black Swan Guardrails use the graph to cap
allowed action. DHSE tests whether graph uncertainty and guardrail boundaries
matter against downstream outcomes.

See:

```text
docs/CLINICAL_UNCERTAINTY_GRAPH.md
docs/ANY_DISPOSITION_MODEL_PLAN.md
docs/EMPIRICAL_UNCERTAINTY_PLAN.md
docs/GOVERNED_MEDICAL_KNOWLEDGE_LAYER.md
```

### MUD → CLEAR

**MUD** classifies the uncertainty:

- **Missing** — important facts not obtained.
- **Uncertain** — answers present but low-confidence.
- **Distorted** — health-literacy, vague language, recall error, or vocabulary mismatch.
- **Contradictory** — answers conflict with other answers.
- **Unknowable remotely** — requires exam, ECG, labs, image, chart, device, or time.

**CLEAR** chooses the next question:

- **Clarify language**
- **Link to concrete examples**
- **Elicit functional evidence**
- **Ask for objective/collateral source**
- **Re-score uncertainty**

### UQ-JST

JRE implements a prototype **Uncertainty-Qualified Judgment Sufficiency Threshold**:

> Not “do we have enough information?” but “do we have enough reliable information after accounting for missingness, distortion, contradictions, and remote limits?”

---

## Quick start

```bash
cd judgment_readiness_engine
python demo.py --case CP-001-heartburn-pressure
python demo.py --all --html artifacts/provider_dashboard_sample.html --json artifacts/reports.json
python black_swan_demo.py --all --html artifacts/black_swan_dashboard.html --json artifacts/black_swan_reports.json --matrix artifacts/black_swan_guardrail_matrix.csv
python -m pytest -q
```

No external dependencies are required for the core demo.

### Optional: API Server

```bash
pip install fastapi uvicorn pydantic
python api_server.py
# Runs at http://localhost:8000 with interactive docs at /docs
```

### Interactive Demo

```bash
pip install -r requirements.txt
python interactive_demo.py
# Runs at http://localhost:8001
```

Live Fly deployment:

```text
https://clinsafer.fly.dev/
```

Final interview readiness write-up:

```text
FINAL_INTERVIEW_READINESS.md
```

For hosted demos, use the included `Procfile`:

```bash
uvicorn interactive_demo:app --host 0.0.0.0 --port $PORT
```

GitHub stores the repo; a dynamic FastAPI app still needs a runtime such as Render, Railway, Fly.io, or Codespaces.

### Run From GitHub Codespaces

1. Open the repository on GitHub.
2. Click `Code` → `Codespaces` → `Create codespace on main`.
3. In the Codespaces terminal:

```bash
python interactive_demo.py
```

4. Open the forwarded `8001` port when prompted.

### Optional: LLM-Augmented Detection

The engine works in pure regex mode by default. To enable LLM-augmented detection (catches novel phrasings regex misses):

```bash
cp .env.example .env
# Edit .env and set your OpenRouter API key
# Demo default: OPENROUTER_MODEL=qwen/qwen3.6-flash
# Set OPENROUTER_MODEL in .env to override it
```

The interactive demo uses bounded LLM roles. The default async safety pass runs
`extractor,boundary,verifier,bias_auditor` in parallel. The bias auditor looks
for reasoning-path failure modes such as anchoring, premature closure,
confirmation bias, omission bias, diagnostic momentum, and overconfidence.
Patient communication and workflow synthesis roles are configured but disabled
by default because they are post-governor drafting roles, not safety authorities.

```bash
OPENROUTER_ANALYSIS_ROLES=extractor,boundary,verifier,bias_auditor
OPENROUTER_EXTRACTOR_MODEL=qwen/qwen3.6-flash
OPENROUTER_BOUNDARY_MODEL=qwen/qwen3.6-flash
OPENROUTER_VERIFIER_MODEL=qwen/qwen3.6-flash
OPENROUTER_BIAS_MODEL=qwen/qwen3.6-flash
OPENROUTER_PATIENT_MODEL=qwen/qwen3.6-flash
OPENROUTER_WORKFLOW_MODEL=qwen/qwen3.6-flash
OPENROUTER_MAX_PARALLEL_ROLES=4
OPENROUTER_TIMEOUT_SECONDS=75
```

On Fly, these are normal secrets:

```bash
flyctl secrets set OPENROUTER_ANALYSIS_ROLES=extractor,boundary,verifier,bias_auditor
flyctl secrets set OPENROUTER_EXTRACTOR_MODEL=qwen/qwen3.6-flash
flyctl secrets set OPENROUTER_BOUNDARY_MODEL=qwen/qwen3.6-flash
flyctl secrets set OPENROUTER_VERIFIER_MODEL=qwen/qwen3.6-flash
flyctl secrets set OPENROUTER_BIAS_MODEL=qwen/qwen3.6-flash
```

LLM findings remain advisory. Curated rules, guardrails, and the ensemble
governor still determine the final autonomy boundary.

When no API key is configured, the engine degrades gracefully to regex-only mode with no errors.

---

## Example output

```text
State=ESCALATE; JRI=2.2/100; completeness=0.61, reliability=0.48, objective=0.00.
Top uncertainty/red-flag signals: red_flag:symptom_quality; contradictory:symptom_quality; red_flag:dyspnea; unknowable_remote:ecg.
Next best questions:
1. When you say it is not chest pain, is there pressure, tightness, heaviness, squeezing, burning, or discomfort anywhere in the chest, jaw, arm, back, or upper belly?
2. Do you have a current blood pressure, heart rate, and oxygen level reading? What are the numbers?
3. Can you walk across the room and speak a full sentence without stopping to catch your breath?
```

---

## Files

```text
jre/models.py          Data models
jre/templates.py       Domain-specific safety slots and red-flag patterns
jre/engine.py          Judgment Readiness scoring, MUD map, CLEAR questions
jre/experience.py      Experiential learning memory for distortion priors and question yield
jre/boundary_trace.py  Stigmergic-style trace field for unresolved boundary signals
jre/associative_memory.py  VAMS-style advisory near-miss recall from sparse signatures
jre/synthetic_data.py  Synthetic cases and dataset generator
jre/black_swan.py     Black Swan Guardrail Layer, assumption register, autonomy caps
jre/any_disposition.py  Any Dispo review engine for proposed destination fit, blockers, capability gaps, and admission-benefit uncertainty
jre/disposition_handoff.py  First implemented Any Dispo head: ED disposition handoff sufficiency scoring and PTR-B labeling
jre/empirical_uncertainty.py  Text-free empirical feature contract for TabPFN/GBDT/conformal modeling
MITIGATION_PLAN.md    Stigmergic/VAMS mitigation plan and demo update path
TELEMEDICINE_TOP_25_COVERAGE.md  Mapping of common telemedicine reasons to templates
demo.py               CLI and HTML dashboard generator
black_swan_demo.py    CLI and HTML dashboard generator for black-swan guardrails
tests/test_jre.py      Smoke tests for key safety behaviors
docs/ANY_DISPOSITION_MODEL_PLAN.md  Umbrella plan for discharge, admission, observation, transfer, and level-of-care review
docs/DHSE_*.md         First implemented Any Dispo head: disposition handoff benchmark/build specifications
data/                 Synthetic JSONL + flat CSV dataset
artifacts/            Demo output, reports, provider dashboard HTML
```

## Any Dispo focus

The product framing is now **Any Dispo Judgment Readiness**. The goal is not
only to find discharged patients who should have stayed. The same safety shell
should also find admitted, observed, transferred, or higher-acuity patients
whose disposition benefit is uncertain and should be reviewed.

The four disposition questions are:

1. lower-acuity risk: home, telehealth, or low-monitoring path may be unsafe;
2. higher-acuity benefit uncertainty: admission, observation, or transfer may
   need review for low observed inpatient-only need;
3. level-of-care mismatch: floor, telemetry, stepdown, ICU, SNF, rehab, or home
   health may not match the resource need;
4. uncertainty preservation: the evidence may not support either reassurance or
   escalation yet.

The system should say `candidate for disposition review`, not `safe to
discharge` or `unnecessary admission`.

The package now includes `AnyDispositionReviewEngine`, a deterministic first
pass that evaluates a proposed destination against decision-time evidence and
destination capability. It can emit:

- `LOWER_ACUITY_BLOCKED`
- `ADMISSION_BENEFIT_UNCERTAIN`
- `LEVEL_OF_CARE_MISMATCH`
- `INSUFFICIENT_EVIDENCE`
- `REVIEW_RECOMMENDED`
- `NO_REVIEW_SIGNAL`

These are review states, not disposition orders.

See:

```text
docs/ANY_DISPOSITION_MODEL_PLAN.md
```

## Disposition Handoff Sufficiency extension

The package now includes a Disposition Handoff Sufficiency Engine (DHSE). DHSE
is the first implemented Any Dispo head. It uses only information available at
ED disposition, then labels post-discharge outcomes with Post-Disposition
Trajectory Revision with Burden (PTR-B). Pending tests and expected inpatient
workup are not failures by themselves; PTR-B requires both objective trajectory
revision and measurable burden.

Run the synthetic fixture:

```bash
python scripts/run_dhse_benchmark.py \
  --summary-json artifacts/dhse_summary.json \
  --case-csv artifacts/dhse_cases.csv
```

Validate a real canonical CSV export:

```bash
python scripts/validate_dhse_export.py path/to/canonical_export.csv --json
```

The validator uses contract `DHSE-CSV-v1.1`, reports snapshot/baseline/label
field roles, and fails closed if post-disposition-looking fields appear in the
snapshot export.

Create the reproducible retrospective pilot packet:

```bash
python scripts/create_dhse_study_packet.py \
  --input path/to/canonical_export.csv \
  --input-format csv \
  --output-dir artifacts/dhse_real_pilot_YYYYMMDD
```

The packet manifest records validation and field-role accounting, input and
code hashes, git provenance, full reports, compact metrics, case-level outputs,
and a methods snapshot.

Pilot build documents:

- `docs/DHSE_REAL_DATA_PILOT_RUNBOOK.md`
- `docs/DHSE_ADJUDICATION_CODEBOOK.md`
- `docs/DHSE_CANONICAL_CSV_SCHEMA.md`
- `data/dhse_column_mapping_template.csv`
- `sql/dhse_cohort_extract_template.sql`

DHSE supports three input modes:

- `notes`: ED note, key PMH, resulted ED data, treatments, disposition diagnosis,
  service, and level of care.
- `dialogue`: current patient/clinician dialogue plus structured objective data.
- `hybrid`: notes and dialogue with source labels preserved for conflict checks.

Build docs:

```text
docs/DHSE_BUILD_SPEC.md
docs/DHSE_BENCHMARK_SPEC.md
docs/DHSE_CANONICAL_CSV_SCHEMA.md
docs/DHSE_METHODOLOGY.md
docs/DHSE_IMPLEMENTATION_PLAN.md
docs/METHODOLOGY_INDEX.md
```

Run the synthetic benchmark:

```bash
python scripts/run_dhse_benchmark.py --review-fraction 0.5
```

Run a canonical flat EHR export:

```bash
python scripts/run_dhse_benchmark.py --input path/to/export.csv --input-format csv
```

Emit paper-facing artifacts:

```bash
python scripts/run_dhse_benchmark.py \
  --reports-json artifacts/dhse_reports.json \
  --summary-json artifacts/dhse_summary.json \
  --case-csv artifacts/dhse_cases.csv
```

Export empirical uncertainty features for imbalanced modeling, TabPFN, and
selective/conformal wrappers:

```bash
python scripts/export_dhse_empirical_features.py \
  --input data/dhse_synthetic_benchmark.jsonl \
  --input-format jsonl \
  --output-csv artifacts/dhse_empirical_features.csv \
  --manifest-json artifacts/dhse_empirical_features_manifest.json \
  --review-fraction 0.5
```

Use `TABPFN_API_KEY` only from `.env`, Fly secrets, or another secret manager.
Do not commit real keys.

---

## How this maps to a real product

In production, the LLM would not be the safety system. LLMs would be bounded
language and reasoning assistants whose outputs remain advisory until validated.

The safety system would be:

1. **Transcript parser and input coverage audit** — proves every line was consumed or explicitly held for review.
2. **Bounded multi-role LLM pipeline** — extractor, boundary reasoner, verifier, and bias auditor propose candidate observations, coverage gaps, missing falsifiers, and cognitive forcing actions.
3. **Expert-system shell** — verifies required slots, red flags, contradictions, and remote boundaries.
4. **Reasoning integrity guard** — audits for anchoring, premature closure, confirmation bias, search satisficing, omission bias, diagnostic momentum, framing risk, and overconfidence.
5. **Uncertainty model** — confidence, missingness, distortion, and source reliability.
6. **Experience memory** — learns which questions expose hidden risk in which patient/context patterns.
7. **Stigmergic boundary trace** — implemented as an in-memory `BoundaryTraceField` that keeps unresolved claims, source conflicts, stale data, social/workflow pressure, and feedback from disappearing between turns.
8. **VAMS-style near-miss recall** — implemented as an in-memory `NearMissMemory` that recalls prior boundary failures from partial case signatures and suggests missing nodes or falsifiers.
9. **Any Dispo disposition governor** — audits whether the proposed destination
   and level of monitoring are justified, whether a lower-acuity path is blocked,
   whether admission benefit is uncertain, and whether level of care is
   mismatched.
10. **Empirical boundary learner** — uses DHSE/Any Dispo feature exports, imbalanced-data
   metrics, TabPFN/GBDT baselines, calibration, and selective/conformal
   thresholds to learn where review is needed.
11. **Governed medical knowledge layer** — asks narrow guideline/red-flag
    questions, stores source-bound candidate facts, and promotes only reviewed
    rules.
12. **Governance queue** — promotes learned rules/templates only after validation, simulation, and review.
13. **Arbiter** — decides whether the case is ready, needs clarification, needs objective data, or must escalate.
14. **Provider UI** — shows the boundary map and rule trace, not just a note summary.

This is designed to be inserted into a telehealth or autonomous-intake pipeline before refills, triage, symptom assessment, or chronic disease check-ins.

The current demo implements transcript intake, input coverage auditing,
deterministic controls, bounded multi-role LLM candidate analysis, visible
mitigation planning, and foundational in-memory trace/near-miss recall modules.
The next step is wiring these modules into the Any Dispo review path, API, and
UI while preserving the invariant that memory output is advisory candidate
risks/questions/falsifiers rather than clinical authorization.

---

## Safety note

This is a prototype for software architecture discussion. It is not a clinical protocol, medical device, diagnosis system, or patient-facing medical advice.

---

## Black Swan Guardrail extension

The package now includes a second safety wrapper: the **Black Swan Guardrail Layer**.

JRE asks:

> Do we know enough reliable clinical facts to act?

The Black Swan Guardrail asks:

> Are we still inside the validated assumptions where this pathway is allowed to act?

It detects identity/proxy failures, prompt-injection and metric-gaming attempts, off-pathway sentinel symptoms, social-channel/coercion risk, stale or conflicting objective data, communication envelope problems, high-risk host factors, and workflow failure such as nonresponse after risk.

The output includes:

- `guardrail_state`, such as `ALLOW_WITH_AUDIT`, `HOLD_AND_VERIFY`, `ROUTE_CLINICIAN`, `FAIL_CLOSED`, or `ESCALATE`;
- `max_autonomy_tier`, from `T0_EMERGENCY_OR_HARD_STOP` through `T4_NARROW_AUTONOMOUS_ACTION`;
- an assumption register;
- a residual risk budget;
- auditable controls and evidence snippets.

Run:

```bash
python black_swan_demo.py --all --html artifacts/black_swan_dashboard.html --json artifacts/black_swan_reports.json --matrix artifacts/black_swan_guardrail_matrix.csv
```

Open:

```text
artifacts/black_swan_dashboard.html
```

Best interview line:

> “For black swans, prediction is the wrong goal. The goal is rapid recognition that the case is outside the validated operating envelope, followed by a safe change in autonomy.”
