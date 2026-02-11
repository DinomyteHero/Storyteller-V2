"""Tests for action linting."""
import sys
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.action_lint import lint_actions
from backend.app.models.state import (
    ActionSuggestion,
    CharacterSheet,
    GameState,
    MechanicOutput,
    RouterOutput,
    ACTION_CATEGORY_SOCIAL,
    ACTION_CATEGORY_EXPLORE,
    ROUTER_ROUTE_TALK,
    ROUTER_ACTION_CLASS_DIALOGUE_ONLY,
)


class TestActionLint(unittest.TestCase):
    def test_lint_drops_invalid_and_pads(self) -> None:
        state = GameState(
            campaign_id="c1",
            player_id="p1",
            current_location="loc-tavern",
            present_npcs=[{"id": "npc-1", "name": "Barkeep", "role": "Barkeep"}],
            player=CharacterSheet(
                character_id="p1",
                name="Player",
                inventory=[{"item_name": "Medkit", "quantity": 1}],
            ),
        )

        router_out = RouterOutput(
            intent_text="hello",
            route=ROUTER_ROUTE_TALK,
            action_class=ROUTER_ACTION_CLASS_DIALOGUE_ONLY,
            requires_resolution=False,
        )
        mechanic = MechanicOutput(action_type="ATTACK", events=[], narrative_facts=[])

        actions = [
            ActionSuggestion(
                label="Talk to Ghost",
                intent_text="Ask Ghost for help.",
                category=ACTION_CATEGORY_SOCIAL,
            ),
            ActionSuggestion(
                label="Use Plasma Rifle",
                intent_text="I use the Plasma Rifle.",
                category=ACTION_CATEGORY_EXPLORE,
            ),
            ActionSuggestion(
                label="Attack the guard",
                intent_text="I attack!",
                category=ACTION_CATEGORY_EXPLORE,
            ),
            ActionSuggestion(
                label="Talk to Barkeep",
                intent_text="Say: Hello.",
                category=ACTION_CATEGORY_SOCIAL,
            ),
            ActionSuggestion(
                label="Travel to market",
                intent_text="I travel to the market.",
                category=ACTION_CATEGORY_EXPLORE,
            ),
        ]

        linted, notes = lint_actions(
            actions,
            game_state=state,
            router_output=router_out,
            mechanic_output=mechanic,
            encounter_context={"in_combat": True},
        )

        from backend.app.constants import SUGGESTED_ACTIONS_TARGET
        self.assertEqual(len(linted), SUGGESTED_ACTIONS_TARGET)
        self.assertTrue(any("removed" in n for n in notes))
        # Valid talk action should survive in TALK-only mode
        self.assertTrue(any(a.label == "Talk to Barkeep" for a in linted))

    def test_lint_keeps_talk_action_with_dialogue_quote(self) -> None:
        """Dialogue quotes should not be mis-read as missing NPC names."""
        state = GameState(
            campaign_id="c1",
            player_id="p1",
            current_location="loc-tavern",
            present_npcs=[{"id": "npc-1", "name": "Barkeep", "role": "Barkeep"}],
            player=CharacterSheet(character_id="p1", name="Player"),
        )
        actions = [
            ActionSuggestion(
                label="Show good faith",
                intent_text="Say: 'Maybe I can help.'",
                category=ACTION_CATEGORY_SOCIAL,
            ),
        ]
        linted, _notes = lint_actions(actions, game_state=state)
        self.assertTrue(any(a.label == "Show good faith" for a in linted))
