from backend.app.core.turn_contract import build_turn_contract
from backend.app.models.state import ActionSuggestion, MechanicOutput
from backend.app.models.turn_contract import TurnMeta


def test_choice_validator_enforces_unique_labels_and_intents():
    contract = build_turn_contract(
        mode="SIM",
        campaign_id="c1",
        turn_id="c1_t2",
        display_text="Text",
        scene_goal="Goal",
        obstacle="Obstacle",
        stakes="Stakes",
        mechanic_result=MechanicOutput(action_type="INTERACT", time_cost_minutes=2, success=True),
        suggested_actions=[
            ActionSuggestion(label="Continue", intent_text="continue", category="EXPLORE"),
            ActionSuggestion(label="Continue", intent_text="continue", category="SOCIAL"),
        ],
        meta=TurnMeta(),
        ledger_facts=None,
    )
    assert contract.debug is not None
    assert contract.debug.repair_count >= 0
    assert 2 <= len(contract.choices) <= 4
    assert len({c.intent.intent_type for c in contract.choices}) >= 2
