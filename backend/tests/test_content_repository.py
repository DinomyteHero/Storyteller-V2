from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from backend.app.content.repository import ContentRepository


def test_stacking_disable_and_extends() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        core = root / "core" / "star_wars_legends" / "periods" / "rebellion"
        override = root / "override" / "star_wars_legends" / "periods" / "rebellion"
        core.mkdir(parents=True)
        override.mkdir(parents=True)

        (core / "manifest.yaml").write_text(
            """
era_id: REBELLION
setting_id: star_wars_legends
period_id: rebellion
style_ref: core
locations:
  - id: loc_a
    name: Alpha
  - id: loc_b
    name: Beta
npcs:
  templates:
    - id: t_base
      role: smuggler
      tags: [criminal]
    - id: t_child
      extends: t_base
      role: captain
""",
            encoding="utf-8",
        )

        (override / "manifest.yaml").write_text(
            """
setting_id: star_wars_legends
period_id: rebellion
locations:
  - id: loc_b
    disabled: true
  - id: loc_c
    name: Gamma
""",
            encoding="utf-8",
        )

        repo = ContentRepository()
        with patch.dict(os.environ, {"SETTING_PACK_PATHS": f"{root / 'core'};{root / 'override'}"}, clear=False):
            pack = repo.get_content("star_wars_legends", "rebellion")

        loc_ids = [l.id for l in pack.locations]
        assert loc_ids == ["loc_a", "loc_c"]

        template = next(t for t in pack.npcs.templates if t.id == "t_child")
        assert template.role == "captain"
        assert "criminal" in template.tags


def test_legacy_era_adapter_uses_default_setting() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        legacy = root / "era_packs" / "rebellion"
        legacy.mkdir(parents=True)
        (legacy / "era.yaml").write_text(
            """
era_id: REBELLION
style_ref: legacy
locations:
  - id: loc_a
    name: Alpha
""",
            encoding="utf-8",
        )

        repo = ContentRepository()
        with patch.dict(
            os.environ,
            {
                "SETTING_PACK_PATHS": str(root / "missing"),
                "ERA_PACK_DIR": str(root / "era_packs"),
                "DEFAULT_SETTING_ID": "star_wars_legends",
            },
            clear=False,
        ):
            pack = repo.get_pack("REBELLION")

        assert pack.era_id == "REBELLION"
        assert pack.metadata.get("setting_id") == "star_wars_legends"
        assert pack.metadata.get("period_id") == "rebellion"
