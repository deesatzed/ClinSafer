"""Run the Disposition Handoff Sufficiency Benchmark fixture.

The script is dependency-free and works with the synthetic JSONL fixture or a
real EHR-derived JSONL file that follows docs/DHSE_BENCHMARK_SPEC.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jre.disposition_handoff import DispositionHandoffSufficiencyEngine, load_benchmark_cases, load_flat_ehr_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DHSE benchmark cases.")
    parser.add_argument(
        "--input",
        default="data/dhse_synthetic_benchmark.jsonl",
        help="Path to DHSE benchmark JSONL.",
    )
    parser.add_argument(
        "--input-format",
        choices=["jsonl", "csv"],
        default="jsonl",
        help="Input format. CSV expects the canonical flat export columns.",
    )
    parser.add_argument(
        "--review-fraction",
        type=float,
        default=0.10,
        help="Fraction of lowest-DSI cases assumed available for review.",
    )
    parser.add_argument(
        "--reports-json",
        default="",
        help="Optional path for full report JSON output.",
    )
    parser.add_argument(
        "--summary-json",
        default="",
        help="Optional path for compact summary JSON output.",
    )
    parser.add_argument(
        "--case-csv",
        default="",
        help="Optional path for per-case compact CSV output.",
    )
    args = parser.parse_args()

    cases = load_flat_ehr_csv(args.input) if args.input_format == "csv" else load_benchmark_cases(args.input)
    run = DispositionHandoffSufficiencyEngine().run_benchmark_cases(
        cases,
        review_fraction=args.review_fraction,
    )

    summary = {
        "input": args.input,
        "input_format": args.input_format,
        "metrics": run.metrics,
        "baseline_metrics": run.baseline_metrics,
        "model_comparison": _model_comparison(run),
        "analysis": run.analysis,
        "case_summary": [
            {
                "case_id": report.case_id,
                "input_mode": report.input_mode,
                "dsi": report.dsi,
                "state": report.state,
                "ptr_b": report.trajectory_label.ptr_b_positive if report.trajectory_label else None,
                "risk_factors": report.risk_factors,
            }
            for report in run.reports
        ],
    }
    print(json.dumps(summary, indent=2))

    if args.reports_json:
        Path(args.reports_json).write_text(json.dumps(run.to_dict(), indent=2), encoding="utf-8")
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.case_csv:
        _write_case_csv(Path(args.case_csv), run)
    return 0


def _write_case_csv(path: Path, run) -> None:
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


def _model_comparison(run):
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


def _select_metric_fields(metrics):
    return {
        "auroc": metrics.get("auroc"),
        "auprc": metrics.get("auprc"),
        "top_decile_enrichment": metrics.get("top_decile_enrichment"),
        "capture_at_review_fraction": metrics.get("capture_at_review_fraction"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
