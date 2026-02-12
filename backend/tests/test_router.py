"""Tests for Router: TALK vs MECHANIC routing and action-verb guardrail (security)."""
import os
import tempfile
import unittest
from unittest.mock import patch

from backend.app.db.migrate import apply_schema
from backend.app.db.connection import get_connection
from backend.app.core.state_loader import build_initial_gamestate
from backend.app.core.graph import run_turn
from backend.app.core.router import route, action_verb_guardrail_triggers
from backend.app.models.state import (
    ROUTER_ROUTE_TALK,
    ROUTER_ROUTE_MECHANIC,
    ROUTER_ROUTE_META,
    ROUTER_ACTION_CLASS_DIALOGUE_ONLY,
    ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION,
    ROUTER_ACTION_CLASS_PHYSICAL_ACTION,
    ROUTER_ACTION_CLASS_META,
)
from backend.app.models.state import MechanicOutput, ActionSuggestion
from backend.app.models.narration import NarrationOutput


class TestRouterClassification(unittest.TestCase):
    """Unit tests: router.route() and guardrail."""

    def test_ask_about_holocron_dialogue_only_skips_mechanic(self):
        """Input: 'I ask him where the holocron is.' => talk skip OK (dialogue-only, no resolution)."""
        out = route("I ask him where the holocron is.")
        self.assertEqual(out.route, ROUTER_ROUTE_TALK)
        self.assertEqual(out.action_class, ROUTER_ACTION_CLASS_DIALOGUE_ONLY)
        self.assertFalse(out.requires_resolution, "Ordinary question must not require resolution")

    def test_convince_must_go_to_mechanic(self):
        """'I convince him to let me pass.' -> must go to Mechanic."""
        out = route("I convince him to let me pass.")
        self.assertEqual(out.route, ROUTER_ROUTE_MECHANIC)
        self.assertTrue(out.requires_resolution)
        self.assertEqual(out.action_class, ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION)

    def test_threaten_must_go_to_mechanic(self):
        """'I threaten him to open the door.' -> must go to Mechanic."""
        out = route("I threaten him to open the door.")
        self.assertEqual(out.route, ROUTER_ROUTE_MECHANIC)
        self.assertTrue(out.requires_resolution)
        self.assertEqual(out.action_class, ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION)

    def test_lie_must_go_to_mechanic(self):
        """'I lie and say I'm with security.' -> must go to Mechanic."""
        out = route("I lie and say I'm with security.")
        self.assertEqual(out.route, ROUTER_ROUTE_MECHANIC)
        self.assertTrue(out.requires_resolution)
        self.assertEqual(out.action_class, ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION)

    def test_say_hi_and_stab_must_route_to_mechanic(self):
        """Input: \"I say 'hi' and stab him.\" => must route to Mechanic."""
        out = route("I say 'hi' and stab him.")
        self.assertEqual(out.route, ROUTER_ROUTE_MECHANIC)
        self.assertIn(
            out.action_class,
            (ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION, ROUTER_ACTION_CLASS_PHYSICAL_ACTION),
        )

    def test_threaten_and_pull_blaster_must_route_to_mechanic(self):
        """Input: 'I threaten him and pull my blaster.' => must route to Mechanic."""
        out = route("I threaten him and pull my blaster.")
        self.assertEqual(out.route, ROUTER_ROUTE_MECHANIC)
        self.assertIn(
            out.action_class,
            (ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION, ROUTER_ACTION_CLASS_PHYSICAL_ACTION),
        )

    def test_tell_her_leaving_dialogue_only(self):
        """Input: \"I tell her I'm leaving.\" => dialogue-only."""
        out = route("I tell her I'm leaving.")
        self.assertEqual(out.route, ROUTER_ROUTE_TALK)
        self.assertEqual(out.action_class, ROUTER_ACTION_CLASS_DIALOGUE_ONLY)

    def test_guardrail_triggers_on_stab(self):
        """Guardrail: 'stab' in input => action_verb_guardrail_triggers True."""
        self.assertTrue(action_verb_guardrail_triggers("I say hi and stab him."))
        self.assertTrue(action_verb_guardrail_triggers("stab the guard"))

    def test_guardrail_no_trigger_on_pure_dialogue(self):
        """Guardrail: no action verbs => no trigger."""
        self.assertFalse(action_verb_guardrail_triggers("I ask him about the holocron."))
        self.assertFalse(action_verb_guardrail_triggers("I tell her I'm leaving."))

    def test_help_routes_to_meta(self):
        """Input: 'help' => route META, action_class META, intent_text normalized."""
        out = route("help")
        self.assertEqual(out.route, ROUTER_ROUTE_META)
        self.assertEqual(out.action_class, ROUTER_ACTION_CLASS_META)
        self.assertEqual(out.intent_text, "help")

    def test_save_routes_to_meta(self):
        """Input: 'save' => route META, intent_text 'save'."""
        out = route("save")
        self.assertEqual(out.route, ROUTER_ROUTE_META)
        self.assertEqual(out.intent_text, "save")

    def test_help_and_stab_must_route_to_mechanic(self):
        """Input: 'I ask for help and stab him' => must NOT be META; route to Mechanic (action verb)."""
        out = route("I ask for help and stab him.")
        self.assertEqual(out.route, ROUTER_ROUTE_MECHANIC)
        self.assertIn(
            out.action_class,
            (ROUTER_ACTION_CLASS_DIALOGUE_WITH_ACTION, ROUTER_ACTION_CLASS_PHYSICAL_ACTION),
        )


class TestRouterIntegration(unittest.TestCase):
    """Integration: run_turn with mocked agents; assert mechanic called or not."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)
        self.conn = get_connection(self.db_path)
        self.campaign_id = "test-router-campaign"
        self.player_id = "test-router-player"
        self.conn.execute(
            """INSERT INTO campaigns (id, title, time_period, world_state_json, world_time_minutes)
               VALUES (?, ?, ?, ?, ?)""",
            (self.campaign_id, "Test", "LOTF", "{}", 0),
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

    def test_dialogue_only_skips_mechanic(self):
        """'I ask him about the holocron.' => mechanic node not invoked (skip to encounter)."""
        director_plan = ("Pacing.", [
            ActionSuggestion(label="Talk", intent_text="Say: Hi"),
            ActionSuggestion(label="Act", intent_text="Do something"),
            ActionSuggestion(label="Look", intent_text="Look around"),
        ])
        narrator_out = NarrationOutput(text="You ask about the holocron.", citations=[])
        mechanic_resolve_calls = []

        def capture_mechanic_resolve(gs):
            mechanic_resolve_calls.append(gs.user_input)
            return MechanicOutput(action_type="TALK", events=[], narrative_facts=[], time_cost_minutes=5)

        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = capture_mechanic_resolve
            with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
                MockDirector.return_value.plan.return_value = director_plan
                with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                    MockNarrator.return_value.generate.return_value = narrator_out
                    state = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
                    state.user_input = "I ask him about the holocron."
                    run_turn(self.conn, state)

        self.assertEqual(len(mechanic_resolve_calls), 0, "Dialogue-only should skip Mechanic")

    def test_stab_must_invoke_mechanic(self):
        """\"I say 'hi' and stab him.\" => mechanic node must be invoked."""
        director_plan = ("Pacing.", [
            ActionSuggestion(label="Talk", intent_text="Say: Hi"),
            ActionSuggestion(label="Act", intent_text="Do something"),
            ActionSuggestion(label="Look", intent_text="Look around"),
        ])
        narrator_out = NarrationOutput(text="Violence ensues.", citations=[])
        mechanic_resolve_calls = []

        def capture_mechanic_resolve(gs):
            mechanic_resolve_calls.append(gs.user_input)
            return MechanicOutput(
                action_type="ATTACK", events=[], narrative_facts=["Attack resolved."], time_cost_minutes=1
            )

        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = capture_mechanic_resolve
            with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
                MockDirector.return_value.plan.return_value = director_plan
                with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                    MockNarrator.return_value.generate.return_value = narrator_out
                    state = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
                    state.user_input = "I say 'hi' and stab him."
                    run_turn(self.conn, state)

        self.assertGreaterEqual(len(mechanic_resolve_calls), 1, "Stab must route to Mechanic")

    def test_threaten_pull_blaster_must_invoke_mechanic(self):
        """'I threaten him and pull my blaster.' => mechanic must be invoked."""
        director_plan = ("Pacing.", [
            ActionSuggestion(label="Talk", intent_text="Say: Hi"),
            ActionSuggestion(label="Act", intent_text="Do something"),
            ActionSuggestion(label="Look", intent_text="Look around"),
        ])
        narrator_out = NarrationOutput(text="Tension rises.", citations=[])
        mechanic_resolve_calls = []

        def capture_mechanic_resolve(gs):
            mechanic_resolve_calls.append(gs.user_input)
            return MechanicOutput(
                action_type="INTERACT", events=[], narrative_facts=["Pull blaster."], time_cost_minutes=1
            )

        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = capture_mechanic_resolve
            with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
                MockDirector.return_value.plan.return_value = director_plan
                with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                    MockNarrator.return_value.generate.return_value = narrator_out
                    state = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
                    state.user_input = "I threaten him and pull my blaster."
                    run_turn(self.conn, state)

        self.assertGreaterEqual(len(mechanic_resolve_calls), 1, "Threaten + pull blaster must route to Mechanic")

    def test_tell_her_leaving_skips_mechanic(self):
        """\"I tell her I'm leaving.\" => dialogue-only => skip mechanic."""
        director_plan = ("Pacing.", [
            ActionSuggestion(label="Talk", intent_text="Say: Hi"),
            ActionSuggestion(label="Act", intent_text="Do something"),
            ActionSuggestion(label="Look", intent_text="Look around"),
        ])
        narrator_out = NarrationOutput(text="You tell her you're leaving.", citations=[])
        mechanic_resolve_calls = []

        def capture_mechanic_resolve(gs):
            mechanic_resolve_calls.append(gs.user_input)
            return MechanicOutput(action_type="TALK", events=[], narrative_facts=[], time_cost_minutes=5)

        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = capture_mechanic_resolve
            with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
                MockDirector.return_value.plan.return_value = director_plan
                with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                    MockNarrator.return_value.generate.return_value = narrator_out
                    state = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
                    state.user_input = "I tell her I'm leaving."
                    run_turn(self.conn, state)

        self.assertEqual(len(mechanic_resolve_calls), 0, "I tell her I'm leaving should skip Mechanic")

    def test_help_routes_to_meta_node_mechanic_not_called_time_not_advanced(self):
        """Input: 'help' => routes to MetaNode, Mechanic not called, time does not advance."""
        from backend.app.core.state_loader import load_campaign

        mechanic_resolve_calls = []

        def capture_mechanic(gs):
            mechanic_resolve_calls.append(gs)
            return MechanicOutput(action_type="TALK", events=[], narrative_facts=[], time_cost_minutes=0)

        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = capture_mechanic
            state = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
            state.user_input = "help"
            result = run_turn(self.conn, state)

        self.assertEqual(len(mechanic_resolve_calls), 0, "help must not hit Mechanic")
        self.assertIn("Help", result.final_text or "", "MetaNode should return help text")
        self.assertGreaterEqual(len(result.suggested_actions or []), 3, "MetaNode should return 3 suggestions")
        camp = load_campaign(self.conn, self.campaign_id)
        self.assertEqual(int(camp.get("world_time_minutes") or 0), 0, "META turn must not advance world_time_minutes")

    def test_save_routes_to_meta_time_not_advanced(self):
        """Input: 'save' => routes to MetaNode, time does not advance."""
        from backend.app.core.state_loader import load_campaign

        state = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
        state.user_input = "save"
        result = run_turn(self.conn, state)

        self.assertIn("autosave", (result.final_text or "").lower(), "MetaNode should mention autosave")
        camp = load_campaign(self.conn, self.campaign_id)
        self.assertEqual(int(camp.get("world_time_minutes") or 0), 0, "META turn must not advance world_time_minutes")

    def test_help_and_stab_must_invoke_mechanic(self):
        """Input: 'I ask for help and stab him' => must NOT be META; must route to Mechanic."""
        director_plan = ("Pacing.", [
            ActionSuggestion(label="Talk", intent_text="Say: Hi"),
            ActionSuggestion(label="Act", intent_text="Do something"),
            ActionSuggestion(label="Look", intent_text="Look around"),
        ])
        narrator_out = NarrationOutput(text="Violence.", citations=[])
        mechanic_resolve_calls = []

        def capture_mechanic(gs):
            mechanic_resolve_calls.append(gs.user_input)
            return MechanicOutput(
                action_type="ATTACK", events=[], narrative_facts=[], time_cost_minutes=1
            )

        with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMechanic:
            MockMechanic.return_value.resolve = capture_mechanic
            with patch("backend.app.core.nodes.director.DirectorAgent") as MockDirector:
                MockDirector.return_value.plan.return_value = director_plan
                with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNarrator:
                    MockNarrator.return_value.generate.return_value = narrator_out
                    state = build_initial_gamestate(self.conn, self.campaign_id, self.player_id)
                    state.user_input = "I ask for help and stab him."
                    run_turn(self.conn, state)

        self.assertGreaterEqual(len(mechanic_resolve_calls), 1, "I ask for help and stab him must route to Mechanic")
