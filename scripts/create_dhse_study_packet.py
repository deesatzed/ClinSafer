"""Create a reproducible DHSE study packet from a canonical export.

The packet is the handoff from data extraction to analysis. It validates the
input export, runs DHSE, writes full and compact outputs, and records a manifest
with enough provenance to rerun the same benchmark.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jre.disposition_handoff import (  # noqa: E402
    BenchmarkRun,
    DispositionHandoffSufficiencyEngine,
    load_benchmark_cases,
    load_flat_ehr_csv,
)
from scripts.validate_dhse_export import validate_csv  # noqa: E402


DEFAULT_REVIEW_FRACTIONS = (0.05, 0.10, 0.20)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a DHSE retrospective study packet.")
    parser.add_argument("--input", required=True, help="Canonical DHSE CSV or JSONL export.")
    parser.add_argument(
        "--input-format",
        choices=["csv", "jsonl"],
        default="csv",
        help="Input format. CSV is the recommended real-data bridge.",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/dhse_study_packet",
        help="Directory where packet files are written.",
    )
    parser.add_argument(
        "--review-fraction",
        type=float,
        action="append",
        default=None,
        help="Review budget fraction. May be repeated. Defaults to 0.05, 0.10, 0.20.",
    )
    args = parser.parse_args()

    result = create_study_packet(
        input_path=Path(args.input),
        input_format=args.input_format,
        output_dir=Path(args.output_dir),
        review_fractions=args.review_fraction or list(DEFAULT_REVIEW_FRACTIONS),
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


def create_study_packet(
    input_path: Path | str,
    input_format: str,
    output_dir: Path | str,
    review_fractions: Sequence[float] = DEFAULT_REVIEW_FRACTIONS,
) -> Dict[str, Any]:
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    validation = _validate_input(input_path, input_format)
    _write_json(output_dir / "validation.json", validation)
    if not validation["valid"]:
        return {
            "status": "invalid_input",
            "output_dir": str(output_dir),
            "validation": validation,
        }

    fractions = _normalized_review_fractions(review_fractions)
    cases = load_flat_ehr_csv(input_path) if input_format == "csv" else load_benchmark_cases(input_path)
    engine = DispositionHandoffSufficiencyEngine()
    primary_fraction = fractions[0]
    primary_run = engine.run_benchmark_cases(cases, review_fraction=primary_fraction)
    sensitivity = _review_fraction_sensitivity(engine, cases, fractions)

    reports_path = output_dir / "reports.json"
    summary_path = output_dir / "summary.json"
    case_csv_path = output_dir / "case_level.csv"
    manifest_path = output_dir / "run_manifest.json"
    methods_path = output_dir / "METHODS_SNAPSHOT.md"

    _write_json(reports_path, primary_run.to_dict())
    _write_case_csv(case_csv_path, primary_run)

    summary = {
        "input": str(input_path),
        "input_format": input_format,
        "input_sha256": _sha256(input_path),
        "created_at_utc": _utc_now(),
        "primary_review_fraction": primary_fraction,
        "metrics": primary_run.metrics,
        "baseline_metrics": primary_run.baseline_metrics,
        "model_comparison": _model_comparison(primary_run),
        "review_fraction_sensitivity": sensitivity,
        "analysis": primary_run.analysis,
    }
    _write_json(summary_path, summary)

    manifest = _manifest(
        input_path=input_path,
        input_format=input_format,
        output_dir=output_dir,
        review_fractions=fractions,
        validation=validation,
        files=[reports_path, summary_path, case_csv_path, manifest_path, methods_path, output_dir / "validation.json"],
    )
    _write_json(manifest_path, manifest)
    methods_path.write_text(_methods_snapshot(summary, validation), encoding="utf-8")

    return {
        "status": "ok",
        "output_dir": str(output_dir),
        "files": {
            "validation": str(output_dir / "validation.json"),
            "reports": str(reports_path),
            "summary": str(summary_path),
            "case_level": str(case_csv_path),
            "manifest": str(manifest_path),
            "methods_snapshot": str(methods_path),
        },
        "metrics": primary_run.metrics,
    }


def _validate_input(input_path: Path, input_format: str) -> Dict[str, Any]:
    if input_format == "csv":
        return validate_csv(input_path)
    if not input_path.exists():
        return {"valid": False, "errors": [f"file not found: {input_path}"], "warnings": [], "row_count": 0}
    try:
        rows = load_benchmark_cases(input_path)
    except Exception as exc:
        return {"valid": False, "errors": [f"JSONL load failed: {exc}"], "warnings": [], "row_count": 0}
    return {
        "valid": True,
        "errors": [],
        "warnings": ["schema validation is lighter for JSONL than for canonical CSV"],
        "row_count": len(rows),
        "ptr_b_labelable_rows": len(rows),
    }


def _normalized_review_fractions(values: Sequence[float]) -> List[float]:
    out = sorted({round(float(value), 4) for value in values if 0 < float(value) <= 1})
    if not out:
        raise ValueError("at least one review fraction must be in (0, 1]")
    return out


def _review_fraction_sensitivity(
    engine: DispositionHandoffSufficiencyEngine,
    cases,
    fractions: Sequence[float],
) -> List[Dict[str, Any]]:
    rows = []
    for fraction in fractions:
        run = engine.run_benchmark_cases(cases, review_fraction=fraction)
        rows.append({"review_fraction": fraction, **_select_metric_fields(run.metrics)})
    return rows


def _write_case_csv(path: Path, run: BenchmarkRun) -> None:
    fields = [
        "case_id",
        "input_mode",
        "dsi",
        "state",
        "ptr_b",
        "jre_state",
        "guardrail_state",
        "risk_factors",
        "revision_events",
        "burden_events",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for report in run.reports:
            label = report.trajectory_label
            writer.writerow(
                {
                    "case_id": report.case_id,
                    "input_mode": report.input_mode,
                    "dsi": report.dsi,
                    "state": report.state,
                    "ptr_b": label.ptr_b_positive if label else "",
                    "jre_state": report.jre_state,
                    "guardrail_state": report.guardrail_state,
                    "risk_factors": "|".join(report.risk_factors),
                    "revision_events": "|".join(label.revision_events if label else []),
                    "burden_events": "|".join(label.burden_events if label else []),
                }
            )


def _model_comparison(run: BenchmarkRun) -> List[Dict[str, Any]]:
    rows = [{"model": "dhse", **_select_metric_fields(run.metrics)}]
    for name, metrics in run.baseline_metrics.items():
        rows.append({"model": name, **_select_metric_fields(metrics)})
    return sorted(
        rows,
        key=lambda row: (
            row.get("auprc") is not None,
            row.get("auprc") or -1,
            row.get("auroc") or -1,
            row.get("capture_at_review_fraction") or -1,
        ),
        reverse=True,
    )


def _select_metric_fields(metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "auroc": metrics.get("auroc"),
        "auprc": metrics.get("auprc"),
        "top_decile_enrichment": metrics.get("top_decile_enrichment"),
        "capture_at_review_fraction": metrics.get("capture_at_review_fraction"),
    }


def _manifest(
    input_path: Path,
    input_format: str,
    output_dir: Path,
    review_fractions: Sequence[float],
    validation: Dict[str, Any],
    files: Iterable[Path],
) -> Dict[str, Any]:
    existing_files = [path for path in files if path.exists()]
    return {
        "run_id": output_dir.name,
        "created_at_utc": _utc_now(),
        "input_path": str(input_path),
        "input_format": input_format,
        "input_sha256": _sha256(input_path) if input_path.exists() else None,
        "review_fractions": list(review_fractions),
        "validation": validation,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "command_template": (
            "python scripts/create_dhse_study_packet.py "
            "--input <canonical_export.csv> --input-format csv --output-dir <packet_dir>"
        ),
        "artifact_files": {path.name: str(path) for path in existing_files},
    }


def _methods_snapshot(summary: Dict[str, Any], validation: Dict[str, Any]) -> str:
    metrics = summary["metrics"]
    return "\n".join(
        [
            "# DHSE Methods Snapshot",
            "",
            "This packet was generated by `scripts/create_dhse_study_packet.py`.",
            "",
            "## Input Contract",
            "",
            "- Scoring inputs are limited to ED-disposition-time material.",
            "- Discharge and hospital-course fields are used only to derive PTR-B labels.",
            "- Pending inpatient workup is not counted as failure.",
            "- Input modes are preserved as `notes`, `dialogue`, or `hybrid`.",
            "",
            "## Primary Outcome",
            "",
            "PTR-B positive requires at least one objective trajectory revision event and at least one measurable burden event.",
            "",
            "## Primary Predictor",
            "",
            "`risk = 100 - DSI`, where DSI is the Disposition Sufficiency Index.",
            "",
            "DSI is derived from the expert-system clinical uncertainty graph, not from a free-form LLM judgment.",
            "Graph nodes include source reliability priors, expert-defined numeric range bands, uncertainty distributions, dependencies, and action implications.",
            "The current graph also includes game-theory strategic-signal nodes and dynamical boundary-sensitivity fields.",
            "",
            "Implemented graph signal families:",
            "",
            "- missingness and objective-data coverage",
            "- source reliability and semantic uncertainty",
            "- contradiction and remote-unobservable load",
            "- numeric range risk and clinical action pressure",
            "- strategic-signal load from incentive-shaped reliability problems",
            "- boundary sensitivity from near-threshold and coupled-instability dynamics",
            "",
            "## Packet Counts",
            "",
            f"- Rows loaded: {validation.get('row_count')}",
            f"- PTR-B labelable rows: {validation.get('ptr_b_labelable_rows')}",
            f"- Positive labels: {metrics.get('positives')}",
            f"- Negative labels: {metrics.get('negatives')}",
            "",
            "## Primary Metrics",
            "",
            f"- AUROC: {metrics.get('auroc')}",
            f"- AUPRC: {metrics.get('auprc')}",
            f"- Top-decile enrichment: {metrics.get('top_decile_enrichment')}",
            f"- Capture at review fraction: {metrics.get('capture_at_review_fraction')}",
            "",
            "Synthetic or pilot packets are engineering artifacts, not clinical validation claims.",
            "",
        ]
    )


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
