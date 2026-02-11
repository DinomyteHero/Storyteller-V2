"""Tests for the arc planner node: deterministic arc stage + pacing guidance.

Updated for V2.5 content-aware arc transitions (Phase 4).
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.nodes.arc_planner import (
    arc_planner_node,
    _determine_arc_stage_dynamic,
    _determine_tension,
)


class TestDetermineArcStageDynamic:
    """Tests for content-aware arc stage transitions."""

    def test_setup_stays_at_turn_1(self):
        stage, transition = _determine_arc_stage_dynamic(1, {}, "SETUP", 0)
        assert stage == "SETUP"
        assert transition is False

    def test_setup_stays_without_content(self):
        """Without enough threads/facts, SETUP persists even past min turns."""
        stage, transition = _determine_arc_stage_dynamic(5, {}, "SETUP", 0)
        assert stage == "SETUP"
        assert transition is False

    def test_setup_to_rising_with_content(self):
        """Enough threads and facts trigger SETUP -> RISING."""
        ledger = {
            "open_threads": ["thread1", "thread2"],
            "established_facts": ["fact1", "fact2", "fact3"],
        }
        stage, transition = _determine_arc_stage_dynamic(5, ledger, "SETUP", 0)
        assert stage == "RISING"
        assert transition is True

    def test_setup_forced_at_max(self):
        """After ARC_MAX_TURNS["SETUP"]=10 turns, force transition even without content."""
        stage, transition = _determine_arc_stage_dynamic(11, {}, "SETUP", 0)
        assert stage == "RISING"
        assert transition is True

    def test_none_stage_returns_setup(self):
        stage, transition = _determine_arc_stage_dynamic(1, {}, None, 0)
        assert stage == "SETUP"
        assert transition is False

    def test_resolution_is_terminal(self):
        stage, transition = _determine_arc_stage_dynamic(50, {}, "RESOLUTION", 30)
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
