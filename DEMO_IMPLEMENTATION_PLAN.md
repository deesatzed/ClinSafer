# Demo Implementation Plan

Status: historical implementation plan. For the current live demo talk track and final review, use `FINAL_INTERVIEW_READINESS.md`. The live app now avoids a separate "Interview Mode" label and no longer uses a fixed "Operational Value" section as the primary story.

## Purpose

Enhance the Judgment Readiness Engine demo into a focused interview showpiece for an AI healthcare leadership audience.

The goal is not to imply a healthcare AI company lacks obvious clinical safeguards. Assume the audience already has strong AI-doctor reasoning, emergency detection, physician escalation, refill checks, and adversarial defenses.

The goal is to demonstrate what the candidate can bring:

- next-level interpretation-boundary thinking,
- mature healthcare AI safety architecture,
- business-aware autonomy design,
- physician/admin/regulatory realism,
- and a concrete implementation style that can turn subtle product risk into auditable software.

Add the human component explicitly: patients may not only minimize because of cost or coercion. They may reshape the history because they are embarrassed, afraid of a bad diagnosis, confused by internet-driven medical facts, worried about what enters the chart, or trying to make the answer less alarming. The system should treat those cues as disclosure-pressure signals that require normalizing, privacy-preserving clarification before autonomy is upgraded.

## Core Interview Thesis

Use this thesis throughout the app and demo:

> The next frontier is not whether the AI can answer. It is whether the AI knows which parts of the encounter are facts, which are inferences, which are unresolved unknowns, and when those unknowns should cap autonomy.

The audience may already have strong clinical reasoning. This prototype shows a way to govern uncertainty around that reasoning:

- know what was said,
- know what was inferred,
- know what was never asked,
- detect when communication is unreliable,
- and dynamically cap autonomy when the unknowns become unsafe.

## Current Limitation And Next Architecture

The current prototype intentionally uses hand-authored domain templates and deterministic expert-system rules so the method is inspectable in an interview. That is useful for a showpiece, but it is not the final architecture.

The next version should evolve from:

> Static expert system around an AI doctor

to:

> AI-generated, governed, auditable expert-system software around an AI doctor.

The better architecture is not "let the LLM decide." It is:

1. AI reads the specific encounter.
2. AI proposes the case-specific boundary map, decision nodes, node ranges, and uncertainty distributions.
3. AI proposes whether an existing template applies, should be extended, or whether a temporary case-specific template is needed.
4. Deterministic validators check the proposed nodes/rules for schema validity, forbidden inferences, source requirements, autonomy caps, and clinical-governance constraints.
5. The expert-system evaluator scores the governed graph.
6. The autonomy governor applies most-restrictive-wins across clinical readiness, assumption sufficiency, distribution fit, and business/workflow risk.

The pitch to a physician executive:

> The current demo proves the safety method. The next layer makes it scalable: AI generates the expert-system graph for the specific case, while governed software validates and executes it.

### Why This Matters

The major limitation of a static expert system is domain coverage. Seven or ten domain templates will never cover the shape of all real encounters, especially when patients blend refill needs, cost avoidance, social risk, chronic disease, old chart facts, and new symptoms.

The limitation of a pure LLM is the opposite: it can reason broadly, but it may blur fact, inference, missingness, and permission to act.

The target architecture combines both:

- AI supplies adaptive breadth.
- Expert-system software supplies bounded action, auditability, and governance.
- Experience memory supplies calibration from outcomes.
- Autonomy caps prevent reasoning confidence from becoming unsafe automation.

## AI-Generated Dynamic Expert-System Layer

### A. AI Case-Boundary Planner

Before applying fixed templates, run an AI planning pass that produces a structured case-boundary specification.

Example output:

```json
{
  "likely_domains": ["med_refill_hypertension", "renal_med_safety"],
  "critical_unknowns": [
    "current blood pressure",
    "recent creatinine/eGFR",
    "recent potassium",
    "NSAID use",
    "pregnancy status",
    "current dizziness or hypotension"
  ],
  "unsafe_inferences": [
    "Do not infer current BP control from an old clinic visit.",
    "Do not infer renal safety from 'labs were okay last time' without date/value.",
    "Do not treat 'nothing serious' as a clean side-effect denial when dizziness is mentioned."
  ],
  "candidate_nodes": [
    "current_bp_reliability",
    "renal_medication_safety_margin",
    "side_effect_signal_strength",
    "stale_data_penalty",
    "autonomous_refill_readiness"
  ]
}
```

The AI planner is not deciding care. It is defining the graph that the governed expert system will evaluate.

### B. Dynamic Node Generation

Each case should generate a set of decision nodes. Nodes can be inherited from templates, added from cross-domain libraries, or created as temporary case-specific nodes.

Node schema:

```json
{
  "node_id": "renal_medication_safety_margin",
  "clinical_question": "Is renal/potassium safety known well enough for ACE-inhibitor refill?",
  "value_type": "ordinal",
  "range": ["unknown", "low_concern", "moderate_concern", "high_concern"],
  "distribution_type": "categorical",
  "prior": {"unknown": 0.55, "low_concern": 0.15, "moderate_concern": 0.20, "high_concern": 0.10},
  "required_evidence": ["recent creatinine/eGFR", "recent potassium", "medication list", "NSAID use"],
  "unsafe_inferences": ["Do not infer safety from stale labs or patient reassurance."],
  "autonomy_effect": "block autonomous refill if unknown or high_concern"
}
```

### C. Node Range And Distribution Types

The AI planner should choose node type based on evidence shape:

- `boolean`: pregnancy possible, identity verified, active bleeding present.
- `categorical`: communication channel safe/unsafe/unknown.
- `ordinal`: low/moderate/high concern.
- `continuous_beta`: bounded confidence or readiness probability from 0 to 1.
- `time_decay`: freshness of vitals, labs, prior reassurance, or chart data.
- `count/poisson_like`: repeated symptom episodes, medication use frequency, retry/nonresponse events.
- `survival/hazard_like`: time-sensitive deterioration risk where delay matters.
- `mixture`: cases where multiple explanations compete, such as reflux vs ACS framing.

Initial implementation can keep distributions simple and auditable:

```text
Beta for bounded confidence.
Categorical for discrete clinical states.
Ordinal buckets for risk tiers.
Exponential/time-decay for stale evidence.
Mixture labels for competing pathways.
```

The crucial point is that ranges and distributions are proposed by AI but accepted only after deterministic validation.

### D. Dynamic Template Creation Or Extension

If an existing template fits, the AI planner can extend it.

If no template fits, it can propose a temporary template:

```json
{
  "template_id": "ace_inhibitor_refill_with_ckd_and_nsaid",
  "parent_templates": ["med_refill_hypertension"],
  "required_nodes": [
    "medication_identity",
    "current_bp_reliability",
    "renal_function_freshness",
    "potassium_freshness",
    "nsaid_interaction_risk",
    "pregnancy_status",
    "side_effect_signal_strength",
    "chart_med_reconciliation"
  ],
  "hard_stops": [
    "possible angioedema",
    "pregnancy possible",
    "severe hypotension symptoms",
    "unknown renal function with CKD plus daily NSAID use"
  ],
  "autonomy_cap_default": "T2_CLINICIAN_DRAFT_ONLY"
}
```

Temporary templates should be tagged:

```text
draft_only
requires_governance_review
not_production_validated
simulation_required
```

### E. AI-Generated Expert Rules With Validators

The AI can propose candidate expert-system rules, but validators must check them before use.

Example proposed rule:

```text
IF medication class is ACE inhibitor
AND known CKD is present
AND NSAID use is frequent
AND recent renal function or potassium is missing/stale
THEN autonomous refill renewal is blocked
AND next step is objective lab/chart verification or clinician review.
```

Validation checks:

- rule schema is valid,
- required evidence sources are explicit,
- no unasked variable is treated as denied,
- stale evidence is not treated as current,
- LLM-only findings cannot create T0/T1 hard stops without deterministic support,
- rule has a test case or simulation case,
- rule is marked draft unless reviewed.

## Learning Architecture Status: VAMS, RL, Stigmergy

Local search status as of April 27, 2026:

- `VAMS`: no literal reference or implementation found in the current repository.
- Reinforcement learning / RL: no true RL policy, reward model, exploration strategy, or online policy optimizer is implemented.
- Stigmergic learning: no explicit stigmergic multi-agent memory, pheromone-style trace, shared blackboard, or emergent agent coordination layer is implemented.
- Pattern learning currently present: yes, but limited. The repo has `ExperienceMemory` with EMA-updated `distortion_priors` and `question_yield` estimates, plus clinician feedback categories.

Current incorporated learning:

- seeded distortion priors,
- seeded question-yield estimates,
- EMA updates from single-turn experience events,
- clinician feedback updates for confirmed/corrected/false-positive/missed findings,
- question priority adjustment using expected question yield.

Not yet incorporated:

- AI-generated dynamic templates,
- AI-defined node ranges/distributions,
- RL-based clarification-policy optimization,
- stigmergic multi-agent pattern memory,
- governed promotion of learned rules into production templates,
- population-level calibration against outcomes.

Recommended next implementation:

1. Add a `DynamicTemplatePlanner` that uses an LLM to draft case-specific nodes, ranges, distributions, and unsafe inferences.
2. Add a `TemplateValidator` that rejects unsafe or unsupported AI-proposed nodes/rules.
3. Add a `NodeDistribution` model with simple auditable distributions: beta, categorical, ordinal, time-decay, mixture.
4. Add a `LearningTraceStore` that records what nodes/rules/questions changed decisions.
5. Add a governance screen that shows draft AI-proposed templates and lets a clinician/admin approve, edit, or reject them.
6. Later: add RL-style offline policy evaluation for question ordering, not autonomous clinical action.
7. Later: add stigmergic pattern learning where repeated near-misses strengthen shared traces for specific unknowns, phrases, and workflow failures.

Important framing:

> The current demo has experiential calibration, not full RL. The future architecture can use RL-like offline learning for question policy and stigmergic memory for near-miss pattern propagation, but autonomy decisions should remain governed and auditable.

## Applied Evaluation: `hcc_synth_1` Stigmergy And `vam-satzed` VAMS

This evaluation is focused on what can make the current `ver2` app smarter, more adaptive, and better at the learning gaps already identified: limited templates, static node definitions, weak memory for near misses, limited learning from experience, and insufficient dynamic boundary-setting around what the patient did not say.

The companion mitigation document is `MITIGATION_PLAN.md`. The interactive demo now includes a `Mitigation Plan` analysis section that translates this architecture into visible case-level controls.

### `hcc_synth_1`: Stigmergic Techniques To Borrow

The most useful pattern in `hcc_synth_1` is not a single model. It is a shared trace substrate: multiple agents deposit signals into a bounded field; traces persist, decay, combine, and become the memory surface used by later decisions.

Relevant components:

- `PatientStateField`: a continuous multi-region tensor where devices, agents, and events deposit perturbations. Each region has different decay behavior.
- `PatientSelfModel`: online patient-specific baseline learning using Welford statistics, hourly buckets, deviation scores, temporal deltas, and sparse peak detection.
- `DeteriorationIndex`: weighted composite risk with missing-component renormalization and trend tracking.
- `EscalationEngine`: severity-specific timed escalation, including renotification and escalation-on-silence.
- `BayesianFalsifierEngine`: generates plausible alternative explanations and tests that could falsify the dangerous hypothesis.
- `DecisionPolicy`: uses asymmetric miss cost versus false-positive cost.
- `EventLabeler`: uses adaptive thresholds and sparse peak detection so one strong sparse signal is not diluted by otherwise calm data.
- `FatigueEngine`: suppresses repetitive low-value alerts but never suppresses critical alerts.

Applied to the current app, this should become a `BoundaryTraceField`, not a direct clinical deterioration field.

Recommended trace regions:

| Region | Meaning | Suggested Decay |
|---|---|---:|
| `claims` | What the patient explicitly says or denies | 0.96 |
| `objective` | BP, labs, vitals, chart facts, device readings | 0.92 |
| `source_conflict` | Patient/chart/device/caregiver disagreement | 0.98 |
| `social_workflow` | fear, cost, coercion, embarrassment, desired outcome seeking, nonresponse | 0.99 |
| `temporal_staleness` | aging evidence, missing timestamps, remote unknowability | 0.90 |
| `outcome_feedback` | clinician correction, near miss, false positive, confirmed risk | 0.995 |

Why this matters:

- The app should not treat each demo case as stateless text.
- Suspicious phrases, silence after a high-risk question, stale objective data, and prior near misses should leave traces.
- Traces should fade if they are not reinforced, but high-value safety signals should persist long enough to shape follow-up.
- A case can become unsafe through accumulated weak signals, not only through one hard red flag.

Concrete implementation target:

```text
Input text + extracted findings
  -> deposit boundary perturbations
  -> integrate BoundaryTraceField
  -> compare against BoundarySelfModel baselines
  -> produce Boundary Instability Index
  -> adjust next questions, falsifiers, autonomy cap, and escalation timer
```

The `BoundarySelfModel` should learn baselines by domain and pathway, not by real patient identity in the demo:

- refill with chronic disease,
- pediatric caregiver report,
- mental health minimization,
- chest pain with vague reassurance,
- post-discharge symptom drift,
- telemedicine-only data limitation.

This gives the app dynamic ranges without pretending that an LLM can invent safe medical thresholds. The AI can propose candidate nodes, but observed cases and governed feedback calibrate the operating ranges.

### Falsification Layer From `hcc_synth_1`

The falsifier pattern is especially important for the premise "do we know what we do not know?"

For every high-risk or autonomy-blocking hypothesis, the system should generate:

- dangerous hypothesis,
- plausible benign or alternate hypotheses,
- what evidence would falsify danger,
- what evidence would falsify reassurance,
- lowest-burden next question or objective check,
- consequence of remaining unresolved.

Example:

```text
Hypothesis: ACE inhibitor refill may be unsafe.
Risk basis: CKD + frequent NSAID use + missing recent BP/labs + dizziness language.
Falsifiers: current normal BP with number, recent creatinine/eGFR, potassium, chart med reconciliation, no NSAID exposure, no orthostasis.
If unresolved: autonomous renewal remains blocked; route to clinician or objective verification.
```

This should be shown in interview mode as "What Would Change The Decision?" because it demonstrates subtle reasoning without claiming diagnosis.

### Escalation And Fatigue From `hcc_synth_1`

The current guardrail system is mostly one-shot. The stigmergic repo suggests adding workflow time:

- if the patient does not answer after a risk-bearing question, risk should not disappear,
- repeated nonresponse should escalate differently by tier,
- repeated low-yield clarifications should be deduplicated,
- critical hard stops should never be suppressed,
- churn reduction comes from asking fewer, better questions while preserving high-risk escalation.

Recommended product language:

> The system should reduce alert fatigue for routine ambiguity while increasing persistence around unresolved high-consequence uncertainty.

### `vam-satzed`: VAMS Memory Techniques To Borrow

`vam-satzed` provides a useful architecture for associative near-miss memory:

- sparse Hopfield memory,
- Hebbian strengthening,
- anti-Hebbian weakening,
- associative recall,
- pattern completion from partial cues,
- typed memory graph edges,
- acceptance/rejection feedback.

The reference design uses sparse attractor memory such as:

```text
N = 16,384 possible bits
k = 256 active bits
partial case signature -> Hopfield recall -> completed near-miss pattern
```

For the current app, VAMS should not decide medical action directly. It should recall similar boundary failures and propose candidate risks, questions, and falsifiers.

Recommended JRE adaptation:

```text
Case text
  -> extractor findings
  -> BSG/JRE report
  -> ClinicalBoundaryEncoder
  -> sparse case signature
  -> AssociativeCaseMemory recall
  -> near-miss analogues + missing nodes + suggested falsifiers
  -> deterministic validators
  -> visible interview-mode "Memory Recall" panel
```

Candidate features for the sparse case signature:

- domain: refill, triage, pediatrics, mental health, post-discharge, chronic disease,
- BSG rule IDs triggered,
- missing objective slots,
- contradiction types,
- source reliability problems,
- stale-data flags,
- social risk flags,
- autonomy tier before and after clarification,
- question concepts asked,
- clinician feedback outcome,
- final disposition.

Memory edge types to preserve:

- `causal`: stale BP + CKD + NSAID -> unsafe refill,
- `temporal`: nonresponse after risk question -> escalation,
- `structural`: similar uncertainty shape across different diseases,
- `workflow`: repeated clarification burden -> churn risk,
- `governance`: draft template promoted, rejected, or needs review.

### What VAMS Fills That Templates Do Not

Static domain templates fail when the case is a rare combination of individually ordinary signals. VAMS can help when:

- the current case only partially resembles a prior near miss,
- no existing template has the right disease label,
- the important feature is the uncertainty shape rather than the diagnosis,
- the patient is steering the conversation toward a desired outcome,
- the system needs to remember that a certain missing fact previously mattered.

Example:

```text
Current case: "BP is fine" + refill request + no number + dizziness minimized.
VAMS recall: prior near miss where "fine BP" hid missing current BP and NSAID use in CKD.
System effect: ask BP number, renal labs, potassium, NSAID use, orthostasis; cap autonomy until objective verification.
```

This is not vector search replacing clinical rules. It is associative memory feeding a governed expert system.

### Hebbian And Anti-Hebbian Feedback

Feedback should update memory safely:

- clinician confirms recalled near-miss pattern: strengthen attractor and causal edges,
- clinician rejects pattern: weaken attractor and reduce future recall confidence,
- missed risk discovered later: create new memory and mark it high-priority for governance review,
- repeated false positives: lower priority but keep hard-stop pathways intact,
- churn event after excessive clarification: reduce low-yield question ordering, not safety-critical questions.

### Safety Boundary For Memory

VAMS-style memory must be sandboxed:

- memory recall can propose candidates, not authorize action,
- no memory-only signal can create a T0/T1 hard stop without deterministic support,
- every recall must show evidence, confidence, and provenance,
- PHI must be de-identified or excluded from the memory substrate,
- production promotion requires governance review and simulation cases,
- feedback updates should be shadow-mode before affecting live patient workflow.

### Recommended Implementation Sequence

1. Add a deterministic `ClinicalBoundaryEncoder` that converts the current JRE/BSG report into a sparse feature set.
2. Add an `AssociativeCaseMemory` service with synthetic seeded near-miss memories.
3. Surface a interview-mode "Memory Recall" panel showing recalled analogue, missing nodes, and proposed falsifiers.
4. Add `BoundaryTraceField` to retain case-level traces across turns and clarification steps.
5. Add `BoundarySelfModel` baselines by domain/pathway using online Welford statistics.
6. Add a `BoundaryInstabilityIndex` that trends uncertainty, contradiction, staleness, source conflict, social risk, and feedback.
7. Add clinician feedback buttons: confirmed, corrected, false positive, missed, churn/friction.
8. Use feedback to update question-yield, memory acceptance, and draft-template promotion queues.
9. Keep all learned changes in shadow or draft mode until governance approval.

### Demo Upgrade From This Evaluation

The best next demo moment is:

1. Run a subtle case that looks routine.
2. Show JRE identifies missing/uncertain/distorted claims.
3. Show BSG caps autonomy.
4. Show VAMS recalls a prior near-miss analogue from partial cues.
5. Show the stigmergic trace field has accumulated unresolved risk from stale objective data, nonresponse, and source conflict.
6. Show the falsifier panel: "what would let us safely proceed?"
7. Show business framing: fewer generic questions, better escalation persistence, lower avoidable churn, lower unsafe automation risk.
8. Show the mitigation plan: current deterministic controls, stigmergic boundary trace, VAMS near-miss recall, governed template promotion, and business mitigation.

Interview line:

> The learning layer should not learn to practice medicine autonomously. It should learn where the system's interpretation boundaries fail, which missing facts matter, which clarifications have yield, and which near-miss patterns deserve governed promotion.

## Non-Goals

Do not build a competing AI doctor.

Do not claim this is production-ready, clinically validated, or superior to internal systems.

Do not lead with obvious cases such as classic stroke, anaphylaxis, active GI bleed, or worst headache. These can remain in the library, but they are not the hero story for a physician executive.

Do not frame the deterministic layer as "regex beats LLM." Frame the LLM as an extractor/interface and the expert system as the governed safety shell.

## Success Criteria

The enhanced demo is successful if a viewer understands within 90 seconds:

1. This is not diagnosis generation.
2. This is an autonomy and interpretation-boundary layer.
3. The product can improve safety and business metrics at the same time.
4. The candidate thinks across medicine, AI, operations, regulation, and revenue.

A less technical viewer should remember:

> The AI should know what it does not know before it acts.

A physician executive should remember:

> This person thinks about subtle scale failure modes, not only textbook red flags.

## Current Codebase Anchors

Primary file to modify:

- `interactive_demo.py`

Core engines:

- `jre/engine.py`
- `jre/black_swan.py`
- `jre/experience.py`
- `jre/templates.py`
- `jre/synthetic_data.py`

Narrative/demo data:

- `unified_demo.py`
- `BLACK_SWAN_INTERVIEW_CARD.md`
- `INTERVIEW_BRIEF.md`
- `Explain2Me.md`

Tests to update:

- `tests/test_interactive_demo.py`
- `tests/test_unified_demo.py`
- `tests/test_jre.py`
- `tests/test_black_swan_guardrails.py`

## Workstream 1: App Enhancements To Meet The New Goals

### 1.1 Add Interview Mode

Add a dedicated demo mode to `interactive_demo.py`.

Implementation target:

- Add a new top navigation item: `Interview Mode`.
- Add a new screen: `screen-interview`.
- Add a new route or frontend state that loads only the curated showpiece cases.

Recommended UI order:

1. **Opening Claim**
   - "This is not an AI doctor. It is an autonomy boundary layer around an AI doctor."
2. **Hero Case**
   - subtle refill autonomy case.
3. **Boundary Map**
   - statement vs fact vs inference vs unknown.
4. **Autonomy Cap**
   - what the AI is allowed to do and why.
5. **Operational Value**
   - safe automation, fewer unnecessary physician escalations, better conversion, better trust.

Acceptance criteria:

- User can click `Interview Mode` and see a guided demo path without browsing the full case grid.
- The first screen includes the core thesis in one sentence.
- The page avoids saying or implying "your team missed this."

### 1.2 Rename Demo Concepts For This Audience

Current labels are technically accurate but not executive-optimal.

Change these labels in `interactive_demo.py`:

- `What did the patient actually say?` -> `Statement vs Fact`
- `What's missing, uncertain, or distorted?` -> `Known Unknowns Map`
- `Hidden danger signals` -> `Interpretation Boundary Breaches`
- `Black Swan Guardrail Check` -> `Assumption Sufficiency Check`
- `Learning & Curation` -> `Boundary Calibration / Governance Review`
- `LLM Second Opinion` -> `Extractor Cross-Check / Candidate Signal Review`

Acceptance criteria:

- No primary UI label says `MUD`.
- No primary UI label says `regex engine`.
- "Learning" copy is governance/calibration oriented, not uncontrolled live learning.

### 1.3 Add Explicit Statement/Fact/Inference/Unknown Payload

Current observations show raw answer, normalized value, confidence, source, and traps. For this new thesis, the UI needs a clearer interpretation-boundary table.

Add a new section builder or enrich `_build_observations_section()` in `interactive_demo.py`.

For each statement, produce:

- `patient_statement`: exact answer text.
- `explicit_claim`: what the patient explicitly claimed.
- `safe_interpretation`: what the system is allowed to treat as supported.
- `unsafe_inference`: what must not be inferred.
- `missing_followup`: what question or data would close the boundary.
- `confidence`: current confidence.
- `source`: patient/caregiver/device/chart/clinician.
- `boundary_status`: one of `supported`, `weak`, `unsafe_to_infer`.

Initial implementation can be heuristic:

- If answer contains vague terms such as "fine", "normal", "okay", "not really", mark `boundary_status=weak`.
- If objective concept lacks a number, mark `unsafe_to_infer`.
- If source conflict exists for the same concept, mark `unsafe_to_infer`.
- If low confidence is below 0.55, mark `unsafe_to_infer`.
- Otherwise mark `supported`.

Acceptance criteria:

- Interview Mode shows this table before clinical scoring.
- The table explicitly communicates "unasked is not denied."
- At least one hero case row shows an unsafe inference that a normal AI intake might make.

### 1.4 Add Autonomy Boundary Summary

Add a compact "Autonomy Boundary" panel to the analysis screen.

Data fields:

- `current_cap`: T0/T1/T2/T3/T4.
- `allowed_actions`: list of allowed AI actions.
- `blocked_actions`: list of blocked AI actions.
- `why_blocked`: top 3 reasons.
- `what_restores_readiness`: top 3 next steps.
- `business_effect`: one sentence describing operational impact.

Example output:

- Allowed: "summarize encounter", "draft clinician note", "ask targeted clarification".
- Blocked: "autonomous refill renewal", "close encounter as low risk".
- Why blocked: "current BP missing", "renal safety context stale", "new dizziness disclosure".
- Restore readiness: "current BP number", "recent creatinine/potassium timestamp", "orthostatic symptom clarification".
- Business effect: "Avoids unnecessary denial by asking one targeted question before paid physician routing."

Implementation location:

- Add `_build_autonomy_boundary_section()` to `interactive_demo.py`.
- Insert before or immediately after `_build_safety_decision_section()`.
- Update tests expecting section count from 8 to 9 if this is a new section.

Acceptance criteria:

- The viewer can tell what the AI may do, not only what state it returned.
- The panel includes both safety and operational/business implications.

### 1.5 Add Operational Value Panel

Add a final interview-specific panel. This is not for clinicians; it is for the business conversation.

Fields:

- `safety_value`
- `revenue_value`
- `churn_value`
- `physician_efficiency_value`
- `regulatory_value`
- `metric_to_track`

Example:

- Safety: "Prevents autonomous refill when renal-monitoring assumptions are weak."
- Revenue: "Asks one high-yield question before routing, preserving safe automation when possible."
- Churn: "Explains uncertainty without scaring or dismissing the patient."
- Physician efficiency: "Hands off a boundary map rather than a raw transcript."
- Regulatory: "Creates auditable refusal/escalation categories."
- Metric: "Percent of routed refill cases where one clarification changed disposition."

Acceptance criteria:

- Interview Mode has a visible business case.
- Copy is pragmatic and avoids buzzwords.
- It connects safety to margin, conversion, retention, or regulatory expansion.

### 1.6 Upgrade Governance Review Language

Current screen says clinicians mark findings to update learning.

Replace with:

- "Governance review"
- "Boundary calibration"
- "Near-miss review"
- "Offline calibration"
- "Model behavior should not silently change in production without review."

Implementation target:

- Update the screen title and descriptions in `interactive_demo.py`.
- Keep existing feedback endpoint as-is for now, but present it as demo governance.

Acceptance criteria:

- A physician/regulator would not think the system is learning unsafely in real time.
- The UI says feedback is captured for review/calibration.

## Workstream 2: Add More Subtle Cases

### Case Design Principles

New cases should not be basic textbook red flags.

Each case should demonstrate a subtle mature-system failure mode:

- over-interpreting silence,
- treating denial as negative evidence,
- relying on stale objective data,
- trusting a patient-shaped conversation,
- failing to notice economic fear,
- failing to detect a workflow safety event,
- confusing documentation completeness with readiness.

### 2.1 Hero Case: Stale Refill Autonomy Boundary

Case ID:

- `showcase-001-stale-ace-refill-ckd-nsaid`

Domain:

- `med_refill_hypertension`

Narrative:

Patient requests lisinopril refill. They say BP is "normal" and deny problems. They mention the normal BP was from months ago. They also started taking ibuprofen daily for back pain and have CKD. They get dizzy standing but say it is "probably nothing."

Statements:

1. Question: "What blood pressure numbers have you been getting recently?"
   - Answer: "It was normal at my last visit a few months ago. I do not have the numbers."
   - Concept: `home_bp_number`
   - Source: `patient`
2. Question: "Any dizziness, fainting, chest pain, shortness of breath, swelling, or new symptoms?"
   - Answer: "No, nothing serious. I just get a little dizzy when I stand up fast, but that is probably normal."
   - Concept: `side_effects`
   - Source: `patient`
3. Question: "Any new medicines or over-the-counter medicines?"
   - Answer: "I have been taking ibuprofen most days for my back."
   - Concept: `medication_identity`
   - Source: `patient`
4. Question: "Any kidney problems or recent labs?"
   - Answer: "I have kidney disease, but my labs were okay last time. I am not sure when."
   - Concept: `renal_function`
   - Source: `patient`

Expected behavior:

- Not autonomous refill.
- State should be `NEED_OBJECTIVE_DATA`, `HOLD_AND_VERIFY`, or stricter.
- Known unknowns should show stale BP, missing exact BP, renal safety uncertainty, dizziness ambiguity, NSAID/ACE inhibitor risk context.
- Autonomy cap should allow intake/draft but block autonomous renewal.

Implementation notes:

- `med_refill_hypertension` may not currently include `renal_function` as a slot. Add it to `jre/templates.py` if needed.
- Add stale-data and NSAID/renal-monitoring patterns if absent.
- Update tests to assert autonomy is capped.

### 2.2 Rote Denial / Refill-Seeking Suppression

Case ID:

- `showcase-002-refill-rote-denial-dizziness`

Domain:

- `med_refill_hypertension`

Narrative:

Patient wants refill quickly and answers "no" repeatedly. Later they casually mention dizziness and seeing spots but frame it as normal. The risk is not a hidden diagnosis; it is that pathway-completion behavior makes denials unreliable.

Expected behavior:

- BSG or JRE flags rote denial / metric-gaming style behavior.
- JRE marks side effects low reliability.
- Next best question asks functional/orthostatic clarification and exact BP.
- Autonomy cap blocks renewal until resolved.

Implementation notes:

- Existing `INTEGRITY_COPY_PASTE_ANSWERS` may catch repeated no answers.
- Add case narrative and test.

### 2.3 Cost Fear / Escalation Resistance

Case ID:

- `showcase-003-cost-fear-minimizes-alarm`

Domain:

- `chest_discomfort` or `dyspnea_respiratory`

Narrative:

Patient reveals concerning symptoms but repeatedly minimizes them because they cannot afford the ER and asks for reassurance that it can wait.

Expected behavior:

- System should not downgrade severity because patient resists escalation.
- It should frame next action empathetically.
- Business panel should mention churn reduction: explain uncertainty without dismissing or scaring the patient.

Implementation notes:

- May need new finding category or tag: `care_avoidance_pressure`.
- Add pattern for "cannot afford", "do not want ER", "can I wait", "just tell me it is okay".

### 2.4 Coercion / Unsafe Disclosure Channel

Case ID:

- `showcase-004-bruising-partner-nearby`

Domain:

- `rash`

Narrative:

Patient asks about bruising/rash and avoids explaining mechanism. They mention partner is nearby or they cannot talk freely.

Expected behavior:

- BSG routes clinician/protected workflow.
- UI should show communication-channel assumption weak/breached.
- Do not ask unsafe direct questions in a way that could expose the patient.

Implementation notes:

- Existing `SENTINEL_COERCION_ABUSE` likely applies.
- Add patient-safe summary language if needed.

### 2.5 Caregiver Conflict / Subtle Mental Status

Case ID:

- `showcase-005-caregiver-conflict-fine-but-confused`

Domain:

- `uti_symptoms`, `diabetes_hyperglycemia`, or `dyspnea_respiratory`

Narrative:

Patient says they are fine. Caregiver says they are not acting normally today. Patient denies confusion.

Expected behavior:

- Source conflict detection fires.
- Patient self-report does not dominate caregiver signal.
- Combined state escalates or routes clinician depending domain.

Implementation notes:

- Existing source conflict code can catch same-concept high/low authority conflicts, but caregiver vs patient may not be high-authority. Add or test caregiver-patient conflict explicitly if needed.

### 2.6 Silent Alarm / Nonresponse After Risk

Case ID:

- `showcase-006-nonresponse-after-risk-warning`

Domain:

- `chest_discomfort` or `med_refill_hypertension`

Narrative:

Patient stops responding after being told a symptom may require urgent care.

Expected behavior:

- Do not close encounter as abandoned.
- Treat as workflow safety event.
- Business panel says this is a recoverable handoff/conversion/safety workflow.

Implementation notes:

- Existing `INTEGRITY_NONRESPONSE_AFTER_RISK` likely applies.
- Add demo copy around operational closure.

### 2.7 Inferred Absence Error

Case ID:

- `showcase-007-unasked-is-not-denied`

Domain:

- `med_refill_hypertension`

Narrative:

Encounter never asks pregnancy status, anticoagulant use, kidney disease, recent hospitalization, or medication changes, but the AI would be tempted to summarize "no relevant risk factors."

Expected behavior:

- Boundary map explicitly marks unasked items as missing, not denied.
- Autonomy cap blocks autonomous action if missing variables are required for that pathway.

Implementation notes:

- Requires adding required slots or an interview-specific "critical unasked assumptions" list.

### 2.8 Prior Reassurance Expired

Case ID:

- `showcase-008-prior-reassurance-expired`

Domain:

- `headache_migraine`, `chest_discomfort`, or `rash`

Narrative:

Patient says "my doctor said it was fine last month," but symptoms changed recently. The old reassurance should not carry forward.

Expected behavior:

- System flags stale reassurance and temporal change.
- Autonomy cap asks what changed and when.

Implementation notes:

- Add pattern for "doctor said it was fine", "already checked", "last month", plus new/worse/sudden.

### 2.9 Embarrassment, Fear, Or Misconstrued Medical Facts Curb The History

Case ID:

- `showcase-009-embarrassment-curbs-history`

Domain:

- `gi_symptoms`, `vaginal_sti`, `uti_symptoms`, `mental_health`, or `general_med_management`

Narrative:

Patient partially reveals a sensitive symptom, then walks it back because they are embarrassed, afraid it is cancer, worried about the chart, or anchored on an internet explanation.

Expected behavior:

- System flags `human_disclosure_pressure`.
- Autonomy remains capped until a normalizing, privacy-preserving clarification resolves whether the partial denial is reliable.
- The final recommendation explains the gap without shaming the patient.

Implementation notes:

- Deterministic guardrail catches explicit disclosure-pressure language.
- LLM candidate extraction should also look for softer equivalents: shame, stigma, fear of bad news, chart anxiety, internet-driven self-triage, or misconceptions about what symptoms matter.

## Workstream 3: Methodology/Engine Enhancements

### 3.1 Add Interpretation Boundary Model

Add a lightweight model or dict structure, not necessarily a new dataclass at first.

Suggested structure:

```python
{
    "concept": "home_bp_number",
    "statement": "It was normal at my last visit a few months ago.",
    "explicit": "Patient reports prior normal BP without number.",
    "supported_fact": "A prior BP may have been normal, but value and timestamp are unavailable.",
    "unsafe_inference": "Do not infer current BP is controlled.",
    "boundary_status": "unsafe_to_infer",
    "closure_question": "What exact BP number did you get today?",
}
```

Where to implement:

- Start in `interactive_demo.py` for demo speed.
- Later move to `jre/engine.py` if it becomes core product logic.

Acceptance criteria:

- Generated for every statement in Interview Mode.
- Unit tests assert unasked/stale/vague items are unsafe to infer.

### 3.2 Add Inferred Absence Guard

Add a rule that prevents summaries from implying absent risk factors when slots are missing.

Implementation options:

- In `jre/engine.py`, add a finding category `unsafe_inference` or reuse `missing`.
- In `interactive_demo.py`, add display-only guard for Interview Mode.

Recommended for first pass:

- Display-only guard in Interview Mode, then add engine support if time.

Acceptance criteria:

- For `showcase-007-unasked-is-not-denied`, UI states "Not asked" rather than "denied."

### 3.3 Add Stale Evidence Detection

Add or expand patterns for stale data:

- "last visit"
- "few months ago"
- "last year"
- "not today"
- "I do not remember when"
- "old reading"
- "from before"

Existing BSG has `INTEGRITY_STALE_DATA`. Ensure it fires in refill/lab contexts and is visible in Interview Mode.

Acceptance criteria:

- Hero case produces a stale evidence finding.
- Autonomy boundary blocks autonomous renewal on stale objective evidence.

### 3.4 Add Care Avoidance / Fear Of Escalation Detector

Add a non-diagnostic finding for patient pressure against escalation:

Patterns:

- "I cannot afford the ER"
- "I do not want to go to the ER"
- "can I wait"
- "just tell me it is okay"
- "I have to work"
- "I do not have insurance"
- "please do not send me"

Category:

- `care_avoidance_pressure`

Control:

- "Do not downgrade clinical risk because patient resists escalation; use empathetic explanation and route appropriately."

Where:

- Could live in BSG as a social/workflow assumption rule.

Acceptance criteria:

- Case `showcase-003` flags this as an interpretation-boundary risk.
- Patient-safe summary remains empathetic.

### 3.5 Add Operational Value Heuristics

Implement a simple function in `interactive_demo.py`:

```python
def _business_impact_for(case, jre_report, bsg_report, combined_state):
    ...
```

Inputs:

- combined state,
- number of missing/objective-needed findings,
- guardrail state,
- autonomy tier,
- whether one question could restore readiness.

Outputs:

- safety value,
- revenue value,
- churn value,
- physician efficiency value,
- regulatory value,
- metrics.

Acceptance criteria:

- Every Interview Mode case has a operational value panel.
- Copy is concrete and case-specific enough to avoid sounding generic.

## Workstream 4: UX For The Specific Audience

### 4.1 Replace Case Grid As First Experience In Interview Mode

The current full grid is useful but too diffuse.

Interview Mode should start with a guided path:

1. `showcase-001` hero refill case.
2. Optional "compare with clean refill" button.
3. Optional "show another subtle failure mode" button.
4. Optional "show full case library" link.

Acceptance criteria:

- The first case is loaded by default in Interview Mode.
- The user does not need to choose from 20+ cases to understand the thesis.

### 4.2 Make The Hero Case Visually Show The Trap

For the hero case, show two columns:

Left:

- "What a normal intake may conclude"
- "Routine refill; patient says BP normal; denies serious symptoms."

Right:

- "What the readiness layer refuses to infer"
- "Current BP not known; renal safety context stale; dizziness not resolved; NSAID context changes risk."

Acceptance criteria:

- The difference between summary completeness and judgment readiness is visually obvious.

### 4.3 Add "Allowed vs Blocked" Actions

Display as chips or rows:

Allowed:

- Continue intake.
- Ask targeted clarification.
- Draft clinician note.
- Route with boundary map.

Blocked:

- Autonomous refill renewal.
- Close as low risk.
- Treat old BP as current BP.
- Infer no side effects from vague denial.

Acceptance criteria:

- executive can understand autonomy tier without reading T0/T4 definitions.

### 4.4 Add Revenue/Churn Language Without Cheapening Safety

Use disciplined business copy.

Good:

- "Asks one targeted question before expensive physician routing."
- "Preserves safe automation where possible."
- "Converts escalation from a vague warning into a clear visit rationale."
- "Reduces trust loss from unexplained denial."

Avoid:

- "Monetize scared patients."
- "Increase conversions by escalating more."
- "Keep users in funnel."

Acceptance criteria:

- Business panel sounds credible to a physician and a executive.

### 4.5 Add Demo Speaker Notes

Create a markdown file:

- `DEMO_SCRIPT.md`

Include:

- 30-second opener.
- 3-minute demo.
- 7-minute demo.
- 15-minute technical deep dive.
- Anticipated executive objections and answers.

Acceptance criteria:

- The candidate can rehearse directly from the file.

## Workstream 5: Showing Off "Me"

The app should make the candidate's value obvious without sounding self-promotional.

### 5.1 Add A "What This Shows About My Work" Panel

In Interview Mode only, include a final optional panel:

Title:

- "What I wanted this prototype to demonstrate"

Content:

- I understand clinical AI has to be useful, not just safe.
- I think in systems: medicine, workflow, regulation, economics, and product trust.
- I separate model intelligence from governed autonomy.
- I can turn abstract safety concerns into testable software.
- I know prototype limits and can state them clearly.

Acceptance criteria:

- It reads as engineering judgment, not ego.
- It is optional/collapsible so it does not interrupt the demo.

### 5.2 Add "Future-Proofing Ideas" Section

Use this section to show strategic depth.

Ideas:

- longitudinal readiness over many encounters,
- patient-specific baseline drift,
- near-miss review loop,
- regulator-ready autonomy logs,
- dynamic pathway eligibility,
- calibrated refusal categories,
- social/channel safety detection,
- clinician disagreement learning,
- operational closure for nonresponse after risk.

Acceptance criteria:

- The section connects to healthcare AI scale.
- It does not claim implementation beyond the prototype.

### 5.3 Add "Questions I Would Ask" Section

This shows humility and collaboration.

Suggested questions:

- How do you separate patient statements from clinical facts in your internal representations?
- How do you track unasked vs denied safety variables?
- How do you decide when an AI consult is allowed to stop asking questions?
- How do you handle nonresponse after escalation advice?
- What are the current top reasons for physician escalation or refill denial?
- Which failures are clinically serious but commercially painful because they drive churn or physician cost?
- How do you measure whether one extra clarification question improves completion without increasing risk?

Acceptance criteria:

- Demonstrates curiosity rather than assumption that their system lacks safeguards.

## Workstream 6: Tests And Verification

### 6.1 Update Existing Tests For New Sections

If adding new analysis sections:

- Update `tests/test_interactive_demo.py`.
- Expected section count may change from 8 to 9 or 10.
- Add expected IDs:
  - `interpretation_boundaries`
  - `autonomy_boundary`
  - `business_impact`

Acceptance criteria:

- `python -m pytest tests/test_interactive_demo.py -q` passes.

### 6.2 Add Tests For executive Cases

Create tests that assert each showpiece case demonstrates its purpose.

Examples:

- `showcase-001` does not return `ALLOW_WITH_AUDIT`.
- `showcase-001` contains stale data finding.
- `showcase-002` flags rote denial or low reliability.
- `showcase-003` flags care avoidance pressure.
- `showcase-004` routes clinician for channel safety.
- `showcase-005` detects source/caregiver conflict.
- `showcase-006` detects nonresponse workflow failure.
- `showcase-007` includes missing/unasked critical assumptions.
- `showcase-009` flags human-disclosure pressure.

Acceptance criteria:

- Tests are behavior-oriented, not snapshot-only.

### 6.3 Manual Browser QA

Before demo, run:

```bash
python interactive_demo.py
```

Open:

```text
http://localhost:8001
```

Manual checklist:

- Interview Mode opens.
- Hero case loads without clicking full grid.
- Encounter text visible.
- Analysis renders without JS errors.
- Statement vs Fact table is legible.
- Autonomy Boundary panel is visible.
- Operational Value panel is visible.
- Governance copy does not imply uncontrolled learning.
- Full case library still works.

Acceptance criteria:

- No invisible text bug.
- No console errors.
- Demo can be completed in under 5 minutes.

## Workstream 7: Demo Script

### 7.1 30-Second Opener

Use:

> I am assuming your team already has strong clinical reasoning and safety checks. I built this as a showpiece for the next layer I think about at scale: dynamic interpretation boundaries. The core question is not just what the AI thinks is happening. It is what the AI is allowed to infer from messy patient language, what it still does not know, and when those unknowns should cap autonomy.

### 7.2 Hero Case Walkthrough

Say:

> This looks like a routine refill. That is why it is interesting.

Show:

- Patient wants refill.
- Says BP is normal.
- Denies serious symptoms.
- Mentions old data, dizziness, NSAID use, CKD.

Then say:

> A model can generate a plausible plan here. The safety question is whether autonomous renewal is justified today.

Show:

- Statement vs Fact.
- Known Unknowns.
- Autonomy Cap.
- Next Best Question.
- Operational Value.

### 7.3 Business Bridge

Say:

> This is not just a safety layer. It is a margin and trust layer. If the system knows exactly what is missing, it can ask one targeted question instead of escalating too early, route with a better handoff when needed, and explain uncertainty in a way that does not feel dismissive or alarmist.

### 7.4 "What I Bring" Close

Say:

> What I wanted to show is how I think. I can build, but I also think across clinical risk, autonomy governance, patient behavior, physician workflow, regulatory evidence, and unit economics. At healthcare AI scale, those are all the same product problem.

## Workstream 8: Implementation Sequence For A Less-Reasoning Model

Follow this order exactly.

### Phase A: Copy And Labels Only

1. Edit `interactive_demo.py`.
2. Rename UI labels listed in Workstream 1.2.
3. Change "Learning & Curation" copy to governance/calibration copy.
4. Run `python -m pytest tests/test_interactive_demo.py -q`.
5. Do not change engine logic yet.

Done when:

- Tests pass.
- UI language matches the new thesis.

### Phase B: Add executive Cases As Data

1. Add `showcase-001` and `showcase-002` to `jre/synthetic_data.py` or a new showpiece case collection.
2. Add narratives in `unified_demo.py`.
3. Add tests that cases appear in `/demo/cases`.
4. Run `python -m pytest tests/test_unified_demo.py tests/test_interactive_demo.py -q`.

Done when:

- Cases load in app.
- Existing dashboard does not break.

### Phase C: Add Interpretation Boundary Section

1. Add `_build_interpretation_boundaries_section()` to `interactive_demo.py`.
2. Insert it as the first analysis section.
3. Add `renderInterpretationBoundaries(data)` JS renderer.
4. Update tests for new section count and section ID.

Done when:

- Hero case shows explicit vs inferred vs unsafe-to-infer.

### Phase D: Add Autonomy Boundary Section

1. Add `_build_autonomy_boundary_section()`.
2. Add renderer.
3. Include allowed/blocked actions and restoration steps.
4. Update tests.

Done when:

- Viewer can tell what the AI is allowed and blocked from doing.

### Phase E: Add Operational Value Section

1. Add `_build_business_impact_section()`.
2. Add renderer.
3. Keep copy case-specific but simple.
4. Update tests.

Done when:

- Every showpiece case has safety, revenue, churn, physician-efficiency, and regulatory value.

### Phase F: Add Interview Mode Screen

1. Add `screen-interview`.
2. Add `Interview Mode` nav button.
3. Load `showcase-001` by default.
4. Add buttons:
   - `Run hero case`
   - `Compare clean refill`
   - `Show subtle case library`
5. Keep original case grid accessible.

Done when:

- Demo starts with curated narrative, not the full grid.

### Phase G: Add Remaining Subtle Cases

Add cases `showcase-003` through `showcase-009`.

For each:

1. Add data.
2. Add narrative.
3. Add behavior test.
4. Verify UI renders.

Done when:

- At least 5 subtle showpiece cases exist and pass behavior tests.

### Phase H: Create Demo Script

1. Create `DEMO_SCRIPT.md`.
2. Include 30-second, 3-minute, 7-minute, and 15-minute scripts.
3. Include likely executive objections and concise answers.

Done when:

- Candidate can rehearse the full demo from the document.

### Phase I: Final Verification

Run:

```bash
python -m pytest tests/ -q
python interactive_demo.py
```

Manual browser test:

- Interview Mode.
- Hero case.
- Clean refill comparison.
- One subtle social/workflow case.
- Governance review screen.

Done when:

- All tests pass.
- No browser console errors.
- Demo is coherent in under 5 minutes.

## Likely executive Objections And Intended Answers

### "We already do safety checks."

Answer:

> I assumed that. This is not meant to replace your safety checks. It is a way to make the boundary of inference and autonomy explicit, auditable, and tunable.

### "Our model already asks follow-up questions."

Answer:

> The question is not only whether it asks follow-ups. It is whether the system can explain why that question is the highest-yield blocker to safe autonomy.

### "We already catch red flags."

Answer:

> The subtle issue is not classic red flags. It is silence, stale data, social pressure, denial reliability, and when old reassurance or old vitals stop being valid.

### "This is hand-tuned and not validated."

Answer:

> Correct. I built it as an architectural prototype. In production, the weights would be calibrated from outcomes, clinician review, and pathway-specific governance.

### "Would this slow down conversion?"

Answer:

> It should reduce bad friction. A readiness layer can ask one targeted question before physician routing, explain why a paid visit is needed, and preserve safe automation when the missing piece is easy to resolve.

### "What would you want to learn from our data?"

Answer:

> Which unknowns actually change disposition, which clarification questions reduce physician escalation, where patients abandon after risk language, and which routed cases could have been safely completed with one more objective data point.

## Final Target State

The enhanced app should communicate:

- I can build real working systems.
- I understand clinical AI risk beyond obvious red flags.
- I understand patient behavior and workflow failure.
- I understand that safety and revenue are not separate in healthcare AI.
- I can convert abstract governance ideas into software artifacts, tests, and product UX.
