"""Tests for SettingRules model and universe contamination prevention."""
from __future__ import annotations

import pytest


# ── SettingRules model tests ─────────────────────────────────────────


class TestSettingRulesModel:
    """Tests for the SettingRules Pydantic model."""

    def test_defaults_to_star_wars(self):
        """SettingRules() defaults should be Star Wars Legends values."""
        from backend.app.world.era_pack_models import SettingRules
        sr = SettingRules()
        assert sr.setting_name == "Star Wars Legends"
        assert sr.setting_genre == "science fantasy"
        assert "Twi'lek" in sr.common_species
        assert "Rebellion" in sr.example_factions
        assert sr.biographer_role == "a biographer for a Star Wars narrative RPG"

    def test_custom_setting(self):
        """SettingRules with custom setting values works."""
        from backend.app.world.era_pack_models import SettingRules
        sr = SettingRules(
            setting_name="Harry Potter",
            setting_genre="urban fantasy",
            biographer_role="a biographer for a Harry Potter narrative RPG",
            architect_role="the World Architect for a Harry Potter narrative RPG",
            director_role="the Director for an interactive Harry Potter story engine",
            suggestion_style="a Harry Potter RPG-style game",
            common_species=["Human", "Goblin", "House-elf", "Centaur"],
            example_factions=["Order of the Phoenix", "Death Eaters", "Ministry of Magic"],
            historical_lore_label="established Harry Potter lore",
            bypass_methods=["magic", "potion", "enchantment"],
            fallback_background="A student at a magical school.",
        )
        assert sr.setting_name == "Harry Potter"
        assert "Twi'lek" not in sr.common_species
        assert "Goblin" in sr.common_species
        assert "Star Wars" not in sr.biographer_role

    def test_concept_location_map_defaults_empty(self):
        """concept_location_map should default to empty dict."""
        from backend.app.world.era_pack_models import SettingRules
        sr = SettingRules()
        assert sr.concept_location_map == {}

    def test_extra_fields_forbidden(self):
        """SettingRules should reject unknown fields."""
        from backend.app.world.era_pack_models import SettingRules
        with pytest.raises(Exception):
            SettingRules(unknown_field="oops")


# ── get_setting_rules() tests ───────────────────────────────────────


class TestGetSettingRules:
    """Tests for the get_setting_rules() helper."""

    def test_empty_state_returns_sw_defaults(self):
        """Empty state should return Star Wars defaults."""
        from backend.app.core.setting_context import get_setting_rules
        sr = get_setting_rules({})
        assert sr.setting_name == "Star Wars Legends"

    def test_state_without_campaign_returns_defaults(self):
        """State with no campaign key returns defaults."""
        from backend.app.core.setting_context import get_setting_rules
        sr = get_setting_rules({"turn_number": 5})
        assert sr.setting_name == "Star Wars Legends"

    def test_state_with_setting_rules(self):
        """State with setting_rules should return the custom rules."""
        from backend.app.core.setting_context import get_setting_rules
        state = {
            "campaign": {
                "world_state_json": {
                    "setting_rules": {
                        "setting_name": "Harry Potter",
                        "setting_genre": "urban fantasy",
                        "common_species": ["Human", "Goblin"],
                        "example_factions": ["Order of the Phoenix", "Death Eaters"],
                    }
                }
            }
        }
        sr = get_setting_rules(state)
        assert sr.setting_name == "Harry Potter"
        assert "Goblin" in sr.common_species
        # Unset fields should still have SW defaults
        assert sr.biographer_role == "a biographer for a Star Wars narrative RPG"

    def test_state_with_no_setting_rules_key(self):
        """State with world_state_json but no setting_rules returns defaults."""
        from backend.app.core.setting_context import get_setting_rules
        state = {
            "campaign": {
                "world_state_json": {
                    "active_factions": []
                }
            }
        }
        sr = get_setting_rules(state)
        assert sr.setting_name == "Star Wars Legends"


# ── EraPack integration tests ───────────────────────────────────────


class TestEraPackSettingRules:
    """Tests that EraPack carries SettingRules correctly."""

    def test_era_pack_default_setting_rules(self):
        """EraPack should have setting_rules with SW defaults."""
        from backend.app.world.era_pack_models import EraPack
        pack = EraPack(era_id="test")
        assert pack.setting_rules.setting_name == "Star Wars Legends"
        assert pack.setting_rules.setting_genre == "science fantasy"

    def test_era_pack_custom_setting_rules(self):
        """EraPack with custom setting_rules."""
        from backend.app.world.era_pack_models import EraPack, SettingRules
        pack = EraPack(
            era_id="hp",
            setting_rules=SettingRules(
                setting_name="Harry Potter",
                setting_genre="urban fantasy",
            ),
        )
        assert pack.setting_rules.setting_name == "Harry Potter"

    def test_setting_rules_serialization(self):
        """SettingRules should serialize and deserialize cleanly."""
        from backend.app.world.era_pack_models import SettingRules
        sr = SettingRules(setting_name="LOTR", common_species=["Human", "Elf", "Dwarf", "Hobbit"])
        data = sr.model_dump(mode="json")
        sr2 = SettingRules.model_validate(data)
        assert sr2.setting_name == "LOTR"
        assert "Elf" in sr2.common_species


# ── Agent prompt contamination tests ────────────────────────────────


class TestAgentDecontamination:
    """Verify agents use setting_rules and don't leak Star Wars into other settings."""

    def _hp_rules(self):
        from backend.app.world.era_pack_models import SettingRules
        return SettingRules(
            setting_name="Harry Potter",
            setting_genre="urban fantasy",
            biographer_role="a biographer for a Harry Potter narrative RPG",
            architect_role="the World Architect for a Harry Potter narrative RPG",
            director_role="the Director for an interactive Harry Potter story engine",
            suggestion_style="a Harry Potter RPG-style game",
            common_species=["Human", "Goblin", "House-elf", "Centaur"],
            example_factions=["Order of the Phoenix", "Death Eaters", "Ministry of Magic"],
            historical_lore_label="established Harry Potter lore",
        )

    def test_biographer_prompt_with_hp_rules(self):
        """Biographer prompt should use HP role, not mention Star Wars."""
        from backend.app.core.agents.biographer import BiographerAgent
        bio = BiographerAgent(llm=None)
        # We can't directly test the system prompt without calling build(),
        # but calling build with no LLM uses fallback. Instead, test that
        # setting_rules parameter is accepted and used in fallback.
        result = bio.build(
            "Harry -- wizard student from London",
            time_period="HOGWARTS",
            setting_rules=self._hp_rules(),
        )
        # Fallback should work with HP setting_rules
        assert result["name"] == "Harry"
        assert isinstance(result["background"], str)

    def test_architect_accepts_setting_rules(self):
        """Architect.build() should accept setting_rules parameter."""
        from backend.app.core.agents.architect import CampaignArchitect
        arch = CampaignArchitect(llm=None)
        # No LLM = fallback. Just verify it doesn't crash with setting_rules.
        result = arch.build(
            time_period="HOGWARTS",
            themes=["magic", "friendship"],
            setting_rules=self._hp_rules(),
        )
        assert result is not None
        assert result.get("title") is not None

    def test_suggestion_refiner_prompt_template(self):
        """SuggestionRefiner prompt template should use __SUGGESTION_STYLE__ placeholder."""
        from backend.app.core.nodes.suggestion_refiner import _SYSTEM_PROMPT_TEMPLATE
        assert "__SUGGESTION_STYLE__" in _SYSTEM_PROMPT_TEMPLATE
        # Replace with HP style
        formatted = _SYSTEM_PROMPT_TEMPLATE.replace("__SUGGESTION_STYLE__", "a Harry Potter RPG-style game")
        assert "Harry Potter" in formatted
        assert "Star Wars" not in formatted

    def test_get_setting_rules_with_hp_state(self):
        """get_setting_rules with HP state should return HP rules."""
        from backend.app.core.setting_context import get_setting_rules
        hp_rules = self._hp_rules()
        state = {
            "campaign": {
                "world_state_json": {
                    "setting_rules": hp_rules.model_dump(mode="json"),
                }
            }
        }
        sr = get_setting_rules(state)
        assert sr.setting_name == "Harry Potter"
        assert "Star Wars" not in sr.director_role
        assert "Star Wars" not in sr.suggestion_style
        assert "Rebellion" not in sr.example_factions
        assert "Twi'lek" not in sr.common_species
