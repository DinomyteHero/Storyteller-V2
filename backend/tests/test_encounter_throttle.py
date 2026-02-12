"""Tests for NPC introduction throttling: early game cap, location change, rumor triggers."""
import json
import os
import tempfile
from unittest.mock import patch

import pytest

from backend.app.db.migrate import apply_schema
from backend.app.db.connection import get_connection
from backend.app.core.state_loader import build_initial_gamestate
from backend.app.core.graph import run_turn
from backend.app.core.encounter_throttle import (
    can_introduce_new_npc,
    load_world_state,
    get_effective_location,
    EARLY_GAME_NPC_CAP,
)
from backend.app.models.state import MechanicOutput, ActionSuggestion
from backend.app.models.narration import NarrationOutput


@pytest.fixture
def throttle_db():
    """Campaign with player at loc-tavern, NO NPCs at loc-tavern (so spawn_request can fire)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    apply_schema(db_path)
    conn = get_connection(db_path)
    campaign_id = "throttle-test-campaign"
    player_id = "throttle-test-player"
    conn.execute(
        """INSERT INTO campaigns (id, title, time_period, world_state_json, world_time_minutes)
           VALUES (?, ?, ?, ?, ?)""",
        (campaign_id, "Throttle Test", "LOTF", "{}", 0),
    )
    conn.execute(
        """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, psych_profile)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (player_id, campaign_id, "Hero", "Player", "loc-tavern", "{}", 10, None, None, 0, "{}"),
    )
    conn.execute(
        """INSERT INTO turn_events (campaign_id, turn_number, event_type, payload_json, is_hidden, is_public_rumor)
           VALUES (?, 0, 'FLAG_SET', '{"key":"campaign_started","value":true}', 1, 0)""",
        (campaign_id,),
    )
    conn.commit()
    yield db_path, conn, campaign_id, player_id
    conn.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


def _always_spawn_request(campaign_id, location_id, state=None, **_kw):
    """Mock: always return spawn_request when location has no NPCs."""
    return [], [], {"campaign_id": campaign_id, "location_id": location_id}, [], []


def _never_spawn_request(campaign_id, location_id, state=None, **_kw):
    """Mock: never spawn (return empty NPCs, no request)."""
    return [], [], None, [], []


def test_early_game_repeated_turns_no_new_named_npcs_after_cap(throttle_db):
    """Early game: repeated turns in same location without triggers => no new named NPCs after cap."""
    db_path, conn, campaign_id, player_id = throttle_db

    with patch("backend.app.api.v2_campaigns.DEFAULT_DB_PATH", db_path):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

    # Force spawn_request when location empty; use IDLE with 5 min so we stay under 60
    with patch("backend.app.core.nodes.encounter.EncounterManager") as MockEnc:
        MockEnc.return_value.check.side_effect = _always_spawn_request

        # Run turns until we hit cap (3) then one more
        introduced_ids = []
        for i in range(5):
            state = build_initial_gamestate(conn, campaign_id, player_id)
            state.user_input = "Look around"
            with patch("backend.app.core.nodes.mechanic.MechanicAgent") as MockMech:
                MockMech.return_value.resolve.return_value = MechanicOutput(
                    action_type="IDLE", time_cost_minutes=5, events=[], narrative_facts=[]
                )
                with patch("backend.app.core.nodes.director.DirectorAgent") as MockDir:
                    MockDir.return_value.plan.return_value = (
                        "Keep pacing.",
                        [ActionSuggestion(label="Look", intent_text="Look around", category="EXPLORE", risk_level="SAFE", strategy_tag="OPTIMAL")] * 3,
                    )
                    with patch("backend.app.core.nodes.narrator.NarratorAgent") as MockNar:
                        MockNar.return_value.generate.return_value = NarrationOutput(
                            text="You look around.", citations=[]
                        )
                        with patch("backend.app.core.nodes.encounter.CastingAgent") as MockCast:
                            def capture_spawn(*a, **kw):
                                payload = {"character_id": f"npc-{i}", "name": f"NPC{i}", "role": "Stranger",
                                           "location_id": "loc-tavern", "relationship_score": 0,
                                           "secret_agenda": None, "stats_json": {}, "hp_current": 10}
                                return payload
                            MockCast.return_value.spawn.side_effect = capture_spawn
                            run_turn(conn, state)

            ws = load_world_state(conn, campaign_id)
            introduced_ids = ws.get("introduced_npcs") or []

        # After 5 turns with always-spawn, we should have capped at 3 (throttle kicks in for turns 4 and 5)
        assert len(introduced_ids) <= EARLY_GAME_NPC_CAP, (
            f"Should cap at {EARLY_GAME_NPC_CAP} in early game, got {len(introduced_ids)}"
        )


def test_location_change_allows_new_npc_introduction(throttle_db):
    """Location change => can introduce one new NPC even at cap."""
    db_path, conn, campaign_id, player_id = throttle_db

    # Pre-seed: 3 already introduced, same location, early game
    ws = {"introduced_npcs": ["npc-a", "npc-b", "npc-c"], "introduction_log": [], "last_location_id": "loc-tavern"}
    conn.execute(
        "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
        (json.dumps(ws), campaign_id),
    )
    conn.commit()

    state_dict = {
        "campaign_id": campaign_id,
        "player_id": player_id,
        "turn_number": 1,
        "current_location": "loc-tavern",
        "campaign": {"world_time_minutes": 10},
        "mechanic_result": {
            "events": [{"event_type": "MOVE", "payload": {"to_location": "loc-market"}}],
            "time_cost_minutes": 30,
        },
    }
    allowed, reason = can_introduce_new_npc(conn, campaign_id, state_dict)
    assert allowed is True, f"Location change should allow intro, got reason={reason}"
    assert reason == "location_changed"


def test_rumor_trigger_allows_npc_introduction(throttle_db):
    """Rumor trigger referencing NPC => may introduce even without location change."""
    db_path, conn, campaign_id, player_id = throttle_db

    ws = {
        "introduced_npcs": ["npc-a", "npc-b", "npc-c"],
        "introduction_log": [],
        "last_location_id": "loc-tavern",
        "npc_introduction_triggers": [{"npc_name": "Captain Vex", "reason": "rumor"}],
    }
    conn.execute(
        "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
        (json.dumps(ws), campaign_id),
    )
    conn.commit()

    state_dict = {
        "campaign_id": campaign_id,
        "player_id": player_id,
        "current_location": "loc-tavern",
        "campaign": {"world_time_minutes": 10},
        "mechanic_result": {"events": [], "time_cost_minutes": 5},
    }
    allowed, reason = can_introduce_new_npc(conn, campaign_id, state_dict)
    assert allowed is True, f"Rumor trigger should allow intro, got reason={reason}"
    assert reason == "rumor_quest_trigger"


def test_effective_location_from_move_event():
    """get_effective_location uses MOVE to_location when present."""
    state = {
        "current_location": "loc-tavern",
        "mechanic_result": {
            "events": [{"event_type": "MOVE", "payload": {"to_location": "loc-market"}}],
        },
    }
    assert get_effective_location(state) == "loc-market"


def test_throttled_same_location_at_cap(throttle_db):
    """At cap, same location, no trigger => not allowed."""
    db_path, conn, campaign_id, player_id = throttle_db

    ws = {
        "introduced_npcs": ["npc-a", "npc-b", "npc-c"],
        "last_location_id": "loc-tavern",
    }
    conn.execute(
        "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
        (json.dumps(ws), campaign_id),
    )
    conn.commit()

    state_dict = {
        "campaign_id": campaign_id,
        "current_location": "loc-tavern",
        "campaign": {"world_time_minutes": 20},
        "mechanic_result": {"events": [], "time_cost_minutes": 5},
    }
    allowed, reason = can_introduce_new_npc(conn, campaign_id, state_dict)
    assert allowed is False
    assert "throttled" in reason.lower()
