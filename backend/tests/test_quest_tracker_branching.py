"""Tests for branching quest stage resolution paths and gating."""

from backend.app.core.quest_tracker import QuestTracker, QUEST_STATUS_ACTIVE


def test_resolution_path_advances_by_matched_conditions():
    quests = [
        {
            "id": "q_blackmail",
            "title": "Blackmail Ledger",
            "stages": [
                {
                    "stage_id": "acquire_ledger",
                    "objective": "Get the ledger from the broker",
                    "resolution_paths": [
                        {
                            "path_id": "pay",
                            "label": "Paid the broker",
                            "success_conditions": {"action_taken": "pay"},
                        },
                        {
                            "path_id": "steal",
                            "label": "Stole the ledger",
                            "success_conditions": {"action_taken": "steal"},
                        },
                    ],
                },
                {
                    "stage_id": "report_back",
                    "objective": "Return to your handler",
                    "success_conditions": {"event_type": "DIALOGUE"},
                },
            ],
        }
    ]
    tracker = QuestTracker(quests)
    quest_log = {
        "q_blackmail": {
            "quest_id": "q_blackmail",
            "status": QUEST_STATUS_ACTIVE,
            "current_stage_idx": 0,
            "stages_completed": [],
            "activated_turn": 1,
        }
    }
    events = [{"event_type": "ACTION", "payload": {"text": "I steal the ledger quietly"}}]
    updated, notes = tracker.process_turn(quest_log, 2, "market", events, world_state={})

    assert updated["q_blackmail"]["current_stage_idx"] == 1
    assert "acquire_ledger:steal" in updated["q_blackmail"]["stages_completed"]
    assert any("Objective complete (Stole the ledger)" in n for n in notes)


def test_stage_condition_supports_alignment_and_reputation_gates():
    quests = [
        {
            "id": "q_dark_contract",
            "title": "Dark Contract",
            "stages": [
                {
                    "stage_id": "enter",
                    "objective": "Meet the contact",
                    "success_conditions": {
                        "alignment_max": {"paragon_renegade": -8},
                        "reputation_min": {"underworld": 5},
                    },
                }
            ],
        }
    ]
    tracker = QuestTracker(quests)
    quest_log = {
        "q_dark_contract": {
            "quest_id": "q_dark_contract",
            "status": QUEST_STATUS_ACTIVE,
            "current_stage_idx": 0,
            "stages_completed": [],
            "activated_turn": 1,
        }
    }

    world_state = {
        "alignment": {"paragon_renegade": -10},
        "faction_reputation": {"underworld": 7},
    }
    updated, _notes = tracker.process_turn(quest_log, 2, "dock", [], world_state=world_state)
    assert updated["q_dark_contract"]["status"] == "completed"
