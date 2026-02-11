"""Tests for the SuggestionRefiner node."""
import json
import unittest
from unittest.mock import MagicMock, patch

from backend.app.constants import SUGGESTED_ACTIONS_TARGET
from backend.app.core.nodes.suggestion_refiner import (
    _apply_stat_gating,
    _build_user_prompt,
    _build_stat_gated_options,
    _parse_and_validate,
    _to_action_suggestions,
    make_suggestion_refiner_node,
)
from backend.app.models.state import ActionSuggestion, GameState


# Emergency fallback labels (must match the node's _emergency_fallback)
_EMERGENCY_LABELS = {
    "Tell me more about what's going on.",
    "What aren't you telling me?",
    "Enough talk. Let's get this done.",
    "I'll look around first.",
}


def _make_state(**overrides) -> dict:
    """Build a minimal pipeline state dict for testing."""
    base = {
        "campaign_id": "test-campaign",
        "player_id": "test-player",
        "user_input": "Look around",
        "current_location": "loc-cantina",
        "present_npcs": [
            {"name": "Kessa", "role": "informant"},
            {"name": "Varn", "role": "bouncer"},
        ],
        "known_npcs": ["Kessa"],
        "final_text": "The cantina was dimly lit. Kessa leaned forward across the bar.",
        "suggested_actions": [],  # Director no longer produces suggestions
        "warnings": [],
    }
    base.update(overrides)
    return base


def _valid_llm_json() -> str:
    """Return valid JSON output matching the expected schema."""
    return json.dumps([
        {"text": "Reassure Kessa that you mean no harm", "tone": "PARAGON", "meaning": "reveal_values"},
        {"text": "Ask Kessa about the recent shipments", "tone": "INVESTIGATE", "meaning": "probe_belief"},
        {"text": "Slam the table and demand answers", "tone": "RENEGADE", "meaning": "set_boundary"},
        {"text": "Scan the exits for a quick escape", "tone": "NEUTRAL", "meaning": "pragmatic"},
    ])


def _is_emergency_fallback(result: dict) -> bool:
    """Check if the result contains emergency fallback suggestions."""
    labels = {a["label"] for a in result.get("suggested_actions", [])}
    return labels == _EMERGENCY_LABELS


class TestBuildUserPrompt(unittest.TestCase):
    """Test prompt construction for the refiner."""

    def test_includes_prose(self):
        prompt = _build_user_prompt(
            "The cantina hummed.", "the cantina", ["Kessa (informant)"], None
        )
        self.assertIn("PROSE:\nThe cantina hummed.", prompt)
        self.assertIn("SCENE: the cantina", prompt)
        self.assertIn("NPCs: Kessa (informant)", prompt)

    def test_no_npcs(self):
        prompt = _build_user_prompt("Quiet streets.", "the streets", [], None)
        self.assertIn("NPCs: No NPCs present", prompt)

    def test_mechanic_summary(self):
        prompt = _build_user_prompt("Battle.", "the bay", [], "combat succeeded")
        self.assertIn("AFTER: combat succeeded", prompt)

    def test_no_mechanic(self):
        prompt = _build_user_prompt("Quiet.", "here", [], None)
        self.assertNotIn("AFTER:", prompt)

    def test_includes_director_intent(self):
        prompt = _build_user_prompt(
            "Quiet.", "here", [], None, director_intent="Escalate primary conflict this turn"
        )
        self.assertIn("DIRECTOR INTENT: Escalate primary conflict this turn", prompt)


class TestStatGating(unittest.TestCase):
    def test_builds_stat_gated_options(self):
        gs = GameState.model_validate(
            {
                "campaign_id": "c1",
                "player_id": "p1",
                "campaign": {"world_state_json": {"alignment": {"paragon_renegade": -12}}},
                "player": {"character_id": "p1", "name": "PC", "stats": {"Charisma": 7, "Tech": 2, "Combat": 8}},
            }
        )
        opts = _build_stat_gated_options(gs)
        labels = [o.label for o in opts]
        self.assertTrue(any("[PERSUADE]" in s for s in labels))
        self.assertTrue(any("[COMBAT]" in s for s in labels))
        self.assertTrue(any("[RENEGADE]" in s for s in labels))

    def test_apply_stat_gating_replaces_first_option(self):
        gs = GameState.model_validate(
            {
                "campaign_id": "c1",
                "player_id": "p1",
                "campaign": {"world_state_json": {"alignment": {"paragon_renegade": 10}}},
                "player": {"character_id": "p1", "name": "PC", "stats": {"Charisma": 9}},
            }
        )
        baseline = [
            ActionSuggestion(label="A", intent_text="A"),
            ActionSuggestion(label="B", intent_text="B"),
            ActionSuggestion(label="C", intent_text="C"),
            ActionSuggestion(label="D", intent_text="D"),
        ]
        result = _apply_stat_gating(gs, baseline)
        self.assertEqual(len(result), 4)
        self.assertNotEqual(result[0].label, "A")


class TestParseAndValidate(unittest.TestCase):
    """Test JSON parsing and validation."""

    def test_valid_json(self):
        raw = _valid_llm_json()
        result = _parse_and_validate(raw, {"Kessa", "Varn"})
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)

    def test_invalid_json(self):
        self.assertIsNone(_parse_and_validate("not json", set()))

    def test_two_items_rejected(self):
        """2 valid items is below the minimum of 3."""
        raw = json.dumps([
            {"label": "Do something", "tone": "PARAGON"},
            {"label": "Do another thing", "tone": "RENEGADE"},
        ])
        self.assertIsNone(_parse_and_validate(raw, set()))

    def test_three_items_padded_to_four(self):
        """3 valid items accepted and padded to SUGGESTED_ACTIONS_TARGET."""
        raw = json.dumps([
            {"text": "Ask about the situation", "tone": "PARAGON", "meaning": "seek_history"},
            {"text": "Challenge their story", "tone": "INVESTIGATE", "meaning": "challenge_premise"},
            {"text": "Threaten them into talking", "tone": "RENEGADE", "meaning": "set_boundary"},
        ])
        result = _parse_and_validate(raw, set())
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)
        # 4th item should be the generic pad
        self.assertEqual(result[3]["tone"], "NEUTRAL")

    def test_five_items_trimmed_to_four(self):
        """5 valid items accepted and trimmed to SUGGESTED_ACTIONS_TARGET."""
        raw = json.dumps([
            {"text": "A", "tone": "PARAGON"},
            {"text": "B", "tone": "INVESTIGATE"},
            {"text": "C", "tone": "RENEGADE"},
            {"text": "D", "tone": "NEUTRAL"},
            {"text": "E", "tone": "PARAGON"},
        ])
        result = _parse_and_validate(raw, set())
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)

    def test_missing_label(self):
        raw = json.dumps([
            {"tone": "PARAGON"},
            {"label": "B", "tone": "INVESTIGATE"},
            {"label": "C", "tone": "RENEGADE"},
            {"label": "D", "tone": "NEUTRAL"},
        ])
        # 3 valid items → padded to 4
        result = _parse_and_validate(raw, set())
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)

    def test_missing_tone(self):
        raw = json.dumps([
            {"label": "A"},
            {"label": "B", "tone": "INVESTIGATE"},
            {"label": "C", "tone": "RENEGADE"},
            {"label": "D", "tone": "NEUTRAL"},
        ])
        # 3 valid items → padded to 4
        result = _parse_and_validate(raw, set())
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)

    def test_invalid_tone_value(self):
        raw = json.dumps([
            {"label": "A", "tone": "EVIL"},
            {"label": "B", "tone": "INVESTIGATE"},
            {"label": "C", "tone": "RENEGADE"},
            {"label": "D", "tone": "NEUTRAL"},
        ])
        # 3 valid items → padded to 4
        result = _parse_and_validate(raw, set())
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)

    def test_empty_label(self):
        raw = json.dumps([
            {"label": "", "tone": "PARAGON"},
            {"label": "B", "tone": "INVESTIGATE"},
            {"label": "C", "tone": "RENEGADE"},
            {"label": "D", "tone": "NEUTRAL"},
        ])
        # 3 valid items → padded to 4
        result = _parse_and_validate(raw, set())
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)

    def test_not_a_list(self):
        """Single object (not 3+) still returns None — count mismatch."""
        raw = json.dumps({"label": "A", "tone": "PARAGON"})
        self.assertIsNone(_parse_and_validate(raw, set()))

    # --- V3.0 hardened parsing tests ---

    def test_think_block_wrapped_array(self):
        """qwen3 <think> block before a valid JSON array."""
        inner = _valid_llm_json()
        raw = f"<think>Let me think about KOTOR dialogue options...</think>\n{inner}"
        result = _parse_and_validate(raw, {"Kessa", "Varn"})
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)

    def test_think_block_wrapped_single_object(self):
        """qwen3 <think> block before a single JSON object → None (count mismatch)."""
        raw = '<think>One response...</think>\n{"text": "Hello there", "tone": "PARAGON"}'
        result = _parse_and_validate(raw, set())
        self.assertIsNone(result)  # 1 item < 3

    def test_markdown_fenced_array(self):
        """Markdown code fence around valid array."""
        inner = _valid_llm_json()
        raw = f"```json\n{inner}\n```"
        result = _parse_and_validate(raw, {"Kessa", "Varn"})
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)

    def test_text_key_accepted(self):
        """V2.18 'text' key normalized to 'label'."""
        raw = json.dumps([
            {"text": "What happened here?", "tone": "PARAGON", "meaning": "seek_history"},
            {"text": "Who told you that?", "tone": "INVESTIGATE", "meaning": "challenge_premise"},
            {"text": "Give me the datapad.", "tone": "RENEGADE", "meaning": "set_boundary"},
            {"text": "Save the talk. What's the job?", "tone": "NEUTRAL", "meaning": "pragmatic"},
        ])
        result = _parse_and_validate(raw, set())
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 4)
        # Should be normalized to "label" key
        self.assertEqual(result[0]["label"], "What happened here?")

    def test_array_extraction_from_noisy_output(self):
        """Array can be extracted even with leading/trailing text."""
        inner = _valid_llm_json()
        raw = f"Here are the options:\n{inner}\nI hope these work."
        result = _parse_and_validate(raw, {"Kessa", "Varn"})
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)

    def test_wrapped_dict_with_suggestions_key(self):
        """Dict wrapping with 'suggestions' key is unwrapped."""
        items = json.loads(_valid_llm_json())
        raw = json.dumps({"suggestions": items})
        result = _parse_and_validate(raw, {"Kessa", "Varn"})
        self.assertIsNotNone(result)
        self.assertEqual(len(result), SUGGESTED_ACTIONS_TARGET)

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_and_validate("", set()))
        self.assertIsNone(_parse_and_validate("   ", set()))

    def test_tone_case_insensitive(self):
        """Tones are normalized to uppercase."""
        raw = json.dumps([
            {"text": "A", "tone": "paragon"},
            {"text": "B", "tone": "investigate"},
            {"text": "C", "tone": "renegade"},
            {"text": "D", "tone": "neutral"},
        ])
        result = _parse_and_validate(raw, set())
        self.assertIsNotNone(result)
        self.assertEqual(result[0]["tone"], "PARAGON")
        self.assertEqual(result[3]["tone"], "NEUTRAL")

    def test_single_object_with_extra_fields(self):
        """The exact bug: model returns a single dialogue exchange object with extra fields."""
        raw = json.dumps({
            "text": "So you're the one who calls the shots here?",
            "tone": "INVESTIGATE",
            "meaning": "probe_belief",
            "subtext": "Establishing authority dynamics",
            "agreement": "neutral",
            "response": "General Veers stiffened slightly, then nodded.",
        })
        result = _parse_and_validate(raw, set())
        self.assertIsNone(result)  # 1 item < 3


class TestToActionSuggestions(unittest.TestCase):
    """Test conversion from raw JSON items to ActionSuggestion."""

    def test_basic_conversion(self):
        # _to_action_suggestions expects "label" key (normalized by _parse_and_validate)
        items = _parse_and_validate(_valid_llm_json(), set())
        self.assertIsNotNone(items)
        suggestions = _to_action_suggestions(items)
        self.assertEqual(len(suggestions), 4)
        self.assertIsInstance(suggestions[0], ActionSuggestion)
        self.assertEqual(suggestions[0].tone_tag, "PARAGON")
        self.assertEqual(suggestions[1].tone_tag, "INVESTIGATE")

    def test_tone_override(self):
        items = [
            {"label": "Search the area", "tone": "RENEGADE"},
            {"label": "Ask about rumors", "tone": "PARAGON"},
            {"label": "Demand payment", "tone": "INVESTIGATE"},
            {"label": "Wait quietly", "tone": "NEUTRAL"},
        ]
        suggestions = _to_action_suggestions(items)
        # LLM's explicit tone assignment should override classify_suggestion defaults
        self.assertEqual(suggestions[0].tone_tag, "RENEGADE")
        self.assertEqual(suggestions[1].tone_tag, "PARAGON")


class TestSuggestionRefinerNode(unittest.TestCase):
    """Integration tests for the full node."""

    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", False)
    def test_disabled_feature_flag(self):
        """When feature flag is off, emergency fallback is returned."""
        node = make_suggestion_refiner_node()
        state = _make_state()
        result = node(state)
        self.assertTrue(_is_emergency_fallback(result))
        self.assertIn("player_responses", result)
        self.assertEqual(len(result["player_responses"]), SUGGESTED_ACTIONS_TARGET)

    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_no_final_text_uses_emergency(self):
        """When there's no final_text, emergency fallback is used."""
        node = make_suggestion_refiner_node()
        state = _make_state(final_text="")
        result = node(state)
        self.assertTrue(_is_emergency_fallback(result))

    @patch("backend.app.core.nodes.suggestion_refiner.AgentLLM")
    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_happy_path_overwrites_suggestions(self, MockLLM):
        """Valid LLM output produces LLM-sourced suggestions."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = _valid_llm_json()
        MockLLM.return_value = mock_llm

        node = make_suggestion_refiner_node()
        state = _make_state()
        result = node(state)

        # Suggestions should come from LLM
        labels = [a["label"] for a in result["suggested_actions"]]
        self.assertTrue(any("Kessa" in l for l in labels))
        self.assertFalse(_is_emergency_fallback(result))

    @patch("backend.app.core.nodes.suggestion_refiner.AgentLLM")
    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_llm_exception_uses_emergency(self, MockLLM):
        """When LLM raises, emergency fallback is used."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = RuntimeError("Ollama down")
        MockLLM.return_value = mock_llm

        node = make_suggestion_refiner_node()
        state = _make_state()
        result = node(state)

        self.assertTrue(_is_emergency_fallback(result))
        self.assertTrue(any("SuggestionRefiner" in w for w in result.get("warnings", [])))

    @patch("backend.app.core.nodes.suggestion_refiner.AgentLLM")
    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_invalid_json_both_attempts_uses_emergency(self, MockLLM):
        """When LLM returns bad JSON on both attempts, emergency fallback is used."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = "This is not JSON at all"
        MockLLM.return_value = mock_llm

        node = make_suggestion_refiner_node()
        state = _make_state()
        result = node(state)

        self.assertTrue(_is_emergency_fallback(result))
        # LLM should have been called twice (original + retry)
        self.assertEqual(mock_llm.complete.call_count, 2)

    @patch("backend.app.core.nodes.suggestion_refiner.AgentLLM")
    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_retry_succeeds_on_second_attempt(self, MockLLM):
        """First call returns bad JSON, retry returns valid array."""
        mock_llm = MagicMock()
        bad_output = json.dumps({"text": "Hello", "tone": "PARAGON", "response": "NPC speaks..."})
        mock_llm.complete.side_effect = [bad_output, _valid_llm_json()]
        MockLLM.return_value = mock_llm

        node = make_suggestion_refiner_node()
        state = _make_state()
        result = node(state)

        # Should succeed on retry
        self.assertFalse(_is_emergency_fallback(result))
        labels = [a["label"] for a in result["suggested_actions"]]
        self.assertTrue(any("Kessa" in l for l in labels))
        self.assertEqual(mock_llm.complete.call_count, 2)

    @patch("backend.app.core.nodes.suggestion_refiner.AgentLLM")
    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_single_object_triggers_retry(self, MockLLM):
        """The exact bug: model returns single dialogue exchange, retry fixes it."""
        mock_llm = MagicMock()
        # Exact output shape from the user's error log
        bad_output = json.dumps({
            "text": "So you're the one who calls the shots here?",
            "tone": "INVESTIGATE",
            "meaning": "probe_belief",
            "subtext": "Establishing authority dynamics",
            "agreement": "neutral",
            "response": "General Veers stiffened slightly, then nodded.",
        })
        mock_llm.complete.side_effect = [bad_output, _valid_llm_json()]
        MockLLM.return_value = mock_llm

        node = make_suggestion_refiner_node()
        state = _make_state()
        result = node(state)

        # Retry should fix it
        self.assertFalse(_is_emergency_fallback(result))
        self.assertEqual(mock_llm.complete.call_count, 2)

    @patch("backend.app.core.nodes.suggestion_refiner.AgentLLM")
    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_wrong_count_triggers_retry(self, MockLLM):
        """When LLM returns too few items, retry is attempted."""
        mock_llm = MagicMock()
        two_items = json.dumps([
            {"text": "A", "tone": "PARAGON"},
            {"text": "B", "tone": "RENEGADE"},
        ])
        mock_llm.complete.side_effect = [two_items, _valid_llm_json()]
        MockLLM.return_value = mock_llm

        node = make_suggestion_refiner_node()
        state = _make_state()
        result = node(state)

        # Retry should fix it
        self.assertFalse(_is_emergency_fallback(result))
        self.assertEqual(mock_llm.complete.call_count, 2)

    @patch("backend.app.core.nodes.suggestion_refiner.AgentLLM")
    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_tone_diversity_enforced(self, MockLLM):
        """Output suggestions have PARAGON/INVESTIGATE/RENEGADE diversity."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = _valid_llm_json()
        MockLLM.return_value = mock_llm

        node = make_suggestion_refiner_node()
        state = _make_state()
        result = node(state)

        tones = {a["tone_tag"] for a in result["suggested_actions"]}
        self.assertIn("PARAGON", tones)
        self.assertIn("INVESTIGATE", tones)
        self.assertIn("RENEGADE", tones)

    @patch("backend.app.core.nodes.suggestion_refiner.AgentLLM")
    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_mechanic_result_context(self, MockLLM):
        """Mechanic result is included in prompt when present."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = _valid_llm_json()
        MockLLM.return_value = mock_llm

        node = make_suggestion_refiner_node()
        state = _make_state(mechanic_result={
            "action_type": "COMBAT",
            "success": True,
            "outcome_summary": "Victory",
        })
        result = node(state)

        # Check that the LLM was called with mechanic context
        call_args = mock_llm.complete.call_args_list[0]
        user_prompt = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("user_prompt", "")
        self.assertIn("AFTER: combat succeeded", user_prompt)


    @patch("backend.app.core.nodes.suggestion_refiner.AgentLLM")
    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_lazy_init_retries_until_success(self, MockLLM):
        """LLM init failure on first call retries on subsequent calls."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Ollama not running")
            mock_llm = MagicMock()
            mock_llm.complete.return_value = _valid_llm_json()
            return mock_llm

        MockLLM.side_effect = side_effect

        node = make_suggestion_refiner_node()
        state = _make_state()

        # First call: AgentLLM init fails → emergency fallback
        result1 = node(state)
        self.assertTrue(_is_emergency_fallback(result1))

        # Second call: AgentLLM init succeeds → refined suggestions
        result2 = node(state)
        labels = [a["label"] for a in result2["suggested_actions"]]
        self.assertTrue(any("Kessa" in l for l in labels))

    @patch("backend.app.core.nodes.suggestion_refiner.ENABLE_SUGGESTION_REFINER", True)
    def test_emergency_fallback_has_correct_structure(self):
        """Emergency fallback produces valid suggestions and player_responses."""
        node = make_suggestion_refiner_node()
        # No LLM available → emergency fallback
        state = _make_state()
        result = node(state)

        self.assertEqual(len(result["suggested_actions"]), SUGGESTED_ACTIONS_TARGET)
        self.assertEqual(len(result["player_responses"]), SUGGESTED_ACTIONS_TARGET)
        tones = {a["tone_tag"] for a in result["suggested_actions"]}
        self.assertEqual(tones, {"PARAGON", "INVESTIGATE", "RENEGADE", "NEUTRAL"})


if __name__ == "__main__":
    unittest.main()
