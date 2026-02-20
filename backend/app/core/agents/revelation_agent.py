"""RevelationAgent: LLM-driven information economy (V10.0 Feature 1).

Runs every ~5 turns. Scans hidden world information (NPC agendas, faction
moves, world_sim events, consequence hints) and evaluates each piece for
dramatic revelation timing. Stores a prioritized revelation queue in
world_state["revelation_queue"] that the Director consults each turn.

The key insight: a human DM controls WHEN to reveal information for maximum
dramatic impact. This agent provides that same intelligence.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM, ensure_json
from backend.app.constants import REVELATION_QUEUE_MAX, REVELATION_EXPIRY_TURNS

logger = logging.getLogger(__name__)


def _build_system_prompt() -> str:
    return """\
You are the Information Broker for a narrative RPG. Your role is to evaluate
hidden world information and decide WHEN it should be revealed for maximum
dramatic impact.

You receive a list of hidden information (NPC secrets, faction plans, approaching
threats, undelivered consequences). For each piece, you must evaluate:

1. DRAMATIC_VALUE (1-10): How much would this revelation change the story?
   1-3 = minor color, 4-6 = meaningful, 7-9 = game-changing, 10 = devastating.

2. OPTIMAL_CONDITIONS: 1-3 conditions describing when this should be revealed.
   Examples: "when player expresses trust in this NPC", "during a moment of
   vulnerability", "at the climax of the current arc", "just before a critical
   choice involving this faction".

Return a JSON array of revelation objects. Only include items with dramatic_value >= 4.
Skip mundane or redundant information.

[JSON OUTPUT SCHEMA]
[
  {
    "content": "what the information is (1 sentence)",
    "source": "npc_agenda|faction_move|hidden_event|consequence",
    "source_npc": "npc-id or null",
    "dramatic_value": int,
    "optimal_conditions": ["condition1", "condition2"]
  }
]

Return ONLY a valid JSON array. No markdown. No preamble."""


def _build_user_prompt(
    npc_agendas: list[dict],
    faction_moves: list[str],
    hidden_events: list[str],
    consequence_hints: list[str],
    arc_stage: str,
    turn_number: int,
) -> str:
    sections = [f"[TURN {turn_number} | ARC STAGE: {arc_stage}]"]

    if npc_agendas:
        sections.append("\n[NPC HIDDEN AGENDAS]")
        for npc in npc_agendas:
            sections.append(f"  - {npc.get('name', '?')}: agenda={npc.get('agenda', '?')}, next_move={npc.get('next_move', '?')}")

    if faction_moves:
        sections.append("\n[FACTION MOVES (hidden from player)]")
        for fm in faction_moves[:5]:
            sections.append(f"  - {fm}")

    if hidden_events:
        sections.append("\n[HIDDEN WORLD EVENTS]")
        for he in hidden_events[:5]:
            sections.append(f"  - {he}")

    if consequence_hints:
        sections.append("\n[APPROACHING CONSEQUENCES]")
        for ch in consequence_hints[:5]:
            sections.append(f"  - {ch}")

    sections.append("\nEvaluate each piece of hidden information for dramatic revelation timing.")
    sections.append("Return only items with dramatic_value >= 4.")
    return "\n".join(sections)


def _normalize_output(raw: list, turn_number: int, existing_ids: set[str]) -> list[dict]:
    """Validate and normalize revelation queue entries."""
    results = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        dv = item.get("dramatic_value", 5)
        try:
            dv = max(1, min(10, int(dv)))
        except (ValueError, TypeError):
            dv = 5
        rev_id = f"rev-{turn_number}-{idx}"
        if rev_id in existing_ids:
            continue
        results.append({
            "id": rev_id,
            "content": content[:200],
            "source": str(item.get("source") or "unknown")[:20],
            "source_npc": str(item.get("source_npc") or "")[:50] or None,
            "dramatic_value": dv,
            "optimal_conditions": [str(c)[:100] for c in (item.get("optimal_conditions") or [])[:3]],
            "turn_queued": turn_number,
            "revealed": False,
        })
    return results


class RevelationAgent:
    """LLM-driven information economy agent.

    Evaluates hidden world information and queues revelations ranked by
    dramatic timing. The Director consults this queue each turn and reveals
    information when conditions are dramatically optimal.
    """

    def __init__(self) -> None:
        self._llm = AgentLLM("revelation_agent")

    def evaluate(
        self,
        world_state: dict[str, Any],
        arc_stage: str,
        turn_number: int,
        recent_narrative: str,
        events: list[dict[str, Any]],
    ) -> None:
        """Evaluate hidden info and update revelation_queue in world_state."""
        # Gather hidden information sources
        npc_states = world_state.get("npc_states") or {}
        npc_agendas = []
        for npc_id, npc_data in npc_states.items():
            if not isinstance(npc_data, dict):
                continue
            agenda = (npc_data.get("agenda") or "").strip()
            next_move = (npc_data.get("next_move") or "").strip()
            if agenda or next_move:
                npc_agendas.append({
                    "name": npc_id,
                    "agenda": agenda,
                    "next_move": next_move,
                })

        faction_memory = world_state.get("faction_memory") or {}
        faction_moves = []
        for fid, fdata in faction_memory.items():
            if isinstance(fdata, dict):
                last_move = fdata.get("last_move") or fdata.get("current_goal") or ""
                if last_move:
                    faction_moves.append(f"{fid}: {last_move}")

        # Hidden events from recent world_sim
        hidden_events = []
        for ev in events:
            if isinstance(ev, dict) and ev.get("event_type") in ("NPC_ACTION", "PLOT_TICK", "FACTION_MOVE"):
                text = (ev.get("payload") or {}).get("text", "")
                if text:
                    hidden_events.append(text)

        ledger = world_state.get("ledger") or {}
        consequence_hints = list((ledger.get("consequence_hints") or [])[:5])

        if not (npc_agendas or faction_moves or hidden_events or consequence_hints):
            logger.debug("RevelationAgent: no hidden information to evaluate")
            return

        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(
            npc_agendas=npc_agendas,
            faction_moves=faction_moves,
            hidden_events=hidden_events,
            consequence_hints=consequence_hints,
            arc_stage=arc_stage,
            turn_number=turn_number,
        )

        raw_text = self._llm.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
        )

        try:
            raw_json = json.loads(ensure_json(raw_text))
            if isinstance(raw_json, dict):
                raw_json = raw_json.get("revelations") or [raw_json]
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error("RevelationAgent: JSON parse failed: %s", exc)
            return

        if not isinstance(raw_json, list):
            raw_json = [raw_json] if isinstance(raw_json, dict) else []

        # Merge with existing queue
        existing_queue = world_state.get("revelation_queue") or []
        existing_ids = {r.get("id") for r in existing_queue if isinstance(r, dict)}

        new_entries = _normalize_output(raw_json, turn_number, existing_ids)

        # Expire old entries
        merged = [
            r for r in existing_queue
            if isinstance(r, dict) and not r.get("revealed", False)
            and (turn_number - r.get("turn_queued", 0)) < REVELATION_EXPIRY_TURNS
        ] + new_entries

        # Cap queue size, keeping highest dramatic value
        merged.sort(key=lambda r: r.get("dramatic_value", 0), reverse=True)
        world_state["revelation_queue"] = merged[:REVELATION_QUEUE_MAX]

        logger.info(
            "RevelationAgent: evaluated at turn %d — %d new entries, %d total queued",
            turn_number,
            len(new_entries),
            len(world_state["revelation_queue"]),
        )
