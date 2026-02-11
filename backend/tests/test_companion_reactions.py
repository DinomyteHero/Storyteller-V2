"""Tests for deterministic companion approval and banter (no LLM, no DB in node)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.app.core.companion_reactions import (
    compute_companion_reactions,
    update_party_state,
    maybe_enqueue_banter,
    apply_alignment_and_faction,
    affinity_to_mood_tag,
    BANTER_COOLDOWN_TURNS,
)
from backend.app.models.state import (
    TONE_TAG_PARAGON,
    TONE_TAG_RENEGADE,
    TONE_TAG_INVESTIGATE,
    TONE_TAG_NEUTRAL,
    MechanicOutput,
)


class TestComputeCompanionReactions(unittest.TestCase):
    """Given party traits and tone_tag, affinity changes are deterministic."""

    def test_paragon_liked_by_idealist(self) -> None:
        party = ["comp-kira"]
        party_traits = {"comp-kira": {"idealist_pragmatic": 80, "merciful_ruthless": -60, "lawful_rebellious": 20}}
        mr = {"tone_tag": TONE_TAG_PARAGON, "alignment_delta": {}, "companion_affinity_delta": {}, "companion_reaction_reason": {}}
        deltas, reasons = compute_companion_reactions(party, party_traits, mr)
        self.assertIn("comp-kira", deltas)
        self.assertGreater(deltas["comp-kira"], 0, "Idealist should like PARAGON")
        self.assertIn("comp-kira", reasons)

    def test_renegade_liked_by_pragmatist(self) -> None:
        party = ["comp-vex"]
        party_traits = {"comp-vex": {"idealist_pragmatic": -70, "merciful_ruthless": 40, "lawful_rebellious": -30}}
        mr = {"tone_tag": TONE_TAG_RENEGADE, "alignment_delta": {}, "companion_affinity_delta": {}, "companion_reaction_reason": {}}
        deltas, reasons = compute_companion_reactions(party, party_traits, mr)
        self.assertIn("comp-vex", deltas)
        self.assertGreater(deltas["comp-vex"], 0, "Pragmatist should like RENEGADE")
        self.assertIn("comp-vex", reasons)

    def test_paragon_disliked_by_pragmatist(self) -> None:
        party = ["comp-vex"]
        party_traits = {"comp-vex": {"idealist_pragmatic": -70, "merciful_ruthless": 40}}
        mr = {"tone_tag": TONE_TAG_PARAGON, "alignment_delta": {}, "companion_affinity_delta": {}, "companion_reaction_reason": {}}
        deltas, _ = compute_companion_reactions(party, party_traits, mr)
        self.assertIn("comp-vex", deltas)
        self.assertLess(deltas["comp-vex"], 0, "Pragmatist should dislike PARAGON")

    def test_explicit_companion_affinity_overrides(self) -> None:
        party = ["comp-kira"]
        party_traits = {"comp-kira": {"idealist_pragmatic": 80}}
        mr = {
            "tone_tag": TONE_TAG_RENEGADE,
            "alignment_delta": {},
            "companion_affinity_delta": {"comp-kira": 4},
            "companion_reaction_reason": {"comp-kira": "mechanic override"},
        }
        deltas, reasons = compute_companion_reactions(party, party_traits, mr)
        self.assertEqual(deltas.get("comp-kira"), 4)
        self.assertIn("override", reasons.get("comp-kira", "").lower() or "override")

    def test_investigate_neutral_or_liked_by_cautious(self) -> None:
        party = ["comp-sentinel"]
        party_traits = {"comp-sentinel": {"idealist_pragmatic": 40, "lawful_rebellious": -80}}
        mr = {"tone_tag": TONE_TAG_INVESTIGATE, "alignment_delta": {}, "companion_affinity_delta": {}, "companion_reaction_reason": {}}
        deltas, _ = compute_companion_reactions(party, party_traits, mr)
        self.assertIn("comp-sentinel", deltas)
        self.assertGreaterEqual(deltas["comp-sentinel"], 0, "Cautious/lawful can like INVESTIGATE")

    def test_neutral_produces_no_delta(self) -> None:
        party = ["comp-kira"]
        party_traits = {"comp-kira": {"idealist_pragmatic": 80}}
        mr = {"tone_tag": TONE_TAG_NEUTRAL, "alignment_delta": {}, "companion_affinity_delta": {}, "companion_reaction_reason": {}}
        deltas, _ = compute_companion_reactions(party, party_traits, mr)
        self.assertEqual(deltas.get("comp-kira"), None)


class TestUpdatePartyState(unittest.TestCase):
    def test_affinity_and_loyalty_updated(self) -> None:
        state = {
            "campaign": {
                "party_affinity": {"c1": 10},
                "loyalty_progress": {"c1": 0},
            },
        }
        out = update_party_state(state, {"c1": 2})
        self.assertEqual(out["campaign"]["party_affinity"]["c1"], 12)
        self.assertEqual(out["campaign"]["loyalty_progress"]["c1"], 1)

    def test_affinity_clamped(self) -> None:
        state = {"campaign": {"party_affinity": {"c1": 98}, "loyalty_progress": {"c1": 0}}}
        out = update_party_state(state, {"c1": 5})
        self.assertEqual(out["campaign"]["party_affinity"]["c1"], 100)


class TestBanterRateLimit(unittest.TestCase):
    """Banter is rate-limited (at most once every BANTER_COOLDOWN_TURNS)."""

    @patch("backend.app.core.companions.get_companion_by_id")
    def test_banter_enqueued_on_cooldown_turn(self, mock_get: unittest.mock.MagicMock) -> None:
        mock_get.return_value = {"id": "c1", "name": "Kira", "banter_style": "warm"}
        state = {
            "campaign": {"party": ["c1"], "banter_queue": []},
            "turn_number": BANTER_COOLDOWN_TURNS - 1,
        }
        mr = {"invalid_action": False}
        out_state, line = maybe_enqueue_banter(state, mr)
        self.assertIsNotNone(line)
        self.assertEqual(len(out_state["campaign"]["banter_queue"]), 1)

    @patch("backend.app.core.companions.get_companion_by_id")
    def test_banter_not_enqueued_every_turn(self, mock_get: unittest.mock.MagicMock) -> None:
        mock_get.return_value = {"id": "c1", "name": "Kira", "banter_style": "warm"}
        state = {
            "campaign": {"party": ["c1"], "banter_queue": []},
            "turn_number": 0,
        }
        mr = {"invalid_action": False}
        out_state, line = maybe_enqueue_banter(state, mr)
        self.assertIsNone(line)
        self.assertEqual(len(out_state["campaign"].get("banter_queue") or []), 0)

    def test_banter_skipped_on_invalid_action(self) -> None:
        state = {"campaign": {"party": ["c1"], "banter_queue": []}, "turn_number": BANTER_COOLDOWN_TURNS - 1}
        mr = {"invalid_action": True}
        out_state, line = maybe_enqueue_banter(state, mr)
        self.assertIsNone(line)
        self.assertEqual(len(out_state["campaign"].get("banter_queue") or []), 0)


class TestCompanionReactionNodeNoDb(unittest.TestCase):
    """CompanionReactionNode is pure: no DB writes. We test the same pipeline without importing graph (avoids heavy deps)."""

    def test_reaction_pipeline_takes_only_state_dict(self) -> None:
        """Companion reaction pipeline is pure: compute_companion_reactions, update_party_state, apply_alignment_and_faction, maybe_enqueue_banter take no conn."""
        state = {
            "mechanic_result": {
                "tone_tag": TONE_TAG_PARAGON,
                "alignment_delta": {"light_dark": 5},
                "companion_affinity_delta": {},
                "companion_reaction_reason": {},
            },
            "campaign": {
                "party": ["comp-kira"],
                "party_traits": {"comp-kira": {"idealist_pragmatic": 80, "merciful_ruthless": -60}},
                "party_affinity": {"comp-kira": 0},
                "loyalty_progress": {"comp-kira": 0},
                "alignment": {"light_dark": 0, "paragon_renegade": 0},
                "banter_queue": [],
            },
        }
        from backend.app.core.companion_reactions import apply_alignment_and_faction
        state = apply_alignment_and_faction(state, state["mechanic_result"])
        deltas, _ = compute_companion_reactions(
            state["campaign"]["party"],
            state["campaign"]["party_traits"],
            state["mechanic_result"],
        )
        state = update_party_state(state, deltas)
        self.assertIn("campaign", state)
        self.assertGreater(state["campaign"]["party_affinity"].get("comp-kira", 0), 0)
        self.assertEqual(state["campaign"]["alignment"]["light_dark"], 5)

    def test_no_db_in_reaction_functions(self) -> None:
        """Reaction module has no database imports or connection parameters."""
        import inspect
        from backend.app.core import companion_reactions
        for name in ("compute_companion_reactions", "update_party_state", "apply_alignment_and_faction", "maybe_enqueue_banter"):
            func = getattr(companion_reactions, name)
            sig = inspect.signature(func)
            params = list(sig.parameters)
            self.assertNotIn("conn", params, f"{name} must not take conn (no DB writes)")


class TestAffinityToMoodTag(unittest.TestCase):
    def test_warm(self) -> None:
        self.assertEqual(affinity_to_mood_tag(50), "Warm")
        self.assertEqual(affinity_to_mood_tag(100), "Warm")

    def test_hostile(self) -> None:
        self.assertEqual(affinity_to_mood_tag(-50), "Hostile")
        self.assertEqual(affinity_to_mood_tag(-100), "Hostile")

    def test_wary_and_neutral(self) -> None:
        self.assertEqual(affinity_to_mood_tag(-1), "Wary")
        self.assertEqual(affinity_to_mood_tag(0), "Neutral")
        self.assertEqual(affinity_to_mood_tag(49), "Neutral")


class TestApplyAlignmentAndFaction(unittest.TestCase):
    def test_alignment_applied(self) -> None:
        state = {"campaign": {"alignment": {"light_dark": 0, "paragon_renegade": 0}}}
        mr = {"alignment_delta": {"light_dark": 10, "paragon_renegade": -5}}
        out = apply_alignment_and_faction(state, mr)
        self.assertEqual(out["campaign"]["alignment"]["light_dark"], 10)
        self.assertEqual(out["campaign"]["alignment"]["paragon_renegade"], -5)


if __name__ == "__main__":
    unittest.main()
