"""Export DHSE empirical uncertainty features for downstream modeling."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jre.disposition_handoff import DispositionHandoffSufficiencyEngine, load_benchmark_cases, load_flat_ehr_csv  # noqa: E402
from jre.empirical_uncertainty import (  # noqa: E402
    empirical_feature_contract,
    feature_rows_from_run,
    positive_recall_floor_threshold,
    review_budget_curve,
    write_feature_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export DHSE empirical uncertainty feature rows.")
    parser.add_argument(
        "--input",
        default="data/dhse_synthetic_benchmark.jsonl",
        help="DHSE JSONL benchmark or canonical CSV export.",
    )
    parser.add_argument(
        "--input-format",
        choices=["jsonl", "csv"],
        default="jsonl",
        help="Input format.",
    )
    parser.add_argument(
        "--output-csv",
        default="artifacts/dhse_empirical_features.csv",
        help="Feature CSV path.",
    )
    parser.add_argument(
        "--manifest-json",
        default="artifacts/dhse_empirical_features_manifest.json",
        help="Feature manifest path.",
    )
    parser.add_argument(
        "--review-fraction",
        type=float,
        default=0.10,
        help="Primary review fraction used for DHSE benchmark metrics.",
    )
    args = parser.parse_args()

    manifest = export_features(
        input_path=Path(args.input),
        input_format=args.input_format,
        output_csv=Path(args.output_csv),
        manifest_json=Path(args.manifest_json),
        review_fraction=args.review_fraction,
    )
    print(json.dumps(manifest, indent=2))
    return 0


def export_features(
    input_path: Path | str,
    input_format: str,
    output_csv: Path | str,
    manifest_json: Path | str,
    review_fraction: float = 0.10,
) -> Dict[str, Any]:
    input_path = Path(input_path)
    output_csv = Path(output_csv)
    manifest_json = Path(manifest_json)
    cases = load_flat_ehr_csv(input_path) if input_format == "csv" else load_benchmark_cases(input_path)
    run = DispositionHandoffSufficiencyEngine().run_benchmark_cases(cases, review_fraction=review_fraction)
    rows = feature_rows_from_run(run)
    write_feature_csv(output_csv, rows)
    manifest = _manifest(input_path, input_format, output_csv, rows, review_fraction)
    manifest_json.parent.mkdir(parents=True, exist_ok=True)
    manifest_json.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _manifest(
    input_path: Path,
    input_format: str,
    output_csv: Path,
    rows: Sequence[Dict[str, Any]],
    review_fraction: float,
) -> Dict[str, Any]:
    contract = empirical_feature_contract()
    return {
        "status": "ok",
        "input": str(input_path),
        "input_format": input_format,
        "output_csv": str(output_csv),
        "row_count": len(rows),
        "review_fraction": review_fraction,
        "feature_contract": contract,
        "review_budget_curve": review_budget_curve(rows),
        "positive_recall_floor_threshold": positive_recall_floor_threshold(rows),
        "tabpfn_notes": {
            "target": contract["label_column"],
            "exclude_columns": contract["excluded_from_model_columns"],
            "recommended_first_pass": "Run baseline TabPFN/GBDT/logistic models on the exported feature columns, then calibrate or wrap with selective/conformal thresholds.",
            "secret_handling": "Set TABPFN_API_KEY in the environment or secret manager; never commit it.",
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
