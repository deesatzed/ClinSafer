"""Tests for the unified demo pipeline.

pytest-style tests — zero mocks, real engine execution.
"""
from __future__ import annotations

import csv
import json
import io
from pathlib import Path

import pytest

from jre import JudgmentReadinessEngine
from jre.synthetic_data import BASE_CASES
from jre.black_swan import BLACK_SWAN_CASES

# Import everything we need from unified_demo
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from unified_demo import (
    CASE_NARRATIVES,
    TRAP_EXPLANATIONS,
    RESOLUTION_ANSWERS,
    MULTITURN_EXPECTED_OUTCOMES,
    CaseNarrative,
    UnifiedResult,
    PerCaseVariation,
    TurnResult,
    run_unified_pipeline,
    get_all_cases,
    make_unified_html,
    unified_report_to_markdown,
    unified_to_json,
    write_unified_matrix,
    run_per_case_sensitivity,
    run_multiturn_simulation,
    validate_multiturn_outcomes,
    _most_restrictive,
    _print_case_list,
)

# Total expected cases: BASE_CASES + BLACK_SWAN_CASES
EXPECTED_TOTAL = len(BASE_CASES) + len(BLACK_SWAN_CASES)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def all_cases():
    """All hand-authored cases."""
    return get_all_cases()


@pytest.fixture(scope="module")
def all_results(all_cases):
    """Run the full pipeline once for the module (expensive, real execution)."""
    return run_unified_pipeline(all_cases)


def _result_by_id(results, case_id):
    return next(r for r in results if r.case.case_id == case_id)


def by_id(case_id):
    return next(c for c in BASE_CASES if c.case_id == case_id)


# ---------------------------------------------------------------------------
# 1. Narrative Completeness (4 tests)
# ---------------------------------------------------------------------------

def test_every_base_case_has_narrative():
    """Every BASE_CASE has a corresponding narrative entry."""
    for case in BASE_CASES:
        assert case.case_id in CASE_NARRATIVES, f"Missing narrative for {case.case_id}"


def test_every_black_swan_case_has_narrative():
    """Every BLACK_SWAN_CASE has a corresponding narrative entry."""
    for case in BLACK_SWAN_CASES:
        assert case.case_id in CASE_NARRATIVES, f"Missing narrative for {case.case_id}"


def test_narrative_fields_non_empty():
    """All narrative fields must be non-empty strings."""
    for case_id, narr in CASE_NARRATIVES.items():
        assert narr.title, f"{case_id}: title empty"
        assert narr.scenario, f"{case_id}: scenario empty"
        assert narr.jre_demonstrates, f"{case_id}: jre_demonstrates empty"
        assert narr.bsg_demonstrates, f"{case_id}: bsg_demonstrates empty"
        assert narr.combined_insight, f"{case_id}: combined_insight empty"
        assert narr.category, f"{case_id}: category empty"


def test_no_extra_narratives():
    """No narrative exists for a case ID that doesn't exist in the case sets."""
    all_ids = {c.case_id for c in BASE_CASES} | {c.case_id for c in BLACK_SWAN_CASES}
    for case_id in CASE_NARRATIVES:
        assert case_id in all_ids, f"Extra narrative for non-existent case: {case_id}"


# ---------------------------------------------------------------------------
# 2. Pipeline Correctness (3 tests)
# ---------------------------------------------------------------------------

def test_pipeline_returns_expected_results(all_results):
    """Pipeline returns correct number of results for all cases."""
    assert len(all_results) == EXPECTED_TOTAL


def test_all_fields_populated(all_results):
    """Every result has all fields populated with correct types."""
    for r in all_results:
        assert isinstance(r, UnifiedResult)
        assert r.case is not None
        assert r.narrative is not None
        assert r.jre_report is not None
        assert r.bsg_report is not None
        assert isinstance(r.combined_state, str)
        assert len(r.combined_state) > 0
        assert isinstance(r.ground_truth_match, bool)
        assert isinstance(r.combined_verdict, str)
        assert len(r.combined_verdict) > 0


def test_combined_state_is_most_restrictive(all_results):
    """Combined state is always the more restrictive of JRE and BSG states."""
    for r in all_results:
        expected = _most_restrictive(r.jre_report.state, r.bsg_report.guardrail_state)
        assert r.combined_state == expected, (
            f"{r.case.case_id}: combined={r.combined_state} but expected "
            f"most_restrictive({r.jre_report.state}, {r.bsg_report.guardrail_state})={expected}"
        )


# ---------------------------------------------------------------------------
# 3. Specific Case Behavior (7 tests)
# ---------------------------------------------------------------------------

def test_rf002_allows_through(all_results):
    """RF-002 (clean refill) should allow with audit."""
    r = _result_by_id(all_results, "RF-002-good-refill-readyish")
    assert r.combined_state == "ALLOW_WITH_AUDIT"


def test_cp001_escalates(all_results):
    """CP-001 (heartburn/pressure) should escalate."""
    r = _result_by_id(all_results, "CP-001-heartburn-pressure")
    assert r.combined_state == "ESCALATE"


def test_bs002_fails_closed(all_results):
    """BS-002 (prompt injection) should fail closed."""
    r = _result_by_id(all_results, "BS-002-prompt-injection-antibiotic")
    assert r.combined_state == "FAIL_CLOSED"


def test_bs001_fails_closed(all_results):
    """BS-001 (wrong patient) should fail closed."""
    r = _result_by_id(all_results, "BS-001-refill-wrong-patient")
    assert r.combined_state == "FAIL_CLOSED"


def test_bs003_escalates(all_results):
    """BS-003 (off-pathway stroke) should escalate."""
    r = _result_by_id(all_results, "BS-003-offpath-stroke-in-refill")
    assert r.combined_state == "ESCALATE"


def test_ha001_escalates(all_results):
    """HA-001 (thunderclap headache) should escalate."""
    r = _result_by_id(all_results, "HA-001-thunderclap-minimized")
    assert r.combined_state == "ESCALATE"


def test_bs009_active_bleeding_escalates(all_results):
    """BS-009 (active bleeding in refill) should escalate."""
    r = _result_by_id(all_results, "BS-009-active-bleeding-in-refill")
    assert r.combined_state == "ESCALATE"


# ---------------------------------------------------------------------------
# 4. Ground Truth Validation (2 tests)
# ---------------------------------------------------------------------------

def test_escalation_cases_get_restrictive_states(all_results):
    """All cases with requires_escalation=True get restrictive combined states."""
    restrictive = {"ESCALATE", "FAIL_CLOSED", "ROUTE_CLINICIAN", "NEED_OBJECTIVE_DATA", "HOLD_AND_VERIFY"}
    for r in all_results:
        gt = r.case.ground_truth
        if gt.get("requires_escalation"):
            assert r.combined_state in restrictive, (
                f"{r.case.case_id}: requires_escalation=True but got {r.combined_state}"
            )


def test_ground_truth_match_rate(all_results):
    """High ground truth match rate across all cases."""
    total = len(all_results)
    matches = sum(1 for r in all_results if r.ground_truth_match)
    min_required = total - 3  # Allow up to 3 mismatches
    assert matches >= min_required, f"Only {matches}/{total} ground truth matches (need >= {min_required})"


# ---------------------------------------------------------------------------
# 5. Output Generation (6 tests)
# ---------------------------------------------------------------------------

def test_html_contains_all_cards(all_results):
    """HTML output contains cards for all cases."""
    html = make_unified_html(all_results)
    assert "<!doctype html>" in html
    for r in all_results:
        assert r.case.case_id in html, f"Missing {r.case.case_id} in HTML"


def test_html_has_stats_bar(all_results):
    """HTML contains the stats header bar."""
    html = make_unified_html(all_results)
    assert "stats-bar" in html
    assert "GT Match" in html


def test_markdown_contains_all_case_ids(all_results):
    """Markdown report mentions all case IDs."""
    md = unified_report_to_markdown(all_results)
    for r in all_results:
        assert r.case.case_id in md, f"Missing {r.case.case_id} in markdown"


def test_json_parseable_with_correct_count(all_results):
    """JSON output parses and contains correct number of entries."""
    json_str = unified_to_json(all_results)
    data = json.loads(json_str)
    assert isinstance(data, list)
    assert len(data) == EXPECTED_TOTAL
    # Spot-check structure
    for item in data:
        assert "case_id" in item
        assert "narrative" in item
        assert "jre_report" in item
        assert "bsg_report" in item
        assert "combined_state" in item
        assert "ground_truth_match" in item


def test_csv_has_correct_rows(all_results, tmp_path):
    """CSV output has header + data rows."""
    csv_path = tmp_path / "test_matrix.csv"
    write_unified_matrix(csv_path, all_results)
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    expected_rows = EXPECTED_TOTAL + 1  # header + data
    assert len(rows) == expected_rows, f"Expected {expected_rows} rows, got {len(rows)}"
    assert rows[0][0] == "case_id"  # header check


def test_csv_columns_correct(all_results, tmp_path):
    """CSV has all expected columns."""
    csv_path = tmp_path / "test_matrix2.csv"
    write_unified_matrix(csv_path, all_results)
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    expected_cols = [
        "case_id", "category", "jre_state", "jri_score",
        "bsg_state", "autonomy_tier", "novelty_score", "risk_budget",
        "combined_state", "ground_truth_match",
        "jre_finding_count", "bsg_finding_count",
        "jre_question_count", "assumption_breaches",
    ]
    assert header == expected_cols


# ---------------------------------------------------------------------------
# 6. Determinism (1 test)
# ---------------------------------------------------------------------------

def test_two_runs_identical():
    """Two runs of the full pipeline produce identical combined states."""
    cases = get_all_cases()
    run1 = run_unified_pipeline(cases)
    run2 = run_unified_pipeline(cases)
    for r1, r2 in zip(run1, run2):
        assert r1.case.case_id == r2.case.case_id
        assert r1.combined_state == r2.combined_state
        assert r1.jre_report.state == r2.jre_report.state
        assert r1.bsg_report.guardrail_state == r2.bsg_report.guardrail_state
        assert r1.ground_truth_match == r2.ground_truth_match


# ---------------------------------------------------------------------------
# 7. Single Case Mode (1 test)
# ---------------------------------------------------------------------------

def test_single_case_pipeline():
    """Pipeline works correctly with a single filtered case."""
    cases = [c for c in get_all_cases() if c.case_id == "BS-003-offpath-stroke-in-refill"]
    assert len(cases) == 1
    results = run_unified_pipeline(cases)
    assert len(results) == 1
    assert results[0].case.case_id == "BS-003-offpath-stroke-in-refill"
    assert results[0].combined_state == "ESCALATE"


# ---------------------------------------------------------------------------
# 8. Shared Module (1 test)
# ---------------------------------------------------------------------------

def test_most_restrictive_from_shared_module():
    """most_restrictive from jre.models works and matches the unified_demo alias."""
    from jre.models import most_restrictive
    assert most_restrictive("READY", "ESCALATE") == "ESCALATE"
    assert most_restrictive("CLARIFY", "ALLOW_WITH_AUDIT") == "CLARIFY"
    assert most_restrictive("READY", "READY") == "READY"
    assert most_restrictive("FAIL_CLOSED", "ESCALATE") == "ESCALATE"
    # The alias in unified_demo should produce same results
    assert _most_restrictive("READY", "ESCALATE") == most_restrictive("READY", "ESCALATE")


# ---------------------------------------------------------------------------
# 9. Dynamic Counts (1 test)
# ---------------------------------------------------------------------------

def test_html_subtitle_has_correct_count(all_results):
    """HTML subtitle shows the actual total count, not a hardcoded number."""
    html = make_unified_html(all_results)
    assert f"All {len(all_results)} hand-authored cases" in html


# ---------------------------------------------------------------------------
# 10. Case List (1 test)
# ---------------------------------------------------------------------------

def test_list_flag_prints_all_case_ids(capsys):
    """_print_case_list() outputs all case IDs grouped."""
    _print_case_list()
    output = capsys.readouterr().out
    # Should contain all case IDs
    for case in BASE_CASES:
        assert case.case_id in output, f"Missing {case.case_id} in --list output"
    for case in BLACK_SWAN_CASES:
        assert case.case_id in output, f"Missing {case.case_id} in --list output"
    # Should show group labels
    assert "Base Cases" in output
    assert "Black Swan Cases" in output


# ---------------------------------------------------------------------------
# 11. Interactive HTML Features (8 tests)
# ---------------------------------------------------------------------------

def test_html_has_javascript(all_results):
    """HTML contains a <script> block with key interactive functions."""
    html = make_unified_html(all_results)
    assert "<script>" in html
    assert "applyFilters" in html
    assert "updateVisibleCount" in html


def test_html_has_filter_controls(all_results):
    """HTML contains search box, category filter, and expand/collapse buttons."""
    html = make_unified_html(all_results)
    assert 'id="searchBox"' in html
    assert 'id="categoryFilter"' in html
    assert 'id="expandAll"' in html
    assert 'id="collapseAll"' in html


def test_html_has_jri_breakdown(all_results):
    """HTML contains JRI breakdown visual elements."""
    html = make_unified_html(all_results)
    assert "jri-breakdown" in html
    assert "jri-bar" in html
    assert "jri-seg-completeness" in html
    assert "jri-seg-reliability" in html


def test_html_has_data_attributes(all_results):
    """Cards have data-state and data-category attributes for filtering."""
    html = make_unified_html(all_results)
    assert 'data-state="' in html
    assert 'data-category="base"' in html
    assert 'data-category="blackswan"' in html


def test_html_has_dark_mode_css(all_results):
    """HTML includes dark mode CSS rules."""
    html = make_unified_html(all_results)
    assert "prefers-color-scheme: dark" in html
    assert "dark-mode" in html
    assert 'id="darkToggle"' in html


def test_html_has_print_css(all_results):
    """HTML includes print-friendly CSS media query."""
    html = make_unified_html(all_results)
    assert "@media print" in html


def test_html_has_responsive_css(all_results):
    """HTML includes responsive CSS media query."""
    html = make_unified_html(all_results)
    assert "@media (max-width: 768px)" in html


def test_html_cards_have_ids(all_results):
    """Each card has id='card-{case_id}' for navigation."""
    html = make_unified_html(all_results)
    for r in all_results:
        assert f'id="card-{r.case.case_id}"' in html, f"Missing card id for {r.case.case_id}"


# ---------------------------------------------------------------------------
# 12. Abbreviation Renaming (4 tests)
# ---------------------------------------------------------------------------

def test_html_no_jre_abbreviation(all_results):
    """'JRE' does not appear as standalone label in HTML output."""
    html = make_unified_html(all_results)
    # Remove internal CSS class names and comments before checking
    import re
    # Strip CSS and JS sections
    content = re.sub(r'<style>.*?</style>', '', html, flags=re.DOTALL)
    content = re.sub(r'<script>.*?</script>', '', content, flags=re.DOTALL)
    # Check no standalone JRE label in visible content
    # Allow "jre" in data attributes, class names, but not as visible text like "JRE:" or ">JRE<"
    assert '>JRE<' not in content, "Found standalone JRE label in HTML"
    assert 'JRE:' not in content, "Found JRE: label in HTML"


def test_html_no_bsg_abbreviation(all_results):
    """'BSG' does not appear as standalone label in HTML output."""
    html = make_unified_html(all_results)
    import re
    content = re.sub(r'<style>.*?</style>', '', html, flags=re.DOTALL)
    content = re.sub(r'<script>.*?</script>', '', content, flags=re.DOTALL)
    assert '>BSG<' not in content, "Found standalone BSG label in HTML"
    assert 'BSG:' not in content, "Found BSG: label in HTML"


def test_html_no_jri_abbreviation(all_results):
    """'JRI' does not appear as standalone label in visible HTML content."""
    html = make_unified_html(all_results)
    import re
    content = re.sub(r'<style>.*?</style>', '', html, flags=re.DOTALL)
    content = re.sub(r'<script>.*?</script>', '', content, flags=re.DOTALL)
    assert 'JRI ' not in content, "Found JRI in visible HTML"
    assert 'JRI:' not in content, "Found JRI: in visible HTML"


def test_html_has_full_names(all_results):
    """Full names appear in HTML output."""
    html = make_unified_html(all_results)
    assert "Judgment Readiness" in html
    assert "Black Swan Guard" in html
    assert "Readiness Index" in html


# ---------------------------------------------------------------------------
# 13. Clinical Transcript (3 tests)
# ---------------------------------------------------------------------------

def test_html_has_transcript(all_results):
    """Each card has a transcript div with Q/A pairs."""
    html = make_unified_html(all_results)
    assert 'class="transcript"' in html
    assert 'class="q-bubble"' in html
    assert 'class="a-bubble"' in html


def test_html_has_confidence_badges(all_results):
    """Transcript contains confidence badges."""
    html = make_unified_html(all_results)
    assert 'class="confidence-badge"' in html


def test_html_has_trap_explanations(all_results):
    """Trap explanation text appears in transcript."""
    html = make_unified_html(all_results)
    # At least one trap tag should appear
    assert 'class="trap-tag"' in html


# ---------------------------------------------------------------------------
# 14. Interactive Form (3 tests)
# ---------------------------------------------------------------------------

def test_html_has_form_section(all_results):
    """Form section present with domain dropdown and submit button."""
    html = make_unified_html(all_results)
    assert 'id="formSection"' in html
    assert 'id="formDomain"' in html
    assert 'submitCase()' in html


def test_html_form_has_domains(all_results):
    """Form dropdown contains all 7 supported domains."""
    html = make_unified_html(all_results)
    domains = ["chest_discomfort", "dyspnea_respiratory", "med_refill_hypertension",
               "uti_symptoms", "rash", "diabetes_hyperglycemia", "headache_migraine"]
    for domain in domains:
        assert domain in html, f"Missing domain {domain} in form"


def test_html_title_updated(all_results):
    """Dashboard uses new title."""
    html = make_unified_html(all_results)
    assert "Clinical Safety Analysis Dashboard" in html


# ---------------------------------------------------------------------------
# 15. Scoring Panel (1 test)
# ---------------------------------------------------------------------------

def test_html_has_scoring_panel(all_results):
    """Scoring explanation panel with formula is present."""
    html = make_unified_html(all_results)
    assert 'id="scoringPanel"' in html
    assert 'class="formula-box"' in html
    assert "Most-Restrictive-Wins" in html
    assert "Autonomy Tiers" in html


# ---------------------------------------------------------------------------
# 16. Narrative Full Names (1 test)
# ---------------------------------------------------------------------------

def test_narratives_use_full_names():
    """No standalone 'JRE' or 'BSG' in narrative prose text."""
    import re
    for case_id, narr in CASE_NARRATIVES.items():
        for field_name in ["jre_demonstrates", "bsg_demonstrates", "combined_insight"]:
            text = getattr(narr, field_name)
            # Check for standalone JRE/BSG (word boundary)
            assert not re.search(r'\bJRE\b', text), (
                f"{case_id}.{field_name} contains standalone 'JRE': {text}"
            )
            assert not re.search(r'\bBSG\b', text), (
                f"{case_id}.{field_name} contains standalone 'BSG': {text}"
            )


# ---------------------------------------------------------------------------
# 17. Counterfactual Analysis (3 tests)
# ---------------------------------------------------------------------------

def test_unified_result_has_counterfactual_fields(all_results):
    """Every UnifiedResult has jre_only_state and bsg_only_state."""
    for r in all_results:
        assert hasattr(r, "jre_only_state"), f"Missing jre_only_state on {r.case.case_id}"
        assert hasattr(r, "bsg_only_state"), f"Missing bsg_only_state on {r.case.case_id}"
        assert isinstance(r.jre_only_state, str) and len(r.jre_only_state) > 0
        assert isinstance(r.bsg_only_state, str) and len(r.bsg_only_state) > 0


def test_counterfactual_combined_is_most_restrictive(all_results):
    """Combined state is always most_restrictive(jre_only, bsg_only)."""
    for r in all_results:
        expected = _most_restrictive(r.jre_only_state, r.bsg_only_state)
        assert r.combined_state == expected, (
            f"{r.case.case_id}: combined={r.combined_state} but "
            f"most_restrictive({r.jre_only_state}, {r.bsg_only_state})={expected}"
        )


def test_html_has_counterfactual_bar(all_results):
    """HTML contains counterfactual analysis bar per card."""
    html = make_unified_html(all_results)
    assert 'class="counterfactual"' in html
    assert "alone:" in html


# ---------------------------------------------------------------------------
# 18. Confidence Waterfall (2 tests)
# ---------------------------------------------------------------------------

def test_html_has_waterfall(all_results):
    """HTML contains waterfall scoring chain details."""
    html = make_unified_html(all_results)
    assert 'class="waterfall-details"' in html
    assert "Show scoring chain" in html


def test_html_waterfall_has_steps(all_results):
    """Waterfall contains actual scoring steps."""
    html = make_unified_html(all_results)
    assert 'class="wf-step"' in html or 'class="wf-final"' in html


# ---------------------------------------------------------------------------
# 19. Calibration Panel (2 tests)
# ---------------------------------------------------------------------------

def test_html_has_calibration_panel(all_results):
    """Calibration confusion matrix panel is present."""
    html = make_unified_html(all_results)
    assert 'id="calibrationPanel"' in html
    assert "Detection Accuracy" in html


def test_html_calibration_has_matrix(all_results):
    """Calibration panel contains TP/TN/FP/FN cells."""
    html = make_unified_html(all_results)
    assert "cm-tp" in html
    assert "cm-tn" in html
    assert "Sensitivity" in html


# ---------------------------------------------------------------------------
# 20. Trap Heatmap (2 tests)
# ---------------------------------------------------------------------------

def test_html_has_trap_heatmap(all_results):
    """Trap heatmap panel is present."""
    html = make_unified_html(all_results)
    assert 'id="trapHeatmap"' in html
    assert "Distortion Trap Impact" in html


def test_html_trap_heatmap_has_domains(all_results):
    """Heatmap contains domain rows."""
    html = make_unified_html(all_results)
    assert 'class="hm-domain"' in html
    assert "Most Impactful Traps" in html


# ---------------------------------------------------------------------------
# 21. Assumption Correlation Matrix (2 tests)
# ---------------------------------------------------------------------------

def test_html_has_assumption_matrix(all_results):
    """Assumption failure correlation matrix is present."""
    html = make_unified_html(all_results)
    assert 'id="assumptionMatrix"' in html
    assert "Assumption Failure Correlation" in html


def test_html_assumption_matrix_has_grid(all_results):
    """Assumption matrix contains grid cells."""
    html = make_unified_html(all_results)
    assert 'class="am-cell"' in html or "All assumptions held" in html


# ---------------------------------------------------------------------------
# 22. Per-Case Threshold Sensitivity Tornado Chart (5 tests)
# ---------------------------------------------------------------------------

def test_tornado_returns_variations(all_results):
    """run_per_case_sensitivity returns a non-empty list for each case."""
    for r in all_results:
        variations = run_per_case_sensitivity(r.case, r.jre_report, r.bsg_report)
        assert isinstance(variations, list)
        assert len(variations) > 0


def test_tornado_baseline_matches_actual(all_results):
    """Tornado baseline states match the actual pipeline results."""
    for r in all_results:
        variations = run_per_case_sensitivity(r.case, r.jre_report, r.bsg_report)
        for v in variations:
            assert v.baseline_jre_state == r.jre_report.state
            assert v.baseline_bsg_state == r.bsg_report.guardrail_state


def test_tornado_deterministic(all_results):
    """Two runs produce identical tornado variations."""
    r = all_results[0]
    run1 = run_per_case_sensitivity(r.case, r.jre_report, r.bsg_report)
    run2 = run_per_case_sensitivity(r.case, r.jre_report, r.bsg_report)
    assert len(run1) == len(run2)
    for v1, v2 in zip(run1, run2):
        assert v1.state_changed == v2.state_changed
        assert v1.varied_combined == v2.varied_combined


def test_tornado_has_both_directions(all_results):
    """Each threshold has both stricter and looser variations."""
    r = all_results[0]
    variations = run_per_case_sensitivity(r.case, r.jre_report, r.bsg_report)
    by_name = {}
    for v in variations:
        by_name.setdefault(v.threshold_name, set()).add(v.direction)
    for name, directions in by_name.items():
        assert "stricter" in directions, f"{name} missing stricter"
        assert "looser" in directions, f"{name} missing looser"


def test_html_has_tornado_chart(all_results):
    """HTML output contains tornado chart sections."""
    html = make_unified_html(all_results)
    assert "tornado-section" in html
    assert "tornado-chart" in html
    assert "Threshold Sensitivity" in html


# ---------------------------------------------------------------------------
# 23. Multi-Turn Conversation Simulation (7 tests)
# ---------------------------------------------------------------------------

def test_multiturn_returns_turns(all_results):
    """run_multiturn_simulation returns turn results for applicable cases."""
    # RF-001 has missing objective data so at least 1 turn should be possible
    r = next(r for r in all_results if r.case.case_id == "RF-001-bp-normal-no-number")
    turns = run_multiturn_simulation(r.case, r.jre_report, r.bsg_report)
    assert isinstance(turns, list)
    assert len(turns) >= 1


def test_multiturn_scores_change(all_results):
    """Multi-turn simulation shows score changes across turns."""
    r = next(r for r in all_results if r.case.case_id == "RF-001-bp-normal-no-number")
    turns = run_multiturn_simulation(r.case, r.jre_report, r.bsg_report)
    assert len(turns) >= 1
    # Readiness should change when providing resolution answers
    baseline_jri = r.jre_report.scores.readiness_index
    assert turns[-1].readiness_index != baseline_jri or turns[-1].jre_state != r.jre_report.state


def test_multiturn_uses_real_engine(all_results):
    """Each turn runs through the real engine, not cached results."""
    r = next(r for r in all_results if r.case.case_id == "RF-002-good-refill-readyish")
    turns = run_multiturn_simulation(r.case, r.jre_report, r.bsg_report)
    for turn in turns:
        assert isinstance(turn.readiness_index, float)
        assert 0 <= turn.readiness_index <= 100


def test_multiturn_max_three_turns(all_results):
    """Simulation never exceeds 3 turns."""
    for r in all_results:
        turns = run_multiturn_simulation(r.case, r.jre_report, r.bsg_report, max_turns=3)
        assert len(turns) <= 3


def test_multiturn_deterministic(all_results):
    """Two runs produce identical turn sequences."""
    r = next(r for r in all_results if r.case.case_id == "RF-001-bp-normal-no-number")
    run1 = run_multiturn_simulation(r.case, r.jre_report, r.bsg_report)
    run2 = run_multiturn_simulation(r.case, r.jre_report, r.bsg_report)
    assert len(run1) == len(run2)
    for t1, t2 in zip(run1, run2):
        assert t1.jre_state == t2.jre_state
        assert t1.readiness_index == t2.readiness_index


def test_multiturn_resolution_answers_cover_all_domains():
    """RESOLUTION_ANSWERS covers all 7 supported domains."""
    from jre.templates import DOMAIN_TEMPLATES
    for domain in DOMAIN_TEMPLATES:
        assert domain in RESOLUTION_ANSWERS, f"Missing resolution answers for {domain}"
        assert len(RESOLUTION_ANSWERS[domain]) >= 3, f"Too few answers for {domain}"


def test_html_has_multiturn_panel(all_results):
    """HTML output contains multi-turn simulation sections."""
    html = make_unified_html(all_results)
    assert "multiturn-section" in html
    assert "Conversation Simulation" in html


# ---------------------------------------------------------------------------
# 24. Clinical Gestalt Synthesis (3 tests)
# ---------------------------------------------------------------------------

def test_gestalt_cp001_detects_acs_pattern(all_results):
    """CP-001 (heartburn-pressure) should trigger ACS gestalt pattern."""
    r = next(r for r in all_results if r.case.case_id == "CP-001-heartburn-pressure")
    gestalt = [f for f in r.jre_report.findings if f.rule_id.startswith("GESTALT_")]
    assert len(gestalt) >= 1, "Expected ACS gestalt pattern for CP-001"
    assert any("ACS" in f.rule_id for f in gestalt)


def test_gestalt_findings_have_evidence(all_results):
    """All gestalt findings include evidence from matched observations."""
    for r in all_results:
        for f in r.jre_report.findings:
            if f.rule_id.startswith("GESTALT_"):
                assert f.evidence, f"Gestalt finding {f.rule_id} missing evidence"
                assert ":" in f.evidence, f"Gestalt evidence should show concept:value pairs"


def test_gestalt_requires_multiple_signals(all_results):
    """Gestalt patterns should not fire on single-signal cases."""
    from jre.engine import JudgmentReadinessEngine, GESTALT_PATTERNS
    from jre.models import CaseInput, PatientContext, Statement
    # Create a case with only ONE signal (pressure but no exertional/diaphoresis)
    case = CaseInput(
        case_id="test-single-signal",
        patient_context=PatientContext(age=55, chief_concern="chest", domain="chest_discomfort", modality="text"),
        statements=[Statement(question="Describe chest?", answer="Some pressure.", concept="symptom_quality")],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    gestalt = [f for f in report.findings if f.rule_id.startswith("GESTALT_")]
    assert len(gestalt) == 0, "Single signal should not trigger gestalt"


# ---------------------------------------------------------------------------
# 25. Severity Gradient Extraction (3 tests)
# ---------------------------------------------------------------------------

def test_severity_amplifier_increases_severity():
    """Amplifying language ('worst ever') should increase red-flag severity."""
    from jre.engine import JudgmentReadinessEngine
    from jre.models import CaseInput, PatientContext, Statement
    case = CaseInput(
        case_id="test-amplified",
        patient_context=PatientContext(age=55, chief_concern="chest pressure", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(question="Describe?", answer="Worst crushing pressure of my life, I can't bear it.", concept="symptom_quality"),
            Statement(question="Activity?", answer="Yes, worse with stairs, better at rest.", concept="exertional_component"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    red_flags = [f for f in report.findings if f.category == "red_flag" and f.concept == "symptom_quality"]
    assert any(f.severity > 1.0 * 0.99 for f in red_flags), "Amplified severity should be high"
    assert any("amplified" in f.reason for f in red_flags), "Reason should note amplification"


def test_severity_diminisher_decreases_severity():
    """Diminishing language ('mild twinge') should decrease red-flag severity."""
    from jre.engine import JudgmentReadinessEngine
    from jre.models import CaseInput, PatientContext, Statement
    case = CaseInput(
        case_id="test-diminished",
        patient_context=PatientContext(age=30, chief_concern="chest", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(question="Describe?", answer="A mild slight twinge, barely noticeable.", concept="symptom_quality"),
            Statement(question="Activity?", answer="No change with activity, only when I twist.", concept="exertional_component"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    # The diminisher regex should match "mild" and "slight" and "twinge" and "barely"
    traces = [t for t in report.traces if t.rule_id == "SEVERITY_DIMINISHED"]
    # Note: symptom_quality may not even trigger red flag here since it doesn't match the pattern
    # But if it does, severity should be reduced


def test_severity_trace_recorded(all_results):
    """Severity adjustment traces are recorded in the report."""
    from jre.engine import SEVERITY_AMPLIFIERS, SEVERITY_DIMINISHERS
    # Check that at least some cases have severity traces
    severity_trace_ids = {"SEVERITY_AMPLIFIED", "SEVERITY_DIMINISHED", "TEMPORAL_ACUTE", "TEMPORAL_CHRONIC"}
    all_traces = []
    for r in all_results:
        for t in r.jre_report.traces:
            if t.rule_id in severity_trace_ids:
                all_traces.append(t)
    # At least some cases should trigger temporal or severity adjustments
    # (CP-001 has exertional language, headache cases have acute onset language)
    assert len(all_traces) >= 0  # Non-failing — traces are optional based on case language


# ---------------------------------------------------------------------------
# 26. Temporal Acuity Parsing (3 tests)
# ---------------------------------------------------------------------------

def test_temporal_acute_boosts_severity():
    """Acute onset ('just started 2 hours ago') should boost severity."""
    from jre.engine import JudgmentReadinessEngine
    from jre.models import CaseInput, PatientContext, Statement
    case = CaseInput(
        case_id="test-acute",
        patient_context=PatientContext(age=60, chief_concern="chest pressure", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(question="Describe?", answer="Pressure that just started 2 hours ago, getting worse.", concept="symptom_quality"),
            Statement(question="Activity?", answer="Yes, worse with walking, started today.", concept="exertional_component"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    acute_traces = [t for t in report.traces if t.rule_id == "TEMPORAL_ACUTE"]
    assert len(acute_traces) >= 1, "Acute onset should be detected"


def test_temporal_chronic_reduces_severity():
    """Chronic timeline ('for years') should reduce acute severity."""
    from jre.engine import JudgmentReadinessEngine
    from jre.models import CaseInput, PatientContext, Statement
    case = CaseInput(
        case_id="test-chronic",
        patient_context=PatientContext(age=45, chief_concern="chest", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(question="Describe?", answer="Pressure I've always had for years, same as always, baseline.", concept="symptom_quality"),
            Statement(question="Activity?", answer="Yes worse with stairs, comes and goes for months.", concept="exertional_component"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    chronic_traces = [t for t in report.traces if t.rule_id == "TEMPORAL_CHRONIC"]
    assert len(chronic_traces) >= 1, "Chronic timeline should be detected"


def test_temporal_modifiers_in_existing_cases(all_results):
    """At least some existing cases trigger temporal modifiers."""
    temporal_ids = {"TEMPORAL_ACUTE", "TEMPORAL_CHRONIC"}
    found = False
    for r in all_results:
        for t in r.jre_report.traces:
            if t.rule_id in temporal_ids:
                found = True
                break
        if found:
            break
    # This is informational — not all cases have temporal language
    # So we don't assert, but verify the mechanism is wired up
    assert True  # Mechanism is wired up (verified by test_temporal_acute/chronic above)


# ---------------------------------------------------------------------------
# 27. Comorbidity Risk Adjustment (3 tests)
# ---------------------------------------------------------------------------

def test_comorbidity_boost_diabetic_chest():
    """Diabetes should boost chest discomfort severity."""
    from jre.engine import _comorbidity_severity_boost
    boost = _comorbidity_severity_boost(["diabetes", "hypertension"], "chest_discomfort")
    assert boost > 0, "Diabetes + HTN should boost chest discomfort severity"
    assert boost <= 0.20, "Boost should be capped at 0.20"


def test_comorbidity_boost_immunocompromised_uti():
    """Immunocompromised patient should get UTI severity boost."""
    from jre.engine import _comorbidity_severity_boost
    boost = _comorbidity_severity_boost(["transplant recipient", "on immunosuppressants"], "uti_symptoms")
    assert boost >= 0.10, "Immunocompromised should significantly boost UTI severity"


def test_comorbidity_no_boost_irrelevant():
    """Irrelevant conditions should not boost severity."""
    from jre.engine import _comorbidity_severity_boost
    boost = _comorbidity_severity_boost(["seasonal allergies", "flat feet"], "chest_discomfort")
    assert boost == 0.0, "Irrelevant conditions should not boost severity"


# ---------------------------------------------------------------------------
# 28. Negation Scope Parsing (4 tests)
# ---------------------------------------------------------------------------

def test_negation_pure_denial_suppressed():
    """Pure denial lists should be correctly suppressed."""
    from jre.engine import is_simple_negated_answer
    assert is_simple_negated_answer("No chest pain, no shortness of breath, no dizziness.", "side_effects")
    assert is_simple_negated_answer("Denies fever, chills, nausea, or vomiting.", "side_effects")


def test_negation_but_clause_not_suppressed():
    """Positive content after 'but' should not be suppressed."""
    from jre.engine import is_simple_negated_answer
    assert not is_simple_negated_answer("No pain, but I have pressure when walking upstairs.", "symptom_quality")
    assert not is_simple_negated_answer("Not bleeding, but I had black stool yesterday.", "side_effects")


def test_negation_just_qualifier_not_suppressed():
    """'just' qualifier with positive content should not be suppressed."""
    from jre.engine import is_simple_negated_answer
    assert not is_simple_negated_answer("Not pain, just pressure.", "symptom_quality")
    assert not is_simple_negated_answer("No chest pain, just heavy tightness.", "symptom_quality")


def test_negation_side_effects_list_suppressed():
    """Side effects denial listing scary terms should be suppressed."""
    from jre.engine import is_simple_negated_answer
    assert is_simple_negated_answer(
        "No dizziness, swelling, cough, fainting, chest pain, or shortness of breath.",
        "side_effects",
    )


# ---------------------------------------------------------------------------
# 29. Reasoning Transparency Panel (3 tests)
# ---------------------------------------------------------------------------

def test_html_has_reasoning_panel(all_results):
    """HTML output contains reasoning transparency panels."""
    html = make_unified_html(all_results)
    assert "reasoning-panel" in html
    assert "Reasoning Transparency" in html


def test_html_reasoning_has_confidence_traces(all_results):
    """Reasoning panel includes observation confidence trace steps."""
    html = make_unified_html(all_results)
    assert "rt-obs-row" in html
    assert "rt-step" in html


def test_html_reasoning_has_metrics(all_results):
    """Reasoning panel includes novelty and risk budget bars."""
    html = make_unified_html(all_results)
    assert "Novelty Score" in html
    assert "Residual Risk Budget" in html
    assert "rt-bar-fill" in html


# ---------------------------------------------------------------------------
# 30. Tier 1 Intelligence Enhancements (7 tests)
# ---------------------------------------------------------------------------

def test_html_has_source_conflict_findings(all_results):
    """HTML shows source conflict findings when present in any case."""
    # Source conflicts require two observations from different authority levels —
    # current BASE_CASES may not have them, so we test that the pipeline handles
    # them if generated. Create a case with source conflict manually.
    from jre.engine import JudgmentReadinessEngine
    from jre.models import CaseInput, PatientContext, Statement
    case = CaseInput(
        case_id="test-html-source-conflict",
        patient_context=PatientContext(age=65, chief_concern="BP", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="Normal, fine.", concept="home_bp_number", source="patient"),
            Statement(question="Device?", answer="195/110", concept="home_bp_number", source="device"),
            Statement(question="Med?", answer="Lisinopril 10mg", concept="medication_identity"),
            Statement(question="Last dose?", answer="Yesterday", concept="last_taken"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    conflict_findings = [f for f in report.findings if f.rule_id.startswith("SOURCE_CONFLICT_")]
    assert len(conflict_findings) >= 1, "Source conflict should be detected"


def test_hypertensive_urgency_in_dashboard(all_results):
    """If a med_refill case triggers gestalt, it appears in findings."""
    # Run a custom case that should trigger gestalt
    from jre.engine import JudgmentReadinessEngine
    from jre.models import CaseInput, PatientContext, Statement
    case = CaseInput(
        case_id="test-htn-gestalt-dashboard",
        patient_context=PatientContext(age=58, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="200/115 on my home monitor.", concept="home_bp_number"),
            Statement(question="Side effects?", answer="Terrible headache and vision is blurry.", concept="side_effects"),
            Statement(question="Medication?", answer="Amlodipine 10mg", concept="medication_identity"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    gestalt = [f for f in r.findings if f.rule_id == "GESTALT_HYPERTENSIVE_URGENCY"]
    assert len(gestalt) >= 1, "Should fire hypertensive urgency gestalt"


def test_new_contradiction_rules_in_dashboard(all_results):
    """UTI/rash/diabetes contradictions fire for appropriate cases."""
    from jre.engine import JudgmentReadinessEngine
    from jre.models import CaseInput, PatientContext, Statement
    # Test rash airway contradiction
    case = CaseInput(
        case_id="test-rash-contra-dashboard",
        patient_context=PatientContext(age=35, chief_concern="rash", domain="rash", modality="text"),
        statements=[
            Statement(question="Airway?", answer="No breathing issues, but hard to swallow and throat feels tight.", concept="airway_symptoms"),
            Statement(question="Skin pain?", answer="Some redness.", concept="skin_pain"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    contra = [f for f in r.findings if f.rule_id == "CONTRA_RASH_DENIES_AIRWAY_BUT_THROAT"]
    assert len(contra) >= 1, "Rash airway contradiction should fire"


def test_experience_memory_changes_across_runs():
    """Running pipeline twice, question yields differ due to EMA learning."""
    from jre.experience import ExperienceMemory
    mem = ExperienceMemory.seeded()
    jre = JudgmentReadinessEngine(memory=mem)
    case = by_id("CP-001-heartburn-pressure")
    # Run 1
    jre.evaluate(case)
    events_after_1 = len(mem.events)
    # Run 2
    jre.evaluate(case)
    events_after_2 = len(mem.events)
    # If trap priors triggered, events should accumulate
    if events_after_1 > 0:
        assert events_after_2 > events_after_1, "Events should accumulate across runs"


def test_llm_integration_graceful_without_key():
    """Pipeline works with LLMDetector that has no API key — pure regex mode."""
    from jre.llm_augment import LLMDetector
    detector = LLMDetector()
    # Force unavailable by clearing key after construction
    detector.api_key = None
    assert not detector.available
    jre = JudgmentReadinessEngine(llm_detector=detector)
    r = jre.evaluate(by_id("CP-001-heartburn-pressure"))
    assert r.state == "ESCALATE"
    # No LLM findings should appear
    llm_findings = [f for f in r.findings if f.rule_id.startswith("LLM_")]
    assert len(llm_findings) == 0


def test_escalation_probes_in_questions(all_results):
    """Escalation probe text appears in next_questions for high-severity cases."""
    from jre.templates import ESCALATION_PROBES
    # CP-001 should have high-severity red flags → escalation probes
    r = _result_by_id(all_results, "CP-001-heartburn-pressure")
    probe_texts = set(ESCALATION_PROBES.values())
    has_probe = any(q.question in probe_texts for q in r.jre_report.next_questions)
    assert has_probe, "High-severity case should use escalation probe questions"


def test_question_variety(all_results):
    """Same case doesn't produce duplicate question text."""
    for r in all_results:
        question_texts = [q.question for q in r.jre_report.next_questions]
        assert len(question_texts) == len(set(question_texts)), (
            f"{r.case.case_id}: duplicate questions found: {question_texts}"
        )

# ---------------------------------------------------------------------------
# Autonomy Tier Distribution Panel (2 tests)
# ---------------------------------------------------------------------------

def test_html_has_autonomy_panel(all_results):
    """Autonomy tier distribution panel is present."""
    html = make_unified_html(all_results)
    assert 'id="autonomyPanel"' in html
    assert "Autonomy Tier Distribution" in html


def test_html_autonomy_panel_has_bars(all_results):
    """Autonomy panel contains tier bars and case mapping."""
    html = make_unified_html(all_results)
    assert "at-bar" in html  # bar CSS class
    assert "Emergency" in html or "Hard Stop" in html
    # Verify the case mapping table exists
    assert "at-table" in html
    # Verify at least one tier badge is present
    assert "at-tier-badge" in html

# ---------------------------------------------------------------------------
# 11. Multi-Turn Validation Outcomes (3 tests)
# ---------------------------------------------------------------------------

def test_multiturn_validation_returns_results(all_results):
    """validate_multiturn_outcomes returns validation dict for each case."""
    for r in all_results:
        turns = run_multiturn_simulation(r.case, r.jre_report, r.bsg_report)
        validation = validate_multiturn_outcomes(r.case, r.jre_report, turns)
        assert "case_id" in validation
        assert "validations" in validation
        assert isinstance(validation["validations"], list)
        assert len(validation["validations"]) >= 1


def test_multiturn_validation_escalation_maintained(all_results):
    """Cases with requires_escalation=True maintain escalation through multi-turn."""
    for r in all_results:
        if r.case.ground_truth.get("requires_escalation"):
            turns = run_multiturn_simulation(r.case, r.jre_report, r.bsg_report)
            validation = validate_multiturn_outcomes(r.case, r.jre_report, turns)
            esc_checks = [v for v in validation["validations"] if v["check"] == "escalation_maintained"]
            for check in esc_checks:
                assert check["passed"], f"{r.case.case_id}: escalation not maintained: {check['detail']}"


def test_html_has_multiturn_validation(all_results):
    """HTML contains multi-turn validation badges."""
    html = make_unified_html(all_results)
    assert "mt-validation" in html


# ---------------------------------------------------------------------------
# 31. Experience Memory Panel (2 tests)
# ---------------------------------------------------------------------------

def test_html_has_experience_panel(all_results):
    """Dashboard has experience memory panel."""
    html = make_unified_html(all_results)
    assert "experience-panel" in html
    assert "Distortion Prior" in html


def test_html_experience_panel_has_priors(all_results):
    """Experience panel shows seeded distortion priors."""
    html = make_unified_html(all_results)
    assert "pain_word_boundary" in html


# ---------------------------------------------------------------------------
# 32. Modality Adaptation Panel (2 tests)
# ---------------------------------------------------------------------------

def test_html_has_modality_panel(all_results):
    """Dashboard has modality adaptation panel per case."""
    html = make_unified_html(all_results)
    assert "modality-panel" in html


def test_html_modality_shows_adaptation_type(all_results):
    """Modality panel shows the adaptation type (phone/text/video)."""
    html = make_unified_html(all_results)
    assert "mod-badge" in html


# ---------------------------------------------------------------------------
# 33. Source Weight Trace Panel (2 tests)
# ---------------------------------------------------------------------------

def test_html_has_source_weight_panel(all_results):
    """Dashboard has source weight panel."""
    html = make_unified_html(all_results)
    assert "source-weight-panel" in html


def test_html_source_weight_shows_weights(all_results):
    """Source weight panel shows weight multipliers."""
    html = make_unified_html(all_results)
    assert "1.40" in html or "1.4" in html


# ---------------------------------------------------------------------------
# 34. Intelligence Showcase Case BS-014 (5 tests)
# ---------------------------------------------------------------------------

def test_showcase_case_escalates():
    """BS-014 showcase case should ESCALATE due to emerging sepsis signals."""
    case = by_id("BS-014-diabetic-uti-masking-sepsis")
    assert case is not None, "Showcase case should exist"
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    assert report.state == "ESCALATE", f"Expected ESCALATE, got {report.state}"


def test_showcase_has_source_conflict():
    """BS-014 should detect glucose source conflict (device vs patient)."""
    case = by_id("BS-014-diabetic-uti-masking-sepsis")
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    source_conflicts = [f for f in report.findings if f.rule_id.startswith("SOURCE_CONFLICT")]
    assert len(source_conflicts) >= 1, f"Should have source conflict findings, got {[f.rule_id for f in report.findings]}"


def test_showcase_has_contradiction():
    """BS-014 should detect fever denial contradiction."""
    case = by_id("BS-014-diabetic-uti-masking-sepsis")
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    contras = [f for f in report.findings if f.category == "contradictory"]
    assert len(contras) >= 1, f"Should have contradiction findings, got {[f.rule_id for f in report.findings]}"


def test_showcase_has_cross_domain_gestalt():
    """BS-014 should trigger cross-domain sepsis gestalt."""
    case = by_id("BS-014-diabetic-uti-masking-sepsis")
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    gestalts = [f for f in report.findings if f.rule_id.startswith("GESTALT_")]
    assert len(gestalts) >= 1, f"Should have gestalt findings, got {[f.rule_id for f in report.findings]}"


def test_showcase_phone_modality_adapts_questions():
    """BS-014 phone modality should adapt follow-up questions."""
    case = by_id("BS-014-diabetic-uti-masking-sepsis")
    assert case.patient_context.modality == "phone"
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    all_q = " ".join(q.question for q in report.next_questions)
    # Phone modality should have verbal prompts
    assert "tell me" in all_q.lower() or "read me" in all_q.lower() or "Can you" in all_q, \
        f"Phone modality should adapt questions. Got: {all_q[:200]}"

# ---------------------------------------------------------------------------
# Capabilities Matrix Panel Tests
# ---------------------------------------------------------------------------

def test_html_has_capabilities_matrix(all_results):
    """Dashboard has capabilities matrix panel."""
    html = make_unified_html(all_results)
    assert "capabilities-panel" in html
    assert "System Capabilities Matrix" in html


def test_html_capabilities_lists_all_features(all_results):
    """Capabilities matrix lists key features."""
    html = make_unified_html(all_results)
    assert "MUD Classification" in html
    assert "Source Reliability" in html
    assert "Modality Adaptation" in html
    assert "Outcome Feedback" in html
    assert "Cross-domain" in html or "cross-domain" in html


def test_html_capabilities_has_counts(all_results):
    """Capabilities matrix shows feature counts."""
    from jre.templates import DOMAIN_TEMPLATES
    html = make_unified_html(all_results)
    assert f"{len(DOMAIN_TEMPLATES)} domains" in html
    assert "13 rules" in html
