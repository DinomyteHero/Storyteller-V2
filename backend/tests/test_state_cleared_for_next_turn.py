"""Unit tests for GameState.cleared_for_next_turn() - verify WorldSim fields are reset."""
import unittest

from backend.app.models.state import GameState, CharacterSheet


class TestClearedForNextTurn(unittest.TestCase):
    """Test that cleared_for_next_turn() resets all WorldSim-related fields."""

    def test_worldsim_fields_reset(self):
        """Create a GameState with WorldSim fields populated, then verify they're reset."""
        # Create a GameState with WorldSim fields populated
        state = GameState(
            campaign_id="test-campaign",
            player_id="test-player",
            turn_number=5,
            current_location="loc-tavern",
            player=CharacterSheet(
                character_id="test-player",
                name="Test Player",
                stats={"Combat": 2},
                hp_current=10,
            ),
            # Populate WorldSim-related fields
            world_sim_ran=True,
            world_sim_rumors=[{"event_type": "RUMOR", "text": "A rumor spreads"}],
            world_sim_factions_update=[{"name": "Test Faction", "resources": 5}],
            world_sim_events=[{"event_type": "FACTION_MOVE", "text": "Faction moved"}],
            new_rumors=["New rumor 1", "New rumor 2"],
            active_rumors=["Active rumor 1", "Active rumor 2"],
            world_sim_debug="Debug info here",
            pending_world_time_minutes=240,
            # Also populate some transient fields to ensure they're reset
            user_input="test input",
            intent="ACTION",
            route="MECHANIC",
            final_text="Some final text",
        )

        # Call cleared_for_next_turn()
        cleared = state.cleared_for_next_turn()

        # Assert all WorldSim fields are reset
        self.assertFalse(cleared.world_sim_ran, "world_sim_ran should be False")
        self.assertEqual(cleared.world_sim_rumors, [], "world_sim_rumors should be empty list")
        self.assertIsNone(cleared.world_sim_factions_update, "world_sim_factions_update should be None")
        self.assertEqual(cleared.world_sim_events, [], "world_sim_events should be empty list")
        self.assertEqual(cleared.new_rumors, [], "new_rumors should be empty list")
        self.assertEqual(cleared.active_rumors, [], "active_rumors should be empty list")
        self.assertIsNone(cleared.world_sim_debug, "world_sim_debug should be None")
        self.assertIsNone(cleared.pending_world_time_minutes, "pending_world_time_minutes should be None")

        # Assert other transient fields are also reset
        self.assertEqual(cleared.user_input, "", "user_input should be empty")
        self.assertIsNone(cleared.intent, "intent should be None")
        self.assertIsNone(cleared.route, "route should be None")
        self.assertIsNone(cleared.final_text, "final_text should be None")

        # Assert persistent fields are kept
        self.assertEqual(cleared.campaign_id, state.campaign_id, "campaign_id should be kept")
        self.assertEqual(cleared.player_id, state.player_id, "player_id should be kept")
        self.assertEqual(cleared.turn_number, state.turn_number, "turn_number should be kept")
        self.assertEqual(cleared.current_location, state.current_location, "current_location should be kept")
        self.assertIsNotNone(cleared.player, "player should be kept")
        self.assertEqual(cleared.player.name, state.player.name, "player data should be kept")

    def test_persistent_fields_kept(self):
        """Verify that persistent and memory fields are not reset."""
        state = GameState(
            campaign_id="test-campaign",
            player_id="test-player",
            turn_number=10,
            current_location="loc-market",
            player=CharacterSheet(
                character_id="test-player",
                name="Test Player",
                stats={"Combat": 3},
                hp_current=15,
            ),
            campaign={"title": "Test Campaign", "time_period": "LOTF"},
            history=["Turn 1", "Turn 2", "Turn 3"],
            last_user_inputs=["input1", "input2"],
        )

        cleared = state.cleared_for_next_turn()

        # Persistent fields should be kept
        self.assertEqual(cleared.campaign_id, state.campaign_id)
        self.assertEqual(cleared.player_id, state.player_id)
        self.assertEqual(cleared.turn_number, state.turn_number)
        self.assertEqual(cleared.current_location, state.current_location)
        self.assertIsNotNone(cleared.player)
        self.assertIsNotNone(cleared.campaign)

        # Memory fields should be kept
        self.assertEqual(len(cleared.history), len(state.history))
        self.assertEqual(len(cleared.last_user_inputs), len(state.last_user_inputs))


if __name__ == "__main__":
    unittest.main()
