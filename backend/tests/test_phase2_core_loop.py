from __future__ import annotations

import json
import sqlite3

from backend.app.core.episodic_memory import generate_story_summary
from backend.app.core.nodes.scene_frame import scene_frame_node


def test_scene_frame_sets_climax_weight_and_pre_context() -> None:
    state = {
        "campaign_id": "camp-1",
        "player_id": "player-1",
        "current_location": "loc-market",
        "user_input": "I charge the barricade.",
        "action_class": "PHYSICAL_ACTION",
        "mechanic_result": {
            "action_type": "ATTACK",
            "outcome_summary": "You break the first line.",
            "events": [{"event_type": "DAMAGE", "payload": {"amount": 3}}],
        },
        "arc_guidance": {"arc_stage": "RISING", "active_themes": [], "tension_level": "HIGH"},
        "campaign": {
            "world_state_json": {
                "current_beat": "ORDEAL",
                "faction_reputation": {},
                "npc_states": {},
            }
        },
        "present_npcs": [{"id": "npc-varo", "name": "Captain Varo", "role": "officer"}],
    }

    result = scene_frame_node(state)

    assert result["scene_weight"] == "CLIMAX"
    pre_context = result.get("choice_crafter_pre_context") or {}
    assert pre_context.get("location") == "loc-market"
    assert pre_context.get("scene_frame")
    assert "Captain Varo" in " ".join(pre_context.get("npc_descriptions", []))


def test_generate_story_summary_uses_world_state_and_memories() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE episodic_memories (
            campaign_id TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            key_events_json TEXT,
            narrative_summary TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO episodic_memories (campaign_id, turn_number, key_events_json, narrative_summary) VALUES (?, ?, ?, ?)",
        ("camp-1", 3, json.dumps([{"event_type": "REVELATION", "payload": {"text": "You uncovered the smuggling route."}}]), "You uncovered the smuggling route."),
    )
    conn.execute(
        "INSERT INTO episodic_memories (campaign_id, turn_number, key_events_json, narrative_summary) VALUES (?, ?, ?, ?)",
        ("camp-1", 2, json.dumps([{"event_type": "DIALOGUE", "payload": {"description": "You negotiated a truce at the docks."}}]), ""),
    )

    world_state = {
        "arc_stage": "RISING",
        "current_beat": "TESTS_ALLIES_ENEMIES",
        "narrative_ledger": {"open_threads": ["The missing cargo", "The informant's debt"]},
        "quest_log": {"active": [{"title": "Find the stolen plans"}, {"title": "Earn faction trust"}]},
    }

    summary = generate_story_summary(conn, "camp-1", world_state)

    assert summary["arc_stage"] == "RISING"
    assert "The missing cargo" in summary["open_threads"]
    assert "Find the stolen plans" in summary["active_quests"]
    assert len(summary["recent_memories"]) >= 1
