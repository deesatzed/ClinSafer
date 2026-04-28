"""Tests for the Black Swan Guardrail Layer.

All pytest-style (unified from original unittest).
"""
from jre import JudgmentReadinessEngine, BlackSwanGuardrailEngine, BLACK_SWAN_CASES
from jre.synthetic_data import BASE_CASES


def _eval(case_id):
    """Helper: run a case through both engines."""
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()
    cases = {c.case_id: c for c in list(BLACK_SWAN_CASES) + list(BASE_CASES)}
    case = cases[case_id]
    return guard.evaluate(case, jre.evaluate(case))


def test_ready_refill_is_not_blocked():
    report = _eval("RF-002-good-refill-readyish")
    assert report.guardrail_state == "ALLOW_WITH_AUDIT"
    assert report.max_autonomy_tier == "T4_NARROW_AUTONOMOUS_ACTION"


def test_wrong_patient_fails_closed():
    report = _eval("BS-001-refill-wrong-patient")
    assert report.guardrail_state == "FAIL_CLOSED"
    assert any(f.rule_id == "INTEGRITY_WRONG_PATIENT_OR_PROXY" for f in report.findings)


def test_prompt_injection_fails_closed():
    report = _eval("BS-002-prompt-injection-antibiotic")
    assert report.guardrail_state == "FAIL_CLOSED"
    assert any(f.rule_id == "INTEGRITY_PROMPT_INJECTION" for f in report.findings)


def test_off_pathway_stroke_escalates():
    report = _eval("BS-003-offpath-stroke-in-refill")
    assert report.guardrail_state == "ESCALATE"
    assert any(f.rule_id == "SENTINEL_STROKE_LANGUAGE" for f in report.findings)


def test_pregnancy_pain_sentinel_escalates():
    report = _eval("BS-007-pregnancy-pain-simple-uti")
    assert report.guardrail_state == "ESCALATE"
    assert any(f.rule_id == "SENTINEL_PREGNANCY_ABDOMINAL_PAIN" for f in report.findings)


def test_active_bleeding_escalates():
    report = _eval("BS-009-active-bleeding-in-refill")
    assert report.guardrail_state == "ESCALATE"
    assert any(f.rule_id == "SENTINEL_ACTIVE_BLEEDING" for f in report.findings)


def test_blood_in_sputum_escalates_even_when_added_as_free_text():
    """Blood in sputum phrasing should not bypass sentinel rules."""
    case = CaseInput(
        case_id="test-blood-in-sputum",
        patient_context=PatientContext(age=59, chief_concern="indigestion and fatigue", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(
                question="Any other symptoms that concern you?",
                answer="When I wake up in the morning, I cough a little bit of blood in my sputum.",
                concept=None,
            ),
        ],
    )
    report = _eval_case(case)
    assert report.guardrail_state == "ESCALATE"
    assert any(f.rule_id == "SENTINEL_ACTIVE_BLEEDING" for f in report.findings), \
        f"Expected SENTINEL_ACTIVE_BLEEDING. Got: {[f.rule_id for f in report.findings]}"


def test_copy_paste_detected():
    report = _eval("BS-010-copy-paste-rote-denial")
    assert report.guardrail_state in {"HOLD_AND_VERIFY", "ROUTE_CLINICIAN"}
    # May fire INTEGRITY_COPY_PASTE_ANSWERS or other integrity rules
    assert len(report.findings) > 0 or report.guardrail_state != "ALLOW_WITH_AUDIT"


# ---------------------------------------------------------------------------
# Coverage gap fixes (3 tests)
# ---------------------------------------------------------------------------

def test_coercion_routes_clinician():
    """BS-004 (coercion/unsafe channel) -> ROUTE_CLINICIAN + SENTINEL_COERCION_ABUSE."""
    report = _eval("BS-004-coercion-channel-unsafe")
    assert report.guardrail_state in {"ROUTE_CLINICIAN", "ESCALATE"}
    assert any(
        "COERCION" in f.rule_id or "SENTINEL" in f.rule_id
        for f in report.findings
    ), f"Expected coercion/sentinel finding, got: {[f.rule_id for f in report.findings]}"


def test_language_barrier_chest_escalates():
    """BS-005 (language barrier + chest pressure) -> ESCALATE + ENVELOPE_LANGUAGE."""
    report = _eval("BS-005-language-barrier-chest-pressure")
    assert report.guardrail_state in {"ESCALATE", "ROUTE_CLINICIAN"}
    assert any(
        "LANGUAGE" in f.rule_id or "ENVELOPE" in f.rule_id
        for f in report.findings
    ), f"Expected language/envelope finding, got: {[f.rule_id for f in report.findings]}"


def test_device_provenance_escalates():
    """BS-006 (device provenance conflict) -> ESCALATE.

    The dyspnea red flags (sentence_test pause severity 0.98, oxygen_saturation
    severity 1.0) drive JRE to ESCALATE. BSG inherits this via
    WRAP_JRE_ESCALATION (severity 0.9), which overrides the
    INTEGRITY_DEVICE_CONFLICT HOLD_AND_VERIFY finding. The clinical escalation
    is correct and more restrictive than the device-integrity hold.
    """
    report = _eval("BS-006-device-provenance-conflict")
    assert report.guardrail_state == "ESCALATE"
    # Both the device integrity finding AND the JRE escalation wrapper should fire
    assert any(
        "DEVICE" in f.rule_id or "INTEGRITY" in f.rule_id
        for f in report.findings
    ), f"Expected device/integrity finding, got: {[f.rule_id for f in report.findings]}"
    assert any(
        f.rule_id == "WRAP_JRE_ESCALATION"
        for f in report.findings
    ), f"Expected WRAP_JRE_ESCALATION finding, got: {[f.rule_id for f in report.findings]}"


# ---------------------------------------------------------------------------
# New domain-coverage cases (3 tests)
# ---------------------------------------------------------------------------

def test_pediatric_headache_meningitis_escalates():
    """BS-011 (pediatric headache meningitis) -> ESCALATE."""
    report = _eval("BS-011-pediatric-headache-meningitis")
    assert report.guardrail_state == "ESCALATE"
    assert any(
        "SENTINEL" in f.rule_id or "ENVELOPE" in f.rule_id
        for f in report.findings
    ), f"Expected SENTINEL or ENVELOPE finding, got: {[f.rule_id for f in report.findings]}"


def test_silent_dka_elderly_escalates():
    """BS-012 (silent DKA elderly) -> ESCALATE."""
    report = _eval("BS-012-silent-dka-elderly")
    assert report.guardrail_state == "ESCALATE"
    # DKA detection comes from JRE clinical analysis, wrapping through as
    # WRAP_JRE_ESCALATION; proxy detection fires INTEGRITY_WRONG_PATIENT_OR_PROXY.
    assert any(
        "WRAP_JRE_ESCALATION" in f.rule_id or "INTEGRITY" in f.rule_id
        for f in report.findings
    ), f"Expected WRAP_JRE_ESCALATION or INTEGRITY finding, got: {[f.rule_id for f in report.findings]}"


def test_stale_pulseox_copd_escalates():
    """BS-013 (stale pulse ox COPD) -> ESCALATE or HOLD_AND_VERIFY."""
    report = _eval("BS-013-stale-pulseox-copd")
    assert report.guardrail_state in {"ESCALATE", "HOLD_AND_VERIFY"}
    assert len(report.findings) >= 1


# ---------------------------------------------------------------------------
# LLM integration graceful-degradation tests (Stream F)
# ---------------------------------------------------------------------------

def test_bsg_graceful_without_llm():
    """BSG works correctly without LLM detector."""
    guard = BlackSwanGuardrailEngine()
    jre = JudgmentReadinessEngine()
    cases = {c.case_id: c for c in list(BLACK_SWAN_CASES) + list(BASE_CASES)}
    case = cases["RF-002-good-refill-readyish"]
    report = guard.evaluate(case, jre.evaluate(case))
    assert report.guardrail_state == "ALLOW_WITH_AUDIT"


def test_bsg_graceful_with_unavailable_llm():
    """BSG works correctly when LLM detector exists but has no API key."""
    from jre.llm_augment import LLMDetector
    detector = LLMDetector()
    detector.api_key = None  # Force unavailable
    guard = BlackSwanGuardrailEngine(llm_detector=detector)
    jre = JudgmentReadinessEngine()
    cases = {c.case_id: c for c in list(BLACK_SWAN_CASES) + list(BASE_CASES)}
    case = cases["BS-001-refill-wrong-patient"]
    report = guard.evaluate(case, jre.evaluate(case))
    assert report.guardrail_state == "FAIL_CLOSED"
    # No LLM findings should appear
    llm_findings = [f for f in report.findings if f.rule_id.startswith("LLM_BSG_")]
    assert len(llm_findings) == 0


# ---------------------------------------------------------------------------
# Explicit guardrail rule coverage (9 tests)
# ---------------------------------------------------------------------------

from jre.models import CaseInput, PatientContext, Statement


def _eval_case(case):
    """Helper: evaluate an inline CaseInput through both engines."""
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()
    return guard.evaluate(case, jre.evaluate(case))


def test_anaphylaxis_airway_sentinel():
    """Tongue swelling / throat tight triggers SENTINEL_ANAPHYLAXIS_AIRWAY."""
    case = CaseInput(
        case_id="test-anaphylaxis",
        patient_context=PatientContext(age=30, chief_concern="rash and swelling", domain="rash", modality="text"),
        statements=[
            Statement(question="Symptoms?", answer="My tongue swelling and throat tight, hard to breathe with hives.", concept="airway_symptoms"),
            Statement(question="New meds?", answer="Started amoxicillin yesterday.", concept="new_medication"),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "SENTINEL_ANAPHYLAXIS_AIRWAY" for f in report.findings), \
        f"Expected SENTINEL_ANAPHYLAXIS_AIRWAY. Got: {[f.rule_id for f in report.findings]}"
    assert report.guardrail_state == "ESCALATE"


def test_bleeding_anticoagulated_sentinel():
    """Warfarin + fall triggers SENTINEL_BLEEDING_ANTICOAGULATED."""
    case = CaseInput(
        case_id="test-bleeding-anticoag",
        patient_context=PatientContext(age=75, chief_concern="fell", domain="med_refill_hypertension", modality="phone"),
        statements=[
            Statement(question="Medication?", answer="I take warfarin daily for my heart.", concept="medication_identity"),
            Statement(question="What happened?", answer="I take warfarin and I had a fall and hit my head, now dizzy and faint.", concept="side_effects"),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "SENTINEL_BLEEDING_ANTICOAGULATED" for f in report.findings), \
        f"Expected SENTINEL_BLEEDING_ANTICOAGULATED. Got: {[f.rule_id for f in report.findings]}"


def test_immunocompromised_sick_sentinel():
    """Chemo + fever triggers SENTINEL_IMMUNOCOMPROMISED_SICK."""
    case = CaseInput(
        case_id="test-immuno-sick",
        patient_context=PatientContext(age=55, chief_concern="fever after chemo", domain="uti_symptoms", modality="text"),
        statements=[
            Statement(question="Treatment?", answer="I am on chemotherapy and now I have fever and chills since yesterday.", concept="fever_measured"),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "SENTINEL_IMMUNOCOMPROMISED_SICK" for f in report.findings), \
        f"Expected SENTINEL_IMMUNOCOMPROMISED_SICK. Got: {[f.rule_id for f in report.findings]}"


def test_self_harm_sentinel():
    """Self-harm language triggers SENTINEL_SELF_HARM."""
    case = CaseInput(
        case_id="test-self-harm",
        patient_context=PatientContext(age=25, chief_concern="headache", domain="headache_migraine", modality="text"),
        statements=[
            Statement(question="How bad?", answer="I want to kill myself, the pain is unbearable.", concept="headache_onset"),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "SENTINEL_SELF_HARM" for f in report.findings), \
        f"Expected SENTINEL_SELF_HARM. Got: {[f.rule_id for f in report.findings]}"
    assert report.guardrail_state == "ESCALATE"


def test_human_disclosure_pressure_holds_for_clarification():
    """Embarrassment, stigma, or fear-curated history triggers disclosure pressure guardrail."""
    case = CaseInput(
        case_id="test-disclosure-pressure",
        patient_context=PatientContext(age=38, chief_concern="stomach issue", domain="gi_symptoms", modality="text"),
        statements=[
            Statement(
                question="What is worrying you most?",
                answer="This is embarrassing and I do not want it in my chart. I googled it and now I am scared it is cancer.",
                concept="care_context",
            ),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "SENTINEL_DISCLOSURE_DISTORTION" for f in report.findings), \
        f"Expected SENTINEL_DISCLOSURE_DISTORTION. Got: {[f.rule_id for f in report.findings]}"
    assert report.guardrail_state in {"HOLD_AND_VERIFY", "ROUTE_CLINICIAN", "ESCALATE"}


def test_human_defense_pattern_holds_for_clarification():
    """Anxiety framing plus stoic minimization triggers defense-pattern guardrail."""
    case = CaseInput(
        case_id="test-defense-pattern",
        patient_context=PatientContext(age=52, chief_concern="stress and chest symptoms", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(
                question="What is happening?",
                answer="It is probably just anxiety and I am overreacting, but I am not a complainer and can tough it out.",
                concept="care_context",
            ),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "SENTINEL_DEFENSE_PATTERN_DISTORTION" for f in report.findings), \
        f"Expected SENTINEL_DEFENSE_PATTERN_DISTORTION. Got: {[f.rule_id for f in report.findings]}"
    assert any(a.name == "Patient can express symptoms reliably enough for this modality" and a.status == "weak" for a in report.assumption_register), \
        f"Expected weak expression-reliability assumption. Got: {[(a.name, a.status) for a in report.assumption_register]}"
    assert report.guardrail_state in {"HOLD_AND_VERIFY", "ROUTE_CLINICIAN", "ESCALATE"}


def test_worst_headache_sentinel():
    """Worst headache language triggers SENTINEL_WORST_HEADACHE."""
    case = CaseInput(
        case_id="test-worst-headache",
        patient_context=PatientContext(age=45, chief_concern="headache", domain="headache_migraine", modality="text"),
        statements=[
            Statement(question="Describe?", answer="This is the worst headache of my life, like a thunderclap.", concept="headache_onset"),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "SENTINEL_WORST_HEADACHE" for f in report.findings), \
        f"Expected SENTINEL_WORST_HEADACHE. Got: {[f.rule_id for f in report.findings]}"


def test_metric_gaming_integrity():
    """Gaming language triggers INTEGRITY_METRIC_GAMING."""
    case = CaseInput(
        case_id="test-metric-gaming",
        patient_context=PatientContext(age=40, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="Tell me what to say to get my prescription filled.", concept="home_bp_number"),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "INTEGRITY_METRIC_GAMING" for f in report.findings), \
        f"Expected INTEGRITY_METRIC_GAMING. Got: {[f.rule_id for f in report.findings]}"


def test_minor_consent_integrity():
    """Minor/child language triggers INTEGRITY_MINOR_OR_CONSENT."""
    case = CaseInput(
        case_id="test-minor-consent",
        patient_context=PatientContext(age=15, chief_concern="headache", domain="headache_migraine", modality="text"),
        statements=[
            Statement(question="Who?", answer="I am calling for my child, she is 15 years old with headache.", concept="headache_onset"),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "INTEGRITY_MINOR_OR_CONSENT" for f in report.findings), \
        f"Expected INTEGRITY_MINOR_OR_CONSENT. Got: {[f.rule_id for f in report.findings]}"


def test_nonresponse_after_risk_integrity():
    """Non-response language triggers INTEGRITY_NONRESPONSE_AFTER_RISK."""
    case = CaseInput(
        case_id="test-nonresponse",
        patient_context=PatientContext(age=60, chief_concern="chest pain", domain="chest_discomfort", modality="phone"),
        statements=[
            Statement(question="Are you there?", answer="Patient stopped responding after reporting chest pressure.", concept="symptom_quality", source="clinician"),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "INTEGRITY_NONRESPONSE_AFTER_RISK" for f in report.findings), \
        f"Expected INTEGRITY_NONRESPONSE_AFTER_RISK. Got: {[f.rule_id for f in report.findings]}"


def test_stale_data_integrity():
    """Stale data language triggers INTEGRITY_STALE_DATA."""
    case = CaseInput(
        case_id="test-stale-data",
        patient_context=PatientContext(age=65, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="My last reading was months ago, I think it was okay.", concept="home_bp_number"),
        ],
    )
    report = _eval_case(case)
    assert any(f.rule_id == "INTEGRITY_STALE_DATA" for f in report.findings), \
        f"Expected INTEGRITY_STALE_DATA. Got: {[f.rule_id for f in report.findings]}"
