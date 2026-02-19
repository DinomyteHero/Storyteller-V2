"""API smoke test: create -> play -> resume -> complete."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.db.migrate import apply_schema


def test_api_smoke_create_play_resume_complete() -> None:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    apply_schema(db_path)

    patcher = patch("backend.app.api.v2_campaigns.DEFAULT_DB_PATH", db_path)
    patcher.start()
    try:
        from backend.main import app

        client = TestClient(app)

        profile = client.post(
            "/v2/player/profiles",
            json={"display_name": "Smoke Tester"},
        )
        assert profile.status_code == 200, profile.text
        profile_id = profile.json()["id"]

        setup = client.post(
            "/v2/setup/auto",
            json={
                "time_period": "LOTF",
                "themes": ["adventure"],
                "player_concept": "A resourceful pilot",
                "player_profile_id": profile_id,
            },
        )
        assert setup.status_code == 200, setup.text
        campaign_id = setup.json()["campaign_id"]
        player_id = setup.json()["player_id"]

        turn = client.post(
            f"/v2/campaigns/{campaign_id}/turn",
            params={"player_id": player_id},
            json={"user_input": "Look around and assess the situation"},
        )
        assert turn.status_code == 200, turn.text
        turn_payload = turn.json()
        assert isinstance(turn_payload.get("narrated_text"), str)
        assert turn_payload.get("turn_contract")
        assert "warnings" in turn_payload

        state = client.get(
            f"/v2/campaigns/{campaign_id}/state",
            params={"player_id": player_id},
        )
        assert state.status_code == 200, state.text
        assert state.json().get("campaign", {}).get("id") == campaign_id

        campaigns = client.get("/v2/campaigns")
        assert campaigns.status_code == 200, campaigns.text
        items = campaigns.json().get("items", [])
        assert any(item.get("campaign_id") == campaign_id for item in items)

        transcript = client.get(f"/v2/campaigns/{campaign_id}/transcript")
        assert transcript.status_code == 200, transcript.text
        assert isinstance(transcript.json().get("turns"), list)

        complete = client.post(
            f"/v2/campaigns/{campaign_id}/complete",
            json={
                "outcome_summary": "Escaped with the intel.",
                "character_fate": "Alive",
            },
        )
        assert complete.status_code == 200, complete.text
        complete_payload = complete.json()
        assert complete_payload.get("status") == "completed"
        assert complete_payload.get("campaign_id") == campaign_id
        assert complete_payload.get("player_profile_id") == profile_id
    finally:
        patcher.stop()
        if os.path.exists(db_path):
            os.unlink(db_path)
