"""Tests for KG extraction pipeline (mocked LLM)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.app.kg.extractor import (
    ExtractionResult,
    _normalize_extraction,
    _validate_extraction,
    extract_from_chunks,
    store_extraction_result,
)
from backend.app.kg.store import KGStore


SAMPLE_LLM_OUTPUT = json.dumps({
    "entities": [
        {"name": "Luke Skywalker", "entity_type": "CHARACTER",
         "properties": {"species": "Human", "force_sensitive": True, "faction": "Rebel Alliance", "role": "Jedi Knight"}},
        {"name": "Darth Vader", "entity_type": "CHARACTER",
         "properties": {"species": "Human", "force_sensitive": True, "faction": "Galactic Empire", "role": "Sith Lord"}},
        {"name": "Tatooine", "entity_type": "LOCATION",
         "properties": {"location_type": "planet", "region": "Outer Rim", "controlling_faction": "Jabba the Hutt"}},
    ],
    "relationships": [
        {"subject": "Darth Vader", "predicate": "FATHER_OF", "object": "Luke Skywalker",
         "context": "Vader reveals he is Luke's father."},
        {"subject": "Luke Skywalker", "predicate": "MEMBER_OF", "object": "Rebel Alliance",
         "context": "Luke is a key member of the Rebel Alliance."},
    ],
    "chapter_summary": "Luke confronts Darth Vader on Cloud City. Vader reveals his true identity as Luke's father.",
    "key_events": [
        {"name": "Duel on Cloud City", "participants": ["Luke Skywalker", "Darth Vader"],
         "location": "Cloud City", "outcome": "Luke loses his hand and escapes."},
    ],
})


@pytest.fixture
def store():
    s = KGStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def alias_lookup():
    return {
        "luke": "luke_skywalker",
        "luke skywalker": "luke_skywalker",
        "vader": "darth_vader",
        "darth vader": "darth_vader",
        "rebel alliance": "rebel_alliance",
    }


class TestValidateExtraction:
    def test_valid(self):
        data = {"entities": [], "relationships": []}
        ok, reason = _validate_extraction(data)
        assert ok is True

    def test_missing_entities(self):
        ok, reason = _validate_extraction({"relationships": []})
        assert ok is False
        assert "entities" in reason

    def test_not_dict(self):
        ok, reason = _validate_extraction("not a dict")
        assert ok is False


class TestNormalizeExtraction:
    def test_entities_resolved(self, alias_lookup):
        raw = json.loads(SAMPLE_LLM_OUTPUT)
        result = _normalize_extraction(raw, "rebellion", alias_lookup, "Empire Strikes Back")
        entity_ids = [e["id"] for e in result.entities]
        assert "luke_skywalker" in entity_ids
        assert "darth_vader" in entity_ids

    def test_triples_resolved(self, alias_lookup):
        raw = json.loads(SAMPLE_LLM_OUTPUT)
        result = _normalize_extraction(raw, "rebellion", alias_lookup, "Empire Strikes Back")
        father_triples = [t for t in result.triples if t["predicate"] == "FATHER_OF"]
        assert len(father_triples) == 1
        assert father_triples[0]["subject_id"] == "darth_vader"
        assert father_triples[0]["object_id"] == "luke_skywalker"

    def test_events_become_entities(self, alias_lookup):
        raw = json.loads(SAMPLE_LLM_OUTPUT)
        result = _normalize_extraction(raw, "rebellion", alias_lookup, "Empire Strikes Back")
        event_entities = [e for e in result.entities if e["entity_type"] == "EVENT"]
        assert len(event_entities) == 1
        assert "cloud_city" in event_entities[0]["id"] or "duel" in event_entities[0]["id"]

    def test_chapter_summary_preserved(self, alias_lookup):
        raw = json.loads(SAMPLE_LLM_OUTPUT)
        result = _normalize_extraction(raw, "rebellion", alias_lookup, "Empire Strikes Back")
        assert "Luke confronts" in result.chapter_summary

    def test_unknown_predicate_warned(self, alias_lookup):
        raw = {"entities": [], "relationships": [
            {"subject": "Luke", "predicate": "LOVES", "object": "Leia", "context": ""},
        ], "chapter_summary": "", "key_events": []}
        result = _normalize_extraction(raw, "rebellion", alias_lookup, "Book")
        assert any("Unknown predicate" in w for w in result.warnings)

    def test_empty_input(self, alias_lookup):
        raw = {"entities": [], "relationships": [], "chapter_summary": "", "key_events": []}
        result = _normalize_extraction(raw, "rebellion", alias_lookup, "Book")
        assert len(result.entities) == 0
        assert len(result.triples) == 0


class TestStoreExtractionResult:
    def test_stores_entities_and_triples(self, store, alias_lookup):
        raw = json.loads(SAMPLE_LLM_OUTPUT)
        result = _normalize_extraction(raw, "rebellion", alias_lookup, "Empire Strikes Back")
        store_extraction_result(result, store, "Empire Strikes Back", "Chapter 21", "rebellion", chapter_index=21)

        assert store.entity_count() > 0
        assert store.triple_count() > 0

        # Luke should exist
        luke = store.get_entity("luke_skywalker")
        assert luke is not None
        assert luke["canonical_name"] == "Luke Skywalker"

        # FATHER_OF triple should exist
        triples = store.get_triples_for_entity("darth_vader", direction="outgoing")
        father_triples = [t for t in triples if t["predicate"] == "FATHER_OF"]
        assert len(father_triples) >= 1

    def test_stores_chapter_summary(self, store, alias_lookup):
        raw = json.loads(SAMPLE_LLM_OUTPUT)
        result = _normalize_extraction(raw, "rebellion", alias_lookup, "Empire Strikes Back")
        store_extraction_result(result, store, "Empire Strikes Back", "Chapter 21", "rebellion", chapter_index=21)

        summaries = store.get_summaries(summary_type="CHAPTER", book_title="Empire Strikes Back")
        assert len(summaries) == 1
        assert "Luke confronts" in summaries[0]["summary_text"]


class TestExtractFromChunks:
    def test_with_mocked_llm(self, alias_lookup):
        mock_llm = MagicMock()
        # Mock the complete method to return valid JSON
        mock_llm.complete.return_value = SAMPLE_LLM_OUTPUT

        chunks = [
            {"text": "Luke faced Vader on the platform of Cloud City."},
            {"text": "I am your father, Vader said."},
        ]

        with patch("backend.app.kg.extractor.call_with_json_reliability") as mock_reliability:
            mock_reliability.return_value = json.loads(SAMPLE_LLM_OUTPUT)
            result = extract_from_chunks(
                chunks, "Empire Strikes Back", "Chapter 21", "rebellion",
                mock_llm, alias_lookup, known_characters=["Luke Skywalker", "Darth Vader"],
            )

        assert len(result.entities) > 0
        assert len(result.triples) > 0
        assert result.chapter_summary

    def test_empty_chunks_returns_warning(self, alias_lookup):
        mock_llm = MagicMock()
        result = extract_from_chunks([], "Book", "Ch1", "rebellion", mock_llm, alias_lookup)
        assert any("No text" in w for w in result.warnings)
