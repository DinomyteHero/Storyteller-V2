"""Tests for Phase 5 deep companion system: arc stages, conflicts, moments, party state."""
from __future__ import annotations

import pytest

from backend.app.core.companion_reactions import (
    companion_arc_stage,
    detect_companion_conflicts,
    extract_companion_moments,
    record_companion_moment,
    update_party_state,
)
from backend.app.constants import COMPANION_MAX_MEMORIES


# ---------------------------------------------------------------------------
# companion_arc_stage
# ---------------------------------------------------------------------------


def test_companion_arc_stage_stranger():
    """affinity=-15 -> STRANGER (threshold is <= -10)."""
    assert companion_arc_stage(-15) == "STRANGER"


def test_companion_arc_stage_ally():
    """affinity=0 -> ALLY (range -9..29)."""
    assert companion_arc_stage(0) == "ALLY"


def test_companion_arc_stage_trusted():
    """affinity=50 -> TRUSTED (range 30..69)."""
    assert companion_arc_stage(50) == "TRUSTED"


def test_companion_arc_stage_loyal():
    """affinity=80 -> LOYAL (threshold >= 70)."""
    assert companion_arc_stage(80) == "LOYAL"


# ---------------------------------------------------------------------------
# detect_companion_conflicts
# ---------------------------------------------------------------------------


def test_detect_companion_conflicts_sharp_drop():
    """delta=-8 (COMPANION_CONFLICT_SHARP_DROP) should trigger 'sharp_drop' conflict."""
    party = ["comp_a"]
    old_aff = {"comp_a": 10}
    new_aff = {"comp_a": 2}
    deltas = {"comp_a": -8}
    conflicts = detect_companion_conflicts(party, old_aff, new_aff, deltas)
    types = [c["conflict_type"] for c in conflicts]
    assert "sharp_drop" in types


def test_detect_companion_conflicts_threshold_cross():
    """old=5, new=-35 should trigger 'threshold_cross' (crossed 0 into hostile territory <= -30)."""
    party = ["comp_b"]
    old_aff = {"comp_b": 5}
    new_aff = {"comp_b": -35}
    deltas = {"comp_b": -40}
    conflicts = detect_companion_conflicts(party, old_aff, new_aff, deltas)
    types = [c["conflict_type"] for c in conflicts]
    assert "threshold_cross" in types


def test_detect_companion_conflicts_stage_downgrade():
    """old=35 (TRUSTED), new=25 (ALLY) should trigger 'stage_downgrade'."""
    party = ["comp_c"]
    old_aff = {"comp_c": 35}
    new_aff = {"comp_c": 25}
    deltas = {"comp_c": -10}
    conflicts = detect_companion_conflicts(party, old_aff, new_aff, deltas)
    types = [c["conflict_type"] for c in conflicts]
    assert "stage_downgrade" in types


# ---------------------------------------------------------------------------
# record_companion_moment
# ---------------------------------------------------------------------------


def test_record_companion_moment():
    """Recording a moment on empty world_state should populate companion_memories."""
    world_state: dict = {}
    cid = "jolee"
    moment = "Turn 5: jolee approved (paragon choice)"
    result = record_companion_moment(world_state, cid, moment)
    assert cid in result["companion_memories"]
    assert moment in result["companion_memories"][cid]


def test_record_companion_moment_caps():
    """Pre-fill 10 memories, record one more. Length should stay at COMPANION_MAX_MEMORIES."""
    cid = "bastila"
    world_state: dict = {
        "companion_memories": {
            cid: [f"memory_{i}" for i in range(COMPANION_MAX_MEMORIES)],
        },
    }
    record_companion_moment(world_state, cid, "newest memory")
    assert len(world_state["companion_memories"][cid]) == COMPANION_MAX_MEMORIES
    assert world_state["companion_memories"][cid][-1] == "newest memory"


# ---------------------------------------------------------------------------
# extract_companion_moments
# ---------------------------------------------------------------------------


def test_extract_companion_moments_significant():
    """delta=3 with reason 'paragon choice' should return a moment string."""
    result = extract_companion_moments(
        companion_id="jolee",
        delta=3,
        reason="paragon choice",
        mechanic_result=None,
        turn_number=7,
    )
    assert result is not None
    assert "jolee" in result
    assert "approved" in result


def test_extract_companion_moments_insignificant():
    """delta=1 (abs < 2) should return None (not significant enough)."""
    result = extract_companion_moments(
        companion_id="jolee",
        delta=1,
        reason="neutral",
        mechanic_result=None,
        turn_number=7,
    )
    assert result is None


# ---------------------------------------------------------------------------
# update_party_state (integration, still pure)
# ---------------------------------------------------------------------------


def test_update_party_state_with_conflicts():
    """Deltas causing a sharp drop should produce companion_conflicts in campaign."""
    state = {
        "campaign": {
            "party": ["comp_x"],
            "party_affinity": {"comp_x": 10},
            "loyalty_progress": {"comp_x": 0},
        },
    }
    deltas = {"comp_x": -8}
    reasons = {"comp_x": "disapproved renegade"}
    result = update_party_state(state, deltas, reasons=reasons, turn_number=5)
    campaign = result["campaign"]
    assert "companion_conflicts" in campaign
    types = [c["conflict_type"] for c in campaign["companion_conflicts"]]
    assert "sharp_drop" in types
