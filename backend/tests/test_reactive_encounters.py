"""Tests for V1.1 Phase 4: reactive encounter system.

Covers:
- Phase 4A: WorldMind reactive encounter output + pending queue in world_sim
- Phase 4B: Encounter node consuming pending reactive encounters
- Phase 4D: NPC death generating reactive encounters
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from backend.app.core.nodes.world_sim import make_world_sim_node
from shared.schemas import WorldSimOutput


def _base_state(turn=5, world_time=300, factions=None, campaign_ws=None):
    """Build a minimal pipeline state dict for world_sim_node.

    Uses action_type=TRAVEL to ensure the sim always runs (bypasses tick boundary check
    which depends on a closure captured at make_world_sim_node() time).
    """
    if factions is None:
        factions = [{"name": "Crimson Talon", "current_goal": "Expand", "resources": 6,
                      "location": "docks", "is_hostile": True}]
    ws = campaign_ws or {"active_factions": factions, "arc_state": {"current_stage": "RISING"}}
    return {
        "__runtime_conn": MagicMock(),
        "campaign_id": "test-campaign",
        "campaign": {
            "world_time_minutes": world_time,
            "world_state_json": ws,
        },
        "mechanic_result": {
            "action_type": "TRAVEL",
            "time_cost_minutes": 60,
            "events": [],
        },
        "user_input": "Scout the area",
        "turn_number": turn,
        "current_location": "loc-cantina",
    }


def _run_world_sim(state, world_sim_output):
    """Run the world_sim_node with mocked WorldMind and load_campaign."""
    node = make_world_sim_node()
    with patch("backend.app.core.nodes.world_sim.load_campaign") as mock_load:
        mock_load.return_value = {"world_state_json": state["campaign"]["world_state_json"]}
        with patch("backend.app.core.agents.world_mind_agent.WorldMindAgent") as MockWM:
            MockWM.return_value.simulate.return_value = world_sim_output
            return node(state)


class TestReactiveEncounterQueue:
    """Phase 4A: WorldMind reactive_encounters are queued in pending_reactive_encounters."""

    def test_reactive_encounters_stored_in_world_state(self):
        """WorldMind output with reactive_encounters produces pending queue entries."""
        world_sim_output = WorldSimOutput(
            elapsed_time_summary="Time passes.",
            faction_moves=[], new_rumors=[], hidden_events=[],
            updated_factions=[],
            reactive_encounters=[
                {
                    "trigger": "faction_move",
                    "npc_archetype": "bounty_hunter",
                    "faction": "Crimson Talon",
                    "description": "A hunter tracks you",
                    "urgency": "next_turn",
                    "hostility": "hostile",
                }
            ],
        )

        state = _base_state()
        result = _run_world_sim(state, world_sim_output)

        ws = result["campaign"]["world_state_json"]
        pending = ws.get("pending_reactive_encounters", [])
        assert len(pending) >= 1, f"Expected at least 1 pending encounter, got {len(pending)}"
        enc = pending[0]
        assert enc["npc_archetype"] == "bounty_hunter"
        assert enc["faction"] == "Crimson Talon"
        assert enc["trigger_turn"] == state["turn_number"] + 1  # next_turn

    def test_reactive_encounters_capped_at_max(self):
        """Pending queue does not exceed REACTIVE_ENCOUNTER_MAX_PENDING."""
        from backend.app.constants import REACTIVE_ENCOUNTER_MAX_PENDING

        encounters = [
            {
                "trigger": "world_event",
                "npc_archetype": f"informant_{i}",
                "faction": None,
                "description": f"Event {i}",
                "urgency": "within_3_turns",
                "hostility": "neutral",
            }
            for i in range(10)  # Way more than max
        ]
        world_sim_output = WorldSimOutput(
            elapsed_time_summary="Time passes.",
            faction_moves=[], new_rumors=[], hidden_events=[],
            updated_factions=[],
            reactive_encounters=encounters,
        )

        state = _base_state()
        result = _run_world_sim(state, world_sim_output)

        ws = result["campaign"]["world_state_json"]
        pending = ws.get("pending_reactive_encounters", [])
        assert len(pending) <= REACTIVE_ENCOUNTER_MAX_PENDING

    def test_no_reactive_encounters_produces_empty_queue(self):
        """When WorldMind returns no reactive encounters, pending queue stays empty."""
        world_sim_output = WorldSimOutput(
            elapsed_time_summary="Time passes.",
            faction_moves=[], new_rumors=[], hidden_events=[],
            updated_factions=[],
            reactive_encounters=[],
        )

        state = _base_state()
        result = _run_world_sim(state, world_sim_output)

        ws = result["campaign"]["world_state_json"]
        pending = ws.get("pending_reactive_encounters", [])
        assert len(pending) == 0

    def test_urgency_affects_trigger_turn(self):
        """Different urgency values produce different trigger_turn ranges."""
        encounters = [
            {"trigger": "w", "npc_archetype": "a", "urgency": "next_turn", "hostility": "neutral"},
            {"trigger": "w", "npc_archetype": "b", "urgency": "eventual", "hostility": "neutral"},
        ]
        world_sim_output = WorldSimOutput(
            elapsed_time_summary=".", faction_moves=[], new_rumors=[], hidden_events=[],
            updated_factions=[], reactive_encounters=encounters,
        )

        state = _base_state(turn=10)
        result = _run_world_sim(state, world_sim_output)

        ws = result["campaign"]["world_state_json"]
        pending = ws.get("pending_reactive_encounters", [])
        # next_turn should have trigger_turn = 11
        next_turn_enc = [e for e in pending if e["npc_archetype"] == "a"]
        if next_turn_enc:
            assert next_turn_enc[0]["trigger_turn"] == 11
        # eventual should have trigger_turn between 13 and 18
        eventual_enc = [e for e in pending if e["npc_archetype"] == "b"]
        if eventual_enc:
            assert 13 <= eventual_enc[0]["trigger_turn"] <= 18


class TestReactiveEncounterNodeIntegration:
    """Phase 4B: Encounter node spawns reactive NPCs from pending queue."""

    def test_triggered_encounter_adds_npc_to_present(self):
        """Pending encounter with trigger_turn <= current_turn spawns a reactive NPC."""
        from backend.app.core.nodes.encounter import make_encounter_node

        pending = [{
            "trigger": "faction_move",
            "npc_archetype": "bounty_hunter",
            "faction": "Crimson Talon",
            "description": "Hunting the player for a bounty",
            "urgency": "next_turn",
            "hostility": "hostile",
            "trigger_turn": 5,
            "source_turn": 4,
        }]

        state = {
            "__runtime_conn": MagicMock(),
            "campaign_id": "test-camp",
            "campaign": {
                "world_state_json": {"pending_reactive_encounters": pending},
                "time_period": "",
            },
            "turn_number": 5,
            "current_location": "loc-cantina",
            "mechanic_result": {"time_cost_minutes": 0},
            "warnings": [],
        }

        node = make_encounter_node()

        with patch("backend.app.core.nodes.encounter.EncounterManager") as MockEM:
            MockEM.return_value.check.return_value = ([], [], None, [], [])
            with patch("backend.app.core.nodes.encounter.can_introduce_new_npc", return_value=(True, "")):
                with patch("backend.app.core.nodes.encounter.get_anonymous_extras", return_value=[]):
                    with patch("backend.app.core.nodes.encounter.throttle_load_world_state", return_value={}):
                        with patch("backend.app.core.nodes.encounter.get_recent_public_rumors", return_value=[]):
                            result = node(state)

        present = result.get("present_npcs", [])
        assert len(present) >= 1, f"Expected at least 1 NPC, got {len(present)}"
        reactive_npc = [n for n in present if n.get("reactive_encounter")]
        assert len(reactive_npc) == 1
        assert reactive_npc[0]["has_secret_agenda"] is True  # hostile
        assert "bounty" in reactive_npc[0].get("reactive_context", "").lower()

        # Triggered encounters removed from remaining
        remaining = result.get("reactive_encounters_remaining", [])
        assert len(remaining) == 0

    def test_future_encounter_not_triggered(self):
        """Pending encounter with trigger_turn > current_turn stays in queue."""
        from backend.app.core.nodes.encounter import make_encounter_node

        pending = [{
            "trigger": "faction_move",
            "npc_archetype": "emissary",
            "faction": "Senate",
            "description": "Diplomatic envoy",
            "urgency": "eventual",
            "hostility": "neutral",
            "trigger_turn": 10,
            "source_turn": 3,
        }]

        state = {
            "__runtime_conn": MagicMock(),
            "campaign_id": "test-camp",
            "campaign": {
                "world_state_json": {"pending_reactive_encounters": pending},
                "time_period": "",
            },
            "turn_number": 5,
            "current_location": "loc-cantina",
            "mechanic_result": {"time_cost_minutes": 0},
            "warnings": [],
        }

        node = make_encounter_node()

        with patch("backend.app.core.nodes.encounter.EncounterManager") as MockEM:
            MockEM.return_value.check.return_value = ([], [], None, [], [])
            with patch("backend.app.core.nodes.encounter.can_introduce_new_npc", return_value=(True, "")):
                with patch("backend.app.core.nodes.encounter.get_anonymous_extras", return_value=[]):
                    with patch("backend.app.core.nodes.encounter.throttle_load_world_state", return_value={}):
                        with patch("backend.app.core.nodes.encounter.get_recent_public_rumors", return_value=[]):
                            result = node(state)

        present = result.get("present_npcs", [])
        reactive_npcs = [n for n in present if n.get("reactive_encounter")]
        assert len(reactive_npcs) == 0, "Future encounters should not trigger"

        remaining = result.get("reactive_encounters_remaining", [])
        assert len(remaining) == 1, "Future encounter should stay in remaining"


class TestNPCDeathReactiveEncounters:
    """Phase 4D: NPC deaths generate reactive encounters for faction-connected NPCs."""

    def test_faction_npc_death_queues_avenger(self):
        """Killing a faction-connected NPC should queue an avenger encounter."""
        state = _base_state(turn=5)
        state["mechanic_result"]["events"] = [
            {
                "event_type": "DAMAGE",
                "payload": {
                    "target_name": "Captain Rex",
                    "target_id": "npc-rex",
                    "remaining_hp": 0,
                },
            }
        ]

        world_sim_output = WorldSimOutput(
            elapsed_time_summary="Death reverberates.",
            faction_moves=[], new_rumors=[], hidden_events=[],
            updated_factions=[],
            reactive_encounters=[],
        )

        node = make_world_sim_node()

        with patch("backend.app.core.nodes.world_sim.load_campaign") as mock_load:
            mock_load.return_value = {"world_state_json": state["campaign"]["world_state_json"]}
            # Patch the known_npcs DB query to return a faction-connected NPC
            mock_conn = state["__runtime_conn"]
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [
                ("npc-rex", "Captain Rex", "Military Officer", "loc-base",
                 '{"faction": "Republic"}', 5)
            ]
            mock_conn.execute.return_value = mock_cursor

            with patch("backend.app.core.agents.world_mind_agent.WorldMindAgent") as MockWM:
                MockWM.return_value.simulate.return_value = world_sim_output
                result = node(state)

        ws = result["campaign"]["world_state_json"]
        pending = ws.get("pending_reactive_encounters", [])
        avengers = [e for e in pending if e.get("npc_archetype") == "avenger"]
        assert len(avengers) >= 1, f"Expected avenger encounter, got {pending}"
        assert avengers[0]["faction"] == "Republic"
        assert avengers[0]["hostility"] == "hostile"

    def test_non_faction_npc_death_no_avenger(self):
        """Killing a non-faction NPC should not queue an avenger encounter."""
        state = _base_state(turn=5)
        state["mechanic_result"]["events"] = [
            {
                "event_type": "NPC_DEATH",
                "payload": {
                    "npc_name": "Random Thug",
                    "npc_id": "npc-thug-42",
                },
            }
        ]

        world_sim_output = WorldSimOutput(
            elapsed_time_summary="A minor event.",
            faction_moves=[], new_rumors=[], hidden_events=[],
            updated_factions=[],
            reactive_encounters=[],
        )

        node = make_world_sim_node()

        with patch("backend.app.core.nodes.world_sim.load_campaign") as mock_load:
            mock_load.return_value = {"world_state_json": state["campaign"]["world_state_json"]}
            mock_conn = state["__runtime_conn"]
            mock_cursor = MagicMock()
            # NPC has no faction
            mock_cursor.fetchall.return_value = [
                ("npc-thug-42", "Random Thug", "Thug", "loc-alley", "{}", 0)
            ]
            mock_conn.execute.return_value = mock_cursor

            with patch("backend.app.core.agents.world_mind_agent.WorldMindAgent") as MockWM:
                MockWM.return_value.simulate.return_value = world_sim_output
                result = node(state)

        ws = result["campaign"]["world_state_json"]
        pending = ws.get("pending_reactive_encounters", [])
        avengers = [e for e in pending if e.get("npc_archetype") == "avenger"]
        assert len(avengers) == 0, "Non-faction NPC death should not queue avenger"
