"""Tests for memory compression: compress_turn_history() and update_era_summaries() from ledger."""
from __future__ import annotations

import pytest

from backend.app.core.ledger import compress_turn_history, update_era_summaries
from backend.app.constants import (
    MEMORY_COMPRESSION_CHUNK_SIZE,
    MEMORY_ERA_SUMMARY_MAX_CHARS,
    MEMORY_MAX_ERA_SUMMARIES,
    MEMORY_RECENT_TURNS,
)


# ---------------------------------------------------------------------------
# compress_turn_history
# ---------------------------------------------------------------------------


def test_compress_turn_history_basic():
    """Events with MOVE, NPC_SPAWN, ITEM_GET, DAMAGE produce expected clauses."""
    events_by_turn = [
        [
            {"event_type": "MOVE", "payload": {"to_location": "Cantina"}},
            {"event_type": "NPC_SPAWN", "payload": {"name": "Jolee", "role": "Jedi"}},
        ],
        [
            {"event_type": "ITEM_GET", "payload": {"item_name": "Medpac", "quantity_delta": 2}},
            {"event_type": "DAMAGE", "payload": {"amount": 5}},
        ],
        [
            {"event_type": "DAMAGE", "payload": {"amount": 3}},
        ],
    ]
    summary = compress_turn_history(events_by_turn, (1, 10))

    assert summary.startswith("Turns 1-10:")
    assert "visited" in summary
    assert "met" in summary
    assert "acquired" in summary
    assert "took 8 total damage" in summary


def test_compress_turn_history_empty():
    """Empty events_by_turn produces 'uneventful' in the summary."""
    summary = compress_turn_history([], (1, 10))
    assert "uneventful" in summary


def test_compress_turn_history_max_chars():
    """Result length must not exceed MEMORY_ERA_SUMMARY_MAX_CHARS."""
    # Generate many events to produce a long summary
    events_by_turn = []
    for i in range(20):
        events_by_turn.append([
            {"event_type": "MOVE", "payload": {"to_location": f"Location_{i}_with_long_name_padding"}},
            {"event_type": "NPC_SPAWN", "payload": {"name": f"NPC_{i}_longname", "role": "guard"}},
            {"event_type": "ITEM_GET", "payload": {"item_name": f"Item_{i}_artifact_of_power"}},
        ])
    summary = compress_turn_history(events_by_turn, (1, 20))
    assert len(summary) <= MEMORY_ERA_SUMMARY_MAX_CHARS


# ---------------------------------------------------------------------------
# update_era_summaries
# ---------------------------------------------------------------------------


def test_update_era_summaries_no_compression_needed():
    """current_turn=5, empty events: no era summaries should be created."""
    world_state: dict = {}
    result = update_era_summaries(world_state, current_turn=5, all_events=[])
    assert result.get("era_summaries") == []


def test_update_era_summaries_triggers_compression():
    """current_turn=25 with events for turns 1-25 should produce 1 era summary (turns 1-10).

    MEMORY_RECENT_TURNS=10 means compressible_up_to = 25-10 = 15.
    CHUNK_SIZE=10, so one chunk [1..10] is fully within 15.
    """
    all_events = []
    for t in range(1, 26):
        all_events.append({
            "turn_number": t,
            "event_type": "MOVE",
            "payload": {"to_location": f"loc_{t}"},
        })

    world_state: dict = {}
    result = update_era_summaries(world_state, current_turn=25, all_events=all_events)
    era_summaries = result.get("era_summaries", [])

    # With chunk_size=10 and compressible_up_to=15, one full chunk [1..10] fits
    assert len(era_summaries) == 1
    assert "Turns 1-10:" in era_summaries[0]


def test_update_era_summaries_caps_at_max():
    """Pre-fill summaries near the cap and verify it does not exceed MEMORY_MAX_ERA_SUMMARIES."""
    world_state: dict = {
        "era_summaries": [f"Turns {i*10+1}-{(i+1)*10}: uneventful." for i in range(MEMORY_MAX_ERA_SUMMARIES)],
    }

    # Enough turns for one more chunk beyond the existing summaries
    last_compressed = MEMORY_MAX_ERA_SUMMARIES * MEMORY_COMPRESSION_CHUNK_SIZE
    current_turn = last_compressed + MEMORY_COMPRESSION_CHUNK_SIZE + MEMORY_RECENT_TURNS + 1
    all_events = []
    for t in range(last_compressed + 1, last_compressed + MEMORY_COMPRESSION_CHUNK_SIZE + 1):
        all_events.append({
            "turn_number": t,
            "event_type": "MOVE",
            "payload": {"to_location": f"loc_{t}"},
        })

    result = update_era_summaries(world_state, current_turn=current_turn, all_events=all_events)
    era_summaries = result.get("era_summaries", [])
    assert len(era_summaries) <= MEMORY_MAX_ERA_SUMMARIES


def test_backward_compat_missing_era_summaries():
    """world_state with no 'era_summaries' key should default to empty list."""
    world_state: dict = {"some_other_key": True}
    result = update_era_summaries(world_state, current_turn=5, all_events=[])
    assert result.get("era_summaries") == []
