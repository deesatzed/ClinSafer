"""Cognitive bias field analysis for JRE and Any Dispo review.

This module turns reasoning-integrity, uncertainty-graph, disposition, trace,
and memory outputs into advisory review pressure. It does not diagnose clinician
bias, simulate true disease probability, or authorize care. It highlights where
reasoning may be overconfident, premature, confirmatory, fragile, or missing
falsifiers.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .associative_memory import ADVISORY_AUTHORITY
from .black_swan import GuardrailReport
from .models import CaseInput, ReadinessReport
from .reasoning_integrity import ReasoningIntegrityReport


@dataclass
class BiasFactorScore:
    bias_id: str
    label: str
    score: float
    evidence: str
    mitigation: str


@dataclass
class InformationGainCandidate:
    source: str
    target: str
    expected_gain: float
    yield_class: str
    rationale: str


@dataclass
class HypothesisSurvivalItem:
    branch: str
    status: str
    supporting_evidence: List[str] = field(default_factory=list)
    missing_falsifiers: List[str] = field(default_factory=list)
    close_condition: str = ""


@dataclass
class DispositionFragilityReport:
    baseline_state: str
    perturbations_tested: int
    state_flips: int
    fragility_index: float
    fragile_inputs: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CognitiveFrictionAction:
    action_id: str
    label: str
    reason: str
    prompt: str
    required: bool = True


@dataclass
class FreshEyesPayload:
    case_id: str
    hidden_fields: List[str]
    visible_facts: List[str]
    prompt: str


@dataclass
class CognitiveBiasFieldReport:
    case_id: str
    context: str
    bias_entropy_score: float
    dominant_biases: List[BiasFactorScore]
    information_gain_candidates: List[InformationGainCandidate]
    hypothesis_survival: List[HypothesisSurvivalItem]
    disposition_fragility: Optional[DispositionFragilityReport]
    friction_actions: List[CognitiveFrictionAction]
    fresh_eyes_payload: FreshEyesPayload
    authority: str = ADVISORY_AUTHORITY

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CognitiveBiasFieldEngine:
    """Advisory cognitive-bias pressure layer."""

    def evaluate_jre(
        self,
        case: CaseInput,
        jre_report: ReadinessReport,
        guardrail_report: GuardrailReport,
        reasoning_report: Optional[ReasoningIntegrityReport] = None,
    ) -> CognitiveBiasFieldReport:
        factors = self._jre_bias_factors(case, jre_report, guardrail_report, reasoning_report)
        info_gain = self._jre_information_gain(jre_report)
        hypothesis_survival = self._jre_hypothesis_survival(case, jre_report)
        entropy = self._entropy_score(factors, extra_pressure=self._jre_extra_pressure(jre_report, guardrail_report))
        friction = self._friction_actions(
            entropy,
            factors,
            has_hard_blockers=guardrail_report.guardrail_state in {"ESCALATE", "FAIL_CLOSED", "ROUTE_CLINICIAN"},
            has_missing_evidence=bool(info_gain),
            has_fragility=False,
            context="jre",
        )
        return CognitiveBiasFieldReport(
            case_id=case.case_id,
            context="jre",
            bias_entropy_score=entropy,
            dominant_biases=factors[:5],
            information_gain_candidates=info_gain,
            hypothesis_survival=hypothesis_survival,
            disposition_fragility=None,
            friction_actions=friction,
            fresh_eyes_payload=self._jre_fresh_eyes(case),
        )

    def evaluate_any_dispo(self, case: Any, any_dispo_report: Any) -> CognitiveBiasFieldReport:
        factors = self._any_dispo_bias_factors(case, any_dispo_report)
        info_gain = self._any_dispo_information_gain(any_dispo_report)
        hypothesis_survival = self._any_dispo_hypothesis_survival(case, any_dispo_report)
        fragility = self._any_dispo_fragility(case, any_dispo_report)
        entropy = self._entropy_score(
            factors,
            extra_pressure=(
                min(30.0, float(getattr(any_dispo_report, "review_priority", 0.0)) * 0.30)
                + min(20.0, fragility.fragility_index * 20.0)
            ),
        )
        friction = self._friction_actions(
            entropy,
            factors,
            has_hard_blockers=bool(getattr(any_dispo_report, "hard_blockers", [])),
            has_missing_evidence=bool(getattr(any_dispo_report, "missing_evidence", [])),
            has_fragility=fragility.fragility_index > 0,
            context="any_dispo",
        )
        return CognitiveBiasFieldReport(
            case_id=case.case_id,
            context="any_dispo",
            bias_entropy_score=entropy,
            dominant_biases=factors[:5],
            information_gain_candidates=info_gain,
            hypothesis_survival=hypothesis_survival,
            disposition_fragility=fragility,
            friction_actions=friction,
            fresh_eyes_payload=self._any_dispo_fresh_eyes(case),
        )

    # ------------------------------------------------------------------
    # JRE analysis
    # ------------------------------------------------------------------
    def _jre_bias_factors(
        self,
        case: CaseInput,
        jre_report: ReadinessReport,
        guardrail_report: GuardrailReport,
        reasoning_report: Optional[ReasoningIntegrityReport],
    ) -> List[BiasFactorScore]:
        factors: Dict[str, BiasFactorScore] = {}
        if reasoning_report:
            for finding in reasoning_report.findings:
                score = _clamp100(finding.severity * 100.0)
                factors[finding.bias_id] = BiasFactorScore(
                    bias_id=finding.bias_id,
                    label=finding.label,
                    score=score,
                    evidence=finding.evidence,
                    mitigation=finding.cognitive_forcing_action,
                )

        scores = jre_report.scores
        if scores.objective_coverage < 0.35 and jre_report.state in {"READY", "CLARIFY"}:
            factors.setdefault(
                "overconfidence",
                BiasFactorScore(
                    "overconfidence",
                    "Overconfidence / Low Objective Evidence",
                    round((0.35 - scores.objective_coverage) * 180.0, 1),
                    f"objective_coverage={scores.objective_coverage:.2f}; state={jre_report.state}",
                    "Separate narrative coherence from objective evidence sufficiency.",
                ),
            )
        if any(f.category in {"missing", "objective_needed", "unknowable_remote"} for f in jre_report.findings):
            factors.setdefault(
                "premature_closure",
                BiasFactorScore(
                    "premature_closure",
                    "Premature Closure Pressure",
                    70.0,
                    "Missing, objective-needed, or remote-unknowable findings remain.",
                    "Keep the case open until a dangerous alternative is actively falsified.",
                ),
            )
        if guardrail_report.guardrail_state in {"ESCALATE", "FAIL_CLOSED", "ROUTE_CLINICIAN"}:
            factors.setdefault(
                "omission_bias",
                BiasFactorScore(
                    "omission_bias",
                    "Omission / Delay Risk",
                    76.0,
                    f"guardrail_state={guardrail_report.guardrail_state}",
                    "Compare harm of routing against harm of delayed action.",
                ),
            )

        return sorted(factors.values(), key=lambda item: item.score, reverse=True)

    def _jre_information_gain(self, jre_report: ReadinessReport) -> List[InformationGainCandidate]:
        candidates: List[InformationGainCandidate] = []
        for question in jre_report.next_questions:
            gain = _clamp01(float(getattr(question, "expected_information_gain", 0.5) or 0.5))
            if "objective" in question.rule_id.lower() or "objective" in question.reason.lower():
                gain = min(1.0, gain + 0.15)
            candidates.append(
                InformationGainCandidate(
                    source="jre_next_question",
                    target=question.question,
                    expected_gain=round(gain, 3),
                    yield_class=_yield_class(gain),
                    rationale=question.reason,
                )
            )
        candidates.sort(key=lambda item: item.expected_gain, reverse=True)
        return candidates[:8]

    def _jre_hypothesis_survival(
        self,
        case: CaseInput,
        jre_report: ReadinessReport,
    ) -> List[HypothesisSurvivalItem]:
        red_flags = [f for f in jre_report.findings if f.category == "red_flag"]
        missing = [f for f in jre_report.findings if f.category in {"missing", "objective_needed", "unknowable_remote"}]
        top_questions = [q.question for q in jre_report.next_questions[:3]]
        return [
            HypothesisSurvivalItem(
                branch=f"working_frame:{case.patient_context.chief_concern}",
                status="unclosed" if jre_report.state != "READY" else "provisionally_supported",
                supporting_evidence=[obs.concept for obs in jre_report.observations[:5]],
                missing_falsifiers=top_questions,
                close_condition="Readiness can improve only after the highest-yield missing or objective facts are resolved.",
            ),
            HypothesisSurvivalItem(
                branch="dangerous_alternative",
                status="alive" if red_flags or missing else "not_prominent",
                supporting_evidence=[f.reason for f in red_flags[:3]],
                missing_falsifiers=[f.next_question or f.reason for f in missing[:3]],
                close_condition="Dangerous alternatives remain alive until red flags and objective-needed gaps are falsified.",
            ),
        ]

    def _jre_extra_pressure(self, jre_report: ReadinessReport, guardrail_report: GuardrailReport) -> float:
        graph_summary = (jre_report.uncertainty_graph or {}).get("summary", {})
        pressure = 0.0
        pressure += float(graph_summary.get("boundary_sensitivity_index", 0.0) or 0.0) * 20.0
        pressure += float(graph_summary.get("missing_load", 0.0) or 0.0) * 15.0
        if guardrail_report.guardrail_state in {"ESCALATE", "FAIL_CLOSED", "ROUTE_CLINICIAN"}:
            pressure += 15.0
        return pressure

    def _jre_fresh_eyes(self, case: CaseInput) -> FreshEyesPayload:
        facts = [
            f"age:{case.patient_context.age}",
            f"chief_concern:{case.patient_context.chief_concern}",
            f"domain:{case.patient_context.domain}",
        ]
        for statement in case.statements[:10]:
            facts.append(f"{statement.source}: {statement.question} -> {statement.answer}")
        return FreshEyesPayload(
            case_id=case.case_id,
            hidden_fields=["working diagnosis", "prior disposition intent", "clinician reassurance labels"],
            visible_facts=facts,
            prompt="Review these decision-time facts without relying on the current working label. What dangerous alternative still needs falsification?",
        )

    # ------------------------------------------------------------------
    # Any Dispo analysis
    # ------------------------------------------------------------------
    def _any_dispo_bias_factors(self, case: Any, report: Any) -> List[BiasFactorScore]:
        factors: List[BiasFactorScore] = []
        if getattr(report, "hard_blockers", []):
            factors.append(
                BiasFactorScore(
                    "premature_closure",
                    "Uncertainty Collapse / Premature Closure",
                    min(95.0, 68.0 + 6.0 * len(report.hard_blockers)),
                    "; ".join(report.hard_blockers[:4]),
                    "Do not close to the proposed destination until each hard blocker is resolved or reviewed.",
                )
            )
        if getattr(report, "capability_gaps", []):
            factors.append(
                BiasFactorScore(
                    "representativeness",
                    "Destination Prototype Mismatch",
                    min(90.0, 64.0 + 7.0 * len(report.capability_gaps)),
                    "; ".join(report.capability_gaps[:4]),
                    "Compare the proposed destination to the actual resource need, not the usual pathway label.",
                )
            )
        if getattr(report, "admission_benefit_signals", []):
            factors.append(
                BiasFactorScore(
                    "status_quo_bias",
                    "Status Quo / Treatment Inertia Pressure",
                    min(82.0, 55.0 + 5.0 * len(report.admission_benefit_signals)),
                    "; ".join(report.admission_benefit_signals[:4]),
                    "Review whether higher-acuity placement has documented inpatient-only benefit.",
                )
            )
        if getattr(report, "missing_evidence", []):
            factors.append(
                BiasFactorScore(
                    "overconfidence",
                    "Overconfidence With Missing Evidence",
                    min(88.0, 58.0 + 4.0 * len(report.missing_evidence)),
                    "; ".join(report.missing_evidence[:5]),
                    "Preserve uncertainty and collect the evidence most likely to change destination fit.",
                )
            )
        if _text_contains_reassurance(case.proposed_disposition.rationale):
            factors.append(
                BiasFactorScore(
                    "confirmation_bias",
                    "Confirmatory Disposition Rationale",
                    62.0,
                    case.proposed_disposition.rationale[:180],
                    "Ask what fact would disprove the reassuring disposition rationale.",
                )
            )
        if not factors:
            factors.append(
                BiasFactorScore(
                    "low_bias_pressure",
                    "Low Deterministic Bias Pressure",
                    12.0,
                    "No hard blockers, major capability gaps, or missing-evidence cluster detected.",
                    "Standard review is sufficient unless new evidence appears.",
                )
            )
        return sorted(factors, key=lambda item: item.score, reverse=True)

    def _any_dispo_information_gain(self, report: Any) -> List[InformationGainCandidate]:
        candidates: List[InformationGainCandidate] = []
        for item in getattr(report, "hard_blockers", []):
            candidates.append(
                InformationGainCandidate(
                    "hard_blocker",
                    item,
                    0.92,
                    "high_yield",
                    "Resolving this blocker can directly change destination readiness.",
                )
            )
        for item in getattr(report, "capability_gaps", []):
            candidates.append(
                InformationGainCandidate(
                    "capability_gap",
                    item,
                    0.86,
                    "high_yield",
                    "Destination capability verification can directly change level-of-care fit.",
                )
            )
        for item in getattr(report, "missing_evidence", []):
            gain = 0.78 if any(word in item.lower() for word in ["vital", "objective", "follow-up", "caregiver"]) else 0.62
            candidates.append(
                InformationGainCandidate(
                    "missing_evidence",
                    item,
                    gain,
                    _yield_class(gain),
                    "Missing evidence should be collected before confident disposition language.",
                )
            )
        for item in (getattr(report, "memory_suggestions", {}) or {}).get("falsifiers", []):
            candidates.append(
                InformationGainCandidate(
                    "near_miss_falsifier",
                    item,
                    0.70,
                    "moderate_yield",
                    "Near-miss memory suggests this falsifier may prevent repeated boundary failure.",
                )
            )
        candidates.sort(key=lambda item: item.expected_gain, reverse=True)
        return candidates[:10]

    def _any_dispo_hypothesis_survival(self, case: Any, report: Any) -> List[HypothesisSurvivalItem]:
        destination = case.proposed_disposition.destination
        return [
            HypothesisSurvivalItem(
                branch=f"proposed_destination:{destination}",
                status="blocked" if report.state in {"LOWER_ACUITY_BLOCKED", "LEVEL_OF_CARE_MISMATCH"} else "reviewable",
                supporting_evidence=list(report.admission_benefit_signals[:4]),
                missing_falsifiers=list(report.missing_evidence[:4]),
                close_condition="Destination fit requires blockers, capability gaps, and missing evidence to be resolved.",
            ),
            HypothesisSurvivalItem(
                branch="lower_acuity_path",
                status="blocked" if report.hard_blockers or report.capability_gaps else "not_blocked_by_current_fields",
                supporting_evidence=list(report.capability_gaps[:4]),
                missing_falsifiers=list(report.memory_suggestions.get("falsifiers", [])[:4]),
                close_condition="A lower-acuity path can only be considered after hard blockers and follow-up/support gaps are resolved.",
            ),
            HypothesisSurvivalItem(
                branch="higher_acuity_benefit",
                status="uncertain" if report.admission_benefit_signals else "not_signaled",
                supporting_evidence=list(report.admission_benefit_signals[:5]),
                missing_falsifiers=list(report.memory_suggestions.get("missing_nodes", [])[:4]),
                close_condition="Admission-benefit uncertainty remains a review signal, not proof that higher-acuity care is unnecessary.",
            ),
        ]

    def _any_dispo_fragility(self, case: Any, report: Any) -> DispositionFragilityReport:
        from .any_disposition import AnyDispositionReviewEngine

        perturbations = self._build_any_dispo_perturbations(case)
        flips: List[Dict[str, Any]] = []
        engine = AnyDispositionReviewEngine(memory=None)
        for label, perturbed_case in perturbations:
            perturbed_report = engine.evaluate(perturbed_case)
            if perturbed_report.state != report.state:
                flips.append(
                    {
                        "input": label,
                        "baseline_state": report.state,
                        "perturbed_state": perturbed_report.state,
                    }
                )
        tested = len(perturbations)
        return DispositionFragilityReport(
            baseline_state=report.state,
            perturbations_tested=tested,
            state_flips=len(flips),
            fragility_index=round(len(flips) / tested, 3) if tested else 0.0,
            fragile_inputs=flips[:8],
        )

    def _build_any_dispo_perturbations(self, case: Any) -> List[Tuple[str, Any]]:
        perturbations: List[Tuple[str, Any]] = []

        def add(label: str, updater: Any) -> None:
            new_case = deepcopy(case)
            updater(new_case)
            perturbations.append((label, new_case))

        add(
            "follow_up_reliability_toggle",
            lambda c: setattr(
                c.evidence,
                "follow_up_reliability",
                "unknown" if c.evidence.follow_up_reliability.lower() in {"confirmed", "reliable"} else "confirmed",
            ),
        )
        add(
            "caregiver_status_toggle",
            lambda c: setattr(
                c.evidence,
                "caregiver_status",
                "unknown" if c.evidence.caregiver_status.lower() in {"available", "staffed", "independent"} else "available",
            ),
        )
        add("telemetry_capability_toggle", lambda c: setattr(c.destination_capability, "telemetry", not c.destination_capability.telemetry))
        add("oxygen_capability_toggle", lambda c: setattr(c.destination_capability, "oxygen", not c.destination_capability.oxygen))
        add(
            "urgent_reassessment_toggle",
            lambda c: setattr(c.destination_capability, "urgent_reassessment", not c.destination_capability.urgent_reassessment),
        )
        add(
            "unresolved_red_flag_toggle",
            lambda c: (
                c.evidence.unresolved_red_flags.pop()
                if c.evidence.unresolved_red_flags
                else c.evidence.unresolved_red_flags.append("perturbation unresolved risk")
            ),
        )
        for key, delta in [("spo2", -2), ("hr", 10), ("rr", 4)]:
            if key in case.evidence.vital_trend:
                add(f"{key}_near_threshold_perturbation", lambda c, k=key, d=delta: _perturb_latest_vital(c.evidence.vital_trend, k, d))
        return perturbations

    def _any_dispo_fresh_eyes(self, case: Any) -> FreshEyesPayload:
        evidence = case.evidence
        facts = [
            f"age:{case.age}",
            f"chief_concern:{case.chief_concern}",
            f"domain:{case.domain}",
            f"vital_trend:{evidence.vital_trend}",
            f"resulted_data:{evidence.resulted_data}",
            f"active_treatments:{evidence.active_treatments}",
            f"inpatient_only_needs:{evidence.inpatient_only_needs}",
            f"unresolved_red_flags:{evidence.unresolved_red_flags}",
            f"source_conflicts:{evidence.source_conflicts}",
            f"high_risk_factors:{evidence.high_risk_factors}",
            f"objective_gaps:{evidence.objective_gaps}",
            f"follow_up_reliability:{evidence.follow_up_reliability}",
            f"caregiver_status:{evidence.caregiver_status}",
        ]
        return FreshEyesPayload(
            case_id=case.case_id,
            hidden_fields=["proposed destination", "proposed disposition rationale", "service preference"],
            visible_facts=facts,
            prompt="Review the decision-time facts without the proposed destination. Which destinations remain plausible, blocked, or under-supported?",
        )

    # ------------------------------------------------------------------
    # Shared scoring and friction
    # ------------------------------------------------------------------
    def _entropy_score(self, factors: Sequence[BiasFactorScore], extra_pressure: float = 0.0) -> float:
        if not factors:
            return round(min(100.0, extra_pressure), 1)
        top = max(f.score for f in factors)
        mean = sum(f.score for f in factors) / len(factors)
        diversity = min(20.0, max(0, len([f for f in factors if f.score >= 45.0]) - 1) * 5.0)
        return round(_clamp100(0.55 * top + 0.25 * mean + diversity + extra_pressure), 1)

    def _friction_actions(
        self,
        entropy: float,
        factors: Sequence[BiasFactorScore],
        has_hard_blockers: bool,
        has_missing_evidence: bool,
        has_fragility: bool,
        context: str,
    ) -> List[CognitiveFrictionAction]:
        actions: List[CognitiveFrictionAction] = []
        factor_ids = {factor.bias_id for factor in factors}
        if entropy >= 65 or has_hard_blockers:
            actions.append(
                CognitiveFrictionAction(
                    "require_disconfirming_fact",
                    "Require Disconfirming Fact",
                    "Bias pressure or hard blockers make confident closure unsafe.",
                    "Name the single fact that would disprove the current reassuring or preferred path.",
                )
            )
        if has_missing_evidence or "overconfidence" in factor_ids:
            actions.append(
                CognitiveFrictionAction(
                    "require_objective_data",
                    "Require Objective Data",
                    "The case has missing evidence or objective-data weakness.",
                    "Which missing objective or collateral fact is most likely to change the action boundary?",
                )
            )
        if "premature_closure" in factor_ids or "confirmation_bias" in factor_ids:
            actions.append(
                CognitiveFrictionAction(
                    "require_falsifier",
                    "Require Falsifier",
                    "The current reasoning may be closing around a preferred explanation.",
                    "What dangerous alternative has not yet been falsified?",
                )
            )
        if has_fragility:
            actions.append(
                CognitiveFrictionAction(
                    "preserve_uncertainty",
                    "Preserve Uncertainty",
                    "Small input changes can flip the disposition review state.",
                    "Avoid confident disposition language and document the fragile inputs.",
                )
            )
        if entropy >= 75:
            actions.append(
                CognitiveFrictionAction(
                    "show_fresh_eyes",
                    "Show Fresh Eyes View",
                    "High bias entropy warrants a blinded re-read of decision-time facts.",
                    "Review the case without the proposed diagnosis or destination before closing.",
                    required=context == "any_dispo",
                )
            )
        return _dedupe_actions(actions)


def _yield_class(gain: float) -> str:
    if gain >= 0.75:
        return "high_yield"
    if gain >= 0.45:
        return "moderate_yield"
    return "redundant_or_confirmatory"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp100(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _dedupe_actions(actions: Iterable[CognitiveFrictionAction]) -> List[CognitiveFrictionAction]:
    out: List[CognitiveFrictionAction] = []
    seen: set[str] = set()
    for action in actions:
        if action.action_id in seen:
            continue
        seen.add(action.action_id)
        out.append(action)
    return out


def _text_contains_reassurance(text: str) -> bool:
    lowered = (text or "").lower()
    return any(term in lowered for term in ["safe", "stable", "simple", "routine", "no concern", "reassur"])


def _perturb_latest_vital(vital_trend: Dict[str, Sequence[Any]], key: str, delta: float) -> None:
    values = vital_trend.get(key)
    if values is None:
        return
    if isinstance(values, list) and values:
        latest = values[-1]
        if isinstance(latest, (int, float)):
            values[-1] = latest + delta
    elif isinstance(values, tuple) and values:
        mutable = list(values)
        latest = mutable[-1]
        if isinstance(latest, (int, float)):
            mutable[-1] = latest + delta
            vital_trend[key] = mutable
