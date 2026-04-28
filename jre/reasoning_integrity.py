"""Reasoning integrity checks for clinical decision support.

This module is a deterministic cognitive-bias guard for the demo. It does not
diagnose clinician bias. It audits the reasoning pathway for known failure modes
that can cause premature closure, anchoring, omission, or overconfidence before
the system allows reassurance or autonomous action.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Sequence

from .black_swan import GuardrailReport
from .models import CaseInput, Finding, ReadinessReport


@dataclass
class ReasoningBiasFinding:
    bias_id: str
    label: str
    severity: float
    evidence: str
    reasoning_failure: str
    cognitive_forcing_action: str
    disconfirming_question: str
    affected_autonomy: str
    authority: str = "Cognitive Forcing"


@dataclass
class ReasoningIntegrityReport:
    case_id: str
    state: str
    findings: List[ReasoningBiasFinding]
    provider_summary: str
    patient_safe_summary: str

    def to_dict(self) -> Dict:
        return asdict(self)


class ReasoningIntegrityEngine:
    """Detect cognitive-bias failure modes in the case reasoning path."""

    def evaluate(
        self,
        case: CaseInput,
        jre_report: ReadinessReport,
        bsg_report: GuardrailReport,
    ) -> ReasoningIntegrityReport:
        findings: List[ReasoningBiasFinding] = []
        text = self._case_text(case)
        jre_categories = {f.category for f in jre_report.findings}
        bsg_categories = {f.category for f in bsg_report.findings}
        rule_ids = {f.rule_id for f in jre_report.findings} | {f.rule_id for f in bsg_report.findings}
        severe_safety_gap = bool(
            {"red_flag", "contradictory", "objective_needed", "unknowable_remote"}.intersection(jre_categories)
            or bsg_report.guardrail_state in {"ESCALATE", "FAIL_CLOSED", "ROUTE_CLINICIAN"}
        )

        findings.extend(self._anchoring_findings(case, jre_report, text))
        findings.extend(self._diagnostic_momentum_findings(text))
        findings.extend(self._framing_findings(text))

        if severe_safety_gap and self._has_plausible_benign_anchor(case, text):
            findings.append(
                ReasoningBiasFinding(
                    bias_id="premature_closure",
                    label="Premature Closure Risk",
                    severity=0.88,
                    evidence=self._evidence_excerpt(text, ["just", "probably", "indigestion", "anxiety", "strain", "viral", "sleep med"]),
                    reasoning_failure="A plausible explanation is present before critical contradictions, red flags, or remote boundaries have been resolved.",
                    cognitive_forcing_action="Pause closure and ask what dangerous alternative has not been falsified.",
                    disconfirming_question=self._best_forcing_question(jre_report, "What critical fact would make the current reassuring explanation unsafe?"),
                    affected_autonomy="Hold or route until the dangerous alternative is actively falsified.",
                )
            )

        if severe_safety_gap and (jre_report.scores.completeness < 0.72 or jre_report.scores.objective_coverage < 0.35):
            findings.append(
                ReasoningBiasFinding(
                    bias_id="overconfidence",
                    label="Overconfidence / Low Evidence Boundary",
                    severity=0.78,
                    evidence=(
                        f"JRI={jre_report.scores.readiness_index:.1f}; "
                        f"completeness={jre_report.scores.completeness:.2f}; "
                        f"objective={jre_report.scores.objective_coverage:.2f}"
                    ),
                    reasoning_failure="The case can produce a coherent summary despite weak completeness or objective evidence.",
                    cognitive_forcing_action="Separate narrative coherence from evidence sufficiency.",
                    disconfirming_question=self._best_forcing_question(jre_report, "Which missing objective fact would change the autonomy boundary?"),
                    affected_autonomy="Cap autonomous action until evidence sufficiency improves or clinician review accepts the residual uncertainty.",
                )
            )

        if "missing" in jre_categories and severe_safety_gap:
            findings.append(
                ReasoningBiasFinding(
                    bias_id="search_satisficing",
                    label="Search Satisficing Risk",
                    severity=0.76,
                    evidence=self._top_finding_evidence(jre_report.findings),
                    reasoning_failure="One explanation may account for part of the story while required safety variables remain unsearched.",
                    cognitive_forcing_action="Generate one competing dangerous explanation and one comorbidity/second-problem check.",
                    disconfirming_question=self._best_forcing_question(jre_report, "What else could be present at the same time?"),
                    affected_autonomy="Do not close the search while required safety slots remain missing.",
                )
            )

        if self._confirmation_pattern(text, jre_categories, rule_ids):
            findings.append(
                ReasoningBiasFinding(
                    bias_id="confirmation_bias",
                    label="Confirmation Bias Risk",
                    severity=0.74,
                    evidence=self._evidence_excerpt(text, ["no", "not", "just", "fine", "normal", "probably"]),
                    reasoning_failure="The pathway may be giving too much weight to answers that confirm reassurance while contradiction or missingness remains.",
                    cognitive_forcing_action="Actively seek disconfirming evidence before summarizing the case as low risk.",
                    disconfirming_question=self._best_forcing_question(jre_report, "What finding would prove this is not safe for routine handling?"),
                    affected_autonomy="Require disconfirming-evidence check before upgrading autonomy.",
                )
            )

        if "care_avoidance_pressure" in bsg_categories or "workflow_integrity" in bsg_categories:
            findings.append(
                ReasoningBiasFinding(
                    bias_id="omission_bias",
                    label="Omission Bias / Remote Inaction Risk",
                    severity=0.73,
                    evidence=self._top_guardrail_evidence(bsg_report),
                    reasoning_failure="Remote uncertainty or patient pressure could make inaction feel safer than routing, even when delay is the risky choice.",
                    cognitive_forcing_action="Compare harm of action against harm of delayed action, not against a false no-action baseline.",
                    disconfirming_question="If this patient delays, what time-sensitive harm are we trying to prevent?",
                    affected_autonomy="Do not downgrade routing because escalation is inconvenient, expensive, or unwanted.",
                )
            )

        if self._availability_pattern(case, text, jre_report):
            findings.append(
                ReasoningBiasFinding(
                    bias_id="availability_bias",
                    label="Availability / Prototype-Match Risk",
                    severity=0.70,
                    evidence=self._evidence_excerpt(text, ["cough", "viral", "covid", "uti", "migraine", "rash", "anxiety"]),
                    reasoning_failure="A common visible pattern may dominate over atypical or high-risk features.",
                    cognitive_forcing_action="Ask which feature does not fit the common prototype.",
                    disconfirming_question=self._best_forcing_question(jre_report, "Which atypical feature should stop a routine diagnosis?"),
                    affected_autonomy="Keep the case in verify/route mode until atypical features are explained.",
                )
            )

        findings = self._dedupe(findings)
        state = self._state_for(findings, severe_safety_gap)
        provider_summary = self._provider_summary(state, findings)
        patient_safe_summary = (
            "The system is checking whether the explanation fits all the facts before deciding what can safely happen next."
            if findings
            else "No major reasoning-integrity concern was detected."
        )
        return ReasoningIntegrityReport(
            case_id=case.case_id,
            state=state,
            findings=sorted(findings, key=lambda f: -f.severity),
            provider_summary=provider_summary,
            patient_safe_summary=patient_safe_summary,
        )

    def _anchoring_findings(
        self,
        case: CaseInput,
        jre_report: ReadinessReport,
        text: str,
    ) -> List[ReasoningBiasFinding]:
        findings: List[ReasoningBiasFinding] = []
        first_blob = " ".join(
            part for stmt in case.statements[:2] for part in [stmt.question, stmt.answer, stmt.concept or ""]
        ).lower()
        anchor_terms = [
            "back pain",
            "lifting",
            "indigestion",
            "reflux",
            "heartburn",
            "anxiety",
            "stress",
            "sleep",
            "viral",
            "cough",
            "uti",
            "rash",
            "migraine",
        ]
        later_red_flags = [
            f for f in jre_report.findings
            if f.category in {"red_flag", "contradictory", "unknowable_remote", "objective_needed"}
        ]
        if later_red_flags and any(term in first_blob for term in anchor_terms):
            top = sorted(later_red_flags, key=lambda f: -f.severity)[0]
            findings.append(
                ReasoningBiasFinding(
                    bias_id="anchoring",
                    label="Anchoring Risk",
                    severity=min(0.92, max(0.72, top.severity)),
                    evidence=f"Early frame: {first_blob[:140]}; later blocker: {top.reason}",
                    reasoning_failure="The early chief-complaint frame may be overweighted relative to later boundary-changing evidence.",
                    cognitive_forcing_action="Name the anchor, then ask what new fact should move the case away from it.",
                    disconfirming_question=top.next_question or self._best_forcing_question(jre_report, "What fact contradicts the initial frame?"),
                    affected_autonomy="Do not let the first plausible frame authorize routine closure.",
                )
            )
        return findings

    def _diagnostic_momentum_findings(self, text: str) -> List[ReasoningBiasFinding]:
        patterns = [
            r"\b(previously diagnosed|already diagnosed|doctor said|they said|was told|urgent care said|er said)\b",
            r"\b(anxiety|panic|gerd|reflux|muscle strain|migraine|viral|covid|uti)\b.{0,60}\b(again|same as|just|probably)\b",
        ]
        if not any(re.search(pattern, text) for pattern in patterns):
            return []
        return [
            ReasoningBiasFinding(
                bias_id="diagnostic_momentum",
                label="Diagnostic Momentum Risk",
                severity=0.72,
                evidence=self._evidence_excerpt(text, ["doctor said", "was told", "already diagnosed", "same as", "again"]),
                reasoning_failure="A prior label or common diagnosis may be carried forward as if it has been proven for this encounter.",
                cognitive_forcing_action="Treat prior labels as hypotheses, not settled facts.",
                disconfirming_question="What current feature would make the prior label incomplete or unsafe today?",
                affected_autonomy="Require current-encounter evidence before closure or reassurance.",
            )
        ]

    def _framing_findings(self, text: str) -> List[ReasoningBiasFinding]:
        if not re.search(r"\b(frequent flyer|drug seeking|noncompliant|non-compliant|anxious patient|hysterical|dramatic|obese|young and healthy|old and frail)\b", text):
            return []
        return [
            ReasoningBiasFinding(
                bias_id="framing_ascertainment",
                label="Framing / Ascertainment Risk",
                severity=0.70,
                evidence=self._evidence_excerpt(text, ["frequent flyer", "drug seeking", "noncompliant", "anxious", "dramatic"]),
                reasoning_failure="Patient identity, prior behavior, or stereotype language may distort how evidence is collected or weighted.",
                cognitive_forcing_action="Strip identity labels from the clinical facts and re-run the boundary questions.",
                disconfirming_question="If this same symptom came from a different patient, what would we ask next?",
                affected_autonomy="Do not lower concern based on identity or utilization labels.",
            )
        ]

    def _confirmation_pattern(self, text: str, categories: set, rule_ids: set) -> bool:
        has_reassurance_language = bool(re.search(r"\b(no|not|fine|normal|okay|ok|just|probably|not really)\b", text))
        has_conflict = bool({"contradictory", "distorted", "uncertain"}.intersection(categories))
        has_boundary_rule = any("CONTRA" in r or "LOW_CONFIDENCE" in r for r in rule_ids)
        return has_reassurance_language and (has_conflict or has_boundary_rule)

    def _availability_pattern(self, case: CaseInput, text: str, jre_report: ReadinessReport) -> bool:
        common_frames = {
            "dyspnea_respiratory": ["cough", "cold", "viral", "covid", "flu"],
            "uti_symptoms": ["uti", "burning", "pee"],
            "headache_migraine": ["migraine", "headache"],
            "rash": ["rash", "bug bite", "hives"],
        }
        if not any(term in text for term in common_frames.get(case.patient_context.domain, [])):
            return False
        return any(f.category in {"red_flag", "objective_needed", "unknowable_remote"} for f in jre_report.findings)

    def _has_plausible_benign_anchor(self, case: CaseInput, text: str) -> bool:
        benign_terms = [
            "just",
            "probably",
            "indigestion",
            "heartburn",
            "reflux",
            "anxiety",
            "stress",
            "strain",
            "pulled",
            "viral",
            "cold",
            "sleep med",
            "sleep medicine",
        ]
        return any(term in text for term in benign_terms) or any(
            term in case.patient_context.chief_concern.lower()
            for term in ["indigestion", "fatigue", "back pain", "cough", "sleep"]
        )

    def _state_for(self, findings: Sequence[ReasoningBiasFinding], severe_safety_gap: bool) -> str:
        if not findings:
            return "ALLOW_WITH_AUDIT"
        max_severity = max(f.severity for f in findings)
        if severe_safety_gap and max_severity >= 0.86:
            return "ROUTE_CLINICIAN"
        if max_severity >= 0.70:
            return "HOLD_AND_VERIFY"
        return "ALLOW_WITH_AUDIT"

    def _case_text(self, case: CaseInput) -> str:
        parts = [
            case.patient_context.chief_concern,
            case.patient_context.domain,
            " ".join(case.patient_context.known_conditions),
        ]
        for stmt in case.statements:
            parts.extend([stmt.question, stmt.answer, stmt.concept or ""])
        return " ".join(parts).lower()

    def _best_forcing_question(self, jre_report: ReadinessReport, fallback: str) -> str:
        return jre_report.next_questions[0].question if jre_report.next_questions else fallback

    def _top_finding_evidence(self, findings: Sequence[Finding]) -> str:
        top = sorted(findings, key=lambda f: -f.severity)[:2]
        return "; ".join(f.reason for f in top) or "Required safety variables remain unresolved."

    def _top_guardrail_evidence(self, bsg_report: GuardrailReport) -> str:
        top = sorted(bsg_report.findings, key=lambda f: -f.severity)[:1]
        return top[0].reason if top else "Remote pathway pressure or uncertainty is present."

    def _evidence_excerpt(self, text: str, needles: Sequence[str]) -> str:
        for needle in needles:
            idx = text.find(needle)
            if idx >= 0:
                start = max(0, idx - 70)
                end = min(len(text), idx + 180)
                return text[start:end].strip()
        return text[:220].strip()

    def _dedupe(self, findings: Sequence[ReasoningBiasFinding]) -> List[ReasoningBiasFinding]:
        out: List[ReasoningBiasFinding] = []
        seen = set()
        for f in findings:
            if f.bias_id in seen:
                continue
            seen.add(f.bias_id)
            out.append(f)
        return out

    def _provider_summary(self, state: str, findings: Sequence[ReasoningBiasFinding]) -> str:
        if not findings:
            return "No major reasoning-integrity concern detected."
        top = sorted(findings, key=lambda f: -f.severity)[:3]
        return f"{state}: " + "; ".join(f"{f.label} - {f.cognitive_forcing_action}" for f in top)
