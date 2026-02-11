from backend.app.core.agents.mechanic import resolve
from backend.app.core.nodes.narrative_validator import narrative_validator_node
from backend.app.models.state import CharacterSheet, GameState


def _state(user_input: str, intent_type: str | None = None) -> GameState:
    return GameState(
        campaign_id="c1",
        player_id="p1",
        user_input=user_input,
        intent="ACTION",
        player_intent={"intent_type": intent_type} if intent_type else None,
        current_location="imperial garrison",
        player=CharacterSheet(character_id="p1", name="Hero", stats={"Combat": 2}, hp_current=10),
        campaign={"world_time_minutes": 120, "world_state_json": {}},
    )


def test_mechanic_produces_difficulty_tier_and_outcome():
    result = resolve(_state("I attack the guard", "FIGHT"))
    assert result.outcome is not None
    assert result.outcome.difficulty in {5, 10, 15, 20, 25}
    assert result.outcome.result in {"CRIT_FAIL", "FAIL", "PARTIAL", "SUCCESS", "CRIT_SUCCESS"}


def test_mechanic_produces_state_delta_authoritatively():
    result = resolve(_state("I attack the guard", "FIGHT"))
    assert result.state_delta.time_minutes >= 0
    # attack always sets at least one fact/heat-affecting flag when target exists
    assert isinstance(result.state_delta.facts, dict)


def test_validator_repairs_invalid_choice_count_and_adds_turn_contract():
    state = {
        "final_text": "You fail to force the lock.",
        "mechanic_result": {"success": False, "outcome": {"check": "LOCK", "result": "FAIL"}, "state_delta": {"time_minutes": 5}},
        "suggested_actions": [{"id": "only", "label": "Wait", "intent_text": "wait", "risk_level": "SAFE"}],
        "scene_frame": {"player_objective": "Open the vault", "immediate_situation": "Locked door"},
        "warnings": [],
        "campaign": {"world_state_json": {}},
    }
    out = narrative_validator_node(state)
    assert "turn_contract" in out
    assert len(out["turn_contract"]["choices"]) >= 2
