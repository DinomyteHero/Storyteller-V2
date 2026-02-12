"""Unit tests for Narrator canon/voice guardrail: Hard Rules in prompt and post-processor for unsupported claims."""
import unittest

from backend.app.core.agents.narrator import (
    _build_prompt,
    _strip_embedded_suggestions,
    _strip_structural_artifacts,
    _truncate_overlong_prose,
    _enforce_pov_consistency,
)
from backend.app.models.state import GameState


class TestHardRulesInPrompt(unittest.TestCase):
    """Hard Rules section must appear in Narrator prompt template."""

    def test_hard_rules_section_present(self) -> None:
        """System prompt includes Hard Rules: Mechanic facts only, cite character specifics, prefer voice."""
        state = GameState(campaign_id="t", player_id="p1", user_input="test")
        system, _ = _build_prompt(state, "(No lore)", "(No voice)")
        self.assertIn("HARD RULES", system)
        # Verify key guardrail rules are present in the prompt
        self.assertIn("LORE", system)
        self.assertIn("VOICE", system)
        self.assertIn("OUTPUT FORMAT", system)


class TestStripEmbeddedSuggestions(unittest.TestCase):
    """Tests for _strip_embedded_suggestions patterns (V2.16: simplified)."""

    def test_strip_numbered_list_at_end(self) -> None:
        """Numbered list at end of text is stripped."""
        text = (
            "The cantina hummed with tension.\n"
            "1. Approach the pilot\n"
            "2. Search the data terminals\n"
            "3. Leave quietly"
        )
        result = _strip_embedded_suggestions(text)
        self.assertNotIn("Approach the pilot", result)
        self.assertIn("cantina hummed", result)

    def test_strip_what_do_you_do_header(self) -> None:
        """'What do you do?' ending is stripped."""
        text = "The enforcer blocked the door.\n\nWhat do you do?"
        result = _strip_embedded_suggestions(text)
        self.assertNotIn("What do you do", result)
        self.assertIn("enforcer blocked", result)

    def test_strip_mid_text_suggestion_block(self) -> None:
        """Suggested Actions header + bulleted list is stripped."""
        text = (
            "The cantina was noisy.\n\n"
            "Suggested Actions:\n"
            "- Approach the pilot\n"
            "- Search the terminals\n"
            "- Leave quietly\n\n"
            "The air smelled of smoke."
        )
        result = _strip_embedded_suggestions(text)
        self.assertNotIn("Suggested Actions", result)
        self.assertNotIn("Approach the pilot", result)
        self.assertIn("cantina was noisy", result)
        self.assertIn("air smelled", result)

    def test_strip_leaves_normal_prose_intact(self) -> None:
        """Normal prose without suggestion patterns is not modified."""
        text = "Corran felt the weight of the blaster at his hip. The cantina was full of noise."
        result = _strip_embedded_suggestions(text)
        self.assertEqual(result, text)

    def test_output_format_rule_in_narrator_prompt(self) -> None:
        """Narrator prompt includes the 'OUTPUT FORMAT' rule and forbids section labels."""
        state = GameState(campaign_id="t", player_id="p1", user_input="test")
        system, _ = _build_prompt(state, "(No lore)", "(No voice)")
        self.assertIn("OUTPUT FORMAT", system)
        self.assertIn("Scene Description", system)  # mentioned as forbidden


class TestMetaNarratorPatterns(unittest.TestCase):
    """V2.13: Expanded meta-narrator pattern stripping."""

    def test_strip_whats_it_gonna_be(self) -> None:
        """'So, what's it gonna be?' is stripped."""
        text = "The enforcer leaned back.\n\nSo, what's it gonna be?"
        result = _enforce_pov_consistency(text)
        self.assertNotIn("gonna be", result)
        self.assertIn("enforcer leaned back", result)

    def test_strip_what_would_you_choose(self) -> None:
        """'What would you choose?' is stripped."""
        text = "Tension filled the room.\n\nWhat would you choose?"
        result = _enforce_pov_consistency(text)
        self.assertNotIn("would you choose", result)
        self.assertIn("Tension filled", result)

    def test_strip_do_you_take_the_job(self) -> None:
        """'Do you take the job?' is stripped."""
        text = "The offer hung in the air.\n\nDo you take the job?"
        result = _enforce_pov_consistency(text)
        self.assertNotIn("Do you take", result)
        self.assertIn("offer hung", result)

    def test_strip_time_to_decide(self) -> None:
        """'Time to decide.' is stripped."""
        text = "The clock was ticking.\n\nTime to decide."
        result = _enforce_pov_consistency(text)
        self.assertNotIn("Time to decide", result)
        self.assertIn("clock was ticking", result)

    def test_strip_and_so_made_choice(self) -> None:
        """'And so, Carth made his choice.' is stripped."""
        text = "The decision was Carth's to make.\n\nAnd so, Carth made his choice."
        result = _enforce_pov_consistency(text)
        self.assertNotIn("made his choice", result)

    def test_strip_three_paths(self) -> None:
        """'Here were three paths...' is stripped."""
        text = "The situation was clear.\n\nHere were three paths: the obvious, the clever, and the risky."
        result = _enforce_pov_consistency(text)
        self.assertNotIn("three paths", result)

    def test_normal_prose_unchanged(self) -> None:
        """Normal prose without meta-narrator patterns is not modified."""
        text = "The cantina hummed with tension. Smoke curled from a deathstick."
        result = _enforce_pov_consistency(text)
        self.assertEqual(result, text)

    def test_npc_reaction_prompt_present(self) -> None:
        """V2.13: Ongoing narrator prompt includes NPC REACTIONS instruction."""
        state = GameState(campaign_id="t", player_id="p1", user_input="test",
                         history=["Turn 1 happened.", "Turn 2 happened."])
        system, _ = _build_prompt(state, "(No lore)", "(No voice)")
        self.assertIn("NPC REACTIONS", system)
        self.assertIn("NOT robots", system)

    def test_mechanic_narration_prompt_present(self) -> None:
        """V2.13: Ongoing narrator prompt includes MECHANIC ACTION NARRATION instruction."""
        state = GameState(campaign_id="t", player_id="p1", user_input="test",
                         history=["Turn 1 happened.", "Turn 2 happened."])
        system, _ = _build_prompt(state, "(No lore)", "(No voice)")
        self.assertIn("MECHANIC ACTION NARRATION", system)


class TestV215ProseStopRule(unittest.TestCase):
    """V2.15: Narrator prompt uses prose-stop rule instead of suggestion request."""

    def test_stop_rule_in_opening_prompt(self) -> None:
        """Opening prompt contains the STOP RULE instruction."""
        state = GameState(campaign_id="t", player_id="p1", user_input="test")
        system, _ = _build_prompt(state, "(No lore)", "(No voice)")
        self.assertIn("STOP RULE", system)
        self.assertIn("Write ONLY narrative prose", system)

    def test_stop_rule_in_ongoing_prompt(self) -> None:
        """Ongoing prompt contains the STOP RULE instruction."""
        state = GameState(campaign_id="t", player_id="p1", user_input="test",
                         history=["Turn 1 happened.", "Turn 2 happened."])
        system, _ = _build_prompt(state, "(No lore)", "(No voice)")
        self.assertIn("STOP RULE", system)
        self.assertIn("Write ONLY narrative prose", system)

    def test_no_suggestion_request_in_prompt(self) -> None:
        """Prompt should NOT contain old suggestion request instructions."""
        state = GameState(campaign_id="t", player_id="p1", user_input="test")
        system, _ = _build_prompt(state, "(No lore)", "(No voice)")
        # Old _suggestion_request asked narrator to generate numbered options
        self.assertNotIn("4 numbered action options", system)
        self.assertNotIn("verb-first imperative", system)


class TestV215StripStructuralArtifacts(unittest.TestCase):
    """V2.15: New stripping patterns for LLM misbehavior."""

    def test_strip_option_inline_blocks(self) -> None:
        """'Option 1 (Paragon): ...' inline choice blocks are stripped."""
        text = (
            "The smuggler leaned forward.\n\n"
            "Option 1 (Paragon): Help the stranger\n"
            "Option 2 (Renegade): Demand payment\n"
            "Option 3 (Investigate): Ask questions"
        )
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Option 1", result)
        self.assertNotIn("Option 2", result)
        self.assertNotIn("Option 3", result)
        self.assertIn("smuggler leaned forward", result)

    def test_strip_scene_continuation(self) -> None:
        """'Scene Continuation' meta-game section is stripped."""
        text = (
            "The cantina fell silent.\n\n"
            "Scene Continuation:\n"
            "Regardless of the player's choice, the scene moves forward with tension."
        )
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Scene Continuation", result)
        self.assertIn("cantina fell silent", result)

    def test_strip_potential_complications(self) -> None:
        """'Potential Complications' meta-game section is stripped."""
        text = (
            "Dust swirled around the landing pad.\n\n"
            "Potential Complications:\n"
            "- The guards might notice the forged documents.\n"
            "- An old rival could appear."
        )
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Potential Complications", result)
        self.assertIn("Dust swirled", result)

    def test_strip_next_steps(self) -> None:
        """'Next Steps' meta-game section is stripped."""
        text = (
            "The transmission ended abruptly.\n\n"
            "Next Steps:\n"
            "The player should investigate the abandoned warehouse."
        )
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Next Steps", result)
        self.assertIn("transmission ended", result)

    def test_strip_stress_level_monitoring(self) -> None:
        """'Stress Level Monitoring' meta-game section is stripped."""
        text = (
            "A blaster bolt scorched the wall.\n\n"
            "Stress Level Monitoring:\n"
            "Current stress: 6/10. Recommend de-escalation options."
        )
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Stress Level", result)
        self.assertIn("blaster bolt scorched", result)

    def test_strip_character_sheet_fields(self) -> None:
        """Character sheet field lines (Name:, Species:, etc.) are stripped."""
        text = (
            "The Twi'lek woman turned to face you.\n\n"
            "Name: Aayla Secura\n"
            "Species: Twi'lek\n"
            "Class: Jedi Guardian\n"
            "Traits: Brave, compassionate"
        )
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Name:", result)
        self.assertNotIn("Species:", result)
        self.assertNotIn("Class:", result)
        self.assertIn("Twi'lek woman turned", result)

    def test_strip_regardless_of_player_choice(self) -> None:
        """'Regardless of player choice' section is stripped."""
        text = (
            "The offer lingered in the smoky air.\n\n"
            "Regardless of player choice:\n"
            "The Hutt's enforcers close in at the end of the scene."
        )
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Regardless of player choice", result)
        self.assertIn("offer lingered", result)

    def test_normal_prose_unchanged(self) -> None:
        """Normal narrative prose is not modified."""
        text = "The star destroyer loomed overhead, its shadow swallowing the outpost."
        result = _strip_structural_artifacts(text)
        self.assertEqual(result.strip(), text)


class TestV215TruncateOverlongProse(unittest.TestCase):
    """V2.15: Word-count truncation safety net."""

    def test_short_prose_unchanged(self) -> None:
        """Prose under 250 words passes through unchanged."""
        text = "The cantina hummed with tension. " * 10  # ~60 words
        result = _truncate_overlong_prose(text)
        self.assertEqual(result, text)

    def test_overlong_prose_truncated(self) -> None:
        """Prose over 250 words is truncated at a sentence boundary."""
        sentences = ["Sentence number %d is here." % i for i in range(80)]
        text = " ".join(sentences)  # ~400 words
        result = _truncate_overlong_prose(text)
        word_count = len(result.split())
        self.assertLessEqual(word_count, 250)
        # Should end at a sentence boundary
        self.assertTrue(result.rstrip().endswith("."))

    def test_exactly_250_words_unchanged(self) -> None:
        """Exactly 250 words passes through unchanged."""
        text = " ".join(["word"] * 250)
        result = _truncate_overlong_prose(text)
        self.assertEqual(result, text)

    def test_truncation_preserves_meaning(self) -> None:
        """Truncated text should not cut mid-sentence."""
        # Build a text with clear sentence boundaries
        text = "The ship landed. " * 100  # ~300 words
        result = _truncate_overlong_prose(text)
        # Should end with period (sentence boundary)
        self.assertTrue(result.rstrip().endswith("."))

    def test_truncation_preserves_paragraph_breaks(self) -> None:
        """V2.16b: Truncation must preserve \\n\\n paragraph separators."""
        para1 = "The cantina buzzed with noise. " * 20  # ~120 words
        para2 = "Outside, the twin suns beat down. " * 30  # ~180 words
        text = para1.strip() + "\n\n" + para2.strip()  # ~300 words total
        result = _truncate_overlong_prose(text)
        # Paragraph break should survive
        self.assertIn("\n\n", result)
        word_count = len(result.split())
        self.assertLessEqual(word_count, 250)

    def test_truncation_short_with_paragraphs_unchanged(self) -> None:
        """V2.16b: Short multi-paragraph text passes through unchanged."""
        text = "First paragraph here.\n\nSecond paragraph here."
        result = _truncate_overlong_prose(text)
        self.assertEqual(result, text)


class TestV216bMetaNarratorLeakage(unittest.TestCase):
    """V2.16b: Meta-narrator instruction leakage patterns."""

    def test_strip_begin_with_sensory(self) -> None:
        """'Begin with a sensory-rich description...' is stripped."""
        text = "The door creaked open.\n\nBegin with a sensory-rich description of the cantina."
        result = _enforce_pov_consistency(text)
        self.assertNotIn("Begin with a sensory", result)
        self.assertIn("door creaked open", result)

    def test_strip_player_can_choose(self) -> None:
        """'The player can choose to...' is stripped."""
        text = "The stranger waited.\n\nThe player can choose to approach or flee."
        result = _enforce_pov_consistency(text)
        self.assertNotIn("player can choose", result)
        self.assertIn("stranger waited", result)

    def test_strip_you_may_choose(self) -> None:
        """'You may choose to...' is stripped."""
        text = "The path diverged.\n\nYou may choose to go left or right."
        result = _enforce_pov_consistency(text)
        self.assertNotIn("You may choose", result)
        self.assertIn("path diverged", result)

    def test_strip_consider_that(self) -> None:
        """'Consider that...' instruction leakage is stripped."""
        text = "The hatch sealed.\n\nConsider that the atmosphere is hostile."
        result = _enforce_pov_consistency(text)
        self.assertNotIn("Consider that", result)
        self.assertIn("hatch sealed", result)

    def test_strip_remember_to(self) -> None:
        """'Remember to...' instruction leakage is stripped."""
        text = "The droid beeped.\n\nRemember to include sensory details."
        result = _enforce_pov_consistency(text)
        self.assertNotIn("Remember to", result)
        self.assertIn("droid beeped", result)


class TestV216bStripInstructionLeakage(unittest.TestCase):
    """V2.16b: _strip_structural_artifacts catches leaked self-instructions."""

    def test_strip_begin_with_instruction(self) -> None:
        """Leaked 'Begin with a sensory-rich...' line is removed."""
        text = "Begin with a sensory-rich description of the docking bay.\nThe engines hummed softly."
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Begin with", result)
        self.assertIn("engines hummed", result)

    def test_strip_describe_the_instruction(self) -> None:
        """Leaked 'Describe the scene...' line is removed."""
        text = "Describe the scene as the player arrives.\nThe cantina was dim and smoky."
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Describe the", result)
        self.assertIn("cantina was dim", result)

    def test_strip_focus_on_instruction(self) -> None:
        """Leaked 'Focus on the tension...' line is removed."""
        text = "Focus on the tension between the two NPCs.\nKessa glared across the table."
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Focus on", result)
        self.assertIn("Kessa glared", result)

    def test_strip_make_sure_instruction(self) -> None:
        """Leaked 'Make sure to...' line is removed."""
        text = "Make sure to include body language.\nVarn's jaw tightened."
        result = _strip_structural_artifacts(text)
        self.assertNotIn("Make sure", result)
        self.assertIn("jaw tightened", result)

    def test_normal_prose_with_similar_words_unchanged(self) -> None:
        """Prose that uses 'begin' naturally in a sentence is not falsely stripped."""
        text = "The ceremony would begin at dawn. Kessa adjusted her cloak."
        result = _strip_structural_artifacts(text)
        # "begin" appears mid-sentence, not at start of line as an instruction
        self.assertIn("begin at dawn", result)
