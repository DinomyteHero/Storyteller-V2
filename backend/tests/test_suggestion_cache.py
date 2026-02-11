"""Tests for the Director suggestion pre-generation cache."""
from __future__ import annotations

import os
import tempfile
import pytest

from backend.app.core.suggestion_cache import SuggestionCache


@pytest.fixture
def cache():
    """Create a SuggestionCache backed by a temporary SQLite DB."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    yield SuggestionCache(db_path=db_path)
    os.unlink(db_path)


class TestSuggestionCache:
    """Tests for SuggestionCache."""

    def test_put_and_get(self, cache):
        """Store and retrieve a Director output."""
        output = {
            "director_instructions": "Keep pacing brisk.",
            "suggested_actions": [
                {"label": "Talk", "intent_text": "Say: Hello", "category": "SOCIAL"},
            ],
        }
        cache.put("camp-1", "loc-cantina", "SETUP", 5, output)

        result = cache.get("camp-1", "loc-cantina", "SETUP", 5)
        assert result is not None
        assert result["director_instructions"] == "Keep pacing brisk."
        assert len(result["suggested_actions"]) == 1
        assert result["suggested_actions"][0]["label"] == "Talk"

    def test_cache_miss(self, cache):
        """Returns None when no match."""
        result = cache.get("camp-1", "loc-cantina", "SETUP", 5)
        assert result is None

    def test_cache_miss_wrong_location(self, cache):
        """Different location = miss."""
        output = {"director_instructions": "Test", "suggested_actions": []}
        cache.put("camp-1", "loc-cantina", "SETUP", 5, output)

        result = cache.get("camp-1", "loc-hangar", "SETUP", 5)
        assert result is None

    def test_cache_miss_wrong_turn(self, cache):
        """Different turn_number = miss."""
        output = {"director_instructions": "Test", "suggested_actions": []}
        cache.put("camp-1", "loc-cantina", "SETUP", 5, output)

        result = cache.get("camp-1", "loc-cantina", "SETUP", 6)
        assert result is None

    def test_cache_miss_wrong_arc_stage(self, cache):
        """Different arc_stage = miss."""
        output = {"director_instructions": "Test", "suggested_actions": []}
        cache.put("camp-1", "loc-cantina", "SETUP", 5, output)

        result = cache.get("camp-1", "loc-cantina", "RISING", 5)
        assert result is None

    def test_invalidate(self, cache):
        """Invalidate clears all entries for a campaign."""
        output = {"director_instructions": "Test", "suggested_actions": []}
        cache.put("camp-1", "loc-cantina", "SETUP", 5, output)
        cache.put("camp-1", "loc-hangar", "RISING", 6, output)
        cache.put("camp-2", "loc-cantina", "SETUP", 5, output)

        cache.invalidate("camp-1")

        assert cache.get("camp-1", "loc-cantina", "SETUP", 5) is None
        assert cache.get("camp-1", "loc-hangar", "RISING", 6) is None
        # camp-2 should still be there
        assert cache.get("camp-2", "loc-cantina", "SETUP", 5) is not None

    def test_overwrite(self, cache):
        """Same key overwrites previous value."""
        output1 = {"director_instructions": "First", "suggested_actions": []}
        output2 = {"director_instructions": "Second", "suggested_actions": []}

        cache.put("camp-1", "loc-cantina", "SETUP", 5, output1)
        cache.put("camp-1", "loc-cantina", "SETUP", 5, output2)

        result = cache.get("camp-1", "loc-cantina", "SETUP", 5)
        assert result is not None
        assert result["director_instructions"] == "Second"

    def test_old_entries_cleaned_up(self, cache):
        """Entries older than 2 turns are cleaned up on put."""
        output = {"director_instructions": "Test", "suggested_actions": []}

        cache.put("camp-1", "loc-cantina", "SETUP", 1, output)
        cache.put("camp-1", "loc-cantina", "SETUP", 2, output)

        # Put at turn 5 should clean up turns < 3
        cache.put("camp-1", "loc-cantina", "SETUP", 5, output)

        assert cache.get("camp-1", "loc-cantina", "SETUP", 1) is None
        assert cache.get("camp-1", "loc-cantina", "SETUP", 2) is None
        assert cache.get("camp-1", "loc-cantina", "SETUP", 5) is not None
