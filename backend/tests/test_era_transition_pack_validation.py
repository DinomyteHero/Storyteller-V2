from backend.app.core.era_transition import validate_era_transition


def test_validate_transition_requires_target_pack_present():
    ok, reason = validate_era_transition("NEW_JEDI_ORDER", "LEGACY")
    assert not ok
    assert "No era pack found" in reason


def test_validate_transition_accepts_adjacent_eras_with_packs():
    ok, reason = validate_era_transition("REBELLION", "NEW_REPUBLIC")
    assert ok
    assert reason == "Adjacent era transition"
