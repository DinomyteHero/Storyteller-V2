from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

from backend.app.content.repository import CONTENT_REPOSITORY
from backend.app.world.npc_generator import generate_npc


def test_load_rebellion_pack_v2():
    CONTENT_REPOSITORY.clear_cache()
    pack = CONTENT_REPOSITORY.get_pack("REBELLION")
    assert pack.era_id == "REBELLION"
    assert pack.schema_version == 2
    assert pack.meters is not None
    assert isinstance(pack.start_location_pool, list) and pack.start_location_pool
    assert pack.location_by_id(pack.start_location_pool[0]) is not None

    loc = pack.location_by_id("loc-yavin_base")
    assert loc is not None
    assert loc.security.security_level >= 0
    assert isinstance(loc.scene_types, list) and loc.scene_types


def test_faction_relationships_loaded_when_present():
    CONTENT_REPOSITORY.clear_cache()
    reb = CONTENT_REPOSITORY.get_pack("REBELLION")
    assert isinstance(reb.faction_relationships, dict)
    assert "rebel_alliance" in reb.faction_relationships

    CONTENT_REPOSITORY.clear_cache()
    nr = CONTENT_REPOSITORY.get_pack("NEW_REPUBLIC")
    assert isinstance(nr.faction_relationships, dict)
    assert "new_republic" in nr.faction_relationships


def test_procedural_npc_uses_location_encounter_table_when_available():
    CONTENT_REPOSITORY.clear_cache()
    pack = CONTENT_REPOSITORY.get_pack("REBELLION")
    loc = pack.location_by_id("loc-yavin_base")
    assert loc is not None
    assert loc.encounter_table

    payload = generate_npc(
        era_pack=pack,
        location_id="loc-yavin_base",
        seed=123,
        campaign_id="c",
        turn_number=1,
    )
    stats = payload.get("stats_json") or {}
    template_id = stats.get("template_id")
    assert template_id in {e.template_id for e in loc.encounter_table}


def test_enrich_script_idempotent_for_minimal_pack():
    # Dynamically import the script (scripts/ is not a Python package).
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "enrich_era_pack_v2.py"
    spec = importlib.util.spec_from_file_location("enrich_era_pack_v2", script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    with tempfile.TemporaryDirectory() as td:
        era_dir = Path(td) / "my_era"
        era_dir.mkdir(parents=True, exist_ok=True)
        (era_dir / "era.yaml").write_text("era_id: MY_ERA\nschema_version: 2\n", encoding="utf-8")
        (era_dir / "factions.yaml").write_text("factions:\n- id: neutral\n  name: Neutral\n", encoding="utf-8")
        (era_dir / "locations.yaml").write_text(
            "locations:\n- id: loc-a\n  name: Alpha\n  tags: [cantina]\n",
            encoding="utf-8",
        )
        (era_dir / "npcs.yaml").write_text(
            "npcs:\n  templates:\n  - id: t1\n    role: Spacer\n    tags: [cantina]\n  rotating:\n  - id: n1\n    name: Rot\n    faction_id: neutral\n    default_location_id: loc-a\n",
            encoding="utf-8",
        )

        os.environ.pop("ERA_PACK_DIR", None)
        mod.enrich_pack_dir(era_dir, in_place=True, suffix="_v2", backup_ext=".bak", dry_run=False)
        first_locations = (era_dir / "locations.yaml").read_text(encoding="utf-8")
        first_npcs = (era_dir / "npcs.yaml").read_text(encoding="utf-8")

        mod.enrich_pack_dir(era_dir, in_place=True, suffix="_v2", backup_ext=".bak", dry_run=False)
        second_locations = (era_dir / "locations.yaml").read_text(encoding="utf-8")
        second_npcs = (era_dir / "npcs.yaml").read_text(encoding="utf-8")

        assert first_locations == second_locations
        assert first_npcs == second_npcs
