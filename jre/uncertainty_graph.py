"""Clinical uncertainty graph primitives.

This module is the explicit expert-system foundation for JRE/BSG/DHSE.
Clinical inputs are represented as typed nodes with source reliability,
range interpretation, uncertainty-state distributions, dependencies, and
action implications. LLMs may help populate observations elsewhere; this graph
is the deterministic safety object that downstream governors consume.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .models import CaseInput, Finding, Observation, SlotSpec


SOURCE_RELIABILITY_PRIOR: Dict[str, float] = {
    "device": 0.92,
    "chart": 0.88,
    "clinician": 0.86,
    "caregiver": 0.78,
    "patient": 0.72,
    "synthetic_truth": 0.99,
}


@dataclass(frozen=True)
class RangeBand:
    """Expert-defined numeric interpretation band for one node."""

    name: str
    low: Optional[float] = None
    high: Optional[float] = None
    severity: float = 0.0
    action_signal: str = ""

    def contains(self, value: float) -> bool:
        if self.low is not None and value < self.low:
            return False
        if self.high is not None and value > self.high:
            return False
        return True


@dataclass
class ClinicalNodeSpec:
    node_id: str
    label: str
    domain: str
    data_type: str
    importance: float
    critical: bool = False
    objective_required: bool = False
    remote_unknowable: bool = False
    acceptable_sources: List[str] = field(default_factory=list)
    ranges: List[RangeBand] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    action_implications: List[str] = field(default_factory=list)
    why_it_matters: str = ""


@dataclass
class ClinicalNodeState:
    node_id: str
    label: str
    domain: str
    data_type: str
    observed: bool
    raw_value: Optional[str]
    numeric_value: Optional[float]
    source: Optional[str]
    source_reliability_prior: float
    confidence: float
    range_band: Optional[str]
    range_severity: float
    boundary_distance: Optional[float]
    boundary_fragility: float
    perturbation_flip_risk: float
    missingness_state: str
    uncertainty_distribution: Dict[str, float]
    finding_categories: List[str]
    action_implications: List[str]
    dependencies: List[str]
    traces: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClinicalUncertaintyGraph:
    case_id: str
    domain: str
    nodes: Dict[str, ClinicalNodeState]
    summary: Dict[str, Any]
    strategic_signals: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "domain": self.domain,
            "summary": self.summary,
            "strategic_signals": self.strategic_signals,
            "nodes": {key: node.to_dict() for key, node in self.nodes.items()},
        }


@dataclass(frozen=True)
class StrategicSignalSpec:
    signal_id: str
    category: str
    pattern: str
    reliability_penalty: float
    severity: float
    action_signal: str
    reason: str
    applies_to_sources: Sequence[str] = ("patient", "caregiver")


@dataclass(frozen=True)
class StrategicSignal:
    signal_id: str
    category: str
    severity: float
    reliability_penalty: float
    action_signal: str
    reason: str
    evidence: str
    applies_to_sources: Sequence[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


NUMERIC_RANGE_REGISTRY: Dict[str, List[RangeBand]] = {
    "oxygen_saturation": [
        RangeBand("normal", low=95, severity=0.0),
        RangeBand("borderline", low=92, high=94.999, severity=0.25, action_signal="VERIFY_OXYGENATION"),
        RangeBand("abnormal", low=90, high=91.999, severity=0.65, action_signal="OBJECTIVE_INSTABILITY"),
        RangeBand("critical", high=89.999, severity=0.95, action_signal="ESCALATE_OXYGENATION"),
    ],
    "respiratory_rate": [
        RangeBand("normal", low=10, high=20, severity=0.0),
        RangeBand("abnormal_low", high=9.999, severity=0.65, action_signal="RESPIRATORY_INSTABILITY"),
        RangeBand("borderline_high", low=20.001, high=23.999, severity=0.35, action_signal="VERIFY_RESPIRATORY_RATE"),
        RangeBand("abnormal_high", low=24, high=29.999, severity=0.75, action_signal="RESPIRATORY_INSTABILITY"),
        RangeBand("critical_high", low=30, severity=0.95, action_signal="ESCALATE_RESPIRATORY_RATE"),
    ],
    "heart_rate": [
        RangeBand("normal", low=50, high=99.999, severity=0.0),
        RangeBand("tachycardia", low=100, high=119.999, severity=0.35, action_signal="VERIFY_HEMODYNAMICS"),
        RangeBand("marked_tachycardia", low=120, high=139.999, severity=0.75, action_signal="OBJECTIVE_INSTABILITY"),
        RangeBand("critical_tachycardia", low=140, severity=0.95, action_signal="ESCALATE_HEMODYNAMICS"),
        RangeBand("bradycardia", high=49.999, severity=0.65, action_signal="VERIFY_HEMODYNAMICS"),
    ],
    "systolic_bp": [
        RangeBand("normal", low=100, high=179.999, severity=0.0),
        RangeBand("borderline_low", low=90, high=99.999, severity=0.35, action_signal="VERIFY_HEMODYNAMICS"),
        RangeBand("hypotension", high=89.999, severity=0.90, action_signal="ESCALATE_HEMODYNAMICS"),
        RangeBand("severe_hypertension", low=180, severity=0.65, action_signal="VERIFY_END_ORGAN_SYMPTOMS"),
    ],
    "home_bp_number": [
        RangeBand("normal_or_mild", high=159.999, severity=0.0),
        RangeBand("very_high", low=160, high=179.999, severity=0.45, action_signal="VERIFY_BP_AND_SYMPTOMS"),
        RangeBand("critical_high", low=180, severity=0.85, action_signal="ESCALATE_BP_IF_SYMPTOMS"),
    ],
    "fever_measured": [
        RangeBand("normal", low=36.0, high=38.499, severity=0.0),
        RangeBand("hypothermia", high=35.999, severity=0.75, action_signal="OBJECTIVE_INSTABILITY"),
        RangeBand("fever", low=38.5, high=39.999, severity=0.55, action_signal="INFECTION_RISK"),
        RangeBand("high_fever", low=40.0, severity=0.80, action_signal="ESCALATE_FEVER_CONTEXT"),
    ],
    "glucose_number": [
        RangeBand("normal_or_mild", low=70, high=249.999, severity=0.0),
        RangeBand("low", high=69.999, severity=0.85, action_signal="ESCALATE_GLUCOSE"),
        RangeBand("high", low=250, high=299.999, severity=0.45, action_signal="VERIFY_DKA_RISK"),
        RangeBand("marked_high", low=300, severity=0.80, action_signal="DKA_RISK"),
    ],
    "lactate": [
        RangeBand("normal", high=1.999, severity=0.0),
        RangeBand("elevated", low=2.0, high=3.999, severity=0.75, action_signal="OBJECTIVE_INSTABILITY"),
        RangeBand("critical", low=4.0, severity=0.95, action_signal="ESCALATE_SHOCK_OR_SEPSIS"),
    ],
    "wbc": [
        RangeBand("normal", low=3.0, high=17.999, severity=0.0),
        RangeBand("low", high=2.999, severity=0.65, action_signal="INFECTION_OR_MARROW_RISK"),
        RangeBand("high", low=18.0, severity=0.65, action_signal="INFECTION_OR_INFLAMMATION_RISK"),
    ],
    "troponin": [
        RangeBand("not_interpretable_without_assay", severity=0.20, action_signal="VERIFY_ASSAY_AND_TREND"),
    ],
}


DEPENDENCY_REGISTRY: Dict[str, List[str]] = {
    "oxygen_saturation": ["respiratory_rate", "sentence_test", "exertional_tolerance"],
    "respiratory_rate": ["oxygen_saturation", "sentence_test"],
    "symptom_quality": ["exertional_component", "dyspnea", "ecg"],
    "home_bp_number": ["side_effects", "renal_function"],
    "glucose_number": ["ketones", "vomiting", "mental_status", "hydration_status"],
    "lactate": ["systolic_bp", "heart_rate", "temperature", "source_of_infection"],
}


STRATEGIC_SIGNAL_SPECS: List[StrategicSignalSpec] = [
    StrategicSignalSpec(
        "care_avoidance_pressure",
        "patient_incentive_distortion",
        r"\b(cannot afford|can't afford|no insurance|do not want to go to (?:the )?ER|don't want to go to (?:the )?ER|please do not send me|please don't send me|can i wait|have to work|need to work|avoid the hospital)\b",
        0.14,
        0.78,
        "DO_NOT_DOWNGRADE_RISK_FOR_REASSURANCE",
        "Cost, work, or access pressure may make reassurance/minimization strategically unreliable.",
    ),
    StrategicSignalSpec(
        "answer_gaming_pressure",
        "strategic_answering",
        r"\b(tell me what to say|what should i answer|need to pass|just approve|quickest way to get|all answers are no|say whatever gets me|mark everything no)\b",
        0.18,
        0.86,
        "VERIFY_BEFORE_AUTOMATION",
        "The answer pattern may be optimized to pass a workflow rather than communicate clinical state.",
    ),
    StrategicSignalSpec(
        "proxy_misalignment",
        "principal_agent_misalignment",
        r"\b(for my (wife|husband|son|daughter|friend|mom|mother|dad|father)|i am not the patient|using (?:my|someone else's) account|wrong patient|not my (medicine|medication|account|chart))\b",
        0.20,
        0.92,
        "VERIFY_IDENTITY_AND_AUTHORITY",
        "The speaker may not be the patient or may not share the patient's incentives/information.",
        applies_to_sources=("patient", "caregiver", "clinician"),
    ),
    StrategicSignalSpec(
        "coercion_or_observation_pressure",
        "unsafe_information_channel",
        r"\b(afraid of|not safe at home|he won't let me|she won't let me|they won't let me|forced me|don't tell|do not tell|partner is listening|whispering)\b",
        0.20,
        0.90,
        "PROTECTED_HUMAN_WORKFLOW",
        "The communication channel may be observed or coerced; negative answers cannot be trusted normally.",
    ),
    StrategicSignalSpec(
        "defensive_minimization",
        "self_presentation_distortion",
        r"\b(just anxiety|probably anxiety|just stress|overreacting|hypochondriac|not a complainer|don't complain|do not complain|tough it out|walk it off|nothing serious|i'll be fine|i will be fine|not the type to go to (?:the )?doctor|hate doctors)\b",
        0.10,
        0.64,
        "ASK_CONCRETE_FUNCTIONAL_FALSIFIERS",
        "Self-presentation or stoic minimization can distort symptom severity.",
    ),
    StrategicSignalSpec(
        "documentation_closure_pressure",
        "documentation_game",
        r"\b(stable for floor|no icu needs?|admit for observation|likely viral|reassuring workup|rule out|r/o|discharge when|medically cleared)\b",
        0.08,
        0.52,
        "PRESERVE_UNCERTAINTY_IN_HANDOFF",
        "Documentation may be compressing unresolved uncertainty into closure language.",
        applies_to_sources=("clinician", "chart"),
    ),
]


BOUNDARY_FRAGILITY_WIDTH: Dict[str, float] = {
    "oxygen_saturation": 3.0,
    "respiratory_rate": 4.0,
    "heart_rate": 10.0,
    "systolic_bp": 10.0,
    "home_bp_number": 10.0,
    "fever_measured": 0.6,
    "glucose_number": 50.0,
    "lactate": 0.6,
    "wbc": 2.0,
}


def build_uncertainty_graph(
    case: CaseInput,
    template: Sequence[SlotSpec],
    observations_by_concept: Dict[str, Observation],
    findings: Sequence[Finding],
) -> ClinicalUncertaintyGraph:
    specs = _node_specs_from_template(case.patient_context.domain, template, observations_by_concept)
    strategic_signals = _detect_strategic_signals(case)
    findings_by_concept: Dict[str, List[Finding]] = {}
    for finding in findings:
        findings_by_concept.setdefault(finding.concept, []).append(finding)

    nodes = {
        spec.node_id: _node_state(
            spec,
            observations_by_concept.get(spec.node_id),
            findings_by_concept.get(spec.node_id, []),
            strategic_signals,
        )
        for spec in specs
    }
    nodes.update(_strategic_signal_nodes(case.patient_context.domain, strategic_signals))
    summary = _graph_summary(nodes.values(), strategic_signals)
    return ClinicalUncertaintyGraph(
        case_id=case.case_id,
        domain=case.patient_context.domain,
        nodes=nodes,
        summary=summary,
        strategic_signals=[signal.to_dict() for signal in strategic_signals],
    )


def _node_specs_from_template(
    domain: str,
    template: Sequence[SlotSpec],
    observations_by_concept: Dict[str, Observation],
) -> List[ClinicalNodeSpec]:
    specs: Dict[str, ClinicalNodeSpec] = {}
    for slot in template:
        specs[slot.name] = ClinicalNodeSpec(
            node_id=slot.name,
            label=slot.label,
            domain=domain,
            data_type=_data_type_for(slot.name, slot),
            importance=slot.importance,
            critical=slot.critical,
            objective_required=slot.objective_required,
            remote_unknowable=slot.remote_unknowable,
            acceptable_sources=list(slot.acceptable_sources),
            ranges=list(NUMERIC_RANGE_REGISTRY.get(slot.name, [])),
            dependencies=list(DEPENDENCY_REGISTRY.get(slot.name, [])),
            action_implications=_slot_action_implications(slot),
            why_it_matters=slot.why_it_matters,
        )
    for concept in observations_by_concept:
        if concept in specs or concept == "unknown":
            continue
        if concept in NUMERIC_RANGE_REGISTRY:
            specs[concept] = ClinicalNodeSpec(
                node_id=concept,
                label=concept.replace("_", " ").title(),
                domain=domain,
                data_type="numeric",
                importance=0.70,
                objective_required=True,
                acceptable_sources=["device", "chart", "clinician", "patient"],
                ranges=list(NUMERIC_RANGE_REGISTRY[concept]),
                dependencies=list(DEPENDENCY_REGISTRY.get(concept, [])),
                action_implications=["interpret numeric node against expert range"],
            )
    return list(specs.values())


def _node_state(
    spec: ClinicalNodeSpec,
    observation: Optional[Observation],
    findings: Sequence[Finding],
    strategic_signals: Sequence[StrategicSignal],
) -> ClinicalNodeState:
    finding_categories = sorted({finding.category for finding in findings})
    numeric_value = _numeric_value(observation.raw_value if observation else None, spec.node_id)
    range_band = _range_band(spec, numeric_value)
    source = observation.source if observation else None
    source_prior = SOURCE_RELIABILITY_PRIOR.get(source or "", 0.0)
    confidence = float(observation.confidence if observation else 0.0)
    strategic_penalty = _strategic_reliability_penalty(observation.source if observation else None, spec, strategic_signals)
    if strategic_penalty:
        confidence = max(0.05, confidence - strategic_penalty)
    missingness_state = _missingness_state(spec, observation, finding_categories)
    distribution = _uncertainty_distribution(spec, observation, findings, range_band, strategic_penalty)
    boundary_distance, boundary_fragility, perturbation_flip_risk = _boundary_fragility(spec, numeric_value, range_band)
    action_implications = list(spec.action_implications)
    if range_band and range_band.action_signal:
        action_implications.append(range_band.action_signal)
    for finding in findings:
        if finding.category in {"red_flag", "contradictory", "objective_needed"}:
            action_implications.append(f"{finding.category.upper()}:{finding.rule_id}")

    traces = []
    if observation:
        traces.extend(observation.trace)
    if strategic_penalty:
        traces.append(f"STRATEGIC_RELIABILITY_PENALTY:-{strategic_penalty:.2f}")
    if range_band:
        traces.append(f"RANGE_BAND:{range_band.name}:severity={range_band.severity:.2f}")
    if boundary_fragility:
        traces.append(f"BOUNDARY_FRAGILITY:{boundary_fragility:.2f}:distance={boundary_distance}")
    for finding in findings:
        traces.append(f"FINDING:{finding.category}:{finding.rule_id}:severity={finding.severity:.2f}")

    return ClinicalNodeState(
        node_id=spec.node_id,
        label=spec.label,
        domain=spec.domain,
        data_type=spec.data_type,
        observed=observation is not None,
        raw_value=str(observation.raw_value) if observation else None,
        numeric_value=numeric_value,
        source=source,
        source_reliability_prior=round(source_prior, 3),
        confidence=round(confidence, 3),
        range_band=range_band.name if range_band else None,
        range_severity=round(range_band.severity if range_band else 0.0, 3),
        boundary_distance=round(boundary_distance, 3) if boundary_distance is not None else None,
        boundary_fragility=round(boundary_fragility, 3),
        perturbation_flip_risk=round(perturbation_flip_risk, 3),
        missingness_state=missingness_state,
        uncertainty_distribution=distribution,
        finding_categories=finding_categories,
        action_implications=_dedupe(action_implications),
        dependencies=list(spec.dependencies),
        traces=traces,
    )


def _uncertainty_distribution(
    spec: ClinicalNodeSpec,
    observation: Optional[Observation],
    findings: Sequence[Finding],
    range_band: Optional[RangeBand],
    strategic_penalty: float = 0.0,
) -> Dict[str, float]:
    categories = {finding.category for finding in findings}
    if spec.remote_unknowable:
        base = {"known_reliable": 0.05, "missing": 0.05, "semantic_uncertain": 0.05, "contradictory": 0.0, "range_abnormal": 0.0, "critical": 0.0, "remote_unknowable": 0.85}
    elif observation is None:
        missing_mass = 0.88 if "objective_needed" not in categories else 0.75
        base = {"known_reliable": 0.0, "missing": missing_mass, "semantic_uncertain": 0.10, "contradictory": 0.0, "range_abnormal": 0.0, "critical": 0.0, "remote_unknowable": 0.0}
    else:
        confidence = max(0.0, min(1.0, observation.confidence))
        range_severity = range_band.severity if range_band else 0.0
        contradiction = min(0.95, sum(f.severity for f in findings if f.category == "contradictory") / 1.5)
        red_flag = min(0.95, sum(f.severity for f in findings if f.category == "red_flag") / 1.5)
        semantic = min(0.95, (1.0 - confidence) + strategic_penalty + sum(f.severity for f in findings if f.category in {"distorted", "uncertain"}) / 2.5)
        critical = max(red_flag, range_severity if range_severity >= 0.85 else 0.0)
        base = {
            "known_reliable": confidence * (1.0 - max(contradiction, semantic * 0.5, critical * 0.4)),
            "missing": 0.0,
            "semantic_uncertain": semantic,
            "contradictory": contradiction,
            "range_abnormal": range_severity,
            "critical": critical,
            "remote_unknowable": 0.0,
        }
    return _normalize_distribution(base)


def _graph_summary(nodes: Iterable[ClinicalNodeState], strategic_signals: Sequence[StrategicSignal]) -> Dict[str, Any]:
    node_list = list(nodes)
    total_weight = sum(_node_weight(node) for node in node_list) or 1.0
    observed_weight = sum(_node_weight(node) for node in node_list if node.observed and node.missingness_state != "remote_unknowable")
    reliable_sum = sum(_node_weight(node) * node.confidence for node in node_list if node.observed)
    reliable_weight = sum(_node_weight(node) for node in node_list if node.observed) or 1.0
    objective_nodes = [node for node in node_list if node.data_type in {"numeric", "objective"} or "objective_needed" in node.finding_categories]
    objective_covered = [node for node in objective_nodes if node.observed and node.source in {"device", "chart", "clinician", "synthetic_truth"} and node.confidence >= 0.60]
    contradiction_load = _weighted_distribution_mass(node_list, "contradictory")
    semantic_uncertainty_load = _weighted_distribution_mass(node_list, "semantic_uncertain")
    range_risk_load = _weighted_distribution_mass(node_list, "range_abnormal")
    criticality_load = _weighted_distribution_mass(node_list, "critical")
    strategic_signal_load = min(1.0, sum(signal.severity for signal in strategic_signals) / 2.0)
    boundary_fragility_load = _weighted_node_attr(node_list, "boundary_fragility")
    boundary_flip_load = _weighted_node_attr(node_list, "perturbation_flip_risk")
    coupled_instability_load = _coupled_instability_load(node_list)
    remote_load = _weighted_distribution_mass(node_list, "remote_unknowable")
    missing_load = _weighted_distribution_mass(node_list, "missing")
    objective_coverage = len(objective_covered) / len(objective_nodes) if objective_nodes else 1.0
    completeness = observed_weight / total_weight
    reliability = reliable_sum / reliable_weight
    boundary_sensitivity_index = min(
        1.0,
        0.45 * boundary_flip_load
        + 0.25 * boundary_fragility_load
        + 0.20 * coupled_instability_load
        + 0.10 * range_risk_load,
    )
    action_pressure = min(
        1.0,
        0.28 * criticality_load
        + 0.20 * range_risk_load
        + 0.16 * contradiction_load
        + 0.10 * missing_load
        + 0.07 * remote_load
        + 0.10 * strategic_signal_load
        + 0.09 * boundary_sensitivity_index,
    )
    graph_readiness = (
        0.38 * completeness
        + 0.27 * reliability
        + 0.17 * objective_coverage
        + 0.10 * (1.0 - semantic_uncertainty_load)
        + 0.08 * (1.0 - range_risk_load)
        - 0.23 * contradiction_load
        - 0.30 * criticality_load
        - 0.12 * missing_load
        - 0.10 * strategic_signal_load
        - 0.10 * boundary_sensitivity_index
    )
    graph_readiness_index = max(0.0, min(100.0, graph_readiness * 100.0))
    breached_nodes = [
        node.node_id
        for node in node_list
        if node.range_severity >= 0.75 or node.uncertainty_distribution.get("critical", 0.0) >= 0.50
    ]
    weak_nodes = [
        node.node_id
        for node in node_list
        if node.node_id not in breached_nodes
        and (
            node.uncertainty_distribution.get("semantic_uncertain", 0.0) >= 0.35
            or node.uncertainty_distribution.get("missing", 0.0) >= 0.50
            or node.uncertainty_distribution.get("contradictory", 0.0) >= 0.35
        )
    ]
    fragile_nodes = [
        node.node_id
        for node in node_list
        if node.boundary_fragility >= 0.30 or node.perturbation_flip_risk >= 0.30
    ]
    return {
        "node_count": len(node_list),
        "observed_nodes": sum(1 for node in node_list if node.observed),
        "completeness": round(completeness, 3),
        "reliability": round(reliability, 3),
        "objective_coverage": round(objective_coverage, 3),
        "missing_load": round(missing_load, 3),
        "semantic_uncertainty_load": round(semantic_uncertainty_load, 3),
        "contradiction_load": round(contradiction_load, 3),
        "range_risk_load": round(range_risk_load, 3),
        "criticality_load": round(criticality_load, 3),
        "strategic_signal_load": round(strategic_signal_load, 3),
        "boundary_fragility_load": round(boundary_fragility_load, 3),
        "boundary_flip_load": round(boundary_flip_load, 3),
        "coupled_instability_load": round(coupled_instability_load, 3),
        "boundary_sensitivity_index": round(boundary_sensitivity_index, 3),
        "remote_unknowable_load": round(remote_load, 3),
        "action_pressure": round(action_pressure, 3),
        "graph_readiness_index": round(graph_readiness_index, 1),
        "breached_nodes": breached_nodes,
        "weak_nodes": weak_nodes[:12],
        "fragile_nodes": fragile_nodes[:12],
        "strategic_signals": [signal.signal_id for signal in strategic_signals],
    }


def _missingness_state(spec: ClinicalNodeSpec, observation: Optional[Observation], categories: Sequence[str]) -> str:
    if spec.remote_unknowable:
        return "remote_unknowable"
    if observation is None and spec.objective_required:
        return "objective_needed"
    if observation is None:
        return "missing"
    if "contradictory" in categories:
        return "conflicted"
    if "distorted" in categories or "uncertain" in categories:
        return "observed_uncertain"
    return "observed"


def _detect_strategic_signals(case: CaseInput) -> List[StrategicSignal]:
    text = " ".join(
        [
            case.patient_context.chief_concern,
            case.patient_context.domain,
            " ".join(case.patient_context.known_conditions),
            *[f"{statement.question} {statement.answer}" for statement in case.statements],
        ]
    )
    signals: List[StrategicSignal] = []
    for spec in STRATEGIC_SIGNAL_SPECS:
        match = re.search(spec.pattern, text, re.I | re.S)
        if not match:
            continue
        signals.append(
            StrategicSignal(
                signal_id=spec.signal_id,
                category=spec.category,
                severity=spec.severity,
                reliability_penalty=spec.reliability_penalty,
                action_signal=spec.action_signal,
                reason=spec.reason,
                evidence=_snippet(text, match.start(), match.end()),
                applies_to_sources=tuple(spec.applies_to_sources),
            )
        )
    return signals


def _strategic_signal_nodes(domain: str, signals: Sequence[StrategicSignal]) -> Dict[str, ClinicalNodeState]:
    nodes: Dict[str, ClinicalNodeState] = {}
    for signal in signals:
        distribution = _normalize_distribution(
            {
                "known_reliable": max(0.0, 0.25 - signal.reliability_penalty),
                "missing": 0.0,
                "semantic_uncertain": signal.severity,
                "contradictory": 0.0,
                "range_abnormal": 0.0,
                "critical": signal.severity if signal.severity >= 0.88 else 0.0,
                "remote_unknowable": 0.0,
            }
        )
        nodes[f"strategic_{signal.signal_id}"] = ClinicalNodeState(
            node_id=f"strategic_{signal.signal_id}",
            label=signal.signal_id.replace("_", " ").title(),
            domain=domain,
            data_type="strategic_signal",
            observed=True,
            raw_value=signal.evidence,
            numeric_value=None,
            source="patient",
            source_reliability_prior=SOURCE_RELIABILITY_PRIOR["patient"],
            confidence=round(max(0.05, 1.0 - signal.reliability_penalty - signal.severity * 0.35), 3),
            range_band=None,
            range_severity=0.0,
            boundary_distance=None,
            boundary_fragility=0.0,
            perturbation_flip_risk=0.0,
            missingness_state="strategic_signal_active",
            uncertainty_distribution=distribution,
            finding_categories=["strategic_signal"],
            action_implications=[signal.action_signal, f"RELIABILITY_PENALTY:{signal.reliability_penalty:.2f}"],
            dependencies=[],
            traces=[f"STRATEGIC_SIGNAL:{signal.signal_id}:severity={signal.severity:.2f}:penalty={signal.reliability_penalty:.2f}"],
        )
    return nodes


def _strategic_reliability_penalty(
    source: Optional[str],
    spec: ClinicalNodeSpec,
    signals: Sequence[StrategicSignal],
) -> float:
    if source is None:
        return 0.0
    applicable = [
        signal.reliability_penalty
        for signal in signals
        if source in signal.applies_to_sources
        and spec.data_type not in {"numeric", "objective"}
        and not spec.remote_unknowable
    ]
    return min(0.28, sum(applicable)) if applicable else 0.0


def _range_band(spec: ClinicalNodeSpec, value: Optional[float]) -> Optional[RangeBand]:
    if value is None:
        return None
    for band in spec.ranges:
        if band.contains(value):
            return band
    return None


def _boundary_fragility(
    spec: ClinicalNodeSpec,
    value: Optional[float],
    current_band: Optional[RangeBand],
) -> tuple[Optional[float], float, float]:
    if value is None or not spec.ranges:
        return None, 0.0, 0.0
    current_severity = current_band.severity if current_band else 0.0
    width = BOUNDARY_FRAGILITY_WIDTH.get(spec.node_id, 1.0)
    best_distance: Optional[float] = None
    best_severity_delta = 0.0
    flip_risk = 0.0

    for band in spec.ranges:
        if band.severity <= current_severity:
            continue
        boundaries = [b for b in (band.low, band.high) if b is not None]
        for boundary in boundaries:
            distance = abs(value - boundary)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_severity_delta = max(0.0, band.severity - current_severity)
            if distance <= width:
                flip_risk = max(flip_risk, (1.0 - distance / width) * max(0.15, band.severity - current_severity))

    if best_distance is None:
        return None, 0.0, 0.0
    fragility = 0.0
    if best_distance <= width:
        fragility = (1.0 - best_distance / width) * max(0.20, best_severity_delta)
    return best_distance, max(0.0, min(1.0, fragility)), max(0.0, min(1.0, flip_risk))


def _numeric_value(raw: Any, concept: str) -> Optional[float]:
    if raw is None:
        return None
    text = str(raw)
    numbers = [float(match) for match in re.findall(r"-?\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    if concept in {"home_bp_number", "systolic_bp"}:
        return numbers[0]
    return numbers[-1] if len(numbers) > 1 and ":" in text else numbers[0]


def _data_type_for(concept: str, slot: SlotSpec) -> str:
    if concept in NUMERIC_RANGE_REGISTRY:
        return "numeric"
    if slot.slot_type in {"objective", "lab"}:
        return "objective"
    return slot.slot_type or "semantic"


def _slot_action_implications(slot: SlotSpec) -> List[str]:
    implications: List[str] = []
    if slot.critical:
        implications.append("critical node")
    if slot.objective_required:
        implications.append("requires objective evidence")
    if slot.remote_unknowable:
        implications.append("cannot be resolved from current modality alone")
    return implications


def _weighted_distribution_mass(nodes: Sequence[ClinicalNodeState], key: str) -> float:
    total_weight = sum(_node_weight(node) for node in nodes) or 1.0
    value = sum(_node_weight(node) * node.uncertainty_distribution.get(key, 0.0) for node in nodes) / total_weight
    return max(0.0, min(1.0, value))


def _weighted_node_attr(nodes: Sequence[ClinicalNodeState], attr: str) -> float:
    total_weight = sum(_node_weight(node) for node in nodes) or 1.0
    value = sum(_node_weight(node) * float(getattr(node, attr, 0.0) or 0.0) for node in nodes) / total_weight
    return max(0.0, min(1.0, value))


def _coupled_instability_load(nodes: Sequence[ClinicalNodeState]) -> float:
    unstable = [
        node
        for node in nodes
        if node.data_type == "numeric"
        and (node.range_severity >= 0.45 or node.boundary_fragility >= 0.35)
    ]
    if not unstable:
        return 0.0
    dependency_links = 0
    unstable_ids = {node.node_id for node in unstable}
    for node in unstable:
        dependency_links += sum(1 for dependency in node.dependencies if dependency in unstable_ids)
    multi_node_pressure = min(1.0, len(unstable) / 4.0)
    coupling_pressure = min(1.0, dependency_links / 4.0)
    return max(multi_node_pressure, coupling_pressure)


def _node_weight(node: ClinicalNodeState) -> float:
    if node.data_type == "strategic_signal":
        return 0.8
    if "critical node" in node.action_implications:
        return 1.2
    return 1.0


def _normalize_distribution(values: Dict[str, float]) -> Dict[str, float]:
    clipped = {key: max(0.0, min(1.0, float(value))) for key, value in values.items()}
    total = sum(clipped.values())
    if total <= 0:
        return clipped
    normalized = {key: round(value / total, 3) for key, value in clipped.items()}
    # Keep probabilities summing close to one after rounding.
    drift = round(1.0 - sum(normalized.values()), 3)
    if normalized and abs(drift) >= 0.001:
        first = next(iter(normalized))
        normalized[first] = round(normalized[first] + drift, 3)
    return normalized


def _dedupe(items: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        if not item or item in seen:
            continue
        out.append(item)
        seen.add(item)
    return out


def _snippet(text: str, start: int, end: int, width: int = 70) -> str:
    lo = max(0, start - width // 2)
    hi = min(len(text), end + width // 2)
    return text[lo:hi].strip()
