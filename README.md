# Judgment Readiness Engine (JRE)

Prototype interview artifact for a clinical AI company: an **Unknowns Intelligence Layer** that sits between patient intake and any autonomous or semi-autonomous action.

The core question is not “what is the diagnosis?”

The core question is:

> **Do we have enough reliable information, with acceptable residual uncertainty, to act safely?**

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
8. **Mitigation plan** — immediate controls plus future learning hooks for boundary traces, VAMS-style near-miss recall, governed template promotion, and churn/routing reduction.

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
python -m unittest discover -s tests -v
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
jre/synthetic_data.py  Synthetic cases and dataset generator
jre/black_swan.py     Black Swan Guardrail Layer, assumption register, autonomy caps
MITIGATION_PLAN.md    Stigmergic/VAMS mitigation plan and demo update path
TELEMEDICINE_TOP_25_COVERAGE.md  Mapping of common telemedicine reasons to templates
demo.py               CLI and HTML dashboard generator
black_swan_demo.py    CLI and HTML dashboard generator for black-swan guardrails
tests/test_jre.py      Smoke tests for key safety behaviors
data/                 Synthetic JSONL + flat CSV dataset
artifacts/            Demo output, reports, provider dashboard HTML
```

---

## How this maps to a real product

In production, the LLM would not be the safety system. The LLM would be the **language interface**.

The safety system would be:

1. **LLM/extractor** — turns natural language into candidate observations.
2. **Expert-system shell** — verifies required slots, red flags, contradictions, and remote boundaries.
3. **Uncertainty model** — confidence, missingness, distortion, and source reliability.
4. **Experience memory** — learns which questions expose hidden risk in which patient/context patterns.
5. **Stigmergic boundary trace** — keeps unresolved claims, source conflicts, stale data, social/workflow pressure, and feedback from disappearing between turns.
6. **VAMS-style near-miss recall** — recalls prior boundary failures from partial case signatures and suggests missing nodes or falsifiers.
7. **Governance queue** — promotes learned rules/templates only after validation, simulation, and review.
8. **Arbiter** — decides whether the case is ready, needs clarification, needs objective data, or must escalate.
9. **Provider UI** — shows the boundary map and rule trace, not just a note summary.

This is designed to be inserted into a telehealth or autonomous-intake pipeline before refills, triage, symptom assessment, or chronic disease check-ins.

The current demo implements the deterministic controls and visible mitigation planning. The stigmergic trace and VAMS memory are documented as the next implementation layer, with memory output constrained to advisory candidate risks/questions/falsifiers rather than clinical authorization.

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
