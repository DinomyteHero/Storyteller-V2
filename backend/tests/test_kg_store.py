"""Tests for KGStore CRUD operations."""
from __future__ import annotations

import pytest

from backend.app.kg.store import KGStore


@pytest.fixture
def store():
    """In-memory KGStore for testing."""
    s = KGStore(":memory:")
    yield s
    s.close()


class TestEntityCRUD:
    def test_insert_and_get(self, store: KGStore):
        store.upsert_entity(
            "luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion",
            properties={"species": "Human", "force_sensitive": True},
            source_book="A New Hope",
        )
        entity = store.get_entity("luke_skywalker")
        assert entity is not None
        assert entity["canonical_name"] == "Luke Skywalker"
        assert entity["entity_type"] == "CHARACTER"
        assert entity["era"] == "rebellion"
        assert entity["confidence"] == 1.0

    def test_upsert_merges_source_books(self, store: KGStore):
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion", source_book="A New Hope")
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion", source_book="Empire Strikes Back")
        entity = store.get_entity("luke_skywalker")
        import json
        books = json.loads(entity["source_books_json"])
        assert "A New Hope" in books
        assert "Empire Strikes Back" in books

    def test_upsert_merges_properties(self, store: KGStore):
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion",
                            properties={"species": "Human"})
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion",
                            properties={"force_sensitive": True, "role": "Jedi Knight"})
        entity = store.get_entity("luke_skywalker")
        import json
        props = json.loads(entity["properties_json"])
        assert props["species"] == "Human"
        assert props["force_sensitive"] is True
        assert props["role"] == "Jedi Knight"

    def test_upsert_keeps_highest_confidence(self, store: KGStore):
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion", confidence=0.5)
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion", confidence=0.9)
        entity = store.get_entity("luke_skywalker")
        assert entity["confidence"] == 0.9

    def test_get_entities_by_type(self, store: KGStore):
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion")
        store.upsert_entity("tatooine", "LOCATION", "Tatooine", "rebellion")
        store.upsert_entity("han_solo", "CHARACTER", "Han Solo", "rebellion")
        characters = store.get_entities_by_type("CHARACTER", era="rebellion")
        assert len(characters) == 2
        names = [c["canonical_name"] for c in characters]
        assert "Han Solo" in names
        assert "Luke Skywalker" in names

    def test_entity_count(self, store: KGStore):
        assert store.entity_count() == 0
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion")
        store.upsert_entity("tatooine", "LOCATION", "Tatooine", "rebellion")
        assert store.entity_count() == 2
        assert store.entity_count(era="rebellion") == 2
        assert store.entity_count(era="clone_wars") == 0

    def test_get_nonexistent_entity(self, store: KGStore):
        assert store.get_entity("nonexistent") is None


class TestTripleCRUD:
    def test_insert_and_get(self, store: KGStore):
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion")
        store.upsert_entity("obi_wan_kenobi", "CHARACTER", "Obi-Wan Kenobi", "rebellion")
        store.upsert_triple("luke_skywalker", "TRAINED_BY", "obi_wan_kenobi", "rebellion",
                            source_book="A New Hope")
        triples = store.get_triples_for_entity("luke_skywalker", direction="outgoing")
        assert len(triples) == 1
        assert triples[0]["predicate"] == "TRAINED_BY"
        assert triples[0]["object_name"] == "Obi-Wan Kenobi"

    def test_upsert_increments_weight(self, store: KGStore):
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion")
        store.upsert_entity("obi_wan_kenobi", "CHARACTER", "Obi-Wan Kenobi", "rebellion")
        store.upsert_triple("luke_skywalker", "TRAINED_BY", "obi_wan_kenobi", "rebellion")
        store.upsert_triple("luke_skywalker", "TRAINED_BY", "obi_wan_kenobi", "rebellion")
        store.upsert_triple("luke_skywalker", "TRAINED_BY", "obi_wan_kenobi", "rebellion")
        triples = store.get_triples_for_entity("luke_skywalker", direction="outgoing")
        assert triples[0]["weight"] == 3.0

    def test_direction_both(self, store: KGStore):
        store.upsert_entity("luke_skywalker", "CHARACTER", "Luke Skywalker", "rebellion")
        store.upsert_entity("darth_vader", "CHARACTER", "Darth Vader", "rebellion")
        store.upsert_triple("darth_vader", "FATHER_OF", "luke_skywalker", "rebellion")
        triples = store.get_triples_for_entity("luke_skywalker", direction="both")
        assert len(triples) == 1
        assert triples[0]["subject_name"] == "Darth Vader"

    def test_get_by_predicate(self, store: KGStore):
        store.upsert_entity("rebel_alliance", "FACTION", "Rebel Alliance", "rebellion")
        store.upsert_entity("galactic_empire", "FACTION", "Galactic Empire", "rebellion")
        store.upsert_triple("rebel_alliance", "OPPOSES", "galactic_empire", "rebellion")
        triples = store.get_triples_by_predicate("OPPOSES", era="rebellion")
        assert len(triples) == 1
        assert triples[0]["subject_name"] == "Rebel Alliance"
        assert triples[0]["object_name"] == "Galactic Empire"

    def test_triple_count(self, store: KGStore):
        store.upsert_entity("a", "CHARACTER", "A", "rebellion")
        store.upsert_entity("b", "CHARACTER", "B", "rebellion")
        assert store.triple_count() == 0
        store.upsert_triple("a", "FRIEND_OF", "b", "rebellion")
        assert store.triple_count() == 1
        assert store.triple_count(era="rebellion") == 1


class TestSummaries:
    def test_add_and_get(self, store: KGStore):
        store.add_summary(
            "CHAPTER", "Luke discovers the Force.", "rebellion",
            book_title="A New Hope", chapter_title="Chapter 1", chapter_index=1,
        )
        summaries = store.get_summaries(summary_type="CHAPTER", book_title="A New Hope")
        assert len(summaries) == 1
        assert summaries[0]["summary_text"] == "Luke discovers the Force."
        assert summaries[0]["chapter_index"] == 1

    def test_filter_by_entity(self, store: KGStore):
        store.add_summary("CHARACTER_ARC", "Luke's journey from farm boy to Jedi.", "rebellion",
                          entity_id="luke_skywalker", book_title="A New Hope")
        store.add_summary("CHARACTER_ARC", "Han's reluctant heroism.", "rebellion",
                          entity_id="han_solo", book_title="A New Hope")
        summaries = store.get_summaries(entity_id="luke_skywalker")
        assert len(summaries) == 1
        assert "Luke" in summaries[0]["summary_text"]


class TestCheckpoints:
    def test_default_pending(self, store: KGStore):
        assert store.get_checkpoint_status("Book1") == "pending"

    def test_set_and_get(self, store: KGStore):
        store.set_checkpoint("Book1", "in_progress", chapter_title="Ch1")
        assert store.get_checkpoint_status("Book1", "Ch1") == "in_progress"
        store.set_checkpoint("Book1", "completed", chapter_title="Ch1")
        assert store.get_checkpoint_status("Book1", "Ch1") == "completed"

    def test_upsert_checkpoint(self, store: KGStore):
        store.set_checkpoint("Book1", "in_progress", chapter_title="Ch1")
        store.set_checkpoint("Book1", "failed", chapter_title="Ch1", error="LLM timeout")
        assert store.get_checkpoint_status("Book1", "Ch1") == "failed"

    def test_book_level_checkpoint(self, store: KGStore):
        store.set_checkpoint("Book1", "completed", phase="synthesis")
        assert store.get_checkpoint_status("Book1", phase="synthesis") == "completed"
