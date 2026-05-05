from jre import (
    ADVISORY_AUTHORITY,
    AnyDispositionCase,
    AnyDispositionReviewEngine,
    BlackSwanGuardrailEngine,
    CaseInput,
    CognitiveBiasFieldEngine,
    DecisionTimeEvidence,
    DestinationCapability,
    JudgmentReadinessEngine,
    PatientContext,
    ProposedDisposition,
    ReasoningIntegrityEngine,
    Statement,
)


def test_jre_bias_entropy_rises_when_reassuring_frame_has_missing_objective_data():
    case = CaseInput(
        case_id="cog-jre-reassuring-missing-objective",
        patient_context=PatientContext(
            age=58,
            chief_concern="chest pressure",
            domain="chest_discomfort",
        ),
        statements=[
            Statement("What is happening?", "It is probably just heartburn, not pain.", concept="symptom_quality"),
            Statement("When does it happen?", "Pressure happens when I walk upstairs.", concept="exertional_component"),
            Statement("Any shortness of breath?", "A little winded but I am fine.", concept="dyspnea"),
        ],
    )
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()
    reasoning = ReasoningIntegrityEngine()
    jre_report = jre.evaluate(case)
    guard_report = guard.evaluate(case, jre_report)
    reasoning_report = reasoning.evaluate(case, jre_report, guard_report)

    report = CognitiveBiasFieldEngine().evaluate_jre(case, jre_report, guard_report, reasoning_report)

    assert report.authority == ADVISORY_AUTHORITY
    assert report.bias_entropy_score >= 50
    assert any(item.bias_id in {"premature_closure", "confirmation_bias", "overconfidence"} for item in report.dominant_biases)
    assert report.hypothesis_survival
    assert report.friction_actions


def test_any_dispo_information_gain_prioritizes_blockers_and_capability_gaps():
    case = AnyDispositionCase(
        case_id="cog-any-home-unstable",
        age=73,
        chief_concern="shortness of breath",
        domain="dyspnea_respiratory",
        proposed_disposition=ProposedDisposition(destination="home", rationale="stable and safe for routine follow-up"),
        destination_capability=DestinationCapability(confirmed_follow_up=False),
        evidence=DecisionTimeEvidence(
            vital_trend={"spo2": [95, 90], "hr": [104, 124]},
            resulted_data={"wbc": 12},
            unresolved_red_flags=["worsening dyspnea"],
            high_risk_factors=["COPD"],
            objective_gaps=["current walking oxygen saturation"],
            follow_up_reliability="uncertain",
            caregiver_status="unknown",
        ),
    )
    any_report = AnyDispositionReviewEngine().evaluate(case)
    report = CognitiveBiasFieldEngine().evaluate_any_dispo(case, any_report)

    assert report.bias_entropy_score >= 65
    assert report.information_gain_candidates[0].yield_class == "high_yield"
    assert report.information_gain_candidates[0].source in {"hard_blocker", "capability_gap"}
    assert any(action.action_id == "require_disconfirming_fact" for action in report.friction_actions)
    assert "safe to discharge" not in str(report.to_dict()).lower()


def test_any_dispo_admission_benefit_uncertainty_remains_review_only():
    case = AnyDispositionCase(
        case_id="cog-any-observation-review",
        age=44,
        chief_concern="vomiting improved",
        domain="abdominal_pain",
        proposed_disposition=ProposedDisposition(destination="observation", rationale="continue current observation pathway"),
        destination_capability=DestinationCapability(
            serial_vitals=True,
            urgent_reassessment=True,
            medication_access=True,
            caregiver_or_staff_support=True,
            confirmed_follow_up=True,
        ),
        evidence=DecisionTimeEvidence(
            vital_trend={"hr": [86], "sbp": [124], "rr": [16], "spo2": [99]},
            resulted_data={"wbc": 8.2},
            response_to_treatment="improved",
            follow_up_reliability="confirmed",
            caregiver_status="available",
        ),
    )
    any_report = AnyDispositionReviewEngine().evaluate(case)
    report = CognitiveBiasFieldEngine().evaluate_any_dispo(case, any_report)

    assert any_report.state == "ADMISSION_BENEFIT_UNCERTAIN"
    assert any(item.branch == "higher_acuity_benefit" and item.status == "uncertain" for item in report.hypothesis_survival)
    assert "unnecessary admission" not in str(report.to_dict()).lower()
    assert "safe to discharge" not in str(report.to_dict()).lower()


def test_disposition_fragility_detects_state_flips_from_small_context_changes():
    case = AnyDispositionCase(
        case_id="cog-any-fragile-home",
        age=51,
        chief_concern="medication refill",
        domain="medication_refill",
        proposed_disposition=ProposedDisposition(destination="home"),
        destination_capability=DestinationCapability(confirmed_follow_up=True),
        evidence=DecisionTimeEvidence(
            vital_trend={"hr": [80], "sbp": [124], "rr": [16], "spo2": [98]},
            resulted_data={"creatinine": 1.0},
            follow_up_reliability="confirmed",
            caregiver_status="independent",
        ),
    )
    any_report = AnyDispositionReviewEngine().evaluate(case)
    report = CognitiveBiasFieldEngine().evaluate_any_dispo(case, any_report)

    assert any_report.state == "NO_REVIEW_SIGNAL"
    assert report.disposition_fragility is not None
    assert report.disposition_fragility.perturbations_tested >= 5
    assert report.disposition_fragility.state_flips >= 1
    assert report.disposition_fragility.fragility_index > 0
    assert any(action.action_id == "preserve_uncertainty" for action in report.friction_actions)


def test_fresh_eyes_payload_hides_proposed_destination_but_preserves_decision_time_facts():
    case = AnyDispositionCase(
        case_id="cog-any-fresh-eyes",
        age=68,
        chief_concern="syncope",
        domain="chest_discomfort",
        proposed_disposition=ProposedDisposition(destination="floor", rationale="routine floor placement"),
        destination_capability=DestinationCapability(serial_vitals=True),
        evidence=DecisionTimeEvidence(
            vital_trend={"hr": [92], "sbp": [118]},
            resulted_data={"troponin": 0.02},
            inpatient_only_needs=["telemetry"],
            source_conflicts=["arrhythmia history"],
            follow_up_reliability="confirmed",
            caregiver_status="available",
        ),
    )
    any_report = AnyDispositionReviewEngine().evaluate(case)
    report = CognitiveBiasFieldEngine().evaluate_any_dispo(case, any_report)

    visible = " ".join(report.fresh_eyes_payload.visible_facts).lower()
    assert "proposed destination" in report.fresh_eyes_payload.hidden_fields
    assert "floor" not in visible
    assert "syncope" in visible
    assert "telemetry" in visible


def test_any_dispo_can_optionally_attach_cognitive_bias_field_payload():
    report = AnyDispositionReviewEngine(include_cognitive_bias_field=True).evaluate(
        AnyDispositionCase(
            case_id="cog-any-attached",
            age=70,
            chief_concern="shortness of breath",
            domain="dyspnea_respiratory",
            proposed_disposition=ProposedDisposition(destination="home"),
            destination_capability=DestinationCapability(confirmed_follow_up=False),
            evidence=DecisionTimeEvidence(
                vital_trend={"spo2": [90]},
                resulted_data={"wbc": 13},
                follow_up_reliability="unknown",
                caregiver_status="unknown",
            ),
        )
    )

    data = report.to_dict()
    assert data["cognitive_bias_field"] is not None
    assert data["cognitive_bias_field"]["authority"] == ADVISORY_AUTHORITY
    assert data["cognitive_bias_field"]["context"] == "any_dispo"
