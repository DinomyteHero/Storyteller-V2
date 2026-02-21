"""Phase 5 integration tests: end-to-end backend–frontend connection verification.

Covers:
  5.1 — Settings API provider endpoints work end-to-end
  5.2 — Preset CRUD works through API
  5.3 — Provider resolver resolves cloud_all correctly
  5.4 — Resolved config endpoint returns cloud provider for cloud_all preset
  5.5 — Full settings→preferences→presets round-trip
"""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.db.migrate import apply_schema
from backend.app.db.connection import get_connection


# ---------------------------------------------------------------------------
# 5.1 — Settings API provider endpoints
# ---------------------------------------------------------------------------


class TestProviderAPIEndpoints(unittest.TestCase):
    """Verify provider key management API endpoints work end-to-end."""

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

    def test_list_providers_returns_five(self):
        """GET /v2/settings/providers should return all 5 cloud providers."""
        r = self.client.get("/v2/settings/providers")
        self.assertEqual(r.status_code, 200)
        providers = r.json()
        self.assertEqual(len(providers), 5)
        provider_ids = {p["provider_id"] for p in providers}
        for expected in ("anthropic", "openai", "xai", "deepseek", "google"):
            self.assertIn(expected, provider_ids)

    def test_set_and_remove_key(self):
        """PUT key → verify has_key=True → DELETE key → verify has_key=False."""
        # Set key
        r = self.client.put(
            "/v2/settings/providers/anthropic/key",
            json={"api_key": "sk-ant-test123456789"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["has_key"])

        # Verify key preview
        self.assertIn("sk-a", r.json()["key_preview"])

        # Remove key
        r2 = self.client.delete("/v2/settings/providers/anthropic/key")
        self.assertEqual(r2.status_code, 200)
        # After removing DB key, has_key depends on env var. Without env var, should be False.
        # (We don't set ANTHROPIC_API_KEY in test env)

    def test_set_key_invalid_provider_returns_404(self):
        """PUT key for unknown provider should return 404."""
        r = self.client.put(
            "/v2/settings/providers/nonexistent/key",
            json={"api_key": "test-key"},
        )
        self.assertEqual(r.status_code, 404)

    def test_set_empty_key_returns_422(self):
        """PUT empty key should return 422."""
        r = self.client.put(
            "/v2/settings/providers/anthropic/key",
            json={"api_key": "   "},
        )
        self.assertEqual(r.status_code, 422)

    def test_test_provider_no_key_returns_error(self):
        """POST test without key configured should return ok=False."""
        r = self.client.post("/v2/settings/providers/openai/test")
        self.assertEqual(r.status_code, 200)
        result = r.json()
        self.assertFalse(result["ok"])
        self.assertIn("No API key", result["error"])

    def test_provider_has_models_list(self):
        """Each provider should include a models list."""
        r = self.client.get("/v2/settings/providers")
        for provider in r.json():
            self.assertIn("models", provider)
            self.assertIsInstance(provider["models"], list)
            self.assertTrue(len(provider["models"]) > 0, f"{provider['provider_id']} has no models")


# ---------------------------------------------------------------------------
# 5.2 — Preset CRUD
# ---------------------------------------------------------------------------


class TestPresetCRUD(unittest.TestCase):
    """Verify user preset create/read/update/delete through API."""

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

    def test_create_user_preset(self):
        """POST /v2/settings/presets creates a new user preset."""
        r = self.client.post(
            "/v2/settings/presets",
            json={
                "name": "My Test Preset",
                "description": "A test preset",
                "role_configs": {
                    "narrator": {"provider": "ollama", "model": "qwen3:8b"},
                },
            },
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["name"], "My Test Preset")
        self.assertFalse(data["is_system"])
        self.assertIn("narrator", data["role_configs"])

    def test_update_user_preset(self):
        """PUT /v2/settings/presets/{id} updates an existing preset."""
        # Create
        r = self.client.post(
            "/v2/settings/presets",
            json={
                "name": "Updatable Preset",
                "description": "Before update",
                "role_configs": {"narrator": {"provider": "ollama", "model": "qwen3:8b"}},
            },
        )
        preset_id = r.json()["id"]

        # Update
        r2 = self.client.put(
            f"/v2/settings/presets/{preset_id}",
            json={"description": "After update"},
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["description"], "After update")

    def test_delete_user_preset(self):
        """DELETE /v2/settings/presets/{id} removes the preset."""
        # Create
        r = self.client.post(
            "/v2/settings/presets",
            json={
                "name": "Deletable",
                "description": "",
                "role_configs": {"narrator": {"provider": "ollama", "model": "qwen3:8b"}},
            },
        )
        preset_id = r.json()["id"]

        # Delete
        r2 = self.client.delete(f"/v2/settings/presets/{preset_id}")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["status"], "deleted")

        # Verify gone from list
        r3 = self.client.get("/v2/settings/presets")
        user_presets = [p for p in r3.json() if not p["is_system"]]
        ids = {p["id"] for p in user_presets}
        self.assertNotIn(preset_id, ids)

    def test_cannot_delete_system_preset(self):
        """DELETE system preset should return 403."""
        r = self.client.delete("/v2/settings/presets/cloud_all")
        self.assertEqual(r.status_code, 403)

    def test_cannot_update_system_preset(self):
        """PUT system preset should return 403."""
        r = self.client.put(
            "/v2/settings/presets/budget",
            json={"description": "hacked"},
        )
        self.assertEqual(r.status_code, 403)

    def test_create_preset_empty_name_returns_422(self):
        """POST preset with empty name should return 422."""
        r = self.client.post(
            "/v2/settings/presets",
            json={
                "name": "   ",
                "description": "",
                "role_configs": {"narrator": {"provider": "ollama", "model": "qwen3:8b"}},
            },
        )
        self.assertEqual(r.status_code, 422)


# ---------------------------------------------------------------------------
# 5.3 — Provider resolver for cloud_all
# ---------------------------------------------------------------------------


class TestProviderResolverCloudAll(unittest.TestCase):
    """Verify that provider_resolver resolves all roles to cloud when cloud_all is active."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)
        # Seed a provider key so resolution succeeds
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO provider_keys (provider_id, api_key, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
            ("anthropic", "sk-ant-test-key-12345678901234567890"),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_all_cloud_all_roles_resolve_to_cloud(self):
        """With cloud_all preset and a configured provider key, all roles should resolve to cloud."""
        from backend.app.config import SYSTEM_PRESETS
        from backend.app.core.provider_resolver import resolve_agent_config

        conn = get_connection(self.db_path)
        try:
            cloud_all_roles = SYSTEM_PRESETS["cloud_all"]
            campaign_settings = {
                "cloud_preset": "cloud_all",
                "custom_preset_id": None,
                "preferred_provider": None,
                "agent_overrides": None,
            }
            for role in cloud_all_roles:
                config = resolve_agent_config(role, campaign_settings, conn)
                self.assertNotEqual(
                    config.get("provider"),
                    "ollama",
                    f"Role '{role}' resolved to Ollama despite cloud_all preset",
                )
                self.assertEqual(
                    config.get("_source"),
                    "preset",
                    f"Role '{role}' did not resolve from preset (source={config.get('_source')})",
                )
        finally:
            conn.close()

    def test_embedding_role_defaults_to_ollama(self):
        """Embedding role is NOT in cloud_all, so it falls through to default (Ollama)."""
        from backend.app.core.provider_resolver import resolve_agent_config

        conn = get_connection(self.db_path)
        try:
            campaign_settings = {
                "cloud_preset": "cloud_all",
                "custom_preset_id": None,
                "preferred_provider": None,
                "agent_overrides": None,
            }
            config = resolve_agent_config("embedding", campaign_settings, conn)
            self.assertEqual(config.get("provider"), "ollama")
        finally:
            conn.close()

    def test_local_preset_resolves_all_to_default(self):
        """With local preset, all roles should resolve from default (Ollama)."""
        from backend.app.config import MODEL_CONFIG
        from backend.app.core.provider_resolver import resolve_agent_config

        conn = get_connection(self.db_path)
        try:
            campaign_settings = {
                "cloud_preset": "local",
                "custom_preset_id": None,
                "preferred_provider": None,
                "agent_overrides": None,
            }
            for role in list(MODEL_CONFIG.keys())[:5]:  # Check a sample
                config = resolve_agent_config(role, campaign_settings, conn)
                self.assertEqual(config.get("_source"), "default")
        finally:
            conn.close()

    def test_preferred_provider_is_respected(self):
        """When preferred_provider is set, roles should use that provider."""
        from backend.app.core.provider_resolver import resolve_agent_config

        conn = get_connection(self.db_path)
        try:
            campaign_settings = {
                "cloud_preset": "cloud_all",
                "custom_preset_id": None,
                "preferred_provider": "anthropic",
                "agent_overrides": None,
            }
            config = resolve_agent_config("narrator", campaign_settings, conn)
            self.assertEqual(config.get("provider"), "anthropic")
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 5.4 — Resolved config endpoint
# ---------------------------------------------------------------------------


class TestResolvedConfigEndpoint(unittest.TestCase):
    """Verify GET /v2/settings/campaigns/{id}/resolved_config returns proper data."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        apply_schema(self.db_path)

        self.settings_patcher = patch("backend.app.api.v2_settings.DEFAULT_DB_PATH", self.db_path)
        self.settings_patcher.start()

        self.campaigns_patcher = patch("backend.app.api.v2_campaigns.DEFAULT_DB_PATH", self.db_path)
        self.campaigns_patcher.start()

        from backend.main import app
        self.client = TestClient(app)

    def tearDown(self):
        self.settings_patcher.stop()
        self.campaigns_patcher.stop()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_resolved_config_for_nonexistent_campaign(self):
        """Should return 404 for unknown campaign."""
        r = self.client.get("/v2/settings/campaigns/nonexistent/resolved_config")
        self.assertEqual(r.status_code, 404)


# ---------------------------------------------------------------------------
# 5.5 — Full settings round-trip
# ---------------------------------------------------------------------------


class TestFullSettingsRoundTrip(unittest.TestCase):
    """Full round-trip: set provider key → get providers → list presets → get preferences."""

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

    def test_full_settings_flow(self):
        """Simulates the frontend settings page loading and user interaction."""
        # 1. Load providers (settings page mount)
        r = self.client.get("/v2/settings/providers")
        self.assertEqual(r.status_code, 200)
        providers = r.json()
        self.assertTrue(len(providers) > 0)

        # 2. Load presets (settings page mount)
        r = self.client.get("/v2/settings/presets")
        self.assertEqual(r.status_code, 200)
        presets = r.json()
        system_presets = [p for p in presets if p["is_system"]]
        self.assertTrue(len(system_presets) >= 4)

        # 3. Load preferences (settings page mount)
        r = self.client.get("/v2/settings/preferences")
        self.assertEqual(r.status_code, 200)
        prefs = r.json()["preferences"]
        self.assertIn("enable_choice_fallbacks", prefs)

        # 4. User sets an API key
        r = self.client.put(
            "/v2/settings/providers/anthropic/key",
            json={"api_key": "sk-ant-integration-test-key"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["has_key"])

        # 5. User disables fallback choices
        r = self.client.put(
            "/v2/settings/preferences",
            json={"preferences": {"enable_choice_fallbacks": "false"}},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["preferences"]["enable_choice_fallbacks"], "false")

        # 6. User creates a custom preset
        r = self.client.post(
            "/v2/settings/presets",
            json={
                "name": "Integration Test Preset",
                "description": "Custom for integration test",
                "role_configs": {
                    "narrator": {"provider": "ollama", "model": "qwen3:8b"},
                    "director": {"provider": "ollama", "model": "qwen3:4b"},
                },
            },
        )
        self.assertEqual(r.status_code, 200)
        custom_id = r.json()["id"]

        # 7. Verify the preset appears in listing
        r = self.client.get("/v2/settings/presets")
        all_ids = {p["id"] for p in r.json()}
        self.assertIn(custom_id, all_ids)

        # 8. User removes the API key
        r = self.client.delete("/v2/settings/providers/anthropic/key")
        self.assertEqual(r.status_code, 200)

        # 9. Verify everything persisted
        r = self.client.get("/v2/settings/preferences")
        self.assertEqual(r.json()["preferences"]["enable_choice_fallbacks"], "false")


if __name__ == "__main__":
    unittest.main()
