"""Hub/Downtime system for Storyteller-V2 (Phase 4.1).

Hub locations are special areas (cantinas, safehouses, guild halls, inns) where
the player can rest, upgrade companions, and pursue relationship beats without
active danger pressure.

The hub system activates when the current location has the "hub" service tag in
its EraLocation definition. The Director node calls ``is_hub_location()`` to
detect this and injects hub-mode context into the prompt.

Hub options:
- rest:         Recover stress/fatigue. Minor health/willpower restoration.
- talk_to_companion: Companion relationship scene (uses companion affinity).
- gather_intel:  Downtime information gathering (no combat, low-tension).
- resupply:     Access items/inventory management beat.
- wait:         Skip downtime, proceed with the story.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Minimum stress reduction from a rest action (arbitrary story units)
_REST_STRESS_REDUCTION = 10
_REST_HEALTH_RESTORATION = 5


def is_hub_location(world_state: dict[str, Any], era_pack: Any | None = None) -> bool:
    """Return True if the current location is a hub (downtime-eligible).

    Checks:
    1. ``world_state["hub_mode"]`` explicit override flag.
    2. The current location's services list contains ``"hub"`` in the era pack.

    Args:
        world_state: The current world_state_json dict.
        era_pack: Optional EraPack instance for the current era.

    Returns:
        True if hub mode should be active.
    """
    if world_state.get("hub_mode"):
        return True

    current_location_id = world_state.get("current_location") or ""
    if not current_location_id or era_pack is None:
        return False

    try:
        loc = era_pack.location_by_id(current_location_id)
        if loc is None:
            return False
        services = getattr(loc, "services", []) or []
        return "hub" in services
    except Exception as e:
        logger.debug("is_hub_location check failed (non-fatal): %s", e)
        return False


def get_hub_options(
    world_state: dict[str, Any],
    party_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return available hub actions for the current downtime scene.

    Args:
        world_state: The current world_state_json dict.
        party_ids: IDs of companions in the party.

    Returns:
        List of action dicts with: id, label, description, available.
    """
    companions = party_ids or []
    has_party = bool(companions)

    options: list[dict[str, Any]] = [
        {
            "id": "rest",
            "label": "Rest",
            "description": "Take time to recover. Reduces stress and restores focus.",
            "available": True,
            "category": "downtime",
        },
        {
            "id": "gather_intel",
            "label": "Gather Intel",
            "description": "Spend time listening to rumors and gathering information about the region.",
            "available": True,
            "category": "downtime",
        },
        {
            "id": "resupply",
            "label": "Resupply",
            "description": "Check inventory and acquire any available supplies.",
            "available": True,
            "category": "downtime",
        },
        {
            "id": "wait",
            "label": "Move On",
            "description": "Skip the downtime and continue the story.",
            "available": True,
            "category": "downtime",
        },
    ]

    if has_party:
        for companion_id in companions[:3]:  # Limit to 3 companion options
            options.append({
                "id": f"talk_{companion_id}",
                "label": f"Talk to {companion_id.replace('_', ' ').title()}",
                "description": "Spend time with your companion. May deepen your relationship or reveal backstory.",
                "available": True,
                "category": "companion",
                "companion_id": companion_id,
            })

    return options


def apply_rest(
    world_state: dict[str, Any],
    player: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a rest action to the world state.

    Reduces stress, restores minor health/willpower. Non-destructive — returns
    a copy of world_state with modifications applied.

    Args:
        world_state: The current world_state_json dict.
        player: The player character dict (optional — for stat restoration).

    Returns:
        Updated world_state dict with rest effects applied.
    """
    new_ws = dict(world_state)

    # Reduce stress counter
    current_stress = int(new_ws.get("stress_level", 0))
    new_stress = max(0, current_stress - _REST_STRESS_REDUCTION)
    new_ws["stress_level"] = new_stress

    # Restore minor health (tracked in player_condition)
    player_condition = dict(new_ws.get("player_condition") or {})
    if player_condition:
        current_fatigue = int(player_condition.get("fatigue", 0))
        player_condition["fatigue"] = max(0, current_fatigue - _REST_HEALTH_RESTORATION)
        new_ws["player_condition"] = player_condition

    # Mark last rest turn for cooldown logic
    new_ws["last_rest_turn"] = int(new_ws.get("turn_number", 0))

    logger.debug(
        "Rest applied: stress %d -> %d", current_stress, new_stress
    )
    return new_ws


def build_hub_system_prompt_injection(
    world_state: dict[str, Any],
    hub_options: list[dict[str, Any]] | None = None,
) -> str:
    """Build a hub-mode system prompt injection for the Director.

    Called by director_node when ``is_hub_location()`` returns True.
    Returns a string to be injected into the Director's system prompt context.

    Args:
        world_state: The current world_state_json dict.
        hub_options: Available hub actions (from get_hub_options()).

    Returns:
        Formatted hub context string for the Director's system prompt.
    """
    location_id = world_state.get("current_location") or "this location"
    stress = world_state.get("stress_level", 0)

    lines = [
        "## Hub/Downtime Mode",
        f"The party is currently at a safe hub location ({location_id}).",
        "This is a downtime scene — no immediate combat threat. The tone should be",
        "reflective, conversational, and character-driven.",
        "",
        f"Player stress level: {stress} (lower is better).",
        "",
        "In hub mode:",
        "- Prioritize character interactions and relationship development",
        "- Allow time for companion conversations if party members are present",
        "- Avoid introducing new urgent threats — this is a breathing room scene",
        "- Suggested actions should focus on downtime activities",
    ]

    if hub_options:
        downtime_opts = [o for o in hub_options if o.get("category") == "downtime"]
        companion_opts = [o for o in hub_options if o.get("category") == "companion"]
        if downtime_opts:
            lines.append("")
            lines.append("Available downtime actions: " + ", ".join(o["label"] for o in downtime_opts))
        if companion_opts:
            lines.append("Companion conversations available: " + ", ".join(o["label"] for o in companion_opts))

    return "\n".join(lines)
