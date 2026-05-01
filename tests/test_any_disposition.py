from jre import (
    ADVISORY_AUTHORITY,
    AnyDispositionCase,
    AnyDispositionReviewEngine,
    DecisionTimeEvidence,
    DestinationCapability,
    ProposedDisposition,
)


def test_lower_acuity_path_is_blocked_by_objective_instability_and_followup_gap():
    engine = AnyDispositionReviewEngine()
    case = AnyDispositionCase(
        case_id="any-home-unstable",
        age=73,
        chief_concern="shortness of breath",
        domain="dyspnea_respiratory",
        proposed_disposition=ProposedDisposition(destination="home", follow_up_plan="call if worse"),
        destination_capability=DestinationCapability(confirmed_follow_up=False, caregiver_or_staff_support=False),
        evidence=DecisionTimeEvidence(
            vital_trend={"spo2": [95, 90], "hr": [106, 124], "rr": [22, 28]},
            unresolved_red_flags=["worsening dyspnea"],
            high_risk_factors=["COPD"],
            objective_gaps=["current walking oxygen saturation"],
            follow_up_reliability="uncertain",
            caregiver_status="unknown",
        ),
    )

    report = engine.evaluate(case)

    assert report.state == "LOWER_ACUITY_BLOCKED"
    assert "LOW_OXYGEN_SATURATION:90" in report.hard_blockers
    assert "LOWER_ACUITY_DESTINATION_WITHOUT_CONFIRMED_FOLLOW_UP" in report.capability_gaps
    assert report.trace_summary["active_patch_count"] >= 1
    assert report.memory_suggestions["authority"] == ADVISORY_AUTHORITY
    assert "safe to discharge" not in str(report.to_dict()).lower()


def test_level_of_care_mismatch_flags_missing_telemetry_capability():
    engine = AnyDispositionReviewEngine()
    case = AnyDispositionCase(
        case_id="any-floor-telemetry-gap",
        age=68,
        chief_concern="syncope",
        domain="chest_discomfort",
        proposed_disposition=ProposedDisposition(destination="floor", monitoring_level="routine vitals"),
        destination_capability=DestinationCapability(serial_vitals=True, urgent_reassessment=True, telemetry=False),
        evidence=DecisionTimeEvidence(
            vital_trend={"hr": [92], "sbp": [118]},
            resulted_data={"troponin": 0.02},
            inpatient_only_needs=["telemetry"],
            source_conflicts=["arrhythmia history"],
            follow_up_reliability="confirmed",
            caregiver_status="available",
        ),
    )

    report = engine.evaluate(case)

    assert report.state == "LEVEL_OF_CARE_MISMATCH"
    assert "DESTINATION_CANNOT_PROVIDE_TELEMETRY" in report.capability_gaps
    assert "any-dispo-floor-telemetry-conflict" in report.memory_suggestions["memory_ids"]
    assert report.review_priority > 0


def test_higher_acuity_case_can_emit_admission_benefit_uncertainty_review_signal():
    engine = AnyDispositionReviewEngine()
    case = AnyDispositionCase(
        case_id="any-observation-low-resource-need",
        age=44,
        chief_concern="vomiting improved",
        domain="abdominal_pain",
        proposed_disposition=ProposedDisposition(destination="observation", monitoring_level="serial reassessment"),
        destination_capability=DestinationCapability(
            serial_vitals=True,
            urgent_reassessment=True,
            medication_access=True,
            caregiver_or_staff_support=True,
            confirmed_follow_up=True,
        ),
        evidence=DecisionTimeEvidence(
            vital_trend={"hr": [88], "sbp": [124], "rr": [16], "spo2": [99]},
            resulted_data={"wbc": 8.2},
            response_to_treatment="improved",
            follow_up_reliability="confirmed",
            caregiver_status="available",
        ),
    )

    report = engine.evaluate(case)

    assert report.state == "ADMISSION_BENEFIT_UNCERTAIN"
    assert "NO_DOCUMENTED_INPATIENT_ONLY_NEED" in report.admission_benefit_signals
    assert "FOLLOW_UP_RELIABILITY_CONFIRMED" in report.admission_benefit_signals
    assert report.hard_blockers == []
    assert report.capability_gaps == []
    assert report.authority == ADVISORY_AUTHORITY
    assert "unnecessary admission" not in str(report.to_dict()).lower()


def test_any_dispo_report_serializes_review_artifacts():
    report = AnyDispositionReviewEngine().evaluate(
        AnyDispositionCase(
            case_id="any-serialize",
            age=51,
            chief_concern="medication refill",
            domain="medication_refill",
            proposed_disposition=ProposedDisposition(destination="telehealth"),
            destination_capability=DestinationCapability(confirmed_follow_up=True),
            evidence=DecisionTimeEvidence(
                high_risk_factors=["CKD"],
                objective_gaps=["no current vitals"],
                follow_up_reliability="confirmed",
                caregiver_status="independent",
            ),
        )
    )

    data = report.to_dict()

    assert data["case_id"] == "any-serialize"
    assert data["authority"] == ADVISORY_AUTHORITY
    assert "trace_summary" in data
    assert "memory_suggestions" in data
    assert "signature_keys" in data
