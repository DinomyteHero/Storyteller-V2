"""Tests for Director suggested_actions: validation, fallback, LLM-driven."""
import json
import unittest

from backend.app.constants import SUGGESTED_ACTIONS_MIN, SUGGESTED_ACTIONS_TARGET
from backend.app.models.state import (
    ActionSuggestion,
    GameState,
    ACTION_CATEGORY_SOCIAL,
    ACTION_CATEGORY_EXPLORE,
    ACTION_CATEGORY_COMMIT,
    STRATEGY_TAG_OPTIMAL,
    STRATEGY_TAG_ALTERNATIVE,
    TONE_TAG_PARAGON,
    TONE_TAG_RENEGADE,
    TONE_TAG_INVESTIGATE,
    TONE_TAG_NEUTRAL,
)
from backend.app.core.agents.director import DirectorAgent
from backend.app.core.director_validation import (
    validate_suggestions,
    fallback_suggestions,
    generate_suggestions,
    sanitize_instructions_for_narrator,
    _jaccard_similarity,
)


def _make_state(**kwargs):
    defaults = dict(campaign_id="c1", player_id="p1", current_location="loc-tavern")
    defaults.update(kwargs)
    return GameState(**defaults)


class _FakeLLM:
    """Mock LLM that returns pre-configured responses in sequence."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._call_count = 0

    @property
    def call_count(self):
        return self._call_count

    def complete(self, system_prompt: str, user_prompt: str, json_mode: bool = False, **_kwargs) -> str:
        self._call_count += 1
        if self._responses:
            return self._responses.pop(0)
        return "{}"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """V2.12: Director now calls generate() for plain text output."""
        return self.complete(system_prompt, user_prompt, json_mode=False)


_VALID_LLM_RESPONSE = json.dumps({
    "director_instructions": "Keep the scene tense.",
    "suggested_actions": [
        {
            "label": "Ask the barkeep about rumors",
            "intent_text": "Say: What have you heard lately?",
            "category": "SOCIAL",
            "risk_level": "SAFE",
            "strategy_tag": "OPTIMAL",
            "tone_tag": "PARAGON",
            "intent_style": "empathetic",
            "consequence_hint": "may gain trust",
        },
        {
            "label": "Scan the room for exits",
            "intent_text": "Look around and check all exits",
            "category": "EXPLORE",
            "risk_level": "SAFE",
            "strategy_tag": "OPTIMAL",
            "tone_tag": "INVESTIGATE",
            "intent_style": "probing",
            "consequence_hint": "learn more about layout",
        },
        {
            "label": "Confront the stranger",
            "intent_text": "I walk up and demand answers",
            "category": "COMMIT",
            "risk_level": "RISKY",
            "strategy_tag": "ALTERNATIVE",
            "tone_tag": "RENEGADE",
            "intent_style": "firm",
            "consequence_hint": "may escalate",
        },
    ],
})


class TestDirectorSuggestions(unittest.TestCase):
    """Director: validation, fallback, and LLM-driven planning."""

    def test_validate_suggestions_valid_passes(self):
        """Valid 3 distinct categories + one ALTERNATIVE passes."""
        actions = [
            ActionSuggestion(label="Talk", intent_text="Say: Hi", category=ACTION_CATEGORY_SOCIAL, strategy_tag=STRATEGY_TAG_OPTIMAL),
            ActionSuggestion(label="Look", intent_text="Inspect the area", category=ACTION_CATEGORY_EXPLORE, strategy_tag=STRATEGY_TAG_OPTIMAL),
            ActionSuggestion(label="Act", intent_text="Try something risky", category=ACTION_CATEGORY_COMMIT, strategy_tag=STRATEGY_TAG_ALTERNATIVE),
        ]
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)

    def test_validate_suggestions_wrong_count_fails(self):
        """Only 2 actions fails validation."""
        actions = [
            ActionSuggestion(label="A", intent_text="a", category=ACTION_CATEGORY_SOCIAL),
            ActionSuggestion(label="B", intent_text="b", category=ACTION_CATEGORY_EXPLORE),
        ]
        valid, reason = validate_suggestions(actions)
        self.assertFalse(valid)
        self.assertIn(str(SUGGESTED_ACTIONS_MIN), reason)

    def test_validate_suggestions_missing_core_category_fails(self):
        """Missing one of SOCIAL/EXPLORE/COMMIT fails validation."""
        actions = [
            ActionSuggestion(label="Talk 1", intent_text="Say: Hi", category=ACTION_CATEGORY_SOCIAL, strategy_tag=STRATEGY_TAG_OPTIMAL),
            ActionSuggestion(label="Talk 2", intent_text="Say: Hello", category=ACTION_CATEGORY_SOCIAL, strategy_tag=STRATEGY_TAG_OPTIMAL),
            ActionSuggestion(label="Act", intent_text="Do something", category=ACTION_CATEGORY_COMMIT, strategy_tag=STRATEGY_TAG_ALTERNATIVE),
        ]
        valid, reason = validate_suggestions(actions)
        self.assertFalse(valid)
        self.assertIn("must include", reason.lower())

    def test_validate_suggestions_near_duplicate_intent_fails(self):
        """Very similar intent_text fails (high Jaccard)."""
        actions = [
            ActionSuggestion(label="A", intent_text="Inspect the area carefully", category=ACTION_CATEGORY_SOCIAL, strategy_tag=STRATEGY_TAG_OPTIMAL),
            ActionSuggestion(label="B", intent_text="Inspect the area thoroughly", category=ACTION_CATEGORY_EXPLORE, strategy_tag=STRATEGY_TAG_OPTIMAL),
            ActionSuggestion(label="C", intent_text="Try something else", category=ACTION_CATEGORY_COMMIT, strategy_tag=STRATEGY_TAG_ALTERNATIVE),
        ]
        valid, reason = validate_suggestions(actions)
        self.assertFalse(valid)
        self.assertIn("duplicate", reason.lower())

    def test_validate_suggestions_no_alternative_fails(self):
        """All OPTIMAL fails validation."""
        actions = [
            ActionSuggestion(label="A", intent_text="Say hi", category=ACTION_CATEGORY_SOCIAL, strategy_tag=STRATEGY_TAG_OPTIMAL),
            ActionSuggestion(label="B", intent_text="Look around", category=ACTION_CATEGORY_EXPLORE, strategy_tag=STRATEGY_TAG_OPTIMAL),
            ActionSuggestion(label="C", intent_text="Do action", category=ACTION_CATEGORY_COMMIT, strategy_tag=STRATEGY_TAG_OPTIMAL),
        ]
        valid, reason = validate_suggestions(actions)
        self.assertFalse(valid)
        self.assertIn("ALTERNATIVE", reason)

    def test_fallback_suggestions_returns_target_count_and_core_categories(self):
        """fallback_suggestions returns target count and includes core categories."""
        state = _make_state(current_location="loc-docks")
        state.present_npcs = [{"name": "Sailor", "role": "NPC"}]
        actions = fallback_suggestions(state)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        categories = {a.category for a in actions}
        self.assertTrue({ACTION_CATEGORY_SOCIAL, ACTION_CATEGORY_EXPLORE, ACTION_CATEGORY_COMMIT}.issubset(categories))
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)

    def test_jaccard_similarity(self):
        """Jaccard: identical = 1, disjoint < 1."""
        self.assertAlmostEqual(_jaccard_similarity("hello world", "hello world"), 1.0)
        self.assertAlmostEqual(_jaccard_similarity("a b c", "d e f"), 0.0)
        self.assertGreater(_jaccard_similarity("inspect the area", "inspect the area carefully"), 0.5)

    def test_validate_suggestions_tone_is_not_strictly_mapped(self):
        """Tone tags are UI hints; validation should not strictly map tone->category."""
        actions = [
            ActionSuggestion(label="Talk", intent_text="Say: Hi", category=ACTION_CATEGORY_SOCIAL, tone_tag=TONE_TAG_RENEGADE, strategy_tag=STRATEGY_TAG_OPTIMAL),
            ActionSuggestion(label="Look", intent_text="Inspect the area", category=ACTION_CATEGORY_EXPLORE, strategy_tag=STRATEGY_TAG_OPTIMAL),
            ActionSuggestion(label="Act", intent_text="Try something risky", category=ACTION_CATEGORY_COMMIT, strategy_tag=STRATEGY_TAG_ALTERNATIVE),
        ]
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)

    def test_fallback_has_dialogue_wheel_fields(self):
        """Fallback suggestions include tone_tag, intent_style, consequence_hint."""
        state = _make_state()
        state.present_npcs = [{"name": "Vendor", "role": "NPC"}]
        actions = fallback_suggestions(state)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        cats_tones = [(a.category, a.tone_tag) for a in actions]
        self.assertIn((ACTION_CATEGORY_SOCIAL, TONE_TAG_PARAGON), cats_tones)
        self.assertTrue(all(a.consequence_hint for a in actions))

    # --- LLM-driven tests ---

    def test_plan_no_llm_returns_deterministic_fallback(self):
        """When llm is None, plan() returns fallback_suggestions that pass validation."""
        agent = DirectorAgent(llm=None)
        state = _make_state()
        state.present_npcs = [{"name": "Guard", "role": "NPC"}]
        instructions, actions = agent.plan(state)
        self.assertIsInstance(instructions, str)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)

    def test_plan_llm_returns_instructions_and_fallback(self):
        """V2.12: LLM output is merged into instructions; suggestions are always deterministic fallback."""
        llm = _FakeLLM(["Set the scene in a tense cantina. Emphasize the smuggler's nervousness."])
        agent = DirectorAgent(llm=llm)
        state = _make_state()
        state.present_npcs = [{"name": "Guard", "role": "NPC"}]
        instructions, actions = agent.plan(state)
        self.assertEqual(llm.call_count, 1)
        # LLM text is merged into instructions
        self.assertIn("cantina", instructions)
        # Suggestions are always fallback (deterministic)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)

    def test_plan_llm_any_text_is_accepted(self):
        """V2.12: Director accepts any text as instructions (no JSON parsing, no retries)."""
        llm = _FakeLLM(["This is arbitrary scene direction text."])
        agent = DirectorAgent(llm=llm)
        state = _make_state()
        state.present_npcs = [{"name": "Vendor", "role": "NPC"}]
        instructions, actions = agent.plan(state)
        # Only one LLM call — no retries
        self.assertEqual(llm.call_count, 1)
        # LLM text is merged into instructions
        self.assertIn("arbitrary scene direction", instructions)
        # Fallback suggestions always valid
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)

    def test_plan_llm_empty_response_uses_built_instructions(self):
        """V2.12: When LLM returns empty text, built instructions are used alone."""
        llm = _FakeLLM([""])
        agent = DirectorAgent(llm=llm)
        state = _make_state()
        state.present_npcs = [{"name": "Vendor", "role": "NPC"}]
        instructions, actions = agent.plan(state)
        self.assertEqual(llm.call_count, 1)
        # Built instructions still present (opening scene text)
        self.assertIn("cinematic", instructions.lower())
        # Fallback suggestions always valid
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)

    def test_plan_llm_exception_falls_back(self):
        """When LLM raises an exception, plan() falls back gracefully."""

        class _ExplodingLLM:
            def generate(self, *a, **kw):
                raise RuntimeError("LLM down")

        agent = DirectorAgent(llm=_ExplodingLLM())
        state = _make_state()
        state.present_npcs = [{"name": "Guard", "role": "NPC"}]
        instructions, actions = agent.plan(state)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)

    def test_plan_with_fix_instruction(self):
        """V2.12: fix_instruction param is accepted but Director always returns fallback."""
        llm = _FakeLLM(["Adjust the pacing to be more tense."])
        agent = DirectorAgent(llm=llm)
        state = _make_state()
        state.present_npcs = [{"name": "Guard", "role": "NPC"}]
        instructions, actions = agent.plan(state, fix_instruction="fix something")
        # LLM should be called
        self.assertEqual(llm.call_count, 1)
        # Suggestions are always deterministic fallback
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)


    # --- sanitize_instructions_for_narrator ---

    def test_sanitize_strips_suggestion_guidance(self):
        """sanitize_instructions_for_narrator strips 'Suggested actions should...' lines."""
        instructions = (
            "Keep pacing brisk.\n"
            "Suggested actions should be INTRODUCTORY.\n"
            "End with a decision point."
        )
        result = sanitize_instructions_for_narrator(instructions)
        self.assertNotIn("Suggested actions should", result)
        self.assertIn("Keep pacing brisk", result)
        self.assertIn("decision point", result)

    def test_sanitize_strips_suggested_actions_section(self):
        """sanitize_instructions_for_narrator strips 'Suggested Actions:' sections."""
        instructions = (
            "Scene feels tense.\n\n"
            "Suggested Actions:\n"
            "1. Talk to Vorru\n"
            "2. Check the exits\n\n"
            "End with drama."
        )
        result = sanitize_instructions_for_narrator(instructions)
        self.assertNotIn("Suggested Actions", result)
        self.assertIn("Scene feels tense", result)

    def test_sanitize_strips_scene_description_label(self):
        """sanitize_instructions_for_narrator strips 'Scene Description:' label."""
        instructions = "Scene Description: The cantina was dimly lit."
        result = sanitize_instructions_for_narrator(instructions)
        self.assertNotIn("Scene Description:", result)
        self.assertIn("cantina", result)


class TestV215GenerateSuggestions(unittest.TestCase):
    """V2.15: generate_suggestions with mechanic_result-aware branches."""

    def test_generate_suggestions_is_same_as_fallback(self):
        """generate_suggestions and fallback_suggestions are the same function."""
        self.assertIs(generate_suggestions, fallback_suggestions)

    def test_generate_suggestions_basic(self):
        """generate_suggestions returns target count with valid structure."""
        state = _make_state()
        state.present_npcs = [{"name": "Vendor", "role": "NPC"}]
        actions = generate_suggestions(state)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)

    def test_generate_suggestions_post_combat_success(self):
        """Post-combat success mechanic_result triggers combat success templates."""
        state = _make_state()
        state.present_npcs = [{"name": "Trooper", "role": "NPC"}]
        mechanic = {
            "action_type": "COMBAT",
            "outcome_summary": "Victory! The enemy was defeated.",
            "events": [],
            "narrative_facts": [],
        }
        actions = generate_suggestions(state, mechanic_result=mechanic)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)
        # Post-combat success suggestions should reference relevant actions
        labels_lower = " ".join(a.label.lower() for a in actions)
        self.assertTrue(
            any(kw in labels_lower for kw in ["search", "interrogat", "claim", "press"]),
            f"Expected post-combat keyword in labels: {labels_lower}",
        )

    def test_generate_suggestions_post_combat_failure(self):
        """Post-combat failure mechanic_result triggers retreat-oriented templates."""
        state = _make_state()
        state.present_npcs = [{"name": "Guard", "role": "NPC"}]
        mechanic = {
            "action_type": "COMBAT",
            "success": False,
            "outcome_summary": "You barely escaped.",
            "events": [],
            "narrative_facts": [],
        }
        actions = generate_suggestions(state, mechanic_result=mechanic)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)
        labels_lower = " ".join(a.label.lower() for a in actions)
        self.assertTrue(
            any(kw in labels_lower for kw in ["fall back", "negotiate", "backup", "alternate"]),
            f"Expected retreat keyword in labels: {labels_lower}",
        )

    def test_generate_suggestions_post_stealth_success(self):
        """Post-stealth success mechanic_result triggers stealth success templates."""
        state = _make_state()
        state.present_npcs = [{"name": "Spy", "role": "NPC"}]
        mechanic = {
            "action_type": "STEALTH",
            "outcome_summary": "Success. You slipped past unnoticed.",
            "events": [],
            "narrative_facts": [],
        }
        actions = generate_suggestions(state, mechanic_result=mechanic)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        valid, reason = validate_suggestions(actions)
        self.assertTrue(valid, reason)

    def test_generate_suggestions_exploration_no_npcs(self):
        """No NPCs present triggers exploration-mode suggestions."""
        state = _make_state()
        state.present_npcs = []
        actions = generate_suggestions(state)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        # Exploration mode: EXPLORE + COMMIT only (no SOCIAL — no NPCs to talk to)
        categories = {a.category for a in actions}
        self.assertIn(ACTION_CATEGORY_EXPLORE, categories)
        self.assertIn(ACTION_CATEGORY_COMMIT, categories)
        labels_lower = " ".join(a.label.lower() for a in actions)
        self.assertTrue(
            any(kw in labels_lower for kw in ["search", "observe", "terminal", "moving"]),
            f"Expected exploration keyword in labels: {labels_lower}",
        )

    def test_generate_suggestions_high_stress(self):
        """High stress level (>7) should produce calming option."""
        from unittest.mock import MagicMock
        state = _make_state()
        state.present_npcs = []
        player_mock = MagicMock()
        player_mock.psych_profile = {"stress_level": 8}
        player_mock.background = ""
        state.player = player_mock
        actions = generate_suggestions(state)
        self.assertEqual(len(actions), SUGGESTED_ACTIONS_TARGET)
        # At least one should be a steadying/calming option
        labels_lower = " ".join(a.label.lower() for a in actions)
        self.assertTrue(
            any(kw in labels_lower for kw in ["steady", "breath", "moment", "calm"]),
            f"Expected calming keyword in labels: {labels_lower}",
        )
