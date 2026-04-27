"""Structured logging and observability for JRE + BSG pipeline.

Provides JSON-structured logging for pipeline decisions, rule firings,
latency tracking, and state transitions. Designed for production monitoring
integration.

Usage:
    from jre.observability import PipelineLogger

    logger = PipelineLogger()
    with logger.trace_case(case) as trace:
        jre_report = jre.evaluate(case)
        trace.log_jre(jre_report)
        bsg_report = guard.evaluate(case, jre_report)
        trace.log_bsg(bsg_report)
    # logger.entries contains all structured log entries
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .models import CaseInput, ReadinessReport
from .black_swan import GuardrailReport


@dataclass
class LogEntry:
    """A single structured log entry."""
    timestamp: float
    event: str
    case_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "timestamp": self.timestamp,
            "event": self.event,
            "case_id": self.case_id,
            **self.data,
        }
        if self.duration_ms is not None:
            d["duration_ms"] = round(self.duration_ms, 2)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class CaseTrace:
    """Trace context for a single case evaluation."""

    def __init__(self, case: CaseInput, logger: PipelineLogger) -> None:
        self.case = case
        self.logger = logger
        self.start_time = time.monotonic()
        self._jre_start: Optional[float] = None
        self._bsg_start: Optional[float] = None

    def log_jre(self, report: ReadinessReport) -> None:
        """Log JRE evaluation results."""
        now = time.monotonic()
        duration = (now - self.start_time) * 1000

        # Rule firings
        rule_ids = list({f.rule_id for f in report.findings})
        finding_categories = list({f.category for f in report.findings})

        # Intelligence feature counts
        source_conflict_count = sum(
            1 for f in report.findings if f.rule_id.startswith("SOURCE_CONFLICT_")
        )
        gestalt_count = sum(
            1 for f in report.findings if f.rule_id.startswith("GESTALT_")
        )
        experience_events_recorded = sum(
            1 for obs in report.observations
            for tag in obs.tags
            if tag.startswith("experience_prior:")
        )

        self.logger._add(LogEntry(
            timestamp=time.time(),
            event="jre_evaluated",
            case_id=self.case.case_id,
            data={
                "state": report.state,
                "jri": report.scores.readiness_index,
                "completeness": report.scores.completeness,
                "reliability": report.scores.reliability,
                "objective_coverage": report.scores.objective_coverage,
                "red_flag_load": report.scores.red_flag_load,
                "contradiction_load": report.scores.contradiction_load,
                "distortion_load": report.scores.distortion_load,
                "finding_count": len(report.findings),
                "question_count": len(report.next_questions),
                "rule_ids_fired": rule_ids,
                "finding_categories": finding_categories,
                "domain": self.case.patient_context.domain,
                "observation_count": len(report.observations),
                "source_conflict_count": source_conflict_count,
                "gestalt_count": gestalt_count,
                "modality": self.case.patient_context.modality,
                "experience_events_recorded": experience_events_recorded,
            },
            duration_ms=duration,
        ))

    def log_bsg(self, report: GuardrailReport) -> None:
        """Log BSG evaluation results."""
        now = time.monotonic()
        duration = (now - self.start_time) * 1000

        rule_ids = [f.rule_id for f in report.findings]
        breached = [a.name for a in report.assumption_register if a.status == "breached"]
        weak = [a.name for a in report.assumption_register if a.status == "weak"]

        llm_findings_count = sum(
            1 for f in report.findings if f.rule_id.startswith("LLM_")
        )

        self.logger._add(LogEntry(
            timestamp=time.time(),
            event="bsg_evaluated",
            case_id=self.case.case_id,
            data={
                "guardrail_state": report.guardrail_state,
                "max_autonomy_tier": report.max_autonomy_tier,
                "novelty_score": report.novelty_score,
                "residual_risk_budget": report.residual_risk_budget,
                "finding_count": len(report.findings),
                "rule_ids_fired": rule_ids,
                "assumptions_breached": breached,
                "assumptions_weak": weak,
                "llm_findings_count": llm_findings_count,
            },
            duration_ms=duration,
        ))

    def log_combined(self, combined_state: str, ground_truth_match: bool) -> None:
        """Log the combined pipeline result."""
        now = time.monotonic()
        duration = (now - self.start_time) * 1000

        self.logger._add(LogEntry(
            timestamp=time.time(),
            event="pipeline_complete",
            case_id=self.case.case_id,
            data={
                "combined_state": combined_state,
                "ground_truth_match": ground_truth_match,
            },
            duration_ms=duration,
        ))

    def log_feedback(self, case_id: str, assessment: str, priors_updated: int) -> None:
        """Log a clinician feedback event."""
        self.logger._add(LogEntry(
            timestamp=time.time(),
            event="feedback",
            case_id=case_id,
            data={
                "assessment": assessment,
                "priors_updated": priors_updated,
            },
        ))

    def log_error(self, error: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Log an error during evaluation."""
        self.logger._add(LogEntry(
            timestamp=time.time(),
            event="pipeline_error",
            case_id=self.case.case_id,
            data={"error": error, **(details or {})},
        ))


class PipelineLogger:
    """Structured logger for the JRE + BSG pipeline.

    Collects structured log entries that can be:
    - Written to a file as JSON lines
    - Sent to a monitoring service
    - Inspected programmatically in tests
    """

    def __init__(self, python_logger: Optional[logging.Logger] = None) -> None:
        self.entries: List[LogEntry] = []
        self._python_logger = python_logger

    def _add(self, entry: LogEntry) -> None:
        self.entries.append(entry)
        if self._python_logger:
            self._python_logger.info(entry.to_json())

    @contextmanager
    def trace_case(self, case: CaseInput):
        """Context manager that creates a case trace."""
        trace = CaseTrace(case, self)
        self._add(LogEntry(
            timestamp=time.time(),
            event="pipeline_start",
            case_id=case.case_id,
            data={
                "domain": case.patient_context.domain,
                "age": case.patient_context.age,
                "statement_count": len(case.statements),
                "modality": case.patient_context.modality,
                "language_barrier": case.patient_context.language_barrier,
            },
        ))
        try:
            yield trace
        except Exception as e:
            trace.log_error(str(e))
            raise

    def log_feedback(self, case_id: str, assessment: str, priors_updated: int) -> None:
        """Log a clinician feedback event (standalone, outside a case trace)."""
        self._add(LogEntry(
            timestamp=time.time(),
            event="feedback",
            case_id=case_id,
            data={
                "assessment": assessment,
                "priors_updated": priors_updated,
            },
        ))

    def to_jsonl(self) -> str:
        """Export all entries as JSON Lines."""
        return "\n".join(entry.to_json() for entry in self.entries)

    def write_jsonl(self, path) -> None:
        """Write all entries to a JSON Lines file."""
        from pathlib import Path
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_jsonl() + "\n", encoding="utf-8")

    def summary(self) -> Dict[str, Any]:
        """Generate a summary of all logged events."""
        events = [e.event for e in self.entries]
        states = {}
        durations = []
        for e in self.entries:
            if e.event == "pipeline_complete":
                state = e.data.get("combined_state", "unknown")
                states[state] = states.get(state, 0) + 1
            if e.duration_ms is not None and e.event == "pipeline_complete":
                durations.append(e.duration_ms)

        return {
            "total_entries": len(self.entries),
            "event_counts": {ev: events.count(ev) for ev in set(events)},
            "state_distribution": states,
            "avg_pipeline_ms": sum(durations) / len(durations) if durations else 0,
            "max_pipeline_ms": max(durations) if durations else 0,
        }

    def clear(self) -> None:
        """Clear all entries."""
        self.entries.clear()
