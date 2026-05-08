from jre import recommend_medical_skills, recommend_skills_for_case
from jre.models import CaseInput, PatientContext, Statement


ROUTING_CASES = [
    (
        "Patient denies chest pain but describes exertional pressure walking upstairs and dyspnea.",
        {"diagnostic_reasoning", "clinical_safety", "clinical_nlp"},
    ),
    (
        "Messy EHR cohort CSV has missing columns, inconsistent schema, and discharge outcome labels.",
        {"data_quality", "epidemiology", "biomedical_analysis"},
    ),
    (
        "Assess trial eligibility using inclusion and exclusion criteria for a recruiting study.",
        {"clinical_trials"},
    ),
    (
        "Medication refill case with lisinopril, ibuprofen, kidney disease, and possible drug interaction.",
        {"medication_safety"},
    ),
    (
        "Build a DHSE benchmark model and report AUROC, AUPRC, calibration, and validation bias.",
        {"statistics", "prediction_model_appraisal", "biomedical_analysis"},
    ),
    (
        "Audit a clinical note export for PHI, identifiers, HIPAA compliance, and de-identification.",
        {"privacy_compliance", "clinical_nlp"},
    ),
    (
        "Population cohort study needs exposure, outcome, incidence, and confounding review.",
        {"epidemiology"},
    ),
    (
        "Remote disposition decision is near ICU threshold and needs monitoring safety guardrails.",
        {"clinical_safety", "diagnostic_reasoning"},
    ),
    (
        "Extract symptoms, vitals, medications, and diagnosis entities from intake transcript.",
        {"clinical_nlp"},
    ),
    (
        "Evaluate prediction model study for PROBAST bias, validation leakage, and calibration.",
        {"prediction_model_appraisal", "statistics"},
    ),
]


def test_medical_skill_router_hits_expected_family_on_at_least_eight_of_ten_cases():
    hits = 0
    for text, expected_families in ROUTING_CASES:
        recommendations = recommend_medical_skills(text, top_n=3)
        actual_families = {item.family for item in recommendations}
        if actual_families & expected_families:
            hits += 1

    assert hits >= 8


def test_medical_skill_router_returns_reasons_for_every_recommendation():
    recommendations = recommend_medical_skills(
        "Chest pressure with vague denial of pain and remote triage uncertainty.",
        top_n=3,
    )

    assert len(recommendations) == 3
    for item in recommendations:
        assert item.reason
        assert item.matched_terms
        assert item.source_repo in {"OpenClaw-Medical-Skills", "medical-research-skills"}


def test_direct_clinical_action_skills_require_review():
    recommendations = recommend_medical_skills(
        "Remote disposition decision with chest pressure and medication safety concern.",
        top_n=5,
    )
    review_required = {item.slug for item in recommendations if item.review_required}

    assert "clinical-decision-support" in review_required
    assert "clinical-diagnostic-reasoning" in review_required


def test_case_router_uses_clinsafer_case_context_and_statements():
    case = CaseInput(
        case_id="router-case",
        patient_context=PatientContext(
            age=61,
            chief_concern="blood pressure refill",
            domain="med_refill_hypertension",
            modality="text",
            known_conditions=["kidney disease"],
        ),
        statements=[
            Statement(
                question="What medications do you take?",
                answer="Lisinopril, ibuprofen, and a water pill.",
                concept="medication_identity",
            ),
            Statement(
                question="Any symptoms?",
                answer="Dizzy today with high blood pressure.",
                concept="side_effects",
            ),
        ],
    )

    recommendations = recommend_skills_for_case(case, top_n=3)
    families = {item.family for item in recommendations}

    assert "medication_safety" in families
