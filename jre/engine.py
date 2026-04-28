"""Judgment Readiness Engine (JRE)

Purpose
-------
A deterministic, inspectable prototype of an AI safety module for clinical
intake. It treats patient answers as noisy observations, maps missing / uncertain
/ distorted information, and asks the highest-yield next questions before a
system crosses a Judgment Sufficiency Threshold.

This is not medical advice or a clinical protocol. It is a software architecture
prototype for interview/demo purposes.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .experience import ExperienceEvent, ExperienceMemory
from .models import (
    CaseInput,
    Finding,
    NextQuestion,
    Observation,
    PatientContext,
    ReadinessReport,
    ReadinessScores,
    RuleTrace,
    SlotSpec,
    Statement,
)
from .templates import CLEAR_STEPS, CONTRADICTION_RULES, DOMAIN_TEMPLATES, ESCALATION_PROBES, MODALITY_ADAPTATIONS, RED_FLAG_PATTERNS

VAGUE_WORDS = re.compile(r"\b(fine|normal|okay|ok|good|not sure|maybe|kind of|kinda|sometimes|a while|recently|usually|i guess|not really)\b", re.I)
NEGATIVE_WORDS = re.compile(r"\b(no|not|none|deny|denies|never|don't|do not|doesn't|nothing)\b", re.I)
AFFIRM_WORDS = re.compile(r"\b(yes|yeah|yep|sure|some|a little|mild|bad|worse|have|had|started|new)\b", re.I)
NUMBER_RE = re.compile(r"(?<!\d)(\d{2,3})(?:\s*/\s*(\d{2,3}))?(?!\d)")

# ---------------------------------------------------------------------------
# Severity Gradient Modifiers
# ---------------------------------------------------------------------------
SEVERITY_AMPLIFIERS = re.compile(
    r"\b(worst|severe|excruciating|unbearable|crushing|extreme|terrible|awful|"
    r"intense|worst ever|worst of my life|10 out of 10|10/10|9/10|can't bear|"
    r"screaming|crying from|agonizing|writhing|passed out|fainted|collapse)\b", re.I
)
SEVERITY_DIMINISHERS = re.compile(
    r"\b(mild|slight|twinge|tiny|little|faint|minor|barely|subtle|"
    r"1 out of 10|1/10|2/10|3/10|not bad|tolerable|manageable|dull|low.grade)\b", re.I
)

# ---------------------------------------------------------------------------
# Temporal Acuity Patterns
# ---------------------------------------------------------------------------
TEMPORAL_ACUTE = re.compile(
    r"\b(just now|just started|minutes? ago|hours? ago|since breakfast|since this morning|"
    r"since last night|today|tonight|woke up with|sudden|suddenly|came on fast|"
    r"started (?:this|today|tonight|an hour|a few minutes|30 minutes|2 hours)|"
    r"right now|at this moment|all of a sudden|out of nowhere|like a switch)\b", re.I
)
TEMPORAL_CHRONIC = re.compile(
    r"\b(years? ago|months? ago|weeks? ago|for years|for months|for weeks|"
    r"always had|chronic|long time|long.standing|ongoing|on and off for|"
    r"comes and goes for|history of|diagnosed (?:in|back in|years)|"
    r"since (?:20\d{2}|childhood|I was young|last year)|usual|baseline|same as always)\b", re.I
)

# ---------------------------------------------------------------------------
# Clinical Gestalt Patterns (multi-signal syndrome detection)
# ---------------------------------------------------------------------------
GESTALT_PATTERNS = [
    {
        "id": "GESTALT_ACS",
        "name": "Acute Coronary Syndrome Pattern",
        "domain": "chest_discomfort",
        "required_signals": [
            ("symptom_quality", r"pressure|tight|heavy|squeez|crushing"),
            ("exertional_component", r"worse|stairs|walk|activity|exertion|rest helps|better.{0,10}(?:sit|rest|stop)|sit down|gets better"),
        ],
        "supporting_signals": [
            ("diaphoresis", r"sweat|clammy|nausea"),
            ("dyspnea", r"breath|can't|short|stop"),
            ("radiation", r"jaw|arm|shoulder|back"),
        ],
        "severity": 1.0,
        "reason": "Multiple converging signals suggest acute coronary syndrome: exertional chest pressure with associated symptoms forms a clinical pattern greater than any single flag.",
        "min_required": 2,
        "min_supporting": 1,
    },
    {
        "id": "GESTALT_DKA",
        "name": "Diabetic Ketoacidosis Pattern",
        "domain": "diabetes_hyperglycemia",
        "required_signals": [
            ("glucose_number", r"high|[3-9]\d{2}|>300|above|over"),
            ("vomiting", r"vomit|throw up|can't keep|nausea"),
        ],
        "supporting_signals": [
            ("mental_status", r"confus|sleepy|weak|dizzy|not right"),
            ("hydration_status", r"dry|thirst|not urinating|dark urine"),
        ],
        "severity": 1.0,
        "reason": "Hyperglycemia + vomiting with altered mental status or dehydration forms the classic DKA triad. Individual signals may be sub-threshold but the pattern demands immediate evaluation.",
        "min_required": 2,
        "min_supporting": 1,
    },
    {
        "id": "GESTALT_MENINGITIS",
        "name": "Meningitis Triad Pattern",
        "domain": "headache_migraine",
        "required_signals": [
            ("headache_onset", r"worst|sudden|severe|thunder|switch|instant"),
            ("neck_stiffness", r"stiff|can't touch|hurts to bend|pain.*neck"),
        ],
        "supporting_signals": [
            ("fever_measured", r"fever|10[0-9]|high|hot"),
            ("neuro_deficit", r"confus|vision|speech|weak|numb"),
        ],
        "severity": 1.0,
        "reason": "Severe headache + neck stiffness with fever or neurological changes forms the meningitis triad. This pattern requires emergent evaluation regardless of individual signal confidence.",
        "min_required": 2,
        "min_supporting": 0,
    },
    {
        "id": "GESTALT_SEPSIS_UTI",
        "name": "Urosepsis Pattern",
        "domain": "uti_symptoms",
        "required_signals": [
            ("fever_measured", r"fever|10[1-9]|hot|chills"),
            ("flank_pain", r"back|side|flank|kidney"),
        ],
        "supporting_signals": [
            ("vomiting", r"vomit|nausea|can't keep"),
            ("dysuria", r"burn|pain.*urinat"),
        ],
        "severity": 1.0,
        "reason": "Fever + flank pain in a UTI context suggests pyelonephritis or urosepsis. The combination elevates simple UTI to a systemic infection pattern requiring urgent assessment.",
        "min_required": 2,
        "min_supporting": 0,
    },
    {
        "id": "GESTALT_SJS",
        "name": "Stevens-Johnson Syndrome Pattern",
        "domain": "rash",
        "required_signals": [
            ("mucosal_involvement", r"mouth|eye|genital|lip|blister"),
            ("skin_pain", r"hurt|burn|peel|blister|painful"),
        ],
        "supporting_signals": [
            ("fever_measured", r"fever|hot|10[0-9]"),
            ("new_medication", r"new|started|antibiotic|seizure"),
        ],
        "severity": 1.0,
        "reason": "Mucosal involvement + painful skin with fever and recent medication exposure suggests Stevens-Johnson syndrome. This pattern is a dermatologic emergency even if individual findings seem moderate.",
        "min_required": 2,
        "min_supporting": 1,
    },
    {
        "id": "GESTALT_RESP_FAILURE",
        "name": "Respiratory Failure Pattern",
        "domain": "dyspnea_respiratory",
        "required_signals": [
            ("oxygen_saturation", r"low|[78]\d|<90|dropping|88|89|85"),
            ("sentence_test", r"can't|no|stop|pause|few words"),
        ],
        "supporting_signals": [
            ("mental_status", r"confus|sleepy|not right|altered"),
            ("respiratory_rate", r"fast|[3-9]\d|high|rapid"),
        ],
        "severity": 1.0,
        "reason": "Low oxygen + inability to speak in full sentences with altered mental status signals impending respiratory failure. This multi-signal pattern overrides any single-observation uncertainty.",
        "min_required": 2,
        "min_supporting": 0,
    },
    {
        "id": "GESTALT_HYPERTENSIVE_URGENCY",
        "name": "Hypertensive Urgency Pattern",
        "domain": "med_refill_hypertension",
        "required_signals": [
            ("home_bp_number", r"1[89]\d|2\d{2}|over 180|above 180|very high|extremely high"),
            ("side_effects", r"headache|chest|faint|vision|dizzy|short of breath|worst headache|blurry|seeing spots"),
        ],
        "supporting_signals": [
            ("last_taken", r"days? ago|week|missed|stopped|ran out|haven't taken|haven't been taking|forgot"),
            ("pregnancy_status", r"pregnant|trying|missed period"),
        ],
        "severity": 0.95,
        "reason": "Critically elevated BP combined with end-organ symptoms creates hypertensive urgency. Remote refill automation is unsafe without clinical evaluation.",
        "min_required": 2,
        "min_supporting": 0,
    },
    # --- Cross-domain gestalt patterns (domain: "*" fires in ANY domain) ---
    {
        "id": "GESTALT_SEPSIS_GENERAL",
        "name": "General Sepsis Pattern",
        "domain": "*",
        "required_signals": [
            ("fever_measured", r"fever|10[1-9]|chills|hot|burning up"),
            ("mental_status", r"confus|sleepy|not right|altered|foggy|drowsy"),
        ],
        "supporting_signals": [
            ("vomiting", r"vomit|nausea|can't keep"),
            ("oxygen_saturation", r"low|[78]\d|<90|dropping"),
        ],
        "severity": 0.95,
        "reason": "Fever combined with altered mental status is a systemic sepsis warning regardless of the presenting domain. This cross-domain pattern triggers even when the chief complaint is unrelated.",
        "min_required": 2,
        "min_supporting": 0,
    },
    {
        "id": "GESTALT_ANAPHYLAXIS_GENERAL",
        "name": "Anaphylaxis Pattern",
        "domain": "*",
        "required_signals": [
            ("airway_symptoms", r"throat.*tight|swallow|wheez|tongue.*swell|can't breathe|lip.*swell"),
            ("new_medication", r"new|started|antibiotic|injection|vaccine|contrast|sting|bite"),
        ],
        "supporting_signals": [
            ("skin_pain", r"hive|itch|rash|welt|flush|red"),
            ("dyspnea", r"breath|can't|short|wheez"),
        ],
        "severity": 1.0,
        "reason": "Airway compromise following new exposure (medication, injection, sting) suggests anaphylaxis regardless of presenting domain. This is a time-critical emergency.",
        "min_required": 2,
        "min_supporting": 0,
    },
]

# ---------------------------------------------------------------------------
# Comorbidity Risk Adjustment
# ---------------------------------------------------------------------------
COMORBIDITY_RISK_MAP = {
    # condition_regex -> list of (domain, severity_boost, reason)
    r"diabet": [
        ("chest_discomfort", 0.10, "Diabetes increases ACS risk; chest symptoms carry higher baseline danger"),
        ("uti_symptoms", 0.08, "Diabetes increases complicated UTI and sepsis risk"),
    ],
    r"hypertension|htn|high blood pressure": [
        ("chest_discomfort", 0.08, "Hypertension increases cardiovascular event risk"),
        ("headache_migraine", 0.08, "Hypertension with severe headache raises hemorrhagic stroke risk"),
    ],
    r"immunocompromis|immunosuppress|transplant|chemo|hiv|aids|lupus": [
        ("uti_symptoms", 0.12, "Immunocompromised patients have higher sepsis risk from UTI"),
        ("rash", 0.10, "Immunocompromised patients have higher risk of severe skin infections"),
        ("dyspnea_respiratory", 0.10, "Immunocompromised patients have higher pneumonia mortality"),
    ],
    r"atrial fib|afib|a-?fib|anticoagul|warfarin|eliquis|xarelto|blood thin": [
        ("headache_migraine", 0.12, "Anticoagulation increases intracranial hemorrhage risk with headache"),
    ],
    r"copd|asthma|emphysema|lung disease": [
        ("dyspnea_respiratory", 0.08, "Baseline lung disease lowers reserve; acute dyspnea is higher risk"),
    ],
    r"heart failure|chf|cardiomyopathy": [
        ("dyspnea_respiratory", 0.10, "Heart failure decompensation can present as acute dyspnea"),
        ("chest_discomfort", 0.08, "Heart failure patients have higher ACS and arrhythmia risk"),
    ],
    r"kidney|renal|dialysis|ckd": [
        ("med_refill_hypertension", 0.08, "Renal disease alters medication safety margins"),
        ("diabetes_hyperglycemia", 0.08, "CKD complicates DKA management and fluid resuscitation"),
    ],
}

# ---------------------------------------------------------------------------
# Source Authority Weights for Scoring (higher = more scoring influence)
# ---------------------------------------------------------------------------
SOURCE_SCORING_WEIGHT = {
    "device": 1.4,
    "chart": 1.3,
    "clinician": 1.25,
    "synthetic_truth": 1.2,
    "caregiver": 0.9,
    "patient": 0.85,
}


class JudgmentReadinessEngine:
    """Expert-system shell + learnable uncertainty model.

    The engine can be wrapped around an LLM intake. The LLM can extract concepts
    from natural language; this module supplies the clinical safety skeleton:
    slots, confidence scoring, uncertainty boundary mapping, and next question
    selection.
    """

    def __init__(self, memory: Optional[ExperienceMemory] = None, llm_detector: Optional[Any] = None) -> None:
        self.memory = memory or ExperienceMemory.seeded()
        self.llm_detector = llm_detector

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def evaluate(self, case: CaseInput, max_questions: int = 5) -> ReadinessReport:
        template = self._template_for(case.patient_context.domain)
        observations = self._extract_observations(case)

        traces: List[RuleTrace] = []
        findings: List[Finding] = []

        # Source conflict detection runs on ALL observations before dedup
        findings.extend(self._source_conflict_findings(observations, traces))
        findings.extend(self._unmapped_observation_findings(observations, traces))

        observations_by_concept = self._best_observations_by_concept(observations)

        findings.extend(self._slot_findings(case, template, observations_by_concept, traces))
        findings.extend(self._contradiction_findings(case, observations_by_concept, traces))
        findings.extend(self._red_flag_findings(case, observations_by_concept, traces))
        findings.extend(self._gestalt_findings(case, observations_by_concept, traces))

        # LLM-augmented finding integration (when available)
        if self.llm_detector and hasattr(self.llm_detector, 'available') and self.llm_detector.available:
            try:
                llm_result = self.llm_detector.analyze_case(case)
                if llm_result.success:
                    _LLM_CATEGORY_MAP = {
                        "sentinel": "red_flag",
                        "distortion": "distorted",
                        "integrity": "red_flag",
                        "clinical_pattern": "red_flag",
                    }
                    for lf in llm_result.findings:
                        mapped_cat = _LLM_CATEGORY_MAP.get(lf.category, "red_flag")
                        findings.append(Finding(
                            category=mapped_cat,
                            concept=lf.concept,
                            severity=min(lf.severity, 0.80),  # Cap so LLM can't independently trigger ESCALATE
                            reason=lf.reason,
                            rule_id=f"LLM_{lf.category.upper()}_{lf.concept.upper()}",
                            evidence=f"{lf.evidence} [LLM:{llm_result.model}, confidence:{lf.confidence}]",
                        ))
                        traces.append(RuleTrace(
                            f"LLM_{lf.category.upper()}_{lf.concept.upper()}",
                            f"LLM-detected {lf.category} pattern",
                            lf.evidence,
                            f"adds {mapped_cat} finding (severity={min(lf.severity, 0.80):.2f}, capped from {lf.severity:.2f})",
                        ))
            except Exception:
                pass  # LLM failure is non-fatal; pipeline continues with regex-only findings

        # Record experience events for observations that triggered trap priors
        domain = case.patient_context.domain
        for obs in observations:
            for tag in obs.tags:
                if tag.startswith("experience_prior:"):
                    trap_name = tag.split(":", 1)[1]
                    slot = self._slot_by_name(domain, obs.concept)
                    self.memory.record_event(ExperienceEvent(
                        domain=domain,
                        concept=obs.concept,
                        trap=trap_name,
                        phrase=str(obs.raw_value),
                        initial_answer=str(obs.raw_value),
                        clarified_truth="",
                        question_used=slot.clarify_questions[0] if slot and slot.clarify_questions else "",
                        information_gain=1.0 - obs.confidence,
                        outcome_label="single_turn_evaluation",
                    ))

        scores = self._score(case, template, observations_by_concept, findings)
        next_questions = self._select_next_questions(case, template, findings, observations_by_concept, max_questions=max_questions)
        state = self._decide_state(scores, findings, next_questions)
        boundary_map = self._make_boundary_map(template, observations_by_concept, findings)
        provider_summary = self._provider_summary(case, state, scores, findings, next_questions)
        patient_safe_summary = self._patient_summary(state, next_questions)

        return ReadinessReport(
            case_id=case.case_id,
            state=state,
            scores=scores,
            boundary_map=boundary_map,
            observations=observations,
            findings=sorted(findings, key=lambda f: (f.category != "red_flag", -f.severity)),
            next_questions=next_questions,
            traces=traces,
            provider_summary=provider_summary,
            patient_safe_summary=patient_safe_summary,
        )

    # ---------------------------------------------------------------------
    # Extraction and normalization
    # ---------------------------------------------------------------------
    def _extract_observations(self, case: CaseInput) -> List[Observation]:
        observations: List[Observation] = []
        domain = case.patient_context.domain
        valid_concepts = {slot.name for slot in self._template_for(domain)}
        for st in case.statements:
            inferred_concept = infer_concept(f"{st.question} {st.answer}")
            supplied_concept = (st.concept or "").strip() if st.concept else ""
            concept = supplied_concept or inferred_concept
            generic_manual_flag = supplied_concept.lower() in {
                "red_flag",
                "redflag",
                "alarm",
                "safety",
                "urgent",
                "manual_red_flag",
            }
            if generic_manual_flag:
                concept = inferred_concept or "manual_red_flag"
            elif supplied_concept and supplied_concept not in valid_concepts and inferred_concept in valid_concepts:
                concept = inferred_concept
            tags: List[str] = []
            trace: List[str] = []
            raw = st.answer.strip()
            norm = normalize_answer(raw)
            confidence = source_base_confidence(st.source)
            trace.append(f"BASE_SOURCE_CONFIDENCE:{st.source}={confidence:.2f}")
            if generic_manual_flag:
                tags.append("manual_red_flag_label")
                trace.append(f"MANUAL_RED_FLAG_LABEL:{supplied_concept}->{concept}")
            elif supplied_concept and supplied_concept != concept:
                tags.append("concept_reclassified_to_domain_slot")
                trace.append(f"CONCEPT_RECLASSIFIED:{supplied_concept}->{concept}")

            has_number = NUMBER_RE.search(raw) is not None
            if VAGUE_WORDS.search(raw) and not (has_number and concept in {"home_bp_number", "glucose_number", "oxygen_saturation", "fever_measured", "respiratory_rate", "vitals"}):
                tags.append("vague_language")
                confidence -= 0.15
                trace.append("VAGUE_LANGUAGE:-0.15")

            if concept and concept in {"home_bp_number", "glucose_number", "oxygen_saturation", "fever_measured", "respiratory_rate", "vitals"}:
                if not NUMBER_RE.search(raw) and not re.search(r"\b(positive|negative|large|moderate|trace)\b", raw, re.I):
                    tags.append("objective_claim_without_number")
                    confidence -= 0.22
                    trace.append("OBJECTIVE_WITHOUT_NUMBER:-0.22")

            if re.search(r"\b(i take|taking|yes|daily|every day)\b", raw, re.I) and concept in {"last_taken", "insulin_access"}:
                if not re.search(r"\b(today|yesterday|this morning|last night|\d+\s*(am|pm|days?|weeks?))\b", raw, re.I):
                    tags.append("adherence_without_time_anchor")
                    confidence -= 0.12
                    trace.append("ADHERENCE_WITHOUT_TIME_ANCHOR:-0.12")

            slot = self._slot_by_name(domain, concept) if concept else None
            if slot:
                for trap in slot.traps:
                    if not trap_triggered(raw, concept, trap):
                        continue
                    penalty = self.memory.prior_penalty(domain, concept, trap)
                    if penalty > 0:
                        tags.append(f"experience_prior:{trap}")
                        confidence -= penalty
                        trace.append(f"EXPERIENCE_PRIOR:{trap}:-{penalty:.2f}")

            # Specific trap detectors.
            if concept == "symptom_quality" and NEGATIVE_WORDS.search(raw) and re.search(r"pressure|tight|heavy|burn|squeez|indigestion", raw, re.I):
                tags.append("pain_word_boundary")
                confidence -= 0.18
                trace.append("PAIN_WORD_BOUNDARY:-0.18")
            if concept in {"dyspnea", "exertional_tolerance", "sentence_test"} and NEGATIVE_WORDS.search(raw) and re.search(r"walk|stairs|sentence|breath|stop", raw, re.I):
                tags.append("sob_word_boundary")
                confidence -= 0.18
                trace.append("SOB_WORD_BOUNDARY:-0.18")
            if case.patient_context.literacy_hint == "low":
                confidence -= 0.06
                tags.append("low_literacy_context")
                trace.append("LOW_LITERACY_CONTEXT:-0.06")
            if case.patient_context.language_barrier:
                confidence -= 0.06
                tags.append("language_barrier")
                trace.append("LANGUAGE_BARRIER:-0.06")
            if case.patient_context.modality == "text":
                confidence -= 0.03
                trace.append("TEXT_MODALITY:-0.03")

            confidence = clamp(confidence, 0.05, 0.98)
            observations.append(
                Observation(
                    concept=concept or "unknown",
                    raw_value=raw,
                    normalized_value=norm,
                    source=st.source,
                    confidence=round(confidence, 3),
                    tags=tags,
                    trace=trace,
                )
            )
        return observations

    def _best_observations_by_concept(self, observations: Sequence[Observation]) -> Dict[str, Observation]:
        best: Dict[str, Observation] = {}
        for obs in observations:
            if obs.concept not in best or obs.confidence > best[obs.concept].confidence:
                best[obs.concept] = obs
        return best

    # ---------------------------------------------------------------------
    # Findings
    # ---------------------------------------------------------------------
    def _slot_findings(
        self,
        case: CaseInput,
        template: Sequence[SlotSpec],
        obs: Dict[str, Observation],
        traces: List[RuleTrace],
    ) -> List[Finding]:
        findings: List[Finding] = []
        for slot in template:
            observation = obs.get(slot.name)
            if slot.remote_unknowable:
                findings.append(
                    Finding(
                        category="unknowable_remote",
                        concept=slot.name,
                        severity=slot.importance,
                        reason=f"{slot.label} is not fully knowable from remote chat/text intake.",
                        rule_id="REMOTE_BOUNDARY",
                        next_question=slot.clarify_questions[0] if slot.clarify_questions else None,
                    )
                )
                traces.append(RuleTrace("REMOTE_BOUNDARY", "Remote modality boundary", slot.name, "adds unknowable_remote finding"))
                continue

            if observation is None:
                category = "objective_needed" if slot.objective_required else "missing"
                findings.append(
                    Finding(
                        category=category,
                        concept=slot.name,
                        severity=slot.importance + (0.2 if slot.critical else 0.0),
                        reason=f"Missing {slot.label}. {slot.why_it_matters}".strip(),
                        rule_id="REQUIRED_SLOT_MISSING",
                        next_question=slot.clarify_questions[0] if slot.clarify_questions else None,
                    )
                )
                traces.append(RuleTrace("REQUIRED_SLOT_MISSING", "Required slot absent", slot.name, "adds missing/objective_needed finding"))
                continue

            if observation.confidence < 0.55:
                findings.append(
                    Finding(
                        category="distorted" if observation.tags else "uncertain",
                        concept=slot.name,
                        severity=slot.importance * (1.0 - observation.confidence),
                        reason=f"{slot.label} is present but low-confidence ({observation.confidence:.2f}); tags={observation.tags}.",
                        rule_id="LOW_CONFIDENCE_OBSERVATION",
                        next_question=slot.clarify_questions[0] if slot.clarify_questions else None,
                        evidence=observation.raw_value,
                    )
                )
                traces.append(RuleTrace("LOW_CONFIDENCE_OBSERVATION", "Observation below reliability threshold", observation.raw_value, "adds uncertain/distorted finding"))
            elif observation.tags:
                # A softer distorted finding, even when not below confidence threshold.
                findings.append(
                    Finding(
                        category="distorted",
                        concept=slot.name,
                        severity=max(0.1, slot.importance * 0.18),
                        reason=f"{slot.label} may be distorted by {', '.join(observation.tags)}.",
                        rule_id="DISTORTION_TAG_PRESENT",
                        next_question=slot.clarify_questions[0] if slot.clarify_questions else None,
                        evidence=observation.raw_value,
                    )
                )
        return findings

    def _contradiction_findings(
        self,
        case: CaseInput,
        obs: Dict[str, Observation],
        traces: List[RuleTrace],
    ) -> List[Finding]:
        findings: List[Finding] = []
        domain = case.patient_context.domain
        for rule in CONTRADICTION_RULES:
            if rule["domain"] != domain:
                continue
            a = obs.get(rule["concept_a"])
            b = obs.get(rule["concept_b"])
            if not a or not b:
                continue
            a_negative = NEGATIVE_WORDS.search(str(a.raw_value)) is not None
            b_match = re.search(str(rule["pattern_b"]), str(b.raw_value), re.I) is not None
            if a_negative == bool(rule["negative_a"]) and b_match:
                findings.append(
                    Finding(
                        category="contradictory",
                        concept=rule["concept_b"],
                        severity=0.85,
                        reason=str(rule["reason"]),
                        rule_id=str(rule["id"]),
                        next_question=self._slot_by_name(domain, str(rule["concept_b"])).clarify_questions[0] if self._slot_by_name(domain, str(rule["concept_b"])) else None,
                        evidence=f"A='{a.raw_value}' B='{b.raw_value}'",
                    )
                )
                traces.append(RuleTrace(str(rule["id"]), "Contradiction detector", f"{a.raw_value} / {b.raw_value}", "adds contradictory finding"))
        return findings

    def _red_flag_findings(
        self,
        case: CaseInput,
        obs: Dict[str, Observation],
        traces: List[RuleTrace],
    ) -> List[Finding]:
        findings: List[Finding] = []
        domain = case.patient_context.domain
        for concept, pattern, base_severity in RED_FLAG_PATTERNS.get(domain, []):
            observation = obs.get(concept)
            if not observation:
                continue
            raw = str(observation.raw_value)
            if not re.search(pattern, raw, re.I):
                continue
            if is_simple_negated_answer(raw, concept):
                traces.append(RuleTrace("NEGATED_RED_FLAG_SUPPRESSED", "Matched red-flag words inside a clear denial", raw, "suppressed red_flag finding"))
                continue

            # Severity gradient adjustment
            severity = base_severity
            severity_notes = []
            if SEVERITY_AMPLIFIERS.search(raw):
                severity = min(1.0, severity * 1.15)
                severity_notes.append("amplified")
                traces.append(RuleTrace("SEVERITY_AMPLIFIED", "Patient language indicates high intensity", raw, f"severity {base_severity:.2f} -> {severity:.2f}"))
            elif SEVERITY_DIMINISHERS.search(raw):
                severity = max(0.3, severity * 0.75)
                severity_notes.append("diminished")
                traces.append(RuleTrace("SEVERITY_DIMINISHED", "Patient language indicates low intensity", raw, f"severity {base_severity:.2f} -> {severity:.2f}"))

            # Temporal acuity adjustment
            if TEMPORAL_ACUTE.search(raw):
                severity = min(1.0, severity * 1.10)
                severity_notes.append("acute onset")
                traces.append(RuleTrace("TEMPORAL_ACUTE", "Acute/recent onset increases urgency", raw, f"acuity boost applied"))
            elif TEMPORAL_CHRONIC.search(raw):
                severity = max(0.3, severity * 0.80)
                severity_notes.append("chronic/historical")
                traces.append(RuleTrace("TEMPORAL_CHRONIC", "Chronic/historical timeline reduces acute urgency", raw, f"chronicity reduction applied"))

            # Comorbidity risk adjustment
            comorbidity_boost = _comorbidity_severity_boost(case.patient_context.known_conditions, domain)
            if comorbidity_boost > 0:
                severity = min(1.0, severity + comorbidity_boost)
                severity_notes.append(f"comorbidity +{comorbidity_boost:.2f}")
                traces.append(RuleTrace("COMORBIDITY_RISK_BOOST", "Patient comorbidities increase risk profile", str(case.patient_context.known_conditions), f"severity boosted by {comorbidity_boost:.2f}"))

            severity = round(severity, 3)
            note_str = f" [{', '.join(severity_notes)}]" if severity_notes else ""
            findings.append(
                Finding(
                    category="red_flag",
                    concept=concept,
                    severity=severity,
                    reason=f"Potential red-flag signal in {concept}: '{raw}'.{note_str}",
                    rule_id="DOMAIN_RED_FLAG_PATTERN",
                    evidence=raw,
                )
            )
            traces.append(RuleTrace("DOMAIN_RED_FLAG_PATTERN", "Domain red flag lexical pattern", raw, f"adds red_flag finding (severity={severity:.3f})"))
        manual = obs.get("manual_red_flag")
        if manual:
            findings.append(
                Finding(
                    category="red_flag",
                    concept="manual_red_flag",
                    severity=0.80,
                    reason="User manually labeled this statement as a red flag, but it did not map to a validated domain slot. It must be reviewed rather than ignored.",
                    rule_id="MANUAL_RED_FLAG_UNMAPPED",
                    evidence=str(manual.raw_value),
                )
            )
            traces.append(RuleTrace("MANUAL_RED_FLAG_UNMAPPED", "Manual safety label without domain-slot mapping", str(manual.raw_value), "adds red_flag finding"))
        return findings

    def _gestalt_findings(
        self,
        case: CaseInput,
        obs: Dict[str, Observation],
        traces: List[RuleTrace],
    ) -> List[Finding]:
        """Detect multi-signal clinical patterns (gestalt synthesis)."""
        findings: List[Finding] = []
        domain = case.patient_context.domain
        for pattern in GESTALT_PATTERNS:
            if pattern["domain"] != "*" and pattern["domain"] != domain:
                continue
            # Count required signals that match
            required_hits = 0
            required_evidence = []
            for concept, regex in pattern["required_signals"]:
                observation = obs.get(concept)
                if observation and re.search(regex, str(observation.raw_value), re.I):
                    if not is_simple_negated_answer(str(observation.raw_value), concept):
                        required_hits += 1
                        required_evidence.append(f"{concept}: '{observation.raw_value}'")
            if required_hits < pattern["min_required"]:
                continue
            # Count supporting signals
            supporting_hits = 0
            supporting_evidence = []
            for concept, regex in pattern["supporting_signals"]:
                observation = obs.get(concept)
                if observation and re.search(regex, str(observation.raw_value), re.I):
                    if not is_simple_negated_answer(str(observation.raw_value), concept):
                        supporting_hits += 1
                        supporting_evidence.append(f"{concept}: '{observation.raw_value}'")
            if supporting_hits < pattern["min_supporting"]:
                continue
            # Gestalt pattern matched
            all_evidence = required_evidence + supporting_evidence
            findings.append(
                Finding(
                    category="red_flag",
                    concept=f"gestalt:{pattern['id']}",
                    severity=pattern["severity"],
                    reason=f"[{pattern['name']}] {pattern['reason']}",
                    rule_id=pattern["id"],
                    evidence=" | ".join(all_evidence),
                )
            )
            traces.append(RuleTrace(
                pattern["id"],
                f"Gestalt pattern: {pattern['name']}",
                " | ".join(all_evidence),
                f"adds gestalt red_flag (required={required_hits}, supporting={supporting_hits})",
            ))
        return findings

    def _source_conflict_findings(
        self,
        all_observations: List[Observation],
        traces: List[RuleTrace],
    ) -> List[Finding]:
        """Detect conflicts between high-authority and low-authority sources for the same concept."""
        from collections import defaultdict
        findings: List[Finding] = []
        HIGH_AUTHORITY = {"device", "chart", "clinician"}
        LOW_AUTHORITY = {"patient", "caregiver"}
        NORMAL_WORDS = re.compile(r"\b(normal|fine|okay|ok|good|no problem)\b", re.I)

        by_concept: Dict[str, List[Observation]] = defaultdict(list)
        for obs in all_observations:
            by_concept[obs.concept].append(obs)

        for concept, obs_list in by_concept.items():
            if len(obs_list) < 2:
                continue
            # Get unique sources
            sources = {obs.source for obs in obs_list}
            has_high = sources & HIGH_AUTHORITY
            has_low = sources & LOW_AUTHORITY
            if not has_high or not has_low:
                continue

            high_obs = [o for o in obs_list if o.source in HIGH_AUTHORITY]
            low_obs = [o for o in obs_list if o.source in LOW_AUTHORITY]

            for hi in high_obs:
                for lo in low_obs:
                    # Detect disagreement
                    hi_negative = NEGATIVE_WORDS.search(str(hi.raw_value)) is not None
                    lo_negative = NEGATIVE_WORDS.search(str(lo.raw_value)) is not None
                    hi_normal = NORMAL_WORDS.search(str(hi.raw_value)) is not None
                    lo_normal = NORMAL_WORDS.search(str(lo.raw_value)) is not None
                    hi_has_number = NUMBER_RE.search(str(hi.raw_value)) is not None
                    lo_has_number = NUMBER_RE.search(str(lo.raw_value)) is not None

                    conflict = False
                    # One denies, the other doesn't
                    if hi_negative != lo_negative:
                        conflict = True
                    # One says normal/fine, the other has a number or clinical finding
                    elif (lo_normal and not lo_has_number) and hi_has_number:
                        conflict = True
                    elif (hi_normal and not hi_has_number) and lo_has_number:
                        conflict = True

                    if conflict:
                        findings.append(
                            Finding(
                                category="contradictory",
                                concept=concept,
                                severity=0.70,
                                reason=f"Source conflict on '{concept}': high-authority source '{hi.source}' disagrees with '{lo.source}'.",
                                rule_id=f"SOURCE_CONFLICT_{concept.upper()}",
                                evidence=f"Source '{hi.source}': '{hi.raw_value}' vs Source '{lo.source}': '{lo.raw_value}'",
                            )
                        )
                        traces.append(RuleTrace(
                            f"SOURCE_CONFLICT_{concept.upper()}",
                            "Source authority conflict detected",
                            f"{hi.source}='{hi.raw_value}' vs {lo.source}='{lo.raw_value}'",
                            "adds contradictory finding (severity=0.70)",
                        ))

        return findings

    def _unmapped_observation_findings(
        self,
        observations: Sequence[Observation],
        traces: List[RuleTrace],
    ) -> List[Finding]:
        findings: List[Finding] = []
        for obs in observations:
            if obs.concept != "unknown":
                continue
            raw = str(obs.raw_value).strip()
            if not raw:
                continue
            findings.append(
                Finding(
                    category="uncertain",
                    concept="unknown",
                    severity=0.65,
                    reason="Statement was captured but not mapped to a validated clinical concept; it cannot support reassurance or closure.",
                    rule_id="UNMAPPED_OBSERVATION_REVIEW",
                    evidence=raw,
                )
            )
            traces.append(
                RuleTrace(
                    "UNMAPPED_OBSERVATION_REVIEW",
                    "Captured statement lacks validated concept mapping",
                    raw,
                    "adds uncertain finding and requires review/classification",
                )
            )
        return findings

    # ---------------------------------------------------------------------
    # Scoring and decisions
    # ---------------------------------------------------------------------
    def _score(
        self,
        case: CaseInput,
        template: Sequence[SlotSpec],
        obs: Dict[str, Observation],
        findings: Sequence[Finding],
    ) -> ReadinessScores:
        total_weight = sum(slot.importance for slot in template) or 1.0
        present_weight = sum(slot.importance for slot in template if slot.name in obs and not slot.remote_unknowable)
        completeness = present_weight / total_weight

        if obs:
            weighted_sum = sum(
                o.confidence * SOURCE_SCORING_WEIGHT.get(o.source, 1.0)
                for o in obs.values()
            )
            weight_total = sum(
                SOURCE_SCORING_WEIGHT.get(o.source, 1.0)
                for o in obs.values()
            )
            reliability = weighted_sum / weight_total
        else:
            reliability = 0.0

        objective_slots = [slot for slot in template if slot.objective_required]
        if objective_slots:
            obj_score = 0.0
            for slot in objective_slots:
                if slot.name in obs and obs[slot.name].confidence >= 0.60:
                    src = obs[slot.name].source
                    if src in ("device", "chart", "clinician"):
                        obj_score += 1.0
                    else:
                        obj_score += 0.7  # Patient-reported objective data gets partial credit
            objective_coverage = obj_score / len(objective_slots)
        else:
            objective_coverage = 1.0

        contradiction_load = min(1.0, sum(f.severity for f in findings if f.category == "contradictory") / 2.0)
        distortion_load = min(1.0, sum(f.severity for f in findings if f.category in {"distorted", "uncertain"}) / 2.5)
        red_flag_load = min(1.0, sum(f.severity for f in findings if f.category == "red_flag") / 1.5)
        critical_missing_penalty = 0.0
        for f in findings:
            if f.category in {"missing", "objective_needed"} and self._slot_by_name(case.patient_context.domain, f.concept) and self._slot_by_name(case.patient_context.domain, f.concept).critical:
                critical_missing_penalty += min(0.20, f.severity * 0.08)
        critical_missing_penalty = min(0.35, critical_missing_penalty)

        index = (
            0.42 * completeness
            + 0.30 * reliability
            + 0.18 * objective_coverage
            + 0.10 * (1 - distortion_load)
        )
        index -= 0.25 * contradiction_load
        index -= 0.32 * red_flag_load
        index -= critical_missing_penalty
        readiness_index = clamp(index * 100, 0, 100)
        return ReadinessScores(
            completeness=round(completeness, 3),
            reliability=round(reliability, 3),
            objective_coverage=round(objective_coverage, 3),
            contradiction_load=round(contradiction_load, 3),
            distortion_load=round(distortion_load, 3),
            red_flag_load=round(red_flag_load, 3),
            readiness_index=round(readiness_index, 1),
        )

    def _decide_state(self, scores: ReadinessScores, findings: Sequence[Finding], next_questions: Sequence[NextQuestion]) -> str:
        if any(f.category == "red_flag" and f.severity >= 0.85 for f in findings):
            return "ESCALATE"
        if any(f.category == "objective_needed" and f.severity >= 0.85 for f in findings):
            return "NEED_OBJECTIVE_DATA"
        if any(f.category == "contradictory" for f in findings):
            return "CLARIFY"
        if scores.readiness_index >= 78 and scores.red_flag_load == 0 and len(next_questions) <= 2:
            return "READY"
        return "CLARIFY"

    # ---------------------------------------------------------------------
    # Question generation
    # ---------------------------------------------------------------------
    def _select_next_questions(
        self,
        case: CaseInput,
        template: Sequence[SlotSpec],
        findings: Sequence[Finding],
        obs: Dict[str, Observation],
        max_questions: int,
    ) -> List[NextQuestion]:
        domain = case.patient_context.domain
        slot_map = {s.name: s for s in template}
        candidates: List[NextQuestion] = []
        used: set[Tuple[str, str]] = set()
        concept_question_index: Dict[str, int] = {}  # track which clarify_questions index used per concept
        category_weight = {
            "red_flag": 1.25,
            "contradictory": 1.15,
            "objective_needed": 1.05,
            "missing": 0.90,
            "distorted": 0.85,
            "uncertain": 0.80,
            "unknowable_remote": 0.45,
        }
        for f in findings:
            # --- Gestalt finding question generation ---
            if f.concept.startswith("gestalt:"):
                # Parse evidence to find contributing concepts, pick weakest
                if f.evidence:
                    parts = f.evidence.split(" | ")
                    weakest_concept = None
                    weakest_conf = 1.0
                    for part in parts:
                        if ":" in part:
                            concept_name = part.split(":")[0].strip()
                            o = obs.get(concept_name)
                            if o and o.confidence < weakest_conf:
                                weakest_conf = o.confidence
                                weakest_concept = concept_name
                    if weakest_concept:
                        slot = slot_map.get(weakest_concept)
                        if slot and slot.clarify_questions:
                            question = slot.clarify_questions[0]
                            key = (weakest_concept, question)
                            if key not in used:
                                used.add(key)
                                yield_est = self.memory.expected_question_yield(domain, question)
                                candidates.append(NextQuestion(
                                    concept=weakest_concept,
                                    question=question,
                                    reason=f.reason,
                                    clear_step=CLEAR_STEPS.get("red_flag", "Escalate or route to clinician."),
                                    priority=round((slot.importance * 1.25) + (0.35 * (1.0 - weakest_conf)) + (0.2 * yield_est), 3),
                                    expected_information_gain=round(yield_est, 3),
                                    rule_id=f.rule_id,
                                ))
                continue

            slot = slot_map.get(f.concept)
            if not slot:
                continue

            # --- Escalation probes for high-severity red flags ---
            question = None
            if f.category == "red_flag" and f.severity >= 0.85:
                probe = ESCALATION_PROBES.get((domain, f.concept))
                if probe:
                    question = probe

            # --- Question index rotation ---
            if question is None:
                idx = concept_question_index.get(f.concept, 0)
                if f.next_question:
                    question = f.next_question
                elif slot.clarify_questions:
                    # Try the next unused index
                    while idx < len(slot.clarify_questions):
                        candidate_q = slot.clarify_questions[idx]
                        if (f.concept, candidate_q) not in used:
                            question = candidate_q
                            break
                        idx += 1
                    if question is None:
                        # Fallback: try escalation probe
                        probe = ESCALATION_PROBES.get((domain, f.concept))
                        if probe and (f.concept, probe) not in used:
                            question = probe
                        else:
                            question = slot.clarify_questions[0]
                else:
                    question = f"Please clarify {slot.label}."
                concept_question_index[f.concept] = idx + 1

            key = (f.concept, question)
            if key in used:
                continue
            used.add(key)
            obs_conf = obs.get(f.concept).confidence if f.concept in obs else 0.0
            uncertainty_gap = 1.0 - obs_conf
            yield_est = self.memory.expected_question_yield(domain, question)
            priority = (slot.importance * category_weight.get(f.category, 0.7)) + (0.35 * uncertainty_gap) + (0.2 * yield_est)
            clear_step = CLEAR_STEPS.get(f.category, "Clarify before proceeding.")
            candidates.append(
                NextQuestion(
                    concept=f.concept,
                    question=question,
                    reason=f.reason,
                    clear_step=clear_step,
                    priority=round(priority, 3),
                    expected_information_gain=round(yield_est, 3),
                    rule_id=f.rule_id,
                )
            )
        selected = sorted(candidates, key=lambda q: q.priority, reverse=True)[:max_questions]

        # --- Modality-specific question adaptation ---
        modality = case.patient_context.modality
        adaptation = MODALITY_ADAPTATIONS.get(modality)
        if adaptation:
            NUMBER_KEYWORDS = re.compile(
                r"\b(glucose|bp|blood pressure|temperature|number|reading|meter|oximeter|thermometer|"
                r"pulse ox|oxygen|respiratory rate|breaths|heart rate)\b", re.I
            )
            VISUAL_KEYWORDS = re.compile(
                r"\b(look|show|see|rash|sore|blister|swelling|redness|photo|upload|mirror)\b", re.I
            )
            ACTION_KEYWORDS = re.compile(
                r"\b(try|walk|swallow|touch|take a|breathe|say|count breaths|read the|hold)\b", re.I
            )
            adapted: List[NextQuestion] = []
            for nq in selected:
                q_text = nq.question
                suffix_parts: List[str] = []
                if NUMBER_KEYWORDS.search(q_text):
                    suffix_parts.append(adaptation["number_prompt"])
                if VISUAL_KEYWORDS.search(q_text):
                    suffix_parts.append(adaptation["visual_prompt"])
                if ACTION_KEYWORDS.search(q_text):
                    suffix_parts.append(adaptation["action_prompt"])
                if suffix_parts:
                    q_text = q_text.rstrip() + " " + " ".join(suffix_parts)
                # Phone prefix
                if modality == "phone" and adaptation["prefix"] and not q_text.startswith("Can you"):
                    q_text = adaptation["prefix"] + " " + q_text
                adapted.append(NextQuestion(
                    concept=nq.concept,
                    question=q_text,
                    reason=nq.reason,
                    clear_step=nq.clear_step,
                    priority=nq.priority,
                    expected_information_gain=nq.expected_information_gain,
                    rule_id=nq.rule_id,
                ))
            selected = adapted

        return selected

    # ---------------------------------------------------------------------
    # Maps and summaries
    # ---------------------------------------------------------------------
    def _make_boundary_map(self, template: Sequence[SlotSpec], obs: Dict[str, Observation], findings: Sequence[Finding]) -> Dict[str, List[str]]:
        by_cat: Dict[str, List[str]] = defaultdict(list)
        findings_by_concept = defaultdict(list)
        for f in findings:
            findings_by_concept[f.concept].append(f)

        for slot in template:
            if slot.name in obs and not findings_by_concept.get(slot.name):
                by_cat["known_high_confidence"].append(f"{slot.label}: {obs[slot.name].raw_value} (confidence {obs[slot.name].confidence:.2f})")
        for f in findings:
            if f.category == "missing":
                by_cat["missing"].append(f"{f.concept}: {f.reason}")
            elif f.category == "objective_needed":
                by_cat["needs_objective_data"].append(f"{f.concept}: {f.reason}")
            elif f.category in {"uncertain", "distorted"}:
                by_cat["uncertain_or_distorted"].append(f"{f.concept}: {f.reason}")
            elif f.category == "contradictory":
                by_cat["contradictions"].append(f"{f.concept}: {f.reason}")
            elif f.category == "unknowable_remote":
                by_cat["remote_boundary"].append(f"{f.concept}: {f.reason}")
            elif f.category == "red_flag":
                by_cat["red_flags"].append(f"{f.concept}: {f.reason}")
        return dict(by_cat)

    def _provider_summary(
        self,
        case: CaseInput,
        state: str,
        scores: ReadinessScores,
        findings: Sequence[Finding],
        questions: Sequence[NextQuestion],
    ) -> str:
        top_findings = sorted(findings, key=lambda f: f.severity, reverse=True)[:4]
        finding_text = "; ".join(f"{f.category}:{f.concept}" for f in top_findings) or "no major uncertainty flags"
        q_text = " | ".join(q.question for q in questions[:3]) or "No further questions recommended."
        return (
            f"State={state}; JRI={scores.readiness_index:.1f}/100; "
            f"completeness={scores.completeness:.2f}, reliability={scores.reliability:.2f}, objective={scores.objective_coverage:.2f}. "
            f"Top uncertainty/red-flag signals: {finding_text}. Next best questions: {q_text}"
        )

    def _patient_summary(self, state: str, questions: Sequence[NextQuestion]) -> str:
        if state == "ESCALATE":
            return "Some answers may point to symptoms that need clinician review before this can be handled automatically."
        if questions:
            return f"I need to clarify one important detail first: {questions[0].question}"
        return "The information provided appears sufficient for the next step in this intake pathway."

    def _template_for(self, domain: str) -> List[SlotSpec]:
        if domain not in DOMAIN_TEMPLATES:
            raise KeyError(f"Unknown domain '{domain}'. Available: {sorted(DOMAIN_TEMPLATES)}")
        return DOMAIN_TEMPLATES[domain]

    def _slot_by_name(self, domain: str, concept: Optional[str]) -> Optional[SlotSpec]:
        if concept is None:
            return None
        for slot in DOMAIN_TEMPLATES.get(domain, []):
            if slot.name == concept:
                return slot
        return None


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def source_base_confidence(source: str) -> float:
    return {
        "device": 0.92,
        "chart": 0.88,
        "clinician": 0.86,
        "caregiver": 0.78,
        "patient": 0.72,
        "synthetic_truth": 0.99,
    }.get(source, 0.65)


def normalize_answer(raw: str) -> Any:
    raw_l = raw.strip().lower()
    m = NUMBER_RE.findall(raw_l)
    if m:
        nums = []
        for a, b in m:
            nums.append(int(a))
            if b:
                nums.append(int(b))
        return nums if len(nums) > 1 else nums[0]
    if NEGATIVE_WORDS.search(raw_l) and not AFFIRM_WORDS.search(raw_l):
        return False
    if AFFIRM_WORDS.search(raw_l) and not NEGATIVE_WORDS.search(raw_l):
        return True
    return raw_l


def infer_concept(text: str) -> Optional[str]:
    q = text.lower()
    if re.search(r"\b(cough(?:ing|ed)?(?: up)?.{0,50}\bblood|blood.{0,40}\bsputum|bloody sputum|spit(?:ting)? blood|hemoptysis)\b", q, re.I):
        return "hemoptysis"
    if re.search(r"\b(saddle|private areas?|groin|genital|perineal|inner thighs?|tingl(?:e|ing)|numb(?:ness)?|weak(?:ness)?|legs?.*weak|foot drop|trouble walking|stairs)\b", q, re.I):
        return "neuro_deficit"
    if re.search(r"\b(bladder|bleeder|urinat(?:e|ion|ing)|pee|void|bowel|stool|incontinence|retention|fuller? than usual|more full|can't go|cannot go|can't empty|cannot empty)\b", q, re.I):
        return "bowel_bladder"
    if re.search(r"\b(lift(?:ing|ed)?|fall|injury|crash|trauma|heavy lift)\b", q, re.I):
        return "trauma_mechanism"
    if re.search(r"\b(back pain|lower back|low back|pain getting worse|not getting better)\b", q, re.I):
        return "pain_function"
    mappings = [
        ("blood pressure", "home_bp_number"),
        ("glucose", "glucose_number"),
        ("sugar", "glucose_number"),
        ("oxygen", "oxygen_saturation"),
        ("pulse ox", "oxygen_saturation"),
        ("breaths", "respiratory_rate"),
        ("temperature", "fever_measured"),
        ("fever", "fever_measured"),
        ("chest", "symptom_quality"),
        ("pressure", "symptom_quality"),
        ("tight", "symptom_quality"),
        ("indigestion", "symptom_quality"),
        ("heartburn", "symptom_quality"),
        ("activity", "exertional_component"),
        ("walk", "exertional_tolerance"),
        ("upstairs", "exertional_component"),
        ("stairs", "exertional_component"),
        ("shortness of breath", "dyspnea"),
        ("breath", "dyspnea"),
        ("slow down", "dyspnea"),
        ("sentence", "sentence_test"),
        ("pregnant", "pregnancy_status"),
        ("vomit", "vomiting"),
        ("flank", "flank_pain"),
        ("back", "flank_pain"),
        ("mouth", "mucosal_involvement"),
        ("eye", "mucosal_involvement"),
        ("new medication", "new_medication"),
        ("medicine bottle", "medication_identity"),
        ("last dose", "last_taken"),
    ]
    for needle, concept in mappings:
        if needle in q:
            return concept
    return None


def trap_triggered(raw: str, concept: Optional[str], trap: str) -> bool:
    text = raw.strip().lower()
    has_num = NUMBER_RE.search(text) is not None
    if trap == "normal_without_number":
        return ("normal" in text or "good" in text or "fine" in text) and not has_num
    if trap == "sugar_fine_without_number":
        return ("fine" in text or "normal" in text or "high" in text or "hi" in text) and not has_num
    if trap == "adherence_social_desirability":
        return concept in {"last_taken", "insulin_access"} and not re.search(r"\b(today|yesterday|this morning|last night|\d+\s*(am|pm|days?|weeks?))\b", text, re.I)
    if trap == "pain_word_boundary":
        return bool(re.search(r"not pain|no pain|pressure|tight|heavy|squeez|burn|indigestion|heartburn", text, re.I))
    if trap == "heartburn_label":
        return bool(re.search(r"heartburn|indigestion|burn", text, re.I))
    if trap == "sob_word_boundary":
        return bool(re.search(r"not really|fine sitting|except|walk|stairs|sentence|stop|tired", text, re.I))
    if trap == "fever_guess":
        return not has_num and bool(re.search(r"feel hot|felt hot|warm|sweaty|chills", text, re.I))
    if trap in {"med_name_confusion", "back_pain_boundary", "rash_boundary"}:
        return bool(re.search(r"not sure|maybe|i think|kidney|side|mouth|eye|genital", text, re.I))
    if trap == "thunderclap_minimized":
        return bool(re.search(r"sudden|worst|instant|seconds|thunderclap|worst ever|like a switch", text, re.I)) and bool(re.search(r"mild|not bad|okay|fine|just|only", text, re.I))
    if trap == "medication_overuse":
        return bool(re.search(r"every day|daily|all the time|constantly|10|15|20", text, re.I))
    return False


def is_simple_negated_answer(raw: str, concept: str) -> bool:
    """Suppress false red flags when the only red-flag words are listed in a denial.

    Uses clause-boundary detection: splits on conjunctions (but, except, however,
    although, though, yet) and checks whether positive clinical content appears
    AFTER the boundary. Content before the boundary in a denial context is suppressed;
    content after a "but"/"except" is NOT suppressed.

    Example: "No chest pain or shortness of breath" → suppressed (pure denial)
    Example: "Not pain, just pressure" → NOT suppressed (positive qualifier after comma)
    Example: "No bleeding, but I had black stool" → NOT suppressed (positive after "but")
    """
    text = raw.strip().lower()
    if not re.match(r"^(no|none|denies|deny|not |i do not|i don't)", text):
        return False

    # Split on clause boundaries — conjunctions only, NOT commas/semicolons in denial lists
    # Commas in "No X, Y, Z" are list separators, not clause boundaries
    clause_boundary = re.compile(r"\b(but|except|however|although|though|yet|just|only when)\b")
    parts = clause_boundary.split(text)

    # If there's only one clause (the denial itself), check for embedded positives
    if len(parts) <= 1:
        # Side effect lists commonly contain scary terms in a clear denial
        if concept in {"side_effects", "airway_symptoms", "vomiting", "pregnancy_status", "radiation", "diaphoresis"}:
            return True
        # Pure denial with no qualifiers
        embedded_positives = [
            "pressure", "tight", "heavy", "squeez", "burn", "clammy",
            "can't", "cannot", "stop", "few words", "pause", "88", "89",
            "mouth", "eye", "blister", "peel", "kidney side", "flank",
            "worse", "better with rest",
        ]
        return not any(q in text for q in embedded_positives)

    # Multi-clause: check if any post-boundary clause contains positive clinical content
    positive_content = re.compile(
        r"(pressure|tight|heavy|squeez|burn|clammy|sweat|"
        r"can't|cannot|stop|pause|worse|weak|numb|slur|"
        r"blister|peel|blood|black stool|"
        r"confus|dizzy|faint|pass|collapse|"
        r"vomit|throw up|can't keep|"
        r"high|low|fast|slow|deep breath|"
        r"mouth|eye|genital|throat|tongue)", re.I
    )
    # The first part is the denial. Check subsequent parts for positive content.
    for part in parts[1:]:
        if part and positive_content.search(part):
            return False  # Positive content after boundary — not a simple negation

    # Side effect concepts: if no positive content after boundary, it's a safe denial
    if concept in {"side_effects", "airway_symptoms", "vomiting", "pregnancy_status", "radiation", "diaphoresis"}:
        return True

    return True


def _comorbidity_severity_boost(known_conditions: List[str], domain: str) -> float:
    """Compute cumulative severity boost from patient comorbidities for this domain."""
    if not known_conditions:
        return 0.0
    conditions_text = " ".join(known_conditions).lower()
    boost = 0.0
    for condition_pattern, domain_boosts in COMORBIDITY_RISK_MAP.items():
        if not re.search(condition_pattern, conditions_text, re.I):
            continue
        for target_domain, severity_boost, _reason in domain_boosts:
            if target_domain == domain:
                boost += severity_boost
    return min(0.20, boost)  # Cap at 0.20 to prevent runaway severity


def case_from_dict(payload: Dict[str, Any]) -> CaseInput:
    ctx_payload = payload["patient_context"]
    ctx = PatientContext(**ctx_payload)
    statements = [Statement(**s) for s in payload.get("statements", [])]
    return CaseInput(
        case_id=payload.get("case_id", "case"),
        patient_context=ctx,
        statements=statements,
        ground_truth=payload.get("ground_truth", {}),
    )


def report_to_markdown(report: ReadinessReport) -> str:
    lines = []
    lines.append(f"# Judgment Readiness Report — {report.case_id}")
    lines.append("")
    lines.append(f"**State:** {report.state}")
    lines.append(f"**Judgment Readiness Index:** {report.scores.readiness_index:.1f}/100")
    lines.append("")
    lines.append("## Provider summary")
    lines.append(report.provider_summary)
    lines.append("")
    lines.append("## Boundary map")
    for category, values in report.boundary_map.items():
        lines.append(f"### {category.replace('_', ' ').title()}")
        for value in values:
            lines.append(f"- {value}")
    lines.append("")
    lines.append("## Next best questions")
    for i, q in enumerate(report.next_questions, start=1):
        lines.append(f"{i}. **{q.concept}** — {q.question}")
        lines.append(f"   - Why: {q.reason}")
        lines.append(f"   - CLEAR step: {q.clear_step}")
        lines.append(f"   - Priority: {q.priority}, expected gain: {q.expected_information_gain}")
    lines.append("")
    lines.append("## Trace")
    for tr in report.traces[:20]:
        lines.append(f"- `{tr.rule_id}`: {tr.description} → {tr.effect} | evidence: {tr.evidence}")
    return "\n".join(lines)
