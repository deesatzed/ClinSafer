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
    ReasoningIntegrityEngine,
    ReasoningIntegrityReport,
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
from jre.engine import SOURCE_SCORING_WEIGHT, GESTALT_PATTERNS, infer_concept
from jre.experience import OutcomeFeedback
from jre.any_disposition import (
    AnyDispositionCase,
    AnyDispositionReviewEngine,
    DecisionTimeEvidence,
    DestinationCapability,
    ProposedDisposition,
)
from jre.cognitive_bias_field import CognitiveBiasFieldEngine

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
_reasoning_guard = ReasoningIntegrityEngine()
_any_dispo = AnyDispositionReviewEngine(include_cognitive_bias_field=True)
_cognitive_bias = CognitiveBiasFieldEngine()

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


class TranscriptParseRequest(BaseModel):
    transcript: str


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
    "showcase_boundary": "Showcase — Interpretation Boundaries",
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
    "human_disclosure_pressure": "Embarrassment, stigma, or fear-curated history",
    "human_defense_pattern": "Somatic amplification or stoic minimization",
    "vitals": "Current objective vitals",
    "ecg": "Remote ECG boundary",
    "diaphoresis": "Sweating, nausea, or faintness",
    "radiation": "Radiation to jaw, arm, back, or upper belly",
    "oxygen_saturation": "Current oxygen level",
    "blood_pressure": "Current blood pressure",
    "renal_function": "Recent kidney function labs",
    "potassium": "Recent potassium result",
    "hemoptysis": "Coughing blood / blood in sputum",
    "unknown": "Unclassified added statement",
}


def _display_concept(concept: str) -> str:
    return CONCEPT_LABELS.get(concept, concept.replace("_", " ").title())


SPEAKER_PREFIX_RE = re.compile(
    r"^\s*(clinician|doctor|provider|nurse|assistant|system|ai|patient|pt|caregiver|daughter|son|mom|mother|father|device|chart)\s*[:\-]\s*",
    re.I,
)


def _speaker_for_line(line: str) -> str:
    match = re.match(r"^\s*([A-Za-z ]{1,20})\s*[:\-]\s*", line)
    if not match:
        return ""
    label = match.group(1).strip().lower()
    if label in {"patient", "pt"}:
        return "patient"
    if label in {"caregiver", "daughter", "son", "mom", "mother", "father"}:
        return "caregiver"
    if label in {"device"}:
        return "device"
    if label in {"chart"}:
        return "chart"
    if label in {"clinician", "doctor", "provider", "nurse", "assistant", "system", "ai"}:
        return "clinician"
    return ""


def _clean_speaker_line(line: str) -> str:
    return SPEAKER_PREFIX_RE.sub("", line).strip()


def _parse_transcript_text(text: str) -> List[Dict[str, Any]]:
    """Parse pasted encounter text into governed, editable statement rows."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    turns: List[Dict[str, Any]] = []
    pending_question = ""

    for line in lines:
        inline_qa = re.match(
            r"^\s*(?:Q(?:uestion)?|Clinician|Doctor|Provider|Nurse|Assistant|AI|System)\s*[:\-]\s*(.*?)\s+\bA(?:nswer)?\s*[:\-]\s*(.*)$",
            line,
            re.I,
        )
        question_only = re.match(
            r"^\s*(?:Q(?:uestion)?|Clinician|Doctor|Provider|Nurse|Assistant|AI|System)\s*[:\-]\s*(.*?)\s*$",
            line,
            re.I,
        )
        answer_only = re.match(
            r"^\s*(?:A(?:nswer)?|Patient|Pt|Caregiver|Daughter|Son|Mom|Mother|Father|Device|Chart)\s*[:\-]\s*(.*)$",
            line,
            re.I,
        )
        speaker = _speaker_for_line(line)

        if inline_qa:
            q = inline_qa.group(1).strip()
            a = inline_qa.group(2).strip()
            concept = infer_concept(f"{q} {a}")
            turns.append({"question": q, "answer": a, "concept": concept, "source": "patient", "metadata": {"imported_from_transcript": True}})
            pending_question = ""
        elif question_only and not answer_only:
            pending_question = _clean_speaker_line(line)
        elif answer_only:
            source = speaker if speaker and speaker != "clinician" else "patient"
            q = pending_question or "Patient statement"
            a = answer_only.group(1).strip()
            turns.append({"question": q, "answer": a, "concept": infer_concept(f"{q} {a}"), "source": source, "metadata": {"imported_from_transcript": True}})
            pending_question = ""
        elif speaker == "clinician":
            pending_question = _clean_speaker_line(line)
        elif speaker:
            source = "patient" if speaker == "clinician" else speaker
            q = pending_question or "Patient statement"
            a = _clean_speaker_line(line)
            turns.append({"question": q, "answer": a, "concept": infer_concept(f"{q} {a}"), "source": source, "metadata": {"imported_from_transcript": True}})
            pending_question = ""
        elif pending_question:
            turns.append({"question": pending_question, "answer": line, "concept": infer_concept(f"{pending_question} {line}"), "source": "patient", "metadata": {"imported_from_transcript": True}})
            pending_question = ""
        elif line.endswith("?"):
            pending_question = line
        else:
            turns.append({"question": "Patient statement", "answer": line, "concept": infer_concept(line), "source": "patient", "metadata": {"imported_from_transcript": True}})

    return [turn for turn in turns if (turn.get("question") or turn.get("answer")) and turn.get("answer")]


def _is_context_statement(stmt: Dict[str, Any]) -> bool:
    question = str(stmt.get("question") or "").lower()
    return bool(
        re.search(
            r"\bage\b|how old|medical conditions|conditions|pmh|past medical|diagnos|medications|medicines|meds|what.*taking",
            question,
            re.I,
        )
    )


CONDITION_ALIASES = {
    "t2dm": "type 2 diabetes",
    "dm2": "type 2 diabetes",
    "diabetes": "diabetes",
    "htn": "hypertension",
    "bph": "BPH",
    "ckd": "chronic kidney disease",
    "copd": "COPD",
    "cad": "coronary artery disease",
}


def _split_listish_answer(answer: str) -> List[str]:
    cleaned = re.sub(r"\band\b", ",", str(answer), flags=re.I)
    items = [
        re.sub(r"^[\s:\-]+|[\s.]+$", "", item).strip()
        for item in re.split(r"[,;/\n]+", cleaned)
    ]
    return [item for item in items if item]


def _normalize_condition(item: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "", item.lower())
    return CONDITION_ALIASES.get(key, item.strip())


def _infer_domain_from_transcript(text: str, chief_concern: str = "") -> str:
    blob = f"{chief_concern} {text}".lower()
    if re.search(r"\b(back pain|lower back|low back|lifting|saddle|private areas?|bladder|bleeder|leg(?:s)? feel weak|foot drop)\b", blob):
        return "musculoskeletal_pain"
    if re.search(r"\b(chest|pressure|tight|indigestion|heartburn|jaw|arm)\b", blob):
        return "chest_discomfort"
    if re.search(r"\b(shortness of breath|breath|oxygen|pulse ox|wheez|cough|sputum)\b", blob):
        return "dyspnea_respiratory"
    if re.search(r"\b(urine|uti|burning with urination|flank|kidney)\b", blob):
        return "uti_symptoms"
    if re.search(r"\b(abdominal|belly|diarrhea|vomit|blood in stool|black stool)\b", blob):
        return "gi_symptoms"
    if re.search(r"\b(headache|migraine|vision|neck stiff)\b", blob):
        return "headache_migraine"
    if re.search(r"\b(rash|skin|hives|itch|blister)\b", blob):
        return "rash"
    if re.search(r"\b(anxiety|depress|suicid|sleep|panic)\b", blob):
        return "mental_health"
    return "general_med_management"


def _extract_context_from_transcript(text: str, statements: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized = str(text).replace("’", "'")
    age = 50
    known_conditions: List[str] = []
    medications: List[str] = []
    chief_concern = ""

    for stmt in statements:
        question = str(stmt.get("question") or "").lower()
        answer = str(stmt.get("answer") or "").strip()
        answer_norm = answer.replace("’", "'")
        if re.search(r"\bage\b|how old", question):
            match = re.search(r"\b(?:i am|i'm|age is|around|about)?\s*(\d{1,3})\b", answer_norm, re.I)
            if match:
                age = int(match.group(1))
        if re.search(r"medical conditions|conditions|pmh|past medical|diagnos", question):
            known_conditions.extend(_normalize_condition(item) for item in _split_listish_answer(answer))
        if re.search(r"medications|medicines|meds|taking", question):
            medications.extend(_split_listish_answer(answer))
        if not chief_concern and re.search(r"tell me about|what.*bring|chief concern|main concern|pain|symptom", question):
            chief_concern = answer

    if age == 50:
        match = re.search(r"\b(?:i am|i'm|age is|age:|aged)\s*(\d{1,3})\b", normalized, re.I)
        if match:
            age = int(match.group(1))
    if not known_conditions:
        for token, label in CONDITION_ALIASES.items():
            if re.search(rf"\b{re.escape(token)}\b", normalized, re.I):
                known_conditions.append(label)
    if not medications:
        med_match = re.search(r"(?:medications|medicines|meds|taking)\??\s*(?:patient:)?\s*([^\n]+)", normalized, re.I)
        if med_match:
            medications.extend(_split_listish_answer(med_match.group(1)))
    if not chief_concern:
        if re.search(r"\blower back|low back|back pain\b", normalized, re.I):
            chief_concern = "lower back pain"
        elif statements:
            chief_concern = str(statements[0].get("answer") or "transcript encounter")

    known_conditions = list(dict.fromkeys(c for c in known_conditions if c))
    medications = list(dict.fromkeys(m for m in medications if m))
    domain = _infer_domain_from_transcript(normalized, chief_concern)
    return {
        "age": max(0, min(150, age)),
        "chief_concern": chief_concern or "transcript encounter",
        "domain": domain,
        "literacy_hint": "unknown",
        "language_barrier": False,
        "has_caregiver": any((s.get("source") == "caregiver") for s in statements),
        "modality": "text",
        "known_conditions": known_conditions,
        "medications": medications,
    }

CATEGORY_GROUPS = {
    "Distortion Detection": [
        "base_escalation",
        "base_objective",
        "base_incomplete",
        "base_control",
        "base_showcase",
        "showcase_boundary",
        "top_telemedicine",
    ],
    "Black Swan Safety": ["bs_integrity", "bs_sentinel", "bs_envelope"],
}


def _to_case_input(model: AnalyzeRequest) -> CaseInput:
    domain = model.patient_context.domain
    if domain == "general_med_management":
        transcript_blob = " ".join(
            [model.patient_context.chief_concern]
            + [f"{stmt.question} {stmt.answer}" for stmt in model.statements]
        )
        inferred_domain = _infer_domain_from_transcript(
            transcript_blob,
            model.patient_context.chief_concern,
        )
        if inferred_domain != "general_med_management":
            domain = inferred_domain
    ctx = PatientContext(
        age=model.patient_context.age,
        chief_concern=model.patient_context.chief_concern,
        domain=domain,
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
    if concept == "hemoptysis":
        return "How much blood was there, did it happen more than once, are you short of breath, and are you on blood thinners?"
    if concept == "unknown":
        return "Classify this added statement into a clinical concept or route it for clinician review before using it to support a decision."
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
    if concept == "unknown":
        return "This added statement is not classified into a validated slot yet; it must stay reviewable and cannot be treated as safely resolved."
    if concept == "hemoptysis":
        return "Coughing blood or blood in sputum is a safety-relevant signal that should be treated as present until clarified."
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
    if concept == "unknown":
        return "Do not let unclassified added text bypass sentinel screening, concept inference, or clinician handoff."
    if concept == "hemoptysis":
        return "Do not treat 'a little blood' or blood-streaked sputum as low-risk without clarifying amount, recurrence, breathing status, anticoagulants, infection risk, and current stability."
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
        if concept == "unknown":
            status = "unsafe_to_infer"
        if concept == "hemoptysis":
            status = "unsafe_to_infer"
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


def _build_input_coverage_section(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
) -> Dict[str, Any]:
    """Show whether every input line was used, routed, or explicitly reviewed."""
    domain_slots = {slot.name for slot in DOMAIN_TEMPLATES.get(case.patient_context.domain, [])}
    jre_by_concept: Dict[str, List[Finding]] = {}
    for finding in jre_report.findings:
        jre_by_concept.setdefault(finding.concept, []).append(finding)

    rows = []
    failure_count = 0
    for idx, stmt in enumerate(case.statements):
        obs = jre_report.observations[idx] if idx < len(jre_report.observations) else None
        supplied = stmt.concept or ""
        inferred = infer_concept(f"{stmt.question} {stmt.answer}") or ""
        effective = obs.concept if obs else (inferred or supplied or "unknown")
        context_row = _is_context_statement(
            {
                "question": stmt.question,
                "answer": stmt.answer,
                "concept": supplied,
                "source": stmt.source,
            }
        )
        manual_label = supplied.lower() in {"red_flag", "redflag", "alarm", "safety", "urgent", "manual_red_flag"}

        matched_bsg = []
        answer_fragment = str(stmt.answer or "")[:80]
        for finding in bsg_report.findings:
            if answer_fragment and answer_fragment in finding.evidence:
                matched_bsg.append(finding)
            elif manual_label and finding.rule_id == "MANUAL_RED_FLAG_REVIEW":
                matched_bsg.append(finding)

        consumers = ["Observation extractor"]
        if context_row:
            consumers.append("Patient-context extractor")
        if effective in domain_slots:
            consumers.append("JRE template slot")
        concept_findings = jre_by_concept.get(effective, [])
        if concept_findings:
            consumers.append("JRE rules")
        if matched_bsg:
            consumers.append("Black Swan Guard")
        consumers.append("Async LLM extractor payload")

        status = "used"
        safety_effect = "Captured and available to governed analysis."
        if context_row:
            status = "context"
            safety_effect = "Extracted as demographics, PMH, medication, or risk context."
        if effective == "unknown":
            status = "review"
            safety_effect = "Captured but unmapped; cannot support reassurance or closure."
        if manual_label:
            status = "review"
            safety_effect = "Manual safety label preserved and forced through review."
        if concept_findings:
            strongest = max(concept_findings, key=lambda f: f.severity)
            safety_effect = f"{strongest.rule_id}: {strongest.reason}"
            if strongest.category == "red_flag":
                status = "red_flag"
        if matched_bsg:
            strongest_bsg = max(matched_bsg, key=lambda f: f.severity)
            safety_effect = f"{strongest_bsg.rule_id}: {strongest_bsg.reason}"
            status = "hard_stop" if strongest_bsg.action in {"ESCALATE", "FAIL_CLOSED"} else "review"

        reclassified = bool(supplied and supplied != effective and effective in domain_slots)
        if reclassified and "Concept reclassifier" not in consumers:
            consumers.append("Concept reclassifier")

        if status in {"review"} or effective == "unknown":
            failure_count += 1

        rows.append(
            {
                "line": idx + 1,
                "question": stmt.question,
                "answer": stmt.answer,
                "source": stmt.source,
                "supplied_concept": supplied or "(blank)",
                "inferred_concept": inferred or "(none)",
                "effective_concept": effective,
                "status": status,
                "consumers": consumers,
                "safety_effect": safety_effect,
                "reclassified": reclassified,
                "tags": obs.tags if obs else [],
            }
        )

    return {
        "id": "input_coverage",
        "title": "Input Coverage Audit",
        "subtitle": "Every transcript line must be used, mapped to context, escalated, or explicitly held for review.",
        "data": {
            "rows": rows,
            "total_lines": len(rows),
            "review_or_unmapped": failure_count,
            "invariant": "No input line may silently disappear or support reassurance while unmapped.",
        },
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


def _build_uncertainty_graph_section(
    jre_report: ReadinessReport,
) -> Dict[str, Any]:
    """Section: explicit expert-system uncertainty nodes."""
    graph = jre_report.uncertainty_graph or {"summary": {}, "nodes": {}}
    summary = graph.get("summary", {})
    rows = []
    for node_id, node in graph.get("nodes", {}).items():
        dist = node.get("uncertainty_distribution", {})
        dominant = max(dist.items(), key=lambda item: item[1])[0] if dist else "unknown"
        rows.append(
            {
                "node_id": node_id,
                "label": node.get("label", node_id),
                "observed": node.get("observed", False),
                "raw_value": node.get("raw_value") or "",
                "source": node.get("source") or "",
                "confidence": node.get("confidence", 0),
                "range_band": node.get("range_band") or "",
                "range_severity": node.get("range_severity", 0),
                "state": node.get("missingness_state", ""),
                "dominant_uncertainty": dominant,
                "distribution": dist,
                "boundary_distance": node.get("boundary_distance"),
                "boundary_fragility": node.get("boundary_fragility", 0),
                "perturbation_flip_risk": node.get("perturbation_flip_risk", 0),
                "actions": node.get("action_implications", []),
            }
        )
    rows.sort(
        key=lambda row: (
            -float(row.get("range_severity") or 0),
            str(row.get("state")) not in {"conflicted", "objective_needed", "missing", "remote_unknowable"},
            str(row.get("node_id")),
        )
    )
    return {
        "id": "uncertainty_graph",
        "title": "Clinical Uncertainty Graph",
        "subtitle": "Typed expert-system nodes with ranges, source reliability, uncertainty distributions, and action implications.",
        "data": {
            "summary": summary,
            "nodes": rows,
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
    reasoning_report: ReasoningIntegrityReport,
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
    ri_idx = (
        STATE_PRIORITY.index(reasoning_report.state)
        if reasoning_report.state in STATE_PRIORITY
        else len(STATE_PRIORITY)
    )

    if jre_idx <= bsg_idx and jre_idx <= ri_idx:
        driver = "Judgment Readiness Engine (clinical signal)"
    elif bsg_idx <= jre_idx and bsg_idx <= ri_idx:
        driver = "Black Swan Guard (system safety)"
    elif ri_idx <= jre_idx and ri_idx <= bsg_idx:
        driver = "Reasoning Integrity Check (cognitive forcing)"
    else:
        driver = "Governed layers agree"

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
        "subtitle": "The combined verdict from clinical readiness, guardrails, and reasoning-integrity checks.",
        "data": {
            "combined_state": combined_state,
            "jre_state": jre_report.state,
            "bsg_state": bsg_report.guardrail_state,
            "reasoning_state": reasoning_report.state,
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


def _build_reasoning_integrity_section(
    reasoning_report: ReasoningIntegrityReport,
) -> Dict[str, Any]:
    """Section: cognitive-bias guard and forcing functions."""
    return {
        "id": "reasoning_integrity",
        "title": "Reasoning Integrity Check",
        "subtitle": "Cognitive forcing against anchoring, premature closure, confirmation bias, omission bias, and overconfidence.",
        "data": {
            "state": reasoning_report.state,
            "summary": reasoning_report.provider_summary,
            "patient_safe_summary": reasoning_report.patient_safe_summary,
            "findings": [
                {
                    "bias_id": f.bias_id,
                    "label": f.label,
                    "severity": round(f.severity, 2),
                    "evidence": f.evidence,
                    "reasoning_failure": f.reasoning_failure,
                    "cognitive_forcing_action": f.cognitive_forcing_action,
                    "disconfirming_question": f.disconfirming_question,
                    "affected_autonomy": f.affected_autonomy,
                    "authority": f.authority,
                }
                for f in reasoning_report.findings
            ],
            "invariants": [
                "This layer audits the reasoning path, not the clinician's character.",
                "A bias finding creates a cognitive forcing action or verification target; it does not diagnose the patient.",
                "Reasoning-integrity findings can cap autonomy only through the governed most-restrictive state.",
            ],
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

    human_boundary = _build_human_factor_boundary(case, jre_report, bsg_report)

    return {
        "state": combined_state,
        "case_title": CASE_NARRATIVES.get(case.case_id).title if case.case_id in CASE_NARRATIVES else case.case_id,
        "why": why[:5],
        "authority": "Curated safety rules and the ensemble governor made the routing decision.",
        "ai_role": "External LLM findings are advisory candidate signals only; they can support review but cannot authorize or hard-stop care by themselves.",
        "patient_pattern": human_boundary["summary"],
        "autonomy": f"{bsg_report.max_autonomy_tier}: {AUTONOMY_TIERS.get(bsg_report.max_autonomy_tier, '')}",
    }


def _build_human_factor_boundary(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
) -> Dict[str, Any]:
    """Summarize human-response patterns that alter answer reliability.

    This is intentionally not a psychiatric label. It is a product-safety layer
    that treats patient language as a measurement shaped by context, fear,
    identity, stigma, and coping style.
    """
    text = " ".join(s.answer for s in case.statements).lower()
    categories = {f.category for f in bsg_report.findings}
    rule_ids = {f.rule_id for f in bsg_report.findings}

    spectrum = []
    cues = []

    cue_patterns = [
        (
            "anxiety / somatic amplification",
            r"\b(anxiety|panic|stress|overreacting|in my head|google|googled|internet|cancer|something bad|bad news)\b",
            "May anchor on a feared diagnosis or seek reassurance before the facts are complete.",
        ),
        (
            "stoic minimization / denial",
            r"\b(tough it out|not a complainer|not weak|look weak|walk it off|push through|make a fuss|big deal|nothing serious|i'?ll be fine|i will be fine)\b",
            "May under-report severity or functional limitation to preserve a self-image of toughness.",
        ),
        (
            "privacy / stigma pressure",
            r"\b(embarrass|ashamed|don'?t judge|do not judge|chart|do not want to talk|don'?t want to talk|awkward)\b",
            "May omit sensitive details unless the system normalizes and narrows the question.",
        ),
        (
            "access / consequence pressure",
            r"\b(afford|insurance|work|wait until|please do not send|please don't send|can i wait|er)\b",
            "May bargain against escalation for practical reasons even when risk is unchanged.",
        ),
    ]

    for label, pattern, reason in cue_patterns:
        if re.search(pattern, text):
            spectrum.append(label)
            cues.append({"label": label, "why": reason})

    if "human_disclosure_pressure" in categories:
        spectrum.append("sensitive disclosure pressure")
        cues.append({
            "label": "sensitive disclosure pressure",
            "why": "The patient may be curating the history because the topic feels embarrassing, stigmatized, or frightening.",
        })
    if "human_defense_pattern" in categories:
        spectrum.append("defense-pattern distortion")
        cues.append({
            "label": "defense-pattern distortion",
            "why": "The patient is framing symptoms through coping language rather than giving clean clinical facts.",
        })
    if "care_avoidance_pressure" in categories:
        spectrum.append("care-avoidance pressure")

    # Deduplicate while preserving order.
    spectrum = list(dict.fromkeys(spectrum))
    unique_cues = []
    seen = set()
    for cue in cues:
        if cue["label"] not in seen:
            unique_cues.append(cue)
            seen.add(cue["label"])
    cues = unique_cues

    reliability_findings = [
        f for f in jre_report.findings
        if f.category in {"distorted", "contradictory", "uncertain"}
    ]

    if not spectrum and not reliability_findings:
        summary = "No explicit human distortion pattern was detected, but patient wording, omissions, and context are still treated as evidence boundaries."
        spectrum_label = "No explicit pattern detected"
    else:
        spectrum_label = " + ".join(spectrum[:4]) if spectrum else "answer reliability weakened"
        summary = (
            "Human factor boundary: "
            + spectrum_label
            + ". Treat coping language as an answer-reliability modifier, not as proof of low or high risk."
        )

    verification_strategy = [
        "Normalize the concern without agreeing to the patient's preferred conclusion.",
        "Ask one concrete function/timing question instead of debating whether the symptom is serious.",
        "Translate clinical vocabulary into body-location and activity examples.",
        "Request current objective data or collateral evidence when it would change autonomy.",
        "Document what remains unknown and why automation is capped.",
    ]
    avoid = [
        "Do not call the patient anxious, dramatic, or unreliable.",
        "Do not accept 'it is just anxiety' as a diagnosis or 'I can tough it out' as negative evidence.",
        "Do not reward minimization by closing the case as low risk.",
        "Do not let an LLM convert coping language into reassurance without validated evidence.",
    ]
    prompt_guardrails = [
        "Label the pattern as an interpretation-boundary cue, not a psychiatric conclusion.",
        "Extract exact statements, missing facts, contradictions, and functional claims.",
        "Generate normalizing, privacy-preserving questions that close one boundary at a time.",
        "Keep all human-factor signals advisory until deterministic safety validators approve behavior changes.",
    ]

    return {
        "title": "Human Factors Boundary",
        "spectrum": spectrum_label,
        "summary": summary,
        "cues": cues[:6],
        "reliability_findings": [
            {
                "signal": _display_concept(f.concept),
                "why": f.reason,
                "rule": f.rule_id,
            }
            for f in reliability_findings[:5]
        ],
        "verification_strategy": verification_strategy,
        "avoid": avoid,
        "prompt_guardrails": prompt_guardrails,
        "triggered_rules": sorted(
            r for r in rule_ids
            if r in {"SENTINEL_DISCLOSURE_DISTORTION", "SENTINEL_DEFENSE_PATTERN_DISTORTION", "SENTINEL_CARE_AVOIDANCE_PRESSURE"}
        ),
    }


def _build_final_recommendations(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    reasoning_report: ReasoningIntegrityReport,
    combined_state: str,
) -> Dict[str, Any]:
    """Actionable final page synthesized from analysis and governance outputs."""
    urgent = combined_state in {"ESCALATE", "FAIL_CLOSED"}
    routed = combined_state in {
        "ESCALATE",
        "FAIL_CLOSED",
        "ROUTE_CLINICIAN",
        "HOLD_AND_VERIFY",
        "NEED_OBJECTIVE_DATA",
    }
    top_findings = sorted(jre_report.findings, key=lambda x: -x.severity)[:6]
    top_guardrails = sorted(bsg_report.findings, key=lambda x: -x.severity)[:4]
    human_boundary = _build_human_factor_boundary(case, jre_report, bsg_report)
    reasoning_actions = [
        {
            "bias": f.label,
            "action": f.cognitive_forcing_action,
            "question": f.disconfirming_question,
            "autonomy_effect": f.affected_autonomy,
        }
        for f in reasoning_report.findings[:3]
    ]

    jre_evidence = [
        {
            "signal": _display_concept(f.concept),
            "why": f.reason,
            "rule": f.rule_id,
            "authority": _authority_for_jre_finding(f)["authority"],
        }
        for f in top_findings
    ]
    guardrail_evidence = [
        {
            "signal": f.rule_id.replace("_", " ").title(),
            "why": f.reason,
            "rule": f.rule_id,
            "authority": _authority_for_bsg_finding(f.rule_id)["authority"],
        }
        for f in top_guardrails
    ]
    critical_evidence = guardrail_evidence + jre_evidence

    do_not_infer = []
    for f in jre_report.findings:
        if f.category in {"missing", "objective_needed", "unknowable_remote"}:
            do_not_infer.append(f"{_display_concept(f.concept)} is not established: {f.reason}")
        elif f.category in {"distorted", "contradictory"}:
            do_not_infer.append(f"Do not treat {_display_concept(f.concept)} as settled negative evidence: {f.reason}")
    do_not_infer = list(dict.fromkeys(do_not_infer))[:6]

    immediate_actions = []
    patient_message = ""
    if urgent:
        immediate_actions = [
            "Stop routine automation and route to urgent human/emergency pathway.",
            "Preserve the boundary map and top evidence in the clinician handoff.",
            "Do not reassure, close, or delay based on patient minimization or cost/work pressure.",
            "Ask only escalation-support questions needed to keep the patient engaged and safe.",
        ]
        if case.patient_context.domain == "chest_discomfort":
            patient_message = (
                "I cannot safely tell you this can wait. The pattern you described can be time-sensitive, "
                "especially because it happens with activity and improves with rest. Because cost and work are real barriers, "
                "I want to help you find the safest urgent option now rather than delay."
            )
        else:
            patient_message = (
                "I cannot safely tell you this can wait. Some details you described can be time-sensitive and need urgent review. "
                "I want to help you get the safest urgent option now rather than delay or minimize it."
            )
    elif routed:
        immediate_actions = [
            "Hold autonomous completion until the listed evidence gap is resolved.",
            "Ask the smallest number of high-yield questions or request the objective data shown below.",
            "Route to clinician if the gap cannot be closed quickly or reliably.",
        ]
        patient_message = (
            "I need one or two specific details before this can be handled safely. "
            "If you cannot provide them, a clinician should review this rather than guessing."
        )
    else:
        immediate_actions = [
            "Proceed only within the displayed autonomy tier.",
            "Keep the audit trail and patient-facing safety boundaries visible.",
            "Monitor for new symptoms, source conflict, stale data, or changed medication context.",
        ]
        patient_message = (
            "The available information supports this narrow pathway, but the system should keep the boundary visible "
            "and ask for help if anything changes."
        )

    next_questions = [
        {
            "target": _display_concept(q.concept),
            "question": q.question,
            "why": q.reason,
        }
        for q in jre_report.next_questions[:5]
    ]
    if urgent:
        next_questions = [
            {
                "target": "Current danger",
                "question": "Are the concerning symptoms happening right now or returning?",
                "why": "Determines whether to intensify the urgent handoff while routing.",
            },
            {
                "target": "Support",
                "question": "Are you alone, or is someone with you who can help call emergency services?",
                "why": "Reduces abandonment and unsafe self-management during escalation.",
            },
            {
                "target": "Transport",
                "question": "Can you call emergency services now? Do not drive yourself if symptoms are active or returning.",
                "why": "Prevents unsafe self-transport.",
            },
            {
                "target": "Access barrier",
                "question": "If cost or work is why you want to wait, can we help find the safest urgent option now?",
                "why": "Addresses the stated barrier without downgrading clinical risk.",
            },
        ]

    governance_actions = [
        "Record final clinician disposition and whether the routing decision was confirmed, corrected, false positive, or missed.",
        "Capture whether patient cost/work pressure caused delay, abandonment, or successful engagement.",
        "If clinician feedback changes the disposition, promote a template/rule update only after review and simulation.",
    ]
    if top_guardrails:
        governance_actions.insert(0, "Review triggered guardrails for calibration before changing automation boundaries.")

    role_manifest = _llm.role_manifest() if _llm is not None else []
    ai_processing = {
        "role": "External LLM roles are bounded assistants, not the decision authority.",
        "prompt_contract": [
            "Fast extractor parses raw language into candidate concepts, red flags, wrong labels, and coverage gaps.",
            "Boundary reasoner asks what would make automation unsafe and which falsifiers are still missing.",
            "Adversarial verifier looks for missed transcript lines, false negatives, and unsafe reassurance.",
            "Patient and workflow synthesis happen only after the governed disposition is already set.",
            "No LLM role may diagnose, reassure, authorize autonomous action, or override curated guardrails.",
        ],
        "current_authority": "Curated rules, validated guardrails, and the ensemble governor determine the final autonomy boundary.",
        "roles": role_manifest,
    }

    return {
        "title": "Final Recommendations",
        "case_id": case.case_id,
        "case_title": CASE_NARRATIVES.get(case.case_id).title if case.case_id in CASE_NARRATIVES else case.case_id,
        "disposition": combined_state,
        "autonomy_tier": bsg_report.max_autonomy_tier,
        "autonomy_description": AUTONOMY_TIERS.get(bsg_report.max_autonomy_tier, ""),
        "bottom_line": (
            "Escalate now. This is not safe for routine automation or delayed reassurance."
            if urgent
            else "Hold or route until the listed evidence boundary is closed."
            if routed
            else "Proceed only within the narrow audited pathway."
        ),
        "clinician_handoff": (
            f"{case.patient_context.age}-year-old with {case.patient_context.chief_concern}. "
            f"Final state {combined_state}; JRE={jre_report.state}, BSG={bsg_report.guardrail_state}. "
            f"Top blockers: " + "; ".join(item["why"] for item in critical_evidence[:3])
        ),
        "immediate_actions": immediate_actions,
        "critical_evidence": critical_evidence[:8],
        "do_not_infer": do_not_infer,
        "next_questions": next_questions,
        "patient_message": patient_message,
        "human_factors": human_boundary,
        "reasoning_integrity": {
            "state": reasoning_report.state,
            "summary": reasoning_report.provider_summary,
            "actions": reasoning_actions,
        },
        "governance_actions": governance_actions,
        "ai_processing": ai_processing,
        "quality_metrics": [
            "Was the final disposition confirmed by clinician review?",
            "Did the patient complete the recommended routing step?",
            "Did the explanation reduce abandonment or unsafe delay?",
            "Which missing evidence would have changed the disposition?",
        ],
    }


def _derive_any_dispo_case(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    combined_state: str,
) -> AnyDispositionCase:
    """Build a conservative any-disposition stress test from the live encounter."""
    lower_acuity_stress = combined_state in {
        "ESCALATE",
        "FAIL_CLOSED",
        "ROUTE_CLINICIAN",
        "HOLD_AND_VERIFY",
        "NEED_OBJECTIVE_DATA",
    }
    destination = "home" if lower_acuity_stress else "telehealth"
    rationale = (
        "Lower-acuity stress test: could this encounter safely go home or stay remote?"
        if lower_acuity_stress
        else "Narrow-pathway stress test: can the encounter remain in a low-acuity audited workflow?"
    )

    unresolved_red_flags = [
        f"{_display_concept(f.concept)}: {f.reason}"
        for f in jre_report.findings
        if f.category == "red_flag"
    ][:6]
    unresolved_red_flags.extend(
        f"{f.rule_id}: {f.reason}"
        for f in bsg_report.findings
        if f.category in {"sentinel_red_flag", "jre_escalation_wrap"}
    )

    source_conflicts = [
        f"{_display_concept(f.concept)}: {f.reason}"
        for f in jre_report.findings
        if f.category == "contradictory"
    ]
    source_conflicts.extend(
        f"{f.rule_id}: {f.reason}"
        for f in bsg_report.findings
        if f.category in {"objective_data_integrity", "workflow_integrity"}
    )

    objective_gaps = [
        f"{_display_concept(f.concept)}: {f.reason}"
        for f in jre_report.findings
        if f.category in {"missing", "objective_needed", "unknowable_remote"}
    ][:8]
    high_risk_factors = list(case.patient_context.known_conditions or [])
    if case.patient_context.age >= 65:
        high_risk_factors.append("age>=65")

    inpatient_needs = []
    if unresolved_red_flags:
        inpatient_needs.append("urgent clinician reassessment")
    if any("oxygen" in item.lower() or "dyspnea" in item.lower() for item in unresolved_red_flags + objective_gaps):
        inpatient_needs.append("serial vitals or oxygen assessment")
    if any("ecg" in item.lower() or "chest" in item.lower() for item in unresolved_red_flags + objective_gaps):
        inpatient_needs.append("objective cardiac evaluation")

    evidence = DecisionTimeEvidence(
        unresolved_red_flags=unresolved_red_flags,
        source_conflicts=source_conflicts,
        high_risk_factors=high_risk_factors,
        objective_gaps=objective_gaps,
        inpatient_only_needs=list(dict.fromkeys(inpatient_needs)),
        response_to_treatment="not_documented",
        follow_up_reliability="unknown",
        caregiver_status="available" if case.patient_context.has_caregiver else "unknown",
    )
    capability = DestinationCapability(
        medication_access=case.patient_context.domain == "med_refill_hypertension",
        caregiver_or_staff_support=case.patient_context.has_caregiver,
        confirmed_follow_up=False,
    )
    return AnyDispositionCase(
        case_id=case.case_id,
        age=case.patient_context.age,
        chief_concern=case.patient_context.chief_concern,
        domain=case.patient_context.domain,
        proposed_disposition=ProposedDisposition(
            destination=destination,
            service="remote_or_home_review",
            monitoring_level="none" if destination == "home" else "remote",
            rationale=rationale,
            follow_up_plan="not confirmed in transcript",
        ),
        destination_capability=capability,
        evidence=evidence,
        metadata={"combined_state": combined_state, "source": "interactive_demo"},
    )


def _build_method_stack_section(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    reasoning_report: ReasoningIntegrityReport,
    combined_state: str,
) -> Dict[str, Any]:
    """Show which newer methods actually ran for this encounter."""
    any_dispo_case = _derive_any_dispo_case(case, jre_report, bsg_report, combined_state)
    any_dispo_report = _any_dispo.evaluate(any_dispo_case).to_dict()
    bias_report = _cognitive_bias.evaluate_jre(
        case,
        jre_report,
        bsg_report,
        reasoning_report,
    ).to_dict()
    graph_summary = (jre_report.uncertainty_graph or {}).get("summary", {})
    dominant_biases = bias_report.get("dominant_biases", [])
    any_bias = any_dispo_report.get("cognitive_bias_field") or {}

    applied_methods = [
        {
            "name": "Judgment Readiness Engine",
            "status": jre_report.state,
            "result": f"JRI {jre_report.scores.readiness_index:.1f}; {len(jre_report.findings)} uncertainty or safety findings.",
            "evidence": "Runs on the current transcript statements and can route, clarify, require objective data, or escalate.",
        },
        {
            "name": "Any Dispo Review",
            "status": any_dispo_report["state"],
            "result": f"{any_dispo_report['proposed_destination']} stress test; priority {any_dispo_report['review_priority']:.1f}.",
            "evidence": any_dispo_report["rationale"],
        },
        {
            "name": "Cognitive Bias Field",
            "status": f"entropy {bias_report['bias_entropy_score']:.1f}",
            "result": ", ".join(b["label"] for b in dominant_biases[:3]) or "No dominant bias pressure detected.",
            "evidence": "Generates fresh-eyes prompts, information-gain candidates, and cognitive friction actions.",
        },
        {
            "name": "Clinical Uncertainty Graph",
            "status": f"{graph_summary.get('observed_nodes', 0)}/{graph_summary.get('node_count', 0)} nodes observed",
            "result": f"graph readiness {graph_summary.get('graph_readiness_index', 'n/a')}; boundary sensitivity {graph_summary.get('boundary_sensitivity_index', 0):.2f}.",
            "evidence": "Turns claims into typed nodes with source reliability, ranges, uncertainty distribution, and action implications.",
        },
        {
            "name": "Black Swan Guardrails",
            "status": bsg_report.guardrail_state,
            "result": f"autonomy cap {bsg_report.max_autonomy_tier}; {len(bsg_report.findings)} guardrail findings.",
            "evidence": "Checks sentinel, integrity, communication-envelope, workflow, and operating-boundary failures.",
        },
        {
            "name": "TabPFN / Imbalance-Aware Models",
            "status": "planned empirical layer",
            "result": "Not run on a single demo transcript; requires a labeled disposition cohort.",
            "evidence": "The app now exposes review states, blockers, uncertainty features, and outcomes needed for later TabPFN, conformal, calibration, and imbalanced-data benchmarking.",
        },
    ]

    return {
        "id": "method_stack",
        "title": "Method Stack Applied",
        "subtitle": "Which new methodologies actually ran on this encounter, and which remain empirical-model work.",
        "data": {
            "applied_methods": applied_methods,
            "any_dispo": any_dispo_report,
            "cognitive_bias_field": bias_report,
            "any_dispo_bias_field": any_bias,
            "input_signature": {
                "case_id": case.case_id,
                "statement_count": len(case.statements),
                "domain": case.patient_context.domain,
                "sources": sorted({s.source for s in case.statements}),
            },
        },
    }


def _llm_role_manifest() -> List[Dict[str, Any]]:
    if _llm is None:
        return []
    try:
        return _llm.role_manifest()
    except Exception:
        return []


def _build_provenance_authority_section(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    reasoning_report: ReasoningIntegrityReport,
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
            "name": "Reasoning integrity guard",
            "authority": "Cognitive Forcing",
            "count": len(reasoning_report.findings),
            "examples": [f.label for f in reasoning_report.findings[:3]],
            "effect": "Can cap autonomy through hold/verify or clinician routing when known reasoning failure modes are paired with unresolved evidence.",
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
            "llm_roles": _llm_role_manifest(),
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
                    "layer": "Reasoning Integrity",
                    "state": reasoning_report.state,
                    "authority": "Cognitive-forcing state",
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
            "signal": "cost fear, coercion, embarrassment, stigma, defense patterns, minimization, nonresponse, desired outcome pressure",
            "status": "hot" if {"workflow_integrity", "communication_envelope", "social_channel_risk", "human_disclosure_pressure", "human_defense_pattern"}.intersection(guardrail_categories) else "watch",
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
                "Deposit traces for claims, objective evidence, source conflict, human-disclosure pressure, temporal staleness, and outcome feedback.",
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
            "layer": "Operational mitigation",
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
            "role_manifest": _llm_role_manifest(),
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
    reasoning_report: ReasoningIntegrityReport,
    combined_state: str,
    llm_result=None,
) -> List[Dict[str, Any]]:
    """Build progressive analysis sections for the executive demo."""
    return [
        _build_input_coverage_section(case, jre_report, bsg_report),
        _build_method_stack_section(case, jre_report, bsg_report, reasoning_report, combined_state),
        _build_interpretation_boundaries_section(case, jre_report),
        _build_provenance_authority_section(case, jre_report, bsg_report, reasoning_report, combined_state),
        _build_observations_section(jre_report),
        _build_mud_map_section(jre_report),
        _build_red_flags_section(jre_report),
        _build_uncertainty_graph_section(jre_report),
        _build_jri_section(jre_report),
        _build_guardrails_section(bsg_report),
        _build_reasoning_integrity_section(reasoning_report),
        _build_safety_decision_section(jre_report, bsg_report, reasoning_report, combined_state),
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
    reasoning_report = _reasoning_guard.evaluate(case, jre_report, bsg_report)
    combined_state = most_restrictive(
        most_restrictive(jre_report.state, bsg_report.guardrail_state),
        reasoning_report.state,
    )

    # LLM is NOT called here — Section 8 reports llm_available status
    # and the browser can trigger LLM analysis separately if desired.
    # This keeps analysis fast and deterministic for the progressive reveal.
    sections = _build_progressive_sections(
        case, jre_report, bsg_report, reasoning_report, combined_state, llm_result=None
    )
    duration_ms = (time.monotonic() - start) * 1000

    return {
        "case_id": case.case_id,
        "combined_state": combined_state,
        "duration_ms": round(duration_ms, 1),
        "summary": _build_demo_summary(case, jre_report, bsg_report, combined_state),
        "recommendations": _build_final_recommendations(
            case, jre_report, bsg_report, reasoning_report, combined_state
        ),
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


@app.post("/demo/parse-transcript")
def parse_transcript(req: TranscriptParseRequest):
    """Parse pasted encounter text into editable statements with governed concept inference."""
    raw_statements = _parse_transcript_text(req.transcript)
    extracted_context = _extract_context_from_transcript(req.transcript, raw_statements)
    statements = [s for s in raw_statements if not _is_context_statement(s)]
    if not statements:
        statements = raw_statements
    concepts = sorted({s.get("concept") or "unknown" for s in statements})
    sources = sorted({s.get("source") or "patient" for s in statements})
    return {
        "statements": statements,
        "count": len(statements),
        "context_rows": len(raw_statements) - len(statements),
        "concepts": concepts,
        "sources": sources,
        "patient_context": {
            k: v
            for k, v in extracted_context.items()
            if k != "medications"
        },
        "medications": extracted_context["medications"],
        "llm_available": bool(_llm is not None and _llm.available),
        "classification_note": (
            "Transcript imported as editable turns. Source and concept labels are used by the governed analysis; "
            "the async LLM extractor receives these same turns after analysis."
        ),
    }


@app.post("/demo/llm-analyze")
def llm_analyze(req: AnalyzeRequest):
    """Run LLM analysis on a case. Called separately from /demo/analyze for async UX."""
    role_manifest = _llm_role_manifest()
    if _llm is None or not _llm.available:
        return {
            "llm_available": False,
            "llm_error": "LLM not available. Set OPENROUTER_API_KEY to enable.",
            "llm_findings": [],
            "model": None,
            "role_manifest": role_manifest,
            "role_runs": [],
            "raw_preview": "",
        }

    _validate_domain(req.patient_context.domain)
    case = _to_case_input(req)

    try:
        role_results = _llm.analyze_case_roles(case)
        findings = []
        role_runs = []
        raw_previews = []
        errors = []
        for role in _llm.configured_roles():
            result = role_results.get(role)
            manifest = next((r for r in role_manifest if r.get("role") == role), {})
            role_findings = []
            if result is None:
                continue
            if result.success:
                for f in result.findings:
                    item = {
                        "role": role,
                        "role_label": manifest.get("label", role),
                        "category": f.category,
                        "concept": f.concept,
                        "severity": round(f.severity, 2),
                        "reason": f.reason,
                        "evidence": f.evidence,
                        "confidence": round(f.confidence, 2),
                    }
                    role_findings.append(item)
                    findings.append(item)
            elif result.error:
                errors.append(f"{manifest.get('label', role)}: {result.error}")
            if result.raw_response:
                raw_previews.append(f"[{manifest.get('label', role)}] {result.raw_response[:350]}")
            role_runs.append(
                {
                    "role": role,
                    "label": manifest.get("label", role),
                    "model": result.model,
                    "success": result.success,
                    "error": result.error,
                    "findings": role_findings,
                    "authority": manifest.get("authority", "Advisory only."),
                    "purpose": manifest.get("purpose", ""),
                }
            )
        return {
            "llm_available": True,
            "llm_error": "; ".join(errors) if errors else None,
            "llm_findings": findings,
            "model": ", ".join(sorted({run["model"] for run in role_runs if run.get("model")})),
            "role_manifest": role_manifest,
            "role_runs": role_runs,
            "raw_preview": "\n\n".join(raw_previews)[:900],
            "llm_note": "LLM roles ran and returned no additional candidate signals." if not errors and not findings else "",
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

.transcript-intake-card {
  background: linear-gradient(135deg, #ffffff 0%, #eefcf9 58%, #fff8e8 100%);
  border: 1px solid rgba(15,159,154,0.26);
  border-radius: var(--radius);
  padding: 18px;
  margin: 18px 0;
  box-shadow: 0 12px 30px rgba(31,97,114,0.10);
}
.transcript-intake-card h3 { font-size: 16px; margin-bottom: 4px; }
.transcript-intake-card p { color: var(--text-dim); font-size: 13px; margin-bottom: 12px; }
.transcript-intake-grid {
  display: grid;
  grid-template-columns: 1fr 96px 160px 1fr;
  gap: 10px;
  margin-bottom: 10px;
}
@media (max-width: 900px) { .transcript-intake-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 560px) { .transcript-intake-grid { grid-template-columns: 1fr; } }
.transcript-intake-card label {
  display: block;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 4px;
}
.transcript-intake-card input,
.transcript-intake-card select,
.transcript-intake-card textarea,
.builder-form textarea {
  background: #f8fcfd;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 9px 11px;
  color: var(--text);
  font-size: 14px;
  width: 100%;
}
.transcript-intake-card textarea,
.builder-form textarea {
  min-height: 120px;
  resize: vertical;
  font-family: 'SF Mono', Menlo, monospace;
  line-height: 1.45;
}
.transcript-proof {
  background: rgba(255,255,255,0.72);
  border: 1px solid rgba(15,159,154,0.18);
  border-radius: 8px;
  padding: 9px 10px;
  color: var(--text-dim);
  font-size: 12px;
  margin-top: 10px;
}
.field-purpose-note {
  background: #f8fcfd;
  border: 1px solid rgba(207,226,234,0.8);
  border-radius: 8px;
  padding: 10px 12px;
  color: var(--text-dim);
  font-size: 12px;
  margin: 10px 0 12px;
}

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
.encounter-edit-note {
  background: linear-gradient(135deg, #ecfdf5, #eff6ff);
  border: 1px solid rgba(15,159,154,0.24);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 14px;
  font-size: 13px;
  color: var(--text-dim);
}
.encounter-edit-note strong { color: var(--text); }
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
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
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
.dialogue-question-text {
  min-width: 180px;
  outline: none;
  border-radius: 4px;
  padding: 1px 3px;
}
.dialogue-question-text:focus {
  background: #ffffff;
  box-shadow: inset 0 0 0 1px var(--accent);
}
.dialogue-tools {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 8px;
}
.dialogue-tools select,
.dialogue-tools input {
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 7px;
  color: var(--text);
  font-size: 12px;
}
.dialogue-tools input { min-width: 170px; }
.dialogue-tools .remove-dialogue {
  color: var(--red);
  border: 1px solid rgba(216,59,76,0.25);
  background: #fff7f8;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
}
.paste-panel {
  display: none;
  background: #fffdf7;
  border: 1px solid rgba(245,158,11,0.28);
  border-radius: 8px;
  padding: 14px;
  margin: 0 0 14px 0;
}
.paste-panel textarea {
  width: 100%;
  min-height: 150px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  font-size: 13px;
  color: var(--text);
  background: #ffffff;
  resize: vertical;
}
.paste-hint { font-size: 12px; color: var(--text-dim); margin-bottom: 8px; }
.parse-proof {
  background: #eefbf8;
  border: 1px solid rgba(15,118,110,0.18);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 0 0 12px 0;
  color: var(--text);
  font-size: 13px;
}
.parse-proof strong { color: var(--teal); }
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
.llm-role-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin-bottom: 14px; }
.llm-role-card { border: 1px solid rgba(207,226,234,0.85); background: #fbfefd; border-radius: 8px; padding: 10px; }
.llm-role-card.disabled { opacity: 0.72; background: #f8fafb; }
.llm-role-title { display:flex; align-items:center; justify-content:space-between; gap:8px; font-size: 12px; font-weight: 800; color: var(--text); margin-bottom: 5px; }
.llm-role-pill { font-size: 10px; text-transform: uppercase; letter-spacing: .04em; border-radius: 999px; padding: 3px 7px; background: #d8f4eb; color: #04745f; white-space: nowrap; }
.llm-role-card.disabled .llm-role-pill { background:#edf2f5; color:var(--text-dim); }
.llm-role-meta { font-size: 11px; color: var(--text-dim); line-height: 1.45; }
.llm-role-run { border-top: 1px solid rgba(207,226,234,0.75); padding-top: 10px; margin-top: 10px; }
.llm-role-run h5 { font-size: 12px; margin-bottom: 6px; color: var(--teal); }

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
.showcase-hero { background: linear-gradient(135deg, #ffffff 0%, #e9fbf7 56%, #fff5d7 100%); border: 1px solid rgba(172,220,218,0.95); border-radius: var(--radius); padding: 24px; margin-bottom: 18px; box-shadow: var(--shadow); }
.showcase-claim { font-size: 22px; font-weight: 700; line-height: 1.35; margin-bottom: 10px; }
.showcase-subclaim { color: var(--text-dim); font-size: 14px; max-width: 860px; }
.showcase-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
.showcase-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
.showcase-panel { background: rgba(255,255,255,0.92); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; box-shadow: 0 10px 24px rgba(31,97,114,0.08); }
.showcase-panel h3 { font-size: 14px; margin-bottom: 8px; color: var(--accent); }
.showcase-panel p { font-size: 13px; color: var(--text-dim); }
.showcase-proof-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
  margin-top: 18px;
}
.showcase-proof {
  background: rgba(255,255,255,0.82);
  border: 1px solid rgba(15,159,154,0.22);
  border-radius: 8px;
  padding: 12px;
}
.showcase-proof strong {
  display: block;
  font-size: 13px;
  margin-bottom: 3px;
}
.showcase-proof span {
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
.coverage-banner {
  background: linear-gradient(135deg, #ecfdf5 0%, #eff6ff 100%);
  border: 1px solid rgba(15,159,154,0.24);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-dim);
  margin-bottom: 8px;
}
.coverage-warning {
  background: var(--orange-bg);
  border: 1px solid rgba(217,119,6,0.25);
  color: #8a4b05;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 10px;
}
.coverage-table-wrap { overflow-x: auto; }
.coverage-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.coverage-table th {
  text-align: left;
  padding: 8px;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
}
.coverage-table td {
  vertical-align: top;
  padding: 9px 8px;
  border-bottom: 1px solid rgba(207,226,234,0.75);
}
.coverage-table small { color: var(--text-dim); }
.coverage-chip {
  display: inline-block;
  background: #f8fcfd;
  border: 1px solid rgba(207,226,234,0.85);
  border-radius: 999px;
  padding: 2px 7px;
  margin: 0 4px 4px 0;
  color: var(--text-dim);
}
.coverage-reclass {
  display: inline-block;
  background: var(--purple-bg);
  color: var(--purple);
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 11px;
  font-weight: 800;
}
.coverage-status {
  display: inline-block;
  border-radius: 999px;
  padding: 3px 8px;
  font-weight: 800;
  text-transform: uppercase;
  font-size: 10px;
}
.coverage-used, .coverage-context { background: var(--green-bg); color: var(--green); }
.coverage-red_flag, .coverage-hard_stop { background: var(--red-bg); color: var(--red); }
.coverage-review { background: var(--orange-bg); color: var(--orange); }
.recommendations-shell { display: grid; gap: 14px; }
.recommendation-hero {
  background: linear-gradient(135deg, #ffffff 0%, #ecfdf5 48%, #fff7ed 100%);
  border: 1px solid rgba(15,159,154,0.26);
  border-radius: var(--radius);
  padding: 18px;
  box-shadow: var(--shadow);
}
.recommendation-hero h2 { font-size: 20px; margin-bottom: 8px; }
.recommendation-bottom-line { font-size: 16px; font-weight: 800; margin: 8px 0; }
.recommendation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}
.recommendation-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
}
.recommendation-card h3 {
  font-size: 13px;
  color: var(--accent);
  margin-bottom: 8px;
  text-transform: uppercase;
}
.recommendation-card ul { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.55; }
.clinician-action-layout { display: grid; grid-template-columns: minmax(280px, .9fr) minmax(320px, 1.1fr); gap: 12px; }
@media (max-width: 860px) { .clinician-action-layout { grid-template-columns: 1fr; } }
.handoff-text { font-size: 14px; line-height: 1.55; }
.compact-boundary-list { display: grid; gap: 8px; }
.compact-boundary-list div {
  border-left: 3px solid var(--accent);
  background: #f8fcfd;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
}
.medical-director-note {
  background: #f8fcfd;
  border: 1px solid rgba(207,226,234,0.8);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-dim);
}
.evidence-row {
  border-left: 3px solid var(--accent);
  background: #f8fcfd;
  border-radius: 6px;
  padding: 9px 10px;
  margin-bottom: 8px;
  font-size: 13px;
}
.patient-script {
  background: #fffdf7;
  border: 1px solid rgba(245,158,11,0.25);
  border-radius: 8px;
  padding: 12px;
  font-size: 14px;
  line-height: 1.55;
}
.human-factor-card {
  border-color: rgba(114,90,193,0.28);
  background: linear-gradient(135deg, #ffffff 0%, #f7f5ff 55%, #f8fcfd 100%);
}
.human-spectrum {
  display: inline-block;
  margin: 2px 0 8px;
  padding: 6px 9px;
  border-radius: 999px;
  background: rgba(114,90,193,0.10);
  color: var(--purple);
  font-size: 12px;
}
.human-summary {
  font-size: 14px;
  line-height: 1.55;
  color: var(--text);
  margin-bottom: 10px;
}
.human-rule-row { margin: 8px 0 12px; }
.human-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
  margin-top: 10px;
}
.human-grid h4 {
  font-size: 12px;
  text-transform: uppercase;
  color: var(--text-dim);
  margin-bottom: 7px;
}
.human-prompt-details {
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-dim);
}
.human-prompt-details summary {
  cursor: pointer;
  font-weight: 800;
  color: var(--accent);
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
.method-stack-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 12px; margin-bottom: 14px; }
.method-stack-card {
  background: #fbfefd;
  border: 1px solid rgba(207,226,234,.92);
  border-radius: 8px;
  padding: 14px;
}
.method-stack-card h4 { font-size: 13px; margin-bottom: 8px; display:flex; justify-content:space-between; gap:8px; align-items:flex-start; }
.method-status { display:inline-block; border-radius: 999px; padding: 2px 8px; background: var(--accent-soft); color: var(--accent); font-size: 11px; font-weight: 800; white-space: nowrap; }
.method-result { font-size: 13px; font-weight: 700; margin-bottom: 6px; }
.method-evidence { font-size: 12px; color: var(--text-dim); }
.bias-grid { display:grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
@media (max-width: 768px) { .bias-grid { grid-template-columns: 1fr; } }
.bias-card { background: #f8f4ff; border: 1px solid rgba(124,58,237,.18); border-radius: 8px; padding: 12px; }
.bias-card h4 { color: var(--purple); font-size: 13px; margin-bottom: 8px; }
.bias-item { border-left: 3px solid var(--purple); background: white; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; font-size: 12px; }
</style>
</head>
<body>

<div class="header">
  <h1>Clinical Safety <span>Interactive Demo</span></h1>
  <div class="header-nav">
    <button id="nav-overview" onclick="showScreen('overview')">Overview</button>
    <button id="nav-cases" onclick="showScreen('cases')">Cases</button>
    <button id="nav-transcript" class="active" onclick="showScreen('transcript')">Start Transcript</button>
    <button id="nav-encounter" onclick="showScreen('encounter')">Encounter</button>
    <button id="nav-analysis" onclick="showScreen('analysis')">Analysis</button>
    <button id="nav-recommendations" onclick="showRecommendations()">Recommendations</button>
    <button id="nav-learning" onclick="showScreen('learning')">Governance</button>
  </div>
</div>

<!-- Screen 0: Transcript-first workflow -->
<div id="screen-transcript" class="screen active">
  <div class="transcript-intake-card">
    <h3>Start With A Real Transcript</h3>
    <p>Paste the encounter as one block, including demographics, history, medications, and the clinical dialogue. The app will infer the patient context, PMH, medication list, domain, source labels, concepts, and editable turns before analysis.</p>
    <label>Paste Transcript</label>
    <textarea id="quick-transcript" style="min-height:340px;" placeholder="Clinician: Mr. X can you tell me your age?
Patient: I’m 62.
Clinician: What medical conditions do you have?
Patient: T2DM, HTN, BPH.
Clinician: What medications are you taking?
Patient: GLP1, Losartan, Flomax, ibuprofen.
Clinician: Tell me about your back pain.
Patient: Lower back pain after lifting last week.
Clinician: Any numbness or tingling?
Patient: Yes, tingling in my left foot at times and in my private areas.
Clinician: Any weakness?
Patient: My legs feel weaker on stairs, but it may be the pain gets worse.
Clinician: Any issues with urination?
Patient: No but my bleeder seems more full than usual.
Clinician: Any loss of bowel control?
Patient: No.
Clinician: Is the pain getting worse?
Patient: No, but not getting better."></textarea>
    <div class="btn-row" style="margin-top:12px;">
      <button class="btn btn-primary" onclick="submitTranscriptCardCase()">Parse Transcript Encounter</button>
      <button class="btn btn-secondary" onclick="showScreen('cases')">Use Demo Case Library</button>
    </div>
    <div id="quick-transcript-proof" class="transcript-proof">This is the real-intake path: no separate clinician data-entry fields. The transcript should carry demographics, PMH, meds, symptoms, denials, uncertainty, and human context.</div>
  </div>
</div>

<!-- Screen 0: Overview -->
<div id="screen-overview" class="screen">
  <div class="showcase-hero">
    <div class="showcase-claim">Not an AI doctor. A learning autonomy-boundary layer around an AI doctor.</div>
    <div class="showcase-subclaim">This demo now shows the mitigation stack explicitly: deterministic controls today, plus stigmergic boundary traces and VAMS near-miss recall as the next governed learning layer.</div>
    <div class="showcase-proof-strip">
      <div class="showcase-proof"><strong>Curated rules</strong><span>Enforced: can route, ask, block, or cap autonomy.</span></div>
      <div class="showcase-proof"><strong>AI candidates</strong><span>Advisory: suggest signals but cannot decide alone.</span></div>
      <div class="showcase-proof"><strong>Memory / priors</strong><span>Bounded: tune questions and propose falsifiers.</span></div>
      <div class="showcase-proof"><strong>Ensemble governor</strong><span>Most restrictive state wins every time.</span></div>
    </div>
    <div class="showcase-actions">
      <button class="btn btn-primary" onclick="selectCaseById('showcase-001-stale-ace-refill-ckd-nsaid')">Run Hero Refill Case</button>
      <button class="btn btn-secondary" onclick="selectCaseById('RF-002-good-refill-readyish')">Compare Clean Refill</button>
      <button class="btn btn-secondary" onclick="selectCaseById('showcase-003-cost-fear-minimizes-alarm')">Show Cost-Fear Case</button>
      <button class="btn btn-secondary" onclick="selectCaseById('showcase-009-embarrassment-curbs-history')">Show Embarrassment/Fear Case</button>
      <button class="btn btn-secondary" onclick="selectCaseById('showcase-010-defense-pattern-distortion')">Show Defense-Pattern Case</button>
      <button class="btn btn-secondary" onclick="showScreen('cases')">Full Case Library</button>
    </div>
  </div>
  <div class="showcase-grid">
    <div class="showcase-panel">
      <h3>What This Adds</h3>
      <p>Separates patient statements from clinical facts, then bounds what the AI is allowed to infer.</p>
    </div>
    <div class="showcase-panel">
      <h3>Why It Matters</h3>
      <p>At scale, subtle failures often come from silence, stale evidence, denial reliability, defense mechanisms, embarrassment, stigma, fear, or patient-shaped conversations.</p>
    </div>
    <div class="showcase-panel">
      <h3>Operating Leverage</h3>
      <p>One targeted clarification can preserve safe automation, reduce avoidable physician review, and explain paid routing more clearly.</p>
    </div>
    <div class="showcase-panel">
      <h3>New: Mitigation Memory</h3>
      <p>Every analyzed case now shows boundary traces, VAMS-style near-miss recall, falsifiers, governance promotion, and churn/routing mitigation.</p>
    </div>
    <div class="showcase-panel">
      <h3>Human Disclosure Pressure</h3>
      <p>Patients may curb history because they are embarrassed, fear a bad outcome, misunderstand what matters, or are trying to make the answer less alarming.</p>
    </div>
    <div class="showcase-panel">
      <h3>Defense Pattern Distortion</h3>
      <p>Answers can swing between anxiety-driven amplification and stoic denial. The system extracts concrete timing, function, and objective facts before trusting either frame.</p>
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
      <div id="paste-panel" class="paste-panel">
        <div class="paste-hint"><strong>Paste real encounter text.</strong> Supports Q/A pairs, Clinician/Patient labels, or alternating prompt/response lines. Imported turns become editable before analysis.</div>
        <textarea id="paste-transcript" placeholder="Example:\nClinician: Do you have chest pain?\\nPatient: No, just tight indigestion when I walk.\nClinician: Any shortness of breath?\\nPatient: Not really, I slow down so it does not get bad."></textarea>
        <div class="btn-row" style="margin-top:10px;">
          <button class="btn btn-secondary btn-sm" onclick="togglePastePanel(false)">Cancel</button>
          <button class="btn btn-secondary btn-sm" onclick="importTranscript(false)">Append To Encounter</button>
          <button class="btn btn-primary btn-sm" onclick="importTranscript(true)">Replace Encounter</button>
        </div>
      </div>
      <div id="dialogue-area" class="dialogue-area"></div>
      <div class="btn-row">
        <button class="btn btn-secondary" onclick="showScreen('cases')">Back to Cases</button>
        <button class="btn btn-secondary" onclick="togglePastePanel(true)">Paste Transcript</button>
        <button class="btn btn-secondary" onclick="addDialogueTurn()">Add Dialogue</button>
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
      <div class="proof-title">Processing Transparency</div>
      <div class="proof-subtitle">Section 2 labels curated rules, AI candidates, learned priors, memory recall, and the ensemble autonomy governor.</div>
    </div>
    <span class="authority-chip authority-Enforced">Transparency layer active</span>
  </div>
  <div id="analysis-summary"></div>
  <div id="analysis-sections"></div>
  <div class="btn-row" id="analysis-actions" style="display:none;">
    <button class="btn btn-secondary" onclick="showScreen('encounter')">Edit Encounter</button>
    <button class="btn btn-primary" onclick="showRecommendations()">Final Recommendations</button>
    <button class="btn btn-primary" onclick="showScreen('learning')">Governance Review</button>
  </div>
</div>

<!-- Screen 4: Final Recommendations -->
<div id="screen-recommendations" class="screen">
  <div id="recommendations-content"></div>
  <div class="btn-row">
    <button class="btn btn-secondary" onclick="showScreen('analysis')">Back to Analysis</button>
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
          <option value="adhd_behavioral_med">ADHD / Behavioral Medication</option>
          <option value="asthma_allergy">Asthma / Allergy</option>
          <option value="chest_discomfort">Chest Discomfort</option>
          <option value="diabetes_hyperglycemia">Diabetes / Hyperglycemia</option>
          <option value="dyspnea_respiratory">Dyspnea/Respiratory</option>
          <option value="eye_ear">Eye / Ear</option>
          <option value="followup_lab_review">Follow-up / Lab Review</option>
          <option value="general_med_management">General Medication Management</option>
          <option value="gerd_dyspepsia">GERD / Dyspepsia</option>
          <option value="gi_symptoms">GI Symptoms</option>
          <option value="headache_migraine">Headache/Migraine</option>
          <option value="med_refill_hypertension">Med Refill/Hypertension</option>
          <option value="mental_health">Mental Health</option>
          <option value="musculoskeletal_pain">Musculoskeletal Pain</option>
          <option value="obesity_metabolic">Obesity / Metabolic Care</option>
          <option value="uti_symptoms">UTI Symptoms</option>
          <option value="routine_dermatology">Routine Dermatology</option>
          <option value="rash">Rash</option>
          <option value="skin_infection">Skin Infection</option>
          <option value="uri_sinus_throat">URI / Sinus / Throat</option>
          <option value="vaginal_sti">Vaginal / STI</option>
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
          <option value="adhd_behavioral_med">ADHD / Behavioral Medication</option>
          <option value="asthma_allergy">Asthma / Allergy</option>
          <option value="chest_discomfort">Chest Discomfort</option>
          <option value="diabetes_hyperglycemia">Diabetes / Hyperglycemia</option>
          <option value="dyspnea_respiratory">Dyspnea/Respiratory</option>
          <option value="eye_ear">Eye / Ear</option>
          <option value="followup_lab_review">Follow-up / Lab Review</option>
          <option value="general_med_management">General Medication Management</option>
          <option value="gerd_dyspepsia">GERD / Dyspepsia</option>
          <option value="gi_symptoms">GI Symptoms</option>
          <option value="headache_migraine">Headache/Migraine</option>
          <option value="med_refill_hypertension">Med Refill/Hypertension</option>
          <option value="mental_health">Mental Health</option>
          <option value="musculoskeletal_pain">Musculoskeletal Pain</option>
          <option value="obesity_metabolic">Obesity / Metabolic Care</option>
          <option value="uti_symptoms">UTI Symptoms</option>
          <option value="routine_dermatology">Routine Dermatology</option>
          <option value="rash">Rash</option>
          <option value="skin_infection">Skin Infection</option>
          <option value="uri_sinus_throat">URI / Sinus / Throat</option>
          <option value="vaginal_sti">Vaginal / STI</option>
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
      <div class="transcript-intake-card" style="box-shadow:none;margin:0 0 12px;padding:14px;">
        <h3 style="font-size:14px;">Transcript Import</h3>
        <p>Paste encounter text here to auto-create editable statement rows. The imported source and concept fields are then used by the analysis engine.</p>
        <textarea id="builder-transcript" placeholder="Clinician: What is worrying you most?&#10;Patient: I am embarrassed and worried this could be cancer.&#10;Clinician: Any bleeding?&#10;Patient: I do not want to answer that here."></textarea>
        <div class="btn-row" style="margin-top:10px;">
          <button class="btn btn-secondary btn-sm" onclick="parseBuilderTranscript(false)">Append Transcript Rows</button>
          <button class="btn btn-primary btn-sm" onclick="parseBuilderTranscript(true)">Replace Rows From Transcript</button>
        </div>
        <div id="builder-parse-proof" class="transcript-proof">Transcript rows remain editable before loading the encounter.</div>
      </div>
      <div class="field-purpose-note"><strong>Why Source and Concept matter:</strong> Source changes reliability scoring and source-conflict detection. Concept maps the statement into the expert-system slot, missing-data rule, contradiction rule, VAMS/experience lookup, and next-question generator. Leave Concept blank when you want governed inference.</div>
      <div id="builder-stmts">
        <div class="builder-stmt" data-idx="0">
          <span class="remove-stmt" onclick="removeBuilderStmt(this)">remove</span>
          <label>Question</label>
          <input class="stmt-q" placeholder="e.g., Describe your chest discomfort">
          <label>Answer</label>
          <input class="stmt-a" placeholder="e.g., It feels like heartburn">
          <label>Source</label>
          <select class="stmt-src"><option value="patient">patient</option><option value="caregiver">caregiver</option><option value="device">device</option><option value="chart">chart</option><option value="clinician">clinician</option></select>
          <label>Concept</label>
          <input class="stmt-concept" placeholder="optional; inferred if blank">
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

function resetSessionForNewEncounter() {
  currentAnalysis = null;
  feedbackSelections = {};
  const rec = document.getElementById('recommendations-content');
  if (rec) rec.innerHTML = '';
  const analysisSummary = document.getElementById('analysis-summary');
  if (analysisSummary) analysisSummary.innerHTML = '';
  const analysisSections = document.getElementById('analysis-sections');
  if (analysisSections) analysisSections.innerHTML = '';
  const analysisActions = document.getElementById('analysis-actions');
  if (analysisActions) analysisActions.style.display = 'none';
  const paste = document.getElementById('paste-transcript');
  if (paste) paste.value = '';
  togglePastePanel(false);
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
    resetSessionForNewEncounter();
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
  const medications = (c.case_data.ground_truth || {}).medications || [];
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
  if (medications.length) {
    bannerHtml += '<div class="ctx-item"><span class="ctx-label">Meds:</span><span class="ctx-value">' + esc(medications.join(', ')) + '</span></div>';
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
  let dHtml = '<div class="encounter-edit-note"><strong>Live encounter input.</strong> Edit any question or answer, add real dialogue turns, then analyze. Blank concept fields are inferred from the question and answer when possible.</div>';
  if (c.parse_proof) {
    dHtml += '<div class="parse-proof"><strong>Live input parsed:</strong> ' + esc(c.parse_proof.summary) + '</div>';
  }
  for (let i = 0; i < stmts.length; i++) {
    const s = stmts[i];
    dHtml += renderDialoguePair(s, i);
  }
  if (!stmts.length) {
    dHtml += '<div class="empty-state">No statements in this case. Add dialogue below.</div>';
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

function renderDialoguePair(s, i) {
    let dHtml = '<div class="dialogue-pair" data-idx="' + i + '">';
    dHtml += '<div class="dialogue-q">';
    dHtml += '<span class="q-number">' + (i + 1) + '.</span> ';
    dHtml += '<span class="dialogue-question-text" contenteditable="true">' + esc(s.question || '') + '</span>';
    if (s.concept) dHtml += ' <span class="concept-tag">' + esc(s.concept) + '</span>';
    dHtml += '</div>';
    dHtml += '<div class="dialogue-a" contenteditable="true" data-idx="' + i + '" data-source="' + esc(s.source || 'patient') + '">';
    dHtml += esc(s.answer || '');
    if (s.source && s.source !== 'patient') dHtml += ' <span class="source-tag">[' + esc(s.source) + ']</span>';
    dHtml += '</div>';
    dHtml += '<div class="dialogue-tools">';
    dHtml += '<label>Source <select class="dialogue-source"><option value="patient"' + ((s.source || 'patient') === 'patient' ? ' selected' : '') + '>patient</option><option value="caregiver"' + (s.source === 'caregiver' ? ' selected' : '') + '>caregiver</option><option value="device"' + (s.source === 'device' ? ' selected' : '') + '>device</option><option value="chart"' + (s.source === 'chart' ? ' selected' : '') + '>chart</option><option value="clinician"' + (s.source === 'clinician' ? ' selected' : '') + '>clinician</option></select></label>';
    dHtml += '<label>Concept <input class="dialogue-concept" value="' + esc(s.concept || '') + '" placeholder="optional; inferred if blank"></label>';
    dHtml += '<button class="remove-dialogue" onclick="removeDialogueTurn(this)">Remove</button>';
    dHtml += '</div>';
    dHtml += '</div>';
    return dHtml;
}

function reindexDialogueTurns() {
  document.querySelectorAll('#dialogue-area .dialogue-pair').forEach((pair, i) => {
    pair.setAttribute('data-idx', i);
    const qNum = pair.querySelector('.q-number');
    if (qNum) qNum.textContent = (i + 1) + '.';
    const answer = pair.querySelector('.dialogue-a');
    if (answer) answer.setAttribute('data-idx', i);
  });
}

function addDialogueTurn() {
  const area = document.getElementById('dialogue-area');
  const idx = document.querySelectorAll('#dialogue-area .dialogue-pair').length;
  area.insertAdjacentHTML('beforeend', renderDialoguePair({
    question: 'Add the intake question or clinician prompt here',
    answer: 'Add the patient, caregiver, device, or chart statement here',
    concept: '',
    source: 'patient'
  }, idx));
  reindexDialogueTurns();
}

function removeDialogueTurn(btn) {
  const pair = btn.closest('.dialogue-pair');
  if (pair) pair.remove();
  reindexDialogueTurns();
}

function togglePastePanel(show) {
  const panel = document.getElementById('paste-panel');
  if (!panel) return;
  panel.style.display = show ? 'block' : 'none';
  if (show) {
    const ta = document.getElementById('paste-transcript');
    if (ta) ta.focus();
  }
}

function cleanSpeakerLine(line) {
  return line.replace(/^\\s*(clinician|doctor|provider|nurse|assistant|system|ai|patient|pt|caregiver|daughter|son|mom|mother|father|device|chart)\\s*[:\\-]\\s*/i, '').trim();
}

function speakerForLine(line) {
  const m = line.match(/^\\s*([A-Za-z ]{1,20})\\s*[:\\-]\\s*/);
  if (!m) return '';
  const label = m[1].trim().toLowerCase();
  if (['patient', 'pt'].includes(label)) return 'patient';
  if (['caregiver', 'daughter', 'son', 'mom', 'mother', 'father'].includes(label)) return 'caregiver';
  if (['device'].includes(label)) return 'device';
  if (['chart'].includes(label)) return 'chart';
  if (['clinician', 'doctor', 'provider', 'nurse', 'assistant', 'system', 'ai'].includes(label)) return 'clinician';
  return '';
}

async function parseTranscriptServer(text) {
  const resp = await fetch(API + '/demo/parse-transcript', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript: text })
  });
  if (!resp.ok) throw new Error('transcript parse failed');
  return await resp.json();
}

function parseTranscript(text) {
  const lines = String(text || '').split(/\\r?\\n/).map(x => x.trim()).filter(Boolean);
  const turns = [];
  let pendingQuestion = '';
  for (const line of lines) {
    const inlineQa = line.match(/^\\s*(?:Q(?:uestion)?|Clinician|Doctor|Provider|Nurse|Assistant|AI|System)\\s*[:\\-]\\s*(.*?)\\s+\\bA(?:nswer)?\\s*[:\\-]\\s*(.*)$/i);
    const qa = line.match(/^\\s*(?:Q(?:uestion)?|Clinician|Doctor|Provider|Nurse|Assistant|AI|System)\\s*[:\\-]\\s*(.*?)\\s*$/i);
    const aa = line.match(/^\\s*(?:A(?:nswer)?|Patient|Pt|Caregiver|Daughter|Son|Mom|Mother|Father|Device|Chart)\\s*[:\\-]\\s*(.*)$/i);
    const speaker = speakerForLine(line);
    if (inlineQa) {
      turns.push({ question: inlineQa[1].trim(), answer: inlineQa[2].trim(), concept: null, source: 'patient', metadata: { imported_from_transcript: true } });
      pendingQuestion = '';
    } else if (qa && !aa) {
      pendingQuestion = cleanSpeakerLine(line);
    } else if (aa) {
      const source = speaker && speaker !== 'clinician' ? speaker : 'patient';
      turns.push({ question: pendingQuestion || 'Patient statement', answer: aa[1].trim(), concept: null, source, metadata: { imported_from_transcript: true } });
      pendingQuestion = '';
    } else if (speaker === 'clinician') {
      pendingQuestion = cleanSpeakerLine(line);
    } else if (speaker) {
      turns.push({ question: pendingQuestion || 'Patient statement', answer: cleanSpeakerLine(line), concept: null, source: speaker === 'clinician' ? 'patient' : speaker, metadata: { imported_from_transcript: true } });
      pendingQuestion = '';
    } else if (pendingQuestion) {
      turns.push({ question: pendingQuestion, answer: line, concept: null, source: 'patient', metadata: { imported_from_transcript: true } });
      pendingQuestion = '';
    } else if (line.endsWith('?')) {
      pendingQuestion = line;
    } else {
      turns.push({ question: 'Patient statement', answer: line, concept: null, source: 'patient', metadata: { imported_from_transcript: true } });
    }
  }
  if (pendingQuestion) turns.push({ question: pendingQuestion, answer: '', concept: null, source: 'patient', metadata: {} });
  return turns.filter(t => (t.question || t.answer) && t.answer !== '');
}

async function importTranscript(replace) {
  const ta = document.getElementById('paste-transcript');
  const text = ta ? ta.value : '';
  let parsed = [];
  let parseData = null;
  try {
    parseData = await parseTranscriptServer(text);
    parsed = parseData.statements || [];
  } catch (e) {
    parsed = parseTranscript(text);
  }
  if (!parsed.length) {
    showToast('No dialogue turns found in pasted text.');
    return;
  }
  const existing = replace ? [] : collectEncounterStatements();
  currentCase.case_data.statements = existing.concat(parsed);
  const sources = (parseData && parseData.sources ? parseData.sources : Array.from(new Set(parsed.map(t => t.source || 'patient')))).join(', ');
  const concepts = (parseData && parseData.concepts ? parseData.concepts : Array.from(new Set(parsed.map(t => t.concept || 'unknown')))).join(', ');
  const inferred = parsed.filter(t => !t.concept).length;
  currentCase.parse_proof = {
    summary: parsed.length + ' pasted turn(s) ' + (replace ? 'replaced the encounter' : 'appended to the encounter') + '; sources: ' + sources + '; concepts: ' + concepts + '; ' + inferred + ' concept field(s) left blank for governed inference.'
  };
  renderEncounter();
  togglePastePanel(false);
  showToast((replace ? 'Replaced' : 'Added') + ' ' + parsed.length + ' dialogue turn(s).');
}

async function submitTranscriptCardCase() {
  const text = (document.getElementById('quick-transcript') || {}).value || '';
  if (!text.trim()) {
    showToast('Paste a transcript first.');
    return;
  }
  let parseData = null;
  let stmts = [];
  try {
    parseData = await parseTranscriptServer(text);
    stmts = parseData.statements || [];
  } catch (e) {
    stmts = parseTranscript(text);
  }
  if (!stmts.length) {
    showToast('No dialogue turns found in transcript.');
    return;
  }

  const parsedCtx = parseData && parseData.patient_context ? parseData.patient_context : {};
  const domain = parsedCtx.domain || 'general_med_management';
  const age = parseInt(parsedCtx.age) || 50;
  const concern = parsedCtx.chief_concern || 'transcript encounter';
  const modality = parsedCtx.modality || 'text';
  const conditions = parsedCtx.known_conditions || [];
  const medications = parseData && parseData.medications ? parseData.medications : [];
  const id = 'TRANSCRIPT-' + Date.now();
  const concepts = parseData && parseData.concepts ? parseData.concepts.join(', ') : Array.from(new Set(stmts.map(s => s.concept || 'unknown'))).join(', ');
  const parsedSummary = 'Parsed age ' + age + '; domain ' + domain.replace(/_/g, ' ') + '; PMH ' + (conditions.length ? conditions.join(', ') : 'not stated') + '; meds ' + (medications.length ? medications.join(', ') : 'not stated') + '; concepts ' + concepts + '.';

  const customCase = {
    case_id: id,
    title: 'Transcript Case',
    scenario: concern,
    category: 'custom',
    category_label: 'Custom',
    domain: domain,
    age: age,
    modality: modality,
    chief_concern: concern,
    jre_demonstrates: 'Free-text transcript is converted into editable, source-aware observations before safety analysis.',
    bsg_demonstrates: 'Sentinel and boundary rules run on every imported statement, including untemplated added details.',
    combined_insight: 'The transcript is not treated as a static demo script; it becomes the active encounter payload.',
    parse_proof: {
      summary: stmts.length + ' transcript turn(s) parsed. ' + parsedSummary + ' External LLM analysis runs after governed analysis.'
    },
    case_data: {
      case_id: id,
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
      ground_truth: { medications: medications, transcript_imported: true },
    }
  };
  const proof = document.getElementById('quick-transcript-proof');
  if (proof) proof.textContent = customCase.parse_proof.summary;
  selectCase(customCase);
}

function collectEncounterStatements() {
  const stmts = [];
  document.querySelectorAll('#dialogue-area .dialogue-pair').forEach((pair) => {
    const qEl = pair.querySelector('.dialogue-question-text');
    const aEl = pair.querySelector('.dialogue-a');
    const sourceEl = pair.querySelector('.dialogue-source');
    const conceptEl = pair.querySelector('.dialogue-concept');
    const question = qEl ? qEl.textContent.trim() : '';
    const answer = aEl ? aEl.textContent.replace(/\\[.*?\\]$/, '').trim() : '';
    const source = sourceEl ? sourceEl.value : 'patient';
    const concept = conceptEl && conceptEl.value.trim() ? conceptEl.value.trim() : null;
    if (question || answer) {
      stmts.push({ question, answer, concept, source, metadata: {} });
    }
  });
  currentCase.case_data.statements = stmts;
  return stmts;
}

// ---------------------------------------------------------------------------
// Screen 3: Analyze encounter
// ---------------------------------------------------------------------------
async function analyzeEncounter() {
  const btn = document.getElementById('analyze-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Analyzing...';

  // Read edited and newly added dialogue turns
  const stmts = collectEncounterStatements();

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
    case 'method_stack': el.innerHTML = renderMethodStack(section.data); break;
    case 'interpretation_boundaries': el.innerHTML = renderInterpretationBoundaries(section.data); break;
    case 'input_coverage': el.innerHTML = renderInputCoverage(section.data); break;
    case 'observations': el.innerHTML = renderObservations(section.data); break;
    case 'mud_map': el.innerHTML = renderMudMap(section.data); break;
    case 'red_flags': el.innerHTML = renderRedFlags(section.data); break;
    case 'uncertainty_graph': el.innerHTML = renderUncertaintyGraph(section.data); break;
    case 'jri_score': el.innerHTML = renderJRI(section.data); break;
    case 'guardrails': el.innerHTML = renderGuardrails(section.data); break;
    case 'reasoning_integrity': el.innerHTML = renderReasoningIntegrity(section.data); break;
    case 'safety_decision': el.innerHTML = renderSafetyDecision(section.data); break;
    case 'provenance_authority': el.innerHTML = renderProvenanceAuthority(section.data); break;
    case 'autonomy_boundary': el.innerHTML = renderAutonomyBoundary(section.data); break;
    case 'next_questions': el.innerHTML = renderQuestions(section.data); break;
    case 'mitigation_plan': el.innerHTML = renderMitigationPlan(section.data); break;
    case 'llm_opinion': renderLLMSection(section.data); break;
  }
}

// Section renderers
function renderMethodStack(data) {
  let h = '<div class="coverage-banner"><strong>Live input signature:</strong> ' + esc(data.input_signature.statement_count) + ' statement(s), domain ' + esc(String(data.input_signature.domain || '').replace(/_/g, ' ')) + ', sources ' + esc((data.input_signature.sources || []).join(', ')) + '. These are computed from the current encounter, not static copy.</div>';
  h += '<div class="method-stack-grid">';
  for (const method of data.applied_methods || []) {
    h += '<div class="method-stack-card">';
    h += '<h4><span>' + esc(method.name) + '</span><span class="method-status">' + esc(method.status) + '</span></h4>';
    h += '<div class="method-result">' + esc(method.result) + '</div>';
    h += '<div class="method-evidence">' + esc(method.evidence) + '</div>';
    h += '</div>';
  }
  h += '</div>';

  const anyDispo = data.any_dispo || {};
  h += '<div class="clinician-action-layout">';
  h += '<div class="recommendation-card"><h3>Any Dispo Review Output</h3>';
  h += '<div class="evidence-row"><strong>State:</strong> ' + esc(anyDispo.state || '') + '<br><span style="color:var(--text-dim)">Proposed destination stress test: ' + esc(anyDispo.proposed_destination || '') + '</span></div>';
  for (const item of (anyDispo.hard_blockers || []).slice(0, 5)) h += '<div class="evidence-row"><strong>Blocker</strong><br>' + esc(item) + '</div>';
  for (const item of (anyDispo.capability_gaps || []).slice(0, 4)) h += '<div class="evidence-row"><strong>Capability gap</strong><br>' + esc(item) + '</div>';
  for (const item of (anyDispo.missing_evidence || []).slice(0, 4)) h += '<div class="evidence-row"><strong>Missing evidence</strong><br>' + esc(item) + '</div>';
  if (!(anyDispo.hard_blockers || []).length && !(anyDispo.capability_gaps || []).length && !(anyDispo.missing_evidence || []).length) h += '<div class="empty-state">No major any-disposition blocker detected for this stress test.</div>';
  h += '</div>';

  const cbf = data.cognitive_bias_field || {};
  h += '<div class="recommendation-card"><h3>Cognitive Bias Field Output</h3>';
  h += '<div class="evidence-row"><strong>Bias entropy:</strong> ' + Number(cbf.bias_entropy_score || 0).toFixed(1) + '<br><span style="color:var(--text-dim)">Authority: ' + esc(cbf.authority || 'Advisory') + '</span></div>';
  for (const bias of (cbf.dominant_biases || []).slice(0, 4)) {
    h += '<div class="evidence-row"><strong>' + esc(bias.label) + '</strong> ' + Number(bias.score || 0).toFixed(1) + '<br>' + esc(bias.evidence || '') + '<br><span style="color:var(--text-dim)">' + esc(bias.mitigation || '') + '</span></div>';
  }
  h += '</div></div>';

  h += '<div class="bias-grid">';
  h += '<div class="bias-card"><h4>Information-Gain Candidates</h4>';
  for (const q of (cbf.information_gain_candidates || []).slice(0, 5)) {
    h += '<div class="bias-item"><strong>' + esc(q.target || '') + '</strong> (' + esc(q.yield_class || '') + ')<br>' + esc(q.rationale || '') + '</div>';
  }
  if (!(cbf.information_gain_candidates || []).length) h += '<div class="empty-state">No high-yield uncertainty reducer identified.</div>';
  h += '</div>';
  h += '<div class="bias-card"><h4>Fresh-Eyes / Friction Actions</h4>';
  for (const action of (cbf.friction_actions || []).slice(0, 5)) {
    h += '<div class="bias-item"><strong>' + esc(action.label || '') + '</strong><br>' + esc(action.reason || '') + '<br><span style="color:var(--text-dim)">' + esc(action.prompt || '') + '</span></div>';
  }
  if (cbf.fresh_eyes_payload && cbf.fresh_eyes_payload.prompt) {
    h += '<details style="margin-top:8px;"><summary style="cursor:pointer;font-weight:800;">Fresh-eyes prompt</summary><div style="font-size:12px;margin-top:6px;color:var(--text-dim);">' + esc(cbf.fresh_eyes_payload.prompt) + '</div></details>';
  }
  h += '</div></div>';
  return h;
}

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

function renderInputCoverage(data) {
  let h = '<div class="coverage-banner"><strong>' + esc(data.total_lines || 0) + ' input line(s) audited.</strong> ' + esc(data.invariant || '') + '</div>';
  if (data.review_or_unmapped) {
    h += '<div class="coverage-warning">' + esc(data.review_or_unmapped) + ' line(s) require classification/review before they can support closure.</div>';
  }
  h += '<div class="coverage-table-wrap"><table class="coverage-table"><thead><tr><th>Line</th><th>Input</th><th>Concept Path</th><th>Used By</th><th>Safety Effect</th><th>Status</th></tr></thead><tbody>';
  for (const row of data.rows || []) {
    h += '<tr>';
    h += '<td>' + esc(row.line) + '</td>';
    h += '<td><strong>' + esc(row.question || 'Statement') + '</strong><br><span>' + esc(row.answer || '') + '</span><br><small>source: ' + esc(row.source || '') + '</small></td>';
    h += '<td><small>supplied: ' + esc(row.supplied_concept || '') + '</small><br><small>inferred: ' + esc(row.inferred_concept || '') + '</small><br><strong>' + esc(row.effective_concept || '') + '</strong>' + (row.reclassified ? '<br><span class="coverage-reclass">reclassified</span>' : '') + '</td>';
    h += '<td>';
    for (const c of row.consumers || []) h += '<span class="coverage-chip">' + esc(c) + '</span>';
    h += '</td>';
    h += '<td>' + esc(row.safety_effect || '') + '</td>';
    h += '<td><span class="coverage-status coverage-' + esc(row.status || 'used') + '">' + esc(String(row.status || 'used').replace(/_/g, ' ')) + '</span></td>';
    h += '</tr>';
  }
  h += '</tbody></table></div>';
  return h;
}

function showRecommendations() {
  if (!currentAnalysis || !currentAnalysis.recommendations) {
    showToast('Run analysis first.');
    return;
  }
  document.getElementById('recommendations-content').innerHTML = renderRecommendations(currentAnalysis.recommendations);
  showScreen('recommendations');
}

function renderRecommendations(data) {
  let h = '<div class="recommendations-shell">';
  h += '<div class="recommendation-hero">';
  h += '<div><span class="state-badge state-' + esc(data.disposition) + '">' + esc(String(data.disposition).replace(/_/g, ' ')) + '</span></div>';
  h += '<h2>' + esc(data.title || 'Final Recommendations') + '</h2>';
  h += '<div style="font-size:13px;color:var(--text-dim);">' + esc(data.case_title || data.case_id || '') + '</div>';
  h += '<div class="recommendation-bottom-line">' + esc(data.bottom_line || '') + '</div>';
  h += '<div style="font-size:13px;color:var(--text-dim);">Autonomy: <strong>' + esc(data.autonomy_tier || '') + '</strong> — ' + esc(data.autonomy_description || '') + '</div>';
  h += '</div>';

  h += '<div class="clinician-action-layout">';
  h += '<div class="recommendation-card"><h3>Immediate Actions</h3><ul>';
  for (const item of data.immediate_actions || []) h += '<li>' + esc(item) + '</li>';
  h += '</ul></div>';
  h += '<div class="recommendation-card"><h3>Clinician Handoff</h3><div class="handoff-text">' + esc(data.clinician_handoff || '') + '</div></div>';
  h += '</div>';

  h += '<div class="recommendation-card"><h3>Why This Is Not Canned</h3>';
  h += '<div class="medical-director-note">This page is rendered from the most recent /demo/analyze response. It uses the current encounter state, top JRE findings, Black Swan guardrails, cognitive forcing actions, human-factor boundary, and governance outputs. If the encounter is edited and analyzed again, these recommendations change.</div>';
  h += '</div>';

  if ((data.critical_evidence || []).length) {
    h += '<div class="recommendation-card"><h3>Critical Evidence Driving The Recommendation</h3>';
    for (const ev of (data.critical_evidence || []).slice(0, 8)) {
      h += '<div class="evidence-row"><strong>' + esc(ev.signal || ev.rule || '') + '</strong> ' + authorityChip(ev.authority) + '<br>' + esc(ev.why || '') + '<br><span style="color:var(--text-dim)">' + esc(ev.rule || '') + '</span></div>';
    }
    h += '</div>';
  }

  h += '<div class="recommendation-card"><h3>Patient-Facing Message</h3><div class="patient-script">' + esc(data.patient_message || '') + '</div></div>';

  if (data.human_factors) h += renderHumanFactorsRecommendation(data.human_factors);

  if (data.reasoning_integrity && (data.reasoning_integrity.actions || []).length) {
    h += '<div class="recommendation-card"><h3>Reasoning Integrity / Cognitive Forcing</h3>';
    h += '<div class="medical-director-note" style="margin-bottom:10px;">' + esc(data.reasoning_integrity.summary || '') + '</div>';
    for (const a of data.reasoning_integrity.actions || []) {
      h += '<div class="evidence-row"><strong>' + esc(a.bias || '') + '</strong><br>' + esc(a.action || '') + '<br><span style="color:var(--text-dim)">' + esc(a.question || '') + '</span></div>';
    }
    h += '</div>';
  }

  h += '<div class="clinician-action-layout">';
  h += '<div class="recommendation-card"><h3>Next Questions / Routing Support</h3>';
  for (const q of data.next_questions || []) {
    h += '<div class="evidence-row"><strong>' + esc(q.target) + '</strong><br>' + esc(q.question) + '<br><span style="color:var(--text-dim)">' + esc(q.why) + '</span></div>';
  }
  h += '</div>';
  h += '<div class="recommendation-card"><h3>Do Not Infer</h3><div class="compact-boundary-list">';
  const boundaryItems = (data.do_not_infer || []).slice(0, 4);
  for (const item of boundaryItems) h += '<div>' + esc(item) + '</div>';
  if (!boundaryItems.length) h += '<div>No major unsafe inference boundary identified.</div>';
  h += '</div></div>';
  h += '</div>';

  h += '<div class="recommendation-card"><h3>Medical Director / Governance Note</h3>';
  h += '<div class="medical-director-note">Supporting evidence, provenance, VAMS-style memory recall, human-factor boundary details, and LLM candidate findings are on the Analysis page. This page is intentionally limited to action, handoff, patient language, and the few boundaries that should change clinician behavior now.</div>';
  h += '</div>';

  if ((data.governance_actions || []).length || (data.quality_metrics || []).length) {
    h += '<div class="clinician-action-layout">';
    h += '<div class="recommendation-card"><h3>Governance Actions</h3><ul>';
    for (const item of data.governance_actions || []) h += '<li>' + esc(item) + '</li>';
    h += '</ul></div>';
    h += '<div class="recommendation-card"><h3>Validation Metrics To Capture</h3><ul>';
    for (const item of data.quality_metrics || []) h += '<li>' + esc(item) + '</li>';
    h += '</ul></div>';
    h += '</div>';
  }

  if (data.ai_processing) {
    h += '<div class="recommendation-card"><h3>AI / Model Authority Boundary</h3>';
    h += '<div class="medical-director-note">' + esc(data.ai_processing.current_authority || '') + '</div>';
    h += '<ul>';
    for (const item of data.ai_processing.prompt_contract || []) h += '<li>' + esc(item) + '</li>';
    h += '</ul></div>';
  }
  h += '</div>';
  return h;
}

function renderHumanFactorsRecommendation(data) {
  let h = '<div class="recommendation-card human-factor-card">';
  h += '<h3>' + esc(data.title || 'Human Factors Boundary') + '</h3>';
  h += '<div class="human-spectrum"><strong>Spectrum:</strong> ' + esc(data.spectrum || 'No explicit pattern detected') + '</div>';
  h += '<div class="human-summary">' + esc(data.summary || '') + '</div>';
  if ((data.triggered_rules || []).length) {
    h += '<div class="human-rule-row">';
    for (const r of data.triggered_rules || []) h += '<span class="provenance-token">' + esc(r) + '</span>';
    h += '</div>';
  }
  h += '<div class="human-grid">';
  h += '<div><h4>Detected Cues</h4>';
  if ((data.cues || []).length) {
    for (const cue of data.cues || []) h += '<div class="evidence-row"><strong>' + esc(cue.label) + '</strong><br><span style="color:var(--text-dim)">' + esc(cue.why) + '</span></div>';
  } else {
    h += '<div class="empty-state">No explicit human-factor cue detected.</div>';
  }
  h += '</div>';
  h += '<div><h4>Reliability Modifiers</h4>';
  if ((data.reliability_findings || []).length) {
    for (const f of data.reliability_findings || []) h += '<div class="evidence-row"><strong>' + esc(f.signal) + '</strong><br><span style="color:var(--text-dim)">' + esc(f.why) + '</span><br><span style="font-size:11px;color:var(--text-dim);">' + esc(f.rule) + '</span></div>';
  } else {
    h += '<div class="empty-state">No contradiction/distortion finding tied to answer reliability.</div>';
  }
  h += '</div></div>';
  h += '<div class="human-grid">';
  h += '<div><h4>How To Ask Next</h4><ul>';
  for (const item of data.verification_strategy || []) h += '<li>' + esc(item) + '</li>';
  h += '</ul></div>';
  h += '<div><h4>Do Not Do</h4><ul>';
  for (const item of data.avoid || []) h += '<li>' + esc(item) + '</li>';
  h += '</ul></div>';
  h += '</div>';
  h += '<details class="human-prompt-details"><summary>LLM prompt boundary for this layer</summary><ul>';
  for (const item of data.prompt_guardrails || []) h += '<li>' + esc(item) + '</li>';
  h += '</ul></details>';
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

function renderUncertaintyGraph(data) {
  const s = data.summary || {};
  const nodes = data.nodes || [];
  let h = '<div class="summary-grid" style="margin-bottom:12px;">';
    const metrics = [
    ['Nodes observed', String(s.observed_nodes || 0) + '/' + String(s.node_count || 0)],
    ['Graph readiness', String(s.graph_readiness_index ?? '')],
    ['Action pressure', Number(s.action_pressure || 0).toFixed(2)],
    ['Strategic signal load', Number(s.strategic_signal_load || 0).toFixed(2)],
    ['Boundary sensitivity', Number(s.boundary_sensitivity_index || 0).toFixed(2)],
    ['Range risk', Number(s.range_risk_load || 0).toFixed(2)],
    ['Missing load', Number(s.missing_load || 0).toFixed(2)],
    ['Objective coverage', Number(s.objective_coverage || 0).toFixed(2)]
  ];
  for (const [label, value] of metrics) {
    h += '<div class="summary-note"><strong>' + esc(label) + '</strong><br>' + esc(value) + '</div>';
  }
  h += '</div>';
  if ((s.breached_nodes || []).length || (s.weak_nodes || []).length) {
    h += '<div class="coverage-warning"><strong>Graph node status:</strong> breached: ' + esc((s.breached_nodes || []).join(', ') || 'none') + ' | weak: ' + esc((s.weak_nodes || []).slice(0, 8).join(', ') || 'none') + '</div>';
  }
  if ((s.strategic_signals || []).length || (s.fragile_nodes || []).length) {
    h += '<div class="coverage-warning"><strong>Strategic / dynamical signals:</strong> strategic: ' + esc((s.strategic_signals || []).join(', ') || 'none') + ' | fragile: ' + esc((s.fragile_nodes || []).slice(0, 8).join(', ') || 'none') + '</div>';
  }
  h += '<div class="coverage-table-wrap"><table class="coverage-table"><thead><tr><th>Node</th><th>Value / Source</th><th>State</th><th>Range</th><th>Fragility</th><th>Dominant Uncertainty</th><th>Action Implications</th></tr></thead><tbody>';
  for (const n of nodes.slice(0, 18)) {
    const rangeSeverity = Number(n.range_severity || 0);
    const fragility = Number(n.boundary_fragility || 0);
    const rowClass = rangeSeverity >= 0.75 || fragility >= 0.45 ? 'low-confidence' : '';
    h += '<tr class="' + rowClass + '">';
    h += '<td><strong>' + esc(n.label || n.node_id) + '</strong><br><small>' + esc(n.node_id || '') + '</small></td>';
    h += '<td>' + (n.observed ? esc(String(n.raw_value || '').substring(0, 90)) : '<em>not observed</em>') + '<br><small>source: ' + esc(n.source || 'none') + ' / conf ' + Number(n.confidence || 0).toFixed(2) + '</small></td>';
    h += '<td><span class="coverage-status coverage-' + esc(n.state || 'missing') + '">' + esc(String(n.state || '').replace(/_/g, ' ')) + '</span></td>';
    h += '<td>' + esc(n.range_band || 'n/a') + '<br><small>severity ' + rangeSeverity.toFixed(2) + '</small></td>';
    h += '<td>' + fragility.toFixed(2) + '<br><small>flip ' + Number(n.perturbation_flip_risk || 0).toFixed(2) + '</small></td>';
    h += '<td>' + esc(String(n.dominant_uncertainty || '').replace(/_/g, ' ')) + '</td>';
    h += '<td>';
    for (const a of (n.actions || []).slice(0, 3)) h += '<span class="coverage-chip">' + esc(a) + '</span>';
    h += '</td></tr>';
  }
  h += '</tbody></table></div>';
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

function renderReasoningIntegrity(data) {
  let h = '<div style="margin-bottom:12px;"><span class="state-badge state-' + esc(data.state || 'ALLOW_WITH_AUDIT') + '">' + esc(String(data.state || '').replace(/_/g, ' ')) + '</span> <span style="font-size:13px;margin-left:8px;">' + esc(data.summary || '') + '</span></div>';
  if (!(data.findings || []).length) {
    h += '<div class="empty-state">No major cognitive forcing concern detected.</div>';
  }
  for (const f of data.findings || []) {
    h += '<div class="red-flag-item" style="border-left-color:var(--purple);background:#f8f4ff;">';
    h += '<div class="rf-concept">' + esc(f.label) + ' ' + authorityChip(f.authority) + ' <span style="font-size:12px;color:var(--text-dim);">severity ' + Number(f.severity || 0).toFixed(2) + '</span></div>';
    h += '<div class="rf-reason"><strong>Reasoning failure:</strong> ' + esc(f.reasoning_failure || '') + '</div>';
    h += '<div style="font-size:13px;margin-top:6px;"><strong>Cognitive forcing action:</strong> ' + esc(f.cognitive_forcing_action || '') + '</div>';
    h += '<div style="font-size:13px;margin-top:6px;"><strong>Disconfirming question:</strong> ' + esc(f.disconfirming_question || '') + '</div>';
    h += '<div style="font-size:12px;color:var(--text-dim);margin-top:6px;"><strong>Evidence:</strong> ' + esc(String(f.evidence || '').substring(0, 220)) + '</div>';
    h += '<div style="font-size:12px;color:var(--text-dim);margin-top:4px;"><strong>Autonomy effect:</strong> ' + esc(f.affected_autonomy || '') + '</div>';
    h += '</div>';
  }
  h += '<ul class="invariant-list">';
  for (const inv of data.invariants || []) h += '<li>' + esc(inv) + '</li>';
  h += '</ul>';
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
  h += '<span class="state-badge state-' + data.reasoning_state + '">Reasoning: ' + data.reasoning_state + '</span>';
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
  if ((data.llm_roles || []).length) {
    h += '<details style="margin-top:12px;" open><summary style="cursor:pointer;font-size:13px;font-weight:800;">Configured LLM roles and model boundaries</summary>';
    h += renderLLMRoleManifest(data.llm_roles || []);
    h += '</details>';
  }
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
  h += '<div class="decision-action" style="margin-top:14px;"><strong>Operational effect:</strong> ' + esc(data.business_effect) + '</div>';
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
  h += '<div class="mitigation-subtitle">This case deposits traces into separate regions so stale data, weak denials, source conflict, embarrassment/fear pressure, and outcome feedback do not vanish after one turn.</div>';
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

  let roleManifest = data.role_manifest || [];
  // Show governed side immediately, LLM side loading
  let h = '<div class="llm-comparison">';
  h += '<div class="llm-col"><h4>Governed Safety Findings (' + data.regex_findings.length + ')</h4>';
  for (const f of data.regex_findings) {
    h += '<div class="llm-finding-item"><strong>' + esc(f.concept) + '</strong> (' + f.severity.toFixed(2) + ')<br><span style="color:var(--text-dim)">' + esc(f.reason.substring(0, 100)) + '</span></div>';
  }
  if (!data.regex_findings.length) h += '<div class="empty-state">No governed findings.</div>';
  h += '</div>';
  h += '<div class="llm-col" id="llm-results-col"><h4>Multi-Role LLM Candidate Pipeline</h4>';
  h += renderLLMRoleManifest(roleManifest);
  if (data.llm_available) {
    h += '<div style="text-align:center;padding:20px;"><span class="spinner"></span> Running enabled advisory roles...</div>';
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
        let lh = '<h4>Multi-Role LLM Candidate Pipeline (' + (llmData.llm_findings || []).length + ' findings)</h4>';
        lh += renderLLMRoleManifest(llmData.role_manifest || roleManifest);
        if (llmData.model) lh += '<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">Executed model(s): ' + esc(llmData.model) + '</div>';
        if (llmData.llm_error) {
          lh += '<div class="llm-unavailable">LLM error: ' + esc(llmData.llm_error) + '</div>';
        } else {
          lh += renderLLMRoleRuns(llmData.role_runs || [], llmData.llm_findings || []);
          if (!(llmData.llm_findings || []).length) {
            lh += '<div class="empty-state">' + esc(llmData.llm_note || 'LLM roles ran but returned no additional candidate signals.') + '</div>';
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

function renderLLMRoleManifest(roles) {
  if (!roles || !roles.length) return '';
  let h = '<div class="llm-role-grid">';
  for (const role of roles) {
    h += '<div class="llm-role-card ' + (role.enabled ? '' : 'disabled') + '">';
    h += '<div class="llm-role-title"><span>' + esc(role.label || role.role) + '</span><span class="llm-role-pill">' + (role.enabled ? 'enabled' : 'available') + '</span></div>';
    h += '<div class="llm-role-meta"><strong>Model:</strong> ' + esc(role.model || '') + '</div>';
    h += '<div class="llm-role-meta"><strong>Env:</strong> ' + esc(role.env_var || '') + '</div>';
    h += '<div class="llm-role-meta">' + esc(role.purpose || '') + '</div>';
    h += '<div class="llm-role-meta"><strong>Authority:</strong> ' + esc(role.authority || 'Advisory only.') + '</div>';
    h += '</div>';
  }
  h += '</div>';
  return h;
}

function renderLLMRoleRuns(roleRuns, flatFindings) {
  if (!roleRuns || !roleRuns.length) {
    let h = '';
    for (const f of (flatFindings || [])) {
      h += renderLLMFinding(f);
    }
    return h;
  }
  let h = '';
  for (const run of roleRuns) {
    h += '<div class="llm-role-run">';
    h += '<h5>' + esc(run.label || run.role) + ' · ' + esc(run.model || '') + '</h5>';
    h += '<div class="llm-role-meta">' + esc(run.purpose || '') + '</div>';
    h += '<div class="llm-role-meta"><strong>Authority:</strong> ' + esc(run.authority || 'Advisory only.') + '</div>';
    if (run.error) {
      h += '<div class="llm-unavailable" style="padding:10px;text-align:left;">' + esc(run.error) + '</div>';
    } else if (run.findings && run.findings.length) {
      for (const f of run.findings) h += renderLLMFinding(f);
    } else {
      h += '<div class="empty-state">No candidate signals from this role.</div>';
    }
    h += '</div>';
  }
  return h;
}

function renderLLMFinding(f) {
  const role = f.role_label ? '<span style="color:var(--text-dim);font-size:11px;">' + esc(f.role_label) + '</span><br>' : '';
  return '<div class="llm-finding-item">' + role + '<strong>' + esc(f.concept) + '</strong> (' + Number(f.severity || 0).toFixed(2) + ', conf ' + Number(f.confidence || 0).toFixed(2) + ')<br><span style="color:var(--text-dim)">' + esc(String(f.reason || '').substring(0, 140)) + '</span></div>';
}

function buildLLMPayloadFromCurrentCase() {
  const stmts = collectEncounterStatements();
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
  return '<h4>Multi-Role LLM Candidate Pipeline</h4><div class="llm-unavailable">' + esc(message) + '<br><button class="btn btn-secondary btn-sm" style="margin-top:10px;" onclick="retryLLMAnalysis()">Retry LLM</button></div>';
}

async function retryLLMAnalysis() {
  if (!currentCase) return;
  const col = document.getElementById('llm-results-col');
  if (!col) return;
  col.innerHTML = '<h4>Multi-Role LLM Candidate Pipeline</h4><div style="text-align:center;padding:20px;"><span class="spinner"></span> Retrying enabled advisory roles...</div>';
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
    let lh = '<h4>Multi-Role LLM Candidate Pipeline (' + (llmData.llm_findings || []).length + ' findings)</h4>';
    lh += renderLLMRoleManifest(llmData.role_manifest || []);
    if (llmData.model) lh += '<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">Executed model(s): ' + esc(llmData.model) + '</div>';
    if (llmData.llm_error) {
      lh += '<div class="llm-unavailable">LLM error: ' + esc(llmData.llm_error) + '</div>';
    } else {
      lh += renderLLMRoleRuns(llmData.role_runs || [], llmData.llm_findings || []);
      if (!(llmData.llm_findings || []).length) lh += '<div class="empty-state">' + esc(llmData.llm_note || 'LLM roles ran but returned no additional candidate signals.') + '</div>';
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
  const quickCard = document.querySelector('.transcript-intake-card');
  if (quickCard) quickCard.style.display = 'none';
  document.getElementById('custom-builder').style.display = 'block';
}

function cancelCustomBuilder() {
  document.getElementById('case-grid-container').style.display = '';
  const quickCard = document.querySelector('.transcript-intake-card');
  if (quickCard) quickCard.style.display = '';
  document.getElementById('custom-builder').style.display = 'none';
}

function builderStmtHtml(stmt) {
  const s = stmt || {};
  const source = s.source || 'patient';
  return '<span class="remove-stmt" onclick="removeBuilderStmt(this)">remove</span><label>Question</label><input class="stmt-q" placeholder="Question" value="' + esc(s.question || '') + '"><label>Answer</label><input class="stmt-a" placeholder="Answer" value="' + esc(s.answer || '') + '"><label>Source</label><select class="stmt-src"><option value="patient"' + (source === 'patient' ? ' selected' : '') + '>patient</option><option value="caregiver"' + (source === 'caregiver' ? ' selected' : '') + '>caregiver</option><option value="device"' + (source === 'device' ? ' selected' : '') + '>device</option><option value="chart"' + (source === 'chart' ? ' selected' : '') + '>chart</option><option value="clinician"' + (source === 'clinician' ? ' selected' : '') + '>clinician</option></select><label>Concept</label><input class="stmt-concept" placeholder="optional; inferred if blank" value="' + esc(s.concept || '') + '">';
}

function addBuilderStmt(stmt) {
  const div = document.createElement('div');
  div.className = 'builder-stmt';
  div.setAttribute('data-idx', stmtCounter++);
  div.innerHTML = builderStmtHtml(stmt || {});
  document.getElementById('builder-stmts').appendChild(div);
}

function removeBuilderStmt(el) {
  const stmtDiv = el.closest('.builder-stmt');
  if (document.querySelectorAll('.builder-stmt').length > 1) stmtDiv.remove();
}

async function parseBuilderTranscript(replace) {
  const ta = document.getElementById('builder-transcript');
  const text = ta ? ta.value : '';
  if (!text.trim()) {
    showToast('Paste transcript text first.');
    return;
  }
  let parseData = null;
  let stmts = [];
  try {
    parseData = await parseTranscriptServer(text);
    stmts = parseData.statements || [];
  } catch (e) {
    stmts = parseTranscript(text);
  }
  if (!stmts.length) {
    showToast('No dialogue turns found in transcript.');
    return;
  }
  const container = document.getElementById('builder-stmts');
  if (replace) container.innerHTML = '';
  for (const stmt of stmts) addBuilderStmt(stmt);
  const proof = document.getElementById('builder-parse-proof');
  if (proof) {
    const concepts = parseData && parseData.concepts ? parseData.concepts.join(', ') : Array.from(new Set(stmts.map(s => s.concept || 'unknown'))).join(', ');
    proof.textContent = stmts.length + ' row(s) imported; concepts: ' + concepts + '. Rows remain editable before analysis.';
  }
  showToast((replace ? 'Replaced with' : 'Added') + ' ' + stmts.length + ' transcript row(s).');
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
    const conceptEl = div.querySelector('.stmt-concept');
    const concept = conceptEl && conceptEl.value.trim() ? conceptEl.value.trim() : null;
    if (q && a) stmts.push({ question: q, answer: a, concept: concept, source: src, metadata: {} });
  });

  if (!stmts.length) { showToast('Add at least one statement.'); return; }

  const customId = 'CUSTOM-' + Date.now();
  const customCase = {
    case_id: customId,
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
      case_id: customId,
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


def _build_landing_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ClinSafer - Any Disposition Judgment Readiness</title>
<style>
:root {
    --ink: #14201f;
    --muted: #5f6f71;
    --line: #d8e2df;
    --paper: #f7fbf8;
    --white: #ffffff;
    --teal: #0c8075;
    --blue: #245f9e;
    --amber: #bf7c1f;
    --red: #a73d3d;
    --dark: #102423;
    --dark-2: #183332;
}

* { box-sizing: border-box; }

html { scroll-behavior: smooth; }

body {
    margin: 0;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: var(--ink);
    background: var(--paper);
    line-height: 1.55;
}

a { color: inherit; }

.topbar {
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    min-height: 72px;
    padding: 0 32px;
    background: rgba(247, 251, 248, 0.94);
    border-bottom: 1px solid var(--line);
    backdrop-filter: blur(14px);
}

.brand {
    display: flex;
    align-items: center;
    gap: 12px;
    font-weight: 800;
    letter-spacing: 0;
    text-decoration: none;
}

.mark {
    width: 34px;
    height: 34px;
    border-radius: 8px;
    display: grid;
    place-items: center;
    color: white;
    background: var(--teal);
    font-size: 13px;
}

.topnav {
    display: flex;
    align-items: center;
    gap: 20px;
    color: #3e4d4e;
    font-size: 14px;
}

.topnav a {
    text-decoration: none;
    white-space: nowrap;
}

.nav-cta {
    padding: 9px 13px;
    border-radius: 6px;
    background: var(--ink);
    color: white;
}

.hero {
    position: relative;
    min-height: 86vh;
    overflow: hidden;
    color: white;
    background: var(--dark);
    border-bottom: 1px solid #203b39;
}

.hero-grid {
    position: absolute;
    inset: 0;
    opacity: 0.28;
    background-image:
        linear-gradient(#24413f 1px, transparent 1px),
        linear-gradient(90deg, #24413f 1px, transparent 1px);
    background-size: 42px 42px;
}

.dashboard-visual {
    position: absolute;
    right: max(24px, 4vw);
    top: 116px;
    width: min(540px, 42vw);
    min-height: 430px;
    padding: 18px;
    border: 1px solid rgba(207, 236, 230, 0.24);
    border-radius: 8px;
    background: #132e2d;
    box-shadow: 0 28px 80px rgba(0, 0, 0, 0.32);
}

.visual-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding-bottom: 14px;
    color: #cde5e0;
    font-size: 12px;
    border-bottom: 1px solid rgba(207, 236, 230, 0.16);
}

.signal-stack {
    display: grid;
    grid-template-columns: 1.2fr 0.8fr;
    gap: 14px;
    padding-top: 16px;
}

.visual-panel {
    min-height: 116px;
    padding: 14px;
    border: 1px solid rgba(207, 236, 230, 0.16);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.045);
}

.visual-panel h3 {
    margin: 0 0 12px;
    color: #f0fbf8;
    font-size: 13px;
    font-weight: 700;
}

.meter {
    display: grid;
    gap: 8px;
}

.meter span {
    display: block;
    height: 8px;
    border-radius: 999px;
    background: #30504e;
    overflow: hidden;
}

.meter span::before {
    content: "";
    display: block;
    height: 100%;
    width: var(--w);
    background: var(--c);
}

.trace-row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 0;
    color: #d8ede9;
    font-size: 12px;
    border-bottom: 1px solid rgba(207, 236, 230, 0.1);
}

.trace-row strong {
    color: white;
    font-weight: 700;
}

.hero-content {
    position: relative;
    z-index: 3;
    width: min(1160px, calc(100% - 48px));
    margin: 0 auto;
    padding: 120px 0 72px;
}

.eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 24px;
    color: #b8ddd8;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.eyebrow::before {
    content: "";
    width: 34px;
    height: 2px;
    background: #4fc0b1;
}

.hero h1 {
    max-width: 640px;
    margin: 0;
    font-size: clamp(44px, 6vw, 78px);
    line-height: 0.98;
    letter-spacing: 0;
}

.hero-copy {
    max-width: 610px;
    margin: 24px 0 0;
    color: #d9e8e5;
    font-size: clamp(18px, 2vw, 22px);
}

.hero-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    margin-top: 34px;
}

.button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 48px;
    padding: 0 18px;
    border: 1px solid transparent;
    border-radius: 6px;
    font-weight: 800;
    text-decoration: none;
}

.button.primary {
    color: #0d2422;
    background: #83eadc;
}

.button.secondary {
    color: white;
    border-color: rgba(255, 255, 255, 0.34);
    background: rgba(255, 255, 255, 0.08);
}

.hero-proof {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    width: min(650px, 100%);
    margin-top: 58px;
}

.proof-item {
    padding: 14px;
    border: 1px solid rgba(207, 236, 230, 0.2);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.055);
}

.proof-item strong {
    display: block;
    margin-bottom: 4px;
    color: white;
    font-size: 18px;
}

.proof-item span {
    color: #c8dfdc;
    font-size: 13px;
}

.section {
    padding: 72px 32px;
}

.section.alt {
    background: white;
    border-block: 1px solid var(--line);
}

.inner {
    width: min(1160px, 100%);
    margin: 0 auto;
}

.section-title {
    max-width: 780px;
    margin-bottom: 34px;
}

.section-title h2 {
    margin: 0 0 12px;
    font-size: clamp(30px, 4vw, 48px);
    line-height: 1.05;
    letter-spacing: 0;
}

.section-title p {
    margin: 0;
    color: var(--muted);
    font-size: 18px;
}

.feature-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px;
}

.feature-card {
    min-height: 238px;
    padding: 22px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: white;
}

.feature-card h3 {
    margin: 0 0 10px;
    font-size: 20px;
    letter-spacing: 0;
}

.feature-card p {
    margin: 0;
    color: #526365;
}

.feature-code {
    display: inline-grid;
    place-items: center;
    width: 38px;
    height: 38px;
    margin-bottom: 18px;
    border-radius: 8px;
    color: white;
    font-size: 13px;
    font-weight: 800;
}

.code-teal { background: var(--teal); }
.code-blue { background: var(--blue); }
.code-amber { background: var(--amber); }
.code-red { background: var(--red); }
.code-dark { background: var(--ink); }
.code-green { background: #477b3a; }

.method-list {
    display: grid;
    gap: 12px;
}

.method-row {
    display: grid;
    grid-template-columns: 210px 1fr;
    gap: 22px;
    padding: 18px 0;
    border-top: 1px solid var(--line);
}

.method-row:last-child {
    border-bottom: 1px solid var(--line);
}

.method-row strong {
    color: var(--ink);
    font-size: 17px;
}

.method-row p {
    margin: 0;
    color: #536466;
}

.split {
    display: grid;
    grid-template-columns: 0.95fr 1.05fr;
    gap: 42px;
    align-items: start;
}

.check-list {
    display: grid;
    gap: 12px;
    margin: 0;
    padding: 0;
    list-style: none;
}

.check-list li {
    padding: 14px 16px;
    border-left: 4px solid var(--teal);
    background: #eef7f3;
}

.risk-band {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 1px;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--line);
}

.risk-band div {
    min-height: 148px;
    padding: 18px;
    background: white;
}

.risk-band strong {
    display: block;
    margin-bottom: 8px;
}

.risk-band span {
    color: var(--muted);
    font-size: 14px;
}

.cta-band {
    color: white;
    background: var(--dark-2);
}

.cta-box {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 28px;
}

.cta-box h2 {
    margin: 0 0 10px;
    font-size: clamp(30px, 4vw, 46px);
    line-height: 1.05;
}

.cta-box p {
    max-width: 720px;
    margin: 0;
    color: #c9dfdb;
}

.footer {
    padding: 28px 32px;
    color: #657476;
    background: #eef4f1;
    border-top: 1px solid var(--line);
    font-size: 13px;
}

.footer .inner {
    display: flex;
    justify-content: space-between;
    gap: 18px;
}

@media (max-width: 1180px) {
    .topbar {
        position: static;
        align-items: flex-start;
        flex-direction: column;
        padding: 18px 22px;
    }

    .topnav {
        width: 100%;
        overflow-x: auto;
        padding-bottom: 4px;
    }

    .dashboard-visual {
        position: relative;
        top: auto;
        right: auto;
        width: min(100% - 44px, 680px);
        min-height: 360px;
        margin: 0 auto 44px;
    }

    .hero-content {
        width: min(100% - 44px, 760px);
        padding: 64px 0 36px;
    }

    .hero-proof,
    .feature-grid,
    .risk-band,
    .split {
        grid-template-columns: 1fr;
    }

    .method-row {
        grid-template-columns: 1fr;
        gap: 8px;
    }

    .cta-box {
        align-items: flex-start;
        flex-direction: column;
    }
}

@media (max-width: 640px) {
    .section {
        padding: 54px 20px;
    }

    .hero h1 {
        font-size: 42px;
    }

    .signal-stack {
        grid-template-columns: 1fr;
    }

    .hero-actions {
        flex-direction: column;
    }

    .button {
        width: 100%;
    }

    .footer .inner {
        flex-direction: column;
    }
}
</style>
</head>
<body>
<header class="topbar">
    <a class="brand" href="/">
        <span class="mark">CS</span>
        <span>ClinSafer</span>
    </a>
    <nav class="topnav" aria-label="Primary navigation">
        <a href="#methodologies">Methodologies</a>
        <a href="#validation">Validation</a>
        <a href="#breakthrough">Why now</a>
        <a class="nav-cta" href="/demo">Launch Demo</a>
    </nav>
</header>

<main>
    <section class="hero">
        <div class="hero-grid" aria-hidden="true"></div>
        <div class="hero-content">
            <div class="eyebrow">Any disposition safety intelligence</div>
            <h1>Judgment readiness for the AI healthcare era.</h1>
            <p class="hero-copy">
                ClinSafer turns clinical uncertainty into inspectable boundaries, red flags, bias checks,
                and escalation logic before an AI system, care team, or workflow overreaches.
            </p>
            <div class="hero-actions">
                <a class="button primary" href="/demo">Launch Interactive Demo</a>
                <a class="button secondary" href="#methodologies">Review Methodology</a>
            </div>
            <div class="hero-proof" aria-label="Core capabilities">
                <div class="proof-item"><strong>Any Dispo</strong><span>Admission, discharge, observe, transfer, consult, follow-up.</span></div>
                <div class="proof-item"><strong>JRE</strong><span>Judgment Readiness Engine with autonomy limits.</span></div>
                <div class="proof-item"><strong>BSG</strong><span>Black Swan Guardrails for rare but costly misses.</span></div>
                <div class="proof-item"><strong>CBF</strong><span>Cognitive Bias Field review before action.</span></div>
            </div>
        </div>
        <aside class="dashboard-visual" aria-label="ClinSafer judgment readiness dashboard preview">
            <div class="visual-bar">
                <span>Boundary Trace - ED chest pain transcript</span>
                <strong>Advisory Only</strong>
            </div>
            <div class="signal-stack">
                <div class="visual-panel">
                    <h3>Disposition Readiness</h3>
                    <div class="meter">
                        <span style="--w: 64%; --c: #83eadc"></span>
                        <span style="--w: 42%; --c: #f0b85a"></span>
                        <span style="--w: 78%; --c: #6fa8dc"></span>
                        <span style="--w: 31%; --c: #d96c6c"></span>
                    </div>
                </div>
                <div class="visual-panel">
                    <h3>Red Flag Pressure</h3>
                    <div class="trace-row"><span>Missing vitals</span><strong>High</strong></div>
                    <div class="trace-row"><span>Risk standard</span><strong>Check</strong></div>
                    <div class="trace-row"><span>Follow-up fragility</span><strong>Medium</strong></div>
                </div>
                <div class="visual-panel">
                    <h3>Bias Field</h3>
                    <div class="trace-row"><span>Premature closure</span><strong>Raised</strong></div>
                    <div class="trace-row"><span>Anchoring</span><strong>Watch</strong></div>
                    <div class="trace-row"><span>Dispo momentum</span><strong>Raised</strong></div>
                </div>
                <div class="visual-panel">
                    <h3>System Output</h3>
                    <div class="trace-row"><span>AI autonomy</span><strong>Limited</strong></div>
                    <div class="trace-row"><span>Needed next step</span><strong>Human review</strong></div>
                    <div class="trace-row"><span>Reason</span><strong>Visible</strong></div>
                </div>
            </div>
        </aside>
    </section>

    <section class="section alt" id="breakthrough">
        <div class="inner split">
            <div class="section-title">
                <h2>Not another AI doctor. A safety layer for uncertainty.</h2>
                <p>
                    The breakthrough is not pretending the model always knows. It is making uncertainty operational:
                    what is missing, what could be catastrophically wrong, what bias may be present, and when autonomy
                    must narrow.
                </p>
            </div>
            <ul class="check-list">
                <li>Separates clinical reasoning support from disposition authority.</li>
                <li>Converts vague concern into auditable guardrails and missing-data questions.</li>
                <li>Supports inverse use cases: patients admitted who may be safe for home only after boundary checks pass.</li>
                <li>Creates reusable traces for governance, QA, model evaluation, and expert review.</li>
            </ul>
        </div>
    </section>

    <section class="section" id="methodologies">
        <div class="inner">
            <div class="section-title">
                <h2>Methodologies built into the platform.</h2>
                <p>
                    ClinSafer combines deterministic safety engineering, uncertainty modeling, medical knowledge governance,
                    and human-factor review into one disposition-readiness workflow.
                </p>
            </div>
            <div class="feature-grid">
                <article class="feature-card">
                    <span class="feature-code code-teal">JRE</span>
                    <h3>Judgment Readiness Engine</h3>
                    <p>Scores whether enough reliable information exists to support a bounded next step, rather than forcing a premature answer.</p>
                </article>
                <article class="feature-card">
                    <span class="feature-code code-red">BSG</span>
                    <h3>Black Swan Guardrails</h3>
                    <p>Looks for rare, high-consequence failure modes that ordinary pattern matching can miss in common presentations.</p>
                </article>
                <article class="feature-card">
                    <span class="feature-code code-amber">CBF</span>
                    <h3>Cognitive Bias Field</h3>
                    <p>Flags anchoring, premature closure, availability bias, confirmation bias, and disposition momentum in the case trace.</p>
                </article>
                <article class="feature-card">
                    <span class="feature-code code-blue">AD</span>
                    <h3>Any Dispo Design</h3>
                    <p>Works across discharge, admission, observation, transfer, consult, and follow-up instead of optimizing only one endpoint.</p>
                </article>
                <article class="feature-card">
                    <span class="feature-code code-green">CUG</span>
                    <h3>Clinical Uncertainty Graph</h3>
                    <p>Maps symptoms, gaps, provenance, red flags, and next questions so uncertainty has structure the team can inspect.</p>
                </article>
                <article class="feature-card">
                    <span class="feature-code code-dark">ML</span>
                    <h3>Empirical Model Layer</h3>
                    <p>Designed to add TabPFN, conformal prediction, imbalance-aware metrics, and calibration studies without replacing safety logic.</p>
                </article>
            </div>
        </div>
    </section>

    <section class="section alt" id="validation">
        <div class="inner">
            <div class="section-title">
                <h2>Built to test what matters before deployment.</h2>
                <p>
                    The landing demo lets teams run transcripts and synthetic cases, inspect the reasoning boundary, and see where the system refuses
                    to overstate certainty. That makes product testing, expert review, and clinical governance possible from the same interface.
                </p>
            </div>
            <div class="risk-band" aria-label="Validation targets">
                <div><strong>Safety</strong><span>Does it catch red flags and force the right uncertainty posture?</span></div>
                <div><strong>Equity</strong><span>Does performance hold with sparse, noisy, imbalanced, or vulnerable-population data?</span></div>
                <div><strong>Governance</strong><span>Can every boundary, warning, and escalation be traced and reviewed?</span></div>
                <div><strong>Generalization</strong><span>Does it work across disposition types, not just admit-versus-discharge?</span></div>
            </div>
        </div>
    </section>

    <section class="section">
        <div class="inner">
            <div class="section-title">
                <h2>Medical knowledge without pretending to be the clinician.</h2>
                <p>
                    The architecture can save precise guideline questions, expert-reviewed red flags, and monitored knowledge checks as governed
                    artifacts. Models can help retrieve and draft specifics, while the product keeps final clinical authority outside the AI.
                </p>
            </div>
            <div class="method-list">
                <div class="method-row"><strong>Knowledge packets</strong><p>Reusable, versioned facts for red flags, standards, contraindications, and guideline thresholds.</p></div>
                <div class="method-row"><strong>Expert review loop</strong><p>Clinical SMEs can approve, reject, annotate, and retire packets as evidence changes.</p></div>
                <div class="method-row"><strong>Boundary-first output</strong><p>The system says what it can and cannot support, then points to missing information and escalation needs.</p></div>
                <div class="method-row"><strong>Audit memory</strong><p>Near misses, false reassurance, bias signals, and uncertainty failures become retrievable improvement data.</p></div>
            </div>
        </div>
    </section>

    <section class="section cta-band">
        <div class="inner cta-box">
            <div>
                <h2>Test the safety layer now.</h2>
                <p>
                    Open the demo, choose a case or paste a transcript, and inspect how ClinSafer handles missing data,
                    red flags, cognitive bias, autonomy boundaries, and any-disposition readiness.
                </p>
            </div>
            <a class="button primary" href="/demo">Launch Interactive Demo</a>
        </div>
    </section>
</main>

<footer class="footer">
    <div class="inner">
        <span>ClinSafer Judgment Readiness Engine</span>
        <span>Research and advisory workflow only. Not a medical device or autonomous clinical decision maker.</span>
    </div>
</footer>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def serve_landing_page():
    """Serve the public landing page."""
    return HTMLResponse(content=_build_landing_html())


@app.get("/demo", response_class=HTMLResponse)
@app.get("/demo/", response_class=HTMLResponse, include_in_schema=False)
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
