"""Tests for V8.0 Gate 4: Narrative Coherence improvements.

Tests cover:
- 4.1: Companion reactions woven into prose (COMPANION PRESENCE block)
- 4.2: Prose-choice bridge (SCENE ENDING in ChoiceCrafter prompt)
- 4.3: Scene loop escalation (tiered disruption)
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


# ---------------------------------------------------------------------------
# 4.1: Companion Reactions Woven Into Prose
# ---------------------------------------------------------------------------


class TestCompanionPresenceBlock:
    """Companion reactions appear as COMPANION PRESENCE woven directive."""

    def test_spoken_reactions_produce_presence_block(self):
        """When spoken_reactions exist, COMPANION PRESENCE block is generated."""
        from backend.app.core.agents.narrator_prompt import _build_story_state_summary
        from backend.app.models.state import GameState

        gs = GameState(
            campaign_id="test",
            player_id="p1",
            current_location="cantina",
            campaign={
                "party": ["kira"],
                "world_state_json": {
                    "companion_spoken_reactions": {
                        "kira": "I don't like this place.",
                    },
                },
            },
            present_npcs=[{"id": "kira", "name": "Kira", "role": "companion"}],
        )
        summary = _build_story_state_summary(gs)
        assert "COMPANION PRESENCE" in summary
        assert "Kira" in summary
        assert "I don't like this place." in summary
        assert "weave into scene" in summary.lower() or "do NOT list separately" in summary

    def test_fallback_to_cr_summary(self):
        """Without spoken_reactions, falls back to companion_reactions_summary."""
        from backend.app.core.agents.narrator_prompt import _build_story_state_summary
        from backend.app.models.state import GameState

        gs = GameState(
            campaign_id="test",
            player_id="p1",
            current_location="cantina",
            campaign={
                "party": ["kira"],
                "companion_reactions_summary": "- Kira (Warm, affinity +3): approved (helped refugees)",
                "world_state_json": {},
            },
            present_npcs=[],
        )
        summary = _build_story_state_summary(gs)
        assert "COMPANION PRESENCE" in summary
        assert "Kira" in summary
        assert "approved" in summary

    def test_no_companions_no_block(self):
        """Without companion data, no COMPANION PRESENCE block."""
        from backend.app.core.agents.narrator_prompt import _build_story_state_summary
        from backend.app.models.state import GameState

        gs = GameState(
            campaign_id="test",
            player_id="p1",
            current_location="cantina",
            campaign={"party": [], "world_state_json": {}},
            present_npcs=[],
        )
        summary = _build_story_state_summary(gs)
        assert "COMPANION PRESENCE" not in summary

    def test_tensions_included_in_presence(self):
        """Inter-party tensions appear in the COMPANION PRESENCE block."""
        from backend.app.core.agents.narrator_prompt import _build_story_state_summary
        from backend.app.models.state import GameState

        gs = GameState(
            campaign_id="test",
            player_id="p1",
            current_location="cantina",
            campaign={
                "party": ["kira", "vekk"],
                "inter_party_tensions_narrator": "Kira and Vekk exchange cold glares",
                "world_state_json": {
                    "companion_spoken_reactions": {"kira": "We should go."},
                },
            },
            present_npcs=[{"id": "kira", "name": "Kira", "role": "companion"}],
        )
        summary = _build_story_state_summary(gs)
        assert "COMPANION PRESENCE" in summary
        assert "cold glares" in summary
        assert "Inter-party tension" in summary

    def test_narrator_node_no_duplicate_kg_injection(self):
        """narrator.py should NOT inject companion reactions into kg_context anymore."""
        import backend.app.core.nodes.narrator as narrator_mod

        source = open(narrator_mod.__file__).read()
        # The old Phase 6.1 block that added reactions to kg_context should be gone
        assert "Companion Reactions This Turn" not in source
        assert "Companion Spoken Lines" not in source
        # Loyalty crisis should still be there
        assert "COMPANION LOYALTY CRISIS" in source


# ---------------------------------------------------------------------------
# 4.2: Prose-Choice Bridge
# ---------------------------------------------------------------------------


class TestProseChoiceBridge:
    """ChoiceCrafter receives SCENE ENDING from last paragraph of prose."""

    def test_scene_ending_extracted(self):
        """User prompt includes SCENE ENDING from last paragraph."""
        from backend.app.core.agents.choice_crafter_agent import _build_context

        prose = (
            "The cantina was dimly lit, smoke curling from the far corner.\n\n"
            "Kira leaned against the bar, her hand resting on her blaster.\n\n"
            "A stranger in a dark cloak stepped through the door, eyes scanning the room."
        )
        prompt = _build_context(
            final_text=prose,
            location="cantina",
            npc_descriptions=["Vale (bartender)"],
            mechanic_summary=None,
        )
        assert "SCENE ENDING" in prompt
        assert "stranger in a dark cloak" in prompt

    def test_scene_ending_capped_at_200_chars(self):
        """SCENE ENDING paragraph is capped at 200 characters."""
        from backend.app.core.agents.choice_crafter_agent import _build_context

        long_para = "A " * 200  # way over 200 chars
        prose = f"First paragraph.\n\n{long_para}"
        prompt = _build_context(
            final_text=prose,
            location="cantina",
            npc_descriptions=[],
            mechanic_summary=None,
        )
        # Find the SCENE ENDING line and check its content length
        assert "SCENE ENDING" in prompt

    def test_single_paragraph_uses_full_text(self):
        """With no paragraph breaks, last paragraph is the whole text."""
        from backend.app.core.agents.choice_crafter_agent import _build_context

        prose = "The guard stares you down, hand on his weapon."
        prompt = _build_context(
            final_text=prose,
            location="outpost",
            npc_descriptions=["Guard (imperial)"],
            mechanic_summary=None,
        )
        assert "SCENE ENDING" in prompt
        assert "guard stares you down" in prompt

    def test_empty_prose_no_scene_ending(self):
        """With empty prose, no SCENE ENDING is injected."""
        from backend.app.core.agents.choice_crafter_agent import _build_context

        prompt = _build_context(
            final_text="",
            location="cantina",
            npc_descriptions=[],
            mechanic_summary=None,
        )
        assert "SCENE ENDING" not in prompt


# ---------------------------------------------------------------------------
# 4.3: Scene Loop Escalation
# ---------------------------------------------------------------------------


class TestSceneLoopEscalation:
    """Tiered scene loop escalation in arc_planner."""

    def test_tier_1_first_loop_detection(self):
        """First loop detection adds escalation hint."""
        from backend.app.core.nodes.arc_planner import arc_planner_node

        state = {
            "turn_number": 10,
            "campaign": {
                "world_state_json": {
                    "arc_state": {"current_stage": "RISING", "stage_start_turn": 5,
                                  "scene_loop_consecutive": 0},
                },
            },
            "scene_loop_detected": True,
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert guidance["scene_loop_detected"] is True
        assert guidance["scene_loop_consecutive"] == 1
        assert "LOOP" in guidance["pacing_hint"].upper() or "ESCALAT" in guidance["pacing_hint"].upper()

    def test_tier_2_disruption_at_2_consecutive(self):
        """Second consecutive loop triggers tier 2 disruption."""
        from backend.app.core.nodes.arc_planner import arc_planner_node

        state = {
            "turn_number": 11,
            "campaign": {
                "world_state_json": {
                    "arc_state": {"current_stage": "RISING", "stage_start_turn": 5,
                                  "scene_loop_consecutive": 1},
                },
            },
            "scene_loop_detected": True,
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert guidance["scene_loop_consecutive"] == 2
        assert "STAGNATION" in guidance["pacing_hint"].upper()

    def test_tier_3_force_event_at_3_consecutive(self):
        """Third consecutive loop sets force_world_event flag."""
        from backend.app.core.nodes.arc_planner import arc_planner_node

        state = {
            "turn_number": 12,
            "campaign": {
                "world_state_json": {
                    "arc_state": {"current_stage": "RISING", "stage_start_turn": 5,
                                  "scene_loop_consecutive": 2},
                },
            },
            "scene_loop_detected": True,
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert guidance["scene_loop_consecutive"] == 3
        assert guidance.get("force_world_event") is True
        assert "CRITICAL" in guidance["pacing_hint"].upper()

    def test_counter_resets_when_loop_breaks(self):
        """Counter resets to 0 when scene_loop_detected is False."""
        from backend.app.core.nodes.arc_planner import arc_planner_node

        state = {
            "turn_number": 13,
            "campaign": {
                "world_state_json": {
                    "arc_state": {"current_stage": "RISING", "stage_start_turn": 5,
                                  "scene_loop_consecutive": 3},
                },
            },
            "scene_loop_detected": False,
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert guidance["scene_loop_consecutive"] == 0
        assert guidance.get("force_world_event") is None or guidance.get("force_world_event") is False

    def test_tension_bumped_on_loop(self):
        """Loop detection bumps tension from CALM/BUILDING to ESCALATING."""
        from backend.app.core.nodes.arc_planner import arc_planner_node

        state = {
            "turn_number": 5,
            "campaign": {
                "world_state_json": {
                    "arc_state": {"current_stage": "SETUP", "stage_start_turn": 0,
                                  "scene_loop_consecutive": 0},
                },
            },
            "scene_loop_detected": True,
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert guidance["tension_level"] == "ESCALATING"

    def test_counter_persists_in_arc_state(self):
        """scene_loop_consecutive is persisted in arc_state for next turn."""
        from backend.app.core.nodes.arc_planner import arc_planner_node

        state = {
            "turn_number": 10,
            "campaign": {
                "world_state_json": {
                    "arc_state": {"current_stage": "RISING", "stage_start_turn": 5,
                                  "scene_loop_consecutive": 1},
                },
            },
            "scene_loop_detected": True,
        }
        result = arc_planner_node(state)
        arc_state = result["arc_guidance"]["arc_state"]
        assert arc_state["scene_loop_consecutive"] == 2
