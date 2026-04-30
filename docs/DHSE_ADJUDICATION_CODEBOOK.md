# DHSE PTR-B Adjudication Codebook

PTR-B is designed to be objective enough for retrospective benchmarking. It is
not a label for malpractice, diagnostic error, or avoidability.

## Label Rule

PTR-B positive requires both:

```text
one or more trajectory revision events
AND
one or more burden events
```

If only one side is present, the case is PTR-B negative.

## Trajectory Revision Events

Use only events after ED disposition.

| Code | Definition | Recommended Source |
|---|---|---|
| `DIAGNOSTIC_CATEGORY_REVISION` | ED diagnosis category differs materially from discharge diagnosis category. | ED diagnosis, discharge diagnosis grouping |
| `EARLY_ICU_UPGRADE` | Patient moved to ICU within 24 hours after ED disposition. | ADT bed movement |
| `EARLY_STEPDOWN_UPGRADE` | Patient moved to stepdown/progressive care within 24 hours. | ADT bed movement |
| `RAPID_RESPONSE_24H` | Rapid response, code, or equivalent team activation within 24 hours. | event log |
| `SERVICE_CHANGE_FOR_DIAGNOSTIC_REVISION` | Admitting service changed because the problem representation changed. | service transfer orders plus reason |
| `THERAPEUTIC_PIVOT_*` | Major therapy added or changed because the working problem changed. | medication/procedure/order timestamp |

Do not count routine completion of an expected inpatient workup as a trajectory
revision unless it changed the problem representation or care trajectory.

## Burden Events

| Code | Definition | Recommended Source |
|---|---|---|
| `ICU_TRANSFER_24H` | ICU transfer within 24 hours. | ADT bed movement |
| `STEPDOWN_TRANSFER_24H` | Stepdown/progressive care transfer within 24 hours. | ADT bed movement |
| `RAPID_RESPONSE_24H` | Rapid response or code within 24 hours. | event log |
| `IN_HOSPITAL_MORTALITY` | Death during index hospitalization. | discharge disposition |
| `MAJOR_PROCEDURE` | Major procedure not already planned at ED disposition. | procedure table |
| `DELAYED_DEFINITIVE_THERAPY_GE_6H` | Definitive therapy delayed at least 6 hours after trajectory revision became clear. | medication/procedure timestamps |
| `RISK_ADJUSTED_LOS_EXCESS` | LOS is at least 1.5x expected and at least 24 hours longer than expected. | LOS plus DRG/risk model |
| `HIGHER_LEVEL_DISCHARGE` | Discharge to higher level of care than baseline. | discharge disposition plus baseline residence |
| `READMISSION_30D` | Unplanned readmission within 30 days. | encounter linkage |

## Negative Examples

These are PTR-B negative unless another qualifying revision and burden event is
present:

- inpatient team completes planned serial troponins after chest-pain admission
- planned MRI confirms the expected admission diagnosis
- culture sensitivities narrow antibiotics without worsening, upgrade, or delay
- longer LOS from placement delay alone
- discharge diagnosis wording differs but category is clinically equivalent
- pending result returns after admission but does not alter trajectory

## Adjudication Fields

For manual review or audit, record:

- `case_id`
- `trajectory_revision_present`
- `revision_event_codes`
- `burden_present`
- `burden_event_codes`
- `ptr_b_positive`
- `evidence_timestamps`
- `adjudicator_initials`
- `uncertain_flag`
- `notes`

## Disagreement Handling

If two reviewers disagree:

1. Re-check whether both required PTR-B sides are present.
2. Prefer timestamped structured facts over narrative interpretation.
3. If revision exists but burden is speculative, label negative.
4. If burden exists but the care trajectory was not revised, label negative.
5. Mark unresolved ambiguity as `uncertain_flag=true` and exclude from the
   primary analysis; include in sensitivity analysis if needed.
