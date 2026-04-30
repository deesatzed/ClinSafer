"""Data models for the Judgment Readiness Engine.

This is intentionally dependency-light so it can be shown in an interview,
run in a notebook, embedded in a backend service, or wrapped around an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Literal

SourceType = Literal["patient", "caregiver", "device", "chart", "clinician", "synthetic_truth"]
FindingCategory = Literal[
    "missing",
    "uncertain",
    "distorted",
    "contradictory",
    "unknowable_remote",
    "objective_needed",
    "red_flag",
    "known",
]
DecisionState = Literal["READY", "CLARIFY", "NEED_OBJECTIVE_DATA", "ESCALATE"]


@dataclass
class Statement:
    """A raw utterance or structured answer from the patient flow."""

    question: str
    answer: str
    concept: Optional[str] = None
    source: SourceType = "patient"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PatientContext:
    age: int
    chief_concern: str
    domain: str
    literacy_hint: str = "unknown"  # low, medium, high, unknown
    language_barrier: bool = False
    has_caregiver: bool = False
    modality: str = "text"  # text, phone, video, in_person
    known_conditions: List[str] = field(default_factory=list)


@dataclass
class CaseInput:
    case_id: str
    patient_context: PatientContext
    statements: List[Statement]
    ground_truth: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    concept: str
    raw_value: str
    normalized_value: Any
    source: SourceType
    confidence: float
    tags: List[str]
    trace: List[str]


@dataclass
class SlotSpec:
    name: str
    label: str
    importance: float
    slot_type: str = "history"  # history, objective, chart, exam, lab
    acceptable_sources: List[SourceType] = field(default_factory=lambda: ["patient", "caregiver", "device", "chart"])
    clarify_questions: List[str] = field(default_factory=list)
    why_it_matters: str = ""
    critical: bool = False
    objective_required: bool = False
    remote_unknowable: bool = False
    traps: List[str] = field(default_factory=list)


@dataclass
class RuleTrace:
    rule_id: str
    description: str
    evidence: str
    effect: str


@dataclass
class Finding:
    category: FindingCategory
    concept: str
    severity: float
    reason: str
    rule_id: str
    next_question: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class NextQuestion:
    concept: str
    question: str
    reason: str
    clear_step: str
    priority: float
    expected_information_gain: float
    rule_id: str


@dataclass
class ReadinessScores:
    completeness: float
    reliability: float
    objective_coverage: float
    contradiction_load: float
    distortion_load: float
    red_flag_load: float
    readiness_index: float


@dataclass
class ReadinessReport:
    case_id: str
    state: DecisionState
    scores: ReadinessScores
    boundary_map: Dict[str, List[str]]
    observations: List[Observation]
    findings: List[Finding]
    next_questions: List[NextQuestion]
    traces: List[RuleTrace]
    provider_summary: str
    patient_safe_summary: str
    uncertainty_graph: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Combined State Priority (shared by unified_demo.py and api_server.py)
# ---------------------------------------------------------------------------

STATE_PRIORITY = [
    "ESCALATE",
    "FAIL_CLOSED",
    "ROUTE_CLINICIAN",
    "NEED_OBJECTIVE_DATA",
    "HOLD_AND_VERIFY",
    "CLARIFY",
    "ALLOW_WITH_AUDIT",
    "READY",
]


def most_restrictive(jre_state: str, bsg_state: str) -> str:
    """Return whichever state is more restrictive (lower index = more restrictive)."""
    jp = STATE_PRIORITY.index(jre_state) if jre_state in STATE_PRIORITY else 0
    bp = STATE_PRIORITY.index(bsg_state) if bsg_state in STATE_PRIORITY else 0
    return STATE_PRIORITY[min(jp, bp)]
