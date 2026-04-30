"""Disposition Handoff Sufficiency Engine.

This module adapts JRE + Black Swan Guardrails to a retrospective ED-admission
question:

    At ED disposition time, did the available record contain enough actionable
    information to support the inpatient trajectory that actually unfolded?

The primary outcome is intentionally post-discharge and objective. It does not
penalize normal pending inpatient work. It looks for trajectory revision with
measurable burden after admission.
"""
from __future__ import annotations

import json
import re
import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple

from .black_swan import BlackSwanGuardrailEngine, GuardrailReport
from .engine import JudgmentReadinessEngine
from .models import CaseInput, PatientContext, ReadinessReport, Statement


InputMode = Literal["notes", "dialogue", "hybrid"]
DispositionState = Literal[
    "SUFFICIENT",
    "UNDER_SPECIFIED",
    "ACUITY_MISMATCH_RISK",
    "DIAGNOSTIC_PIVOT_RISK",
]


@dataclass
class DispositionSnapshot:
    """Information available at the ED disposition decision.

    `notes` mode evaluates the documented ED disposition representation.
    `dialogue` mode evaluates the current elicitation transcript before it has
    been converted into a note. `hybrid` mode allows both.
    """

    case_id: str
    input_mode: InputMode
    age: int
    chief_concern: str
    domain: str
    disposition_diagnosis: str
    admission_service: str = ""
    level_of_care: str = "floor"
    ed_note: str = ""
    key_pmh: List[str] = field(default_factory=list)
    ed_results: Dict[str, Any] = field(default_factory=dict)
    vital_trend: Dict[str, Sequence[Any]] = field(default_factory=dict)
    treatments: List[str] = field(default_factory=list)
    dialogue: List[Statement] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PostDischargeTrajectory:
    """Objective post-discharge facts used to label PTR-B.

    These fields are intentionally downstream of ED disposition. They are used
    to label the benchmark, not to score the disposition snapshot.
    """

    ed_diagnosis_category: str = ""
    discharge_diagnosis_category: str = ""
    discharge_principal_diagnosis: str = ""
    los_hours: Optional[float] = None
    expected_los_hours: Optional[float] = None
    icu_transfer_within_24h: bool = False
    stepdown_transfer_within_24h: bool = False
    rapid_response_within_24h: bool = False
    mortality: bool = False
    major_procedure: bool = False
    service_change_due_to_diagnosis: bool = False
    major_therapeutic_pivots: List[str] = field(default_factory=list)
    delayed_definitive_therapy_hours: Optional[float] = None
    discharge_to_higher_level_of_care: bool = False
    readmission_30d: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TrajectoryBurdenLabel:
    """Post-Disposition Trajectory Revision with Burden label."""

    ptr_b_positive: bool
    revision_events: List[str]
    burden_events: List[str]
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DispositionSufficiencyReport:
    case_id: str
    input_mode: InputMode
    dsi: float
    state: DispositionState
    jre_state: str
    guardrail_state: str
    risk_factors: List[str]
    protective_factors: List[str]
    input_limitations: List[str]
    jre_report: ReadinessReport
    guardrail_report: GuardrailReport
    trajectory_label: Optional[TrajectoryBurdenLabel] = None

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["jre_report"] = self.jre_report.to_dict()
        out["guardrail_report"] = self.guardrail_report.to_dict()
        out["trajectory_label"] = self.trajectory_label.to_dict() if self.trajectory_label else None
        return out


@dataclass
class BenchmarkCase:
    """Fixture row for the synthetic or retrospective DHSE benchmark."""

    snapshot: DispositionSnapshot
    trajectory: PostDischargeTrajectory
    expected_ptr_b: Optional[bool] = None
    expected_state: Optional[DispositionState] = None
    defect_family: str = ""
    notes: str = ""


@dataclass
class BenchmarkRun:
    """Reports and aggregate metrics for a DHSE benchmark run."""

    reports: List[DispositionSufficiencyReport]
    metrics: Dict[str, Any]
    baseline_metrics: Dict[str, Dict[str, Any]]
    analysis: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics": self.metrics,
            "baseline_metrics": self.baseline_metrics,
            "analysis": self.analysis,
            "reports": [report.to_dict() for report in self.reports],
        }


NONSPECIFIC_DIAGNOSIS = re.compile(
    r"\b(weakness|dizziness|syncope|near syncope|altered mental status|ams|"
    r"abdominal pain|chest pain|back pain|shortness of breath|dyspnea|fall|"
    r"fever|failure to thrive|pain|malaise|dehydration|rule out|r/o|unclear|"
    r"unknown|symptom|observation)\b",
    re.I,
)

HIGH_RISK_PMH = re.compile(
    r"\b(chf|heart failure|cad|coronary|diabetes|dialysis|ckd|renal failure|"
    r"transplant|chemo|chemotherapy|immunosuppressed|neutropenia|cirrhosis|"
    r"warfarin|eliquis|apixaban|xarelto|rivaroxaban|blood thinner|pregnan)\b",
    re.I,
)

HIGH_INTENSITY_TREATMENTS = re.compile(
    r"\b(pressors?|norepi|vasopressin|intubat|bipap|high flow|nonrebreather|"
    r"insulin drip|heparin drip|blood transfusion|massive transfusion|cefepime|"
    r"vancomycin|zosyn|piperacillin|tazobactam|broad.?spectrum|sepsis bolus|"
    r"cath lab|stroke alert|trauma activation)\b",
    re.I,
)

VALUE_RE = re.compile(r"-?\d+(?:\.\d+)?")


class DispositionHandoffSufficiencyEngine:
    """Score ED disposition handoff sufficiency and label retrospective outcomes."""

    def __init__(
        self,
        jre: Optional[JudgmentReadinessEngine] = None,
        guard: Optional[BlackSwanGuardrailEngine] = None,
    ) -> None:
        self.jre = jre or JudgmentReadinessEngine()
        self.guard = guard or BlackSwanGuardrailEngine()

    def evaluate_snapshot(self, snapshot: DispositionSnapshot) -> DispositionSufficiencyReport:
        case = self._case_from_snapshot(snapshot)
        jre_report = self.jre.evaluate(case)
        guardrail_report = self.guard.evaluate(case, jre_report)
        risk_factors, protective_factors = self._snapshot_risk_factors(snapshot, jre_report, guardrail_report)
        dsi = self._score_dsi(snapshot, jre_report, guardrail_report, risk_factors)
        state = self._decide_state(snapshot, dsi, risk_factors, guardrail_report)

        return DispositionSufficiencyReport(
            case_id=snapshot.case_id,
            input_mode=snapshot.input_mode,
            dsi=dsi,
            state=state,
            jre_state=jre_report.state,
            guardrail_state=guardrail_report.guardrail_state,
            risk_factors=risk_factors,
            protective_factors=protective_factors,
            input_limitations=self._input_limitations(snapshot),
            jre_report=jre_report,
            guardrail_report=guardrail_report,
        )

    def evaluate_retrospective(
        self,
        snapshot: DispositionSnapshot,
        trajectory: PostDischargeTrajectory,
    ) -> DispositionSufficiencyReport:
        report = self.evaluate_snapshot(snapshot)
        report.trajectory_label = self.label_trajectory(trajectory)
        return report

    def label_trajectory(self, trajectory: PostDischargeTrajectory) -> TrajectoryBurdenLabel:
        revision_events: List[str] = []
        burden_events: List[str] = []

        ed_cat = trajectory.ed_diagnosis_category.strip().lower()
        dc_cat = trajectory.discharge_diagnosis_category.strip().lower()
        if ed_cat and dc_cat and ed_cat != dc_cat:
            revision_events.append("DIAGNOSTIC_CATEGORY_REVISION")

        if trajectory.icu_transfer_within_24h:
            revision_events.append("EARLY_ICU_UPGRADE")
            burden_events.append("ICU_TRANSFER_24H")
        if trajectory.stepdown_transfer_within_24h:
            revision_events.append("EARLY_STEPDOWN_UPGRADE")
            burden_events.append("STEPDOWN_TRANSFER_24H")
        if trajectory.rapid_response_within_24h:
            revision_events.append("RAPID_RESPONSE_24H")
            burden_events.append("RAPID_RESPONSE_24H")
        if trajectory.service_change_due_to_diagnosis:
            revision_events.append("SERVICE_CHANGE_FOR_DIAGNOSTIC_REVISION")

        for pivot in trajectory.major_therapeutic_pivots:
            clean = re.sub(r"[^A-Z0-9]+", "_", pivot.upper()).strip("_")
            revision_events.append(f"THERAPEUTIC_PIVOT_{clean or 'UNSPECIFIED'}")

        if trajectory.mortality:
            burden_events.append("IN_HOSPITAL_MORTALITY")
        if trajectory.major_procedure:
            burden_events.append("MAJOR_PROCEDURE")
        if trajectory.discharge_to_higher_level_of_care:
            burden_events.append("HIGHER_LEVEL_DISCHARGE")
        if trajectory.readmission_30d:
            burden_events.append("READMISSION_30D")
        if (
            trajectory.delayed_definitive_therapy_hours is not None
            and trajectory.delayed_definitive_therapy_hours >= 6
        ):
            burden_events.append("DELAYED_DEFINITIVE_THERAPY_GE_6H")

        if (
            trajectory.los_hours is not None
            and trajectory.expected_los_hours is not None
            and trajectory.expected_los_hours > 0
            and trajectory.los_hours >= trajectory.expected_los_hours * 1.5
            and trajectory.los_hours - trajectory.expected_los_hours >= 24
        ):
            burden_events.append("RISK_ADJUSTED_LOS_EXCESS")

        ptr_b = bool(revision_events and burden_events)
        rationale = (
            "PTR-B positive: objective trajectory revision occurred with measurable burden."
            if ptr_b
            else "PTR-B negative: revision and burden criteria were not both met."
        )
        return TrajectoryBurdenLabel(ptr_b, revision_events, burden_events, rationale)

    def benchmark(self, reports: Sequence[DispositionSufficiencyReport], review_fraction: float = 0.10) -> Dict[str, Any]:
        labeled = [r for r in reports if r.trajectory_label is not None]
        labels = [bool(r.trajectory_label and r.trajectory_label.ptr_b_positive) for r in labeled]
        risk_scores = [100.0 - r.dsi for r in labeled]
        return _binary_metric_summary(risk_scores, labels, review_fraction)

    def run_benchmark_cases(
        self,
        cases: Sequence[BenchmarkCase],
        review_fraction: float = 0.10,
    ) -> BenchmarkRun:
        reports = [self.evaluate_retrospective(case.snapshot, case.trajectory) for case in cases]
        labels = [bool(report.trajectory_label and report.trajectory_label.ptr_b_positive) for report in reports]
        primary_metrics = self.benchmark(reports, review_fraction=review_fraction)
        baseline_metrics = self._baseline_metrics(cases, reports, labels, review_fraction)
        analysis = make_paper_analysis(cases, reports, review_fraction=review_fraction)
        return BenchmarkRun(reports=reports, metrics=primary_metrics, baseline_metrics=baseline_metrics, analysis=analysis)

    def run_benchmark_jsonl(
        self,
        path: str | Path,
        review_fraction: float = 0.10,
    ) -> BenchmarkRun:
        return self.run_benchmark_cases(load_benchmark_cases(path), review_fraction=review_fraction)

    def _baseline_metrics(
        self,
        cases: Sequence[BenchmarkCase],
        reports: Sequence[DispositionSufficiencyReport],
        labels: Sequence[bool],
        review_fraction: float,
    ) -> Dict[str, Dict[str, Any]]:
        scores: Dict[str, List[float]] = {
            "structured_severity": [],
            "nonspecific_diagnosis": [],
            "ed_los": [],
            "jre_only": [],
            "black_swan_only": [],
        }
        for case, report in zip(cases, reports):
            scores["structured_severity"].append(_structured_severity_risk(case.snapshot))
            scores["nonspecific_diagnosis"].append(100.0 if NONSPECIFIC_DIAGNOSIS.search(case.snapshot.disposition_diagnosis or "") else 0.0)
            scores["ed_los"].append(_to_float(case.snapshot.metadata.get("ed_los_hours")) or 0.0)
            scores["jre_only"].append(100.0 - report.jre_report.scores.readiness_index)
            scores["black_swan_only"].append(_guardrail_risk_score(report.guardrail_state))
        return {
            name: _binary_metric_summary(values, labels, review_fraction)
            for name, values in scores.items()
        }

    # Snapshot conversion
    # ------------------------------------------------------------------
    def _case_from_snapshot(self, snapshot: DispositionSnapshot) -> CaseInput:
        statements: List[Statement] = []

        if snapshot.input_mode in {"dialogue", "hybrid"}:
            statements.extend(snapshot.dialogue)

        if snapshot.input_mode in {"notes", "hybrid"} and snapshot.ed_note:
            statements.extend(self._note_statements(snapshot.ed_note))

        statements.append(
            Statement(
                question="ED disposition diagnosis",
                answer=snapshot.disposition_diagnosis,
                concept=None,
                source="clinician",
            )
        )
        if snapshot.admission_service:
            statements.append(
                Statement(
                    question="Admitting service",
                    answer=snapshot.admission_service,
                    concept=None,
                    source="clinician",
                )
            )
        if snapshot.level_of_care:
            statements.append(
                Statement(
                    question="Disposition level of care",
                    answer=snapshot.level_of_care,
                    concept=None,
                    source="clinician",
                )
            )

        for item in snapshot.key_pmh:
            statements.append(Statement("Key PMH", item, concept=None, source="chart"))
        for treatment in snapshot.treatments:
            statements.append(Statement("ED treatment", treatment, concept=None, source="clinician"))
        for key, value in snapshot.ed_results.items():
            statements.append(
                Statement(
                    question=f"ED resulted data: {key}",
                    answer=f"{key}: {value}",
                    concept=_concept_for_key(key),
                    source="chart",
                )
            )
        for key, values in snapshot.vital_trend.items():
            latest = _latest(values)
            if latest is not None:
                statements.append(
                    Statement(
                        question=f"Latest ED vital: {key}",
                        answer=f"{key}: {latest}",
                        concept=_concept_for_key(key),
                        source="device",
                    )
                )

        return CaseInput(
            case_id=snapshot.case_id,
            patient_context=PatientContext(
                age=snapshot.age,
                chief_concern=snapshot.chief_concern,
                domain=snapshot.domain,
                modality="in_person" if snapshot.input_mode == "notes" else "text",
                known_conditions=snapshot.key_pmh,
            ),
            statements=statements,
            ground_truth={"input_mode": snapshot.input_mode},
        )

    def _note_statements(self, note: str) -> List[Statement]:
        chunks = [c.strip() for c in re.split(r"[\n.;]+", note) if c.strip()]
        return [
            Statement("ED note sentence", chunk, concept=None, source="clinician")
            for chunk in chunks[:80]
        ]

    # ------------------------------------------------------------------
    # DSI scoring
    # ------------------------------------------------------------------
    def _snapshot_risk_factors(
        self,
        snapshot: DispositionSnapshot,
        jre_report: ReadinessReport,
        guardrail_report: GuardrailReport,
    ) -> Tuple[List[str], List[str]]:
        risks: List[str] = []
        protective: List[str] = []

        if jre_report.scores.readiness_index < 65:
            risks.append(f"LOW_JRE_READINESS:{jre_report.scores.readiness_index:.1f}")
        if jre_report.state == "ESCALATE":
            risks.append("JRE_STATE_ESCALATE")
        elif jre_report.state == "NEED_OBJECTIVE_DATA":
            risks.append("JRE_STATE_NEED_OBJECTIVE_DATA")
        graph_summary = (jre_report.uncertainty_graph or {}).get("summary", {})
        action_pressure = float(graph_summary.get("action_pressure", 0.0) or 0.0)
        range_risk_load = float(graph_summary.get("range_risk_load", 0.0) or 0.0)
        missing_load = float(graph_summary.get("missing_load", 0.0) or 0.0)
        objective_coverage = float(graph_summary.get("objective_coverage", 1.0) or 1.0)
        strategic_signal_load = float(graph_summary.get("strategic_signal_load", 0.0) or 0.0)
        boundary_sensitivity = float(graph_summary.get("boundary_sensitivity_index", 0.0) or 0.0)
        breached_nodes = graph_summary.get("breached_nodes", []) or []
        fragile_nodes = graph_summary.get("fragile_nodes", []) or []
        if action_pressure >= 0.25:
            risks.append(f"GRAPH_ACTION_PRESSURE:{action_pressure:.2f}")
        if range_risk_load >= 0.20:
            risks.append(f"GRAPH_RANGE_RISK_LOAD:{range_risk_load:.2f}")
        if objective_coverage < 0.50:
            risks.append(f"GRAPH_OBJECTIVE_COVERAGE_GAP:{objective_coverage:.2f}")
        if missing_load >= 0.35:
            risks.append(f"GRAPH_MISSING_LOAD:{missing_load:.2f}")
        if strategic_signal_load > 0:
            risks.append(f"GRAPH_STRATEGIC_SIGNAL_LOAD:{strategic_signal_load:.2f}")
        if boundary_sensitivity >= 0.18:
            risks.append(f"GRAPH_BOUNDARY_SENSITIVITY:{boundary_sensitivity:.2f}")
        for node_id in breached_nodes[:6]:
            risks.append(f"GRAPH_BREACHED_NODE:{node_id}")
        for node_id in fragile_nodes[:4]:
            risks.append(f"GRAPH_FRAGILE_NODE:{node_id}")
        guardrail_assumption_breach = _guardrail_is_assumption_breach(guardrail_report)
        if guardrail_assumption_breach and guardrail_report.guardrail_state in {"ESCALATE", "FAIL_CLOSED", "ROUTE_CLINICIAN", "HOLD_AND_VERIFY"}:
            risks.append(f"GUARDRAIL_{guardrail_report.guardrail_state}")

        objective_risks = self._objective_instability(snapshot)
        risks.extend(objective_risks)

        text_blob = " ".join([snapshot.disposition_diagnosis, snapshot.ed_note, " ".join(snapshot.treatments)])
        nonspecific = NONSPECIFIC_DIAGNOSIS.search(snapshot.disposition_diagnosis or "") is not None
        high_risk_host = any(HIGH_RISK_PMH.search(item) for item in snapshot.key_pmh)
        high_intensity_treatment = HIGH_INTENSITY_TREATMENTS.search(text_blob) is not None

        if nonspecific and (objective_risks or high_risk_host or high_intensity_treatment):
            risks.append("NONSPECIFIC_DISPOSITION_WITH_HIGH_RISK_CONTEXT")
        elif nonspecific:
            risks.append("NONSPECIFIC_DISPOSITION_LABEL")

        if high_risk_host:
            risks.append("HIGH_RISK_HOST_FACTORS")
        if high_intensity_treatment and nonspecific:
            risks.append("TREATMENT_INTENSITY_EXCEEDS_PROBLEM_REPRESENTATION")

        if jre_report.scores.readiness_index >= 78 and guardrail_report.guardrail_state == "ALLOW_WITH_AUDIT":
            protective.append("HIGH_JRE_READINESS_AND_NO_GUARDRAIL_BLOCK")
        if not objective_risks:
            protective.append("NO_OBJECTIVE_INSTABILITY_PATTERN_DETECTED")
        if not nonspecific:
            protective.append("SPECIFIC_DISPOSITION_DIAGNOSIS")

        return _dedupe(risks), _dedupe(protective)

    def _objective_instability(self, snapshot: DispositionSnapshot) -> List[str]:
        risks: List[str] = []
        latest = {key.lower(): _to_float(_latest(values)) for key, values in snapshot.vital_trend.items()}
        latest.update({key.lower(): _to_float(value) for key, value in snapshot.ed_results.items()})

        spo2 = _first_present(latest, "spo2", "o2", "oxygen", "oxygen_saturation")
        if spo2 is not None and spo2 < 92:
            risks.append(f"LOW_OXYGEN_SATURATION:{spo2:g}")

        sbp = _first_present(latest, "sbp", "systolic", "blood_pressure_systolic")
        if sbp is not None and sbp < 90:
            risks.append(f"HYPOTENSION_SBP:{sbp:g}")

        hr = _first_present(latest, "hr", "heart_rate", "pulse")
        if hr is not None and hr >= 120:
            risks.append(f"MARKED_TACHYCARDIA:{hr:g}")

        rr = _first_present(latest, "rr", "respiratory_rate")
        if rr is not None and rr >= 24:
            risks.append(f"TACHYPNEA:{rr:g}")

        temp = _first_present(latest, "temp", "temperature", "fever")
        if temp is not None and (temp >= 38.5 or temp < 36):
            risks.append(f"ABNORMAL_TEMPERATURE:{temp:g}")

        lactate = _first_present(latest, "lactate")
        if lactate is not None and lactate >= 2.5:
            risks.append(f"ELEVATED_LACTATE:{lactate:g}")

        glucose = _first_present(latest, "glucose", "blood_glucose")
        if glucose is not None and glucose >= 300:
            risks.append(f"MARKED_HYPERGLYCEMIA:{glucose:g}")

        wbc = _first_present(latest, "wbc", "white_blood_cell_count")
        if wbc is not None and (wbc >= 18 or wbc < 3):
            risks.append(f"ABNORMAL_WBC:{wbc:g}")

        if snapshot.level_of_care.lower() in {"floor", "med/surg", "med surg", "observation"}:
            for risk in list(risks):
                if risk.startswith(("LOW_OXYGEN", "HYPOTENSION", "MARKED_TACHYCARDIA", "TACHYPNEA", "ELEVATED_LACTATE")):
                    risks.append("FLOOR_DISPOSITION_WITH_OBJECTIVE_INSTABILITY")
                    break
        return _dedupe(risks)

    def _score_dsi(
        self,
        snapshot: DispositionSnapshot,
        jre_report: ReadinessReport,
        guardrail_report: GuardrailReport,
        risk_factors: Sequence[str],
    ) -> float:
        score = 100.0
        mode_weight = 0.10 if snapshot.input_mode == "notes" else 0.35
        score -= max(0.0, 78.0 - jre_report.scores.readiness_index) * mode_weight

        if _guardrail_is_assumption_breach(guardrail_report):
            guard_penalty = {
                "ESCALATE": 35.0,
                "FAIL_CLOSED": 30.0,
                "ROUTE_CLINICIAN": 22.0,
                "HOLD_AND_VERIFY": 14.0,
                "ALLOW_WITH_AUDIT": 0.0,
            }.get(guardrail_report.guardrail_state, 10.0)
        else:
            guard_penalty = {
                "ESCALATE": 8.0,
                "FAIL_CLOSED": 12.0,
                "ROUTE_CLINICIAN": 8.0,
                "HOLD_AND_VERIFY": 4.0,
                "ALLOW_WITH_AUDIT": 0.0,
            }.get(guardrail_report.guardrail_state, 4.0)
        score -= guard_penalty

        for risk in risk_factors:
            if risk.startswith(("LOW_OXYGEN", "HYPOTENSION", "ELEVATED_LACTATE")):
                score -= 16.0
            elif risk.startswith(("MARKED_TACHYCARDIA", "TACHYPNEA", "ABNORMAL_TEMPERATURE", "MARKED_HYPERGLYCEMIA", "ABNORMAL_WBC")):
                score -= 10.0
            elif risk == "FLOOR_DISPOSITION_WITH_OBJECTIVE_INSTABILITY":
                score -= 12.0
            elif risk == "TREATMENT_INTENSITY_EXCEEDS_PROBLEM_REPRESENTATION":
                score -= 14.0
            elif risk == "NONSPECIFIC_DISPOSITION_WITH_HIGH_RISK_CONTEXT":
                score -= 12.0
            elif risk == "HIGH_RISK_HOST_FACTORS":
                score -= 6.0
            elif risk == "NONSPECIFIC_DISPOSITION_LABEL":
                score -= 4.0
            elif risk == "JRE_STATE_ESCALATE":
                score -= 10.0
            elif risk == "JRE_STATE_NEED_OBJECTIVE_DATA":
                score -= 7.0
            elif risk.startswith("GRAPH_ACTION_PRESSURE"):
                score -= 8.0
            elif risk.startswith("GRAPH_RANGE_RISK_LOAD"):
                score -= 6.0
            elif risk.startswith("GRAPH_OBJECTIVE_COVERAGE_GAP"):
                score -= 8.0
            elif risk.startswith("GRAPH_MISSING_LOAD"):
                score -= 5.0
            elif risk.startswith("GRAPH_STRATEGIC_SIGNAL_LOAD"):
                score -= 5.0
            elif risk.startswith("GRAPH_BOUNDARY_SENSITIVITY"):
                score -= 7.0
            elif risk.startswith("GRAPH_BREACHED_NODE"):
                score -= 3.0
            elif risk.startswith("GRAPH_FRAGILE_NODE"):
                score -= 2.0

        return round(max(0.0, min(100.0, score)), 1)

    def _decide_state(
        self,
        snapshot: DispositionSnapshot,
        dsi: float,
        risk_factors: Sequence[str],
        guardrail_report: GuardrailReport,
    ) -> DispositionState:
        if "GUARDRAIL_ESCALATE" in risk_factors or any(
            r in risk_factors
            for r in {
                "FLOOR_DISPOSITION_WITH_OBJECTIVE_INSTABILITY",
                "TREATMENT_INTENSITY_EXCEEDS_PROBLEM_REPRESENTATION",
            }
        ):
            return "ACUITY_MISMATCH_RISK"
        if "NONSPECIFIC_DISPOSITION_WITH_HIGH_RISK_CONTEXT" in risk_factors:
            return "DIAGNOSTIC_PIVOT_RISK"
        if dsi < 75:
            return "UNDER_SPECIFIED"
        return "SUFFICIENT"

    def _input_limitations(self, snapshot: DispositionSnapshot) -> List[str]:
        if snapshot.input_mode == "notes":
            return [
                "Evaluates the documented ED disposition representation, not the original clinician-patient dialogue.",
                "Does not treat pending inpatient workup as failure; only resulted ED data and documented disposition context are scored.",
            ]
        if snapshot.input_mode == "dialogue":
            return [
                "Evaluates current elicitation quality before note synthesis.",
                "Objective ED results must be supplied separately or they remain absent from scoring.",
            ]
        return [
            "Evaluates both current dialogue and documented ED disposition material.",
            "Disagreements between dialogue and note inputs are treated as source conflicts rather than silently reconciled.",
        ]


def load_benchmark_cases(path: str | Path) -> List[BenchmarkCase]:
    """Load DHSE benchmark cases from newline-delimited JSON."""

    rows: List[BenchmarkCase] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                rows.append(benchmark_case_from_dict(json.loads(stripped)))
            except Exception as exc:
                raise ValueError(f"Invalid DHSE benchmark row {line_number} in {path}: {exc}") from exc
    return rows


def load_flat_ehr_csv(path: str | Path) -> List[BenchmarkCase]:
    """Load a canonical flat EHR export CSV into DHSE benchmark cases.

    This adapter is intentionally site-neutral. Complex fields use either JSON
    columns (`ed_results_json`, `vital_trend_json`, `dialogue_json`) or
    pipe-separated strings (`key_pmh`, `treatments`,
    `major_therapeutic_pivots`). Sites can map their native extract into these
    columns without changing the scoring engine.
    """

    rows: List[BenchmarkCase] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            try:
                rows.append(benchmark_case_from_flat_row(row))
            except Exception as exc:
                raise ValueError(f"Invalid DHSE CSV row {row_number} in {path}: {exc}") from exc
    return rows


def benchmark_case_from_flat_row(row: Dict[str, str]) -> BenchmarkCase:
    metadata = _json_dict(row.get("metadata_json", ""))
    if row.get("ed_los_hours") not in {None, ""}:
        metadata["ed_los_hours"] = _coerce_number(row.get("ed_los_hours"))

    snapshot = DispositionSnapshot(
        case_id=_required(row, "case_id"),
        input_mode=row.get("input_mode") or "notes",
        age=int(float(_required(row, "age"))),
        chief_concern=_required(row, "chief_concern"),
        domain=_required(row, "domain"),
        disposition_diagnosis=_required(row, "disposition_diagnosis"),
        admission_service=row.get("admission_service", ""),
        level_of_care=row.get("level_of_care", "floor"),
        ed_note=row.get("ed_note", ""),
        key_pmh=_split_pipe(row.get("key_pmh", "")),
        ed_results=_json_dict(row.get("ed_results_json", "")),
        vital_trend=_json_dict(row.get("vital_trend_json", "")),
        treatments=_split_pipe(row.get("treatments", "")),
        dialogue=[_statement_from_dict(item) for item in _json_list(row.get("dialogue_json", ""))],
        metadata=metadata,
    )
    trajectory = PostDischargeTrajectory(
        ed_diagnosis_category=row.get("ed_diagnosis_category", ""),
        discharge_diagnosis_category=row.get("discharge_diagnosis_category", ""),
        discharge_principal_diagnosis=row.get("discharge_principal_diagnosis", ""),
        los_hours=_coerce_number(row.get("los_hours")),
        expected_los_hours=_coerce_number(row.get("expected_los_hours")),
        icu_transfer_within_24h=_coerce_bool(row.get("icu_transfer_within_24h")),
        stepdown_transfer_within_24h=_coerce_bool(row.get("stepdown_transfer_within_24h")),
        rapid_response_within_24h=_coerce_bool(row.get("rapid_response_within_24h")),
        mortality=_coerce_bool(row.get("mortality")),
        major_procedure=_coerce_bool(row.get("major_procedure")),
        service_change_due_to_diagnosis=_coerce_bool(row.get("service_change_due_to_diagnosis")),
        major_therapeutic_pivots=_split_pipe(row.get("major_therapeutic_pivots", "")),
        delayed_definitive_therapy_hours=_coerce_number(row.get("delayed_definitive_therapy_hours")),
        discharge_to_higher_level_of_care=_coerce_bool(row.get("discharge_to_higher_level_of_care")),
        readmission_30d=_coerce_bool(row.get("readmission_30d")),
        metadata=_json_dict(row.get("trajectory_metadata_json", "")),
    )
    return BenchmarkCase(
        snapshot=snapshot,
        trajectory=trajectory,
        expected_ptr_b=_coerce_optional_bool(row.get("expected_ptr_b")),
        expected_state=row.get("expected_state") or None,
        defect_family=row.get("defect_family", ""),
        notes=row.get("notes", ""),
    )


def benchmark_case_from_dict(payload: Dict[str, Any]) -> BenchmarkCase:
    return BenchmarkCase(
        snapshot=snapshot_from_dict(payload["snapshot"]),
        trajectory=trajectory_from_dict(payload["trajectory"]),
        expected_ptr_b=payload.get("expected_ptr_b"),
        expected_state=payload.get("expected_state"),
        defect_family=payload.get("defect_family", ""),
        notes=payload.get("notes", ""),
    )


def snapshot_from_dict(payload: Dict[str, Any]) -> DispositionSnapshot:
    return DispositionSnapshot(
        case_id=payload["case_id"],
        input_mode=payload.get("input_mode", "notes"),
        age=int(payload["age"]),
        chief_concern=payload["chief_concern"],
        domain=payload["domain"],
        disposition_diagnosis=payload["disposition_diagnosis"],
        admission_service=payload.get("admission_service", ""),
        level_of_care=payload.get("level_of_care", "floor"),
        ed_note=payload.get("ed_note", ""),
        key_pmh=list(payload.get("key_pmh", [])),
        ed_results=dict(payload.get("ed_results", {})),
        vital_trend=dict(payload.get("vital_trend", {})),
        treatments=list(payload.get("treatments", [])),
        dialogue=[_statement_from_dict(item) for item in payload.get("dialogue", [])],
        metadata=dict(payload.get("metadata", {})),
    )


def trajectory_from_dict(payload: Dict[str, Any]) -> PostDischargeTrajectory:
    return PostDischargeTrajectory(
        ed_diagnosis_category=payload.get("ed_diagnosis_category", ""),
        discharge_diagnosis_category=payload.get("discharge_diagnosis_category", ""),
        discharge_principal_diagnosis=payload.get("discharge_principal_diagnosis", ""),
        los_hours=payload.get("los_hours"),
        expected_los_hours=payload.get("expected_los_hours"),
        icu_transfer_within_24h=bool(payload.get("icu_transfer_within_24h", False)),
        stepdown_transfer_within_24h=bool(payload.get("stepdown_transfer_within_24h", False)),
        rapid_response_within_24h=bool(payload.get("rapid_response_within_24h", False)),
        mortality=bool(payload.get("mortality", False)),
        major_procedure=bool(payload.get("major_procedure", False)),
        service_change_due_to_diagnosis=bool(payload.get("service_change_due_to_diagnosis", False)),
        major_therapeutic_pivots=list(payload.get("major_therapeutic_pivots", [])),
        delayed_definitive_therapy_hours=payload.get("delayed_definitive_therapy_hours"),
        discharge_to_higher_level_of_care=bool(payload.get("discharge_to_higher_level_of_care", False)),
        readmission_30d=bool(payload.get("readmission_30d", False)),
        metadata=dict(payload.get("metadata", {})),
    )


def _statement_from_dict(payload: Dict[str, Any]) -> Statement:
    return Statement(
        question=payload.get("question", ""),
        answer=payload.get("answer", ""),
        concept=payload.get("concept"),
        source=payload.get("source", "patient"),
        metadata=dict(payload.get("metadata", {})),
    )


def make_paper_analysis(
    cases: Sequence[BenchmarkCase],
    reports: Sequence[DispositionSufficiencyReport],
    review_fraction: float = 0.10,
) -> Dict[str, Any]:
    labels = [bool(report.trajectory_label and report.trajectory_label.ptr_b_positive) for report in reports]
    risk_scores = [100.0 - report.dsi for report in reports]
    return {
        "cohort_flow": _cohort_flow(cases, reports),
        "label_prevalence": _label_prevalence(reports),
        "calibration": _calibration_bins(risk_scores, labels, bins=5),
        "threshold_table": _threshold_table(reports, thresholds=(50, 65, 75, 85)),
        "source_mode_stratification": _stratified_metrics(reports, key_fn=lambda report: report.input_mode, review_fraction=review_fraction),
        "state_stratification": _stratified_metrics(reports, key_fn=lambda report: report.state, review_fraction=review_fraction),
        "defect_family_stratification": _defect_family_metrics(cases, reports, review_fraction=review_fraction),
        "error_analysis": _error_analysis(reports, threshold=75),
    }


def _note_mode_summary() -> Dict[str, str]:
    return {
        "notes": "ED note, key PMH, resulted ED data, ED treatments, disposition diagnosis, service, and level of care.",
        "dialogue": "Current patient/clinician dialogue plus any structured objective data available at the decision point.",
        "hybrid": "Both dialogue and notes, preserving source labels so contradictions remain visible.",
    }


def _cohort_flow(cases: Sequence[BenchmarkCase], reports: Sequence[DispositionSufficiencyReport]) -> Dict[str, Any]:
    by_mode: Dict[str, int] = {}
    for report in reports:
        by_mode[report.input_mode] = by_mode.get(report.input_mode, 0) + 1
    return {
        "records_loaded": len(cases),
        "records_scored": len(reports),
        "records_with_ptr_b_label": sum(1 for r in reports if r.trajectory_label is not None),
        "by_input_mode": by_mode,
    }


def _label_prevalence(reports: Sequence[DispositionSufficiencyReport]) -> Dict[str, Any]:
    revision_counts: Dict[str, int] = {}
    burden_counts: Dict[str, int] = {}
    positives = 0
    for report in reports:
        label = report.trajectory_label
        if not label:
            continue
        positives += int(label.ptr_b_positive)
        for event in label.revision_events:
            revision_counts[event] = revision_counts.get(event, 0) + 1
        for event in label.burden_events:
            burden_counts[event] = burden_counts.get(event, 0) + 1
    n = sum(1 for r in reports if r.trajectory_label is not None)
    return {
        "n_labeled": n,
        "ptr_b_positive": positives,
        "ptr_b_negative": n - positives,
        "ptr_b_rate": round(positives / n, 4) if n else None,
        "revision_event_counts": dict(sorted(revision_counts.items())),
        "burden_event_counts": dict(sorted(burden_counts.items())),
    }


def _calibration_bins(scores: Sequence[float], labels: Sequence[bool], bins: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if bins <= 0:
        return out
    width = 100.0 / bins
    for idx in range(bins):
        lo = idx * width
        hi = 100.0 if idx == bins - 1 else (idx + 1) * width
        members = [
            (score, label)
            for score, label in zip(scores, labels)
            if (score >= lo and (score <= hi if idx == bins - 1 else score < hi))
        ]
        positives = sum(1 for _, label in members if label)
        out.append(
            {
                "risk_score_min": round(lo, 1),
                "risk_score_max": round(hi, 1),
                "n": len(members),
                "mean_predicted_risk": round(sum(score for score, _ in members) / (100.0 * len(members)), 4) if members else None,
                "observed_ptr_b_rate": round(positives / len(members), 4) if members else None,
            }
        )
    return out


def _threshold_table(reports: Sequence[DispositionSufficiencyReport], thresholds: Sequence[float]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    labels = [bool(r.trajectory_label and r.trajectory_label.ptr_b_positive) for r in reports]
    for threshold in thresholds:
        predicted = [r.dsi < threshold for r in reports]
        tp = sum(1 for p, y in zip(predicted, labels) if p and y)
        fp = sum(1 for p, y in zip(predicted, labels) if p and not y)
        tn = sum(1 for p, y in zip(predicted, labels) if not p and not y)
        fn = sum(1 for p, y in zip(predicted, labels) if not p and y)
        out.append(
            {
                "dsi_threshold": threshold,
                "tp": tp,
                "fp": fp,
                "tn": tn,
                "fn": fn,
                "sensitivity": round(tp / (tp + fn), 4) if (tp + fn) else None,
                "specificity": round(tn / (tn + fp), 4) if (tn + fp) else None,
                "ppv": round(tp / (tp + fp), 4) if (tp + fp) else None,
                "npv": round(tn / (tn + fn), 4) if (tn + fn) else None,
            }
        )
    return out


def _stratified_metrics(
    reports: Sequence[DispositionSufficiencyReport],
    key_fn: Any,
    review_fraction: float,
) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[DispositionSufficiencyReport]] = {}
    for report in reports:
        groups.setdefault(str(key_fn(report)), []).append(report)
    out: Dict[str, Dict[str, Any]] = {}
    for key, group in sorted(groups.items()):
        labels = [bool(r.trajectory_label and r.trajectory_label.ptr_b_positive) for r in group]
        scores = [100.0 - r.dsi for r in group]
        out[key] = _binary_metric_summary(scores, labels, review_fraction)
    return out


def _defect_family_metrics(
    cases: Sequence[BenchmarkCase],
    reports: Sequence[DispositionSufficiencyReport],
    review_fraction: float,
) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[DispositionSufficiencyReport]] = {}
    for case, report in zip(cases, reports):
        groups.setdefault(case.defect_family or "unspecified", []).append(report)
    out: Dict[str, Dict[str, Any]] = {}
    for key, group in sorted(groups.items()):
        labels = [bool(r.trajectory_label and r.trajectory_label.ptr_b_positive) for r in group]
        scores = [100.0 - r.dsi for r in group]
        out[key] = _binary_metric_summary(scores, labels, review_fraction)
    return out


def _error_analysis(reports: Sequence[DispositionSufficiencyReport], threshold: float) -> Dict[str, List[Dict[str, Any]]]:
    false_positives: List[Dict[str, Any]] = []
    false_negatives: List[Dict[str, Any]] = []
    for report in reports:
        if not report.trajectory_label:
            continue
        predicted_positive = report.dsi < threshold
        actual_positive = report.trajectory_label.ptr_b_positive
        row = _error_row(report)
        if predicted_positive and not actual_positive:
            false_positives.append(row)
        elif not predicted_positive and actual_positive:
            false_negatives.append(row)
    return {
        "threshold": threshold,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
    }


def _error_row(report: DispositionSufficiencyReport) -> Dict[str, Any]:
    label = report.trajectory_label
    return {
        "case_id": report.case_id,
        "input_mode": report.input_mode,
        "dsi": report.dsi,
        "state": report.state,
        "ptr_b": label.ptr_b_positive if label else None,
        "revision_events": label.revision_events if label else [],
        "burden_events": label.burden_events if label else [],
        "risk_factors": report.risk_factors,
    }


def _concept_for_key(key: str) -> Optional[str]:
    k = key.lower()
    if any(x in k for x in ["spo2", "oxygen", "o2 sat"]):
        return "oxygen_saturation"
    if "resp" in k or k == "rr":
        return "respiratory_rate"
    if k in {"hr", "heart_rate", "pulse"} or "heart rate" in k or "pulse" in k:
        return "heart_rate"
    if k in {"sbp", "systolic", "systolic_bp"} or "systolic" in k:
        return "systolic_bp"
    if "glucose" in k or "sugar" in k:
        return "glucose_number"
    if "temp" in k or "fever" in k:
        return "fever_measured"
    if "lactate" in k:
        return "lactate"
    if k == "wbc" or "white_blood" in k or "white blood" in k:
        return "wbc"
    if "troponin" in k:
        return "troponin"
    if "bp" in k or "blood_pressure" in k or "systolic" in k:
        return "vitals"
    if "heart" in k or k == "hr" or "pulse" in k:
        return "vitals"
    return None


def _latest(values: Any) -> Any:
    if isinstance(values, (list, tuple)) and values:
        return values[-1]
    return values


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)) and value:
        return _to_float(value[-1])
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
    seen = set()
    for item in items:
        if item in seen:
            continue
        out.append(item)
        seen.add(item)
    return out


def _auroc(scores: Sequence[float], labels: Sequence[bool]) -> Optional[float]:
    positives = [(s, i) for i, (s, y) in enumerate(zip(scores, labels)) if y]
    negatives = [(s, i) for i, (s, y) in enumerate(zip(scores, labels)) if not y]
    if not positives or not negatives:
        return None
    wins = 0.0
    total = len(positives) * len(negatives)
    for ps, _ in positives:
        for ns, _ in negatives:
            if ps > ns:
                wins += 1.0
            elif ps == ns:
                wins += 0.5
    return round(wins / total, 4)


def _capture_at_fraction(scores: Sequence[float], labels: Sequence[bool], fraction: float) -> Optional[float]:
    positives = sum(1 for y in labels if y)
    if positives == 0 or not scores:
        return None
    k = max(1, int(round(len(scores) * fraction)))
    ordered = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    captured = sum(1 for _, y in ordered[:k] if y)
    return round(captured / positives, 4)


def _binary_metric_summary(scores: Sequence[float], labels: Sequence[bool], review_fraction: float) -> Dict[str, Any]:
    labels = list(labels)
    scores = list(scores)
    positives = sum(1 for x in labels if x)
    negatives = len(labels) - positives
    return {
        "n": len(labels),
        "positives": positives,
        "negatives": negatives,
        "ptr_b_rate": round(positives / len(labels), 4) if labels else None,
        "auroc": _auroc(scores, labels),
        "auprc": _auprc(scores, labels),
        "top_decile_enrichment": _top_fraction_enrichment(scores, labels, 0.10),
        "review_fraction": review_fraction,
        "capture_at_review_fraction": _capture_at_fraction(scores, labels, review_fraction),
    }


def _auprc(scores: Sequence[float], labels: Sequence[bool]) -> Optional[float]:
    positives = sum(1 for x in labels if x)
    if positives == 0 or not scores:
        return None
    ordered = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    hit_count = 0
    precision_sum = 0.0
    for rank, (_, label) in enumerate(ordered, start=1):
        if not label:
            continue
        hit_count += 1
        precision_sum += hit_count / rank
    return round(precision_sum / positives, 4)


def _top_fraction_enrichment(scores: Sequence[float], labels: Sequence[bool], fraction: float) -> Optional[float]:
    if not scores or not labels:
        return None
    base_rate = sum(1 for x in labels if x) / len(labels)
    if base_rate == 0:
        return None
    k = max(1, int(round(len(scores) * fraction)))
    ordered = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    top_rate = sum(1 for _, label in ordered[:k] if label) / k
    return round(top_rate / base_rate, 4)


def _structured_severity_risk(snapshot: DispositionSnapshot) -> float:
    risk = 0.0
    if snapshot.age >= 75:
        risk += 15.0
    elif snapshot.age >= 65:
        risk += 8.0
    if any(HIGH_RISK_PMH.search(item) for item in snapshot.key_pmh):
        risk += 15.0
    objective_risk_count = len(DispositionHandoffSufficiencyEngine()._objective_instability(snapshot))
    risk += min(50.0, objective_risk_count * 10.0)
    if snapshot.level_of_care.lower() in {"floor", "med/surg", "med surg", "observation"} and objective_risk_count:
        risk += 10.0
    return round(min(100.0, risk), 1)


def _guardrail_risk_score(state: str) -> float:
    return {
        "ESCALATE": 100.0,
        "FAIL_CLOSED": 90.0,
        "ROUTE_CLINICIAN": 75.0,
        "HOLD_AND_VERIFY": 55.0,
        "ALLOW_WITH_AUDIT": 0.0,
    }.get(state, 40.0)


def _required(row: Dict[str, str], key: str) -> str:
    value = row.get(key)
    if value is None or value == "":
        raise ValueError(f"missing required column {key}")
    return value


def _split_pipe(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def _json_dict(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object")
    return parsed


def _json_list(value: Optional[str]) -> List[Dict[str, Any]]:
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("expected JSON list")
    return parsed


def _coerce_number(value: Any) -> Optional[float]:
    if value in {None, ""}:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in {None, ""}:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}


def _coerce_optional_bool(value: Any) -> Optional[bool]:
    if value in {None, ""}:
        return None
    return _coerce_bool(value)


def _guardrail_is_assumption_breach(report: GuardrailReport) -> bool:
    """Return true when BSG detected an operating-envelope breach.

    DHSE uses admitted-patient snapshots. A wrapped JRE escalation can simply
    mean "this patient appropriately needed admission," which should not by
    itself count as disposition handoff insufficiency. Direct Black Swan
    findings such as wrong-patient, source-integrity, social safety, or
    off-pathway sentinel findings still count as assumption breaches.
    """

    return any(_is_dhse_actionable_guardrail_finding(f) for f in report.findings)


def _is_dhse_actionable_guardrail_finding(finding: Any) -> bool:
    if str(finding.rule_id).startswith("WRAP_"):
        return False
    evidence = str(getattr(finding, "evidence", "")).lower()
    if finding.rule_id == "SENTINEL_PREGNANCY_ABDOMINAL_PAIN" and re.search(
        r"\b(not pregnant|pregnancy test(?: was)? negative|negative pregnancy)\b",
        evidence,
    ):
        return False
    return True


INPUT_MODE_SUMMARY = _note_mode_summary()
