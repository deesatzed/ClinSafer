# Disposition Handoff Sufficiency in Emergency Admissions: A Retrospective Benchmark for ED Representation Quality Using Post-Disposition Trajectory Revision With Burden

**Authors:** Wayne Satz, MD; [co-author placeholders]

**Affiliation:** Department of Emergency Medicine, Temple University Health System; [additional affiliations]

**Status:** Preliminary manuscript draft v0.1

**Target venues:** NEJM AI, JAMIA, npj Digital Medicine

**Date:** April 29, 2026

---

## Abstract

### Background

Emergency department (ED) admission handoffs routinely transfer unresolved diagnostic work. Evaluation frameworks that treat pending results or incomplete inpatient workup as handoff failure are therefore poorly aligned with ED operations and risk encouraging unsafe disposition delays. A more appropriate retrospective question is whether the ED disposition representation, using only information available at the time of admission, was sufficient for the inpatient trajectory that subsequently unfolded.

### Objective

To introduce the Disposition Handoff Sufficiency Engine (DHSE), a retrospective benchmark framework that scores ED-disposition-time representations and evaluates whether low sufficiency scores enrich for post-disposition trajectory revision with measurable burden.

### Methods

We define Post-Disposition Trajectory Revision with Burden (PTR-B), a post-discharge label requiring both an objective trajectory revision event and a measurable burden event. DHSE scores only ED-disposition-time inputs, including ED HPI, ED MDM, ED-available labs/diagnostic imaging, key past medical history, treatments, disposition diagnosis, admitting service, and intended level of care. The scoring substrate is an expert-system clinical uncertainty graph: clinical facts are typed nodes with source reliability priors, expert-defined range bands, uncertainty distributions, dependencies, action implications, strategic-signal reliability modifiers, and boundary-sensitivity measures. JRE builds and scores the node graph; Black Swan Guardrails convert graph state and assumption breaches into action boundaries; DHSE evaluates whether those graph/action-boundary signals enrich for PTR-B. Inpatient H&P and discharge summary material are excluded from scoring and used only for retrospective label adjudication. DHSE produces a Disposition Sufficiency Index (DSI, 0-100), with lower scores indicating greater representation-sufficiency risk. The primary prediction task is PTR-B enrichment using `risk = 100 - DSI`. Primary metrics are AUROC, AUPRC, top-decile enrichment, and capture at fixed review budgets. Required baselines include structured severity, nonspecific diagnosis, ED length of stay, JRE-only risk, and Black Swan Guardrail-only risk.

### Results

Retrospective cohort results are pending. The current implementation includes a canonical CSV contract, validator, reproducible study-packet generator, adjudication codebook, synthetic fixture, and automated tests. Synthetic and sample-export outputs are engineering smoke tests only and are not clinical validation results.

### Conclusions

DHSE operationalizes a measurable retrospective question: whether ED-disposition-time documentation contains computable insufficiency signals that enrich for later objective trajectory revision with measurable burden. The framework does not infer diagnostic error, causality, clinician fault, or prospective need to delay admission. If validated, DHSE may support ED-to-inpatient handoff quality surveillance, documentation improvement, and safety evaluation of clinical AI systems that consume or generate disposition representations.

---

## Key Points

**Question:** Can ED-disposition-time documentation be scored for representation sufficiency in a way that predicts later objective trajectory revision with measurable burden?

**Findings:** Cohort results are pending. The proposed benchmark defines PTR-B as a hard retrospective endpoint requiring both trajectory revision and burden, while prohibiting inpatient and discharge information from scoring inputs.

**Meaning:** The framework shifts handoff evaluation away from subjective checklist quality and away from penalizing routine pending workup, toward an auditable prediction task grounded in post-discharge outcomes.

---

## 1. Introduction

ED-to-inpatient handoff is a safety-critical transition. At admission, however, the ED is not expected to have completed the entire diagnostic and therapeutic arc. Hospital admission often exists precisely because additional observation, testing, specialist evaluation, or treatment response monitoring is needed. A handoff metric that treats pending results as failure would be operationally incorrect and could encourage ED gridlock.

The more clinically coherent question is narrower: at the point of ED disposition, did the available representation of the patient adequately describe the problem, acuity, uncertainty, and objective risk needed for the inpatient trajectory that actually unfolded?

Existing handoff evaluation approaches commonly emphasize information completeness, checklist adherence, communication quality, or subjective reviewer assessment. These approaches are valuable but insufficient for a benchmark intended to evaluate computational systems. Subjective evaluations are difficult to reproduce across sites, while checklist completeness can reward longer documentation without testing whether the disposition representation matched the patient’s subsequent trajectory. Conversely, adverse outcomes alone are too broad: they may reflect baseline severity, disease progression, inpatient delays, bed availability, or expected diagnostic evolution rather than ED handoff insufficiency.

We propose a retrospective benchmark that occupies a middle ground. The Disposition Handoff Sufficiency Engine (DHSE) uses only information available at the ED disposition decision to compute a Disposition Sufficiency Index (DSI). Outcomes are assigned only after discharge using Post-Disposition Trajectory Revision with Burden (PTR-B), a label requiring both objective trajectory revision and measurable burden. The method is designed to be falsifiable: DHSE must be compared with simple severity and documentation baselines, and any claim of value depends on incremental signal beyond these alternatives.

The intended contribution is methodological. DHSE does not prove diagnostic error. It does not assign clinician fault. It does not recommend delaying admission for pending inpatient workup. It tests whether the ED disposition representation contains computable insufficiency signals associated with later material trajectory revision.

---

## 2. Methods

### 2.1 Study Design

This is a retrospective observational benchmark and methods study. The unit of analysis is an adult ED admission. The scoring input is the ED-disposition-time representation. The outcome label is assigned after hospital discharge.

The study has two phases:

1. **Engineering and feasibility phase:** validate schema, leakage controls, reproducible packet generation, and PTR-B labelability on a small redacted notes-mode cohort.
2. **Retrospective benchmark phase:** evaluate DSI against PTR-B and required baselines in a larger cohort.

The present manuscript draft describes the methodology and analysis plan. Clinical validation results will be inserted only after a locked cohort export and analysis run.

### 2.2 Cohort

The initial target cohort is adult ED admissions to hospital medicine or medicine observation-to-inpatient pathways.

Recommended inclusion criteria:

- age 18 years or older
- ED admission with disposition timestamp available
- ED HPI and ED MDM available
- ED MDM or structured extract includes ED-resulted labs and diagnostic imaging available before disposition
- inpatient H&P available for label support
- discharge summary available for label support
- hospital discharge diagnosis and length of stay available

Recommended primary exclusions:

- direct ICU admissions
- planned procedural admissions
- hospice or comfort-care admissions
- social or placement-only admissions
- missing ED disposition timestamp
- missing discharge outcome fields required for PTR-B
- pure protocolized observation pathways where serial inpatient testing was the intended reason for admission and no trajectory revision occurred

### 2.3 Data Sources

The preliminary notes-mode pilot may use redacted documents:

- ED HPI
- ED MDM, including labs and diagnostic imaging documented as available to the ED clinician
- inpatient H&P
- inpatient discharge summary

These documents are separated into scoring and labeling roles.

**Scoring inputs:**

- ED HPI
- ED MDM
- ED-available labs and diagnostic imaging
- key past medical history
- ED treatments
- disposition diagnosis or problem representation
- admitting service
- intended level of care

**Label/adjudication inputs only:**

- inpatient H&P
- inpatient discharge summary
- post-disposition hospital course
- discharge diagnosis
- inpatient procedures
- ICU/stepdown transfer
- rapid response/code events
- hospital length of stay
- discharge disposition
- readmission when available

The DHSE scoring function must not receive inpatient H&P or discharge summary text.

### 2.4 Input Modes

DHSE supports three input modes.

**Notes mode:** evaluates documented ED disposition material. This is the primary mode for the preliminary retrospective pilot.

**Dialogue mode:** evaluates a current or recorded patient-clinician exchange before note synthesis. Objective data must be supplied separately.

**Hybrid mode:** evaluates both dialogue and documentation while preserving source labels. This mode is relevant when current dialogue and notes are both available.

The preliminary cohort may be notes-only. Dialogue and hybrid analyses should be reported only when those data exist.

### 2.5 Clinical Uncertainty Graph

The methodological foundation is an explicit expert-system graph. Each clinically meaningful input is represented as a node containing:

- node identifier and clinical label
- domain and data type
- observed raw value and normalized numeric value when available
- source and source reliability prior
- observation confidence
- expert-defined range band and range severity for numeric nodes
- missingness state
- discrete uncertainty distribution
- finding categories
- dependencies
- action implications
- boundary distance, boundary fragility, and perturbation flip risk for numeric nodes
- strategic-signal membership when the reliability of a statement is incentive-shaped

The current graph distribution contains:

```text
known_reliable
missing
semantic_uncertain
contradictory
range_abnormal
critical
remote_unknowable
strategic_signal
```

The graph summary includes completeness, reliability, objective coverage, missing load, semantic uncertainty load, contradiction load, range risk load, criticality load, remote-unknowable load, strategic signal load, boundary fragility load, perturbation flip load, coupled instability load, action pressure, boundary sensitivity index, and graph readiness index. These are deterministic expert-system quantities in the current implementation, not yet outcome-calibrated probabilities.

The game-theory layer treats some statements as strategic signals rather than neutral facts. Examples include care-avoidance pressure, answer gaming pressure, proxy misalignment, coercion or observation pressure, defensive minimization, and documentation closure pressure. These signals create graph nodes and modify reliability of affected semantic observations.

The dynamical-sensitivity layer does not claim mathematical chaos in the strict sense. It operationalizes the clinically important part: small changes near action-changing thresholds can flip the safe boundary. Numeric nodes therefore record distance to worse thresholds, boundary fragility, and perturbation flip risk; the graph summarizes coupled instability across related nodes.

### 2.6 Disposition Handoff Sufficiency Engine

DHSE adapts two existing project components:

- the Judgment Readiness Engine (JRE), which scores completeness, reliability, missingness, uncertainty, distortion, contradiction, objective-data needs, and remote unobservability
- Black Swan Guardrails, which detect assumption-boundary failures and unsafe autonomy conditions

For an ED disposition snapshot, DHSE constructs a case representation from ED-disposition-time materials and computes:

- DSI: Disposition Sufficiency Index, 0-100
- DHSE state: `SUFFICIENT`, `UNDER_SPECIFIED`, `ACUITY_MISMATCH_RISK`, or `DIAGNOSTIC_PIVOT_RISK`
- JRE state
- Black Swan Guardrail state
- risk factors and protective factors
- input limitations

DSI is not a diagnosis score. It is a representation-sufficiency score. Lower DSI indicates greater risk that the disposition representation is under-specified, mismatched to objective acuity, or vulnerable to diagnostic pivot.

### 2.7 Primary Outcome: PTR-B

The primary label is Post-Disposition Trajectory Revision with Burden (PTR-B).

PTR-B is positive only when both conditions are met:

```text
any objective trajectory revision event
AND
any measurable burden event
```

Trajectory revision events include:

- ED diagnosis category differs materially from discharge diagnosis category
- floor admission upgraded to stepdown or ICU within 24 hours
- rapid response or code within 24 hours
- major therapeutic pivot after admission
- admitting service changed because the initial problem representation was materially wrong or incomplete

Burden events include:

- ICU or stepdown transfer within 24 hours
- rapid response or code within 24 hours
- in-hospital mortality
- major procedure
- delayed definitive therapy of at least 6 hours
- risk-adjusted LOS at least 1.5 times expected and at least 24 hours longer than expected
- discharge to higher level of care than baseline
- 30-day readmission

PTR-B negative examples include:

- planned inpatient serial testing without trajectory revision
- expected diagnostic refinement without burden
- culture narrowing without clinical worsening or delayed definitive therapy
- longer LOS due only to placement or social delay
- discharge diagnosis wording changes within the same clinical category
- post-admission pending result that does not alter care trajectory

### 2.8 Leakage Controls

The central validity threat is label leakage. To prevent leakage:

1. ED scoring inputs and inpatient label inputs are stored separately.
2. DHSE scoring is completed before PTR-B adjudication is attached.
3. Inpatient H&P and discharge summary are prohibited from the scoring file.
4. Discharge diagnosis, LOS, ICU transfer, rapid response, mortality, readmission, and hospital-course narratives are label fields only.
5. The study packet records input hashes and validation output.
6. Any leakage-risk column in a flat export is flagged by the validator.

### 2.9 Redaction Handling

PII/PHI redaction should preserve clinical temporality and role structure where possible. For example, relative timing should be retained as “3 days,” “yesterday,” or “after dialysis,” rather than removed entirely. Redaction density should be tracked as metadata when feasible. Heavily redacted cases may be excluded or analyzed in sensitivity analyses.

### 2.10 Baselines

Minimum implemented baselines:

- structured severity heuristic
- nonspecific diagnosis heuristic
- ED length-of-stay heuristic
- JRE-only risk
- Black Swan Guardrail-only risk

Recommended additional baselines for the full retrospective study:

- structured severity logistic model using objective ED features
- diagnosis-discordance-only model
- admission service and level-of-care model
- graph-family ablations removing strategic signals, boundary sensitivity, range-risk nodes, and missingness/objective-coverage nodes
- generic LLM risk score using a fixed prompt and fixed model, if a model and governance contract are fixed before analysis lock

The key benchmark question is not whether DHSE has a high unadjusted association with PTR-B, but whether it adds signal beyond severity, nonspecific diagnosis, and operational baselines.

### 2.11 Metrics

The primary risk score is:

```text
risk = 100 - DSI
```

Primary metrics:

- AUROC for PTR-B
- AUPRC for PTR-B
- top-decile enrichment
- capture at fixed review budgets: 5%, 10%, 20%

Secondary analyses:

- calibration bins
- DSI threshold table
- input-mode stratification
- DHSE-state stratification
- defect-family stratification
- false-positive and false-negative error analysis
- sensitivity excluding LOS burden
- sensitivity excluding narrative-only therapeutic pivots
- sensitivity by diagnosis domain

### 2.12 Reproducibility

The implementation includes:

- canonical flat CSV schema
- export validator
- study-packet generator
- run manifest with input hash
- case-level output CSV
- full report JSON
- methods snapshot
- synthetic fixture
- automated test suite

The study packet is the auditable unit for collaborator review.

---

## 3. Results

### 3.1 Implementation Status

The DHSE implementation is complete enough for notes-mode retrospective pilot testing. It supports canonical CSV and JSONL inputs, validates export structure, runs DHSE, computes PTR-B labels from outcome fields, compares implemented baselines, and writes reproducible study packets.

Current local verification:

- full automated test suite: 346 tests passing
- DHSE-focused tests: 10 tests passing
- sample canonical CSV validation: valid
- sample study packet generation: successful

These are engineering checks only. They do not constitute clinical validation.

### 3.2 Cohort Flow

To be populated after real cohort export.

Planned table:

| Cohort step | n |
|---|---:|
| Candidate adult ED admissions | pending |
| Excluded direct ICU admissions | pending |
| Excluded planned/procedural admissions | pending |
| Excluded missing ED disposition timestamp | pending |
| Excluded missing label fields | pending |
| Final scored cohort | pending |
| PTR-B labelable cohort | pending |

### 3.3 PTR-B Prevalence

To be populated after adjudication.

Planned table:

| Label/event | n | % |
|---|---:|---:|
| PTR-B positive | pending | pending |
| PTR-B negative | pending | pending |
| Diagnostic category revision | pending | pending |
| Early ICU/stepdown upgrade | pending | pending |
| Rapid response/code within 24h | pending | pending |
| Major therapeutic pivot | pending | pending |
| LOS burden | pending | pending |

### 3.4 Primary Benchmark Performance

To be populated after the locked analysis run.

Planned table:

| Model | AUROC | AUPRC | Top-decile enrichment | Capture at 10% review |
|---|---:|---:|---:|---:|
| DHSE | pending | pending | pending | pending |
| Structured severity | pending | pending | pending | pending |
| Nonspecific diagnosis | pending | pending | pending | pending |
| ED LOS | pending | pending | pending | pending |
| JRE-only | pending | pending | pending | pending |
| Black Swan-only | pending | pending | pending | pending |

### 3.5 Calibration and Thresholds

To be populated after cohort run. The main paper should report calibration bins and operating characteristics across pre-specified DSI thresholds, but should not present thresholds as deployment recommendations.

### 3.6 Error Analysis

False positives and false negatives will be reviewed to determine whether DHSE is capturing:

- severity rather than representation insufficiency
- nonspecific documentation without material trajectory change
- true acuity mismatch
- diagnostic pivot risk
- label noise
- redaction-related loss of signal
- inpatient-course events unrelated to ED disposition representation

---

## 4. Discussion

This manuscript proposes a retrospective benchmark for ED disposition representation sufficiency. The framework addresses a practical problem: ED admissions often appropriately transfer unresolved diagnostic work, so handoff evaluation should not penalize pending workup itself. DHSE instead asks whether the ED-disposition-time representation was sufficient relative to the patient trajectory that later became evident.

The key methodological move is the PTR-B label. PTR-B requires both trajectory revision and burden. This prevents routine diagnostic refinement from being counted as failure and prevents adverse outcomes without representational mismatch from being treated as handoff defects. It also makes the benchmark measurable: AUROC, AUPRC, enrichment, capture at review budgets, and baseline comparisons can be computed without subjective site-specific quality ratings as the primary endpoint.

The framework is intentionally conservative. A positive PTR-B label does not prove diagnostic error. A low DSI does not prove clinician fault. A high DSI does not prove that the original ED representation was ideal. Rather, DSI is a ranking signal intended to identify records for retrospective quality review, handoff-improvement analysis, and clinical AI safety evaluation.

If validated, DHSE could support several use cases. Health systems could use it to identify patterns of disposition representations that later required major inpatient reframing. Training programs could use it to teach problem representation under uncertainty. Clinical AI developers could use it to test whether AI-generated summaries or intake workflows preserve enough actionable uncertainty before disposition. Importantly, these are retrospective and quality-improvement uses; prospective clinical deployment would require separate safety evaluation.

---

## 5. Anticipated Criticisms and Design Responses

### 5.1 PTR-B May Reflect Severity Rather Than Handoff Insufficiency

This is the most important validity threat. The benchmark must compare DHSE against structured severity, abnormal vitals/labs, ED LOS, level of care, and diagnosis nonspecificity. Any manuscript claim should depend on incremental performance over these baselines.

### 5.2 Documentation Quality Is Not Clinical Reasoning Quality

DHSE evaluates the documented ED disposition representation, not the clinician’s internal reasoning. This is an intentional scope restriction. The documented representation remains clinically relevant because it is what inpatient teams and downstream AI systems inherit.

### 5.3 Inpatient Documents Create Hindsight Bias

Inpatient H&P and discharge summary are prohibited from scoring. They are used only for label construction. Manual adjudication should classify objective events and timestamps rather than judge whether the ED clinician should have known the final diagnosis.

### 5.4 LOS Is Operationally Noisy

LOS burden is paired with trajectory revision and should be analyzed in sensitivity analyses. The manuscript should report results excluding LOS-only burden if enough events exist.

### 5.5 Redaction May Remove Clinical Signal

Redaction should preserve timing, clinical relationships, and role labels when possible. Redaction density should be tracked. Heavily redacted cases may require exclusion or sensitivity analysis.

### 5.6 DSI Thresholds May Be Arbitrary

The primary analysis is ranking and enrichment, not threshold classification. DSI thresholds are reported as descriptive operating points only.

---

## 6. Limitations

This study is retrospective and cannot establish causality. PTR-B identifies trajectory revision with burden, not preventable diagnostic error. ED notes may incompletely reflect bedside communication. Discharge summaries are post-hoc narratives and may contain retrospective rationalization. LOS is influenced by hospital operations, bed availability, social needs, and placement delays. Diagnosis-category mapping may be coarse. Redaction may remove clinically relevant detail. Initial notes-mode evaluation does not test dialogue sufficiency unless dialogue data are available. The framework should not be used prospectively to delay ED admissions without separate validation.

---

## 7. Conclusion

DHSE provides a reproducible retrospective benchmark for ED disposition handoff sufficiency. By scoring only ED-disposition-time material and labeling outcomes after discharge with PTR-B, the framework avoids penalizing routine pending workup while creating a measurable prediction task. The appropriate claim is conservative: DHSE tests whether ED disposition representations contain computable insufficiency signals that enrich for later objective trajectory revision with measurable burden. Clinical validation remains pending.

---

## Data Availability

The preliminary implementation uses synthetic fixtures and sample canonical exports. Real institutional data will require IRB/governance approval and de-identification or limited-data handling. Code, schema, study-packet tooling, and synthetic fixtures are intended for open release where permissible.

---

## Code Availability

The current implementation includes:

- `jre/disposition_handoff.py`
- `scripts/validate_dhse_export.py`
- `scripts/run_dhse_benchmark.py`
- `scripts/create_dhse_study_packet.py`
- `docs/DHSE_CANONICAL_CSV_SCHEMA.md`
- `docs/DHSE_ADJUDICATION_CODEBOOK.md`
- `docs/DHSE_REAL_DATA_PILOT_RUNBOOK.md`

---

## Funding

No external funding reported.

---

## Conflicts of Interest

None reported.

---

## Author Contributions

Wayne Satz: conceptualization, clinical framing, methodology, software direction, manuscript drafting. Additional contributions pending co-author assignment.

---

## References To Assemble

1. ED handoff and transitions-of-care safety literature.
2. Diagnostic error and cognitive bias literature, including Croskerry and related emergency medicine diagnostic reasoning work.
3. Handoff quality instruments and I-PASS literature.
4. EHR-based retrospective outcome and diagnostic safety trigger literature.
5. Clinical AI evaluation and deployment-safety literature.
6. JRE and Black Swan Guardrail project documentation.
7. DHSE protocol, schema, and adjudication codebook.
