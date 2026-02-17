"""MemoryAgent: LLM-based NPC narrative memory system.

After each turn, updates per-NPC narrative memory stored in
world_state_json["npc_states"]. Each NPC entry gains:
  - emotional_state: how the NPC feels right now (1–2 adjectives)
  - memories: curated list of key interaction facts (max 10)
  - agenda: what this NPC wants from the player
  - next_move: what the NPC is likely to do at the next meeting

This memory is injected into the Narrator and Director context so that every
encounter with a returning NPC feels like a continuation of a real relationship
rather than a cold restart.

No deterministic fallbacks. If the LLM fails, the exception propagates and
the commit node handles it as a non-fatal warning.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM, ensure_json

logger = logging.getLogger(__name__)

_MAX_MEMORIES_PER_NPC = 10
_MAX_NARRATIVE_CHARS = 600
_MEMORY_SYSTEM_PROMPT = """You are the Memory Keeper for an AI narrative RPG. After each story turn you update \
the narrative memory of NPCs who appeared in the scene.

Your job: read what just happened, then update each NPC's memory record.

Rules:
- Keep memories concrete and specific (what actually happened, not vague generalities)
- Each memory entry must start with "Turn {N}:" so the reader knows when it happened
- Keep the memories list to AT MOST 10 entries — if there are already 10, remove the oldest one before adding
- emotional_state must be 1–3 vivid adjectives reflecting their current feeling toward the player
- agenda must be 1 sentence about what this NPC wants FROM the player
- next_move must be 1 sentence about what this NPC will likely DO next (not say — do)
- Be psychologically honest: a hostile NPC does not suddenly like the player after one good turn
- DO NOT add memories that didn't actually happen in this turn's narrative

Return ONLY a JSON object. No markdown, no preamble.

Output schema:
{
  "npc_updates": [
    {
      "npc_id": string,
      "emotional_state": string,
      "memories": [string],
      "agenda": string,
      "next_move": string
    }
  ]
}"""


def _build_events_summary(npc_id: str, npc_name: str, events: list[dict]) -> str:
    """Extract events relevant to this specific NPC."""
    relevant = []
    npc_id_lower = (npc_id or "").lower()
    npc_name_lower = (npc_name or "").lower()

    for e in events:
        etype = str(e.get("event_type", "")).upper()
        payload = e.get("payload") or {}

        # RELATIONSHIP event
        if etype == "RELATIONSHIP":
            target = str(payload.get("npc_id", "")).lower()
            if target in (npc_id_lower, npc_name_lower):
                delta = int(payload.get("delta", 0))
                reason = payload.get("reason", "")
                sign = "+" if delta >= 0 else ""
                relevant.append(f"Relationship delta {sign}{delta}: {reason}")

        # DAMAGE targeting this NPC
        elif etype == "DAMAGE":
            target = str(payload.get("character_id", "")).lower()
            if target in (npc_id_lower, npc_name_lower):
                amount = payload.get("amount", 0)
                relevant.append(f"Took {amount} damage from the player")

        # DIALOGUE attributed to this NPC
        elif etype == "DIALOGUE":
            speaker = str(payload.get("speaker", "")).lower()
            if speaker in (npc_id_lower, npc_name_lower):
                text = (payload.get("text") or "")[:80]
                relevant.append(f"Spoke: \"{text}\"")

        # FLAG_SET relevant to scene (all NPCs share environmental flags)
        elif etype == "FLAG_SET":
            key = str(payload.get("key", "")).lower()
            val = payload.get("value")
            if key in ("public_violence", "combat_alert", "wanted_level", "stealth_broken"):
                relevant.append(f"Scene flag: {key}={val}")

    return "\n".join(f"  - {r}" for r in relevant) if relevant else "  (no direct events)"


def _build_user_prompt(
    final_text: str,
    turn_number: int,
    present_npcs: list[dict],
    existing_npc_states: dict[str, dict],
    events: list[dict],
) -> str:
    narrative_excerpt = (final_text or "")[:_MAX_NARRATIVE_CHARS]
    if len(final_text or "") > _MAX_NARRATIVE_CHARS:
        narrative_excerpt += "…"

    npc_sections = []
    for npc in present_npcs:
        npc_id = npc.get("id") or ""
        npc_name = npc.get("name") or npc_id or "Unknown"
        relationship_score = npc.get("relationship_score", 0)

        existing = existing_npc_states.get(npc_id) or existing_npc_states.get(npc_name) or {}
        current_memories = existing.get("memories") or []
        current_emotional = existing.get("emotional_state") or "neutral"
        current_agenda = existing.get("agenda") or "(unknown)"
        current_next_move = existing.get("next_move") or "(unknown)"

        memories_str = "\n".join(f"    {m}" for m in current_memories[-8:]) or "    (no prior memories)"
        events_str = _build_events_summary(npc_id, npc_name, events)

        section = f"""NPC: {npc_name} [id: {npc_id}]
  relationship_score: {relationship_score}
  current emotional_state: {current_emotional}
  current agenda: {current_agenda}
  current next_move: {current_next_move}
  prior memories ({len(current_memories)} entries, showing last 8):
{memories_str}
  events this turn involving this NPC:
{events_str}"""
        npc_sections.append(section)

    npcs_block = "\n\n".join(npc_sections)

    return f"""[TURN {turn_number} NARRATIVE]
{narrative_excerpt}

[NPCs TO UPDATE]
{npcs_block}

Update each NPC's memory based on what actually happened in this turn's narrative.
Return only the JSON object."""


def update_npc_states(
    llm: AgentLLM,
    final_text: str,
    turn_number: int,
    present_npcs: list[dict],
    existing_npc_states: dict[str, dict],
    events: list[dict],
) -> dict[str, dict]:
    """Run the LLM memory update for all present NPCs.

    Returns an updated copy of npc_states with narrative memory added/refreshed
    for each NPC present in the scene.

    existing_npc_states is NOT modified in place.
    """
    if not present_npcs:
        return existing_npc_states

    user_prompt = _build_user_prompt(
        final_text=final_text,
        turn_number=turn_number,
        present_npcs=present_npcs,
        existing_npc_states=existing_npc_states,
        events=events,
    )

    logger.debug(
        "MemoryAgent: updating memory for %d NPC(s) at turn %d",
        len(present_npcs), turn_number,
    )

    raw_text = llm.complete(
        system_prompt=_MEMORY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        json_mode=True,
    )

    try:
        raw_json = json.loads(ensure_json(raw_text))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(
            f"MemoryAgent: LLM returned unparseable JSON. "
            f"Raw (truncated): {str(raw_text)[:200]}"
        ) from exc

    npc_updates = raw_json.get("npc_updates") or []
    updated_states = dict(existing_npc_states)

    for update in npc_updates:
        npc_id = str(update.get("npc_id") or "").strip()
        if not npc_id:
            continue

        # Find the matching NPC's current relationship_score (preserve it)
        rel_score = 0
        for npc in present_npcs:
            if npc.get("id") == npc_id or npc.get("name") == npc_id:
                rel_score = int(npc.get("relationship_score") or 0)
                break
        existing = updated_states.get(npc_id) or {}
        rel_score = existing.get("relationship_score", rel_score)

        # Validate and cap memories list
        memories = update.get("memories") or []
        if not isinstance(memories, list):
            memories = []
        memories = [str(m).strip() for m in memories if isinstance(m, str) and m.strip()]
        memories = memories[:_MAX_MEMORIES_PER_NPC]

        emotional_state = str(update.get("emotional_state") or "neutral").strip()[:80]
        agenda = str(update.get("agenda") or "").strip()[:150]
        next_move = str(update.get("next_move") or "").strip()[:150]

        updated_states[npc_id] = {
            **existing,
            "relationship_score": rel_score,
            "emotional_state": emotional_state,
            "memories": memories,
            "agenda": agenda,
            "next_move": next_move,
        }
        logger.info(
            "MemoryAgent: updated %s | state=%r | memories=%d",
            npc_id, emotional_state, len(memories),
        )

    return updated_states


def format_npc_memory_for_narrator(npc_id: str, npc_states: dict[str, dict]) -> str:
    """Return a compact narrative memory block for a single NPC, for Narrator injection.

    Returns empty string if no memory exists for this NPC.
    """
    state = npc_states.get(npc_id)
    if not state:
        return ""

    lines = []
    emotional = state.get("emotional_state")
    if emotional:
        lines.append(f"  Emotional state: {emotional}")

    memories = state.get("memories") or []
    if memories:
        # Show last 3 memories for prompt efficiency
        recent = memories[-3:]
        lines.append("  Memory (recent):")
        for m in recent:
            lines.append(f"    - {m}")

    agenda = state.get("agenda")
    if agenda:
        lines.append(f"  Agenda toward player: {agenda}")

    next_move = state.get("next_move")
    if next_move:
        lines.append(f"  Likely next move: {next_move}")

    return "\n".join(lines) if lines else ""


class MemoryAgent:
    """LLM-based NPC narrative memory manager.

    Runs after each story turn to update per-NPC memory in world_state_json["npc_states"].
    Call update() from the commit node after the main DB transaction completes.
    """

    def __init__(self) -> None:
        self._llm = AgentLLM("memory")

    def update(
        self,
        world_state: dict[str, Any],
        final_text: str,
        turn_number: int,
        present_npcs: list[dict],
        events: list[dict],
    ) -> None:
        """Update NPC narrative memory in world_state["npc_states"] in place.

        Modifies world_state directly. Logs a warning on failure (non-fatal).
        """
        if not present_npcs or not final_text:
            return

        existing_npc_states = world_state.get("npc_states") or {}

        updated = update_npc_states(
            llm=self._llm,
            final_text=final_text,
            turn_number=turn_number,
            present_npcs=present_npcs,
            existing_npc_states=existing_npc_states,
            events=events,
        )
        world_state["npc_states"] = updated
