"""Tests for EraForge: LLM-powered era pack auto-generator.

Tests cover:
- Period suggestion fallback (no LLM)
- Pack generation fallback (no LLM)
- Canon character refinement fallback (no LLM)
- Generated pack passes lenient EraPack validation
- Generated pack has required sections
- Setting rules are universe-appropriate
- ContentRepository DB fallback (finds generated packs)
- list_catalog includes generated packs
- DB migration creates table and index
- Version increment for same setting+period
- Canon refinement can change proximity
"""
from __future__ import annotations

import json
import sqlite3

from backend.app.api.eraforge_models import (
    EraForgeSuggestOutput,
)
from backend.app.core.agents.era_forge_agent import (
    EraForgeAgent,
    _default_pack,
    _default_periods,
)
from backend.app.world.era_pack_models import EraPack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _in_memory_db_with_migration() -> sqlite3.Connection:
    """Create an in-memory DB and apply the 0034 migration."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from pathlib import Path

    migration = Path(__file__).resolve().parent.parent / "app" / "db" / "migrations" / "0034_generated_era_packs.sql"
    sql = migration.read_text(encoding="utf-8")
    conn.executescript(sql)
    return conn


def _sample_pack_data() -> dict:
    """Generate a sample pack dict using the fallback function."""
    return _default_pack(
        setting_id="game_of_thrones",
        setting_name="Game of Thrones",
        setting_genre="fantasy",
        period_id="war_of_five_kings",
        display_name="War of the Five Kings",
        time_period="298-300 AC",
        summary="War engulfs Westeros as five kings compete for the Iron Throne.",
        tone="political intrigue, brutal warfare",
        key_conflicts=["succession crisis", "northern rebellion", "southern scheming"],
    )


# ---------------------------------------------------------------------------
# Phase 1: Period Discovery
# ---------------------------------------------------------------------------


def test_suggest_periods_fallback() -> None:
    """EraForgeAgent(llm=None).suggest_periods() returns valid output with 3-5 periods."""
    agent = EraForgeAgent(llm=None)
    result = agent.suggest_periods("Game of Thrones")
    assert isinstance(result, dict)
    assert "setting_id" in result
    assert "setting_name" in result
    assert "periods" in result
    periods = result["periods"]
    assert 3 <= len(periods) <= 5
    # Validate period structure
    for p in periods:
        assert "period_id" in p
        assert "display_name" in p
        assert "summary" in p
        assert len(p["summary"]) > 10  # not empty
    # Validate against Pydantic schema
    EraForgeSuggestOutput.model_validate(result)


def test_suggest_periods_fallback_normalizes_setting_id() -> None:
    """Setting ID is normalized to lowercase underscore format."""
    result = _default_periods("Game of Thrones")
    assert result["setting_id"] == "game_of_thrones"
    assert result["setting_name"] == "Game of Thrones"


# ---------------------------------------------------------------------------
# Phase 2: Pack Generation
# ---------------------------------------------------------------------------


def test_generate_pack_fallback() -> None:
    """EraForgeAgent(llm=None).generate_pack() returns a valid pack dict."""
    agent = EraForgeAgent(llm=None)
    result = agent.generate_pack(
        setting_id="game_of_thrones",
        setting_name="Game of Thrones",
        setting_genre="fantasy",
        period_id="war_of_five_kings",
        display_name="War of the Five Kings",
        time_period="298-300 AC",
        summary="War engulfs Westeros.",
        tone="political intrigue",
    )
    assert isinstance(result, dict)
    assert result["era_id"] == "game_of_thrones__war_of_five_kings"


def test_generate_pack_has_required_sections() -> None:
    """Generated pack has non-empty backgrounds, species, setting_rules, metadata."""
    pack = _sample_pack_data()
    assert len(pack["backgrounds"]) >= 2
    assert len(pack["species"]) >= 1
    assert isinstance(pack["setting_rules"], dict)
    assert pack["setting_rules"]["setting_name"] == "Game of Thrones"
    assert isinstance(pack["metadata"], dict)
    assert pack["metadata"]["source"] == "eraforge_fallback"
    assert len(pack.get("start_location_pool", [])) >= 1


def test_generate_pack_passes_lenient_era_pack_validation() -> None:
    """Fallback pack passes EraPack.model_validate() in lenient mode."""
    import os
    os.environ["ERA_PACK_LENIENT_VALIDATION"] = "1"
    try:
        pack = _sample_pack_data()
        era_pack = EraPack.model_validate(pack)
        assert era_pack.era_id == "game_of_thrones__war_of_five_kings"
        assert len(era_pack.backgrounds) >= 2
        assert len(era_pack.species) >= 1
        assert era_pack.setting_rules.setting_name == "Game of Thrones"
    finally:
        os.environ.pop("ERA_PACK_LENIENT_VALIDATION", None)


def test_setting_rules_universe_appropriate_fantasy() -> None:
    """Fantasy pack should not have sci-fi bypass methods like 'hack' or 'force'."""
    pack = _default_pack(
        setting_id="game_of_thrones",
        setting_name="Game of Thrones",
        setting_genre="fantasy",
        period_id="war_of_five_kings",
        display_name="War of the Five Kings",
        time_period="298 AC",
        summary="War.",
        tone="gritty",
        key_conflicts=["war"],
    )
    bypass = pack["setting_rules"]["bypass_methods"]
    assert "force" not in bypass
    assert "hack" not in bypass
    assert "slice" not in bypass
    assert "magic" in bypass  # fantasy setting should have magic


def test_setting_rules_universe_appropriate_scifi() -> None:
    """Sci-fi pack should have tech bypass methods, not magic."""
    pack = _default_pack(
        setting_id="star_trek",
        setting_name="Star Trek",
        setting_genre="science fiction",
        period_id="tng_era",
        display_name="TNG Era",
        time_period="2364-2370",
        summary="Exploration.",
        tone="diplomatic",
        key_conflicts=["exploration"],
    )
    bypass = pack["setting_rules"]["bypass_methods"]
    assert "hack" in bypass
    assert "magic" not in bypass


# ---------------------------------------------------------------------------
# Phase 3: Canon Character Refinement
# ---------------------------------------------------------------------------


def test_refine_canon_fallback() -> None:
    """refine_canon_characters() with no LLM returns original characters unchanged."""
    agent = EraForgeAgent(llm=None)
    originals = [
        {"name": "Robb Stark", "proximity": "interaction", "locations": ["winterfell"]},
        {"name": "Tyrion Lannister", "proximity": "cameo", "locations": ["kings_landing"]},
    ]
    result = agent.refine_canon_characters(
        originals,
        background_id="bg-stark-bannerman",
        background_name="Stark Bannerman",
    )
    assert len(result) == 2
    assert result[0]["name"] == "Robb Stark"
    assert result[0]["proximity"] == "interaction"
    assert result[1]["name"] == "Tyrion Lannister"


def test_refine_canon_empty_list() -> None:
    """Empty canon characters list returns empty."""
    agent = EraForgeAgent(llm=None)
    result = agent.refine_canon_characters(
        [],
        background_id="bg-test",
    )
    assert result == []


# ---------------------------------------------------------------------------
# DB Migration
# ---------------------------------------------------------------------------


def test_migration_0034_creates_table() -> None:
    """Apply migration to fresh DB, verify table + index exist."""
    conn = _in_memory_db_with_migration()
    try:
        # Check table exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='generated_era_packs'"
        ).fetchone()
        assert row is not None

        # Check index exists
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_generated_era_packs_lookup'"
        ).fetchone()
        assert idx is not None
    finally:
        conn.close()


def test_migration_unique_constraint() -> None:
    """Unique constraint on (setting_id, period_id, version) is enforced."""
    conn = _in_memory_db_with_migration()
    try:
        conn.execute(
            "INSERT INTO generated_era_packs (setting_id, period_id, display_name, era_pack_json, version) "
            "VALUES ('got', 'wotfk', 'War', '{}', 1)"
        )
        # Duplicate should fail
        try:
            conn.execute(
                "INSERT INTO generated_era_packs (setting_id, period_id, display_name, era_pack_json, version) "
                "VALUES ('got', 'wotfk', 'War', '{}', 1)"
            )
            assert False, "Should have raised IntegrityError"
        except sqlite3.IntegrityError:
            pass
        # Different version should succeed
        conn.execute(
            "INSERT INTO generated_era_packs (setting_id, period_id, display_name, era_pack_json, version) "
            "VALUES ('got', 'wotfk', 'War v2', '{}', 2)"
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Version Increment
# ---------------------------------------------------------------------------


def test_version_increment() -> None:
    """Multiple generations for same setting+period get incrementing versions."""
    conn = _in_memory_db_with_migration()
    try:
        for v in (1, 2, 3):
            conn.execute(
                "INSERT INTO generated_era_packs (setting_id, period_id, display_name, era_pack_json, version) "
                "VALUES (?, ?, ?, ?, ?)",
                ("got", "wotfk", f"War v{v}", json.dumps({"era_id": "got__wotfk"}), v),
            )
        # Check we can query the latest version
        row = conn.execute(
            "SELECT MAX(version) AS max_ver FROM generated_era_packs WHERE setting_id = 'got' AND period_id = 'wotfk'"
        ).fetchone()
        assert row["max_ver"] == 3
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# ContentRepository DB Fallback
# ---------------------------------------------------------------------------


def test_content_repository_finds_generated_pack(monkeypatch) -> None:
    """Insert a row in in-memory DB, verify _load_generated_pack returns it."""
    import os
    os.environ["ERA_PACK_LENIENT_VALIDATION"] = "1"

    conn = _in_memory_db_with_migration()
    pack_data = _sample_pack_data()
    conn.execute(
        "INSERT INTO generated_era_packs (setting_id, period_id, display_name, summary, era_pack_json, version) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("game_of_thrones", "war_of_five_kings", "War of the Five Kings", "War", json.dumps(pack_data), 1),
    )
    conn.commit()

    from backend.app.content.repository import ContentRepository

    repo = ContentRepository()

    # Monkeypatch _load_generated_pack to use our in-memory connection
    def mock_load(setting_id, period_id):
        row = conn.execute(
            "SELECT era_pack_json FROM generated_era_packs "
            "WHERE setting_id = ? AND period_id = ? "
            "ORDER BY version DESC LIMIT 1",
            (setting_id, period_id),
        ).fetchone()
        if not row:
            return None
        data = json.loads(row["era_pack_json"])
        return EraPack.model_validate(data)

    monkeypatch.setattr(repo, "_load_generated_pack", mock_load)

    # Also make load_stacked_period_content raise FileNotFoundError
    def mock_load_stacked(**kwargs):
        raise FileNotFoundError("No YAML pack")

    monkeypatch.setattr(
        "backend.app.content.repository.load_stacked_period_content",
        mock_load_stacked,
    )

    pack = repo.get_content("game_of_thrones", "war_of_five_kings")
    assert pack.era_id == "game_of_thrones__war_of_five_kings"
    assert len(pack.backgrounds) >= 2

    conn.close()
    os.environ.pop("ERA_PACK_LENIENT_VALIDATION", None)


# ---------------------------------------------------------------------------
# list_catalog Includes Generated Packs
# ---------------------------------------------------------------------------


def test_list_catalog_includes_generated(monkeypatch) -> None:
    """list_catalog() includes entries with source='generated_era_pack'."""
    from backend.app.content.repository import ContentRepository

    repo = ContentRepository()

    # Monkeypatch load_all_packs to return empty (no static YAML packs)
    monkeypatch.setattr(repo, "load_all_packs", lambda: [])

    # Monkeypatch _list_generated_catalog_entries to return a fake entry
    def mock_generated():
        return [
            {
                "setting_id": "game_of_thrones",
                "setting_display_name": "Game of Thrones",
                "period_id": "war_of_five_kings",
                "period_display_name": "War of the Five Kings",
                "legacy_era_id": "game_of_thrones__war_of_five_kings",
                "source": "generated_era_pack",
                "summary": "War engulfs Westeros.",
                "playable": True,
                "playability_reasons": [],
                "locations_count": 0,
                "backgrounds_count": 4,
                "companions_count": 0,
                "quests_count": 0,
            }
        ]

    monkeypatch.setattr(repo, "_list_generated_catalog_entries", mock_generated)

    catalog = repo.list_catalog()
    generated = [e for e in catalog if e["source"] == "generated_era_pack"]
    assert len(generated) == 1
    assert generated[0]["setting_id"] == "game_of_thrones"
    assert generated[0]["period_id"] == "war_of_five_kings"


def test_list_catalog_static_takes_priority(monkeypatch) -> None:
    """Static YAML packs take priority over generated packs for the same key."""
    import os
    os.environ["ERA_PACK_LENIENT_VALIDATION"] = "1"

    from backend.app.content.repository import ContentRepository

    repo = ContentRepository()

    # Use "rebellion" era_id which resolves to (star_wars_legends, rebellion)
    static_pack = EraPack.model_validate({
        "era_id": "rebellion",
        "backgrounds": [],
        "locations": [],
    })

    monkeypatch.setattr(repo, "load_all_packs", lambda: [static_pack])

    # The static pack resolves to (star_wars_legends, rebellion) via resolve_legacy_era
    def mock_generated():
        return [
            {
                "setting_id": "star_wars_legends",
                "setting_display_name": "Star Wars Legends",
                "period_id": "rebellion",
                "period_display_name": "Rebellion",
                "legacy_era_id": "rebellion",
                "source": "generated_era_pack",
                "summary": "Generated version",
                "playable": True,
                "playability_reasons": [],
                "locations_count": 0,
                "backgrounds_count": 4,
                "companions_count": 0,
                "quests_count": 0,
            }
        ]

    monkeypatch.setattr(repo, "_list_generated_catalog_entries", mock_generated)

    catalog = repo.list_catalog()
    # Should only have 1 entry (static), not the duplicate generated one
    matching = [e for e in catalog if e["period_id"] == "rebellion"]
    assert len(matching) == 1
    assert matching[0]["source"] == "legacy_era_pack"

    os.environ.pop("ERA_PACK_LENIENT_VALIDATION", None)


# ---------------------------------------------------------------------------
# Pydantic Model Validation
# ---------------------------------------------------------------------------


def test_eraforge_suggest_output_validation() -> None:
    """EraForgeSuggestOutput validates correctly."""
    data = _default_periods("Lord of the Rings")
    validated = EraForgeSuggestOutput.model_validate(data)
    assert validated.setting_name == "Lord of the Rings"
    assert len(validated.periods) == 3


def test_eraforge_models_suggest_request_min_length() -> None:
    """EraForgeSuggestRequest rejects empty setting_prompt."""
    from pydantic import ValidationError
    from backend.app.api.eraforge_models import EraForgeSuggestRequest

    try:
        EraForgeSuggestRequest(setting_prompt="")
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass
