"""V2 campaign API tests: setup/auto, one turn (TURN marker, events, projections, narrator references mechanic)."""
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.constants import SUGGESTED_ACTIONS_TARGET
from backend.app.db.migrate import apply_schema
from backend.app.db.connection import get_connection
from backend.app.core.event_store import get_events, get_current_turn_number
from backend.app.core.state_loader import load_campaign


class TestV2SetupAuto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)
        self.patcher = patch("backend.app.api.v2_campaigns.DEFAULT_DB_PATH", self.db_path)
        self.patcher.start()
        from backend.main import app
        self.client = TestClient(app)

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_setup_auto_returns_campaign_and_player(self):
        r = self.client.post(
            "/v2/setup/auto",
            json={
                "time_period": "LOTF",
                "themes": ["space", "adventure"],
                "player_concept": "A pilot",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("campaign_id", data)
        self.assertIn("player_id", data)
        self.assertIn("skeleton", data)
        self.assertIn("character_sheet", data)
        self.assertTrue(len(data["campaign_id"]) > 0)
        self.assertTrue(len(data["player_id"]) > 0)

    def test_setup_auto_seeds_companion_state(self):
        """Campaign creation seeds party, alignment, faction_reputation in world_state_json."""
        r = self.client.post(
            "/v2/setup/auto",
            json={"time_period": "LOTF", "themes": [], "player_concept": "Hero"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        campaign_id = r.json()["campaign_id"]
        conn = get_connection(self.db_path)
        try:
            camp = load_campaign(conn, campaign_id)
            self.assertIsNotNone(camp)
            self.assertIn("party", camp)
            self.assertIn("party_affinity", camp)
            self.assertIn("alignment", camp)
            self.assertIn("faction_reputation", camp)
            self.assertIn("story_position", camp["world_state_json"])
            self.assertIsInstance(camp["party"], list)
            self.assertIsInstance(camp["party_affinity"], dict)
            self.assertIsInstance(camp["alignment"], dict)
            self.assertIsInstance(camp["world_state_json"]["story_position"], dict)
            self.assertTrue(camp["world_state_json"]["story_position"].get("canonical_year_label"))
            self.assertEqual(camp["alignment"].get("light_dark"), 0)
            self.assertEqual(camp["alignment"].get("paragon_renegade"), 0)
            # Party starts EMPTY — companions are recruited organically through gameplay
            self.assertEqual(len(camp["party"]), 0, "Party should start empty for organic recruitment")
        finally:
            conn.close()


class TestV2OneTurn(unittest.TestCase):
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

    def test_one_turn_writes_events_and_turn_marker(self):
        r = self.client.post(
            f"/v2/campaigns/{self.campaign_id}/turn",
            params={"player_id": self.player_id},
            json={"user_input": "Look around"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("narrated_text", data)
        self.assertIn("suggested_actions", data)
        self.assertIn("warnings", data)
        self.assertIn("canonical_year_label", data)
        self.assertTrue(data.get("canonical_year_label"))
        self.assertIsInstance(data["warnings"], list)
        actions = data["suggested_actions"]
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET, "suggested_actions padded to UI target")
        categories = {a.get("category") for a in actions if a.get("category")}
        self.assertTrue(len(categories) >= 2, "must include diverse action categories")

        conn = get_connection(self.db_path)
        try:
            events = get_events(conn, self.campaign_id, since_turn=0, include_hidden=True)
            turn_events = [e for e in events if e.get("event_type") == "TURN"]
            self.assertGreaterEqual(len(turn_events), 1, "TURN marker event should exist")
            current = get_current_turn_number(conn, self.campaign_id)
            self.assertGreaterEqual(current, 1)
        finally:
            conn.close()

    def test_narrator_response_present(self):
        r = self.client.post(
            f"/v2/campaigns/{self.campaign_id}/turn",
            params={"player_id": self.player_id},
            json={"user_input": "Go to loc-market"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        narrated = r.json().get("narrated_text", "")
        self.assertTrue(isinstance(narrated, str), "narrated_text should be string")
        self.assertGreater(len(narrated.strip()), 0, "narrated text should be non-empty")

    def test_turn_without_state_returns_ui_contract_only(self):
        """Turn with include_state=false (default) must return all UI fields and state=null."""
        r = self.client.post(
            f"/v2/campaigns/{self.campaign_id}/turn",
            params={"player_id": self.player_id},
            json={"user_input": "Look around", "include_state": False},
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("narrated_text", data)
        self.assertIn("suggested_actions", data)
        self.assertIn("player_sheet", data)
        self.assertIn("inventory", data)
        self.assertIn("quest_log", data)
        self.assertIn("warnings", data)
        self.assertIsInstance(data["warnings"], list)
        self.assertEqual(len(data["suggested_actions"]), SUGGESTED_ACTIONS_TARGET, "suggested_actions padded to UI target")
        self.assertIsNone(data.get("state"), "state should be null when include_state=false")
        self.assertIsNone(data.get("debug"), "debug should be null when debug=false")
        self.assertTrue(isinstance(data["player_sheet"], dict))
        self.assertTrue(isinstance(data["quest_log"], dict))

    def test_turn_may_include_party_status_and_alignment(self):
        """Turn response may include optional party_status, alignment, faction_reputation when companions exist."""
        r = self.client.post(
            f"/v2/campaigns/{self.campaign_id}/turn",
            params={"player_id": self.player_id},
            json={"user_input": "Look around"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        # Optional fields: may be null or present (UI renders if present)
        if data.get("party_status") is not None:
            self.assertIsInstance(data["party_status"], list)
            for item in data["party_status"]:
                self.assertIn("id", item)
                self.assertIn("name", item)
                self.assertIn("affinity", item)
                self.assertIn("loyalty_progress", item)
        if data.get("alignment") is not None:
            self.assertIn("light_dark", data["alignment"])
            self.assertIn("paragon_renegade", data["alignment"])


    def test_turn_contract_has_coherent_choices_and_objectives(self):
        r = self.client.post(
            f"/v2/campaigns/{self.campaign_id}/turn",
            params={"player_id": self.player_id},
            json={"user_input": "Look around"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        tc = data.get("turn_contract") or {}
        self.assertTrue(tc)
        choices = tc.get("choices") or []
        self.assertGreaterEqual(len(choices), 2)
        self.assertLessEqual(len(choices), 4)
        labels = [c.get("label", "") for c in choices]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertTrue(all(len(lbl) <= 80 for lbl in labels))
        intents = [((c.get("intent") or {}).get("intent_type")) for c in choices]
        self.assertGreaterEqual(len(set(intents)), 2)
        risks = {c.get("risk") for c in choices}
        self.assertIn("low", risks)
        self.assertTrue(bool({"med", "high"}.intersection(risks)))
        meta = tc.get("meta") or {}
        self.assertTrue(meta.get("active_objectives"), "active objectives must be present")

    def test_stream_done_event_includes_turn_contract(self):
        with self.client.stream(
            "POST",
            f"/v2/campaigns/{self.campaign_id}/turn_stream",
            params={"player_id": self.player_id},
            json={"user_input": "Look around"},
        ) as resp:
            self.assertEqual(resp.status_code, 200)
            done = None
            for line in resp.iter_lines():
                if not line:
                    continue
                txt = line.decode() if isinstance(line, bytes) else line
                if txt.startswith("data: "):
                    payload = __import__("json").loads(txt[6:])
                    if payload.get("type") == "done":
                        done = payload
                        break
            self.assertIsNotNone(done, "stream must emit done event")
            self.assertIn("turn_contract", done)
            self.assertIn("canonical_year_label", done)
            self.assertIsInstance(done["turn_contract"], dict)

    def test_validation_failures_endpoint_exists(self):
        r = self.client.get(f"/v2/campaigns/{self.campaign_id}/validation_failures")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("validation_failures", body)
        self.assertIsInstance(body["validation_failures"], list)
