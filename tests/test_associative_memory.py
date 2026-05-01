from jre import ADVISORY_AUTHORITY, NearMissMemory


def test_near_miss_memory_recalls_best_partial_signature_match():
    memory = NearMissMemory()
    low_overlap = memory.store(
        signature_keys=["dyspnea denial", "functional probe missing", "no pulse ox"],
        missing_nodes=["current oxygen saturation"],
        falsifiers=["walk test without dyspnea"],
        recommended_actions=["ask functional breathing probe"],
        strength=0.8,
    )
    high_overlap = memory.store(
        signature_keys=["nsaid use", "ckd", "no current blood pressure", "medication refill"],
        missing_nodes=["current blood pressure", "renal function"],
        falsifiers=["normal same-day BP and creatinine"],
        recommended_actions=["block refill until objective data reviewed"],
        strength=0.7,
    )

    recalls = memory.recall(["CKD", "NSAID use", "medication refill"])

    assert recalls[0].pattern.memory_id == high_overlap.memory_id
    assert recalls[0].score > 0
    assert low_overlap.memory_id not in [recall.pattern.memory_id for recall in recalls]
    assert recalls[0].authority == ADVISORY_AUTHORITY


def test_near_miss_memory_strengthen_and_weaken_are_hebbian_feedback():
    memory = NearMissMemory()
    pattern = memory.store(
        signature_keys=["source conflict", "destination capability gap"],
        missing_nodes=["capability verification"],
        recommended_actions=["verify destination monitoring"],
        strength=0.5,
    )

    memory.strengthen(pattern.memory_id, amount=0.25)
    assert pattern.strength == 0.75
    assert pattern.success_count == 1

    memory.weaken(pattern.memory_id, amount=0.50)
    assert pattern.strength == 0.25
    assert pattern.failure_count == 1


def test_near_miss_suggest_returns_advisory_pattern_completion():
    memory = NearMissMemory()
    pattern = memory.store(
        signature_keys=["older adult", "falls risk", "no caregiver", "home dispo"],
        missing_nodes=["baseline mobility", "caregiver availability"],
        falsifiers=["independent ambulation documented", "confirmed caregiver tonight"],
        recommended_actions=["route to disposition review"],
        metadata={"source": "synthetic near miss"},
        strength=0.9,
    )

    suggestion = memory.suggest(["falls risk", "home dispo"])

    assert suggestion["authority"] == ADVISORY_AUTHORITY
    assert suggestion["memory_ids"] == [pattern.memory_id]
    assert "baseline mobility" in suggestion["missing_nodes"]
    assert "confirmed caregiver tonight" in suggestion["falsifiers"]
    assert "route to disposition review" in suggestion["recommended_actions"]
    assert "older adult" in suggestion["pattern_completion"]
    assert "no caregiver" in suggestion["pattern_completion"]
    assert "safe to discharge" not in str(suggestion).lower()
