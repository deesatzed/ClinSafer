"""CLI demo for the Judgment Readiness Engine.

Run:
    python demo.py --case CP-001-heartburn-pressure
    python demo.py --all
    python demo.py --html artifacts/provider_dashboard_sample.html
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import List

from jre import JudgmentReadinessEngine, report_to_markdown
from jre.synthetic_data import generate_cases, write_dataset, case_to_dict


def make_html(reports) -> str:
    cards = []
    for r in reports:
        qs = "".join(f"<li><b>{html.escape(q.concept)}</b>: {html.escape(q.question)}<br><small>{html.escape(q.clear_step)}</small></li>" for q in r.next_questions[:4])
        bmap = "".join(
            f"<h4>{html.escape(k.replace('_',' ').title())}</h4><ul>" + "".join(f"<li>{html.escape(v)}</li>" for v in vals[:5]) + "</ul>"
            for k, vals in r.boundary_map.items()
        )
        findings = "".join(f"<tr><td>{html.escape(f.category)}</td><td>{html.escape(f.concept)}</td><td>{f.severity:.2f}</td><td>{html.escape(f.reason)}</td></tr>" for f in r.findings[:8])
        cards.append(f"""
        <section class="card state-{html.escape(r.state.lower())}">
          <div class="topline"><span class="case">{html.escape(r.case_id)}</span><span class="state">{html.escape(r.state)}</span><span class="score">JRI {r.scores.readiness_index:.1f}/100</span></div>
          <p class="summary">{html.escape(r.provider_summary)}</p>
          <div class="grid"><div><h3>Boundary Map</h3>{bmap}</div><div><h3>Next Best Questions</h3><ol>{qs}</ol></div></div>
          <h3>Top Findings</h3><table><thead><tr><th>Category</th><th>Concept</th><th>Severity</th><th>Reason</th></tr></thead><tbody>{findings}</tbody></table>
        </section>
        """)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Judgment Readiness Demo Dashboard</title>
<style>
body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 32px; background: #f7f7f8; color: #111; }}
h1 {{ margin-bottom: 0; }} .subtitle {{ color: #555; margin-top: 4px; }}
.card {{ background: white; border: 1px solid #ddd; border-radius: 14px; padding: 20px; margin: 18px 0; box-shadow: 0 1px 4px rgba(0,0,0,.05); }}
.topline {{ display: flex; gap: 12px; align-items: center; font-weight: 700; }}
.case {{ font-size: 1.1rem; flex: 1; }} .state, .score {{ border: 1px solid #bbb; padding: 4px 8px; border-radius: 999px; background: #fafafa; }}
.summary {{ color: #333; line-height: 1.45; }} .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }}
h3 {{ margin-bottom: 6px; }} h4 {{ margin: 10px 0 4px; }} ul, ol {{ margin-top: 4px; }} li {{ margin-bottom: 4px; }}
table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }} th, td {{ border-top: 1px solid #e5e5e5; padding: 8px; text-align: left; vertical-align: top; }}
.state-escalate {{ border-left: 8px solid #a33; }} .state-need_objective_data {{ border-left: 8px solid #b70; }} .state-clarify {{ border-left: 8px solid #777; }} .state-ready {{ border-left: 8px solid #287; }}
</style></head><body>
<h1>Judgment Readiness / Unknowns Intelligence Demo</h1>
<p class="subtitle">Synthetic cases. Demonstrates MUD → CLEAR, uncertainty-qualified JST, and provider-facing boundary maps.</p>
{''.join(cards)}
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="Case ID to run")
    parser.add_argument("--all", action="store_true", help="Run all base + synthetic cases")
    parser.add_argument("--n", type=int, default=24, help="Number of synthetic cases to generate")
    parser.add_argument("--dataset-dir", default="data", help="Where to write synthetic data")
    parser.add_argument("--html", help="Write HTML provider dashboard")
    parser.add_argument("--json", help="Write JSON reports")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    cases = write_dataset(base_dir / args.dataset_dir, n=args.n)
    if args.case:
        cases = [c for c in cases if c.case_id == args.case]
        if not cases:
            raise SystemExit(f"Case not found: {args.case}")
    elif not args.all:
        cases = cases[:6]

    engine = JudgmentReadinessEngine()
    reports = [engine.evaluate(c) for c in cases]

    for report in reports[:6 if args.all else len(reports)]:
        print(report_to_markdown(report))
        print("\n" + "=" * 90 + "\n")

    if args.html:
        out = base_dir / args.html
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(make_html(reports), encoding="utf-8")
        print(f"Wrote HTML dashboard: {out}")

    if args.json:
        out = base_dir / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([r.to_dict() for r in reports], indent=2), encoding="utf-8")
        print(f"Wrote JSON reports: {out}")


if __name__ == "__main__":
    main()
