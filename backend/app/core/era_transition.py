"""Era transition manager: handles progression between Star Wars eras.

Triggers when an arc reaches RESOLUTION and narrative milestones are met.
Carries over: player sheet, companions, KG entities, episodic memories.
Resets: NPC cast, factions, locations (loaded from new era pack).
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Canonical era progression order
ERA_PROGRESSION: list[str] = [
    "REBELLION",
    "NEW_REPUBLIC",
    "NEW_JEDI_ORDER",
    "LEGACY",
]

# Era display names for transition narration
ERA_DISPLAY_NAMES: dict[str, str] = {
    "REBELLION": "the Galactic Civil War",
    "NEW_REPUBLIC": "the New Republic Era",
    "NEW_JEDI_ORDER": "the Yuuzhan Vong War",
    "LEGACY": "the Legacy Era",
}

# Approximate timeline gaps between eras (in-universe years)
ERA_TIME_GAPS: dict[str, str] = {
    "REBELLION->NEW_REPUBLIC": "Five years have passed since the Battle of Endor.",
    "NEW_REPUBLIC->NEW_JEDI_ORDER": "Two decades of fragile peace are shattered.",
    "NEW_JEDI_ORDER->LEGACY": "A century of change has reshaped the galaxy.",
}


def get_next_era(current_era: str) -> str | None:
    """Return the next era in the progression, or None if at the end."""
    current_upper = current_era.upper().strip()
    try:
        idx = ERA_PROGRESSION.index(current_upper)
    except ValueError:
        return None
    if idx < len(ERA_PROGRESSION) - 1:
        return ERA_PROGRESSION[idx + 1]
    return None


def can_transition(
    current_era: str,
    arc_stage: str | None,
    arc_guidance: dict | None = None,
) -> bool:
    """Check if an era transition is available.

    Conditions:
    - Current arc is in RESOLUTION stage
    - There is a next era to transition to
    - Arc guidance indicates the resolution is sufficiently complete
    """
    if not arc_stage or arc_stage.upper() != "RESOLUTION":
        return False
    if get_next_era(current_era) is None:
        return False
    # Check if resolution has progressed enough (at least 2 turns in RESOLUTION)
    if arc_guidance:
        turns_in_stage = arc_guidance.get("turns_in_stage", 0)
        if turns_in_stage < 2:
            return False
    return True


def build_transition_summary(
    current_era: str,
    next_era: str,
    player_name: str = "the protagonist",
) -> str:
    """Build a cinematic era transition narrative summary."""
    current_display = ERA_DISPLAY_NAMES.get(current_era.upper(), current_era)
    next_display = ERA_DISPLAY_NAMES.get(next_era.upper(), next_era)
    gap_key = f"{current_era.upper()}->{next_era.upper()}"
    time_gap = ERA_TIME_GAPS.get(gap_key, "Time passes. The galaxy transforms.")

    return (
        f"The chapter of {current_display} draws to a close.\n\n"
        f"{time_gap}\n\n"
        f"A new chapter begins: {next_display}.\n\n"
        f"{player_name}'s story continues, shaped by everything that came before."
    )


def execute_transition(
    world_state: dict[str, Any],
    current_era: str,
    next_era: str,
) -> dict[str, Any]:
    """Execute an era transition on world_state.

    Carries over:
    - Player sheet (preserved externally in characters table)
    - Companions (party, party_affinity, party_traits)
    - Ledger (established_facts, constraints — threads are closed)
    - Era summaries (compressed memory of previous eras)
    - Episodic memories (preserved in DB table, campaign-scoped)

    Resets:
    - Active factions (loaded fresh from new era pack)
    - NPC cast (new era = new cast, old NPCs remain in KG)
    - Arc state (resets to SETUP for new era)
    - News feed (cleared for new era)
    """
    new_ws = dict(world_state)

    # Reset arc state to SETUP for new era
    new_ws["arc_state"] = {
        "current_stage": "SETUP",
        "stage_start_turn": 0,  # Will be updated by next arc planner run
    }

    # Close all open threads (they belong to the old era)
    ledger = dict(new_ws.get("ledger") or {})
    closed_threads = ledger.get("open_threads") or []
    if closed_threads:
        facts = list(ledger.get("established_facts") or [])
        for thread in closed_threads:
            facts.append(f"[{current_era}] Resolved: {thread}")
        ledger["established_facts"] = facts
    ledger["open_threads"] = []
    # Reset active themes for new era
    ledger["active_themes"] = []
    new_ws["ledger"] = ledger

    # Clear news feed
    new_ws["news_feed"] = []

    # Active factions will be loaded from the new era pack by the encounter system
    # Mark them for refresh
    new_ws["active_factions"] = []
    new_ws["_era_factions_stale"] = True

    # Compress current era into a summary
    era_summaries = list(new_ws.get("era_summaries") or [])
    current_display = ERA_DISPLAY_NAMES.get(current_era.upper(), current_era)
    facts = (new_ws.get("ledger") or {}).get("established_facts") or []
    recent_facts = [f for f in facts if not f.startswith(f"[{current_era}]")][:5]
    summary_text = f"During {current_display}: " + "; ".join(recent_facts) if recent_facts else f"Lived through {current_display}."
    era_summaries.append(summary_text)
    new_ws["era_summaries"] = era_summaries

    logger.info("Era transition executed: %s -> %s", current_era, next_era)
    return new_ws
