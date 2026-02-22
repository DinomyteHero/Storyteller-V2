"""Tests for V1.1 Phase 4C: faction reputation quest gating.

Covers:
- faction_ally entry condition: quest activates when reputation >= threshold
- faction_hostile fail condition: quest fails when reputation drops below threshold
- Failure consequence generation on faction_hostile trigger
"""
from __future__ import annotations

from backend.app.core.quest_tracker import (
    QuestTracker,
    QUEST_STATUS_ACTIVE,
    QUEST_STATUS_COMPLETED,
    QUEST_STATUS_FAILED,
)


def _gated_quests() -> list[dict]:
    """Quests using faction_ally / faction_hostile conditions."""
    return [
        {
            "id": "q_alliance_mission",
            "title": "Alliance Mission",
            "entry_conditions": {
                "turn": {"min": 1},
                "faction_ally": {"rebel_alliance": 20},
            },
            "stages": [
                {
                    "stage_id": "briefing",
                    "objective": "Attend briefing",
                    "success_conditions": {"action_taken": "attend_briefing"},
                    "fail_conditions": {
                        "faction_hostile": {"rebel_alliance": -10},
                    },
                },
            ],
        },
        {
            "id": "q_trade_deal",
            "title": "Trade Deal",
            "entry_conditions": {
                "turn": {"min": 1},
                "faction_ally": {"merchants_guild": 10},
            },
            "stages": [
                {
                    "stage_id": "negotiate",
                    "objective": "Negotiate terms",
                    "success_conditions": {"action_taken": "negotiate"},
                },
            ],
        },
    ]


class TestFactionAllyEntryCondition:
    """faction_ally: quest activates when faction reputation >= threshold."""

    def test_low_reputation_blocks_activation(self):
        tracker = QuestTracker(_gated_quests())
        ws = {"faction_reputation": {"rebel_alliance": 5}}
        updated, notes, _cevents = tracker.process_turn({}, 5, None, [], ws)
        assert "q_alliance_mission" not in updated, \
            "Quest should not activate with reputation below threshold"

    def test_exact_threshold_allows_activation(self):
        tracker = QuestTracker(_gated_quests())
        ws = {"faction_reputation": {"rebel_alliance": 20}}
        updated, notes, _cevents = tracker.process_turn({}, 5, None, [], ws)
        assert "q_alliance_mission" in updated
        assert updated["q_alliance_mission"]["status"] == QUEST_STATUS_ACTIVE
        assert any("Alliance Mission" in n for n in notes)

    def test_above_threshold_allows_activation(self):
        tracker = QuestTracker(_gated_quests())
        ws = {"faction_reputation": {"rebel_alliance": 50}}
        updated, notes, _cevents = tracker.process_turn({}, 5, None, [], ws)
        assert "q_alliance_mission" in updated
        assert updated["q_alliance_mission"]["status"] == QUEST_STATUS_ACTIVE

    def test_missing_faction_reputation_blocks(self):
        tracker = QuestTracker(_gated_quests())
        ws = {}  # No faction_reputation key at all
        updated, notes, _cevents = tracker.process_turn({}, 5, None, [], ws)
        assert "q_alliance_mission" not in updated
        assert "q_trade_deal" not in updated

    def test_different_faction_reputation(self):
        tracker = QuestTracker(_gated_quests())
        ws = {"faction_reputation": {"rebel_alliance": 50, "merchants_guild": 5}}
        updated, notes, _cevents = tracker.process_turn({}, 5, None, [], ws)
        # Alliance mission activates (rebel_alliance >= 20)
        assert "q_alliance_mission" in updated
        # Trade deal doesn't (merchants_guild < 10)
        assert "q_trade_deal" not in updated


class TestFactionHostileFailCondition:
    """faction_hostile: active quest fails when faction reputation drops below threshold."""

    def test_hostile_reputation_fails_quest(self):
        tracker = QuestTracker(_gated_quests())
        quest_log = {
            "q_alliance_mission": {
                "quest_id": "q_alliance_mission",
                "status": QUEST_STATUS_ACTIVE,
                "current_stage_idx": 0,
                "stages_completed": [],
                "activated_turn": 1,
            }
        }
        # Reputation dropped below -10 threshold
        ws = {"faction_reputation": {"rebel_alliance": -15}}
        updated, notes, cevents = tracker.process_turn(quest_log, 5, None, [], ws)
        assert updated["q_alliance_mission"]["status"] == QUEST_STATUS_FAILED
        assert any("failed" in n.lower() for n in notes)

    def test_reputation_above_hostile_threshold_keeps_quest(self):
        tracker = QuestTracker(_gated_quests())
        quest_log = {
            "q_alliance_mission": {
                "quest_id": "q_alliance_mission",
                "status": QUEST_STATUS_ACTIVE,
                "current_stage_idx": 0,
                "stages_completed": [],
                "activated_turn": 1,
            }
        }
        # Reputation is -5, above the -10 threshold
        ws = {"faction_reputation": {"rebel_alliance": -5}}
        updated, notes, _cevents = tracker.process_turn(quest_log, 5, None, [], ws)
        assert updated["q_alliance_mission"]["status"] == QUEST_STATUS_ACTIVE

    def test_hostile_failure_generates_consequences(self):
        tracker = QuestTracker(_gated_quests())
        quest_log = {
            "q_alliance_mission": {
                "quest_id": "q_alliance_mission",
                "status": QUEST_STATUS_ACTIVE,
                "current_stage_idx": 0,
                "stages_completed": [],
                "activated_turn": 1,
            }
        }
        ws = {"faction_reputation": {"rebel_alliance": -20}}
        updated, notes, cevents = tracker.process_turn(quest_log, 5, None, [], ws)
        assert updated["q_alliance_mission"]["status"] == QUEST_STATUS_FAILED
        # Should have at least a FLAG_SET consequence
        flag_events = [e for e in cevents if e.get("event_type") == "FLAG_SET"]
        assert len(flag_events) >= 1, "Failed quest should generate FLAG_SET consequence"
