"""Projection regression tests for event-to-read-model consistency."""
import json
import os
import tempfile

import pytest

from backend.app.core.projections import apply_projection
from backend.app.db.connection import get_connection
from backend.app.db.migrate import apply_schema
from backend.app.models.events import Event


@pytest.fixture
def projection_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    apply_schema(db_path)
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO campaigns (id, title, time_period, world_state_json, world_time_minutes)
           VALUES (?, ?, ?, ?, ?)""",
        ("c1", "Projection Test", "LOTF", "{}", 0),
    )
    conn.execute(
        """INSERT INTO characters
           (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, psych_profile)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("p1", "c1", "Player", "Player", "loc-tavern", "{}", 10, None, None, 0, '{"current_mood":"neutral","stress_level":3}'),
    )
    conn.execute(
        """INSERT INTO characters
           (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, psych_profile)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("n1", "c1", "Hostile NPC", "NPC", "loc-tavern", "{}", 10, -80, None, 0, "{}"),
    )
    conn.commit()
    yield conn
    conn.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_npc_depart_projection_clears_location(projection_db):
    conn = projection_db
    apply_projection(
        conn,
        "c1",
        [Event(event_type="NPC_DEPART", payload={"character_id": "n1"})],
        commit=True,
    )
    row = conn.execute(
        "SELECT location_id FROM characters WHERE id = ? AND campaign_id = ?",
        ("n1", "c1"),
    ).fetchone()
    assert row is not None
    assert row[0] is None


def test_player_psych_projection_updates_character_and_world_state_mirror(projection_db):
    conn = projection_db
    apply_projection(
        conn,
        "c1",
        [Event(event_type="PLAYER_PSYCH_UPDATE", payload={"character_id": "p1", "stress_delta": 6})],
        commit=True,
    )
    char_row = conn.execute(
        "SELECT psych_profile FROM characters WHERE id = ? AND campaign_id = ?",
        ("p1", "c1"),
    ).fetchone()
    assert char_row is not None
    psych = json.loads(char_row[0]) if isinstance(char_row[0], str) else (char_row[0] or {})
    assert psych.get("stress_level") == 9
    assert psych.get("current_mood") == "distressed"

    camp_row = conn.execute(
        "SELECT world_state_json FROM campaigns WHERE id = ?",
        ("c1",),
    ).fetchone()
    assert camp_row is not None
    world_state = json.loads(camp_row[0]) if isinstance(camp_row[0], str) else (camp_row[0] or {})
    mirrored = world_state.get("psych_profile") or {}
    assert mirrored.get("stress_level") == 9


def test_world_time_advance_projection_supports_add_and_set_modes(projection_db):
    conn = projection_db
    apply_projection(
        conn,
        "c1",
        [
            Event(event_type="WORLD_TIME_ADVANCE", payload={"mode": "add", "minutes": 90}),
            Event(event_type="WORLD_TIME_ADVANCE", payload={"mode": "set", "world_time_minutes": 25}),
        ],
        commit=True,
    )
    row = conn.execute(
        "SELECT world_time_minutes FROM campaigns WHERE id = ?",
        ("c1",),
    ).fetchone()
    assert row is not None
    assert int(row[0] or 0) == 25
