"""Interactive Clinical Safety Demo — Progressive Clinical Safety Walkthrough.

A guided, step-by-step interactive demo for presenting JRE + BSG to executives.
Serves a single-page browser app via FastAPI with 5 screens:
  1. Overview — interview-focused opening and hero cases
  2. Case Selection — grid of case cards
  3. Encounter — editable dialogue view
  4. Progressive Analysis — 13 sections revealed one at a time
  5. Governance — feedback, experience viewer, rule/case suggestion

Run:
    python interactive_demo.py
    # Opens at http://localhost:8001
"""
from __future__ import annotations

import html as html_mod
import json
import re
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    from pydantic import BaseModel, Field, field_validator
except ImportError:
    raise ImportError(
        "FastAPI is required. Install with: pip install fastapi uvicorn"
    )

from jre import (
    JudgmentReadinessEngine,
    BlackSwanGuardrailEngine,
    BLACK_SWAN_CASES,
    ExperienceMemory,
)
from jre.models import (
    CaseInput,
    Finding,
    PatientContext,
    Statement,
    ReadinessReport,
    most_restrictive,
    STATE_PRIORITY,
)
from jre.black_swan import (
    GuardrailReport,
    SENTINEL_RULES,
    INTEGRITY_RULES,
    AUTONOMY_TIERS,
)
from jre.synthetic_data import BASE_CASES
from jre.templates import (
    DOMAIN_TEMPLATES,
    MODALITY_ADAPTATIONS,
    CONTRADICTION_RULES,
    ESCALATION_PROBES,
)
from jre.engine import SOURCE_SCORING_WEIGHT, GESTALT_PATTERNS
from jre.experience import OutcomeFeedback

# Import narratives and trap explanations from unified_demo
from unified_demo import CASE_NARRATIVES, TRAP_EXPLANATIONS

# Optional LLM detector
try:
    from jre.llm_augment import LLMDetector

    _llm = LLMDetector()
except ImportError:
    _llm = None

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="JRE Interactive Demo",
    description="Progressive clinical safety walkthrough for executive audiences",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Process-scoped singletons — reset on restart.
# JRE/BSG use regex-only detection for deterministic, fast analysis.
# LLM is called separately for Section 8 comparison display.
_memory = ExperienceMemory.seeded()
_jre = JudgmentReadinessEngine(memory=_memory)
_guard = BlackSwanGuardrailEngine()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class StatementInput(BaseModel):
    question: str
    answer: str
    concept: Optional[str] = None
    source: str = "patient"
    metadata: Dict[str, Any] = {}

    @field_validator("source")
    @classmethod
    def validate_source(cls, v):
        valid = {
            "patient",
            "caregiver",
            "device",
            "chart",
            "clinician",
            "synthetic_truth",
        }
        if v not in valid:
            raise ValueError(f"source must be one of {sorted(valid)}, got '{v}'")
        return v


class PatientContextInput(BaseModel):
    age: int = Field(ge=0, le=150)
    chief_concern: str
    domain: str
    literacy_hint: str = "unknown"
    language_barrier: bool = False
    has_caregiver: bool = False
    modality: str = "text"
    known_conditions: List[str] = []

    @field_validator("literacy_hint")
    @classmethod
    def validate_literacy_hint(cls, v):
        valid = {"low", "medium", "high", "unknown"}
        if v not in valid:
            raise ValueError(
                f"literacy_hint must be one of {sorted(valid)}, got '{v}'"
            )
        return v

    @field_validator("modality")
    @classmethod
    def validate_modality(cls, v):
        valid = {"text", "phone", "video", "in_person"}
        if v not in valid:
            raise ValueError(f"modality must be one of {sorted(valid)}, got '{v}'")
        return v


class AnalyzeRequest(BaseModel):
    case_id: str = "custom-case"
    patient_context: PatientContextInput
    statements: List[StatementInput]
    ground_truth: Dict[str, Any] = {}


class FeedbackInput(BaseModel):
    case_id: str
    concept: str
    domain: str
    clinician_assessment: str
    corrected_value: str = ""
    severity_adjustment: float = 0.0
    notes: str = ""


class SuggestRuleRequest(BaseModel):
    case_id: str = ""
    patient_context: Optional[PatientContextInput] = None
    statements: List[StatementInput] = []
    findings: List[Dict[str, Any]] = []


class SuggestCaseRequest(BaseModel):
    domain: str
    gap_description: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_CASES = {c.case_id: c for c in list(BASE_CASES) + list(BLACK_SWAN_CASES)}

CATEGORY_LABELS = {
    "base_escalation": "Distortion Detection",
    "base_objective": "Objective Data Gating",
    "base_incomplete": "Remote Boundary",
    "base_control": "Happy Path",
    "base_showcase": "Intelligence Showcase",
    "ceo_boundary": "Showcase — Interpretation Boundaries",
    "top_telemedicine": "Top Telemedicine Complaints",
    "bs_integrity": "Black Swan — Integrity",
    "bs_sentinel": "Black Swan — Sentinel",
    "bs_envelope": "Black Swan — Envelope",
}

CONCEPT_LABELS = {
    "symptom_quality": "Exertional chest tightness framed as indigestion",
    "exertional_component": "Exertional pattern",
    "dyspnea": "Functional limitation despite denial",
    "care_context": "Cost/work pressure to delay care",
    "vitals": "Current objective vitals",
    "ecg": "Remote ECG boundary",
    "diaphoresis": "Sweating, nausea, or faintness",
    "radiation": "Radiation to jaw, arm, back, or upper belly",
    "oxygen_saturation": "Current oxygen level",
    "blood_pressure": "Current blood pressure",
    "renal_function": "Recent kidney function labs",
    "potassium": "Recent potassium result",
}


def _display_concept(concept: str) -> str:
    return CONCEPT_LABELS.get(concept, concept.replace("_", " ").title())

CATEGORY_GROUPS = {
    "Distortion Detection": [
        "base_escalation",
        "base_objective",
        "base_incomplete",
        "base_control",
        "base_showcase",
        "ceo_boundary",
        "top_telemedicine",
    ],
    "Black Swan Safety": ["bs_integrity", "bs_sentinel", "bs_envelope"],
}


def _to_case_input(model: AnalyzeRequest) -> CaseInput:
    ctx = PatientContext(
        age=model.patient_context.age,
        chief_concern=model.patient_context.chief_concern,
        domain=model.patient_context.domain,
        literacy_hint=model.patient_context.literacy_hint,
        language_barrier=model.patient_context.language_barrier,
        has_caregiver=model.patient_context.has_caregiver,
        modality=model.patient_context.modality,
        known_conditions=model.patient_context.known_conditions,
    )
    stmts = [
        Statement(
            question=s.question,
            answer=s.answer,
            concept=s.concept,
            source=s.source,
            metadata=s.metadata,
        )
        for s in model.statements
    ]
    return CaseInput(
        case_id=model.case_id,
        patient_context=ctx,
        statements=stmts,
        ground_truth=model.ground_truth,
    )


def _case_to_analyze_dict(case: CaseInput) -> Dict[str, Any]:
    """Convert a built-in CaseInput to the dict shape matching AnalyzeRequest."""
    return {
        "case_id": case.case_id,
        "patient_context": {
            "age": case.patient_context.age,
            "chief_concern": case.patient_context.chief_concern,
            "domain": case.patient_context.domain,
            "literacy_hint": case.patient_context.literacy_hint,
            "language_barrier": case.patient_context.language_barrier,
            "has_caregiver": case.patient_context.has_caregiver,
            "modality": case.patient_context.modality,
            "known_conditions": list(case.patient_context.known_conditions),
        },
        "statements": [
            {
                "question": s.question,
                "answer": s.answer,
                "concept": s.concept,
                "source": s.source,
                "metadata": dict(s.metadata) if s.metadata else {},
            }
            for s in case.statements
        ],
        "ground_truth": dict(case.ground_truth) if case.ground_truth else {},
    }


def _validate_domain(domain: str) -> None:
    if domain not in DOMAIN_TEMPLATES:
        supported = sorted(DOMAIN_TEMPLATES.keys())
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported domain '{domain}'. Supported: {supported}",
        )


VAGUE_BOUNDARY_RE = re.compile(
    r"\b(fine|normal|okay|ok|not really|probably|maybe|last time|last visit|a while ago|not sure|no symptoms|nothing serious)\b",
    re.I,
)
STALE_BOUNDARY_RE = re.compile(
    r"\b(months? ago|last year|last visit|old reading|a while ago|not today|not sure when|from before|last time)\b",
    re.I,
)
OBJECTIVE_CONCEPTS = {
    "home_bp_number",
    "glucose_number",
    "oxygen_saturation",
    "fever_measured",
    "respiratory_rate",
    "vitals",
    "renal_function",
    "chart_med_reconciliation",
}


def _slot_question(domain: str, concept: str) -> str:
    for slot in DOMAIN_TEMPLATES.get(domain, []):
        if slot.name == concept and slot.clarify_questions:
            return slot.clarify_questions[0]
    return "Ask the targeted follow-up needed to convert this statement into reliable evidence."


def _status_label(status: str) -> str:
    return {
        "supported": "Supported",
        "weak": "Weak Evidence",
        "unsafe_to_infer": "Unsafe To Infer",
    }.get(status, status)


def _authority_for_jre_finding(f: Finding) -> Dict[str, str]:
    if f.rule_id.startswith("LLM_"):
        return {
            "layer": "AI Candidate",
            "authority": "Advisory",
            "effect": "candidate signal only; capped before autonomy",
        }
    return {
        "layer": "Curated Rule",
        "authority": "Enforced",
        "effect": "can change readiness state, question order, or autonomy boundary",
    }


def _authority_for_bsg_finding(rule_id: str) -> Dict[str, str]:
    if rule_id.startswith("LLM_BSG_"):
        return {
            "layer": "AI Candidate",
            "authority": "Advisory",
            "effect": "holds for review; cannot independently fail closed",
        }
    return {
        "layer": "Curated Guardrail",
        "authority": "Enforced",
        "effect": "can cap maximum autonomy tier",
    }


def _explicit_claim_for(answer: str, concept: str) -> str:
    lower = answer.lower()
    if "no" in lower or "not" in lower or "deny" in lower:
        return f"Patient offers a negative or minimizing statement about {concept}."
    if re.search(r"\d", answer):
        return f"Patient/source provides a numeric or concrete statement about {concept}."
    return f"Patient/source provides a qualitative statement about {concept}."


def _safe_interpretation_for(answer: str, concept: str, confidence: float, status: str) -> str:
    label = _display_concept(concept)
    if concept == "care_context":
        return "The patient is asking to delay care because of cost or work pressure; this raises unsafe-delay and abandonment risk, not clinical reassurance."
    if status == "supported":
        return f"{label} can be treated as reasonably supported for this demo pathway."
    if STALE_BOUNDARY_RE.search(answer):
        return f"A past statement about {label} may exist, but current status is not established."
    if concept in OBJECTIVE_CONCEPTS and not re.search(r"\d", answer):
        return f"{label} was discussed, but no verifiable current number/timestamp is available."
    if confidence < 0.55:
        return f"{label} is present but too low-confidence to use as a stable fact."
    return f"{label} is only weakly supported and should be clarified before action."


def _unsafe_inference_for(answer: str, concept: str, status: str) -> str:
    label = _display_concept(concept)
    if status == "supported":
        return ""
    if STALE_BOUNDARY_RE.search(answer):
        return f"Do not infer current {label} from stale reassurance."
    if concept in OBJECTIVE_CONCEPTS and not re.search(r"\d", answer):
        return f"Do not infer objective safety for {label} without a number or source."
    if re.search(r"\b(no|not|nothing|fine|normal|okay|ok)\b", answer, re.I):
        return "Do not treat this denial or reassurance as strong negative evidence."
    return "Do not convert this statement into an unqualified clinical fact."


def _build_interpretation_boundaries_section(
    case: CaseInput,
    jre_report: ReadinessReport,
) -> Dict[str, Any]:
    """Section: explicit statement vs safe fact vs unsafe inference."""
    findings_by_concept: Dict[str, List[str]] = {}
    for f in jre_report.findings:
        findings_by_concept.setdefault(f.concept, []).append(f.category)

    rows = []
    for obs in jre_report.observations:
        answer = str(obs.raw_value)
        concept = obs.concept
        status = "supported"
        if obs.confidence < 0.55:
            status = "unsafe_to_infer"
        elif VAGUE_BOUNDARY_RE.search(answer) or obs.tags:
            status = "weak"
        if STALE_BOUNDARY_RE.search(answer):
            status = "unsafe_to_infer"
        if concept in OBJECTIVE_CONCEPTS and not re.search(r"\d", answer):
            status = "unsafe_to_infer"
        if "contradictory" in findings_by_concept.get(concept, []):
            status = "unsafe_to_infer"

        rows.append(
            {
                "concept": concept,
                "concept_label": _display_concept(concept),
                "patient_statement": answer,
                "explicit_claim": _explicit_claim_for(answer, concept),
                "safe_interpretation": _safe_interpretation_for(
                    answer, concept, obs.confidence, status
                ),
                "unsafe_inference": _unsafe_inference_for(answer, concept, status),
                "missing_followup": _slot_question(case.patient_context.domain, concept),
                "confidence": round(obs.confidence, 2),
                "source": obs.source,
                "boundary_status": status,
                "boundary_label": _status_label(status),
            }
        )

    unasked = []
    for category in ("missing", "needs_objective_data", "remote_boundary"):
        for item in jre_report.boundary_map.get(category, []):
            concept = str(item).split(":", 1)[0]
            detail = str(item).split(":", 1)[1].strip() if ":" in str(item) else str(item)
            unasked.append(
                {
                    "category": category,
                    "item": item,
                    "concept_label": _display_concept(concept),
                    "detail": detail,
                    "unsafe_inference": "Unasked is not denied; this cannot be summarized as absent.",
                    "closure_question": _slot_question(case.patient_context.domain, concept),
                }
            )

    return {
        "id": "interpretation_boundaries",
        "title": "Statement vs Fact",
        "subtitle": "What was said, what can safely be treated as fact, and what must not be inferred.",
        "data": {"rows": rows, "unasked": unasked[:8]},
    }


# ---------------------------------------------------------------------------
# Section builders for progressive analysis
# ---------------------------------------------------------------------------


def _build_observations_section(
    jre_report: ReadinessReport,
) -> Dict[str, Any]:
    """Section: observation confidence table."""
    obs_list = []
    for o in jre_report.observations:
        trap_explanations = []
        learned_prior_applied = False
        for tag in o.tags:
            if str(tag).startswith("experience_prior:"):
                learned_prior_applied = True
            if tag in TRAP_EXPLANATIONS:
                trap_explanations.append(
                    {"trap": tag, "explanation": TRAP_EXPLANATIONS[tag]}
                )
            elif "trap:" in str(o.trace):
                trap_explanations.append({"trap": tag, "explanation": tag})
        obs_list.append(
            {
                "concept": o.concept,
                "concept_label": _display_concept(o.concept),
                "raw": o.raw_value,
                "normalized": o.normalized_value,
                "confidence": round(o.confidence, 2),
                "source": o.source,
                "traps": [t["trap"] for t in trap_explanations],
                "trap_explanations": trap_explanations,
                "trace": o.trace,
                "learned_prior_applied": learned_prior_applied,
                "authority_layer": "Learned Prior" if learned_prior_applied else "Extractor",
                "authority": "Bounded Adjustment" if learned_prior_applied else "Evidence Candidate",
            }
        )
    return {
        "id": "observations",
        "title": "Observation Confidence",
        "subtitle": "Each answer scored for confidence. Red = low trust.",
        "data": {"observations": obs_list},
    }


def _build_mud_map_section(
    jre_report: ReadinessReport,
) -> Dict[str, Any]:
    """Section: known unknowns map."""
    categories = {
        "missing": [],
        "uncertain": [],
        "distorted": [],
        "contradictory": [],
        "unknowable_remote": [],
        "objective_needed": [],
    }
    for f in jre_report.findings:
        if f.category in categories:
            authority = _authority_for_jre_finding(f)
            categories[f.category].append(
                {
                    "concept": f.concept,
                    "display_name": _display_concept(f.concept),
                    "severity": round(f.severity, 2),
                    "reason": f.reason,
                    "rule_id": f.rule_id,
                    "evidence": f.evidence or "",
                    **authority,
                }
            )
    return {
        "id": "mud_map",
        "title": "Known Unknowns Map",
        "subtitle": "Missing, uncertain, distorted, contradictory, objective-needed, and remote-boundary signals.",
        "data": {
            "boundary_map": jre_report.boundary_map,
            "findings_by_category": categories,
            "total_findings": sum(len(v) for v in categories.values()),
        },
    }


def _build_red_flags_section(
    jre_report: ReadinessReport,
) -> Dict[str, Any]:
    """Section: interpretation boundary breaches."""
    red_flags = []
    for f in jre_report.findings:
        if f.category == "red_flag":
            authority = _authority_for_jre_finding(f)
            red_flags.append(
                {
                    "concept": f.concept,
                    "display_name": _display_concept(f.concept),
                    "severity": round(f.severity, 2),
                    "reason": f.reason,
                    "rule_id": f.rule_id,
                    "evidence": f.evidence or "",
                    **authority,
                }
            )

    # Gestalt patterns
    gestalts = []
    for t in jre_report.traces:
        if t.rule_id.startswith("GESTALT_"):
            gestalts.append(
                {
                    "pattern": t.rule_id,
                    "description": t.description,
                    "evidence": t.evidence,
                    "effect": t.effect,
                    "layer": "Curated Pattern",
                    "authority": "Enforced",
                }
            )

    # Source conflicts
    source_conflicts = []
    for t in jre_report.traces:
        if t.rule_id.startswith("SOURCE_CONFLICT"):
            source_conflicts.append(
                {
                    "rule_id": t.rule_id,
                    "description": t.description,
                    "evidence": t.evidence,
                    "effect": t.effect,
                    "layer": "Curated Source Rule",
                    "authority": "Enforced",
                }
            )

    return {
        "id": "red_flags",
        "title": "Interpretation Boundary Breaches",
        "subtitle": "Red flags, cross-domain patterns, and source conflicts that limit safe inference.",
        "data": {
            "red_flags": red_flags,
            "gestalts": gestalts,
            "source_conflicts": source_conflicts,
        },
    }


def _build_jri_section(
    jre_report: ReadinessReport,
) -> Dict[str, Any]:
    """Section 4: Judgment Readiness Score."""
    scores = jre_report.scores
    # Plain-English state reasons
    state_reasons = {
        "ESCALATE": "A critical clinical signal requires immediate clinician attention.",
        "NEED_OBJECTIVE_DATA": "Key objective measurements are missing — cannot safely proceed without them.",
        "CLARIFY": "Ambiguous or contradictory information needs resolution before proceeding.",
        "READY": "Sufficient information collected with acceptable confidence levels.",
    }
    return {
        "id": "jri_score",
        "title": "Judgment Readiness Score",
        "subtitle": "How ready is this encounter for a decision?",
        "data": {
            "readiness_index": round(scores.readiness_index, 1),
            "completeness": round(scores.completeness, 2),
            "reliability": round(scores.reliability, 2),
            "objective_coverage": round(scores.objective_coverage, 2),
            "contradiction_load": round(scores.contradiction_load, 2),
            "distortion_load": round(scores.distortion_load, 2),
            "red_flag_load": round(scores.red_flag_load, 2),
            "jre_state": jre_report.state,
            "state_reason": state_reasons.get(
                jre_report.state, "State determined by engine rules."
            ),
        },
    }


def _build_guardrails_section(
    bsg_report: GuardrailReport,
) -> Dict[str, Any]:
    """Section: assumption sufficiency check."""
    assumptions = []
    for a in bsg_report.assumption_register:
        assumptions.append(
            {"name": a.name, "status": a.status, "reason": a.reason}
        )

    findings = []
    for f in bsg_report.findings:
        authority = _authority_for_bsg_finding(f.rule_id)
        findings.append(
            {
                "rule_id": f.rule_id,
                "category": f.category,
                "severity": round(f.severity, 2),
                "reason": f.reason,
                "evidence": f.evidence,
                "control": f.control,
                "action": f.action,
                "autonomy_cap": f.autonomy_cap,
                **authority,
            }
        )

    return {
        "id": "guardrails",
        "title": "Assumption Sufficiency Check",
        "subtitle": "Are we still inside the safe operating envelope?",
        "data": {
            "guardrail_state": bsg_report.guardrail_state,
            "max_autonomy_tier": bsg_report.max_autonomy_tier,
            "autonomy_description": AUTONOMY_TIERS.get(
                bsg_report.max_autonomy_tier, ""
            ),
            "novelty_score": round(bsg_report.novelty_score, 2),
            "residual_risk_budget": round(bsg_report.residual_risk_budget, 2),
            "assumption_register": assumptions,
            "findings": findings,
        },
    }


def _build_safety_decision_section(
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    combined_state: str,
) -> Dict[str, Any]:
    """Section 6: Combined Safety Decision."""
    # Determine which engine drove the decision
    jre_idx = (
        STATE_PRIORITY.index(jre_report.state)
        if jre_report.state in STATE_PRIORITY
        else len(STATE_PRIORITY)
    )
    bsg_idx = (
        STATE_PRIORITY.index(bsg_report.guardrail_state)
        if bsg_report.guardrail_state in STATE_PRIORITY
        else len(STATE_PRIORITY)
    )

    if jre_idx < bsg_idx:
        driver = "Judgment Readiness Engine (clinical signal)"
    elif bsg_idx < jre_idx:
        driver = "Black Swan Guard (system safety)"
    else:
        driver = "Both engines agree"

    # What would happen next
    next_actions = {
        "ESCALATE": "Route immediately to emergency clinician pathway. No autonomous action permitted.",
        "FAIL_CLOSED": "Hard stop. System integrity breach detected. Human review required before any action.",
        "ROUTE_CLINICIAN": "Route to available clinician for review. AI may summarize but not act.",
        "NEED_OBJECTIVE_DATA": "Request specific objective measurements before proceeding.",
        "HOLD_AND_VERIFY": "Pause pathway. Clinician must verify key information before continuing.",
        "CLARIFY": "Ask targeted clarification questions to resolve ambiguity.",
        "ALLOW_WITH_AUDIT": "Pathway may proceed with audit trail. Clinician oversight per tier.",
        "READY": "Sufficient information for pathway action within approved autonomy tier.",
    }

    return {
        "id": "safety_decision",
        "title": "Safety Decision",
        "subtitle": "The combined verdict from both engines.",
        "data": {
            "combined_state": combined_state,
            "jre_state": jre_report.state,
            "bsg_state": bsg_report.guardrail_state,
            "decision_driver": driver,
            "next_action": next_actions.get(
                combined_state, "Refer to clinical governance."
            ),
            "autonomy_tier": bsg_report.max_autonomy_tier,
            "autonomy_description": AUTONOMY_TIERS.get(
                bsg_report.max_autonomy_tier, ""
            ),
        },
    }


def _build_demo_summary(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    combined_state: str,
) -> Dict[str, Any]:
    """Top-level non-technical summary for the live walkthrough."""
    top_jre = sorted(jre_report.findings, key=lambda x: -x.severity)[:4]
    top_bsg = sorted(bsg_report.findings, key=lambda x: -x.severity)[:3]
    why = []
    for f in top_jre:
        why.append(f"{_display_concept(f.concept)}: {f.reason}")
    for f in top_bsg:
        why.append(f.reason)

    if not why:
        why.append("No high-severity blocker was found by the governed layers.")

    return {
        "state": combined_state,
        "case_title": CASE_NARRATIVES.get(case.case_id).title if case.case_id in CASE_NARRATIVES else case.case_id,
        "why": why[:5],
        "authority": "Curated safety rules and the ensemble governor made the routing decision.",
        "ai_role": "External LLM findings are advisory candidate signals only; they can support review but cannot authorize or hard-stop care by themselves.",
        "patient_pattern": "The patient wording, omissions, and context are evaluated as evidence boundaries, not treated as clean negative evidence.",
        "autonomy": f"{bsg_report.max_autonomy_tier}: {AUTONOMY_TIERS.get(bsg_report.max_autonomy_tier, '')}",
    }


def _build_provenance_authority_section(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    combined_state: str,
) -> Dict[str, Any]:
    """Section: show what is curated, AI-derived, learned, or memory-only."""
    learned_observations = [
        o
        for o in jre_report.observations
        if any(str(tag).startswith("experience_prior:") for tag in o.tags)
    ]
    learned_questions = [
        q for q in jre_report.next_questions if str(q.rule_id).startswith("EXP_")
    ]
    curated_jre = [f for f in jre_report.findings if not f.rule_id.startswith("LLM_")]
    ai_jre = [f for f in jre_report.findings if f.rule_id.startswith("LLM_")]
    curated_bsg = [f for f in bsg_report.findings if not f.rule_id.startswith("LLM_BSG_")]
    ai_bsg = [f for f in bsg_report.findings if f.rule_id.startswith("LLM_BSG_")]

    finding_rows = []
    for f in sorted(jre_report.findings, key=lambda x: -x.severity)[:6]:
        finding_rows.append(
            {
                "name": f.concept,
                "display_name": _display_concept(f.concept),
                "evidence": f.evidence or f.reason,
                "rule_id": f.rule_id,
                "source": "JRE",
                **_authority_for_jre_finding(f),
            }
        )
    for f in sorted(bsg_report.findings, key=lambda x: -x.severity)[:5]:
        finding_rows.append(
            {
                "name": f.rule_id,
                "display_name": f.reason,
                "evidence": f.evidence or f.reason,
                "rule_id": f.rule_id,
                "source": "BSG",
                **_authority_for_bsg_finding(f.rule_id),
            }
        )

    layers = [
        {
            "name": "Curated clinical rules",
            "authority": "Enforced",
            "count": len(curated_jre),
            "examples": [_display_concept(f.concept) for f in curated_jre[:3]],
            "effect": "Can change readiness state, ask questions, route, or cap automation.",
        },
        {
            "name": "Curated safety guardrails",
            "authority": "Enforced",
            "count": len(curated_bsg),
            "examples": [f.rule_id for f in curated_bsg[:3]],
            "effect": "Can fail closed or cap the maximum autonomy tier.",
        },
        {
            "name": "AI candidate signals",
            "authority": "Advisory",
            "count": len(ai_jre) + len(ai_bsg),
            "examples": [f.rule_id for f in ai_jre[:2]] + [f.rule_id for f in ai_bsg[:2]],
            "effect": "Can suggest review targets, but cannot independently authorize or hard-stop action.",
        },
        {
            "name": "Learned priors",
            "authority": "Bounded Adjustment",
            "count": len(learned_observations) + len(learned_questions),
            "examples": [_display_concept(o.concept) for o in learned_observations[:3]]
            + [_display_concept(q.concept) for q in learned_questions[:3]],
            "effect": "Can adjust confidence or question priority inside bounded limits.",
        },
        {
            "name": "VAMS / stigmergic memory",
            "authority": "Advisory",
            "count": 1,
            "examples": [
                "near-miss recall",
                "trace heat",
                "pattern completion",
            ],
            "effect": "Can propose missing nodes and falsifiers; validators must approve before behavior changes.",
        },
        {
            "name": "Ensemble governor",
            "authority": "Enforced",
            "count": 1,
            "examples": [
                f"JRE={jre_report.state}",
                f"BSG={bsg_report.guardrail_state}",
                f"Final={combined_state}",
            ],
            "effect": "Most restrictive state wins; autonomy cannot exceed the guardrail cap.",
        },
    ]

    return {
        "id": "provenance_authority",
        "title": "Provenance & Authority",
        "subtitle": "Which layer produced each signal and whether it can actually affect autonomy.",
        "data": {
            "llm_available": _llm is not None and _llm.available,
            "case_domain": case.patient_context.domain,
            "layers": layers,
            "finding_rows": finding_rows,
            "ensemble": [
                {
                    "layer": "Judgment Readiness Engine",
                    "state": jre_report.state,
                    "authority": "Enforced clinical-readiness state",
                },
                {
                    "layer": "Black Swan Guard",
                    "state": bsg_report.guardrail_state,
                    "authority": "Enforced operating-envelope state",
                },
                {
                    "layer": "Combined governor",
                    "state": combined_state,
                    "authority": "Most restrictive final disposition",
                },
                {
                    "layer": "Autonomy tier",
                    "state": bsg_report.max_autonomy_tier,
                    "authority": AUTONOMY_TIERS.get(bsg_report.max_autonomy_tier, ""),
                },
            ],
            "invariants": [
                "LLM-only findings are advisory candidate signals and cannot independently create a hard stop or authorization.",
                "Memory recall can suggest missing nodes, falsifiers, and template candidates, but cannot authorize action.",
                "Learned priors can tune confidence and question priority only inside bounded limits.",
                "Validated rules, guardrails, and the ensemble governor decide the visible autonomy boundary.",
            ],
        },
    }


def _build_autonomy_boundary_section(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    combined_state: str,
) -> Dict[str, Any]:
    """Section: what the AI may do and what is blocked."""
    allowed = ["summarize the encounter", "preserve an audit trail"]
    blocked = []
    if combined_state in {"ESCALATE", "FAIL_CLOSED"}:
        allowed.append("route urgently to a human pathway")
        blocked.extend(["continue routine automation", "close the encounter as low risk"])
    elif combined_state in {"ROUTE_CLINICIAN", "HOLD_AND_VERIFY", "NEED_OBJECTIVE_DATA", "CLARIFY"}:
        allowed.extend(["ask targeted clarification", "draft a clinician handoff"])
        blocked.extend(["complete autonomous action", "treat weak denials as settled facts"])
    else:
        allowed.extend(["complete the narrow pathway action", "proceed with audit"])

    if case.patient_context.domain == "med_refill_hypertension" and bsg_report.max_autonomy_tier != "T4_NARROW_AUTONOMOUS_ACTION":
        blocked.append("autonomous refill renewal")

    reasons = []
    for f in sorted(jre_report.findings, key=lambda x: -x.severity):
        if f.category in {"objective_needed", "missing", "contradictory", "distorted", "unknowable_remote", "red_flag"}:
            reasons.append(f"{_display_concept(f.concept)}: {f.reason}")
        if len(reasons) >= 3:
            break
    for f in sorted(bsg_report.findings, key=lambda x: -x.severity):
        if len(reasons) >= 3:
            break
        reasons.append(f"{f.rule_id}: {f.reason}")

    restore = [q.question for q in jre_report.next_questions[:3]]
    if not restore:
        restore = ["Human review or governance confirmation is the next step."]

    business_effect = (
        "Preserves safe automation by asking the smallest useful clarification before routing."
        if combined_state in {"CLARIFY", "NEED_OBJECTIVE_DATA", "HOLD_AND_VERIFY"}
        else "Routes decisively when uncertainty or assumption failure makes automation inappropriate."
        if combined_state in {"ESCALATE", "FAIL_CLOSED", "ROUTE_CLINICIAN"}
        else "Allows the narrow action while keeping the audit boundary visible."
    )

    return {
        "id": "autonomy_boundary",
        "title": "Autonomy Boundary",
        "subtitle": "What the AI is allowed to do, what is blocked, and what would restore readiness.",
        "data": {
            "current_cap": bsg_report.max_autonomy_tier,
            "current_state": combined_state,
            "allowed_actions": list(dict.fromkeys(allowed)),
            "blocked_actions": list(dict.fromkeys(blocked)),
            "why_blocked": reasons,
            "what_restores_readiness": restore,
            "business_effect": business_effect,
        },
    }


def _build_mitigation_plan_section(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    combined_state: str,
) -> Dict[str, Any]:
    """Section: how the system mitigates current and learned failure modes."""
    finding_categories = {f.category for f in jre_report.findings}
    guardrail_categories = {f.category for f in bsg_report.findings}
    objective_gap = "objective_needed" in finding_categories
    source_or_stale_gap = bool(
        {"objective_data_integrity", "workflow_integrity", "communication_envelope"}.intersection(
            guardrail_categories
        )
    )
    routed = combined_state in {
        "ESCALATE",
        "FAIL_CLOSED",
        "ROUTE_CLINICIAN",
        "HOLD_AND_VERIFY",
        "NEED_OBJECTIVE_DATA",
    }

    immediate_controls = []
    if routed:
        immediate_controls.append("Cap autonomy and route, verify, or escalate before routine completion.")
    else:
        immediate_controls.append("Allow the narrow action only with audit and explicit boundary trace.")
    if objective_gap or source_or_stale_gap:
        immediate_controls.append("Require timestamped objective evidence or source verification before upgrading autonomy.")
    if "contradictory" in finding_categories:
        immediate_controls.append("Resolve contradictory statements before treating either source as settled fact.")
    if "distorted" in finding_categories or "uncertain" in finding_categories:
        immediate_controls.append("Ask the highest-yield clarification rather than accepting vague reassurance.")
    if not immediate_controls:
        immediate_controls.append("Continue standard audit logging and monitor for boundary drift.")

    top_findings = sorted(jre_report.findings, key=lambda x: -x.severity)[:5]
    top_bsg = sorted(bsg_report.findings, key=lambda x: -x.severity)[:4]
    trace_regions = [
        {
            "region": "claims",
            "signal": "patient statements and denials",
            "status": "reinforced" if {"distorted", "uncertain"}.intersection(finding_categories) else "quiet",
            "decay": "medium",
        },
        {
            "region": "objective",
            "signal": "numbers, timestamps, chart/device evidence",
            "status": "hot" if objective_gap or source_or_stale_gap else "stable",
            "decay": "fast unless timestamped",
        },
        {
            "region": "source_conflict",
            "signal": "patient/device/caregiver/chart disagreement",
            "status": "hot" if "contradictory" in finding_categories else "quiet",
            "decay": "slow",
        },
        {
            "region": "social_workflow",
            "signal": "cost fear, coercion, minimization, nonresponse, desired outcome pressure",
            "status": "hot" if {"workflow_integrity", "communication_envelope", "social_channel_risk"}.intersection(guardrail_categories) else "watch",
            "decay": "very slow",
        },
        {
            "region": "temporal_staleness",
            "signal": "old reassurance, old vitals, missing freshness",
            "status": "hot" if source_or_stale_gap else "watch",
            "decay": "fast for old objective data",
        },
    ]

    if case.patient_context.domain == "med_refill_hypertension" and (routed or objective_gap or source_or_stale_gap):
        recalled_pattern = "Refill near miss: vague BP control + stale or missing objective data + medication-context risk."
        pattern_completion = [
            "current BP number and timestamp",
            "renal function / potassium freshness when ACE/ARB-like safety matters",
            "NSAID or medication-change context",
            "dizziness, hypotension, pregnancy, or adverse-effect signal",
        ]
    elif case.patient_context.domain == "med_refill_hypertension":
        recalled_pattern = "Clean refill analogue: current objective data and pathway assumptions appear sufficient for narrow audited automation."
        pattern_completion = [
            "preserve audit trace",
            "avoid redundant questions",
            "monitor for new symptoms or medication changes",
            "use as low-friction control example",
        ]
    elif case.patient_context.domain == "chest_discomfort":
        recalled_pattern = "Chest-discomfort near miss: patient rejects the word pain while describing exertional pressure or functional limitation."
        pattern_completion = [
            "exertional relationship",
            "dyspnea or sentence-test limitation",
            "diaphoresis, nausea, radiation, syncope",
            "remote ECG/vital boundary",
        ]
    elif case.patient_context.domain == "dyspnea_respiratory":
        recalled_pattern = "Respiratory near miss: calm denial conflicts with functional limitation, stale device reading, or caregiver/device evidence."
        pattern_completion = [
            "current oxygen saturation with timestamp",
            "sentence test",
            "walking-room tolerance",
            "mental status and rescue-medication response",
        ]
    else:
        recalled_pattern = "Boundary near miss: the important signal is uncertainty shape, not just the diagnosis label."
        pattern_completion = [
            "source reliability",
            "missing hard-stop variables",
            "stale evidence",
            "patient minimization or workflow pressure",
        ]

    falsifiers = []
    for q in jre_report.next_questions[:4]:
        falsifiers.append(
            {
                "target": q.concept,
                "test": q.question,
                "why": q.reason,
            }
        )
    if not falsifiers:
        falsifiers.append(
            {
                "target": "governance",
                "test": "Clinician review confirms the pathway assumptions and objective evidence are sufficient.",
                "why": "No further automated question was selected by the current engine.",
            }
        )

    memory_effect = (
        "Seed this pattern as a high-value near-miss analogue for future recall."
        if routed or objective_gap or source_or_stale_gap
        else "Record as a clean or low-friction pathway example to reduce unnecessary future questions."
    )

    mitigations = [
        {
            "layer": "Current deterministic controls",
            "purpose": "Prevent unsafe action today.",
            "actions": immediate_controls[:4],
        },
        {
            "layer": "Stigmergic boundary trace",
            "purpose": "Keep weak but repeated signals from disappearing between turns.",
            "actions": [
                "Deposit traces for claims, objective evidence, source conflict, social/workflow risk, temporal staleness, and outcome feedback.",
                "Let stale evidence fade while unresolved source conflict and nonresponse persist longer.",
                "Escalate repeated nonresponse after risk instead of closing the encounter as abandoned.",
            ],
        },
        {
            "layer": "VAMS near-miss recall",
            "purpose": "Use partial cues to remember prior boundary failures.",
            "actions": [
                memory_effect,
                "Recall similar cases by sparse clinical-boundary signature, not only diagnosis label.",
                "Use recalled memories to suggest missing nodes and falsifiers, then pass them through deterministic validators.",
            ],
        },
        {
            "layer": "Governed template promotion",
            "purpose": "Turn repeated learning into auditable software, not uncontrolled online behavior.",
            "actions": [
                "Store clinician feedback as confirmed, corrected, false positive, missed, or churn/friction.",
                "Promote new rules only after simulation cases and governance review.",
                "Keep memory-only signals advisory until validated by deterministic evidence requirements.",
            ],
        },
        {
            "layer": "Business mitigation",
            "purpose": "Protect safety while reducing avoidable routing, abandonment, and trust loss.",
            "actions": [
                "Ask the smallest useful next question when the gap is fixable.",
                "Provide a clearer visit rationale when routing is necessary.",
                "Deduplicate low-yield clarification loops while never suppressing critical hard stops.",
            ],
        },
    ]

    return {
        "id": "mitigation_plan",
        "title": "Mitigation Plan",
        "subtitle": "How this case becomes safer now and smarter later without letting memory make clinical decisions.",
        "data": {
            "case_id": case.case_id,
            "combined_state": combined_state,
            "recalled_pattern": recalled_pattern,
            "pattern_completion": pattern_completion,
            "trace_regions": trace_regions,
            "falsifiers": falsifiers,
            "top_current_signals": [
                {"kind": "JRE", "name": _display_concept(f.concept), "reason": f.reason}
                for f in top_findings
            ]
            + [
                {"kind": "BSG", "name": f.rule_id, "reason": f.reason}
                for f in top_bsg
            ],
            "mitigations": mitigations,
        },
    }


def _build_questions_section(
    jre_report: ReadinessReport,
    case: CaseInput,
    combined_state: str,
) -> Dict[str, Any]:
    """Section 7: What should we ask next?"""
    modality = case.patient_context.modality
    modality_info = MODALITY_ADAPTATIONS.get(modality, {})

    questions = []
    if combined_state in {"ESCALATE", "FAIL_CLOSED"}:
        for priority, concept, question, reason in [
            (3.0, "current_symptoms", "Are the tightness, pressure, shortness of breath, sweating, faintness, or weakness happening right now?", "Confirm immediate danger while routing to urgent human care."),
            (2.8, "support", "Are you alone, or is someone with you who can help call emergency services?", "Reduce abandonment risk during escalation."),
            (2.6, "transport", "Can you call emergency services now? Do not drive yourself if symptoms are active or returning.", "Prevent unsafe self-transport after a possible time-sensitive event."),
            (2.4, "cost_barrier", "If cost is why you want to wait, can we help you find the safest urgent option now rather than delaying?", "Address the stated barrier without downgrading risk."),
        ]:
            questions.append(
                {
                    "concept": concept,
                    "concept_label": _display_concept(concept),
                    "question": question,
                    "reason": reason,
                    "clear_step": "Escalation support; do not continue autonomous pathway.",
                    "priority": priority,
                    "expected_gain": 0.0,
                    "rule_id": "ESCALATION_SUPPORT",
                }
            )

    for q in jre_report.next_questions:
        questions.append(
            {
                "concept": q.concept,
                "concept_label": _display_concept(q.concept),
                "question": q.question,
                "reason": q.reason,
                "clear_step": q.clear_step,
                "priority": round(q.priority, 2),
                "expected_gain": round(q.expected_information_gain, 2),
                "rule_id": q.rule_id,
            }
        )

    return {
        "id": "next_questions",
        "title": "Immediate Next Steps" if combined_state in {"ESCALATE", "FAIL_CLOSED"} else "What should we ask next?",
        "subtitle": "Escalation support questions; the system should not continue a routine autonomous pathway." if combined_state in {"ESCALATE", "FAIL_CLOSED"} else f"CLEAR questions adapted for {modality} modality.",
        "data": {
            "questions": questions,
            "modality": modality,
            "modality_prefix": modality_info.get("prefix", ""),
            "total_questions": len(questions),
            "mode": "escalation" if combined_state in {"ESCALATE", "FAIL_CLOSED"} else "clarification",
        },
    }


def _build_llm_section(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    llm_result=None,
) -> Dict[str, Any]:
    """Section 8: LLM Second Opinion.

    Accepts a pre-computed LLMAnalysisResult to avoid redundant HTTP calls.
    The analyze endpoint runs a single LLM call and passes it here.
    """
    llm_findings = []
    llm_available = _llm is not None and _llm.available
    llm_error = None

    if llm_result is not None:
        if llm_result.success:
            for f in llm_result.findings:
                llm_findings.append(
                    {
                        "category": f.category,
                        "concept": f.concept,
                        "severity": round(f.severity, 2),
                        "reason": f.reason,
                        "evidence": f.evidence,
                        "confidence": round(f.confidence, 2),
                    }
                )
        else:
            llm_error = llm_result.error
    # No fallback LLM call here — the frontend calls /demo/llm-analyze
    # separately for async UX. This keeps section building fast.

    # Regex-only findings for comparison
    regex_findings = []
    for f in jre_report.findings:
        if f.category in ("red_flag", "distorted"):
            regex_findings.append(
                {
                    "category": f.category,
                    "concept": f.concept,
                    "severity": round(f.severity, 2),
                    "reason": f.reason,
                    "rule_id": f.rule_id,
                }
            )
    for f in bsg_report.findings:
        regex_findings.append(
            {
                "category": f.category,
                "concept": f.rule_id,
                "severity": round(f.severity, 2),
                "reason": f.reason,
                "rule_id": f.rule_id,
            }
        )

    # Compute what each caught uniquely
    llm_concepts = {f["concept"] for f in llm_findings}
    regex_concepts = {f["concept"] for f in regex_findings}
    llm_unique = llm_concepts - regex_concepts
    regex_unique = regex_concepts - llm_concepts

    return {
        "id": "llm_opinion",
        "title": "Extractor Cross-Check",
        "subtitle": "Optional LLM-generated candidate signals compared with governed safety findings.",
        "data": {
            "llm_available": llm_available,
            "llm_error": llm_error,
            "llm_findings": llm_findings,
            "regex_findings": regex_findings,
            "llm_unique_concepts": sorted(llm_unique),
            "regex_unique_concepts": sorted(regex_unique),
            "overlap_concepts": sorted(llm_concepts & regex_concepts),
        },
    }


def _build_progressive_sections(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    combined_state: str,
    llm_result=None,
) -> List[Dict[str, Any]]:
    """Build progressive analysis sections for the executive demo."""
    return [
        _build_interpretation_boundaries_section(case, jre_report),
        _build_provenance_authority_section(case, jre_report, bsg_report, combined_state),
        _build_observations_section(jre_report),
        _build_mud_map_section(jre_report),
        _build_red_flags_section(jre_report),
        _build_jri_section(jre_report),
        _build_guardrails_section(bsg_report),
        _build_safety_decision_section(jre_report, bsg_report, combined_state),
        _build_autonomy_boundary_section(case, jre_report, bsg_report, combined_state),
        _build_questions_section(jre_report, case, combined_state),
        _build_mitigation_plan_section(case, jre_report, bsg_report, combined_state),
        _build_llm_section(case, jre_report, bsg_report, llm_result=llm_result),
    ]


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.get("/demo/cases")
def get_demo_cases():
    """Return all cases with narratives for the case selection grid."""
    cases = []
    for case in list(BASE_CASES) + list(BLACK_SWAN_CASES):
        narrative = CASE_NARRATIVES.get(case.case_id)
        case_dict = _case_to_analyze_dict(case)
        cases.append(
            {
                "case_id": case.case_id,
                "title": narrative.title if narrative else case.case_id,
                "scenario": narrative.scenario if narrative else "",
                "category": narrative.category if narrative else "unknown",
                "category_label": CATEGORY_LABELS.get(
                    narrative.category if narrative else "", "Other"
                ),
                "domain": case.patient_context.domain,
                "age": case.patient_context.age,
                "modality": case.patient_context.modality,
                "chief_concern": case.patient_context.chief_concern,
                "jre_demonstrates": narrative.jre_demonstrates if narrative else "",
                "bsg_demonstrates": narrative.bsg_demonstrates if narrative else "",
                "combined_insight": narrative.combined_insight if narrative else "",
                "case_data": case_dict,
            }
        )
    return {"total": len(cases), "cases": cases}


@app.post("/demo/analyze")
def analyze_case(req: AnalyzeRequest):
    """Full analysis returning 13 progressive sections."""
    _validate_domain(req.patient_context.domain)
    start = time.monotonic()
    case = _to_case_input(req)

    jre_report = _jre.evaluate(case)
    bsg_report = _guard.evaluate(case, jre_report)
    combined_state = most_restrictive(jre_report.state, bsg_report.guardrail_state)

    # LLM is NOT called here — Section 8 reports llm_available status
    # and the browser can trigger LLM analysis separately if desired.
    # This keeps analysis fast and deterministic for the progressive reveal.
    sections = _build_progressive_sections(
        case, jre_report, bsg_report, combined_state, llm_result=None
    )
    duration_ms = (time.monotonic() - start) * 1000

    return {
        "case_id": case.case_id,
        "combined_state": combined_state,
        "duration_ms": round(duration_ms, 1),
        "summary": _build_demo_summary(case, jre_report, bsg_report, combined_state),
        "sections": sections,
    }


@app.post("/demo/feedback")
def submit_feedback(feedback: FeedbackInput):
    """Submit clinician feedback to update experience memory."""
    valid_assessments = {"confirmed", "corrected", "false_positive", "missed"}
    if feedback.clinician_assessment not in valid_assessments:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid assessment '{feedback.clinician_assessment}'. Valid: {sorted(valid_assessments)}",
        )

    of = OutcomeFeedback(
        case_id=feedback.case_id,
        concept=feedback.concept,
        domain=feedback.domain,
        clinician_assessment=feedback.clinician_assessment,
        corrected_value=feedback.corrected_value,
        severity_adjustment=feedback.severity_adjustment,
        notes=feedback.notes,
    )
    updates = _memory.record_feedback(of)
    return {
        "status": "recorded",
        "case_id": feedback.case_id,
        "assessment": feedback.clinician_assessment,
        "priors_updated": len(updates),
        "updated_values": updates,
        "total_feedback": len(_memory.feedback_log),
    }


@app.get("/demo/experience")
def get_experience():
    """Return current distortion priors and feedback count."""
    priors = {}
    for (domain, concept, trap), val in _memory.distortion_priors.items():
        key = f"{domain}/{concept}/{trap}"
        priors[key] = round(val, 4)
    return {
        "distortion_priors": priors,
        "total_priors": len(priors),
        "feedback_count": len(_memory.feedback_log),
        "events_count": len(_memory.events),
    }


@app.post("/demo/llm-analyze")
def llm_analyze(req: AnalyzeRequest):
    """Run LLM analysis on a case. Called separately from /demo/analyze for async UX."""
    if _llm is None or not _llm.available:
        return {
            "llm_available": False,
            "llm_error": "LLM not available. Set OPENROUTER_API_KEY to enable.",
            "llm_findings": [],
            "model": None,
            "raw_preview": "",
        }

    _validate_domain(req.patient_context.domain)
    case = _to_case_input(req)

    try:
        result = _llm.analyze_case(case)
        findings = []
        if result.success:
            for f in result.findings:
                findings.append(
                    {
                        "category": f.category,
                        "concept": f.concept,
                        "severity": round(f.severity, 2),
                        "reason": f.reason,
                        "evidence": f.evidence,
                        "confidence": round(f.confidence, 2),
                    }
                )
        return {
            "llm_available": True,
            "llm_error": result.error if not result.success else None,
            "llm_findings": findings,
            "model": result.model,
            "raw_preview": result.raw_response[:500],
            "llm_note": "LLM ran and returned no additional candidate signals." if result.success and not findings else "",
        }
    except Exception as e:
        return {
            "llm_available": True,
            "llm_error": str(e),
            "llm_findings": [],
            "model": _llm.model if _llm is not None else None,
            "raw_preview": "",
        }


@app.post("/demo/suggest-rule")
def suggest_rule(req: SuggestRuleRequest):
    """Ask LLM to propose new detection rules for a case."""
    if _llm is None or not _llm.available:
        return {
            "success": False,
            "error": "LLM not available. Set OPENROUTER_API_KEY to enable.",
            "suggestions": [],
        }

    # Build a CaseInput if case data provided
    if req.statements and req.patient_context:
        case = CaseInput(
            case_id=req.case_id or "suggest-rule-case",
            patient_context=PatientContext(
                age=req.patient_context.age,
                chief_concern=req.patient_context.chief_concern,
                domain=req.patient_context.domain,
                literacy_hint=req.patient_context.literacy_hint,
                language_barrier=req.patient_context.language_barrier,
                has_caregiver=req.patient_context.has_caregiver,
                modality=req.patient_context.modality,
                known_conditions=req.patient_context.known_conditions,
            ),
            statements=[
                Statement(
                    question=s.question,
                    answer=s.answer,
                    concept=s.concept,
                    source=s.source,
                )
                for s in req.statements
            ],
        )
    elif req.case_id and req.case_id in _ALL_CASES:
        case = _ALL_CASES[req.case_id]
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either case_id of a built-in case or patient_context + statements.",
        )

    result = _llm.suggest_rules(case, req.findings)
    return result


@app.post("/demo/suggest-case")
def suggest_case(req: SuggestCaseRequest):
    """Ask LLM to generate a new synthetic case for a domain."""
    if req.domain not in DOMAIN_TEMPLATES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported domain '{req.domain}'. Supported: {sorted(DOMAIN_TEMPLATES.keys())}",
        )

    if _llm is None or not _llm.available:
        return {
            "success": False,
            "error": "LLM not available. Set OPENROUTER_API_KEY to enable.",
            "case": None,
        }

    result = _llm.suggest_case(req.domain, req.gap_description)
    return result


# ---------------------------------------------------------------------------
# Inline HTML/CSS/JS — served at GET /
# ---------------------------------------------------------------------------


def _build_interactive_html() -> str:
    """Build the complete single-page interactive demo HTML."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Clinical Safety Demo — Judgment Readiness + Black Swan Guardrails</title>
<style>
:root {
  --bg: #f7fbff;
  --surface: #ffffff;
  --surface2: #eef7fb;
  --surface3: #fff8e8;
  --border: #cfe2ea;
  --text: #173042;
  --text-dim: #647789;
  --accent: #0f9f9a;
  --accent-light: #12b9b1;
  --accent-soft: #d9f8f4;
  --red: #d83b4c;
  --red-bg: rgba(216,59,76,0.12);
  --orange: #d97706;
  --orange-bg: rgba(245,158,11,0.16);
  --yellow: #a16207;
  --yellow-bg: rgba(250,204,21,0.22);
  --green: #11845b;
  --green-bg: rgba(16,185,129,0.15);
  --blue: #2563eb;
  --blue-bg: rgba(59,130,246,0.13);
  --purple: #7c3aed;
  --purple-bg: rgba(124,58,237,0.12);
  --radius: 10px;
  --shadow: 0 16px 38px rgba(31,97,114,0.14);
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background:
    radial-gradient(circle at top left, rgba(18,185,177,0.18), transparent 34rem),
    linear-gradient(180deg, #f7fbff 0%, #eef8f7 44%, #fffaf0 100%);
  color: var(--text);
  line-height: 1.6;
  min-height: 100vh;
}
.screen { display: none; padding: 24px; max-width: 1200px; margin: 0 auto; }
.screen.active { display: block; }

/* Header */
.header {
  background: rgba(255,255,255,0.88);
  border-bottom: 1px solid rgba(207,226,234,0.9);
  box-shadow: 0 6px 24px rgba(31,97,114,0.08);
  backdrop-filter: blur(14px);
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
}
.header h1 { font-size: 18px; font-weight: 600; }
.header h1 span { color: var(--accent); }
.header-nav { display: flex; gap: 8px; }
.header-nav button {
  background: #f5fbfd;
  border: 1px solid var(--border);
  color: var(--text-dim);
  padding: 6px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}
.header-nav button:hover, .header-nav button.active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
  box-shadow: 0 8px 18px rgba(15,159,154,0.22);
}

/* Screen 1: Case Grid */
.case-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.case-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}
.case-card:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}
.case-card .card-title { font-size: 16px; font-weight: 600; margin-bottom: 6px; }
.case-card .card-scenario { font-size: 13px; color: var(--text-dim); margin-bottom: 12px; line-height: 1.5; }
.case-card .card-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 500;
  white-space: nowrap;
}
.badge-domain { background: var(--blue-bg); color: var(--blue); }
.badge-age { background: var(--purple-bg); color: var(--purple); }
.badge-modality { background: var(--yellow-bg); color: var(--yellow); }
.category-header {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
  margin: 24px 0 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
.category-header:first-of-type { margin-top: 8px; }

/* Custom case button */
.custom-case-btn {
  background: linear-gradient(135deg, #ffffff, #f1fbfb);
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 20px;
  cursor: pointer;
  text-align: center;
  color: var(--text-dim);
  transition: all 0.2s;
  min-height: 150px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.custom-case-btn:hover {
  border-color: var(--accent);
  color: var(--accent-light);
}
.custom-case-btn .plus { font-size: 32px; line-height: 1; }

/* Screen 2: Encounter */
.encounter-banner {
  background: linear-gradient(135deg, #ffffff, #ecfbf8);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  margin-bottom: 16px;
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  align-items: center;
}
.encounter-banner .ctx-item { font-size: 13px; }
.encounter-banner .ctx-label { color: var(--text-dim); margin-right: 4px; }
.encounter-banner .ctx-value { font-weight: 600; }
.encounter-layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 20px;
}
@media (max-width: 768px) {
  .encounter-layout { grid-template-columns: 1fr; }
  .case-grid { grid-template-columns: 1fr; }
}
.dialogue-area {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}
.dialogue-pair {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}
.dialogue-pair:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
.dialogue-q {
  font-size: 13px;
  color: var(--accent);
  margin-bottom: 6px;
  font-weight: 500;
}
.dialogue-q .q-number { color: var(--text-dim); font-weight: 600; }
.dialogue-q .concept-tag {
  font-size: 11px;
  background: var(--accent-soft);
  padding: 1px 6px;
  border-radius: 4px;
  color: var(--text-dim);
  margin-left: 6px;
}
.dialogue-a {
  font-size: 14px;
  padding: 8px 12px;
  background: #f7fcfd;
  border-radius: 8px;
  border: 1px solid transparent;
  min-height: 40px;
  outline: none;
  transition: border-color 0.2s;
}
.dialogue-a:focus { border-color: var(--accent); }
.dialogue-a .source-tag {
  font-size: 11px;
  color: var(--text-dim);
  float: right;
}
.sidebar-narrative {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}
.sidebar-narrative h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--accent);
}
.sidebar-narrative p { font-size: 13px; color: var(--text-dim); margin-bottom: 12px; line-height: 1.6; }
.sidebar-narrative .scenario-text { color: var(--text); font-size: 14px; font-weight: 500; }
.sidebar-narrative .insight-label { font-size: 11px; font-weight: 600; color: var(--text); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }

/* Buttons */
.btn {
  padding: 10px 24px;
  border-radius: 8px;
  border: none;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.btn-primary { background: var(--accent); color: white; box-shadow: 0 8px 18px rgba(15,159,154,0.2); }
.btn-primary:hover { background: var(--accent-light); transform: translateY(-1px); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: #f8fcfd; color: var(--text); border: 1px solid var(--border); }
.btn-secondary:hover { border-color: var(--accent); }
.btn-sm { padding: 6px 14px; font-size: 12px; }
.btn-row { display: flex; gap: 10px; margin-top: 20px; justify-content: flex-end; }

/* Screen 3: Analysis */
.analysis-section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
  margin-bottom: 16px;
  opacity: 0;
  transform: translateY(16px);
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.analysis-section:nth-child(3n+1) { border-top: 3px solid var(--accent); }
.analysis-section:nth-child(3n+2) { border-top: 3px solid #f59e0b; }
.analysis-section:nth-child(3n) { border-top: 3px solid #3b82f6; }
.analysis-section.revealed {
  opacity: 1;
  transform: translateY(0);
}
.analysis-section .section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
}
.section-number {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), var(--blue));
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.section-title { font-size: 16px; font-weight: 600; }
.section-subtitle { font-size: 13px; color: var(--text-dim); margin-bottom: 16px; margin-left: 40px; }
.section-body { margin-left: 40px; }

/* Observation table */
.obs-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.obs-table th { text-align: left; padding: 8px 10px; color: var(--text-dim); font-weight: 500; border-bottom: 1px solid var(--border); }
.obs-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
.obs-table tr.low-confidence { background: var(--red-bg); }
.confidence-bar {
  width: 60px;
  height: 8px;
  background: var(--surface2);
  border-radius: 4px;
  overflow: hidden;
  display: inline-block;
  vertical-align: middle;
  margin-right: 6px;
}
.confidence-bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }
.trap-tag { font-size: 11px; background: var(--red-bg); color: var(--red); padding: 1px 6px; border-radius: 4px; }

/* MUD Map */
.mud-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.mud-cell {
  background: #f8fcfd;
  border: 1px solid rgba(207,226,234,0.75);
  border-radius: 8px;
  padding: 12px;
}
.mud-cell .mud-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 6px; font-weight: 600; }
.mud-cell .mud-count { font-size: 24px; font-weight: 700; }
.mud-finding { font-size: 12px; color: var(--text-dim); margin-top: 4px; padding-left: 8px; border-left: 2px solid var(--border); }
.mud-cell.has-items .mud-count { color: var(--orange); }

/* Provenance and authority */
.authority-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}
.authority-Enforced { background: var(--green-bg); color: var(--green); }
.authority-Advisory { background: var(--blue-bg); color: var(--blue); }
.authority-Bounded { background: var(--yellow-bg); color: #9a5d00; }
.authority-Evidence { background: var(--surface2); color: var(--text-dim); }
.provenance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.provenance-card {
  background: #f8fcfd;
  border: 1px solid rgba(207,226,234,0.85);
  border-radius: 8px;
  padding: 12px;
}
.provenance-card h4 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 6px;
}
.provenance-effect { font-size: 12px; color: var(--text-dim); line-height: 1.45; margin-bottom: 8px; }
.provenance-examples { display: flex; flex-wrap: wrap; gap: 4px; }
.provenance-token {
  font-size: 11px;
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 2px 6px;
  color: var(--text-dim);
}
.authority-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 10px; }
.authority-table th { text-align: left; padding: 7px 8px; color: var(--text-dim); border-bottom: 1px solid var(--border); }
.authority-table td { padding: 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
.ensemble-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
  margin: 12px 0;
}
.ensemble-step {
  background: linear-gradient(135deg, #ffffff, #eefaf9);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
}
.ensemble-step .step-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; font-weight: 700; margin-bottom: 4px; }
.ensemble-step .step-state { font-size: 14px; font-weight: 700; }
.invariant-list {
  margin: 10px 0 0 0;
  padding-left: 18px;
  color: var(--text);
  font-size: 13px;
  line-height: 1.55;
}

/* Red flags */
.red-flag-item {
  padding: 12px;
  background: var(--red-bg);
  border-radius: 8px;
  margin-bottom: 8px;
  border-left: 3px solid var(--red);
}
.red-flag-item .rf-concept { font-weight: 600; font-size: 14px; }
.red-flag-item .rf-reason { font-size: 13px; color: var(--text-dim); margin-top: 4px; }
.severity-bar {
  width: 100%;
  height: 6px;
  background: var(--surface2);
  border-radius: 3px;
  margin-top: 8px;
  overflow: hidden;
}
.severity-bar-fill { height: 100%; border-radius: 3px; }
.gestalt-item {
  padding: 12px;
  background: var(--orange-bg);
  border-radius: 8px;
  margin-bottom: 8px;
  border-left: 3px solid var(--orange);
}
.conflict-item {
  padding: 12px;
  background: var(--yellow-bg);
  border-radius: 8px;
  margin-bottom: 8px;
  border-left: 3px solid var(--yellow);
}

/* JRI Gauge */
.gauge-container { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.gauge-svg { width: 160px; height: 100px; }
.gauge-breakdown { flex: 1; min-width: 200px; }
.breakdown-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; }
.breakdown-bar { flex: 1; height: 8px; background: var(--surface2); border-radius: 4px; overflow: hidden; }
.breakdown-fill { height: 100%; border-radius: 4px; }
.state-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  margin-top: 8px;
}
.state-ESCALATE { background: var(--red-bg); color: var(--red); }
.state-FAIL_CLOSED { background: var(--red-bg); color: var(--red); }
.state-ROUTE_CLINICIAN { background: var(--orange-bg); color: var(--orange); }
.state-NEED_OBJECTIVE_DATA { background: var(--yellow-bg); color: var(--yellow); }
.state-HOLD_AND_VERIFY { background: var(--yellow-bg); color: var(--yellow); }
.state-CLARIFY { background: var(--blue-bg); color: var(--blue); }
.state-ALLOW_WITH_AUDIT { background: var(--green-bg); color: var(--green); }
.state-READY { background: var(--green-bg); color: var(--green); }

/* Guardrails */
.assumption-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 8px; }
.assumption-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--surface2);
  border-radius: 6px;
  font-size: 13px;
}
.assumption-status {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.assumption-status.ok { background: var(--green); }
.assumption-status.weak { background: var(--yellow); }
.assumption-status.breached { background: var(--red); }
.assumption-name { font-weight: 500; min-width: 100px; }
.assumption-reason { color: var(--text-dim); font-size: 12px; }

/* Safety decision */
.decision-box {
  text-align: center;
  padding: 24px;
  border-radius: var(--radius);
  margin-bottom: 16px;
}
.decision-state { font-size: 28px; font-weight: 700; margin-bottom: 8px; }
.decision-driver { font-size: 14px; color: var(--text-dim); margin-bottom: 12px; }
.decision-action { font-size: 14px; padding: 12px; background: var(--surface2); border-radius: 8px; text-align: left; }

/* Questions */
.question-card {
  background: #f8fcfd;
  border: 1px solid rgba(207,226,234,0.8);
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 10px;
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.question-priority {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  min-width: 36px;
  text-align: center;
  padding-top: 2px;
}
.question-content { flex: 1; }
.question-text { font-size: 14px; font-weight: 500; margin-bottom: 4px; }
.question-meta { font-size: 12px; color: var(--text-dim); }

/* LLM section */
.llm-comparison { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 768px) { .llm-comparison { grid-template-columns: 1fr; } }
.llm-col { background: #f8fcfd; border: 1px solid rgba(207,226,234,0.8); border-radius: 8px; padding: 16px; }
.llm-col h4 { font-size: 13px; font-weight: 600; margin-bottom: 10px; }
.llm-finding-item { font-size: 13px; padding: 8px; background: var(--surface); border-radius: 6px; margin-bottom: 6px; border: 1px solid rgba(207,226,234,0.65); }
.llm-unavailable { text-align: center; padding: 32px; color: var(--text-dim); font-size: 14px; }

/* Screen 4: Governance */
.learning-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 768px) { .learning-grid { grid-template-columns: 1fr; } }
.learning-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}
.learning-panel h3 {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
.feedback-finding-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: #f8fcfd;
  border-radius: 6px;
  margin-bottom: 6px;
  font-size: 13px;
}
.feedback-finding-row .finding-text { flex: 1; }
.feedback-btns { display: flex; gap: 4px; }
.feedback-btns button {
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: #ffffff;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}
.feedback-btns button:hover { border-color: var(--accent); color: var(--text); }
.feedback-btns button.selected-confirmed { background: var(--green-bg); color: var(--green); border-color: var(--green); }
.feedback-btns button.selected-corrected { background: var(--yellow-bg); color: var(--yellow); border-color: var(--yellow); }
.feedback-btns button.selected-false_positive { background: var(--red-bg); color: var(--red); border-color: var(--red); }
.feedback-btns button.selected-missed { background: var(--purple-bg); color: var(--purple); border-color: var(--purple); }
.prior-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.prior-table th { text-align: left; padding: 6px 8px; color: var(--text-dim); font-weight: 500; border-bottom: 1px solid var(--border); }
.prior-table td { padding: 6px 8px; border-bottom: 1px solid var(--border); }
.suggestion-area {
  min-height: 120px;
  background: #f8fcfd;
  border-radius: 8px;
  padding: 14px;
  margin-top: 10px;
  font-size: 13px;
  white-space: pre-wrap;
  font-family: 'SF Mono', Menlo, monospace;
}
textarea.suggestion-edit {
  width: 100%;
  min-height: 120px;
  background: #f8fcfd;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  margin-top: 10px;
  font-size: 13px;
  color: var(--text);
  font-family: 'SF Mono', Menlo, monospace;
  resize: vertical;
}

/* Spinner */
.spinner {
  display: inline-block;
  width: 18px;
  height: 18px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Toast */
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: #ffffff;
  border: 1px solid var(--green);
  color: var(--green);
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 13px;
  box-shadow: var(--shadow);
  z-index: 200;
  opacity: 0;
  transform: translateY(10px);
  transition: all 0.3s;
}
.toast.show { opacity: 1; transform: translateY(0); }

/* Custom case builder */
.builder-form { display: flex; flex-direction: column; gap: 14px; }
.builder-form label { font-size: 13px; color: var(--text-dim); font-weight: 500; }
.builder-form input, .builder-form select {
  background: #f8fcfd;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
  color: var(--text);
  font-size: 14px;
  width: 100%;
}
.builder-form input:focus, .builder-form select:focus { outline: none; border-color: var(--accent); }
.builder-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.builder-stmt {
  background: #f8fcfd;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 8px;
}
.builder-stmt input { margin-top: 4px; }
.remove-stmt { color: var(--red); cursor: pointer; font-size: 12px; float: right; }
.remove-stmt:hover { text-decoration: underline; }

/* Duration badge */
.duration-badge {
  font-size: 12px;
  color: var(--text-dim);
  background: var(--accent-soft);
  padding: 3px 10px;
  border-radius: 12px;
  margin-left: 12px;
}

/* Empty states */
.empty-state { text-align: center; padding: 24px; color: var(--text-dim); font-size: 14px; }

/* Overview and boundary panels */
.ceo-hero { background: linear-gradient(135deg, #ffffff 0%, #e9fbf7 56%, #fff5d7 100%); border: 1px solid rgba(172,220,218,0.95); border-radius: var(--radius); padding: 24px; margin-bottom: 18px; box-shadow: var(--shadow); }
.ceo-claim { font-size: 22px; font-weight: 700; line-height: 1.35; margin-bottom: 10px; }
.ceo-subclaim { color: var(--text-dim); font-size: 14px; max-width: 860px; }
.ceo-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
.ceo-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
.ceo-panel { background: rgba(255,255,255,0.92); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; box-shadow: 0 10px 24px rgba(31,97,114,0.08); }
.ceo-panel h3 { font-size: 14px; margin-bottom: 8px; color: var(--accent); }
.ceo-panel p { font-size: 13px; color: var(--text-dim); }
.ceo-proof-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
  margin-top: 18px;
}
.ceo-proof {
  background: rgba(255,255,255,0.82);
  border: 1px solid rgba(15,159,154,0.22);
  border-radius: 8px;
  padding: 12px;
}
.ceo-proof strong {
  display: block;
  font-size: 13px;
  margin-bottom: 3px;
}
.ceo-proof span {
  color: var(--text-dim);
  font-size: 12px;
}
.demo-proof-callout {
  background: linear-gradient(135deg, #ecfdf5 0%, #eff6ff 100%);
  border: 1px solid rgba(17,132,91,0.28);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 14px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.demo-proof-callout .proof-title { font-weight: 800; font-size: 14px; }
.demo-proof-callout .proof-subtitle { color: var(--text-dim); font-size: 12px; }
.summary-panel {
  background: linear-gradient(135deg, #fff 0%, #f0fbf9 58%, #fff8e8 100%);
  border: 1px solid rgba(15,159,154,0.25);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 14px;
  box-shadow: 0 10px 24px rgba(31,97,114,0.08);
}
.summary-topline {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.summary-title { font-size: 17px; font-weight: 800; }
.summary-grid {
  display: grid;
  grid-template-columns: minmax(260px, 1.3fr) minmax(220px, .9fr);
  gap: 12px;
}
@media (max-width: 820px) { .summary-grid { grid-template-columns: 1fr; } }
.summary-panel ul { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.55; }
.summary-note {
  background: rgba(255,255,255,0.72);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  font-size: 13px;
  color: var(--text-dim);
  margin-bottom: 8px;
}
.boundary-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.boundary-table th { text-align: left; padding: 8px; color: var(--text-dim); border-bottom: 1px solid var(--border); }
.boundary-table td { padding: 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
.boundary-card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
.boundary-card {
  background: #f8fcfd;
  border: 1px solid rgba(207,226,234,0.85);
  border-radius: 8px;
  padding: 12px;
}
.boundary-card h4 { display:flex; justify-content:space-between; gap:8px; align-items:flex-start; font-size:13px; margin-bottom:8px; }
.boundary-card .boundary-block { margin-top:8px; }
.boundary-card .boundary-block strong { display:block; font-size:11px; color:var(--text-dim); text-transform:uppercase; margin-bottom:2px; }
.boundary-card .boundary-block span { font-size:13px; }
.boundary-status { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; white-space: nowrap; }
.boundary-status.supported { background: var(--green-bg); color: var(--green); }
.boundary-status.weak { background: var(--yellow-bg); color: var(--yellow); }
.boundary-status.unsafe_to_infer { background: var(--red-bg); color: var(--red); }
.unasked-list { margin-top: 12px; display: grid; gap: 8px; }
.unasked-item { background: #fbf8ff; border-left: 3px solid var(--purple); border-radius: 6px; padding: 10px; font-size: 12px; }
.action-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 768px) { .action-grid { grid-template-columns: 1fr; } }
.action-list { background: #f8fcfd; border: 1px solid rgba(207,226,234,0.8); border-radius: 8px; padding: 14px; }
.action-list h4 { font-size: 13px; margin-bottom: 8px; }
.action-list ul { padding-left: 18px; }
.action-list li { font-size: 13px; color: var(--text-dim); margin-bottom: 4px; }
.impact-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.impact-item { background: #fffdf7; border: 1px solid rgba(245,158,11,0.22); border-radius: 8px; padding: 12px; }
.impact-label { font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: var(--text-dim); font-weight: 700; margin-bottom: 6px; }
.impact-text { font-size: 13px; }
.mitigation-shell { display: grid; grid-template-columns: minmax(260px, .95fr) minmax(320px, 1.25fr); gap: 14px; }
@media (max-width: 900px) { .mitigation-shell { grid-template-columns: 1fr; } }
.mitigation-hero-card { background: linear-gradient(135deg, #f0fff9 0%, #fff7df 100%); border: 1px solid rgba(19,157,122,.28); border-radius: 8px; padding: 16px; }
.mitigation-title { font-size: 15px; font-weight: 800; color: #0f766e; margin-bottom: 6px; }
.mitigation-subtitle { font-size: 13px; color: var(--text-dim); line-height: 1.5; }
.trace-grid { display: grid; gap: 8px; margin-top: 12px; }
.trace-row { display: grid; grid-template-columns: 112px 1fr 78px; gap: 8px; align-items: start; background: rgba(255,255,255,.78); border: 1px solid rgba(172,220,218,.7); border-radius: 7px; padding: 8px; font-size: 12px; }
.trace-region { font-weight: 800; color: #0f766e; }
.trace-status { text-align: right; font-weight: 800; color: var(--orange); text-transform: uppercase; font-size: 10px; }
.memory-card { background: #fbf8ff; border: 1px solid rgba(124,58,237,.18); border-radius: 8px; padding: 14px; margin-bottom: 10px; }
.memory-card h4, .falsifier-card h4 { font-size: 13px; margin-bottom: 8px; color: var(--purple); }
.memory-chip { display: inline-block; background: #ffffff; border: 1px solid rgba(124,58,237,.18); border-radius: 999px; padding: 4px 9px; font-size: 12px; margin: 3px 4px 3px 0; }
.falsifier-card { background: #f8fcfd; border: 1px solid rgba(207,226,234,.9); border-radius: 8px; padding: 14px; }
.falsifier-item { border-left: 3px solid var(--accent); padding: 8px 10px; background: #ffffff; border-radius: 6px; margin-bottom: 8px; font-size: 12px; }
.signal-list { margin-top: 12px; display: grid; gap: 6px; }
.signal-pill { background: #ffffff; border: 1px solid rgba(207,226,234,.9); border-radius: 7px; padding: 8px; font-size: 12px; }
.signal-kind { font-weight: 800; color: var(--accent); margin-right: 6px; }
</style>
</head>
<body>

<div class="header">
  <h1>Clinical Safety <span>Interactive Demo</span></h1>
  <div class="header-nav">
    <button id="nav-overview" class="active" onclick="showScreen('overview')">Overview</button>
    <button id="nav-cases" onclick="showScreen('cases')">Cases</button>
    <button id="nav-encounter" onclick="showScreen('encounter')">Encounter</button>
    <button id="nav-analysis" onclick="showScreen('analysis')">Analysis</button>
    <button id="nav-learning" onclick="showScreen('learning')">Governance</button>
  </div>
</div>

<!-- Screen 0: Overview -->
<div id="screen-overview" class="screen active">
  <div class="ceo-hero">
    <div class="ceo-claim">Not an AI doctor. A learning autonomy-boundary layer around an AI doctor.</div>
    <div class="ceo-subclaim">This demo now shows the mitigation stack explicitly: deterministic controls today, plus stigmergic boundary traces and VAMS near-miss recall as the next governed learning layer.</div>
    <div class="ceo-proof-strip">
      <div class="ceo-proof"><strong>Curated rules</strong><span>Enforced: can route, ask, block, or cap autonomy.</span></div>
      <div class="ceo-proof"><strong>AI candidates</strong><span>Advisory: suggest signals but cannot decide alone.</span></div>
      <div class="ceo-proof"><strong>Memory / priors</strong><span>Bounded: tune questions and propose falsifiers.</span></div>
      <div class="ceo-proof"><strong>Ensemble governor</strong><span>Most restrictive state wins every time.</span></div>
    </div>
    <div class="ceo-actions">
      <button class="btn btn-primary" onclick="selectCaseById('CEO-001-stale-ace-refill-ckd-nsaid')">Run Hero Refill Case</button>
      <button class="btn btn-secondary" onclick="selectCaseById('RF-002-good-refill-readyish')">Compare Clean Refill</button>
      <button class="btn btn-secondary" onclick="selectCaseById('CEO-003-cost-fear-minimizes-alarm')">Show Cost-Fear Case</button>
      <button class="btn btn-secondary" onclick="showScreen('cases')">Full Case Library</button>
    </div>
  </div>
  <div class="ceo-grid">
    <div class="ceo-panel">
      <h3>What This Adds</h3>
      <p>Separates patient statements from clinical facts, then bounds what the AI is allowed to infer.</p>
    </div>
    <div class="ceo-panel">
      <h3>Why It Matters</h3>
      <p>At scale, subtle failures often come from silence, stale evidence, denial reliability, or patient-shaped conversations.</p>
    </div>
    <div class="ceo-panel">
      <h3>Business Value</h3>
      <p>One targeted clarification can preserve safe automation, reduce avoidable physician review, and explain paid routing more clearly.</p>
    </div>
    <div class="ceo-panel">
      <h3>New: Mitigation Memory</h3>
      <p>Every analyzed case now shows boundary traces, VAMS-style near-miss recall, falsifiers, governance promotion, and churn/routing mitigation.</p>
    </div>
  </div>
</div>

<!-- Screen 1: Case Selection -->
<div id="screen-cases" class="screen">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
    <div>
      <h2 style="font-size:20px;font-weight:600;">Select a Clinical Case</h2>
      <p style="font-size:13px;color:var(--text-dim);">Each case demonstrates a different safety detection capability.</p>
    </div>
  </div>
  <div id="case-grid-container"></div>
</div>

<!-- Screen 2: Encounter -->
<div id="screen-encounter" class="screen">
  <div id="encounter-banner" class="encounter-banner"></div>
  <div class="encounter-layout">
    <div>
      <div id="dialogue-area" class="dialogue-area"></div>
      <div class="btn-row">
        <button class="btn btn-secondary" onclick="showScreen('cases')">Back to Cases</button>
        <button id="analyze-btn" class="btn btn-primary" onclick="analyzeEncounter()">Analyze This Encounter</button>
      </div>
    </div>
    <div id="sidebar-narrative" class="sidebar-narrative"></div>
  </div>
</div>

<!-- Screen 3: Analysis -->
<div id="screen-analysis" class="screen">
  <div style="display:flex;align-items:center;margin-bottom:16px;">
    <h2 style="font-size:20px;font-weight:600;" id="analysis-title">Progressive Analysis</h2>
    <span id="analysis-duration" class="duration-badge"></span>
  </div>
  <div class="demo-proof-callout">
    <div>
      <div class="proof-title">Demo proof: processing transparency is now explicit.</div>
      <div class="proof-subtitle">Section 2 labels curated rules, AI candidates, learned priors, memory recall, and the ensemble autonomy governor.</div>
    </div>
    <span class="authority-chip authority-Enforced">Transparency layer active</span>
  </div>
  <div id="analysis-summary"></div>
  <div id="analysis-sections"></div>
  <div class="btn-row" id="analysis-actions" style="display:none;">
    <button class="btn btn-secondary" onclick="showScreen('encounter')">Edit Encounter</button>
    <button class="btn btn-primary" onclick="showScreen('learning')">Governance Review</button>
  </div>
</div>

<!-- Screen 4: Governance -->
<div id="screen-learning" class="screen">
  <h2 style="font-size:20px;font-weight:600;margin-bottom:16px;">Boundary Calibration / Governance Review</h2>
  <div class="learning-grid">
    <div class="learning-panel" id="feedback-panel">
      <h3>Clinician Review</h3>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px;">Mark findings as a demo of offline boundary calibration. Production behavior should change only through governed review.</p>
      <div id="feedback-findings-list"></div>
      <div class="btn-row" style="margin-top:12px;">
        <button class="btn btn-primary btn-sm" onclick="submitAllFeedback()">Submit Feedback</button>
      </div>
    </div>
    <div class="learning-panel" id="experience-panel">
      <h3>Experience Memory</h3>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px;">Current distortion priors for governance review and near-miss calibration.</p>
      <div id="experience-content"></div>
      <div class="btn-row">
        <button class="btn btn-secondary btn-sm" onclick="refreshExperience()">Refresh</button>
      </div>
    </div>
    <div class="learning-panel">
      <h3>Suggest New Rule</h3>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px;">LLM proposes detection patterns you can review and edit.</p>
      <button class="btn btn-secondary btn-sm" id="suggest-rule-btn" onclick="suggestRule()">Generate Rule Suggestions</button>
      <div id="rule-suggestion-area" class="suggestion-area" style="display:none;"></div>
    </div>
    <div class="learning-panel">
      <h3>Suggest New Case</h3>
      <p style="font-size:13px;color:var(--text-dim);margin-bottom:12px;">LLM generates a synthetic case that stress-tests a gap.</p>
      <div style="display:flex;gap:8px;margin-bottom:10px;">
        <select id="suggest-domain" style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:6px;color:var(--text);font-size:13px;flex:1;">
          <option value="chest_discomfort">Chest Discomfort</option>
          <option value="dyspnea_respiratory">Dyspnea/Respiratory</option>
          <option value="med_refill_hypertension">Med Refill/Hypertension</option>
          <option value="uti_symptoms">UTI Symptoms</option>
          <option value="rash">Rash</option>
          <option value="diabetes_hyperglycemia">Diabetes/Hyperglycemia</option>
          <option value="headache_migraine">Headache/Migraine</option>
        </select>
        <button class="btn btn-secondary btn-sm" id="suggest-case-btn" onclick="suggestCase()">Generate Case</button>
      </div>
      <input id="suggest-gap" placeholder="Optional: describe what gap to test..." style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);font-size:13px;width:100%;">
      <div id="case-suggestion-area" class="suggestion-area" style="display:none;"></div>
    </div>
  </div>
  <div class="btn-row">
    <button class="btn btn-secondary" onclick="showScreen('analysis')">Back to Analysis</button>
    <button class="btn btn-secondary" onclick="showScreen('cases')">New Case</button>
  </div>
</div>

<!-- Custom case builder modal -->
<div id="custom-builder" style="display:none;">
  <h3 style="font-size:16px;font-weight:600;margin-bottom:14px;">Build Custom Case</h3>
  <div class="builder-form">
    <div class="builder-row">
      <div>
        <label>Domain</label>
        <select id="builder-domain">
          <option value="chest_discomfort">Chest Discomfort</option>
          <option value="dyspnea_respiratory">Dyspnea/Respiratory</option>
          <option value="med_refill_hypertension">Med Refill/Hypertension</option>
          <option value="uti_symptoms">UTI Symptoms</option>
          <option value="rash">Rash</option>
          <option value="diabetes_hyperglycemia">Diabetes/Hyperglycemia</option>
          <option value="headache_migraine">Headache/Migraine</option>
        </select>
      </div>
      <div>
        <label>Patient Age</label>
        <input id="builder-age" type="number" value="50" min="0" max="150">
      </div>
    </div>
    <div>
      <label>Chief Concern</label>
      <input id="builder-concern" type="text" placeholder="e.g., chest pressure with exertion">
    </div>
    <div class="builder-row">
      <div>
        <label>Modality</label>
        <select id="builder-modality">
          <option value="text">Text</option>
          <option value="phone">Phone</option>
          <option value="video">Video</option>
          <option value="in_person">In Person</option>
        </select>
      </div>
      <div>
        <label>Known Conditions (comma-sep)</label>
        <input id="builder-conditions" type="text" placeholder="e.g., diabetes, hypertension">
      </div>
    </div>
    <div>
      <label>Statements</label>
      <div id="builder-stmts">
        <div class="builder-stmt" data-idx="0">
          <span class="remove-stmt" onclick="removeBuilderStmt(this)">remove</span>
          <label>Question</label>
          <input class="stmt-q" placeholder="e.g., Describe your chest discomfort">
          <label>Answer</label>
          <input class="stmt-a" placeholder="e.g., It feels like heartburn">
          <label>Source</label>
          <select class="stmt-src"><option value="patient">patient</option><option value="caregiver">caregiver</option><option value="device">device</option><option value="chart">chart</option><option value="clinician">clinician</option></select>
        </div>
      </div>
      <button class="btn btn-secondary btn-sm" style="margin-top:8px;" onclick="addBuilderStmt()">+ Add Statement</button>
    </div>
    <div class="btn-row">
      <button class="btn btn-secondary" onclick="cancelCustomBuilder()">Cancel</button>
      <button class="btn btn-primary" onclick="submitCustomCase()">Load Encounter</button>
    </div>
  </div>
</div>

<div id="toast" class="toast"></div>

<script>
// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let currentCase = null;       // The active case data (from /demo/cases)
let currentAnalysis = null;   // The analysis result (from /demo/analyze)
let feedbackSelections = {};  // { findingKey: assessment }

const API = '';  // Same origin

// ---------------------------------------------------------------------------
// Screen navigation
// ---------------------------------------------------------------------------
function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById('screen-' + name).classList.add('active');
  document.querySelectorAll('.header-nav button').forEach(b => b.classList.remove('active'));
  const nav = document.getElementById('nav-' + name);
  if (nav) nav.classList.add('active');
  window.scrollTo(0, 0);
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// ---------------------------------------------------------------------------
// Screen 1: Load cases
// ---------------------------------------------------------------------------
let allCases = [];  // Populated by loadCases, indexed by selectCaseByIndex

async function loadCases() {
  const resp = await fetch(API + '/demo/cases');
  const data = await resp.json();
  allCases = data.cases;
  const container = document.getElementById('case-grid-container');

  // Group by category_label, preserving original index
  const groups = {};
  for (let i = 0; i < allCases.length; i++) {
    const c = allCases[i];
    const g = c.category_label || 'Other';
    if (!groups[g]) groups[g] = [];
    groups[g].push({ idx: i, c: c });
  }

  let html = '';
  let firstGroup = true;
  for (const [group, entries] of Object.entries(groups)) {
    html += '<div class="category-header">' + esc(group) + ' (' + entries.length + ' cases)</div>';
    html += '<div class="case-grid">';
    for (const entry of entries) {
      const c = entry.c;
      html += '<div class="case-card" onclick="selectCaseByIndex(' + entry.idx + ')">';
      html += '<div class="card-title">' + esc(c.title) + '</div>';
      html += '<div class="card-scenario">' + esc(c.scenario) + '</div>';
      html += '<div class="card-badges">';
      html += '<span class="badge badge-domain">' + esc(c.domain.replace(/_/g, ' ')) + '</span>';
      html += '<span class="badge badge-age">' + c.age + 'y</span>';
      if (c.modality !== 'text') html += '<span class="badge badge-modality">' + esc(c.modality) + '</span>';
      html += '</div></div>';
    }
    if (firstGroup) {
      html += '<div class="custom-case-btn" onclick="openCustomBuilder()"><span class="plus">+</span><span>Build Custom Case</span></div>';
      firstGroup = false;
    }
    html += '</div>';
  }
  container.innerHTML = html;
}

function selectCaseByIndex(idx) {
  selectCase(allCases[idx]);
}

function selectCaseById(caseId) {
  const c = allCases.find(x => x.case_id === caseId);
  if (!c) {
    showToast('Case not loaded yet: ' + caseId);
    return;
  }
  selectCase(c);
}

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ---------------------------------------------------------------------------
// Screen 2: Select & render encounter
// ---------------------------------------------------------------------------
function selectCase(c) {
  try {
    currentCase = c;
    currentAnalysis = null;
    feedbackSelections = {};
    renderEncounter();
    showScreen('encounter');
  } catch(e) {
    console.error('selectCase error:', e);
    showToast('Error loading case: ' + e.message);
  }
}

function renderEncounter() {
  const c = currentCase;
  if (!c || !c.case_data) {
    console.error('renderEncounter: no case data', c);
    return;
  }
  const ctx = c.case_data.patient_context || {};
  const conditions = ctx.known_conditions || [];
  const stmts = c.case_data.statements || [];

  // Banner — patient context summary
  const banner = document.getElementById('encounter-banner');
  let bannerHtml = '';
  bannerHtml += '<div class="ctx-item"><span class="ctx-label">Age:</span><span class="ctx-value">' + (ctx.age || '?') + '</span></div>';
  bannerHtml += '<div class="ctx-item"><span class="ctx-label">Concern:</span><span class="ctx-value">' + esc(ctx.chief_concern || '') + '</span></div>';
  bannerHtml += '<div class="ctx-item"><span class="ctx-label">Domain:</span><span class="ctx-value">' + esc((ctx.domain || '').replace(/_/g, ' ')) + '</span></div>';
  bannerHtml += '<div class="ctx-item"><span class="ctx-label">Modality:</span><span class="ctx-value">' + esc(ctx.modality || '') + '</span></div>';
  if (conditions.length) {
    bannerHtml += '<div class="ctx-item"><span class="ctx-label">Conditions:</span><span class="ctx-value">' + esc(conditions.join(', ')) + '</span></div>';
  }
  if (ctx.language_barrier) {
    bannerHtml += '<div class="ctx-item"><span class="ctx-value" style="color:var(--orange)">Language Barrier</span></div>';
  }
  if (ctx.literacy_hint && ctx.literacy_hint !== 'average') {
    bannerHtml += '<div class="ctx-item"><span class="ctx-label">Literacy:</span><span class="ctx-value">' + esc(ctx.literacy_hint) + '</span></div>';
  }
  if (ctx.has_caregiver) {
    bannerHtml += '<div class="ctx-item"><span class="ctx-value" style="color:var(--blue)">Caregiver Present</span></div>';
  }
  banner.innerHTML = bannerHtml;

  // Dialogue — Q&A pairs, answers are editable
  let dHtml = '';
  for (let i = 0; i < stmts.length; i++) {
    const s = stmts[i];
    dHtml += '<div class="dialogue-pair">';
    dHtml += '<div class="dialogue-q">';
    dHtml += '<span class="q-number">' + (i + 1) + '.</span> ';
    dHtml += esc(s.question || '');
    if (s.concept) dHtml += ' <span class="concept-tag">' + esc(s.concept) + '</span>';
    dHtml += '</div>';
    dHtml += '<div class="dialogue-a" contenteditable="true" data-idx="' + i + '" data-source="' + esc(s.source || 'patient') + '">';
    dHtml += esc(s.answer || '');
    if (s.source && s.source !== 'patient') dHtml += ' <span class="source-tag">[' + esc(s.source) + ']</span>';
    dHtml += '</div>';
    dHtml += '</div>';
  }
  if (!stmts.length) {
    dHtml = '<div class="empty-state">No statements in this case.</div>';
  }
  document.getElementById('dialogue-area').innerHTML = dHtml;

  // Sidebar — narrative context
  const sidebar = document.getElementById('sidebar-narrative');
  let sideHtml = '';
  sideHtml += '<h3>' + esc(c.title || c.case_id || 'Case') + '</h3>';
  if (c.scenario) sideHtml += '<p class="scenario-text">' + esc(c.scenario) + '</p>';
  if (c.jre_demonstrates) {
    sideHtml += '<div class="insight-label">JRE Demonstrates</div><p>' + esc(c.jre_demonstrates) + '</p>';
  }
  if (c.bsg_demonstrates) {
    sideHtml += '<div class="insight-label">BSG Demonstrates</div><p>' + esc(c.bsg_demonstrates) + '</p>';
  }
  if (c.combined_insight) {
    sideHtml += '<div class="insight-label">Combined Insight</div><p>' + esc(c.combined_insight) + '</p>';
  }
  sidebar.innerHTML = sideHtml;
}

// ---------------------------------------------------------------------------
// Screen 3: Analyze encounter
// ---------------------------------------------------------------------------
async function analyzeEncounter() {
  const btn = document.getElementById('analyze-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Analyzing...';

  // Read potentially edited answers
  const stmts = currentCase.case_data.statements.map((s, i) => {
    const el = document.querySelector('.dialogue-a[data-idx="' + i + '"]');
    const text = el ? el.textContent.replace(/\\[.*?\\]$/, '').trim() : s.answer;
    return { question: s.question, answer: text, concept: s.concept, source: s.source, metadata: s.metadata || {} };
  });

  const payload = {
    case_id: currentCase.case_id,
    patient_context: currentCase.case_data.patient_context,
    statements: stmts,
    ground_truth: currentCase.case_data.ground_truth || {}
  };

  try {
    const resp = await fetch(API + '/demo/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    currentAnalysis = await resp.json();
    showScreen('analysis');
    renderAnalysis();
  } catch (e) {
    showToast('Analysis failed: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Analyze This Encounter';
  }
}

function renderAnalysis() {
  const a = currentAnalysis;
  document.getElementById('analysis-title').textContent = 'Progressive Analysis: ' + (currentCase.title || a.case_id);
  document.getElementById('analysis-duration').textContent = a.duration_ms.toFixed(0) + 'ms';
  document.getElementById('analysis-summary').innerHTML = renderDemoSummary(a.summary || {});

  const container = document.getElementById('analysis-sections');
  container.innerHTML = '';

  for (let i = 0; i < a.sections.length; i++) {
    const s = a.sections[i];
    const div = document.createElement('div');
    div.className = 'analysis-section';
    div.id = 'section-' + s.id;
    div.innerHTML =
      '<div class="section-header"><span class="section-number">' + (i+1) + '</span><span class="section-title">' + esc(s.title) + '</span></div>' +
      '<div class="section-subtitle">' + esc(s.subtitle) + '</div>' +
      '<div class="section-body" id="section-body-' + s.id + '"></div>';
    container.appendChild(div);

    // Progressive reveal
    setTimeout(() => {
      div.classList.add('revealed');
      renderSectionBody(s);
    }, 800 * i);
  }

  // Show actions after all revealed
  setTimeout(() => {
    document.getElementById('analysis-actions').style.display = 'flex';
    populateFeedbackPanel();
  }, 800 * a.sections.length + 200);
}

function renderSectionBody(section) {
  const el = document.getElementById('section-body-' + section.id);
  if (!el) return;

  switch (section.id) {
    case 'interpretation_boundaries': el.innerHTML = renderInterpretationBoundaries(section.data); break;
    case 'observations': el.innerHTML = renderObservations(section.data); break;
    case 'mud_map': el.innerHTML = renderMudMap(section.data); break;
    case 'red_flags': el.innerHTML = renderRedFlags(section.data); break;
    case 'jri_score': el.innerHTML = renderJRI(section.data); break;
    case 'guardrails': el.innerHTML = renderGuardrails(section.data); break;
    case 'safety_decision': el.innerHTML = renderSafetyDecision(section.data); break;
    case 'provenance_authority': el.innerHTML = renderProvenanceAuthority(section.data); break;
    case 'autonomy_boundary': el.innerHTML = renderAutonomyBoundary(section.data); break;
    case 'next_questions': el.innerHTML = renderQuestions(section.data); break;
    case 'mitigation_plan': el.innerHTML = renderMitigationPlan(section.data); break;
    case 'llm_opinion': renderLLMSection(section.data); break;
  }
}

// Section renderers
function renderDemoSummary(data) {
  if (!data.state) return '';
  let h = '<div class="summary-panel">';
  h += '<div class="summary-topline"><span class="state-badge state-' + esc(data.state) + '">' + esc(String(data.state).replace(/_/g, ' ')) + '</span><span class="summary-title">' + esc(data.case_title || 'Case summary') + '</span></div>';
  h += '<div class="summary-grid"><div>';
  h += '<div style="font-size:13px;font-weight:800;margin-bottom:6px;">Why this disposition was chosen</div><ul>';
  for (const item of (data.why || [])) h += '<li>' + esc(item) + '</li>';
  h += '</ul></div><div>';
  h += '<div class="summary-note"><strong>Authority:</strong><br>' + esc(data.authority || '') + '</div>';
  h += '<div class="summary-note"><strong>AI role:</strong><br>' + esc(data.ai_role || '') + '</div>';
  h += '<div class="summary-note"><strong>Autonomy:</strong><br>' + esc(data.autonomy || '') + '</div>';
  h += '</div></div>';
  h += '<div style="font-size:13px;color:var(--text-dim);margin-top:10px;">' + esc(data.patient_pattern || '') + '</div>';
  h += '</div>';
  return h;
}

function authorityChip(label) {
  const cls = String(label || 'Evidence').split(' ')[0].replace(/[^A-Za-z]/g, '') || 'Evidence';
  return '<span class="authority-chip authority-' + cls + '">' + esc(label || 'Evidence Candidate') + '</span>';
}

function renderInterpretationBoundaries(data) {
  const rows = data.rows || [];
  let h = '<div class="boundary-card-grid">';
  for (const r of rows) {
    h += '<div class="boundary-card">';
    h += '<h4><span>' + esc(r.concept_label || r.concept) + '</span><span class="boundary-status ' + esc(r.boundary_status) + '">' + esc(r.boundary_label) + '</span></h4>';
    h += '<div style="font-size:12px;color:var(--text-dim);margin-bottom:6px;">' + esc(r.source) + ' / confidence ' + Number(r.confidence).toFixed(2) + '</div>';
    h += '<div class="boundary-block"><strong>Patient said</strong><span>' + esc(r.patient_statement) + '</span></div>';
    h += '<div class="boundary-block"><strong>Safe interpretation</strong><span>' + esc(r.safe_interpretation) + '</span></div>';
    h += '<div class="boundary-block"><strong>Unsafe inference</strong><span>' + (r.unsafe_inference ? esc(r.unsafe_inference) : 'No major unsafe inference flagged.') + '</span></div>';
    h += '<div class="boundary-block"><strong>Close the boundary</strong><span>' + esc(r.missing_followup) + '</span></div>';
    h += '</div>';
  }
  h += '</div>';
  if ((data.unasked || []).length) {
    h += '<div class="unasked-list">';
    h += '<div style="font-size:13px;font-weight:700;">Unasked is not denied</div>';
    for (const u of data.unasked) {
      h += '<div class="unasked-item"><strong>' + esc(u.category.replace(/_/g, ' ')) + '</strong>: ' + esc(u.concept_label || u.item) + '<br><span style="color:var(--text-dim)">' + esc(u.detail || u.unsafe_inference) + '</span></div>';
    }
    h += '</div>';
  }
  return h;
}

function renderObservations(data) {
  if (!data.observations.length) return '<div class="empty-state">No observations extracted.</div>';
  let h = '<table class="obs-table"><thead><tr><th>Concept</th><th>Raw Answer</th><th>Normalized</th><th>Confidence</th><th>Source</th><th>Traps</th></tr></thead><tbody>';
  for (const o of data.observations) {
    const low = o.confidence < 0.55;
    h += '<tr class="' + (low ? 'low-confidence' : '') + '">';
    h += '<td><strong>' + esc(o.concept_label || o.concept) + '</strong></td>';
    h += '<td>' + esc(String(o.raw).substring(0, 80)) + '</td>';
    h += '<td>' + esc(String(o.normalized)) + '</td>';
    h += '<td><div class="confidence-bar"><div class="confidence-bar-fill" style="width:' + (o.confidence*100) + '%;background:' + (low ? 'var(--red)' : o.confidence < 0.75 ? 'var(--yellow)' : 'var(--green)') + '"></div></div>' + o.confidence.toFixed(2) + '</td>';
    h += '<td>' + esc(o.source) + '</td>';
    h += '<td>';
    if (o.learned_prior_applied) h += authorityChip(o.authority) + ' ';
    for (const te of (o.trap_explanations || [])) {
      h += '<span class="trap-tag" title="' + esc(te.explanation) + '">' + esc(te.trap) + '</span> ';
    }
    h += '</td></tr>';
  }
  h += '</tbody></table>';
  return h;
}

function renderMudMap(data) {
  const cats = data.findings_by_category;
  const labels = {missing:'Missing',uncertain:'Uncertain',distorted:'Distorted',contradictory:'Contradictory',unknowable_remote:'Remote Unknowable',objective_needed:'Objective Needed'};
  const colors = {missing:'var(--orange)',uncertain:'var(--yellow)',distorted:'var(--red)',contradictory:'var(--purple)',unknowable_remote:'var(--text-dim)',objective_needed:'var(--blue)'};
  let h = '<div class="mud-grid">';
  for (const [cat, label] of Object.entries(labels)) {
    const items = cats[cat] || [];
    h += '<div class="mud-cell ' + (items.length ? 'has-items' : '') + '">';
    h += '<div class="mud-label">' + label + '</div>';
    h += '<div class="mud-count" style="color:' + (items.length ? colors[cat] : 'var(--text-dim)') + '">' + items.length + '</div>';
    for (const f of items.slice(0, 3)) {
      h += '<div class="mud-finding">' + esc(f.display_name || f.concept) + ' ' + authorityChip(f.authority) + '<br>' + esc(f.reason.substring(0, 60)) + '</div>';
    }
    if (items.length > 3) h += '<div class="mud-finding">... +' + (items.length - 3) + ' more</div>';
    h += '</div>';
  }
  h += '</div>';
  return h;
}

function renderRedFlags(data) {
  let h = '';
  if (!data.red_flags.length && !data.gestalts.length && !data.source_conflicts.length) {
    return '<div class="empty-state">No red flags, gestalt patterns, or source conflicts detected.</div>';
  }
  for (const rf of data.red_flags) {
    const sev = rf.severity;
    h += '<div class="red-flag-item">';
    h += '<div class="rf-concept">' + esc(rf.display_name || rf.concept) + ' ' + authorityChip(rf.authority) + ' <span style="font-size:12px;color:var(--text-dim);">severity ' + sev.toFixed(2) + '</span></div>';
    h += '<div class="rf-reason">' + esc(rf.reason) + '</div>';
    h += '<div class="severity-bar"><div class="severity-bar-fill" style="width:' + (sev*100) + '%;background:' + (sev >= 0.85 ? 'var(--red)' : sev >= 0.6 ? 'var(--orange)' : 'var(--yellow)') + '"></div></div>';
    h += '</div>';
  }
  for (const g of data.gestalts) {
    h += '<div class="gestalt-item"><strong>' + esc(g.pattern) + '</strong> ' + authorityChip(g.authority) + '<br><span style="font-size:13px;color:var(--text-dim);">' + esc(g.description) + '</span><br><span style="font-size:12px;">' + esc(g.evidence) + '</span></div>';
  }
  for (const sc of data.source_conflicts) {
    h += '<div class="conflict-item"><strong>' + esc(sc.description) + '</strong> ' + authorityChip(sc.authority) + '<br><span style="font-size:12px;color:var(--text-dim);">' + esc(sc.evidence) + '</span></div>';
  }
  return h;
}

function renderJRI(data) {
  const jri = data.readiness_index;
  const pct = Math.min(jri, 100);
  const angle = -90 + (pct / 100) * 180;
  const color = jri >= 78 ? 'var(--green)' : jri >= 50 ? 'var(--yellow)' : 'var(--red)';

  let h = '<div class="gauge-container">';
  // SVG gauge
  h += '<svg class="gauge-svg" viewBox="0 0 160 100">';
  h += '<path d="M 15 90 A 65 65 0 0 1 145 90" fill="none" stroke="var(--surface2)" stroke-width="12" stroke-linecap="round"/>';
  const endAngle = (-180 + (pct / 100) * 180) * Math.PI / 180;
  const ex = 80 + 65 * Math.cos(endAngle);
  const ey = 90 + 65 * Math.sin(endAngle);
  const largeArc = pct > 50 ? 1 : 0;
  h += '<path d="M 15 90 A 65 65 0 ' + largeArc + ' 1 ' + ex.toFixed(1) + ' ' + ey.toFixed(1) + '" fill="none" stroke="' + color + '" stroke-width="12" stroke-linecap="round"/>';
  h += '<text x="80" y="80" text-anchor="middle" font-size="28" font-weight="700" fill="' + color + '">' + jri.toFixed(0) + '</text>';
  h += '<text x="80" y="95" text-anchor="middle" font-size="10" fill="var(--text-dim)">JRI</text>';
  h += '</svg>';

  // Breakdown bars
  h += '<div class="gauge-breakdown">';
  const bars = [
    ['Completeness', data.completeness, 'var(--blue)'],
    ['Reliability', data.reliability, 'var(--green)'],
    ['Objective Coverage', data.objective_coverage, 'var(--orange)'],
    ['Contradiction Load', data.contradiction_load, 'var(--purple)'],
    ['Distortion Load', data.distortion_load, 'var(--red)'],
    ['Red Flag Load', data.red_flag_load, 'var(--red)'],
  ];
  for (const [label, val, clr] of bars) {
    h += '<div class="breakdown-row"><span style="min-width:130px;">' + label + '</span><div class="breakdown-bar"><div class="breakdown-fill" style="width:' + (val*100) + '%;background:' + clr + '"></div></div><span style="min-width:40px;text-align:right;">' + val.toFixed(2) + '</span></div>';
  }
  h += '<div><span class="state-badge state-' + data.jre_state + '">' + data.jre_state + '</span></div>';
  h += '<div style="font-size:13px;color:var(--text-dim);margin-top:4px;">' + esc(data.state_reason) + '</div>';
  h += '</div></div>';
  return h;
}

function renderGuardrails(data) {
  let h = '';
  // Assumption register
  h += '<div style="margin-bottom:16px;"><strong style="font-size:13px;">Assumption Register</strong></div>';
  h += '<div class="assumption-grid">';
  for (const a of data.assumption_register) {
    h += '<div class="assumption-row"><span class="assumption-status ' + a.status + '"></span><span class="assumption-name">' + esc(a.name) + '</span><span class="assumption-reason">' + esc(a.reason) + '</span></div>';
  }
  h += '</div>';

  // Findings
  if (data.findings.length) {
    h += '<div style="margin-top:16px;margin-bottom:8px;"><strong style="font-size:13px;">Guardrail Findings</strong></div>';
    for (const f of data.findings) {
      h += '<div class="red-flag-item" style="border-left-color:var(--orange);background:var(--orange-bg);">';
      h += '<div class="rf-concept">' + esc(f.rule_id) + ' ' + authorityChip(f.authority) + ' <span class="state-badge state-' + f.action + '" style="font-size:11px;">' + f.action + '</span></div>';
      h += '<div class="rf-reason">' + esc(f.reason) + '</div>';
      if (f.evidence) h += '<div style="font-size:12px;color:var(--text-dim);margin-top:4px;">' + esc(f.evidence.substring(0, 120)) + '</div>';
      h += '</div>';
    }
  }

  // Tier
  h += '<div style="margin-top:16px;display:flex;align-items:center;gap:12px;">';
  h += '<span class="state-badge state-' + data.guardrail_state + '">' + data.guardrail_state + '</span>';
  h += '<span style="font-size:13px;">Autonomy: <strong>' + esc(data.max_autonomy_tier) + '</strong></span>';
  h += '</div>';
  if (data.autonomy_description) {
    h += '<div style="font-size:12px;color:var(--text-dim);margin-top:4px;">' + esc(data.autonomy_description) + '</div>';
  }
  h += '<div style="margin-top:8px;font-size:12px;color:var(--text-dim);">Novelty: ' + data.novelty_score.toFixed(2) + ' | Risk Budget: ' + data.residual_risk_budget.toFixed(2) + '</div>';
  return h;
}

function renderSafetyDecision(data) {
  const stateColors = {
    ESCALATE:'var(--red-bg)', FAIL_CLOSED:'var(--red-bg)',
    ROUTE_CLINICIAN:'var(--orange-bg)', NEED_OBJECTIVE_DATA:'var(--yellow-bg)',
    HOLD_AND_VERIFY:'var(--yellow-bg)', CLARIFY:'var(--blue-bg)',
    ALLOW_WITH_AUDIT:'var(--green-bg)', READY:'var(--green-bg)'
  };
  let h = '<div class="decision-box" style="background:' + (stateColors[data.combined_state] || 'var(--surface2)') + '">';
  h += '<div class="decision-state state-' + data.combined_state + '" style="font-size:32px;">' + data.combined_state.replace(/_/g, ' ') + '</div>';
  h += '<div class="decision-driver">' + esc(data.decision_driver) + '</div>';
  h += '<div style="display:flex;gap:8px;justify-content:center;margin-bottom:12px;">';
  h += '<span class="state-badge state-' + data.jre_state + '">JRE: ' + data.jre_state + '</span>';
  h += '<span class="state-badge state-' + data.bsg_state + '">BSG: ' + data.bsg_state + '</span>';
  h += '</div>';
  h += '</div>';
  h += '<div class="decision-action"><strong>Next Action:</strong> ' + esc(data.next_action) + '</div>';
  h += '<div style="margin-top:8px;font-size:13px;color:var(--text-dim);">Autonomy Tier: <strong>' + esc(data.autonomy_tier) + '</strong> — ' + esc(data.autonomy_description) + '</div>';
  return h;
}

function renderProvenanceAuthority(data) {
  let h = '<div class="provenance-grid">';
  for (const layer of data.layers || []) {
    h += '<div class="provenance-card">';
    h += '<h4><span>' + esc(layer.name) + '</span>' + authorityChip(layer.authority) + '</h4>';
    h += '<div class="provenance-effect">' + esc(layer.effect) + '</div>';
    h += '<div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">Signals: <strong>' + esc(String(layer.count)) + '</strong></div>';
    h += '<div class="provenance-examples">';
    for (const ex of (layer.examples || []).slice(0, 5)) h += '<span class="provenance-token">' + esc(ex) + '</span>';
    if (!(layer.examples || []).length) h += '<span class="provenance-token">none in this case</span>';
    h += '</div></div>';
  }
  h += '</div>';

  h += '<div class="ensemble-strip">';
  for (const e of data.ensemble || []) {
    h += '<div class="ensemble-step"><div class="step-label">' + esc(e.layer) + '</div><div class="step-state">' + esc(e.state) + '</div><div style="font-size:12px;color:var(--text-dim);margin-top:4px;">' + esc(e.authority) + '</div></div>';
  }
  h += '</div>';

  if ((data.finding_rows || []).length) {
    h += '<details style="margin-top:12px;"><summary style="cursor:pointer;font-size:13px;font-weight:800;">Technical trace</summary>';
    h += '<table class="authority-table"><thead><tr><th>Source</th><th>Signal</th><th>Authority</th><th>Evidence</th><th>Effect</th></tr></thead><tbody>';
    for (const r of data.finding_rows || []) {
      h += '<tr>';
      h += '<td>' + esc(r.source) + '<br><span style="color:var(--text-dim)">' + esc(r.rule_id) + '</span></td>';
      h += '<td><strong>' + esc(r.display_name || r.name) + '</strong><br><span style="color:var(--text-dim)">' + esc(r.layer) + '</span></td>';
      h += '<td>' + authorityChip(r.authority) + '</td>';
      h += '<td>' + esc(String(r.evidence || '').substring(0, 140)) + '</td>';
      h += '<td>' + esc(r.effect) + '</td>';
      h += '</tr>';
    }
    h += '</tbody></table></details>';
  }

  h += '<ul class="invariant-list">';
  for (const inv of data.invariants || []) h += '<li>' + esc(inv) + '</li>';
  h += '</ul>';
  h += '<div style="font-size:12px;color:var(--text-dim);margin-top:10px;">Async LLM available: <strong>' + (data.llm_available ? 'yes' : 'no') + '</strong>. Domain: <strong>' + esc(data.case_domain) + '</strong>.</div>';
  return h;
}

function renderAutonomyBoundary(data) {
  let h = '<div style="margin-bottom:12px;"><span class="state-badge state-' + data.current_state + '">' + esc(data.current_state) + '</span> <span style="font-size:13px;margin-left:8px;">Autonomy cap: <strong>' + esc(data.current_cap) + '</strong></span></div>';
  h += '<div class="action-grid">';
  h += '<div class="action-list"><h4 style="color:var(--green)">Allowed</h4><ul>';
  for (const a of data.allowed_actions || []) h += '<li>' + esc(a) + '</li>';
  h += '</ul></div>';
  h += '<div class="action-list"><h4 style="color:var(--red)">Blocked</h4><ul>';
  for (const b of data.blocked_actions || []) h += '<li>' + esc(b) + '</li>';
  if (!(data.blocked_actions || []).length) h += '<li>No pathway action blocked beyond normal audit.</li>';
  h += '</ul></div></div>';
  h += '<div class="action-grid" style="margin-top:14px;">';
  h += '<div class="action-list"><h4>Why blocked or capped</h4><ul>';
  for (const r of data.why_blocked || []) h += '<li>' + esc(r) + '</li>';
  h += '</ul></div>';
  h += '<div class="action-list"><h4>What restores readiness</h4><ul>';
  for (const r of data.what_restores_readiness || []) h += '<li>' + esc(r) + '</li>';
  h += '</ul></div></div>';
  h += '<div class="decision-action" style="margin-top:14px;"><strong>Business effect:</strong> ' + esc(data.business_effect) + '</div>';
  return h;
}

function renderQuestions(data) {
  if (!data.questions.length) return '<div class="empty-state">No follow-up questions needed.</div>';
  let h = '<div style="font-size:12px;color:var(--text-dim);margin-bottom:10px;">Modality: <strong>' + esc(data.modality) + '</strong>' + (data.modality_prefix ? ' — ' + esc(data.modality_prefix) : '') + '</div>';
  for (const q of data.questions) {
    h += '<div class="question-card">';
    h += '<div class="question-priority">' + (data.mode === 'escalation' ? 'NOW' : '#' + q.priority.toFixed(0)) + '</div>';
    h += '<div class="question-content">';
    h += '<div class="question-text">' + esc(q.question) + '</div>';
    h += '<div class="question-meta">' + esc(q.clear_step) + ' | ' + esc(q.concept_label || q.concept) + (data.mode === 'escalation' ? '' : ' | Gain: ' + q.expected_gain.toFixed(2)) + '</div>';
    h += '</div></div>';
  }
  return h;
}

function renderMitigationPlan(data) {
  let h = '<div class="mitigation-shell">';
  h += '<div>';
  h += '<div class="mitigation-hero-card">';
  h += '<div><span class="state-badge state-' + data.combined_state + '">' + esc(data.combined_state) + '</span></div>';
  h += '<div class="mitigation-title">Stigmergic Boundary Trace</div>';
  h += '<div class="mitigation-subtitle">This case deposits traces into separate regions so stale data, weak denials, source conflict, social pressure, and outcome feedback do not vanish after one turn.</div>';
  h += '<div class="trace-grid">';
  for (const t of data.trace_regions || []) {
    h += '<div class="trace-row"><div class="trace-region">' + esc(t.region) + '</div><div>' + esc(t.signal) + '<br><span style="color:var(--text-dim)">Decay: ' + esc(t.decay) + '</span></div><div class="trace-status">' + esc(t.status) + '</div></div>';
  }
  h += '</div></div>';
  if ((data.top_current_signals || []).length) {
    h += '<div class="signal-list">';
    for (const s of (data.top_current_signals || []).slice(0, 5)) {
      h += '<div class="signal-pill"><span class="signal-kind">' + esc(s.kind) + '</span><strong>' + esc(s.name) + '</strong><br><span style="color:var(--text-dim)">' + esc(String(s.reason).substring(0, 120)) + '</span></div>';
    }
    h += '</div>';
  }
  h += '</div><div>';
  h += '<div class="memory-card"><h4>VAMS Near-Miss Recall</h4>';
  h += '<div style="font-size:13px;margin-bottom:8px;">' + esc(data.recalled_pattern) + '</div>';
  h += '<div style="font-size:12px;color:var(--text-dim);margin-bottom:6px;">Pattern completion suggests checking:</div>';
  for (const p of data.pattern_completion || []) h += '<span class="memory-chip">' + esc(p) + '</span>';
  h += '</div>';
  h += '<div class="falsifier-card"><h4>What Would Change The Decision?</h4>';
  for (const f of data.falsifiers || []) {
    h += '<div class="falsifier-item"><strong>' + esc(f.target) + '</strong><br>' + esc(f.test) + '<br><span style="color:var(--text-dim)">' + esc(f.why) + '</span></div>';
  }
  h += '</div></div></div>';
  h += '<div style="margin-top:14px;" class="impact-grid">';
  for (const m of data.mitigations || []) {
    h += '<div class="impact-item">';
    h += '<div class="impact-label">' + esc(m.layer) + '</div>';
    h += '<div class="impact-text" style="margin-bottom:8px;">' + esc(m.purpose) + '</div>';
    h += '<ul style="margin:0;padding-left:18px;color:var(--text);font-size:13px;line-height:1.55;">';
    for (const a of m.actions || []) h += '<li>' + esc(a) + '</li>';
    h += '</ul></div>';
  }
  h += '</div>';
  return h;
}

async function renderLLMSection(data) {
  // Immediately show regex findings
  const el = document.getElementById('section-body-llm_opinion');
  if (!el) return;

  // Show regex side immediately, LLM side loading
  let h = '<div class="llm-comparison">';
  h += '<div class="llm-col"><h4>Governed Safety Findings (' + data.regex_findings.length + ')</h4>';
  for (const f of data.regex_findings) {
    h += '<div class="llm-finding-item"><strong>' + esc(f.concept) + '</strong> (' + f.severity.toFixed(2) + ')<br><span style="color:var(--text-dim)">' + esc(f.reason.substring(0, 100)) + '</span></div>';
  }
  if (!data.regex_findings.length) h += '<div class="empty-state">No governed findings.</div>';
  h += '</div>';
  h += '<div class="llm-col" id="llm-results-col"><h4>Extractor Candidate Signals</h4>';
  if (data.llm_available) {
    h += '<div style="text-align:center;padding:20px;"><span class="spinner"></span> Fetching LLM analysis...</div>';
  } else {
    h += '<div class="llm-unavailable">LLM not available — set OPENROUTER_API_KEY to enable.</div>';
  }
  h += '</div></div>';
  el.innerHTML = h;

  // Fetch LLM results asynchronously if available
  if (data.llm_available && currentCase) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 90000);
      const resp = await fetch(API + '/demo/llm-analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify(buildLLMPayloadFromCurrentCase())
      });
      clearTimeout(timeoutId);
      const llmData = await resp.json();
      const col = document.getElementById('llm-results-col');
      if (col) {
        let lh = '<h4>LLM Analysis (' + (llmData.llm_findings || []).length + ' findings)</h4>';
        if (llmData.model) lh += '<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">Model: ' + esc(llmData.model) + '</div>';
        if (llmData.llm_error) {
          lh += '<div class="llm-unavailable">LLM error: ' + esc(llmData.llm_error) + '</div>';
        } else {
          for (const f of (llmData.llm_findings || [])) {
            lh += '<div class="llm-finding-item"><strong>' + esc(f.concept) + '</strong> (' + f.severity.toFixed(2) + ', conf ' + f.confidence.toFixed(2) + ')<br><span style="color:var(--text-dim)">' + esc(f.reason.substring(0, 100)) + '</span></div>';
          }
          if (!(llmData.llm_findings || []).length) {
            lh += '<div class="empty-state">' + esc(llmData.llm_note || 'LLM ran but returned no additional candidate signals.') + '</div>';
            if (llmData.raw_preview) lh += '<details style="font-size:12px;color:var(--text-dim);margin-top:8px;"><summary>Raw LLM response preview</summary><pre style="white-space:pre-wrap;">' + esc(llmData.raw_preview) + '</pre></details>';
          }
        }
        col.innerHTML = lh;
      }
    } catch (e) {
      const col = document.getElementById('llm-results-col');
      if (col) col.innerHTML = renderLLMTimeout(e);
    }
  }
}

function buildLLMPayloadFromCurrentCase() {
  const stmts = currentCase.case_data.statements.map((s, i) => {
    const ansEl = document.querySelector('.dialogue-a[data-idx="' + i + '"]');
    const text = ansEl ? ansEl.textContent.replace(/\\[.*?\\]$/, '').trim() : s.answer;
    return { question: s.question, answer: text, concept: s.concept, source: s.source, metadata: s.metadata || {} };
  });
  return {
    case_id: currentCase.case_id,
    patient_context: currentCase.case_data.patient_context,
    statements: stmts,
  };
}

function renderLLMTimeout(e) {
  const isAbort = e && e.name === 'AbortError';
  const message = isAbort
    ? 'External model exceeded the demo response window. Governed safety findings remain authoritative; retry when the network/model is responsive.'
    : 'External model call did not complete: ' + (e ? (e.message || e.name || String(e)) : 'unknown error');
  return '<h4>LLM Analysis</h4><div class="llm-unavailable">' + esc(message) + '<br><button class="btn btn-secondary btn-sm" style="margin-top:10px;" onclick="retryLLMAnalysis()">Retry LLM</button></div>';
}

async function retryLLMAnalysis() {
  if (!currentCase) return;
  const col = document.getElementById('llm-results-col');
  if (!col) return;
  col.innerHTML = '<h4>Extractor Candidate Signals</h4><div style="text-align:center;padding:20px;"><span class="spinner"></span> Retrying external model...</div>';
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 90000);
    const resp = await fetch(API + '/demo/llm-analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify(buildLLMPayloadFromCurrentCase())
    });
    clearTimeout(timeoutId);
    const llmData = await resp.json();
    let lh = '<h4>LLM Analysis (' + (llmData.llm_findings || []).length + ' findings)</h4>';
    if (llmData.model) lh += '<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">Model: ' + esc(llmData.model) + '</div>';
    if (llmData.llm_error) {
      lh += '<div class="llm-unavailable">LLM error: ' + esc(llmData.llm_error) + '</div>';
    } else {
      for (const f of (llmData.llm_findings || [])) {
        lh += '<div class="llm-finding-item"><strong>' + esc(f.concept) + '</strong> (' + f.severity.toFixed(2) + ', conf ' + f.confidence.toFixed(2) + ')<br><span style="color:var(--text-dim)">' + esc(f.reason.substring(0, 100)) + '</span></div>';
      }
      if (!(llmData.llm_findings || []).length) lh += '<div class="empty-state">' + esc(llmData.llm_note || 'LLM ran but returned no additional candidate signals.') + '</div>';
    }
    col.innerHTML = lh;
  } catch (e) {
    col.innerHTML = renderLLMTimeout(e);
  }
}

function renderLLM(data) {
  if (!data.llm_available) {
    return '<div class="llm-unavailable">LLM not available — set OPENROUTER_API_KEY to enable.<br>Showing governed findings below.</div>' + renderLLMRegexOnly(data);
  }
  if (data.llm_error) {
    return '<div class="llm-unavailable">LLM error: ' + esc(data.llm_error) + '</div>' + renderLLMRegexOnly(data);
  }
  let h = '<div class="llm-comparison">';
  h += '<div class="llm-col"><h4>Governed Safety Findings (' + data.regex_findings.length + ' findings)</h4>';
  for (const f of data.regex_findings) {
    h += '<div class="llm-finding-item"><strong>' + esc(f.concept) + '</strong> (' + f.severity.toFixed(2) + ')<br><span style="color:var(--text-dim)">' + esc(f.reason.substring(0, 100)) + '</span></div>';
  }
  if (!data.regex_findings.length) h += '<div class="empty-state">No governed findings.</div>';
  h += '</div>';

  h += '<div class="llm-col"><h4>LLM Analysis (' + data.llm_findings.length + ' findings)</h4>';
  for (const f of data.llm_findings) {
    h += '<div class="llm-finding-item"><strong>' + esc(f.concept) + '</strong> (' + f.severity.toFixed(2) + ', conf ' + f.confidence.toFixed(2) + ')<br><span style="color:var(--text-dim)">' + esc(f.reason.substring(0, 100)) + '</span></div>';
  }
  if (!data.llm_findings.length) h += '<div class="empty-state">No LLM findings.</div>';
  h += '</div></div>';

  // Unique concepts
  if (data.llm_unique_concepts.length || data.regex_unique_concepts.length) {
    h += '<div style="margin-top:12px;font-size:13px;">';
    if (data.llm_unique_concepts.length) h += '<div style="margin-bottom:4px;"><strong style="color:var(--purple);">LLM caught uniquely:</strong> ' + data.llm_unique_concepts.map(esc).join(', ') + '</div>';
    if (data.regex_unique_concepts.length) h += '<div style="margin-bottom:4px;"><strong style="color:var(--blue);">Governed layer caught uniquely:</strong> ' + data.regex_unique_concepts.map(esc).join(', ') + '</div>';
    if (data.overlap_concepts.length) h += '<div><strong style="color:var(--green);">Both caught:</strong> ' + data.overlap_concepts.map(esc).join(', ') + '</div>';
    h += '</div>';
  }
  return h;
}

function renderLLMRegexOnly(data) {
  if (!data.regex_findings.length) return '';
  let h = '<div style="margin-top:12px;"><strong style="font-size:13px;">Governed Safety Findings</strong></div>';
  for (const f of data.regex_findings) {
    h += '<div class="llm-finding-item" style="margin-top:6px;"><strong>' + esc(f.concept) + '</strong> (' + f.severity.toFixed(2) + ')<br><span style="color:var(--text-dim)">' + esc(f.reason.substring(0, 100)) + '</span></div>';
  }
  return h;
}

// ---------------------------------------------------------------------------
// Screen 4: Governance
// ---------------------------------------------------------------------------
function populateFeedbackPanel() {
  if (!currentAnalysis) return;
  const container = document.getElementById('feedback-findings-list');
  let h = '';
  const allFindings = [];

  // Collect findings from analysis sections
  for (const s of currentAnalysis.sections) {
    if (s.id === 'red_flags') {
      for (const rf of (s.data.red_flags || [])) {
        allFindings.push({ key: 'rf_' + rf.concept, concept: rf.concept, reason: rf.reason, category: 'red_flag' });
      }
    }
    if (s.id === 'mud_map') {
      for (const [cat, items] of Object.entries(s.data.findings_by_category || {})) {
        for (const f of items) {
          allFindings.push({ key: cat + '_' + f.concept, concept: f.concept, reason: f.reason, category: cat });
        }
      }
    }
    if (s.id === 'guardrails') {
      for (const f of (s.data.findings || [])) {
        allFindings.push({ key: 'bsg_' + f.rule_id, concept: f.rule_id, reason: f.reason, category: f.category });
      }
    }
  }

  if (!allFindings.length) {
    container.innerHTML = '<div class="empty-state">No findings to review.</div>';
    return;
  }

  for (const f of allFindings) {
    h += '<div class="feedback-finding-row">';
    h += '<div class="finding-text"><strong>' + esc(f.concept) + '</strong> <span style="color:var(--text-dim);">(' + esc(f.category) + ')</span><br><span style="font-size:12px;color:var(--text-dim);">' + esc(f.reason.substring(0, 80)) + '</span></div>';
    h += '<div class="feedback-btns">';
    for (const a of ['confirmed','corrected','false_positive','missed']) {
      const sel = feedbackSelections[f.key] === a ? ' selected-' + a : '';
      h += '<button class="' + sel + '" onclick="setFeedback(\\'' + f.key + '\\',\\'' + f.concept + '\\',\\'' + a + '\\')">' + a.replace(/_/g, ' ') + '</button>';
    }
    h += '</div></div>';
  }
  container.innerHTML = h;
}

function setFeedback(key, concept, assessment) {
  feedbackSelections[key] = assessment;
  populateFeedbackPanel();
}

async function submitAllFeedback() {
  if (!currentCase || !Object.keys(feedbackSelections).length) {
    showToast('No feedback selected.');
    return;
  }
  const domain = currentCase.case_data.patient_context.domain;
  let submitted = 0;
  for (const [key, assessment] of Object.entries(feedbackSelections)) {
    const concept = key.split('_').slice(1).join('_');
    try {
      await fetch(API + '/demo/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: currentCase.case_id,
          concept: concept,
          domain: domain,
          clinician_assessment: assessment,
        })
      });
      submitted++;
    } catch (e) { /* continue */ }
  }
  showToast(submitted + ' feedback item(s) submitted.');
  refreshExperience();
}

async function refreshExperience() {
  try {
    const resp = await fetch(API + '/demo/experience');
    const data = await resp.json();
    const el = document.getElementById('experience-content');
    let h = '<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">' + data.total_priors + ' priors | ' + data.feedback_count + ' feedback recorded</div>';
    h += '<table class="prior-table"><thead><tr><th>Domain/Concept/Trap</th><th>Prior</th></tr></thead><tbody>';
    const sorted = Object.entries(data.distortion_priors).sort((a, b) => b[1] - a[1]);
    for (const [key, val] of sorted.slice(0, 20)) {
      h += '<tr><td>' + esc(key) + '</td><td>' + val.toFixed(4) + '</td></tr>';
    }
    if (sorted.length > 20) h += '<tr><td colspan="2" style="color:var(--text-dim);">... +' + (sorted.length - 20) + ' more</td></tr>';
    h += '</tbody></table>';
    el.innerHTML = h;
  } catch (e) {
    document.getElementById('experience-content').innerHTML = '<div class="empty-state">Failed to load experience data.</div>';
  }
}

// ---------------------------------------------------------------------------
// LLM Suggestions
// ---------------------------------------------------------------------------
async function suggestRule() {
  if (!currentCase) { showToast('Select a case first.'); return; }
  const btn = document.getElementById('suggest-rule-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Generating...';
  const area = document.getElementById('rule-suggestion-area');
  area.style.display = 'block';
  area.textContent = 'Asking LLM...';

  // Collect findings for context
  const findings = [];
  if (currentAnalysis) {
    for (const s of currentAnalysis.sections) {
      if (s.id === 'red_flags') for (const rf of s.data.red_flags || []) findings.push(rf);
      if (s.id === 'guardrails') for (const f of s.data.findings || []) findings.push(f);
    }
  }

  try {
    const resp = await fetch(API + '/demo/suggest-rule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        case_id: currentCase.case_id,
        patient_context: currentCase.case_data.patient_context,
        statements: currentCase.case_data.statements,
        findings: findings,
      })
    });
    const data = await resp.json();
    if (data.success && data.suggestions && data.suggestions.length) {
      area.textContent = JSON.stringify(data.suggestions, null, 2);
    } else {
      area.textContent = data.error || 'No suggestions generated.';
    }
  } catch (e) {
    area.textContent = 'Error: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate Rule Suggestions';
  }
}

async function suggestCase() {
  const domain = document.getElementById('suggest-domain').value;
  const gap = document.getElementById('suggest-gap').value;
  const btn = document.getElementById('suggest-case-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Generating...';
  const area = document.getElementById('case-suggestion-area');
  area.style.display = 'block';
  area.textContent = 'Asking LLM...';

  try {
    const resp = await fetch(API + '/demo/suggest-case', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain: domain, gap_description: gap })
    });
    const data = await resp.json();
    if (data.success && data.case) {
      area.textContent = JSON.stringify(data.case, null, 2);
    } else {
      area.textContent = data.error || 'No case generated.';
    }
  } catch (e) {
    area.textContent = 'Error: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate Case';
  }
}

// ---------------------------------------------------------------------------
// Custom case builder
// ---------------------------------------------------------------------------
let stmtCounter = 1;

function openCustomBuilder() {
  // Show builder in screen-cases by swapping content
  document.getElementById('case-grid-container').style.display = 'none';
  document.getElementById('custom-builder').style.display = 'block';
}

function cancelCustomBuilder() {
  document.getElementById('case-grid-container').style.display = '';
  document.getElementById('custom-builder').style.display = 'none';
}

function addBuilderStmt() {
  const div = document.createElement('div');
  div.className = 'builder-stmt';
  div.setAttribute('data-idx', stmtCounter++);
  div.innerHTML = '<span class="remove-stmt" onclick="removeBuilderStmt(this)">remove</span><label>Question</label><input class="stmt-q" placeholder="Question"><label>Answer</label><input class="stmt-a" placeholder="Answer"><label>Source</label><select class="stmt-src"><option value="patient">patient</option><option value="caregiver">caregiver</option><option value="device">device</option><option value="chart">chart</option><option value="clinician">clinician</option></select>';
  document.getElementById('builder-stmts').appendChild(div);
}

function removeBuilderStmt(el) {
  const stmtDiv = el.closest('.builder-stmt');
  if (document.querySelectorAll('.builder-stmt').length > 1) stmtDiv.remove();
}

function submitCustomCase() {
  const domain = document.getElementById('builder-domain').value;
  const age = parseInt(document.getElementById('builder-age').value) || 50;
  const concern = document.getElementById('builder-concern').value || 'General concern';
  const modality = document.getElementById('builder-modality').value;
  const conditions = document.getElementById('builder-conditions').value.split(',').map(s => s.trim()).filter(Boolean);

  const stmts = [];
  document.querySelectorAll('.builder-stmt').forEach(div => {
    const q = div.querySelector('.stmt-q').value;
    const a = div.querySelector('.stmt-a').value;
    const src = div.querySelector('.stmt-src').value;
    if (q && a) stmts.push({ question: q, answer: a, concept: null, source: src, metadata: {} });
  });

  if (!stmts.length) { showToast('Add at least one statement.'); return; }

  const customCase = {
    case_id: 'CUSTOM-' + Date.now(),
    title: 'Custom Case',
    scenario: concern,
    category: 'custom',
    category_label: 'Custom',
    domain: domain,
    age: age,
    modality: modality,
    chief_concern: concern,
    jre_demonstrates: '',
    bsg_demonstrates: '',
    combined_insight: '',
    case_data: {
      case_id: 'CUSTOM-' + Date.now(),
      patient_context: {
        age: age,
        chief_concern: concern,
        domain: domain,
        literacy_hint: 'unknown',
        language_barrier: false,
        has_caregiver: false,
        modality: modality,
        known_conditions: conditions,
      },
      statements: stmts,
      ground_truth: {},
    }
  };

  cancelCustomBuilder();
  selectCase(customCase);
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
loadCases();
refreshExperience();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def serve_interactive_page():
    """Serve the interactive demo HTML page."""
    return HTMLResponse(content=_build_interactive_html())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        raise ImportError("uvicorn is required. Install with: pip install uvicorn")
    print("Starting Interactive Demo at http://localhost:8001")
    print("Open in browser to begin the walkthrough.")
    uvicorn.run(app, host="0.0.0.0", port=8001)
