"""Any Disposition review engine.

This module evaluates the fit between a proposed disposition, the evidence
available at decision time, and the capability of the destination. It is not a
clinical disposition authority. It emits review signals, hard blockers, missing
evidence, and advisory trace/memory outputs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence

from .associative_memory import NearMissMemory, ADVISORY_AUTHORITY
from .boundary_trace import BoundaryTraceField, TRACE_CONSTRAINT, TRACE_SIGNAL


AnyDispositionState = Literal[
    "NO_REVIEW_SIGNAL",
    "REVIEW_RECOMMENDED",
    "LOWER_ACUITY_BLOCKED",
    "ADMISSION_BENEFIT_UNCERTAIN",
    "LEVEL_OF_CARE_MISMATCH",
    "INSUFFICIENT_EVIDENCE",
]

DispositionAcuity = Literal[
    "home",
    "telehealth",
    "clinic",
    "home_health",
    "observation",
    "floor",
    "telemetry",
    "stepdown",
    "icu",
    "transfer",
    "snf",
    "rehab",
]


LOWER_ACUITY_DESTINATIONS = {"home", "telehealth", "clinic", "home_health"}
HIGHER_ACUITY_DESTINATIONS = {"observation", "floor", "telemetry", "stepdown", "icu", "transfer"}
MONITORED_DESTINATIONS = {"telemetry", "stepdown", "icu", "transfer"}

VALUE_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class ProposedDisposition:
    destination: DispositionAcuity
    service: str = ""
    monitoring_level: str = ""
    rationale: str = ""
    follow_up_plan: str = ""


@dataclass
class DestinationCapability:
    serial_vitals: bool = False
    oxygen: bool = False
    iv_therapy: bool = False
    telemetry: bool = False
    urgent_reassessment: bool = False
    urgent_imaging_or_procedure: bool = False
    medication_access: bool = False
    caregiver_or_staff_support: bool = False
    confirmed_follow_up: bool = False


@dataclass
class DecisionTimeEvidence:
    vital_trend: Dict[str, Sequence[Any]] = field(default_factory=dict)
    resulted_data: Dict[str, Any] = field(default_factory=dict)
    active_treatments: List[str] = field(default_factory=list)
    inpatient_only_needs: List[str] = field(default_factory=list)
    unresolved_red_flags: List[str] = field(default_factory=list)
    source_conflicts: List[str] = field(default_factory=list)
    high_risk_factors: List[str] = field(default_factory=list)
    objective_gaps: List[str] = field(default_factory=list)
    pending_tests: List[str] = field(default_factory=list)
    response_to_treatment: str = "not_documented"
    follow_up_reliability: str = "unknown"
    caregiver_status: str = "unknown"


@dataclass
class AnyDispositionCase:
    case_id: str
    age: int
    chief_concern: str
    domain: str
    proposed_disposition: ProposedDisposition
    destination_capability: DestinationCapability
    evidence: DecisionTimeEvidence
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnyDispositionReviewReport:
    case_id: str
    state: AnyDispositionState
    review_priority: float
    proposed_destination: str
    hard_blockers: List[str]
    capability_gaps: List[str]
    admission_benefit_signals: List[str]
    missing_evidence: List[str]
    trace_summary: Dict[str, Any]
    memory_suggestions: Dict[str, Any]
    signature_keys: List[str]
    rationale: str
    authority: str = ADVISORY_AUTHORITY

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AnyDispositionReviewEngine:
    """Review proposed destinations without authorizing care."""

    def __init__(self, memory: Optional[NearMissMemory] = None) -> None:
        self.memory = memory or seeded_any_dispo_memory()

    def evaluate(self, case: AnyDispositionCase) -> AnyDispositionReviewReport:
        signature_keys = self.signature_keys(case)
        blockers = self._hard_blockers(case)
        capability_gaps = self._capability_gaps(case)
        admission_signals = self._admission_benefit_signals(case, blockers, capability_gaps)
        missing_evidence = self._missing_evidence(case)

        trace_field = BoundaryTraceField()
        self._deposit_traces(trace_field, blockers, capability_gaps, admission_signals, missing_evidence)
        memory_suggestions = self.memory.suggest(signature_keys, k=5, min_score=0.05)

        state = self._decide_state(case, blockers, capability_gaps, admission_signals, missing_evidence)
        review_priority = self._review_priority(
            blockers=blockers,
            capability_gaps=capability_gaps,
            admission_signals=admission_signals,
            missing_evidence=missing_evidence,
            trace_pressure=trace_field.risk_pressure(),
            recall_count=int(memory_suggestions["recall_count"]),
        )

        return AnyDispositionReviewReport(
            case_id=case.case_id,
            state=state,
            review_priority=review_priority,
            proposed_destination=case.proposed_disposition.destination,
            hard_blockers=blockers,
            capability_gaps=capability_gaps,
            admission_benefit_signals=admission_signals,
            missing_evidence=missing_evidence,
            trace_summary=trace_field.summary(),
            memory_suggestions=memory_suggestions,
            signature_keys=signature_keys,
            rationale=self._rationale(state),
        )

    def signature_keys(self, case: AnyDispositionCase) -> List[str]:
        evidence = case.evidence
        keys = {
            case.proposed_disposition.destination,
            f"domain:{case.domain}",
            f"chief:{case.chief_concern.lower()}",
        }
        keys.update(_normalize_items(evidence.unresolved_red_flags))
        keys.update(_normalize_items(evidence.source_conflicts, prefix="source_conflict"))
        keys.update(_normalize_items(evidence.high_risk_factors, prefix="high_risk"))
        keys.update(_normalize_items(evidence.objective_gaps, prefix="objective_gap"))
        keys.update(_normalize_items(evidence.inpatient_only_needs, prefix="inpatient_need"))
        if self._has_objective_instability(case):
            keys.add("objective_instability")
        if evidence.response_to_treatment.lower() in {"improved", "worsening", "uncertain"}:
            keys.add(f"response:{evidence.response_to_treatment.lower()}")
        if evidence.follow_up_reliability:
            keys.add(f"follow_up:{evidence.follow_up_reliability.lower()}")
        if evidence.caregiver_status:
            keys.add(f"caregiver:{evidence.caregiver_status.lower()}")
        return sorted(keys)

    def _hard_blockers(self, case: AnyDispositionCase) -> List[str]:
        evidence = case.evidence
        blockers: List[str] = []
        blockers.extend(self._objective_instability(case))
        blockers.extend(f"UNRESOLVED_RED_FLAG:{item}" for item in evidence.unresolved_red_flags)
        blockers.extend(f"SOURCE_CONFLICT:{item}" for item in evidence.source_conflicts)

        destination = case.proposed_disposition.destination
        lower_acuity = destination in LOWER_ACUITY_DESTINATIONS
        if lower_acuity and evidence.high_risk_factors and evidence.objective_gaps:
            blockers.append("HIGH_RISK_HOST_WITH_OBJECTIVE_GAPS")
        if lower_acuity and evidence.follow_up_reliability.lower() in {"unknown", "uncertain", "unreliable", "none"}:
            blockers.append("LOWER_ACUITY_WITH_UNRELIABLE_FOLLOW_UP")
        if lower_acuity and evidence.caregiver_status.lower() in {"unknown", "uncertain", "unavailable"}:
            blockers.append("LOWER_ACUITY_WITH_UNCONFIRMED_SUPPORT")
        return _dedupe(blockers)

    def _capability_gaps(self, case: AnyDispositionCase) -> List[str]:
        evidence = case.evidence
        capability = case.destination_capability
        gaps: List[str] = []
        needs = {item.lower() for item in evidence.inpatient_only_needs}
        treatments = " ".join(evidence.active_treatments).lower()

        if any("oxygen" in item or "respiratory" in item for item in needs) and not capability.oxygen:
            gaps.append("DESTINATION_CANNOT_PROVIDE_OXYGEN")
        if ("oxygen" in treatments or "nonrebreather" in treatments or "high flow" in treatments) and not capability.oxygen:
            gaps.append("ACTIVE_OXYGEN_NEED_WITH_NO_DESTINATION_OXYGEN")
        if any("iv" in item or "infusion" in item for item in needs) and not capability.iv_therapy:
            gaps.append("DESTINATION_CANNOT_PROVIDE_IV_THERAPY")
        if any("telemetry" in item or "arrhythmia" in item for item in needs) and not capability.telemetry:
            gaps.append("DESTINATION_CANNOT_PROVIDE_TELEMETRY")
        if any("procedure" in item or "imaging" in item for item in needs) and not capability.urgent_imaging_or_procedure:
            gaps.append("DESTINATION_CANNOT_PROVIDE_URGENT_PROCEDURE_OR_IMAGING")
        if self._has_objective_instability(case) and not capability.urgent_reassessment:
            gaps.append("OBJECTIVE_INSTABILITY_WITHOUT_URGENT_REASSESSMENT")
        if case.proposed_disposition.destination in LOWER_ACUITY_DESTINATIONS and not capability.confirmed_follow_up:
            gaps.append("LOWER_ACUITY_DESTINATION_WITHOUT_CONFIRMED_FOLLOW_UP")
        return _dedupe(gaps)

    def _admission_benefit_signals(
        self,
        case: AnyDispositionCase,
        blockers: Sequence[str],
        capability_gaps: Sequence[str],
    ) -> List[str]:
        evidence = case.evidence
        destination = case.proposed_disposition.destination
        if destination not in HIGHER_ACUITY_DESTINATIONS:
            return []
        if blockers or capability_gaps:
            return []
        signals: List[str] = []
        if not evidence.inpatient_only_needs:
            signals.append("NO_DOCUMENTED_INPATIENT_ONLY_NEED")
        if evidence.response_to_treatment.lower() == "improved":
            signals.append("DOCUMENTED_RESPONSE_TO_TREATMENT_IMPROVED")
        if evidence.follow_up_reliability.lower() in {"confirmed", "reliable"}:
            signals.append("FOLLOW_UP_RELIABILITY_CONFIRMED")
        if evidence.caregiver_status.lower() in {"available", "staffed", "independent"}:
            signals.append("SUPPORT_OR_SELF_CARE_CONFIRMED")
        if destination in MONITORED_DESTINATIONS and "NO_DOCUMENTED_INPATIENT_ONLY_NEED" in signals:
            signals.append("MONITORED_DESTINATION_WITH_LOW_DOCUMENTED_RESOURCE_NEED")
        return signals if len(signals) >= 3 else []

    def _missing_evidence(self, case: AnyDispositionCase) -> List[str]:
        evidence = case.evidence
        missing = list(evidence.objective_gaps)
        if not evidence.vital_trend:
            missing.append("current vital trend")
        if not evidence.resulted_data:
            missing.append("resulted objective data")
        if evidence.follow_up_reliability.lower() in {"unknown", "uncertain", ""}:
            missing.append("follow-up reliability")
        if evidence.caregiver_status.lower() in {"unknown", "uncertain", ""}:
            missing.append("caregiver or self-care support")
        return _dedupe(missing)

    def _deposit_traces(
        self,
        trace_field: BoundaryTraceField,
        blockers: Sequence[str],
        capability_gaps: Sequence[str],
        admission_signals: Sequence[str],
        missing_evidence: Sequence[str],
    ) -> None:
        for blocker in blockers:
            patch = trace_field.apply_patch(
                TRACE_CONSTRAINT,
                "hard_blocker",
                {"blocker": blocker},
                symbolic_keys=["hard_blocker", blocker],
                confidence=0.9,
                decay_rate=0.02,
            )
            trace_field.reinforce(patch.patch_id, magnitude=1.0)
        for gap in capability_gaps:
            trace_field.apply_patch(
                TRACE_CONSTRAINT,
                "destination_capability_gap",
                {"gap": gap},
                symbolic_keys=["destination_capability_gap", gap],
                confidence=0.8,
                decay_rate=0.05,
            )
        for signal in admission_signals:
            trace_field.apply_patch(
                TRACE_SIGNAL,
                "admission_benefit_uncertainty",
                {"signal": signal},
                symbolic_keys=["admission_benefit_uncertainty", signal],
                confidence=0.55,
                decay_rate=0.08,
            )
        for item in missing_evidence:
            trace_field.apply_patch(
                TRACE_SIGNAL,
                "missing_evidence",
                {"missing": item},
                symbolic_keys=["missing_evidence", item],
                confidence=0.45,
                decay_rate=0.10,
            )

    def _decide_state(
        self,
        case: AnyDispositionCase,
        blockers: Sequence[str],
        capability_gaps: Sequence[str],
        admission_signals: Sequence[str],
        missing_evidence: Sequence[str],
    ) -> AnyDispositionState:
        destination = case.proposed_disposition.destination
        if blockers and destination in LOWER_ACUITY_DESTINATIONS:
            return "LOWER_ACUITY_BLOCKED"
        if capability_gaps:
            return "LEVEL_OF_CARE_MISMATCH"
        if blockers:
            return "REVIEW_RECOMMENDED"
        if admission_signals:
            return "ADMISSION_BENEFIT_UNCERTAIN"
        if len(missing_evidence) >= 3:
            return "INSUFFICIENT_EVIDENCE"
        if missing_evidence:
            return "REVIEW_RECOMMENDED"
        return "NO_REVIEW_SIGNAL"

    def _review_priority(
        self,
        blockers: Sequence[str],
        capability_gaps: Sequence[str],
        admission_signals: Sequence[str],
        missing_evidence: Sequence[str],
        trace_pressure: float,
        recall_count: int,
    ) -> float:
        score = 0.0
        score += min(45.0, len(blockers) * 15.0)
        score += min(30.0, len(capability_gaps) * 10.0)
        score += min(20.0, len(admission_signals) * 5.0)
        score += min(15.0, len(missing_evidence) * 3.0)
        score += min(15.0, trace_pressure * 2.0)
        score += min(10.0, recall_count * 3.0)
        return round(min(100.0, score), 1)

    def _rationale(self, state: AnyDispositionState) -> str:
        return {
            "LOWER_ACUITY_BLOCKED": "A lower-acuity path has unresolved hard blockers and should be reviewed.",
            "LEVEL_OF_CARE_MISMATCH": "The proposed destination may not provide the documented monitoring, treatment, or reassessment capability.",
            "ADMISSION_BENEFIT_UNCERTAIN": "The higher-acuity disposition has a reviewable low documented inpatient-only need signal.",
            "INSUFFICIENT_EVIDENCE": "The decision-time snapshot is missing enough core evidence that uncertainty should be preserved.",
            "REVIEW_RECOMMENDED": "The case has reviewable uncertainty even without a destination-specific hard block.",
            "NO_REVIEW_SIGNAL": "No deterministic Any Dispo review signal was produced from the provided decision-time fields.",
        }[state]

    def _has_objective_instability(self, case: AnyDispositionCase) -> bool:
        return bool(self._objective_instability(case))

    def _objective_instability(self, case: AnyDispositionCase) -> List[str]:
        values = {key.lower(): _to_float(_latest(value)) for key, value in case.evidence.vital_trend.items()}
        values.update({key.lower(): _to_float(value) for key, value in case.evidence.resulted_data.items()})
        risks: List[str] = []
        spo2 = _first_present(values, "spo2", "oxygen", "oxygen_saturation")
        if spo2 is not None and spo2 < 92:
            risks.append(f"LOW_OXYGEN_SATURATION:{spo2:g}")
        sbp = _first_present(values, "sbp", "systolic", "blood_pressure_systolic")
        if sbp is not None and sbp < 90:
            risks.append(f"HYPOTENSION_SBP:{sbp:g}")
        hr = _first_present(values, "hr", "heart_rate", "pulse")
        if hr is not None and hr >= 120:
            risks.append(f"MARKED_TACHYCARDIA:{hr:g}")
        rr = _first_present(values, "rr", "respiratory_rate")
        if rr is not None and rr >= 24:
            risks.append(f"TACHYPNEA:{rr:g}")
        lactate = _first_present(values, "lactate")
        if lactate is not None and lactate >= 2.5:
            risks.append(f"ELEVATED_LACTATE:{lactate:g}")
        return risks


def seeded_any_dispo_memory() -> NearMissMemory:
    memory = NearMissMemory()
    memory.store(
        signature_keys=["home", "objective_gap:no current vitals", "high_risk:ckd"],
        missing_nodes=["current vital trend", "renal function", "medication access"],
        falsifiers=["same-day stable vitals", "recent renal function reviewed", "confirmed follow-up"],
        recommended_actions=["route to disposition review before lower-acuity path"],
        outcome="near_miss_lower_acuity",
        strength=0.8,
        memory_id="any-dispo-home-ckd-objective-gap",
    )
    memory.store(
        signature_keys=["floor", "inpatient_need:telemetry", "source_conflict:arrhythmia history"],
        missing_nodes=["telemetry capability", "arrhythmia history reconciliation"],
        falsifiers=["telemetry available at destination", "source conflict resolved"],
        recommended_actions=["verify monitored destination capability"],
        outcome="level_of_care_mismatch",
        strength=0.75,
        memory_id="any-dispo-floor-telemetry-conflict",
    )
    memory.store(
        signature_keys=["observation", "response:improved", "follow_up:confirmed", "caregiver:available"],
        missing_nodes=["documented inpatient-only need", "explicit return precautions"],
        falsifiers=["active inpatient-only therapy required", "worsening vital trend"],
        recommended_actions=["review admission-benefit uncertainty, not discharge safety"],
        outcome="admission_benefit_uncertainty",
        strength=0.65,
        memory_id="any-dispo-observation-low-resource-need",
    )
    return memory


def _normalize_items(items: Iterable[str], prefix: str = "") -> set[str]:
    out: set[str] = set()
    for item in items:
        clean = str(item).strip().lower()
        if not clean:
            continue
        out.add(f"{prefix}:{clean}" if prefix else clean)
    return out


def _latest(values: Any) -> Any:
    if isinstance(values, (list, tuple)) and values:
        return values[-1]
    return values


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = VALUE_RE.search(str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _first_present(values: Dict[str, Optional[float]], *keys: str) -> Optional[float]:
    for key in keys:
        if key in values and values[key] is not None:
            return values[key]
    for key, value in values.items():
        if value is None:
            continue
        if any(target in key for target in keys):
            return value
    return None


def _dedupe(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
