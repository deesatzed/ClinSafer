"""Small experiential-learning memory.

This deliberately mirrors the user's CAM-Pulse idea at healthcare scale:
store what worked, retrieve similar patterns, verify outcomes, and learn which
questions reduced uncertainty fastest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple, List


@dataclass
class ExperienceEvent:
    domain: str
    concept: str
    trap: str
    phrase: str
    initial_answer: str
    clarified_truth: str
    question_used: str
    information_gain: float
    outcome_label: str


@dataclass
class OutcomeFeedback:
    """Clinician feedback on a completed evaluation."""
    case_id: str
    concept: str
    domain: str
    clinician_assessment: str  # "confirmed", "corrected", "false_positive", "missed"
    corrected_value: str = ""  # what the clinician determined the real value was
    severity_adjustment: float = 0.0  # positive = was more severe, negative = was less severe
    notes: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            import time
            self.timestamp = time.time()


@dataclass
class ExperienceMemory:
    """Tiny in-memory version of a production outcome-learning store."""

    distortion_priors: Dict[Tuple[str, str, str], float] = field(default_factory=dict)
    question_yield: Dict[Tuple[str, str], float] = field(default_factory=dict)
    events: List[ExperienceEvent] = field(default_factory=list)
    feedback_log: List[OutcomeFeedback] = field(default_factory=list)
    alpha: float = 0.15  # EMA smoothing factor (matches record_event rate)

    @classmethod
    def seeded(cls) -> "ExperienceMemory":
        mem = cls()
        seeds = [
            # --- dyspnea_respiratory ---
            ("dyspnea_respiratory", "exertional_tolerance", "sob_word_boundary", 0.18),
            ("dyspnea_respiratory", "sentence_test", "sob_word_boundary", 0.16),
            # --- chest_discomfort ---
            ("chest_discomfort", "symptom_quality", "pain_word_boundary", 0.20),
            ("chest_discomfort", "symptom_quality", "heartburn_label", 0.13),
            ("chest_discomfort", "dyspnea", "sob_word_boundary", 0.15),
            # --- med_refill_hypertension ---
            ("med_refill_hypertension", "home_bp_number", "normal_without_number", 0.22),
            ("med_refill_hypertension", "last_taken", "adherence_social_desirability", 0.15),
            ("med_refill_hypertension", "medication_identity", "med_name_confusion", 0.17),
            # --- diabetes_hyperglycemia ---
            ("diabetes_hyperglycemia", "glucose_number", "sugar_fine_without_number", 0.25),
            # --- uti_symptoms ---
            ("uti_symptoms", "fever_measured", "fever_guess", 0.16),
            ("uti_symptoms", "flank_pain", "back_pain_boundary", 0.14),
            # --- rash ---
            ("rash", "mucosal_involvement", "rash_boundary", 0.14),
            # --- headache_migraine ---
            ("headache_migraine", "headache_onset", "thunderclap_minimized", 0.20),
            ("headache_migraine", "medication_use", "medication_overuse", 0.12),
            ("headache_migraine", "fever_measured", "fever_guess", 0.15),
            # --- expanded telemedicine coverage ---
            ("adhd_behavioral_med", "medication_identity", "med_name_confusion", 0.17),
            ("general_med_management", "medication_identity", "med_name_confusion", 0.17),
            ("general_med_management", "last_taken", "adherence_social_desirability", 0.15),
            ("uri_sinus_throat", "fever_measured", "fever_guess", 0.16),
            ("vaginal_sti", "fever_measured", "fever_guess", 0.16),
            ("gerd_dyspepsia", "chest_or_exertional", "heartburn_label", 0.15),
            ("skin_infection", "fever_measured", "fever_guess", 0.16),
            ("obesity_metabolic", "medication_identity", "med_name_confusion", 0.17),
        ]
        for key in seeds:
            mem.distortion_priors[(key[0], key[1], key[2])] = key[3]

        # Seed question_yield with differentiated priors based on trap type.
        # Format: (domain, question_text) -> yield estimate
        question_yield_seeds = [
            ("dyspnea_respiratory", "Can you walk from bedroom to kitchen without stopping? Is that worse than your baseline?", 0.72),
            ("dyspnea_respiratory", "Can you say a full sentence out loud without needing to pause for breath?", 0.68),
            ("chest_discomfort", "When you say it is not chest pain, is there pressure, tightness, heaviness, squeezing, burning, or discomfort anywhere in the chest, jaw, arm, back, or upper belly?", 0.75),
            ("chest_discomfort", "Does it feel different from your usual indigestion or reflux?", 0.63),
            # New: chest_discomfort dyspnea slot — sob_word_boundary trap
            ("chest_discomfort", "Can you walk across the room and speak a full sentence without stopping to catch your breath?", 0.70),
            ("chest_discomfort", "Compared with your usual, are you breathing harder with normal activities?", 0.62),
            ("med_refill_hypertension", "When you say your blood pressure is normal, what exact numbers did you get, and when were they measured?", 0.70),
            ("med_refill_hypertension", "When was the last dose you actually swallowed? Today, yesterday, or longer ago?", 0.65),
            # New: med_refill_hypertension medication_identity slot — med_name_confusion trap
            ("med_refill_hypertension", "Please read the exact name and dose from the medication bottle, including how often you take it.", 0.68),
            ("diabetes_hyperglycemia", "What exact glucose number did you get, and was it fasting or after eating?", 0.73),
            ("uti_symptoms", "Have you measured a temperature with a thermometer? What was the highest number?", 0.67),
            # New: uti_symptoms flank_pain slot — back_pain_boundary trap
            ("uti_symptoms", "Any pain in the side of your back below the ribs, especially one-sided?", 0.64),
            ("rash", "Any sores, pain, or rash in the mouth, eyes, lips, genitals, or inside the nose?", 0.60),
            ("headache_migraine", "Did this headache come on suddenly — like a switch being flipped — or did it build up gradually over hours?", 0.71),
            ("headache_migraine", "How often do you take pain medication for headaches? More than 10-15 days per month?", 0.55),
            # New: headache_migraine fever_measured slot — fever_guess trap
            ("headache_migraine", "Have you measured your temperature with a thermometer? What was the number?", 0.66),
        ]
        for domain, question, yield_val in question_yield_seeds:
            mem.question_yield[(domain, question)] = yield_val

        return mem

    def prior_penalty(self, domain: str, concept: str, trap: str) -> float:
        return self.distortion_priors.get((domain, concept, trap), 0.0)

    def record_event(self, event: ExperienceEvent) -> None:
        self.events.append(event)
        key = (event.domain, event.concept, event.trap)
        old = self.distortion_priors.get(key, 0.05)
        # EMA update: if clarification exposed distortion, increase prior.
        target = min(max(event.information_gain, 0.0), 1.0) * 0.35
        self.distortion_priors[key] = (0.85 * old) + (0.15 * target)

        qkey = (event.domain, event.question_used)
        old_q = self.question_yield.get(qkey, 0.5)
        self.question_yield[qkey] = (0.80 * old_q) + (0.20 * event.information_gain)

    def record_feedback(self, feedback: OutcomeFeedback) -> Dict[str, float]:
        """Record clinician feedback and update priors accordingly.

        Returns dict of updated prior values (string keys for serialisation).
        """
        updates: Dict[str, float] = {}

        if feedback.clinician_assessment == "confirmed":
            # Finding was correct -- reinforce current prior (decrease distortion expectation)
            for trap_key, val in list(self.distortion_priors.items()):
                domain, concept, trap = trap_key
                if domain == feedback.domain and concept == feedback.concept:
                    new_val = val * (1 - self.alpha) + 0.0 * self.alpha  # EMA toward 0
                    self.distortion_priors[trap_key] = new_val
                    updates[f"{domain}/{concept}/{trap}"] = new_val

        elif feedback.clinician_assessment == "corrected":
            # Finding existed but value was wrong -- increase distortion prior
            for trap_key, val in list(self.distortion_priors.items()):
                domain, concept, trap = trap_key
                if domain == feedback.domain and concept == feedback.concept:
                    new_val = val * (1 - self.alpha) + 0.5 * self.alpha  # EMA toward 0.5
                    self.distortion_priors[trap_key] = new_val
                    updates[f"{domain}/{concept}/{trap}"] = new_val

        elif feedback.clinician_assessment == "false_positive":
            # Finding was wrong -- strongly decrease distortion prior
            for trap_key, val in list(self.distortion_priors.items()):
                domain, concept, trap = trap_key
                if domain == feedback.domain and concept == feedback.concept:
                    fast_alpha = self.alpha * 2
                    new_val = val * (1 - fast_alpha) + 0.0 * fast_alpha  # Faster EMA toward 0
                    new_val = max(0.01, new_val)  # Floor to prevent zero
                    self.distortion_priors[trap_key] = new_val
                    updates[f"{domain}/{concept}/{trap}"] = new_val

        elif feedback.clinician_assessment == "missed":
            # Something was missed -- increase prior significantly; create if absent
            trap_key = (feedback.domain, feedback.concept, "clinician_feedback")
            old_val = self.distortion_priors.get(trap_key, 0.20)
            fast_alpha = self.alpha * 2
            new_val = old_val * (1 - fast_alpha) + 0.8 * fast_alpha  # Fast EMA toward 0.8
            new_val = min(0.95, new_val)  # Cap
            self.distortion_priors[trap_key] = new_val
            str_key = f"{feedback.domain}/{feedback.concept}/clinician_feedback"
            updates[str_key] = new_val

        # Update question yields based on severity adjustment
        if feedback.severity_adjustment != 0:
            for q_key, val in list(self.question_yield.items()):
                domain, question = q_key
                if domain == feedback.domain:
                    # Higher severity = higher yield expected
                    adjustment = feedback.severity_adjustment * 0.1
                    new_val = max(0.1, min(0.95, val + adjustment))
                    self.question_yield[q_key] = new_val
                    updates[f"yield:{domain}/{question[:60]}"] = new_val

        self.feedback_log.append(feedback)
        return updates

    def expected_question_yield(self, domain: str, question: str) -> float:
        return self.question_yield.get((domain, question), 0.62)
