"""Tests for narrator style-chunk wiring: _build_prompt accepts and uses style chunks."""
from __future__ import annotations


from backend.app.models.state import GameState
from backend.app.core.agents.narrator import _build_prompt, NarratorAgent
from backend.app.rag.style_retriever import retrieve_style


def _minimal_state(**overrides) -> GameState:
    """Build a minimal GameState suitable for prompt tests (no DB, no LLM)."""
    defaults = {
        "campaign_id": "test",
        "player_id": "p1",
        "turn_number": 1,
        "current_location": "Cantina",
        "user_input": "Look around",
        "campaign": {
            "world_state_json": {
                "ledger": {
                    "established_facts": [],
                    "open_threads": [],
                    "active_goals": [],
                    "constraints": [],
                    "tone_tags": ["neutral"],
                    "active_themes": [],
                },
            },
        },
    }
    defaults.update(overrides)
    return GameState.model_validate(defaults)


# ---------------------------------------------------------------------------
# _build_prompt with style_chunks
# ---------------------------------------------------------------------------


def test_build_prompt_with_style_chunks():
    """Style chunk text should appear in the user prompt when provided."""
    state = _minimal_state()
    style_chunks = [
        {
            "text": "Use short punchy sentences.",
            "source_title": "noir",
            "tags": ["noir"],
            "score": 0.9,
        }
    ]
    system_prompt, user_prompt = _build_prompt(
        state,
        lore_chunks=[],
        voice_snippets_by_char={},
        style_chunks=style_chunks,
    )
    assert "short punchy sentences" in user_prompt


def test_build_prompt_without_style_chunks():
    """Prompt should build without error when style_chunks is None or empty."""
    state = _minimal_state()

    # With None
    system_prompt, user_prompt = _build_prompt(
        state,
        lore_chunks=[],
        voice_snippets_by_char={},
        style_chunks=None,
    )
    assert isinstance(system_prompt, str)
    assert isinstance(user_prompt, str)

    # With empty list
    system_prompt2, user_prompt2 = _build_prompt(
        state,
        lore_chunks=[],
        voice_snippets_by_char={},
        style_chunks=[],
    )
    assert isinstance(system_prompt2, str)
    assert isinstance(user_prompt2, str)


# ---------------------------------------------------------------------------
# NarratorAgent accepts style_retriever
# ---------------------------------------------------------------------------


def test_narrator_agent_init_accepts_style_retriever():
    """NarratorAgent can be constructed with a style_retriever callable."""
    dummy_retriever = lambda q, top_k=3: []
    agent = NarratorAgent(style_retriever=dummy_retriever)
    assert agent._style_retriever is not None


# ---------------------------------------------------------------------------
# retrieve_style function signature
# ---------------------------------------------------------------------------


def test_retrieve_style_tags_filter():
    """retrieve_style() accepts style_tags and returns [] when DB path does not exist."""
    # Use a non-existent path -- function should return [] gracefully
    result = retrieve_style(
        query="test query",
        top_k=3,
        db_path="/nonexistent/path/lancedb",
        style_tags=["noir", "gritty"],
    )
    assert result == []
