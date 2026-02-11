"""Tests for ContextBudget trimming behavior."""
import os
import sys
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.context_budget import build_context


def _make_parts():
    style_chunks = [
        {"text": "STYLE_ONE " * 20},
        {"text": "STYLE_TWO " * 20},
    ]
    voice_snippets = {
        "char-a": [
            {"text": "VOICE_A1 " * 10},
            {"text": "VOICE_A2 " * 10},
            {"text": "VOICE_A3 " * 10},
        ]
    }
    lore_chunks = [
        {"text": "LORE_HIGH " * 12, "source_title": "BookH", "chunk_id": "h", "score": 0.9},
        {"text": "LORE_MED " * 12, "source_title": "BookM", "chunk_id": "m", "score": 0.5},
        {"text": "LORE_LOW " * 12, "source_title": "BookL", "chunk_id": "l", "score": 0.1},
    ]
    history = ["H1 " * 12, "H2 " * 12, "H3 " * 12]
    return {
        "system": "SYS",
        "state": "STATE",
        "history": history,
        "lore_chunks": lore_chunks,
        "style_chunks": style_chunks,
        "voice_snippets": voice_snippets,
        "user_input": "INPUT",
    }


def _estimate_tokens_for_parts(parts):
    _, report = build_context(
        parts,
        max_input_tokens=10_000,
        reserve_output_tokens=0,
        max_voice_snippets_per_char=2,
        min_lore_chunks=1,
        user_input_label="User input:",
        empty_voice_text="(No voice.)",
        empty_lore_text="(No lore.)",
    )
    return report.estimated_tokens


class TestContextBudgetTrimming(unittest.TestCase):
    """Verify ContextBudget trims in the expected order."""

    def test_trimming_order(self) -> None:
        parts_full = _make_parts()
        tokens_full = _estimate_tokens_for_parts(parts_full)

        parts_no_style = dict(parts_full)
        parts_no_style["style_chunks"] = []
        tokens_no_style = _estimate_tokens_for_parts(parts_no_style)

        parts_no_style_voice = dict(parts_no_style)
        parts_no_style_voice["voice_snippets"] = {
            "char-a": parts_full["voice_snippets"]["char-a"][:2],
        }
        tokens_no_style_voice = _estimate_tokens_for_parts(parts_no_style_voice)

        parts_no_style_voice_lore = dict(parts_no_style_voice)
        parts_no_style_voice_lore["lore_chunks"] = parts_full["lore_chunks"][:2]
        tokens_no_style_voice_lore = _estimate_tokens_for_parts(parts_no_style_voice_lore)

        parts_no_style_voice_lore_history = dict(parts_no_style_voice_lore)
        parts_no_style_voice_lore_history["history"] = parts_full["history"][1:]
        tokens_no_style_voice_lore_history = _estimate_tokens_for_parts(parts_no_style_voice_lore_history)

        self.assertGreater(tokens_full, tokens_no_style)
        self.assertGreater(tokens_no_style, tokens_no_style_voice)
        self.assertGreater(tokens_no_style_voice, tokens_no_style_voice_lore)
        self.assertGreater(tokens_no_style_voice_lore, tokens_no_style_voice_lore_history)

        # Budget between full and no-style -> only style trimmed
        budget_style = tokens_no_style + 1
        messages, report = build_context(
            parts_full,
            max_input_tokens=budget_style,
            reserve_output_tokens=0,
            max_voice_snippets_per_char=2,
            min_lore_chunks=1,
            user_input_label="User input:",
            empty_voice_text="(No voice.)",
            empty_lore_text="(No lore.)",
        )
        self.assertEqual(report.dropped_style_chunks, len(parts_full["style_chunks"]))
        self.assertEqual(report.dropped_voice_snippets, 0)
        self.assertEqual(report.dropped_lore_chunks, 0)
        self.assertEqual(report.dropped_history_items, 0)

        # Budget between no-style and no-style+voice -> style + voice trimmed
        budget_voice = tokens_no_style_voice + 1
        messages, report = build_context(
            parts_full,
            max_input_tokens=budget_voice,
            reserve_output_tokens=0,
            max_voice_snippets_per_char=2,
            min_lore_chunks=1,
            user_input_label="User input:",
            empty_voice_text="(No voice.)",
            empty_lore_text="(No lore.)",
        )
        self.assertEqual(report.dropped_style_chunks, len(parts_full["style_chunks"]))
        self.assertGreater(report.dropped_voice_snippets, 0)
        self.assertEqual(report.dropped_lore_chunks, 0)
        self.assertEqual(report.dropped_history_items, 0)

        # Budget between no-style+voice and no-style+voice+lore -> lore trimmed by lowest score
        budget_lore = tokens_no_style_voice_lore + 1
        messages, report = build_context(
            parts_full,
            max_input_tokens=budget_lore,
            reserve_output_tokens=0,
            max_voice_snippets_per_char=2,
            min_lore_chunks=1,
            user_input_label="User input:",
            empty_voice_text="(No voice.)",
            empty_lore_text="(No lore.)",
        )
        user_text = messages[1]["content"]
        self.assertIn("LORE_HIGH", user_text)
        self.assertIn("LORE_MED", user_text)
        self.assertNotIn("LORE_LOW", user_text)
        self.assertEqual(report.dropped_history_items, 0)

        # Budget between no-style+voice+lore and no-style+voice+lore+history -> history trimmed oldest-first
        budget_history = tokens_no_style_voice_lore_history + 1
        messages, report = build_context(
            parts_full,
            max_input_tokens=budget_history,
            reserve_output_tokens=0,
            max_voice_snippets_per_char=2,
            min_lore_chunks=1,
            user_input_label="User input:",
            empty_voice_text="(No voice.)",
            empty_lore_text="(No lore.)",
        )
        user_text = messages[1]["content"]
        self.assertNotIn("H1", user_text)
        self.assertIn("H2", user_text)
        self.assertIn("H3", user_text)
        self.assertGreater(report.dropped_history_items, 0)


class TestNarratorContextBudgetIntegration(unittest.TestCase):
    """Integration-ish test: Narrator uses ContextBudget and emits warning."""

    def test_narrator_warns_when_context_trimmed(self) -> None:
        from backend.app.core.agents.narrator import NarratorAgent
        from backend.app.models.state import GameState, MechanicOutput

        old_env = os.environ.get("NARRATOR_MAX_INPUT_TOKENS")
        os.environ["NARRATOR_MAX_INPUT_TOKENS"] = "200"
        try:
            def lore_retriever(query, top_k=6, era=None, related_npcs=None, warnings=None, **_kw):
                return [
                    {
                        "text": "LORE " * 200,
                        "source_title": "Book",
                        "chunk_id": f"c{i}",
                        "score": 1.0 - i * 0.1,
                    }
                    for i in range(8)
                ]

            def voice_retriever(cids, era, k=6, warnings=None):
                return {
                    cid: [
                        {"text": "VOICE " * 120, "character_id": cid, "era": era, "chunk_id": f"v{i}"}
                        for i in range(6)
                    ]
                    for cid in (cids or [])
                }

            narrator = NarratorAgent(llm=None, lore_retriever=lore_retriever, voice_retriever=voice_retriever)
            state = GameState(
                campaign_id="c1",
                player_id="p1",
                turn_number=1,
                current_location="loc-tavern",
                campaign={"time_period": "LOTF", "party": ["char-a"]},
                present_npcs=[{"id": "char-a", "name": "A", "role": "NPC"}],
                mechanic_result=MechanicOutput(action_type="TALK", events=[], narrative_facts=[]),
                user_input="Tell me about the tavern.",
            )
            output = narrator.generate(state)
            self.assertTrue(output.text)
            self.assertTrue(any("Context trimmed:" in w for w in (state.warnings or [])))
        finally:
            if old_env is None:
                os.environ.pop("NARRATOR_MAX_INPUT_TOKENS", None)
            else:
                os.environ["NARRATOR_MAX_INPUT_TOKENS"] = old_env
