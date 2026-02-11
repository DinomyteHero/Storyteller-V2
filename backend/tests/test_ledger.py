"""Tests for narrative ledger updates and prompt inclusion."""
import sys
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.ledger import update_ledger
from backend.app.constants import LEDGER_MAX_FACTS
from backend.app.models.state import GameState, MechanicOutput
from backend.app.core.agents import narrator as narrator_mod


class TestLedgerUpdate(unittest.TestCase):
    def test_ledger_caps_facts(self) -> None:
        previous = {"established_facts": [f"Fact {i}" for i in range(50)]}
        updated = update_ledger(previous, [], "")
        self.assertLessEqual(len(updated["established_facts"]), LEDGER_MAX_FACTS)

    def test_ledger_persists_previous(self) -> None:
        previous = {
            "established_facts": ["A happened."],
            "open_threads": ["Resolve the mystery."],
        }
        updated = update_ledger(previous, [], "What do you do next?")
        self.assertIn("A happened.", updated["established_facts"])
        self.assertIn("Resolve the mystery.", updated["open_threads"])


class TestLedgerInNarratorContext(unittest.TestCase):
    def test_ledger_included_in_story_state_summary(self) -> None:
        ledger = {
            "established_facts": ["The vault is sealed."],
            "open_threads": ["Find the key."],
            "active_goals": ["Open the vault."],
            "constraints": ["Location: Vault Room."],
            "tone_tags": ["tense"],
        }
        state = GameState(
            campaign_id="c1",
            player_id="p1",
            turn_number=1,
            current_location="loc-vault",
            campaign={"world_state_json": {"ledger": ledger}},
            mechanic_result=MechanicOutput(action_type="TALK", events=[], narrative_facts=[]),
        )
        summary = narrator_mod._build_story_state_summary(state)
        self.assertIn("Narrative Ledger", summary)
        self.assertIn("The vault is sealed.", summary)
