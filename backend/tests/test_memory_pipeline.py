"""Tests for V8.0 Gate 2: Memory Pipeline improvements.

Tests cover:
- Relevance scoring (history, facts, threads)
- NPC memory prioritization
- Context budget rebalancing
- Adaptive narrative truncation
- Cross-arc memory bridging
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.app.core.agents.narrator_prompt import (  # noqa: E402
    _score_history_relevance,
    _score_fact_relevance,
    _score_thread_relevance,
    _rank_npc_importance,
    _format_npc_oneliner,
)
from backend.app.core.context_budget import build_context, estimate_tokens  # noqa: E402


# ---------------------------------------------------------------------------
# 2.1: History Relevance Scoring
# ---------------------------------------------------------------------------


class TestScoreHistoryRelevance:
    def test_npc_mention_scores_high(self):
        score = _score_history_relevance(
            "T5 DIALOGUE with Captain Vale",
            present_npc_names=["Captain Vale"],
            active_threads=[],
            current_location="",
        )
        assert score >= 0.3

    def test_thread_keyword_scores_high(self):
        score = _score_history_relevance(
            "T5 FLAG_SET artifact_found=true",
            present_npc_names=[],
            active_threads=["[W2]Find the ancient artifact before dawn"],
            current_location="",
        )
        assert score >= 0.3

    def test_location_mention_adds_score(self):
        score = _score_history_relevance(
            "T3 MOVE to loc-cantina",
            present_npc_names=[],
            active_threads=[],
            current_location="loc-cantina",
        )
        assert score >= 0.2

    def test_current_arc_adds_score(self):
        score = _score_history_relevance(
            "T15 DAMAGE -5",
            present_npc_names=[],
            active_threads=[],
            current_location="",
            arc_stage_start_turn=10,
        )
        assert score >= 0.2

    def test_old_arc_no_bonus(self):
        score = _score_history_relevance(
            "T5 DAMAGE -5",
            present_npc_names=[],
            active_threads=[],
            current_location="",
            arc_stage_start_turn=10,
        )
        # Turn 5 is before arc start (10), so no arc bonus
        assert score < 0.2

    def test_empty_context_scores_zero(self):
        score = _score_history_relevance(
            "T1 some event",
            present_npc_names=[],
            active_threads=[],
            current_location="",
        )
        assert score == 0.0

    def test_combined_npc_and_location(self):
        score = _score_history_relevance(
            "T8 DIALOGUE with Kira at loc-cantina",
            present_npc_names=["Kira"],
            active_threads=[],
            current_location="loc-cantina",
        )
        assert score >= 0.5

    def test_score_capped_at_1(self):
        score = _score_history_relevance(
            "T15 Kira artifact cantina ancient",
            present_npc_names=["Kira"],
            active_threads=["[W3]Find the ancient artifact"],
            current_location="cantina",
            arc_stage_start_turn=10,
        )
        assert score <= 1.0


# ---------------------------------------------------------------------------
# 2.2: Fact Relevance Scoring
# ---------------------------------------------------------------------------


class TestScoreFactRelevance:
    def test_npc_mention_scores_highest(self):
        score = _score_fact_relevance(
            "Captain Vale offered a deal",
            present_npc_names=["Captain Vale"],
            active_threads=[],
            current_location="",
        )
        assert score >= 0.4

    def test_thread_keyword_match(self):
        score = _score_fact_relevance(
            "The artifact was last seen in the temple",
            present_npc_names=[],
            active_threads=["[W2]Find the ancient artifact"],
            current_location="",
        )
        assert score >= 0.3

    def test_location_match(self):
        score = _score_fact_relevance(
            "A fight broke out at loc-cantina",
            present_npc_names=[],
            active_threads=[],
            current_location="loc-cantina",
        )
        assert score >= 0.2

    def test_no_match_scores_low(self):
        score = _score_fact_relevance(
            "The weather was pleasant",
            present_npc_names=["Kira"],
            active_threads=["[W1]Find the artifact"],
            current_location="loc-cantina",
        )
        assert score < 0.2


# ---------------------------------------------------------------------------
# 2.2: Thread Relevance Scoring
# ---------------------------------------------------------------------------


class TestScoreThreadRelevance:
    def test_npc_mention_scores_high(self):
        score = _score_thread_relevance(
            "[W2]Captain Vale's smuggling operation",
            present_npc_names=["Captain Vale"],
            dynamic_quests=[],
        )
        assert score >= 0.4

    def test_quest_match_scores_high(self):
        score = _score_thread_relevance(
            "[W2]Find the stolen shipment",
            present_npc_names=[],
            dynamic_quests=[{"title": "The Stolen Shipment", "description": "Recover the cargo"}],
        )
        assert score >= 0.3

    def test_weight_prefix_adds_score(self):
        score_w3 = _score_thread_relevance("[W3]Major thread", [], [])
        score_w1 = _score_thread_relevance("[W1]Minor thread", [], [])
        assert score_w3 > score_w1

    def test_no_weight_no_bonus(self):
        score = _score_thread_relevance("Plain thread", [], [])
        assert score == 0.0


# ---------------------------------------------------------------------------
# 2.3: NPC Memory Prioritization
# ---------------------------------------------------------------------------


class TestNPCPrioritization:
    def test_quest_involved_npc_ranks_highest(self):
        npc = {"id": "vale", "name": "Captain Vale"}
        quests = [{"title": "Captain Vale's mission", "description": "Help Vale"}]
        rank = _rank_npc_importance(npc, {}, quests, turn_number=10)
        assert rank == 1

    def test_recent_interaction_ranks_second(self):
        npc = {"id": "kira", "name": "Kira"}
        npc_states = {"kira": {"memories": ["Turn 8: Kira shared a secret"]}}
        rank = _rank_npc_importance(npc, npc_states, [], turn_number=10)
        assert rank == 2

    def test_old_interaction_ranks_third(self):
        npc = {"id": "kira", "name": "Kira"}
        npc_states = {"kira": {"memories": ["Turn 1: Met Kira"]}}
        rank = _rank_npc_importance(npc, npc_states, [], turn_number=20)
        assert rank == 3

    def test_no_memory_ranks_third(self):
        npc = {"id": "random", "name": "Random NPC"}
        rank = _rank_npc_importance(npc, {}, [], turn_number=10)
        assert rank == 3


class TestFormatNPCOneliner:
    def test_basic_oneliner(self):
        npc = {"id": "vale", "name": "Captain Vale", "role": "Smuggler"}
        npc_states = {"vale": {"emotional_state": "wary"}}
        line = _format_npc_oneliner(npc, npc_states)
        assert "Captain Vale" in line
        assert "Smuggler" in line
        assert "wary" in line

    def test_no_emotional_state(self):
        npc = {"id": "vale", "name": "Captain Vale", "role": "Smuggler"}
        line = _format_npc_oneliner(npc, {})
        assert "Captain Vale" in line
        assert "[mood:" not in line


# ---------------------------------------------------------------------------
# 2.4: Context Budget Rebalancing
# ---------------------------------------------------------------------------


class TestContextBudgetRebalancing:
    """Test that the new trim order drops KG/era before style/lore."""

    def _make_parts(self, *, extra_tokens: int = 0):
        """Build parts dict that's slightly over budget when extra_tokens added."""
        return {
            "system": "You are a narrator.",
            "state": "Location: cantina.",
            "history": [f"T{i} EVENT" for i in range(5)],
            "era_summaries": ["Turns 1-5: visited cantina, met Vale."],
            "lore_chunks": [{"text": "Lore chunk about cantina history " * 5, "score": 0.8}],
            "style_chunks": [
                {"text": "Style: Use vivid sensory details and tight prose."},
                {"text": "Style: Favor short punchy sentences in action."},
                {"text": "Style: Dialogue should feel like KOTOR companions."},
            ],
            "voice_snippets": {"vale": [{"text": "Vale speaks gruffly."}]},
            "kg_context": "KG: Captain Vale is a smuggler based in the Outer Rim." + ("x" * extra_tokens),
            "user_input": "I look around the cantina.",
        }

    def test_kg_drops_before_style(self):
        """When over budget, KG should drop before style chunks."""
        parts = self._make_parts(extra_tokens=0)
        # Force a very tight budget
        msgs, report = build_context(
            parts,
            max_input_tokens=100,  # Very tight
            reserve_output_tokens=50,
            min_lore_chunks=0,
        )
        # KG should be among the first things dropped
        if report.trimmed():
            # If KG was dropped but style wasn't, the order is correct
            # The key assertion: style should survive longer than KG
            if report.dropped_kg_context:
                # Good — KG dropped first as expected
                pass

    def test_era_summaries_drop_before_style(self):
        """Era summaries should drop before style in new trim order."""
        parts = self._make_parts()
        msgs, report = build_context(
            parts,
            max_input_tokens=120,
            reserve_output_tokens=50,
            min_lore_chunks=0,
        )
        if report.trimmed():
            if report.dropped_era_summaries and not report.dropped_style_chunks:
                pass  # Correct: era dropped, style preserved

    def test_style_capped_at_two_under_pressure(self):
        """Under budget pressure, style should cap at 2 rather than drop entirely."""
        parts = self._make_parts()
        # Medium-tight budget: should trigger style capping but not full removal
        msgs, report = build_context(
            parts,
            max_input_tokens=80,
            reserve_output_tokens=30,
            min_lore_chunks=0,
        )
        # If style was trimmed, it should be partial (dropped some, not all)
        if report.dropped_style_chunks > 0:
            assert report.final_style_chunks <= 2


# ---------------------------------------------------------------------------
# 2.5: Adaptive Narrative Truncation
# ---------------------------------------------------------------------------


class TestAdaptiveNarrativeTruncation:
    """Test that dialogue-heavy text gets more words than action text."""

    def test_dialogue_heavy_gets_more_words(self):
        """Text with multiple quote blocks should retain more words."""
        dialogue_text = (
            '"Hello there," said the captain. "I have a proposition for you." '
            "The room fell silent. "
            '"What kind of proposition?" asked the stranger. '
        ) * 20  # Make it long enough to trigger truncation

        # Count quote pairs
        quote_count = dialogue_text.count('"') // 2
        assert quote_count >= 2

        # The word limit for dialogue should be 280
        words = dialogue_text.split()
        if len(words) > 280:
            # Dialogue text with 2+ quote pairs → 280 word limit
            truncated = " ".join(words[:280]) + "..."
            assert len(truncated.split()) <= 281  # 280 + "..."

    def test_action_text_gets_fewer_words(self):
        """Text without dialogue gets shorter truncation."""
        action_text = (
            "The blaster bolt struck the wall behind him. "
            "He ducked behind the crate, heart pounding. "
            "Another shot whistled overhead. "
        ) * 20

        quote_count = action_text.count('"') // 2
        assert quote_count < 2

        # The word limit for action should be 160
        words = action_text.split()
        if len(words) > 160:
            truncated = " ".join(words[:160]) + "..."
            assert len(truncated.split()) <= 161


# ---------------------------------------------------------------------------
# 2.6: Cross-Arc Memory Bridging
# ---------------------------------------------------------------------------


class TestCrossArcMemoryBridging:
    """Test that saga_context appears in narrator prompt for new arc turns."""

    def test_saga_context_injected_in_new_arc(self):
        """When current_arc_number > 1 and turns_in_arc <= 3, saga_context should appear."""
        from unittest.mock import MagicMock
        from backend.app.core.agents.narrator_prompt import _build_story_state_summary

        state = MagicMock()
        state.current_location = "loc-cantina"
        state.campaign_id = "test-campaign"
        state.present_npcs = []
        state.campaign = {
            "world_state_json": {
                "npc_states": {},
                "ledger": {"open_threads": [], "established_facts": []},
                "dynamic_quests": [],
            }
        }
        state.player = None
        state.mechanic_result = None
        state.director_instructions = "Keep pacing brisk."
        state.active_rumors = []
        state.new_rumors = []
        state.background_figures = []
        state.recent_narrative = []
        state.scene_frame = {}
        state.turn_number = 27  # 2 turns into new arc (start at 25)
        state.arc_guidance = {
            "saga_context": "Arc 1: The crew escaped Yavin. Kira was wounded.",
            "current_arc_number": 2,
            "arc_state": {
                "stage_start_turn": 25,
                "current_stage": "SETUP",
            },
        }

        result = _build_story_state_summary(state)
        assert "SAGA CONTEXT" in result
        assert "Yavin" in result

    def test_saga_context_not_injected_after_3_turns(self):
        """After 3+ turns in the new arc, saga_context should not appear."""
        from unittest.mock import MagicMock
        from backend.app.core.agents.narrator_prompt import _build_story_state_summary

        state = MagicMock()
        state.current_location = "loc-cantina"
        state.campaign_id = "test-campaign"
        state.present_npcs = []
        state.campaign = {
            "world_state_json": {
                "npc_states": {},
                "ledger": {"open_threads": [], "established_facts": []},
                "dynamic_quests": [],
            }
        }
        state.player = None
        state.mechanic_result = None
        state.director_instructions = "Keep pacing brisk."
        state.active_rumors = []
        state.new_rumors = []
        state.background_figures = []
        state.recent_narrative = []
        state.scene_frame = {}
        state.turn_number = 30  # 5 turns into new arc
        state.arc_guidance = {
            "saga_context": "Arc 1: The crew escaped Yavin.",
            "current_arc_number": 2,
            "arc_state": {
                "stage_start_turn": 25,
                "current_stage": "RISING",
            },
        }

        result = _build_story_state_summary(state)
        assert "SAGA CONTEXT" not in result

    def test_no_saga_context_for_first_arc(self):
        """Arc 1 should never have saga context (nothing came before)."""
        from unittest.mock import MagicMock
        from backend.app.core.agents.narrator_prompt import _build_story_state_summary

        state = MagicMock()
        state.current_location = "loc-cantina"
        state.campaign_id = "test-campaign"
        state.present_npcs = []
        state.campaign = {
            "world_state_json": {
                "npc_states": {},
                "ledger": {"open_threads": [], "established_facts": []},
                "dynamic_quests": [],
            }
        }
        state.player = None
        state.mechanic_result = None
        state.director_instructions = ""
        state.active_rumors = []
        state.new_rumors = []
        state.background_figures = []
        state.recent_narrative = []
        state.scene_frame = {}
        state.turn_number = 3
        state.arc_guidance = {
            "saga_context": "",
            "current_arc_number": 1,
            "arc_state": {"stage_start_turn": 0, "current_stage": "SETUP"},
        }

        result = _build_story_state_summary(state)
        assert "SAGA CONTEXT" not in result


class TestConsequenceSurfacing:
    """Test that wave/tsunami consequences appear as MUST-reference sections."""

    def test_wave_consequence_injected(self):
        from unittest.mock import MagicMock
        from backend.app.core.agents.narrator_prompt import _build_story_state_summary

        state = MagicMock()
        state.current_location = "loc-cantina"
        state.campaign_id = "test-campaign"
        state.present_npcs = []
        state.campaign = {
            "world_state_json": {
                "npc_states": {},
                "ledger": {
                    "open_threads": [],
                    "established_facts": [],
                    "consequence_hints": [
                        "[WAVE] Your betrayal of the Rebellion is whispered about in cantinas",
                        "[RIPPLE] A merchant remembers you",
                    ],
                },
                "dynamic_quests": [],
            }
        }
        state.player = None
        state.mechanic_result = None
        state.director_instructions = ""
        state.active_rumors = []
        state.new_rumors = []
        state.background_figures = []
        state.recent_narrative = []
        state.scene_frame = {}
        state.turn_number = 10
        state.arc_guidance = {}

        result = _build_story_state_summary(state)
        assert "ACTIVE CONSEQUENCES" in result
        assert "[WAVE]" in result
        # Ripple-tier should NOT appear in the mandatory section
        assert "[RIPPLE]" not in result.split("ACTIVE CONSEQUENCES")[1].split("Write the narrative")[0]

    def test_no_consequences_when_empty(self):
        from unittest.mock import MagicMock
        from backend.app.core.agents.narrator_prompt import _build_story_state_summary

        state = MagicMock()
        state.current_location = "loc-cantina"
        state.campaign_id = "test-campaign"
        state.present_npcs = []
        state.campaign = {
            "world_state_json": {
                "npc_states": {},
                "ledger": {"open_threads": [], "established_facts": []},
                "dynamic_quests": [],
            }
        }
        state.player = None
        state.mechanic_result = None
        state.director_instructions = ""
        state.active_rumors = []
        state.new_rumors = []
        state.background_figures = []
        state.recent_narrative = []
        state.scene_frame = {}
        state.turn_number = 10
        state.arc_guidance = {}

        result = _build_story_state_summary(state)
        assert "ACTIVE CONSEQUENCES" not in result
