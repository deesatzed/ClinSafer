"""Tests for the observability/structured logging module."""
import json

from jre import JudgmentReadinessEngine, BlackSwanGuardrailEngine, BLACK_SWAN_CASES
from jre.synthetic_data import BASE_CASES
from jre.observability import PipelineLogger, LogEntry, CaseTrace


def _get_case(case_id):
    all_cases = {c.case_id: c for c in list(BASE_CASES) + list(BLACK_SWAN_CASES)}
    return all_cases[case_id]


def test_logger_traces_case():
    """Logger creates entries for a traced case."""
    logger = PipelineLogger()
    case = _get_case("CP-001-heartburn-pressure")
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)
        bsg_report = guard.evaluate(case, jre_report)
        trace.log_bsg(bsg_report)
        trace.log_combined("ESCALATE", True)

    # Should have: pipeline_start, jre_evaluated, bsg_evaluated, pipeline_complete
    events = [e.event for e in logger.entries]
    assert "pipeline_start" in events
    assert "jre_evaluated" in events
    assert "bsg_evaluated" in events
    assert "pipeline_complete" in events


def test_log_entry_serializable():
    """Log entries serialize to valid JSON."""
    logger = PipelineLogger()
    case = _get_case("RF-002-good-refill-readyish")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    for entry in logger.entries:
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert "event" in parsed
        assert "case_id" in parsed


def test_jre_log_contains_scores():
    """JRE log entry contains key scores."""
    logger = PipelineLogger()
    case = _get_case("CP-001-heartburn-pressure")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    jre_entries = [e for e in logger.entries if e.event == "jre_evaluated"]
    assert len(jre_entries) == 1
    data = jre_entries[0].data
    assert "state" in data
    assert "jri" in data
    assert "finding_count" in data
    assert "rule_ids_fired" in data


def test_bsg_log_contains_assumptions():
    """BSG log entry contains assumption breach info."""
    logger = PipelineLogger()
    case = _get_case("BS-001-refill-wrong-patient")
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)
        bsg_report = guard.evaluate(case, jre_report)
        trace.log_bsg(bsg_report)

    bsg_entries = [e for e in logger.entries if e.event == "bsg_evaluated"]
    assert len(bsg_entries) == 1
    data = bsg_entries[0].data
    assert "guardrail_state" in data
    assert "assumptions_breached" in data


def test_jsonl_output():
    """Logger exports valid JSONL."""
    logger = PipelineLogger()
    case = _get_case("RF-002-good-refill-readyish")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    jsonl = logger.to_jsonl()
    lines = jsonl.strip().split("\n")
    assert len(lines) >= 2  # pipeline_start + jre_evaluated
    for line in lines:
        parsed = json.loads(line)
        assert isinstance(parsed, dict)


def test_summary_counts():
    """Logger summary correctly counts events."""
    logger = PipelineLogger()
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()

    for case_id in ["CP-001-heartburn-pressure", "RF-002-good-refill-readyish"]:
        case = _get_case(case_id)
        with logger.trace_case(case) as trace:
            jre_report = jre.evaluate(case)
            trace.log_jre(jre_report)
            bsg_report = guard.evaluate(case, jre_report)
            trace.log_bsg(bsg_report)
            trace.log_combined("ESCALATE", True)

    summary = logger.summary()
    assert summary["total_entries"] == 8  # 4 events x 2 cases
    assert summary["event_counts"]["pipeline_start"] == 2
    assert summary["event_counts"]["pipeline_complete"] == 2


def test_clear_resets():
    """Logger clear removes all entries."""
    logger = PipelineLogger()
    case = _get_case("CP-001-heartburn-pressure")

    with logger.trace_case(case) as trace:
        pass

    assert len(logger.entries) > 0
    logger.clear()
    assert len(logger.entries) == 0


def test_duration_tracked():
    """Pipeline entries have duration_ms."""
    logger = PipelineLogger()
    case = _get_case("CP-001-heartburn-pressure")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    jre_entries = [e for e in logger.entries if e.event == "jre_evaluated"]
    assert jre_entries[0].duration_ms is not None
    assert jre_entries[0].duration_ms >= 0


# ---------------------------------------------------------------------------
# New tests: intelligence feature fields in log entries
# ---------------------------------------------------------------------------


def test_log_entry_has_source_conflict_count():
    """JRE log entry includes source conflict count for a case with conflicts."""
    logger = PipelineLogger()
    # BS-014 has a SOURCE_CONFLICT_GLUCOSE_NUMBER finding (device vs patient)
    case = _get_case("BS-014-diabetic-uti-masking-sepsis")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    jre_entries = [e for e in logger.entries if e.event == "jre_evaluated"]
    assert len(jre_entries) == 1
    data = jre_entries[0].data
    assert "source_conflict_count" in data
    assert isinstance(data["source_conflict_count"], int)
    assert data["source_conflict_count"] >= 1, (
        f"BS-014 should have at least 1 source conflict, got {data['source_conflict_count']}"
    )


def test_log_entry_has_source_conflict_count_zero():
    """JRE log entry has source_conflict_count=0 when no conflicts exist."""
    logger = PipelineLogger()
    # RF-002 is a clean refill case with no source conflicts
    case = _get_case("RF-002-good-refill-readyish")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    jre_entries = [e for e in logger.entries if e.event == "jre_evaluated"]
    data = jre_entries[0].data
    assert "source_conflict_count" in data
    assert data["source_conflict_count"] == 0


def test_log_entry_has_gestalt_count():
    """JRE log entry includes gestalt pattern count."""
    logger = PipelineLogger()
    # CP-001 triggers GESTALT_ACS (acute coronary syndrome)
    case = _get_case("CP-001-heartburn-pressure")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    jre_entries = [e for e in logger.entries if e.event == "jre_evaluated"]
    assert len(jre_entries) == 1
    data = jre_entries[0].data
    assert "gestalt_count" in data
    assert isinstance(data["gestalt_count"], int)
    assert data["gestalt_count"] >= 1, (
        f"CP-001 should have at least 1 gestalt pattern, got {data['gestalt_count']}"
    )


def test_log_entry_has_gestalt_count_zero():
    """JRE log entry has gestalt_count=0 when no gestalt patterns fire."""
    logger = PipelineLogger()
    # RF-001 does not trigger any gestalt patterns
    case = _get_case("RF-001-bp-normal-no-number")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    jre_entries = [e for e in logger.entries if e.event == "jre_evaluated"]
    data = jre_entries[0].data
    assert "gestalt_count" in data
    assert data["gestalt_count"] == 0


def test_log_entry_has_modality():
    """JRE log entry includes the case modality."""
    logger = PipelineLogger()
    # DY-001 is a phone case
    case = _get_case("DY-001-denies-sob-low-ox")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    jre_entries = [e for e in logger.entries if e.event == "jre_evaluated"]
    data = jre_entries[0].data
    assert "modality" in data
    assert data["modality"] == "phone"


def test_log_entry_has_experience_events_recorded():
    """JRE log entry includes experience events count from observation tags."""
    logger = PipelineLogger()
    # CP-001 triggers experience priors on multiple observations
    case = _get_case("CP-001-heartburn-pressure")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    jre_entries = [e for e in logger.entries if e.event == "jre_evaluated"]
    data = jre_entries[0].data
    assert "experience_events_recorded" in data
    assert isinstance(data["experience_events_recorded"], int)
    assert data["experience_events_recorded"] >= 1, (
        f"CP-001 should have at least 1 experience event, got {data['experience_events_recorded']}"
    )


def test_log_entry_experience_events_zero():
    """JRE log entry has experience_events_recorded=0 when no priors fire."""
    logger = PipelineLogger()
    # RASH-001 has no experience_prior tags on its observations
    case = _get_case("RASH-001-new-med-mouth-sores")
    jre = JudgmentReadinessEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)

    jre_entries = [e for e in logger.entries if e.event == "jre_evaluated"]
    data = jre_entries[0].data
    assert "experience_events_recorded" in data
    assert data["experience_events_recorded"] == 0


def test_bsg_log_has_llm_findings_count():
    """BSG log entry includes llm_findings_count field."""
    logger = PipelineLogger()
    case = _get_case("CP-001-heartburn-pressure")
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)
        bsg_report = guard.evaluate(case, jre_report)
        trace.log_bsg(bsg_report)

    bsg_entries = [e for e in logger.entries if e.event == "bsg_evaluated"]
    assert len(bsg_entries) == 1
    data = bsg_entries[0].data
    assert "llm_findings_count" in data
    assert isinstance(data["llm_findings_count"], int)
    # Without LLM augmentation enabled, this should be 0
    assert data["llm_findings_count"] == 0


def test_log_feedback_via_trace():
    """Feedback event is logged through a CaseTrace."""
    logger = PipelineLogger()
    case = _get_case("CP-001-heartburn-pressure")

    with logger.trace_case(case) as trace:
        trace.log_feedback(
            case_id="CP-001-heartburn-pressure",
            assessment="correct_escalation",
            priors_updated=3,
        )

    feedback_entries = [e for e in logger.entries if e.event == "feedback"]
    assert len(feedback_entries) == 1
    entry = feedback_entries[0]
    # case_id is stored on the LogEntry itself, not in data
    assert entry.case_id == "CP-001-heartburn-pressure"
    assert entry.data["assessment"] == "correct_escalation"
    assert entry.data["priors_updated"] == 3


def test_log_feedback_via_logger():
    """Feedback event is logged directly through PipelineLogger."""
    logger = PipelineLogger()
    logger.log_feedback(
        case_id="RF-001-bp-normal-no-number",
        assessment="missed_finding",
        priors_updated=1,
    )

    feedback_entries = [e for e in logger.entries if e.event == "feedback"]
    assert len(feedback_entries) == 1
    entry = feedback_entries[0]
    assert entry.case_id == "RF-001-bp-normal-no-number"
    assert entry.data["assessment"] == "missed_finding"
    assert entry.data["priors_updated"] == 1


def test_log_feedback_serializable():
    """Feedback log entries serialize to valid JSON."""
    logger = PipelineLogger()
    logger.log_feedback(
        case_id="TEST-001",
        assessment="escalation_was_correct",
        priors_updated=5,
    )

    for entry in logger.entries:
        json_str = entry.to_json()
        parsed = json.loads(json_str)
        assert parsed["event"] == "feedback"
        assert parsed["case_id"] == "TEST-001"
        assert parsed["assessment"] == "escalation_was_correct"
        assert parsed["priors_updated"] == 5


def test_intelligence_fields_in_json_output():
    """New intelligence fields appear in serialized JSONL output."""
    logger = PipelineLogger()
    case = _get_case("CP-001-heartburn-pressure")
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()

    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)
        bsg_report = guard.evaluate(case, jre_report)
        trace.log_bsg(bsg_report)

    jsonl = logger.to_jsonl()
    lines = jsonl.strip().split("\n")

    # Find jre_evaluated line
    jre_line = None
    bsg_line = None
    for line in lines:
        parsed = json.loads(line)
        if parsed.get("event") == "jre_evaluated":
            jre_line = parsed
        if parsed.get("event") == "bsg_evaluated":
            bsg_line = parsed

    assert jre_line is not None
    assert "source_conflict_count" in jre_line
    assert "gestalt_count" in jre_line
    assert "modality" in jre_line
    assert "experience_events_recorded" in jre_line

    assert bsg_line is not None
    assert "llm_findings_count" in bsg_line
