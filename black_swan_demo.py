"""CLI demo for the Black Swan Guardrail Layer.

Run:
    python black_swan_demo.py --case BS-003-offpath-stroke-in-refill
    python black_swan_demo.py --all --html artifacts/black_swan_dashboard.html
"""
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path

from jre import JudgmentReadinessEngine, BlackSwanGuardrailEngine, BLACK_SWAN_CASES, guardrail_report_to_markdown
from jre.synthetic_data import BASE_CASES, write_dataset


def make_html(items) -> str:
    cards = []
    for case, jre_report, guard_report in items:
        findings = "".join(
            f"<tr><td>{html.escape(f.rule_id)}</td><td>{html.escape(f.category)}</td><td>{f.severity:.2f}</td><td>{html.escape(f.control)}</td></tr>"
            for f in guard_report.findings[:8]
        ) or "<tr><td colspan='4'>No hard guardrail triggers</td></tr>"
        assumptions = "".join(
            f"<li><b>{html.escape(a.status.upper())}</b> — {html.escape(a.name)}: {html.escape(a.reason)}</li>"
            for a in guard_report.assumption_register
        )
        case_rows = "".join(
            f"<li><b>{html.escape(s.question)}</b><br>{html.escape(s.answer)}</li>"
            for s in case.statements
        )
        cards.append(f"""
        <section class="card state-{html.escape(guard_report.guardrail_state.lower())}">
          <div class="topline"><span class="case">{html.escape(case.case_id)}</span><span class="state">{html.escape(guard_report.guardrail_state)}</span><span class="score">{html.escape(guard_report.max_autonomy_tier)}</span></div>
          <p class="summary"><b>JRE:</b> {html.escape(jre_report.state)} / JRI {jre_report.scores.readiness_index:.1f}. <b>Guardrail:</b> {html.escape(guard_report.provider_summary)}</p>
          <div class="grid"><div><h3>Input statements</h3><ul>{case_rows}</ul></div><div><h3>Assumption Register</h3><ul>{assumptions}</ul></div></div>
          <h3>Guardrail Findings</h3><table><thead><tr><th>Rule</th><th>Category</th><th>Severity</th><th>Control</th></tr></thead><tbody>{findings}</tbody></table>
        </section>
        """)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Black Swan Guardrail Demo</title>
<style>
body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 32px; background: #f7f7f8; color: #111; }}
h1 {{ margin-bottom: 0; }} .subtitle {{ color: #555; margin-top: 4px; }}
.card {{ background: white; border: 1px solid #ddd; border-radius: 14px; padding: 20px; margin: 18px 0; box-shadow: 0 1px 4px rgba(0,0,0,.05); }}
.topline {{ display: flex; gap: 12px; align-items: center; font-weight: 700; }}
.case {{ font-size: 1.1rem; flex: 1; }} .state, .score {{ border: 1px solid #bbb; padding: 4px 8px; border-radius: 999px; background: #fafafa; }}
.summary {{ color: #333; line-height: 1.45; }} .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }}
table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }} th, td {{ border-top: 1px solid #e5e5e5; padding: 8px; text-align: left; vertical-align: top; }}
.state-escalate {{ border-left: 8px solid #a33; }} .state-fail_closed {{ border-left: 8px solid #111; }} .state-route_clinician {{ border-left: 8px solid #b70; }} .state-hold_and_verify {{ border-left: 8px solid #777; }} .state-allow_with_audit {{ border-left: 8px solid #287; }}
</style></head><body>
<h1>Black Swan Guardrail Demo</h1>
<p class="subtitle">Synthetic cases. Demonstrates assumption-register guardrails around the Judgment Readiness Engine.</p>
{''.join(cards)}
</body></html>"""


def write_matrix(path: Path, reports) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "guardrail_state", "max_autonomy_tier", "novelty_score", "residual_risk_budget", "rule_id", "category", "severity", "control", "evidence"])
        for case, _jre_report, gr in reports:
            if not gr.findings:
                writer.writerow([case.case_id, gr.guardrail_state, gr.max_autonomy_tier, gr.novelty_score, gr.residual_risk_budget, "", "", "", "", ""])
            for item in gr.findings:
                writer.writerow([case.case_id, gr.guardrail_state, gr.max_autonomy_tier, gr.novelty_score, gr.residual_risk_budget, item.rule_id, item.category, item.severity, item.control, item.evidence])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", help="Case ID to run")
    parser.add_argument("--all", action="store_true", help="Run all black swan cases plus selected normal controls")
    parser.add_argument("--html", default="artifacts/black_swan_dashboard.html", help="Write HTML dashboard")
    parser.add_argument("--json", default="artifacts/black_swan_reports.json", help="Write JSON reports")
    parser.add_argument("--matrix", default="artifacts/black_swan_guardrail_matrix.csv", help="Write guardrail matrix CSV")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    # Include two normal controls so the demo proves the guardrail does not simply stop everything.
    cases = list(BLACK_SWAN_CASES)
    if args.all:
        cases = list(BLACK_SWAN_CASES) + [c for c in BASE_CASES if c.case_id in {"RF-002-good-refill-readyish", "CP-002-low-risk-but-incomplete"}]
    if args.case:
        all_cases = list(BLACK_SWAN_CASES) + BASE_CASES
        cases = [c for c in all_cases if c.case_id == args.case]
        if not cases:
            raise SystemExit(f"Case not found: {args.case}")

    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()
    items = []
    for case in cases:
        jre_report = jre.evaluate(case)
        guard_report = guard.evaluate(case, jre_report)
        items.append((case, jre_report, guard_report))

    for _case, _jre_report, guard_report in items[:8]:
        print(guardrail_report_to_markdown(guard_report))
        print("\n" + "=" * 90 + "\n")

    if args.html:
        out = base_dir / args.html
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(make_html(items), encoding="utf-8")
        print(f"Wrote HTML dashboard: {out}")
    if args.json:
        out = base_dir / args.json
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"case": case.case_id, "jre": jre_report.to_dict(), "guardrail": guard_report.to_dict()} for case, jre_report, guard_report in items]
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote JSON reports: {out}")
    if args.matrix:
        out = base_dir / args.matrix
        write_matrix(out, items)
        print(f"Wrote guardrail matrix: {out}")


if __name__ == "__main__":
    main()
