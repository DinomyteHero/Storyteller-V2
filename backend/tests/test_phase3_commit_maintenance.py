from __future__ import annotations

from backend.app.constants import NPC_STATES_MAX
from backend.app.core.nodes.commit import (
    _extract_latest_turn_from_memories,
    _touch_and_cap_npc_states,
)


def test_extract_latest_turn_from_memories() -> None:
    memories = [
        "Turn 3: First contact in the market.",
        "Turn 11: The standoff escalated.",
        "Unstructured note",
        "Turn 9: Negotiation failed.",
    ]
    assert _extract_latest_turn_from_memories(memories) == 11


def test_touch_and_cap_npc_states_marks_present_and_caps_by_recency() -> None:
    world_state = {
        "npc_states": {
            f"npc-{i}": {"last_seen_turn": i, "memories": [f"Turn {i}: memory"]}
            for i in range(1, 45)
        }
    }
    present_npcs = [{"id": "npc-2", "name": "Existing NPC"}, {"id": "npc-new", "name": "New NPC"}]

    _touch_and_cap_npc_states(world_state, present_npcs=present_npcs, turn_number=100)

    npc_states = world_state.get("npc_states") or {}
    assert len(npc_states) == NPC_STATES_MAX
    assert "npc-new" in npc_states
    assert npc_states["npc-new"]["last_seen_turn"] == 100
    assert "npc-2" in npc_states
    assert npc_states["npc-2"]["last_seen_turn"] == 100
    # Old, stale NPCs should be evicted once capped.
    assert "npc-1" not in npc_states


def test_touch_and_cap_falls_back_to_memory_turn_when_last_seen_missing() -> None:
    world_state = {
        "npc_states": {
            "npc-old": {"memories": ["Turn 2: Old encounter."]},
            "npc-mid": {"memories": ["Turn 8: Mid encounter."]},
            "npc-newer": {"memories": ["Turn 15: Recent encounter."]},
        }
    }

    # Force very small cap behavior by overfilling with low-recency NPCs.
    for i in range(40):
        world_state["npc_states"][f"filler-{i}"] = {"last_seen_turn": 1}

    _touch_and_cap_npc_states(world_state, present_npcs=[], turn_number=20)

    npc_states = world_state.get("npc_states") or {}
    assert "npc-newer" in npc_states
