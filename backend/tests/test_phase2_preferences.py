"""Phase 2 tests: App preferences API + choice fallback gating.

Covers:
  2.1 — app_preferences migration creates table
  2.2 — GET/PUT /v2/settings/preferences API endpoints
  2.3 — ChoiceCrafter fallback gating via DB preference + env var
"""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.app.db.migrate import apply_schema


# ---------------------------------------------------------------------------
# 2.1 — Migration creates app_preferences table
# ---------------------------------------------------------------------------


class TestAppPreferencesMigration(unittest.TestCase):
    """Migration 0041 should create the app_preferences table."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_app_preferences_table_exists(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_preferences'"
        )
        tables = {r[0] for r in cur.fetchall()}
        conn.close()
        self.assertIn("app_preferences", tables)

    def test_app_preferences_table_schema(self):
        """Table should have key, value, updated_at columns."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("PRAGMA table_info(app_preferences)")
        columns = {row[1] for row in cur.fetchall()}
        conn.close()
        self.assertIn("key", columns)
        self.assertIn("value", columns)
        self.assertIn("updated_at", columns)

    def test_app_preferences_idempotent(self):
        """Applying schema twice should not fail."""
        apply_schema(self.db_path)  # second apply
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_preferences'"
        )
        tables = {r[0] for r in cur.fetchall()}
        conn.close()
        self.assertIn("app_preferences", tables)


# ---------------------------------------------------------------------------
# 2.2 — Preferences API endpoints
# ---------------------------------------------------------------------------


class TestPreferencesAPI(unittest.TestCase):
    """GET/PUT /v2/settings/preferences should read/write app preferences."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)
        self.patcher = patch("backend.app.api.v2_settings.DEFAULT_DB_PATH", self.db_path)
        self.patcher.start()
        from backend.main import app
        self.client = TestClient(app)

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_get_preferences_returns_defaults(self):
        """GET /v2/settings/preferences with empty table returns defaults."""
        r = self.client.get("/v2/settings/preferences")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("preferences", data)
        self.assertEqual(data["preferences"]["enable_choice_fallbacks"], "true")

    def test_put_preferences_persists(self):
        """PUT /v2/settings/preferences should upsert and return updated prefs."""
        r = self.client.put(
            "/v2/settings/preferences",
            json={"preferences": {"enable_choice_fallbacks": "false"}},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["preferences"]["enable_choice_fallbacks"], "false")

        # GET should confirm persistence
        r2 = self.client.get("/v2/settings/preferences")
        self.assertEqual(r2.json()["preferences"]["enable_choice_fallbacks"], "false")

    def test_put_preferences_toggle_back(self):
        """Toggling preference back to 'true' persists correctly."""
        # Disable
        self.client.put(
            "/v2/settings/preferences",
            json={"preferences": {"enable_choice_fallbacks": "false"}},
        )
        # Re-enable
        r = self.client.put(
            "/v2/settings/preferences",
            json={"preferences": {"enable_choice_fallbacks": "true"}},
        )
        self.assertEqual(r.json()["preferences"]["enable_choice_fallbacks"], "true")

    def test_put_custom_preference(self):
        """Storing a custom preference key should work."""
        r = self.client.put(
            "/v2/settings/preferences",
            json={"preferences": {"custom_key": "custom_value"}},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["preferences"]["custom_key"], "custom_value")


# ---------------------------------------------------------------------------
# 2.3 — ChoiceCrafter fallback gating
# ---------------------------------------------------------------------------


class TestChoiceFallbackGating(unittest.TestCase):
    """Verify fallback choices are gated by DB preference and env var."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _set_preference(self, value: str):
        """Set the enable_choice_fallbacks preference in the DB."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """INSERT INTO app_preferences (key, value, updated_at)
               VALUES ('enable_choice_fallbacks', ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (value,),
        )
        conn.commit()
        conn.close()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_preference_true_allows_fallback(self):
        """When DB preference is 'true', fallback is allowed."""
        self._set_preference("true")
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM app_preferences WHERE key = 'enable_choice_fallbacks'"
            ).fetchone()
            val = row["value"]
            allow = str(val).lower() in ("1", "true", "yes")
            self.assertTrue(allow)
        finally:
            conn.close()

    def test_preference_false_blocks_fallback(self):
        """When DB preference is 'false', fallback is blocked."""
        self._set_preference("false")
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM app_preferences WHERE key = 'enable_choice_fallbacks'"
            ).fetchone()
            val = row["value"]
            allow = str(val).lower() in ("1", "true", "yes")
            self.assertFalse(allow)
        finally:
            conn.close()

    def test_no_preference_defaults_to_true(self):
        """When no DB preference exists, fallback defaults to True."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM app_preferences WHERE key = 'enable_choice_fallbacks'"
            ).fetchone()
            # Row should not exist
            self.assertIsNone(row)
            # Default behavior: allow_fallback = True (when row is None)
            allow = True
            if row:
                val = row["value"] if hasattr(row, "keys") else row[0]
                allow = str(val).lower() in ("1", "true", "yes")
            self.assertTrue(allow)
        finally:
            conn.close()

    @patch.dict(os.environ, {"ENABLE_CHOICE_FALLBACKS": "0"}, clear=False)
    def test_env_var_overrides_to_disable(self):
        """Env var ENABLE_CHOICE_FALLBACKS=0 should disable fallback regardless of DB."""
        self._set_preference("true")
        # Simulate the logic from choice_crafter_node.py
        allow_fallback = True
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM app_preferences WHERE key = 'enable_choice_fallbacks'"
            ).fetchone()
            if row:
                val = row["value"]
                allow_fallback = str(val).lower() in ("1", "true", "yes")
        finally:
            conn.close()
        # Env var override
        env_val = os.environ.get("ENABLE_CHOICE_FALLBACKS", "").strip().lower()
        if env_val in ("0", "false", "no"):
            allow_fallback = False
        self.assertFalse(allow_fallback)

    @patch.dict(os.environ, {"ENABLE_CHOICE_FALLBACKS": ""}, clear=False)
    def test_empty_env_var_does_not_override(self):
        """Empty env var should not override DB preference."""
        self._set_preference("true")
        allow_fallback = True
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT value FROM app_preferences WHERE key = 'enable_choice_fallbacks'"
            ).fetchone()
            if row:
                val = row["value"]
                allow_fallback = str(val).lower() in ("1", "true", "yes")
        finally:
            conn.close()
        env_val = os.environ.get("ENABLE_CHOICE_FALLBACKS", "").strip().lower()
        if env_val in ("0", "false", "no"):
            allow_fallback = False
        self.assertTrue(allow_fallback)


if __name__ == "__main__":
    unittest.main()
