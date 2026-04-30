"""Empirical uncertainty features for DHSE.

This layer turns deterministic DHSE/JRE/BSG reports into a stable tabular
feature contract. It is intentionally model-agnostic: logistic regression,
gradient boosting, TabPFN, conformal wrappers, and review-budget policies can
all consume the same rows.

The export avoids raw notes, diagnoses, dialogue text, or evidence snippets.
It is designed for retrospective risk modeling of PTR-B, not clinical
authorization.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .black_swan import AssumptionStatus
from .disposition_handoff import BenchmarkRun, DispositionSufficiencyReport


EMPIRICAL_FEATURE_CONTRACT_VERSION = "DHSE-EMPIRICAL-v0.1"

STATE_CODE = {
    "SUFFICIENT": 0,
    "READY": 0,
    "ALLOW_WITH_AUDIT": 0,
    "CLARIFY": 1,
    "UNDER_SPECIFIED": 2,
    "NEED_OBJECTIVE_DATA": 3,
    "DIAGNOSTIC_PIVOT_RISK": 4,
    "HOLD_AND_VERIFY": 5,
    "ROUTE_CLINICIAN": 6,
    "ACUITY_MISMATCH_RISK": 7,
    "FAIL_CLOSED": 8,
    "ESCALATE": 9,
}

GRAPH_SUMMARY_FEATURES = [
    "node_count",
    "observed_nodes",
    "completeness",
    "reliability",
    "objective_coverage",
    "missing_load",
    "semantic_uncertainty_load",
    "contradiction_load",
    "range_risk_load",
    "criticality_load",
    "strategic_signal_load",
    "boundary_fragility_load",
    "boundary_flip_load",
    "coupled_instability_load",
    "boundary_sensitivity_index",
    "remote_unknowable_load",
    "action_pressure",
    "graph_readiness_index",
]

GRAPH_FEATURE_COLUMN_NAMES = {
    name: name if name.startswith("graph_") else f"graph_{name}"
    for name in GRAPH_SUMMARY_FEATURES
}

EMPIRICAL_FEATURE_COLUMNS = [
    "case_id",
    "ptr_b",
    "risk_score",
    "dsi",
    "input_mode_code",
    "dhse_state_code",
    "jre_state_code",
    "guardrail_state_code",
    "jre_completeness",
    "jre_reliability",
    "jre_objective_coverage",
    "jre_contradiction_load",
    "jre_distortion_load",
    "jre_red_flag_load",
    "jre_readiness_index",
    "guardrail_novelty_score",
    "guardrail_residual_risk_budget",
    "guardrail_finding_count",
    "assumption_ok_count",
    "assumption_weak_count",
    "assumption_breached_count",
    "risk_factor_count",
    "protective_factor_count",
    "input_limitation_count",
    *[GRAPH_FEATURE_COLUMN_NAMES[name] for name in GRAPH_SUMMARY_FEATURES],
    "graph_breached_node_count",
    "graph_weak_node_count",
    "graph_fragile_node_count",
    "graph_strategic_signal_count",
]

MODEL_EXCLUDED_COLUMNS = {"case_id", "ptr_b"}
MODEL_FEATURE_COLUMNS = [column for column in EMPIRICAL_FEATURE_COLUMNS if column not in MODEL_EXCLUDED_COLUMNS]


def empirical_feature_contract() -> Dict[str, Any]:
    return {
        "contract_version": EMPIRICAL_FEATURE_CONTRACT_VERSION,
        "label_column": "ptr_b",
        "risk_score_column": "risk_score",
        "excluded_from_model_columns": sorted(MODEL_EXCLUDED_COLUMNS),
        "feature_columns": list(MODEL_FEATURE_COLUMNS),
        "all_columns": list(EMPIRICAL_FEATURE_COLUMNS),
        "privacy_boundary": "No raw notes, diagnosis text, dialogue text, evidence snippets, or patient identifiers beyond case_id.",
        "intended_models": [
            "calibrated_logistic_regression",
            "gradient_boosted_trees",
            "balanced_random_forest",
            "TabPFN",
            "TabPFN_HPO",
            "selective_or_conformal_wrapper",
        ],
    }


def feature_rows_from_run(run: BenchmarkRun) -> List[Dict[str, Any]]:
    return feature_rows_from_reports(run.reports)


def feature_rows_from_reports(reports: Sequence[DispositionSufficiencyReport]) -> List[Dict[str, Any]]:
    return [feature_row_from_report(report) for report in reports]


def feature_row_from_report(report: DispositionSufficiencyReport) -> Dict[str, Any]:
    scores = report.jre_report.scores
    graph_summary = (report.jre_report.uncertainty_graph or {}).get("summary", {})
    assumption_counts = _assumption_counts(report.guardrail_report.assumption_register)
    row: Dict[str, Any] = {
        "case_id": report.case_id,
        "ptr_b": _label_value(report),
        "risk_score": round(100.0 - float(report.dsi), 4),
        "dsi": report.dsi,
        "input_mode_code": _input_mode_code(report.input_mode),
        "dhse_state_code": _state_code(report.state),
        "jre_state_code": _state_code(report.jre_state),
        "guardrail_state_code": _state_code(report.guardrail_state),
        "jre_completeness": scores.completeness,
        "jre_reliability": scores.reliability,
        "jre_objective_coverage": scores.objective_coverage,
        "jre_contradiction_load": scores.contradiction_load,
        "jre_distortion_load": scores.distortion_load,
        "jre_red_flag_load": scores.red_flag_load,
        "jre_readiness_index": scores.readiness_index,
        "guardrail_novelty_score": report.guardrail_report.novelty_score,
        "guardrail_residual_risk_budget": report.guardrail_report.residual_risk_budget,
        "guardrail_finding_count": len(report.guardrail_report.findings),
        "assumption_ok_count": assumption_counts["ok"],
        "assumption_weak_count": assumption_counts["weak"],
        "assumption_breached_count": assumption_counts["breached"],
        "risk_factor_count": len(report.risk_factors),
        "protective_factor_count": len(report.protective_factors),
        "input_limitation_count": len(report.input_limitations),
        "graph_breached_node_count": len(graph_summary.get("breached_nodes", []) or []),
        "graph_weak_node_count": len(graph_summary.get("weak_nodes", []) or []),
        "graph_fragile_node_count": len(graph_summary.get("fragile_nodes", []) or []),
        "graph_strategic_signal_count": len(graph_summary.get("strategic_signals", []) or []),
    }
    for name in GRAPH_SUMMARY_FEATURES:
        row[GRAPH_FEATURE_COLUMN_NAMES[name]] = graph_summary.get(name, 0)
    return {column: row.get(column, "") for column in EMPIRICAL_FEATURE_COLUMNS}


def write_feature_csv(path: Path | str, rows: Sequence[Dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EMPIRICAL_FEATURE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in EMPIRICAL_FEATURE_COLUMNS})


def review_budget_curve(
    rows: Sequence[Dict[str, Any]],
    review_fractions: Sequence[float] = (0.05, 0.10, 0.20, 0.50),
    risk_column: str = "risk_score",
    label_column: str = "ptr_b",
) -> List[Dict[str, Any]]:
    labeled = [row for row in rows if row.get(label_column) not in {"", None}]
    positives = sum(1 for row in labeled if _as_bool(row.get(label_column)))
    ordered = sorted(labeled, key=lambda row: float(row.get(risk_column, 0) or 0), reverse=True)
    out: List[Dict[str, Any]] = []
    for fraction in review_fractions:
        if not labeled or fraction <= 0:
            k = 0
        else:
            k = max(1, int(round(len(labeled) * min(1.0, fraction))))
        reviewed = ordered[:k]
        captured = sum(1 for row in reviewed if _as_bool(row.get(label_column)))
        out.append(
            {
                "review_fraction": fraction,
                "reviewed": k,
                "positives": positives,
                "captured_positives": captured,
                "capture": round(captured / positives, 4) if positives else None,
                "precision": round(captured / k, 4) if k else None,
            }
        )
    return out


def positive_recall_floor_threshold(
    rows: Sequence[Dict[str, Any]],
    miss_rate: float = 0.10,
    risk_column: str = "risk_score",
    label_column: str = "ptr_b",
) -> Dict[str, Any]:
    """Empirical threshold that reviews at least 1 - miss_rate of positives.

    This is a simple split-calibration primitive, not a full proof of safety.
    Use it as the first deterministic thresholding object before adding a
    formal conformal risk-control implementation around model probabilities.
    """

    positive_scores = sorted(
        [float(row.get(risk_column, 0) or 0) for row in rows if _as_bool(row.get(label_column))],
        reverse=True,
    )
    if not positive_scores:
        return {
            "threshold": None,
            "target_recall": round(1.0 - miss_rate, 4),
            "positive_count": 0,
            "rule": "no positive calibration cases available",
        }
    target_recall = max(0.0, min(1.0, 1.0 - miss_rate))
    index = min(len(positive_scores) - 1, max(0, int(round(len(positive_scores) * target_recall)) - 1))
    threshold = positive_scores[index]
    return {
        "threshold": round(threshold, 4),
        "target_recall": round(target_recall, 4),
        "positive_count": len(positive_scores),
        "rule": f"review cases with {risk_column} >= threshold",
    }


def _assumption_counts(assumptions: Iterable[AssumptionStatus]) -> Dict[str, int]:
    counts = {"ok": 0, "weak": 0, "breached": 0}
    for assumption in assumptions:
        if assumption.status in counts:
            counts[assumption.status] += 1
    return counts


def _label_value(report: DispositionSufficiencyReport) -> str | int:
    if report.trajectory_label is None:
        return ""
    return int(report.trajectory_label.ptr_b_positive)


def _state_code(state: str) -> int:
    return STATE_CODE.get(state, 5)


def _input_mode_code(mode: str) -> int:
    return {"notes": 0, "dialogue": 1, "hybrid": 2}.get(mode, 3)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}
