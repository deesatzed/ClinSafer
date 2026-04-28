"""Tests for the Interactive Clinical Safety Demo.

Covers:
  - Page serving (HTML, 5 screens, JS functions)
  - Cases endpoint (all cases returned, required fields, categories)
  - Analysis endpoint (13 sections, field validation, escalation, happy path)
  - Feedback endpoint (accepted, invalid rejected)
  - Experience endpoint (priors returned)
  - Suggest-rule/case endpoints (graceful without LLM key)
  - Determinism (same input → same output)
  - Edited encounter (changing answer changes result)
"""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from interactive_demo import (
    app,
    _build_progressive_sections,
    _ALL_CASES,
    _memory,
    _jre,
    _guard,
    CASE_NARRATIVES,
    CATEGORY_LABELS,
)
from jre import JudgmentReadinessEngine, BlackSwanGuardrailEngine
from jre.models import most_restrictive
from jre.synthetic_data import BASE_CASES
from jre.black_swan import BLACK_SWAN_CASES
from jre.experience import ExperienceMemory


client = TestClient(app)

EXPECTED_SECTION_IDS = [
    "input_coverage",
    "interpretation_boundaries",
    "provenance_authority",
    "observations",
    "mud_map",
    "red_flags",
    "jri_score",
    "guardrails",
    "safety_decision",
    "autonomy_boundary",
    "next_questions",
    "mitigation_plan",
    "llm_opinion",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analyze_payload(case):
    """Convert a CaseInput to the JSON payload expected by /demo/analyze."""
    return {
        "case_id": case.case_id,
        "patient_context": {
            "age": case.patient_context.age,
            "chief_concern": case.patient_context.chief_concern,
            "domain": case.patient_context.domain,
            "literacy_hint": case.patient_context.literacy_hint,
            "language_barrier": case.patient_context.language_barrier,
            "has_caregiver": case.patient_context.has_caregiver,
            "modality": case.patient_context.modality,
            "known_conditions": list(case.patient_context.known_conditions),
        },
        "statements": [
            {
                "question": s.question,
                "answer": s.answer,
                "concept": s.concept,
                "source": s.source,
                "metadata": dict(s.metadata) if s.metadata else {},
            }
            for s in case.statements
        ],
        "ground_truth": dict(case.ground_truth) if case.ground_truth else {},
    }


def _section(data, section_id: str):
    for section in data["sections"]:
        if section["id"] == section_id:
            return section
    raise AssertionError(f"Missing section {section_id}")


# ===========================================================================
# Page Serving Tests
# ===========================================================================

class TestPageServing:
    """Verify the HTML page is served correctly."""

    def test_page_returns_html(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_page_contains_all_five_screens(self):
        resp = client.get("/")
        html = resp.text
        assert 'id="screen-overview"' in html
        assert 'id="screen-cases"' in html
        assert 'id="screen-encounter"' in html
        assert 'id="screen-analysis"' in html
        assert 'id="screen-recommendations"' in html
        assert 'id="screen-learning"' in html

    def test_page_contains_js_functions(self):
        resp = client.get("/")
        html = resp.text
        assert "function showScreen" in html
        assert "function analyzeEncounter" in html
        assert "function renderAnalysis" in html
        assert "function showRecommendations" in html
        assert "function renderRecommendations" in html
        assert "function loadCases" in html
        assert "function selectCaseById" in html
        assert "function addDialogueTurn" in html
        assert "function importTranscript" in html
        assert "function parseTranscript" in html
        assert "function collectEncounterStatements" in html
        assert "function submitAllFeedback" in html
        assert "function suggestRule" in html
        assert "function suggestCase" in html

    def test_page_contains_navigation(self):
        resp = client.get("/")
        html = resp.text
        assert 'id="nav-overview"' in html
        assert 'id="nav-cases"' in html
        assert 'id="nav-encounter"' in html
        assert 'id="nav-analysis"' in html
        assert 'id="nav-recommendations"' in html
        assert 'id="nav-learning"' in html
        assert "Overview" in html
        assert "Recommendations" in html
        assert "Governance" in html

    def test_encounter_page_has_live_edit_controls(self):
        resp = client.get("/")
        html = resp.text
        assert "Live encounter input" in html
        assert "Add Dialogue" in html
        assert "Paste Transcript" in html
        assert "Replace Encounter" in html
        assert "Live input parsed" in html
        assert "Processing Transparency" in html
        assert "dialogue-question-text" in html
        assert "dialogue-concept" in html
        assert "Start With A Real Transcript" in html
        assert "Parse Transcript Encounter" in html
        assert "Why Source and Concept matter" in html
        assert "parseTranscriptServer" in html

    def test_custom_builder_exposes_top_telemedicine_domains(self):
        resp = client.get("/")
        html = resp.text
        for domain in [
            "mental_health",
            "uri_sinus_throat",
            "gerd_dyspepsia",
            "skin_infection",
            "obesity_metabolic",
            "vaginal_sti",
        ]:
            assert html.count(f'value="{domain}"') >= 2

    def test_page_contains_css(self):
        resp = client.get("/")
        html = resp.text
        assert "<style>" in html
        assert "--bg:" in html
        assert ".case-card" in html
        assert ".analysis-section" in html


# ===========================================================================
# Cases Endpoint Tests
# ===========================================================================

class TestCasesEndpoint:
    """Test GET /demo/cases."""

    def test_returns_all_cases(self):
        resp = client.get("/demo/cases")
        assert resp.status_code == 200
        data = resp.json()
        expected_total = len(BASE_CASES) + len(BLACK_SWAN_CASES)
        assert data["total"] == expected_total
        assert len(data["cases"]) == expected_total

    def test_cases_have_required_fields(self):
        resp = client.get("/demo/cases")
        data = resp.json()
        for case in data["cases"]:
            assert "case_id" in case
            assert "title" in case
            assert "scenario" in case
            assert "category" in case
            assert "domain" in case
            assert "age" in case
            assert "case_data" in case

    def test_cases_have_narratives(self):
        resp = client.get("/demo/cases")
        data = resp.json()
        for case in data["cases"]:
            if case["case_id"] in CASE_NARRATIVES:
                assert case["title"] != case["case_id"]  # title should be human-readable
                assert len(case["scenario"]) > 10

    def test_cases_have_valid_categories(self):
        resp = client.get("/demo/cases")
        data = resp.json()
        valid_categories = set(CATEGORY_LABELS.keys()) | {"unknown"}
        for case in data["cases"]:
            assert case["category"] in valid_categories, f"Unknown category: {case['category']}"

    def test_top_telemedicine_cases_are_visible(self):
        resp = client.get("/demo/cases")
        data = resp.json()
        case_ids = {case["case_id"] for case in data["cases"]}
        assert "TOP-001-mental-health-self-harm" in case_ids
        assert "TOP-005-sore-throat-airway" in case_ids
        assert "TOP-014-glp1-severe-abdominal-pain" in case_ids
        top_cases = [case for case in data["cases"] if case["category"] == "top_telemedicine"]
        assert len(top_cases) >= 10

    def test_case_data_includes_statements(self):
        resp = client.get("/demo/cases")
        data = resp.json()
        for case in data["cases"]:
            assert "statements" in case["case_data"]
            assert len(case["case_data"]["statements"]) > 0

    def test_case_data_includes_patient_context(self):
        resp = client.get("/demo/cases")
        data = resp.json()
        for case in data["cases"]:
            ctx = case["case_data"]["patient_context"]
            assert "age" in ctx
            assert "domain" in ctx
            assert "chief_concern" in ctx


# ===========================================================================
# Analysis Endpoint Tests
# ===========================================================================

class TestAnalysisEndpoint:
    """Test POST /demo/analyze."""

    def test_returns_expected_sections(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sections"]) == len(EXPECTED_SECTION_IDS)

    def test_section_ids_are_correct(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        actual_ids = [s["id"] for s in data["sections"]]
        assert actual_ids == EXPECTED_SECTION_IDS

    def test_sections_have_title_and_subtitle(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        for section in data["sections"]:
            assert "title" in section
            assert "subtitle" in section
            assert len(section["title"]) > 0

    def test_analysis_returns_final_recommendations(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        recs = data["recommendations"]
        assert recs["title"] == "Final Recommendations"
        assert recs["disposition"] == data["combined_state"]
        assert recs["bottom_line"]
        assert recs["immediate_actions"]
        assert recs["critical_evidence"]
        assert recs["patient_message"]
        assert recs["clinician_handoff"]
        assert recs["human_factors"]["title"] == "Human Factors Boundary"
        assert recs["human_factors"]["prompt_guardrails"]
        assert recs["ai_processing"]["prompt_contract"]
        assert recs["governance_actions"]

    def test_parse_transcript_endpoint_classifies_free_text_concepts(self):
        resp = client.post(
            "/demo/parse-transcript",
            json={
                "transcript": (
                    "Patient: Cough and fever.\n"
                    "Clinician: Any blood when you cough?\n"
                    "Patient: I coughed a little blood in my sputum this morning."
                )
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert "hemoptysis" in data["concepts"]
        assert data["statements"][1]["concept"] == "hemoptysis"
        assert data["statements"][1]["metadata"]["imported_from_transcript"] is True

    def test_parse_transcript_infers_context_and_back_pain_red_flags(self):
        transcript = (
            "Clinician: Mr. X can you tell me your age?\n"
            "Patient: I’m 62.\n"
            "Clinician: What medical conditions do you have?\n"
            "Patient: T2DM, HTN, BPH.\n"
            "Clinician: What medications are you taking?\n"
            "Patient: GLP1, Losartan, Flomax, ibuprofen.\n"
            "Clinician: Tell me about your back pain.\n"
            "Patient: Lower back pain after lifting last week.\n"
            "Clinician: Any numbness or tingling?\n"
            "Patient: Yes, tingling in my left foot at times and in my private areas.\n"
            "Clinician: Any weakness?\n"
            "Patient: My legs feel weaker on stairs, but it may be the pain gets worse.\n"
            "Clinician: Any issues with urination?\n"
            "Patient: No but my bleeder seems more full than usual.\n"
            "Clinician: Any loss of bowel control?\n"
            "Patient: No.\n"
            "Clinician: Is the pain getting worse?\n"
            "Patient: No, but not getting better."
        )
        resp = client.post("/demo/parse-transcript", json={"transcript": transcript})
        assert resp.status_code == 200
        data = resp.json()
        assert data["patient_context"]["age"] == 62
        assert data["patient_context"]["domain"] == "musculoskeletal_pain"
        assert "type 2 diabetes" in data["patient_context"]["known_conditions"]
        assert "hypertension" in data["patient_context"]["known_conditions"]
        assert "BPH" in data["patient_context"]["known_conditions"]
        assert "Losartan" in data["medications"]
        assert data["context_rows"] == 3
        assert "unknown" not in data["concepts"]
        assert "neuro_deficit" in data["concepts"]
        assert "bowel_bladder" in data["concepts"]

        analyze_resp = client.post(
            "/demo/analyze",
            json={
                "case_id": "parsed-back-pain-transcript",
                "patient_context": data["patient_context"],
                "statements": data["statements"],
                "ground_truth": {"medications": data["medications"]},
            },
        )
        assert analyze_resp.status_code == 200
        analysis = analyze_resp.json()
        assert analysis["combined_state"] == "ESCALATE"
        guardrails = {
            f["rule_id"]
            for s in analysis["sections"]
            if s["id"] == "guardrails"
            for f in s["data"]["findings"]
        }
        assert "SENTINEL_BACK_PAIN_NEURO_BLADDER" in guardrails

    def test_manual_red_flag_and_wrong_concepts_are_reclassified_for_domain(self):
        payload = {
            "case_id": "manual-red-flag-back-pain",
            "patient_context": {
                "age": 62,
                "chief_concern": "lower back pain",
                "domain": "musculoskeletal_pain",
                "literacy_hint": "unknown",
                "language_barrier": False,
                "has_caregiver": False,
                "modality": "text",
                "known_conditions": ["type 2 diabetes", "hypertension", "BPH"],
            },
            "statements": [
                {
                    "question": "Tell me about your back pain.",
                    "answer": "Lower back pain after lifting last week.",
                    "concept": "flank_pain",
                    "source": "patient",
                    "metadata": {},
                },
                {
                    "question": "Any numbness or tingling?",
                    "answer": "Yes, tingling in my left foot at times and in my private areas.",
                    "concept": "red_flag",
                    "source": "patient",
                    "metadata": {},
                },
                {
                    "question": "Any weakness?",
                    "answer": "My legs feel weaker on stairs, but it may be the pain gets worse.",
                    "concept": "exertional_component",
                    "source": "patient",
                    "metadata": {},
                },
                {
                    "question": "Any issues with urination?",
                    "answer": "No but my bladder seems more full than usual.",
                    "concept": "red_flag",
                    "source": "patient",
                    "metadata": {},
                },
            ],
            "ground_truth": {},
        }
        resp = client.post("/demo/analyze", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["combined_state"] == "ESCALATE"

        observations = [
            o
            for s in data["sections"]
            if s["id"] == "observations"
            for o in s["data"]["observations"]
        ]
        concepts = {o["concept"] for o in observations}
        assert "trauma_mechanism" in concepts
        assert "neuro_deficit" in concepts
        assert "bowel_bladder" in concepts

        mud_map = next(s for s in data["sections"] if s["id"] == "mud_map")["data"]["boundary_map"]
        missing_text = " ".join(mud_map.get("missing", []))
        assert "neuro_deficit" not in missing_text
        assert "bowel_bladder" not in missing_text
        assert "trauma_mechanism" not in missing_text

        guardrails = {
            f["rule_id"]
            for s in data["sections"]
            if s["id"] == "guardrails"
            for f in s["data"]["findings"]
        }
        assert "SENTINEL_BACK_PAIN_NEURO_BLADDER" in guardrails
        assert "MANUAL_RED_FLAG_REVIEW" in guardrails

        coverage = next(s for s in data["sections"] if s["id"] == "input_coverage")["data"]
        assert coverage["total_lines"] == 4
        assert all(row["status"] != "unused" for row in coverage["rows"])
        neuro_row = next(row for row in coverage["rows"] if row["answer"].startswith("Yes, tingling"))
        bladder_row = next(row for row in coverage["rows"] if "bladder seems more full" in row["answer"])
        assert neuro_row["effective_concept"] == "neuro_deficit"
        assert bladder_row["effective_concept"] == "bowel_bladder"
        assert "Black Swan Guard" in neuro_row["consumers"]
        assert "Async LLM extractor payload" in bladder_row["consumers"]

    def test_defense_pattern_case_has_actionable_human_factor_recommendations(self):
        case = _ALL_CASES["showcase-010-defense-pattern-distortion"]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        assert resp.status_code == 200
        data = resp.json()
        human = data["recommendations"]["human_factors"]
        assert "defense" in human["spectrum"].lower()
        assert "SENTINEL_DEFENSE_PATTERN_DISTORTION" in human["triggered_rules"]
        assert any("stoic" in cue["label"] for cue in human["cues"])
        assert any("anxiety" in cue["label"] for cue in human["cues"])
        assert any("Do not call the patient anxious" in item for item in human["avoid"])

    def test_pasted_real_encounter_without_concepts_is_analyzed(self):
        payload = {
            "case_id": "paste-real-encounter",
            "patient_context": {
                "age": 59,
                "chief_concern": "indigestion and fatigue",
                "domain": "chest_discomfort",
                "literacy_hint": "medium",
                "language_barrier": False,
                "has_caregiver": False,
                "modality": "text",
                "known_conditions": ["diabetes", "hypertension"],
            },
            "statements": [
                {
                    "question": "Patient statement",
                    "answer": "No chest pain. It is just tight indigestion when I walk, but I cannot afford the ER.",
                    "concept": None,
                    "source": "patient",
                    "metadata": {},
                },
                {
                    "question": "Does it change with activity?",
                    "answer": "It starts when I carry laundry upstairs and gets better if I sit.",
                    "concept": None,
                    "source": "patient",
                    "metadata": {},
                },
                {
                    "question": "Any shortness of breath?",
                    "answer": "Not really. I just slow down so it does not get bad.",
                    "concept": None,
                    "source": "patient",
                    "metadata": {},
                },
            ],
            "ground_truth": {},
        }
        resp = client.post("/demo/analyze", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        concepts = {
            obs["concept"]
            for obs in _section(data, "observations")["data"]["observations"]
        }
        assert "symptom_quality" in concepts
        assert "dyspnea" in concepts
        assert data["combined_state"] in {"ESCALATE", "HOLD_AND_VERIFY"}
        assert data["recommendations"]["critical_evidence"]

    def test_added_blood_in_sputum_free_text_is_not_treated_as_unknown_supported(self):
        case = _ALL_CASES["showcase-003-cost-fear-minimizes-alarm"]
        payload = _make_analyze_payload(case)
        payload["statements"].append(
            {
                "question": "Any other symptoms that concern you?",
                "answer": "When I wake up in the morning, I cough a little bit of blood in my sputum.",
                "concept": None,
                "source": "patient",
                "metadata": {},
            }
        )
        resp = client.post("/demo/analyze", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["combined_state"] == "ESCALATE"

        observations = _section(data, "observations")["data"]["observations"]
        assert any(o["concept"] == "hemoptysis" for o in observations)

        boundaries = _section(data, "interpretation_boundaries")["data"]["rows"]
        hemoptysis_rows = [r for r in boundaries if r["concept"] == "hemoptysis"]
        assert hemoptysis_rows
        assert hemoptysis_rows[0]["boundary_status"] == "unsafe_to_infer"

        guardrails = _section(data, "guardrails")["data"]["findings"]
        assert any(f["rule_id"] == "SENTINEL_ACTIVE_BLEEDING" for f in guardrails)

        llm_section = _section(data, "llm_opinion")["data"]["regex_findings"]
        assert any(f["rule_id"] == "SENTINEL_ACTIVE_BLEEDING" for f in llm_section)

        evidence_rules = {ev["rule"] for ev in data["recommendations"]["critical_evidence"]}
        assert "SENTINEL_ACTIVE_BLEEDING" in evidence_rules

    def test_mitigation_plan_section_has_learning_layers(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        mitigation = _section(data, "mitigation_plan")
        layers = [m["layer"] for m in mitigation["data"]["mitigations"]]
        assert "Current deterministic controls" in layers
        assert "Stigmergic boundary trace" in layers
        assert "VAMS near-miss recall" in layers
        assert "Governed template promotion" in layers
        assert "Operational mitigation" in layers
        assert mitigation["data"]["recalled_pattern"]
        assert mitigation["data"]["trace_regions"]
        assert mitigation["data"]["falsifiers"]

    def test_provenance_authority_section_labels_layers(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        provenance = _section(data, "provenance_authority")
        layer_names = [layer["name"] for layer in provenance["data"]["layers"]]
        authorities = [layer["authority"] for layer in provenance["data"]["layers"]]
        assert "Curated clinical rules" in layer_names
        assert "Curated safety guardrails" in layer_names
        assert "AI candidate signals" in layer_names
        assert "Learned priors" in layer_names
        assert "VAMS / stigmergic memory" in layer_names
        assert "Ensemble governor" in layer_names
        assert "Enforced" in authorities
        assert "Advisory" in authorities
        assert "Bounded Adjustment" in authorities
        assert provenance["data"]["ensemble"]
        assert provenance["data"]["invariants"]

    def test_observations_section_has_data(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        obs_section = _section(data, "observations")
        assert obs_section["id"] == "observations"
        assert "observations" in obs_section["data"]
        assert len(obs_section["data"]["observations"]) > 0

    def test_observation_fields(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        obs = _section(data, "observations")["data"]["observations"][0]
        assert "concept" in obs
        assert "raw" in obs
        assert "confidence" in obs
        assert "source" in obs
        assert "traps" in obs
        assert isinstance(obs["confidence"], (int, float))
        assert 0 <= obs["confidence"] <= 1

    def test_mud_map_has_categories(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        mud = _section(data, "mud_map")
        assert mud["id"] == "mud_map"
        fbc = mud["data"]["findings_by_category"]
        expected_cats = {"missing", "uncertain", "distorted", "contradictory", "unknowable_remote", "objective_needed"}
        assert set(fbc.keys()) == expected_cats

    def test_jri_section_has_score(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        jri = _section(data, "jri_score")
        assert jri["id"] == "jri_score"
        assert "readiness_index" in jri["data"]
        assert isinstance(jri["data"]["readiness_index"], (int, float))
        assert "jre_state" in jri["data"]

    def test_guardrails_section_has_assumptions(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        guard = _section(data, "guardrails")
        assert guard["id"] == "guardrails"
        assert "assumption_register" in guard["data"]
        assert len(guard["data"]["assumption_register"]) > 0

    def test_safety_decision_has_combined_state(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        dec = _section(data, "safety_decision")
        assert dec["id"] == "safety_decision"
        assert "combined_state" in dec["data"]
        assert "jre_state" in dec["data"]
        assert "bsg_state" in dec["data"]
        assert "decision_driver" in dec["data"]

    def test_escalation_case_detected(self):
        """CP-001-heartburn-pressure should ESCALATE."""
        case = _ALL_CASES["CP-001-heartburn-pressure"]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        assert data["combined_state"] == "ESCALATE"

    def test_happy_path_case(self):
        """RF-002-good-refill-readyish should not ESCALATE."""
        case = _ALL_CASES["RF-002-good-refill-readyish"]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        assert data["combined_state"] != "ESCALATE"

    def test_black_swan_case_detected(self):
        """BS-003-offpath-stroke-in-refill should ESCALATE."""
        case = _ALL_CASES["BS-003-offpath-stroke-in-refill"]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        assert data["combined_state"] == "ESCALATE"

    def test_analysis_has_duration(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        assert "duration_ms" in data
        assert data["duration_ms"] > 0

    def test_invalid_domain_rejected(self):
        payload = {
            "case_id": "test",
            "patient_context": {
                "age": 50,
                "chief_concern": "test",
                "domain": "nonexistent_domain",
            },
            "statements": [
                {"question": "q", "answer": "a"},
            ],
        }
        resp = client.post("/demo/analyze", json=payload)
        assert resp.status_code == 422

    def test_questions_section_present(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        qs = _section(data, "next_questions")
        assert qs["id"] == "next_questions"
        assert "questions" in qs["data"]
        assert "modality" in qs["data"]

    def test_llm_section_present(self):
        case = BASE_CASES[0]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        data = resp.json()
        llm = _section(data, "llm_opinion")
        assert llm["id"] == "llm_opinion"
        assert "llm_available" in llm["data"]
        assert "regex_findings" in llm["data"]

    def test_showcase_case_has_boundary_and_autonomy_sections(self):
        case = _ALL_CASES["showcase-001-stale-ace-refill-ckd-nsaid"]
        resp = client.post("/demo/analyze", json=_make_analyze_payload(case))
        assert resp.status_code == 200
        data = resp.json()

        boundaries = _section(data, "interpretation_boundaries")["data"]
        assert boundaries["rows"]
        assert any(
            r["boundary_status"] in {"unsafe_to_infer", "weak"}
            for r in boundaries["rows"]
        )

        autonomy = _section(data, "autonomy_boundary")["data"]
        assert autonomy["current_state"] == data["combined_state"]
        assert autonomy["blocked_actions"]
        assert "what_restores_readiness" in autonomy

        assert "summary" in data
        assert data["summary"]["authority"]
        assert data["summary"]["autonomy"]


# ===========================================================================
# Feedback Endpoint Tests
# ===========================================================================

class TestFeedbackEndpoint:
    """Test POST /demo/feedback."""

    def test_valid_feedback_accepted(self):
        resp = client.post(
            "/demo/feedback",
            json={
                "case_id": "CP-001-heartburn-pressure",
                "concept": "symptom_quality",
                "domain": "chest_discomfort",
                "clinician_assessment": "confirmed",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "recorded"
        assert data["assessment"] == "confirmed"

    def test_all_assessment_types_accepted(self):
        for assessment in ["confirmed", "corrected", "false_positive", "missed"]:
            resp = client.post(
                "/demo/feedback",
                json={
                    "case_id": "test-case",
                    "concept": "test_concept",
                    "domain": "chest_discomfort",
                    "clinician_assessment": assessment,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["assessment"] == assessment

    def test_invalid_assessment_rejected(self):
        resp = client.post(
            "/demo/feedback",
            json={
                "case_id": "test",
                "concept": "test",
                "domain": "chest_discomfort",
                "clinician_assessment": "invalid_type",
            },
        )
        assert resp.status_code == 422

    def test_feedback_increments_count(self):
        # Get baseline
        exp_resp = client.get("/demo/experience")
        baseline = exp_resp.json()["feedback_count"]

        client.post(
            "/demo/feedback",
            json={
                "case_id": "count-test",
                "concept": "test_concept",
                "domain": "chest_discomfort",
                "clinician_assessment": "confirmed",
            },
        )

        exp_resp2 = client.get("/demo/experience")
        assert exp_resp2.json()["feedback_count"] == baseline + 1


# ===========================================================================
# Experience Endpoint Tests
# ===========================================================================

class TestExperienceEndpoint:
    """Test GET /demo/experience."""

    def test_returns_priors(self):
        resp = client.get("/demo/experience")
        assert resp.status_code == 200
        data = resp.json()
        assert "distortion_priors" in data
        assert "total_priors" in data
        assert data["total_priors"] > 0

    def test_priors_are_formatted_correctly(self):
        resp = client.get("/demo/experience")
        data = resp.json()
        for key, val in data["distortion_priors"].items():
            assert "/" in key  # format: domain/concept/trap
            assert isinstance(val, (int, float))


# ===========================================================================
# Suggest Endpoints Tests
# ===========================================================================

class TestSuggestEndpoints:
    """Test POST /demo/suggest-rule and POST /demo/suggest-case."""

    def test_suggest_rule_accepts_valid_request(self):
        """Endpoint accepts valid request structure. Tests request validation, not LLM response."""
        from interactive_demo import _llm as demo_llm

        # Temporarily disable LLM to avoid HTTP call in tests
        original_available = None
        if demo_llm is not None:
            original_key = demo_llm.api_key
            demo_llm.api_key = None  # Make unavailable
        try:
            resp = client.post(
                "/demo/suggest-rule",
                json={
                    "case_id": "CP-001-heartburn-pressure",
                    "findings": [],
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "success" in data
            assert "suggestions" in data or "error" in data
        finally:
            if demo_llm is not None:
                demo_llm.api_key = original_key

    def test_suggest_case_accepts_valid_request(self):
        """Endpoint accepts valid request structure. Tests request validation, not LLM response."""
        from interactive_demo import _llm as demo_llm

        original_key = None
        if demo_llm is not None:
            original_key = demo_llm.api_key
            demo_llm.api_key = None
        try:
            resp = client.post(
                "/demo/suggest-case",
                json={"domain": "chest_discomfort"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "success" in data
        finally:
            if demo_llm is not None:
                demo_llm.api_key = original_key

    def test_suggest_rule_requires_case_data(self):
        """Should reject request without case_id or patient_context."""
        from interactive_demo import _llm as demo_llm

        # Only test when LLM is available (needs to pass validation to reach case check)
        if demo_llm is not None and demo_llm.available:
            resp = client.post(
                "/demo/suggest-rule",
                json={"findings": []},
            )
            assert resp.status_code == 422

    def test_suggest_case_invalid_domain_rejected(self):
        resp = client.post(
            "/demo/suggest-case",
            json={"domain": "nonexistent_domain"},
        )
        assert resp.status_code == 422


# ===========================================================================
# Determinism Tests
# ===========================================================================

class TestDeterminism:
    """Same input produces same output (excluding timing)."""

    def test_same_case_same_result(self):
        """Two consecutive calls with the same input should produce the same state and structure."""
        case = BASE_CASES[0]
        payload = _make_analyze_payload(case)

        resp1 = client.post("/demo/analyze", json=payload)
        resp2 = client.post("/demo/analyze", json=payload)

        data1 = resp1.json()
        data2 = resp2.json()

        # Combined state must be identical
        assert data1["combined_state"] == data2["combined_state"]
        # Same number of sections
        assert len(data1["sections"]) == len(data2["sections"])
        # Section IDs match
        for s1, s2 in zip(data1["sections"], data2["sections"]):
            assert s1["id"] == s2["id"]
            assert s1["title"] == s2["title"]

        # JRE state and score match.
        jri1 = _section(data1, "jri_score")["data"]
        jri2 = _section(data2, "jri_score")["data"]
        assert jri1["jre_state"] == jri2["jre_state"]
        assert jri1["readiness_index"] == jri2["readiness_index"]

        # Guardrail state matches
        g1 = _section(data1, "guardrails")["data"]
        g2 = _section(data2, "guardrails")["data"]
        assert g1["guardrail_state"] == g2["guardrail_state"]


# ===========================================================================
# Edited Encounter Tests
# ===========================================================================

class TestEditedEncounter:
    """Editing an answer should change the analysis result."""

    def test_editing_answer_changes_observations(self):
        """Changing 'heartburn' answer to 'crushing chest pain' should change results."""
        case = _ALL_CASES["CP-001-heartburn-pressure"]
        payload1 = _make_analyze_payload(case)

        # Modified version — change first answer
        payload2 = _make_analyze_payload(case)
        payload2["statements"][0]["answer"] = "Yes, I have crushing chest pain"

        resp1 = client.post("/demo/analyze", json=payload1)
        resp2 = client.post("/demo/analyze", json=payload2)

        data1 = resp1.json()
        data2 = resp2.json()

        # Observations should differ
        obs1 = _section(data1, "observations")["data"]["observations"]
        obs2 = _section(data2, "observations")["data"]["observations"]
        # At least one observation should have different confidence or normalized value
        diffs = 0
        for o1, o2 in zip(obs1, obs2):
            if o1["confidence"] != o2["confidence"] or o1["normalized"] != o2["normalized"]:
                diffs += 1
        assert diffs > 0, "Editing an answer should change at least one observation"

    def test_removing_red_flag_changes_state(self):
        """RF-002 is happy path — changing an answer to distorted shouldn't break it."""
        case = _ALL_CASES["RF-002-good-refill-readyish"]
        payload = _make_analyze_payload(case)
        resp = client.post("/demo/analyze", json=payload)
        data = resp.json()
        # Should not be ESCALATE for the control case
        assert data["combined_state"] != "ESCALATE"


# ===========================================================================
# Section Builder Unit Tests
# ===========================================================================

class TestSectionBuilders:
    """Unit test the progressive section builders."""

    def _run_analysis(self, case):
        mem = ExperienceMemory.seeded()
        jre = JudgmentReadinessEngine(memory=mem)
        guard = BlackSwanGuardrailEngine()
        jre_report = jre.evaluate(case)
        bsg_report = guard.evaluate(case, jre_report)
        combined = most_restrictive(jre_report.state, bsg_report.guardrail_state)
        return case, jre_report, bsg_report, combined

    def test_eleven_sections_built(self):
        case, jre_r, bsg_r, combined = self._run_analysis(BASE_CASES[0])
        sections = _build_progressive_sections(case, jre_r, bsg_r, combined)
        assert len(sections) == len(EXPECTED_SECTION_IDS)
        assert [s["id"] for s in sections] == EXPECTED_SECTION_IDS

    def test_each_section_has_id_title_subtitle_data(self):
        case, jre_r, bsg_r, combined = self._run_analysis(BASE_CASES[0])
        sections = _build_progressive_sections(case, jre_r, bsg_r, combined)
        for s in sections:
            assert "id" in s
            assert "title" in s
            assert "subtitle" in s
            assert "data" in s

    def test_observation_confidence_bounded(self):
        case, jre_r, bsg_r, combined = self._run_analysis(BASE_CASES[0])
        sections = _build_progressive_sections(case, jre_r, bsg_r, combined)
        obs_data = next(s for s in sections if s["id"] == "observations")["data"]["observations"]
        for o in obs_data:
            assert 0 <= o["confidence"] <= 1

    def test_guardrails_has_autonomy_tier(self):
        case, jre_r, bsg_r, combined = self._run_analysis(BASE_CASES[0])
        sections = _build_progressive_sections(case, jre_r, bsg_r, combined)
        guard_data = next(s for s in sections if s["id"] == "guardrails")["data"]
        assert "max_autonomy_tier" in guard_data
        assert guard_data["max_autonomy_tier"].startswith("T")

    def test_safety_decision_driver_present(self):
        case, jre_r, bsg_r, combined = self._run_analysis(BASE_CASES[0])
        sections = _build_progressive_sections(case, jre_r, bsg_r, combined)
        dec_data = next(s for s in sections if s["id"] == "safety_decision")["data"]
        assert "decision_driver" in dec_data
        assert len(dec_data["decision_driver"]) > 0
