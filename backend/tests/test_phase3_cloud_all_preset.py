"""Phase 3 tests: cloud_all preset covers all LLM roles.

Covers:
  3.1 — SYSTEM_PRESETS includes cloud_all with all LLM roles
  3.2 — VALID_CLOUD_PRESETS includes cloud_all
  3.3 — Preset listing API shows cloud_all with correct description
  3.4 — All cloud_all roles are valid MODEL_CONFIG roles
  3.5 — cloud_all preset coverage (no LLM role falls through to Ollama)
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.db.migrate import apply_schema


# ---------------------------------------------------------------------------
# 3.1 — cloud_all preset structure
# ---------------------------------------------------------------------------


class TestCloudAllPresetStructure(unittest.TestCase):
    """SYSTEM_PRESETS should include a cloud_all preset covering all LLM roles."""

    def test_cloud_all_exists(self):
        from backend.app.config import SYSTEM_PRESETS

        self.assertIn("cloud_all", SYSTEM_PRESETS)

    def test_cloud_all_has_quality_and_fast_tiers(self):
        from backend.app.config import SYSTEM_PRESETS

        cloud_all = SYSTEM_PRESETS["cloud_all"]
        tiers_used = {cfg["tier"] for cfg in cloud_all.values()}
        self.assertIn("quality", tiers_used)
        self.assertIn("fast", tiers_used)

    def test_cloud_all_covers_core_narrative_roles(self):
        """cloud_all must cover all narrative-critical roles."""
        from backend.app.config import SYSTEM_PRESETS

        cloud_all = SYSTEM_PRESETS["cloud_all"]
        required_narrative_roles = [
            "director",
            "narrator",
            "choice_crafter",
            "companion_system",
            "mechanic",
        ]
        for role in required_narrative_roles:
            self.assertIn(role, cloud_all, f"cloud_all missing narrative role: {role}")

    def test_cloud_all_covers_infrastructure_roles(self):
        """cloud_all must cover infrastructure LLM roles."""
        from backend.app.config import SYSTEM_PRESETS

        cloud_all = SYSTEM_PRESETS["cloud_all"]
        infra_roles = [
            "campaign_init",
            "kg_extractor",
            "ingestion_tagger",
        ]
        for role in infra_roles:
            self.assertIn(role, cloud_all, f"cloud_all missing infra role: {role}")

    def test_cloud_all_excludes_embedding(self):
        """embedding uses local sentence-transformers, not a cloud LLM — should NOT be in cloud_all."""
        from backend.app.config import SYSTEM_PRESETS

        cloud_all = SYSTEM_PRESETS["cloud_all"]
        self.assertNotIn("embedding", cloud_all)

    def test_cloud_all_excludes_npc_render(self):
        """npc_render is optional — should NOT be in cloud_all."""
        from backend.app.config import SYSTEM_PRESETS

        cloud_all = SYSTEM_PRESETS["cloud_all"]
        self.assertNotIn("npc_render", cloud_all)

    def test_cloud_all_all_roles_in_model_config(self):
        """Every role in cloud_all must be a valid role in MODEL_CONFIG."""
        from backend.app.config import MODEL_CONFIG, SYSTEM_PRESETS

        cloud_all = SYSTEM_PRESETS["cloud_all"]
        for role in cloud_all:
            self.assertIn(role, MODEL_CONFIG, f"cloud_all role '{role}' not in MODEL_CONFIG")

    def test_cloud_all_covers_all_llm_roles(self):
        """cloud_all should cover every MODEL_CONFIG role except embedding and npc_render."""
        from backend.app.config import MODEL_CONFIG, SYSTEM_PRESETS

        cloud_all = SYSTEM_PRESETS["cloud_all"]
        excluded = {"embedding", "npc_render"}
        missing = []
        for role in MODEL_CONFIG:
            if role in excluded:
                continue
            if role not in cloud_all:
                missing.append(role)
        self.assertEqual(
            missing, [],
            f"cloud_all missing LLM roles (should cover all except embedding/npc_render): {missing}",
        )

    def test_cloud_all_role_count(self):
        """cloud_all should have 27-28 roles (all LLM roles except embedding + npc_render)."""
        from backend.app.config import MODEL_CONFIG, SYSTEM_PRESETS

        cloud_all = SYSTEM_PRESETS["cloud_all"]
        expected_count = len(MODEL_CONFIG) - 2  # minus embedding, npc_render
        self.assertEqual(
            len(cloud_all),
            expected_count,
            f"cloud_all has {len(cloud_all)} roles, expected {expected_count}",
        )


# ---------------------------------------------------------------------------
# 3.2 — VALID_CLOUD_PRESETS
# ---------------------------------------------------------------------------


class TestValidCloudPresets(unittest.TestCase):
    """VALID_CLOUD_PRESETS must include cloud_all."""

    def test_cloud_all_in_valid_presets(self):
        from backend.app.config import VALID_CLOUD_PRESETS

        self.assertIn("cloud_all", VALID_CLOUD_PRESETS)

    def test_all_system_presets_are_valid(self):
        """All system preset keys must be in VALID_CLOUD_PRESETS."""
        from backend.app.config import SYSTEM_PRESETS, VALID_CLOUD_PRESETS

        for preset_name in SYSTEM_PRESETS:
            self.assertIn(
                preset_name,
                VALID_CLOUD_PRESETS,
                f"System preset '{preset_name}' not in VALID_CLOUD_PRESETS",
            )

    def test_valid_presets_include_local_and_custom(self):
        from backend.app.config import VALID_CLOUD_PRESETS

        self.assertIn("local", VALID_CLOUD_PRESETS)
        self.assertIn("custom", VALID_CLOUD_PRESETS)


# ---------------------------------------------------------------------------
# 3.3 — Preset listing API
# ---------------------------------------------------------------------------


class TestPresetListingAPI(unittest.TestCase):
    """GET /v2/settings/presets should include cloud_all with correct metadata."""

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

    def test_presets_include_cloud_all(self):
        r = self.client.get("/v2/settings/presets")
        self.assertEqual(r.status_code, 200)
        presets = r.json()
        cloud_all_presets = [p for p in presets if p["id"] == "cloud_all"]
        self.assertEqual(len(cloud_all_presets), 1, "cloud_all preset should appear exactly once")

    def test_cloud_all_has_correct_name(self):
        r = self.client.get("/v2/settings/presets")
        presets = r.json()
        cloud_all = next(p for p in presets if p["id"] == "cloud_all")
        self.assertEqual(cloud_all["name"], "Cloud All")

    def test_cloud_all_has_description(self):
        r = self.client.get("/v2/settings/presets")
        presets = r.json()
        cloud_all = next(p for p in presets if p["id"] == "cloud_all")
        self.assertIn("no Ollama", cloud_all["description"])

    def test_cloud_all_is_system_preset(self):
        r = self.client.get("/v2/settings/presets")
        presets = r.json()
        cloud_all = next(p for p in presets if p["id"] == "cloud_all")
        self.assertTrue(cloud_all["is_system"])

    def test_cloud_all_has_role_configs(self):
        r = self.client.get("/v2/settings/presets")
        presets = r.json()
        cloud_all = next(p for p in presets if p["id"] == "cloud_all")
        self.assertIsInstance(cloud_all["role_configs"], dict)
        self.assertTrue(len(cloud_all["role_configs"]) > 20, "cloud_all should have 20+ roles")

    def test_all_four_system_presets_listed(self):
        """budget, balanced, quality, cloud_all should all appear."""
        r = self.client.get("/v2/settings/presets")
        presets = r.json()
        system_ids = {p["id"] for p in presets if p["is_system"]}
        for expected in ("budget", "balanced", "quality", "cloud_all"):
            self.assertIn(expected, system_ids)


if __name__ == "__main__":
    unittest.main()
