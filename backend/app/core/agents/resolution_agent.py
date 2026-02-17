"""ResolutionAgent: LLM-based Game Master that resolves player actions using the Storyteller Core rules.

Replaces the deterministic Python dice engine in mechanic.py. The LLM reads the active
rule system corpus and acts as a fair, contextual Game Master — setting difficulty, simulating
narrative dice, and producing a full MechanicOutput-compatible JSON response.

No deterministic fallbacks. If the LLM fails, the exception propagates.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from backend.app.core.agents.base import AgentLLM, ensure_json
from backend.app.models.state import GameState, MechanicOutput
from backend.app.models.events import Event
from backend.app.time_economy import get_time_cost, TRAVEL_HYPERSPACE_MINUTES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule system loader
# ---------------------------------------------------------------------------

_RULE_SYSTEM_CACHE: dict[str, str] = {}


def _load_rule_system(rule_system_id: str) -> str:
    """Load rule system text from /data/static/rule_systems/{id}.md.

    Cached after first load. Raises FileNotFoundError if not found.
    """
    if rule_system_id in _RULE_SYSTEM_CACHE:
        return _RULE_SYSTEM_CACHE[rule_system_id]

    data_root = Path(os.environ.get("STORYTELLER_DATA_ROOT", "./data"))
    path = data_root / "static" / "rule_systems" / f"{rule_system_id}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Rule system '{rule_system_id}' not found at {path}. "
            f"Create {path} or set STORYTELLER_RULE_SYSTEM to an existing rule system id."
        )
    text = path.read_text(encoding="utf-8")
    _RULE_SYSTEM_CACHE[rule_system_id] = text
    logger.info("ResolutionAgent: loaded rule system '%s' (%d chars)", rule_system_id, len(text))
    return text


def _get_active_rule_system(state: GameState) -> str:
    """Return the active rule system corpus text for this game state."""
    # Era pack can specify a rule_system_id in setting_rules (future)
    rule_system_id = os.environ.get("STORYTELLER_RULE_SYSTEM", "storyteller_core")
    return _load_rule_system(rule_system_id)


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def _time_of_day(world_time_minutes: int) -> str:
    day_minutes = world_time_minutes % 1440
    if day_minutes < 360:
        return "late night"
    elif day_minutes < 720:
        return "morning"
    elif day_minutes < 1080:
        return "afternoon"
    elif day_minutes < 1260:
        return "evening"
    else:
        return "night"


def _arc_stage(state: GameState) -> str:
    campaign = getattr(state, "campaign", None) or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ws = ws if isinstance(ws, dict) else {}
    arc_state = ws.get("arc_state") or {}
    return arc_state.get("current_stage", "SETUP")


def _build_npc_list(state: GameState) -> str:
    if not state.present_npcs:
        return "No NPCs present."
    lines = []
    for npc in state.present_npcs:
        name = npc.get("name") or npc.get("id") or "Unknown"
        role = npc.get("role") or ""
        rel = npc.get("relationship_score")
        npc_id = npc.get("id") or name.lower().replace(" ", "-")
        rel_str = f", relationship: {rel}" if rel is not None else ""
        role_str = f" ({role})" if role else ""
        lines.append(f"- {name}{role_str} [id: {npc_id}]{rel_str}")
    return "\n".join(lines)


def _build_inventory_summary(state: GameState) -> str:
    if not state.player or not state.player.inventory:
        return "Empty"
    items = []
    for item in state.player.inventory[:10]:
        name = item.get("item_name") or item.get("name") or "unknown"
        qty = item.get("quantity") or item.get("quantity_delta") or 1
        items.append(f"{name} x{qty}")
    return ", ".join(items) if items else "Empty"


def _player_id(state: GameState) -> str:
    if state.player and getattr(state.player, "character_id", None):
        return state.player.character_id
    return state.player_id


def _build_user_prompt(state: GameState) -> str:
    campaign = getattr(state, "campaign", None) or {}
    world_time = int(campaign.get("world_time_minutes") or 0) if isinstance(campaign, dict) else 0

    player = state.player
    player_name = (player.name if player else None) or "Unknown"
    stats = (player.stats if player else {}) or {}
    hp = (player.hp_current if player else 0) or 0
    arc = _arc_stage(state)

    # Recent narrative: last 1 turn is enough to avoid token bloat
    recent = ""
    if state.recent_narrative:
        recent = state.recent_narrative[-1][:800]
    elif state.history:
        recent = state.history[-1][:500]

    active_companions = []
    try:
        campaign_ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
        if isinstance(campaign_ws, dict):
            active_companions = campaign_ws.get("party", []) or []
    except Exception:
        pass

    return f"""[SCENE CONTEXT]
Location: {state.current_location or "unknown"}
Planet: {state.current_planet or "unknown"}
Time of Day: {_time_of_day(world_time)}
Arc Stage: {arc}
Active Companions: {", ".join(active_companions) if active_companions else "none"}

[PLAYER]
Name: {player_name}
Player ID: {_player_id(state)}
Stats: {json.dumps(stats)}
HP: {hp}
Inventory: {_build_inventory_summary(state)}

[PRESENT NPCs]
{_build_npc_list(state)}

[RECENT NARRATIVE]
{recent if recent else "This is the start of the scene."}

[PLAYER ACTION]
"{state.user_input}"

Resolve this action as Game Master. Be contextually fair and let consequences be real.
Output only the JSON object — no markdown, no explanation."""


def _build_system_prompt(rule_system_text: str) -> str:
    return f"""You are the Game Master AI for a narrative RPG. Your role is to resolve player actions
mechanically and fairly using the STORYTELLER CORE RULES below.

You receive a scene context and a player action. You must:
1. Classify the action type
2. Assess the difficulty band based on context
3. Simulate a narrative dice roll
4. Produce a full JSON resolution object

Return ONLY a single valid JSON object. No markdown code fences. No preamble.

[STORYTELLER CORE RULES]
{rule_system_text}

[JSON OUTPUT SCHEMA]
Return this exact structure (all fields required):
{{
  "action_type": string,         // TRAVEL|ATTACK|SNEAK|PERSUADE|INVESTIGATE|INTERACT|IDLE|TALK
  "difficulty": string,          // Trivial|Easy|Moderate|Hard|Formidable|Extreme
  "dice_result": string,         // Triumph|Success+Advantage|Success|Success+Threat|Failure+Advantage|Failure|Failure+Threat|Despair
  "success": boolean,
  "time_cost_minutes": integer,  // 0-1440
  "narrative_facts": [string],   // 2-5 precise facts for the Narrator to include
  "events": [                    // game state changes — only generate justified events
    {{"event_type": string, "payload": object}}
  ],
  "outcome_summary": string,     // max 120 chars
  "tone_tag": string,            // PARAGON|RENEGADE|INVESTIGATE|NEUTRAL
  "alignment_delta": object,     // e.g. {{"light_dark": 1, "paragon_renegade": -1}}
  "faction_reputation_delta": object,
  "companion_affinity_delta": object,
  "companion_reaction_reason": object,
  "stress_delta": integer,       // -3 to +3
  "critical_outcome": string|null,  // CRITICAL_SUCCESS|CRITICAL_FAILURE|null
  "world_reaction_needed": boolean,
  "invalid_action": boolean
}}"""


# ---------------------------------------------------------------------------
# JSON parsing and normalization
# ---------------------------------------------------------------------------

_VALID_OUTCOME_CATEGORIES = {
    "Triumph", "Success+Advantage", "Success", "Success+Threat",
    "Failure+Advantage", "Failure", "Failure+Threat", "Despair",
}
_SUCCESS_OUTCOMES = {"Triumph", "Success+Advantage", "Success", "Success+Threat"}
_CRITICAL_SUCCESS_OUTCOMES = {"Triumph"}
_CRITICAL_FAILURE_OUTCOMES = {"Despair"}
_WORLD_REACTION_OUTCOMES = {"Triumph", "Despair"}

_VALID_ACTION_TYPES = {"TRAVEL", "ATTACK", "SNEAK", "PERSUADE", "INVESTIGATE", "INTERACT", "IDLE", "TALK"}
_VALID_TONE_TAGS = {"PARAGON", "RENEGADE", "INVESTIGATE", "NEUTRAL"}
_VALID_EVENT_TYPES = {"MOVE", "DAMAGE", "HEAL", "ITEM_GET", "ITEM_LOSE", "FLAG_SET", "RELATIONSHIP"}


def _parse_events(raw_events: Any) -> list[Event]:
    """Parse LLM-produced event list into validated Event objects."""
    if not isinstance(raw_events, list):
        return []
    events = []
    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        event_type = str(raw.get("event_type", "")).upper()
        if event_type not in _VALID_EVENT_TYPES:
            logger.warning("ResolutionAgent: unknown event_type '%s' — skipped", event_type)
            continue
        payload = raw.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        events.append(Event(event_type=event_type, payload=payload))
    return events


def _normalize_output(raw: dict, state: GameState) -> MechanicOutput:
    """Normalize and validate the LLM JSON output into a MechanicOutput."""
    action_type = str(raw.get("action_type", "INTERACT")).upper()
    if action_type not in _VALID_ACTION_TYPES:
        action_type = "INTERACT"

    dice_result = str(raw.get("dice_result", "Success"))
    if dice_result not in _VALID_OUTCOME_CATEGORIES:
        dice_result = "Success"

    success_val = raw.get("success")
    if success_val is None:
        success_val = dice_result in _SUCCESS_OUTCOMES
    else:
        success_val = bool(success_val)

    time_cost = raw.get("time_cost_minutes", get_time_cost(action_type))
    try:
        time_cost = max(0, min(1440, int(time_cost)))
    except (TypeError, ValueError):
        time_cost = get_time_cost(action_type)

    narrative_facts = []
    for fact in raw.get("narrative_facts", []):
        if isinstance(fact, str) and fact.strip():
            narrative_facts.append(fact.strip())

    events = _parse_events(raw.get("events", []))

    outcome_summary = str(raw.get("outcome_summary", f"{action_type}: {dice_result}"))[:200]

    tone_tag = str(raw.get("tone_tag", "NEUTRAL")).upper()
    if tone_tag not in _VALID_TONE_TAGS:
        tone_tag = "NEUTRAL"

    def _clean_int_dict(d: Any) -> dict[str, int]:
        if not isinstance(d, dict):
            return {}
        out = {}
        for k, v in d.items():
            try:
                out[str(k)] = int(v)
            except (TypeError, ValueError):
                pass
        return out

    def _clean_str_dict(d: Any) -> dict[str, str]:
        if not isinstance(d, dict):
            return {}
        return {str(k): str(v) for k, v in d.items()}

    alignment_delta = _clean_int_dict(raw.get("alignment_delta", {}))
    faction_reputation_delta = _clean_int_dict(raw.get("faction_reputation_delta", {}))
    companion_affinity_delta = _clean_int_dict(raw.get("companion_affinity_delta", {}))
    companion_reaction_reason = _clean_str_dict(raw.get("companion_reaction_reason", {}))

    try:
        stress_delta = max(-3, min(3, int(raw.get("stress_delta", 0))))
    except (TypeError, ValueError):
        stress_delta = 0

    critical_outcome = raw.get("critical_outcome")
    if dice_result in _CRITICAL_SUCCESS_OUTCOMES:
        critical_outcome = "CRITICAL_SUCCESS"
    elif dice_result in _CRITICAL_FAILURE_OUTCOMES:
        critical_outcome = "CRITICAL_FAILURE"
    elif critical_outcome not in ("CRITICAL_SUCCESS", "CRITICAL_FAILURE"):
        critical_outcome = None

    world_reaction_needed = bool(raw.get("world_reaction_needed", False))
    if dice_result in _WORLD_REACTION_OUTCOMES:
        world_reaction_needed = True

    invalid_action = bool(raw.get("invalid_action", False))

    difficulty = str(raw.get("difficulty", "Moderate"))

    return MechanicOutput(
        action_type=action_type,
        time_cost_minutes=time_cost,
        events=events,
        outcome_summary=outcome_summary,
        success=None if invalid_action else success_val,
        narrative_facts=narrative_facts,
        tone_tag=tone_tag,
        alignment_delta=alignment_delta,
        faction_reputation_delta=faction_reputation_delta,
        companion_affinity_delta=companion_affinity_delta,
        companion_reaction_reason=companion_reaction_reason,
        stress_delta=stress_delta,
        critical_outcome=critical_outcome,
        world_reaction_needed=world_reaction_needed,
        invalid_action=invalid_action,
        # New narrative dice fields
        dice_result=dice_result,
        difficulty=difficulty,
    )


# ---------------------------------------------------------------------------
# ResolutionAgent
# ---------------------------------------------------------------------------

class ResolutionAgent:
    """LLM-based Game Master that resolves player actions using the Storyteller Core rule system.

    Replaces the deterministic d20 Python engine. The LLM reads the active rule system corpus
    and acts as a contextual, fair Game Master. All action classification, difficulty assessment,
    dice simulation, and event generation is LLM-driven.

    No deterministic fallback. If the LLM fails, the exception propagates to the caller.
    """

    def __init__(self) -> None:
        self._llm = AgentLLM("mechanic")

    def resolve(self, state: GameState) -> MechanicOutput:
        """Resolve player action via LLM Game Master. Returns validated MechanicOutput."""
        user_input = (state.user_input or "").strip()
        if not user_input:
            from backend.app.time_economy import DIALOGUE_ONLY_MINUTES
            return MechanicOutput(
                action_type="IDLE",
                time_cost_minutes=0,
                narrative_facts=["No input provided."],
                outcome_summary="No input.",
                invalid_action=True,
                dice_result="Failure",
                difficulty="Trivial",
            )

        rule_system_text = _get_active_rule_system(state)
        system_prompt = _build_system_prompt(rule_system_text)
        user_prompt = _build_user_prompt(state)

        logger.debug(
            "ResolutionAgent: resolving action for campaign=%s turn=%d input=%r",
            state.campaign_id, state.turn_number, user_input[:60],
        )

        raw_text = self._llm.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
        )

        try:
            raw_json = json.loads(ensure_json(raw_text))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error(
                "ResolutionAgent: JSON parse failed after LLM retry: %s. Raw (truncated): %r",
                exc, str(raw_text)[:300],
            )
            raise ValueError(
                f"ResolutionAgent: LLM returned unparseable JSON. "
                f"Raw (truncated): {str(raw_text)[:200]}"
            ) from exc

        result = _normalize_output(raw_json, state)
        logger.info(
            "ResolutionAgent: %s | %s | %s | success=%s",
            result.action_type, result.difficulty, result.dice_result, result.success,
        )
        return result
