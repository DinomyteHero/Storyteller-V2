"""Tests for dynamic arc staging: _determine_arc_stage_dynamic() and arc_planner_node()."""
from __future__ import annotations


from backend.app.core.nodes.arc_planner import (
    _determine_arc_stage_dynamic,
    arc_planner_node,
)


# ---------------------------------------------------------------------------
# _determine_arc_stage_dynamic
# ---------------------------------------------------------------------------


def test_setup_stays_below_min_turns():
    """turn=2, stage_start=0: too early to leave SETUP (min_turns=3)."""
    stage, transitioned = _determine_arc_stage_dynamic(
        turn_number=2,
        ledger={"open_threads": ["t1", "t2", "t3"], "established_facts": ["f1", "f2", "f3", "f4"]},
        current_stage="SETUP",
        stage_start_turn=0,
    )
    assert stage == "SETUP"
    assert transitioned is False


def test_setup_to_rising_on_content_readiness():
    """turn=5, stage_start=0, ledger with 2+ threads and 3+ facts -> transition to RISING."""
    ledger = {
        "open_threads": ["thread_a", "thread_b"],
        "established_facts": ["fact_1", "fact_2", "fact_3"],
    }
    stage, transitioned = _determine_arc_stage_dynamic(
        turn_number=5,
        ledger=ledger,
        current_stage="SETUP",
        stage_start_turn=0,
    )
    assert stage == "RISING"
    assert transitioned is True


def test_setup_stays_without_content():
    """turn=5, stage_start=0, ledger with 0 threads -> stays SETUP."""
    ledger = {
        "open_threads": [],
        "established_facts": [],
    }
    stage, transitioned = _determine_arc_stage_dynamic(
        turn_number=5,
        ledger=ledger,
        current_stage="SETUP",
        stage_start_turn=0,
    )
    assert stage == "SETUP"
    assert transitioned is False


def test_setup_forced_at_max_turns():
    """turn=11, stage_start=0, empty ledger: exceeds ARC_MAX_TURNS['SETUP']=10 -> forced transition."""
    stage, transitioned = _determine_arc_stage_dynamic(
        turn_number=11,
        ledger={"open_threads": [], "established_facts": []},
        current_stage="SETUP",
        stage_start_turn=0,
    )
    assert stage == "RISING"
    assert transitioned is True


def test_rising_to_climax():
    """turn=12, stage_start=5, ledger with 4+ threads -> transition to CLIMAX."""
    ledger = {
        "open_threads": ["t1", "t2", "t3", "t4"],
        "established_facts": [],
    }
    stage, transitioned = _determine_arc_stage_dynamic(
        turn_number=12,
        ledger=ledger,
        current_stage="RISING",
        stage_start_turn=5,
    )
    assert stage == "CLIMAX"
    assert transitioned is True


def test_climax_to_resolution():
    """turn=20, stage_start=14, ledger with a 'resolved_quest' flag -> transition to RESOLUTION."""
    ledger = {
        "open_threads": [],
        "established_facts": ["Flag set: resolved_quest=True"],
    }
    stage, transitioned = _determine_arc_stage_dynamic(
        turn_number=20,
        ledger=ledger,
        current_stage="CLIMAX",
        stage_start_turn=14,
    )
    assert stage == "RESOLUTION"
    assert transitioned is True


def test_resolution_is_terminal():
    """RESOLUTION is terminal: it never transitions further."""
    stage, transitioned = _determine_arc_stage_dynamic(
        turn_number=30,
        ledger={"open_threads": [], "established_facts": []},
        current_stage="RESOLUTION",
        stage_start_turn=25,
    )
    assert stage == "RESOLUTION"
    assert transitioned is False


def test_backward_compat_none_stage():
    """current_stage=None should return ('SETUP', False)."""
    stage, transitioned = _determine_arc_stage_dynamic(
        turn_number=1,
        ledger={},
        current_stage=None,
        stage_start_turn=0,
    )
    assert stage == "SETUP"
    assert transitioned is False


# ---------------------------------------------------------------------------
# arc_planner_node (integration-level, still pure)
# ---------------------------------------------------------------------------


def test_arc_planner_node_persists_arc_state():
    """arc_planner_node() should produce arc_guidance with arc_state inside."""
    state = {
        "turn_number": 5,
        "campaign": {
            "world_state_json": {
                "ledger": {
                    "open_threads": ["t1", "t2"],
                    "established_facts": ["f1", "f2", "f3"],
                    "active_themes": [],
                },
            },
        },
    }
    result = arc_planner_node(state)
    assert "arc_guidance" in result
    guidance = result["arc_guidance"]
    assert "arc_state" in guidance
    assert "current_stage" in guidance["arc_state"]
    assert "stage_start_turn" in guidance["arc_state"]
