from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.core.episodic_memory import EpisodicMemory
from backend.app.db.connection import get_connection
from backend.app.db.migrate import apply_schema


def test_phase3_migrations_add_tables_and_saga_columns() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    try:
        apply_schema(db_path)
        conn = get_connection(db_path)
        try:
            tables = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            assert "crystallized_memories" in tables
            assert "character_legacies" in tables
            assert "sagas" in tables

            columns = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(campaigns)").fetchall()
            }
            assert "saga_id" in columns
            assert "saga_chapter" in columns
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_episodic_memory_recall_includes_crystallized_memories() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    try:
        apply_schema(db_path)
        conn = get_connection(db_path)
        try:
            campaign_id = "camp-test"
            conn.execute(
                "INSERT INTO campaigns (id, title, time_period, world_state_json) VALUES (?, ?, ?, ?)",
                (campaign_id, "Test", "LOTF", "{}"),
            )
            epi = EpisodicMemory(conn, campaign_id)
            epi.store(
                turn_number=1,
                location_id="loc-marketplace",
                npcs_present=["Nora"],
                key_events=[{"event_type": "DISCOVERY", "payload": {"text": "Found a hidden map"}}],
                narrative_text="You found a hidden map in the market.",
            )
            epi.add_crystallized_memory(
                turn_number=2,
                memory_type="arc_climax",
                summary="Commander Thane betrayed the team during extraction.",
                full_text="Commander Thane betrayed the team during extraction, changing every alliance.",
                npcs_involved=["Commander Thane"],
                location="loc-docking-bay",
                emotional_tag="revelation",
            )
            recalled = epi.recall(
                query_text="thane betrayal extraction",
                current_turn=20,
                location_id="loc-docking-bay",
                npcs=["Commander Thane"],
                max_results=5,
            )
            assert recalled
            assert any(bool(item.get("is_crystallized")) for item in recalled)
            assert any(
                "thane" in str(item.get("narrative_summary", "")).lower()
                for item in recalled
            )
        finally:
            conn.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_complete_campaign_creates_character_legacy_and_saga_links() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    apply_schema(db_path)
    patcher = patch("backend.app.api.v2_campaigns.DEFAULT_DB_PATH", db_path)
    patcher.start()
    try:
        from backend.main import app

        client = TestClient(app)
        prof = client.post("/v2/player/profiles", json={"display_name": "Legacy Tester"})
        assert prof.status_code == 200, prof.text
        player_profile_id = prof.json()["id"]

        saga = client.post(
            "/v2/sagas",
            json={"player_id": player_profile_id, "universe_id": "star_wars_legends", "title": "Legacy Saga"},
        )
        assert saga.status_code == 200, saga.text
        saga_id = saga.json()["saga_id"]

        setup = client.post(
            "/v2/setup/auto",
            json={
                "time_period": "LOTF",
                "themes": ["legacy"],
                "player_concept": "A veteran searching for closure",
                "player_profile_id": player_profile_id,
                "saga_id": saga_id,
            },
        )
        assert setup.status_code == 200, setup.text
        campaign_id = setup.json()["campaign_id"]

        complete = client.post(
            f"/v2/campaigns/{campaign_id}/complete",
            json={"outcome_summary": "The war ended with uneasy peace.", "character_fate": "Alive"},
        )
        assert complete.status_code == 200, complete.text
        payload = complete.json()
        assert payload.get("character_legacy")
        assert payload.get("character_legacy_id") is not None
        assert payload.get("player_profile_id") == player_profile_id
        assert payload.get("saga_id") == saga_id

        conn = get_connection(db_path)
        try:
            leg = conn.execute(
                "SELECT id FROM character_legacies WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            assert leg is not None
        finally:
            conn.close()

        sagas = client.get(f"/v2/player/{player_profile_id}/sagas")
        assert sagas.status_code == 200, sagas.text
        assert any(s["saga_id"] == saga_id for s in sagas.json().get("sagas", []))

        saga_detail = client.get(f"/v2/sagas/{saga_id}")
        assert saga_detail.status_code == 200, saga_detail.text
        campaigns = saga_detail.json().get("campaigns", [])
        assert len(campaigns) >= 1
        assert campaigns[0].get("campaign_id") == campaign_id
    finally:
        patcher.stop()
        if os.path.exists(db_path):
            os.unlink(db_path)
