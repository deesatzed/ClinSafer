from jre import JudgmentReadinessEngine
from jre.models import CaseInput, PatientContext, Statement
from jre.experience import ExperienceMemory, ExperienceEvent
from jre.synthetic_data import BASE_CASES


def by_id(case_id):
    return next(c for c in BASE_CASES if c.case_id == case_id)


def test_chest_pressure_escalates():
    r = JudgmentReadinessEngine().evaluate(by_id("CP-001-heartburn-pressure"))
    assert r.state == "ESCALATE"
    assert any(f.category == "red_flag" for f in r.findings)
    assert any("pressure" in (f.evidence or "").lower() for f in r.findings)


def test_bp_refill_requires_objective_data():
    r = JudgmentReadinessEngine().evaluate(by_id("RF-001-bp-normal-no-number"))
    assert r.state in {"NEED_OBJECTIVE_DATA", "CLARIFY"}
    assert any(f.concept == "home_bp_number" and f.category in {"distorted", "objective_needed"} for f in r.findings)
    assert any("exact numbers" in q.question.lower() for q in r.next_questions)


def test_good_refill_ready_or_high_jri():
    r = JudgmentReadinessEngine().evaluate(by_id("RF-002-good-refill-readyish"))
    assert r.scores.readiness_index >= 75
    assert r.state in {"READY", "CLARIFY"}  # depends on strict remote-boundary policy


def test_dyspnea_denial_caught():
    r = JudgmentReadinessEngine().evaluate(by_id("DY-001-denies-sob-low-ox"))
    assert r.state == "ESCALATE"
    assert any(f.concept == "oxygen_saturation" for f in r.findings)
    assert any(q.concept in {"oxygen_saturation", "sentence_test", "exertional_tolerance"} for q in r.next_questions)


def test_boundary_map_has_unknowns():
    r = JudgmentReadinessEngine().evaluate(by_id("CP-002-low-risk-but-incomplete"))
    assert "remote_boundary" in r.boundary_map
    assert any("ecg" in item.lower() for item in r.boundary_map["remote_boundary"])


def test_headache_thunderclap_escalates():
    r = JudgmentReadinessEngine().evaluate(by_id("HA-001-thunderclap-minimized"))
    assert r.state == "ESCALATE"
    assert any(f.category == "red_flag" for f in r.findings)


# ---------------------------------------------------------------------------
# Source Conflict Detection (3 tests)
# ---------------------------------------------------------------------------

def test_source_conflict_device_vs_patient():
    """Two observations for same concept from device/patient with disagreement generate conflict finding."""
    case = CaseInput(
        case_id="test-source-conflict",
        patient_context=PatientContext(age=65, chief_concern="BP check", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="What is your BP?", answer="It's fine, normal.", concept="home_bp_number", source="patient"),
            Statement(question="Device BP reading?", answer="192/105", concept="home_bp_number", source="device"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    conflict_findings = [f for f in r.findings if f.rule_id.startswith("SOURCE_CONFLICT_")]
    assert len(conflict_findings) >= 1, "Should detect device vs patient conflict"
    assert conflict_findings[0].category == "contradictory"
    assert conflict_findings[0].severity == 0.70


def test_source_conflict_same_source_no_conflict():
    """Two observations from the same source type should not generate a source conflict."""
    case = CaseInput(
        case_id="test-no-source-conflict",
        patient_context=PatientContext(age=50, chief_concern="BP", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP reading?", answer="130/85", concept="home_bp_number", source="patient"),
            Statement(question="Another BP?", answer="135/88", concept="home_bp_number", source="patient"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    conflict_findings = [f for f in r.findings if f.rule_id.startswith("SOURCE_CONFLICT_")]
    assert len(conflict_findings) == 0, "Same source should not trigger conflict"


def test_source_conflict_evidence_shows_both():
    """Source conflict evidence string contains both source values."""
    case = CaseInput(
        case_id="test-conflict-evidence",
        patient_context=PatientContext(age=70, chief_concern="BP", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="No problems at all.", concept="home_bp_number", source="patient"),
            Statement(question="Device?", answer="188/110", concept="home_bp_number", source="device"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    conflict_findings = [f for f in r.findings if f.rule_id.startswith("SOURCE_CONFLICT_")]
    assert len(conflict_findings) >= 1
    evidence = conflict_findings[0].evidence
    assert "device" in evidence
    assert "patient" in evidence


# ---------------------------------------------------------------------------
# Hypertensive Urgency Gestalt (2 tests)
# ---------------------------------------------------------------------------

def test_hypertensive_urgency_gestalt_fires():
    """High BP + symptoms triggers GESTALT_HYPERTENSIVE_URGENCY."""
    case = CaseInput(
        case_id="test-htn-urgency",
        patient_context=PatientContext(age=58, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="195/110, I measured it twice.", concept="home_bp_number"),
            Statement(question="Side effects?", answer="I have a terrible headache and I'm dizzy.", concept="side_effects"),
            Statement(question="Medication?", answer="Lisinopril 20mg", concept="medication_identity"),
            Statement(question="Last dose?", answer="Yesterday morning.", concept="last_taken"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    gestalt = [f for f in r.findings if f.rule_id == "GESTALT_HYPERTENSIVE_URGENCY"]
    assert len(gestalt) >= 1, "Should fire hypertensive urgency gestalt"
    assert gestalt[0].severity == 0.95


def test_hypertensive_urgency_needs_both_required():
    """BP alone without symptoms should not trigger gestalt."""
    case = CaseInput(
        case_id="test-htn-no-symptoms",
        patient_context=PatientContext(age=55, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="190/105", concept="home_bp_number"),
            Statement(question="Side effects?", answer="No side effects at all, feeling fine.", concept="side_effects"),
            Statement(question="Medication?", answer="Amlodipine 10mg", concept="medication_identity"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    gestalt = [f for f in r.findings if f.rule_id == "GESTALT_HYPERTENSIVE_URGENCY"]
    assert len(gestalt) == 0, "Should not fire without both required signals"


# ---------------------------------------------------------------------------
# New Contradiction Rules (5 tests)
# ---------------------------------------------------------------------------

def test_contradiction_uti_fever_denial():
    """UTI fever denial with 'I feel hot' triggers CONTRA_UTI_DENIES_FEVER_BUT_HOT."""
    case = CaseInput(
        case_id="test-uti-fever-contra",
        patient_context=PatientContext(age=32, chief_concern="UTI", domain="uti_symptoms", modality="text"),
        statements=[
            Statement(question="Fever?", answer="No fever, I haven't checked but I feel hot and sweating.", concept="fever_measured"),
            Statement(question="Burning?", answer="Yes, burning when I pee.", concept="dysuria"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    contra = [f for f in r.findings if f.rule_id == "CONTRA_UTI_DENIES_FEVER_BUT_HOT"]
    assert len(contra) >= 1, "Should detect fever denial with hot language"


def test_contradiction_uti_flank_pain():
    """Simple UTI + flank pain triggers CONTRA_UTI_SIMPLE_BUT_FLANK."""
    case = CaseInput(
        case_id="test-uti-flank-contra",
        patient_context=PatientContext(age=28, chief_concern="UTI", domain="uti_symptoms", modality="text"),
        statements=[
            Statement(question="Burning?", answer="Yes, painful urination.", concept="dysuria"),
            Statement(question="Flank pain?", answer="My kidney area hurts on the right side.", concept="flank_pain"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    contra = [f for f in r.findings if f.rule_id == "CONTRA_UTI_SIMPLE_BUT_FLANK"]
    assert len(contra) >= 1, "Should detect flank pain contradiction"


def test_contradiction_rash_airway():
    """Airway denial + throat tightness triggers CONTRA_RASH_DENIES_AIRWAY_BUT_THROAT."""
    case = CaseInput(
        case_id="test-rash-airway-contra",
        patient_context=PatientContext(age=40, chief_concern="rash", domain="rash", modality="text"),
        statements=[
            Statement(question="Airway symptoms?", answer="No trouble breathing, but my throat feels tight and it's hard to swallow.", concept="airway_symptoms"),
            Statement(question="Mucosal?", answer="No mouth sores.", concept="mucosal_involvement"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    contra = [f for f in r.findings if f.rule_id == "CONTRA_RASH_DENIES_AIRWAY_BUT_THROAT"]
    assert len(contra) >= 1, "Should detect airway denial with throat tightness"


def test_contradiction_dm_glucose_fine_but_vomiting():
    """Glucose 'fine' + vomiting triggers CONTRA_DM_GLUCOSE_FINE_BUT_SYMPTOMS."""
    case = CaseInput(
        case_id="test-dm-glucose-contra",
        patient_context=PatientContext(age=55, chief_concern="diabetes", domain="diabetes_hyperglycemia", modality="text"),
        statements=[
            Statement(question="Glucose?", answer="My sugar is fine, I checked it.", concept="glucose_number"),
            Statement(question="Vomiting?", answer="I've been throwing up and can't keep water down, very thirsty.", concept="vomiting"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    contra = [f for f in r.findings if f.rule_id == "CONTRA_DM_GLUCOSE_FINE_BUT_SYMPTOMS"]
    assert len(contra) >= 1, "Should detect glucose fine but DKA symptoms"


def test_contradiction_dm_confusion_denied():
    """Mental status denial + confusion language triggers CONTRA_DM_DENIES_CONFUSION_BUT_CAREGIVER."""
    case = CaseInput(
        case_id="test-dm-confusion-contra",
        patient_context=PatientContext(age=70, chief_concern="diabetes", domain="diabetes_hyperglycemia", modality="text"),
        statements=[
            Statement(question="Mental status?", answer="No, I'm not confused, but my daughter says I'm not making sense today and acting strange.", concept="mental_status"),
            Statement(question="Glucose?", answer="450", concept="glucose_number"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    contra = [f for f in r.findings if f.rule_id == "CONTRA_DM_DENIES_CONFUSION_BUT_CAREGIVER"]
    assert len(contra) >= 1, "Should detect confusion denial with caregiver report"


# ---------------------------------------------------------------------------
# ExperienceMemory Learning (4 tests)
# ---------------------------------------------------------------------------

def test_experience_record_event_updates_priors():
    """After record_event, prior_penalty returns updated value."""
    mem = ExperienceMemory.seeded()
    old_val = mem.prior_penalty("chest_discomfort", "symptom_quality", "pain_word_boundary")
    from jre.experience import ExperienceEvent
    mem.record_event(ExperienceEvent(
        domain="chest_discomfort", concept="symptom_quality", trap="pain_word_boundary",
        phrase="not pain, pressure", initial_answer="not pain, pressure",
        clarified_truth="", question_used="When you say it is not chest pain...",
        information_gain=0.8, outcome_label="test",
    ))
    new_val = mem.prior_penalty("chest_discomfort", "symptom_quality", "pain_word_boundary")
    assert new_val != old_val, "Prior should change after record_event"


def test_experience_question_yield_updates():
    """After record_event, question yield for the domain+question changes."""
    mem = ExperienceMemory.seeded()
    q = "When you say it is not chest pain, is there pressure, tightness, heaviness, squeezing, burning, or discomfort anywhere in the chest, jaw, arm, back, or upper belly?"
    old_yield = mem.expected_question_yield("chest_discomfort", q)
    from jre.experience import ExperienceEvent
    mem.record_event(ExperienceEvent(
        domain="chest_discomfort", concept="symptom_quality", trap="pain_word_boundary",
        phrase="pressure", initial_answer="pressure",
        clarified_truth="", question_used=q,
        information_gain=0.9, outcome_label="test",
    ))
    new_yield = mem.expected_question_yield("chest_discomfort", q)
    assert new_yield != old_yield, "Question yield should change after record_event"


def test_experience_seeded_question_yield():
    """seeded() now populates question_yield with non-default values."""
    mem = ExperienceMemory.seeded()
    # At least some question_yield entries should exist and differ from 0.62
    assert len(mem.question_yield) >= 10, f"Expected >=10 seeded yields, got {len(mem.question_yield)}"
    non_default = [v for v in mem.question_yield.values() if v != 0.62]
    assert len(non_default) >= 10, "Seeded yields should not all be 0.62"


def test_experience_ema_convergence_direction():
    """High information_gain events should increase distortion priors, not decrease."""
    mem = ExperienceMemory.seeded()
    from jre.experience import ExperienceEvent
    key = ("chest_discomfort", "symptom_quality", "pain_word_boundary")
    old_val = mem.distortion_priors[key]
    # Record high-gain event
    for _ in range(5):
        mem.record_event(ExperienceEvent(
            domain="chest_discomfort", concept="symptom_quality", trap="pain_word_boundary",
            phrase="not pain", initial_answer="not pain",
            clarified_truth="actually pressure", question_used="test q",
            information_gain=0.95, outcome_label="test",
        ))
    new_val = mem.distortion_priors[key]
    # With high info gain (0.95), target = 0.95*0.35 = 0.3325
    # Starting from 0.20, EMA should push toward 0.3325 (increase)
    assert new_val > old_val, f"High-gain events should increase prior: {old_val} -> {new_val}"


# ---------------------------------------------------------------------------
# Escalation Probes and Smart Questions (3 tests)
# ---------------------------------------------------------------------------

def test_escalation_probe_replaces_slot_question():
    """Red flag with severity >= 0.85 gets ESCALATION_PROBES question instead of slot question."""
    from jre.templates import ESCALATION_PROBES
    case = CaseInput(
        case_id="test-escalation-probe",
        patient_context=PatientContext(age=60, chief_concern="chest", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(question="Describe?", answer="Crushing pressure that started 30 minutes ago, worst ever.", concept="symptom_quality"),
            Statement(question="Activity?", answer="Yes, worse with any movement.", concept="exertional_component"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    probe_text = ESCALATION_PROBES.get(("chest_discomfort", "symptom_quality"))
    assert probe_text is not None
    probe_in_questions = any(probe_text == q.question for q in r.next_questions)
    # The probe should appear for high-severity red flags
    assert probe_in_questions, f"Escalation probe should appear. Got questions: {[q.question for q in r.next_questions]}"


def test_gestalt_finding_generates_question():
    """Gestalt finding produces a question for the weakest contributing observation."""
    case = CaseInput(
        case_id="test-gestalt-question",
        patient_context=PatientContext(age=60, chief_concern="chest pressure", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(question="Describe?", answer="Heavy pressure in my chest.", concept="symptom_quality"),
            Statement(question="Activity?", answer="Gets better when I sit down, worse walking.", concept="exertional_component"),
            Statement(question="Sweating?", answer="Yes, clammy and nauseous.", concept="diaphoresis"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    gestalt = [f for f in r.findings if f.rule_id.startswith("GESTALT_")]
    assert len(gestalt) >= 1, "Should fire gestalt"
    # Questions should include something for the gestalt contributing concepts
    assert len(r.next_questions) >= 1, "Gestalt should produce at least one question"


def test_question_index_rotation():
    """When concept has multiple findings, different clarify_questions are used."""
    # Create a case where symptom_quality gets both a distorted finding and a red_flag,
    # so it should try to use different question indices
    case = CaseInput(
        case_id="test-question-rotation",
        patient_context=PatientContext(age=50, chief_concern="chest", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(question="Describe?", answer="Not pain, but I have pressure that's kind of bad.", concept="symptom_quality"),
            Statement(question="Breathing?", answer="Not short of breath but I can't walk up stairs, I have to stop.", concept="dyspnea"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    # Check that questions for the same concept don't duplicate text
    questions_by_concept: dict[str, list[str]] = {}
    for q in r.next_questions:
        questions_by_concept.setdefault(q.concept, []).append(q.question)
    for concept, qs in questions_by_concept.items():
        assert len(qs) == len(set(qs)), f"Duplicate questions for {concept}: {qs}"


# ---------------------------------------------------------------------------
# Distortion Prior Coverage (1 test)
# ---------------------------------------------------------------------------

def test_experience_all_traps_have_priors():
    """Every trap defined in DOMAIN_TEMPLATES has a seeded distortion prior."""
    from jre.templates import DOMAIN_TEMPLATES
    from jre.experience import ExperienceMemory
    mem = ExperienceMemory.seeded()
    missing = []
    for domain, slots in DOMAIN_TEMPLATES.items():
        for slot in slots:
            for trap in slot.traps:
                if (domain, slot.name, trap) not in mem.distortion_priors:
                    missing.append((domain, slot.name, trap))
    assert len(missing) == 0, f"Missing distortion priors for: {missing}"


# ---------------------------------------------------------------------------
# Headache & Dyspnea Additional Contradiction Rules (4 tests)
# ---------------------------------------------------------------------------

def test_contradiction_headache_neuro_denial():
    """Headache neuro deficit denial with focal symptoms triggers CONTRA_HA_DENIES_NEURO_BUT_SYMPTOMS."""
    case = CaseInput(
        case_id="test-ha-neuro-contra",
        patient_context=PatientContext(age=55, chief_concern="headache", domain="headache_migraine", modality="text"),
        statements=[
            Statement(question="Neuro symptoms?", answer="No weakness or numbness, but my vision is blurry and I see double.", concept="neuro_deficit"),
            Statement(question="Onset?", answer="Started this morning.", concept="headache_onset"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    contra = [f for f in r.findings if f.rule_id == "CONTRA_HA_DENIES_NEURO_BUT_SYMPTOMS"]
    assert len(contra) >= 1, "Should detect neuro denial with focal symptoms"


def test_contradiction_headache_no_fever_stiff_neck():
    """Headache fever denial + stiff neck triggers CONTRA_HA_NO_FEVER_BUT_STIFF_NECK."""
    case = CaseInput(
        case_id="test-ha-fever-neck-contra",
        patient_context=PatientContext(age=30, chief_concern="headache", domain="headache_migraine", modality="text"),
        statements=[
            Statement(question="Fever?", answer="No fever, I haven't checked.", concept="fever_measured"),
            Statement(question="Neck?", answer="My neck is stiff, I can't touch my chin to chest.", concept="neck_stiffness"),
            Statement(question="Onset?", answer="Worst headache of my life.", concept="headache_onset"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    contra = [f for f in r.findings if f.rule_id == "CONTRA_HA_NO_FEVER_BUT_STIFF_NECK"]
    assert len(contra) >= 1, "Should detect fever denial with stiff neck"


def test_contradiction_dyspnea_claims_fine_but_cant_speak():
    """Dyspnea sentence test denial with gasping language triggers CONTRA_DY_CLAIMS_FINE_BUT_CANT_SPEAK."""
    case = CaseInput(
        case_id="test-dy-sentence-contra",
        patient_context=PatientContext(age=70, chief_concern="breathing", domain="dyspnea_respiratory", modality="text"),
        statements=[
            Statement(question="Sentence test?", answer="No I'm fine, but I have to stop and I'm catching my breath after every few words.", concept="sentence_test"),
            Statement(question="Oxygen?", answer="I don't have a meter.", concept="oxygen_saturation"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    contra = [f for f in r.findings if f.rule_id == "CONTRA_DY_CLAIMS_FINE_BUT_CANT_SPEAK"]
    assert len(contra) >= 1, "Should detect sentence test denial with gasping language"


def test_contradiction_dyspnea_denies_confusion():
    """Dyspnea mental status denial with drowsy language triggers CONTRA_DY_DENIES_CONFUSION_BUT_ALTERED."""
    case = CaseInput(
        case_id="test-dy-confusion-contra",
        patient_context=PatientContext(age=65, chief_concern="breathing", domain="dyspnea_respiratory", modality="text"),
        statements=[
            Statement(question="Mental status?", answer="Not confused, but I'm very sleepy and foggy, hard to think.", concept="mental_status"),
            Statement(question="Breathing?", answer="A little harder than usual.", concept="exertional_tolerance"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    contra = [f for f in r.findings if f.rule_id == "CONTRA_DY_DENIES_CONFUSION_BUT_ALTERED"]
    assert len(contra) >= 1, "Should detect mental status denial with confusion language"


# ---------------------------------------------------------------------------
# Cross-Domain Gestalt Patterns (4 tests)
# ---------------------------------------------------------------------------

def test_cross_domain_sepsis_gestalt_fires():
    """Fever + confusion in a med_refill case triggers GESTALT_SEPSIS_GENERAL."""
    case = CaseInput(
        case_id="test-cross-sepsis",
        patient_context=PatientContext(age=72, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="Fever?", answer="Yes I have fever and chills since yesterday.", concept="fever_measured"),
            Statement(question="How do you feel?", answer="I'm confused and sleepy, not right at all.", concept="mental_status"),
            Statement(question="Medication?", answer="Lisinopril 20mg", concept="medication_identity"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    gestalt = [f for f in r.findings if f.rule_id == "GESTALT_SEPSIS_GENERAL"]
    assert len(gestalt) >= 1, "Should fire cross-domain sepsis gestalt"
    assert gestalt[0].severity == 0.95


def test_cross_domain_sepsis_needs_both_signals():
    """Fever alone without confusion should not trigger GESTALT_SEPSIS_GENERAL."""
    case = CaseInput(
        case_id="test-cross-sepsis-no-fire",
        patient_context=PatientContext(age=45, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="Fever?", answer="Yes, fever 101.", concept="fever_measured"),
            Statement(question="How do you feel?", answer="Fine otherwise.", concept="mental_status"),
            Statement(question="Medication?", answer="Amlodipine 10mg", concept="medication_identity"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    gestalt = [f for f in r.findings if f.rule_id == "GESTALT_SEPSIS_GENERAL"]
    assert len(gestalt) == 0, "Should not fire without both required signals"


def test_cross_domain_anaphylaxis_gestalt_fires():
    """Airway symptoms + new medication in a rash case triggers GESTALT_ANAPHYLAXIS_GENERAL."""
    case = CaseInput(
        case_id="test-cross-anaphylaxis",
        patient_context=PatientContext(age=35, chief_concern="rash", domain="rash", modality="text"),
        statements=[
            Statement(question="Airway?", answer="My throat is tight and I can't swallow, tongue feels swollen.", concept="airway_symptoms"),
            Statement(question="New meds?", answer="Yes, started a new antibiotic yesterday.", concept="new_medication"),
            Statement(question="Skin?", answer="Hives all over, itching.", concept="skin_pain"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    gestalt = [f for f in r.findings if f.rule_id == "GESTALT_ANAPHYLAXIS_GENERAL"]
    assert len(gestalt) >= 1, "Should fire cross-domain anaphylaxis gestalt"
    assert gestalt[0].severity == 1.0


def test_cross_domain_gestalt_works_in_non_native_domain():
    """Cross-domain gestalt fires even in a domain where the concepts aren't native slots."""
    # Fever + confusion mentioned in a headache case should still trigger sepsis gestalt
    case = CaseInput(
        case_id="test-cross-gestalt-foreign-domain",
        patient_context=PatientContext(age=60, chief_concern="headache", domain="headache_migraine", modality="text"),
        statements=[
            Statement(question="Fever?", answer="Yes, 103 degrees, burning up with chills.", concept="fever_measured"),
            Statement(question="Mental status?", answer="I'm confused and drowsy, not right.", concept="mental_status"),
            Statement(question="Onset?", answer="Started today.", concept="headache_onset"),
        ],
    )
    r = JudgmentReadinessEngine().evaluate(case)
    gestalt = [f for f in r.findings if f.rule_id == "GESTALT_SEPSIS_GENERAL"]
    assert len(gestalt) >= 1, "Cross-domain gestalt should fire even in headache domain"


# ---------------------------------------------------------------------------
# Source Reliability Weighting (Stream H) -- 3 tests
# ---------------------------------------------------------------------------

def test_source_weighting_device_higher_reliability():
    """Cases with device data should have higher reliability than patient-only."""
    # Case with device source
    device_case = CaseInput(
        case_id="test-device-reliability",
        patient_context=PatientContext(age=60, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="142/88", concept="home_bp_number", source="device"),
            Statement(question="Med?", answer="Lisinopril 20mg", concept="medication_identity", source="patient"),
            Statement(question="Last dose?", answer="This morning", concept="last_taken", source="patient"),
        ],
    )
    # Same case with patient source for BP
    patient_case = CaseInput(
        case_id="test-patient-reliability",
        patient_context=PatientContext(age=60, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="142/88", concept="home_bp_number", source="patient"),
            Statement(question="Med?", answer="Lisinopril 20mg", concept="medication_identity", source="patient"),
            Statement(question="Last dose?", answer="This morning", concept="last_taken", source="patient"),
        ],
    )
    jre = JudgmentReadinessEngine()
    device_report = jre.evaluate(device_case)
    patient_report = jre.evaluate(patient_case)
    assert device_report.scores.reliability > patient_report.scores.reliability, (
        f"Device reliability {device_report.scores.reliability} should exceed patient {patient_report.scores.reliability}"
    )


def test_source_weighting_objective_coverage_device_vs_patient():
    """Device-sourced objective data should get full credit vs partial for patient."""
    device_case = CaseInput(
        case_id="test-obj-device",
        patient_context=PatientContext(age=60, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="138/85", concept="home_bp_number", source="device"),
            Statement(question="Med?", answer="Amlodipine 10mg", concept="medication_identity", source="patient"),
            Statement(question="Last dose?", answer="Yesterday", concept="last_taken", source="patient"),
            Statement(question="Kidney labs?", answer="Creatinine 1.1, normal", concept="renal_function", source="chart"),
        ],
    )
    patient_case = CaseInput(
        case_id="test-obj-patient",
        patient_context=PatientContext(age=60, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="BP?", answer="138/85", concept="home_bp_number", source="patient"),
            Statement(question="Med?", answer="Amlodipine 10mg", concept="medication_identity", source="patient"),
            Statement(question="Last dose?", answer="Yesterday", concept="last_taken", source="patient"),
            Statement(question="Kidney labs?", answer="Creatinine 1.1, normal", concept="renal_function", source="patient"),
        ],
    )
    jre = JudgmentReadinessEngine()
    device_report = jre.evaluate(device_case)
    patient_report = jre.evaluate(patient_case)
    assert device_report.scores.objective_coverage > patient_report.scores.objective_coverage, (
        f"Device obj coverage {device_report.scores.objective_coverage} should exceed patient {patient_report.scores.objective_coverage}"
    )


def test_source_weighting_constants_exported():
    """SOURCE_SCORING_WEIGHT constant is accessible."""
    from jre.engine import SOURCE_SCORING_WEIGHT
    assert SOURCE_SCORING_WEIGHT["device"] > SOURCE_SCORING_WEIGHT["patient"]
    assert all(w > 0 for w in SOURCE_SCORING_WEIGHT.values())


# ---------------------------------------------------------------------------
# Outcome Feedback Loop (Stream J) -- 4 tests
# ---------------------------------------------------------------------------

def test_outcome_feedback_confirmed_decreases_prior():
    """Confirmed feedback decreases distortion prior via EMA."""
    from jre.experience import ExperienceMemory, OutcomeFeedback
    mem = ExperienceMemory.seeded()
    # Get a known prior
    key = ("chest_discomfort", "symptom_quality", "pain_word_boundary")
    old_val = mem.distortion_priors.get(key)
    assert old_val is not None, f"Expected seeded prior for {key}"

    feedback = OutcomeFeedback(
        case_id="test", concept="symptom_quality", domain="chest_discomfort",
        clinician_assessment="confirmed",
    )
    updates = mem.record_feedback(feedback)
    str_key = "chest_discomfort/symptom_quality/pain_word_boundary"
    assert str_key in updates
    assert updates[str_key] < old_val  # confirmed = less distortion expected


def test_outcome_feedback_false_positive_drops_prior_fast():
    """False positive feedback drops prior faster than confirmed."""
    from jre.experience import ExperienceMemory, OutcomeFeedback
    mem = ExperienceMemory.seeded()
    key = ("chest_discomfort", "symptom_quality", "pain_word_boundary")
    old_val = mem.distortion_priors[key]

    feedback = OutcomeFeedback(
        case_id="test", concept="symptom_quality", domain="chest_discomfort",
        clinician_assessment="false_positive",
    )
    updates = mem.record_feedback(feedback)
    str_key = "chest_discomfort/symptom_quality/pain_word_boundary"
    # false_positive uses 2x alpha, so should drop faster
    assert updates[str_key] < old_val * 0.9  # Should drop noticeably


def test_outcome_feedback_missed_creates_or_increases_prior():
    """Missed feedback creates/increases distortion prior for the concept."""
    from jre.experience import ExperienceMemory, OutcomeFeedback
    mem = ExperienceMemory.seeded()

    feedback = OutcomeFeedback(
        case_id="test", concept="glucose_number", domain="diabetes_hyperglycemia",
        clinician_assessment="missed",
    )
    updates = mem.record_feedback(feedback)
    new_key = "diabetes_hyperglycemia/glucose_number/clinician_feedback"
    assert new_key in updates
    assert updates[new_key] > 0.20  # Should be above default starting point


def test_outcome_feedback_log_accumulates():
    """Feedback log grows with each submission."""
    from jre.experience import ExperienceMemory, OutcomeFeedback
    mem = ExperienceMemory.seeded()

    for i in range(3):
        feedback = OutcomeFeedback(
            case_id=f"test-{i}", concept="symptom_quality", domain="chest_discomfort",
            clinician_assessment="confirmed",
        )
        mem.record_feedback(feedback)

    assert len(mem.feedback_log) == 3


# ---------------------------------------------------------------------------
# Modality-Specific Question Adaptations (Stream I) -- 4 tests
# ---------------------------------------------------------------------------

def test_modality_phone_adapts_question():
    """Phone modality adds conversational prefix and verbal prompts."""
    # Create a case with modality="phone" that triggers a number-related question
    # (e.g., diabetes case asking about glucose)
    case = CaseInput(
        case_id="modality-phone",
        patient_context=PatientContext(
            age=55, chief_concern="high blood sugar",
            domain="diabetes_hyperglycemia", modality="phone",
        ),
        statements=[
            Statement(question="What is your blood glucose?", answer="I think it's fine", source="patient", concept="glucose_number"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    # At least one question should contain phone-specific number prompt
    all_q_text = " ".join(q.question for q in report.next_questions)
    assert "Read me the exact number" in all_q_text or "tell me" in all_q_text.lower()


def test_modality_text_adapts_question():
    """Text modality adds text-specific prompts like 'type' or 'send a photo'."""
    case = CaseInput(
        case_id="modality-text",
        patient_context=PatientContext(
            age=30, chief_concern="rash spreading",
            domain="rash", modality="text",
        ),
        statements=[
            Statement(question="What does the rash look like?", answer="It's red and bumpy", source="patient", concept="skin_pain"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    all_q_text = " ".join(q.question for q in report.next_questions)
    # Text modality should have photo or type prompt
    assert "photo" in all_q_text.lower() or "type" in all_q_text.lower()


def test_modality_video_adapts_question():
    """Video modality adds visual prompts like 'show me' or 'hold up'."""
    case = CaseInput(
        case_id="modality-video",
        patient_context=PatientContext(
            age=45, chief_concern="rash on arm",
            domain="rash", modality="video",
        ),
        statements=[
            Statement(question="Can you describe the rash?", answer="It's all over my arm", source="patient", concept="skin_pain"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    all_q_text = " ".join(q.question for q in report.next_questions)
    # Video modality should have camera/show prompt
    assert "camera" in all_q_text.lower() or "show" in all_q_text.lower() or "watch" in all_q_text.lower()


def test_modality_unknown_no_adaptation():
    """Unknown modality leaves questions unchanged (no crash)."""
    case = CaseInput(
        case_id="modality-unknown",
        patient_context=PatientContext(
            age=40, chief_concern="chest pain",
            domain="chest_discomfort", modality="unknown_modality",
        ),
        statements=[
            Statement(question="Describe the pain", answer="pressure in chest", source="patient", concept="symptom_quality"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    # Should still generate questions without crashing
    assert len(report.next_questions) > 0


# ---------------------------------------------------------------------------
# Explicit Gestalt Pattern Tests (5 tests)
#
# These tests validate that specific gestalt patterns fire with the correct
# rule_id. Prior tests checked gestalt behavior generically; these assert
# exact pattern IDs for the 5 previously untested gestalt patterns:
#   GESTALT_DKA, GESTALT_MENINGITIS, GESTALT_SEPSIS_UTI,
#   GESTALT_SJS, GESTALT_RESP_FAILURE
# ---------------------------------------------------------------------------

def test_gestalt_dka_fires():
    """Custom DKA case triggers GESTALT_DKA pattern.

    Note: The existing DM-001 case uses 'threw up' and 'cannot keep' which do
    not match the gestalt regex (expects 'vomit|throw up|can't keep|nausea').
    This test constructs a case with phrasing that matches the actual regexes.
    """
    case = CaseInput(
        case_id="test-gestalt-dka",
        patient_context=PatientContext(
            age=42, chief_concern="nausea and thirst",
            domain="diabetes_hyperglycemia", modality="text",
        ),
        statements=[
            Statement(question="What is your blood sugar?", answer="My meter says 450, it is very high.", concept="glucose_number"),
            Statement(question="Any vomiting?", answer="I have been vomiting all day and nausea is terrible.", concept="vomiting"),
            Statement(question="Mental status?", answer="I am confused and very sleepy, not right at all.", concept="mental_status"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    gestalt = [f for f in report.findings if f.rule_id == "GESTALT_DKA"]
    assert len(gestalt) >= 1, (
        f"Should fire GESTALT_DKA. Got: {[f.rule_id for f in report.findings if 'GESTALT' in f.rule_id]}"
    )
    assert gestalt[0].severity == 1.0


def test_gestalt_meningitis_fires():
    """HA-001 case triggers GESTALT_MENINGITIS pattern.

    Required signals: headache_onset matches 'worst|sudden|severe|thunder|switch|instant',
    neck_stiffness matches 'stiff|can't touch|hurts to bend|pain.*neck'.
    HA-001 has both: thunderclap onset + stiff neck.
    """
    case = by_id("HA-001-thunderclap-minimized")
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    gestalt = [f for f in report.findings if f.rule_id == "GESTALT_MENINGITIS"]
    assert len(gestalt) >= 1, (
        f"HA-001 should fire GESTALT_MENINGITIS. Got: {[f.rule_id for f in report.findings if 'GESTALT' in f.rule_id]}"
    )
    assert gestalt[0].severity == 1.0


def test_gestalt_sepsis_uti_fires():
    """BS-014 case triggers GESTALT_SEPSIS_UTI pattern.

    Required signals: fever_measured matches 'fever|10[1-9]|hot|chills',
    flank_pain matches 'back|side|flank|kidney'.
    BS-014 has both: 'feel hot and sweaty' + 'my side hurts, right under my ribs'.
    """
    case = by_id("BS-014-diabetic-uti-masking-sepsis")
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    gestalt = [f for f in report.findings if f.rule_id == "GESTALT_SEPSIS_UTI"]
    assert len(gestalt) >= 1, (
        f"BS-014 should fire GESTALT_SEPSIS_UTI. Got: {[f.rule_id for f in report.findings if 'GESTALT' in f.rule_id]}"
    )
    assert gestalt[0].severity == 1.0


def test_gestalt_sjs_fires():
    """RASH-001 case triggers GESTALT_SJS pattern.

    Required signals: mucosal_involvement matches 'mouth|eye|genital|lip|blister',
    skin_pain matches 'hurt|burn|peel|blister|painful'.
    Supporting (min 1): new_medication matches 'new|started|antibiotic|seizure'.
    RASH-001 has all three: mouth sores + burning skin + seizure medicine.
    """
    case = by_id("RASH-001-new-med-mouth-sores")
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    gestalt = [f for f in report.findings if f.rule_id == "GESTALT_SJS"]
    assert len(gestalt) >= 1, (
        f"RASH-001 should fire GESTALT_SJS. Got: {[f.rule_id for f in report.findings if 'GESTALT' in f.rule_id]}"
    )
    assert gestalt[0].severity == 1.0


def test_gestalt_resp_failure_fires():
    """DY-001 case triggers GESTALT_RESP_FAILURE pattern.

    Required signals: oxygen_saturation matches 'low|[78]\\d|<90|dropping|88|89|85',
    sentence_test matches 'can't|no|stop|pause|few words'.
    DY-001 has both: '88 or 89' + 'I pause after a few words'.
    """
    case = by_id("DY-001-denies-sob-low-ox")
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    gestalt = [f for f in report.findings if f.rule_id == "GESTALT_RESP_FAILURE"]
    assert len(gestalt) >= 1, (
        f"DY-001 should fire GESTALT_RESP_FAILURE. Got: {[f.rule_id for f in report.findings if 'GESTALT' in f.rule_id]}"
    )
    assert gestalt[0].severity == 1.0


# ---------------------------------------------------------------------------
# Untested Contradiction Rule Tests (4 tests)
#
# These cover the 4 contradiction rules that had no dedicated test asserting
# their specific rule_id:
#   CONTRA_CHEST_NO_PAIN_PRESSURE, CONTRA_DYSPNEA_DENIAL_FUNCTIONAL_LIMIT,
#   CONTRA_HEADACHE_MILD_BUT_SUDDEN, CONTRA_MED_ADHERENCE_BOTTLE_EMPTY
# ---------------------------------------------------------------------------

def test_contradiction_chest_no_pain_pressure():
    """Patient denies pain but describes pressure triggers CONTRA_CHEST_NO_PAIN_PRESSURE.

    Rule: concept_a=symptom_quality (negative_a=True, needs negative words),
          concept_b=symptom_quality (pattern_b=pressure|tight|heavy|burn|squeez).
    Both concepts are the same, so the single observation must contain both
    a negative word AND match the pressure/tightness pattern.
    """
    case = CaseInput(
        case_id="test-chest-no-pain-pressure",
        patient_context=PatientContext(age=55, chief_concern="chest discomfort", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(question="Any chest pain?", answer="No pain at all, but there is this heavy pressure in my chest.", concept="symptom_quality"),
            Statement(question="When does it happen?", answer="When I walk upstairs.", concept="exertional_component"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    contra = [f for f in report.findings if f.rule_id == "CONTRA_CHEST_NO_PAIN_PRESSURE"]
    assert len(contra) >= 1, (
        f"Should detect pain denial with pressure. Got: {[f.rule_id for f in report.findings if 'CONTRA' in f.rule_id]}"
    )
    assert contra[0].category == "contradictory"
    assert contra[0].severity == 0.85


def test_contradiction_dyspnea_denial_functional_limit():
    """Patient denies SOB but describes functional limitation triggers CONTRA_DYSPNEA_DENIAL_FUNCTIONAL_LIMIT.

    Rule: concept_a=dyspnea (negative_a=True, needs negative words),
          concept_b=exertional_tolerance (pattern_b=can't|cannot|stop|worse|bedroom|kitchen|stairs).
    """
    case = CaseInput(
        case_id="test-dyspnea-denial-functional",
        patient_context=PatientContext(age=65, chief_concern="breathing", domain="dyspnea_respiratory", modality="text"),
        statements=[
            Statement(question="Are you short of breath?", answer="No, not short of breath at all.", concept="dyspnea"),
            Statement(question="Can you walk?", answer="I cannot walk to the mailbox anymore, I have to stop every few steps.", concept="exertional_tolerance"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    contra = [f for f in report.findings if f.rule_id == "CONTRA_DYSPNEA_DENIAL_FUNCTIONAL_LIMIT"]
    assert len(contra) >= 1, (
        f"Should detect SOB denial with functional limit. Got: {[f.rule_id for f in report.findings if 'CONTRA' in f.rule_id]}"
    )
    assert contra[0].category == "contradictory"
    assert contra[0].severity == 0.85


def test_contradiction_headache_mild_but_sudden():
    """Patient says mild headache but sudden onset triggers CONTRA_HEADACHE_MILD_BUT_SUDDEN.

    Rule: concept_a=headache_onset (negative_a=False, so NO negative words needed),
          concept_b=headache_onset (pattern_b=sudden|worst|thunderclap|instant|seconds).
    Both concepts are the same observation: a single answer must lack negative words
    AND match the thunderclap pattern. The 'mild' minimization is captured by
    SEVERITY_DIMINISHERS, while this rule flags the sudden onset in the same breath.
    """
    case = CaseInput(
        case_id="test-headache-mild-sudden",
        patient_context=PatientContext(age=45, chief_concern="headache", domain="headache_migraine", modality="text"),
        statements=[
            Statement(
                question="How severe and when did it start?",
                answer="It is mild, just a little headache, it came on suddenly like a thunderclap, worst headache of my life.",
                concept="headache_onset",
            ),
            Statement(question="Neck?", answer="A bit sore.", concept="neck_stiffness"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    contra = [f for f in report.findings if f.rule_id == "CONTRA_HEADACHE_MILD_BUT_SUDDEN"]
    assert len(contra) >= 1, (
        f"Should detect mild + sudden contradiction. Got: {[f.rule_id for f in report.findings if 'CONTRA' in f.rule_id]}"
    )
    assert contra[0].category == "contradictory"
    assert contra[0].severity == 0.85


def test_contradiction_med_adherence_bottle_empty():
    """Patient claims adherence but lost bottle triggers CONTRA_MED_ADHERENCE_BOTTLE_EMPTY.

    Rule: concept_a=last_taken (negative_a=False, NO negative words in adherence claim),
          concept_b=medication_identity (pattern_b=empty|lost|don't know|not sure).
    """
    case = CaseInput(
        case_id="test-med-adherence-empty",
        patient_context=PatientContext(age=60, chief_concern="refill", domain="med_refill_hypertension", modality="text"),
        statements=[
            Statement(question="Taking your medication?", answer="Yes, I take it every day.", concept="last_taken"),
            Statement(question="What medication?", answer="I lost my bottle and I am not sure what it is called.", concept="medication_identity"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    contra = [f for f in report.findings if f.rule_id == "CONTRA_MED_ADHERENCE_BOTTLE_EMPTY"]
    assert len(contra) >= 1, (
        f"Should detect adherence claim with lost bottle. Got: {[f.rule_id for f in report.findings if 'CONTRA' in f.rule_id]}"
    )
    assert contra[0].category == "contradictory"
    assert contra[0].severity == 0.85


# ---------------------------------------------------------------------------
# Gap 1: in_person modality adaptation
# ---------------------------------------------------------------------------

def test_modality_in_person_adapts_question():
    """In-person modality adds direct observation prompts like 'let me see' or 'let me take a look'."""
    case = CaseInput(
        case_id="modality-in-person",
        patient_context=PatientContext(
            age=55, chief_concern="high blood sugar",
            domain="diabetes_hyperglycemia", modality="in_person",
        ),
        statements=[
            Statement(question="What is your blood glucose?", answer="I think it's fine", source="patient", concept="glucose_number"),
        ],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    # At least one question should contain in_person-specific prompt
    all_q_text = " ".join(q.question for q in report.next_questions)
    assert "let me see" in all_q_text.lower() or "let me take a look" in all_q_text.lower() or "observe" in all_q_text.lower()


# ---------------------------------------------------------------------------
# Gap 2: Zero statements edge case
# ---------------------------------------------------------------------------

def test_zero_statements_handled_gracefully():
    """Empty statements list doesn't crash and produces safe state."""
    case = CaseInput(
        case_id="test-zero-statements",
        patient_context=PatientContext(age=50, chief_concern="test", domain="chest_discomfort", modality="text"),
        statements=[],
    )
    jre = JudgmentReadinessEngine()
    report = jre.evaluate(case)
    # Should not crash, and should NOT be READY (no information = not safe to proceed)
    assert report.state != "READY", f"Zero statements should not be READY, got {report.state}"
    assert report.scores.readiness_index < 50, f"Zero statements should have low RI"


# ---------------------------------------------------------------------------
# Gap 3: LLM detector exception handling
# ---------------------------------------------------------------------------

def test_llm_detector_exception_doesnt_crash():
    """LLM detector that raises exception doesn't crash evaluate()."""
    class CrashingDetector:
        available = True
        def analyze_case(self, case):
            raise RuntimeError("Network timeout")

    case = CaseInput(
        case_id="test-llm-crash",
        patient_context=PatientContext(age=50, chief_concern="chest pain", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(question="Pain?", answer="Heavy pressure in my chest", concept="symptom_quality"),
        ],
    )
    jre = JudgmentReadinessEngine(llm_detector=CrashingDetector())
    report = jre.evaluate(case)  # Should not raise
    assert report.state is not None  # Pipeline completed
    assert len(report.findings) >= 1  # Regex findings still work


# ---------------------------------------------------------------------------
# Gap 4: ExperienceMemory behavioral change
# ---------------------------------------------------------------------------

def test_experience_memory_changes_evaluation():
    """Running evaluate() twice on same JRE instance produces different confidence after events."""
    mem = ExperienceMemory.seeded()
    jre = JudgmentReadinessEngine(memory=mem)

    case = CaseInput(
        case_id="test-memory-behavioral",
        patient_context=PatientContext(age=55, chief_concern="chest", domain="chest_discomfort", modality="text"),
        statements=[
            Statement(question="Describe?", answer="Not pain, but there's pressure.", concept="symptom_quality"),
        ],
    )

    # First evaluation
    r1 = jre.evaluate(case)

    # Record high-information-gain events to shift priors significantly
    for _ in range(10):
        mem.record_event(ExperienceEvent(
            domain="chest_discomfort", concept="symptom_quality", trap="pain_word_boundary",
            phrase="not pain", initial_answer="not pain, pressure",
            clarified_truth="actually severe pressure", question_used="test",
            information_gain=0.95, outcome_label="test",
        ))

    # Second evaluation - same case, same JRE instance
    r2 = jre.evaluate(case)

    # The distortion prior for pain_word_boundary should have increased,
    # which means the confidence penalty is different
    # Check that SOMETHING changed (scores, findings, or questions)
    scores_differ = (r1.scores.readiness_index != r2.scores.readiness_index or
                     r1.scores.reliability != r2.scores.reliability or
                     r1.scores.distortion_load != r2.scores.distortion_load)
    assert scores_differ, (
        f"Scores should change after experience events. "
        f"Before: RI={r1.scores.readiness_index:.2f}, rel={r1.scores.reliability:.2f}, dist={r1.scores.distortion_load:.2f}. "
        f"After: RI={r2.scores.readiness_index:.2f}, rel={r2.scores.reliability:.2f}, dist={r2.scores.distortion_load:.2f}"
    )



# ---------------------------------------------------------------------------
# Utility Function Unit Tests (Gap 9)
# ---------------------------------------------------------------------------

def test_clamp_within_bounds():
    """clamp returns value when within bounds."""
    from jre.engine import clamp
    assert clamp(0.5, 0.0, 1.0) == 0.5


def test_clamp_below_floor():
    """clamp returns floor when below."""
    from jre.engine import clamp
    assert clamp(-0.5, 0.0, 1.0) == 0.0


def test_clamp_above_ceiling():
    """clamp returns ceiling when above."""
    from jre.engine import clamp
    assert clamp(1.5, 0.0, 1.0) == 1.0


def test_source_base_confidence_device():
    """Device source has highest base confidence after synthetic_truth."""
    from jre.engine import source_base_confidence
    assert source_base_confidence("device") > source_base_confidence("patient")


def test_source_base_confidence_unknown():
    """Unknown source type returns a reasonable default."""
    from jre.engine import source_base_confidence
    result = source_base_confidence("unknown_source")
    assert 0.0 < result <= 1.0


def test_normalize_answer_strips_and_lowers():
    """normalize_answer lowercases and strips when no numbers or keywords present."""
    from jre.engine import normalize_answer
    # "HELLO WORLD" has no numbers, no negative words, no affirmative words
    # so normalize_answer returns the lowercased stripped string
    assert normalize_answer("  HELLO WORLD  ") == "hello world"


def test_normalize_answer_empty():
    """normalize_answer handles empty string."""
    from jre.engine import normalize_answer
    result = normalize_answer("")
    assert isinstance(result, str)
