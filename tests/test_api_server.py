"""Tests for the FastAPI API server."""
import pytest

try:
    from fastapi.testclient import TestClient
    from api_server import app
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")


@pytest.fixture
def client():
    return TestClient(app)


SAMPLE_CASE = {
    "case_id": "test-001",
    "patient_context": {
        "age": 55,
        "chief_concern": "chest pressure",
        "domain": "chest_discomfort",
        "modality": "text",
    },
    "statements": [
        {
            "question": "Do you have chest pain?",
            "answer": "No pain, just pressure when I walk upstairs.",
            "concept": "symptom_quality",
        },
        {
            "question": "Does it change with activity?",
            "answer": "Yes, worse with stairs, better at rest.",
            "concept": "exertional_component",
        },
    ],
}


def test_health_endpoint(client):
    """Health endpoint returns 200 with status."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["cases_available"] > 0


def test_evaluate_endpoint(client):
    """Full pipeline evaluate endpoint works."""
    resp = client.post("/evaluate", json=SAMPLE_CASE)
    assert resp.status_code == 200
    data = resp.json()
    assert "case_id" in data
    assert "jre_report" in data
    assert "bsg_report" in data
    assert "combined_state" in data
    assert "duration_ms" in data
    assert data["case_id"] == "test-001"


def test_jre_endpoint(client):
    """JRE-only endpoint returns a readiness report."""
    resp = client.post("/jre", json=SAMPLE_CASE)
    assert resp.status_code == 200
    data = resp.json()
    assert "state" in data
    assert "scores" in data
    assert "findings" in data


def test_bsg_endpoint(client):
    """BSG endpoint returns a guardrail report."""
    resp = client.post("/bsg", json=SAMPLE_CASE)
    assert resp.status_code == 200
    data = resp.json()
    assert "guardrail_state" in data
    assert "assumption_register" in data


def test_cases_endpoint(client):
    """Cases listing returns base and black swan cases."""
    resp = client.get("/cases")
    assert resp.status_code == 200
    data = resp.json()
    assert "base_cases" in data
    assert "black_swan_cases" in data
    assert data["total"] > 0


def test_evaluate_case_by_id(client):
    """Named case evaluation works."""
    resp = client.post("/evaluate-case", json={"case_id": "CP-001-heartburn-pressure"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == "CP-001-heartburn-pressure"
    assert data["combined_state"] == "ESCALATE"


def test_evaluate_case_not_found(client):
    """404 for non-existent case ID."""
    resp = client.post("/evaluate-case", json={"case_id": "FAKE-CASE"})
    assert resp.status_code == 404


def test_logs_endpoint(client):
    """Logs endpoint returns summary."""
    # First make a request to generate some logs
    client.post("/evaluate-case", json={"case_id": "RF-002-good-refill-readyish"})
    resp = client.get("/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "recent_entries" in data


def test_evaluate_unsupported_domain_returns_422(client):
    """Unsupported domain returns 422 with list of supported domains."""
    bad_case = {
        "case_id": "test-bad-domain",
        "patient_context": {
            "age": 40,
            "chief_concern": "toothache",
            "domain": "dental_pain",
            "modality": "text",
        },
        "statements": [
            {"question": "What hurts?", "answer": "My tooth.", "concept": "symptom"},
        ],
    }
    resp = client.post("/evaluate", json=bad_case)
    assert resp.status_code == 422
    data = resp.json()
    assert "dental_pain" in data["detail"]
    assert "chest_discomfort" in data["detail"]

    # Also check /jre and /bsg
    resp2 = client.post("/jre", json=bad_case)
    assert resp2.status_code == 422
    resp3 = client.post("/bsg", json=bad_case)
    assert resp3.status_code == 422


def test_cors_headers(client):
    """CORS headers present on response."""
    resp = client.options(
        "/evaluate",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


def test_evaluate_escalation_case(client):
    """Escalation case correctly identified through API."""
    case = {
        "case_id": "api-escalation",
        "patient_context": {
            "age": 68,
            "chief_concern": "lisinopril refill",
            "domain": "med_refill_hypertension",
            "modality": "phone",
            "known_conditions": ["hypertension", "atrial fibrillation"],
        },
        "statements": [
            {
                "question": "Any side effects?",
                "answer": "No medication side effects, but my left side feels weak and my speech is slurred since breakfast.",
                "concept": "side_effects",
            },
        ],
    }
    resp = client.post("/evaluate", json=case)
    assert resp.status_code == 200
    data = resp.json()
    assert data["combined_state"] == "ESCALATE"


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------

def test_invalid_age_rejected(client):
    """API rejects age outside 0-150."""
    payload = {
        "patient_context": {"age": -1, "chief_concern": "test", "domain": "chest_discomfort"},
        "statements": [{"question": "q", "answer": "a"}],
    }
    response = client.post("/evaluate", json=payload)
    assert response.status_code == 422


def test_invalid_modality_rejected(client):
    """API rejects unknown modality."""
    payload = {
        "patient_context": {"age": 50, "chief_concern": "test", "domain": "chest_discomfort", "modality": "telegraph"},
        "statements": [{"question": "q", "answer": "a"}],
    }
    response = client.post("/evaluate", json=payload)
    assert response.status_code == 422


def test_invalid_source_rejected(client):
    """API rejects unknown source."""
    payload = {
        "patient_context": {"age": 50, "chief_concern": "test", "domain": "chest_discomfort"},
        "statements": [{"question": "q", "answer": "a", "source": "psychic"}],
    }
    response = client.post("/evaluate", json=payload)
    assert response.status_code == 422


def test_invalid_literacy_hint_rejected(client):
    """API rejects unknown literacy hint."""
    payload = {
        "patient_context": {"age": 50, "chief_concern": "test", "domain": "chest_discomfort", "literacy_hint": "genius"},
        "statements": [{"question": "q", "answer": "a"}],
    }
    response = client.post("/evaluate", json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Log rotation tests
# ---------------------------------------------------------------------------

def test_health_shows_log_rotation(client):
    """Health endpoint includes log rotation info."""
    response = client.get("/health")
    data = response.json()
    assert "log_rotation_threshold" in data
    assert data["log_rotation_threshold"] == 10000


# ---------------------------------------------------------------------------
# POST /feedback endpoint tests (8 tests)
# ---------------------------------------------------------------------------

def test_feedback_confirmed_records(client):
    """POST confirmed feedback returns 200 with status=recorded."""
    payload = {
        "case_id": "CP-001",
        "concept": "symptom_quality",
        "domain": "chest_discomfort",
        "clinician_assessment": "confirmed",
    }
    resp = client.post("/feedback", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "recorded"
    assert data["assessment"] == "confirmed"
    assert data["total_feedback"] >= 1


def test_feedback_corrected_updates_priors(client):
    """POST corrected feedback with severity_adjustment returns 200."""
    payload = {
        "case_id": "RF-002",
        "concept": "home_bp_number",
        "domain": "med_refill_hypertension",
        "clinician_assessment": "corrected",
        "corrected_value": "systolic was actually 168",
        "severity_adjustment": 0.3,
    }
    resp = client.post("/feedback", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "recorded"
    assert data["assessment"] == "corrected"


def test_feedback_false_positive_accepted(client):
    """POST false_positive feedback returns 200."""
    payload = {
        "case_id": "CP-001",
        "concept": "symptom_quality",
        "domain": "chest_discomfort",
        "clinician_assessment": "false_positive",
    }
    resp = client.post("/feedback", json=payload)
    assert resp.status_code == 200
    assert resp.json()["assessment"] == "false_positive"


def test_feedback_missed_creates_prior(client):
    """POST missed feedback creates a new prior."""
    payload = {
        "case_id": "DY-001",
        "concept": "exertional_tolerance",
        "domain": "dyspnea_respiratory",
        "clinician_assessment": "missed",
    }
    resp = client.post("/feedback", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["assessment"] == "missed"
    assert data["priors_updated"] >= 1


def test_feedback_invalid_assessment_rejected(client):
    """POST with invalid clinician_assessment returns 422."""
    payload = {
        "case_id": "CP-001",
        "concept": "symptom_quality",
        "domain": "chest_discomfort",
        "clinician_assessment": "invalid_type",
    }
    resp = client.post("/feedback", json=payload)
    assert resp.status_code == 422


def test_feedback_total_increments(client):
    """Multiple feedback submissions increment total count."""
    baseline = client.get("/health").json()["feedback_recorded"]
    for i in range(3):
        client.post("/feedback", json={
            "case_id": f"incr-{i}", "concept": "glucose_number",
            "domain": "diabetes_hyperglycemia", "clinician_assessment": "confirmed",
        })
    after = client.get("/health").json()["feedback_recorded"]
    assert after >= baseline + 3


def test_feedback_with_notes(client):
    """POST feedback with notes field returns 200."""
    payload = {
        "case_id": "UTI-001",
        "concept": "fever_measured",
        "domain": "uti_symptoms",
        "clinician_assessment": "corrected",
        "notes": "Confirmed fever on exam.",
    }
    resp = client.post("/feedback", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "recorded"


def test_feedback_severity_adjustment_accepted(client):
    """POST feedback with severity_adjustment returns 200."""
    payload = {
        "case_id": "HA-001",
        "concept": "headache_onset",
        "domain": "headache_migraine",
        "clinician_assessment": "confirmed",
        "severity_adjustment": 0.5,
    }
    resp = client.post("/feedback", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "recorded"


# ---------------------------------------------------------------------------
# Edge case tests (6 tests)
# ---------------------------------------------------------------------------

def test_age_zero_accepted(client):
    """Age 0 (newborn) is within valid range."""
    payload = {
        "patient_context": {"age": 0, "chief_concern": "rash", "domain": "rash"},
        "statements": [{"question": "Describe?", "answer": "Red rash on chest"}],
    }
    assert client.post("/evaluate", json=payload).status_code == 200


def test_age_150_accepted(client):
    """Age 150 is at upper bound."""
    payload = {
        "patient_context": {"age": 150, "chief_concern": "refill", "domain": "med_refill_hypertension"},
        "statements": [{"question": "BP?", "answer": "120/80"}],
    }
    assert client.post("/evaluate", json=payload).status_code == 200


def test_age_151_rejected(client):
    """Age 151 exceeds upper bound."""
    payload = {
        "patient_context": {"age": 151, "chief_concern": "refill", "domain": "med_refill_hypertension"},
        "statements": [{"question": "BP?", "answer": "120/80"}],
    }
    assert client.post("/evaluate", json=payload).status_code == 422


def test_long_answer_handled(client):
    """Very long answer (2000+ chars) doesn't crash."""
    long_answer = "I have been experiencing chest pressure " * 50
    payload = {
        "patient_context": {"age": 55, "chief_concern": "chest", "domain": "chest_discomfort"},
        "statements": [{"question": "Describe?", "answer": long_answer}],
    }
    assert client.post("/evaluate", json=payload).status_code == 200


def test_duplicate_concepts_handled(client):
    """Multiple statements with same concept don't crash."""
    payload = {
        "patient_context": {"age": 50, "chief_concern": "chest", "domain": "chest_discomfort"},
        "statements": [
            {"question": "Pain?", "answer": "Not really pain", "concept": "symptom_quality"},
            {"question": "More?", "answer": "Heavy pressure in chest", "concept": "symptom_quality"},
            {"question": "Else?", "answer": "Burning sensation too", "concept": "symptom_quality"},
        ],
    }
    resp = client.post("/evaluate", json=payload)
    assert resp.status_code == 200
    assert "jre_report" in resp.json()


def test_in_person_modality_accepted(client):
    """in_person modality is accepted by API."""
    payload = {
        "patient_context": {"age": 45, "chief_concern": "rash", "domain": "rash", "modality": "in_person"},
        "statements": [{"question": "Show me?", "answer": "Red bumps on arm"}],
    }
    assert client.post("/evaluate", json=payload).status_code == 200


# ---------------------------------------------------------------------------
# Logs endpoint tests
# ---------------------------------------------------------------------------

def test_logs_structure(client):
    """GET /logs returns summary dict and recent_entries list."""
    resp = client.get("/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["summary"], dict)
    assert isinstance(data["recent_entries"], list)


def test_logs_grow_after_evaluation(client):
    """Log entries increase after an evaluation."""
    before = len(client.get("/logs").json()["recent_entries"])
    client.post("/evaluate-case", json={"case_id": "CP-001-heartburn-pressure"})
    after = len(client.get("/logs").json()["recent_entries"])
    assert after > before
