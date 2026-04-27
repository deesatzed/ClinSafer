"""FastAPI wrapper for the JRE + BSG pipeline.

Run:
    python api_server.py
    # or: uvicorn api_server:app --reload --port 8000

Endpoints:
    GET  /health              -- Health check
    POST /evaluate            -- Full unified pipeline (JRE + BSG)
    POST /jre                 -- JRE only
    POST /bsg                 -- BSG only (requires JRE report)
    POST /llm-analyze         -- LLM-augmented analysis (optional)
    GET  /cases               -- List all available case IDs
    POST /evaluate-case       -- Run a named case by ID
    POST /feedback            -- Submit clinician feedback on an evaluation
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field, field_validator
except ImportError:
    raise ImportError(
        "FastAPI is required for the API server. Install with: pip install fastapi uvicorn"
    )

from jre import JudgmentReadinessEngine, BlackSwanGuardrailEngine, BLACK_SWAN_CASES
from jre.engine import case_from_dict
from jre.models import CaseInput, most_restrictive
from jre.synthetic_data import BASE_CASES
from jre.templates import DOMAIN_TEMPLATES
from jre.observability import PipelineLogger

app = FastAPI(
    title="JRE + BSG Clinical Safety API",
    description="Judgment Readiness Engine + Black Swan Guardrail Layer API",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# LLM detector (optional — no API key = no LLM calls, pure regex mode)
try:
    from jre.llm_augment import LLMDetector
    _llm_detector = LLMDetector()
except ImportError:
    _llm_detector = None

# Shared singleton instances — state accumulates across requests within process lifetime.
# ExperienceMemory learns from evaluations; PipelineLogger is bounded via _rotate_logs().
# For production deployment, consider per-request instances or external state stores.
_jre = JudgmentReadinessEngine(llm_detector=_llm_detector)
_guard = BlackSwanGuardrailEngine(llm_detector=_llm_detector)
_logger = PipelineLogger()

_LOG_ROTATION_THRESHOLD = 10000
_LOG_ROTATION_KEEP = 5000


def _rotate_logs():
    """Keep logger entries bounded to prevent unbounded memory growth."""
    if len(_logger.entries) > _LOG_ROTATION_THRESHOLD:
        _logger.entries = _logger.entries[-_LOG_ROTATION_KEEP:]


# ---------------------------------------------------------------------------
# Request / Response models
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
        valid = {"patient", "caregiver", "device", "chart", "clinician", "synthetic_truth"}
        if v not in valid:
            raise ValueError(f"source must be one of {sorted(valid)}, got '{v}'")
        return v


class PatientContextInput(BaseModel):
    age: int = Field(ge=0, le=150, description="Patient age in years")
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
            raise ValueError(f"literacy_hint must be one of {sorted(valid)}, got '{v}'")
        return v

    @field_validator("modality")
    @classmethod
    def validate_modality(cls, v):
        valid = {"text", "phone", "video", "in_person"}
        if v not in valid:
            raise ValueError(f"modality must be one of {sorted(valid)}, got '{v}'")
        return v


class CaseInputModel(BaseModel):
    case_id: str = "api-case"
    patient_context: PatientContextInput
    statements: List[StatementInput]
    ground_truth: Dict[str, Any] = {}


class CaseIdRequest(BaseModel):
    case_id: str


class FeedbackInput(BaseModel):
    case_id: str
    concept: str
    domain: str
    clinician_assessment: str  # "confirmed", "corrected", "false_positive", "missed"
    corrected_value: str = ""
    severity_adjustment: float = 0.0
    notes: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Health check."""
    return {
        "status": "healthy",
        "engine": "JRE + BSG",
        "cases_available": len(BASE_CASES) + len(BLACK_SWAN_CASES),
        "log_entries": len(_logger.entries),
        "feedback_recorded": len(_jre.memory.feedback_log),
        "log_rotation_threshold": _LOG_ROTATION_THRESHOLD,
    }


@app.post("/evaluate")
def evaluate(case_input: CaseInputModel):
    """Run full unified pipeline (JRE + BSG) on a case."""
    _validate_domain(case_input.patient_context.domain)
    start = time.monotonic()
    case = _to_case_input(case_input)

    with _logger.trace_case(case) as trace:
        jre_report = _jre.evaluate(case)
        trace.log_jre(jre_report)

        bsg_report = _guard.evaluate(case, jre_report)
        trace.log_bsg(bsg_report)

        # Compute combined state
        combined = _most_restrictive(jre_report.state, bsg_report.guardrail_state)
        trace.log_combined(combined, True)

    _rotate_logs()
    duration_ms = (time.monotonic() - start) * 1000

    return {
        "case_id": case.case_id,
        "jre_report": jre_report.to_dict(),
        "bsg_report": bsg_report.to_dict(),
        "combined_state": combined,
        "duration_ms": round(duration_ms, 2),
    }


@app.post("/jre")
def jre_evaluate(case_input: CaseInputModel):
    """Run JRE only on a case."""
    _validate_domain(case_input.patient_context.domain)
    case = _to_case_input(case_input)
    report = _jre.evaluate(case)
    return report.to_dict()


@app.post("/bsg")
def bsg_evaluate(case_input: CaseInputModel):
    """Run BSG on a case (includes JRE internally)."""
    _validate_domain(case_input.patient_context.domain)
    case = _to_case_input(case_input)
    jre_report = _jre.evaluate(case)
    bsg_report = _guard.evaluate(case, jre_report)
    return bsg_report.to_dict()


@app.post("/llm-analyze")
def llm_analyze(case_input: CaseInputModel):
    """Run LLM-augmented analysis on a case (requires OpenRouter API key)."""
    try:
        from jre.llm_augment import LLMDetector
    except ImportError:
        raise HTTPException(status_code=501, detail="LLM augmentation module not available")

    _validate_domain(case_input.patient_context.domain)
    case = _to_case_input(case_input)
    detector = LLMDetector()

    if not detector.available:
        raise HTTPException(
            status_code=503,
            detail="No OpenRouter API key configured. Set OPENROUTER_API_KEY in .env or environment.",
        )

    result = detector.analyze_case(case)
    return {
        "case_id": result.case_id,
        "success": result.success,
        "model": result.model,
        "findings": [
            {
                "category": f.category,
                "concept": f.concept,
                "severity": f.severity,
                "reason": f.reason,
                "evidence": f.evidence,
                "confidence": f.confidence,
            }
            for f in result.findings
        ],
        "error": result.error,
    }


@app.get("/cases")
def list_cases():
    """List all available built-in case IDs."""
    all_cases = list(BASE_CASES) + list(BLACK_SWAN_CASES)
    return {
        "total": len(all_cases),
        "base_cases": [c.case_id for c in BASE_CASES],
        "black_swan_cases": [c.case_id for c in BLACK_SWAN_CASES],
    }


@app.post("/evaluate-case")
def evaluate_named_case(req: CaseIdRequest):
    """Run a built-in case by its ID through the full pipeline."""
    all_cases = {c.case_id: c for c in list(BASE_CASES) + list(BLACK_SWAN_CASES)}
    case = all_cases.get(req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case not found: {req.case_id}")

    start = time.monotonic()

    with _logger.trace_case(case) as trace:
        jre_report = _jre.evaluate(case)
        trace.log_jre(jre_report)

        bsg_report = _guard.evaluate(case, jre_report)
        trace.log_bsg(bsg_report)

        combined = _most_restrictive(jre_report.state, bsg_report.guardrail_state)
        trace.log_combined(combined, True)

    _rotate_logs()
    duration_ms = (time.monotonic() - start) * 1000

    return {
        "case_id": case.case_id,
        "jre_report": jre_report.to_dict(),
        "bsg_report": bsg_report.to_dict(),
        "combined_state": combined,
        "duration_ms": round(duration_ms, 2),
    }


@app.post("/feedback")
def submit_feedback(feedback: FeedbackInput):
    """Submit clinician feedback on an evaluation to update experience memory."""
    valid_assessments = {"confirmed", "corrected", "false_positive", "missed"}
    if feedback.clinician_assessment not in valid_assessments:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid assessment '{feedback.clinician_assessment}'. Valid: {sorted(valid_assessments)}",
        )

    from jre.experience import OutcomeFeedback
    of = OutcomeFeedback(
        case_id=feedback.case_id,
        concept=feedback.concept,
        domain=feedback.domain,
        clinician_assessment=feedback.clinician_assessment,
        corrected_value=feedback.corrected_value,
        severity_adjustment=feedback.severity_adjustment,
        notes=feedback.notes,
    )

    updates = _jre.memory.record_feedback(of)

    return {
        "status": "recorded",
        "case_id": feedback.case_id,
        "assessment": feedback.clinician_assessment,
        "priors_updated": len(updates),
        "updated_values": updates,
        "total_feedback": len(_jre.memory.feedback_log),
    }


@app.get("/logs")
def get_logs():
    """Get pipeline log summary and recent entries."""
    return {
        "summary": _logger.summary(),
        "recent_entries": [e.to_dict() for e in _logger.entries[-50:]],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_most_restrictive = most_restrictive  # backward-compat alias


def _validate_domain(domain: str) -> None:
    """Raise 422 if domain is not in DOMAIN_TEMPLATES."""
    if domain not in DOMAIN_TEMPLATES:
        supported = sorted(DOMAIN_TEMPLATES.keys())
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported domain '{domain}'. Supported domains: {supported}",
        )


def _to_case_input(model: CaseInputModel) -> CaseInput:
    """Convert Pydantic model to CaseInput."""
    from jre.models import PatientContext, Statement
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


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        raise ImportError("uvicorn is required. Install with: pip install uvicorn")
    uvicorn.run(app, host="0.0.0.0", port=8000)
