"""Unit tests for era normalization and UI key canonicalization."""
import os
import unittest

from ingestion.era_normalization import (
    canonicalize_to_ui_era_key,
    apply_era_mode,
    resolve_era_mode,
    infer_era_from_input_root,
)


class TestEraCanonicalization(unittest.TestCase):
    def test_ui_key_mapping_common_variants(self) -> None:
        self.assertEqual(canonicalize_to_ui_era_key("LOTF"), "LEGACY")
        self.assertEqual(canonicalize_to_ui_era_key("Legacy Era"), "LEGACY")
        self.assertEqual(canonicalize_to_ui_era_key("New Jedi Order Era"), "NEW_REPUBLIC")
        self.assertEqual(canonicalize_to_ui_era_key("New Republic"), "NEW_REPUBLIC")
        self.assertEqual(canonicalize_to_ui_era_key("Rebellion Era"), "REBELLION")
        self.assertEqual(canonicalize_to_ui_era_key("Galactic Civil War"), "REBELLION")
        self.assertEqual(canonicalize_to_ui_era_key("Clone Wars"), "CLONE_WARS")
        self.assertEqual(canonicalize_to_ui_era_key("Rise of the Empire"), "CLONE_WARS")
        self.assertEqual(canonicalize_to_ui_era_key("Old Galactic Republic"), "OLD_REPUBLIC")
        self.assertEqual(canonicalize_to_ui_era_key("High Republic"), "HIGH_REPUBLIC")

    def test_ui_key_mapping_unknown(self) -> None:
        self.assertIsNone(canonicalize_to_ui_era_key("Some Random Era"))

    def test_apply_era_mode(self) -> None:
        self.assertEqual(apply_era_mode("LOTF", "ui"), "LEGACY")
        self.assertEqual(apply_era_mode("Unknown Era", "ui"), "Unknown Era")
        self.assertEqual(apply_era_mode("LOTF", "legacy"), "LOTF")

    def test_resolve_era_mode_env(self) -> None:
        old = os.environ.get("STORYTELLER_ERA_MODE")
        try:
            os.environ["STORYTELLER_ERA_MODE"] = "ui"
            self.assertEqual(resolve_era_mode(None), "ui")
            self.assertEqual(resolve_era_mode("legacy"), "legacy")
            os.environ["STORYTELLER_ERA_MODE"] = "folder"
            self.assertEqual(resolve_era_mode(None), "folder")
        finally:
            if old is None:
                os.environ.pop("STORYTELLER_ERA_MODE", None)
            else:
                os.environ["STORYTELLER_ERA_MODE"] = old

    def test_infer_era_from_input_root(self) -> None:
        # Treat the first folder segment under input root as the era label.
        file_path = os.path.join("data", "lore", "New Jedi Order Era", "Novels", "book.epub")
        root = os.path.join("data", "lore")
        from pathlib import Path
        self.assertEqual(
            infer_era_from_input_root(Path(file_path), Path(root)),
            "New Jedi Order Era",
        )
