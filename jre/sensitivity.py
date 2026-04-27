"""Threshold sensitivity analysis for JRE + BSG.

Varies key thresholds and measures how outcomes change across all cases.
Answers: "How sensitive are our safety decisions to the hand-tuned constants?"

Run:
    python -m jre.sensitivity
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .engine import JudgmentReadinessEngine, GESTALT_PATTERNS
from .black_swan import BlackSwanGuardrailEngine
from .models import CaseInput, ReadinessReport
from .black_swan import GuardrailReport
from .synthetic_data import BASE_CASES
from .black_swan import BLACK_SWAN_CASES


@dataclass
class ThresholdVariation:
    """One threshold setting to test."""
    name: str
    parameter: str
    baseline: float
    test_value: float


@dataclass
class SensitivityResult:
    """Result of running all cases at one threshold setting."""
    variation: ThresholdVariation
    case_results: List[Dict[str, Any]]
    state_changes: int
    total_cases: int

    @property
    def change_rate(self) -> float:
        return self.state_changes / self.total_cases if self.total_cases > 0 else 0.0


# Thresholds we vary
THRESHOLD_VARIATIONS: List[ThresholdVariation] = [
    # JRE thresholds (in engine._decide_state)
    ThresholdVariation("JRI cutoff (strict)", "jri_ready_threshold", 78.0, 85.0),
    ThresholdVariation("JRI cutoff (loose)", "jri_ready_threshold", 78.0, 70.0),
    ThresholdVariation("Red flag severity (strict)", "red_flag_escalation_threshold", 0.85, 0.75),
    ThresholdVariation("Red flag severity (loose)", "red_flag_escalation_threshold", 0.85, 0.95),
    ThresholdVariation("Objective needed severity (strict)", "objective_needed_threshold", 0.85, 0.75),
    ThresholdVariation("Objective needed severity (loose)", "objective_needed_threshold", 0.85, 0.95),
    # BSG thresholds (in _decide_state)
    ThresholdVariation("Novelty threshold (strict)", "novelty_route_threshold", 0.55, 0.40),
    ThresholdVariation("Novelty threshold (loose)", "novelty_route_threshold", 0.55, 0.70),
    ThresholdVariation("Risk budget threshold (strict)", "risk_budget_route_threshold", 0.72, 0.55),
    ThresholdVariation("Risk budget threshold (loose)", "risk_budget_route_threshold", 0.72, 0.85),
    ThresholdVariation("Escalation severity (strict)", "escalation_severity_threshold", 0.90, 0.80),
    ThresholdVariation("Escalation severity (loose)", "escalation_severity_threshold", 0.90, 0.95),
    # Finding-generation thresholds (affect which findings are produced)
    ThresholdVariation("Source conflict severity (strict)", "source_conflict_severity", 0.70, 0.50),
    ThresholdVariation("Source conflict severity (loose)", "source_conflict_severity", 0.70, 0.90),
    ThresholdVariation("Gestalt min required (strict)", "gestalt_min_required", 2.0, 3.0),
    ThresholdVariation("Gestalt min required (loose)", "gestalt_min_required", 2.0, 1.0),
]


def get_all_cases() -> List[CaseInput]:
    return list(BASE_CASES) + list(BLACK_SWAN_CASES)


def _run_baseline(cases: List[CaseInput]) -> List[Dict[str, Any]]:
    """Run all cases at baseline thresholds."""
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()
    results = []
    for case in cases:
        jre_report = jre.evaluate(case)
        bsg_report = guard.evaluate(case, jre_report)
        results.append({
            "case_id": case.case_id,
            "jre_state": jre_report.state,
            "bsg_state": bsg_report.guardrail_state,
            "jri": jre_report.scores.readiness_index,
            "novelty": bsg_report.novelty_score,
            "risk_budget": bsg_report.residual_risk_budget,
        })
    return results


def _run_with_jre_threshold(
    cases: List[CaseInput],
    parameter: str,
    value: float,
) -> List[Dict[str, Any]]:
    """Run with a modified JRE threshold (monkey-patched)."""
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()

    # Store original method
    original_decide = jre._decide_state

    def patched_decide(scores, findings, next_questions):
        if parameter == "jri_ready_threshold":
            if any(f.category == "red_flag" and f.severity >= 0.85 for f in findings):
                return "ESCALATE"
            if any(f.category == "objective_needed" and f.severity >= 0.85 for f in findings):
                return "NEED_OBJECTIVE_DATA"
            if any(f.category == "contradictory" for f in findings):
                return "CLARIFY"
            if scores.readiness_index >= value and scores.red_flag_load == 0 and len(next_questions) <= 2:
                return "READY"
            return "CLARIFY"
        elif parameter == "red_flag_escalation_threshold":
            if any(f.category == "red_flag" and f.severity >= value for f in findings):
                return "ESCALATE"
            if any(f.category == "objective_needed" and f.severity >= 0.85 for f in findings):
                return "NEED_OBJECTIVE_DATA"
            if any(f.category == "contradictory" for f in findings):
                return "CLARIFY"
            if scores.readiness_index >= 78 and scores.red_flag_load == 0 and len(next_questions) <= 2:
                return "READY"
            return "CLARIFY"
        elif parameter == "objective_needed_threshold":
            if any(f.category == "red_flag" and f.severity >= 0.85 for f in findings):
                return "ESCALATE"
            if any(f.category == "objective_needed" and f.severity >= value for f in findings):
                return "NEED_OBJECTIVE_DATA"
            if any(f.category == "contradictory" for f in findings):
                return "CLARIFY"
            if scores.readiness_index >= 78 and scores.red_flag_load == 0 and len(next_questions) <= 2:
                return "READY"
            return "CLARIFY"
        return original_decide(scores, findings, next_questions)

    jre._decide_state = patched_decide

    results = []
    for case in cases:
        jre_report = jre.evaluate(case)
        bsg_report = guard.evaluate(case, jre_report)
        results.append({
            "case_id": case.case_id,
            "jre_state": jre_report.state,
            "bsg_state": bsg_report.guardrail_state,
            "jri": jre_report.scores.readiness_index,
            "novelty": bsg_report.novelty_score,
            "risk_budget": bsg_report.residual_risk_budget,
        })
    return results


def _run_with_bsg_threshold(
    cases: List[CaseInput],
    parameter: str,
    value: float,
) -> List[Dict[str, Any]]:
    """Run with a modified BSG threshold (monkey-patched)."""
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()

    original_decide = guard._decide_state

    def patched_decide(findings, risk_budget, novelty, report):
        if parameter == "novelty_route_threshold":
            if any(f.action == "ESCALATE" and f.severity >= 0.90 for f in findings):
                return "ESCALATE", "T0_EMERGENCY_OR_HARD_STOP"
            if any(f.action == "FAIL_CLOSED" for f in findings):
                return "FAIL_CLOSED", "T1_INTAKE_ONLY"
            if novelty >= value or risk_budget >= 0.72:
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "ROUTE_CLINICIAN" for f in findings):
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "HOLD_AND_VERIFY" for f in findings):
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            if report is not None and report.state == "READY" and risk_budget < 0.25 and novelty < 0.20:
                return "ALLOW_WITH_AUDIT", "T4_NARROW_AUTONOMOUS_ACTION"
            if report is not None and report.state in {"CLARIFY", "NEED_OBJECTIVE_DATA"}:
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            return "ALLOW_WITH_AUDIT", "T3_SUPERVISED_PROTOCOL"
        elif parameter == "risk_budget_route_threshold":
            if any(f.action == "ESCALATE" and f.severity >= 0.90 for f in findings):
                return "ESCALATE", "T0_EMERGENCY_OR_HARD_STOP"
            if any(f.action == "FAIL_CLOSED" for f in findings):
                return "FAIL_CLOSED", "T1_INTAKE_ONLY"
            if novelty >= 0.55 or risk_budget >= value:
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "ROUTE_CLINICIAN" for f in findings):
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "HOLD_AND_VERIFY" for f in findings):
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            if report is not None and report.state == "READY" and risk_budget < 0.25 and novelty < 0.20:
                return "ALLOW_WITH_AUDIT", "T4_NARROW_AUTONOMOUS_ACTION"
            if report is not None and report.state in {"CLARIFY", "NEED_OBJECTIVE_DATA"}:
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            return "ALLOW_WITH_AUDIT", "T3_SUPERVISED_PROTOCOL"
        elif parameter == "escalation_severity_threshold":
            if any(f.action == "ESCALATE" and f.severity >= value for f in findings):
                return "ESCALATE", "T0_EMERGENCY_OR_HARD_STOP"
            if any(f.action == "FAIL_CLOSED" for f in findings):
                return "FAIL_CLOSED", "T1_INTAKE_ONLY"
            if novelty >= 0.55 or risk_budget >= 0.72:
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "ROUTE_CLINICIAN" for f in findings):
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "HOLD_AND_VERIFY" for f in findings):
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            if report is not None and report.state == "READY" and risk_budget < 0.25 and novelty < 0.20:
                return "ALLOW_WITH_AUDIT", "T4_NARROW_AUTONOMOUS_ACTION"
            if report is not None and report.state in {"CLARIFY", "NEED_OBJECTIVE_DATA"}:
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            return "ALLOW_WITH_AUDIT", "T3_SUPERVISED_PROTOCOL"
        return original_decide(findings, risk_budget, novelty, report)

    guard._decide_state = patched_decide

    results = []
    for case in cases:
        jre_report = jre.evaluate(case)
        bsg_report = guard.evaluate(case, jre_report)
        results.append({
            "case_id": case.case_id,
            "jre_state": jre_report.state,
            "bsg_state": bsg_report.guardrail_state,
            "jri": jre_report.scores.readiness_index,
            "novelty": bsg_report.novelty_score,
            "risk_budget": bsg_report.residual_risk_budget,
        })
    return results


def _run_with_source_conflict_severity(
    cases: List[CaseInput],
    severity_value: float,
) -> List[Dict[str, Any]]:
    """Run with a modified source conflict severity threshold.

    Monkey-patches _source_conflict_findings to use the given severity
    instead of the hardcoded 0.70, then evaluates all cases.
    """
    import re
    from .models import Finding, Observation
    from .engine import NEGATIVE_WORDS, NUMBER_RE
    from collections import defaultdict

    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()

    original_source_conflict = jre._source_conflict_findings

    def patched_source_conflict(all_observations, traces):
        """Same logic as original but with configurable severity."""
        findings = []
        HIGH_AUTHORITY = {"device", "chart", "clinician"}
        LOW_AUTHORITY = {"patient", "caregiver"}
        NORMAL_WORDS = re.compile(r"\b(normal|fine|okay|ok|good|no problem)\b", re.I)

        by_concept = defaultdict(list)
        for obs in all_observations:
            by_concept[obs.concept].append(obs)

        for concept, obs_list in by_concept.items():
            if len(obs_list) < 2:
                continue
            sources = {obs.source for obs in obs_list}
            has_high = sources & HIGH_AUTHORITY
            has_low = sources & LOW_AUTHORITY
            if not has_high or not has_low:
                continue

            high_obs = [o for o in obs_list if o.source in HIGH_AUTHORITY]
            low_obs = [o for o in obs_list if o.source in LOW_AUTHORITY]

            for hi in high_obs:
                for lo in low_obs:
                    hi_negative = NEGATIVE_WORDS.search(str(hi.raw_value)) is not None
                    lo_negative = NEGATIVE_WORDS.search(str(lo.raw_value)) is not None
                    hi_normal = NORMAL_WORDS.search(str(hi.raw_value)) is not None
                    lo_normal = NORMAL_WORDS.search(str(lo.raw_value)) is not None
                    hi_has_number = NUMBER_RE.search(str(hi.raw_value)) is not None
                    lo_has_number = NUMBER_RE.search(str(lo.raw_value)) is not None

                    conflict = False
                    if hi_negative != lo_negative:
                        conflict = True
                    elif (lo_normal and not lo_has_number) and hi_has_number:
                        conflict = True
                    elif (hi_normal and not hi_has_number) and lo_has_number:
                        conflict = True

                    if conflict:
                        from .models import RuleTrace
                        findings.append(
                            Finding(
                                category="contradictory",
                                concept=concept,
                                severity=severity_value,
                                reason=f"Source conflict on '{concept}': high-authority source '{hi.source}' disagrees with '{lo.source}'.",
                                rule_id=f"SOURCE_CONFLICT_{concept.upper()}",
                                evidence=f"Source '{hi.source}': '{hi.raw_value}' vs Source '{lo.source}': '{lo.raw_value}'",
                            )
                        )
                        traces.append(RuleTrace(
                            f"SOURCE_CONFLICT_{concept.upper()}",
                            "Source authority conflict detected",
                            f"{hi.source}='{hi.raw_value}' vs {lo.source}='{lo.raw_value}'",
                            f"adds contradictory finding (severity={severity_value:.2f})",
                        ))

        return findings

    jre._source_conflict_findings = patched_source_conflict

    results = []
    for case in cases:
        jre_report = jre.evaluate(case)
        bsg_report = guard.evaluate(case, jre_report)
        results.append({
            "case_id": case.case_id,
            "jre_state": jre_report.state,
            "bsg_state": bsg_report.guardrail_state,
            "jri": jre_report.scores.readiness_index,
            "novelty": bsg_report.novelty_score,
            "risk_budget": bsg_report.residual_risk_budget,
        })
    return results


def _run_with_gestalt_min_required(
    cases: List[CaseInput],
    min_required_value: int,
) -> List[Dict[str, Any]]:
    """Run with a modified gestalt min_required threshold.

    Temporarily modifies the min_required field in every GESTALT_PATTERNS
    entry, runs all cases, then restores the original values.
    """
    # Save originals
    originals = {p["id"]: p["min_required"] for p in GESTALT_PATTERNS}
    try:
        for p in GESTALT_PATTERNS:
            p["min_required"] = min_required_value

        jre = JudgmentReadinessEngine()
        guard = BlackSwanGuardrailEngine()

        results = []
        for case in cases:
            jre_report = jre.evaluate(case)
            bsg_report = guard.evaluate(case, jre_report)
            results.append({
                "case_id": case.case_id,
                "jre_state": jre_report.state,
                "bsg_state": bsg_report.guardrail_state,
                "jri": jre_report.scores.readiness_index,
                "novelty": bsg_report.novelty_score,
                "risk_budget": bsg_report.residual_risk_budget,
            })
        return results
    finally:
        # Always restore original values
        for p in GESTALT_PATTERNS:
            p["min_required"] = originals[p["id"]]


def run_sensitivity_analysis(
    cases: Optional[List[CaseInput]] = None,
    variations: Optional[List[ThresholdVariation]] = None,
) -> Tuple[List[Dict[str, Any]], List[SensitivityResult]]:
    """Run full sensitivity analysis. Returns (baseline_results, variation_results)."""
    if cases is None:
        cases = get_all_cases()
    if variations is None:
        variations = THRESHOLD_VARIATIONS

    baseline = _run_baseline(cases)
    baseline_states = {r["case_id"]: (r["jre_state"], r["bsg_state"]) for r in baseline}

    results = []
    for var in variations:
        jre_params = {"jri_ready_threshold", "red_flag_escalation_threshold", "objective_needed_threshold"}
        bsg_params = {"novelty_route_threshold", "risk_budget_route_threshold", "escalation_severity_threshold"}

        if var.parameter in jre_params:
            varied = _run_with_jre_threshold(cases, var.parameter, var.test_value)
        elif var.parameter in bsg_params:
            varied = _run_with_bsg_threshold(cases, var.parameter, var.test_value)
        elif var.parameter == "source_conflict_severity":
            varied = _run_with_source_conflict_severity(cases, var.test_value)
        elif var.parameter == "gestalt_min_required":
            varied = _run_with_gestalt_min_required(cases, int(var.test_value))
        else:
            continue

        changes = 0
        for r in varied:
            base_jre, base_bsg = baseline_states[r["case_id"]]
            if r["jre_state"] != base_jre or r["bsg_state"] != base_bsg:
                changes += 1
                r["changed"] = True
                r["baseline_jre"] = base_jre
                r["baseline_bsg"] = base_bsg
            else:
                r["changed"] = False

        results.append(SensitivityResult(
            variation=var,
            case_results=varied,
            state_changes=changes,
            total_cases=len(cases),
        ))

    return baseline, results


def sensitivity_to_markdown(
    baseline: List[Dict[str, Any]],
    results: List[SensitivityResult],
) -> str:
    """Generate a markdown report of sensitivity analysis."""
    lines = ["# Threshold Sensitivity Analysis", ""]
    lines.append(f"**Cases analyzed:** {len(baseline)}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Variation | Parameter | Baseline | Test Value | Cases Changed | Change Rate |")
    lines.append("|-----------|-----------|----------|------------|---------------|-------------|")
    for sr in results:
        v = sr.variation
        lines.append(
            f"| {v.name} | {v.parameter} | {v.baseline} | {v.test_value} | "
            f"{sr.state_changes}/{sr.total_cases} | {sr.change_rate:.0%} |"
        )

    # Detail per variation
    lines.append("")
    lines.append("## Details")
    for sr in results:
        v = sr.variation
        changed = [r for r in sr.case_results if r.get("changed")]
        lines.append("")
        lines.append(f"### {v.name}")
        lines.append(f"**{v.parameter}:** {v.baseline} -> {v.test_value}")
        lines.append(f"**Impact:** {sr.state_changes}/{sr.total_cases} cases changed ({sr.change_rate:.0%})")
        if changed:
            lines.append("")
            lines.append("| Case | Baseline JRE | New JRE | Baseline BSG | New BSG |")
            lines.append("|------|-------------|---------|-------------|---------|")
            for r in changed:
                lines.append(
                    f"| {r['case_id']} | {r.get('baseline_jre', '')} | {r['jre_state']} | "
                    f"{r.get('baseline_bsg', '')} | {r['bsg_state']} |"
                )
        else:
            lines.append("*No cases changed.*")

    return "\n".join(lines)


def sensitivity_to_csv(
    baseline: List[Dict[str, Any]],
    results: List[SensitivityResult],
) -> str:
    """Generate CSV of sensitivity analysis."""
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "variation_name", "parameter", "baseline_value", "test_value",
        "case_id", "baseline_jre", "new_jre", "baseline_bsg", "new_bsg",
        "changed", "jri", "novelty", "risk_budget",
    ])

    baseline_states = {r["case_id"]: (r["jre_state"], r["bsg_state"]) for r in baseline}

    for sr in results:
        v = sr.variation
        for r in sr.case_results:
            base_jre, base_bsg = baseline_states[r["case_id"]]
            writer.writerow([
                v.name, v.parameter, v.baseline, v.test_value,
                r["case_id"], base_jre, r["jre_state"],
                base_bsg, r["bsg_state"],
                r.get("changed", False),
                f"{r['jri']:.1f}", f"{r['novelty']:.3f}", f"{r['risk_budget']:.3f}",
            ])

    return output.getvalue()


def main() -> None:
    """CLI entry point."""
    import sys

    cases = get_all_cases()
    print(f"Running sensitivity analysis on {len(cases)} cases across {len(THRESHOLD_VARIATIONS)} threshold variations...")

    baseline, results = run_sensitivity_analysis(cases)

    md = sensitivity_to_markdown(baseline, results)
    print(md)

    # Write artifacts
    base_dir = Path(__file__).resolve().parents[1] / "artifacts"
    base_dir.mkdir(parents=True, exist_ok=True)

    md_path = base_dir / "sensitivity_report.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"\nWrote: {md_path}")

    csv_path = base_dir / "sensitivity_matrix.csv"
    csv_path.write_text(sensitivity_to_csv(baseline, results), encoding="utf-8")
    print(f"Wrote: {csv_path}")


if __name__ == "__main__":
    main()
