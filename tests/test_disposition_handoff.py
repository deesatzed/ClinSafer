import csv
import json

from jre import (
    DHSE_CONTRACT_VERSION,
    DispositionHandoffSufficiencyEngine,
    DispositionSnapshot,
    PostDischargeTrajectory,
    Statement,
    load_benchmark_cases,
    load_flat_ehr_csv,
)
from scripts.create_dhse_study_packet import create_study_packet
from scripts.validate_dhse_export import validate_csv


def test_notes_snapshot_flags_acuity_mismatch_from_ed_available_data():
    engine = DispositionHandoffSufficiencyEngine()
    snapshot = DispositionSnapshot(
        case_id="dhse-notes-unstable-floor",
        input_mode="notes",
        age=72,
        chief_concern="shortness of breath",
        domain="dyspnea_respiratory",
        disposition_diagnosis="weakness and pneumonia",
        admission_service="medicine",
        level_of_care="floor",
        ed_note="Admit to floor. Patient is weak with pneumonia. No ICU needs documented.",
        key_pmh=["COPD", "heart failure"],
        ed_results={"lactate": 3.1, "wbc": 21.0},
        vital_trend={"spo2": [96, 91, 88], "hr": [102, 121], "rr": [20, 28], "sbp": [118, 104]},
        treatments=["vancomycin and cefepime", "oxygen by nonrebreather"],
    )

    report = engine.evaluate_snapshot(snapshot)

    assert report.input_mode == "notes"
    assert report.state == "ACUITY_MISMATCH_RISK"
    assert report.dsi < 75
    assert "FLOOR_DISPOSITION_WITH_OBJECTIVE_INSTABILITY" in report.risk_factors


def test_dialogue_snapshot_keeps_dialogue_mode_and_limitations():
    engine = DispositionHandoffSufficiencyEngine()
    snapshot = DispositionSnapshot(
        case_id="dhse-dialogue-current",
        input_mode="dialogue",
        age=58,
        chief_concern="breathing problem",
        domain="dyspnea_respiratory",
        disposition_diagnosis="COPD exacerbation",
        admission_service="medicine",
        level_of_care="floor",
        key_pmh=["COPD"],
        ed_results={"spo2": 94, "rr": 20, "temperature": 37.2},
        dialogue=[
            Statement("Can you speak full sentences?", "Yes, I can speak a full sentence.", concept="sentence_test"),
            Statement("Can you walk to the kitchen?", "I can walk across the room, worse than baseline but not stopping.", concept="exertional_tolerance"),
            Statement("Are you confused?", "No confusion or sleepiness.", concept="mental_status"),
        ],
    )

    report = engine.evaluate_snapshot(snapshot)

    assert report.input_mode == "dialogue"
    assert any("current elicitation" in item for item in report.input_limitations)
    assert "NO_OBJECTIVE_INSTABILITY_PATTERN_DETECTED" in report.protective_factors


def test_ptr_b_requires_revision_and_burden_not_revision_alone():
    engine = DispositionHandoffSufficiencyEngine()

    revision_only = engine.label_trajectory(
        PostDischargeTrajectory(
            ed_diagnosis_category="symptom",
            discharge_diagnosis_category="infection",
            los_hours=48,
            expected_los_hours=48,
        )
    )
    assert revision_only.ptr_b_positive is False
    assert "DIAGNOSTIC_CATEGORY_REVISION" in revision_only.revision_events
    assert revision_only.burden_events == []

    revision_with_burden = engine.label_trajectory(
        PostDischargeTrajectory(
            ed_diagnosis_category="symptom",
            discharge_diagnosis_category="infection",
            los_hours=120,
            expected_los_hours=48,
            major_therapeutic_pivots=["broad spectrum antibiotics"],
        )
    )
    assert revision_with_burden.ptr_b_positive is True
    assert "RISK_ADJUSTED_LOS_EXCESS" in revision_with_burden.burden_events
    assert any(event.startswith("THERAPEUTIC_PIVOT_") for event in revision_with_burden.revision_events)


def test_retrospective_report_attaches_label_without_using_it_for_snapshot_state():
    engine = DispositionHandoffSufficiencyEngine()
    snapshot = DispositionSnapshot(
        case_id="dhse-retro",
        input_mode="notes",
        age=66,
        chief_concern="dizzy",
        domain="chest_discomfort",
        disposition_diagnosis="dizziness",
        admission_service="medicine",
        level_of_care="floor",
        ed_note="Dizziness, no chest pain. Admit for observation.",
        key_pmh=["diabetes", "CAD"],
        ed_results={"troponin": 0.02, "sbp": 92, "hr": 124},
        vital_trend={"sbp": [130, 110, 92], "hr": [88, 110, 124]},
    )
    trajectory = PostDischargeTrajectory(
        ed_diagnosis_category="symptom",
        discharge_diagnosis_category="cardiac",
        icu_transfer_within_24h=True,
    )

    report = engine.evaluate_retrospective(snapshot, trajectory)

    assert report.trajectory_label is not None
    assert report.trajectory_label.ptr_b_positive is True
    assert report.dsi == engine.evaluate_snapshot(snapshot).dsi


def test_snapshot_score_is_invariant_to_post_discharge_label_mutation():
    engine = DispositionHandoffSufficiencyEngine()
    snapshot = DispositionSnapshot(
        case_id="dhse-label-invariance",
        input_mode="notes",
        age=70,
        chief_concern="weakness",
        domain="dyspnea_respiratory",
        disposition_diagnosis="weakness",
        admission_service="medicine",
        level_of_care="floor",
        ed_note="Weakness, admit to floor. No ICU needs documented.",
        key_pmh=["heart failure"],
        ed_results={"lactate": 3.0},
        vital_trend={"spo2": [94, 89], "hr": [116, 128], "rr": [22, 28]},
    )
    negative = PostDischargeTrajectory(
        ed_diagnosis_category="symptom",
        discharge_diagnosis_category="symptom",
        los_hours=48,
        expected_los_hours=48,
    )
    positive = PostDischargeTrajectory(
        ed_diagnosis_category="symptom",
        discharge_diagnosis_category="sepsis",
        icu_transfer_within_24h=True,
        major_therapeutic_pivots=["pressors"],
    )

    negative_report = engine.evaluate_retrospective(snapshot, negative)
    positive_report = engine.evaluate_retrospective(snapshot, positive)

    assert negative_report.trajectory_label.ptr_b_positive is False
    assert positive_report.trajectory_label.ptr_b_positive is True
    assert negative_report.dsi == positive_report.dsi
    assert negative_report.state == positive_report.state


def test_benchmark_reports_auroc_and_review_capture():
    engine = DispositionHandoffSufficiencyEngine()
    stable = DispositionSnapshot(
        case_id="stable",
        input_mode="notes",
        age=44,
        chief_concern="cellulitis",
        domain="rash",
        disposition_diagnosis="cellulitis",
        admission_service="medicine",
        level_of_care="floor",
        ed_note="Cellulitis without airway symptoms, no mucosal involvement, no skin peeling.",
        ed_results={"temperature": 37.3, "wbc": 10.2},
        vital_trend={"hr": [86], "sbp": [126], "spo2": [98]},
    )
    unstable = DispositionSnapshot(
        case_id="unstable",
        input_mode="notes",
        age=79,
        chief_concern="weak",
        domain="dyspnea_respiratory",
        disposition_diagnosis="weakness",
        admission_service="medicine",
        level_of_care="floor",
        ed_results={"lactate": 4.0},
        vital_trend={"spo2": [89], "rr": [30], "hr": [130]},
        treatments=["cefepime", "oxygen by nonrebreather"],
    )
    reports = [
        engine.evaluate_retrospective(
            stable,
            PostDischargeTrajectory(
                ed_diagnosis_category="skin",
                discharge_diagnosis_category="skin",
                los_hours=48,
                expected_los_hours=48,
            ),
        ),
        engine.evaluate_retrospective(
            unstable,
            PostDischargeTrajectory(
                ed_diagnosis_category="symptom",
                discharge_diagnosis_category="sepsis",
                icu_transfer_within_24h=True,
            ),
        ),
    ]

    metrics = engine.benchmark(reports, review_fraction=0.5)

    assert metrics["n"] == 2
    assert metrics["positives"] == 1
    assert metrics["auroc"] == 1.0
    assert metrics["capture_at_review_fraction"] == 1.0


def test_synthetic_fixture_runs_expected_cases():
    cases = load_benchmark_cases("data/dhse_synthetic_benchmark.jsonl")
    run = DispositionHandoffSufficiencyEngine().run_benchmark_cases(cases, review_fraction=0.5)

    assert len(cases) == 6
    assert run.metrics["n"] == 6
    assert run.metrics["positives"] == 3
    assert run.metrics["auprc"] is not None
    assert "structured_severity" in run.baseline_metrics

    by_id = {report.case_id: report for report in run.reports}
    for case in cases:
        report = by_id[case.snapshot.case_id]
        assert report.trajectory_label.ptr_b_positive is case.expected_ptr_b
        assert report.state == case.expected_state


def test_dialogue_and_notes_modes_score_differently_in_fixture():
    cases = load_benchmark_cases("data/dhse_synthetic_benchmark.jsonl")
    run = DispositionHandoffSufficiencyEngine().run_benchmark_cases(cases, review_fraction=0.5)
    by_id = {report.case_id: report for report in run.reports}

    dialogue = by_id["DHSB-004-dialogue-under-specified"]
    note_only = by_id["DHSB-005-uti-adequate"]

    assert dialogue.input_mode == "dialogue"
    assert note_only.input_mode == "notes"
    assert dialogue.state == "UNDER_SPECIFIED"
    assert note_only.state == "SUFFICIENT"
    assert note_only.dsi > dialogue.dsi


def test_paper_analysis_contains_required_tables():
    cases = load_benchmark_cases("data/dhse_synthetic_benchmark.jsonl")
    run = DispositionHandoffSufficiencyEngine().run_benchmark_cases(cases, review_fraction=0.5)
    analysis = run.analysis

    assert analysis["cohort_flow"]["records_loaded"] == 6
    assert analysis["label_prevalence"]["ptr_b_positive"] == 3
    assert len(analysis["calibration"]) == 5
    assert any(row["dsi_threshold"] == 75 for row in analysis["threshold_table"])
    assert "notes" in analysis["source_mode_stratification"]
    assert "ACUITY_MISMATCH_RISK" in analysis["state_stratification"]
    assert "false_positives" in analysis["error_analysis"]
    assert "false_negatives" in analysis["error_analysis"]


def test_flat_csv_adapter_loads_canonical_export(tmp_path):
    csv_path = tmp_path / "dhse_flat.csv"
    csv_path.write_text(
        "\n".join(
            [
                "case_id,input_mode,age,chief_concern,domain,disposition_diagnosis,admission_service,level_of_care,ed_note,key_pmh,ed_results_json,vital_trend_json,treatments,dialogue_json,ed_los_hours,ed_diagnosis_category,discharge_diagnosis_category,discharge_principal_diagnosis,los_hours,expected_los_hours,icu_transfer_within_24h,stepdown_transfer_within_24h,rapid_response_within_24h,mortality,major_procedure,service_change_due_to_diagnosis,major_therapeutic_pivots,delayed_definitive_therapy_hours,discharge_to_higher_level_of_care,readmission_30d,expected_ptr_b,expected_state,defect_family,notes",
                'CSV-001,notes,72,weakness,dyspnea_respiratory,weakness,medicine,floor,Weakness admit to floor,COPD|heart failure,"{""lactate"": 3.2}","{""spo2"": [94, 89], ""hr"": [110, 130]}","cefepime|oxygen by nonrebreather",[],6.1,symptom,sepsis,sepsis,144,72,true,false,false,false,false,false,pressors,,false,false,true,ACUITY_MISMATCH_RISK,csv_fixture,CSV adapter row',
            ]
        ),
        encoding="utf-8",
    )

    cases = load_flat_ehr_csv(csv_path)
    run = DispositionHandoffSufficiencyEngine().run_benchmark_cases(cases, review_fraction=1.0)

    assert len(cases) == 1
    assert cases[0].snapshot.key_pmh == ["COPD", "heart failure"]
    assert cases[0].trajectory.icu_transfer_within_24h is True
    assert run.reports[0].trajectory_label.ptr_b_positive is True


def test_create_study_packet_writes_reproducible_outputs(tmp_path):
    output_dir = tmp_path / "packet"

    result = create_study_packet(
        input_path="data/sample_dhse_ehr_export.csv",
        input_format="csv",
        output_dir=output_dir,
        review_fractions=[0.5],
    )

    assert result["status"] == "ok"
    assert (output_dir / "validation.json").exists()
    assert (output_dir / "reports.json").exists()
    assert (output_dir / "summary.json").exists()
    assert (output_dir / "case_level.csv").exists()
    assert (output_dir / "run_manifest.json").exists()
    assert (output_dir / "METHODS_SNAPSHOT.md").exists()

    manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["contract_version"] == DHSE_CONTRACT_VERSION
    assert manifest["validation"]["valid"] is True
    assert manifest["validation"]["field_roles"]["counts"]["snapshot_scoring_input"] > 0
    assert manifest["code_provenance"]["git_commit"]
    assert "jre/dhse_contract.py" in manifest["code_provenance"]["code_sha256"]


def test_validator_reports_contract_roles_for_sample_export():
    result = validate_csv("data/sample_dhse_ehr_export.csv")

    assert result["valid"] is True
    assert result["contract_version"] == DHSE_CONTRACT_VERSION
    assert result["field_roles"]["counts"]["snapshot_scoring_input"] > 0
    assert result["field_roles"]["counts"]["post_disposition_label_only"] > 0
    assert result["leakage_risk_columns"] == []


def test_validator_rejects_noncanonical_leakage_columns(tmp_path):
    csv_path = tmp_path / "leaky.csv"
    fields = [
        "case_id",
        "age",
        "chief_concern",
        "domain",
        "disposition_diagnosis",
        "inpatient_note_text",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "case_id": "LEAK-001",
                "age": "71",
                "chief_concern": "weakness",
                "domain": "dyspnea_respiratory",
                "disposition_diagnosis": "weakness",
                "inpatient_note_text": "Later ICU course should not be in snapshot export.",
            }
        )

    result = validate_csv(csv_path)

    assert result["valid"] is False
    assert "inpatient_note_text" in result["leakage_risk_columns"]
    assert any("leakage-risk column" in error for error in result["errors"])


def test_validator_rejects_label_keys_inside_snapshot_metadata(tmp_path):
    csv_path = tmp_path / "metadata_leak.csv"
    fields = [
        "case_id",
        "age",
        "chief_concern",
        "domain",
        "disposition_diagnosis",
        "metadata_json",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "case_id": "LEAK-002",
                "age": "66",
                "chief_concern": "dizziness",
                "domain": "chest_discomfort",
                "disposition_diagnosis": "dizziness",
                "metadata_json": json.dumps({"discharge_diagnosis_category": "cardiac"}),
            }
        )

    result = validate_csv(csv_path)

    assert result["valid"] is False
    assert any("metadata_json contains post-disposition-looking key" in error for error in result["errors"])
