"""Era pack loader: modular folder-per-era format support."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.content.repository import CONTENT_REPOSITORY


class TestEraPackLoaderModular(unittest.TestCase):
    def setUp(self) -> None:
        CONTENT_REPOSITORY.clear_cache()

    def tearDown(self) -> None:
        CONTENT_REPOSITORY.clear_cache()

    def test_load_era_pack_from_directory_merges_sections(self):
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td)
            era_dir = pack_dir / "my_era"
            (era_dir / "factions").mkdir(parents=True)
            (era_dir / "npcs" / "anchors").mkdir(parents=True)

            (era_dir / "era.yaml").write_text("era_id: MY_ERA\nstyle_ref: test_style\n", encoding="utf-8")
            (era_dir / "factions" / "f1.yaml").write_text("id: f1\nname: Faction One\n", encoding="utf-8")
            (era_dir / "factions" / "f2.yaml").write_text("id: f2\nname: Faction Two\n", encoding="utf-8")
            (era_dir / "locations.yaml").write_text(
                "- id: loc-a\n  name: Alpha Base\n- id: loc-b\n  name: Bravo Station\n",
                encoding="utf-8",
            )
            (era_dir / "npcs" / "anchors" / "npc1.yaml").write_text("id: npc1\nname: Test NPC\n", encoding="utf-8")
            (era_dir / "namebanks.yaml").write_text(
                "namebanks:\n  human_first:\n    - Asha\n    - Bix\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"ERA_PACK_DIR": str(pack_dir)}, clear=False):
                pack = CONTENT_REPOSITORY.get_pack("MY_ERA")
                self.assertEqual(pack.era_id, "MY_ERA")
                self.assertEqual(pack.style_ref, "test_style")
                self.assertEqual(len(pack.factions), 2)
                self.assertEqual(len(pack.locations), 2)
                self.assertEqual(len(pack.npcs.anchors), 1)
                self.assertIn("human_first", pack.namebanks)

    def test_directory_pack_takes_precedence_over_file(self):
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td)
            era_dir = pack_dir / "my_era"
            era_dir.mkdir(parents=True)

            # File-based pack (legacy)
            (pack_dir / "my_era.yaml").write_text("era_id: MY_ERA\nstyle_ref: from_file\n", encoding="utf-8")
            # Directory-based pack (new)
            (era_dir / "era.yaml").write_text("era_id: MY_ERA\nstyle_ref: from_dir\n", encoding="utf-8")

            with patch.dict(os.environ, {"ERA_PACK_DIR": str(pack_dir)}, clear=False):
                pack = CONTENT_REPOSITORY.get_pack("MY_ERA")
                self.assertEqual(pack.style_ref, "from_dir")

    def test_load_all_era_packs_ignores_file_when_directory_exists(self):
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td)
            era_dir = pack_dir / "my_era"
            era_dir.mkdir(parents=True)

            (pack_dir / "my_era.yaml").write_text("era_id: MY_ERA\nstyle_ref: from_file\n", encoding="utf-8")
            (era_dir / "era.yaml").write_text("era_id: MY_ERA\nstyle_ref: from_dir\n", encoding="utf-8")

            packs = CONTENT_REPOSITORY.load_all_packs()
            self.assertEqual(len(packs), 1)
            self.assertEqual(packs[0].era_id, "MY_ERA")
            self.assertEqual(packs[0].style_ref, "from_dir")

