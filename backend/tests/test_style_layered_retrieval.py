"""Tests for era+genre layered style retrieval and static mappings."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.rag.style_mappings import (
    ERA_STYLE_MAP,
    GENRE_STYLE_MAP,
    era_source_titles,
    genre_source_title,
)
from backend.app.rag.style_retriever import retrieve_style_layered
from backend.app.models.state import GameState


# ---------------------------------------------------------------------------
# style_mappings: era_source_titles
# ---------------------------------------------------------------------------


def test_era_source_titles_rebellion():
    sources = era_source_titles("REBELLION")
    assert "rebellion_style" in sources


def test_era_source_titles_new_republic():
    sources = era_source_titles("NEW_REPUBLIC")
    assert "new_republic_style" in sources


def test_era_source_titles_new_jedi_order():
    sources = era_source_titles("NEW_JEDI_ORDER")
    assert "new_jedi_order_style" in sources


def test_era_source_titles_legacy():
    sources = era_source_titles("LEGACY")
    assert "legacy_style" in sources


def test_era_source_titles_unknown_era_returns_empty():
    assert era_source_titles("OLD_REPUBLIC") == []
    assert era_source_titles("CLONE_WARS") == []
    assert era_source_titles("NONEXISTENT") == []


# ---------------------------------------------------------------------------
# style_mappings: genre_source_title
# ---------------------------------------------------------------------------


def test_genre_source_title_noir():
    assert genre_source_title("noir_detective") == "noir_detective_style"


def test_genre_source_title_cosmic_horror():
    assert genre_source_title("cosmic_horror") == "cosmic_horror_style"


def test_genre_source_title_unknown_returns_none():
    assert genre_source_title("steampunk") is None
    assert genre_source_title("") is None


def test_all_genre_map_entries_have_reverse():
    """Every genre slug should round-trip through the reverse lookup."""
    for source_title, slug in GENRE_STYLE_MAP.items():
        assert genre_source_title(slug) == source_title


# ---------------------------------------------------------------------------
# retrieve_style_layered: fallback to retrieve_style
# ---------------------------------------------------------------------------


@patch("backend.app.rag.style_retriever.retrieve_style")
def test_layered_delegates_when_no_era_no_genre(mock_retrieve):
    """When era_id=None and genre=None, should delegate to retrieve_style."""
    mock_retrieve.return_value = [{"text": "fallback", "source_title": "x", "tags": [], "score": 0.5}]
    result = retrieve_style_layered("test query", era_id=None, genre=None, top_k=3)
    assert mock_retrieve.called
    assert len(result) == 1
    assert result[0]["text"] == "fallback"


# ---------------------------------------------------------------------------
# retrieve_style_layered: graceful degradation
# ---------------------------------------------------------------------------


def test_layered_graceful_degradation_nonexistent_db():
    """With a nonexistent DB path, returns [] and doesn't crash."""
    warnings: list[str] = []
    result = retrieve_style_layered(
        "test query",
        era_id="REBELLION",
        genre="noir_detective",
        top_k=5,
        db_path="/nonexistent/path/lancedb",
        warnings=warnings,
    )
    assert result == []
    assert any("Style retrieval failed" in w for w in warnings)


# ---------------------------------------------------------------------------
# Director agent passes era_id and genre to style retriever
# ---------------------------------------------------------------------------


def _minimal_state(**overrides) -> GameState:
    defaults = {
        "campaign_id": "test",
        "player_id": "p1",
        "turn_number": 1,
        "current_location": "Cantina",
        "user_input": "Look around",
        "campaign": {
            "time_period": "REBELLION",
            "genre": "noir_detective",
            "world_state_json": {},
        },
    }
    defaults.update(overrides)
    return GameState.model_validate(defaults)


def test_director_passes_era_genre_to_style_retriever():
    """DirectorAgent._build_instructions should pass era_id and genre kwargs to style retriever."""
    from backend.app.core.agents.director import DirectorAgent

    captured_kwargs: dict = {}

    def fake_style_retriever(q, k, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    agent = DirectorAgent(llm=None, style_retriever=fake_style_retriever)
    state = _minimal_state()
    agent._build_instructions(state)

    assert captured_kwargs.get("era_id") == "REBELLION"
    assert captured_kwargs.get("genre") == "noir_detective"


def test_director_passes_none_when_no_genre():
    """When campaign has no genre, era_id should still be passed but genre should be None."""
    from backend.app.core.agents.director import DirectorAgent

    captured_kwargs: dict = {}

    def fake_style_retriever(q, k, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    agent = DirectorAgent(llm=None, style_retriever=fake_style_retriever)
    state = _minimal_state(campaign={"time_period": "REBELLION", "world_state_json": {}})
    agent._build_instructions(state)

    assert captured_kwargs.get("era_id") == "REBELLION"
    assert captured_kwargs.get("genre") is None


# ---------------------------------------------------------------------------
# Narrator agent passes era_id and genre to style retriever
# ---------------------------------------------------------------------------


def test_narrator_passes_era_genre_to_style_retriever():
    """NarratorAgent.generate should pass era_id and genre kwargs to style retriever."""
    from backend.app.core.agents.narrator import NarratorAgent

    captured_kwargs: dict = {}

    def fake_style_retriever(q, top_k=3, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    agent = NarratorAgent(style_retriever=fake_style_retriever)
    state = _minimal_state()
    # generate() will fail on LLM call, but style retriever should still be called
    try:
        agent.generate(state)
    except Exception:
        pass

    assert captured_kwargs.get("era_id") == "REBELLION"
    assert captured_kwargs.get("genre") == "noir_detective"
