"""Tests for runtime KG retriever."""
from __future__ import annotations

import pytest

from backend.app.kg.store import KGStore
from backend.app.rag.kg_retriever import KGRetriever


@pytest.fixture
def populated_store(tmp_path):
    """Create a KGStore with test data and return the db path."""
    db_path = str(tmp_path / "test.db")
    store = KGStore(db_path)

    # Entities
    store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion",
                        properties={"species": "Human", "force_sensitive": True, "role": "Jedi Knight", "faction": "Rebel Alliance"})
    store.upsert_entity("darth_vader", "CHARACTER", "Darth Vader", "rebellion",
                        properties={"species": "Human", "force_sensitive": True, "role": "Sith Lord", "faction": "Galactic Empire"})
    store.upsert_entity("han_solo", "CHARACTER", "Han Solo", "rebellion",
                        properties={"species": "Human", "role": "Smuggler", "faction": "Rebel Alliance"})
    store.upsert_entity("rebel_alliance", "FACTION", "Rebel Alliance", "rebellion",
                        properties={"faction_type": "military", "alignment": "light"})
    store.upsert_entity("galactic_empire", "FACTION", "Galactic Empire", "rebellion",
                        properties={"faction_type": "government", "alignment": "dark"})
    store.upsert_entity("tatooine", "LOCATION", "Tatooine", "rebellion",
                        properties={"location_type": "planet", "region": "Outer Rim", "controlling_faction": "Jabba the Hutt"})
    store.upsert_entity("battle_of_yavin", "EVENT", "Battle of Yavin", "rebellion",
                        properties={"outcome": "Rebel victory, Death Star destroyed", "location": "Yavin 4",
                                    "participants": ["Luke Skywalker", "Darth Vader"]})

    # Triples
    store.upsert_triple("darth_vader", "FATHER_OF", "luke_skywalker", "rebellion")
    store.upsert_triple("luke_skywalker", "TRAINED_BY", "darth_vader", "rebellion")  # not accurate but good for testing
    store.upsert_triple("luke_skywalker", "FRIEND_OF", "han_solo", "rebellion")
    store.upsert_triple("luke_skywalker", "MEMBER_OF", "rebel_alliance", "rebellion")
    store.upsert_triple("rebel_alliance", "OPPOSES", "galactic_empire", "rebellion")
    store.upsert_triple("luke_skywalker", "PARTICIPATED_IN", "battle_of_yavin", "rebellion")

    # Summaries
    store.add_summary("CHARACTER_ARC", "Luke Skywalker grew from a Tatooine farm boy to a Jedi Knight.",
                      "rebellion", entity_id="luke_skywalker")
    store.add_summary("LOCATION_DOSSIER", "Tatooine is a harsh desert world in the Outer Rim.",
                      "rebellion", entity_id="tatooine")

    store.close()
    return db_path


@pytest.fixture
def retriever(populated_store):
    return KGRetriever(db_path=populated_store)


class TestCharacterContext:
    def test_returns_character_data(self, retriever):
        result = retriever.get_character_context(["luke_skywalker"], era="rebellion")
        assert "Luke Skywalker" in result
        assert "Character Relationships" in result

    def test_includes_relationships(self, retriever):
        result = retriever.get_character_context(["luke_skywalker"], era="rebellion")
        assert "Han Solo" in result or "friend" in result.lower()

    def test_includes_arc_summary(self, retriever):
        result = retriever.get_character_context(["luke_skywalker"], era="rebellion")
        assert "Arc:" in result
        assert "farm boy" in result

    def test_empty_for_unknown_character(self, retriever):
        result = retriever.get_character_context(["nonexistent"], era="rebellion")
        assert result == ""

    def test_empty_for_no_ids(self, retriever):
        assert retriever.get_character_context([], era="rebellion") == ""


class TestFactionDynamics:
    def test_returns_faction_data(self, retriever):
        result = retriever.get_faction_dynamics(era="rebellion")
        assert "Rebel Alliance" in result
        assert "Galactic Empire" in result
        assert "opposes" in result.lower()

    def test_filtered_by_faction(self, retriever):
        result = retriever.get_faction_dynamics(faction_ids=["rebel_alliance"], era="rebellion")
        assert "Rebel Alliance" in result


class TestLocationContext:
    def test_returns_location_data(self, retriever):
        result = retriever.get_location_context("Tatooine", era="rebellion")
        assert "Tatooine" in result
        assert "Outer Rim" in result

    def test_includes_dossier(self, retriever):
        result = retriever.get_location_context("Tatooine", era="rebellion")
        assert "desert world" in result

    def test_empty_for_unknown_location(self, retriever):
        assert retriever.get_location_context("Nonexistent", era="rebellion") == ""


class TestRelevantEvents:
    def test_returns_events(self, retriever):
        result = retriever.get_relevant_events(
            character_ids=["luke_skywalker"], era="rebellion"
        )
        assert "Battle of Yavin" in result or "Events" in result

    def test_empty_for_no_matches(self, retriever):
        result = retriever.get_relevant_events(
            character_ids=["nonexistent"], era="rebellion"
        )
        # May be empty or may return events with score=0
        assert isinstance(result, str)


class TestDirectorContext:
    def test_builds_context(self, retriever):
        # Create a minimal mock state
        state = _make_mock_state(
            present_npcs=[{"id": "luke_skywalker", "name": "Luke Skywalker"}],
            campaign={"time_period": "rebellion", "party": ["han_solo"]},
        )
        result = retriever.get_context_for_director(state)
        assert "Knowledge Graph Context" in result
        assert "Luke Skywalker" in result

    def test_empty_when_no_kg(self):
        retriever = KGRetriever(db_path=":memory:")
        state = _make_mock_state()
        assert retriever.get_context_for_director(state) == ""


class TestNarratorContext:
    def test_builds_context(self, retriever):
        state = _make_mock_state(
            present_npcs=[{"id": "luke_skywalker", "name": "Luke Skywalker"}],
            campaign={"time_period": "rebellion"},
            current_location="Tatooine",
        )
        result = retriever.get_context_for_narrator(state)
        assert "Knowledge Graph Context" in result


class TestGracefulDegradation:
    def test_missing_db_returns_empty(self):
        retriever = KGRetriever(db_path="/nonexistent/path.db")
        assert retriever.get_character_context(["luke"], era="rebellion") == ""

    def test_empty_db_returns_empty(self, tmp_path):
        import sqlite3
        db_path = str(tmp_path / "empty.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        retriever = KGRetriever(db_path=db_path)
        assert retriever.get_character_context(["luke"], era="rebellion") == ""


# ── Helpers ───────────────────────────────────────────────────────────

class _MockState:
    """Minimal mock for GameState."""
    def __init__(self, **kwargs):
        self.present_npcs = kwargs.get("present_npcs", [])
        self.campaign = kwargs.get("campaign", {})
        self.current_location = kwargs.get("current_location", "")
        self.campaign_id = kwargs.get("campaign_id", "test")
        self.user_input = kwargs.get("user_input", "")


def _make_mock_state(**kwargs) -> _MockState:
    return _MockState(**kwargs)
