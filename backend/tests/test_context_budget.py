"""Tests for ContextBudget trimming behavior."""
import os
import sys
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.context_budget import build_context  # noqa: E402


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
    """Verify ContextBudget trims in the expected order.

    V8.0 Gate 2: Trim order changed to KG → era_summaries → history → voice → style → lore.
    Style is now preserved longer to maintain narrator voice quality.
    """

    def test_trimming_order(self) -> None:
        """V8.0: New trim order — KG/era/history drop before style/lore."""
        parts_full = _make_parts()
        # Add KG context and era_summaries so they can be trimmed first
        parts_full["kg_context"] = "KG_CONTEXT " * 15
        parts_full["era_summaries"] = ["ERA_SUM_1 " * 10, "ERA_SUM_2 " * 10]
        tokens_full = _estimate_tokens_for_parts(parts_full)

        # Phase 1: KG drops first
        parts_no_kg = dict(parts_full)
        parts_no_kg["kg_context"] = ""
        tokens_no_kg = _estimate_tokens_for_parts(parts_no_kg)

        # Phase 2: Era summaries drop next
        parts_no_kg_era = dict(parts_no_kg)
        parts_no_kg_era["era_summaries"] = []
        tokens_no_kg_era = _estimate_tokens_for_parts(parts_no_kg_era)

        # Phase 3: History drops next
        parts_no_kg_era_hist = dict(parts_no_kg_era)
        parts_no_kg_era_hist["history"] = parts_full["history"][1:]
        tokens_no_kg_era_hist = _estimate_tokens_for_parts(parts_no_kg_era_hist)

        self.assertGreater(tokens_full, tokens_no_kg)
        self.assertGreater(tokens_no_kg, tokens_no_kg_era)
        self.assertGreater(tokens_no_kg_era, tokens_no_kg_era_hist)

        # Budget just below full: KG should drop, style should survive
        budget_kg = tokens_no_kg + 1
        messages, report = build_context(
            parts_full,
            max_input_tokens=budget_kg,
            reserve_output_tokens=0,
            max_voice_snippets_per_char=2,
            min_lore_chunks=1,
            user_input_label="User input:",
            empty_voice_text="(No voice.)",
            empty_lore_text="(No lore.)",
        )
        self.assertTrue(report.dropped_kg_context)
        self.assertEqual(report.dropped_style_chunks, 0)  # Style preserved!
        self.assertEqual(report.dropped_lore_chunks, 0)

        # Budget below no-KG: era_summaries should drop, style still survives
        budget_era = tokens_no_kg_era + 1
        messages, report = build_context(
            parts_full,
            max_input_tokens=budget_era,
            reserve_output_tokens=0,
            max_voice_snippets_per_char=2,
            min_lore_chunks=1,
            user_input_label="User input:",
            empty_voice_text="(No voice.)",
            empty_lore_text="(No lore.)",
        )
        self.assertTrue(report.dropped_kg_context)
        self.assertGreater(report.dropped_era_summaries, 0)
        self.assertEqual(report.dropped_style_chunks, 0)  # Style still preserved!

        # Budget below no-KG-era: history drops, style still survives
        budget_hist = tokens_no_kg_era_hist + 1
        messages, report = build_context(
            parts_full,
            max_input_tokens=budget_hist,
            reserve_output_tokens=0,
            max_voice_snippets_per_char=2,
            min_lore_chunks=1,
            user_input_label="User input:",
            empty_voice_text="(No voice.)",
            empty_lore_text="(No lore.)",
        )
        self.assertGreater(report.dropped_history_items, 0)
        self.assertEqual(report.dropped_style_chunks, 0)  # Style STILL preserved!


class TestNarratorContextBudgetIntegration(unittest.TestCase):
    """Integration-ish test: Narrator uses ContextBudget and emits warning."""

    def test_narrator_warns_when_context_trimmed(self) -> None:
        from backend.app.core.agents.narrator import NarratorAgent  # noqa: E402
        from backend.app.models.state import GameState, MechanicOutput  # noqa: E402

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
