"""Deterministic medical skill routing for ClinSafer.

The router maps a clinical/research scenario to bounded specialist skill
families. It is intentionally deterministic: clinical safety should not depend
on a free-form model choosing tools without an auditable reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .models import CaseInput


@dataclass(frozen=True)
class MedicalSkillCard:
    """A governed source-skill summary that ClinSafer may recommend."""

    slug: str
    family: str
    source_repo: str
    purpose: str
    keywords: tuple[str, ...]
    review_required: bool = False
    safety_note: str = ""


@dataclass(frozen=True)
class SkillRecommendation:
    """A routed skill plus the evidence that caused the route."""

    slug: str
    family: str
    source_repo: str
    reason: str
    score: float
    review_required: bool
    safety_note: str
    matched_terms: tuple[str, ...] = field(default_factory=tuple)


SKILL_CATALOG: tuple[MedicalSkillCard, ...] = (
    MedicalSkillCard(
        slug="medical-entity-extractor",
        family="clinical_nlp",
        source_repo="OpenClaw-Medical-Skills",
        purpose="Extract symptoms, medications, vitals, diagnoses, and clinical entities.",
        keywords=(
            "entity",
            "extract",
            "symptom",
            "medication",
            "vital",
            "note",
            "transcript",
            "pain",
            "pressure",
        ),
    ),
    MedicalSkillCard(
        slug="clinical-diagnostic-reasoning",
        family="diagnostic_reasoning",
        source_repo="OpenClaw-Medical-Skills",
        purpose="Review diagnostic uncertainty and differential diagnosis boundaries.",
        keywords=(
            "diagnosis",
            "differential",
            "chest",
            "pressure",
            "dyspnea",
            "headache",
            "red flag",
            "uncertain",
        ),
        review_required=True,
        safety_note="Advisory only; cannot make autonomous diagnosis or treatment decisions.",
    ),
    MedicalSkillCard(
        slug="clinical-decision-support",
        family="clinical_safety",
        source_repo="OpenClaw-Medical-Skills",
        purpose="Identify decision-support guardrails, escalation needs, and safety boundaries.",
        keywords=(
            "triage",
            "escalate",
            "decision",
            "disposition",
            "monitoring",
            "safety",
            "guardrail",
            "icu",
        ),
        review_required=True,
        safety_note="Requires clinician review before action-changing use.",
    ),
    MedicalSkillCard(
        slug="clinical-data-cleaner",
        family="data_quality",
        source_repo="medical-research-skills",
        purpose="Clean messy clinical tabular data before analysis or modeling.",
        keywords=("csv", "cohort", "missing", "messy", "column", "data", "clean", "schema"),
    ),
    MedicalSkillCard(
        slug="statistical-analysis",
        family="statistics",
        source_repo="medical-research-skills",
        purpose="Choose and run appropriate statistical analysis for medical datasets.",
        keywords=("statistics", "statistical", "p value", "confidence interval", "regression", "auc"),
    ),
    MedicalSkillCard(
        slug="epidemiologist-analyst",
        family="epidemiology",
        source_repo="OpenClaw-Medical-Skills",
        purpose="Frame cohort, exposure, outcome, bias, and population-health questions.",
        keywords=("cohort", "exposure", "outcome", "epidemiology", "population", "incidence"),
    ),
    MedicalSkillCard(
        slug="trial-eligibility-agent",
        family="clinical_trials",
        source_repo="OpenClaw-Medical-Skills",
        purpose="Map patient facts to trial inclusion and exclusion criteria.",
        keywords=("trial", "eligibility", "inclusion", "exclusion", "criteria", "enroll"),
        review_required=True,
        safety_note="Trial matching is advisory and must be verified against the protocol.",
    ),
    MedicalSkillCard(
        slug="clinical-trials-search",
        family="clinical_trials",
        source_repo="OpenClaw-Medical-Skills",
        purpose="Search for potentially relevant clinical trials.",
        keywords=("clinicaltrials", "clinical trial", "trial", "recruiting", "study"),
    ),
    MedicalSkillCard(
        slug="drug-interaction-checker",
        family="medication_safety",
        source_repo="OpenClaw-Medical-Skills",
        purpose="Screen medication lists for possible interaction concerns.",
        keywords=("drug", "interaction", "medication", "polypharmacy", "contraindication"),
        review_required=True,
        safety_note="Medication safety output requires pharmacist or clinician confirmation.",
    ),
    MedicalSkillCard(
        slug="hipaa-compliance-auditor",
        family="privacy_compliance",
        source_repo="medical-research-skills",
        purpose="Check medical text or workflow for PHI/privacy handling risk.",
        keywords=("hipaa", "phi", "privacy", "de-identify", "identifier", "compliance"),
    ),
    MedicalSkillCard(
        slug="probast-quality-assessment-for-prediction-model-studies",
        family="prediction_model_appraisal",
        source_repo="medical-research-skills",
        purpose="Appraise bias risk in prediction model studies.",
        keywords=("prediction model", "probast", "bias", "validation", "calibration"),
    ),
    MedicalSkillCard(
        slug="biomedical-data-analysis",
        family="biomedical_analysis",
        source_repo="OpenClaw-Medical-Skills",
        purpose="Support biomedical data analysis workflows and reporting.",
        keywords=("biomedical", "analysis", "dataset", "feature", "model", "benchmark"),
    ),
)


FAMILY_FALLBACKS: dict[str, tuple[str, ...]] = {
    "diagnostic_reasoning": ("symptom", "unclear", "remote", "red flag"),
    "clinical_safety": ("unsafe", "autonomy", "boundary", "ready", "clarify"),
    "data_quality": ("spreadsheet", "table", "ehr", "export"),
    "statistics": ("metric", "evaluate", "benchmark", "performance"),
    "clinical_trials": ("patient criteria", "recruitment"),
    "medication_safety": ("dose", "prescription", "refill"),
}


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", text.lower()) if token}


def _contains_phrase(text: str, phrase: str) -> bool:
    return phrase in text


def _score_card(card: MedicalSkillCard, text: str, tokens: set[str]) -> tuple[float, tuple[str, ...]]:
    score = 0.0
    matched: list[str] = []
    for keyword in card.keywords:
        key = keyword.lower()
        if " " in key:
            if _contains_phrase(text, key):
                score += 2.5
                matched.append(keyword)
        elif key in tokens:
            score += 1.5
            matched.append(keyword)
    for fallback in FAMILY_FALLBACKS.get(card.family, ()):
        key = fallback.lower()
        if (" " in key and key in text) or key in tokens:
            score += 0.6
            matched.append(fallback)
    if card.review_required and score:
        score += 0.2
    return score, tuple(dict.fromkeys(matched))


def recommend_medical_skills(
    scenario_text: str,
    *,
    top_n: int = 3,
    catalog: Iterable[MedicalSkillCard] = SKILL_CATALOG,
) -> list[SkillRecommendation]:
    """Return ranked medical skill recommendations with audit reasons."""

    normalized = scenario_text.lower()
    tokens = _tokenize(normalized)
    recommendations: list[SkillRecommendation] = []
    for card in catalog:
        score, matched = _score_card(card, normalized, tokens)
        if score <= 0:
            continue
        reason_terms = ", ".join(matched[:4])
        reason = (
            f"Matched {card.family} signals"
            + (f": {reason_terms}." if reason_terms else ".")
            + f" Use for: {card.purpose}"
        )
        recommendations.append(
            SkillRecommendation(
                slug=card.slug,
                family=card.family,
                source_repo=card.source_repo,
                reason=reason,
                score=round(score, 3),
                review_required=card.review_required,
                safety_note=card.safety_note,
                matched_terms=matched,
            )
        )
    recommendations.sort(key=lambda item: (-item.score, item.slug))
    return recommendations[: max(1, top_n)]


def recommend_skills_for_case(case: CaseInput, *, top_n: int = 3) -> list[SkillRecommendation]:
    """Route a ClinSafer case using patient context and all available statements."""

    parts = [
        case.patient_context.chief_concern,
        case.patient_context.domain,
        case.patient_context.modality,
        " ".join(case.patient_context.known_conditions),
    ]
    for statement in case.statements:
        parts.extend([statement.question, statement.answer, statement.concept or ""])
    return recommend_medical_skills(" ".join(parts), top_n=top_n)
