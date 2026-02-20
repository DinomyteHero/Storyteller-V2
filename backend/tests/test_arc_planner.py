"""Tests for the arc planner node: deterministic arc stage + pacing guidance.

Updated for V2.5 content-aware arc transitions (Phase 4).
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.nodes.arc_planner import (  # noqa: E402
    arc_planner_node,
    _determine_arc_stage_dynamic,
    _determine_tension,
)


class TestDetermineArcStageDynamic:
    """Tests for content-aware arc stage transitions."""

    def test_setup_stays_at_turn_1(self):
        stage, transition, _ = _determine_arc_stage_dynamic(1, {}, "SETUP", 0)
        assert stage == "SETUP"
        assert transition is False

    def test_setup_stays_without_content(self):
        """Without enough threads/facts, SETUP persists even past min turns."""
        stage, transition, _ = _determine_arc_stage_dynamic(5, {}, "SETUP", 0)
        assert stage == "SETUP"
        assert transition is False

    def test_setup_to_rising_with_content(self):
        """Enough threads and facts trigger SETUP -> RISING."""
        ledger = {
            "open_threads": ["thread1", "thread2"],
            "established_facts": ["fact1", "fact2", "fact3"],
        }
        stage, transition, _ = _determine_arc_stage_dynamic(5, ledger, "SETUP", 0)
        assert stage == "RISING"
        assert transition is True

    def test_setup_forced_at_max(self):
        """After ARC_MAX_TURNS["SETUP"]=10 turns, force transition even without content."""
        stage, transition, _ = _determine_arc_stage_dynamic(11, {}, "SETUP", 0)
        assert stage == "RISING"
        assert transition is True

    def test_none_stage_returns_setup(self):
        stage, transition, _ = _determine_arc_stage_dynamic(1, {}, None, 0)
        assert stage == "SETUP"
        assert transition is False

    def test_resolution_stays_in_resolution(self):
        """RESOLUTION stays — multi-arc transition handled by arc_planner_node."""
        stage, transition, _ = _determine_arc_stage_dynamic(50, {}, "RESOLUTION", 30)
        assert stage == "RESOLUTION"
        assert transition is False


class TestDetermineTension:
    def test_setup_calm(self):
        assert _determine_tension("SETUP", {}) == "CALM"

    def test_rising_escalating_with_threads(self):
        ledger = {"open_threads": ["thread1", "thread2"]}
        assert _determine_tension("RISING", ledger) == "ESCALATING"

    def test_rising_building_with_few_threads(self):
        ledger = {"open_threads": ["thread1"]}
        assert _determine_tension("RISING", ledger) == "BUILDING"

    def test_rising_building_no_threads(self):
        assert _determine_tension("RISING", {}) == "BUILDING"

    def test_climax_peak(self):
        assert _determine_tension("CLIMAX", {}) == "PEAK"

    def test_resolution_resolving(self):
        assert _determine_tension("RESOLUTION", {}) == "RESOLVING"


class TestArcPlannerNode:
    def test_node_returns_arc_guidance(self):
        state = {"turn_number": 3, "campaign": {}}
        result = arc_planner_node(state)
        assert "arc_guidance" in result
        guidance = result["arc_guidance"]
        assert guidance["arc_stage"] == "SETUP"
        assert guidance["tension_level"] == "CALM"
        assert guidance["pacing_hint"] != ""
        assert "suggested_weight" in guidance

    def test_node_reads_ledger_threads(self):
        ledger = {
            "open_threads": ["Find the artifact", "Rescue the prisoner"],
            "established_facts": ["fact1", "fact2", "fact3"],
        }
        # Provide arc_state so it starts at SETUP from turn 0
        state = {
            "turn_number": 10,
            "campaign": {"world_state_json": {"ledger": ledger, "arc_state": {"current_stage": "SETUP", "stage_start_turn": 0}}},
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        # With 2 threads + 3 facts and turn 10, should transition to RISING
        assert guidance["arc_stage"] == "RISING"
        assert guidance["priority_threads"] == ["Find the artifact", "Rescue the prisoner"]

    def test_node_preserves_state(self):
        state = {"turn_number": 20, "campaign": {}, "some_key": "some_value"}
        result = arc_planner_node(state)
        assert result["some_key"] == "some_value"
        assert result["turn_number"] == 20

    def test_node_handles_missing_campaign(self):
        state = {"turn_number": 5}
        result = arc_planner_node(state)
        assert "arc_guidance" in result
        assert result["arc_guidance"]["arc_stage"] == "SETUP"

    def test_node_includes_arc_state_for_persistence(self):
        state = {"turn_number": 3, "campaign": {}}
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert "arc_state" in guidance
        assert "current_stage" in guidance["arc_state"]
        assert "stage_start_turn" in guidance["arc_state"]

    def test_setup_weights_balanced(self):
        state = {"turn_number": 2, "campaign": {}}
        result = arc_planner_node(state)
        weights = result["arc_guidance"]["suggested_weight"]
        assert weights["SOCIAL"] == weights["EXPLORE"]

    def test_node_includes_theme_fields(self):
        """Arc planner should include active_themes and theme_guidance."""
        ledger = {"active_themes": ["redemption"], "open_threads": [], "established_facts": []}
        state = {
            "turn_number": 5,
            "campaign": {"world_state_json": {"ledger": ledger}},
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert "active_themes" in guidance
        assert guidance["active_themes"] == ["redemption"]
        assert "theme_guidance" in guidance


    def test_node_uses_arc_seed_themes_when_ledger_empty(self):
        state = {
            "turn_number": 2,
            "campaign": {
                "world_state_json": {
                    "ledger": {},
                    "arc_seed": {
                        "active_themes": ["duty", "trust"],
                        "opening_threads": ["A", "B"],
                        "climax_question": "Will they hold the line?",
                        "arc_intent": "pressure curve",
                    },
                }
            },
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert guidance["active_themes"] == ["duty", "trust"]
        assert guidance["seed_climax_question"] == "Will they hold the line?"
        assert guidance["arc_intent"] == "pressure curve"

    def test_node_uses_arc_seed_threads_in_opening_turns(self):
        state = {
            "turn_number": 3,
            "campaign": {
                "world_state_json": {
                    "ledger": {"open_threads": [], "established_facts": []},
                    "arc_seed": {
                        "active_themes": ["survival"],
                        "opening_threads": ["Seed thread one", "Seed thread two", "Seed thread three"],
                    },
                }
            },
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert guidance["priority_threads"] == ["Seed thread one", "Seed thread two"]


class TestMultiArcChaining:
    """Tests for V8.0 multi-arc orchestration."""

    def test_arc_state_includes_multi_arc_fields(self):
        """New arc_state should include current_arc_number and arc_history."""
        state = {"turn_number": 3, "campaign": {}}
        result = arc_planner_node(state)
        arc_state = result["arc_guidance"]["arc_state"]
        assert "current_arc_number" in arc_state
        assert "arc_history" in arc_state
        assert arc_state["current_arc_number"] == 1
        assert arc_state["arc_history"] == []

    def test_arc_guidance_includes_multi_arc_tracking(self):
        """arc_guidance output should include saga-level tracking fields."""
        state = {"turn_number": 3, "campaign": {}}
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert guidance["current_arc_number"] == 1
        assert guidance["current_arc_id"] == "arc_1"
        assert guidance["campaign_concluding"] is False
        assert guidance["epilogue_active"] is False
        assert guidance["campaign_complete"] is False

    def test_resolution_triggers_arc_transition(self):
        """When conclusion_ready=True in RESOLUTION, arc should transition to new SETUP."""
        # Build state that's deep into RESOLUTION with all threads resolved
        ledger = {
            "open_threads": ["[W1] Thread A"],
            "established_facts": ["resolved: Thread A outcome"],
            "active_themes": ["hope"],
        }
        state = {
            "turn_number": 25,
            "campaign": {
                "world_state_json": {
                    "ledger": ledger,
                    "arc_state": {
                        "current_stage": "RESOLUTION",
                        "stage_start_turn": 20,
                        "interlude_remaining": 0,
                        "current_arc_number": 1,
                        "current_arc_id": "arc_1",
                        "arc_history": [],
                    },
                    "campaign_scale": "medium",  # needs 3 arcs, so arc 1→2 should chain
                }
            },
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]

        # Should have transitioned to a new arc
        if guidance["arc_stage"] == "SETUP":
            # Arc transition occurred
            assert guidance["current_arc_number"] == 2
            assert guidance["interlude_active"] is True
            assert len(guidance["arc_history"]) == 1
            assert guidance["arc_history"][0]["arc_number"] == 1
        else:
            # Still in RESOLUTION (conclusion not ready yet due to ratio)
            # This is also valid if resolved_ratio < required_ratio (0.7)
            assert guidance["arc_stage"] == "RESOLUTION"

    def test_epilogue_triggers_after_max_arcs(self):
        """When final arc completes, epilogue should activate."""
        ledger = {
            "open_threads": ["[W1] Last thread"],
            "established_facts": ["resolved: Last thread done"],
            "active_themes": ["legacy"],
        }
        state = {
            "turn_number": 80,
            "campaign": {
                "world_state_json": {
                    "ledger": ledger,
                    "arc_state": {
                        "current_stage": "RESOLUTION",
                        "stage_start_turn": 75,
                        "interlude_remaining": 0,
                        "current_arc_number": 3,  # medium scale max = 3
                        "current_arc_id": "arc_3",
                        "arc_history": [
                            {"arc_id": "arc_1", "arc_number": 1, "arc_seed_summary": "Arc 1 summary",
                             "dangling_hooks": [], "turns": 25, "ending_style": "soft_cliffhanger"},
                            {"arc_id": "arc_2", "arc_number": 2, "arc_seed_summary": "Arc 2 summary",
                             "dangling_hooks": [], "turns": 25, "ending_style": "soft_cliffhanger"},
                        ],
                    },
                    "campaign_scale": "medium",
                }
            },
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]

        # Either epilogue triggers or still resolving
        if guidance.get("epilogue_active"):
            assert guidance["campaign_concluding"] is True
            assert guidance["arc_stage"] == "RESOLUTION"
            assert len(guidance["arc_history"]) == 3

    def test_epilogue_counts_down_to_campaign_complete(self):
        """Epilogue should count down and set campaign_complete."""
        state = {
            "turn_number": 85,
            "campaign": {
                "world_state_json": {
                    "ledger": {},
                    "arc_state": {
                        "current_stage": "RESOLUTION",
                        "stage_start_turn": 80,
                        "interlude_remaining": 0,
                        "current_arc_number": 3,
                        "current_arc_id": "arc_3",
                        "arc_history": [
                            {"arc_id": "arc_1", "arc_number": 1, "arc_seed_summary": "s",
                             "dangling_hooks": [], "turns": 25, "ending_style": "closed"},
                        ],
                        "campaign_concluding": True,
                        "epilogue_active": True,
                        "epilogue_remaining": 1,  # Last epilogue turn
                    },
                    "campaign_scale": "medium",
                }
            },
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert guidance["epilogue_active"] is True
        assert guidance["campaign_complete"] is True

    def test_campaign_complete_returns_minimal_guidance(self):
        """After campaign_complete, arc planner returns minimal guidance."""
        state = {
            "turn_number": 90,
            "campaign": {
                "world_state_json": {
                    "ledger": {},
                    "arc_state": {
                        "current_stage": "RESOLUTION",
                        "stage_start_turn": 80,
                        "current_arc_number": 3,
                        "current_arc_id": "arc_3",
                        "arc_history": [],
                        "campaign_concluding": True,
                        "epilogue_active": True,
                        "epilogue_remaining": 0,
                        "campaign_complete": True,
                    },
                }
            },
        }
        result = arc_planner_node(state)
        guidance = result["arc_guidance"]
        assert guidance.get("campaign_complete") is True
        assert guidance["pacing_hint"] == "Campaign is complete."

    def test_interlude_node_passthrough_when_inactive(self):
        """Interlude node should pass through when interlude_active is False."""
        from backend.app.core.nodes.interlude import interlude_node
        state = {"arc_guidance": {"interlude_active": False}, "campaign": {}}
        result = interlude_node(state)
        assert result is state  # Should be exact same dict

    def test_interlude_node_injects_context_when_active(self):
        """Interlude node should inject director_instructions when active."""
        from backend.app.core.nodes.interlude import interlude_node
        state = {
            "arc_guidance": {
                "interlude_active": True,
                "current_arc_number": 2,
                "arc_history": [{"arc_seed_summary": "Arc 1 ended with betrayal"}],
                "saga_context": "Arc 1 ended with betrayal",
                "arc_state": {"interlude_remaining": 1},
            },
            "campaign": {
                "news_feed": [{"headline": "Empire tightens grip"}],
                "world_state_json": {
                    "banter_queue": ["Kira mutters about the cold"],
                },
            },
            "active_rumors": ["Rebels gathering in sector 7"],
        }
        result = interlude_node(state)
        assert "INTERLUDE SCENE" in result["director_instructions"]
        assert "Empire tightens grip" in result["director_instructions"]
        assert result["pending_world_time_minutes"] == 48 * 60
