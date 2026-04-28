"""Clinical domain templates and expert-system rules.

The point is not to be exhaustive. The point is to demonstrate a future-proof
pattern: deterministic safety slots + LLM-friendly language + learnable
question selection. A deployed version would be specialty-specific and reviewed
through clinical governance.
"""
from __future__ import annotations

from typing import Dict, List
from .models import SlotSpec


def q(*items: str) -> List[str]:
    return list(items)


DOMAIN_TEMPLATES: Dict[str, List[SlotSpec]] = {
    "chest_discomfort": [
        SlotSpec(
            "symptom_quality",
            "Symptom quality",
            0.95,
            critical=True,
            traps=["pain_word_boundary", "heartburn_label"],
            clarify_questions=q(
                "When you say it is not chest pain, is there pressure, tightness, heaviness, squeezing, burning, or discomfort anywhere in the chest, jaw, arm, back, or upper belly?",
                "Does it feel different from your usual indigestion or reflux?",
            ),
            why_it_matters="Patients may not label pressure, heaviness, or burning as 'pain'.",
        ),
        SlotSpec(
            "exertional_component",
            "Relationship to exertion",
            0.90,
            critical=True,
            clarify_questions=q(
                "Does the discomfort happen or get worse when walking, climbing stairs, or doing chores, and improve with rest?"
            ),
            why_it_matters="Exertional symptoms change the safety boundary of remote care.",
        ),
        SlotSpec(
            "dyspnea",
            "Shortness of breath",
            0.80,
            critical=True,
            traps=["sob_word_boundary"],
            clarify_questions=q(
                "Can you walk across the room and speak a full sentence without stopping to catch your breath?",
                "Compared with your usual, are you breathing harder with normal activities?",
            ),
            why_it_matters="Patients often deny 'shortness of breath' while reporting functional breathing limitation.",
        ),
        SlotSpec("diaphoresis", "Sweating", 0.55, clarify_questions=q("Any unusual sweating, nausea, or feeling faint with the discomfort?")),
        SlotSpec("radiation", "Radiation", 0.55, clarify_questions=q("Does the discomfort spread to your jaw, shoulder, arm, back, or upper abdomen?")),
        SlotSpec("vitals", "Current vitals", 0.70, slot_type="objective", objective_required=True, clarify_questions=q("Do you have a current blood pressure, heart rate, and oxygen level reading? What are the numbers?")),
        SlotSpec("ecg", "ECG", 0.80, slot_type="exam", remote_unknowable=True, critical=True, why_it_matters="ECG cannot be inferred from text chat."),
    ],
    "dyspnea_respiratory": [
        SlotSpec("oxygen_saturation", "Oxygen saturation", 0.95, slot_type="objective", critical=True, objective_required=True, clarify_questions=q("Do you have a pulse oximeter reading right now? What number does it show after sitting still for one minute?")),
        SlotSpec("respiratory_rate", "Respiratory rate", 0.85, slot_type="objective", critical=True, objective_required=True, clarify_questions=q("Please count breaths for 60 seconds, or have someone count them. What number do you get?")),
        SlotSpec("sentence_test", "Sentence test", 0.80, critical=True, clarify_questions=q("Can you say a full sentence out loud without needing to pause for breath?")),
        SlotSpec("exertional_tolerance", "Functional exertional tolerance", 0.85, critical=True, traps=["sob_word_boundary"], clarify_questions=q("Can you walk from bedroom to kitchen without stopping? Is that worse than your baseline?")),
        SlotSpec("mental_status", "Mental status", 0.65, critical=True, clarify_questions=q("Are you confused, unusually sleepy, or having trouble staying awake?")),
        SlotSpec("fever_measured", "Measured fever", 0.55, objective_required=True, clarify_questions=q("Have you measured your temperature with a thermometer? What was the number and when?")),
        SlotSpec("baseline_lung_disease", "Baseline lung disease", 0.45, slot_type="chart", clarify_questions=q("Do you have COPD, asthma, heart failure, or use oxygen at home?")),
        SlotSpec("lung_exam", "Lung exam", 0.75, slot_type="exam", remote_unknowable=True, why_it_matters="Work of breathing and auscultation are only partially inferable remotely."),
    ],
    "med_refill_hypertension": [
        SlotSpec("medication_identity", "Medication identity", 0.90, critical=True, traps=["med_name_confusion"], clarify_questions=q("Please read the exact name and dose from the medication bottle, including how often you take it.")),
        SlotSpec("last_taken", "Last dose taken", 0.75, critical=True, traps=["adherence_social_desirability"], clarify_questions=q("When was the last dose you actually swallowed? Today, yesterday, or longer ago?")),
        SlotSpec("home_bp_number", "Home blood pressure number", 0.95, slot_type="objective", critical=True, objective_required=True, traps=["normal_without_number"], clarify_questions=q("When you say your blood pressure is normal, what exact numbers did you get, and when were they measured?")),
        SlotSpec("side_effects", "Side effects", 0.65, clarify_questions=q("Any dizziness, fainting, swelling, cough, weakness, or new symptoms since taking it?")),
        SlotSpec("renal_function", "Recent kidney function", 0.75, slot_type="lab", objective_required=True, clarify_questions=q("Do you know if you had kidney bloodwork recently, such as creatinine or eGFR?")),
        SlotSpec("pregnancy_status", "Pregnancy status", 0.70, critical=True, clarify_questions=q("Is there any chance you are pregnant or trying to become pregnant?")),
        SlotSpec("chart_med_reconciliation", "Chart medication reconciliation", 0.70, slot_type="chart", objective_required=True, clarify_questions=q("Can this be verified against the medication list in your chart or pharmacy fill record?")),
    ],
    "uti_symptoms": [
        SlotSpec("dysuria", "Burning with urination", 0.70, clarify_questions=q("Do you feel burning or pain when urine comes out?")),
        SlotSpec("fever_measured", "Measured fever", 0.80, objective_required=True, critical=True, traps=["fever_guess"], clarify_questions=q("Have you measured a temperature with a thermometer? What was the highest number?")),
        SlotSpec("flank_pain", "Flank/back pain", 0.85, critical=True, traps=["back_pain_boundary"], clarify_questions=q("Any pain in the side of your back below the ribs, especially one-sided?")),
        SlotSpec("vomiting", "Vomiting / PO intolerance", 0.80, critical=True, clarify_questions=q("Are you vomiting or unable to keep fluids down?")),
        SlotSpec("pregnancy_status", "Pregnancy status", 0.80, critical=True, clarify_questions=q("Is there any chance you are pregnant?")),
        SlotSpec("sex_or_complicated_risk", "Complicated UTI risk", 0.70, critical=True, clarify_questions=q("Are you male, immunocompromised, diabetic, or do you have kidney disease, catheter, or recent urologic procedure?")),
        SlotSpec("urinalysis", "Urinalysis", 0.55, slot_type="lab", remote_unknowable=True, why_it_matters="Urine testing may be needed depending on risk and pathway."),
    ],
    "rash": [
        SlotSpec("mucosal_involvement", "Mouth/eye/genital involvement", 0.95, critical=True, clarify_questions=q("Any sores, pain, or rash in the mouth, eyes, lips, genitals, or inside the nose?")),
        SlotSpec("skin_pain", "Skin pain", 0.85, critical=True, clarify_questions=q("Does the skin hurt, burn, blister, peel, or feel painful to touch?")),
        SlotSpec("fever_measured", "Measured fever", 0.70, objective_required=True, clarify_questions=q("Have you measured a temperature? What was the number?")),
        SlotSpec("new_medication", "New medication exposure", 0.90, critical=True, clarify_questions=q("Have you started any new medication, antibiotic, seizure medicine, or supplement in the last 8 weeks?")),
        SlotSpec("airway_symptoms", "Airway symptoms", 0.95, critical=True, clarify_questions=q("Any lip/tongue swelling, wheezing, throat tightness, or trouble breathing?")),
        SlotSpec("rash_exam", "Visual rash exam", 0.80, slot_type="exam", remote_unknowable=True, clarify_questions=q("Can you upload clear photos in good light from close up and farther away?")),
    ],
    "diabetes_hyperglycemia": [
        SlotSpec("glucose_number", "Blood glucose number", 0.95, slot_type="objective", critical=True, objective_required=True, traps=["sugar_fine_without_number"], clarify_questions=q("What exact glucose number did you get, and was it fasting or after eating?")),
        SlotSpec("ketones", "Ketones", 0.85, slot_type="objective", critical=True, objective_required=True, clarify_questions=q("Have you checked urine or blood ketones? What was the result?")),
        SlotSpec("vomiting", "Vomiting", 0.85, critical=True, clarify_questions=q("Are you vomiting or unable to keep fluids down?")),
        SlotSpec("insulin_access", "Insulin/medication access", 0.75, critical=True, clarify_questions=q("Do you have your insulin or diabetes medication available, and when was your last dose?")),
        SlotSpec("mental_status", "Mental status", 0.75, critical=True, clarify_questions=q("Are you confused, very sleepy, weak, or breathing unusually deep or fast?")),
        SlotSpec("hydration_status", "Hydration", 0.55, clarify_questions=q("Are you urinating normally and able to drink fluids?")),
        SlotSpec("anion_gap", "DKA labs", 0.80, slot_type="lab", remote_unknowable=True, why_it_matters="DKA cannot be ruled out by conversation alone when red flags exist."),
    ],
    "headache_migraine": [
        SlotSpec(
            "headache_onset",
            "Headache onset and severity",
            0.95,
            critical=True,
            traps=["thunderclap_minimized"],
            clarify_questions=q(
                "Did this headache come on suddenly — like a switch being flipped — or did it build up gradually over hours?",
                "On a scale of 0 to 10, how severe is this headache at its worst?",
            ),
            why_it_matters="Thunderclap onset (peak within seconds) is a subarachnoid hemorrhage red flag.",
        ),
        SlotSpec(
            "neck_stiffness",
            "Neck stiffness",
            0.90,
            critical=True,
            clarify_questions=q(
                "Can you touch your chin to your chest without pain? Does bending your neck forward make the headache worse?",
            ),
            why_it_matters="Meningismus with headache suggests meningitis or subarachnoid hemorrhage.",
        ),
        SlotSpec(
            "fever_measured",
            "Measured fever",
            0.80,
            objective_required=True,
            critical=True,
            traps=["fever_guess"],
            clarify_questions=q("Have you measured your temperature with a thermometer? What was the number?"),
            why_it_matters="Fever + headache + neck stiffness is the meningitis triad.",
        ),
        SlotSpec(
            "neuro_deficit",
            "Neurological deficit",
            0.95,
            critical=True,
            clarify_questions=q(
                "Any vision changes, double vision, weakness on one side, numbness, speech difficulty, or confusion?",
            ),
            why_it_matters="Focal neuro deficits with headache suggest stroke, mass lesion, or complicated migraine requiring urgent evaluation.",
        ),
        SlotSpec(
            "aura_pattern",
            "Aura or prodrome",
            0.50,
            clarify_questions=q("Do you see flashing lights, zigzag lines, or have visual changes before or during the headache?"),
            why_it_matters="Aura helps classify migraine vs other causes but does not rule out dangerous causes.",
        ),
        SlotSpec(
            "medication_use",
            "Headache medication use",
            0.60,
            traps=["medication_overuse"],
            clarify_questions=q("How often do you take pain medication for headaches? More than 10-15 days per month?"),
            why_it_matters="Medication overuse headache is common and undertreated.",
        ),
        SlotSpec(
            "vitals",
            "Current vitals",
            0.70,
            slot_type="objective",
            objective_required=True,
            clarify_questions=q("Do you have a current blood pressure reading? What are the numbers?"),
        ),
        SlotSpec("neuro_exam", "Neurological exam", 0.85, slot_type="exam", remote_unknowable=True, critical=True, why_it_matters="Fundoscopy, cranial nerves, and motor exam cannot be done remotely."),
    ],
    "mental_health": [
        SlotSpec("self_harm", "Self-harm or suicide risk", 1.00, critical=True, clarify_questions=q("Are you having thoughts of hurting yourself, ending your life, or not being safe right now?")),
        SlotSpec("harm_others", "Risk of harm to others", 0.95, critical=True, clarify_questions=q("Are you worried you might hurt someone else or lose control?")),
        SlotSpec("psychosis_mania", "Psychosis or mania signal", 0.90, critical=True, clarify_questions=q("Are you hearing or seeing things others do not, feeling unusually energized without sleep, or acting in ways others say are not like you?")),
        SlotSpec("substance_intoxication", "Substance or intoxication risk", 0.75, critical=True, clarify_questions=q("Any alcohol, drugs, sedatives, stimulants, or medication changes today?")),
        SlotSpec("support_safety_plan", "Support and safety plan", 0.80, critical=True, clarify_questions=q("Is there a trusted person physically nearby who can stay with you if you feel unsafe?")),
        SlotSpec("function_impairment", "Functional impairment", 0.60, clarify_questions=q("Is this affecting sleep, work, school, eating, or caring for yourself?")),
        SlotSpec("vitals_med_safety", "Medication safety vitals", 0.60, slot_type="objective", objective_required=True, clarify_questions=q("Do you have a current blood pressure and heart rate, especially if requesting or changing medication?")),
    ],
    "adhd_behavioral_med": [
        SlotSpec("medication_identity", "Medication identity", 0.90, critical=True, traps=["med_name_confusion"], clarify_questions=q("Please read the exact medication name, dose, and directions from the bottle.")),
        SlotSpec("controlled_substance_context", "Controlled-substance context", 0.95, critical=True, clarify_questions=q("Is this a stimulant or controlled medication, and when was it last filled?")),
        SlotSpec("diagnosis_history", "Diagnosis and prior evaluation", 0.75, critical=True, clarify_questions=q("Who diagnosed ADHD and when, and what records are available?")),
        SlotSpec("bp_hr", "Blood pressure and heart rate", 0.80, slot_type="objective", objective_required=True, critical=True, clarify_questions=q("What are your current blood pressure and heart rate numbers?")),
        SlotSpec("side_effects", "Side effects", 0.70, critical=True, clarify_questions=q("Any chest pain, palpitations, fainting, severe anxiety, insomnia, appetite loss, or mood changes?")),
        SlotSpec("diversion_risk", "Diversion or lost-medication risk", 0.75, critical=True, clarify_questions=q("Any early refill, lost medication, dose escalation, or taking more than prescribed?")),
        SlotSpec("function_goals", "Function goals", 0.50, clarify_questions=q("What specific function is worse without the medication, and what improved when it worked?")),
    ],
    "general_med_management": [
        SlotSpec("medication_identity", "Medication identity", 0.90, critical=True, traps=["med_name_confusion"], clarify_questions=q("Please read the exact name, dose, and directions from the medication bottle.")),
        SlotSpec("indication", "Reason for medication", 0.65, clarify_questions=q("What condition is this medication treating?")),
        SlotSpec("last_taken", "Last dose taken", 0.70, critical=True, traps=["adherence_social_desirability"], clarify_questions=q("When was the last dose you actually took?")),
        SlotSpec("side_effects", "Side effects or adverse reaction", 0.80, critical=True, clarify_questions=q("Any new symptoms, rash, swelling, dizziness, fainting, bleeding, mood change, or trouble breathing?")),
        SlotSpec("contraindications", "Contraindications and interactions", 0.80, critical=True, clarify_questions=q("Any pregnancy, kidney/liver disease, blood thinners, new medications, or allergies relevant to this medicine?")),
        SlotSpec("monitoring_labs", "Required monitoring labs", 0.75, slot_type="lab", objective_required=True, clarify_questions=q("Does this medication require recent labs or monitoring, and when were they last checked?")),
        SlotSpec("chart_med_reconciliation", "Chart/pharmacy verification", 0.70, slot_type="chart", objective_required=True, clarify_questions=q("Can this be verified against the medication list in your chart or pharmacy fill record?")),
    ],
    "followup_lab_review": [
        SlotSpec("result_identity", "Test/result identity", 0.80, critical=True, clarify_questions=q("What exact test or lab result are you asking about?")),
        SlotSpec("result_value", "Exact value", 0.85, slot_type="objective", objective_required=True, critical=True, clarify_questions=q("What is the exact value and reference range shown?")),
        SlotSpec("result_date", "Result date and freshness", 0.75, slot_type="objective", objective_required=True, clarify_questions=q("What date was the test collected or resulted?")),
        SlotSpec("ordering_context", "Ordering context", 0.60, slot_type="chart", clarify_questions=q("Why was the test ordered and what symptoms or condition was it checking?")),
        SlotSpec("critical_callback", "Critical-result callback", 0.95, critical=True, clarify_questions=q("Were you told this was critical, urgent, or that you needed immediate follow-up?")),
        SlotSpec("current_symptoms", "Current symptoms", 0.75, critical=True, clarify_questions=q("Any new or worsening symptoms since the test was done?")),
    ],
    "uri_sinus_throat": [
        SlotSpec("symptom_duration", "Symptom duration", 0.65, clarify_questions=q("How many days have symptoms been present, and are they improving, worsening, or double-worsening after initial improvement?")),
        SlotSpec("fever_measured", "Measured fever", 0.75, objective_required=True, critical=True, traps=["fever_guess"], clarify_questions=q("Have you measured your temperature? What number and when?")),
        SlotSpec("breathing_status", "Breathing status", 0.90, critical=True, clarify_questions=q("Any shortness of breath, chest pain, blue lips, or trouble speaking full sentences?")),
        SlotSpec("throat_airway", "Throat/airway danger", 0.90, critical=True, clarify_questions=q("Any drooling, trouble swallowing saliva, muffled voice, neck swelling, or trouble opening your mouth?")),
        SlotSpec("immune_risk", "High-risk host factors", 0.75, critical=True, clarify_questions=q("Are you pregnant, immunocompromised, on chemotherapy, or do you have severe heart/lung disease?")),
        SlotSpec("test_status", "COVID/flu/strep testing", 0.60, slot_type="objective", clarify_questions=q("Have you tested for COVID, flu, or strep? What test and result?")),
        SlotSpec("antibiotic_stewardship", "Antibiotic eligibility", 0.65, clarify_questions=q("Are you asking for antibiotics, and what symptoms make you think this is bacterial?")),
    ],
    "asthma_allergy": [
        SlotSpec("airway_symptoms", "Airway symptoms", 0.95, critical=True, clarify_questions=q("Any throat tightness, tongue/lip swelling, wheezing, or trouble breathing right now?")),
        SlotSpec("rescue_inhaler_use", "Rescue inhaler use", 0.85, critical=True, clarify_questions=q("How often are you using your rescue inhaler, and is it helping?")),
        SlotSpec("peak_flow_or_o2", "Peak flow or oxygen", 0.80, slot_type="objective", objective_required=True, clarify_questions=q("Do you have a peak flow or oxygen reading right now? What is the number?")),
        SlotSpec("trigger_exposure", "Trigger exposure", 0.60, clarify_questions=q("Any new food, medication, sting, allergen, smoke, infection, or exercise trigger?")),
        SlotSpec("prior_severity", "Prior severe reaction", 0.70, critical=True, clarify_questions=q("Have you ever needed epinephrine, ER care, intubation, or hospitalization for this?")),
        SlotSpec("controller_adherence", "Controller medication adherence", 0.55, clarify_questions=q("Are you using your controller inhaler or allergy medication as prescribed?")),
    ],
    "vaginal_sti": [
        SlotSpec("pregnancy_status", "Pregnancy status", 0.90, critical=True, clarify_questions=q("Is there any chance you are pregnant?")),
        SlotSpec("pelvic_pain", "Pelvic or abdominal pain", 0.90, critical=True, clarify_questions=q("Any pelvic, lower belly, or one-sided pain?")),
        SlotSpec("fever_measured", "Measured fever", 0.80, objective_required=True, critical=True, traps=["fever_guess"], clarify_questions=q("Have you measured a fever? What was the number?")),
        SlotSpec("discharge_description", "Discharge description", 0.65, clarify_questions=q("What color, odor, amount, and itch/burning symptoms are present?")),
        SlotSpec("sti_exposure_timing", "STI exposure timing", 0.75, critical=True, clarify_questions=q("When was the possible exposure, and what type of contact occurred?")),
        SlotSpec("hiv_pep_window", "HIV PEP timing", 0.90, critical=True, clarify_questions=q("Was possible HIV exposure within the last 72 hours?")),
        SlotSpec("assault_or_coercion", "Assault or coercion safety", 0.95, critical=True, clarify_questions=q("Was any part of this unwanted, forced, or unsafe for you to discuss privately?")),
    ],
    "eye_ear": [
        SlotSpec("vision_change", "Vision change", 0.95, critical=True, clarify_questions=q("Any vision loss, blurred vision, double vision, or new trouble seeing?")),
        SlotSpec("eye_pain_photophobia", "Eye pain or light sensitivity", 0.90, critical=True, clarify_questions=q("Any significant eye pain, light sensitivity, or pain with eye movement?")),
        SlotSpec("contact_lens", "Contact lens use", 0.80, critical=True, clarify_questions=q("Do you wear contact lenses, and are you wearing them now?")),
        SlotSpec("trauma_chemical", "Trauma or chemical exposure", 0.95, critical=True, clarify_questions=q("Any eye/ear injury, foreign body, chemical exposure, or burn?")),
        SlotSpec("ear_red_flags", "Ear red flags", 0.85, critical=True, clarify_questions=q("Any swelling behind the ear, severe headache, stiff neck, facial weakness, or high fever?")),
        SlotSpec("visual_exam", "Visual exam/photo", 0.70, slot_type="exam", remote_unknowable=True, clarify_questions=q("Can you show or upload a clear photo in good light?")),
    ],
    "gi_symptoms": [
        SlotSpec("abdominal_pain", "Abdominal pain", 0.85, critical=True, clarify_questions=q("Where is the pain, how severe is it, and is it constant or worsening?")),
        SlotSpec("vomiting", "Vomiting", 0.80, critical=True, clarify_questions=q("How many times have you vomited, and can you keep fluids down?")),
        SlotSpec("diarrhea_blood", "Blood or black stool", 0.90, critical=True, clarify_questions=q("Any blood in stool, black/tarry stool, or vomiting blood?")),
        SlotSpec("dehydration", "Dehydration", 0.80, critical=True, clarify_questions=q("Are you dizzy, fainting, very weak, or urinating much less than usual?")),
        SlotSpec("pregnancy_status", "Pregnancy status", 0.75, critical=True, clarify_questions=q("Is there any chance you are pregnant?")),
        SlotSpec("travel_exposure", "Travel or outbreak exposure", 0.55, clarify_questions=q("Any recent travel, suspicious food, sick contacts, antibiotics, or outbreak exposure?")),
        SlotSpec("abdominal_exam", "Abdominal exam", 0.75, slot_type="exam", remote_unknowable=True, why_it_matters="Peritoneal signs and focal exam cannot be reliably assessed remotely."),
    ],
    "gerd_dyspepsia": [
        SlotSpec("chest_or_exertional", "Chest/exertional symptoms", 0.95, critical=True, traps=["heartburn_label"], clarify_questions=q("Is there pressure, tightness, heaviness, shortness of breath, sweating, or symptoms with exertion?")),
        SlotSpec("alarm_gi", "GI alarm features", 0.85, critical=True, clarify_questions=q("Any trouble swallowing, vomiting blood, black stool, unintentional weight loss, or persistent vomiting?")),
        SlotSpec("abdominal_pain", "Abdominal pain", 0.70, clarify_questions=q("Where is the pain or burning, and what makes it better or worse?")),
        SlotSpec("medication_risk", "Medication risk", 0.65, clarify_questions=q("Any NSAID use, blood thinners, steroids, or heavy alcohol use?")),
        SlotSpec("prior_history", "Prior history", 0.45, clarify_questions=q("Have you had reflux, ulcer disease, gallbladder problems, or heart disease before?")),
        SlotSpec("exam_ecg_boundary", "Exam/ECG boundary", 0.85, slot_type="exam", remote_unknowable=True, critical=True, why_it_matters="Cardiac causes cannot be ruled out by remote symptom labels alone."),
    ],
    "musculoskeletal_pain": [
        SlotSpec("trauma_mechanism", "Trauma mechanism", 0.75, critical=True, clarify_questions=q("Was there a fall, injury, crash, heavy lift, or direct blow?")),
        SlotSpec("neuro_deficit", "Neurological deficit", 0.95, critical=True, clarify_questions=q("Any new weakness, numbness, saddle anesthesia, foot drop, or trouble walking?")),
        SlotSpec("bowel_bladder", "Bowel/bladder red flag", 0.95, critical=True, clarify_questions=q("Any new loss of bladder/bowel control or inability to urinate?")),
        SlotSpec("infection_cancer_risk", "Infection/cancer risk", 0.85, critical=True, clarify_questions=q("Any fever, IV drug use, cancer history, immunosuppression, or unexplained weight loss?")),
        SlotSpec("anticoagulant_risk", "Anticoagulant risk", 0.70, critical=True, clarify_questions=q("Are you on blood thinners, or do you bruise/bleed easily?")),
        SlotSpec("pain_function", "Pain and function", 0.55, clarify_questions=q("Can you walk, work, sleep, and do normal activities? What makes the pain worse or better?")),
        SlotSpec("physical_exam", "Physical exam", 0.70, slot_type="exam", remote_unknowable=True, why_it_matters="Strength, reflexes, point tenderness, and imaging decisions may require in-person exam."),
    ],
    "routine_dermatology": [
        SlotSpec("lesion_photo_quality", "Photo quality", 0.70, slot_type="exam", objective_required=True, clarify_questions=q("Can you upload clear photos in good light, close up and from farther away?")),
        SlotSpec("infection_signs", "Infection signs", 0.85, critical=True, clarify_questions=q("Any spreading redness, warmth, pus, severe pain, fever, red streaking, or rapidly worsening area?")),
        SlotSpec("mucosal_or_airway", "Mucosal/airway involvement", 0.95, critical=True, clarify_questions=q("Any mouth/eye/genital sores, lip/tongue swelling, wheezing, or throat tightness?")),
        SlotSpec("pregnancy_status", "Pregnancy status", 0.70, critical=True, clarify_questions=q("Is there any chance you are pregnant, especially if requesting prescription skin medication?")),
        SlotSpec("new_medication", "New medication/exposure", 0.75, critical=True, clarify_questions=q("Any new medication, product, plant exposure, chemical, bite, or travel?")),
        SlotSpec("routine_goal", "Routine dermatology goal", 0.45, clarify_questions=q("Are you mainly seeking acne/eczema/fungal treatment, itch relief, cosmetic treatment, or infection evaluation?")),
    ],
    "skin_infection": [
        SlotSpec("infection_spread", "Spread and severity", 0.90, critical=True, clarify_questions=q("Is redness spreading quickly, very painful, warm, swollen, or larger than your palm?")),
        SlotSpec("fever_measured", "Measured fever", 0.80, objective_required=True, critical=True, traps=["fever_guess"], clarify_questions=q("Have you measured a fever? What was the number?")),
        SlotSpec("abscess_drainage", "Abscess or drainage", 0.75, critical=True, clarify_questions=q("Is there pus, a boil, drainage, or a soft/fluctuant lump?")),
        SlotSpec("high_risk_host", "High-risk host factors", 0.80, critical=True, clarify_questions=q("Do you have diabetes, immune suppression, chemotherapy, dialysis, or poor circulation?")),
        SlotSpec("location_risk", "High-risk location", 0.75, critical=True, clarify_questions=q("Is it on the face, near the eye, hand, genitals, or over a joint?")),
        SlotSpec("photo_exam", "Photo/visual exam", 0.70, slot_type="exam", objective_required=True, clarify_questions=q("Can you upload a clear photo with something for size comparison?")),
    ],
    "obesity_metabolic": [
        SlotSpec("medication_identity", "Medication identity", 0.80, critical=True, traps=["med_name_confusion"], clarify_questions=q("What medication are you requesting or taking, including exact dose and schedule?")),
        SlotSpec("bmi_weight_trend", "Weight/BMI trend", 0.65, slot_type="objective", objective_required=True, clarify_questions=q("What is your current height, weight, and recent weight trend?")),
        SlotSpec("contraindications", "Contraindications", 0.90, critical=True, clarify_questions=q("Any pregnancy, pancreatitis, gallbladder disease, medullary thyroid cancer/MEN2, severe GI disease, or eating disorder history?")),
        SlotSpec("side_effects", "Side effects", 0.80, critical=True, clarify_questions=q("Any severe abdominal pain, persistent vomiting, dehydration, fainting, or low blood sugar symptoms?")),
        SlotSpec("diabetes_context", "Diabetes context", 0.65, clarify_questions=q("Do you have diabetes, and are you using insulin or sulfonylureas?")),
        SlotSpec("lab_monitoring", "Lab monitoring", 0.65, slot_type="lab", objective_required=True, clarify_questions=q("Any recent A1c, kidney/liver labs, lipids, or pregnancy test if applicable?")),
    ],
}


RED_FLAG_PATTERNS: Dict[str, List[tuple[str, str, float]]] = {
    "chest_discomfort": [
        ("symptom_quality", "pressure|tight|squeez|heavy|crushing|elephant", 1.0),
        ("exertional_component", "yes|worse with|worse when|brought on|triggered by|better with rest|rest helps|improves? with rest", 0.9),
        ("dyspnea", "can't|cannot|hard|short|breath|full sentence|stop", 0.85),
        ("diaphoresis", "sweat|clammy|nausea|faint|passed out", 0.8),
    ],
    "dyspnea_respiratory": [
        ("oxygen_saturation", "8[0-9]|low|below 90|eighty", 1.0),
        ("sentence_test", "no|can't|cannot|pause|few words", 0.9),
        ("mental_status", "confus|sleepy|drowsy|hard to wake", 0.9),
        ("exertional_tolerance", "can't walk|cannot walk|bedroom|kitchen|worse", 0.75),
    ],
    "med_refill_hypertension": [
        ("home_bp_number", "1[89][0-9]|2[0-9][0-9]|over 180|above 180|very high", 0.95),
        ("side_effects", "faint|passed out|swelling tongue|chest pain|short of breath", 0.8),
        ("pregnancy_status", "pregnant|trying", 0.9),
    ],
    "uti_symptoms": [
        ("fever_measured", "10[2-9]|fever|chills", 0.8),
        ("flank_pain", "side|flank|kidney|back below ribs|one sided", 0.9),
        ("vomiting", "vomit|can't keep|cannot keep", 0.85),
        ("pregnancy_status", "pregnant|yes", 0.85),
    ],
    "rash": [
        ("mucosal_involvement", "mouth|eye|lip|genital|nose|sores", 1.0),
        ("skin_pain", "pain|burn|blister|peel|slough", 0.95),
        ("airway_symptoms", "tongue|throat|wheez|breath|swelling", 1.0),
        ("new_medication", "new|started|antibiotic|seizure|sulfa|lamotrigine", 0.75),
    ],
    "diabetes_hyperglycemia": [
        ("glucose_number", "[4-9][0-9]{2}|high|meter says hi", 0.9),
        ("ketones", "large|moderate|positive", 0.9),
        ("vomiting", "vomit|can't keep|cannot keep", 0.85),
        ("mental_status", "confus|sleepy|drowsy|deep breathing|fast breathing", 0.9),
    ],
    "headache_migraine": [
        ("headache_onset", "sudden|worst|thunderclap|instant|seconds|switch|worst ever|worst of my life", 1.0),
        ("neck_stiffness", "stiff|can't bend|cannot bend|meningitis|neck pain with headache", 0.95),
        ("neuro_deficit", "weak|numb|vision|double|slur|confus|droop|can't move|cannot move", 0.95),
        ("fever_measured", "10[2-9]|fever|chills", 0.85),
    ],
    "mental_health": [
        ("self_harm", "kill myself|end my life|suicide|hurt myself|not safe|overdose|no reason to live", 1.0),
        ("harm_others", "hurt someone|kill someone|homicid|lose control|weapon", 1.0),
        ("psychosis_mania", "voices|hearing things|seeing things|paranoid|no sleep|manic|invincible", 0.9),
        ("substance_intoxication", "overdose|took too much|mixed with alcohol|blackout", 0.9),
    ],
    "adhd_behavioral_med": [
        ("side_effects", "chest pain|palpitations|faint|severe anxiety|not sleeping|suicid", 0.9),
        ("bp_hr", "1[89][0-9]|2[0-9][0-9]|heart rate.*1[3-9][0-9]|very high", 0.85),
        ("diversion_risk", "lost|stolen|early refill|took extra|ran out early", 0.75),
    ],
    "general_med_management": [
        ("side_effects", "swelling|trouble breathing|faint|bleeding|black stool|rash|chest pain|suicid", 0.9),
        ("contraindications", "pregnant|kidney failure|liver failure|blood thinner|allergic|anaphylaxis", 0.85),
    ],
    "followup_lab_review": [
        ("critical_callback", "critical|urgent|go to ER|dangerously|panic value|called me", 0.95),
        ("current_symptoms", "chest pain|short of breath|confus|faint|severe|weak|bleeding", 0.9),
        ("result_value", "potassium.*[67]|glucose.*[4-9][0-9]{2}|hemoglobin.*[0-6]\\b|creatinine.*[5-9]", 0.9),
    ],
    "uri_sinus_throat": [
        ("breathing_status", "short of breath|can't breathe|blue lips|can't speak|chest pain", 0.95),
        ("throat_airway", "drool|can't swallow|muffled voice|neck swelling|can't open mouth|stridor", 0.95),
        ("fever_measured", "10[3-9]|fever.*5 days|rigors|chills", 0.75),
    ],
    "asthma_allergy": [
        ("airway_symptoms", "throat.*tight|tongue.*swell|lip.*swell|can't breathe|wheez", 1.0),
        ("rescue_inhaler_use", "not helping|every hour|every two hours|can't speak|worse", 0.9),
        ("prior_severity", "intubated|ICU|epinephrine|anaphylaxis|hospitalized", 0.85),
    ],
    "vaginal_sti": [
        ("pelvic_pain", "severe|one-sided|lower belly|pelvic pain|shoulder pain", 0.9),
        ("fever_measured", "10[2-9]|fever|chills", 0.85),
        ("hiv_pep_window", "within 72 hours|last night|yesterday|unprotected|needle", 0.9),
        ("assault_or_coercion", "forced|assault|rape|coerced|not safe|partner", 1.0),
    ],
    "eye_ear": [
        ("vision_change", "vision loss|can't see|blurred|double|curtain", 0.95),
        ("eye_pain_photophobia", "severe pain|light hurts|photophobia|pain with movement", 0.9),
        ("trauma_chemical", "chemical|acid|alkali|foreign body|metal|injury", 1.0),
        ("ear_red_flags", "swelling behind ear|facial weakness|stiff neck|severe headache", 0.9),
    ],
    "gi_symptoms": [
        ("abdominal_pain", "severe|constant|right lower|rigid|worst|guarding", 0.9),
        ("diarrhea_blood", "blood|black|tarry|vomiting blood|coffee ground", 0.95),
        ("dehydration", "faint|dizzy|not urinating|very weak|can't keep fluids", 0.85),
        ("vomiting", "can't keep|cannot keep|persistent|green vomit|projectile", 0.8),
    ],
    "gerd_dyspepsia": [
        ("chest_or_exertional", "pressure|tight|heavy|exertion|stairs|short of breath|sweat", 1.0),
        ("alarm_gi", "trouble swallowing|vomiting blood|black stool|weight loss|persistent vomiting", 0.9),
    ],
    "musculoskeletal_pain": [
        ("neuro_deficit", "weak|numb|tingl|saddle|private area|groin|genital|perineal|inner thigh|foot drop|can't walk|cannot walk|stairs", 0.95),
        ("bowel_bladder", "lost bladder|lost bowel|can't urinate|cannot urinate|can't pee|cannot pee|can't empty|cannot empty|incontinence|urinary retention|bladder.*full|bleeder.*full|more full than usual", 1.0),
        ("infection_cancer_risk", "fever|cancer|IV drug|immunosuppressed|weight loss", 0.9),
        ("trauma_mechanism", "fall|crash|major injury|hit by|blood thinner", 0.85),
    ],
    "routine_dermatology": [
        ("infection_signs", "spreading|red streak|pus|fever|very painful|rapid", 0.85),
        ("mucosal_or_airway", "mouth|eye|genital|tongue|throat|wheez|trouble breathing", 1.0),
        ("new_medication", "new medication|started|antibiotic|sulfa|lamotrigine", 0.75),
    ],
    "skin_infection": [
        ("infection_spread", "spreading quickly|rapid|severe pain|larger than|warm|swollen", 0.85),
        ("fever_measured", "10[2-9]|fever|chills", 0.85),
        ("location_risk", "near eye|face|hand|genitals|over joint", 0.75),
        ("high_risk_host", "diabetes|chemo|dialysis|immunosuppressed|transplant", 0.8),
    ],
    "obesity_metabolic": [
        ("contraindications", "pregnant|pancreatitis|thyroid cancer|MEN2|eating disorder", 0.9),
        ("side_effects", "severe abdominal pain|persistent vomiting|dehydrated|faint|low blood sugar", 0.9),
    ],
}


HEADACHE_CONTRADICTION = {
    "id": "CONTRA_HEADACHE_MILD_BUT_SUDDEN",
    "domain": "headache_migraine",
    "concept_a": "headache_onset",
    "negative_a": False,
    "concept_b": "headache_onset",
    "pattern_b": "sudden|worst|thunderclap|instant|seconds",
    "reason": "Patient describes headache as mild but onset language suggests thunderclap — severity may be minimized.",
}

CONTRADICTION_RULES = [
    HEADACHE_CONTRADICTION,
    {
        "id": "CONTRA_DYSPNEA_DENIAL_FUNCTIONAL_LIMIT",
        "domain": "dyspnea_respiratory",
        "concept_a": "dyspnea",
        "negative_a": True,
        "concept_b": "exertional_tolerance",
        "pattern_b": "can't|cannot|stop|worse|bedroom|kitchen|stairs",
        "reason": "Patient denies shortness of breath but reports functional breathing limitation.",
    },
    {
        "id": "CONTRA_CHEST_NO_PAIN_PRESSURE",
        "domain": "chest_discomfort",
        "concept_a": "symptom_quality",
        "negative_a": True,
        "concept_b": "symptom_quality",
        "pattern_b": "pressure|tight|heavy|burn|squeez",
        "reason": "Patient denies 'pain' but describes pressure/tightness/burning, which may cross the pain-word boundary.",
    },
    {
        "id": "CONTRA_MED_ADHERENCE_BOTTLE_EMPTY",
        "domain": "med_refill_hypertension",
        "concept_a": "last_taken",
        "negative_a": False,
        "concept_b": "medication_identity",
        "pattern_b": "empty|lost|don't know|not sure",
        "reason": "Patient reports taking medication but cannot verify medication identity or supply.",
    },
    {
        "id": "CONTRA_UTI_DENIES_FEVER_BUT_HOT",
        "domain": "uti_symptoms",
        "concept_a": "fever_measured",
        "negative_a": True,
        "concept_b": "fever_measured",
        "pattern_b": r"hot|warm|burning up|sweating|10[0-9]",
        "reason": "Patient denies fever but uses fever-suggestive language or reports elevated temperature.",
    },
    {
        "id": "CONTRA_UTI_SIMPLE_BUT_FLANK",
        "domain": "uti_symptoms",
        "concept_a": "dysuria",
        "negative_a": False,
        "concept_b": "flank_pain",
        "pattern_b": r"kidney|flank|back.*hurts|side.*hurts|under.*rib",
        "reason": "Patient describes simple lower UTI but reports flank/kidney pain suggesting pyelonephritis.",
    },
    {
        "id": "CONTRA_RASH_DENIES_AIRWAY_BUT_THROAT",
        "domain": "rash",
        "concept_a": "airway_symptoms",
        "negative_a": True,
        "concept_b": "airway_symptoms",
        "pattern_b": r"throat.*tight|swallow|hoarse|voice.*change|tongue.*swell",
        "reason": "Patient denies airway symptoms but describes throat tightness or swallowing difficulty.",
    },
    {
        "id": "CONTRA_DM_GLUCOSE_FINE_BUT_SYMPTOMS",
        "domain": "diabetes_hyperglycemia",
        "concept_a": "glucose_number",
        "negative_a": False,
        "concept_b": "vomiting",
        "pattern_b": r"vomit|throw up|nausea|can't keep|thirst|dry",
        "reason": "Patient says glucose is fine but reports DKA-suggestive symptoms.",
    },
    {
        "id": "CONTRA_DM_DENIES_CONFUSION_BUT_CAREGIVER",
        "domain": "diabetes_hyperglycemia",
        "concept_a": "mental_status",
        "negative_a": True,
        "concept_b": "mental_status",
        "pattern_b": r"confus|not right|acting strange|sleepy|can't think|not making sense",
        "reason": "Patient denies altered mental status but language or caregiver report suggests confusion.",
    },
    # --- Headache / Migraine additional contradiction rules ---
    {
        "id": "CONTRA_HA_DENIES_NEURO_BUT_SYMPTOMS",
        "domain": "headache_migraine",
        "concept_a": "neuro_deficit",
        "negative_a": True,
        "concept_b": "neuro_deficit",
        "pattern_b": r"weak|numb|vision|double|blur|slur|droop|can't move|tingling|one side",
        "reason": "Patient denies neurological deficit but describes focal symptoms suggesting stroke or mass lesion.",
    },
    {
        "id": "CONTRA_HA_NO_FEVER_BUT_STIFF_NECK",
        "domain": "headache_migraine",
        "concept_a": "fever_measured",
        "negative_a": True,
        "concept_b": "neck_stiffness",
        "pattern_b": r"stiff|can't bend|hurts to bend|can't touch chin|pain.*neck",
        "reason": "Patient denies fever but reports neck stiffness — meningitis cannot be excluded by self-reported absence of fever alone.",
    },
    # --- Dyspnea / Respiratory additional contradiction rules ---
    {
        "id": "CONTRA_DY_CLAIMS_FINE_BUT_CANT_SPEAK",
        "domain": "dyspnea_respiratory",
        "concept_a": "sentence_test",
        "negative_a": True,
        "concept_b": "sentence_test",
        "pattern_b": r"can't|cannot|stop|pause|few words|catching|gasping|winded",
        "reason": "Patient denies sentence test difficulty but uses language suggesting inability to speak in full sentences.",
    },
    {
        "id": "CONTRA_DY_DENIES_CONFUSION_BUT_ALTERED",
        "domain": "dyspnea_respiratory",
        "concept_a": "mental_status",
        "negative_a": True,
        "concept_b": "mental_status",
        "pattern_b": r"confus|sleepy|drowsy|not right|hard to wake|foggy|daze",
        "reason": "Patient denies altered mental status but describes confusion or excessive drowsiness suggesting hypoxia.",
    },
]


ESCALATION_PROBES: Dict[tuple[str, str], str] = {
    ("chest_discomfort", "symptom_quality"): "Is the pressure/tightness happening right now, or has it stopped?",
    ("chest_discomfort", "dyspnea"): "Right now, can you walk across the room without stopping to catch your breath?",
    ("headache_migraine", "headache_onset"): "Did this headache reach maximum intensity within seconds, like a switch, or did it build up over minutes to hours?",
    ("headache_migraine", "neck_stiffness"): "Can you touch your chin to your chest without pain?",
    ("dyspnea_respiratory", "oxygen_saturation"): "What number does the pulse oximeter show right now?",
    ("dyspnea_respiratory", "sentence_test"): "Can you say 'today is a good day' without pausing to breathe?",
    ("uti_symptoms", "flank_pain"): "Is the pain in your side constant, or does it come and go? Point to exactly where it hurts.",
    ("uti_symptoms", "fever_measured"): "Do you have a thermometer? Can you take your temperature right now?",
    ("rash", "mucosal_involvement"): "Look in a mirror — are there any sores or blisters inside your mouth, on your lips, or around your eyes?",
    ("rash", "airway_symptoms"): "Can you swallow a sip of water without difficulty right now?",
    ("diabetes_hyperglycemia", "glucose_number"): "What does your meter say right now? Read me the exact number.",
    ("diabetes_hyperglycemia", "mental_status"): "Can you tell me today's date and where you are right now?",
    ("med_refill_hypertension", "home_bp_number"): "Take a reading right now if you have a cuff. What are the two numbers?",
    ("med_refill_hypertension", "side_effects"): "Are you having chest pain, blurred vision, or severe headache right now?",
}

# ---------------------------------------------------------------------------
# Modality-specific question adaptations
# ---------------------------------------------------------------------------

MODALITY_ADAPTATIONS: Dict[str, Dict[str, str]] = {
    "phone": {
        "prefix": "Can you tell me \u2014",
        "number_prompt": "Read me the exact number you see.",
        "visual_prompt": "Describe what it looks like in your own words.",
        "action_prompt": "Are you able to do that right now while we talk?",
    },
    "text": {
        "prefix": "",
        "number_prompt": "Type the exact number shown.",
        "visual_prompt": "If possible, send a photo.",
        "action_prompt": "Try this now and reply with the result.",
    },
    "video": {
        "prefix": "",
        "number_prompt": "Hold the display up to the camera so I can read it.",
        "visual_prompt": "Show me the area \u2014 hold your camera about 6 inches away.",
        "action_prompt": "Let me watch you try that now.",
    },
    "in_person": {
        "prefix": "",
        "number_prompt": "Let me see the reading on your device.",
        "visual_prompt": "Let me take a look at that area.",
        "action_prompt": "Go ahead and try that now \u2014 I'll observe.",
    },
}

CLEAR_STEPS = {
    "missing": "Elicit the missing safety variable before proceeding.",
    "uncertain": "Clarify ambiguous language into observable facts or numbers.",
    "distorted": "Translate medical vocabulary into patient-life examples.",
    "contradictory": "Resolve inconsistency using functional or objective evidence.",
    "objective_needed": "Ask for a number, device reading, chart value, photo, or collateral source.",
    "unknowable_remote": "Name the remote boundary and define the trigger for escalation.",
    "red_flag": "Escalate or route to clinician; do not continue autonomous pathway.",
}
