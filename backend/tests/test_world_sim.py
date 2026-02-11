"""Integration tests for world sim: clock ticks, WorldSimNode, commit, rumors, faction updates."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from backend.app.db.migrate import apply_schema
from backend.app.db.connection import get_connection
from backend.app.core.state_loader import build_initial_gamestate, load_campaign
from backend.app.core.graph import run_turn
from backend.app.core.nodes.world_sim import world_sim_tick_crosses_boundary
from backend.app.models.state import MechanicOutput, ActionSuggestion
from backend.app.models.narration import NarrationOutput


class TestWorldSimTickBoundary(unittest.TestCase):
    """Regression: PRE-COMMIT tick — WorldSim runs when (t0 + time_cost) crosses a boundary."""

    def test_crosses_boundary_runs_world_sim(self):
        """t0=235, tick=240, dt=10 => t1=245 crosses boundary => WorldSim runs this turn."""
        self.assertTrue(
            world_sim_tick_crosses_boundary(235, 235 + 10, 240),
            "235 + 10 = 245 crosses into next tick (floor(235/240)=0, floor(245/240)=1)",
        )

    def test_no_boundary_does_not_run_world_sim(self):
        """t0=200, tick=240, dt=10 => t1=210 no boundary => WorldSim not run."""
        self.assertFalse(
            world_sim_tick_crosses_boundary(200, 200 + 10, 240),
            "200 + 10 = 210 still in same tick (floor(200/240)=0, floor(210/240)=0)",
        )

    def test_large_dt_crosses_multiple_boundaries_one_run_per_turn(self):
        """Large dt (0 + 500) crosses multiple boundaries; design: one WorldSim run per turn."""
        self.assertTrue(
            world_sim_tick_crosses_boundary(0, 500, 240),
            "0 + 500 crosses boundaries; we still run WorldSim once per turn",
        )
        # Boundary check returns True whenever floor(t0/tick) != floor(t1/tick); single run is enforced by pipeline
        self.assertEqual(
            (0 // 240, 500 // 240),
            (0, 2),
            "Crosses two boundaries; pipeline runs WorldSim once",
        )


def _row_to_dict(row):
    if hasattr(row, "keys"):
        return dict(zip(row.keys(), row))
    return dict(row)


def _get_events_with_public_rumor(conn, campaign_id: str):
    """Return rows from turn_events where is_public_rumor is true."""
    cur = conn.execute(
        """SELECT id, turn_number, event_type, payload_json, is_hidden, is_public_rumor
           FROM turn_events
           WHERE campaign_id = ? AND (is_public_rumor = 1 OR is_public_rumor = '1')
           ORDER BY turn_number ASC, id ASC""",
        (campaign_id,),
    )
    return [_row_to_dict(row) for row in cur.fetchall()]


class TestClockTicksAndWorldReacts(unittest.TestCase):
    """Test: campaign clock advances, WorldSim runs on tick, rumors and faction updates persist."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)
        self.conn = get_connection(self.db_path)
        self.campaign_id = "test-campaign-world-sim"
        self.player_id = "test-player-world-sim"
        # One active faction for world_state_json
        self.initial_faction = {
            "name": "Red Hand Cult",
            "current_location": "The Docks",
            "goal": "Summon the Leviathan",
            "resources": 5,
        }
        world_state_json = json.dumps({"active_factions": [self.initial_faction]})
        self.conn.execute(
            """INSERT INTO campaigns (id, title, time_period, world_state_json, world_time_minutes)
               VALUES (?, ?, ?, ?, ?)""",
            (self.campaign_id, "Test Campaign", "LOTF", world_state_json, 0),
        )
        self.conn.execute(
            """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.player_id, self.campaign_id, "Hero", "Player", "loc-tavern", "{}", 10, None, None, 0),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    @patch("backend.app.core.nodes.world_sim.WORLD_TICK_INTERVAL_HOURS", 1)
    def test_clock_ticks_and_world_reacts(self):
        # PRE-COMMIT: tick is (t0 + time_cost). Turn 1: t0=0, dt=300 => t1=300 crosses boundary => WorldSim runs this turn.
        from shared.schemas import WorldSimOutput

        updated_faction = {
            "name": "Red Hand Cult",
            "current_location": "The Market",
            "goal": "Summon the Leviathan",
            "resources": 4,
        }
        world_sim_output = WorldSimOutput(
            elapsed_time_summary="Time advanced.",
            faction_moves=[],
            new_rumors=["Whispers speak of cult activity near the docks."],
            hidden_events=[],
            updated_factions=[updated_faction],
        )

        mechanic_result_turn1 = MechanicOutput(
            action_type="TRAVEL",
            time_cost_minutes=300,
            events=[],
            narrative_facts=[],
        )

        def mechanic_resolve_turn1(gs):
            return mechanic_result_turn1

        director_plan_return = (
            "Keep pacing brisk.",
            [
                ActionSuggestion(label="Talk", intent_text="Say: Hello"),
                ActionSuggestion(label="Act", intent_text="Try something"),
                ActionSuggestion(label="Look", intent_text="Look around"),
            ],
        )
        narrator_output = NarrationOutput(text="You travel. What do you do next?", citations=[])
        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = mechanic_resolve_turn1
            with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
                MockDirector.return_value.plan.return_value = director_plan_return
                with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                    MockNarrator.return_value.generate.return_value = narrator_output
                    # WorldSim is now deterministic (no LLM) — mock faction engine for controlled output
                    with patch("backend.app.core.nodes.world_sim.simulate_faction_tick") as MockFactionTick:
                        MockFactionTick.return_value = world_sim_output
                        state1 = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
                        state1.user_input = "Travel to the market"
                        run_turn(self.conn, state1)

        camp = load_campaign(self.conn, self.campaign_id)
        self.assertIsNotNone(camp)
        self.assertEqual(
            int(camp.get("world_time_minutes") or 0),
            300,
            "campaign.world_time_minutes should be 300 after turn 1 (time_cost=300)",
        )
        public_rumor_events_after_turn1 = _get_events_with_public_rumor(self.conn, self.campaign_id)
        self.assertGreaterEqual(
            len(public_rumor_events_after_turn1),
            1,
            "WorldSim runs on turn 1 when (t0+dt) crosses boundary; expect at least one is_public_rumor event",
        )
        world_state = camp.get("world_state_json")
        if isinstance(world_state, str):
            world_state = json.loads(world_state) if world_state else {}
        if not isinstance(world_state, dict):
            world_state = {}
        factions = world_state.get("active_factions") or []
        self.assertGreaterEqual(len(factions), 1, "world_state_json should have at least one faction")
        faction = factions[0]
        self.assertTrue(
            faction.get("current_location") != self.initial_faction.get("current_location")
            or faction.get("resources") != self.initial_faction.get("resources"),
            "Faction in world_state_json should have changed (location or resources); "
            f"got {faction}, initial was {self.initial_faction}",
        )

        # Turn 2: t0=300, dt=0 => t1=300. Same tick bucket => WorldSim does not run.
        def mechanic_resolve_turn2(gs):
            return MechanicOutput(
                action_type="TALK",
                time_cost_minutes=0,
                events=[],
                narrative_facts=[],
            )

        narrator_output2 = NarrationOutput(text="You look around. What next?", citations=[])
        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = mechanic_resolve_turn2
            with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
                MockDirector.return_value.plan.return_value = director_plan_return
                with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                    MockNarrator.return_value.generate.return_value = narrator_output2
                    state2 = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
                    state2.user_input = "Look around"
                    run_turn(self.conn, state2)

        camp = load_campaign(self.conn, self.campaign_id)
        self.assertIsNotNone(camp)
        self.assertEqual(
            int(camp.get("world_time_minutes") or 0),
            300,
            "campaign.world_time_minutes should still be 300 (turn 2 added 0)",
        )


class TestWorldSimNoPartialWrites(unittest.TestCase):
    """Regression: no SQLite writes outside CommitNode; mid-turn failure leaves DB unchanged."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)
        self.conn = get_connection(self.db_path)
        self.campaign_id = "test-campaign-partial-fail"
        self.player_id = "test-player-partial-fail"
        self.initial_faction = {
            "name": "Red Hand Cult",
            "current_location": "The Docks",
            "goal": "Summon the Leviathan",
            "resources": 5,
        }
        world_state_json = json.dumps({"active_factions": [self.initial_faction]})
        self.conn.execute(
            """INSERT INTO campaigns (id, title, time_period, world_state_json, world_time_minutes)
               VALUES (?, ?, ?, ?, ?)""",
            (self.campaign_id, "Test Campaign", "LOTF", world_state_json, 0),
        )
        self.conn.execute(
            """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.player_id, self.campaign_id, "Hero", "Player", "loc-tavern", "{}", 10, None, None, 0),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _active_factions_snapshot(self):
        """Active factions only (WorldSim persists these in Commit; unchanged if Commit never runs)."""
        camp = load_campaign(self.conn, self.campaign_id)
        ws = camp.get("world_state_json") if camp else None
        if isinstance(ws, str):
            ws = json.loads(ws) if ws else {}
        if not isinstance(ws, dict):
            return []
        return ws.get("active_factions") or []

    def _public_rumor_count(self):
        rows = _get_events_with_public_rumor(self.conn, self.campaign_id)
        return len(rows)

    @patch("backend.app.core.nodes.world_sim.WORLD_TICK_INTERVAL_HOURS", 1)
    def test_partial_failure_no_db_writes(self):
        """Tick boundary crossed, WorldSim produces faction update + rumors; Director raises before Commit. Assert: no DB partial updates."""
        from shared.schemas import WorldSimOutput

        updated_faction = {
            "name": "Red Hand Cult",
            "current_location": "The Market",
            "goal": "Summon the Leviathan",
            "resources": 4,
        }
        world_sim_output = WorldSimOutput(
            elapsed_time_summary="Time advanced.",
            faction_moves=[],
            new_rumors=["Whispers speak of cult activity near the docks."],
            hidden_events=[],
            updated_factions=[updated_faction],
        )
        mechanic_result = MechanicOutput(
            action_type="TRAVEL",
            time_cost_minutes=300,
            events=[],
            narrative_facts=[],
        )

        initial_factions = self._active_factions_snapshot()
        initial_rumor_count = self._public_rumor_count()

        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = lambda gs: mechanic_result
            # WorldSim is now deterministic — mock faction engine for controlled output
            with patch("backend.app.core.nodes.world_sim.simulate_faction_tick") as MockFactionTick:
                MockFactionTick.return_value = world_sim_output
                with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
                    MockDirector.return_value.plan.side_effect = RuntimeError("Director failed mid-turn")
                    with patch("backend.app.core.nodes.narrator.NarratorAgent"):
                        state = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
                        state.user_input = "Travel to the market"
                        with self.assertRaises(RuntimeError):
                            run_turn(self.conn, state)

        # No WorldSim persistence: active_factions and rumor events unchanged (Commit never ran)
        after_factions = self._active_factions_snapshot()
        self.assertEqual(
            len(after_factions),
            len(initial_factions),
            "active_factions count unchanged when Commit never runs",
        )
        if initial_factions and after_factions:
            self.assertEqual(
                after_factions[0].get("current_location"),
                self.initial_faction.get("current_location"),
                "WorldSim faction update must not be persisted when Commit never runs",
            )
        self.assertEqual(
            self._public_rumor_count(),
            initial_rumor_count,
            "No rumor events must be committed when Commit never runs",
        )

    @patch("backend.app.core.nodes.world_sim.WORLD_TICK_INTERVAL_HOURS", 1)
    def test_normal_turn_commits_once(self):
        """After partial-failure test: run a normal turn and assert DB updates are committed once."""
        from shared.schemas import WorldSimOutput

        updated_faction = {
            "name": "Red Hand Cult",
            "current_location": "The Market",
            "goal": "Summon the Leviathan",
            "resources": 4,
        }
        world_sim_output = WorldSimOutput(
            elapsed_time_summary="Time advanced.",
            faction_moves=[],
            new_rumors=["Whispers speak of cult activity near the docks."],
            hidden_events=[],
            updated_factions=[updated_faction],
        )
        mechanic_result = MechanicOutput(
            action_type="TRAVEL",
            time_cost_minutes=300,
            events=[],
            narrative_facts=[],
        )
        director_plan_return = (
            "Keep pacing brisk.",
            [
                ActionSuggestion(label="Talk", intent_text="Say: Hello"),
                ActionSuggestion(label="Act", intent_text="Try something"),
                ActionSuggestion(label="Look", intent_text="Look around"),
            ],
        )
        narrator_output = NarrationOutput(text="You travel. What do you do next?", citations=[])

        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = lambda gs: mechanic_result
            # WorldSim is now deterministic — mock faction engine for controlled output
            with patch("backend.app.core.nodes.world_sim.simulate_faction_tick") as MockFactionTick:
                MockFactionTick.return_value = world_sim_output
                with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
                    MockDirector.return_value.plan.return_value = director_plan_return
                    with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                        MockNarrator.return_value.generate.return_value = narrator_output
                        state = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
                        state.user_input = "Travel to the market"
                        run_turn(self.conn, state)

        camp = load_campaign(self.conn, self.campaign_id)
        self.assertIsNotNone(camp)
        self.assertEqual(int(camp.get("world_time_minutes") or 0), 300)
        world_state = camp.get("world_state_json")
        if isinstance(world_state, str):
            world_state = json.loads(world_state) if world_state else {}
        factions = world_state.get("active_factions") or []
        self.assertGreaterEqual(len(factions), 1)
        self.assertEqual(factions[0].get("current_location"), "The Market")
        self.assertEqual(factions[0].get("resources"), 4)
        rumor_events = _get_events_with_public_rumor(self.conn, self.campaign_id)
        self.assertGreaterEqual(len(rumor_events), 1, "Rumor events must be committed in Commit")
