"""Validate a canonical DHSE flat EHR CSV export.

The validator checks schema, parsability, and obvious leakage-risk columns
before benchmark execution. It does not certify clinical correctness.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jre.disposition_handoff import load_flat_ehr_csv
from jre.templates import DOMAIN_TEMPLATES


REQUIRED_COLUMNS = {
    "case_id",
    "age",
    "chief_concern",
    "domain",
    "disposition_diagnosis",
}

JSON_OBJECT_COLUMNS = {
    "ed_results_json",
    "vital_trend_json",
    "metadata_json",
    "trajectory_metadata_json",
}

JSON_LIST_COLUMNS = {
    "dialogue_json",
}

BOOLEAN_COLUMNS = {
    "icu_transfer_within_24h",
    "stepdown_transfer_within_24h",
    "rapid_response_within_24h",
    "mortality",
    "major_procedure",
    "service_change_due_to_diagnosis",
    "discharge_to_higher_level_of_care",
    "readmission_30d",
    "expected_ptr_b",
}

NUMERIC_COLUMNS = {
    "age",
    "ed_los_hours",
    "los_hours",
    "expected_los_hours",
    "delayed_definitive_therapy_hours",
}

SUPPORTED_INPUT_MODES = {"", "notes", "dialogue", "hybrid"}

LEAKAGE_COLUMN_PATTERNS = (
    "inpatient_note",
    "post_disposition_lab",
    "post_disposition_imaging",
    "post_ed_result",
    "future_result",
    "hospital_course_note",
    "discharge_summary_text",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical DHSE flat CSV export.")
    parser.add_argument("csv_path", help="Path to canonical flat DHSE CSV.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    result = validate_csv(Path(args.csv_path))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)
    return 0 if result["valid"] else 1


def validate_csv(path: Path) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    row_count = 0
    ptr_b_labelable = 0

    if not path.exists():
        return {"valid": False, "errors": [f"file not found: {path}"], "warnings": [], "row_count": 0}

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = sorted(REQUIRED_COLUMNS - set(fieldnames))
        if missing:
            errors.append(f"missing required columns: {', '.join(missing)}")

        for column in fieldnames:
            normalized = column.lower()
            if any(pattern in normalized for pattern in LEAKAGE_COLUMN_PATTERNS):
                warnings.append(f"potential leakage-risk column present: {column}")

        seen_case_ids = set()
        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            case_id = row.get("case_id", "").strip()
            if not case_id:
                errors.append(f"row {row_number}: missing case_id")
            elif case_id in seen_case_ids:
                errors.append(f"row {row_number}: duplicate case_id {case_id}")
            seen_case_ids.add(case_id)

            mode = row.get("input_mode", "")
            if mode not in SUPPORTED_INPUT_MODES:
                errors.append(f"row {row_number}: unsupported input_mode {mode!r}")

            domain = row.get("domain", "")
            if domain and domain not in DOMAIN_TEMPLATES:
                errors.append(f"row {row_number}: unsupported domain {domain!r}")

            for column in NUMERIC_COLUMNS:
                value = row.get(column, "")
                if value not in {"", None}:
                    try:
                        float(value)
                    except ValueError:
                        errors.append(f"row {row_number}: {column} is not numeric: {value!r}")

            for column in BOOLEAN_COLUMNS:
                value = row.get(column, "")
                if value not in {"", None} and str(value).strip().lower() not in {"0", "1", "true", "false", "yes", "no", "y", "n", "t", "f"}:
                    errors.append(f"row {row_number}: {column} is not boolean-like: {value!r}")

            for column in JSON_OBJECT_COLUMNS:
                _validate_json(row.get(column, ""), dict, row_number, column, errors)

            for column in JSON_LIST_COLUMNS:
                _validate_json(row.get(column, ""), list, row_number, column, errors)

            if row.get("discharge_diagnosis_category") or row.get("icu_transfer_within_24h") or row.get("los_hours"):
                ptr_b_labelable += 1

    if row_count == 0:
        errors.append("CSV contains no data rows")

    if not errors:
        try:
            load_flat_ehr_csv(path)
        except Exception as exc:
            errors.append(f"adapter load failed: {exc}")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "row_count": row_count,
        "ptr_b_labelable_rows": ptr_b_labelable,
    }


def _validate_json(value: str | None, expected_type: type, row_number: int, column: str, errors: List[str]) -> None:
    if value in {"", None}:
        return
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        errors.append(f"row {row_number}: {column} invalid JSON: {exc.msg}")
        return
    if not isinstance(parsed, expected_type):
        errors.append(f"row {row_number}: {column} must be JSON {expected_type.__name__}")


def _print_human(result: Dict[str, Any]) -> None:
    print(f"valid: {result['valid']}")
    print(f"rows: {result.get('row_count', 0)}")
    print(f"ptr_b_labelable_rows: {result.get('ptr_b_labelable_rows', 0)}")
    for warning in result.get("warnings", []):
        print(f"warning: {warning}")
    for error in result.get("errors", []):
        print(f"error: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
