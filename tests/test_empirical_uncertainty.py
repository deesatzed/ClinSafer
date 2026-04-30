import csv
import json

from jre import (
    DispositionHandoffSufficiencyEngine,
    EMPIRICAL_FEATURE_CONTRACT_VERSION,
    empirical_feature_contract,
    feature_rows_from_run,
    load_benchmark_cases,
    positive_recall_floor_threshold,
    review_budget_curve,
    write_feature_csv,
)
from scripts.export_dhse_empirical_features import export_features


def _synthetic_run():
    cases = load_benchmark_cases("data/dhse_synthetic_benchmark.jsonl")
    return DispositionHandoffSufficiencyEngine().run_benchmark_cases(cases, review_fraction=0.5)


def test_empirical_feature_rows_are_tabpfn_ready_without_free_text():
    run = _synthetic_run()
    rows = feature_rows_from_run(run)
    contract = empirical_feature_contract()

    assert contract["contract_version"] == EMPIRICAL_FEATURE_CONTRACT_VERSION
    assert len(rows) == 6
    assert "ptr_b" in rows[0]
    assert "risk_score" in rows[0]
    assert "graph_action_pressure" in rows[0]
    assert "case_id" in contract["excluded_from_model_columns"]
    assert "ptr_b" in contract["excluded_from_model_columns"]

    forbidden_substrings = ["note", "diagnosis", "dialogue", "evidence", "answer", "question"]
    feature_names = " ".join(contract["feature_columns"]).lower()
    for substring in forbidden_substrings:
        assert substring not in feature_names


def test_review_budget_curve_and_recall_floor_are_computed():
    rows = feature_rows_from_run(_synthetic_run())

    curve = review_budget_curve(rows, review_fractions=[0.5, 1.0])
    threshold = positive_recall_floor_threshold(rows, miss_rate=0.10)

    assert curve[0]["review_fraction"] == 0.5
    assert curve[0]["positives"] == 3
    assert curve[0]["capture"] is not None
    assert threshold["threshold"] is not None
    assert threshold["positive_count"] == 3


def test_write_feature_csv_round_trips_header(tmp_path):
    rows = feature_rows_from_run(_synthetic_run())
    out_path = tmp_path / "features.csv"

    write_feature_csv(out_path, rows)

    with out_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        loaded = list(reader)
    assert len(loaded) == len(rows)
    assert reader.fieldnames[0] == "case_id"
    assert "ptr_b" in reader.fieldnames
    assert "graph_readiness_index" in reader.fieldnames


def test_export_dhse_empirical_features_manifest(tmp_path):
    output_csv = tmp_path / "features.csv"
    manifest_json = tmp_path / "manifest.json"

    manifest = export_features(
        input_path="data/dhse_synthetic_benchmark.jsonl",
        input_format="jsonl",
        output_csv=output_csv,
        manifest_json=manifest_json,
        review_fraction=0.5,
    )

    assert output_csv.exists()
    assert manifest_json.exists()
    persisted = json.loads(manifest_json.read_text(encoding="utf-8"))
    assert persisted == manifest
    assert manifest["status"] == "ok"
    assert manifest["feature_contract"]["contract_version"] == EMPIRICAL_FEATURE_CONTRACT_VERSION
    assert manifest["tabpfn_notes"]["target"] == "ptr_b"
