# ClinSafer / Judgment Readiness Engine Handoff

**Updated:** 2026-05-05
**Repo:** `https://github.com/deesatzed/ClinSafer.git`
**Live app:** `https://clinsafer.fly.dev/`
**Latest feature:** Public landing page plus `/demo` interactive app route

This is an interview/demo artifact, not a clinical protocol, medical device, or
production triage system.

## Current State

The app is a governed clinical-AI boundary layer. It asks:

- What did the patient actually say?
- What can safely be treated as fact?
- What remains missing, distorted, contradictory, stale, or unknowable remotely?
- Which layer produced each signal?
- What is the AI allowed to do next?

The core safety invariant is:

> Models propose candidate signals; deterministic rules, guardrails, and the
> most-restrictive governor decide the autonomy boundary.

## What Is Implemented

- Transcript-first workflow with a large paste-transcript entry path.
- Context extraction from transcript: age, concern, domain, PMH, medications.
- Editable dialogue rows after parsing.
- Concept inference for blank concepts.
- Concept reclassification for wrong or generic concepts.
- Manual `red_flag` labels preserved as safety hints and remapped to concrete
  domain slots when supported.
- Input Coverage Audit for every submitted line.
- Deterministic Judgment Readiness Engine.
- Deterministic Black Swan Guardrail Engine.
- Deterministic Reasoning Integrity Engine for cognitive forcing against
  anchoring, premature closure, confirmation bias, search satisficing,
  availability bias, omission bias, diagnostic momentum, framing risk, and
  overconfidence.
- Cross-domain sentinel rules including back pain plus neuro/bladder language.
- Human-factor boundaries for embarrassment, stigma, fear-curated history,
  somatic amplification, reassurance seeking, stoic minimization, and denial.
- Final Recommendations page focused on actionable clinician/patient output.
- Public landing page at `/` for testing, promotion, and explaining why the
  Any Dispo Judgment Readiness methodology matters in AI healthcare.
- Interactive app route at `/demo`.
- Bounded multi-role LLM candidate pipeline through OpenRouter.
- Governance review and in-memory feedback/experience prototype.
- Fly deployment.

## Bounded Multi-Role LLM Pipeline

Implemented in `jre/llm_augment.py` and surfaced in `interactive_demo.py`.

Enabled by default:

| Role | Purpose | Authority |
| --- | --- | --- |
| `extractor` | Fast semantic extraction of red flags, wrong labels, human distortion, and coverage gaps. | Advisory only. Can add review targets, never authorize care. |
| `boundary` | Clinical boundary reasoning: what makes automation unsafe and which falsifiers are missing. | Advisory only. Can recommend hold/verify targets for deterministic validation. |
| `verifier` | Adversarial audit for ignored lines, false negatives, wrong concepts, and unsafe reassurance. | Advisory only. Can force review, never downgrade a guardrail. |
| `bias_auditor` | Cognitive-bias audit of the reasoning path: anchoring, premature closure, confirmation bias, omission bias, diagnostic momentum, and overconfidence. | Advisory only. Can propose cognitive forcing actions, never accuse a clinician or change disposition. |

Configured but disabled by default:

| Role | Purpose | Authority |
| --- | --- | --- |
| `patient_comm` | Patient-facing language after the governed disposition is set. | Cannot change disposition. |
| `workflow` | Clinician/workflow synthesis after the governed disposition is set. | Cannot change autonomy tier. |

Fly secrets currently set:

```text
OPENROUTER_ANALYSIS_ROLES=extractor,boundary,verifier,bias_auditor
OPENROUTER_EXTRACTOR_MODEL=qwen/qwen3.6-flash
OPENROUTER_BOUNDARY_MODEL=qwen/qwen3.6-flash
OPENROUTER_VERIFIER_MODEL=qwen/qwen3.6-flash
OPENROUTER_BIAS_MODEL=qwen/qwen3.6-flash
OPENROUTER_PATIENT_MODEL=qwen/qwen3.6-flash
OPENROUTER_WORKFLOW_MODEL=qwen/qwen3.6-flash
OPENROUTER_MAX_PARALLEL_ROLES=4
```

Live smoke on 2026-04-28 after adding `bias_auditor`:

```text
/demo/llm-analyze
model: qwen/qwen3.6-flash
extractor: success, 3 findings
boundary: success, 4 findings
verifier: success, 4 findings
bias_auditor: success, 4 findings
total LLM candidate findings: 15
```

## Input Coverage Guarantee

Every row in the encounter is audited. For each row the UI shows:

- supplied concept,
- inferred concept,
- effective concept,
- source,
- reclassification status,
- consumers:
  - observation extractor,
  - patient-context extractor,
  - JRE template slot,
  - JRE rules,
  - Black Swan Guard,
  - async LLM extractor payload,
  - concept reclassifier,
- safety effect,
- status.

Unknown/unmapped rows are not neutral. They create review findings and cannot
support closure or reassurance.

## Verification

Latest local verification:

```text
python -m py_compile interactive_demo.py jre/llm_augment.py
python -m pytest -q
350 passed
python scripts/run_dhse_benchmark.py --review-fraction 0.5 --summary-json artifacts/dhse_summary.json --case-csv artifacts/dhse_cases.csv
served inline JavaScript parsed with node --check
```

Latest live verification:

```text
/demo/analyze back-pain red-flag smoke:
HTTP 200
combined_state: ESCALATE
guardrails:
  SENTINEL_BACK_PAIN_NEURO_BLADDER
  MANUAL_RED_FLAG_REVIEW
LLM role manifest:
  extractor qwen/qwen3.6-flash enabled
  boundary qwen/qwen3.6-flash enabled
  verifier qwen/qwen3.6-flash enabled
  bias_auditor qwen/qwen3.6-flash enabled
```

Reasoning Integrity smoke:

```text
manual back-pain red-flag case:
reasoning_integrity section present
anchoring finding present
premature_closure finding present
recommendations include cognitive forcing actions
```

## Key Files

| File | Purpose |
| --- | --- |
| `interactive_demo.py` | Main FastAPI single-page demo, transcript workflow, analysis sections, recommendations UI. |
| `jre/engine.py` | Judgment Readiness Engine, concept inference/reclassification, observations, JRI scoring. |
| `jre/black_swan.py` | Guardrail engine, sentinels, autonomy caps, assumption register. |
| `jre/reasoning_integrity.py` | Deterministic cognitive-bias guard and forcing-function generator. |
| `jre/llm_augment.py` | OpenRouter integration, bounded role configs, role prompts, parallel role execution. |
| `jre/templates.py` | Domain templates, slot specs, red-flag patterns, contradiction rules. |
| `tests/test_interactive_demo.py` | Interactive endpoint, transcript, coverage, role manifest tests. |
| `README.md` | Run instructions and OpenRouter/Fly model configuration. |
| `ARCHITECTURE.md` | System architecture and current/future methodology. |
| `TECHNICAL_FLOW_FOR_CS_SWE.md` | Detailed CS/SWE methodology flow. |
| `FINAL_INTERVIEW_READINESS.md` | Demo positioning, limitations, and presentation strategy. |

## Known Limits

- This is not clinically validated.
- Domain templates are demo coverage scaffolds, not production protocols.
- Memory is process-local and prototype-level.
- VAMS/stigmergic layers are represented as governed design hooks and visible
  mitigation structure, not a production Hopfield memory subsystem.
- No EHR/device/pharmacy integration exists yet.
- No outcomes calibration exists yet.
- No browser-level E2E suite exists yet.

## Next Technical Steps

1. Add browser E2E tests for transcript paste, analyze, LLM retry, and final recommendations.
2. Add latency/cost telemetry by LLM role.
3. Persist feedback and boundary traces.
4. Add dynamic template planner as a draft-only LLM role.
5. Add deterministic validators for AI-proposed nodes/ranges/distributions.
6. Add governance queue for proposed rule/template promotion.
7. Add downloadable clinician handoff.

## Demo Guidance

Use this wording:

> This is not an AI doctor. It is a governed boundary layer around clinical AI.
> The LLM roles notice candidate risks, but deterministic rules and the
> most-restrictive governor decide what autonomy is allowed.

Avoid implying any named company lacks these safeguards. The point is to show
how the candidate thinks across medicine, software, AI behavior, workflow,
patient psychology, business pressure, and risk governance.
