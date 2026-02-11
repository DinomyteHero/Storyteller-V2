"""Quest tracking system — deterministic, pure Python.

Checks quest entry conditions and stage completion conditions against
game events and world state. No LLM calls. Integrates into the Commit
node's event processing pipeline.

Quest definitions come from era pack YAML (EraQuest, EraQuestStage).
Quest runtime state lives in world_state_json["quest_log"].
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── Quest runtime state ──

QUEST_STATUS_AVAILABLE = "available"
QUEST_STATUS_ACTIVE = "active"
QUEST_STATUS_COMPLETED = "completed"
QUEST_STATUS_FAILED = "failed"


class QuestState:
    """Runtime state for a single quest instance."""

    def __init__(
        self,
        quest_id: str,
        status: str = QUEST_STATUS_AVAILABLE,
        current_stage_idx: int = 0,
        stages_completed: list[str] | None = None,
        activated_turn: int = 0,
    ) -> None:
        self.quest_id = quest_id
        self.status = status
        self.current_stage_idx = current_stage_idx
        self.stages_completed = stages_completed or []
        self.activated_turn = activated_turn

    def to_dict(self) -> dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "status": self.status,
            "current_stage_idx": self.current_stage_idx,
            "stages_completed": list(self.stages_completed),
            "activated_turn": self.activated_turn,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuestState:
        return cls(
            quest_id=data.get("quest_id", ""),
            status=data.get("status", QUEST_STATUS_AVAILABLE),
            current_stage_idx=int(data.get("current_stage_idx", 0)),
            stages_completed=list(data.get("stages_completed") or []),
            activated_turn=int(data.get("activated_turn", 0)),
        )


# ── Condition checking ──

def _check_entry_conditions(
    conditions: dict[str, Any] | None,
    turn_number: int,
    location_id: str | None,
    events: list[dict],
    world_state: dict,
) -> bool:
    """Check if quest entry conditions are met. Returns True if quest should activate.

    Supported condition keys:
    - turn.min: minimum turn number
    - turn.max: maximum turn number
    - location: must be at this location
    - event_type: an event with this type must be in the turn's events
    - npc_met: player must have met this NPC (in known_npcs)
    """
    if not conditions:
        return True  # No conditions = always available

    # Turn range
    turn_cond = conditions.get("turn")
    if isinstance(turn_cond, dict):
        min_turn = int(turn_cond.get("min", 0))
        max_turn = int(turn_cond.get("max", 9999))
        if turn_number < min_turn or turn_number > max_turn:
            return False
    elif isinstance(turn_cond, (int, float)):
        if turn_number < int(turn_cond):
            return False

    # Location
    loc_cond = conditions.get("location")
    if loc_cond and location_id:
        if str(loc_cond).lower() != str(location_id).lower():
            return False

    # Event type present this turn
    event_cond = conditions.get("event_type")
    if event_cond:
        event_types = {e.get("event_type", "") for e in events}
        if str(event_cond) not in event_types:
            return False

    # NPC met
    npc_cond = conditions.get("npc_met")
    if npc_cond:
        known = set(world_state.get("known_npcs") or [])
        if str(npc_cond) not in known:
            return False

    return True


def _check_stage_conditions(
    conditions: dict[str, Any] | None,
    events: list[dict],
    world_state: dict,
    completed_stages: list[str],
) -> bool:
    """Check if a quest stage's success conditions are met.

    Supported condition keys:
    - npc_met: player must have met this NPC
    - action_taken: an event payload must contain this action
    - event_type: an event with this type must exist
    - stage_completed: a previous stage must be completed
    - item_acquired: player must have this item in inventory
    """
    if not conditions:
        return False  # No conditions = can't auto-complete

    # NPC met
    npc_cond = conditions.get("npc_met")
    if npc_cond:
        known = set(world_state.get("known_npcs") or [])
        if str(npc_cond) not in known:
            return False

    # Action taken (check event payloads)
    action_cond = conditions.get("action_taken")
    if action_cond:
        found = False
        for e in events:
            payload = e.get("payload") or {}
            # Check if the action appears anywhere in event payloads
            for v in payload.values():
                if isinstance(v, str) and str(action_cond).lower() in v.lower():
                    found = True
                    break
            if found:
                break
        if not found:
            return False

    # Event type present
    event_cond = conditions.get("event_type")
    if event_cond:
        event_types = {e.get("event_type", "") for e in events}
        if str(event_cond) not in event_types:
            return False

    # Previous stage completed
    stage_cond = conditions.get("stage_completed")
    if stage_cond:
        if str(stage_cond) not in completed_stages:
            return False

    # Item acquired
    item_cond = conditions.get("item_acquired")
    if item_cond:
        inventory = world_state.get("inventory") or []
        item_names = set()
        for item in inventory:
            if isinstance(item, dict):
                item_names.add(item.get("item_name", "").lower())
            elif isinstance(item, str):
                item_names.add(item.lower())
        if str(item_cond).lower() not in item_names:
            return False

    return True


# ── Quest Tracker ──

class QuestTracker:
    """Deterministic quest state machine.

    Checks quest conditions against game events and world state.
    No LLM calls, no DB access — pure Python logic.
    """

    def __init__(self, era_quests: list[dict]) -> None:
        """Initialize with quest definitions from era pack.

        Args:
            era_quests: List of EraQuest dicts (from era pack YAML).
        """
        self._quest_defs: dict[str, dict] = {}
        for q in era_quests:
            if isinstance(q, dict) and q.get("id"):
                self._quest_defs[q["id"]] = q

    def process_turn(
        self,
        quest_log: dict[str, dict],
        turn_number: int,
        location_id: str | None,
        events: list[dict],
        world_state: dict,
    ) -> tuple[dict[str, dict], list[str]]:
        """Process a turn's events against all quests.

        Args:
            quest_log: Current quest_log from world_state_json.
            turn_number: Current turn number.
            location_id: Current location ID.
            events: Turn events (list of dicts with event_type + payload).
            world_state: Full world_state_json dict.

        Returns:
            (updated_quest_log, notifications) — notifications are player-facing strings.
        """
        updated = dict(quest_log)
        notifications: list[str] = []

        # Check entry conditions for quests not yet in the log
        for quest_id, quest_def in self._quest_defs.items():
            if quest_id in updated:
                continue  # Already tracked

            entry_conds = quest_def.get("entry_conditions")
            if _check_entry_conditions(entry_conds, turn_number, location_id, events, world_state):
                # Activate the quest
                qs = QuestState(
                    quest_id=quest_id,
                    status=QUEST_STATUS_ACTIVE,
                    current_stage_idx=0,
                    activated_turn=turn_number,
                )
                updated[quest_id] = qs.to_dict()
                title = quest_def.get("title", quest_id)
                notifications.append(f"New quest: {title}")
                logger.info("Quest activated: %s (turn %d)", quest_id, turn_number)

        # Check stage completion for active quests
        for quest_id in list(updated.keys()):
            qs_data = updated[quest_id]
            if qs_data.get("status") != QUEST_STATUS_ACTIVE:
                continue

            quest_def = self._quest_defs.get(quest_id)
            if not quest_def:
                continue

            qs = QuestState.from_dict(qs_data)
            stages = quest_def.get("stages") or []

            if qs.current_stage_idx >= len(stages):
                # All stages done — complete the quest
                qs.status = QUEST_STATUS_COMPLETED
                updated[quest_id] = qs.to_dict()
                title = quest_def.get("title", quest_id)
                notifications.append(f"Quest completed: {title}")
                logger.info("Quest completed: %s (turn %d)", quest_id, turn_number)
                continue

            current_stage = stages[qs.current_stage_idx]
            stage_id = current_stage.get("stage_id", f"stage_{qs.current_stage_idx}")
            success_conds = current_stage.get("success_conditions")

            if _check_stage_conditions(success_conds, events, world_state, qs.stages_completed):
                # Stage completed — advance
                qs.stages_completed.append(stage_id)
                qs.current_stage_idx += 1
                objective = current_stage.get("objective", stage_id)
                notifications.append(f"Objective complete: {objective}")
                logger.info(
                    "Quest %s stage %s completed (turn %d), advancing to stage %d",
                    quest_id, stage_id, turn_number, qs.current_stage_idx,
                )

                # Check if quest is now fully completed
                if qs.current_stage_idx >= len(stages):
                    qs.status = QUEST_STATUS_COMPLETED
                    title = quest_def.get("title", quest_id)
                    notifications.append(f"Quest completed: {title}")
                    logger.info("Quest completed: %s (turn %d)", quest_id, turn_number)

                updated[quest_id] = qs.to_dict()

            # Check fail conditions
            fail_conds = current_stage.get("fail_conditions")
            if fail_conds and _check_stage_conditions(fail_conds, events, world_state, qs.stages_completed):
                qs.status = QUEST_STATUS_FAILED
                updated[quest_id] = qs.to_dict()
                title = quest_def.get("title", quest_id)
                notifications.append(f"Quest failed: {title}")
                logger.info("Quest failed: %s (turn %d)", quest_id, turn_number)

        return updated, notifications


def get_quest_tracker(era: str) -> QuestTracker | None:
    """Create a QuestTracker from era pack quest definitions.

    Returns None if no era pack or no quests found.
    """
    try:
        from backend.app.world.era_pack_loader import get_era_pack
        pack = get_era_pack(era)
        if not pack or not pack.quests:
            return None
        quest_dicts = [q.model_dump(mode="json") for q in pack.quests]
        return QuestTracker(quest_dicts)
    except Exception as e:
        logger.warning("Failed to create QuestTracker for era %s: %s", era, e)
        return None


def process_quests_for_turn(
    world_state: dict,
    era: str,
    turn_number: int,
    location_id: str | None,
    events: list[dict],
) -> list[str]:
    """Convenience: process quest conditions for a turn and update world_state in place.

    Returns list of player-facing notifications.
    """
    tracker = get_quest_tracker(era)
    if not tracker:
        return []

    quest_log = world_state.get("quest_log") or {}
    if not isinstance(quest_log, dict):
        quest_log = {}

    updated_log, notifications = tracker.process_turn(
        quest_log, turn_number, location_id, events, world_state,
    )

    world_state["quest_log"] = updated_log
    return notifications
