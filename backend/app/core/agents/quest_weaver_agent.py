"""QuestWeaverAgent: LLM-driven dynamic quest generation and completion evaluation.

Replaces the finite pre-authored YAML quest system for long campaigns (50-100+ turns).
The LLM reads current world state — factions, NPCs, arc stage, recent narrative,
consequence hints — and weaves 1-2 new quests that feel like natural outgrowths
of the player's story so far.

Two entry points:
  generate()            — creates new dynamic quests (every ~10 turns)
  evaluate_completion() — checks active dynamic quests against recent narrative

Dynamic quests are stored in world_state_json["dynamic_quests"] as a list of dicts.
Active quests (status="active") are injected into the Narrator/Director context.

No deterministic fallbacks. If the LLM fails, the exception propagates.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from backend.app.core.agents.base import AgentLLM, BaseAgent, ensure_json
from backend.app.prompts.registry import load_prompt

logger = logging.getLogger(__name__)

# How many dynamic quests to keep (completed + active)
MAX_DYNAMIC_QUESTS = 20
# How many active quests to target before generating more
TARGET_ACTIVE_QUESTS = 2


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------


def _format_existing_dynamic_quests(dynamic_quests: list[dict]) -> str:
    active = [q for q in dynamic_quests if q.get("status") == "active"]
    completed = [q for q in dynamic_quests if q.get("status") == "completed"]
    if not active and not completed:
        return "(No dynamic quests yet.)"
    lines = []
    if active:
        lines.append("Active quests:")
        for q in active:
            lines.append(f"  - [{q.get('id', '?')}] {q.get('title', '?')}: {q.get('description', '')[:80]}")
    if completed:
        lines.append("Completed quests (avoid repeating these themes):")
        for q in completed[-5:]:
            lines.append(f"  - {q.get('title', '?')}")
    return "\n".join(lines)


def _format_known_npcs_summary(known_npcs: list[str], npc_states: dict[str, dict]) -> str:
    if not known_npcs:
        return "(No known NPCs yet.)"
    lines = []
    for name in known_npcs[:8]:
        state = npc_states.get(name) or {}
        agenda = state.get("agenda", "")
        emotion = state.get("emotional_state", "")
        line = f"- {name}"
        if emotion:
            line += f" [{emotion}]"
        if agenda:
            line += f" — wants: {agenda[:60]}"
        lines.append(line)
    return "\n".join(lines)


def _format_active_factions(active_factions: list[dict]) -> str:
    if not active_factions:
        return "(No active factions.)"
    lines = []
    for f in active_factions[:5]:
        name = f.get("name", "?")
        goal = f.get("current_goal", "")[:60]
        hostile = " [HOSTILE]" if f.get("is_hostile") else ""
        lines.append(f"- {name}{hostile}: {goal}")
    return "\n".join(lines)


def _format_consequence_hints(consequence_hints: list[str]) -> str:
    if not consequence_hints:
        return "(None)"
    return "\n".join(f"- {h}" for h in consequence_hints[:5])


def _format_arc_hooks(arc_stage: str, dynamic_quests: list[dict]) -> str:
    """Format previous arc hooks and arc-stage-specific guidance for quest generation."""
    # Extract dangling_hooks from world_state arc_history (passed via dynamic_quests context)
    # The hooks are injected as a special entry in the quest context
    hooks = []
    for q in (dynamic_quests or []):
        if isinstance(q, dict) and q.get("_arc_dangling_hook"):
            hooks.append(q["_arc_dangling_hook"])

    parts = []
    if hooks:
        parts.append("[PREVIOUS ARC HOOKS (unresolved threads from earlier arcs)]")
        parts.extend(f"- {h}" for h in hooks[:5])
        parts.append("")

    # Arc-stage specific emphasis
    stage_emphasis = {
        "SETUP": "[ARC STAGE EMPHASIS: New arc beginning. Prioritize discovery and relationship quests.]",
        "RISING": "[ARC STAGE EMPHASIS: Stakes rising. Generate quests that entangle the player deeper.]",
        "CLIMAX": "[ARC STAGE EMPHASIS: Crisis point. Only time-pressured, high-consequence quests.]",
        "RESOLUTION": "",  # Should not reach here (blocked at trigger level)
    }
    emphasis = stage_emphasis.get(arc_stage, "")
    if emphasis:
        parts.append(emphasis)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# generate() — prompt builders
# ---------------------------------------------------------------------------


def _build_generate_system_prompt() -> str:
    return load_prompt("quest_weaver_generate_system")


def _build_generate_user_prompt(
    arc_stage: str,
    player_location: str,
    turn_number: int,
    known_npcs: list[str],
    npc_states: dict[str, dict],
    active_factions: list[dict],
    consequence_hints: list[str],
    established_facts: list[str],
    recent_narrative: str,
    dynamic_quests: list[dict],
) -> str:
    return f"""\
[WORLD STATE — Turn {turn_number}]
Arc Stage: {arc_stage}
Player Location: {player_location}

[KNOWN NPCs]
{_format_known_npcs_summary(known_npcs, npc_states)}

[ACTIVE FACTIONS]
{_format_active_factions(active_factions)}

[PLAYER OBLIGATIONS (Consequence Hints)]
{_format_consequence_hints(consequence_hints)}

[ESTABLISHED FACTS (recent)]
{chr(10).join(f"- {f}" for f in (established_facts or [])[-6:])}

[RECENT NARRATIVE (excerpt)]
{recent_narrative[:500] if recent_narrative else "(No recent narrative.)"}

[EXISTING QUESTS]
{_format_existing_dynamic_quests(dynamic_quests)}

{_format_arc_hooks(arc_stage, dynamic_quests)}
Weave 1-2 new quests that emerge naturally from the tensions above.
Output only the JSON object."""


# ---------------------------------------------------------------------------
# evaluate_completion() — prompt builders
# ---------------------------------------------------------------------------


def _build_evaluate_system_prompt() -> str:
    return load_prompt("quest_weaver_evaluate_system")


def _build_evaluate_user_prompt(
    active_quests: list[dict],
    final_text: str,
    events_summary: str,
) -> str:
    quest_lines = []
    for q in active_quests:
        quest_lines.append(f"\n[Quest: {q.get('id')} — {q.get('title')}]")
        quest_lines.append(f"Description: {q.get('description', '')}")
        stages = q.get("stages") or []
        stage_idx = q.get("current_stage_idx", 0)
        if stage_idx < len(stages):
            stage = stages[stage_idx]
            quest_lines.append(f"Current objective: {stage.get('objective', '')}")
            quest_lines.append(f"Narrative condition: {stage.get('narrative_condition', '')}")

    return f"""\
[ACTIVE QUESTS]
{"".join(quest_lines) if quest_lines else "(No active quests.)"}

[THIS TURN'S EVENTS]
{events_summary or "(No notable events.)"}

[NARRATED PROSE (this turn)]
{final_text[:700] if final_text else "(No narrative text.)"}

Evaluate which quests were completed, failed, or had a stage advance.
Output only the JSON object."""


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _normalize_generated_quests(
    raw: dict,
    existing_ids: set[str],
    turn_number: int,
) -> list[dict]:
    """Validate and normalize LLM-generated quest objects."""
    raw_quests = raw.get("quests") or []
    result = []
    for q in raw_quests:
        if not isinstance(q, dict):
            continue
        quest_id = str(q.get("id") or "").strip()
        if not quest_id:
            quest_id = f"dq-{uuid.uuid4().hex[:8]}"
        # Ensure unique ID
        while quest_id in existing_ids:
            quest_id = f"{quest_id}-{uuid.uuid4().hex[:4]}"
        existing_ids.add(quest_id)

        title = str(q.get("title") or "Unnamed Quest").strip()[:60]
        description = str(q.get("description") or "").strip()[:300]
        hook = str(q.get("hook") or "").strip()[:200]
        urgency = str(q.get("urgency") or "medium").lower()
        if urgency not in ("low", "medium", "high"):
            urgency = "medium"
        reward_hint = str(q.get("reward_hint") or "").strip()[:200]
        faction_connection = q.get("faction_connection")
        if faction_connection and not isinstance(faction_connection, str):
            faction_connection = str(faction_connection)

        # Normalize stages
        stages = []
        for s in (q.get("stages") or [])[:3]:
            if not isinstance(s, dict):
                continue
            stage_id = str(s.get("stage_id") or f"stage_{len(stages)+1}").strip()
            objective = str(s.get("objective") or "").strip()[:150]
            narrative_condition = str(s.get("narrative_condition") or "").strip()[:300]
            if objective:
                stages.append({
                    "stage_id": stage_id,
                    "objective": objective,
                    "narrative_condition": narrative_condition,
                })

        if not stages or not title:
            logger.debug("QuestWeaverAgent: skipping quest with no stages or title")
            continue

        result.append({
            "id": quest_id,
            "title": title,
            "description": description,
            "hook": hook,
            "urgency": urgency,
            "stages": stages,
            "reward_hint": reward_hint,
            "faction_connection": faction_connection,
            "generated_turn": turn_number,
            "current_stage_idx": 0,
            "status": "active",
        })
    return result


def _events_summary(events: list[dict]) -> str:
    lines = []
    for e in events:
        etype = str(e.get("event_type", "")).upper()
        payload = e.get("payload") or {}
        if etype == "MOVE":
            loc = payload.get("to_location") or payload.get("location_id", "")
            if loc:
                lines.append(f"Moved to: {loc}")
        elif etype == "DAMAGE":
            lines.append(f"Took {payload.get('amount', 0)} damage")
        elif etype == "NPC_SPAWN":
            name = payload.get("name", "")
            if name:
                lines.append(f"NPC introduced: {name}")
        elif etype == "FLAG_SET":
            key = payload.get("key", "")
            if key:
                lines.append(f"Flag: {key}={payload.get('value', '')}")
        elif etype == "RELATIONSHIP":
            npc = payload.get("npc_id", "")
            delta = payload.get("delta", 0)
            if npc:
                lines.append(f"Relationship {npc}: {delta:+d}")
    return "\n".join(f"- {l}" for l in lines) if lines else "(No notable events)"


# ---------------------------------------------------------------------------
# QuestWeaverAgent
# ---------------------------------------------------------------------------


class QuestWeaverAgent(BaseAgent):
    """LLM-driven dynamic quest generation and completion evaluation.

    Generates contextually-grounded quests from the living world state and
    evaluates active dynamic quest completion against recent narrative prose.

    dynamic_quests stored in world_state_json["dynamic_quests"] as a list.
    Each quest: id, title, description, hook, urgency, stages, reward_hint,
    faction_connection, generated_turn, current_stage_idx, status.
    """

    _role = "quest_weaver"

    def __init__(self) -> None:
        super().__init__()

    def generate(
        self,
        world_state: dict[str, Any],
        arc_stage: str,
        player_location: str,
        turn_number: int,
        recent_narrative: str,
    ) -> list[dict]:
        """Generate 1-2 new dynamic quests from current world state.

        Mutates world_state["dynamic_quests"] in place and returns the newly
        added quests. Skips generation if there are already TARGET_ACTIVE_QUESTS
        or more active quests.

        Args:
            world_state: Campaign world state dict (mutated).
            arc_stage: Current story arc stage.
            player_location: Current player location ID.
            turn_number: Current turn number.
            recent_narrative: Last 1-2 turns of narrated prose.

        Returns:
            List of newly generated quest dicts (may be empty).
        """
        dynamic_quests: list[dict] = list(world_state.get("dynamic_quests") or [])
        active_count = sum(1 for q in dynamic_quests if q.get("status") == "active")
        if active_count >= TARGET_ACTIVE_QUESTS:
            logger.debug(
                "QuestWeaverAgent: skipping generation (%d active quests >= target %d)",
                active_count, TARGET_ACTIVE_QUESTS,
            )
            return []

        existing_ids = {q.get("id", "") for q in dynamic_quests}
        ledger = world_state.get("ledger") or {}
        npc_states = world_state.get("npc_states") or {}
        active_factions = world_state.get("active_factions") or []

        system_prompt = _build_generate_system_prompt()
        user_prompt = _build_generate_user_prompt(
            arc_stage=arc_stage,
            player_location=player_location,
            turn_number=turn_number,
            known_npcs=list(world_state.get("known_npcs") or []),
            npc_states=npc_states,
            active_factions=active_factions,
            consequence_hints=list(ledger.get("consequence_hints") or []),
            established_facts=list(ledger.get("established_facts") or []),
            recent_narrative=recent_narrative,
            dynamic_quests=dynamic_quests,
        )

        logger.debug(
            "QuestWeaverAgent: generating quests (turn=%d arc=%s active=%d)",
            turn_number, arc_stage, active_count,
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
                "QuestWeaverAgent.generate: JSON parse failed: %s. Raw: %r",
                exc, str(raw_text)[:300],
            )
            raise ValueError(
                f"QuestWeaverAgent: LLM returned unparseable JSON. "
                f"Raw (truncated): {str(raw_text)[:200]}"
            ) from exc

        new_quests = _normalize_generated_quests(raw_json, existing_ids, turn_number)
        if new_quests:
            dynamic_quests.extend(new_quests)
            # Cap total quest history
            if len(dynamic_quests) > MAX_DYNAMIC_QUESTS:
                # Keep all active, trim completed from oldest
                active_qs = [q for q in dynamic_quests if q.get("status") == "active"]
                done_qs = [q for q in dynamic_quests if q.get("status") != "active"]
                done_qs = done_qs[-(MAX_DYNAMIC_QUESTS - len(active_qs)):]
                dynamic_quests = done_qs + active_qs
            world_state["dynamic_quests"] = dynamic_quests
            logger.info(
                "QuestWeaverAgent: generated %d new quests (turn %d)",
                len(new_quests), turn_number,
            )
        return new_quests

    def evaluate_completion(
        self,
        world_state: dict[str, Any],
        final_text: str,
        events: list[dict],
    ) -> list[str]:
        """Check active dynamic quests against recent narrative for completion/failure.

        Mutates world_state["dynamic_quests"] in place.

        Args:
            world_state: Campaign world state dict (mutated).
            final_text: Narrated prose from this turn.
            events: Turn events (list of dicts).

        Returns:
            List of player-facing notifications (e.g., "Quest completed: The Heist").
        """
        dynamic_quests: list[dict] = list(world_state.get("dynamic_quests") or [])
        active_quests = [q for q in dynamic_quests if q.get("status") == "active"]
        if not active_quests or not final_text:
            return []

        system_prompt = _build_evaluate_system_prompt()
        user_prompt = _build_evaluate_user_prompt(
            active_quests=active_quests,
            final_text=final_text,
            events_summary=_events_summary(events),
        )

        logger.debug(
            "QuestWeaverAgent: evaluating %d active quests", len(active_quests)
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
                "QuestWeaverAgent.evaluate_completion: JSON parse failed: %s",
                exc,
            )
            raise ValueError(
                f"QuestWeaverAgent: evaluation LLM returned unparseable JSON. "
                f"Raw (truncated): {str(raw_text)[:200]}"
            ) from exc

        completed_ids = set(raw_json.get("completed_quest_ids") or [])
        failed_ids = set(raw_json.get("failed_quest_ids") or [])
        advanced_ids = set(raw_json.get("stage_advanced_ids") or [])
        progress_notes = raw_json.get("progress_notes") or {}

        notifications: list[str] = []
        quest_by_id = {q.get("id"): q for q in dynamic_quests}

        for quest_id in completed_ids:
            q = quest_by_id.get(quest_id)
            if q and q.get("status") == "active":
                q["status"] = "completed"
                note = progress_notes.get(quest_id, "")
                notifications.append(f"Quest completed: {q.get('title', quest_id)}")
                if note:
                    logger.info("Quest completed %s: %s", quest_id, note)

        for quest_id in failed_ids:
            q = quest_by_id.get(quest_id)
            if q and q.get("status") == "active":
                q["status"] = "failed"
                notifications.append(f"Quest failed: {q.get('title', quest_id)}")

        for quest_id in advanced_ids - completed_ids - failed_ids:
            q = quest_by_id.get(quest_id)
            if q and q.get("status") == "active":
                stages = q.get("stages") or []
                current_idx = int(q.get("current_stage_idx") or 0)
                if current_idx + 1 < len(stages):
                    q["current_stage_idx"] = current_idx + 1
                    next_stage = stages[current_idx + 1]
                    notifications.append(
                        f"Quest progress ({q.get('title', quest_id)}): "
                        f"{next_stage.get('objective', '')}"
                    )

        world_state["dynamic_quests"] = dynamic_quests

        if notifications:
            logger.info(
                "QuestWeaverAgent: %d notifications: %s",
                len(notifications), notifications,
            )
        return notifications


def format_dynamic_quests_for_prompt(dynamic_quests: list[dict]) -> str:
    """Format active dynamic quests for injection into Director/Narrator prompts."""
    active = [q for q in (dynamic_quests or []) if q.get("status") == "active"]
    if not active:
        return ""
    lines = ["## Active Quest Hooks (player-generated, must reference narratively)"]
    for q in active:
        urgency_marker = {"high": "⚠ URGENT", "medium": "~", "low": "-"}.get(
            q.get("urgency", "medium"), "~"
        )
        lines.append(f"{urgency_marker} **{q.get('title', '?')}**: {q.get('description', '')}")
        stages = q.get("stages") or []
        stage_idx = int(q.get("current_stage_idx") or 0)
        if stage_idx < len(stages):
            obj = stages[stage_idx].get("objective", "")
            if obj:
                lines.append(f"   Current objective: {obj}")
        if q.get("hook"):
            lines.append(f"   Hook: {q['hook']}")
    return "\n".join(lines)
