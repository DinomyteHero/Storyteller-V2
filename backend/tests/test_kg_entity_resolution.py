"""Tests for entity resolution module."""
from __future__ import annotations

import pytest

from backend.app.kg.entity_resolution import (
    build_alias_lookup,
    merge_entity_properties,
    resolve_entity_id,
    slugify,
    _levenshtein,
)


class TestSlugify:
    def test_basic_name(self):
        assert slugify("Luke Skywalker") == "luke_skywalker"

    def test_hyphenated(self):
        assert slugify("AT-AT Walker") == "at_at_walker"

    def test_special_chars(self):
        assert slugify("Mos Eisley's Cantina!") == "mos_eisleys_cantina"

    def test_multiple_spaces(self):
        assert slugify("Darth   Vader") == "darth_vader"

    def test_empty(self):
        assert slugify("") == ""


class TestLevenshtein:
    def test_identical(self):
        assert _levenshtein("hello", "hello") == 0

    def test_one_edit(self):
        assert _levenshtein("hello", "helo") == 1

    def test_two_edits(self):
        assert _levenshtein("hello", "hllo") == 1

    def test_empty(self):
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3


class TestResolveEntityId:
    def test_alias_match(self):
        lookup = {"luke": "luke_skywalker", "luke skywalker": "luke_skywalker"}
        assert resolve_entity_id("Luke", "CHARACTER", lookup) == "luke_skywalker"
        assert resolve_entity_id("Luke Skywalker", "CHARACTER", lookup) == "luke_skywalker"

    def test_existing_cache_match(self):
        lookup = {}
        existing = {"tatooine": "tatooine"}
        assert resolve_entity_id("Tatooine", "LOCATION", lookup, existing) == "tatooine"

    def test_fuzzy_match(self):
        lookup = {}
        existing = {"luke skywalker": "luke_skywalker"}
        # "luke skywalkr" is 1 edit away
        assert resolve_entity_id("Luke Skywalkr", "CHARACTER", lookup, existing) == "luke_skywalker"

    def test_new_entity_generates_slug(self):
        lookup = {}
        result = resolve_entity_id("Mos Eisley Cantina", "LOCATION", lookup)
        assert result == "mos_eisley_cantina"

    def test_alias_takes_priority(self):
        lookup = {"vader": "darth_vader"}
        existing = {"vader": "some_other_id"}
        assert resolve_entity_id("Vader", "CHARACTER", lookup, existing) == "darth_vader"


class TestMergeEntityProperties:
    def test_union_lists(self):
        result = merge_entity_properties(
            {"aliases": ["Luke", "Wormie"]},
            {"aliases": ["Wormie", "Master Skywalker"]},
        )
        assert result["aliases"] == ["Luke", "Wormie", "Master Skywalker"]

    def test_new_key_added(self):
        result = merge_entity_properties(
            {"species": "Human"},
            {"role": "Jedi Knight"},
        )
        assert result["species"] == "Human"
        assert result["role"] == "Jedi Knight"

    def test_empty_overwritten_by_nonempty(self):
        result = merge_entity_properties(
            {"faction": ""},
            {"faction": "Rebel Alliance"},
        )
        assert result["faction"] == "Rebel Alliance"

    def test_existing_scalar_preserved(self):
        result = merge_entity_properties(
            {"species": "Human"},
            {"species": "Near-Human"},
        )
        # First-seen wins for non-empty scalars
        assert result["species"] == "Human"

    def test_none_overwritten(self):
        result = merge_entity_properties(
            {"active_trauma": None},
            {"active_trauma": "loss of hand"},
        )
        assert result["active_trauma"] == "loss of hand"


class TestBuildAliasLookup:
    def test_loads_from_project_file(self):
        """Test loading from the actual project aliases file (integration)."""
        lookup = build_alias_lookup()
        if not lookup:
            pytest.skip("character_aliases.yml not found")
        # Should have Luke in there
        assert "luke" in lookup or "luke skywalker" in lookup
        if "luke" in lookup:
            assert lookup["luke"] == "luke_skywalker"

    def test_missing_file_returns_empty(self, tmp_path):
        result = build_alias_lookup(tmp_path / "nonexistent.yml")
        assert result == {}

    def test_canonical_id_included(self, tmp_path):
        """The canonical ID itself should be in the lookup."""
        yaml_file = tmp_path / "aliases.yml"
        yaml_file.write_text("han_solo:\n  - Han\n  - Han Solo\n")
        lookup = build_alias_lookup(yaml_file)
        assert lookup["han_solo"] == "han_solo"
        assert lookup["han solo"] == "han_solo"
        assert lookup["han"] == "han_solo"
