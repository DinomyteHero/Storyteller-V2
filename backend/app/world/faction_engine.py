"""Deterministic faction simulation engine.

Replaces LLM-based ``CampaignArchitect.simulate_off_screen()`` with a
template-driven, seeded-RNG engine.  Zero LLM calls, <100 ms per tick.

All randomness is seeded by ``turn_number`` so the same inputs always
produce the same outputs (deterministic for testing / replay).
"""
from __future__ import annotations

import logging
import random
from typing import Any

from shared.schemas import WorldSimOutput
from backend.app.world.era_pack_loader import get_era_pack

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rumor / event templates keyed by primary faction tag
# ---------------------------------------------------------------------------

RUMOR_TEMPLATES: dict[str, list[str]] = {
    "rebel": [
        "Whispers at {location} suggest a Rebel cell is recruiting sympathizers.",
        "Spacers report {faction_name} operatives sighted near {location}.",
        "A coded transmission from {faction_name} was intercepted — contents unknown.",
        "Locals at {location} murmur about hidden supply caches for {faction_name}.",
        "A smuggler claims {faction_name} is planning something big in the Outer Rim.",
        "Word is {faction_name} lost a safe house — agents scrambling for new cover.",
        "Dock workers at {location} found Rebel insignia scratched into cargo crates.",
        "A bounty has been posted for information on {faction_name} leadership.",
        "Propaganda holodiscs bearing the {faction_name} sigil surfaced at {location}.",
        "Rumor has it a defector from the Empire reached {faction_name} last rotation.",
        "{faction_name} sympathizers are spreading leaflets in the lower levels of {location}.",
        "An encrypted burst from {faction_name} briefly jammed local comms at {location}.",
        "A freighter captain refuses to discuss cargo — spacers suspect {faction_name} ties.",
        "Security patrols near {location} doubled after suspected {faction_name} activity.",
        "The cantina buzz says {faction_name} pulled off a supply raid near the hyperspace lane.",
    ],
    "imperial": [
        "Imperial patrols near {location} have increased — something has them on edge.",
        "{faction_name} officers are conducting inspections at every docking bay.",
        "A Star Destroyer was spotted in the sector — {faction_name} flexing its muscle.",
        "Stormtroopers at {location} detained several civilians for questioning.",
        "An {faction_name} checkpoint now blocks the main approach to {location}.",
        "{faction_name} intelligence is offering credits for information on dissidents.",
        "A curfew has been imposed near {location} by {faction_name} garrison command.",
        "Imperial probe droids were seen scanning the outskirts of {location}.",
        "{faction_name} requisitioned supplies from local merchants — no compensation.",
        "An officer from {faction_name} was overheard discussing a crackdown.",
        "Surveillance drones bearing {faction_name} markings now circle {location}.",
        "A transport carrying {faction_name} reinforcements docked at {location}.",
        "{faction_name} posted new wanted holos — several faces locals recognize.",
        "The {faction_name} garrison commander at {location} has been replaced without explanation.",
        "Shipyard workers say {faction_name} is building something in the orbital drydock.",
    ],
    "criminal": [
        "The underworld at {location} is buzzing — {faction_name} is making moves.",
        "A bounty hunter was seen meeting with {faction_name} contacts at {location}.",
        "{faction_name} is said to be cornering the spice market in this sector.",
        "Smugglers at {location} report that {faction_name} is offering protection — for a price.",
        "A cargo ship vanished near {location} — {faction_name} piracy suspected.",
        "{faction_name} enforcers were spotted collecting debts in the lower streets.",
        "The black market at {location} has new merchandise — {faction_name} connections suspected.",
        "A gambling den at {location} is rumored to be a {faction_name} front.",
        "{faction_name} is recruiting muscle — credits are good, questions are not.",
        "Dock security found contraband marked with {faction_name} symbols at {location}.",
        "A fixer at {location} claims {faction_name} is hiring for a high-stakes job.",
        "{faction_name} hitmen eliminated a rival operator near {location}.",
        "Spice prices spiked at {location} — spacers blame {faction_name} supply disruptions.",
        "A {faction_name} courier was seen entering the VIP section at {location}.",
        "Local merchants at {location} are paying {faction_name} for 'insurance' again.",
    ],
    "civilian": [
        "Refugees at {location} speak of hardship in the outer systems.",
        "Local merchants at {location} are worried about supply shortages.",
        "A protest was quietly dispersed at {location} — tensions remain.",
        "Food prices at {location} are climbing — freighter traffic is down.",
        "A community leader at {location} is calling for neutrality in the conflict.",
        "Medics at {location} report treating injuries from an undisclosed incident.",
        "Power outages at {location} have residents on edge — sabotage or neglect?",
        "Children at {location} were seen playing soldiers — the war touches everything.",
        "A relief convoy bound for {location} has gone missing en route.",
        "Workers at {location} organized a slowdown after wages were cut again.",
    ],
    "default": [
        "Something is stirring at {location} — the spacers are talking.",
        "Travelers from {location} bring unsettling news.",
        "Activity near {location} has locals on edge.",
        "A ship arrived at {location} under unusual circumstances.",
        "The mood at {location} has shifted — something is coming.",
        "An unidentified vessel was tracked entering the system near {location}.",
        "Sensors picked up anomalous readings near {location}.",
        "Trade routes through {location} have been rerouted without explanation.",
    ],
}

FACTION_MOVE_TEMPLATES: list[str] = [
    "{faction_name} repositioned operatives to {location}.",
    "{faction_name} shifted resources toward {goal_summary}.",
    "{faction_name} consolidated presence at {location}.",
    "{faction_name} began operations related to {goal_summary}.",
    "{faction_name} recalled agents from the field to {location}.",
    "{faction_name} dispatched scouts to assess conditions near {location}.",
]

HIDDEN_EVENT_TEMPLATES: dict[str, list[str]] = {
    "CLIMAX": [
        "{faction_name} launched a decisive operation targeting {location}.",
        "A major confrontation between factions erupted near {location}.",
        "{faction_name} made a bold power play — the balance of power shifts.",
        "An assassination attempt rocked {location} — consequences ripple outward.",
    ],
    "RESOLUTION": [
        "The aftermath of recent events settles over {location}.",
        "{faction_name} is regrouping after losses — the dust is settling.",
        "A fragile ceasefire holds near {location} — for now.",
        "Survivors are picking up the pieces at {location}.",
    ],
    "default": [
        "{faction_name} agents conducted a covert operation near {location}.",
        "An informant changed sides — intelligence networks are compromised.",
        "A hidden cache was discovered near {location}.",
        "A secret meeting took place between rival operatives.",
    ],
}

ELAPSED_TIME_TEMPLATES: list[str] = [
    "Time passes. The galaxy turns.",
    "Hours slip by in the hum of hyperspace lanes.",
    "The world moves on while you act.",
    "Events continue to unfold across the sector.",
]


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------


def _primary_tag(faction: dict, era_factions: list | None = None) -> str:
    """Determine the primary tag category for a faction (rebel/imperial/criminal/civilian)."""
    tags = set()

    # Check era pack data for richer tags
    if era_factions:
        name_lower = (faction.get("name") or "").lower()
        for ef in era_factions:
            if ef.name.lower() == name_lower or ef.id.lower() == name_lower.replace(" ", "_"):
                tags.update(t.lower() for t in ef.tags)
                break

    # Fallback: infer from faction dict
    if not tags:
        raw_tags = faction.get("tags") or []
        tags.update(t.lower() for t in raw_tags)

    # Also infer from name
    name = (faction.get("name") or "").lower()
    if any(k in name for k in ("rebel", "alliance", "resistance")):
        tags.add("rebel")
    elif any(k in name for k in ("empire", "imperial", "isb", "security bureau")):
        tags.add("imperial")
    elif any(k in name for k in ("syndicate", "cartel", "hutt", "criminal", "smuggler")):
        tags.add("criminal")

    # Also infer from is_hostile
    if faction.get("is_hostile") and not tags & {"rebel", "imperial", "criminal"}:
        tags.add("imperial")  # hostile factions default to imperial-style rumors

    for category in ("rebel", "imperial", "criminal", "civilian"):
        if category in tags:
            return category
    return "default"


def _pick_location(faction: dict, player_location: str, rng: random.Random) -> str:
    """Pick a location for template slot filling."""
    candidates = []
    loc = faction.get("location")
    if loc:
        candidates.append(loc)
    home = faction.get("home_locations") or []
    candidates.extend(home)
    if player_location:
        candidates.append(player_location)
    if not candidates:
        candidates = ["the sector"]
    return rng.choice(candidates)


def _goal_summary(faction: dict, era_factions: list | None = None) -> str:
    """Get a short goal summary for a faction."""
    goal = faction.get("current_goal") or ""
    if goal:
        # Truncate long goals
        return goal[:80] if len(goal) > 80 else goal

    # Try era pack data
    if era_factions:
        name_lower = (faction.get("name") or "").lower()
        for ef in era_factions:
            if ef.name.lower() == name_lower and ef.goals:
                return ef.goals[0][:80]

    return "advancing their agenda"


def simulate_faction_tick(
    active_factions: list[dict[str, Any]],
    turn_number: int,
    player_location: str,
    arc_stage: str = "SETUP",
    era_id: str = "REBELLION",
    world_time_minutes: int = 0,
    travel_occurred: bool = False,
    world_reaction_needed: bool = False,
    user_action_summary: str = "",
    faction_memory: dict[str, dict] | None = None,
    npc_states: dict[str, dict] | None = None,
    known_npcs: list[dict] | None = None,
) -> WorldSimOutput:
    """Run one deterministic faction simulation tick.

    Args:
        active_factions: Current faction state dicts (name, location, current_goal, resources, is_hostile).
        turn_number: Current turn (used as RNG seed for determinism).
        player_location: Player's current location ID.
        arc_stage: Story arc stage (SETUP, RISING, CLIMAX, RESOLUTION).
        era_id: Canonical era ID for era pack lookup.
        world_time_minutes: Current world time.
        travel_occurred: Whether the player travelled this turn.
        world_reaction_needed: Whether a major world event occurred.
        user_action_summary: Brief description of what the player did.

    Returns:
        WorldSimOutput with rumors, faction_moves, hidden_events, updated_factions.
    """
    if not active_factions:
        return WorldSimOutput(
            elapsed_time_summary="Time passes quietly.",
            faction_moves=[],
            new_rumors=[],
            hidden_events=[],
            updated_factions=None,
        )

    rng = random.Random(turn_number * 7919 + world_time_minutes)  # deterministic seed

    # Load era pack for richer faction data
    era_pack = get_era_pack(era_id) if era_id else None
    era_factions = era_pack.factions if era_pack else None

    # --- Determine how many outputs based on arc stage and triggers ---
    if arc_stage == "CLIMAX":
        rumor_count = rng.randint(2, 3)
        move_count = rng.randint(1, 2)
        hidden_count = 1
    elif arc_stage == "RISING":
        rumor_count = rng.randint(1, 3)
        move_count = rng.randint(1, 2)
        hidden_count = 1 if rng.random() < 0.6 else 0
    elif arc_stage == "RESOLUTION":
        rumor_count = rng.randint(1, 2)
        move_count = 1
        hidden_count = 1
    else:  # SETUP
        rumor_count = rng.randint(1, 2)
        move_count = 1
        hidden_count = 1 if rng.random() < 0.4 else 0

    if travel_occurred:
        rumor_count = max(rumor_count, 2)
    if world_reaction_needed:
        rumor_count = max(rumor_count, 2)
        hidden_count = max(hidden_count, 1)

    # --- Generate rumors ---
    new_rumors: list[str] = []
    shuffled_factions = list(active_factions)
    rng.shuffle(shuffled_factions)

    for i in range(min(rumor_count, len(shuffled_factions))):
        faction = shuffled_factions[i % len(shuffled_factions)]
        tag = _primary_tag(faction, era_factions)
        templates = RUMOR_TEMPLATES.get(tag, RUMOR_TEMPLATES["default"])
        template = rng.choice(templates)
        location = _pick_location(faction, player_location, rng)
        rumor = template.format(
            faction_name=faction.get("name", "Unknown Faction"),
            location=location,
        )
        new_rumors.append(rumor)

    # If we need more rumors than factions, pick from default pool
    while len(new_rumors) < rumor_count:
        template = rng.choice(RUMOR_TEMPLATES["default"])
        location = player_location or "the sector"
        new_rumors.append(template.format(
            faction_name="unknown forces",
            location=location,
        ))

    # --- Generate faction moves (hidden) ---
    faction_moves: list[str] = []
    rng.shuffle(shuffled_factions)
    for i in range(min(move_count, len(shuffled_factions))):
        faction = shuffled_factions[i]
        template = rng.choice(FACTION_MOVE_TEMPLATES)
        location = _pick_location(faction, player_location, rng)
        goal = _goal_summary(faction, era_factions)
        move = template.format(
            faction_name=faction.get("name", "Unknown Faction"),
            location=location,
            goal_summary=goal,
        )
        faction_moves.append(move)

    # --- Generate hidden events ---
    hidden_events: list[str] = []
    if hidden_count > 0:
        event_pool = HIDDEN_EVENT_TEMPLATES.get(arc_stage, HIDDEN_EVENT_TEMPLATES["default"])
        for _ in range(hidden_count):
            faction = rng.choice(active_factions)
            template = rng.choice(event_pool)
            location = _pick_location(faction, player_location, rng)
            event = template.format(
                faction_name=faction.get("name", "Unknown Faction"),
                location=location,
            )
            hidden_events.append(event)

    # --- Update faction resources and locations ---
    updated_factions: list[dict[str, Any]] = []
    for faction in active_factions:
        updated = dict(faction)
        old_resources = int(updated.get("resources") or 5)

        # Resource drift: ±1, biased by hostility and arc stage
        drift = rng.choice([-1, 0, 0, 1])  # slight upward bias
        if updated.get("is_hostile") and arc_stage == "CLIMAX":
            drift = rng.choice([-1, -1, 0, 1])  # hostile factions lose resources at climax
        elif arc_stage == "SETUP":
            drift = rng.choice([0, 0, 1, 1])  # factions build resources during setup

        new_resources = max(1, min(10, old_resources + drift))
        updated["resources"] = new_resources

        # Location shift: 20% chance to shift to a home_location
        if era_factions and rng.random() < 0.2:
            name_lower = (faction.get("name") or "").lower()
            for ef in era_factions:
                if ef.name.lower() == name_lower and ef.home_locations:
                    updated["location"] = rng.choice(ef.home_locations)
                    break

        updated_factions.append(updated)

    # --- Faction memory: track recent actions and multi-turn plans ---
    faction_memory = dict(faction_memory or {})
    for faction in updated_factions:
        fname = faction.get("name", "Unknown")
        mem = dict(faction_memory.get(fname) or {})
        recent_actions = list(mem.get("recent_actions") or [])
        # Record this tick's faction move as a recent action
        for move_text in faction_moves:
            if fname in move_text:
                recent_actions.append(move_text[:120])
                break
        # Keep only last 5 actions
        mem["recent_actions"] = recent_actions[-5:]
        # Multi-turn plan: derive from current_goal + arc stage
        goal = faction.get("current_goal") or ""
        if not mem.get("multi_turn_plan") and goal:
            # Generate a simple multi-step plan from the goal
            mem["multi_turn_plan"] = goal
            mem["plan_progress"] = 0
        elif mem.get("multi_turn_plan"):
            # Advance plan progress each tick (simple deterministic advancement)
            progress = int(mem.get("plan_progress") or 0)
            mem["plan_progress"] = progress + 1
            # Plan complete after ~5 ticks — generate new plan from updated goal
            if progress >= 4:
                mem["multi_turn_plan"] = goal if goal != mem.get("multi_turn_plan") else ""
                mem["plan_progress"] = 0
        faction_memory[fname] = mem

    # --- 3.1: NPC autonomy — update known NPC locations and goals ---
    npc_states = dict(npc_states or {})
    for npc in (known_npcs or []):
        npc_id = npc.get("character_id") or npc.get("id")
        if not npc_id:
            continue
        npc_name = npc.get("name", "Unknown")
        state_entry = dict(npc_states.get(npc_id) or {})
        state_entry["name"] = npc_name
        state_entry["last_known_location"] = state_entry.get("current_location") or npc.get("location_id", "")

        # NPCs may move between ticks (20% chance, seeded)
        if rng.random() < 0.20:
            # Move to a faction-associated location or random home location
            npc_faction = (npc.get("stats_json") or {}).get("faction_id", "")
            moved = False
            if npc_faction and era_factions:
                for ef in era_factions:
                    if ef.id == npc_faction and ef.home_locations:
                        new_loc = rng.choice(ef.home_locations)
                        state_entry["current_location"] = new_loc
                        moved = True
                        break
            if not moved:
                state_entry["current_location"] = state_entry.get("current_location", npc.get("location_id", ""))
        else:
            state_entry["current_location"] = state_entry.get("current_location", npc.get("location_id", ""))

        # NPCs update their goals based on faction context
        npc_faction = (npc.get("stats_json") or {}).get("faction_id", "")
        for f in updated_factions:
            if f.get("name", "").lower().replace(" ", "_") == npc_faction:
                state_entry["current_goal"] = f.get("current_goal", "")[:100]
                break

        # Track disposition (from relationship_score if available)
        rel = npc.get("relationship_score")
        if rel is not None:
            state_entry["disposition_to_player"] = int(rel)

        state_entry["last_updated_turn"] = turn_number
        npc_states[npc_id] = state_entry

    # --- Elapsed time summary ---
    elapsed = rng.choice(ELAPSED_TIME_TEMPLATES)

    return WorldSimOutput(
        elapsed_time_summary=elapsed,
        faction_moves=faction_moves,
        new_rumors=new_rumors,
        hidden_events=hidden_events,
        updated_factions=updated_factions,
        faction_memory=faction_memory,
        npc_states=npc_states,
    )
