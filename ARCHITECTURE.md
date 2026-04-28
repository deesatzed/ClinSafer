# JRE Architecture

## Module overview

```text
Patient conversation / intake form
        ↓
Transcript parser + input coverage audit
        ↓
Observation extractor + concept reclassifier
        ↓
Reliability scorer
        ↓
Expert-system safety slots
        ↓
MUD classifier: missing / uncertain / distorted / contradictory / unknowable
        ↓
CLEAR next-question selector
        ↓
Black Swan Guardrail assumption layer
        ↓
Most-restrictive autonomy governor
        ↓
Mitigation planner + final recommendations
        ↓
Provider boundary map + patient-safe clarification
```

## Design influence from prior builds

This prototype borrows three patterns from the user’s prior software systems:

### CAM-style pattern memory

- Store reusable patterns.
- Retrieve the most relevant pattern.
- Apply it to the current case.
- Verify result with tests/traces.
- Learn which method worked.

In JRE, the pattern is not code. The pattern is a clarification method:

> “When a respiratory patient says they are not short of breath, ask a functional probe and sentence test before trusting the denial.”

### aXc-style ensemble/meta-reasoning

JRE separates reasoning lenses:

- Slot completeness
- Reliability
- Distortion/health literacy
- Contradiction
- Red-flag safety
- Remote boundary

The final arbiter combines these into a state: `READY`, `CLARIFY`, `NEED_OBJECTIVE_DATA`, or `ESCALATE`.

### Expert-system discipline

Rather than relying on opaque LLM judgment, safety-critical rules are explicit:

- Required slots
- Objective-data requirements
- Red-flag patterns
- Remote-unknowable elements
- Rule traces

### Bounded multi-role LLM pipeline

The deployed interactive demo no longer represents the LLM as one generic
"second opinion." It exposes bounded roles:

- `extractor`: fast semantic extraction of candidate red flags, wrong labels,
  human distortion, and coverage gaps.
- `boundary`: clinical boundary reasoning about what makes automation unsafe and
  which falsifiers are still missing.
- `verifier`: adversarial audit for ignored transcript lines, false negatives,
  and unsafe reassurance.
- `patient_comm`: post-governor patient-language drafting only.
- `workflow`: post-governor clinician/workflow synthesis only.

The default async safety pass runs `extractor,boundary,verifier` in parallel.
All LLM roles are advisory. They can propose review targets and missing
falsifiers, but they cannot authorize care, downgrade a guardrail, prescribe,
close a case, or independently create the final autonomy boundary.

Role-specific model configuration is exposed through environment variables:

```text
OPENROUTER_ANALYSIS_ROLES=extractor,boundary,verifier
OPENROUTER_EXTRACTOR_MODEL=qwen/qwen3.6-flash
OPENROUTER_BOUNDARY_MODEL=qwen/qwen3.6-flash
OPENROUTER_VERIFIER_MODEL=qwen/qwen3.6-flash
OPENROUTER_PATIENT_MODEL=qwen/qwen3.6-flash
OPENROUTER_WORKFLOW_MODEL=qwen/qwen3.6-flash
OPENROUTER_MAX_PARALLEL_ROLES=3
```

The UI shows role, model, purpose, and authority so a technical reviewer can see
which layer produced a signal and whether that signal is allowed to affect
automation.

### Stigmergic boundary traces

The next mitigation layer borrows from the local `hcc_synth_1` repo. Instead of treating every encounter as stateless text, unresolved signals should leave bounded traces:

- patient claims and denials,
- objective evidence and timestamps,
- source conflict,
- social/workflow pressure,
- temporal staleness,
- outcome feedback.

Each trace type should decay at a different rate. Stale objective evidence should lose force quickly; unresolved source conflict, nonresponse after risk, and confirmed near-miss feedback should persist longer.

### VAMS-style associative memory

The next memory layer borrows from the local `vam-satzed` repo:

- sparse Hopfield attractor memory,
- Hebbian strengthening for confirmed recalls,
- anti-Hebbian weakening for rejected recalls,
- associative recall from partial cues,
- pattern completion,
- typed memory edges.

In this app, VAMS-style memory should recall near-miss boundary shapes, not make clinical decisions. A recalled memory can suggest missing nodes, falsifiers, and clarification questions. Deterministic validators still decide whether autonomy is capped.

## Core objects

### Statement

Raw answer from patient, caregiver, chart, device, or clinician.

### Observation

Normalized statement plus confidence and distortion tags.

### SlotSpec

Safety-relevant clinical variable for a domain.

### Finding

A MUD or safety issue.

### NextQuestion

A selected clarification question with rationale and expected information gain.

### ReadinessReport

Full provider-facing result.

## Judgment Readiness Index

The prototype combines:

- Completeness
- Reliability
- Objective-data coverage
- Contradiction load
- Distortion load
- Red-flag load
- Critical missingness

The score is intentionally transparent rather than optimized. A production version would calibrate weights through outcomes and governance review.

## Current Guarantees

The deployed app now enforces these demo-level guarantees:

1. Every submitted line appears in the Input Coverage Audit.
2. Wrong or generic concepts, including manual `red_flag`, are treated as hints
   and reclassified into active domain slots when the text supports it.
3. Unknown or unmapped observations are not neutral; they create review findings
   and cannot support closure.
4. Missing data is not treated as absent data.
5. LLM findings are candidate signals only.
6. The most-restrictive governor combines JRE and BSG states before any final
   recommendation is rendered.

## Future extension

1. Add specialty-specific pathway packs.
2. Connect to EHR/pharmacy/device sources to verify objective data.
3. Use outcome feedback to update distortion priors and question-yield estimates.
4. Add `BoundaryTraceField` and `BoundarySelfModel` for stigmergic mitigation of repeated weak signals.
5. Add VAMS-style `AssociativeCaseMemory` for near-miss recall from sparse case signatures.
6. Add falsifier planning: what would disprove danger, what would disprove reassurance, and what evidence changes the autonomy cap.
7. Add governed AI-generated dynamic templates: LLM proposes nodes, ranges, distributions, and rules; validators decide what can execute.
8. Build A/B studies: ordinary intake vs uncertainty-aware intake.

## Black Swan Guardrail Layer extension

The Black Swan Guardrail Layer wraps the JRE. JRE answers, “Do we know enough to act?” The guardrail answers, “Are we still inside the validated operating envelope where this pathway is allowed to act?”

```text
Patient conversation / intake form
        ↓
Judgment Readiness Engine
        ↓
Black Swan Guardrail Layer
        ↓
Assumption register + autonomy-tier cap
        ↓
ALLOW_WITH_AUDIT / HOLD_AND_VERIFY / ROUTE_CLINICIAN / FAIL_CLOSED / ESCALATE
```

The guardrail detects:

- off-pathway sentinel symptoms,
- identity/proxy breaches,
- adversarial or prompt-injection attempts,
- metric-gaming behavior,
- communication reliability failure,
- social-channel/coercion risk,
- stale or conflicting objective data,
- workflow failure such as nonresponse after risk,
- high-risk host factors that invalidate routine thresholds.

This separates model confidence from autonomy permission. A case can look clinically simple but still be non-automatable because a hidden assumption has failed.

## Mitigation architecture

The updated mitigation plan is:

```text
Current case
        ↓
Deterministic JRE + BSG controls
        ↓
Mitigation planner
        ↓
Immediate action cap / verification / escalation
        ↓
BoundaryTraceField deposit
        ↓
VAMS near-miss recall
        ↓
Candidate missing nodes and falsifiers
        ↓
Template validator + governance queue
```

The safety invariant is that memory and AI planning propose structure; governed expert-system software enforces boundaries.
