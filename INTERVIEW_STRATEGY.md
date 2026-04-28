# Interview Strategy: Dynamic Interpretation Boundaries

Current live-demo companion: `FINAL_INTERVIEW_READINESS.md`.

## Core Thesis

Assume the audience already has strong AI-doctor capabilities: clinical reasoning, multi-agent review, patient-facing dialogue, physician escalation, prescription-refill constraints, and safety checks. The showpiece should not imply those are missing.

The stronger contribution is a next-layer safety and autonomy framework:

> The next frontier is not just whether the AI can answer. It is whether the AI knows which parts of the encounter are facts, which are inferences, which are unresolved unknowns, and when those unknowns should cap autonomy.

This is an interpretation-control problem, not a diagnosis-prediction problem.

## Important Reassessment

The current prototype is intentionally inspectable, but it is still too static:

- domain templates are limited,
- expert-system rules are mostly hand-authored,
- node ranges and weights are fixed,
- distributions are bounded scores rather than case-specific probabilistic objects,
- and the system does not yet create new governed templates dynamically.

The stronger future-facing claim is:

> The current demo proves the method. The next version uses AI to generate the case-specific expert-system graph, then governed deterministic software validates and executes it.

This avoids two weak positions:

1. A static rule system cannot cover the messy breadth of real healthcare encounters.
2. A pure LLM cannot be trusted to blur clinical facts, patient language, missing variables, and autonomy permission.

The best architecture is:

> AI-generated expert-system software with deterministic validation, outcome calibration, and autonomy governance.

## Dynamic Expert-System Architecture

Use this framing in the interview:

> I would not want to scale this only by hand-writing hundreds of templates. I would use AI initially to propose the case-specific boundaries, nodes, node ranges, probability distributions, and template extensions. But I would not let the AI directly decide autonomy. The AI proposes the expert-system graph; governed software validates it, scores it, and caps action.

### Step 1: AI Defines The Case Boundary

The AI reads the encounter and identifies:

- likely domains,
- overlapping domains,
- critical unknowns,
- unsafe inferences,
- stale evidence,
- source conflicts,
- social/workflow constraints,
- and autonomy-limiting assumptions.

Example:

```text
Routine refill + CKD + NSAID use + stale BP/labs = not a generic refill.
This needs a renal medication safety subgraph.
```

### Step 2: AI Proposes Dynamic Nodes

Instead of only using fixed slots, the system creates case-specific nodes:

- `current_bp_reliability`
- `renal_function_freshness`
- `potassium_safety_known`
- `nsaid_interaction_risk`
- `side_effect_signal_strength`
- `communication_reliability`
- `care_avoidance_pressure`
- `autonomous_refill_readiness`

Each node includes:

- range,
- distribution type,
- evidence sources,
- missingness rules,
- unsafe inference rules,
- and autonomy effect.

### Step 3: AI Proposes Ranges And Distributions

The node distribution should match the evidence type:

- boolean for present/absent hard-stop variables,
- categorical for source/channel states,
- ordinal for low/moderate/high risk,
- beta for bounded confidence/readiness,
- time-decay for stale objective evidence,
- mixture for competing clinical interpretations,
- hazard-like timing for deterioration-sensitive cases.

The key interview line:

> The system should not use one generic confidence number for everything. BP freshness, denial reliability, coercion risk, and time-sensitive clinical deterioration have different mathematical shapes.

### Step 4: AI Extends Or Creates Templates

If an existing template fits, extend it.

If no template fits, create a temporary governed template:

```text
ace_inhibitor_refill_with_ckd_and_nsaid
parent: med_refill_hypertension
required nodes: BP freshness, renal function, potassium, NSAID use, pregnancy, chart reconciliation
default cap: clinician draft only until objective verification
status: draft, not production-validated
```

### Step 5: Validators Control The AI

AI-generated rules should be rejected unless they pass checks:

- no unasked variable is treated as denied,
- stale data is not treated as current,
- source requirements are explicit,
- rule action does not exceed evidence,
- LLM-only findings cannot hard-stop without deterministic support,
- every new template has simulation cases,
- governance status is explicit.

This is the defensible healthcare AI architecture:

> AI creates adaptive structure. Expert software enforces boundaries.

## Learning Status: What Is Actually Incorporated

Local repo search found:

- No literal `VAMS` reference or implementation.
- No true reinforcement-learning policy.
- No explicit stigmergic learning layer.
- Yes: experiential learning exists through `ExperienceMemory`.

Current incorporated learning:

- distortion priors,
- question-yield estimates,
- EMA updates from experience events,
- clinician feedback categories: confirmed, corrected, false positive, missed,
- question priority influenced by expected information gain.

This is better described as:

> governed experiential calibration

not:

> full reinforcement learning.

## Future Learning Direction

The next version should add three learning layers:

1. **Offline RL-style question policy learning**
   - Learn which clarification question reduces unsafe uncertainty fastest.
   - Keep this offline or shadow-mode first.
   - Optimize question order, not clinical autonomy.

2. **Stigmergic near-miss memory**
   - Repeated near misses leave stronger traces.
   - Example: "normal BP without number" + refill approval churn/risk strengthens that trace across future cases.
   - Useful for propagating pattern awareness without requiring a single global rule edit every time.

3. **Governed template promotion**
   - AI-proposed dynamic templates start as draft.
   - Repeated validated cases promote them to reviewed templates.
   - Clinician/admin review remains the gate.

Interview language:

> I would not deploy live RL over medical decisions. I would use offline RL-like learning for question ordering, stigmergic memory for near-miss pattern propagation, and governance gates for promoting learned templates. The autonomy decision remains auditable.

## Local Learning Repo Assessment

The local `hcc_synth_1` and `vam-satzed` repos suggest a stronger next version of the demo.

`hcc_synth_1` is most useful as a stigmergic boundary substrate:

- signals leave traces instead of disappearing after one turn,
- traces decay at different rates depending on type,
- repeated weak signals can accumulate,
- nonresponse after risk can escalate over time,
- falsifiers can ask "what evidence would change the decision?",
- alert fatigue can be controlled without suppressing critical risk.

For this app, the right translation is not "clinical deterioration monitoring." It is:

> boundary deterioration monitoring

The field should track claims, objective evidence, source conflict, social/workflow risk, temporal staleness, and outcome feedback.

`vam-satzed` is most useful as associative near-miss memory:

- sparse Hopfield attractors,
- Hebbian strengthening when a recalled pattern is confirmed,
- anti-Hebbian weakening when it is rejected,
- pattern completion from partial cues,
- typed edges between related memories.

For this app, VAMS should not make clinical decisions. It should recall prior boundary failures:

```text
partial case signature
  -> recalled near-miss analogue
  -> missing nodes
  -> suggested falsifiers
  -> deterministic validators
  -> autonomy cap or clarification plan
```

The executive-facing framing:

> The system learns where interpretation failed, not just what diagnosis was present. It remembers the shape of near misses: stale objective data, patient minimization, missing source verification, nonresponse, and workflow pressure.

This directly addresses the limits in the current prototype:

- limited domain templates,
- static node ranges,
- weak memory of prior cases,
- weak handling of silence or vague reassurance,
- limited distinction between "not said," "denied," "inferred," and "objective."

Best demo language:

> I would use VAMS-style memory as a governed recall layer. It can say, "This looks like a prior near miss where the dangerous part was not the symptom, it was the missing verification." Then the expert system still decides what is allowed.

Demo update:

- Use the `Mitigation Plan` panel after `Operational Value`.
- Say that the current app mitigates the case with deterministic controls today.
- Then show how the same case would feed a stigmergic boundary trace, VAMS near-miss recall, and governed template-promotion queue.
- Keep the boundary clear: memory suggests; validators and governance decide.

## Premise

The system should maintain a dynamic boundary between:

- what the patient explicitly said,
- what the patient explicitly denied,
- what was never asked,
- what the AI inferred,
- what contradicts another statement or source,
- what may be minimized, hidden, embarrassing, misunderstood, socially unsafe to disclose, or shaped by defense patterns,
- what cannot be known remotely,
- and what assumptions must hold before autonomous action is defensible.

Patient language is not the same thing as clinical fact. Silence is not absence. A denial is not always reliable negative evidence. Vague reassurance is not objective data.

At scale, the dangerous cases are often not where the AI lacks medical knowledge. They are where the system over-trusts patient language, over-interprets silence, or fails to notice that the patient is shaping the conversation because they are afraid, embarrassed, cost-constrained, coerced, confused by medical facts, frightened by internet search, seeking reassurance, or trying to look stoic and avoid making a fuss.

## Best Interview Framing

Use this positioning:

> I am assuming your team already has strong clinical triage, emergency detection, physician escalation, refill eligibility checks, and adversarial safeguards. I built this to show the next layer I think about: how to make autonomy decisions auditable under uncertainty.

Then sharpen it:

> I am interested in the layer that separates patient statements from clinical facts. A patient denial is not automatically negative evidence. Silence is not absence. Vague reassurance is not objective data. The system needs to maintain dynamic boundaries around what it can safely infer, especially when patients are scared, cost-sensitive, embarrassed, coerced, confused by medical facts, seeking reassurance, or trying to appear stoic.

## What This Showpiece Demonstrates

The prototype is best described as an uncertainty-aware autonomy boundary layer around an AI clinical system.

It has two main thresholds:

1. **Judgment sufficiency**: do we know enough reliable clinical facts to act?
2. **Assumption sufficiency**: are we still inside the validated conditions where this pathway is allowed to act?

The current methodology maps to that architecture:

- **MUD map**: missing, uncertain, distorted, contradictory, objective-needed, and remotely unknowable information.
- **Source weighting**: patient, caregiver, device, chart, clinician, and synthetic truth are not equally reliable.
- **Contradiction rules**: patient language can internally conflict or conflict with another source.
- **Distortion priors**: some phrases are predictable interpretation traps.
- **CLEAR questions**: ask the highest-yield next question instead of continuing generic intake.
- **Black Swan Guardrails**: detect assumption failure, not just rare diagnoses.
- **Autonomy tiers**: dynamically cap what the AI is allowed to do.
- **Experience memory**: learn which clarification patterns reveal hidden risk, framed as governance/calibration rather than uncontrolled online learning.

## Terms To Use

Preferred terms:

- Dynamic Interpretation Boundaries
- Uncertainty-Aware Autonomy Boundaries
- Known Unknowns Map
- Assumption Sufficiency
- Judgment Readiness
- Boundary Calibration
- Autonomy Cap
- Interpretation-Control Layer

Avoid leading with:

- "better diagnosis"
- "we catch red flags you miss"
- "regex engine"
- "AI second opinion"
- "learning system" without governance framing

## Demo Language Rewrite

Current labels can be reframed:

- "What did the patient actually say?" -> **Statement vs Fact**
- "MUD Map" -> **Known Unknowns Map**
- "Hidden danger signals" -> **Interpretation Boundary Breaches**
- "Black Swan Guardrail" -> **Assumption Sufficiency Check**
- "Learning & Curation" -> **Boundary Calibration / Governance Review**
- "Generic LLM review" -> **Multi-Role LLM Candidate Pipeline / Extractor Cross-Check**

## Subtle Case Themes For A Physician executive

Avoid relying on obvious third-year medical student misses as the hero demo. Use those only as explainers.

Lead with mature-system failure modes:

1. **Fear of ER cost**
   - Patient minimizes symptoms because they cannot afford urgent care.
   - Boundary: do not downgrade severity because the patient resists escalation.

2. **Afraid to reveal domestic violence or coercion**
   - Patient asks about bruising but avoids cause; someone may be nearby.
   - Boundary: communication-channel safety is weak.

3. **Refill-seeking suppression**
   - Patient wants a refill and gives rote denials, then casually mentions dizziness, edema, bleeding, pregnancy possibility, or medication changes.
   - Boundary: pathway-completion behavior is not clean negative evidence.

4. **Embarrassment boundary**
   - Patient minimizes urinary, GI, sexual, pregnancy, substance-use, or mental-health details due to shame, stigma, or fear of a bad diagnosis.
   - Boundary: ask nonjudgmental clarifying questions before inferring low risk.

5. **Misconstrued medical-facts boundary**
   - Patient has searched online, latched onto one feared diagnosis, or believes a symptom is irrelevant because it does not match their mental model.
   - Boundary: normalize the uncertainty and ask concrete symptom questions rather than accepting the patient's self-triage frame.

6. **Defense-pattern boundary**
   - Patient frames the report through anxiety/somatic amplification ("maybe I am overreacting", "is this cancer?") or stoic minimization ("I do not complain", "I can tough it out", "not a big deal").
   - Boundary: do not label the patient; treat the transcript as lower-reliability evidence until concrete function, timing, current severity, and objective data are clarified.

7. **Caregiver-patient conflict**
   - Patient says they are fine; caregiver says they are confused, weaker, or not acting normally.
   - Boundary: patient self-report cannot dominate source conflict.

8. **Silent alarm**
   - Patient stops responding after the system says a symptom may require urgent care.
   - Boundary: nonresponse after risk is a workflow safety event, not a closed encounter.

8. **False reassurance**
   - Patient says "my doctor said this was okay" but current symptoms have changed.
   - Boundary: prior reassurance expires when new red flags or context changes appear.

8. **Inferred absence error**
   - Intake never asks pregnancy status, anticoagulants, immunosuppression, or recent labs, but the AI summary implies no relevant risk factors.
   - Boundary: unasked is not denied.

9. **Stale objective data**
   - BP, labs, glucose, pulse ox, renal function, pregnancy status, or medication list appears reassuring but is old or provenance is weak.
   - Boundary: objective-looking data is not automatically reliable data.

10. **Documentation completeness vs judgment readiness**
   - The AI can produce a coherent SOAP note, but the evidence is not reliable enough for autonomous action.
   - Boundary: complete documentation is not the same as decision readiness.

## Best One-Liner

> Your system may already have strong clinical reasoning. What I am bringing is a way to govern the uncertainty around that reasoning: know what was said, know what was inferred, know what was not asked, detect when communication is unreliable, and dynamically cap autonomy when the unknowns become unsafe.

## Recommended Demo Direction

The demo should show a routine-looking workflow where a mature AI could plausibly over-trust the encounter.

Best hero: a prescription-refill autonomy case.

Narrative:

> This looks like a routine refill. The AI can generate a reasonable plan. But the readiness layer refuses autonomous completion because the objective evidence is stale, patient denials are low-reliability, and a recent context change invalidates the low-risk pathway.

The demo arc should be:

1. Show the intake as the AI would see it.
2. Separate statement from fact.
3. Show what was inferred and what was not asked.
4. Highlight contradictions, silence, or soft avoidance.
5. Show the known-unknowns map.
6. Show the autonomy cap and next best question.
7. Show how clinician/governance feedback would calibrate future boundaries.
