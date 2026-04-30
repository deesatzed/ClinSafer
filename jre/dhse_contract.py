"""DHSE canonical data contract.

This module is the shared source of truth for the flat EHR export consumed by
the Disposition Handoff Sufficiency Engine. The key invariant is temporal:
snapshot fields may contain only ED-disposition-time information; label fields
may contain post-disposition outcomes and must never feed snapshot scoring.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Sequence


CONTRACT_VERSION = "DHSE-CSV-v1.1"

ROLE_SNAPSHOT = "snapshot_scoring_input"
ROLE_BASELINE = "baseline_only"
ROLE_LABEL = "post_disposition_label_only"
ROLE_FIXTURE = "fixture_or_audit_only"


@dataclass(frozen=True)
class DhseColumnSpec:
    name: str
    role: str
    required: bool = False
    value_type: str = "string"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DHSE_COLUMN_SPECS: Sequence[DhseColumnSpec] = (
    DhseColumnSpec("case_id", ROLE_SNAPSHOT, True, "string", "Stable encounter identifier."),
    DhseColumnSpec("input_mode", ROLE_SNAPSHOT, False, "enum", "notes, dialogue, or hybrid."),
    DhseColumnSpec("age", ROLE_SNAPSHOT, True, "number", "Age at ED encounter."),
    DhseColumnSpec("chief_concern", ROLE_SNAPSHOT, True, "string", "ED chief concern or triage reason."),
    DhseColumnSpec("domain", ROLE_SNAPSHOT, True, "enum", "Supported JRE domain."),
    DhseColumnSpec("disposition_diagnosis", ROLE_SNAPSHOT, True, "string", "ED disposition problem representation."),
    DhseColumnSpec("admission_service", ROLE_SNAPSHOT, False, "string", "Admitting service at disposition."),
    DhseColumnSpec("level_of_care", ROLE_SNAPSHOT, False, "string", "Intended care level at disposition."),
    DhseColumnSpec("ed_note", ROLE_SNAPSHOT, False, "string", "ED note text available at or before disposition."),
    DhseColumnSpec("key_pmh", ROLE_SNAPSHOT, False, "pipe_list", "Known PMH before disposition."),
    DhseColumnSpec("ed_results_json", ROLE_SNAPSHOT, False, "json_object", "Resulted ED data before disposition."),
    DhseColumnSpec("vital_trend_json", ROLE_SNAPSHOT, False, "json_object", "Vitals before disposition."),
    DhseColumnSpec("treatments", ROLE_SNAPSHOT, False, "pipe_list", "ED treatments before disposition."),
    DhseColumnSpec("dialogue_json", ROLE_SNAPSHOT, False, "json_list", "Dialogue available before note synthesis."),
    DhseColumnSpec("metadata_json", ROLE_SNAPSHOT, False, "json_object", "Snapshot metadata only."),
    DhseColumnSpec("ed_los_hours", ROLE_BASELINE, False, "number", "ED LOS baseline feature only, not DHSE DSI input."),
    DhseColumnSpec("ed_diagnosis_category", ROLE_LABEL, False, "string", "ED disposition diagnosis category."),
    DhseColumnSpec("discharge_diagnosis_category", ROLE_LABEL, False, "string", "Discharge diagnosis category."),
    DhseColumnSpec("discharge_principal_diagnosis", ROLE_LABEL, False, "string", "Discharge principal diagnosis."),
    DhseColumnSpec("los_hours", ROLE_LABEL, False, "number", "Index hospital length of stay."),
    DhseColumnSpec("expected_los_hours", ROLE_LABEL, False, "number", "Risk-adjusted or DRG expected LOS."),
    DhseColumnSpec("icu_transfer_within_24h", ROLE_LABEL, False, "boolean", "ICU transfer after ED disposition."),
    DhseColumnSpec("stepdown_transfer_within_24h", ROLE_LABEL, False, "boolean", "Stepdown transfer after ED disposition."),
    DhseColumnSpec("rapid_response_within_24h", ROLE_LABEL, False, "boolean", "Rapid response after ED disposition."),
    DhseColumnSpec("mortality", ROLE_LABEL, False, "boolean", "Index hospitalization mortality."),
    DhseColumnSpec("major_procedure", ROLE_LABEL, False, "boolean", "Major procedure after disposition."),
    DhseColumnSpec("service_change_due_to_diagnosis", ROLE_LABEL, False, "boolean", "Service change after diagnostic revision."),
    DhseColumnSpec("major_therapeutic_pivots", ROLE_LABEL, False, "pipe_list", "Post-disposition therapeutic pivots."),
    DhseColumnSpec("delayed_definitive_therapy_hours", ROLE_LABEL, False, "number", "Delay to definitive therapy."),
    DhseColumnSpec("discharge_to_higher_level_of_care", ROLE_LABEL, False, "boolean", "Higher-care discharge disposition."),
    DhseColumnSpec("readmission_30d", ROLE_LABEL, False, "boolean", "Thirty-day readmission."),
    DhseColumnSpec("trajectory_metadata_json", ROLE_LABEL, False, "json_object", "Post-disposition label metadata."),
    DhseColumnSpec("expected_ptr_b", ROLE_FIXTURE, False, "boolean", "Fixture-only expected PTR-B."),
    DhseColumnSpec("expected_state", ROLE_FIXTURE, False, "string", "Fixture-only expected DHSE state."),
    DhseColumnSpec("defect_family", ROLE_FIXTURE, False, "string", "Audit stratum; not used by scoring."),
    DhseColumnSpec("notes", ROLE_FIXTURE, False, "string", "Human audit note; not used by scoring."),
)

COLUMN_SPECS_BY_NAME: Dict[str, DhseColumnSpec] = {spec.name: spec for spec in DHSE_COLUMN_SPECS}
CANONICAL_COLUMNS = tuple(COLUMN_SPECS_BY_NAME)
REQUIRED_COLUMNS = frozenset(spec.name for spec in DHSE_COLUMN_SPECS if spec.required)
SNAPSHOT_COLUMNS = frozenset(spec.name for spec in DHSE_COLUMN_SPECS if spec.role == ROLE_SNAPSHOT)
BASELINE_COLUMNS = frozenset(spec.name for spec in DHSE_COLUMN_SPECS if spec.role == ROLE_BASELINE)
LABEL_COLUMNS = frozenset(spec.name for spec in DHSE_COLUMN_SPECS if spec.role == ROLE_LABEL)
FIXTURE_COLUMNS = frozenset(spec.name for spec in DHSE_COLUMN_SPECS if spec.role == ROLE_FIXTURE)

JSON_OBJECT_COLUMNS = frozenset(spec.name for spec in DHSE_COLUMN_SPECS if spec.value_type == "json_object")
JSON_LIST_COLUMNS = frozenset(spec.name for spec in DHSE_COLUMN_SPECS if spec.value_type == "json_list")
BOOLEAN_COLUMNS = frozenset(spec.name for spec in DHSE_COLUMN_SPECS if spec.value_type == "boolean")
NUMERIC_COLUMNS = frozenset(spec.name for spec in DHSE_COLUMN_SPECS if spec.value_type == "number")

SUPPORTED_INPUT_MODES = {"", "notes", "dialogue", "hybrid"}
BOOLEAN_LITERALS = {"0", "1", "true", "false", "yes", "no", "y", "n", "t", "f"}

LEAKAGE_COLUMN_PATTERNS = (
    "inpatient_note",
    "post_disposition_lab",
    "post_disposition_imaging",
    "post_ed_result",
    "future_result",
    "hospital_course_note",
    "discharge_summary_text",
    "discharge_summary",
    "post_disposition",
    "after_disposition",
    "inpatient_result",
)


def schema_summary() -> Dict[str, Any]:
    """Return a machine-readable contract summary for manifests and docs."""

    return {
        "contract_version": CONTRACT_VERSION,
        "columns": [spec.to_dict() for spec in DHSE_COLUMN_SPECS],
        "required_columns": sorted(REQUIRED_COLUMNS),
        "snapshot_columns": sorted(SNAPSHOT_COLUMNS),
        "baseline_columns": sorted(BASELINE_COLUMNS),
        "label_columns": sorted(LABEL_COLUMNS),
        "fixture_columns": sorted(FIXTURE_COLUMNS),
    }


def field_role_report(fieldnames: Iterable[str]) -> Dict[str, Any]:
    """Summarize a concrete export header against the canonical contract."""

    roles: Dict[str, List[str]] = {
        ROLE_SNAPSHOT: [],
        ROLE_BASELINE: [],
        ROLE_LABEL: [],
        ROLE_FIXTURE: [],
        "unknown": [],
    }
    for field in fieldnames:
        spec = COLUMN_SPECS_BY_NAME.get(field)
        roles[spec.role if spec else "unknown"].append(field)
    return {
        "contract_version": CONTRACT_VERSION,
        "roles": {role: sorted(columns) for role, columns in roles.items()},
        "counts": {role: len(columns) for role, columns in roles.items()},
        "unknown_columns": sorted(roles["unknown"]),
    }


def leakage_risk_columns(fieldnames: Iterable[str]) -> List[str]:
    """Return non-canonical columns whose names look post-disposition-only."""

    out = []
    for field in fieldnames:
        if field in COLUMN_SPECS_BY_NAME:
            continue
        normalized = field.lower()
        if any(pattern in normalized for pattern in LEAKAGE_COLUMN_PATTERNS):
            out.append(field)
    return sorted(out)


def snapshot_json_leakage_paths(value: Any, prefix: str = "") -> List[str]:
    """Return JSON paths that look like labels/outcomes inside snapshot inputs."""

    paths: List[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_str = str(key)
            path = f"{prefix}.{key_str}" if prefix else key_str
            normalized = key_str.lower()
            if key_str in LABEL_COLUMNS or any(pattern in normalized for pattern in LEAKAGE_COLUMN_PATTERNS):
                paths.append(path)
            paths.extend(snapshot_json_leakage_paths(child, path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            paths.extend(snapshot_json_leakage_paths(child, f"{prefix}[{idx}]"))
    return paths


def is_boolean_like(value: Any) -> bool:
    if value in {"", None}:
        return True
    return str(value).strip().lower() in BOOLEAN_LITERALS
