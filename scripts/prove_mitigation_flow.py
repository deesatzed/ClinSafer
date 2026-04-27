#!/usr/bin/env python3
"""Proof harness for the CEO mitigation flow.

This intentionally uses the same objects the interactive demo uses rather than
mocking the response shape. It proves the current app can distinguish a subtle
refill near miss from a clean refill control and emits the exact analysis
sections a user sees in the browser.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interactive_demo import (
    _ALL_CASES,
    _build_progressive_sections,
    _guard,
    _jre,
)
from jre.models import most_restrictive


def section_by_id(sections: list[dict[str, Any]], section_id: str) -> dict[str, Any]:
    for section in sections:
        if section["id"] == section_id:
            return section
    raise AssertionError(f"missing section: {section_id}")


def analyze(case_id: str) -> dict[str, Any]:
    case = _ALL_CASES[case_id]
    jre_report = _jre.evaluate(case)
    bsg_report = _guard.evaluate(case, jre_report)
    combined_state = most_restrictive(jre_report.state, bsg_report.guardrail_state)
    sections = _build_progressive_sections(case, jre_report, bsg_report, combined_state)
    mitigation = section_by_id(sections, "mitigation_plan")["data"]
    business = section_by_id(sections, "business_impact")["data"]
    autonomy = section_by_id(sections, "autonomy_boundary")["data"]

    return {
        "case_id": case_id,
        "jre_state": jre_report.state,
        "bsg_state": bsg_report.guardrail_state,
        "combined_state": combined_state,
        "jri": jre_report.scores.readiness_index,
        "autonomy_cap": bsg_report.max_autonomy_tier,
        "section_ids": [section["id"] for section in sections],
        "blocked_actions": autonomy["blocked_actions"],
        "business_metric": business["metric_to_track"],
        "recalled_pattern": mitigation["recalled_pattern"],
        "trace_hot_regions": [
            row["region"]
            for row in mitigation["trace_regions"]
            if row["status"] in {"hot", "reinforced"}
        ],
        "pattern_completion": mitigation["pattern_completion"],
        "falsifier_targets": [row["target"] for row in mitigation["falsifiers"]],
        "mitigation_layers": [
            row["layer"]
            for row in mitigation["mitigations"]
        ],
    }


def main() -> None:
    hero = analyze("CEO-001-stale-ace-refill-ckd-nsaid")
    clean = analyze("RF-002-good-refill-readyish")

    expected_layers = {
        "Current deterministic controls",
        "Stigmergic boundary trace",
        "VAMS near-miss recall",
        "Governed template promotion",
        "Business mitigation",
    }

    assert "mitigation_plan" in hero["section_ids"]
    assert "mitigation_plan" in clean["section_ids"]
    assert expected_layers.issubset(hero["mitigation_layers"])
    assert expected_layers.issubset(clean["mitigation_layers"])

    assert hero["combined_state"] in {
        "ESCALATE",
        "FAIL_CLOSED",
        "ROUTE_CLINICIAN",
        "HOLD_AND_VERIFY",
        "NEED_OBJECTIVE_DATA",
        "CLARIFY",
    }
    assert "autonomous refill renewal" in hero["blocked_actions"]
    assert "Refill near miss" in hero["recalled_pattern"]
    assert {"claims", "objective"}.intersection(hero["trace_hot_regions"])
    assert len(hero["falsifier_targets"]) >= 1

    assert clean["combined_state"] in {"ALLOW_WITH_AUDIT", "READY"}
    assert "Clean refill analogue" in clean["recalled_pattern"]
    assert "autonomous refill renewal" not in clean["blocked_actions"]

    proof = {
        "proof": "PASS",
        "hero_near_miss": hero,
        "clean_control": clean,
    }
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    main()
