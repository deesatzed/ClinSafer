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

from jre.dhse_contract import (  # noqa: E402
    BASELINE_COLUMNS,
    BOOLEAN_COLUMNS,
    CONTRACT_VERSION,
    JSON_LIST_COLUMNS,
    JSON_OBJECT_COLUMNS,
    LABEL_COLUMNS,
    NUMERIC_COLUMNS,
    REQUIRED_COLUMNS,
    SNAPSHOT_COLUMNS,
    SUPPORTED_INPUT_MODES,
    field_role_report,
    is_boolean_like,
    leakage_risk_columns,
    schema_summary,
    snapshot_json_leakage_paths,
)
from jre.disposition_handoff import load_flat_ehr_csv
from jre.templates import DOMAIN_TEMPLATES


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical DHSE flat CSV export.")
    parser.add_argument("csv_path", help="Path to canonical flat DHSE CSV.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--allow-leakage-risk-columns",
        action="store_true",
        help="Downgrade non-canonical post-disposition-looking columns to warnings. Use only for mapping audits, not scoring packets.",
    )
    args = parser.parse_args()

    result = validate_csv(Path(args.csv_path), allow_leakage_risk_columns=args.allow_leakage_risk_columns)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)
    return 0 if result["valid"] else 1


def validate_csv(path: Path | str, allow_leakage_risk_columns: bool = False) -> Dict[str, Any]:
    path = Path(path)
    errors: List[str] = []
    warnings: List[str] = []
    row_count = 0
    ptr_b_labelable = 0

    if not path.exists():
        return {
            "valid": False,
            "contract_version": CONTRACT_VERSION,
            "errors": [f"file not found: {path}"],
            "warnings": [],
            "row_count": 0,
        }

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        roles = field_role_report(fieldnames)
        missing = sorted(REQUIRED_COLUMNS - set(fieldnames))
        if missing:
            errors.append(f"missing required columns: {', '.join(missing)}")

        leakage_columns = leakage_risk_columns(fieldnames)
        for column in leakage_columns:
            message = f"non-canonical leakage-risk column present: {column}"
            if allow_leakage_risk_columns:
                warnings.append(message)
            else:
                errors.append(message)

        for column in roles["unknown_columns"]:
            if column not in leakage_columns:
                warnings.append(f"unknown non-canonical column ignored by adapter: {column}")

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
                if not is_boolean_like(value):
                    errors.append(f"row {row_number}: {column} is not boolean-like: {value!r}")

            for column in JSON_OBJECT_COLUMNS:
                parsed = _validate_json(row.get(column, ""), dict, row_number, column, errors)
                if parsed is not None and column in SNAPSHOT_COLUMNS | BASELINE_COLUMNS:
                    leakage_paths = snapshot_json_leakage_paths(parsed)
                    for path_item in leakage_paths:
                        errors.append(f"row {row_number}: {column} contains post-disposition-looking key: {path_item}")

            for column in JSON_LIST_COLUMNS:
                _validate_json(row.get(column, ""), list, row_number, column, errors)

            if any(str(row.get(column, "")).strip() for column in LABEL_COLUMNS if column != "trajectory_metadata_json"):
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
        "contract_version": CONTRACT_VERSION,
        "errors": errors,
        "warnings": warnings,
        "row_count": row_count,
        "ptr_b_labelable_rows": ptr_b_labelable,
        "allow_leakage_risk_columns": allow_leakage_risk_columns,
        "schema": schema_summary(),
        "field_roles": roles if "roles" in locals() else field_role_report([]),
        "leakage_risk_columns": leakage_columns if "leakage_columns" in locals() else [],
    }


def _validate_json(value: str | None, expected_type: type, row_number: int, column: str, errors: List[str]) -> Any:
    if value in {"", None}:
        return None
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        errors.append(f"row {row_number}: {column} invalid JSON: {exc.msg}")
        return None
    if not isinstance(parsed, expected_type):
        errors.append(f"row {row_number}: {column} must be JSON {expected_type.__name__}")
        return None
    return parsed


def _print_human(result: Dict[str, Any]) -> None:
    print(f"contract: {result.get('contract_version')}")
    print(f"valid: {result['valid']}")
    print(f"rows: {result.get('row_count', 0)}")
    print(f"ptr_b_labelable_rows: {result.get('ptr_b_labelable_rows', 0)}")
    roles = result.get("field_roles", {}).get("counts", {})
    if roles:
        print("field_role_counts: " + ", ".join(f"{role}={count}" for role, count in sorted(roles.items())))
    for warning in result.get("warnings", []):
        print(f"warning: {warning}")
    for error in result.get("errors", []):
        print(f"error: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
