from jre import JudgmentReadinessEngine, BlackSwanGuardrailEngine
from jre.black_swan import SUPPORTED_DEMO_DOMAINS
from jre.models import CaseInput, PatientContext, Statement
from jre.templates import DOMAIN_TEMPLATES, RED_FLAG_PATTERNS


TOP_25_TELEMEDICINE_COVERAGE = {
    "medication_refills": "general_med_management",
    "hypertension_refill": "med_refill_hypertension",
    "follow_up_visit": "followup_lab_review",
    "lab_result_review": "followup_lab_review",
    "anxiety_depression": "mental_health",
    "adhd_behavioral_med": "adhd_behavioral_med",
    "uri_cold_viral": "uri_sinus_throat",
    "cough_bronchitis": "uri_sinus_throat",
    "covid_flu": "uri_sinus_throat",
    "sinusitis": "uri_sinus_throat",
    "sore_throat_strep": "uri_sinus_throat",
    "allergies": "asthma_allergy",
    "asthma_wheezing": "asthma_allergy",
    "uti": "uti_symptoms",
    "vaginal_discharge": "vaginal_sti",
    "sti_exposure": "vaginal_sti",
    "rash_hives": "rash",
    "skin_infection": "skin_infection",
    "acne_dermatology": "routine_dermatology",
    "pink_eye": "eye_ear",
    "ear_pain": "eye_ear",
    "nausea_vomiting_diarrhea": "gi_symptoms",
    "heartburn_indigestion": "gerd_dyspepsia",
    "headache_migraine": "headache_migraine",
    "back_musculoskeletal_pain": "musculoskeletal_pain",
    "obesity_glp1_metabolic": "obesity_metabolic",
    "diabetes_chronic_checkin": "diabetes_hyperglycemia",
}


def test_top_telemedicine_reasons_have_supported_templates():
    for reason, domain in TOP_25_TELEMEDICINE_COVERAGE.items():
        assert domain in DOMAIN_TEMPLATES, f"{reason} maps to missing template {domain}"
        assert domain in SUPPORTED_DEMO_DOMAINS, f"{domain} missing from BSG supported envelope"
        assert len(DOMAIN_TEMPLATES[domain]) >= 5, f"{domain} template is too thin"


def test_new_high_volume_domains_have_red_flag_patterns():
    newly_added = {
        "mental_health",
        "adhd_behavioral_med",
        "general_med_management",
        "followup_lab_review",
        "uri_sinus_throat",
        "asthma_allergy",
        "vaginal_sti",
        "eye_ear",
        "gi_symptoms",
        "gerd_dyspepsia",
        "musculoskeletal_pain",
        "routine_dermatology",
        "skin_infection",
        "obesity_metabolic",
    }
    for domain in newly_added:
        assert domain in RED_FLAG_PATTERNS
        assert len(RED_FLAG_PATTERNS[domain]) >= 2


def test_mental_health_self_harm_escalates():
    case = CaseInput(
        case_id="test-mental-health-self-harm",
        patient_context=PatientContext(
            age=31,
            chief_concern="anxiety and depression",
            domain="mental_health",
            modality="text",
        ),
        statements=[
            Statement(
                question="Are you safe?",
                answer="I am thinking about ending my life tonight and I am not safe.",
                concept="self_harm",
            ),
            Statement(
                question="Is anyone with you?",
                answer="No, I am alone.",
                concept="support_safety_plan",
            ),
        ],
    )
    report = JudgmentReadinessEngine().evaluate(case)
    assert report.state == "ESCALATE"
    assert any(f.concept == "self_harm" and f.category == "red_flag" for f in report.findings)


def test_uri_airway_red_flag_escalates():
    case = CaseInput(
        case_id="test-uri-airway",
        patient_context=PatientContext(
            age=44,
            chief_concern="sore throat",
            domain="uri_sinus_throat",
            modality="phone",
        ),
        statements=[
            Statement(
                question="Any trouble swallowing?",
                answer="I am drooling and cannot swallow saliva, my voice sounds muffled.",
                concept="throat_airway",
            ),
            Statement(
                question="Fever?",
                answer="102.8",
                concept="fever_measured",
            ),
        ],
    )
    report = JudgmentReadinessEngine().evaluate(case)
    assert report.state == "ESCALATE"
    assert any(f.concept == "throat_airway" and f.category == "red_flag" for f in report.findings)


def test_clean_supported_new_domain_does_not_get_envelope_breach():
    case = CaseInput(
        case_id="test-clean-uri",
        patient_context=PatientContext(
            age=29,
            chief_concern="runny nose",
            domain="uri_sinus_throat",
            modality="text",
        ),
        statements=[
            Statement(question="Duration?", answer="Two days, improving.", concept="symptom_duration"),
            Statement(question="Fever?", answer="98.6 today.", concept="fever_measured", source="device"),
            Statement(question="Breathing?", answer="No shortness of breath or chest pain.", concept="breathing_status"),
            Statement(question="Throat?", answer="No trouble swallowing, no drooling.", concept="throat_airway"),
            Statement(question="Risks?", answer="Not pregnant or immunocompromised.", concept="immune_risk"),
            Statement(question="Testing?", answer="COVID test negative today.", concept="test_status"),
        ],
    )
    jre = JudgmentReadinessEngine().evaluate(case)
    bsg = BlackSwanGuardrailEngine().evaluate(case, jre)
    assert not any(f.rule_id == "ENVELOPE_UNSUPPORTED_DOMAIN" for f in bsg.findings)
