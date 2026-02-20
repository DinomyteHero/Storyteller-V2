"""Gate 5: Multi-arc campaign lifecycle integration tests.

Tests the full arc engine lifecycle:
- Single arc progression SETUP→RISING→CLIMAX→RESOLUTION
- Multi-arc chaining with interludes
- Epilogue and campaign_complete
- Edge cases: empty state, missing fields, arc boundary rewinding
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.nodes.arc_planner import (  # noqa: E402
    arc_planner_node,
    _determine_arc_stage_dynamic,
)


# ---------------------------------------------------------------------------
# 5.2a: Single Arc Progression
# ---------------------------------------------------------------------------


class TestSingleArcProgression:
    """Verify a single arc progresses through all stages correctly."""

    def _run_arc(self, start_turn: int, arc_number: int = 1, stage_start: int = 0):
        """Drive an arc through SETUP → RISING → CLIMAX → RESOLUTION."""
        stages_seen = []
        state = {
            "turn_number": start_turn,
            "campaign": {
                "world_state_json": {
                    "ledger": {"open_threads": [], "established_facts": []},
                    "arc_state": {
                        "current_stage": "SETUP",
                        "stage_start_turn": stage_start,
                        "current_arc_number": arc_number,
                        "current_arc_id": f"arc_{arc_number}",
                        "arc_history": [],
                        "campaign_concluding": False,
                        "epilogue_active": False,
                        "epilogue_remaining": 0,
                        "campaign_complete": False,
                    },
                    "campaign_scale": "medium",
                },
            },
        }

        for turn_offset in range(60):
            turn = start_turn + turn_offset
            state["turn_number"] = turn

            # Evolve ledger to trigger transitions
            ws = state["campaign"]["world_state_json"]
            ledger = ws["ledger"]
            result = arc_planner_node(state)
            guidance = result["arc_guidance"]
            stage = guidance["arc_stage"]
            stages_seen.append(stage)

            # Update state for next turn
            ws["arc_state"] = guidance["arc_state"]
            state["campaign"]["world_state_json"] = ws

            # Simulate content accumulation to drive transitions
            if stage == "SETUP" and turn_offset >= 3:
                ledger["open_threads"] = ["thread_a", "thread_b"]
                ledger["established_facts"] = ["fact1", "fact2", "fact3"]
            elif stage == "RISING" and turn_offset >= 10:
                ledger["open_threads"] = ["t1", "t2", "t3", "t4"]
                ledger["established_facts"] = ["f1", "f2", "f3", "f4", "f5"]
            elif stage == "CLIMAX" and turn_offset >= 18:
                ledger["established_facts"].append("Flag set: resolved_climax=True")
            elif stage == "RESOLUTION":
                break

        return stages_seen

    def test_arc_progresses_through_all_stages(self):
        """An arc should visit SETUP, RISING, CLIMAX, and RESOLUTION."""
        stages = self._run_arc(start_turn=1)
        unique = list(dict.fromkeys(stages))
        assert "SETUP" in unique
        assert "RISING" in unique
        assert "CLIMAX" in unique
        assert "RESOLUTION" in unique
        # Verify order
        assert unique.index("SETUP") < unique.index("RISING")
        assert unique.index("RISING") < unique.index("CLIMAX")
        assert unique.index("CLIMAX") < unique.index("RESOLUTION")

    def test_stages_never_regress(self):
        """Stages should only progress forward, never go backwards."""
        stages = self._run_arc(start_turn=1)
        stage_order = {"SETUP": 0, "RISING": 1, "CLIMAX": 2, "RESOLUTION": 3}
        for i in range(1, len(stages)):
            assert stage_order[stages[i]] >= stage_order[stages[i - 1]], (
                f"Stage regressed from {stages[i-1]} to {stages[i]} at step {i}"
            )


# ---------------------------------------------------------------------------
# 5.2b: Full Multi-Arc Campaign Lifecycle
# ---------------------------------------------------------------------------


class TestMultiArcCampaignLifecycle:
    """Full 3-arc campaign lifecycle for medium scale."""

    def test_three_arc_campaign_to_completion(self):
        """Drive a medium-scale campaign through 3 arcs to campaign_complete."""
        state = {
            "turn_number": 1,
            "campaign": {
                "world_state_json": {
                    "ledger": {"open_threads": [], "established_facts": [], "active_themes": ["duty"]},
                    "arc_state": {
                        "current_stage": "SETUP",
                        "stage_start_turn": 0,
                        "interlude_remaining": 0,
                        "current_arc_number": 1,
                        "current_arc_id": "arc_1",
                        "arc_history": [],
                        "campaign_concluding": False,
                        "epilogue_active": False,
                        "epilogue_remaining": 0,
                        "campaign_complete": False,
                    },
                    "campaign_scale": "medium",
                },
            },
        }

        max_turns = 200
        arc_transitions = []
        arc_numbers_seen = []
        campaign_complete = False
        epilogue_seen = False

        for turn in range(1, max_turns + 1):
            state["turn_number"] = turn
            ws = state["campaign"]["world_state_json"]
            ledger = ws["ledger"]
            arc_state = ws["arc_state"]
            current_stage = arc_state.get("current_stage", "SETUP")
            arc_num = arc_state.get("current_arc_number", 1)

            # Simulate content to drive transitions
            stage_start = arc_state.get("stage_start_turn", 0)
            turns_in_stage = turn - stage_start

            if current_stage == "SETUP" and turns_in_stage >= 4:
                ledger["open_threads"] = [f"arc{arc_num}_thread_{i}" for i in range(3)]
                ledger["established_facts"] = [f"arc{arc_num}_fact_{i}" for i in range(4)]
            elif current_stage == "RISING" and turns_in_stage >= 6:
                ledger["open_threads"] = [f"[W3] arc{arc_num}_thread_{i}" for i in range(5)]
                ledger["established_facts"] = [f"arc{arc_num}_fact_{i}" for i in range(6)]
            elif current_stage == "CLIMAX" and turns_in_stage >= 6:
                ledger["established_facts"].append("Flag set: resolved_climax=True")
            elif current_stage == "RESOLUTION" and turns_in_stage >= 3:
                # Resolve enough threads for conclusion (70% for medium)
                resolved = [f"resolved: arc{arc_num}_thread_{i}" for i in range(5)]
                ledger["established_facts"] = resolved + ledger.get("established_facts", [])

            result = arc_planner_node(state)
            guidance = result["arc_guidance"]

            # Track transitions
            new_arc_num = guidance.get("current_arc_number", arc_num)
            if new_arc_num != arc_num or (new_arc_num not in arc_numbers_seen):
                arc_numbers_seen.append(new_arc_num)
            if guidance.get("transition_occurred"):
                arc_transitions.append(turn)

            # Check for epilogue
            if guidance.get("epilogue_active"):
                epilogue_seen = True

            # Check for campaign complete
            if guidance.get("campaign_complete"):
                campaign_complete = True
                break

            # Persist state for next turn
            ws["arc_state"] = guidance["arc_state"]
            # Reset ledger for new arcs
            if guidance.get("transition_occurred") and guidance["arc_stage"] == "SETUP":
                ledger["open_threads"] = []
                ledger["established_facts"] = []

        assert campaign_complete, f"Campaign did not complete within {max_turns} turns"
        assert epilogue_seen, "Epilogue phase was never reached"
        assert len(arc_numbers_seen) >= 3, f"Expected 3 arcs but saw: {arc_numbers_seen}"

    def test_arc_history_accumulates(self):
        """Each completed arc should add an entry to arc_history."""
        # Start at the END of arc 1's resolution, with conclusion ready
        state = {
            "turn_number": 25,
            "campaign": {
                "world_state_json": {
                    "ledger": {
                        "open_threads": ["[W1] Thread A"],
                        "established_facts": ["resolved: Thread A outcome"],
                        "active_themes": ["hope"],
                    },
                    "arc_state": {
                        "current_stage": "RESOLUTION",
                        "stage_start_turn": 20,
                        "interlude_remaining": 0,
                        "current_arc_number": 1,
                        "current_arc_id": "arc_1",
                        "arc_history": [],
                        "campaign_concluding": False,
                        "epilogue_active": False,
                        "epilogue_remaining": 0,
                        "campaign_complete": False,
                    },
                    "campaign_scale": "medium",
                },
            },
        }

        result = arc_planner_node(state)
        guidance = result["arc_guidance"]

        # Depending on resolved_ratio, may or may not transition
        if guidance["arc_stage"] == "SETUP":
            # Transition happened
            assert guidance["current_arc_number"] == 2
            assert len(guidance["arc_history"]) >= 1
            assert guidance["arc_history"][0]["arc_number"] == 1
        else:
            # Still in RESOLUTION (resolved ratio not sufficient)
            assert guidance["arc_stage"] == "RESOLUTION"


# ---------------------------------------------------------------------------
# 5.2c: Interlude Behavior
# ---------------------------------------------------------------------------


class TestInterludeBehavior:
    """Interlude node behaves correctly between arcs."""

    def test_interlude_passthrough_when_inactive(self):
        """Interlude node passes state through unchanged when inactive."""
        from backend.app.core.nodes.interlude import interlude_node

        state = {"arc_guidance": {"interlude_active": False}, "campaign": {}}
        result = interlude_node(state)
        assert result is state

    def test_interlude_injects_director_instructions(self):
        """Active interlude injects INTERLUDE SCENE into director_instructions."""
        from backend.app.core.nodes.interlude import interlude_node

        state = {
            "arc_guidance": {
                "interlude_active": True,
                "current_arc_number": 2,
                "arc_history": [{"arc_seed_summary": "Escape from Yavin"}],
                "saga_context": "Escape from Yavin",
                "arc_state": {"interlude_remaining": 1},
            },
            "campaign": {
                "news_feed": [{"headline": "Rebel fleet regroups at Hoth"}],
                "world_state_json": {"banter_queue": []},
            },
            "active_rumors": [],
        }
        result = interlude_node(state)
        assert "INTERLUDE SCENE" in result["director_instructions"]


# ---------------------------------------------------------------------------
# 5.3: Edge Case Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases for campaign robustness."""

    def test_missing_campaign_key(self):
        """Arc planner handles state with no campaign key."""
        result = arc_planner_node({"turn_number": 5})
        assert "arc_guidance" in result
        assert result["arc_guidance"]["arc_stage"] == "SETUP"

    def test_empty_world_state_json(self):
        """Arc planner handles empty world_state_json."""
        state = {"turn_number": 5, "campaign": {"world_state_json": {}}}
        result = arc_planner_node(state)
        assert "arc_guidance" in result
        assert result["arc_guidance"]["arc_stage"] == "SETUP"

    def test_none_arc_state(self):
        """Arc planner handles None arc_state in world_state_json."""
        state = {
            "turn_number": 5,
            "campaign": {"world_state_json": {"arc_state": None}},
        }
        result = arc_planner_node(state)
        assert result["arc_guidance"]["arc_stage"] == "SETUP"

    def test_corrupted_arc_state_types(self):
        """Arc planner handles non-dict arc_state."""
        state = {
            "turn_number": 5,
            "campaign": {"world_state_json": {"arc_state": "corrupted"}},
        }
        result = arc_planner_node(state)
        assert result["arc_guidance"]["arc_stage"] == "SETUP"

    def test_turn_number_zero(self):
        """Arc planner handles turn_number=0."""
        state = {"turn_number": 0, "campaign": {}}
        result = arc_planner_node(state)
        assert result["arc_guidance"]["arc_stage"] == "SETUP"

    def test_very_high_turn_number(self):
        """Arc planner handles very high turn numbers gracefully."""
        state = {
            "turn_number": 999,
            "campaign": {
                "world_state_json": {
                    "arc_state": {
                        "current_stage": "RISING",
                        "stage_start_turn": 900,
                        "current_arc_number": 1,
                    },
                },
            },
        }
        result = arc_planner_node(state)
        assert "arc_guidance" in result

    def test_arc_state_preserves_custom_fields(self):
        """State dict keys outside arc_guidance are preserved."""
        state = {
            "turn_number": 5,
            "campaign": {},
            "custom_field": "should_survive",
            "user_input": "test",
        }
        result = arc_planner_node(state)
        assert result["custom_field"] == "should_survive"
        assert result["user_input"] == "test"

    def test_campaign_complete_is_idempotent(self):
        """After campaign_complete, repeated calls return same minimal state."""
        state = {
            "turn_number": 100,
            "campaign": {
                "world_state_json": {
                    "arc_state": {
                        "current_stage": "RESOLUTION",
                        "stage_start_turn": 95,
                        "current_arc_number": 3,
                        "current_arc_id": "arc_3",
                        "arc_history": [],
                        "campaign_concluding": True,
                        "epilogue_active": True,
                        "epilogue_remaining": 0,
                        "campaign_complete": True,
                    },
                },
            },
        }
        r1 = arc_planner_node(state)
        assert r1["arc_guidance"]["campaign_complete"] is True
        assert r1["arc_guidance"]["pacing_hint"] == "Campaign is complete."

        # Run again with same state
        state["campaign"]["world_state_json"]["arc_state"] = r1["arc_guidance"]["arc_state"]
        r2 = arc_planner_node(state)
        assert r2["arc_guidance"]["campaign_complete"] is True
        assert r2["arc_guidance"]["pacing_hint"] == "Campaign is complete."

    def test_determine_arc_stage_none_input(self):
        """_determine_arc_stage_dynamic handles None current_stage."""
        stage, transition, _ = _determine_arc_stage_dynamic(1, {}, None, 0)
        assert stage == "SETUP"
        assert transition is False


# ---------------------------------------------------------------------------
# 5.3b: Snapshot / Rewind Safety
# ---------------------------------------------------------------------------


class TestSnapshotRewindSafety:
    """Arc state should be safely restorable from a snapshot."""

    def test_arc_state_is_serializable(self):
        """arc_state output should be JSON-serializable (dict of primitives)."""
        import json

        state = {
            "turn_number": 20,
            "campaign": {
                "world_state_json": {
                    "ledger": {"open_threads": ["a"], "established_facts": ["b"]},
                    "arc_state": {
                        "current_stage": "RISING",
                        "stage_start_turn": 10,
                        "current_arc_number": 2,
                        "current_arc_id": "arc_2",
                        "arc_history": [
                            {"arc_id": "arc_1", "arc_number": 1, "turns": 15,
                             "arc_seed_summary": "test", "dangling_hooks": [],
                             "ending_style": "soft_cliffhanger"},
                        ],
                    },
                },
            },
        }
        result = arc_planner_node(state)
        arc_state = result["arc_guidance"]["arc_state"]

        # Must be JSON-serializable
        serialized = json.dumps(arc_state)
        deserialized = json.loads(serialized)
        assert deserialized["current_stage"] == arc_state["current_stage"]
        assert deserialized["current_arc_number"] == arc_state["current_arc_number"]

    def test_restored_arc_state_produces_same_guidance(self):
        """Restoring arc_state from a snapshot should produce equivalent guidance."""
        import json

        state = {
            "turn_number": 15,
            "campaign": {
                "world_state_json": {
                    "ledger": {"open_threads": ["t1", "t2"], "established_facts": ["f1"]},
                    "arc_state": {
                        "current_stage": "RISING",
                        "stage_start_turn": 5,
                        "current_arc_number": 1,
                        "current_arc_id": "arc_1",
                        "arc_history": [],
                    },
                },
            },
        }
        result1 = arc_planner_node(state)
        arc_state_snapshot = json.loads(json.dumps(result1["arc_guidance"]["arc_state"]))

        # Restore from snapshot
        state["campaign"]["world_state_json"]["arc_state"] = arc_state_snapshot
        result2 = arc_planner_node(state)

        assert result1["arc_guidance"]["arc_stage"] == result2["arc_guidance"]["arc_stage"]
        assert result1["arc_guidance"]["tension_level"] == result2["arc_guidance"]["tension_level"]
