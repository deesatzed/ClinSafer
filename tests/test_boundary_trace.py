from jre import (
    BoundaryTraceField,
    TRACE_CLAIM,
    TRACE_CONSTRAINT,
    TRACE_RETRACTION,
    TRACE_SIGNAL,
)


def test_boundary_trace_reinforcement_opposition_and_decay():
    field = BoundaryTraceField()
    patch = field.apply_patch(
        TRACE_SIGNAL,
        concept="objective_data_gap",
        symbolic_keys=["No Current Vitals", "Destination Capability"],
        confidence=0.7,
        decay_rate=0.2,
    )

    initial_strength = patch.effective_strength()
    field.reinforce(patch.patch_id, magnitude=2.0, direction="support", evidence_ids=["ev-1"])

    assert patch.support_mass == 2.0
    assert patch.net_support == 2.0
    assert "ev-1" in patch.evidence_ids
    assert patch.effective_strength() > initial_strength

    field.oppose(patch.patch_id, magnitude=1.0)
    opposed_strength = patch.effective_strength()
    assert patch.opposition_mass == 1.0
    assert patch.support_ratio == 2.0 / 3.0

    field.decay(ticks=1.0)
    assert patch.support_mass < 2.0
    assert patch.opposition_mass < 1.0
    assert patch.effective_strength() < opposed_strength


def test_boundary_trace_search_sorts_by_review_pressure():
    field = BoundaryTraceField()
    weak = field.apply_patch(
        TRACE_CLAIM,
        concept="source_conflict",
        symbolic_keys=["source conflict", "follow-up"],
        confidence=0.4,
    )
    strong = field.apply_patch(
        TRACE_CONSTRAINT,
        concept="source_conflict",
        symbolic_keys=["source conflict", "objective missing"],
        confidence=0.8,
    )
    field.reinforce(strong.patch_id, magnitude=1.0)

    results = field.search(symbolic_keys=["SOURCE CONFLICT"])

    assert [item.patch_id for item in results] == [strong.patch_id, weak.patch_id]
    assert field.risk_pressure(symbolic_keys=["source conflict"]) >= strong.effective_strength()


def test_boundary_trace_retraction_removes_risk_pressure_from_original_patch():
    field = BoundaryTraceField()
    patch = field.apply_patch(
        TRACE_SIGNAL,
        concept="workflow_failure",
        symbolic_keys=["nonresponse after risk"],
        confidence=0.9,
    )
    before = field.risk_pressure(symbolic_keys=["nonresponse after risk"])

    retraction = field.retract(patch.patch_id, reason="resolved by callback")
    after = field.risk_pressure(symbolic_keys=["nonresponse after risk"])

    assert before > 0
    assert patch.status == "retracted"
    assert retraction.patch_type == TRACE_RETRACTION
    assert retraction.target_id == patch.patch_id
    assert after == 0
    assert field.summary()["retracted_patch_count"] == 1
