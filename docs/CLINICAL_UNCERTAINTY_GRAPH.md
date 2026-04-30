# Clinical Uncertainty Graph

This is now the foundational JRE/BSG/DHSE object.

The system should not be described as an LLM judging clinical notes. It is an
expert-system uncertainty graph populated from clinical text, dialogue, chart,
device, clinician, or caregiver inputs. AI may assist extraction, but action
logic is explicit and auditable.

## Core Claim

```text
JRE builds and scores the clinical uncertainty graph.
BSG converts graph state into action boundaries.
DHSE tests whether graph and guardrail states matter against downstream outcomes.
```

## Node Model

Each clinically meaningful fact is represented as a typed node:

```text
ClinicalNodeState
  node_id
  label
  domain
  data_type
  observed
  raw_value
  numeric_value
  source
  source_reliability_prior
  confidence
  range_band
  range_severity
  boundary_distance
  boundary_fragility
  perturbation_flip_risk
  missingness_state
  uncertainty_distribution
  finding_categories
  action_implications
  dependencies
  traces
```

Nodes come from domain templates such as:

- `oxygen_saturation`
- `respiratory_rate`
- `sentence_test`
- `symptom_quality`
- `home_bp_number`
- `glucose_number`
- `mental_status`
- `lactate`
- `wbc`
- `heart_rate`
- `systolic_bp`

## Node Specifications

Each node has an expert-defined specification:

```text
ClinicalNodeSpec
  node_id
  label
  domain
  data_type
  importance
  critical
  objective_required
  remote_unknowable
  acceptable_sources
  ranges
  dependencies
  action_implications
  why_it_matters
```

Existing `SlotSpec` templates now compile into `ClinicalNodeSpec` objects.

## Numeric Ranges

Objective nodes can carry explicit ranges:

```text
RangeBand
  name
  low
  high
  severity
  action_signal
```

Examples:

| Node | Range | Severity | Action signal |
|---|---:|---:|---|
| `oxygen_saturation` | `<90` | `0.95` | `ESCALATE_OXYGENATION` |
| `oxygen_saturation` | `90-91.999` | `0.65` | `OBJECTIVE_INSTABILITY` |
| `respiratory_rate` | `>=30` | `0.95` | `ESCALATE_RESPIRATORY_RATE` |
| `heart_rate` | `>=120` | `0.75` | `OBJECTIVE_INSTABILITY` |
| `systolic_bp` | `<90` | `0.90` | `ESCALATE_HEMODYNAMICS` |
| `lactate` | `>=4` | `0.95` | `ESCALATE_SHOCK_OR_SEPSIS` |
| `glucose_number` | `>=300` | `0.80` | `DKA_RISK` |

These are deterministic expert ranges, not learned probabilities.

## Source Reliability Priors

Node observations carry source priors:

| Source | Prior |
|---|---:|
| `synthetic_truth` | `0.99` |
| `device` | `0.92` |
| `chart` | `0.88` |
| `clinician` | `0.86` |
| `caregiver` | `0.78` |
| `patient` | `0.72` |

JRE still applies penalties for vague language, objective claims without
numbers, trap patterns, language barriers, low literacy context, and text-only
modality.

## Uncertainty Distribution

Each node has a discrete uncertainty distribution:

```text
known_reliable
missing
semantic_uncertain
contradictory
range_abnormal
critical
remote_unknowable
```

This is the first implemented version of the probability-distribution premise.
It is expert-derived and deterministic, not yet outcome-calibrated. A future
real cohort can recalibrate these distributions.

## Game-Theory Layer: Strategic Signal Nodes

Clinical inputs are not neutral measurements. Patients, proxies, clinicians,
templates, and AI workflows operate under incentives that can distort what is
said or documented. The graph now models this explicitly through strategic
signal nodes.

Implemented strategic signals:

| Signal | Interpretation | Graph Effect |
|---|---|---|
| `care_avoidance_pressure` | Cost, work, fear, or access pressure may shape minimization. | Reduces reliability of patient/caregiver semantic nodes. |
| `answer_gaming_pressure` | The speaker may be optimizing answers to pass a workflow. | Raises strategic signal load and caps automation through BSG. |
| `proxy_misalignment` | Speaker may not be the patient or may not share patient information/incentives. | Raises reliability penalty and identity/proxy concern. |
| `coercion_or_observation_pressure` | Communication channel may be observed or unsafe. | Treats negative answers as weak and routes to protected workflow. |
| `defensive_minimization` | Stoicism, anxiety framing, or self-presentation may distort symptom severity. | Prioritizes concrete functional falsifiers. |
| `documentation_closure_pressure` | Documentation may compress unresolved uncertainty into closure language. | Preserves uncertainty in handoff and DHSE scoring. |

These are not moral judgments about patients or clinicians. They are
principal-agent / signaling-risk nodes that keep the system from treating a
strategically shaped signal as straightforward clinical reassurance.

Graph summary fields:

```text
strategic_signal_load
strategic_signals
```

## Dynamical Layer: Boundary Fragility

Clinical trajectories are often nonlinear near decision thresholds. A small
uncertainty in oxygenation, respiratory rate, lactate, blood pressure, or
diagnostic framing can flip the safe action boundary.

Each numeric range node now estimates:

```text
boundary_distance
boundary_fragility
perturbation_flip_risk
```

These are deterministic stress-test proxies:

- `boundary_distance`: distance to the nearest worse expert-defined threshold.
- `boundary_fragility`: how close the node is to a worse action band.
- `perturbation_flip_risk`: whether plausible small perturbation would flip the
  range/action interpretation.

Graph summary fields:

```text
boundary_fragility_load
boundary_flip_load
coupled_instability_load
boundary_sensitivity_index
fragile_nodes
```

This is the practical chaos/dynamical-systems translation: not claims of
mathematical chaos, but explicit modeling of threshold sensitivity and coupled
instability.

## Graph Summary

The graph computes:

```text
node_count
observed_nodes
completeness
reliability
objective_coverage
missing_load
semantic_uncertainty_load
contradiction_load
range_risk_load
criticality_load
strategic_signal_load
boundary_fragility_load
boundary_flip_load
coupled_instability_load
boundary_sensitivity_index
remote_unknowable_load
action_pressure
graph_readiness_index
breached_nodes
weak_nodes
fragile_nodes
strategic_signals
```

`graph_readiness_index` now feeds JRE `ReadinessScores`.

`action_pressure` now feeds Black Swan Guardrails.

DHSE now adds graph risk factors such as:

- `GRAPH_ACTION_PRESSURE`
- `GRAPH_RANGE_RISK_LOAD`
- `GRAPH_OBJECTIVE_COVERAGE_GAP`
- `GRAPH_MISSING_LOAD`
- `GRAPH_BREACHED_NODE:<node_id>`

## JRE Role

JRE builds the graph, classifies node states, computes the graph readiness
summary, creates the boundary map, and selects CLEAR questions.

JRE should now be described as:

> a node-state inference layer over an expert-defined clinical uncertainty
> graph.

## BSG Role

BSG consumes the JRE graph and adds assumption-boundary logic:

- identity/proxy integrity
- adversarial/channel integrity
- communication reliability
- operating envelope fit
- off-pathway sentinel risk
- objective data reliability
- JRE safety state
- novelty/distribution fit
- clinical uncertainty graph action pressure
- strategic signal reliability game
- boundary fragility / dynamical sensitivity

BSG should now be described as:

> an action-boundary governor over graph state and assumption state.

## DHSE Role

DHSE applies the same graph/governor architecture to ED disposition snapshots.

It scores only ED-disposition-time material and tests whether low graph
readiness / high action pressure / guardrail restriction enriches for PTR-B:

```text
Post-Disposition Trajectory Revision with Burden
```

DHSE should now be described as:

> a retrospective validation harness for whether uncertainty graph states and
> action-boundary states correspond to real downstream trajectory revision.

## Current Limits

Implemented now:

- typed nodes
- expert ranges
- source reliability priors
- discrete uncertainty distributions
- graph summary loads
- JRE score integration
- BSG action-pressure integration
- BSG strategic-signal and boundary-sensitivity assumptions
- DHSE graph-derived risk factors
- app-visible graph section
- tests

Not yet implemented:

- real-cohort calibration
- Bayesian posterior updating
- learned node dependency weights
- externally validated probability estimates
- site-specific range governance

Therefore, the current claim is:

> The app now implements a deterministic expert-system uncertainty graph. The
> graph is not yet calibrated as a clinical probability model, but it is a real,
> inspectable foundation for doing that calibration.
