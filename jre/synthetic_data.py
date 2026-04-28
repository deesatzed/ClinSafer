"""Synthetic cases for the Judgment Readiness Engine demo.

Synthetic data design goals:
- Realistic enough for an interview demo.
- Explicitly includes health-literacy distortion, ambiguous language, and hidden
  ground truth so the module can demonstrate what it does *not* know.
- No real patient information.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .models import CaseInput, PatientContext, Statement


BASE_CASES: List[CaseInput] = [
    CaseInput(
        case_id="CP-001-heartburn-pressure",
        patient_context=PatientContext(age=58, chief_concern="heartburn", domain="chest_discomfort", literacy_hint="medium", modality="text", known_conditions=["diabetes", "hypertension"]),
        statements=[
            Statement("Do you have chest pain?", "No, it is not pain. It is just pressure and burning after walking upstairs.", "symptom_quality"),
            Statement("Does it change with activity?", "It gets better when I sit down for a few minutes.", "exertional_component"),
            Statement("Are you short of breath?", "Not really, but I stop halfway up stairs.", "dyspnea"),
            Statement("Any sweating or nausea?", "I was a little clammy this morning.", "diaphoresis"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "pain-word boundary; exertional pressure"},
    ),
    CaseInput(
        case_id="DY-001-denies-sob-low-ox",
        patient_context=PatientContext(age=72, chief_concern="cough", domain="dyspnea_respiratory", literacy_hint="low", has_caregiver=True, modality="phone", known_conditions=["COPD"]),
        statements=[
            Statement("Are you short of breath?", "No, I am fine sitting down.", "dyspnea"),
            Statement("Can you walk from bedroom to kitchen?", "I have to stop at the doorway now, worse than usual.", "exertional_tolerance"),
            Statement("Can you speak a full sentence?", "My daughter says I pause after a few words.", "sentence_test", source="caregiver"),
            Statement("What is your oxygen level?", "It says 88 or 89 after a minute.", "oxygen_saturation", source="device"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "patient answer 'no SOB' unreliable without functional probe"},
    ),
    CaseInput(
        case_id="RF-001-bp-normal-no-number",
        patient_context=PatientContext(age=49, chief_concern="blood pressure medication refill", domain="med_refill_hypertension", literacy_hint="medium", modality="text", known_conditions=["hypertension"]),
        statements=[
            Statement("Which medication do you need refilled?", "The small white pressure pill, I think lis-something.", "medication_identity"),
            Statement("When was your last dose?", "I take it every day.", "last_taken"),
            Statement("What is your home blood pressure?", "It is normal.", "home_bp_number"),
            Statement("Any side effects?", "Sometimes dizzy when I stand but probably okay.", "side_effects"),
        ],
        ground_truth={
            "requires_escalation": False,
            "expected_state": "CLARIFY",
            "rationale": "BP 'normal' without a number triggers normal_without_number trap. Insufficient objective data for safe refill automation. System correctly holds for verification.",
            "hidden_issue": "insufficient refill safety; needs bottle, BP number, renal function",
        },
    ),
    CaseInput(
        case_id="UTI-001-simple-words-hide-flank",
        patient_context=PatientContext(age=34, chief_concern="burning urination", domain="uti_symptoms", literacy_hint="low", modality="text"),
        statements=[
            Statement("Do you have burning when urinating?", "Yes, it burns when pee comes out.", "dysuria"),
            Statement("Any fever?", "I feel hot but I did not check.", "fever_measured"),
            Statement("Any back or side pain?", "My kidney side hurts under the ribs but maybe from sleeping wrong.", "flank_pain"),
            Statement("Any vomiting?", "No vomiting.", "vomiting"),
            Statement("Any chance of pregnancy?", "No.", "pregnancy_status"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "flank pain and unmeasured fever make uncomplicated pathway unsafe"},
    ),
    CaseInput(
        case_id="RASH-001-new-med-mouth-sores",
        patient_context=PatientContext(age=27, chief_concern="rash", domain="rash", literacy_hint="medium", modality="video"),
        statements=[
            Statement("Any rash in the mouth, eyes, or genitals?", "My lips are cracked and mouth has sore spots.", "mucosal_involvement"),
            Statement("Does the skin hurt or blister?", "It burns more than it itches.", "skin_pain"),
            Statement("Any new medicines?", "I started a seizure medicine maybe five weeks ago.", "new_medication"),
            Statement("Any breathing or throat symptoms?", "No breathing issue.", "airway_symptoms"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "mucosal involvement + new med + skin pain"},
    ),
    CaseInput(
        case_id="DM-001-sugar-fine-hidden-400",
        patient_context=PatientContext(age=42, chief_concern="nausea and thirst", domain="diabetes_hyperglycemia", literacy_hint="low", modality="text", known_conditions=["type 1 diabetes"]),
        statements=[
            Statement("What is your blood sugar?", "My sugar is fine, the meter just said high earlier.", "glucose_number"),
            Statement("Any vomiting?", "I threw up twice and cannot keep much down.", "vomiting"),
            Statement("Do you have ketones?", "I don't know what that means.", "ketones"),
            Statement("Do you have insulin?", "I ran out yesterday but my refill is coming.", "insulin_access"),
            Statement("Any confusion or unusual breathing?", "My partner says I am breathing deep but I feel okay.", "mental_status", source="caregiver"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "DKA risk hidden by vague phrase 'sugar is fine'"},
    ),
    CaseInput(
        case_id="CP-002-low-risk-but-incomplete",
        patient_context=PatientContext(age=24, chief_concern="brief chest soreness", domain="chest_discomfort", literacy_hint="high", modality="text"),
        statements=[
            Statement("Describe the symptom.", "Sharp soreness only when I twist my torso, started after lifting boxes.", "symptom_quality"),
            Statement("Does it happen with walking or stairs?", "No, walking and stairs do not change it.", "exertional_component"),
            Statement("Any shortness of breath?", "No, I can run and speak normally.", "dyspnea"),
            Statement("Any sweating, nausea, or fainting?", "No.", "diaphoresis"),
            Statement("Does it spread to jaw/arm/back?", "No.", "radiation"),
        ],
        ground_truth={"requires_escalation": False, "hidden_issue": "still remote ECG/vitals boundary"},
    ),
    CaseInput(
        case_id="RF-002-good-refill-readyish",
        patient_context=PatientContext(age=62, chief_concern="lisinopril refill", domain="med_refill_hypertension", literacy_hint="high", modality="text", known_conditions=["hypertension"]),
        statements=[
            Statement("Which medication do you need refilled?", "Lisinopril 20 mg once daily; I am reading the bottle.", "medication_identity", source="patient"),
            Statement("When was your last dose?", "This morning at 7 AM.", "last_taken"),
            Statement("What is your home blood pressure?", "128 over 76 today, and usually 120s over 70s.", "home_bp_number", source="device"),
            Statement("Any side effects?", "No dizziness, swelling, cough, fainting, chest pain, or shortness of breath.", "side_effects"),
            Statement("Kidney bloodwork?", "Chart shows creatinine 0.9 and potassium 4.3 last month.", "renal_function", source="chart"),
            Statement("Any chance of pregnancy?", "No.", "pregnancy_status"),
            Statement("Can we verify against chart/pharmacy?", "Chart medication list matches lisinopril 20 mg daily.", "chart_med_reconciliation", source="chart"),
        ],
        ground_truth={"requires_escalation": False, "hidden_issue": "high readiness example"},
    ),
    CaseInput(
        case_id="HA-001-thunderclap-minimized",
        patient_context=PatientContext(age=45, chief_concern="bad headache", domain="headache_migraine", literacy_hint="medium", modality="phone"),
        statements=[
            Statement("When did this headache start?", "It came on suddenly, like a switch flipped, worst headache of my life, but it is just mild now.", "headache_onset"),
            Statement("Any neck stiffness?", "My neck is stiff and bending makes it worse.", "neck_stiffness"),
            Statement("Any vision changes or weakness?", "No vision changes, no weakness.", "neuro_deficit"),
            Statement("Have you measured your temperature?", "No, I did not check.", "fever_measured"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "thunderclap onset + neck stiffness; subarachnoid hemorrhage until proven otherwise"},
    ),
    # --- INTELLIGENCE SHOWCASE CASE ---
    CaseInput(
        case_id="BS-014-diabetic-uti-masking-sepsis",
        patient_context=PatientContext(
            age=68,
            chief_concern="UTI symptoms, needs antibiotic refill",
            domain="uti_symptoms",
            literacy_hint="low",
            language_barrier=False,
            has_caregiver=True,
            modality="phone",
            known_conditions=["diabetes", "chronic_kidney_disease"],
        ),
        statements=[
            Statement(
                question="Do you have a fever?",
                answer="No fever, I have not checked but I feel hot and sweaty, worst I have ever felt.",
                concept="fever_measured",
                source="patient",
            ),
            Statement(
                question="What is your blood glucose reading?",
                answer="My sugar is fine, I checked it recently.",
                concept="glucose_number",
                source="patient",
            ),
            Statement(
                question="Device glucose reading?",
                answer="380 mg/dL",
                concept="glucose_number",
                source="device",
            ),
            Statement(
                question="Any confusion or mental status changes?",
                answer="A little confused but I am fine, just tired.",
                concept="mental_status",
                source="patient",
            ),
            Statement(
                question="Caregiver observation of mental status?",
                answer="She is not right today, confused and not making sense, she cannot remember what day it is.",
                concept="mental_status",
                source="caregiver",
            ),
            Statement(
                question="When did symptoms get worse?",
                answer="Got worse suddenly this morning, came on fast.",
                concept="onset_timing",
                source="patient",
            ),
            Statement(
                question="Burning with urination?",
                answer="Yes, painful urination and it smells bad.",
                concept="dysuria",
                source="patient",
            ),
            Statement(
                question="Any flank or kidney pain?",
                answer="My side hurts, right under my ribs on the back.",
                concept="flank_pain",
                source="patient",
            ),
        ],
        ground_truth={
            "requires_escalation": True,
            "hidden_issue": "Emerging sepsis in diabetic UTI patient: fever contradiction, critically elevated glucose (device 380 vs patient fine), mental status conflict (patient vs caregiver), flank pain suggesting pyelonephritis, acute onset with severity amplifiers. Cross-domain sepsis gestalt fires.",
        },
    ),
    # --- Interview showcase cases: subtle autonomy-boundary failures ---
    CaseInput(
        case_id="showcase-001-stale-ace-refill-ckd-nsaid",
        patient_context=PatientContext(
            age=66,
            chief_concern="lisinopril refill",
            domain="med_refill_hypertension",
            literacy_hint="medium",
            modality="text",
            known_conditions=["hypertension", "chronic kidney disease"],
        ),
        statements=[
            Statement(
                "What blood pressure numbers have you been getting recently?",
                "It was normal at my last visit a few months ago. I do not have the numbers.",
                "home_bp_number",
            ),
            Statement(
                "Any dizziness, fainting, chest pain, shortness of breath, swelling, or new symptoms?",
                "No, nothing serious. I just get a little dizzy when I stand up fast, but that is probably normal.",
                "side_effects",
            ),
            Statement(
                "Any new medicines or over-the-counter medicines?",
                "I have been taking ibuprofen most days for my back.",
                "medication_identity",
            ),
            Statement(
                "Any kidney problems or recent labs?",
                "I have chronic kidney disease, but my labs were okay last time. I am not sure when.",
                "renal_function",
            ),
            Statement(
                "Any chance of pregnancy?",
                "No.",
                "pregnancy_status",
            ),
        ],
        ground_truth={
            "requires_escalation": False,
            "expected_state": "HOLD_AND_VERIFY",
            "hidden_issue": "Routine-looking ACE-inhibitor refill has stale BP evidence, CKD, daily NSAID use, and unresolved dizziness; autonomous refill should be capped.",
        },
    ),
    CaseInput(
        case_id="showcase-002-refill-rote-denial-dizziness",
        patient_context=PatientContext(
            age=54,
            chief_concern="blood pressure refill before travel",
            domain="med_refill_hypertension",
            literacy_hint="medium",
            modality="text",
            known_conditions=["hypertension"],
        ),
        statements=[
            Statement("Which medication needs refill?", "Lisinopril. I just need it approved fast before I leave town.", "medication_identity"),
            Statement("Any missed doses?", "No. No. No missed doses, no side effects, no problems, all no.", "last_taken"),
            Statement("What is your home blood pressure?", "It is fine, I do not have the numbers with me.", "home_bp_number"),
            Statement("Any dizziness, fainting, chest pain, shortness of breath, swelling, or new symptoms?", "No symptoms. Well, sometimes I see spots and get dizzy when I stand, but everyone does that.", "side_effects"),
        ],
        ground_truth={
            "requires_escalation": False,
            "expected_state": "HOLD_AND_VERIFY",
            "hidden_issue": "Pathway-completion behavior and rote denial make negative answers unreliable; dizziness/visual symptoms need clarification before refill automation.",
        },
    ),
    CaseInput(
        case_id="showcase-003-cost-fear-minimizes-alarm",
        patient_context=PatientContext(
            age=59,
            chief_concern="indigestion and fatigue",
            domain="chest_discomfort",
            literacy_hint="medium",
            modality="text",
            known_conditions=["diabetes", "hypertension"],
        ),
        statements=[
            Statement("Do you have chest pain?", "No chest pain. It is just tight indigestion when I walk, but I cannot afford the ER.", "symptom_quality"),
            Statement("Does it change with activity?", "It starts when I carry laundry upstairs and gets better if I sit.", "exertional_component"),
            Statement("Any shortness of breath?", "Not really. I just slow down so it does not get bad.", "dyspnea"),
            Statement("What are you hoping we can do?", "Please just tell me it can wait until tomorrow. I have to work tonight.", "care_context"),
        ],
        ground_truth={
            "requires_escalation": True,
            "hidden_issue": "Economic pressure and reassurance-seeking should not downgrade exertional cardiac symptoms.",
        },
    ),
    CaseInput(
        case_id="showcase-004-bruising-partner-nearby",
        patient_context=PatientContext(
            age=32,
            chief_concern="bruises and rash",
            domain="rash",
            literacy_hint="medium",
            modality="text",
        ),
        statements=[
            Statement("Can you answer privately?", "My partner is listening, so I cannot say much. Please do not mention this message.", "social_context"),
            Statement("How did the bruises happen?", "I do not want to say. They just show up after arguments.", "skin_pain"),
            Statement("Any mouth, eye, or genital sores?", "No sores.", "mucosal_involvement"),
            Statement("Any breathing or throat symptoms?", "No.", "airway_symptoms"),
        ],
        ground_truth={
            "requires_escalation": False,
            "expected_state": "ROUTE_CLINICIAN",
            "hidden_issue": "Potential coercion or unsafe channel; routine rash workflow is not appropriate.",
        },
    ),
    CaseInput(
        case_id="showcase-005-caregiver-conflict-fine-but-confused",
        patient_context=PatientContext(
            age=71,
            chief_concern="possible UTI",
            domain="uti_symptoms",
            literacy_hint="medium",
            has_caregiver=True,
            modality="phone",
            known_conditions=["diabetes"],
        ),
        statements=[
            Statement("Do you have a fever?", "No fever, I am fine.", "fever_measured", source="patient"),
            Statement("Caregiver, how does she seem today?", "She is not herself today and keeps asking the same question.", "mental_status", source="caregiver"),
            Statement("Any burning with urination?", "A little burning, but I am fine.", "dysuria", source="patient"),
            Statement("Any back or side pain?", "Her side hurt this morning, but she says it is nothing.", "flank_pain", source="caregiver"),
        ],
        ground_truth={
            "requires_escalation": True,
            "hidden_issue": "Patient minimization conflicts with caregiver report of mental status change and flank pain in diabetic UTI context.",
        },
    ),
    CaseInput(
        case_id="showcase-006-nonresponse-after-risk-warning",
        patient_context=PatientContext(
            age=57,
            chief_concern="chest pressure follow-up",
            domain="chest_discomfort",
            literacy_hint="medium",
            modality="text",
            known_conditions=["diabetes"],
        ),
        statements=[
            Statement("Describe the symptom.", "Pressure when walking to the mailbox, then sweating. It stops when I rest.", "symptom_quality"),
            Statement("Are you still there?", "Patient stopped responding after risk warning. Chat disconnected. No answer by phone.", "vitals"),
        ],
        ground_truth={
            "requires_escalation": True,
            "hidden_issue": "Nonresponse after risk disclosure is an operational safety event, not a closed low-risk encounter.",
        },
    ),
    CaseInput(
        case_id="showcase-007-unasked-is-not-denied",
        patient_context=PatientContext(
            age=41,
            chief_concern="blood pressure medication refill",
            domain="med_refill_hypertension",
            literacy_hint="high",
            modality="text",
            known_conditions=["hypertension"],
        ),
        statements=[
            Statement("Which medication needs refill?", "Lisinopril 20 mg.", "medication_identity"),
            Statement("When was your last dose?", "This morning.", "last_taken"),
            Statement("What is your home blood pressure?", "126 over 78 today.", "home_bp_number", source="device"),
            Statement("Any side effects?", "No side effects.", "side_effects"),
        ],
        ground_truth={
            "requires_escalation": False,
            "expected_state": "HOLD_AND_VERIFY",
            "hidden_issue": "A complete-looking refill transcript omitted pregnancy status, recent renal labs, and chart/pharmacy reconciliation; unasked is not denied.",
        },
    ),
    CaseInput(
        case_id="showcase-008-prior-reassurance-expired",
        patient_context=PatientContext(
            age=47,
            chief_concern="headache again",
            domain="headache_migraine",
            literacy_hint="medium",
            modality="phone",
            known_conditions=["hypertension"],
        ),
        statements=[
            Statement("Tell me about the headache.", "My doctor said my headaches were okay last month, but this one is new and hit suddenly this morning.", "headache_onset"),
            Statement("Any neck stiffness?", "A little stiff, but maybe I slept wrong.", "neck_stiffness"),
            Statement("Any weakness, numbness, vision changes, speech trouble, or confusion?", "No weakness, but my vision went blurry for a few minutes.", "neuro_deficit"),
            Statement("Have you measured your temperature?", "No, I have not checked.", "fever_measured"),
        ],
        ground_truth={
            "requires_escalation": True,
            "hidden_issue": "Prior reassurance is stale when symptom character changes; new sudden headache and transient visual symptoms reset the safety boundary.",
        },
    ),
    CaseInput(
        case_id="showcase-009-embarrassment-curbs-history",
        patient_context=PatientContext(
            age=38,
            chief_concern="stomach issue",
            domain="gi_symptoms",
            literacy_hint="medium",
            modality="text",
        ),
        statements=[
            Statement("What is worrying you most?", "This is embarrassing and I do not want it in my chart, but I googled it and now I am scared it is cancer.", "care_context"),
            Statement("Any bathroom alarm details you are avoiding?", "I do not want to answer that here. It is probably nothing and I am embarrassed.", "diarrhea_blood"),
            Statement("Any weight loss, trouble swallowing, or persistent vomiting?", "I lost some weight because I am avoiding food. I do not want to talk about the bathroom details.", "alarm_gi"),
            Statement("Where is the pain?", "Low belly cramps off and on, not bad enough to make a fuss.", "abdominal_pain"),
        ],
        ground_truth={
            "requires_escalation": False,
            "expected_state": "HOLD_AND_VERIFY",
            "hidden_issue": "Embarrassment, fear of a diagnosis, and misconstrued internet medical facts are shaping the history; partial denials should not be treated as complete GI alarm review.",
        },
    ),
    CaseInput(
        case_id="showcase-010-defense-pattern-distortion",
        patient_context=PatientContext(
            age=52,
            chief_concern="stress and chest symptoms",
            domain="chest_discomfort",
            literacy_hint="medium",
            modality="text",
            known_conditions=["hypertension"],
        ),
        statements=[
            Statement("What do you think is happening?", "I am probably just overreacting. Google says heart attack, but I know it is anxiety.", "care_context"),
            Statement("Describe the symptom.", "Pressure in my upper chest when I walk fast, but I am not a complainer and I can tough it out.", "symptom_quality"),
            Statement("Any shortness of breath?", "No. I just slow down and wait because I do not want to look weak.", "dyspnea"),
            Statement("What are you hoping we can do?", "Please do not make a big deal. I have a lot going on and I will be fine.", "care_context"),
        ],
        ground_truth={
            "requires_escalation": True,
            "expected_state": "ESCALATE",
            "hidden_issue": "Defense mechanisms shape both directions of the history: anxiety-labeling and reassurance seeking on one side, stoic minimization and denial on the other. The system must extract concrete exertional pressure, function, timing, and objective data instead of accepting either coping frame.",
        },
    ),
    # --- Top telemedicine complaint coverage cases ---
    CaseInput(
        case_id="TOP-001-mental-health-self-harm",
        patient_context=PatientContext(age=31, chief_concern="anxiety and depression", domain="mental_health", modality="text"),
        statements=[
            Statement("Are you safe right now?", "I keep thinking about ending my life tonight and I am alone.", "self_harm"),
            Statement("Any thoughts of hurting someone else?", "No.", "harm_others"),
            Statement("Any substances today?", "I drank a lot and took extra sleeping pills.", "substance_intoxication"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "Self-harm plus intoxication requires crisis workflow."},
    ),
    CaseInput(
        case_id="TOP-002-adhd-stimulant-palpitations",
        patient_context=PatientContext(age=28, chief_concern="ADHD stimulant refill", domain="adhd_behavioral_med", modality="text"),
        statements=[
            Statement("Medication?", "Adderall XR 30 mg, I need an early refill because I ran out.", "medication_identity"),
            Statement("Any side effects?", "My heart races and I had chest tightness after taking extra doses.", "side_effects"),
            Statement("Current BP or pulse?", "I do not know, no numbers.", "bp_hr"),
        ],
        ground_truth={"requires_escalation": False, "expected_state": "HOLD_AND_VERIFY", "hidden_issue": "Controlled-med refill has early refill, dose escalation, cardiopulmonary symptoms, and missing vitals."},
    ),
    CaseInput(
        case_id="TOP-003-general-med-rash-swelling",
        patient_context=PatientContext(age=46, chief_concern="new medication reaction", domain="general_med_management", modality="text"),
        statements=[
            Statement("Which medication?", "I started the antibiotic yesterday, not sure the name.", "medication_identity"),
            Statement("Any side effects?", "I have a rash and my lips feel a little swollen.", "side_effects"),
            Statement("Any allergies?", "I had an allergic reaction years ago but do not remember to what.", "contraindications"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "Medication reaction with lip swelling needs airway/allergy boundary."},
    ),
    CaseInput(
        case_id="TOP-004-lab-review-critical-potassium",
        patient_context=PatientContext(age=69, chief_concern="lab result question", domain="followup_lab_review", modality="text", known_conditions=["chronic kidney disease"]),
        statements=[
            Statement("Which result?", "My potassium is marked critical at 6.4.", "result_value"),
            Statement("When was it drawn?", "Yesterday.", "result_date"),
            Statement("Any symptoms?", "I feel weak and a little lightheaded.", "current_symptoms"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "Critical potassium value and symptoms should not be treated as routine lab review."},
    ),
    CaseInput(
        case_id="TOP-005-sore-throat-airway",
        patient_context=PatientContext(age=44, chief_concern="sore throat", domain="uri_sinus_throat", modality="phone"),
        statements=[
            Statement("How long?", "Two days and worse today.", "symptom_duration"),
            Statement("Any swallowing trouble?", "I am drooling and cannot swallow saliva, my voice sounds muffled.", "throat_airway"),
            Statement("Temperature?", "102.8.", "fever_measured"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "Sore throat with drooling/muffled voice crosses deep neck/airway boundary."},
    ),
    CaseInput(
        case_id="TOP-006-asthma-rescue-not-helping",
        patient_context=PatientContext(age=37, chief_concern="wheezing", domain="asthma_allergy", modality="phone", known_conditions=["asthma"]),
        statements=[
            Statement("Breathing now?", "I am wheezing and it is hard to finish sentences.", "airway_symptoms"),
            Statement("Rescue inhaler?", "Using it every hour and it is not helping.", "rescue_inhaler_use"),
            Statement("Oxygen or peak flow?", "No device here.", "peak_flow_or_o2"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "Asthma symptoms with frequent rescue use and poor response require escalation."},
    ),
    CaseInput(
        case_id="TOP-007-sti-exposure-pep-window",
        patient_context=PatientContext(age=24, chief_concern="STI exposure", domain="vaginal_sti", modality="text"),
        statements=[
            Statement("Pregnancy?", "No, not pregnant.", "pregnancy_status"),
            Statement("Exposure timing?", "Unprotected sex last night with someone whose HIV status I do not know.", "sti_exposure_timing"),
            Statement("Was it wanted?", "Yes, consensual.", "assault_or_coercion"),
        ],
        ground_truth={"requires_escalation": False, "expected_state": "ROUTE_CLINICIAN", "hidden_issue": "Possible HIV exposure is within PEP timing window and needs time-sensitive clinician workflow."},
    ),
    CaseInput(
        case_id="TOP-008-eye-pain-contact-lens",
        patient_context=PatientContext(age=33, chief_concern="pink eye", domain="eye_ear", modality="video"),
        statements=[
            Statement("Vision?", "My vision is blurry in that eye.", "vision_change"),
            Statement("Pain or light sensitivity?", "It hurts a lot and light bothers me.", "eye_pain_photophobia"),
            Statement("Contacts?", "Yes, I slept in my contacts.", "contact_lens"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "Contact lens wearer with pain/photophobia/vision change is not routine conjunctivitis."},
    ),
    CaseInput(
        case_id="TOP-009-gi-blood-dehydration",
        patient_context=PatientContext(age=52, chief_concern="vomiting and diarrhea", domain="gi_symptoms", modality="text"),
        statements=[
            Statement("Pain?", "Bad constant belly pain.", "abdominal_pain"),
            Statement("Vomiting?", "I cannot keep fluids down since last night.", "vomiting"),
            Statement("Blood?", "The stool is black and tarry.", "diarrhea_blood"),
            Statement("Hydration?", "I feel faint when standing.", "dehydration"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "GI bleed/dehydration signals require urgent evaluation."},
    ),
    CaseInput(
        case_id="TOP-010-heartburn-exertional",
        patient_context=PatientContext(age=61, chief_concern="heartburn", domain="gerd_dyspepsia", modality="text", known_conditions=["diabetes"]),
        statements=[
            Statement("Chest or exertional symptoms?", "It is heartburn but it comes when I walk uphill and I get sweaty.", "chest_or_exertional"),
            Statement("GI alarm features?", "No black stool or trouble swallowing.", "alarm_gi"),
            Statement("Pain location?", "Burning pressure in the upper chest.", "abdominal_pain"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "Heartburn label hides exertional cardiac-pattern symptoms."},
    ),
    CaseInput(
        case_id="TOP-011-back-pain-bladder",
        patient_context=PatientContext(age=58, chief_concern="back pain", domain="musculoskeletal_pain", modality="text"),
        statements=[
            Statement("Any trauma?", "No injury.", "trauma_mechanism"),
            Statement("Any weakness or numbness?", "My legs feel weak and numb.", "neuro_deficit"),
            Statement("Bladder or bowel changes?", "I cannot urinate since this morning.", "bowel_bladder"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "Back pain with neuro deficit and urinary retention crosses cauda equina boundary."},
    ),
    CaseInput(
        case_id="TOP-012-routine-derm-mucosal",
        patient_context=PatientContext(age=35, chief_concern="acne/rash question", domain="routine_dermatology", modality="video"),
        statements=[
            Statement("Photo?", "I uploaded a photo.", "lesion_photo_quality"),
            Statement("Infection signs?", "No pus or fever.", "infection_signs"),
            Statement("Mouth or airway?", "I also have sores in my mouth and eyes.", "mucosal_or_airway"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "Routine dermatology request has mucosal involvement."},
    ),
    CaseInput(
        case_id="TOP-013-skin-infection-face-fever",
        patient_context=PatientContext(age=48, chief_concern="skin infection", domain="skin_infection", modality="video", known_conditions=["diabetes"]),
        statements=[
            Statement("Spread?", "Redness is spreading quickly and very painful.", "infection_spread"),
            Statement("Fever?", "102.4.", "fever_measured"),
            Statement("Location?", "It is near my eye.", "location_risk"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "Skin infection near eye with fever and diabetes should not be routine telemedicine antibiotic flow."},
    ),
    CaseInput(
        case_id="TOP-014-glp1-severe-abdominal-pain",
        patient_context=PatientContext(age=41, chief_concern="GLP-1 refill", domain="obesity_metabolic", modality="text"),
        statements=[
            Statement("Medication?", "Semaglutide, I increased the dose last week.", "medication_identity"),
            Statement("Contraindications?", "No pregnancy or thyroid cancer history.", "contraindications"),
            Statement("Side effects?", "Severe upper abdominal pain and vomiting for two days.", "side_effects"),
        ],
        ground_truth={"requires_escalation": True, "hidden_issue": "GLP-1 medication request with severe abdominal pain/vomiting needs pancreatitis/gallbladder boundary."},
    ),
]


DISTORTION_VARIANTS: Dict[str, List[Tuple[str, str, str]]] = {
    "dyspnea_respiratory": [
        ("dyspnea", "Are you short of breath?", "No, except when I move around."),
        ("exertional_tolerance", "Can you walk normally?", "I can, but I have to rest after a few steps."),
        ("oxygen_saturation", "What is your oxygen level?", "It is probably normal, I don't have the thing."),
        ("fever_measured", "Any fever?", "I felt warm."),
    ],
    "chest_discomfort": [
        ("symptom_quality", "Do you have chest pain?", "No pain, just a heavy tight feeling."),
        ("exertional_component", "Does activity affect it?", "Maybe with stairs, I did not pay attention."),
        ("dyspnea", "Any shortness of breath?", "Not really, I just get tired walking."),
    ],
    "med_refill_hypertension": [
        ("medication_identity", "What medicine?", "The blood pill, blue bottle, not sure the name."),
        ("home_bp_number", "What is the BP?", "Normal at the pharmacy last time."),
        ("last_taken", "Last dose?", "I take it every day, mostly."),
    ],
    "uti_symptoms": [
        ("fever_measured", "Any fever?", "I think so, I was sweaty."),
        ("flank_pain", "Any side pain?", "Just back pain by my kidney side."),
    ],
    "diabetes_hyperglycemia": [
        ("glucose_number", "What is your sugar?", "Fine, I do not remember the number."),
        ("ketones", "Ketones?", "No idea."),
    ],
    "headache_migraine": [
        ("headache_onset", "When did it start?", "It came on fast, worst ever, but mild now."),
        ("neck_stiffness", "Neck stiffness?", "A little sore maybe."),
        ("fever_measured", "Any fever?", "I felt warm."),
    ],
}


def generate_cases(n: int = 24, seed: int = 7) -> List[CaseInput]:
    """Generate a mix of hand-authored and mutated cases."""
    rng = random.Random(seed)
    cases: List[CaseInput] = list(BASE_CASES)
    domains = list(DISTORTION_VARIANTS)
    while len(cases) < n:
        base = rng.choice(BASE_CASES)
        domain = base.patient_context.domain
        ctx = PatientContext(
            age=max(18, min(90, base.patient_context.age + rng.randint(-8, 9))),
            chief_concern=base.patient_context.chief_concern,
            domain=domain,
            literacy_hint=rng.choice(["low", "medium", "unknown"]),
            language_barrier=rng.random() < 0.15,
            has_caregiver=rng.random() < 0.30,
            modality=rng.choice(["text", "phone", "video"]),
            known_conditions=list(base.patient_context.known_conditions),
        )
        statements = [Statement(s.question, s.answer, s.concept, s.source, dict(s.metadata)) for s in base.statements]
        for concept, question, answer in DISTORTION_VARIANTS.get(domain, []):
            if rng.random() < 0.45:
                # Replace matching concept or append if absent.
                replaced = False
                for i, s in enumerate(statements):
                    if s.concept == concept:
                        statements[i] = Statement(question, answer, concept)
                        replaced = True
                        break
                if not replaced:
                    statements.append(Statement(question, answer, concept))
        case_id = f"SYN-{len(cases)+1:03d}-{domain}"
        cases.append(
            CaseInput(
                case_id=case_id,
                patient_context=ctx,
                statements=statements,
                ground_truth={"synthetic": True, "base_case": base.case_id, **base.ground_truth},
            )
        )
    return cases


def case_to_dict(case: CaseInput) -> Dict:
    return {
        "case_id": case.case_id,
        "patient_context": case.patient_context.__dict__,
        "statements": [s.__dict__ for s in case.statements],
        "ground_truth": case.ground_truth,
    }


def write_dataset(out_dir: str | Path, n: int = 24, seed: int = 7) -> List[CaseInput]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cases = generate_cases(n=n, seed=seed)
    jsonl_path = out / "synthetic_jre_cases.jsonl"
    csv_path = out / "synthetic_jre_cases_flat.csv"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case_to_dict(case), ensure_ascii=False) + "\n")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "domain", "age", "chief_concern", "literacy_hint", "question", "answer", "concept", "source", "hidden_issue", "requires_escalation"])
        for case in cases:
            for s in case.statements:
                writer.writerow([
                    case.case_id,
                    case.patient_context.domain,
                    case.patient_context.age,
                    case.patient_context.chief_concern,
                    case.patient_context.literacy_hint,
                    s.question,
                    s.answer,
                    s.concept,
                    s.source,
                    case.ground_truth.get("hidden_issue", ""),
                    case.ground_truth.get("requires_escalation", ""),
                ])
    return cases


if __name__ == "__main__":
    write_dataset(Path(__file__).resolve().parents[1] / "data")
