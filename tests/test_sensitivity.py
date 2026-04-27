"""Tests for threshold sensitivity analysis."""
from jre.sensitivity import (
    run_sensitivity_analysis,
    sensitivity_to_markdown,
    sensitivity_to_csv,
    get_all_cases,
    THRESHOLD_VARIATIONS,
)


def test_analysis_runs_without_error():
    """Full sensitivity analysis completes on all cases."""
    cases = get_all_cases()
    baseline, results = run_sensitivity_analysis(cases)
    assert len(baseline) == len(cases)
    assert len(results) == len(THRESHOLD_VARIATIONS)


def test_baseline_has_all_fields():
    """Each baseline result has expected fields."""
    cases = get_all_cases()
    baseline, _ = run_sensitivity_analysis(cases)
    for r in baseline:
        assert "case_id" in r
        assert "jre_state" in r
        assert "bsg_state" in r
        assert "jri" in r


def test_variations_report_changes():
    """Each variation correctly reports state changes vs baseline."""
    cases = get_all_cases()
    _, results = run_sensitivity_analysis(cases)
    for sr in results:
        assert sr.total_cases == len(cases)
        assert 0 <= sr.state_changes <= sr.total_cases
        assert 0.0 <= sr.change_rate <= 1.0


def test_strict_thresholds_are_more_restrictive():
    """Strict thresholds should generally change at least as many states as loose ones."""
    cases = get_all_cases()
    _, results = run_sensitivity_analysis(cases)
    # At least one strict variation should cause changes
    strict = [r for r in results if "strict" in r.variation.name.lower()]
    assert any(r.state_changes > 0 for r in strict), "No strict threshold caused any state changes"


def test_markdown_output_valid():
    """Markdown output is non-empty and contains expected sections."""
    cases = get_all_cases()
    baseline, results = run_sensitivity_analysis(cases)
    md = sensitivity_to_markdown(baseline, results)
    assert "# Threshold Sensitivity Analysis" in md
    assert "## Summary" in md
    assert "Cases Changed" in md


def test_csv_output_valid():
    """CSV output has header and data rows."""
    cases = get_all_cases()
    baseline, results = run_sensitivity_analysis(cases)
    csv_text = sensitivity_to_csv(baseline, results)
    lines = csv_text.strip().split("\n")
    assert len(lines) > 1  # header + at least some data
    assert "variation_name" in lines[0]


def test_new_variations_included():
    """THRESHOLD_VARIATIONS includes the new source_conflict and gestalt entries."""
    param_names = {v.parameter for v in THRESHOLD_VARIATIONS}
    assert "source_conflict_severity" in param_names, (
        "source_conflict_severity not found in THRESHOLD_VARIATIONS"
    )
    assert "gestalt_min_required" in param_names, (
        "gestalt_min_required not found in THRESHOLD_VARIATIONS"
    )


def test_source_conflict_severity_variations_run():
    """Source conflict severity variations complete without error."""
    cases = get_all_cases()
    sc_variations = [v for v in THRESHOLD_VARIATIONS if v.parameter == "source_conflict_severity"]
    assert len(sc_variations) >= 2, "Expected at least strict and loose source_conflict_severity"
    baseline, results = run_sensitivity_analysis(cases, sc_variations)
    assert len(results) == len(sc_variations)
    for sr in results:
        assert sr.total_cases == len(cases)
        for r in sr.case_results:
            assert "case_id" in r
            assert "jre_state" in r
            assert "bsg_state" in r


def test_gestalt_min_required_variations_run():
    """Gestalt min_required variations complete without error."""
    cases = get_all_cases()
    gm_variations = [v for v in THRESHOLD_VARIATIONS if v.parameter == "gestalt_min_required"]
    assert len(gm_variations) >= 2, "Expected at least strict and loose gestalt_min_required"
    baseline, results = run_sensitivity_analysis(cases, gm_variations)
    assert len(results) == len(gm_variations)
    for sr in results:
        assert sr.total_cases == len(cases)
        for r in sr.case_results:
            assert "case_id" in r
            assert "jre_state" in r
            assert "bsg_state" in r


def test_gestalt_patterns_restored_after_variation():
    """GESTALT_PATTERNS min_required values are restored after sensitivity run."""
    from jre.engine import GESTALT_PATTERNS

    # Capture original values
    originals = {p["id"]: p["min_required"] for p in GESTALT_PATTERNS}

    # Run the gestalt variations
    cases = get_all_cases()
    gm_variations = [v for v in THRESHOLD_VARIATIONS if v.parameter == "gestalt_min_required"]
    run_sensitivity_analysis(cases, gm_variations)

    # Verify originals are restored
    for p in GESTALT_PATTERNS:
        assert p["min_required"] == originals[p["id"]], (
            f"GESTALT_PATTERNS[{p['id']}].min_required not restored: "
            f"expected {originals[p['id']]}, got {p['min_required']}"
        )


def test_sensitivity_markdown_includes_new_variations():
    """Markdown report includes rows for new variation parameters."""
    cases = get_all_cases()
    baseline, results = run_sensitivity_analysis(cases)
    md = sensitivity_to_markdown(baseline, results)
    assert "source_conflict_severity" in md
    assert "gestalt_min_required" in md
    assert "Source conflict severity" in md
    assert "Gestalt min required" in md


def test_sensitivity_csv_includes_new_variations():
    """CSV output includes rows for new variation parameters."""
    cases = get_all_cases()
    baseline, results = run_sensitivity_analysis(cases)
    csv_text = sensitivity_to_csv(baseline, results)
    assert "source_conflict_severity" in csv_text
    assert "gestalt_min_required" in csv_text
