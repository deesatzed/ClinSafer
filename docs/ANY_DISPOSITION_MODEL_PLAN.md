# Any Disposition Model Plan

Last updated: 2026-04-30

## North Star

The project should now be framed as an **Any Dispo Judgment Readiness Engine**:

> For any proposed disposition, do we have enough reliable information, with
> acceptable residual uncertainty, to justify that destination and level of
> monitoring?

This keeps the original safety thesis but removes the one-direction assumption.
The system should evaluate the fit between patient state, uncertainty, resources,
follow-up, and the proposed destination.

## Disposition Directions

The same architecture should support at least four disposition questions:

1. **Lower-acuity risk**
   - Patient is being discharged, sent home, routed to telehealth follow-up, or
     placed in a low-monitoring pathway.
   - Question: is the case too uncertain or risky for that lower-acuity path?

2. **Higher-acuity benefit uncertainty**
   - Patient is being admitted, observed, transferred, or placed in a monitored
     pathway.
   - Question: is there a reviewable signal that inpatient or higher-acuity
     benefit may be low, given the information available at the decision point?

3. **Level-of-care mismatch**
   - Patient is being routed to floor, observation, stepdown, ICU, transfer,
     SNF, rehab, or home health.
   - Question: does the proposed destination have the monitoring, therapy, and
     follow-up capacity the patient needs?

4. **Disposition uncertainty preservation**
   - The available data may not support either reassurance or escalation.
   - Question: what uncertainty remains, what evidence would reduce it, and what
     is the safest review path?

## Claim Boundary

The system should not claim:

```text
This patient should be discharged.
This admission was unnecessary.
This patient is safe.
```

The system may claim:

```text
This case is a candidate for disposition review.
This proposed destination has unresolved readiness gaps.
This admission-benefit signal is uncertain and should be reviewed.
This lower-acuity path is blocked by deterministic guardrails.
This level-of-care choice appears mismatched to observed risk or resource need.
```

## Architecture

```text
Decision-time snapshot
  (ED, inpatient, observation, telehealth, clinic, or transition-of-care data)
        |
        v
Proposed disposition
  (home, observation, inpatient, floor, stepdown, ICU, transfer, SNF, rehab)
        |
        v
Clinical uncertainty graph
        |
        v
Black Swan / operating-envelope guardrails
        |
        v
Destination capability map
        |
        v
Disposition-specific heads
  - lower-acuity risk head
  - admission-benefit uncertainty head
  - level-of-care mismatch head
  - follow-up feasibility head
        |
        v
Empirical boundary learner
  (logistic, class-weighted logistic, GBDT, balanced forest, TabPFN)
        |
        v
Calibration + conformal/selective review
        |
        v
Most-restrictive disposition governor
        |
        v
Review recommendation with reasons, missing evidence, and safer alternatives
```

DHSE remains the first implemented head:

```text
ED admission snapshot -> was representation sufficient for downstream trajectory?
```

The next sister head is:

```text
Admitted/observed patient -> candidate for home, observation, or rapid outpatient
pathway review?
```

## Boundary Memory And Trace Layer

The Any Dispo frame needs memory, but only as a source of review hypotheses.
Two foundational modules now exist:

- `jre/boundary_trace.py`: a stigmergic-style `BoundaryTraceField` adapted from
  the `rustigmergic-logswarm-engine` pattern of patches, symbolic keys,
  support/opposition, decay, and retraction.
- `jre/associative_memory.py`: a VAMS-style `NearMissMemory` adapted from
  `Vamplify-Claude` action-memory patterns: partial signature recall, pattern
  completion, Hebbian strengthening, and anti-Hebbian weakening.

For Any Dispo, these modules should capture:

- unresolved lower-acuity blockers;
- source conflicts and stale objective data;
- destination capability gaps;
- nonresponse or unreliable follow-up after risk;
- low observed inpatient-only need signals;
- recurring level-of-care mismatch patterns;
- confirmed near misses and rejected false analogues.

Memory output may add review pressure, missing nodes, falsifiers, and suggested
review actions. It may not emit "safe to discharge," "unnecessary admission,"
or any autonomous disposition order.

## Data Contract Direction

Create a future `ANY-DISPO-CSV-v0.1` contract rather than forcing all cases into
`DHSE-CSV-v1.1`. DHSE can remain a specialization inside the broader schema.

The contract should separate:

- decision-time snapshot fields,
- proposed disposition fields,
- destination capability fields,
- baseline patient/context fields,
- post-disposition outcome labels,
- adjudication fields,
- governance and provenance fields.

Outcome and hospital-course fields must remain labels only. They cannot leak
into decision-time scoring.

## Data To Collect

### Encounter and Timing

- encounter ID and patient-stable deidentified ID
- encounter type: ED, observation, inpatient, telehealth, clinic, transfer
- arrival timestamp
- decision timestamp for the disposition being evaluated
- actual disposition timestamp
- proposed disposition at decision time
- actual disposition
- admitting or accepting service if applicable
- level of care: home, observation, floor, telemetry, stepdown, ICU, transfer,
  SNF, rehab, home health

### Decision-Time Clinical Snapshot

- triage acuity or equivalent severity marker
- chief concern and working diagnosis/problem representation
- clinician note/MDM available at or before decision time
- resulted labs available before decision time with timestamps
- resulted imaging available before decision time with timestamps
- vital signs before decision time with timestamps and trend
- oxygen requirement and respiratory support status
- ED/observation treatments before decision time
- response to treatment before decision time
- active medications relevant to disposition risk
- allergies and major medication constraints
- consult requests and consult recommendations available before decision time
- pending tests known at decision time
- known unresolved red flags

### Baseline Risk and Context

- age band
- comorbidity burden
- immunosuppression, pregnancy, frailty, dialysis, transplant, anticoagulation,
  or other high-risk host factors
- baseline oxygen use
- baseline mobility and functional status
- baseline residence
- caregiver availability
- ability to obtain medications
- ability to return if worse
- transportation reliability
- language/communication barriers
- cognitive impairment, delirium risk, or capacity concerns
- follow-up access and scheduled follow-up date if available
- patient preference or refusal constraints when documented

### Destination Capability

- destination can provide serial vitals
- destination can provide oxygen or respiratory support
- destination can provide IV therapy
- destination can provide telemetry or continuous monitoring
- destination can provide urgent imaging or procedure access
- destination can provide nursing checks
- destination can provide medication reconciliation
- destination can provide rapid clinician reassessment
- destination has confirmed follow-up path
- destination has confirmed caregiver or self-care capacity

### Post-Disposition Labels

For lower-acuity paths:

- 24-hour, 72-hour, 7-day, and 30-day ED return
- 7-day admission after discharge
- 30-day unplanned readmission
- death after discharge
- escalation to higher level of care after return
- urgent procedure after return
- major diagnostic change after discharge
- inability to obtain medication or follow-up

For admitted, observed, or higher-acuity paths:

- ICU or stepdown upgrade within 24 or 48 hours
- rapid response or code event
- urgent inpatient procedure
- new oxygen or ventilatory support
- IV-only therapy that could not be outpatient
- telemetry-relevant event
- major diagnostic pivot
- inpatient mortality
- length of stay and whether stay crossed two midnights
- discharge within 24 hours with no inpatient-only resource used
- observation-to-inpatient conversion
- inpatient-to-observation status change if available
- discharge disposition and higher-level-of-care need

### Clinician Adjudication

- reviewer role
- review timestamp
- adjudicated disposition category:
  - lower-acuity path appropriate
  - higher-acuity path appropriate
  - admission-benefit uncertain
  - lower-acuity risk missed
  - level-of-care mismatch
  - insufficient evidence
- adjudication confidence
- reason codes
- data missingness reason
- whether the model signal would have changed review priority

## Core Labels

Do not use one label for everything. Use a family of labels:

```text
lower_acuity_failure
observed_inpatient_need
low_observed_inpatient_need
admission_benefit_uncertain
level_of_care_mismatch
home_ready_review_candidate
disposition_review_needed
```

The first implementable inverse label should be:

```text
low_observed_inpatient_need =
  admitted_or_observed
  AND no ICU/stepdown upgrade
  AND no rapid response/code
  AND no urgent procedure
  AND no new oxygen/ventilatory support
  AND no IV-only therapy requirement
  AND no major diagnostic pivot
  AND no inpatient mortality
  AND short LOS or no inpatient-only resource used
```

This is a review label, not proof that admission was unnecessary.

## Deterministic Blockers

Any Dispo must preserve hard blockers. A case cannot be promoted to a
lower-acuity candidate when any blocker is unresolved:

- unstable or worsening vital signs
- oxygen requirement or escalating respiratory support
- critical or worsening lab trend
- unresolved dangerous diagnosis
- high-risk imaging or ECG finding
- active delirium, incapacity, or unsafe self-care
- high-risk host factor with inadequate objective data
- required procedure, consult, or inpatient-only therapy
- no reliable follow-up for a condition requiring close follow-up
- social or communication context that makes return precautions unreliable
- source conflict or missing objective data that would change the action tier

## Empirical Modeling

Use empirical models to prioritize review, not to authorize disposition.

Benchmarks:

- transparent logistic regression
- class-weighted logistic regression
- gradient boosting
- balanced random forest
- TabPFN
- TabPFN with tuning or HPO after schema stability
- fine-tuned TabPFN only after enough real rows and stable labels

Metrics:

- AUPRC
- recall at review budget
- precision at review budget
- false-negative concentration by subgroup
- calibration
- selective/conformal abstention rate
- review yield
- net benefit under clinician-defined harm weights

## First Build Sequence

1. Preserve DHSE as the first implemented Any Dispo head.
2. Add `docs/ANY_DISPOSITION_MODEL_PLAN.md` as the umbrella plan.
3. Implement foundational `BoundaryTraceField` and `NearMissMemory` modules.
4. Define `ANY-DISPO-CSV-v0.1` in a new schema doc.
5. Add sample admitted/observed cohort fixture.
6. Add `scripts/validate_any_dispo_export.py`.
7. Add `jre/any_disposition.py` with destination capability and deterministic
   blocker logic.
8. Add boundary trace and near-miss recall fields to Any Dispo reports.
9. Add `scripts/export_any_dispo_features.py`.
10. Add `scripts/benchmark_any_dispo_models.py`.
11. Add clinician adjudication codebook for any-dispo labels.
12. Add a demo/API panel named `Any Dispo Review`, initially read-only and
    retrospective.

## Pilot Readout

The first real-data readout should report:

- cohort flow by proposed disposition
- field completeness at decision time
- leakage validation
- label prevalence
- lower-acuity failures captured at review budgets
- low observed inpatient-need cases captured at review budgets
- subgroup false-negative analysis
- deterministic blocker frequency
- clinician adjudication agreement
- examples of useful and non-useful review flags

## Product Positioning

The strongest product framing is:

> ClinSafer does not decide where the patient goes. It audits whether the
> proposed disposition is justified by the available evidence, flags unresolved
> uncertainty, and routes ambiguous cases to the right review pathway.

That supports discharge safety, avoidable admission review, observation
management, level-of-care selection, and transition-of-care quality without
claiming autonomous clinical authority.
