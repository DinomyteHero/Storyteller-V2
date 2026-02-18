"""ArcConsequenceTracker: captures arc-end state for sequel generation (Phase 2.2).

Called at RESOLUTION arc stage and by POST /prologue/complete.
Writes a structured snapshot to world_state_json["arc_consequences"] that:
- Seeds the next arc's screenplay with context
- Lets the Director reference prior decisions in the opening crawl
- Tracks the fate of NPCs and factions

Pure utility — no LLM calls, no DB writes. The caller is responsible for
persisting the result.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def capture(
    world_state: dict[str, Any],
    player: dict[str, Any] | None = None,
    ledger_facts: list[str] | None = None,
    quest_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an arc_consequences dict from current campaign state.

    Args:
        world_state: The current world_state_json dict.
        player: The player character dict (optional — for background/species context).
        ledger_facts: Recent established_facts from the ledger (optional).
        quest_log: The current quest_log dict (optional).
    Returns:
        arc_consequences dict. Written to world_state["arc_consequences"] by caller.
    """
    ws = world_state if isinstance(world_state, dict) else {}
    p = player if isinstance(player, dict) else {}
    facts = list(ledger_facts or [])
    q_log = quest_log if isinstance(quest_log, dict) else {}

    # Collect resolved quests
    resolved_quests: list[str] = []
    for qid, qdata in q_log.items():
        if isinstance(qdata, dict) and qdata.get("status") in ("completed", "failed"):
            resolved_quests.append(qid)

    # Open threads from ledger
    ledger = ws.get("ledger") or {}
    if not isinstance(ledger, dict):
        ledger = {}
    open_threads = list((ledger.get("open_threads") or [])[:10])
    consequence_hints = list((ledger.get("consequence_hints") or [])[:5])

    # NPC states snapshot
    npc_cast = ws.get("npc_cast") or []
    npc_fates: list[dict[str, Any]] = []
    for npc in (npc_cast if isinstance(npc_cast, list) else []):
        if not isinstance(npc, dict):
            continue
        npc_id = npc.get("id") or npc.get("name", "unknown")
        npc_fates.append({
            "id": npc_id,
            "name": npc.get("name", npc_id),
            "relationship_score": npc.get("relationship_score", 0),
            "status": npc.get("status", "unknown"),
        })

    # Faction standings
    faction_reputation: dict[str, int] = {}
    raw_rep = ws.get("faction_reputation") or {}
    if isinstance(raw_rep, dict):
        faction_reputation = {k: int(v) for k, v in raw_rep.items() if isinstance(v, (int, float))}

    # Arc state
    arc_state = ws.get("arc_state") or {}
    arc_stage_reached = (
        arc_state.get("current_stage", "SETUP")
        if isinstance(arc_state, dict)
        else "SETUP"
    )

    # Player summary
    player_summary: dict[str, Any] = {
        "background_id": p.get("background_id") or p.get("background"),
        "species_id": ws.get("species_id") or p.get("species_id"),
        "name": p.get("name") or ws.get("player_name"),
        "alignment": ws.get("alignment"),
        "stats": p.get("stats") or {},
        "hp_current": p.get("hp_current"),
    }

    # Most important decisions: look for major alignment/psych events in facts
    major_decisions = [
        f for f in facts
        if any(kw in f.lower() for kw in ("chose", "decided", "betrayed", "saved", "killed", "allied"))
    ][:5]

    consequences: dict[str, Any] = {
        "arc_number": ws.get("arc_number", 1),
        "arc_stage_reached": arc_stage_reached,
        "resolved_quests": resolved_quests,
        "open_threads": open_threads,
        "consequence_hints": consequence_hints,
        "npc_fates": npc_fates[:12],
        "faction_standing_snapshot": faction_reputation,
        "major_decisions": major_decisions,
        "player_summary": player_summary,
        "dangling_hooks": open_threads[:5],  # Top 5 open threads become next arc seeds
    }

    # Merge with existing consequences if any (preserve arc history)
    existing = ws.get("arc_consequences")
    if isinstance(existing, dict):
        history = existing.get("arc_history") or []
        if isinstance(history, list):
            history = history[-4:]  # Keep last 4 arcs
        consequences["arc_history"] = history + [
            {
                "arc_number": existing.get("arc_number"),
                "arc_stage_reached": existing.get("arc_stage_reached"),
                "resolved_quests": existing.get("resolved_quests", []),
                "dangling_hooks": existing.get("dangling_hooks", []),
            }
        ]

    logger.info(
        "ArcConsequenceTracker: arc=%d stage=%s resolved_quests=%d open_threads=%d",
        consequences["arc_number"],
        arc_stage_reached,
        len(resolved_quests),
        len(open_threads),
    )
    return consequences
