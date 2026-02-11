"""Warnings surfaced in TurnResponse when LLM fails and fallback is used."""
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.db.migrate import apply_schema


class TestTurnWarnings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)
        self.patcher = patch("backend.app.api.v2_campaigns.DEFAULT_DB_PATH", self.db_path)
        self.patcher.start()
        from backend.main import app
        self.client = TestClient(app)
        r = self.client.post(
            "/v2/setup/auto",
            json={"time_period": "LOTF", "themes": [], "player_concept": "Hero"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.campaign_id = r.json()["campaign_id"]
        self.player_id = r.json()["player_id"]

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_turn_includes_warning_on_llm_failure(self):
        with patch("backend.app.core.agents.base.AgentLLM._get_client", side_effect=RuntimeError("LLM down")):
            r = self.client.post(
                f"/v2/campaigns/{self.campaign_id}/turn",
                params={"player_id": self.player_id},
                json={"user_input": "go to loc-market"},
            )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("warnings", data)
        self.assertIsInstance(data["warnings"], list)
        self.assertTrue(
            any("LLM error" in w for w in data["warnings"]),
            f"Expected LLM error warning, got: {data['warnings']}",
        )
