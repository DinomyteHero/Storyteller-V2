"""Character legacy document generator for cross-campaign continuity."""
from __future__ import annotations

from typing import Any


def _extract_open_threads(world_state: dict[str, Any]) -> list[str]:
    ledger = world_state.get("narrative_ledger") or world_state.get("ledger") or {}
    if not isinstance(ledger, dict):
        return []
    threads = ledger.get("open_threads") or []
    out: list[str] = []
    for item in threads:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            txt = item.get("title") or item.get("text") or item.get("summary")
            if isinstance(txt, str) and txt.strip():
                out.append(txt.strip())
    seen: set[str] = set()
    deduped: list[str] = []
    for item in out:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:6]


def _extract_relationships(world_state: dict[str, Any]) -> list[dict[str, str]]:
    npc_states = world_state.get("npc_states") or {}
    if not isinstance(npc_states, dict):
        return []
    relationships: list[dict[str, str]] = []
    for npc_name, state in npc_states.items():
        if not isinstance(state, dict):
            continue
        emotional = str(state.get("emotional_state") or "neutral")
        agenda = str(state.get("agenda") or "unknown motives")
        relationships.append(
            {
                "name": str(npc_name),
                "relationship": "ally" if emotional in {"warm", "friendly", "loyal"} else "contact",
                "status": "unknown",
                "sentiment": f"{emotional}; agenda: {agenda}"[:180],
            }
        )
    return relationships[:6]


def _extract_key_possessions(world_state: dict[str, Any]) -> list[dict[str, str]]:
    items = world_state.get("key_items") or world_state.get("notable_items") or []
    if not isinstance(items, list):
        return []
    out: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            out.append({"item": item.strip(), "significance": "Carried forward from prior chapters."})
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("item") or "").strip()
            if not name:
                continue
            significance = str(item.get("significance") or item.get("description") or "Narratively meaningful possession.").strip()
            out.append({"item": name[:120], "significance": significance[:200]})
    return out[:5]


class LegacyAgent:
    """Generate a structured character legacy document from world state."""

    def generate(
        self,
        *,
        character_name: str,
        saga_chapter: int,
        world_state: dict[str, Any],
        outcome_summary: str,
        character_fate: str,
        crystallized_summaries: list[str] | None = None,
    ) -> dict[str, Any]:
        relationships = _extract_relationships(world_state)
        unresolved_threads = _extract_open_threads(world_state)
        key_possessions = _extract_key_possessions(world_state)
        faction_rep = world_state.get("faction_reputation") or {}
        rep_text = ", ".join(
            f"{name}: {score}"
            for name, score in list(faction_rep.items())[:5]
            if isinstance(name, str)
        )
        if not rep_text:
            rep_text = "No major faction standings were recorded."

        cryst = [s.strip() for s in (crystallized_summaries or []) if isinstance(s, str) and s.strip()]
        crystallized_summary = " ".join(cryst[:6])[:900]
        if not crystallized_summary:
            crystallized_summary = (outcome_summary or "The campaign concluded with unresolved echoes.").strip()[:900]

        emotional_state = str(
            world_state.get("character_emotional_state")
            or world_state.get("current_emotional_state")
            or "Seasoned by recent events, carrying both resolve and scars."
        )
        philosophy_shift = str(
            world_state.get("philosophy_shift")
            or "The character adapted under pressure, balancing principle against survival."
        )

        return {
            "character_name": character_name or "Unknown Hero",
            "saga_chapter": max(1, int(saga_chapter or 1)),
            "key_relationships": relationships,
            "unresolved_threads": unresolved_threads,
            "emotional_state": emotional_state[:280],
            "reputation": rep_text[:320],
            "philosophy_shift": philosophy_shift[:320],
            "key_possessions": key_possessions,
            "character_fate": (character_fate or "").strip()[:320],
            "outcome_summary": (outcome_summary or "").strip()[:500],
            "crystallized_memories_summary": crystallized_summary,
        }
