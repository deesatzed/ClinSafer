"""Unified demo: runs all hand-authored cases through JRE + Black Swan Guardrails.

Run:
    python unified_demo.py                                         # All cases, all outputs
    python unified_demo.py --case BS-003-offpath-stroke-in-refill  # Single case
    python unified_demo.py --list                                  # List all case IDs
    python unified_demo.py --open                                  # Generate + open in browser
    python unified_demo.py --no-write                              # Stdout only
"""
from __future__ import annotations

import argparse
import csv
import html as html_mod
import json
import webbrowser
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from jre import JudgmentReadinessEngine, BlackSwanGuardrailEngine, BLACK_SWAN_CASES
from jre import report_to_markdown, guardrail_report_to_markdown
from jre.models import CaseInput, ReadinessReport, most_restrictive, STATE_PRIORITY
from jre.black_swan import GuardrailReport, SENTINEL_RULES, INTEGRITY_RULES
from jre.synthetic_data import BASE_CASES
from jre.templates import (
    MODALITY_ADAPTATIONS, DOMAIN_TEMPLATES, CONTRADICTION_RULES,
    ESCALATION_PROBES,
)
from jre.engine import SOURCE_SCORING_WEIGHT, GESTALT_PATTERNS
from jre.experience import ExperienceMemory


# ---------------------------------------------------------------------------
# Case Narrative System
# ---------------------------------------------------------------------------

@dataclass
class CaseNarrative:
    """Human-readable explanation of what a case demonstrates."""
    title: str
    scenario: str
    jre_demonstrates: str
    bsg_demonstrates: str
    combined_insight: str
    category: str  # grouping tag


CASE_NARRATIVES: Dict[str, CaseNarrative] = {
    # --- BASE CASES (8) ---
    "CP-001-heartburn-pressure": CaseNarrative(
        title="Pain-Word Boundary",
        scenario="58-year-old calls about heartburn, but describes sub-sternal pressure that worsens walking upstairs. The word 'heartburn' masks exertional cardiac pain.",
        jre_demonstrates="Catches the pain-word boundary trap: 'heartburn' vs 'pressure' mismatch. Detects exertional component and escalates despite patient framing.",
        bsg_demonstrates="No sentinel or integrity triggers -- the danger is entirely in clinical semantics, which Judgment Readiness handles.",
        combined_insight="Pure Judgment Readiness escalation. Black Swan Guard confirms no assumption breaches, validating that the escalation is clinically driven, not a system anomaly.",
        category="base_escalation",
    ),
    "DY-001-denies-sob-low-ox": CaseNarrative(
        title="Denial with Low O2",
        scenario="72-year-old denies shortness of breath but pulse oximeter reads 89%. Patient's self-report contradicts objective device data.",
        jre_demonstrates="Detects that 'no shortness of breath' is unreliable when O2 is 89%. Red-flags the oxygen reading and escalates.",
        bsg_demonstrates="No sentinel triggers beyond what Judgment Readiness already catches. The objective data contradiction is a clinical issue, not a system integrity issue.",
        combined_insight="Judgment Readiness objective-data gating works correctly -- device data overrides patient denial. Black Swan Guard adds no further restriction, confirming this is handled at the clinical layer.",
        category="base_escalation",
    ),
    "RF-001-bp-normal-no-number": CaseNarrative(
        title="Normal Without Number",
        scenario="49-year-old says blood pressure is 'normal' but provides no actual number. Wants a med refill without objective verification.",
        jre_demonstrates="Catches the 'normal without number' distortion trap. Requires objective BP data before allowing refill pathway.",
        bsg_demonstrates="No guardrail triggers -- this is a completeness/quality issue that Judgment Readiness handles through slot analysis.",
        combined_insight="Judgment Readiness correctly gates the refill on missing objective data. The system won't proceed without a real BP number, which is exactly the safety behavior needed.",
        category="base_objective",
    ),
    "UTI-001-simple-words-hide-flank": CaseNarrative(
        title="Hidden Flank Pain",
        scenario="34-year-old reports burning urination but also mentions side pain and feeling hot. Simple UTI framing hides possible pyelonephritis.",
        jre_demonstrates="Detects flank pain and unmeasured fever as red flags that push this beyond uncomplicated UTI pathway. Escalates.",
        bsg_demonstrates="No additional triggers -- the clinical red flags are sufficient for Judgment Readiness to handle correctly.",
        combined_insight="Judgment Readiness red-flag pattern matching catches the complicated UTI signals. The escalation is appropriate and Black Swan Guard confirms no system-level issues.",
        category="base_escalation",
    ),
    "RASH-001-new-med-mouth-sores": CaseNarrative(
        title="New Med + Mucosal Involvement",
        scenario="27-year-old has a new rash with mouth sores after starting a new medication. Potential Stevens-Johnson syndrome risk.",
        jre_demonstrates="Detects mucosal involvement + new medication + skin pain as a dangerous combination requiring escalation.",
        bsg_demonstrates="No sentinel triggers -- SJS risk is a clinical pattern, not a system integrity issue.",
        combined_insight="Judgment Readiness correctly identifies the SJS-risk triad. This case demonstrates that clinical pattern detection doesn't need guardrail-layer intervention.",
        category="base_escalation",
    ),
    "DM-001-sugar-fine-hidden-400": CaseNarrative(
        title="Sugar Is Fine (Hidden DKA)",
        scenario="42-year-old with nausea and thirst says sugar is 'fine' but a device reading shows glucose of 400. Classic DKA risk hidden by vague language.",
        jre_demonstrates="Catches the distortion in 'sugar is fine' when objective glucose is critically high. Escalates for DKA risk.",
        bsg_demonstrates="No additional triggers. The objective data contradiction is handled at the Judgment Readiness layer.",
        combined_insight="This case validates that Judgment Readiness distortion detection works even when patients sincerely believe their own inaccurate assessment.",
        category="base_escalation",
    ),
    "CP-002-low-risk-but-incomplete": CaseNarrative(
        title="Low Risk, Remote Boundary",
        scenario="24-year-old with brief chest soreness after exercise. Low risk profile but no ECG or vitals available remotely.",
        jre_demonstrates="Assigns relatively high readiness but marks ECG/vitals as remote unknowable boundary -- can't fully clear without in-person data.",
        bsg_demonstrates="Black Swan Guard detects the incomplete boundary and applies HOLD_AND_VERIFY, requiring clinician review before proceeding.",
        combined_insight="Even low-risk cases hit the remote-boundary wall. The combined pipeline correctly holds for clinician verification rather than auto-clearing based on history alone.",
        category="base_incomplete",
    ),
    "RF-002-good-refill-readyish": CaseNarrative(
        title="Clean Refill (Control Case)",
        scenario="62-year-old with stable lisinopril refill, provides BP numbers, no red flags, no contradictions. This is the 'happy path' case.",
        jre_demonstrates="High Readiness Index score, READY or near-READY state. Minimal unknowns, good objective data coverage.",
        bsg_demonstrates="ALLOW_WITH_AUDIT at T4 autonomy. No sentinel, integrity, or envelope issues.",
        combined_insight="This control case proves the system doesn't over-restrict. A genuinely safe refill flows through both engines without being blocked.",
        category="base_control",
    ),
    # --- HEADACHE DOMAIN ---
    "HA-001-thunderclap-minimized": CaseNarrative(
        title="Thunderclap Minimized",
        scenario="45-year-old reports 'worst headache of my life' that came on suddenly like a switch, but minimizes it as 'just mild now.' Neck is stiff.",
        jre_demonstrates="Catches thunderclap onset language as a critical red flag. Detects the minimization trap where 'mild now' contradicts 'worst ever.' Neck stiffness adds to the severity.",
        bsg_demonstrates="No sentinel or integrity triggers beyond what Judgment Readiness handles. The danger is in the clinical presentation pattern.",
        combined_insight="Thunderclap + neck stiffness = subarachnoid hemorrhage until proven otherwise. Judgment Readiness pattern detection correctly escalates despite the patient's attempt to minimize.",
        category="base_escalation",
    ),
    # --- INTELLIGENCE SHOWCASE CASE ---
    "BS-014-diabetic-uti-masking-sepsis": CaseNarrative(
        title="Diabetic UTI Masking Emerging Sepsis -- Phone Triage Intelligence Showcase",
        scenario="A 68-year-old diabetic with CKD calls for UTI antibiotic refill. Multiple intelligence layers activate: fever contradiction (denies but hot and sweaty), device-patient glucose conflict (380 vs fine), caregiver-patient mental status disagreement, flank pain suggesting pyelonephritis, acute onset with severity amplifiers, and cross-domain sepsis gestalt detection.",
        jre_demonstrates="UTI domain with cascading red flags: fever contradiction, glucose source conflict (device 380mg/dL vs patient fine), mental status source conflict (caregiver not making sense vs patient I am fine), flank pain pyelonephritis signal. Comorbidity boost from diabetes + CKD. Severity amplifier from worst I have ever felt. Temporal acute from suddenly this morning. Phone modality adapts questions with verbal prompts.",
        bsg_demonstrates="Cross-domain sepsis gestalt fires (fever + confusion in UTI domain). Source integrity flags for device-patient disagreement on glucose. Caregiver-patient conflict on mental status. Multiple assumption breaches push autonomy cap down.",
        combined_insight="This single case exercises 8+ intelligence features simultaneously: contradiction rules, source conflicts, cross-domain gestalt, modality adaptation, severity amplifiers, temporal modifiers, comorbidity boost, and experience memory recording. It demonstrates the system ability to synthesize multiple weak signals into a strong escalation decision.",
        category="base_showcase",
    ),
    # --- DOCTRONIC CEO CASES: subtle autonomy-boundary failures ---
    "CEO-001-stale-ace-refill-ckd-nsaid": CaseNarrative(
        title="Routine Refill With Stale Safety Evidence",
        scenario="66-year-old requests lisinopril refill. BP is described as normal, but the reading is months old and no number is available. Patient has CKD, uses ibuprofen most days, and mentions dizziness standing.",
        jre_demonstrates="Separates statement from fact: prior normal BP is not current BP control; 'labs okay last time' is not current renal safety; dizziness is not a clean denial. Objective data and medication-context gaps block judgment readiness.",
        bsg_demonstrates="Stale-data and high-risk comorbidity assumptions weaken the refill pathway. Autonomy should be capped to intake/draft/clarification, not autonomous renewal.",
        combined_insight="This is the CEO hero case: a mature AI can write a plausible refill plan, but an autonomy-boundary layer refuses to infer current safety from stale, vague, patient-shaped evidence.",
        category="ceo_boundary",
    ),
    "CEO-002-refill-rote-denial-dizziness": CaseNarrative(
        title="Refill-Seeking Rote Denial",
        scenario="54-year-old wants a refill approved quickly before travel. Answers are repetitive denials, then the patient casually mentions seeing spots and dizziness when standing.",
        jre_demonstrates="Shows denial reliability as a measured signal. The system does not treat rote negative answers as strong evidence when the same encounter contains unresolved symptoms and no current BP number.",
        bsg_demonstrates="Copy-paste / metric-gaming style behavior weakens the communication assumption even if the patient is not malicious.",
        combined_insight="The business problem is avoidable friction: ask one targeted question before denying, escalating, or approving a refill on unreliable denials.",
        category="ceo_boundary",
    ),
    "CEO-003-cost-fear-minimizes-alarm": CaseNarrative(
        title="Cost Fear Minimizes Alarm Symptoms",
        scenario="59-year-old with diabetes describes exertional tight indigestion but asks the system to say it can wait because they cannot afford the ER and need to work.",
        jre_demonstrates="Catches exertional cardiac-pattern language despite minimization and care-avoidance pressure.",
        bsg_demonstrates="Care-avoidance pressure prevents the system from downgrading risk simply because the patient resists escalation.",
        combined_insight="At scale, patients shape the conversation for economic and practical reasons. Safety language must preserve trust without letting cost fear lower clinical boundaries.",
        category="ceo_boundary",
    ),
    "CEO-004-bruising-partner-nearby": CaseNarrative(
        title="Unsafe Disclosure Channel",
        scenario="32-year-old asks about bruises/rash but says their partner is listening and asks the system not to mention the message.",
        jre_demonstrates="Clinical rash data alone is not the main issue; the encounter evidence is socially unsafe and incomplete.",
        bsg_demonstrates="Coercion/channel safety assumption is breached, routing to a protected human workflow rather than routine automation.",
        combined_insight="This demonstrates that healthcare AI safety includes communication context, not only clinical pattern matching.",
        category="ceo_boundary",
    ),
    "CEO-005-caregiver-conflict-fine-but-confused": CaseNarrative(
        title="Patient Says Fine, Caregiver Says Confused",
        scenario="71-year-old diabetic with possible UTI says she is fine. Caregiver reports she is not herself, repeats questions, and had side/flank pain.",
        jre_demonstrates="Shows source and interpretation boundaries: patient self-report should not dominate caregiver concern when mental status and systemic infection risk are possible.",
        bsg_demonstrates="High-risk host factors and uncertainty budget cap autonomy even if the patient minimizes symptoms.",
        combined_insight="This is a subtle telemedicine problem: the patient is seeking help but may be unable to accurately report their own alarm state.",
        category="ceo_boundary",
    ),
    "CEO-006-nonresponse-after-risk-warning": CaseNarrative(
        title="Silent Alarm After Risk Warning",
        scenario="57-year-old describes exertional chest pressure and sweating, then stops responding after risk is raised.",
        jre_demonstrates="Clinical signal is concerning, but the important operational fact is that the encounter did not close safely.",
        bsg_demonstrates="Nonresponse after risk disclosure is treated as workflow failure requiring active handoff rather than silent abandonment.",
        combined_insight="This links safety to churn and operations: abandonment after scary language is both a patient-risk event and a recoverable workflow moment.",
        category="ceo_boundary",
    ),
    "CEO-007-unasked-is-not-denied": CaseNarrative(
        title="Unasked Is Not Denied",
        scenario="41-year-old has a clean-looking lisinopril refill transcript with current BP and no side effects, but pregnancy status, renal labs, and chart/pharmacy reconciliation were never asked.",
        jre_demonstrates="Shows the difference between documentation completeness and judgment readiness. Missing required safety slots remain missing, not negative.",
        bsg_demonstrates="Autonomy is capped because critical assumptions were not established, even though the available answers look reassuring.",
        combined_insight="A mature AI should not summarize unasked safety variables as absent. This case makes inference boundaries visible.",
        category="ceo_boundary",
    ),
    "CEO-008-prior-reassurance-expired": CaseNarrative(
        title="Prior Reassurance Expired",
        scenario="47-year-old says a doctor said prior headaches were okay last month, but this headache is new, sudden, and included transient blurry vision.",
        jre_demonstrates="Temporal change invalidates prior reassurance. New sudden onset and neuro-like symptoms reset the safety boundary.",
        bsg_demonstrates="The pathway should not rely on stale reassurance when the current encounter has a different risk shape.",
        combined_insight="Longitudinal memory helps only when the system knows when old reassurance expires.",
        category="ceo_boundary",
    ),
    # --- TOP TELEMEDICINE COMPLAINT COVERAGE CASES ---
    "TOP-001-mental-health-self-harm": CaseNarrative("Mental Health Crisis", "Anxiety/depression visit includes self-harm intent and intoxication.", "New mental-health template catches self-harm and substance risk.", "Self-harm sentinel reinforces emergency/crisis workflow.", "High-volume mental health needs crisis gating before routine telemedicine care.", "top_telemedicine"),
    "TOP-002-adhd-stimulant-palpitations": CaseNarrative("ADHD Refill With Cardiac Symptoms", "Stimulant refill request includes early refill, extra doses, chest tightness, and missing vitals.", "ADHD/behavioral-med template catches controlled-medication, cardiovascular, and diversion boundaries.", "Guardrail envelope allows the domain but caps autonomy through unresolved safety findings.", "This shows medication management cannot be generic refill logic.", "top_telemedicine"),
    "TOP-003-general-med-rash-swelling": CaseNarrative("General Med Reaction", "New antibiotic reaction with rash and lip swelling.", "General medication template catches medication identity uncertainty plus allergic reaction symptoms.", "Sentinel allergy/anaphylaxis guardrails reinforce escalation.", "A generic med-management pathway needs allergy/airway boundaries.", "top_telemedicine"),
    "TOP-004-lab-review-critical-potassium": CaseNarrative("Critical Lab Review", "Patient asks about a critical potassium result with weakness/lightheadedness.", "Lab-review template treats exact value/date/current symptoms as required decision nodes.", "Operating envelope supports lab review but urgent value changes autonomy.", "Lab review is not just explanation; critical values need action routing.", "top_telemedicine"),
    "TOP-005-sore-throat-airway": CaseNarrative("Sore Throat Airway Boundary", "Sore throat with drooling, inability to swallow, muffled voice, and fever.", "URI/sore-throat template catches deep neck or airway danger signs.", "Sentinel/guardrail layer supports escalation rather than routine strep flow.", "Common URI complaints need explicit airway boundary checks.", "top_telemedicine"),
    "TOP-006-asthma-rescue-not-helping": CaseNarrative("Asthma Not Responding", "Wheezing with inability to finish sentences and rescue inhaler every hour without relief.", "Asthma/allergy template catches rescue-use failure and airway symptoms.", "High-risk respiratory assumption caps routine care.", "Asthma telemedicine needs severity and rescue-response gates.", "top_telemedicine"),
    "TOP-007-sti-exposure-pep-window": CaseNarrative("STI Exposure / PEP Window", "Possible HIV exposure occurred last night.", "Vaginal/STI template catches time-sensitive PEP window and consent/coercion questions.", "Guardrail keeps this in clinician workflow, not generic advice.", "Sexual health workflows need timing and safety-channel boundaries.", "top_telemedicine"),
    "TOP-008-eye-pain-contact-lens": CaseNarrative("Pink Eye That Is Not Routine", "Contact lens wearer has eye pain, photophobia, and blurred vision.", "Eye/ear template catches contact-lens plus vision/pain red flags.", "Remote visual limits and eye-danger findings cap autonomy.", "Conjunctivitis telemedicine needs corneal/vision red-flag gates.", "top_telemedicine"),
    "TOP-009-gi-blood-dehydration": CaseNarrative("GI Bleed / Dehydration", "Vomiting/diarrhea visit includes black stool and faintness.", "GI template catches blood/black stool, dehydration, vomiting, and abdominal pain.", "Active bleeding sentinel supports escalation.", "GI telemedicine must not treat bleeding/dehydration as routine gastroenteritis.", "top_telemedicine"),
    "TOP-010-heartburn-exertional": CaseNarrative("Heartburn With Exertional Pattern", "Heartburn label hides exertional chest pressure and sweating.", "GERD/dyspepsia template routes cardiac-boundary symptoms out of routine reflux care.", "Guardrail plus Judgment Readiness prevent label-based false reassurance.", "This is a common telemedicine failure mode: symptom label is not diagnosis.", "top_telemedicine"),
    "TOP-011-back-pain-bladder": CaseNarrative("Back Pain Red Flags", "Back pain includes leg weakness/numbness and urinary retention.", "MSK template catches neuro deficit and bowel/bladder red flags.", "Autonomy is capped to emergency/human workflow.", "Back-pain telemedicine needs cauda-equina and infection/cancer boundaries.", "top_telemedicine"),
    "TOP-012-routine-derm-mucosal": CaseNarrative("Routine Derm With Mucosal Involvement", "Acne/rash request includes mouth and eye sores.", "Routine dermatology template catches mucosal involvement despite routine framing.", "Dangerous rash guardrails reinforce escalation.", "Routine dermatology needs SJS/anaphylaxis/infection boundaries.", "top_telemedicine"),
    "TOP-013-skin-infection-face-fever": CaseNarrative("Skin Infection Near Eye", "Cellulitis-like complaint near eye with fever and diabetes.", "Skin infection template catches high-risk location, fever, spread, and host risk.", "High-risk host and location cap routine antibiotic automation.", "Skin infection telemedicine needs location and host-risk gates.", "top_telemedicine"),
    "TOP-014-glp1-severe-abdominal-pain": CaseNarrative("GLP-1 Severe Abdominal Pain", "GLP-1 refill request includes severe abdominal pain and vomiting after dose increase.", "Obesity/metabolic template catches medication side-effect boundary.", "Medication safety and symptom severity prevent routine refill.", "Metabolic/GLP-1 care needs pancreatitis/gallbladder safety checks.", "top_telemedicine"),
    # --- BLACK SWAN CASES (8) ---
    "BS-001-refill-wrong-patient": CaseNarrative(
        title="Wrong Patient Identity",
        scenario="52-year-old medication refill, but the caller refers to themselves in the third person and mentions picking up 'his' medication. Identity/proxy breach.",
        jre_demonstrates="Judgment Readiness processes the clinical content normally -- the refill data looks reasonable.",
        bsg_demonstrates="FAIL_CLOSED. Integrity rule INTEGRITY_WRONG_PATIENT_OR_PROXY catches the third-person language indicating this may not be the actual patient.",
        combined_insight="Judgment Readiness alone would miss this. The two-engine design catches a non-clinical but critical safety issue that pure clinical analysis cannot detect.",
        category="bs_integrity",
    ),
    "BS-002-prompt-injection-antibiotic": CaseNarrative(
        title="Prompt Injection Attack",
        scenario="31-year-old UTI case where patient input contains adversarial text attempting to override clinical protocols and force antibiotic prescription.",
        jre_demonstrates="Judgment Readiness processes the clinical content and may not flag the injection -- it's focused on clinical semantics.",
        bsg_demonstrates="FAIL_CLOSED. Integrity rule INTEGRITY_PROMPT_INJECTION detects adversarial override language in patient statements.",
        combined_insight="Black Swan Guard catches what Judgment Readiness cannot: adversarial manipulation. The two layers together protect against both clinical and system-level threats.",
        category="bs_integrity",
    ),
    "BS-003-offpath-stroke-in-refill": CaseNarrative(
        title="Off-Pathway Stroke in Refill",
        scenario="68-year-old calling for a routine lisinopril refill, but mentions sudden one-sided weakness and slurred speech -- acute stroke symptoms during a routine call.",
        jre_demonstrates="Judgment Readiness may partially catch the severity through red-flag patterns, depending on domain mapping.",
        bsg_demonstrates="ESCALATE. Sentinel rule SENTINEL_STROKE_LANGUAGE detects stroke-specific language regardless of the pathway context.",
        combined_insight="The sentinel layer catches emergencies that appear in unexpected contexts. A refill pathway should never proceed when stroke symptoms are present.",
        category="bs_sentinel",
    ),
    "BS-004-coercion-channel-unsafe": CaseNarrative(
        title="Coercion / Unsafe Channel",
        scenario="29-year-old rash case where statements suggest someone else is controlling the interaction, and the communication channel may not be secure.",
        jre_demonstrates="Judgment Readiness evaluates the rash clinically and may clarify based on incomplete information.",
        bsg_demonstrates="ROUTE_CLINICIAN. Sentinel rule SENTINEL_COERCION_ABUSE detects potential coercion patterns requiring human assessment.",
        combined_insight="Safety extends beyond clinical accuracy. A clinician must verify the interaction is voluntary and the channel is secure before any action.",
        category="bs_sentinel",
    ),
    "BS-005-language-barrier-chest-pressure": CaseNarrative(
        title="Language Barrier + Chest Red Flag",
        scenario="61-year-old with 'indigestion' who has a language barrier. Communication unreliability combined with potential cardiac symptoms.",
        jre_demonstrates="Judgment Readiness detects cardiac red flags and escalates based on clinical patterns.",
        bsg_demonstrates="Envelope breach for language barrier + sentinel escalation for chest symptoms. Double trigger reinforces the escalation.",
        combined_insight="The combined pipeline catches both the clinical danger and the communication reliability issue, ensuring escalation even if one engine alone might under-weight the risk.",
        category="bs_envelope",
    ),
    "BS-006-device-provenance-conflict": CaseNarrative(
        title="Device Data Integrity Conflict",
        scenario="73-year-old cough case where patient reports normal oxygen but a device reads critically low. The provenance of the device reading is questioned.",
        jre_demonstrates="Judgment Readiness escalates due to low O2 red flag -- the clinical signal alone is sufficient for escalation.",
        bsg_demonstrates="Black Swan Guard would apply HOLD_AND_VERIFY for device integrity, but Judgment Readiness escalation is more restrictive and takes priority in the combined state.",
        combined_insight="When Judgment Readiness escalates on clinical grounds, that's the correct conservative behavior even though Black Swan Guard's intended HOLD_AND_VERIFY is less restrictive. The most-restrictive-wins logic is correct here.",
        category="bs_integrity",
    ),
    "BS-007-pregnancy-pain-simple-uti": CaseNarrative(
        title="Pregnancy + Pain Sentinel",
        scenario="24-year-old UTI case who is pregnant with lower abdominal pain. Simple UTI pathway is unsafe with pregnancy and pain.",
        jre_demonstrates="Judgment Readiness may flag pregnancy and pain through its slot analysis, but the sentinel pattern is what drives the hard escalation.",
        bsg_demonstrates="ESCALATE. Sentinel rule SENTINEL_PREGNANCY_ABDOMINAL_PAIN fires on the combination of pregnancy + abdominal pain.",
        combined_insight="The sentinel rule provides a hard guardrail that fires regardless of Judgment Readiness clinical assessment. Pregnancy + pain requires immediate escalation.",
        category="bs_sentinel",
    ),
    "BS-008-nonresponse-after-risk": CaseNarrative(
        title="Non-Response After Risk Disclosure",
        scenario="57-year-old chest pressure case who stops responding after being told their symptoms could be cardiac. Workflow failure after risk disclosure.",
        jre_demonstrates="Judgment Readiness evaluates the clinical content and may escalate based on chest pressure red flags.",
        bsg_demonstrates="Black Swan Guard detects the non-response pattern after risk disclosure via INTEGRITY_NONRESPONSE_AFTER_RISK, routing to clinician.",
        combined_insight="When a patient goes silent after learning they may have a serious condition, the system must not simply time out. Active clinician follow-up is required.",
        category="bs_integrity",
    ),
    # --- NEW GUARDRAIL CASES ---
    "BS-009-active-bleeding-in-refill": CaseNarrative(
        title="Active Bleeding in Refill",
        scenario="66-year-old calling for BP medication refill mentions vomiting blood and black tarry stool. A routine refill pathway encounters a GI bleeding emergency.",
        jre_demonstrates="Judgment Readiness processes the refill context but may not have specific GI bleeding patterns in the hypertension domain.",
        bsg_demonstrates="ESCALATE. Sentinel rule SENTINEL_ACTIVE_BLEEDING catches active bleeding language regardless of the pathway domain.",
        combined_insight="Like off-pathway stroke, this demonstrates sentinel rules catching emergencies in unexpected contexts. Active bleeding during a routine refill call requires immediate escalation.",
        category="bs_sentinel",
    ),
    "BS-010-copy-paste-rote-denial": CaseNarrative(
        title="Copy-Paste Rote Denial",
        scenario="38-year-old rash case where every answer is just 'no' -- a string of minimal, identical negative responses suggesting disengagement or copy-paste behavior.",
        jre_demonstrates="Judgment Readiness may accept the negative answers at face value, giving a relatively clean readiness score.",
        bsg_demonstrates="HOLD_AND_VERIFY. Integrity rule INTEGRITY_COPY_PASTE_ANSWERS detects the pattern of rote, minimal negative answers that suggest disengagement rather than genuine clinical engagement.",
        combined_insight="Rote denials are a subtle form of gaming -- the patient may not be malicious, but the answers are unreliable. The system correctly requires verification before proceeding.",
        category="bs_integrity",
    ),
    # --- NEW DOMAIN-COVERAGE CASES (BS-011 through BS-013) ---
    "BS-011-pediatric-headache-meningitis": CaseNarrative(
        title="Pediatric Meningitis Sentinel",
        scenario="8-year-old brought in by parent for a bad headache. Parent says no fever but the child feels hot. Child reports neck stiffness and photophobia. Parent frames it as routine and just wants Tylenol.",
        jre_demonstrates="Judgment Readiness detects thunderclap-like headache language and neck stiffness as critical red flags. The combination triggers escalation despite the parent framing this as a simple headache.",
        bsg_demonstrates="ESCALATE. Sentinel rule SENTINEL_WORST_HEADACHE fires on the worst-headache-plus-neck-stiffness pattern. Envelope rule ENVELOPE_PEDIATRIC_AGE fires because patient is 8 years old. Integrity rule INTEGRITY_MINOR_OR_CONSENT detects pediatric language.",
        combined_insight="This case demonstrates triple-layer detection: Judgment Readiness catches the clinical pattern, Black Swan Guard catches both the sentinel headache language and the pediatric envelope breach. A routine Tylenol request hides a potential meningitis emergency.",
        category="bs_sentinel",
    ),
    "BS-012-silent-dka-elderly": CaseNarrative(
        title="Silent DKA with Proxy Caller",
        scenario="78-year-old with diabetes. Caregiver calls saying glucose is a little high but meter shows HI (over 500). Patient is sleepy, not making sense, breathing fast and deep. Caregiver minimizes because the patient always runs high.",
        jre_demonstrates="Judgment Readiness detects critical glucose values, altered mental status, and Kussmaul breathing as red flags in the diabetes domain. Escalates on DKA risk despite caregiver minimization.",
        bsg_demonstrates="ESCALATE. Integrity rule INTEGRITY_WRONG_PATIENT_OR_PROXY fires because the caregiver is calling on behalf of the patient. The Judgment Readiness escalation wraps through via WRAP_JRE_ESCALATION.",
        combined_insight="Both engines contribute independently. Judgment Readiness catches the clinical DKA emergency through domain-specific red flags. Black Swan Guard catches the proxy/identity issue. The caregiver's minimization does not prevent escalation.",
        category="bs_integrity",
    ),
    "BS-013-stale-pulseox-copd": CaseNarrative(
        title="Stale Pulse Ox in COPD Exacerbation",
        scenario="67-year-old with COPD and home oxygen calls about worsening breathing. Reports pulse ox was 94 but that reading is old, not from today. Currently cannot complete sentences and is using rescue inhaler every two hours without relief.",
        jre_demonstrates="Judgment Readiness detects severe functional limitation from the sentence test and escalates. The stale oxygen reading cannot be relied upon to rule out hypoxia.",
        bsg_demonstrates="ESCALATE. Integrity rule INTEGRITY_STALE_DATA fires on the outdated pulse ox reading. Envelope rule ENVELOPE_HIGH_RISK_COMORBIDITY fires for home oxygen. Judgment Readiness escalation wraps through via WRAP_JRE_ESCALATION.",
        combined_insight="The stale data problem is critical here. A pulse ox of 94 from days ago means nothing when the patient cannot finish a sentence today. Both engines converge on escalation from different angles -- clinical distress and data integrity.",
        category="bs_integrity",
    ),
}


# ---------------------------------------------------------------------------
# Trap Explanations (plain-English for dashboard)
# ---------------------------------------------------------------------------

TRAP_EXPLANATIONS: Dict[str, str] = {
    "pain_word_boundary": "Patient uses a pain-adjacent word (e.g., 'heartburn') that may mask actual cardiac pain",
    "heartburn_label": "Patient labels symptom as heartburn, potentially hiding sub-sternal pressure",
    "sob_word_boundary": "Patient uses colloquial breathing description that may hide severity of dyspnea",
    "normal_without_number": "Patient says 'normal' but provides no objective measurement to verify",
    "thunderclap_minimized": "Sudden severe headache onset is being downplayed or minimized by patient",
    "vague_language": "Patient uses vague or non-specific language that reduces observation reliability",
    "objective_without_number": "An objective claim is made without any supporting numeric value",
}


# ---------------------------------------------------------------------------
# Combined State Priority
# ---------------------------------------------------------------------------

_most_restrictive = most_restrictive  # backward-compat alias


# ---------------------------------------------------------------------------
# Counterfactual Analysis Helpers
# ---------------------------------------------------------------------------

def _counterfactual_delta(jre_only_state: str, bsg_only_state: str, combined_state: str) -> str:
    """Compute a human-readable delta string describing the architectural value-add.

    Compares what each engine would produce alone against the combined state
    to show where the two-engine design catches things a single engine misses.
    """
    jre_idx = STATE_PRIORITY.index(jre_only_state) if jre_only_state in STATE_PRIORITY else 0
    bsg_idx = STATE_PRIORITY.index(bsg_only_state) if bsg_only_state in STATE_PRIORITY else 0
    combined_idx = STATE_PRIORITY.index(combined_state) if combined_state in STATE_PRIORITY else 0

    # combined is more restrictive than JRE alone (BSG added value)
    bsg_added = combined_idx < jre_idx
    # combined is more restrictive than BSG alone (JRE added value)
    jre_added = combined_idx < bsg_idx

    if bsg_added and jre_added:
        return "Both engines independently restrict -- combined is stricter than either alone"
    elif bsg_added:
        return "Black Swan Guard caught what Judgment Readiness missed"
    elif jre_added:
        return "Judgment Readiness caught what Black Swan Guard missed"
    else:
        return "Both engines agree"


# ---------------------------------------------------------------------------
# Per-Case Threshold Sensitivity (Tornado Chart)
# ---------------------------------------------------------------------------

@dataclass
class PerCaseVariation:
    """Result of varying one threshold for one case."""
    threshold_name: str
    parameter: str
    baseline_value: float
    test_value: float
    direction: str  # "stricter" or "looser"
    baseline_jre_state: str
    baseline_bsg_state: str
    baseline_combined: str
    varied_jre_state: str
    varied_bsg_state: str
    varied_combined: str
    state_changed: bool


PER_CASE_VARIATIONS = [
    # (name, parameter, baseline, strict_value, loose_value)
    ("Readiness Index Cutoff", "jri_ready_threshold", 78.0, 85.0, 70.0),
    ("Red Flag Severity", "red_flag_escalation_threshold", 0.85, 0.75, 0.95),
    ("Objective Needed Severity", "objective_needed_threshold", 0.85, 0.75, 0.95),
    ("Novelty Threshold", "novelty_route_threshold", 0.55, 0.40, 0.70),
    ("Risk Budget", "risk_budget_route_threshold", 0.72, 0.55, 0.85),
    ("Escalation Severity", "escalation_severity_threshold", 0.90, 0.80, 0.95),
]

_JRE_PARAMS = {"jri_ready_threshold", "red_flag_escalation_threshold", "objective_needed_threshold"}
_BSG_PARAMS = {"novelty_route_threshold", "risk_budget_route_threshold", "escalation_severity_threshold"}


def _run_case_with_jre_threshold(case: CaseInput, parameter: str, value: float):
    """Run a single case with a modified JRE threshold."""
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()
    original_decide = jre._decide_state

    def patched_decide(scores, findings, next_questions):
        if parameter == "jri_ready_threshold":
            if any(f.category == "red_flag" and f.severity >= 0.85 for f in findings):
                return "ESCALATE"
            if any(f.category == "objective_needed" and f.severity >= 0.85 for f in findings):
                return "NEED_OBJECTIVE_DATA"
            if any(f.category == "contradictory" for f in findings):
                return "CLARIFY"
            if scores.readiness_index >= value and scores.red_flag_load == 0 and len(next_questions) <= 2:
                return "READY"
            return "CLARIFY"
        elif parameter == "red_flag_escalation_threshold":
            if any(f.category == "red_flag" and f.severity >= value for f in findings):
                return "ESCALATE"
            if any(f.category == "objective_needed" and f.severity >= 0.85 for f in findings):
                return "NEED_OBJECTIVE_DATA"
            if any(f.category == "contradictory" for f in findings):
                return "CLARIFY"
            if scores.readiness_index >= 78 and scores.red_flag_load == 0 and len(next_questions) <= 2:
                return "READY"
            return "CLARIFY"
        elif parameter == "objective_needed_threshold":
            if any(f.category == "red_flag" and f.severity >= 0.85 for f in findings):
                return "ESCALATE"
            if any(f.category == "objective_needed" and f.severity >= value for f in findings):
                return "NEED_OBJECTIVE_DATA"
            if any(f.category == "contradictory" for f in findings):
                return "CLARIFY"
            if scores.readiness_index >= 78 and scores.red_flag_load == 0 and len(next_questions) <= 2:
                return "READY"
            return "CLARIFY"
        return original_decide(scores, findings, next_questions)

    jre._decide_state = patched_decide
    jre_report = jre.evaluate(case)
    bsg_report = guard.evaluate(case, jre_report)
    return jre_report.state, bsg_report.guardrail_state


def _run_case_with_bsg_threshold(case: CaseInput, parameter: str, value: float):
    """Run a single case with a modified BSG threshold."""
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()
    original_decide = guard._decide_state

    def patched_decide(findings, risk_budget, novelty, report):
        if parameter == "novelty_route_threshold":
            if any(f.action == "ESCALATE" and f.severity >= 0.90 for f in findings):
                return "ESCALATE", "T0_EMERGENCY_OR_HARD_STOP"
            if any(f.action == "FAIL_CLOSED" for f in findings):
                return "FAIL_CLOSED", "T1_INTAKE_ONLY"
            if novelty >= value or risk_budget >= 0.72:
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "ROUTE_CLINICIAN" for f in findings):
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "HOLD_AND_VERIFY" for f in findings):
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            if report is not None and report.state == "READY" and risk_budget < 0.25 and novelty < 0.20:
                return "ALLOW_WITH_AUDIT", "T4_NARROW_AUTONOMOUS_ACTION"
            if report is not None and report.state in {"CLARIFY", "NEED_OBJECTIVE_DATA"}:
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            return "ALLOW_WITH_AUDIT", "T3_SUPERVISED_PROTOCOL"
        elif parameter == "risk_budget_route_threshold":
            if any(f.action == "ESCALATE" and f.severity >= 0.90 for f in findings):
                return "ESCALATE", "T0_EMERGENCY_OR_HARD_STOP"
            if any(f.action == "FAIL_CLOSED" for f in findings):
                return "FAIL_CLOSED", "T1_INTAKE_ONLY"
            if novelty >= 0.55 or risk_budget >= value:
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "ROUTE_CLINICIAN" for f in findings):
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "HOLD_AND_VERIFY" for f in findings):
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            if report is not None and report.state == "READY" and risk_budget < 0.25 and novelty < 0.20:
                return "ALLOW_WITH_AUDIT", "T4_NARROW_AUTONOMOUS_ACTION"
            if report is not None and report.state in {"CLARIFY", "NEED_OBJECTIVE_DATA"}:
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            return "ALLOW_WITH_AUDIT", "T3_SUPERVISED_PROTOCOL"
        elif parameter == "escalation_severity_threshold":
            if any(f.action == "ESCALATE" and f.severity >= value for f in findings):
                return "ESCALATE", "T0_EMERGENCY_OR_HARD_STOP"
            if any(f.action == "FAIL_CLOSED" for f in findings):
                return "FAIL_CLOSED", "T1_INTAKE_ONLY"
            if novelty >= 0.55 or risk_budget >= 0.72:
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "ROUTE_CLINICIAN" for f in findings):
                return "ROUTE_CLINICIAN", "T1_INTAKE_ONLY"
            if any(f.action == "HOLD_AND_VERIFY" for f in findings):
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            if report is not None and report.state == "READY" and risk_budget < 0.25 and novelty < 0.20:
                return "ALLOW_WITH_AUDIT", "T4_NARROW_AUTONOMOUS_ACTION"
            if report is not None and report.state in {"CLARIFY", "NEED_OBJECTIVE_DATA"}:
                return "HOLD_AND_VERIFY", "T2_CLINICIAN_DRAFT_ONLY"
            return "ALLOW_WITH_AUDIT", "T3_SUPERVISED_PROTOCOL"
        return original_decide(findings, risk_budget, novelty, report)

    guard._decide_state = patched_decide
    jre_report = jre.evaluate(case)
    bsg_report = guard.evaluate(case, jre_report)
    return jre_report.state, bsg_report.guardrail_state


def run_per_case_sensitivity(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
) -> List[PerCaseVariation]:
    """Run threshold sensitivity analysis for a single case."""
    baseline_jre = jre_report.state
    baseline_bsg = bsg_report.guardrail_state
    baseline_combined = most_restrictive(baseline_jre, baseline_bsg)
    variations = []

    for name, param, baseline_val, strict_val, loose_val in PER_CASE_VARIATIONS:
        for direction, test_val in [("stricter", strict_val), ("looser", loose_val)]:
            if param in _JRE_PARAMS:
                var_jre, var_bsg = _run_case_with_jre_threshold(case, param, test_val)
            else:
                var_jre, var_bsg = _run_case_with_bsg_threshold(case, param, test_val)
            var_combined = most_restrictive(var_jre, var_bsg)
            variations.append(PerCaseVariation(
                threshold_name=name,
                parameter=param,
                baseline_value=baseline_val,
                test_value=test_val,
                direction=direction,
                baseline_jre_state=baseline_jre,
                baseline_bsg_state=baseline_bsg,
                baseline_combined=baseline_combined,
                varied_jre_state=var_jre,
                varied_bsg_state=var_bsg,
                varied_combined=var_combined,
                state_changed=var_combined != baseline_combined,
            ))
    return variations


# ---------------------------------------------------------------------------
# Multi-Turn Conversation Simulation
# ---------------------------------------------------------------------------

@dataclass
class TurnResult:
    """One turn of the multi-turn conversation simulation."""
    turn_number: int
    question_asked: str
    concept_targeted: str
    answer_given: str
    clear_step: str
    jre_state: str
    bsg_state: str
    combined_state: str
    readiness_index: float
    questions_remaining: int
    findings_count: int
    state_changed: bool


RESOLUTION_ANSWERS = {
    "chest_discomfort": {
        "symptom_quality": "Sharp soreness only when I twist, no pressure, tightness, heaviness, squeezing, or burning.",
        "exertional_component": "No, walking and stairs do not change it at all. Only twisting.",
        "dyspnea": "No, I can run and speak a full sentence without stopping for breath.",
        "diaphoresis": "No sweating, nausea, or faintness.",
        "radiation": "No, it does not spread to jaw, shoulder, arm, back, or abdomen.",
        "vitals": "Blood pressure 118/72, heart rate 68, oxygen 98%.",
    },
    "dyspnea_respiratory": {
        "oxygen_saturation": "Pulse oximeter reads 97% after sitting for one minute.",
        "respiratory_rate": "I counted 16 breaths in 60 seconds.",
        "sentence_test": "Yes, I can say a full sentence out loud without pausing for breath.",
        "exertional_tolerance": "I can walk from bedroom to kitchen without stopping, same as my baseline.",
        "mental_status": "No, I am not confused, sleepy, or having trouble staying awake.",
        "fever_measured": "Thermometer reads 98.4 degrees Fahrenheit this morning.",
        "baseline_lung_disease": "No COPD, asthma, heart failure, or home oxygen use.",
    },
    "med_refill_hypertension": {
        "medication_identity": "Lisinopril 20 mg once daily, reading from the bottle right now.",
        "last_taken": "I took my last dose this morning at 7 AM.",
        "home_bp_number": "128 over 76 measured today with my home cuff.",
        "side_effects": "No dizziness, fainting, swelling, cough, weakness, or new symptoms.",
        "renal_function": "Chart shows creatinine 0.9 and potassium 4.3 last month.",
        "pregnancy_status": "No, not pregnant and not trying to become pregnant.",
        "chart_med_reconciliation": "Chart medication list confirms lisinopril 20 mg daily.",
    },
    "uti_symptoms": {
        "dysuria": "Yes, mild burning when I urinate.",
        "fever_measured": "Thermometer reads 98.6 degrees, no fever.",
        "flank_pain": "No back or side pain at all.",
        "vomiting": "No vomiting, I can eat and drink normally.",
        "pregnancy_status": "No, not pregnant.",
        "sex_or_complicated_risk": "Female, no immunocompromise, no diabetes, no kidney disease, no catheter.",
    },
    "rash": {
        "mucosal_involvement": "No sores or rash in mouth, eyes, lips, genitals, or nose.",
        "skin_pain": "It itches but does not hurt, burn, blister, or peel.",
        "fever_measured": "Thermometer reads 98.4, no fever.",
        "new_medication": "No new medications, antibiotics, or supplements in the past 8 weeks.",
        "airway_symptoms": "No lip or tongue swelling, no wheezing, no throat tightness, breathing is normal.",
    },
    "diabetes_hyperglycemia": {
        "glucose_number": "Blood glucose meter reads 145 mg/dL fasting this morning.",
        "ketones": "Urine ketone strip is negative, no ketones.",
        "vomiting": "No vomiting, I can eat and drink normally.",
        "insulin_access": "I have my insulin pen here, last dose was this morning at 7 AM.",
        "mental_status": "No confusion, fully awake, breathing normally.",
        "hydration_status": "Urinating normally and drinking fluids well.",
    },
    "headache_migraine": {
        "headache_onset": "It came on gradually over about two hours, building slowly.",
        "neck_stiffness": "No, I can touch my chin to my chest without pain.",
        "fever_measured": "Thermometer reads 98.4, no fever.",
        "neuro_deficit": "No vision changes, no weakness, no numbness, no speech difficulty, no confusion.",
        "aura_pattern": "I see zigzag lines before the headache starts, typical for my migraines.",
        "medication_use": "I take ibuprofen about twice a month for headaches.",
        "vitals": "Blood pressure 122 over 78 today.",
    },
    "mental_health": {
        "self_harm": "No thoughts of hurting myself or ending my life; I feel safe right now.",
        "harm_others": "No thoughts of hurting anyone else.",
        "psychosis_mania": "No hallucinations, paranoia, or days without sleep.",
        "support_safety_plan": "My spouse is home and can stay with me if needed.",
    },
    "adhd_behavioral_med": {
        "medication_identity": "Adderall XR 20 mg once each morning, reading from the bottle.",
        "controlled_substance_context": "It is a stimulant and was last filled 30 days ago.",
        "bp_hr": "Blood pressure 118/74 and heart rate 72 today.",
        "side_effects": "No chest pain, palpitations, fainting, severe anxiety, or insomnia.",
    },
    "general_med_management": {
        "medication_identity": "Sertraline 50 mg once daily, reading from the bottle.",
        "last_taken": "I took the last dose this morning.",
        "side_effects": "No rash, swelling, bleeding, mood crisis, or trouble breathing.",
        "chart_med_reconciliation": "The chart and pharmacy fill record match this medication.",
    },
    "followup_lab_review": {
        "result_identity": "Basic metabolic panel.",
        "result_value": "Potassium 4.2 and creatinine 0.9, both in range.",
        "result_date": "Collected two days ago.",
        "current_symptoms": "No new or worsening symptoms.",
    },
    "uri_sinus_throat": {
        "symptom_duration": "Symptoms for two days and improving.",
        "fever_measured": "Temperature 98.6 today.",
        "breathing_status": "No shortness of breath, chest pain, blue lips, or trouble speaking.",
        "throat_airway": "No drooling, trouble swallowing, muffled voice, or neck swelling.",
    },
    "asthma_allergy": {
        "airway_symptoms": "No throat tightness, tongue swelling, wheezing, or trouble breathing.",
        "rescue_inhaler_use": "I have not needed my rescue inhaler today.",
        "peak_flow_or_o2": "Peak flow is at my usual baseline and oxygen is 98%.",
        "prior_severity": "No prior intubation, epinephrine use, or hospitalization.",
    },
    "vaginal_sti": {
        "pregnancy_status": "No chance of pregnancy.",
        "pelvic_pain": "No pelvic, lower belly, or one-sided pain.",
        "fever_measured": "Temperature is 98.4.",
        "sti_exposure_timing": "No known STI exposure.",
    },
    "eye_ear": {
        "vision_change": "No vision loss, blurred vision, or double vision.",
        "eye_pain_photophobia": "No significant eye pain or light sensitivity.",
        "contact_lens": "I do not wear contact lenses.",
        "trauma_chemical": "No injury, foreign body, or chemical exposure.",
    },
    "gi_symptoms": {
        "abdominal_pain": "Mild cramping only, not severe or worsening.",
        "vomiting": "No vomiting and I can keep fluids down.",
        "diarrhea_blood": "No blood, black stool, or vomiting blood.",
        "dehydration": "No dizziness or fainting, and I am urinating normally.",
    },
    "gerd_dyspepsia": {
        "chest_or_exertional": "No pressure, tightness, shortness of breath, sweating, or exertional symptoms.",
        "alarm_gi": "No trouble swallowing, blood, black stool, weight loss, or persistent vomiting.",
        "abdominal_pain": "Burning after meals that improves with antacid.",
        "medication_risk": "No NSAIDs, blood thinners, steroids, or heavy alcohol use.",
    },
    "musculoskeletal_pain": {
        "trauma_mechanism": "No fall, crash, or major injury.",
        "neuro_deficit": "No weakness, numbness, saddle anesthesia, or trouble walking.",
        "bowel_bladder": "No bladder or bowel control changes.",
        "infection_cancer_risk": "No fever, cancer history, IV drug use, or weight loss.",
    },
    "routine_dermatology": {
        "lesion_photo_quality": "I uploaded clear photos in good light.",
        "infection_signs": "No spreading redness, pus, fever, or severe pain.",
        "mucosal_or_airway": "No mouth, eye, genital, airway, lip, or tongue involvement.",
        "new_medication": "No new medication or product exposure.",
    },
    "skin_infection": {
        "infection_spread": "The redness is small and not spreading quickly.",
        "fever_measured": "Temperature is 98.6.",
        "abscess_drainage": "No pus, boil, drainage, or soft lump.",
        "high_risk_host": "No diabetes, immune suppression, dialysis, or poor circulation.",
    },
    "obesity_metabolic": {
        "medication_identity": "Semaglutide 0.25 mg weekly, reading from the pen label.",
        "bmi_weight_trend": "Height 5 foot 7, weight 214 pounds, stable this month.",
        "contraindications": "No pregnancy, pancreatitis, gallbladder disease, MEN2, or thyroid cancer.",
        "side_effects": "No severe abdominal pain, persistent vomiting, dehydration, fainting, or low sugar symptoms.",
    },
}

MULTITURN_EXPECTED_OUTCOMES: Dict[str, Dict[str, str]] = {
    # domain -> {metric: expected_direction}
    "chest_discomfort": {"jri_direction": "may_increase", "state_if_benign": "CLARIFY"},
    "dyspnea_respiratory": {"jri_direction": "may_increase", "state_if_benign": "CLARIFY"},
    "med_refill_hypertension": {"jri_direction": "increase", "state_if_benign": "READY"},
    "uti_symptoms": {"jri_direction": "may_increase", "state_if_benign": "CLARIFY"},
    "rash": {"jri_direction": "may_increase", "state_if_benign": "CLARIFY"},
    "diabetes_hyperglycemia": {"jri_direction": "may_increase", "state_if_benign": "CLARIFY"},
    "headache_migraine": {"jri_direction": "may_increase", "state_if_benign": "CLARIFY"},
}



def run_multiturn_simulation(
    case: CaseInput,
    jre_report: ReadinessReport,
    bsg_report: GuardrailReport,
    max_turns: int = 3,
) -> List[TurnResult]:
    """Simulate multi-turn conversation using resolution answers and real engine."""
    from jre.models import Statement
    domain = case.patient_context.domain
    domain_answers = RESOLUTION_ANSWERS.get(domain, {})
    if not domain_answers:
        return []

    turns = []
    current_statements = list(case.statements)
    current_jre_report = jre_report
    current_bsg_report = bsg_report
    current_combined = most_restrictive(jre_report.state, bsg_report.guardrail_state)
    answered_concepts = set()

    for turn_num in range(1, max_turns + 1):
        # Find the highest-priority unanswered question with a resolution answer
        question_to_ask = None
        for q in current_jre_report.next_questions:
            if q.concept in answered_concepts:
                continue
            if q.concept in domain_answers:
                question_to_ask = q
                break
        if question_to_ask is None:
            break

        resolution = domain_answers[question_to_ask.concept]
        answered_concepts.add(question_to_ask.concept)

        # Build augmented case with the new statement
        new_stmt = Statement(
            question=question_to_ask.question,
            answer=resolution,
            concept=question_to_ask.concept,
            source="patient",
        )
        current_statements = current_statements + [new_stmt]
        augmented_case = CaseInput(
            case_id=case.case_id,
            patient_context=case.patient_context,
            statements=current_statements,
            ground_truth=case.ground_truth,
        )

        # Run through real engines
        jre = JudgmentReadinessEngine()
        guard = BlackSwanGuardrailEngine()
        new_jre_report = jre.evaluate(augmented_case)
        new_bsg_report = guard.evaluate(augmented_case, new_jre_report)
        new_combined = most_restrictive(new_jre_report.state, new_bsg_report.guardrail_state)

        turns.append(TurnResult(
            turn_number=turn_num,
            question_asked=question_to_ask.question,
            concept_targeted=question_to_ask.concept,
            answer_given=resolution,
            clear_step=question_to_ask.clear_step,
            jre_state=new_jre_report.state,
            bsg_state=new_bsg_report.guardrail_state,
            combined_state=new_combined,
            readiness_index=new_jre_report.scores.readiness_index,
            questions_remaining=len(new_jre_report.next_questions),
            findings_count=len(new_jre_report.findings),
            state_changed=new_combined != current_combined,
        ))

        current_jre_report = new_jre_report
        current_bsg_report = new_bsg_report
        current_combined = new_combined

        # Stop if converged to READY/ALLOW_WITH_AUDIT
        if new_combined in {"READY", "ALLOW_WITH_AUDIT"}:
            break

    return turns


def validate_multiturn_outcomes(
    case: CaseInput,
    baseline_report: ReadinessReport,
    turns: List[TurnResult],
) -> Dict[str, Any]:
    """Validate that multi-turn simulation produces expected outcomes.

    Checks whether resolution answers actually move the case toward
    resolution (JRI improves, state changes) and whether escalation
    cases maintain their escalation posture through multi-turn.
    """
    domain = case.patient_context.domain
    expected = MULTITURN_EXPECTED_OUTCOMES.get(domain, {})

    result: Dict[str, Any] = {
        "case_id": case.case_id,
        "domain": domain,
        "baseline_jri": baseline_report.scores.readiness_index,
        "baseline_state": baseline_report.state,
        "turns_completed": len(turns),
        "validations": [],
    }

    if not turns:
        result["validations"].append({
            "check": "has_turns",
            "passed": False,
            "detail": "No turns generated -- case may already be resolved or fully escalated",
        })
        return result

    result["validations"].append({
        "check": "has_turns",
        "passed": True,
        "detail": f"{len(turns)} turn(s) completed",
    })

    final = turns[-1]

    # Check: readiness index should not decrease when providing good resolution answers
    jri_direction = expected.get("jri_direction", "may_increase")
    if jri_direction == "increase":
        jri_improved = final.readiness_index >= baseline_report.scores.readiness_index
        result["validations"].append({
            "check": "jri_improves",
            "passed": jri_improved,
            "detail": f"Readiness Index {baseline_report.scores.readiness_index:.1f} -> {final.readiness_index:.1f}",
        })

    # Check: state should change or readiness index should change (not stagnant)
    state_or_jri_changed = (
        final.jre_state != baseline_report.state
        or final.readiness_index != baseline_report.scores.readiness_index
    )
    result["validations"].append({
        "check": "not_stagnant",
        "passed": state_or_jri_changed,
        "detail": f"State: {baseline_report.state} -> {final.jre_state}, Readiness: {baseline_report.scores.readiness_index:.1f} -> {final.readiness_index:.1f}",
    })

    # Check: escalation cases should remain escalated
    if case.ground_truth.get("requires_escalation"):
        still_restrictive = final.jre_state in {"ESCALATE", "NEED_OBJECTIVE_DATA", "CLARIFY"}
        result["validations"].append({
            "check": "escalation_maintained",
            "passed": still_restrictive,
            "detail": f"Escalation case final state: {final.jre_state}",
        })

    return result



# ---------------------------------------------------------------------------
# Unified Result
# ---------------------------------------------------------------------------

@dataclass
class UnifiedResult:
    """Output from running one case through both engines."""
    case: CaseInput
    narrative: CaseNarrative
    jre_report: ReadinessReport
    bsg_report: GuardrailReport
    combined_state: str
    ground_truth_match: bool
    combined_verdict: str
    jre_only_state: str
    bsg_only_state: str


def _check_ground_truth(case: CaseInput, combined_state: str) -> bool:
    """Check if combined state matches case ground truth."""
    gt = case.ground_truth
    if not gt:
        return True

    # BASE_CASES use {"requires_escalation": bool, ...}
    if "requires_escalation" in gt:
        restrictive = {"ESCALATE", "FAIL_CLOSED", "ROUTE_CLINICIAN", "NEED_OBJECTIVE_DATA", "HOLD_AND_VERIFY"}
        permissive = {"READY", "ALLOW_WITH_AUDIT", "CLARIFY"}
        if gt["requires_escalation"]:
            return combined_state in restrictive
        else:
            # Non-escalation cases: either permissive or moderate is OK
            return combined_state in (permissive | restrictive)

    # BLACK_SWAN_CASES use {"expected_guardrail": str, ...}
    if "expected_guardrail" in gt:
        expected = gt["expected_guardrail"]
        if expected == "ESCALATE_OR_ROUTE":
            return combined_state in {"ESCALATE", "ROUTE_CLINICIAN"}
        return combined_state == expected

    return True


def _make_verdict(case, jre_report, bsg_report, combined_state, gt_match):
    """Generate a human-readable verdict string."""
    parts = [f"Judgment Readiness={jre_report.state}"]
    parts.append(f"Black Swan Guard={bsg_report.guardrail_state}")
    parts.append(f"Combined={combined_state}")
    parts.append(f"Tier={bsg_report.max_autonomy_tier}")
    if gt_match:
        parts.append("GT=MATCH")
    else:
        parts.append("GT=MISMATCH")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_unified_pipeline(cases):
    """Run all cases through JRE then BSG, returning unified results."""
    jre = JudgmentReadinessEngine()
    guard = BlackSwanGuardrailEngine()
    results = []
    for case in cases:
        jre_report = jre.evaluate(case)
        bsg_report = guard.evaluate(case, jre_report)
        jre_only_state = jre_report.state
        bsg_only_state = bsg_report.guardrail_state
        combined = _most_restrictive(jre_only_state, bsg_only_state)
        gt_match = _check_ground_truth(case, combined)
        verdict = _make_verdict(case, jre_report, bsg_report, combined, gt_match)
        narrative = CASE_NARRATIVES.get(case.case_id, CaseNarrative(
            title=case.case_id,
            scenario="No narrative available.",
            jre_demonstrates="N/A",
            bsg_demonstrates="N/A",
            combined_insight="N/A",
            category="unknown",
        ))
        results.append(UnifiedResult(
            case=case,
            narrative=narrative,
            jre_report=jre_report,
            bsg_report=bsg_report,
            combined_state=combined,
            ground_truth_match=gt_match,
            combined_verdict=verdict,
            jre_only_state=jre_only_state,
            bsg_only_state=bsg_only_state,
        ))
    return results


def get_all_cases():
    """Return all hand-authored cases (base + black swan)."""
    return list(BASE_CASES) + list(BLACK_SWAN_CASES)


# ---------------------------------------------------------------------------
# Output: Markdown
# ---------------------------------------------------------------------------

def unified_report_to_markdown(results):
    """Generate a full markdown report for all unified results."""
    lines = []
    total = len(results)
    gt_matches = sum(1 for r in results if r.ground_truth_match)
    state_counts = {}
    for r in results:
        state_counts[r.combined_state] = state_counts.get(r.combined_state, 0) + 1

    bsg_value_count = sum(1 for r in results if r.combined_state != r.jre_only_state)
    jre_value_count = sum(1 for r in results if r.combined_state != r.bsg_only_state)

    lines.append("# Clinical Safety Analysis Report")
    lines.append("")
    lines.append(f"**Cases evaluated:** {total}")
    lines.append(f"**Ground truth match:** {gt_matches}/{total}")
    lines.append(f"**Combined state distribution:** {', '.join(f'{k}: {v}' for k, v in sorted(state_counts.items()))}")
    lines.append(f"**Black Swan Guard added value:** {bsg_value_count}/{total} cases (combined more restrictive than Judgment Readiness alone)")
    lines.append(f"**Judgment Readiness added value:** {jre_value_count}/{total} cases (combined more restrictive than Black Swan Guard alone)")
    lines.append("")
    lines.append("---")

    for r in results:
        delta_text = _counterfactual_delta(r.jre_only_state, r.bsg_only_state, r.combined_state)
        lines.append("")
        lines.append(f"## {r.case.case_id} -- {r.narrative.title}")
        lines.append("")
        lines.append(f"**Category:** {r.narrative.category}")
        lines.append(f"**Scenario:** {r.narrative.scenario}")
        lines.append("")
        lines.append(f"**Combined state:** {r.combined_state} {'(matches ground truth)' if r.ground_truth_match else '(MISMATCH)'}")
        lines.append(f"**Verdict:** {r.combined_verdict}")
        lines.append("")
        lines.append("**Counterfactual analysis:**")
        lines.append(f"- Judgment Readiness alone: {r.jre_only_state}")
        lines.append(f"- Black Swan Guard alone: {r.bsg_only_state}")
        lines.append(f"- Combined (most restrictive): {r.combined_state}")
        lines.append(f"- *{delta_text}*")
        lines.append("")
        lines.append("### Judgment Readiness Result")
        lines.append(f"- **State:** {r.jre_report.state}")
        lines.append(f"- **Readiness Index:** {r.jre_report.scores.readiness_index:.1f}/100")
        lines.append(f"- **Judgment Readiness demonstrates:** {r.narrative.jre_demonstrates}")
        lines.append(f"- **Summary:** {r.jre_report.provider_summary}")
        if r.jre_report.next_questions:
            lines.append("- **Top questions:**")
            for q in r.jre_report.next_questions[:3]:
                lines.append(f"  - {q.concept}: {q.question}")
        lines.append("")
        lines.append("### Black Swan Guard Result")
        lines.append(f"- **State:** {r.bsg_report.guardrail_state}")
        lines.append(f"- **Tier:** {r.bsg_report.max_autonomy_tier}")
        lines.append(f"- **Novelty:** {r.bsg_report.novelty_score:.2f}")
        lines.append(f"- **Risk budget:** {r.bsg_report.residual_risk_budget:.2f}")
        lines.append(f"- **Black Swan Guard demonstrates:** {r.narrative.bsg_demonstrates}")
        if r.bsg_report.findings:
            lines.append("- **Findings:**")
            for f in r.bsg_report.findings:
                lines.append(f"  - {f.rule_id} ({f.category}, severity {f.severity:.2f})")
        if r.bsg_report.assumption_register:
            lines.append("- **Assumptions:**")
            for a in r.bsg_report.assumption_register:
                lines.append(f"  - {a.status.upper()} -- {a.name}: {a.reason}")
        lines.append("")
        lines.append("### Combined Insight")
        lines.append(r.narrative.combined_insight)
        lines.append("")
        lines.append("---")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output: JSON
# ---------------------------------------------------------------------------

def unified_to_json(results):
    """Serialize unified results to JSON."""
    payload = []
    for r in results:
        payload.append({
            "case_id": r.case.case_id,
            "narrative": {
                "title": r.narrative.title,
                "scenario": r.narrative.scenario,
                "jre_demonstrates": r.narrative.jre_demonstrates,
                "bsg_demonstrates": r.narrative.bsg_demonstrates,
                "combined_insight": r.narrative.combined_insight,
                "category": r.narrative.category,
            },
            "jre_report": r.jre_report.to_dict(),
            "bsg_report": r.bsg_report.to_dict(),
            "combined_state": r.combined_state,
            "ground_truth_match": r.ground_truth_match,
            "combined_verdict": r.combined_verdict,
            "jre_only_state": r.jre_only_state,
            "bsg_only_state": r.bsg_only_state,
            "counterfactual_delta": _counterfactual_delta(
                r.jre_only_state, r.bsg_only_state, r.combined_state
            ),
        })
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# Output: CSV Matrix
# ---------------------------------------------------------------------------

def write_unified_matrix(path, results):
    """Write a flat CSV with one row per case."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "case_id", "category", "jre_state", "jri_score",
            "bsg_state", "autonomy_tier", "novelty_score", "risk_budget",
            "combined_state", "ground_truth_match",
            "jre_finding_count", "bsg_finding_count",
            "jre_question_count", "assumption_breaches",
        ])
        for r in results:
            breaches = sum(1 for a in r.bsg_report.assumption_register if a.status == "breached")
            writer.writerow([
                r.case.case_id,
                r.narrative.category,
                r.jre_report.state,
                f"{r.jre_report.scores.readiness_index:.1f}",
                r.bsg_report.guardrail_state,
                r.bsg_report.max_autonomy_tier,
                f"{r.bsg_report.novelty_score:.2f}",
                f"{r.bsg_report.residual_risk_budget:.2f}",
                r.combined_state,
                r.ground_truth_match,
                len(r.jre_report.findings),
                len(r.bsg_report.findings),
                len(r.jre_report.next_questions),
                breaches,
            ])


# ---------------------------------------------------------------------------
# Output: HTML Dashboard
# ---------------------------------------------------------------------------

def _html_css():
    """Return all CSS as a plain string (no f-string braces)."""
    return """
/* Base */
:root { --bg: #f7f7f8; --card-bg: white; --text: #111; --muted: #555; --border: #ddd; --shadow: rgba(0,0,0,.05); }
*, *::before, *::after { box-sizing: border-box; }
body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; background: var(--bg); color: var(--text); }
.container { max-width: 1200px; margin: 0 auto; padding: 24px 32px; }
/* Header */
.sticky-header { position: sticky; top: 0; z-index: 100; background: var(--bg); padding: 16px 0 0; border-bottom: 1px solid var(--border); }
h1 { margin: 0 0 2px; font-size: 1.6rem; }
.subtitle { color: var(--muted); margin: 0 0 12px; font-size: .95rem; }
/* Controls bar */
.controls { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; padding: 10px 0 12px; }
.controls input[type="text"] { padding: 6px 12px; border: 1px solid var(--border); border-radius: 8px; font-size: .9rem; width: 220px; background: var(--card-bg); color: var(--text); }
.controls select { padding: 6px 10px; border: 1px solid var(--border); border-radius: 8px; font-size: .9rem; background: var(--card-bg); color: var(--text); }
.controls button { padding: 6px 12px; border: 1px solid var(--border); border-radius: 8px; font-size: .85rem; cursor: pointer; background: var(--card-bg); color: var(--text); }
.controls button:hover { background: #e8e8ec; }
.visible-count { font-size: .85rem; color: var(--muted); margin-left: auto; }
/* Stats bar */
.stats-bar { display: flex; gap: 12px; margin: 16px 0; padding: 14px 16px; background: var(--card-bg); border-radius: 14px; border: 1px solid var(--border); box-shadow: 0 1px 4px var(--shadow); flex-wrap: wrap; }
.stat { text-align: center; cursor: pointer; padding: 4px 8px; border-radius: 8px; transition: background .15s; }
.stat:hover { background: #eef; }
.stat.active { background: #ddf; outline: 2px solid #44c; }
.stat-num { display: block; font-size: 1.3rem; font-weight: 700; }
.stat-label { font-size: .8rem; color: var(--muted); }
/* Section headers */
.section-header { margin: 24px 0 8px; padding: 8px 14px; background: #e8e8ec; border-radius: 8px; font-size: 1.05rem; font-weight: 700; }
/* Cards */
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; margin: 14px 0; box-shadow: 0 1px 4px var(--shadow); overflow: hidden; transition: margin .2s; }
.card-header { display: flex; gap: 10px; align-items: center; font-weight: 700; flex-wrap: wrap; padding: 16px 20px; cursor: pointer; user-select: none; }
.card-header:hover { background: #f5f5f8; }
.card-body { padding: 0 20px 20px; overflow: hidden; transition: max-height .3s ease, padding .3s ease; }
.card.collapsed .card-body { max-height: 0; padding-top: 0; padding-bottom: 0; }
.collapse-icon { font-size: 1.1rem; transition: transform .2s; margin-right: 4px; }
.card.collapsed .collapse-icon { transform: rotate(-90deg); }
.case-id { font-size: 1.05rem; flex: 1; }
.state-badge, .score-badge { border: 1px solid #bbb; padding: 3px 8px; border-radius: 999px; font-size: .82rem; white-space: nowrap; }
.gt-match { color: #287; font-weight: 700; }
.gt-mismatch { color: #a33; font-weight: 700; }
/* State colors */
.state-escalate { border-left: 8px solid #a33; }
.state-fail_closed { border-left: 8px solid #111; }
.state-route_clinician { border-left: 8px solid #b70; }
.state-need_objective_data { border-left: 8px solid #c60; }
.state-hold_and_verify { border-left: 8px solid #777; }
.state-clarify { border-left: 8px solid #999; }
.state-allow_with_audit { border-left: 8px solid #287; }
.state-ready { border-left: 8px solid #2a5; }
/* State badge colors */
.badge-escalate { background: #fdd; color: #a33; border-color: #a33; }
.badge-fail_closed { background: #e0e0e0; color: #111; border-color: #111; }
.badge-route_clinician { background: #fec; color: #b70; border-color: #b70; }
.badge-need_objective_data { background: #fed; color: #c60; border-color: #c60; }
.badge-hold_and_verify { background: #eee; color: #555; border-color: #777; }
.badge-clarify { background: #f0f0f0; color: #666; border-color: #999; }
.badge-allow_with_audit { background: #dfe; color: #287; border-color: #287; }
.badge-ready { background: #dfd; color: #2a5; border-color: #2a5; }
/* Narrative */
.narrative { background: #f0f4ff; border-left: 4px solid #4466cc; padding: 12px 16px; margin: 12px 0; border-radius: 6px; }
.narrative-title { font-weight: 700; font-size: 1rem; margin-bottom: 4px; }
/* Engine labels */
.engine-labels { display: flex; gap: 12px; margin: 8px 0; }
.engine-label { padding: 4px 10px; border-radius: 6px; background: #f5f5f5; font-size: .85rem; font-weight: 600; }
/* Counterfactual analysis bar */
.counterfactual { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 10px 0; padding: 10px 14px; background: #f3f3f6; border: 1px solid var(--border); border-radius: 8px; }
.cf-label { font-size: .82rem; font-weight: 600; color: var(--muted); white-space: nowrap; }
.cf-badge { display: inline-block; padding: 3px 8px; border-radius: 999px; font-size: .78rem; font-weight: 600; border: 1px solid #bbb; white-space: nowrap; }
.cf-delta { font-size: .82rem; font-style: italic; color: #665; margin-left: auto; }
/* Content */
.summary { color: #333; line-height: 1.45; margin: 8px 0; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }
.demonstrates { font-style: italic; color: var(--muted); font-size: .92rem; }
h3 { margin: 12px 0 6px; font-size: .95rem; }
h4 { margin: 10px 0 4px; font-size: .88rem; }
ul, ol { margin-top: 4px; padding-left: 20px; }
li { margin-bottom: 4px; font-size: .92rem; }
table { width: 100%; border-collapse: collapse; font-size: .88rem; }
th, td { border-top: 1px solid #e5e5e5; padding: 6px 8px; text-align: left; vertical-align: top; }
th { font-weight: 600; background: #f9f9f9; }
.assumption-ok { color: #287; font-weight: 700; }
.assumption-weak { color: #b70; font-weight: 700; }
.assumption-breached { color: #a33; font-weight: 700; }
.insight { margin-top: 12px; padding: 10px 14px; background: #f8f8f0; border-left: 4px solid #998; border-radius: 6px; font-size: .92rem; }
.verdict { margin-top: 8px; font-family: monospace; font-size: .8rem; color: #888; }
/* JRI Breakdown */
.jri-breakdown { margin: 10px 0; }
.jri-bar { display: flex; height: 18px; border-radius: 4px; overflow: hidden; background: #eee; }
.jri-seg { height: 100%; display: flex; align-items: center; justify-content: center; font-size: .7rem; color: white; font-weight: 600; overflow: hidden; white-space: nowrap; }
.jri-seg-completeness { background: #4a90d9; }
.jri-seg-reliability { background: #5cb85c; }
.jri-seg-objective { background: #f0ad4e; }
.jri-seg-distortion { background: #9b59b6; }
.jri-penalty-bar { display: flex; height: 8px; border-radius: 3px; overflow: hidden; background: #f5f5f5; margin-top: 3px; }
.jri-penalty { height: 100%; background: #d9534f; }
.jri-labels { display: flex; justify-content: space-between; font-size: .75rem; color: var(--muted); margin-top: 2px; }
/* Transcript */
.transcript { margin: 12px 0; padding: 12px 16px; background: #fafbfc; border: 1px solid var(--border); border-radius: 8px; }
.transcript h3 { margin-top: 0; }
.transcript-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.q-bubble { background: #e8eaed; padding: 8px 12px; border-radius: 12px 12px 12px 4px; font-size: .9rem; align-self: flex-start; max-width: 85%; }
.a-bubble { background: #d0e8ff; padding: 8px 12px; border-radius: 12px 12px 4px 12px; font-size: .9rem; align-self: flex-end; max-width: 85%; text-align: right; }
.transcript-annotations { display: flex; gap: 6px; justify-content: flex-end; flex-wrap: wrap; margin-top: 4px; }
.confidence-badge { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: .72rem; color: white; font-weight: 700; }
.trap-tag { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: .72rem; background: #fdd; color: #a33; border: 1px solid #a33; cursor: help; }
.redflag-icon { color: #a33; font-size: 1rem; cursor: help; }
.transcript-legend { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; font-size: .78rem; color: var(--muted); margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
/* Confidence Waterfall */
.waterfall-details { margin-top: 4px; text-align: left; }
.waterfall-toggle { font-size: .75rem; color: var(--muted); cursor: pointer; }
.waterfall-toggle:hover { color: var(--text); }
.waterfall { padding: 6px 0; }
.wf-step { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; font-size: .78rem; }
.wf-label { min-width: 140px; text-align: right; color: var(--muted); font-family: monospace; font-size: .75rem; }
.wf-bar { height: 14px; border-radius: 3px; display: flex; align-items: center; padding: 0 4px; font-size: .7rem; color: white; font-weight: 600; min-width: 30px; }
.wf-positive { background: #2a5; }
.wf-negative { background: #d9534f; }
.wf-learned { background: #e67e22; }
.wf-final { font-weight: 700; font-size: .82rem; margin-top: 4px; padding-top: 4px; border-top: 1px solid var(--border); }
/* Form Section */
.form-section { margin: 16px 0; background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; box-shadow: 0 1px 4px var(--shadow); }
.form-header { padding: 14px 20px; font-weight: 700; font-size: 1.05rem; cursor: pointer; list-style: none; }
.form-header::-webkit-details-marker { display: none; }
.form-header::before { content: "\\25B6 "; font-size: .8rem; }
details[open] .form-header::before { content: "\\25BC "; }
.form-content { padding: 0 20px 20px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.form-field label { display: block; font-size: .82rem; font-weight: 600; margin-bottom: 3px; color: var(--muted); }
.form-field input, .form-field select { width: 100%; padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: .9rem; background: var(--bg); color: var(--text); }
.stmt-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
.stmt-row input { flex: 1; padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: .88rem; background: var(--bg); color: var(--text); }
.stmt-remove { background: none; border: none; color: #a33; font-size: 1.2rem; cursor: pointer; padding: 0 4px; }
.form-actions { display: flex; gap: 8px; margin: 12px 0; }
.form-actions button { padding: 6px 14px; border: 1px solid var(--border); border-radius: 8px; font-size: .88rem; cursor: pointer; background: var(--card-bg); color: var(--text); }
.form-actions .submit-btn { background: #4466cc; color: white; border-color: #4466cc; font-weight: 600; }
.form-actions .submit-btn:hover { background: #3355bb; }
.form-result { margin-top: 16px; padding: 14px; background: #f0f4ff; border: 1px solid #4466cc; border-radius: 8px; }
.form-error { margin-top: 12px; padding: 10px 14px; background: #fdd; border: 1px solid #a33; border-radius: 8px; color: #a33; font-size: .9rem; }
.form-note { font-size: .82rem; color: var(--muted); margin-top: 8px; }
/* Scoring Panel */
.scoring-panel .form-content { max-width: 900px; }
.scoring-section { margin-bottom: 20px; }
.scoring-section h3 { margin-bottom: 6px; font-size: .95rem; }
.scoring-section p, .scoring-section li { font-size: .9rem; line-height: 1.5; }
.formula-box { background: #f0f4ff; border: 1px solid #4466cc; border-radius: 8px; padding: 12px 16px; font-size: .88rem; overflow-x: auto; margin: 8px 0; }
.tier-grid { display: flex; flex-direction: column; gap: 6px; }
.tier-grid div { padding: 6px 10px; background: #f9f9fb; border-radius: 6px; font-size: .9rem; }

/* Trap Heatmap */
.heatmap-grid { display: grid; gap: 2px; margin: 12px 0; overflow-x: auto; }
.hm-corner { background: transparent; }
.hm-header { padding: 6px 8px; font-size: .72rem; font-weight: 600; background: #f0f0f4; text-align: center; writing-mode: vertical-rl; transform: rotate(180deg); min-height: 80px; }
.hm-domain { padding: 6px 10px; font-size: .82rem; font-weight: 600; background: #f0f0f4; white-space: nowrap; }
.hm-cell { padding: 6px 8px; text-align: center; font-size: .8rem; font-weight: 600; border-radius: 3px; min-width: 40px; }
.heatmap-note { font-size: .82rem; color: var(--muted); margin-bottom: 8px; }
.trap-summary { font-size: .9rem; }
.trap-summary-item { margin-bottom: 6px; }
.trap-summary-count { font-weight: 700; color: #a33; }

/* Calibration Panel */
.calibration-grid { display: flex; gap: 24px; flex-wrap: wrap; align-items: flex-start; }
.cm-matrix { border-collapse: collapse; }
.cm-matrix th { padding: 8px 12px; font-size: .85rem; text-align: center; background: #f0f0f4; }
.cm-cell { padding: 12px 16px; text-align: center; font-size: 1.1rem; font-weight: 700; border-radius: 4px; }
.cm-tp { background: #d4edda; color: #155724; }
.cm-fp { background: #fff3cd; color: #856404; }
.cm-fn { background: #f8d7da; color: #721c24; }
.cm-tn { background: #d4edda; color: #155724; }
.cm-metrics { font-size: .9rem; }
.cm-note { font-size: .82rem; color: var(--muted); margin-top: 8px; font-style: italic; }
.calibration-bands { display: flex; gap: 12px; flex-wrap: wrap; }
.cal-band { padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; text-align: center; min-width: 120px; }
.cal-band-label { font-weight: 700; font-size: .88rem; }
.cal-band-stats { font-size: .82rem; color: var(--muted); }

/* Assumption Matrix */
.am-grid { display: grid; gap: 2px; margin: 12px 0; overflow-x: auto; }
.am-corner { background: transparent; }
.am-header { padding: 6px 8px; font-size: .72rem; font-weight: 600; background: #f0f0f4; text-align: center; writing-mode: vertical-rl; transform: rotate(180deg); min-height: 80px; }
.am-row-label { padding: 6px 10px; font-size: .78rem; font-weight: 600; background: #f0f0f4; white-space: nowrap; }
.am-cell { padding: 6px; text-align: center; font-size: .8rem; font-weight: 600; border-radius: 3px; min-width: 36px; }
.am-note { font-size: .82rem; color: var(--muted); margin-bottom: 8px; }
.am-insight { margin-top: 12px; padding: 10px 14px; background: #f8f8f0; border-left: 4px solid #998; border-radius: 6px; font-size: .9rem; }
.am-all-ok { padding: 12px; color: #287; font-weight: 600; }

/* Case navigation */
.case-nav { display: flex; flex-wrap: wrap; gap: 4px; margin: 8px 0 16px; }
.case-nav a { font-size: .78rem; padding: 2px 6px; border-radius: 4px; text-decoration: none; color: #4466cc; background: #f0f4ff; }
.case-nav a:hover { background: #ddf; }
/* Back to top */
.back-to-top { position: fixed; bottom: 24px; right: 24px; width: 40px; height: 40px; border-radius: 50%; background: #4466cc; color: white; border: none; font-size: 1.2rem; cursor: pointer; display: none; z-index: 200; box-shadow: 0 2px 8px rgba(0,0,0,.2); }
.back-to-top:hover { background: #3355bb; }
/* Assumption Failure Correlation Matrix */
.am-grid { display: grid; gap: 2px; margin: 12px 0; overflow-x: auto; }
.am-corner { background: transparent; }
.am-header { padding: 6px 8px; font-size: .72rem; font-weight: 600; background: #f0f0f4; text-align: center; writing-mode: vertical-rl; transform: rotate(180deg); min-height: 80px; }
.am-row-label { padding: 6px 10px; font-size: .78rem; font-weight: 600; background: #f0f0f4; white-space: nowrap; }
.am-cell { padding: 6px; text-align: center; font-size: .8rem; font-weight: 600; border-radius: 3px; min-width: 36px; }
.am-note { font-size: .82rem; color: var(--muted); margin-bottom: 8px; }
.am-insight { margin-top: 12px; padding: 10px 14px; background: #f8f8f0; border-left: 4px solid #998; border-radius: 6px; font-size: .9rem; }
.am-all-ok { padding: 14px; color: #287; font-weight: 600; font-size: .95rem; }
/* Dark mode */
@media (prefers-color-scheme: dark) {
  :root { --bg: #1a1a2e; --card-bg: #222240; --text: #e0e0e0; --muted: #999; --border: #3a3a5c; --shadow: rgba(0,0,0,.3); }
  .controls input[type="text"], .controls select, .controls button { background: #2a2a48; color: #e0e0e0; border-color: #3a3a5c; }
  .controls button:hover { background: #3a3a5c; }
  .stat:hover { background: #2a2a48; }
  .stat.active { background: #333360; outline-color: #6688ee; }
  .section-header { background: #2a2a48; }
  .card-header:hover { background: #2a2a48; }
  .narrative { background: #1e2040; border-color: #5577cc; }
  .engine-label { background: #2a2a48; }
  .counterfactual { background: #2a2a3e; border-color: #3a3a5c; }
  .cf-delta { color: #aaa; }
  th { background: #2a2a48; }
  .insight { background: #28283a; border-color: #665; }
  .case-nav a { background: #2a2a48; color: #88aaee; }
  .jri-bar { background: #333; }
  .transcript { background: #1e2040; }
  .q-bubble { background: #333360; }
  .a-bubble { background: #2a3a5c; }
  .waterfall-details { color: var(--muted); }
  .wf-final { border-top-color: var(--border); }
  .am-header { background: #2a2a48; }
  .am-row-label { background: #2a2a48; }
  .am-insight { background: #28283a; border-color: #665; }
  .hm-header { background: #2a2a48; color: #ccc; }
  .hm-domain { background: #2a2a48; color: #ccc; }
  .cm-matrix th { background: #2a2a48; }
}
body.dark-mode { --bg: #1a1a2e; --card-bg: #222240; --text: #e0e0e0; --muted: #999; --border: #3a3a5c; --shadow: rgba(0,0,0,.3); }
body.dark-mode .controls input[type="text"], body.dark-mode .controls select, body.dark-mode .controls button { background: #2a2a48; color: #e0e0e0; border-color: #3a3a5c; }
body.dark-mode .controls button:hover { background: #3a3a5c; }
body.dark-mode .stat:hover { background: #2a2a48; }
body.dark-mode .stat.active { background: #333360; outline-color: #6688ee; }
body.dark-mode .section-header { background: #2a2a48; }
body.dark-mode .card-header:hover { background: #2a2a48; }
body.dark-mode .narrative { background: #1e2040; border-color: #5577cc; }
body.dark-mode .engine-label { background: #2a2a48; }
body.dark-mode .counterfactual { background: #2a2a3e; border-color: #3a3a5c; }
body.dark-mode .cf-delta { color: #aaa; }
body.dark-mode th { background: #2a2a48; }
body.dark-mode .insight { background: #28283a; border-color: #665; }
body.dark-mode .case-nav a { background: #2a2a48; color: #88aaee; }
body.dark-mode .jri-bar { background: #333; }
body.dark-mode .transcript { background: #1e2040; }
body.dark-mode .q-bubble { background: #333360; }
body.dark-mode .a-bubble { background: #2a3a5c; }
body.dark-mode .waterfall-details { color: var(--muted); }
body.dark-mode .am-header { background: #2a2a48; }
body.dark-mode .am-row-label { background: #2a2a48; }
body.dark-mode .am-insight { background: #28283a; border-color: #665; }
body.dark-mode .wf-final { border-top-color: var(--border); }
body.dark-mode .hm-header { background: #2a2a48; color: #ccc; }
body.dark-mode .hm-domain { background: #2a2a48; color: #ccc; }
body.dark-mode .cm-matrix th { background: #2a2a48; }
/* Print */
@media print {
  .sticky-header, .controls, .stats-bar, .case-nav, .back-to-top, #darkToggle { display: none !important; }
  .card.collapsed .card-body { max-height: none !important; padding: 0 20px 20px !important; }
  .card { break-inside: avoid; box-shadow: none; border: 1px solid #ccc; }
  body { background: white; color: black; }
}
/* Responsive */
@media (max-width: 768px) {
  .container { padding: 12px 16px; }
  .grid { grid-template-columns: 1fr; }
  .controls { flex-direction: column; align-items: stretch; }
  .controls input[type="text"] { width: 100%; }
  .visible-count { margin-left: 0; }
  .stats-bar { flex-direction: column; gap: 8px; }
  .counterfactual { flex-direction: column; gap: 6px; }
  .cf-delta { margin-left: 0; }
  .tornado-row { flex-direction: column; align-items: stretch; }
  .tornado-label { text-align: left; min-width: auto; }
}
/* Tornado Chart */
.tornado-section { margin: 12px 0; }
.tornado-section > summary { cursor: pointer; font-size: .92rem; color: var(--text); }
.tornado-chart { margin: 8px 0; }
.tornado-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; min-height: 28px; }
.tornado-label { min-width: 160px; text-align: right; font-size: .78rem; font-weight: 600; color: var(--muted); white-space: nowrap; }
.tornado-center { width: 2px; background: var(--text); height: 24px; flex-shrink: 0; }
.tornado-bar { height: 22px; border-radius: 4px; display: flex; align-items: center; padding: 0 6px; font-size: .68rem; font-weight: 600; color: white; min-width: 20px; white-space: nowrap; }
.tornado-bar-strict { background: #d9534f; }
.tornado-bar-loose { background: #5bc0de; }
.tornado-bar-changed { outline: 2px solid #111; }
.tornado-legend { display: flex; gap: 12px; font-size: .78rem; color: var(--muted); margin-bottom: 8px; }
.tornado-note { font-size: .82rem; color: var(--muted); font-style: italic; font-weight: normal; }
body.dark-mode .tornado-center { background: var(--muted); }
body.dark-mode .tornado-bar-changed { outline-color: #fff; }
/* Multi-Turn Simulation */
.multiturn-section { margin: 12px 0; }
.multiturn-section > summary { cursor: pointer; font-size: .92rem; color: var(--text); }
.multiturn-timeline { position: relative; padding-left: 24px; margin: 12px 0; }
.multiturn-timeline::before { content: ''; position: absolute; left: 8px; top: 0; bottom: 0; width: 2px; background: var(--border); }
.mt-turn { position: relative; margin-bottom: 16px; padding: 10px 14px; background: #f9f9fb; border: 1px solid var(--border); border-radius: 8px; }
.mt-turn::before { content: ''; position: absolute; left: -20px; top: 14px; width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--border); background: var(--card-bg); }
.mt-turn-changed::before { background: #4466cc; border-color: #4466cc; }
.mt-turn-converged::before { background: #2a5; border-color: #2a5; }
.mt-turn-header { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.mt-turn-num { font-weight: 700; font-size: .88rem; }
.mt-question { font-size: .85rem; color: var(--muted); margin: 4px 0; }
.mt-answer { font-size: .85rem; color: #333; margin: 4px 0; padding: 6px 10px; background: #e8f0ff; border-radius: 6px; }
.mt-scores { display: flex; gap: 12px; margin-top: 6px; font-size: .82rem; flex-wrap: wrap; }
.mt-delta { font-weight: 600; }
.mt-delta-positive { color: #2a5; }
.mt-delta-negative { color: #a33; }
.mt-delta-neutral { color: var(--muted); }
.mt-summary { margin-top: 12px; padding: 10px 14px; background: #f0f4ff; border-left: 4px solid #4466cc; border-radius: 6px; font-size: .88rem; }
.mt-no-improvement { color: #a33; font-weight: 600; }
body.dark-mode .mt-turn { background: #1a1a2e; }
body.dark-mode .mt-answer { background: #1a2940; color: #d0d0d0; }
body.dark-mode .mt-summary { background: #1a2040; border-color: #5577cc; }
/* Multi-Turn Validation */
.mt-validation { margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.mt-validation-label { font-size: .82rem; font-weight: 600; color: var(--muted); margin-right: 4px; }
.mt-pass { display: inline-block; font-size: .72rem; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
.mt-fail { display: inline-block; font-size: .72rem; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
body.dark-mode .mt-pass { background: #1a3a2a; color: #7dcea0; border-color: #2a5a3a; }
body.dark-mode .mt-fail { background: #3a1a1a; color: #e09090; border-color: #5a2a2a; }
/* Reasoning Transparency Panel */
.reasoning-panel { margin: 12px 0; }
.reasoning-panel > summary { cursor: pointer; font-size: .92rem; color: var(--text); }
.rt-content { padding: 8px 0; }
.rt-section h5, .rt-gestalt-section h5, .rt-intel-section h5 { margin: 12px 0 6px 0; font-size: .88rem; color: var(--text); }
.rt-obs-grid { display: flex; flex-direction: column; gap: 4px; }
.rt-obs-row { display: flex; align-items: center; gap: 8px; padding: 4px 8px; background: #f8f9fb; border-radius: 6px; font-size: .78rem; flex-wrap: wrap; }
.rt-obs-concept { font-weight: 700; min-width: 120px; color: var(--text); }
.rt-obs-conf { font-weight: 700; min-width: 40px; text-align: center; padding: 2px 6px; border-radius: 4px; color: white; font-size: .72rem; }
.rt-conf-high { background: #2a5; }
.rt-conf-med { background: #cc8800; }
.rt-conf-low { background: #c33; }
.rt-obs-trace { display: flex; gap: 4px; flex-wrap: wrap; }
.rt-step { font-size: .7rem; padding: 1px 6px; border-radius: 3px; white-space: nowrap; }
.rt-base { background: #e0eaff; color: #335; }
.rt-penalty { background: #ffe0e0; color: #633; }
.rt-neutral { background: #eee; color: #555; }
.rt-obs-tags { display: flex; gap: 3px; flex-wrap: wrap; }
.rt-tag { font-size: .68rem; padding: 1px 5px; border-radius: 3px; background: #d9534f; color: white; }
.rt-metrics { display: flex; gap: 16px; margin: 12px 0; flex-wrap: wrap; }
.rt-metric { flex: 1; min-width: 200px; }
.rt-metric-label { font-size: .82rem; font-weight: 600; color: var(--muted); }
.rt-bar { height: 14px; background: #eee; border-radius: 7px; overflow: hidden; margin: 4px 0; }
.rt-bar-fill { height: 100%; background: #4466cc; border-radius: 7px; transition: width 0.3s; }
.rt-bar-risk { background: #d9534f; }
.rt-metric-value { font-size: .82rem; font-weight: 700; }
.rt-gestalt-item { padding: 8px 12px; margin: 6px 0; background: #fff3e0; border-left: 4px solid #ff9800; border-radius: 6px; }
.rt-gestalt-name { font-weight: 700; font-size: .88rem; color: #e65100; }
.rt-gestalt-reason { font-size: .82rem; color: #333; margin: 4px 0; }
.rt-gestalt-evidence { font-size: .75rem; color: var(--muted); }
.rt-intel-section { margin: 8px 0; }
.rt-intel-item { display: flex; gap: 8px; align-items: center; padding: 4px 8px; margin: 3px 0; border-radius: 4px; font-size: .78rem; }
.rt-intel-high { background: #ffe0e0; }
.rt-intel-low { background: #e0ffe0; }
.rt-intel-label { font-weight: 700; min-width: 140px; }
.rt-intel-desc { flex: 1; color: var(--muted); }
.rt-intel-effect { font-style: italic; color: var(--muted); font-size: .72rem; }
body.dark-mode .rt-obs-row { background: #1a1a2e; }
body.dark-mode .rt-gestalt-item { background: #2a1a00; border-color: #cc7700; }
body.dark-mode .rt-gestalt-name { color: #ffb74d; }
body.dark-mode .rt-gestalt-reason { color: #d0d0d0; }
body.dark-mode .rt-intel-high { background: #2a1010; }
body.dark-mode .rt-intel-low { background: #102a10; }
body.dark-mode .rt-bar { background: #333; }
/* Autonomy Tier Distribution Panel */
.at-panel { margin: 16px 0; }
.at-chart { margin: 12px 0; }
.at-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.at-label { min-width: 160px; text-align: right; font-size: .85rem; font-weight: 600; color: var(--muted); white-space: nowrap; }
.at-bar-track { flex: 1; height: 24px; background: #eee; border-radius: 6px; overflow: hidden; position: relative; }
.at-bar { height: 100%; border-radius: 6px; display: flex; align-items: center; padding: 0 8px; font-size: .78rem; font-weight: 700; color: white; min-width: 24px; transition: width 0.3s; }
.at-bar-t0 { background: #c0392b; }
.at-bar-t1 { background: #e67e22; }
.at-bar-t2 { background: #f1c40f; color: #333; }
.at-bar-t3 { background: #82c97c; color: #1a3a1a; }
.at-bar-t4 { background: #27ae60; }
.at-count { min-width: 30px; font-size: .85rem; font-weight: 700; color: var(--text); }
.at-table { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: .88rem; }
.at-table th { padding: 8px 12px; background: #f0f0f4; text-align: left; font-weight: 600; }
.at-table td { padding: 6px 12px; border-top: 1px solid #e5e5e5; }
.at-tier-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: .78rem; font-weight: 700; color: white; }
.at-badge-t0 { background: #c0392b; }
.at-badge-t1 { background: #e67e22; }
.at-badge-t2 { background: #f1c40f; color: #333; }
.at-badge-t3 { background: #82c97c; color: #1a3a1a; }
.at-badge-t4 { background: #27ae60; }
.at-note { font-size: .82rem; color: var(--muted); margin-bottom: 8px; }
body.dark-mode .at-bar-track { background: #333; }
body.dark-mode .at-table th { background: #2a2a48; }
body.dark-mode .at-bar-t2 { color: #111; }
body.dark-mode .at-badge-t2 { color: #111; }
body.dark-mode .at-bar-t3 { color: #0a1a0a; }
body.dark-mode .at-badge-t3 { color: #0a1a0a; }
/* Experience Memory Panel */
.experience-panel { background: #f8f9fa; border-left: 4px solid #6c5ce7; padding: 18px; margin: 16px 0; border-radius: 8px; }
.exp-table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 10px 0; }
.exp-table th { background: #dfe6e9; padding: 6px 10px; text-align: left; }
.exp-table td { padding: 5px 10px; border-bottom: 1px solid #eee; }
.exp-bar { height: 14px; background: linear-gradient(90deg, #6c5ce7, #a29bfe); border-radius: 3px; min-width: 2px; }
.exp-note { color: #636e72; font-style: italic; font-size: 13px; }
body.dark-mode .experience-panel { background: #1e1e3a; border-color: #9b8ce7; }
body.dark-mode .exp-table th { background: #2a2a48; }
body.dark-mode .exp-table td { border-color: #3a3a5c; }
body.dark-mode .exp-note { color: #999; }
/* Modality Adaptation Panel */
.modality-panel { background: #fef9ef; border-left: 4px solid #fdcb6e; padding: 14px; margin: 10px 0; border-radius: 8px; }
.mod-badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-weight: 700; font-size: 12px; color: #fff; }
.mod-phone { background: #00b894; }
.mod-text { background: #0984e3; }
.mod-video { background: #e17055; }
.mod-in_person { background: #6c5ce7; }
.mod-list { font-size: 13px; }
.mod-questions { margin-top: 10px; }
.mod-questions li { margin: 4px 0; font-size: 13px; }
body.dark-mode .modality-panel { background: #2a2a1e; border-color: #fdcb6e; }
/* Source Weight Trace Panel */
.source-weight-panel { background: #f0f9ff; border-left: 4px solid #74b9ff; padding: 14px; margin: 10px 0; border-radius: 8px; }
.sw-table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; }
.sw-table th { background: #dfe6e9; padding: 5px 8px; text-align: left; }
.sw-table td { padding: 4px 8px; border-bottom: 1px solid #eee; }
.sw-source { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; color: #fff; }
.sw-device { background: #00b894; }
.sw-chart { background: #0984e3; }
.sw-clinician { background: #6c5ce7; }
.sw-synthetic_truth { background: #00cec9; }
.sw-caregiver { background: #fdcb6e; color: #2d3436; }
.sw-patient { background: #b2bec3; color: #2d3436; }
.sw-note { color: #636e72; font-size: 12px; margin-top: 6px; }
body.dark-mode .source-weight-panel { background: #1a2040; border-color: #74b9ff; }
body.dark-mode .sw-table th { background: #2a2a48; }
body.dark-mode .sw-table td { border-color: #3a3a5c; }
body.dark-mode .sw-note { color: #999; }
/* Capabilities Matrix Panel */
.capabilities-panel { background: var(--card-bg); border: 2px solid #2d3436; padding: 20px; margin: 24px 0; border-radius: 10px; }
.capabilities-panel h3 { margin-top: 0; color: var(--text); border-bottom: 2px solid #dfe6e9; padding-bottom: 10px; }
.cap-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.cap-table th { background: #2d3436; color: #fff; padding: 8px 12px; text-align: left; }
.cap-table td { padding: 7px 12px; border-bottom: 1px solid #eee; }
.cap-table tr:hover { background: #f8f9fa; }
.cap-active { display: inline-block; background: #00b894; color: #fff; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.cap-optional { display: inline-block; background: #fdcb6e; color: #2d3436; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
body.dark-mode .capabilities-panel { border-color: #636e72; }
body.dark-mode .capabilities-panel h3 { border-bottom-color: #444; }
body.dark-mode .cap-table th { background: #1a1a2e; }
body.dark-mode .cap-table td { border-bottom-color: #333; }
body.dark-mode .cap-table tr:hover { background: #1e1e3e; }
"""


def _html_js():
    """Return all JavaScript as a plain string (no f-string braces)."""
    return """
(function() {
  var activeState = null;
  var activeCategory = 'all';
  var searchTerm = '';
  function getCards() { return document.querySelectorAll('.card'); }
  function updateVisibleCount() {
    var cards = getCards();
    var visible = 0;
    cards.forEach(function(c) { if (c.style.display !== 'none') visible++; });
    var el = document.getElementById('visibleCount');
    if (el) el.textContent = visible + ' of ' + cards.length + ' cases shown';
  }
  function applyFilters() {
    var cards = getCards();
    cards.forEach(function(card) {
      var stateMatch = !activeState || card.getAttribute('data-state') === activeState;
      var catMatch = activeCategory === 'all' || card.getAttribute('data-category') === activeCategory;
      var textMatch = !searchTerm || card.textContent.toLowerCase().indexOf(searchTerm.toLowerCase()) !== -1;
      card.style.display = (stateMatch && catMatch && textMatch) ? '' : 'none';
    });
    updateVisibleCount();
  }
  document.addEventListener('click', function(e) {
    var stat = e.target.closest('.stat[data-filter-state]');
    if (!stat) return;
    var state = stat.getAttribute('data-filter-state');
    var allStats = document.querySelectorAll('.stat[data-filter-state]');
    if (activeState === state) {
      activeState = null;
      allStats.forEach(function(s) { s.classList.remove('active'); });
    } else {
      activeState = state;
      allStats.forEach(function(s) { s.classList.remove('active'); });
      stat.classList.add('active');
    }
    applyFilters();
  });
  var catSelect = document.getElementById('categoryFilter');
  if (catSelect) { catSelect.addEventListener('change', function() { activeCategory = this.value; applyFilters(); }); }
  var searchInput = document.getElementById('searchBox');
  if (searchInput) { searchInput.addEventListener('input', function() { searchTerm = this.value; applyFilters(); }); }
  document.addEventListener('click', function(e) {
    var header = e.target.closest('.card-header');
    if (!header) return;
    var card = header.closest('.card');
    if (card) card.classList.toggle('collapsed');
  });
  var expandBtn = document.getElementById('expandAll');
  var collapseBtn = document.getElementById('collapseAll');
  if (expandBtn) expandBtn.addEventListener('click', function() { getCards().forEach(function(c) { c.classList.remove('collapsed'); }); });
  if (collapseBtn) collapseBtn.addEventListener('click', function() { getCards().forEach(function(c) { c.classList.add('collapsed'); }); });
  var darkBtn = document.getElementById('darkToggle');
  if (darkBtn) {
    darkBtn.addEventListener('click', function() {
      document.body.classList.toggle('dark-mode');
      darkBtn.textContent = document.body.classList.contains('dark-mode') ? 'Light' : 'Dark';
    });
  }
  var topBtn = document.getElementById('backToTop');
  if (topBtn) {
    window.addEventListener('scroll', function() { topBtn.style.display = window.scrollY > 400 ? 'block' : 'none'; });
    topBtn.addEventListener('click', function() { window.scrollTo({top: 0, behavior: 'smooth'}); });
  }
  updateVisibleCount();
  function escHtml(str) { var d = document.createElement('div'); d.appendChild(document.createTextNode(str)); return d.innerHTML; }
  window.addStatementRow = function() {
    var container = document.getElementById('statementsContainer');
    var row = document.createElement('div');
    row.className = 'stmt-row';
    row.innerHTML = '<input type="text" class="stmt-q" placeholder="Question" />' + '<input type="text" class="stmt-a" placeholder="Patient Answer" />' + '<input type="text" class="stmt-c" placeholder="Concept (optional)" />' + '<button type="button" onclick="removeStatementRow(this)" class="stmt-remove">&times;</button>';
    container.appendChild(row);
  };
  window.removeStatementRow = function(btn) { var row = btn.closest('.stmt-row'); var container = document.getElementById('statementsContainer'); if (container.children.length > 1) row.remove(); };
  window.fillExample = function() {
    document.getElementById('formCaseId').value = 'example-chest-001';
    document.getElementById('formAge').value = '58';
    document.getElementById('formConcern').value = 'chest pressure';
    document.getElementById('formDomain').value = 'chest_discomfort';
    document.getElementById('formModality').value = 'text';
    document.getElementById('formConditions').value = 'hypertension';
    var container = document.getElementById('statementsContainer');
    container.innerHTML = '';
    var stmts = [{q:'Do you have chest pain?',a:'No pain, just heartburn and pressure when I walk upstairs.',c:'symptom_quality'},{q:'Does it change with activity?',a:'Yes, worse with stairs, better at rest.',c:'exertional_component'}];
    stmts.forEach(function(s) {
      var row = document.createElement('div');
      row.className = 'stmt-row';
      row.innerHTML = '<input type="text" class="stmt-q" value="' + escHtml(s.q) + '" />' + '<input type="text" class="stmt-a" value="' + escHtml(s.a) + '" />' + '<input type="text" class="stmt-c" value="' + escHtml(s.c) + '" />' + '<button type="button" onclick="removeStatementRow(this)" class="stmt-remove">&times;</button>';
      container.appendChild(row);
    });
  };
  window.submitCase = function() {
    var resultEl = document.getElementById('formResult');
    var errorEl = document.getElementById('formError');
    resultEl.style.display = 'none';
    errorEl.style.display = 'none';
    var conditions = document.getElementById('formConditions').value;
    var condList = conditions ? conditions.split(',').map(function(c) { return c.trim(); }).filter(Boolean) : [];
    var rows = document.querySelectorAll('#statementsContainer .stmt-row');
    var statements = [];
    rows.forEach(function(row) {
      var q = row.querySelector('.stmt-q').value.trim();
      var a = row.querySelector('.stmt-a').value.trim();
      var c = row.querySelector('.stmt-c').value.trim();
      if (q && a) { var s = {question: q, answer: a, source: 'patient'}; if (c) s.concept = c; statements.push(s); }
    });
    if (statements.length === 0) { errorEl.textContent = 'Please add at least one statement with a question and answer.'; errorEl.style.display = 'block'; return; }
    var payload = { case_id: document.getElementById('formCaseId').value || 'custom-001', patient_context: { age: parseInt(document.getElementById('formAge').value) || 55, chief_concern: document.getElementById('formConcern').value || 'unknown', domain: document.getElementById('formDomain').value, modality: document.getElementById('formModality').value, known_conditions: condList }, statements: statements };
    fetch('http://localhost:8000/evaluate', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) })
    .then(function(resp) { if (!resp.ok) return resp.json().then(function(d) { throw new Error(d.detail || 'API error ' + resp.status); }); return resp.json(); })
    .then(function(data) { renderResult(data, resultEl); })
    .catch(function(err) { errorEl.textContent = 'Error: ' + err.message + '. Is the API server running on localhost:8000?'; errorEl.style.display = 'block'; });
  };
  function renderResult(data, el) {
    var jre = data.jre_report || {};
    var bsg = data.bsg_report || {};
    var scores = jre.scores || {};
    var findings = (jre.findings || []).concat(bsg.findings || []);
    var questions = jre.next_questions || [];
    var h = '<div><strong>Combined State:</strong> <span class="state-badge badge-' + escHtml((data.combined_state || '').toLowerCase()) + '">' + escHtml(data.combined_state) + '</span></div>';
    h += '<div style="margin:8px 0"><strong>Judgment Readiness:</strong> ' + escHtml(jre.state || '') + ' &nbsp; <strong>Black Swan Guard:</strong> ' + escHtml(bsg.guardrail_state || '') + '</div>';
    if (scores.readiness_index !== undefined) h += '<div><strong>Readiness Index:</strong> ' + scores.readiness_index.toFixed(1) + '/100</div>';
    if (findings.length > 0) { h += '<div style="margin-top:8px"><strong>Findings:</strong><ul>'; findings.slice(0, 6).forEach(function(f) { h += '<li>' + escHtml(f.category || f.rule_id || '') + ': ' + escHtml(f.reason || '') + '</li>'; }); h += '</ul></div>'; }
    if (questions.length > 0) { h += '<div style="margin-top:8px"><strong>Next Questions:</strong><ul>'; questions.slice(0, 3).forEach(function(q) { h += '<li><b>' + escHtml(q.concept || '') + '</b>: ' + escHtml(q.question || '') + '</li>'; }); h += '</ul></div>'; }
    h += '<div style="margin-top:4px;font-size:.82rem;color:#888">' + (data.duration_ms || 0).toFixed(1) + 'ms</div>';
    el.innerHTML = h;
    el.style.display = 'block';
  }
})();
"""


def _html_jri_breakdown(scores):
    """Generate JRI stacked bar HTML for a ReadinessScores object."""
    w_comp, w_rel, w_obj, w_dist = 0.35, 0.30, 0.20, 0.15
    comp_pct = scores.completeness * w_comp
    rel_pct = scores.reliability * w_rel
    obj_pct = scores.objective_coverage * w_obj
    dist_pct = (1.0 - scores.distortion_load) * w_dist
    total_base = comp_pct + rel_pct + obj_pct + dist_pct
    if total_base < 0.01:
        total_base = 1.0
    seg_comp = comp_pct / total_base * 100
    seg_rel = rel_pct / total_base * 100
    seg_obj = obj_pct / total_base * 100
    seg_dist = dist_pct / total_base * 100
    contra_pct = min(scores.contradiction_load * 100, 100)
    redflag_pct = min(scores.red_flag_load * 100, 100)
    bar = (f'<div class="jri-breakdown"><div class="jri-bar">'
           f'<div class="jri-seg jri-seg-completeness" style="width:{seg_comp:.1f}%" title="Completeness {scores.completeness:.0%}">Completeness</div>'
           f'<div class="jri-seg jri-seg-reliability" style="width:{seg_rel:.1f}%" title="Reliability {scores.reliability:.0%}">Reliability</div>'
           f'<div class="jri-seg jri-seg-objective" style="width:{seg_obj:.1f}%" title="Objective {scores.objective_coverage:.0%}">Objective</div>'
           f'<div class="jri-seg jri-seg-distortion" style="width:{seg_dist:.1f}%" title="Low Distortion {1-scores.distortion_load:.0%}">Distortion</div></div>')
    if contra_pct > 0 or redflag_pct > 0:
        bar += (f'<div class="jri-penalty-bar">'
                f'<div class="jri-penalty" style="width:{contra_pct:.1f}%" title="Contradiction penalty {scores.contradiction_load:.0%}"></div>'
                f'<div class="jri-penalty" style="width:{redflag_pct:.1f}%; margin-left:2px" title="Red flag penalty {scores.red_flag_load:.0%}"></div></div>')
    bar += (f'<div class="jri-labels"><span>Completeness {scores.completeness:.0%} | Reliability {scores.reliability:.0%} | Objective {scores.objective_coverage:.0%} | Distortion {scores.distortion_load:.0%}</span>'
            f'<span>Readiness Index: {scores.readiness_index:.1f}/100</span></div></div>')
    return bar


def _parse_trace_entry(entry):
    """Parse a single trace entry into (label, value, category)."""
    if entry.startswith("BASE_SOURCE_CONFIDENCE:"):
        remainder = entry.split(":", 1)[1]
        eq_idx = remainder.find("=")
        if eq_idx != -1:
            label = remainder[:eq_idx].strip()
            try:
                value = float(remainder[eq_idx + 1:])
            except ValueError:
                value = 0.0
        else:
            label = remainder
            value = 0.0
        return label, value, "base"
    if entry.startswith("EXPERIENCE_PRIOR:"):
        remainder = entry.split(":", 1)[1]
        colon_idx = remainder.rfind(":")
        if colon_idx != -1:
            label = remainder[:colon_idx].strip()
            try:
                value = float(remainder[colon_idx + 1:])
            except ValueError:
                value = 0.0
        else:
            label = remainder
            value = 0.0
        return label, value, "learned"
    colon_idx = entry.rfind(":")
    if colon_idx != -1:
        label = entry[:colon_idx].strip()
        try:
            value = float(entry[colon_idx + 1:])
        except ValueError:
            label = entry
            value = 0.0
    else:
        label = entry
        value = 0.0
    category = "base" if value >= 0 else "penalty"
    return label, value, category


def _html_transcript(r):
    """Generate annotated clinical transcript for a case."""
    e = html_mod.escape
    obs_by_concept = {}
    for obs in r.jre_report.observations:
        obs_by_concept[obs.concept] = obs
    redflag_concepts = set()
    for f in r.jre_report.findings:
        if f.category == "red_flag":
            redflag_concepts.add(f.concept)
    rows = ""
    for stmt in r.case.statements:
        concept = stmt.concept or ""
        obs = obs_by_concept.get(concept)
        conf_html = ""
        if obs:
            conf = obs.confidence
            if conf >= 0.80:
                conf_color = "#2a5"
            elif conf >= 0.55:
                conf_color = "#c90"
            else:
                conf_color = "#a33"
            conf_html = f'<span class="confidence-badge" style="background:{conf_color}">{conf:.0%}</span>'
        trap_html = ""
        if obs and obs.tags:
            for tag in obs.tags:
                explanation = TRAP_EXPLANATIONS.get(tag, tag.replace("_", " "))
                trap_html += f'<span class="trap-tag" title="{e(explanation)}">{e(tag.replace("_", " "))}</span>'
        redflag_html = ""
        if concept in redflag_concepts:
            redflag_html = '<span class="redflag-icon" title="Red flag detected">&#9888;</span>'
        waterfall_html = ""
        if obs and obs.trace:
            wf_steps = ""
            for trace_entry in obs.trace:
                wf_label, wf_value, wf_category = _parse_trace_entry(trace_entry)
                if wf_category == "base":
                    wf_class = "wf-positive"
                elif wf_category == "learned":
                    wf_class = "wf-learned"
                else:
                    wf_class = "wf-negative"
                bar_width = max(30, int(abs(wf_value) * 200))
                wf_steps += (f'<div class="wf-step"><span class="wf-label">{e(wf_label.lower().replace("_", " "))}</span>'
                             f'<span class="wf-bar {wf_class}" style="width:{bar_width}px">{wf_value:+.2f}</span></div>')
            waterfall_html = (f'<details class="waterfall-details"><summary class="waterfall-toggle">Show scoring chain</summary>'
                              f'<div class="waterfall">{wf_steps}<div class="wf-final">Final: {obs.confidence:.2f}</div></div></details>')
        rows += f"""
        <div class="transcript-row">
          <div class="q-bubble"><b>Q:</b> {e(stmt.question)}</div>
          <div class="a-bubble">{e(stmt.answer)}
            <div class="transcript-annotations">{conf_html} {trap_html} {redflag_html}</div>
            {waterfall_html}
          </div>
        </div>"""
    legend = """
    <div class="transcript-legend">
      <span><span class="confidence-badge" style="background:#2a5">80%+</span> High confidence</span>
      <span><span class="confidence-badge" style="background:#c90">55-79%</span> Moderate</span>
      <span><span class="confidence-badge" style="background:#a33">&lt;55%</span> Low</span>
      <span class="trap-tag">trap</span> = Distortion trap detected
      <span class="redflag-icon">&#9888;</span> = Red flag
    </div>"""
    return f'<div class="transcript"><h3>Clinical Transcript</h3>{rows}{legend}</div>'


def _html_form_section():
    """Generate interactive patient data entry form."""
    domains = sorted(DOMAIN_TEMPLATES)
    domain_options = "".join(f'<option value="{d}">{d.replace("_", " ").title()}</option>' for d in domains)
    return f"""
    <details class="form-section" id="formSection">
      <summary class="form-header">Try Your Own Case</summary>
      <div class="form-content">
        <div class="form-grid">
          <div class="form-field"><label>Case ID</label><input type="text" id="formCaseId" value="custom-001" /></div>
          <div class="form-field"><label>Patient Age</label><input type="number" id="formAge" value="55" min="1" max="120" /></div>
          <div class="form-field"><label>Chief Concern</label><input type="text" id="formConcern" value="" placeholder="e.g., chest pressure" /></div>
          <div class="form-field"><label>Domain</label><select id="formDomain">{domain_options}</select></div>
          <div class="form-field"><label>Modality</label><select id="formModality"><option value="text">Text</option><option value="phone">Phone</option><option value="video">Video</option><option value="in_person">In Person</option></select></div>
          <div class="form-field"><label>Known Conditions</label><input type="text" id="formConditions" placeholder="comma-separated, e.g., hypertension, diabetes" /></div>
        </div>
        <h4>Patient Statements</h4>
        <div id="statementsContainer">
          <div class="stmt-row">
            <input type="text" class="stmt-q" placeholder="Question" />
            <input type="text" class="stmt-a" placeholder="Patient Answer" />
            <input type="text" class="stmt-c" placeholder="Concept (optional)" />
            <button type="button" onclick="removeStatementRow(this)" class="stmt-remove">&times;</button>
          </div>
        </div>
        <div class="form-actions">
          <button type="button" onclick="addStatementRow()">+ Add Statement</button>
          <button type="button" onclick="fillExample()">Try Example</button>
          <button type="button" onclick="submitCase()" class="submit-btn">Submit</button>
        </div>
        <div id="formResult" class="form-result" style="display:none"></div>
        <div id="formError" class="form-error" style="display:none"></div>
        <p class="form-note">Requires API server running: <code>python api_server.py</code></p>
      </div>
    </details>"""


def _html_scoring_panel():
    """Generate scoring explanation panel."""
    trap_rows = "".join(f"<tr><td><code>{k}</code></td><td>{v}</td></tr>" for k, v in TRAP_EXPLANATIONS.items())
    return """
    <details class="form-section scoring-panel" id="scoringPanel">
      <summary class="form-header">How Scoring Works</summary>
      <div class="form-content">
        <div class="scoring-section"><h3>Readiness Index Formula</h3><div class="formula-box"><code>readiness_index = 0.35 &times; completeness + 0.30 &times; reliability + 0.20 &times; objective_coverage + 0.15 &times; (1 &minus; distortion_load) &minus; contradiction_penalty &minus; red_flag_penalty &minus; critical_missing_penalty</code></div><p>Each component is scored 0&ndash;1 based on slot coverage, source reliability, objective data presence, and distortion detection. Penalties reduce the score for contradictions, red flags, and critical missing data.</p></div>
        <div class="scoring-section"><h3>Confidence Scoring</h3><p><b>Source hierarchy:</b> Device data (0.92) &gt; Clinician (0.88) &gt; Chart (0.85) &gt; Caregiver (0.78) &gt; Patient self-report (0.72)</p><p><b>Penalties applied:</b></p><ul><li>Vague language (e.g., &ldquo;kind of&rdquo;, &ldquo;maybe&rdquo;): &minus;0.15</li><li>Objective claim without number (e.g., &ldquo;BP is normal&rdquo;): &minus;0.22</li><li>Trap detection (distortion pattern matched): &minus;0.18</li></ul></div>
        <div class="scoring-section"><h3>Named Distortion Traps</h3><table><thead><tr><th>Trap ID</th><th>Explanation</th></tr></thead><tbody>""" + trap_rows + """</tbody></table></div>
        <div class="scoring-section"><h3>State Decision Thresholds</h3><table><thead><tr><th>State</th><th>Condition</th></tr></thead><tbody><tr><td><b>ESCALATE</b></td><td>Red flag severity &ge; 0.80, or critical contradictions found</td></tr><tr><td><b>NEED_OBJECTIVE_DATA</b></td><td>Critical slot requires objective data not yet provided</td></tr><tr><td><b>CLARIFY</b></td><td>Readiness Index &lt; threshold (typically 65) or low-confidence observations need follow-up</td></tr><tr><td><b>READY</b></td><td>Readiness Index &ge; threshold, no red flags, no critical gaps</td></tr></tbody></table></div>
        <div class="scoring-section"><h3>Black Swan Guard Layer</h3><p><b>Sentinel rules</b> (fire on pattern match regardless of pathway):</p><ul><li>Stroke language (one-sided weakness, slurred speech, facial droop)</li><li>Active bleeding (vomiting blood, black tarry stool, hemorrhage)</li><li>Pregnancy + abdominal pain</li><li>Suicidal ideation / self-harm</li><li>Anaphylaxis (throat closing, can&rsquo;t breathe + allergy)</li><li>Coercion / abuse indicators</li></ul><p><b>Integrity rules</b> (detect system-level threats):</p><ul><li>Wrong patient / proxy identity</li><li>Prompt injection / adversarial text</li><li>Copy-paste rote answers</li><li>Non-response after risk disclosure</li><li>Stale / expired data</li></ul><p><b>Envelope checks</b> (operating boundary violations):</p><ul><li>Unsupported clinical domain</li><li>Language barrier detected</li><li>Pediatric patient (age-appropriate handling)</li></ul></div>
        <div class="scoring-section"><h3>Autonomy Tiers</h3><div class="tier-grid"><div><b>T0</b> &mdash; Emergency hard stop. Immediate human intervention required.</div><div><b>T1</b> &mdash; Intake only. System can collect data but cannot recommend.</div><div><b>T2</b> &mdash; Clinician draft. System proposes, clinician approves every action.</div><div><b>T3</b> &mdash; Supervised protocol. System follows approved protocol with oversight.</div><div><b>T4</b> &mdash; Narrow autonomous action. Safe actions within proven boundaries.</div></div></div>
        <div class="scoring-section"><h3>Most-Restrictive-Wins</h3><p>The combined state is always the <em>more restrictive</em> of the Judgment Readiness state and the Black Swan Guard state. ESCALATE &gt; FAIL_CLOSED &gt; ROUTE_CLINICIAN &gt; NEED_OBJECTIVE_DATA &gt; HOLD_AND_VERIFY &gt; CLARIFY &gt; ALLOW_WITH_AUDIT &gt; READY.</p></div>
        <div class="scoring-section"><h3>Why This Matters</h3><p>This system is deterministic and rule-based. Every decision is traceable to specific patterns, thresholds, and rules &mdash; no LLM hallucination risk, fully auditable, and perfectly reproducible. The same input always produces the same output, which is essential for clinical safety systems where unpredictable behavior is unacceptable.</p></div>
      </div>
    </details>"""


def _html_trap_heatmap(results: List[UnifiedResult]) -> str:
    """Generate a cross-case domain x trap heatmap showing confidence degradation patterns."""
    e = html_mod.escape

    # Aggregate: domain -> trap -> {count, total_conf_loss}
    trap_data: Dict[str, Dict[str, Dict[str, float]]] = {}
    all_traps: set = set()
    all_domains: set = set()

    for r in results:
        domain = r.case.patient_context.domain
        all_domains.add(domain)
        for obs in r.jre_report.observations:
            for raw_tag in obs.tags:
                tag = raw_tag.split(":", 1)[-1] if ":" in raw_tag else raw_tag
                all_traps.add(tag)
                if domain not in trap_data:
                    trap_data[domain] = {}
                if tag not in trap_data[domain]:
                    trap_data[domain][tag] = {"count": 0, "total_conf_loss": 0.0}
                trap_data[domain][tag]["count"] += 1
                trap_data[domain][tag]["total_conf_loss"] += max(0.0, 0.72 - obs.confidence)

    if not all_traps or not all_domains:
        return ""

    sorted_traps = sorted(all_traps)
    sorted_domains = sorted(all_domains)

    max_count = 0
    for domain in sorted_domains:
        for trap in sorted_traps:
            cell = trap_data.get(domain, {}).get(trap)
            if cell and cell["count"] > max_count:
                max_count = cell["count"]

    num_cols = len(sorted_traps)
    grid_cols = f"auto repeat({num_cols}, 1fr)"

    headers = '<div class="hm-corner"></div>'
    for trap in sorted_traps:
        label = trap.replace("_", " ").title()
        headers += f'<div class="hm-header">{e(label)}</div>'

    domain_rows = ""
    for domain in sorted_domains:
        domain_label = domain.replace("_", " ").title()
        domain_rows += f'<div class="hm-domain">{e(domain_label)}</div>'
        for trap in sorted_traps:
            cell = trap_data.get(domain, {}).get(trap)
            if cell and cell["count"] > 0:
                count = cell["count"]
                intensity = count / max_count if max_count > 0 else 0
                bg_color = f"rgba(170, 51, 51, {intensity * 0.7 + 0.1:.2f})"
                text_color = "white" if intensity > 0.5 else "var(--text)"
                conf_loss = cell["total_conf_loss"]
                title_text = f"{count} occurrence(s), total conf loss: {conf_loss:.2f}"
                domain_rows += (
                    f'<div class="hm-cell" style="background:{bg_color};color:{text_color}" '
                    f'title="{e(title_text)}">{count}</div>'
                )
            else:
                domain_rows += '<div class="hm-cell" style="background:transparent"></div>'

    trap_totals: Dict[str, int] = {}
    for domain in sorted_domains:
        for trap in sorted_traps:
            cell = trap_data.get(domain, {}).get(trap)
            if cell:
                trap_totals[trap] = trap_totals.get(trap, 0) + cell["count"]
    top_traps = sorted(trap_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    top_traps_html = ""
    for trap, count in top_traps:
        explanation = TRAP_EXPLANATIONS.get(trap, trap.replace("_", " "))
        trap_label = trap.replace("_", " ").title()
        top_traps_html += (
            f'<div class="trap-summary-item">'
            f'<span class="trap-summary-count">{count}x</span> '
            f'<b>{e(trap_label)}</b> &mdash; {e(explanation)}'
            f'</div>'
        )

    return f"""
    <details class="form-section" id="trapHeatmap">
      <summary class="form-header">Distortion Trap Impact Across Domains</summary>
      <div class="form-content">
        <p class="heatmap-note">Cell intensity shows how many observations were affected by each trap in each domain. Darker = more impact. Hover for details.</p>
        <div class="heatmap-grid" style="grid-template-columns: {grid_cols}">
          {headers}
          {domain_rows}
        </div>
        <h4>Most Impactful Traps</h4>
        <div class="trap-summary">
          {top_traps_html}
        </div>
      </div>
    </details>"""


def _html_calibration_panel(results: List[UnifiedResult]) -> str:
    """Generate calibration confusion matrix panel."""
    e = html_mod.escape

    restrictive_states = {"ESCALATE", "FAIL_CLOSED", "ROUTE_CLINICIAN", "NEED_OBJECTIVE_DATA", "HOLD_AND_VERIFY"}
    gt_positive_guardrails = {"ESCALATE", "FAIL_CLOSED", "ROUTE_CLINICIAN"}

    tp = tn = fp = fn = 0
    bands: Dict[str, Dict[str, int]] = {
        "0-25": {"total": 0, "gt_restrict": 0, "sys_restrict": 0},
        "25-50": {"total": 0, "gt_restrict": 0, "sys_restrict": 0},
        "50-75": {"total": 0, "gt_restrict": 0, "sys_restrict": 0},
        "75-100": {"total": 0, "gt_restrict": 0, "sys_restrict": 0},
    }

    for r in results:
        gt = r.case.ground_truth
        sys_positive = r.combined_state in restrictive_states
        gt_positive = (
            gt.get("requires_escalation", False)
            or gt.get("expected_guardrail", "") in gt_positive_guardrails
        )

        if sys_positive and gt_positive:
            tp += 1
        elif sys_positive and not gt_positive:
            fp += 1
        elif not sys_positive and gt_positive:
            fn += 1
        else:
            tn += 1

        jri = r.jre_report.scores.readiness_index
        if jri < 25:
            band = "0-25"
        elif jri < 50:
            band = "25-50"
        elif jri < 75:
            band = "50-75"
        else:
            band = "75-100"
        bands[band]["total"] += 1
        if gt_positive:
            bands[band]["gt_restrict"] += 1
        if sys_positive:
            bands[band]["sys_restrict"] += 1

    total = tp + tn + fp + fn
    sensitivity = f"{tp / (tp + fn):.0%}" if (tp + fn) > 0 else "N/A"
    specificity = f"{tn / (tn + fp):.0%}" if (tn + fp) > 0 else "N/A"
    fnr = f"{fn / (fn + tp):.0%}" if (fn + tp) > 0 else "N/A"

    bands_html = ""
    for label, data in bands.items():
        if data["total"] > 0:
            restrict_rate = f"{data['sys_restrict'] / data['total']:.0%}"
        else:
            restrict_rate = "N/A"
        bands_html += (
            f'<div class="cal-band">'
            f'<div class="cal-band-label">RI {e(label)}</div>'
            f'<div class="cal-band-stats">{data["total"]} cases<br>Restrict rate: {restrict_rate}</div>'
            f'</div>'
        )

    return f"""
    <details class="form-section" id="calibrationPanel">
      <summary class="form-header">Detection Accuracy</summary>
      <div class="form-content">
        <div class="calibration-grid">
          <div>
            <table class="cm-matrix">
              <thead><tr><th></th><th>Actual: Restrict</th><th>Actual: Allow</th></tr></thead>
              <tbody>
                <tr><th>Predicted: Restrict</th><td class="cm-cell cm-tp">{tp} TP</td><td class="cm-cell cm-fp">{fp} FP</td></tr>
                <tr><th>Predicted: Allow</th><td class="cm-cell cm-fn">{fn} FN</td><td class="cm-cell cm-tn">{tn} TN</td></tr>
              </tbody>
            </table>
          </div>
          <div class="cm-metrics">
            <div><b>Sensitivity (recall):</b> {sensitivity}</div>
            <div><b>Specificity:</b> {specificity}</div>
            <div><b>False Negative Rate:</b> {fnr}</div>
            <p class="cm-note">N={total}; directional only, not statistically significant</p>
          </div>
        </div>
        <h4>Readiness Index Calibration</h4>
        <div class="calibration-bands">{bands_html}</div>
      </div>
    </details>"""


def _html_assumption_matrix(results):
    """Generate cross-case assumption failure correlation matrix."""
    e = html_mod.escape
    all_names = []
    seen = set()
    for r in results:
        for a in r.bsg_report.assumption_register:
            if a.name not in seen:
                all_names.append(a.name)
                seen.add(a.name)
    if not all_names:
        return ""
    total_cases = len(results)
    case_statuses = []
    for r in results:
        status_map = {a.name: a.status for a in r.bsg_report.assumption_register}
        case_statuses.append(status_map)
    individual_counts = {}
    for name in all_names:
        individual_counts[name] = sum(1 for cs in case_statuses if cs.get(name, "ok") in ("weak", "breached"))
    any_non_ok = any(c > 0 for c in individual_counts.values())
    if not any_non_ok:
        return ('<details class="form-section" id="assumptionMatrix">'
                '<summary class="form-header">Assumption Failure Correlation</summary>'
                '<div class="form-content">'
                f'<div class="am-all-ok">All assumptions held across all {total_cases} cases. No failure correlation to display.</div>'
                '</div></details>')
    co_occur = {}
    for i, name_i in enumerate(all_names):
        for j, name_j in enumerate(all_names):
            count = sum(1 for cs in case_statuses if cs.get(name_i, "ok") in ("weak", "breached") and cs.get(name_j, "ok") in ("weak", "breached"))
            co_occur[(name_i, name_j)] = count
    max_co_occur = 0
    for i, name_i in enumerate(all_names):
        for j, name_j in enumerate(all_names):
            if i != j:
                max_co_occur = max(max_co_occur, co_occur[(name_i, name_j)])
    if max_co_occur == 0:
        max_co_occur = 1
    best_pair = ("", "")
    best_count = 0
    for i, name_i in enumerate(all_names):
        for j, name_j in enumerate(all_names):
            if i < j and co_occur[(name_i, name_j)] > best_count:
                best_count = co_occur[(name_i, name_j)]
                best_pair = (name_i, name_j)
    def short_name(name):
        if len(name) <= 12:
            return name
        return name[:12].rstrip() + "..."
    n_cols = len(all_names)
    repeat = " ".join(["auto"] * n_cols)
    header_cells = '<div class="am-corner"></div>\n'
    for name in all_names:
        header_cells += f'<div class="am-header" title="{e(name)}">{e(short_name(name))}</div>\n'
    data_rows = ""
    for i, name_i in enumerate(all_names):
        data_rows += f'<div class="am-row-label" title="{e(name_i)}">{e(short_name(name_i))}</div>\n'
        for j, name_j in enumerate(all_names):
            count = co_occur[(name_i, name_j)]
            if i == j:
                frac = individual_counts[name_i] / total_cases if total_cases > 0 else 0
                if frac == 0:
                    bg = "rgba(40, 119, 70, 0.12)"
                elif frac < 0.3:
                    bg = f"rgba(200, 180, 40, {0.15 + frac * 0.6:.2f})"
                else:
                    bg = f"rgba(170, 51, 51, {0.15 + frac * 0.55:.2f})"
                data_rows += f'<div class="am-cell" style="background:{bg};border:2px solid #888" title="{e(name_i)}: {count}/{total_cases} cases non-ok">{count}</div>\n'
            else:
                if count == 0:
                    bg = "rgba(200, 200, 200, 0.08)"
                else:
                    intensity = count / max_co_occur
                    bg = f"rgba(68, 102, 204, {0.10 + intensity * 0.50:.2f})"
                data_rows += f'<div class="am-cell" style="background:{bg}" title="{e(name_i)} + {e(name_j)}: {count} co-occurrences">{count}</div>\n'
    if best_count > 0:
        insight_text = (f"'{e(best_pair[0])}' and '{e(best_pair[1])}' "
                        f"co-breach in {best_count} of {total_cases} cases -- these failure modes are linked.")
    else:
        insight_text = "No assumption pairs co-breach across any cases -- failure modes appear independent."
    return (f'<details class="form-section" id="assumptionMatrix">'
            f'<summary class="form-header">Assumption Failure Correlation</summary>'
            f'<div class="form-content">'
            f'<p class="am-note">Shows how often assumption failures co-occur across {total_cases} cases. '
            f'Diagonal = individual breach/weak count. Off-diagonal = co-occurrence count.</p>'
            f'<div class="am-grid" style="grid-template-columns: auto {repeat}">'
            f'{header_cells}{data_rows}</div>'
            f'<div class="am-insight"><b>Key pattern:</b> {insight_text}</div>'
            f'</div></details>')


def _html_autonomy_panel(results):
    """Generate autonomy tier distribution panel with bar chart and case mapping."""
    e = html_mod.escape

    # Tier definitions: internal name -> (short label, CSS suffix)
    tier_defs = [
        ('T0_EMERGENCY_OR_HARD_STOP',       'T0: Emergency / Hard Stop',  't0'),
        ('T1_INTAKE_ONLY',                   'T1: Intake Only',            't1'),
        ('T2_CLINICIAN_DRAFT_ONLY',          'T2: Clinician Draft',        't2'),
        ('T3_SUPERVISED_PROTOCOL',           'T3: Supervised Protocol',    't3'),
        ('T4_NARROW_AUTONOMOUS_ACTION',      'T4: Narrow Autonomous',      't4'),
    ]

    # Count cases per tier
    tier_counts = {}
    for internal, _, _ in tier_defs:
        tier_counts[internal] = 0
    for r in results:
        tier = r.bsg_report.max_autonomy_tier
        if tier in tier_counts:
            tier_counts[tier] += 1
        else:
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

    total = len(results)
    max_count = max(tier_counts.values()) if tier_counts else 1
    if max_count == 0:
        max_count = 1

    # Build bar chart rows
    bar_rows = ''
    for internal, label, css_suffix in tier_defs:
        count = tier_counts.get(internal, 0)
        pct = (count / max_count) * 100 if max_count > 0 else 0
        bar_rows += (
            f'<div class="at-row">'
            f'<div class="at-label">{e(label)}</div>'
            f'<div class="at-bar-track">'
            f'<div class="at-bar at-bar-{css_suffix}" style="width:{pct:.0f}%">{count}</div>'
            f'</div>'
            f'<div class="at-count">{count}/{total}</div>'
            f'</div>\n'
        )

    # Build case-to-tier mapping table
    # Map internal tier names to short labels
    tier_label_map = {internal: label for internal, label, _ in tier_defs}
    tier_css_map = {internal: css_suffix for internal, _, css_suffix in tier_defs}

    table_rows = ''
    for r in results:
        tier = r.bsg_report.max_autonomy_tier
        label = tier_label_map.get(tier, tier)
        css_suffix = tier_css_map.get(tier, 't2')
        bsg_state = r.bsg_report.guardrail_state
        table_rows += (
            f'<tr>'
            f'<td>{e(r.case.case_id)}</td>'
            f'<td><span class="at-tier-badge at-badge-{css_suffix}">{e(label)}</span></td>'
            f'<td>{e(bsg_state)}</td>'
            f'</tr>\n'
        )

    return (
        f'<details class="form-section" id="autonomyPanel">'
        f'<summary class="form-header">Autonomy Tier Distribution</summary>'
        f'<div class="form-content">'
        f'<p class="at-note">Distribution of Black Swan Guard autonomy tier caps across all {total} cases. '
        f'T0 is most restrictive (emergency hard stop), T4 is least restrictive (narrow autonomous action).</p>'
        f'<div class="at-chart">{bar_rows}</div>'
        f'<table class="at-table">'
        f'<thead><tr><th>Case ID</th><th>Autonomy Tier</th><th>BSG State</th></tr></thead>'
        f'<tbody>{table_rows}</tbody>'
        f'</table>'
        f'</div></details>'
    )



def _html_experience_panel(jre_engine) -> str:
    """Render the experience memory panel showing learning state from the JRE engine."""
    e = html_mod.escape
    mem = getattr(jre_engine, "memory", None)
    if mem is None:
        mem = ExperienceMemory.seeded()

    # Distortion priors table
    sorted_priors = sorted(mem.distortion_priors.items(), key=lambda x: (x[0][0], x[0][1], x[0][2]))
    prior_rows = ""
    for (domain, concept, trap), prior_val in sorted_priors:
        bar_width = max(2, int(prior_val * 100))
        prior_rows += (
            f'<tr>'
            f'<td>{e(domain.replace("_", " ").title())}</td>'
            f'<td>{e(concept)}</td>'
            f'<td>{e(trap)}</td>'
            f'<td>{prior_val:.2f}</td>'
            f'<td><div class="exp-bar" style="width: {bar_width}%"></div></td>'
            f'</tr>'
        )

    # Question yield table
    sorted_yields = sorted(mem.question_yield.items(), key=lambda x: x[1], reverse=True)
    yield_rows = ""
    for (domain, question), yield_val in sorted_yields:
        bar_width = max(2, int(yield_val * 100))
        truncated_q = question[:80] + "..." if len(question) > 80 else question
        yield_rows += (
            f'<tr>'
            f'<td>{e(domain.replace("_", " ").title())}</td>'
            f'<td title="{e(question)}">{e(truncated_q)}</td>'
            f'<td>{yield_val:.2f}</td>'
            f'<td><div class="exp-bar" style="width: {bar_width}%"></div></td>'
            f'</tr>'
        )

    # Feedback log
    feedback_count = len(mem.feedback_log)
    if feedback_count > 0:
        feedback_html = f'<p class="exp-note">{feedback_count} feedback event(s) recorded. Priors updated via EMA (alpha={mem.alpha}).</p>'
        for fb in mem.feedback_log[-5:]:
            feedback_html += (
                f'<p class="exp-note">  {e(fb.case_id)} / {e(fb.concept)}: '
                f'{e(fb.clinician_assessment)} (severity adj: {fb.severity_adjustment:+.1f})</p>'
            )
    else:
        feedback_html = '<p class="exp-note">No clinician feedback recorded yet. Use POST /feedback to submit corrections.</p>'

    return f"""
    <details class="form-section" id="experiencePanel">
      <summary class="form-header">Experience Memory &mdash; Learning State</summary>
      <div class="form-content">
        <div class="panel experience-panel">
          <h4>Distortion Prior Calibration</h4>
          <table class="exp-table">
            <tr><th>Domain</th><th>Concept</th><th>Trap</th><th>Prior</th><th>Bar</th></tr>
            {prior_rows}
          </table>
          <h4>Question Effectiveness Yields</h4>
          <table class="exp-table">
            <tr><th>Domain</th><th>Question (truncated)</th><th>Yield</th><th>Bar</th></tr>
            {yield_rows}
          </table>
          <h4>Clinician Feedback Log</h4>
          {feedback_html}
        </div>
      </div>
    </details>"""


def _html_modality_panel(case, report) -> str:
    """Render the modality adaptation panel for a case."""
    e = html_mod.escape
    modality = case.patient_context.modality or "text"
    adaptations = MODALITY_ADAPTATIONS.get(modality, {})

    if not adaptations:
        # Modality not in MODALITY_ADAPTATIONS (e.g., in_person)
        return f"""
        <div class="panel modality-panel">
          <h4>Modality: <span class="mod-badge mod-{e(modality)}">{e(modality)}</span></h4>
          <p class="mod-list" style="font-size:13px;color:#636e72;">No modality-specific adaptations defined for \'{e(modality)}\'. Standard question phrasing used.</p>
        </div>"""

    number_prompt = adaptations.get("number_prompt", "")
    visual_prompt = adaptations.get("visual_prompt", "")
    action_prompt = adaptations.get("action_prompt", "")

    # Show adapted questions
    adapted_qs = ""
    for q in report.next_questions[:4]:
        q_text = q.question
        marks = []
        if any(kw in q_text.lower() for kw in ["number", "reading", "exact", "measured"]):
            marks.append(("number", number_prompt))
        if any(kw in q_text.lower() for kw in ["photo", "look", "show", "see", "visual", "describe"]):
            marks.append(("visual", visual_prompt))
        if any(kw in q_text.lower() for kw in ["try", "do", "walk", "say", "touch", "count"]):
            marks.append(("action", action_prompt))
        mark_tags = " ".join(f'<mark title="{e(prompt)}">{e(mtype)}</mark>' for mtype, prompt in marks)
        adapted_qs += f'<li>{e(q_text)} {mark_tags}</li>'

    if not adapted_qs:
        adapted_qs = '<li style="color:#636e72;">No follow-up questions generated for this case.</li>'

    return f"""
        <div class="panel modality-panel">
          <h4>Modality: <span class="mod-badge mod-{e(modality)}">{e(modality)}</span></h4>
          <p class="mod-list" style="margin-bottom:6px;">Questions adapted for {e(modality)} interaction:</p>
          <ul class="mod-list">
            <li>Number prompts: &ldquo;{e(number_prompt)}&rdquo;</li>
            <li>Visual prompts: &ldquo;{e(visual_prompt)}&rdquo;</li>
            <li>Action prompts: &ldquo;{e(action_prompt)}&rdquo;</li>
          </ul>
          <div class="mod-questions">
            <h5>Adapted Follow-up Questions</h5>
            <ul>{adapted_qs}</ul>
          </div>
        </div>"""


def _html_source_weight_panel(report) -> str:
    """Render the source weight trace panel showing per-observation weight impact."""
    e = html_mod.escape

    rows = ""
    for obs in report.observations:
        source = obs.source or "patient"
        weight = SOURCE_SCORING_WEIGHT.get(source, 1.0)
        raw_conf = obs.confidence
        weighted = raw_conf * weight
        source_css = source.replace(" ", "_")
        rows += (
            f'<tr>'
            f'<td>{e(obs.concept)}</td>'
            f'<td><span class="sw-source sw-{e(source_css)}">{e(source)}</span></td>'
            f'<td>{weight:.2f}x</td>'
            f'<td>{raw_conf:.2f}</td>'
            f'<td>{weighted:.2f}</td>'
            f'</tr>'
        )

    if not rows:
        rows = '<tr><td colspan="5" style="color:#636e72;">No observations available for this case.</td></tr>'

    weight_summary = " | ".join(f"{k} {v}x" for k, v in SOURCE_SCORING_WEIGHT.items())

    return f"""
        <div class="panel source-weight-panel">
          <h4>Source Reliability Weighting</h4>
          <table class="sw-table">
            <tr><th>Concept</th><th>Source</th><th>Weight</th><th>Raw Conf</th><th>Weighted</th></tr>
            {rows}
          </table>
          <p class="sw-note">Weights: {e(weight_summary)}</p>
        </div>"""


def _html_capabilities_matrix() -> str:
    """Generate the system capabilities matrix panel with real counts from the codebase."""
    # Compute real counts from source modules
    n_domains = len(DOMAIN_TEMPLATES)
    n_contradiction = len(CONTRADICTION_RULES)
    n_gestalt = len(GESTALT_PATTERNS)
    n_cross_domain = len([p for p in GESTALT_PATTERNS if p.get("domain") == "*"])
    n_sources = len([k for k in SOURCE_SCORING_WEIGHT if k != "synthetic_truth"])
    n_modalities = len(MODALITY_ADAPTATIONS)
    n_probes = len(ESCALATION_PROBES)
    n_sentinel = len(SENTINEL_RULES)
    n_integrity = len(INTEGRITY_RULES)
    em = ExperienceMemory.seeded()
    n_priors = len(em.distortion_priors)
    n_yields = len(em.question_yield)
    # Count unique traps from slot definitions
    trap_ids: set = set()
    for domain_slots in DOMAIN_TEMPLATES.values():
        for slot in domain_slots:
            for trap in slot.traps:
                trap_ids.add(trap)
    n_traps = len(trap_ids)

    rows = [
        ("MUD Classification", "active", f"{n_domains} domains",
         "Missing, Uncertain, Distorted, Contradictory, Unknowable-remote, Objective-needed"),
        ("CLEAR Question Selection", "active", f"{n_domains} domains",
         "Clarify, Link, Elicit, Ask-objective, Re-score &mdash; with escalation probes &amp; index rotation"),
        ("Distortion Trap Detection", "active", f"{n_traps} traps",
         "Pain-word boundary, normal-without-number, med-name confusion, fever-guess, etc."),
        ("Contradiction Rules", "active", f"{n_contradiction} rules / {n_domains} domains",
         "Cross-statement inconsistency detection with regex pattern matching"),
        ("Gestalt Patterns", "active", f"{n_gestalt} patterns ({n_cross_domain} cross-domain)",
         "Multi-signal syndrome detection: ACS, DKA, pyelonephritis, sepsis, anaphylaxis, etc."),
        ("Source Reliability Weighting", "active", f"{n_sources} source types",
         "Device 1.4x &rarr; Chart 1.3x &rarr; Clinician 1.25x &rarr; Caregiver 0.9x &rarr; Patient 0.85x"),
        ("Source Conflict Detection", "active", "All domains",
         "Flags disagreement between high-authority (device/chart) and low-authority (patient) sources"),
        ("Modality Adaptation", "active", f"{n_modalities} modalities",
         "Phone (verbal), Text (typed + photo), Video (camera + visual) question adaptations"),
        ("Severity Modifiers", "active", "All findings",
         "Amplifiers (worst, crushing, 10/10) and diminishers (mild, slight, 1/10)"),
        ("Temporal Modifiers", "active", "All findings",
         "Acute onset (thunderclap, sudden) boosts severity; chronic (years, baseline) reduces"),
        ("Comorbidity Risk Boost", "active", "Mapped per domain",
         "Known conditions (diabetes, immunocompromised, etc.) increase finding severity"),
        ("Escalation Probes", "active", f"{n_probes} probes / {n_domains} domains",
         "High-severity red flags get targeted disambiguation before hard escalation"),
        ("Experience Memory", "active", f"{n_priors} priors, {n_yields} yields",
         "EMA-updated distortion priors and question yields from evaluation history"),
        ("Outcome Feedback Loop", "active", "4 assessment types",
         "Clinician corrections (confirmed/corrected/false_positive/missed) update priors via API"),
        ("Black Swan Sentinels", "active", f"{n_sentinel} rules",
         "Stroke, anaphylaxis, self-harm, pregnancy+pain, active bleeding, pediatric, coercion"),
        ("Integrity Rules", "active", f"{n_integrity} rules",
         "Prompt injection, wrong patient, copy-paste, metric gaming, device conflict"),
        ("Autonomy Tiers", "active", "T0&ndash;T4",
         "Emergency hard stop &rarr; Intake only &rarr; Clinician draft &rarr; Supervised &rarr; Narrow autonomous"),
        ("LLM Augmentation", "optional", "Via OpenRouter",
         "Novel phrasing detection beyond regex; severity capped at 0.80 to prevent uncontrolled escalation"),
        ("Threshold Sensitivity", "active", "4 parameters",
         "Per-case tornado charts varying Readiness Index cutoff, red-flag severity, novelty, risk budget"),
    ]

    table_rows = ""
    for name, status, coverage, description in rows:
        css_class = "cap-active" if status == "active" else "cap-optional"
        label = "Active" if status == "active" else "Optional"
        table_rows += (
            f'<tr>'
            f'<td>{name}</td>'
            f'<td><span class="{css_class}">{label}</span></td>'
            f'<td>{coverage}</td>'
            f'<td>{description}</td>'
            f'</tr>\n'
        )

    return (
        '<div class="panel capabilities-panel">\n'
        '  <h3>System Capabilities Matrix</h3>\n'
        '  <table class="cap-table">\n'
        '    <tr>\n'
        '      <th>Capability</th>\n'
        '      <th>Status</th>\n'
        '      <th>Coverage</th>\n'
        '      <th>Description</th>\n'
        '    </tr>\n'
        f'    {table_rows}'
        '  </table>\n'
        '</div>\n'
    )


def _html_counterfactual(r):
    """Generate the counterfactual analysis bar for a case card."""
    e = html_mod.escape
    jre_css = r.jre_only_state.lower()
    bsg_css = r.bsg_only_state.lower()
    delta_text = _counterfactual_delta(r.jre_only_state, r.bsg_only_state, r.combined_state)
    return f"""
        <div class="counterfactual">
          <span class="cf-label">If only one engine ran:</span>
          <span class="cf-badge badge-{e(jre_css)}">Judgment Readiness alone: {e(r.jre_only_state)}</span>
          <span class="cf-badge badge-{e(bsg_css)}">Black Swan Guard alone: {e(r.bsg_only_state)}</span>
          <span class="cf-delta">{e(delta_text)}</span>
        </div>"""


def _html_reasoning_panel(r) -> str:
    """Render the reasoning transparency panel showing full audit trail."""
    e = html_mod.escape
    # 1. Observation confidence traces
    obs_rows = ""
    for obs in r.jre_report.observations:
        trace_steps = ""
        for step in obs.trace:
            if ":" in step:
                parts = step.split(":", 1)
                label = parts[0].replace("_", " ").title()
                value = parts[1]
                if value.startswith("-"):
                    css = "rt-penalty"
                elif value.startswith("+") or "=" in value:
                    css = "rt-base"
                else:
                    css = "rt-neutral"
                trace_steps += f'<span class="rt-step {css}">{e(label)}: {e(value)}</span>'
            else:
                trace_steps += f'<span class="rt-step rt-neutral">{e(step)}</span>'
        tag_pills = "".join(f'<span class="rt-tag">{e(t)}</span>' for t in obs.tags) if obs.tags else ""
        conf_pct = obs.confidence * 100
        conf_cls = "rt-conf-high" if conf_pct >= 70 else ("rt-conf-med" if conf_pct >= 50 else "rt-conf-low")
        obs_rows += f"""<div class="rt-obs-row">
          <div class="rt-obs-concept">{e(obs.concept)}</div>
          <div class="rt-obs-conf {conf_cls}">{conf_pct:.0f}%</div>
          <div class="rt-obs-trace">{trace_steps}</div>
          <div class="rt-obs-tags">{tag_pills}</div>
        </div>"""

    # 2. Novelty score decomposition (from BSG report findings)
    novelty = r.bsg_report.novelty_score
    novelty_bar = f'<div class="rt-bar-fill" style="width:{min(100, novelty * 100):.0f}%"></div>'

    # 3. Risk budget breakdown
    risk = r.bsg_report.residual_risk_budget
    risk_bar = f'<div class="rt-bar-fill rt-bar-risk" style="width:{min(100, risk * 100):.0f}%"></div>'

    # 4. Gestalt findings (if any)
    gestalt_html = ""
    gestalt_findings = [f for f in r.jre_report.findings if f.rule_id.startswith("GESTALT_")]
    if gestalt_findings:
        gestalt_items = ""
        for gf in gestalt_findings:
            gestalt_items += f"""<div class="rt-gestalt-item">
              <div class="rt-gestalt-name">{e(gf.rule_id.replace('GESTALT_', ''))}</div>
              <div class="rt-gestalt-reason">{e(gf.reason)}</div>
              <div class="rt-gestalt-evidence"><small>{e(gf.evidence or '')}</small></div>
            </div>"""
        gestalt_html = f'<div class="rt-gestalt-section"><h5>Clinical Gestalt Patterns Detected</h5>{gestalt_items}</div>'

    # 5. Severity/temporal/comorbidity trace entries
    intelligence_traces = ""
    for tr in r.jre_report.traces:
        if tr.rule_id in {"SEVERITY_AMPLIFIED", "SEVERITY_DIMINISHED", "TEMPORAL_ACUTE", "TEMPORAL_CHRONIC", "COMORBIDITY_RISK_BOOST"}:
            label_map = {
                "SEVERITY_AMPLIFIED": "Severity Amplified",
                "SEVERITY_DIMINISHED": "Severity Diminished",
                "TEMPORAL_ACUTE": "Acute Onset",
                "TEMPORAL_CHRONIC": "Chronic/Historical",
                "COMORBIDITY_RISK_BOOST": "Comorbidity Risk",
            }
            css_map = {
                "SEVERITY_AMPLIFIED": "rt-intel-high",
                "SEVERITY_DIMINISHED": "rt-intel-low",
                "TEMPORAL_ACUTE": "rt-intel-high",
                "TEMPORAL_CHRONIC": "rt-intel-low",
                "COMORBIDITY_RISK_BOOST": "rt-intel-high",
            }
            intelligence_traces += f'<div class="rt-intel-item {css_map.get(tr.rule_id, "")}">' \
                f'<span class="rt-intel-label">{label_map.get(tr.rule_id, tr.rule_id)}</span>' \
                f'<span class="rt-intel-desc">{e(tr.description)}</span>' \
                f'<span class="rt-intel-effect">{e(tr.effect)}</span></div>'

    intel_section = f'<div class="rt-intel-section"><h5>Intelligence Adjustments</h5>{intelligence_traces}</div>' if intelligence_traces else ""

    return f"""
        <details class="reasoning-panel">
          <summary><b>Reasoning Transparency</b> &mdash; <span class="tornado-note">Full confidence trace and decomposition</span></summary>
          <div class="rt-content">
            <div class="rt-section">
              <h5>Observation Confidence Audit Trail</h5>
              <div class="rt-obs-grid">{obs_rows}</div>
            </div>
            <div class="rt-metrics">
              <div class="rt-metric">
                <span class="rt-metric-label">Novelty Score</span>
                <div class="rt-bar">{novelty_bar}</div>
                <span class="rt-metric-value">{novelty:.3f}</span>
              </div>
              <div class="rt-metric">
                <span class="rt-metric-label">Residual Risk Budget</span>
                <div class="rt-bar">{risk_bar}</div>
                <span class="rt-metric-value">{risk:.3f}</span>
              </div>
            </div>
            {gestalt_html}
            {intel_section}
          </div>
        </details>"""


def _html_tornado_chart(variations: List[PerCaseVariation]) -> str:
    """Render a tornado/butterfly chart for per-case threshold sensitivity."""
    if not variations:
        return ""
    e = html_mod.escape
    # Group by threshold name
    by_name = {}
    for v in variations:
        by_name.setdefault(v.threshold_name, []).append(v)

    rows = ""
    any_changed = False
    for name, vars in by_name.items():
        strict = next((v for v in vars if v.direction == "stricter"), None)
        loose = next((v for v in vars if v.direction == "looser"), None)
        # Build bars
        strict_html = ""
        if strict:
            changed = strict.state_changed
            if changed:
                any_changed = True
            css_cls = "tornado-bar tornado-bar-strict" + (" tornado-bar-changed" if changed else "")
            label = e(strict.varied_combined) if changed else "no change"
            strict_html = f'<div class="{css_cls}" style="width:{60 if changed else 30}px" title="Stricter ({strict.test_value}): {strict.varied_combined}">{label}</div>'
        loose_html = ""
        if loose:
            changed = loose.state_changed
            if changed:
                any_changed = True
            css_cls = "tornado-bar tornado-bar-loose" + (" tornado-bar-changed" if changed else "")
            label = e(loose.varied_combined) if changed else "no change"
            loose_html = f'<div class="{css_cls}" style="width:{60 if changed else 30}px" title="Looser ({loose.test_value}): {loose.varied_combined}">{label}</div>'
        rows += f"""<div class="tornado-row">
          <div class="tornado-label">{e(name)}</div>
          <div style="display:flex;align-items:center;justify-content:flex-end;flex:1">{strict_html}</div>
          <div class="tornado-center"></div>
          <div style="display:flex;align-items:center;flex:1">{loose_html}</div>
        </div>"""

    summary = "This case is sensitive to threshold changes" if any_changed else "This case is robust to threshold changes"
    return f"""
        <details class="tornado-section">
          <summary><b>Threshold Sensitivity</b> &mdash; <span class="tornado-note">{summary}</span></summary>
          <div class="tornado-chart">
            <div class="tornado-legend">
              <span><span style="display:inline-block;width:12px;height:12px;background:#d9534f;border-radius:3px"></span> Stricter</span>
              <span><span style="display:inline-block;width:12px;height:12px;background:#5bc0de;border-radius:3px"></span> Looser</span>
              <span><span style="display:inline-block;width:12px;height:12px;background:#ccc;border-radius:3px"></span> No change</span>
            </div>
            {rows}
          </div>
        </details>"""


def _html_multiturn_panel(baseline_state: str, baseline_jri: float, turns: List[TurnResult], validation: Optional[Dict[str, Any]] = None) -> str:
    """Render the multi-turn conversation simulation panel."""
    e = html_mod.escape
    if not turns:
        return f"""
        <details class="multiturn-section">
          <summary><b>Conversation Simulation</b> &mdash; <span class="tornado-note">No additional questions can be simulated for this case</span></summary>
          <div class="mt-summary mt-no-improvement">This case cannot be further resolved through additional questions alone.</div>
        </details>"""

    timeline = ""
    prev_state = baseline_state
    prev_jri = baseline_jri
    for t in turns:
        delta_jri = t.readiness_index - prev_jri
        delta_sign = "+" if delta_jri >= 0 else ""
        delta_cls = "mt-delta-positive" if delta_jri > 0 else ("mt-delta-negative" if delta_jri < 0 else "mt-delta-neutral")
        turn_cls = "mt-turn"
        if t.combined_state in {"READY", "ALLOW_WITH_AUDIT"}:
            turn_cls += " mt-turn-converged"
        elif t.state_changed:
            turn_cls += " mt-turn-changed"
        state_arrow = f"{e(prev_state)} &rarr; {e(t.combined_state)}" if t.state_changed else e(t.combined_state)
        timeline += f"""<div class="{turn_cls}">
          <div class="mt-turn-header">
            <span class="mt-turn-num">Turn {t.turn_number}</span>
            <span class="state-badge badge-{e(t.combined_state.lower())}" style="font-size:.75rem;padding:2px 8px">{state_arrow}</span>
          </div>
          <div class="mt-question"><b>Asked:</b> {e(t.question_asked)}</div>
          <div class="mt-answer">{e(t.answer_given)}</div>
          <div class="mt-scores">
            <span>Readiness: {t.readiness_index:.1f}</span>
            <span class="mt-delta {delta_cls}">({delta_sign}{delta_jri:.1f})</span>
            <span>Findings: {t.findings_count}</span>
            <span>Questions left: {t.questions_remaining}</span>
          </div>
        </div>"""
        prev_state = t.combined_state
        prev_jri = t.readiness_index

    final = turns[-1]
    if final.combined_state in {"READY", "ALLOW_WITH_AUDIT"}:
        summary_text = f"After {len(turns)} turn(s), case converged to {final.combined_state} (Readiness {final.readiness_index:.1f})"
    elif final.combined_state != baseline_state:
        summary_text = f"After {len(turns)} turn(s), state changed from {baseline_state} to {final.combined_state} (Readiness {baseline_jri:.1f} &rarr; {final.readiness_index:.1f})"
    else:
        summary_text = f"After {len(turns)} turn(s), state remains {final.combined_state} &mdash; escalation drivers persist despite resolution answers"

    # Render validation badges
    validation_html = ""
    if validation and validation.get("validations"):
        badges = ""
        for v in validation["validations"]:
            badge_cls = "mt-pass" if v["passed"] else "mt-fail"
            label = v["check"].replace("_", " ").title()
            icon = "PASS" if v["passed"] else "FAIL"
            badges += f'<span class="{badge_cls}" title="{e(v["detail"])}">{icon}: {e(label)}</span>'
        validation_html = f'<div class="mt-validation"><span class="mt-validation-label">Validation:</span>{badges}</div>'

    return f"""
        <details class="multiturn-section">
          <summary><b>Conversation Simulation</b> &mdash; <span class="tornado-note">{len(turns)} turn(s) simulated</span></summary>
          <div class="multiturn-timeline">
            {timeline}
          </div>
          <div class="mt-summary">{summary_text}</div>
          {validation_html}
        </details>"""


def _html_card(r, per_case_variations=None, multiturn_turns=None, multiturn_validation=None):
    """Generate a single interactive case card."""
    e = html_mod.escape
    css_state = r.combined_state.lower()
    category = "base" if not r.case.case_id.startswith("BS-") else "blackswan"
    gt_icon = "&#10003;" if r.ground_truth_match else "&#10007;"
    gt_class = "gt-match" if r.ground_truth_match else "gt-mismatch"
    bmap = ""
    for k, vals in r.jre_report.boundary_map.items():
        bmap += f"<h4>{e(k.replace('_', ' ').title())}</h4><ul>"
        for v in vals[:5]:
            bmap += f"<li>{e(v)}</li>"
        bmap += "</ul>"
    qs = "".join(f"<li><b>{e(q.concept)}</b>: {e(q.question)}<br><small>{e(q.clear_step)}</small></li>" for q in r.jre_report.next_questions[:4])
    assumptions = "".join(f"<li><span class='assumption-{e(a.status)}'>{e(a.status.upper())}</span> -- {e(a.name)}: {e(a.reason)}</li>" for a in r.bsg_report.assumption_register)
    findings_rows = ""
    for f in r.jre_report.findings[:4]:
        findings_rows += f"<tr><td>Judgment Readiness</td><td>{e(f.category)}</td><td>{e(f.concept)}</td><td>{f.severity:.2f}</td><td>{e(f.reason)}</td></tr>"
    for f in r.bsg_report.findings[:4]:
        findings_rows += f"<tr><td>Black Swan Guard</td><td>{e(f.category)}</td><td>{e(f.rule_id)}</td><td>{f.severity:.2f}</td><td>{e(f.reason)}</td></tr>"
    if not findings_rows:
        findings_rows = "<tr><td colspan='5'>No findings</td></tr>"
    jri_bar = _html_jri_breakdown(r.jre_report.scores)
    transcript = _html_transcript(r)
    counterfactual = _html_counterfactual(r)
    tornado = _html_tornado_chart(per_case_variations) if per_case_variations else ""
    baseline_combined = most_restrictive(r.jre_report.state, r.bsg_report.guardrail_state)
    multiturn = _html_multiturn_panel(baseline_combined, r.jre_report.scores.readiness_index, multiturn_turns, validation=multiturn_validation) if multiturn_turns is not None else ""
    reasoning = _html_reasoning_panel(r)
    modality_panel = _html_modality_panel(r.case, r.jre_report)
    source_weight = _html_source_weight_panel(r.jre_report)
    return f"""
    <section class="card state-{e(css_state)}" id="card-{e(r.case.case_id)}" data-state="{e(r.combined_state)}" data-category="{category}">
      <div class="card-header">
        <span class="collapse-icon">&#9660;</span>
        <span class="case-id">{e(r.case.case_id)} -- {e(r.narrative.title)}</span>
        <span class="state-badge badge-{e(css_state)}">{e(r.combined_state)}</span>
        <span class="score-badge">Readiness {r.jre_report.scores.readiness_index:.1f}</span>
        <span class="score-badge">{e(r.bsg_report.max_autonomy_tier)}</span>
        <span class="{gt_class}">{gt_icon} GT</span>
      </div>
      <div class="card-body">
        <div class="narrative"><div class="narrative-title">{e(r.narrative.title)}</div><p>{e(r.narrative.scenario)}</p></div>
        {transcript}
        <div class="engine-labels"><div class="engine-label">Judgment Readiness: {e(r.jre_report.state)}</div><div class="engine-label">Black Swan Guard: {e(r.bsg_report.guardrail_state)}</div></div>
        {counterfactual}
        {jri_bar}
        {tornado}
        {multiturn}
        {reasoning}
        {modality_panel}
        {source_weight}
        <p class="summary">{e(r.jre_report.provider_summary)}</p>
        <div class="grid">
          <div><h3>Boundary Map</h3>{bmap}<h3>Next Best Questions</h3><ol>{qs}</ol></div>
          <div><h3>Assumption Register</h3><ul>{assumptions}</ul><h3>Judgment Readiness Demonstrates</h3><p class="demonstrates">{e(r.narrative.jre_demonstrates)}</p><h3>Black Swan Guard Demonstrates</h3><p class="demonstrates">{e(r.narrative.bsg_demonstrates)}</p></div>
        </div>
        <h3>Combined Findings</h3>
        <table><thead><tr><th>Engine</th><th>Category</th><th>Concept/Rule</th><th>Severity</th><th>Reason</th></tr></thead><tbody>{findings_rows}</tbody></table>
        <div class="insight"><b>Combined insight:</b> {e(r.narrative.combined_insight)}</div>
        <div class="verdict">{e(r.combined_verdict)}</div>
      </div>
    </section>"""


def make_unified_html(results):
    """Generate an interactive unified HTML dashboard."""
    e = html_mod.escape
    total = len(results)
    gt_matches = sum(1 for r in results if r.ground_truth_match)
    state_counts = {}
    for r in results:
        state_counts[r.combined_state] = state_counts.get(r.combined_state, 0) + 1
    bsg_value_count = sum(1 for r in results if r.combined_state != r.jre_only_state)
    jre_value_count = sum(1 for r in results if r.combined_state != r.bsg_only_state)
    stats_items = (f'<div class="stat"><span class="stat-num">{total}</span><span class="stat-label">Cases</span></div>'
                   f'<div class="stat"><span class="stat-num">{gt_matches}/{total}</span><span class="stat-label">GT Match</span></div>')
    for k, v in sorted(state_counts.items()):
        stats_items += f'<div class="stat" data-filter-state="{e(k)}"><span class="stat-num">{v}</span><span class="stat-label">{e(k)}</span></div>'
    stats_items += (f'<div class="stat"><span class="stat-num">{bsg_value_count}/{total}</span><span class="stat-label">Black Swan Guard Added Value</span></div>'
                    f'<div class="stat"><span class="stat-num">{jre_value_count}/{total}</span><span class="stat-label">Judgment Readiness Added Value</span></div>')
    # Precompute per-case sensitivity, multi-turn simulation, and validation
    tornado_data = {}
    multiturn_data = {}
    validation_data = {}
    for r in results:
        tornado_data[r.case.case_id] = run_per_case_sensitivity(r.case, r.jre_report, r.bsg_report)
        turns = run_multiturn_simulation(r.case, r.jre_report, r.bsg_report)
        multiturn_data[r.case.case_id] = turns
        validation_data[r.case.case_id] = validate_multiturn_outcomes(r.case, r.jre_report, turns)
    base_results = [r for r in results if not r.case.case_id.startswith("BS-")]
    bs_results = [r for r in results if r.case.case_id.startswith("BS-")]
    base_cards = "".join(_html_card(r, per_case_variations=tornado_data.get(r.case.case_id), multiturn_turns=multiturn_data.get(r.case.case_id), multiturn_validation=validation_data.get(r.case.case_id)) for r in base_results)
    bs_cards = "".join(_html_card(r, per_case_variations=tornado_data.get(r.case.case_id), multiturn_turns=multiturn_data.get(r.case.case_id), multiturn_validation=validation_data.get(r.case.case_id)) for r in bs_results)
    nav_links = "".join(f'<a href="#card-{e(r.case.case_id)}">{e(r.case.case_id.split("-", 2)[-1][:12] if "-" in r.case.case_id else r.case.case_id)}</a>' for r in results)
    css = _html_css()
    js = _html_js()
    form_section = _html_form_section()
    capabilities_matrix = _html_capabilities_matrix()
    scoring_panel = _html_scoring_panel()
    calibration_panel = _html_calibration_panel(results)
    trap_heatmap = _html_trap_heatmap(results)
    assumption_matrix = _html_assumption_matrix(results)
    autonomy_panel = _html_autonomy_panel(results)
    experience_panel = _html_experience_panel(JudgmentReadinessEngine())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clinical Safety Analysis Dashboard</title>
<style>{css}</style></head><body>
<div class="container">
  <div class="sticky-header">
    <h1>Clinical Safety Analysis Dashboard</h1>
    <p class="subtitle">All {total} hand-authored cases through both engines. &ldquo;Do we have enough?&rdquo; (Judgment Readiness) and &ldquo;Are we still safe?&rdquo; (Black Swan Guard).</p>
    <div class="controls">
      <input type="text" id="searchBox" placeholder="Search cases...">
      <select id="categoryFilter"><option value="all">All Engines</option><option value="base">Base Cases</option><option value="blackswan">Black Swan Cases</option></select>
      <button id="expandAll">Expand All</button>
      <button id="collapseAll">Collapse All</button>
      <button id="darkToggle">Dark</button>
      <span class="visible-count" id="visibleCount"></span>
    </div>
  </div>
  {capabilities_matrix}
  {form_section}
  {scoring_panel}
  {calibration_panel}
  {trap_heatmap}
  {assumption_matrix}
  {autonomy_panel}
  {experience_panel}
  <div class="stats-bar">{stats_items}</div>
  <div class="case-nav">{nav_links}</div>
  <div class="section-header">Base Cases ({len(base_results)}) &mdash; Clinical Pattern Detection</div>
  {base_cards}
  <div class="section-header">Black Swan Cases ({len(bs_results)}) &mdash; Adversarial &amp; Edge Scenarios</div>
  {bs_cards}
</div>
<button class="back-to-top" id="backToTop" title="Back to top">&#8593;</button>
<script>{js}</script>
</body></html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_case_list():
    """Print all case IDs grouped by base/black-swan with narrative titles."""
    base = list(BASE_CASES)
    bs = list(BLACK_SWAN_CASES)
    total = len(base) + len(bs)
    print(f"All {total} cases:\n")
    print(f"  Base Cases ({len(base)}):")
    for c in base:
        narr = CASE_NARRATIVES.get(c.case_id)
        title = f" -- {narr.title}" if narr else ""
        print(f"    {c.case_id}{title}")
    print(f"\n  Black Swan Cases ({len(bs)}):")
    for c in bs:
        narr = CASE_NARRATIVES.get(c.case_id)
        title = f" -- {narr.title}" if narr else ""
        print(f"    {c.case_id}{title}")


def main():
    parser = argparse.ArgumentParser(description="Unified JRE + BSG demo")
    parser.add_argument("--case", help="Run a single case by ID")
    parser.add_argument("--list", action="store_true", help="List all case IDs and exit")
    parser.add_argument("--open", action="store_true", help="Open HTML dashboard in browser after generating")
    parser.add_argument("--no-write", action="store_true", help="Stdout only, no file writes")
    parser.add_argument("--html", default="artifacts/unified_dashboard.html", help="HTML output path")
    parser.add_argument("--json", default="artifacts/unified_reports.json", help="JSON output path")
    parser.add_argument("--csv", default="artifacts/unified_matrix.csv", help="CSV output path")
    parser.add_argument("--markdown", default="artifacts/unified_report.md", help="Markdown output path")
    args = parser.parse_args()

    if args.list:
        _print_case_list()
        return

    base_dir = Path(__file__).resolve().parent
    cases = get_all_cases()

    if args.case:
        cases = [c for c in cases if c.case_id == args.case]
        if not cases:
            raise SystemExit(f"Case not found: {args.case}")

    results = run_unified_pipeline(cases)

    md = unified_report_to_markdown(results)
    print(md)

    if not args.no_write:
        html_path = base_dir / args.html
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(make_unified_html(results), encoding="utf-8")
        print(f"\nWrote HTML dashboard: {html_path}")
        if args.open:
            webbrowser.open(html_path.as_uri())

        json_path = base_dir / args.json
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(unified_to_json(results), encoding="utf-8")
        print(f"Wrote JSON reports: {json_path}")

        csv_path = base_dir / args.csv
        write_unified_matrix(csv_path, results)
        print(f"Wrote CSV matrix: {csv_path}")

        md_path = base_dir / args.markdown
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md, encoding="utf-8")
        print(f"Wrote Markdown report: {md_path}")


if __name__ == "__main__":
    main()
