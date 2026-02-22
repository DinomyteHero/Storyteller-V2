"""WorldMindAgent: LLM-based world simulation replacing the deterministic faction engine.

Replaces simulate_faction_tick() in faction_engine.py. The LLM reads the current
world state (factions, NPC states, faction memory, player action + outcome) and
reasons about how the living world responds off-screen — generating contextual rumors,
faction moves, and hidden plot events causally connected to player behavior.

No deterministic fallbacks. If the LLM fails, the exception propagates to the caller.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM, ensure_json
from shared.schemas import WorldSimOutput

logger = logging.getLogger(__name__)


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


def _build_factions_summary(active_factions: list[dict]) -> str:
    if not active_factions:
        return "No active factions."
    lines = []
    for f in active_factions:
        name = f.get("name", "Unknown")
        goal = f.get("current_goal", "unknown goal")
        resources = f.get("resources", 5)
        location = f.get("location", "unknown")
        hostile = "HOSTILE" if f.get("is_hostile") else "neutral"
        lines.append(
            f"- {name}: goal={goal!r}, resources={resources}/10, "
            f"location={location}, stance={hostile}"
        )
    return "\n".join(lines)


def _build_faction_memory_summary(faction_memory: dict[str, dict]) -> str:
    if not faction_memory:
        return "No faction memory."
    lines = []
    for fname, mem in faction_memory.items():
        plan = mem.get("multi_turn_plan", "")
        progress = mem.get("plan_progress", 0)
        recent = (mem.get("recent_actions") or [])[-2:]
        if plan:
            lines.append(f"- {fname}: plan={plan!r} (progress: {progress} ticks)")
        if recent:
            lines.append(f"  Recent actions: {'; '.join(recent)}")
    return "\n".join(lines) if lines else "No faction memory."


def _build_npc_summary(known_npcs: list[dict], npc_states: dict[str, dict]) -> str:
    if not known_npcs:
        return "No known NPCs."
    lines = []
    for npc in known_npcs[:8]:  # cap to avoid token bloat
        npc_id = npc.get("character_id") or npc.get("id", "")
        name = npc.get("name", "Unknown")
        loc = npc.get("location_id", "unknown")
        rel = npc.get("relationship_score", 0)
        state = npc_states.get(npc_id) or npc_states.get(name) or {}
        goal = state.get("current_goal", "")
        emotion = state.get("emotional_state", "")
        line = f"- {name} [{npc_id}]: location={loc}, relationship={rel:+d}"
        if goal:
            line += f", goal={goal!r}"
        if emotion:
            line += f", emotional_state={emotion}"
        lines.append(line)
    return "\n".join(lines)


def _build_system_prompt() -> str:
    return """\
You are the World Mind — the off-screen conscience of a living narrative RPG world.
Your role is to simulate how the world changes BETWEEN turns based on faction agendas,
NPC motivations, and the player's most recent action.

You receive:
- Active factions with goals, resources, locations, and stance
- Faction memory (multi-turn plans in progress)
- Known NPCs and their current states
- The player's action and how it resolved (success/failure/mixed)
- Arc stage and world context

You must produce a JSON object describing off-screen world activity:
1. RUMORS — What would bystanders hear? Public, concrete, specific, atmospheric.
2. FACTION MOVES — What did factions do off-screen? Hidden from player.
3. HIDDEN EVENTS — Secret plot developments. GM-only. May become future quest hooks.
4. FACTION UPDATES — Did any faction's goals, resources, or location shift?
5. FACTION MEMORY — Update multi-turn plans based on what just happened.

CRITICAL RULES:
- Every rumor must feel causally connected to either the player's action or a faction's plan.
- Faction moves must reflect each faction's stated current_goal and resource level.
- Use the resolution outcome to drive world reactions (e.g., if player failed to stop an
  assassination, the target is dead — factions react accordingly).
- At CLIMAX: dramatic confrontations, high-stakes moves, desperate faction gambits.
- At SETUP: slower buildup, factions consolidating, establishing quiet tensions.
- At RISING: mounting pressure, factions committing resources, rumors escalating.
- At RESOLUTION: aftermath, winners consolidating, losers regrouping.
- Rumors: 1-2 atmospheric sentences, written as overheard gossip or traveler tales.
- Do NOT generate rumors or moves unrelated to the game state provided.

Return ONLY a single valid JSON object. No markdown fences. No preamble.

[JSON OUTPUT SCHEMA]
{
  "elapsed_time_summary": string,      // 1 sentence: how off-screen time passed
  "new_rumors": [string],              // 1-3 specific public rumors
  "faction_moves": [string],           // 1-2 off-screen faction actions (hidden)
  "hidden_events": [string],           // 0-2 secret GM-only plot events
  "updated_factions": [                // Updated state for ALL active factions
    {
      "name": string,
      "current_goal": string,
      "resources": integer,            // 1-10
      "location": string,
      "is_hostile": boolean
    }
  ],
  "faction_memory": {                  // Updated multi-turn faction plans
    "<faction_name>": {
      "recent_actions": [string],      // max 5 entries, most recent last
      "multi_turn_plan": string,       // current multi-step plan
      "plan_progress": integer         // 0-based tick counter
    }
  },
  "reactive_encounters": [             // 0-2 NPCs that should appear as consequences
    {
      "trigger": string,               // faction_move|npc_death|reputation_change|world_event
      "npc_archetype": string,         // bounty_hunter|emissary|avenger|opportunist|informant
      "faction": string|null,
      "description": string,           // Brief context for EncounterManager
      "urgency": string,               // next_turn|within_3_turns|eventual
      "hostility": string              // hostile|neutral|friendly
    }
  ]
}"""


def _build_user_prompt(
    active_factions: list[dict],
    turn_number: int,
    player_location: str,
    arc_stage: str,
    world_time_minutes: int,
    travel_occurred: bool,
    world_reaction_needed: bool,
    user_action_summary: str,
    mechanic_result_summary: str,
    faction_memory: dict[str, dict],
    npc_states: dict[str, dict],
    known_npcs: list[dict],
) -> str:
    trigger_parts = []
    if travel_occurred:
        trigger_parts.append("player traveled to new location")
    if world_reaction_needed:
        trigger_parts.append("major world event requiring faction response")
    if not trigger_parts:
        trigger_parts.append("time tick boundary")
    trigger_str = "; ".join(trigger_parts)

    return f"""\
[WORLD STATE — Turn {turn_number}]
Arc Stage: {arc_stage}
Time of Day: {_time_of_day(world_time_minutes)}
Player Location: {player_location}
Simulation Trigger: {trigger_str}

[ACTIVE FACTIONS]
{_build_factions_summary(active_factions)}

[FACTION MEMORY (Multi-Turn Plans)]
{_build_faction_memory_summary(faction_memory)}

[KNOWN NPCs]
{_build_npc_summary(known_npcs, npc_states)}

[PLAYER'S LAST ACTION]
{user_action_summary or "No significant player action this tick."}

[RESOLUTION OUTCOME]
{mechanic_result_summary or "Action resolved normally."}

Simulate the world's off-screen response. What do factions do? What rumors spread?
What hidden events unfold? Update faction goals and plans accordingly.
Output only the JSON object — no markdown, no explanation."""


# ---------------------------------------------------------------------------
# Output normalization
# ---------------------------------------------------------------------------


def _normalize_output(
    raw: dict,
    active_factions: list[dict],
    faction_memory: dict[str, dict],
    npc_states: dict[str, dict],
) -> WorldSimOutput:
    """Normalize and validate LLM JSON into a WorldSimOutput."""
    elapsed = str(raw.get("elapsed_time_summary", "Time passes quietly."))[:200]

    # new_rumors: list of strings, cap at 3
    new_rumors: list[str] = []
    for r in (raw.get("new_rumors") or []):
        if isinstance(r, str) and r.strip():
            new_rumors.append(r.strip()[:300])
    new_rumors = new_rumors[:3]

    # faction_moves: list of strings, cap at 2
    faction_moves: list[str] = []
    for m in (raw.get("faction_moves") or []):
        if isinstance(m, str) and m.strip():
            faction_moves.append(m.strip()[:300])
    faction_moves = faction_moves[:2]

    # hidden_events: list of strings, cap at 2
    hidden_events: list[str] = []
    for e in (raw.get("hidden_events") or []):
        if isinstance(e, str) and e.strip():
            hidden_events.append(e.strip()[:300])
    hidden_events = hidden_events[:2]

    # updated_factions: merge LLM output with original data for safety
    updated_factions: list[dict] = []
    raw_factions = raw.get("updated_factions") or []
    if raw_factions and isinstance(raw_factions, list):
        orig_by_name = {f.get("name", ""): f for f in active_factions}
        for rf in raw_factions:
            if not isinstance(rf, dict):
                continue
            name = str(rf.get("name", "")).strip()
            if not name:
                continue
            orig = orig_by_name.get(name, {})
            resources = rf.get("resources", orig.get("resources", 5))
            try:
                resources = max(1, min(10, int(resources)))
            except (TypeError, ValueError):
                resources = max(1, min(10, int(orig.get("resources", 5))))
            updated_factions.append({
                "name": name,
                "current_goal": str(
                    rf.get("current_goal", orig.get("current_goal", ""))
                )[:200],
                "resources": resources,
                "location": str(
                    rf.get("location", orig.get("location", "unknown"))
                )[:100],
                "is_hostile": bool(rf.get("is_hostile", orig.get("is_hostile", False))),
            })
    # Fall back to original factions if LLM produced nothing usable
    if not updated_factions:
        updated_factions = list(active_factions)

    # faction_memory: validate and merge with existing memory
    raw_mem = raw.get("faction_memory") or {}
    new_faction_memory: dict[str, dict[str, Any]] = dict(faction_memory)
    if isinstance(raw_mem, dict):
        for fname, mem in raw_mem.items():
            if not isinstance(mem, dict):
                continue
            entry: dict[str, Any] = dict(new_faction_memory.get(fname) or {})
            raw_actions = mem.get("recent_actions") or []
            if isinstance(raw_actions, list):
                actions = [str(a)[:120] for a in raw_actions if isinstance(a, str)]
                entry["recent_actions"] = actions[-5:]
            plan = mem.get("multi_turn_plan")
            if plan and isinstance(plan, str):
                entry["multi_turn_plan"] = plan[:200]
            progress = mem.get("plan_progress")
            if progress is not None:
                try:
                    entry["plan_progress"] = int(progress)
                except (TypeError, ValueError):
                    pass
            new_faction_memory[fname] = entry

    # V1.1: Normalize reactive_encounters
    reactive_encounters: list[dict[str, Any]] = []
    raw_re = raw.get("reactive_encounters") or []
    if isinstance(raw_re, list):
        for enc in raw_re[:3]:  # Cap at 3
            if not isinstance(enc, dict):
                continue
            reactive_encounters.append({
                "trigger": str(enc.get("trigger", "world_event"))[:50],
                "npc_archetype": str(enc.get("npc_archetype", "informant"))[:30],
                "faction": str(enc.get("faction", ""))[:50] or None,
                "description": str(enc.get("description", ""))[:200],
                "urgency": str(enc.get("urgency", "within_3_turns"))[:20],
                "hostility": str(enc.get("hostility", "neutral"))[:20],
            })

    return WorldSimOutput(
        elapsed_time_summary=elapsed,
        faction_moves=faction_moves,
        new_rumors=new_rumors,
        hidden_events=hidden_events,
        updated_factions=updated_factions if updated_factions else None,
        faction_memory=new_faction_memory,
        # NPC states are managed by MemoryAgent (commit.py); pass through unchanged
        npc_states=npc_states,
        reactive_encounters=reactive_encounters,
    )


# ---------------------------------------------------------------------------
# WorldMindAgent
# ---------------------------------------------------------------------------


class WorldMindAgent:
    """LLM-based world simulation replacing the deterministic faction engine.

    Generates contextual world responses to player actions — rumors that spread
    through cantinas, factions repositioning operatives, hidden plot events that
    feel like natural consequences of the player's choices rather than random
    template draws from a seeded RNG.

    No deterministic fallback. If the LLM fails, the exception propagates.
    """

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm if llm is not None else AgentLLM("world_mind")

    def simulate(
        self,
        active_factions: list[dict],
        turn_number: int,
        player_location: str,
        arc_stage: str = "SETUP",
        world_time_minutes: int = 0,
        travel_occurred: bool = False,
        world_reaction_needed: bool = False,
        user_action_summary: str = "",
        mechanic_result_summary: str = "",
        faction_memory: dict[str, dict] | None = None,
        npc_states: dict[str, dict] | None = None,
        known_npcs: list[dict] | None = None,
    ) -> WorldSimOutput:
        """Simulate off-screen world activity via LLM. Returns WorldSimOutput.

        Args:
            active_factions: Current faction state dicts (name, goal, resources,
                location, is_hostile).
            turn_number: Current turn number.
            player_location: Player's current location ID.
            arc_stage: Story arc stage (SETUP/RISING/CLIMAX/RESOLUTION).
            world_time_minutes: Current world time in minutes.
            travel_occurred: Whether the player travelled this turn.
            world_reaction_needed: Whether a major world event demands a reaction.
            user_action_summary: Brief description of what the player did.
            mechanic_result_summary: The narrative outcome of the player's action.
            faction_memory: Existing multi-turn faction plan memory.
            npc_states: Existing NPC state dict (passed through unchanged).
            known_npcs: Known NPCs from the characters table.
        """
        if not active_factions:
            return WorldSimOutput(
                elapsed_time_summary="Time passes quietly.",
                faction_moves=[],
                new_rumors=[],
                hidden_events=[],
                updated_factions=None,
                faction_memory=faction_memory or {},
                npc_states=npc_states or {},
            )

        _faction_memory = faction_memory or {}
        _npc_states = npc_states or {}
        _known_npcs = known_npcs or []

        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(
            active_factions=active_factions,
            turn_number=turn_number,
            player_location=player_location,
            arc_stage=arc_stage,
            world_time_minutes=world_time_minutes,
            travel_occurred=travel_occurred,
            world_reaction_needed=world_reaction_needed,
            user_action_summary=user_action_summary,
            mechanic_result_summary=mechanic_result_summary,
            faction_memory=_faction_memory,
            npc_states=_npc_states,
            known_npcs=_known_npcs,
        )

        logger.debug(
            "WorldMindAgent: simulating turn=%d arc=%s factions=%d "
            "trigger=travel:%s,reaction:%s",
            turn_number, arc_stage, len(active_factions),
            travel_occurred, world_reaction_needed,
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
                "WorldMindAgent: JSON parse failed: %s. Raw (truncated): %r",
                exc, str(raw_text)[:300],
            )
            raise ValueError(
                f"WorldMindAgent: LLM returned unparseable JSON. "
                f"Raw (truncated): {str(raw_text)[:200]}"
            ) from exc

        result = _normalize_output(raw_json, active_factions, _faction_memory, _npc_states)
        logger.info(
            "WorldMindAgent: %d rumors, %d faction_moves, %d hidden_events",
            len(result.new_rumors), len(result.faction_moves), len(result.hidden_events),
        )
        return result
