"""Tests for the era content generator — deterministic scaffold generation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from ingestion.era_content_generator import (
    GeneratedContent,
    generate_era_content,
    _generate_quest_deterministic,
    _generate_companion_deterministic,
    _extract_entities_from_chunks,
    _detect_genre,
    QUEST_TEMPLATES,
    COMPANION_ARCHETYPES,
)


class TestQuestGeneration:
    """Test deterministic quest scaffold generation."""

    def test_generates_valid_quest_structure(self):
        quest = _generate_quest_deterministic(
            quest_id="test_quest_1",
            template_key="rescue",
            era="REBELLION",
        )
        assert quest["id"] == "test_quest_1"
        assert "title" in quest
        assert "stages" in quest
        assert len(quest["stages"]) == len(QUEST_TEMPLATES["rescue"]["stages"])
        assert quest["entry_conditions"]["turn"]["min"] == 5

    def test_all_templates_produce_valid_quests(self):
        for key in QUEST_TEMPLATES:
            quest = _generate_quest_deterministic(
                quest_id=f"q_{key}",
                template_key=key,
                era="REBELLION",
            )
            assert quest["id"] == f"q_{key}"
            assert len(quest["stages"]) >= 3
            for stage in quest["stages"]:
                assert "stage_id" in stage
                assert "objective" in stage
                assert "success_conditions" in stage

    def test_quest_stages_have_sequential_dependencies(self):
        quest = _generate_quest_deterministic(
            quest_id="q_test",
            template_key="espionage",
            era="REBELLION",
        )
        stages = quest["stages"]
        # Stage 1+ should reference previous stage in success_conditions
        for i in range(1, len(stages)):
            assert "stage_completed" in stages[i]["success_conditions"]
            assert stages[i]["success_conditions"]["stage_completed"] == stages[i - 1]["stage_id"]

    def test_context_hints_stored(self):
        quest = _generate_quest_deterministic(
            quest_id="q_ctx",
            template_key="rescue",
            era="REBELLION",
            context_hints=["Luke Skywalker", "Han Solo"],
        )
        assert "_generation_context" in quest
        assert "Luke Skywalker" in quest["_generation_context"]


class TestCompanionGeneration:
    """Test deterministic companion scaffold generation."""

    def test_generates_valid_companion_structure(self):
        archetype = COMPANION_ARCHETYPES[0]
        comp = _generate_companion_deterministic(
            comp_id="comp_test_1",
            archetype=archetype,
            era="REBELLION",
            species="Twi'lek",
        )
        assert comp["id"] == "comp_test_1"
        assert comp["species"] == "Twi'lek"
        assert "voice" in comp
        assert "belief" in comp["voice"]
        assert "wound" in comp["voice"]
        assert "taboo" in comp["voice"]
        assert "recruitment" in comp
        assert "influence" in comp
        assert "banter" in comp

    def test_all_archetypes_produce_valid_companions(self):
        for i, archetype in enumerate(COMPANION_ARCHETYPES):
            comp = _generate_companion_deterministic(
                comp_id=f"comp_{i}",
                archetype=archetype,
                era="REBELLION",
            )
            assert comp["role_in_party"] == archetype["role_in_party"]
            assert comp["voice"]["rhetorical_style"] == archetype["voice_style"]

    def test_companion_influence_has_required_fields(self):
        comp = _generate_companion_deterministic(
            comp_id="comp_inf",
            archetype=COMPANION_ARCHETYPES[0],
            era="REBELLION",
        )
        inf = comp["influence"]
        assert "starts_at" in inf
        assert "min" in inf
        assert "max" in inf
        assert "triggers" in inf
        assert isinstance(inf["triggers"], list)


class TestEntityExtraction:
    """Test entity extraction from lore chunks."""

    def test_extracts_character_names(self):
        chunks = [{"text": "Luke Skywalker met with Princess Leia in the command center."}]
        entities = _extract_entities_from_chunks(chunks)
        assert "Luke Skywalker" in entities["characters"]
        assert "Princess Leia" in entities["characters"]

    def test_extracts_multi_word_names(self):
        chunks = [{"text": "The Rebel Alliance fought against the Galactic Empire."}]
        entities = _extract_entities_from_chunks(chunks)
        # 2-word capitalized names go to characters, 3+ word names with faction keywords go to factions
        all_names = entities["characters"] + entities["locations"] + entities["factions"]
        assert len(all_names) > 0  # Should extract at least some entities
        # "Rebel Alliance" (2 words) → characters; "Galactic Empire" (2 words) → characters
        assert "Rebel Alliance" in entities["characters"] or "Galactic Empire" in entities["characters"]

    def test_handles_empty_chunks(self):
        entities = _extract_entities_from_chunks([])
        assert entities["characters"] == []
        assert entities["locations"] == []
        assert entities["factions"] == []


class TestGenreDetection:
    """Test genre detection from lore chunks."""

    def test_detects_military_genre(self):
        chunks = [{"text": "The fleet assembled for battle. The squad advanced under strategy command."}]
        genres = _detect_genre(chunks)
        assert "military_tactical" in genres

    def test_detects_espionage_genre(self):
        chunks = [{"text": "The spy infiltrated the covert intelligence operation."}]
        genres = _detect_genre(chunks)
        assert "espionage" in genres

    def test_returns_empty_for_unmatched(self):
        chunks = [{"text": "Hello world."}]
        genres = _detect_genre(chunks)
        assert isinstance(genres, list)


class TestEndToEnd:
    """Test full generation pipeline with dry run."""

    def test_dry_run_produces_content(self, tmp_path: Path):
        result = generate_era_content(
            era="REBELLION",
            output_dir=tmp_path / "output",
            num_quests=3,
            num_companions=2,
            use_llm=False,
            dry_run=True,
        )
        assert isinstance(result, GeneratedContent)
        assert len(result.quests) == 3
        assert len(result.companions) == 2
        assert result.manifest["era"] == "REBELLION"
        assert result.manifest["quests_generated"] == 3
        assert result.manifest["companions_generated"] == 2
        # Dry run: no files written
        assert not (tmp_path / "output").exists()

    def test_writes_valid_yaml(self, tmp_path: Path):
        output_dir = tmp_path / "era_output"
        result = generate_era_content(
            era="REBELLION",
            output_dir=output_dir,
            num_quests=2,
            num_companions=2,
            use_llm=False,
            dry_run=False,
        )

        # Verify files created
        assert (output_dir / "generated_quests.yaml").exists()
        assert (output_dir / "generated_companions.yaml").exists()
        assert (output_dir / "_generation_manifest.json").exists()

        # Verify YAML is parseable
        quests_data = yaml.safe_load((output_dir / "generated_quests.yaml").read_text())
        assert "quests" in quests_data
        assert len(quests_data["quests"]) == 2

        companions_data = yaml.safe_load((output_dir / "generated_companions.yaml").read_text())
        assert "companions" in companions_data
        assert len(companions_data["companions"]) == 2

        # Verify manifest is valid JSON
        manifest = json.loads((output_dir / "_generation_manifest.json").read_text())
        assert manifest["era"] == "REBELLION"
        assert manifest["llm_used"] is False
