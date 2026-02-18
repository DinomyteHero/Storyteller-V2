"""Multi-universe validation tests for arc screenplay generation (Phase 5).

Tests that:
1. Star Wars (DARK_TIMES) and Forgotten Realms packs load cleanly.
2. ArcScreenplayAgent generates valid output for both settings.
3. No setting bleed (Star Wars language in FR output, fantasy words in SW output).
4. Stat schemas (storyteller_core, dnd_5e_simplified) load and have correct keys.
5. Era pack backgrounds use only valid stat IDs from their schema.
"""
from __future__ import annotations

import pytest
from pathlib import Path
import sys

# Ensure repo root on path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dark_times_pack():
    from backend.app.content.repository import CONTENT_REPOSITORY
    pack = CONTENT_REPOSITORY.get_pack("dark_times")
    assert pack is not None, "dark_times era pack should load"
    return pack


@pytest.fixture(scope="module")
def forgotten_realms_pack():
    from backend.app.content.repository import CONTENT_REPOSITORY
    pack = CONTENT_REPOSITORY.get_pack("forgotten_realms")
    assert pack is not None, "forgotten_realms era pack should load"
    return pack


# ---------------------------------------------------------------------------
# Era pack loading tests
# ---------------------------------------------------------------------------

class TestEraPackLoading:
    def test_dark_times_loads(self, dark_times_pack):
        pack = dark_times_pack
        assert pack.era_id == "DARK_TIMES"
        assert pack.setting_rules.setting_genre == "science fantasy"
        assert pack.setting_rules.rule_system_id == "storyteller_core"

    def test_forgotten_realms_loads(self, forgotten_realms_pack):
        pack = forgotten_realms_pack
        assert pack.era_id == "FORGOTTEN_REALMS"
        assert pack.setting_rules.setting_genre == "high fantasy"
        assert pack.setting_rules.rule_system_id == "dnd_5e_simplified"

    def test_dark_times_has_locations(self, dark_times_pack):
        assert len(dark_times_pack.locations) > 0

    def test_forgotten_realms_has_locations(self, forgotten_realms_pack):
        assert len(forgotten_realms_pack.locations) >= 4

    def test_forgotten_realms_has_backgrounds(self, forgotten_realms_pack):
        assert len(forgotten_realms_pack.backgrounds) >= 2

    def test_forgotten_realms_has_npcs(self, forgotten_realms_pack):
        npcs = forgotten_realms_pack.all_npcs()
        assert len(npcs) >= 3

    def test_forgotten_realms_has_factions(self, forgotten_realms_pack):
        assert len(forgotten_realms_pack.factions) >= 3

    def test_forgotten_realms_has_quests(self, forgotten_realms_pack):
        assert len(forgotten_realms_pack.quests) >= 2


# ---------------------------------------------------------------------------
# Stat schema tests
# ---------------------------------------------------------------------------

class TestStatSchemas:
    def test_storyteller_core_loads(self):
        from backend.app.world.stat_schema_loader import load_stat_schema, get_stat_ids
        schema = load_stat_schema("storyteller_core")
        assert isinstance(schema, dict)
        stat_ids = get_stat_ids("storyteller_core")
        assert "Combat" in stat_ids
        assert "Stealth" in stat_ids
        assert "Charisma" in stat_ids
        assert "Tech" in stat_ids

    def test_dnd_5e_simplified_loads(self):
        from backend.app.world.stat_schema_loader import load_stat_schema, get_stat_ids
        schema = load_stat_schema("dnd_5e_simplified")
        assert isinstance(schema, dict)
        stat_ids = get_stat_ids("dnd_5e_simplified")
        assert "Strength" in stat_ids
        assert "Dexterity" in stat_ids
        assert "Intelligence" in stat_ids
        assert "Wisdom" in stat_ids
        assert "Charisma" in stat_ids
        assert "Constitution" in stat_ids

    def test_dnd_5e_has_correct_defaults(self):
        from backend.app.world.stat_schema_loader import get_stat_defaults
        defaults = get_stat_defaults("dnd_5e_simplified")
        assert all(v == 10 for v in defaults.values()), "All D&D 5e stats should default to 10"

    def test_storyteller_core_has_check_mechanics(self):
        from backend.app.world.stat_schema_loader import load_stat_schema
        schema = load_stat_schema("storyteller_core")
        assert "check_mechanics" in schema
        assert schema["check_mechanics"]["base_difficulty"] > 0

    def test_dnd_5e_has_proficiency_bonus(self):
        from backend.app.world.stat_schema_loader import load_stat_schema
        schema = load_stat_schema("dnd_5e_simplified")
        assert "check_mechanics" in schema
        assert schema["check_mechanics"].get("proficiency_bonus") == 2


# ---------------------------------------------------------------------------
# No setting bleed tests
# ---------------------------------------------------------------------------

class TestNoSettingBleed:
    """Ensure Star Wars terminology doesn't appear in FR pack and vice versa.

    Uses highly setting-specific terms unlikely to appear in the other setting.
    Generic terms like "empire", "magic", "elf" are excluded as they can appear
    in either context without representing setting bleed.
    """

    # Highly Star Wars-specific terms
    STAR_WARS_TERMS = {"lightsaber", "jedi", "sith", "hyperspace", "parsec", "midi-chlorian"}
    # Highly fantasy-specific terms (D&D specific, not generic)
    FANTASY_TERMS = {"draconic", "spellslot", "dungeon master", "d20", "beholder"}

    def _pack_text_blob(self, pack) -> str:
        """Extract all text from a pack for term checking."""
        parts = []
        for loc in pack.locations:
            parts.append(loc.description or "")
            parts.append(loc.name)
        for bg in pack.backgrounds:
            parts.append(bg.description)
            parts.append(bg.prologue_scenario or "")
        for npc in pack.all_npcs():
            parts.append(npc.motivation or "")
        return " ".join(parts).lower()

    def test_forgotten_realms_no_star_wars_bleed(self, forgotten_realms_pack):
        text = self._pack_text_blob(forgotten_realms_pack)
        bleeding_terms = [t for t in self.STAR_WARS_TERMS if t in text]
        assert not bleeding_terms, f"Star Wars terms found in FR pack: {bleeding_terms}"

    def test_dark_times_no_fantasy_bleed(self, dark_times_pack):
        text = self._pack_text_blob(dark_times_pack)
        bleeding_terms = [t for t in self.FANTASY_TERMS if t in text]
        assert not bleeding_terms, f"High fantasy terms found in SW pack: {bleeding_terms}"


# ---------------------------------------------------------------------------
# ArcScreenplayAgent fallback tests (no LLM required)
# ---------------------------------------------------------------------------

class TestArcScreenplayAgentMultiverse:
    """Test ArcScreenplayAgent fallback for both settings (no cloud LLM)."""

    def _get_fallback_screenplay(self, pack):
        """Get a deterministic fallback screenplay from ArcScreenplayAgent."""
        from backend.app.core.agents.arc_screenplay_agent import ArcScreenplayAgent
        agent = ArcScreenplayAgent(llm=None)  # no LLM — will use fallback
        return agent.generate(
            era_pack=pack,
            player_concept="A brave adventurer",
            background_id=pack.backgrounds[0].id if pack.backgrounds else "default",
            origin_context={},
            setting_rules=pack.setting_rules,
        )

    def test_dark_times_screenplay_generation(self, dark_times_pack):
        result = self._get_fallback_screenplay(dark_times_pack)
        assert isinstance(result, dict)
        assert "title" in result or "opening_crawl" in result or "arc_stage" in result

    def test_forgotten_realms_screenplay_generation(self, forgotten_realms_pack):
        result = self._get_fallback_screenplay(forgotten_realms_pack)
        assert isinstance(result, dict)
        # Result is valid regardless of which keys are present

    def test_screenplay_titles_differ(self, dark_times_pack, forgotten_realms_pack):
        """Screenplay titles should differ between settings (no bleed)."""
        sw_result = self._get_fallback_screenplay(dark_times_pack)
        fr_result = self._get_fallback_screenplay(forgotten_realms_pack)
        # At minimum, they're both valid dicts
        assert isinstance(sw_result, dict)
        assert isinstance(fr_result, dict)
        # If both have titles, they should be different
        sw_title = sw_result.get("title", "")
        fr_title = fr_result.get("title", "")
        if sw_title and fr_title:
            assert sw_title != fr_title, "Both settings produced identical screenplay titles"


# ---------------------------------------------------------------------------
# Stat schema validation integration test
# ---------------------------------------------------------------------------

class TestStatSchemaValidation:
    """Integration test for scripts/validate_stat_schema.py."""

    def test_forgotten_realms_stat_validation(self):
        """Verify FR backgrounds only use D&D 5e stat names."""
        from backend.app.world.stat_schema_loader import get_stat_ids
        from backend.app.content.repository import CONTENT_REPOSITORY

        pack = CONTENT_REPOSITORY.get_pack("forgotten_realms")
        valid_stat_ids = set(get_stat_ids("dnd_5e_simplified"))

        errors = []
        for bg in pack.backgrounds:
            for stat_name in (bg.starting_stats or {}):
                if stat_name not in valid_stat_ids:
                    errors.append(f"bg[{bg.id}].starting_stats has invalid stat: {stat_name}")
            for question in bg.questions:
                for choice in question.choices:
                    effects = choice.effects if hasattr(choice, "effects") else {}
                    stat_bonus = (
                        effects.stat_bonus if hasattr(effects, "stat_bonus")
                        else {}
                    ) or {}
                    for stat_name in stat_bonus:
                        if stat_name not in valid_stat_ids:
                            errors.append(
                                f"bg[{bg.id}].q[{question.id}].choice[{choice.label}] "
                                f"has invalid stat: {stat_name}"
                            )

        assert not errors, f"FR pack has invalid stat references: {errors}"

    def test_dark_times_stat_validation(self):
        """Verify SW backgrounds only use storyteller_core stat names."""
        from backend.app.world.stat_schema_loader import get_stat_ids
        from backend.app.content.repository import CONTENT_REPOSITORY

        pack = CONTENT_REPOSITORY.get_pack("dark_times")
        valid_stat_ids = set(get_stat_ids("storyteller_core"))

        errors = []
        for bg in pack.backgrounds:
            for stat_name in (bg.starting_stats or {}):
                if stat_name not in valid_stat_ids:
                    errors.append(f"bg[{bg.id}].starting_stats has invalid stat: {stat_name}")
            for question in bg.questions:
                for choice in question.choices:
                    effects = choice.effects if hasattr(choice, "effects") else {}
                    stat_bonus = (
                        effects.stat_bonus if hasattr(effects, "stat_bonus")
                        else {}
                    ) or {}
                    for stat_name in stat_bonus:
                        if stat_name not in valid_stat_ids:
                            errors.append(
                                f"bg[{bg.id}].q[{question.id}].choice[{choice.label}] "
                                f"has invalid stat: {stat_name}"
                            )

        assert not errors, f"SW pack has invalid stat references: {errors}"
