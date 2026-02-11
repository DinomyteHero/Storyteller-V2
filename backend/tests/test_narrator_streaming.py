"""Tests for Narrator streaming (V2.8 Phase 2D)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.app.core.agents.narrator import NarratorAgent
from backend.app.models.state import GameState


def _minimal_game_state(**overrides) -> GameState:
    """Build a minimal GameState for narrator tests."""
    defaults = {
        "campaign_id": "test-campaign",
        "player_id": "test-player",
        "turn_number": 2,
        "user_input": "I look around",
        "current_location": "loc-cantina",
        "intent": "ACTION",
        "player": {
            "character_id": "test-player",
            "name": "Hero",
            "role": "Player",
            "location_id": "loc-cantina",
            "stats": {},
            "hp_current": 10,
        },
        "campaign": {
            "time_period": "REBELLION",
        },
        "present_npcs": [],
        "history": ["Turn 1: Hero entered the cantina."],
        "mechanic_result": {
            "action_type": "INTERACT",
            "events": [],
            "narrative_facts": ["Player looked around."],
            "time_cost_minutes": 5,
        },
        "director_instructions": "Keep pacing brisk.",
    }
    defaults.update(overrides)
    return GameState.model_validate(defaults)


class TestNarratorGenerateStream:
    """Tests for NarratorAgent.generate_stream()."""

    def test_stream_yields_tokens(self):
        """generate_stream() should yield individual tokens from the LLM."""
        mock_llm = MagicMock()
        mock_llm.complete_stream.return_value = iter(["The ", "cantina ", "was ", "dark."])

        narrator = NarratorAgent(llm=mock_llm)
        gs = _minimal_game_state()

        tokens = list(narrator.generate_stream(gs, kg_context=""))
        assert len(tokens) == 4
        assert tokens[0] == "The "
        assert "".join(tokens) == "The cantina was dark."

    def test_stream_fallback_on_no_llm(self):
        """generate_stream() should yield fallback text when no LLM is available."""
        narrator = NarratorAgent(llm=None)
        gs = _minimal_game_state()

        tokens = list(narrator.generate_stream(gs, kg_context=""))
        # Should yield at least one token (the full fallback text)
        assert len(tokens) >= 1
        full_text = "".join(tokens)
        assert len(full_text) > 10  # Fallback should have some content

    def test_stream_fallback_on_llm_error(self):
        """generate_stream() should fall back to deterministic output on LLM error."""
        mock_llm = MagicMock()
        mock_llm.complete_stream.side_effect = Exception("Connection refused")

        narrator = NarratorAgent(llm=mock_llm)
        gs = _minimal_game_state()

        tokens = list(narrator.generate_stream(gs, kg_context=""))
        assert len(tokens) >= 1
        full_text = "".join(tokens)
        assert len(full_text) > 10

    def test_stream_invalid_action_yields_rephrase(self):
        """generate_stream() should yield rephrase message for invalid actions."""
        narrator = NarratorAgent(llm=MagicMock())
        gs = _minimal_game_state(
            mechanic_result={
                "action_type": "INTERACT",
                "events": [],
                "narrative_facts": [],
                "time_cost_minutes": 0,
                "invalid_action": True,
                "rephrase_message": "That action is unclear. Try rephrasing.",
            }
        )

        tokens = list(narrator.generate_stream(gs, kg_context=""))
        assert len(tokens) == 1
        assert "unclear" in tokens[0].lower() or "rephrase" in tokens[0].lower()

    def test_stream_with_lore_retriever(self):
        """generate_stream() should work with lore retriever."""
        mock_llm = MagicMock()
        mock_llm.complete_stream.return_value = iter(["A ", "scene."])

        mock_lore = MagicMock(return_value=[
            {"text": "The cantina was a den of scum.", "source_title": "ANH", "chunk_id": "c1"},
        ])

        narrator = NarratorAgent(llm=mock_llm, lore_retriever=mock_lore)
        gs = _minimal_game_state()

        tokens = list(narrator.generate_stream(gs, kg_context=""))
        assert len(tokens) == 2
        # Lore retriever should have been called
        mock_lore.assert_called()


class TestLLMClientStream:
    """Tests for LLMClient._call_llm_stream()."""

    def test_stream_parses_ndjson(self):
        """_call_llm_stream should parse NDJSON lines and yield tokens."""
        from backend.llm_client import LLMClient

        # Mock httpx streaming response
        ndjson_lines = [
            json.dumps({"response": "Hello", "done": False}),
            json.dumps({"response": " world", "done": False}),
            json.dumps({"response": "!", "done": True}),
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_lines.return_value = iter(ndjson_lines)
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        client = LLMClient(model="test-model")
        with patch.object(client.client, "stream", return_value=mock_response):
            tokens = list(client._call_llm_stream("test prompt"))

        assert tokens == ["Hello", " world", "!"]

    def test_stream_skips_empty_tokens(self):
        """_call_llm_stream should skip empty response fields."""
        from backend.llm_client import LLMClient

        ndjson_lines = [
            json.dumps({"response": "token", "done": False}),
            json.dumps({"response": "", "done": False}),
            json.dumps({"response": "end", "done": True}),
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_lines.return_value = iter(ndjson_lines)
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        client = LLMClient(model="test-model")
        with patch.object(client.client, "stream", return_value=mock_response):
            tokens = list(client._call_llm_stream("test prompt"))

        assert tokens == ["token", "end"]


class TestAgentLLMCompleteStream:
    """Tests for AgentLLM.complete_stream()."""

    def test_complete_stream_delegates_to_client(self):
        """complete_stream() should delegate to client._call_llm_stream()."""
        from backend.app.core.agents.base import AgentLLM

        mock_client = MagicMock()
        mock_client._call_llm_stream.return_value = iter(["a", "b", "c"])

        agent = AgentLLM("narrator")
        agent._client = mock_client

        tokens = list(agent.complete_stream("system", "user"))
        assert tokens == ["a", "b", "c"]
        mock_client._call_llm_stream.assert_called_once_with("user", "system")
