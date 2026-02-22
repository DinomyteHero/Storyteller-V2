"""Turn idempotency and per-campaign concurrency guard tests."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.db.migrate import apply_schema
from backend.app.models.state import ActionSuggestion


class _DenyLock:
    def __enter__(self):
        raise HTTPException(
            status_code=409,
            detail="A turn is already in progress for this campaign. Retry after it finishes.",
        )

    def __exit__(self, exc_type, exc, tb):
        return False


class TestTurnIdempotency(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)
        self.patcher = patch("backend.app.api.v2_campaigns.DEFAULT_DB_PATH", self.db_path)
        self.patcher.start()
        self.patcher_turn = patch("backend.app.api.v2_turn.DEFAULT_DB_PATH", self.db_path)
        self.patcher_turn.start()
        self.run_turn_calls = 0

        def _fake_run_turn(_conn, state):
            self.run_turn_calls += 1
            state.final_text = f"Mock turn output #{self.run_turn_calls}"
            state.suggested_actions = [
                ActionSuggestion(
                    label="Observe",
                    intent_text="Observe the area.",
                    category="SOCIAL",
                    risk_level="SAFE",
                    strategy_tag="SCOUT",
                    tone_tag="INVESTIGATE",
                    intent_style="careful",
                    consequence_hint="You gather clues.",
                    companion_reactions={},
                    risk_factors=[],
                ),
                ActionSuggestion(
                    label="Advance",
                    intent_text="Advance toward the objective.",
                    category="COMMIT",
                    risk_level="RISKY",
                    strategy_tag="PUSH",
                    tone_tag="PARAGON",
                    intent_style="bold",
                    consequence_hint="You may trigger resistance.",
                    companion_reactions={},
                    risk_factors=[],
                ),
            ]
            state.warnings = []
            state.mechanic_result = None
            return state

        self.run_turn_patcher = patch("backend.app.api.v2_turn.run_turn", side_effect=_fake_run_turn)
        self.run_turn_patcher.start()

        self.bio_patcher = patch(
            "backend.app.api.v2_campaigns.BiographerAgent.build",
            return_value={
                "name": "Test Hero",
                "stats": {"brawn": 1, "agility": 1, "intellect": 1, "cunning": 1, "willpower": 1, "presence": 1},
                "hp_current": 10,
                "starting_location": "loc-cantina",
                "starting_planet": "coruscant",
                "background": "A determined drifter.",
            },
        )
        self.bio_patcher.start()
        self.bible_patcher = patch(
            "backend.app.api.v2_campaigns.CampaignBibleAgent.build",
            return_value={
                "campaign_title": "Smoke Test Campaign",
                "active_factions": [],
                "quest_arcs": [],
                "campaign_theme": "adventure",
                "opening_crawl": "A new story begins.",
                "locations": [],
            },
        )
        self.bible_patcher.start()
        from backend.main import app

        self.client = TestClient(app)
        setup = self.client.post(
            "/v2/setup/auto",
            json={"time_period": "LOTF", "themes": [], "player_concept": "Hero"},
        )
        self.assertEqual(setup.status_code, 200, setup.text)
        payload = setup.json()
        self.campaign_id = payload["campaign_id"]
        self.player_id = payload["player_id"]

    def tearDown(self):
        self.bible_patcher.stop()
        self.bio_patcher.stop()
        self.run_turn_patcher.stop()
        self.patcher_turn.stop()
        self.patcher.stop()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_same_idempotency_key_replays_deterministically(self):
        key = "idem-turn-1"
        first = self.client.post(
            f"/v2/campaigns/{self.campaign_id}/turn",
            params={"player_id": self.player_id},
            headers={"Idempotency-Key": key},
            json={"user_input": "Look around"},
        )
        self.assertEqual(first.status_code, 200, first.text)

        second = self.client.post(
            f"/v2/campaigns/{self.campaign_id}/turn",
            params={"player_id": self.player_id},
            headers={"Idempotency-Key": key},
            json={"user_input": "Look around"},
        )
        self.assertEqual(second.status_code, 200, second.text)

        first_payload = first.json()
        second_payload = second.json()
        self.assertEqual(
            first_payload.get("turn_contract", {}).get("turn_id"),
            second_payload.get("turn_contract", {}).get("turn_id"),
        )
        self.assertEqual(first_payload.get("narrated_text"), second_payload.get("narrated_text"))
        self.assertEqual(self.run_turn_calls, 1)

    def test_idempotency_key_conflict_on_different_payload(self):
        key = "idem-turn-conflict"
        first = self.client.post(
            f"/v2/campaigns/{self.campaign_id}/turn",
            params={"player_id": self.player_id},
            headers={"Idempotency-Key": key},
            json={"user_input": "Look around"},
        )
        self.assertEqual(first.status_code, 200, first.text)

        second = self.client.post(
            f"/v2/campaigns/{self.campaign_id}/turn",
            params={"player_id": self.player_id},
            headers={"Idempotency-Key": key},
            json={"user_input": "Attack immediately"},
        )
        self.assertEqual(second.status_code, 409, second.text)
        self.assertIn("different request payload", second.text)

    def test_parallel_turn_guard_rejects_when_campaign_busy(self):
        with patch("backend.app.api.v2_turn._campaign_turn_lock", return_value=_DenyLock()):
            resp = self.client.post(
                f"/v2/campaigns/{self.campaign_id}/turn",
                params={"player_id": self.player_id},
                json={"user_input": "Look around"},
            )
        self.assertEqual(resp.status_code, 409, resp.text)
