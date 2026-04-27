# JRE Architecture

## Module overview

```text
Patient conversation / intake form
        ↓
Observation extractor
        ↓
Reliability scorer
        ↓
Expert-system safety slots
        ↓
MUD classifier: missing / uncertain / distorted / contradictory / unknowable
        ↓
CLEAR next-question selector
        ↓
Mitigation planner
        ↓
Judgment Readiness Arbiter
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

## Future extension

1. Replace keyword extraction with LLM extraction while keeping deterministic safety gates.
2. Add specialty-specific pathway packs.
3. Connect to EHR/pharmacy/device sources to verify objective data.
4. Use outcome feedback to update distortion priors and question-yield estimates.
5. Add `BoundaryTraceField` and `BoundarySelfModel` for stigmergic mitigation of repeated weak signals.
6. Add VAMS-style `AssociativeCaseMemory` for near-miss recall from sparse case signatures.
7. Add falsifier planning: what would disprove danger, what would disprove reassurance, and what evidence changes the autonomy cap.
8. Add provider UI with boundary cards and “why not ready?” summaries.
9. Build A/B studies: ordinary intake vs uncertainty-aware intake.

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
