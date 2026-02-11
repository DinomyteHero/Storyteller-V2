from backend.app.core.nodes.narrative_validator import (
    _check_constraint_contradictions,
    _check_mechanic_consistency,
    narrative_validator_node,
)


def test_mechanic_consistency_warns_on_success_language_for_failure():
    warnings = _check_mechanic_consistency("You succeeded in breaking the lock.", {"success": False})
    assert warnings


def test_constraint_checker_is_noop():
    assert _check_constraint_contradictions("x", ["y"]) == []


def test_validator_produces_turn_contract_and_validation_notes():
    state = {
        "final_text": "You succeeded in the attack.",
        "mechanic_result": {"success": False, "outcome": {"check": "ATTACK", "result": "FAIL"}, "state_delta": {"time_minutes": 5}},
        "suggested_actions": [
            {"id": "a1", "label": "Push forward", "intent_text": "attack", "risk_level": "RISKY"},
            {"id": "a2", "label": "Fall back", "intent_text": "retreat", "risk_level": "SAFE"},
        ],
        "campaign": {"world_state_json": {}},
        "warnings": [],
    }
    result = narrative_validator_node(state)
    assert "turn_contract" in result
    assert len(result["validation_notes"]) >= 1
