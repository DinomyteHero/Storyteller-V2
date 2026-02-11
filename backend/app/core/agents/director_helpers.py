"""Helper functions for Director agent companion reactions and risk assessment.

V2.9: Extracted to separate module for clarity and testability.
"""
from __future__ import annotations


def _compute_companion_reactions_for_suggestion(
    tone_tag: str,
    party: list[str],
    party_traits: dict[str, dict[str, int]],
) -> dict[str, int]:
    """Compute affinity deltas for a single suggestion based on tone.

    Args:
        tone_tag: PARAGON, RENEGADE, INVESTIGATE, or NEUTRAL
        party: List of companion IDs in active party
        party_traits: {companion_id: {trait_key: int}}

    Returns:
        {companion_id: affinity_delta} where delta is -5..5
        (zero deltas filtered out for UI)
    """
    from backend.app.core.companion_reactions import compute_companion_reactions

    if not party:
        return {}

    # Build mock MechanicOutput with just the tone
    mock_mechanic = {
        "tone_tag": tone_tag,
        "companion_affinity_delta": {},  # No explicit overrides
        "companion_reaction_reason": {},
    }

    # Compute reactions
    affinity_deltas, _ = compute_companion_reactions(party, party_traits, mock_mechanic)

    # Filter zero deltas (UI only shows non-neutral reactions)
    return {comp_id: delta for comp_id, delta in affinity_deltas.items() if delta != 0}


def _build_tactical_context(state) -> dict:
    """Extract tactical context for risk assessment.

    Args:
        state: GameState

    Returns:
        {
            "enemy_count": int,
            "player_advantage": float,
            "location_hazards": list[str],
            "time_of_day": str  # "Night" | "Day"
        }
    """
    npcs = getattr(state, "present_npcs", None) or []
    hostile_count = sum(1 for npc in npcs if _is_hostile_npc(npc))

    # Player advantage (stats + equipment vs enemy count)
    player = getattr(state, "player", None)
    player_stats_avg = _get_player_stats_average(player) if player else 5.0
    player_advantage = player_stats_avg / max(1, hostile_count) if hostile_count > 0 else 1.0

    # Location hazards
    location = getattr(state, "current_location", "") or ""
    location_hazards = _infer_location_hazards(location)

    # Time of day
    world_time = (state.campaign or {}).get("world_time_minutes") or 0
    time_of_day = _time_of_day_label(world_time)

    return {
        "enemy_count": hostile_count,
        "player_advantage": player_advantage,
        "location_hazards": location_hazards,
        "time_of_day": time_of_day,
    }


def _is_hostile_npc(npc: dict) -> bool:
    """Check if NPC is hostile (enemy).

    Args:
        npc: NPC dict with "archetype" and "role" keys

    Returns:
        True if NPC is likely hostile
    """
    archetype = (npc.get("archetype") or "").lower()
    role = (npc.get("role") or "").lower()
    return any(
        keyword in archetype or keyword in role
        for keyword in ["warrior", "guard", "bounty_hunter", "hostile", "enemy", "trooper", "soldier"]
    )


def _get_player_stats_average(player) -> float:
    """Compute average player stat (strength, intellect, cunning, charisma).

    Args:
        player: CharacterSheet or dict with "stats" key

    Returns:
        Average of non-zero stats, default 5.0
    """
    if isinstance(player, dict):
        stats = player.get("stats") or {}
    else:
        stats = getattr(player, "stats", None) or {}
    relevant = [stats.get(k, 0) for k in ["strength", "intellect", "cunning", "charisma"]]
    non_zero = [s for s in relevant if s > 0]
    return sum(non_zero) / max(1, len(non_zero)) if non_zero else 5.0


def _infer_location_hazards(location: str) -> list[str]:
    """Infer location hazards from location name.

    Args:
        location: Location ID or name

    Returns:
        List of hazard strings (max 2)
    """
    loc_lower = location.lower()
    hazards = []

    if any(kw in loc_lower for kw in ["imperial", "garrison", "prison", "vault", "restricted", "military"]):
        hazards.append("tight security")
    if any(kw in loc_lower for kw in ["guard", "patrol", "checkpoint", "stronghold"]):
        hazards.append("heavy guard presence")
    if any(kw in loc_lower for kw in ["dark", "cave", "sewer", "tunnel", "shadow", "underworld"]):
        hazards.append("low visibility")

    return hazards[:2]  # Max 2 location hazards


def _time_of_day_label(world_time_minutes: int) -> str:
    """Return 'Night' or 'Day' based on world_time_minutes.

    Args:
        world_time_minutes: Campaign world time in minutes

    Returns:
        "Night" (0-6h, 18-24h) or "Day" (6-18h)
    """
    hour_of_day = (world_time_minutes % 1440) / 60
    return "Night" if hour_of_day < 6 or hour_of_day >= 18 else "Day"


def _infer_risk_factors(
    suggestion,
    tactical_context: dict,
    state,
) -> list[str]:
    """Deterministic fallback: infer risk factors if LLM didn't provide.

    Args:
        suggestion: ActionSuggestion instance
        tactical_context: Output from _build_tactical_context()
        state: GameState

    Returns:
        List of risk factor strings (max 3)
    """
    from backend.app.models.state import ACTION_CATEGORY_COMMIT

    factors = []

    # Outnumbered?
    enemy_count = tactical_context["enemy_count"]
    party_size = len((state.campaign or {}).get("party") or []) + 1  # Player + companions
    if enemy_count > party_size:
        factors.append(f"Outnumbered {enemy_count}-to-{party_size}")

    # Location hazards
    for hazard in tactical_context["location_hazards"]:
        factors.append(hazard.replace("_", " ").title())

    # Nighttime + dangerous action
    if tactical_context["time_of_day"] == "Night" and suggestion.risk_level == "DANGEROUS":
        factors.append("Nighttime (low visibility)")

    # No weapon (check inventory)
    player = getattr(state, "player", None)
    if player is None:
        inv = None
    elif isinstance(player, dict):
        inv = player.get("inventory")
    else:
        inv = getattr(player, "inventory", None)
    inv = inv or []
    has_weapon = any(
        "blaster" in (item.get("item_name") or "").lower() or "weapon" in (item.get("item_name") or "").lower()
        for item in inv
        if isinstance(item, dict)
    )
    if suggestion.category == ACTION_CATEGORY_COMMIT and not has_weapon and enemy_count > 0:
        factors.append("No weapon equipped")

    return factors[:3]  # Max 3
