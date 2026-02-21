"""Phase 4 tests: Legacy code cleanup verification.

Covers:
  4.1 — HYBRID_CLOUD_PRESETS removed from config.py
  4.2 — resolve_cloud_config() removed from config.py
  4.3 — HARDWARE_PROFILES removed from config.py
  4.4 — Feature flag ENABLE_CHOICE_FALLBACKS exists
  4.5 — No imports reference removed symbols
"""
import importlib
import inspect
import unittest


class TestLegacyCodeRemoved(unittest.TestCase):
    """Dead code identified in review should be removed from config.py."""

    def test_hybrid_cloud_presets_removed(self):
        """HYBRID_CLOUD_PRESETS should NOT exist in config module."""
        from backend.app import config

        self.assertFalse(
            hasattr(config, "HYBRID_CLOUD_PRESETS"),
            "HYBRID_CLOUD_PRESETS should have been removed (dead code)",
        )

    def test_resolve_cloud_config_removed(self):
        """resolve_cloud_config() should NOT exist in config module."""
        from backend.app import config

        self.assertFalse(
            hasattr(config, "resolve_cloud_config"),
            "resolve_cloud_config() should have been removed (dead code)",
        )

    def test_hardware_profiles_removed(self):
        """HARDWARE_PROFILES should NOT exist in config module."""
        from backend.app import config

        self.assertFalse(
            hasattr(config, "HARDWARE_PROFILES"),
            "HARDWARE_PROFILES should have been removed (dead code)",
        )


class TestConfigExportsIntact(unittest.TestCase):
    """Verify that essential config exports still exist after cleanup."""

    def test_system_presets_exists(self):
        from backend.app.config import SYSTEM_PRESETS

        self.assertIsInstance(SYSTEM_PRESETS, dict)

    def test_valid_cloud_presets_exists(self):
        from backend.app.config import VALID_CLOUD_PRESETS

        self.assertIsInstance(VALID_CLOUD_PRESETS, tuple)

    def test_model_config_exists(self):
        from backend.app.config import MODEL_CONFIG

        self.assertIsInstance(MODEL_CONFIG, dict)
        self.assertTrue(len(MODEL_CONFIG) > 0)

    def test_enable_choice_fallbacks_exists(self):
        from backend.app.config import ENABLE_CHOICE_FALLBACKS

        self.assertIsInstance(ENABLE_CHOICE_FALLBACKS, bool)

    def test_get_role_timeout_exists(self):
        from backend.app.config import get_role_timeout

        self.assertTrue(callable(get_role_timeout))

    def test_default_db_path_exists(self):
        from backend.app.config import DEFAULT_DB_PATH

        self.assertIsInstance(DEFAULT_DB_PATH, str)

    def test_data_root_exists(self):
        from backend.app.config import DATA_ROOT

        self.assertIsNotNone(DATA_ROOT)


class TestNoStaleImports(unittest.TestCase):
    """Verify no other module imports the removed symbols."""

    def _check_module_source_for(self, module_name: str, symbol: str) -> bool:
        """Check if a module's source mentions a symbol."""
        try:
            mod = importlib.import_module(module_name)
            source = inspect.getsource(mod)
            return symbol in source
        except (ImportError, OSError, TypeError):
            return False

    def test_no_imports_of_hybrid_cloud_presets(self):
        """No backend module should import HYBRID_CLOUD_PRESETS."""
        modules_to_check = [
            "backend.app.api.v2_settings",
            "backend.app.api.v2_campaigns",
            "backend.app.core.provider_resolver",
        ]
        for mod_name in modules_to_check:
            found = self._check_module_source_for(mod_name, "HYBRID_CLOUD_PRESETS")
            self.assertFalse(
                found,
                f"Module {mod_name} still references HYBRID_CLOUD_PRESETS",
            )

    def test_no_imports_of_resolve_cloud_config(self):
        """No backend module should import resolve_cloud_config."""
        modules_to_check = [
            "backend.app.api.v2_settings",
            "backend.app.api.v2_campaigns",
            "backend.app.core.provider_resolver",
        ]
        for mod_name in modules_to_check:
            found = self._check_module_source_for(mod_name, "resolve_cloud_config")
            self.assertFalse(
                found,
                f"Module {mod_name} still references resolve_cloud_config",
            )

    def test_no_imports_of_hardware_profiles(self):
        """No backend module should import HARDWARE_PROFILES."""
        modules_to_check = [
            "backend.app.api.v2_settings",
            "backend.app.api.v2_campaigns",
            "backend.app.core.provider_resolver",
        ]
        for mod_name in modules_to_check:
            found = self._check_module_source_for(mod_name, "HARDWARE_PROFILES")
            self.assertFalse(
                found,
                f"Module {mod_name} still references HARDWARE_PROFILES",
            )


if __name__ == "__main__":
    unittest.main()
