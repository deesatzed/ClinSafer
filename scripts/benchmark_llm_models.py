"""Benchmark OpenRouter LLM latency on fixed demo cases.

Usage:
    python scripts/benchmark_llm_models.py
    python scripts/benchmark_llm_models.py --models deepseek/deepseek-v4-pro qwen/qwen3.6-flash --runs 2
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jre.black_swan import BLACK_SWAN_CASES
from jre.llm_augment import LLMDetector
from jre.synthetic_data import BASE_CASES


DEFAULT_CASE_IDS = [
    "showcase-001-stale-ace-refill-ckd-nsaid",
    "CP-001-heartburn-pressure",
    "RF-002-good-refill-readyish",
]


def _case_index() -> dict[str, Any]:
    return {case.case_id: case for case in list(BASE_CASES) + list(BLACK_SWAN_CASES)}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[idx]


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for model in sorted({row["model"] for row in rows}):
        model_rows = [row for row in rows if row["model"] == model]
        successes = [row for row in model_rows if row["success"]]
        latencies = [row["latency_ms"] for row in successes]
        summaries.append(
            {
                "model": model,
                "runs": len(model_rows),
                "successes": len(successes),
                "errors": len(model_rows) - len(successes),
                "mean_ms": round(statistics.mean(latencies), 1) if latencies else None,
                "median_ms": round(statistics.median(latencies), 1) if latencies else None,
                "p90_ms": round(_percentile(latencies, 0.9), 1) if latencies else None,
                "min_ms": round(min(latencies), 1) if latencies else None,
                "max_ms": round(max(latencies), 1) if latencies else None,
                "avg_findings": round(
                    statistics.mean([row["finding_count"] for row in successes]), 2
                )
                if successes
                else None,
            }
        )
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["deepseek/deepseek-v4-pro", "qwen/qwen3.6-flash"],
        help="OpenRouter model IDs to benchmark.",
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        default=DEFAULT_CASE_IDS,
        help="Built-in case IDs to benchmark.",
    )
    parser.add_argument("--runs", type=int, default=1, help="Runs per model/case.")
    parser.add_argument("--timeout", type=int, default=90, help="Per-request timeout seconds.")
    parser.add_argument(
        "--json-out",
        default="artifacts/llm_latency_benchmark.json",
        help="Where to write machine-readable results.",
    )
    args = parser.parse_args()

    cases = _case_index()
    missing = [case_id for case_id in args.cases if case_id not in cases]
    if missing:
        raise SystemExit(f"Unknown case id(s): {', '.join(missing)}")

    rows: list[dict[str, Any]] = []
    for model in args.models:
        detector = LLMDetector(model=model, timeout=args.timeout)
        if not detector.available:
            raise SystemExit("OPENROUTER_API_KEY is not configured.")
        for run_idx in range(args.runs):
            for case_id in args.cases:
                case = cases[case_id]
                start = time.perf_counter()
                result = detector.analyze_case(case)
                latency_ms = (time.perf_counter() - start) * 1000
                row = {
                    "model": model,
                    "case_id": case_id,
                    "run": run_idx + 1,
                    "latency_ms": round(latency_ms, 1),
                    "success": result.success,
                    "error": result.error,
                    "finding_count": len(result.findings),
                    "findings": [asdict(f) for f in result.findings],
                    "raw_preview": result.raw_response[:500],
                }
                rows.append(row)
                status = "ok" if result.success else f"error={result.error}"
                print(
                    f"{model} | {case_id} | run {run_idx + 1} | "
                    f"{latency_ms:.0f} ms | {len(result.findings)} findings | {status}"
                )

    payload = {"rows": rows, "summary": _summarize(rows)}
    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))

    print("\nSummary")
    for item in payload["summary"]:
        print(
            f"{item['model']}: successes {item['successes']}/{item['runs']}, "
            f"median={item['median_ms']} ms, mean={item['mean_ms']} ms, "
            f"p90={item['p90_ms']} ms, avg_findings={item['avg_findings']}"
        )
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
