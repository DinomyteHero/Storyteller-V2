"""Mechanic agent: authoritative for physics (dice, DC, events). Narrator must not decide outcomes."""
from __future__ import annotations

import os
import re
import random
from typing import List

from backend.app.models.state import (
    GameState,
    MechanicOutput,
    TONE_TAG_PARAGON,
    TONE_TAG_RENEGADE,
    TONE_TAG_INVESTIGATE,
    TONE_TAG_NEUTRAL,
)
from backend.app.models.events import Event
from backend.app.time_economy import get_time_cost, TRAVEL_HYPERSPACE_MINUTES

# Action types (authoritative)
ACTION_TYPES = (
    "TRAVEL", "ATTACK", "SNEAK", "PERSUADE", "INVESTIGATE", "INTERACT", "IDLE", "TALK"
)


def _get_seed(state: GameState) -> int | None:
    """Optional deterministic seed: state.debug_seed or MECHANIC_SEED env."""
    seed = getattr(state, "debug_seed", None)
    if seed is not None:
        return int(seed)
    env = os.environ.get("MECHANIC_SEED")
    if env is not None and env.strip():
        try:
            return int(env.strip())
        except ValueError:
            pass
    return None


def _choice_impact_for_action(
    action_type: str,
    success: bool | None,
) -> tuple[str, dict[str, int], dict[str, int], dict[str, int], dict[str, str]]:
    """Return (tone_tag, alignment_delta, faction_reputation_delta, companion_affinity_delta, companion_reaction_reason).
    Deterministic defaults based on action_type and success/failure tier."""
    tone = TONE_TAG_NEUTRAL
    alignment_delta: dict[str, int] = {}
    faction_reputation_delta: dict[str, int] = {}
    companion_affinity_delta: dict[str, int] = {}
    companion_reaction_reason: dict[str, str] = {}

    if action_type == "TALK":
        tone = TONE_TAG_PARAGON
        alignment_delta = {"light_dark": 1, "paragon_renegade": 1}
        faction_reputation_delta = {"locals": 1}
    elif action_type == "PERSUADE":
        tone = TONE_TAG_PARAGON if success else TONE_TAG_NEUTRAL
        if success:
            alignment_delta = {"paragon_renegade": 1}
            faction_reputation_delta = {"locals": 1}
        else:
            alignment_delta = {"paragon_renegade": -1}
            faction_reputation_delta = {"locals": -1}
    elif action_type == "INVESTIGATE":
        tone = TONE_TAG_INVESTIGATE
        if success:
            alignment_delta = {"light_dark": 1}
    elif action_type in ("ATTACK", "SNEAK"):
        tone = TONE_TAG_RENEGADE
        if action_type == "ATTACK":
            if success:
                alignment_delta = {"light_dark": -2, "paragon_renegade": -2}
                faction_reputation_delta = {"law_enforcement": -2}
            else:
                alignment_delta = {"light_dark": -1, "paragon_renegade": -1}
                faction_reputation_delta = {"law_enforcement": -1}
        else:
            if success:
                alignment_delta = {"paragon_renegade": -1}
                faction_reputation_delta = {"law_enforcement": -1}
            else:
                alignment_delta = {"paragon_renegade": -1}
                faction_reputation_delta = {"law_enforcement": -2}
    elif action_type == "INTERACT":
        tone = TONE_TAG_NEUTRAL
    alignment_delta = {k: v for k, v in alignment_delta.items() if v}
    faction_reputation_delta = {k: v for k, v in faction_reputation_delta.items() if v}
    return tone, alignment_delta, faction_reputation_delta, companion_affinity_delta, companion_reaction_reason


def _compute_stress_delta(
    action_type: str,
    success: bool | None,
    roll: int | None,
    events: list,
) -> int:
    """Compute stress change for psych profile. Deterministic, no LLM."""
    delta = 0
    # Critical failure: roll == 1
    if roll == 1:
        delta += 2
    # Normal failure (non-critical)
    elif success is False:
        delta += 1
    # High damage event
    for e in events:
        if isinstance(e, Event):
            et = e.event_type
            payload = e.payload or {}
        elif isinstance(e, dict):
            et = e.get("event_type", "")
            payload = e.get("payload") or {}
        else:
            continue
        if et == "DAMAGE":
            amount = int(payload.get("amount", 0))
            if amount > 3:
                delta += 1
    # Success on risky action: relief
    if success is True and action_type in ("ATTACK", "SNEAK", "PERSUADE"):
        delta -= 1
    # TALK action: social relief
    if action_type == "TALK":
        delta -= 1
    return delta


def _compute_critical_outcome(roll: int | None) -> str | None:
    """Return critical outcome flag based on natural roll. None if no critical."""
    if roll == 1:
        return "CRITICAL_FAILURE"
    if roll == 20:
        return "CRITICAL_SUCCESS"
    return None


def _compute_world_reaction_needed(events: list) -> bool:
    """True when events demand immediate world-sim response."""
    for e in events:
        if isinstance(e, Event):
            et = e.event_type
            payload = e.payload or {}
        elif isinstance(e, dict):
            et = e.get("event_type", "")
            payload = e.get("payload") or {}
        else:
            continue
        # Severe combat event.
        if et == "DAMAGE" and int(payload.get("amount", 0)) >= 6:
            return True
        # Large relationship drop
        if et == "RELATIONSHIP" and int(payload.get("delta", 0)) < -3:
            return True
        # Faction flag set
        if et == "FLAG_SET":
            key = str(payload.get("key", "")).lower()
            value = payload.get("value", True)
            if "faction" in key:
                return True
            if key in {"public_violence", "combat_alert", "wanted_level"} and bool(value):
                return True
    return False


def _classify_action(user_input: str, intent: str | None) -> str:
    """Classify user_input into action_type. If intent==TALK return TALK; else heuristics."""
    if intent == "TALK":
        return "TALK"
    raw = (user_input or "").strip()
    if not raw:
        return "IDLE"
    low = raw.lower()
    if re.search(r"\b(go to|travel|head to|move to|return to|leave for)\b", low):
        return "TRAVEL"
    if re.search(r"\b(attack|shoot|slash|strike|fight|stab|hit)\b", low):
        return "ATTACK"
    if re.search(r"\b(sneak|quietly|stealth|hide|slip past|creep)\b", low):
        return "SNEAK"
    if re.search(r"\b(convince|persuade|negotiate|threaten|bribe|intimidate|charm|plead)\b", low):
        return "PERSUADE"
    if re.search(r"\b(inspect|search|look for|examine|scan|analyze|track|investigate)\b", low):
        return "INVESTIGATE"
    if re.search(r"\b(take|grab|use|open|hack|loot|pick up)\b", low):
        return "INTERACT"  # will emit ITEM_GET when we parse "take X"
    return "INTERACT"


def _get_modifier(state: GameState, action_type: str) -> int:
    """Skill modifier from player.stats for the action type."""
    stats = {}
    if state.player and state.player.stats:
        stats = state.player.stats
    # Normalize keys (support both CamelCase and lowercase)
    def get_stat(*keys: str) -> int:
        for k in keys:
            v = stats.get(k) or stats.get(k.lower())
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        return 0
    if action_type == "ATTACK":
        return get_stat("Combat", "combat")
    if action_type == "SNEAK":
        return get_stat("Stealth", "stealth")
    if action_type == "PERSUADE":
        return get_stat("Charisma", "charisma")
    if action_type == "INVESTIGATE":
        return get_stat("Tech", "Investigation", "tech", "investigation")
    return get_stat("General", "general")


# ---------------------------------------------------------------------------
# 3.3: Contextual advantage/disadvantage modifiers
# ---------------------------------------------------------------------------

# Location name substrings that imply environment tags
_LOC_TAG_MAP: dict[str, list[str]] = {
    "dark": ["underworld", "cave", "sewer", "tunnel", "alley", "undercity", "shadow"],
    "crowded": ["cantina", "marketplace", "market", "bazaar", "spaceport", "port", "plaza"],
    "wilderness": ["forest", "jungle", "swamp", "desert", "wasteland", "mountain"],
    "secure": ["imperial", "garrison", "prison", "vault", "restricted", "military"],
}


def _infer_location_tags(location: str) -> set[str]:
    """Infer environment tags from location name."""
    low = (location or "").lower()
    tags: set[str] = set()
    for tag, keywords in _LOC_TAG_MAP.items():
        if any(kw in low for kw in keywords):
            tags.add(tag)
    return tags


def environmental_modifiers(
    action_type: str,
    location: str,
    user_input: str,
    inventory: list[dict] | None = None,
    world_time_minutes: int = 0,
) -> list[dict[str, int | str]]:
    """Compute contextual roll modifiers from environment, gear, and time.

    Returns list of {source: str, value: int} dicts. Positive = bonus, negative = penalty.
    100% deterministic, no LLM.
    """
    mods: list[dict[str, int | str]] = []
    loc_tags = _infer_location_tags(location)

    # Darkness advantage for stealth
    if action_type == "SNEAK" and "dark" in loc_tags:
        mods.append({"source": "darkness", "value": 2})

    # Crowded locations: bonus to blending in, penalty to persuasion
    if "crowded" in loc_tags:
        if action_type == "SNEAK":
            mods.append({"source": "crowd cover", "value": 1})
        elif action_type == "PERSUADE":
            mods.append({"source": "public pressure", "value": -1})

    # Secure locations: harder to sneak, harder to attack
    if "secure" in loc_tags:
        if action_type == "SNEAK":
            mods.append({"source": "tight security", "value": -2})
        elif action_type == "ATTACK":
            mods.append({"source": "heavy guard presence", "value": -1})

    # Wilderness: bonus to investigation (tracking), penalty to persuasion (no audience)
    if "wilderness" in loc_tags:
        if action_type == "INVESTIGATE":
            mods.append({"source": "open terrain", "value": 1})

    # Inventory: armed bonus for combat
    if inventory and action_type == "ATTACK":
        weapon_keywords = {"blaster", "rifle", "saber", "lightsaber", "vibroblade", "weapon", "pistol", "sword"}
        for item in inventory:
            item_name = str(item.get("item_name") or item.get("name") or "").lower()
            if any(w in item_name for w in weapon_keywords):
                mods.append({"source": "armed", "value": 2})
                break

    # Time-of-day: nighttime bonus to stealth (every 24h cycle: night = 0-360 or 1080-1440 minutes)
    day_minutes = world_time_minutes % 1440
    is_night = day_minutes < 360 or day_minutes >= 1080
    if is_night and action_type == "SNEAK" and "dark" not in loc_tags:
        mods.append({"source": "nighttime", "value": 1})

    return mods


_ARC_DC_MODIFIER: dict[str, int] = {
    "SETUP": -2,
    "RISING": 0,
    "CLIMAX": 3,
    "RESOLUTION": -1,
}


def _compute_dc(state: GameState, action_type: str, user_input: str) -> int:
    """DC heuristic with dynamic difficulty scaling.

    Base DC 10, modified by:
      - Context keywords: +2 for risky context (fast, under fire, guards)
      - NPC hostility: +2 for negative relationship on PERSUADE
      - Arc stage: -2 SETUP, +0 RISING, +3 CLIMAX, -1 RESOLUTION
      - Player stats: -modifier (higher skill = easier)
    Cap: 6–20.
    """
    dc = 10
    low = (user_input or "").lower()
    if re.search(r"\b(fast|under fire|guards)\b", low):
        dc += 2
    if action_type == "PERSUADE" and state.present_npcs:
        for n in state.present_npcs:
            rel = n.get("relationship_score")
            if rel is not None and int(rel) < 0:
                dc += 2
                break

    # 2.3: Arc-stage difficulty scaling
    campaign = getattr(state, "campaign", None) or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ws = ws if isinstance(ws, dict) else {}
    arc_state = ws.get("arc_state") or {}
    arc_stage = arc_state.get("current_stage", "SETUP")
    dc += _ARC_DC_MODIFIER.get(arc_stage, 0)

    # 2.3: Player stat advantage (higher skill = lower DC)
    modifier = _get_modifier(state, action_type)
    dc -= modifier

    return max(6, min(20, dc))


# Known planet names for interplanetary travel detection
_KNOWN_PLANETS: set[str] = {
    "tatooine", "coruscant", "hoth", "yavin 4", "yavin", "endor",
    "naboo", "kashyyyk", "dagobah", "bespin", "mustafar", "kamino",
    "geonosis", "alderaan", "corellia", "mandalore", "lothal",
    "jedha", "scarif", "mon calamari", "sullust", "kessel",
    "nar shaddaa", "nal hutta", "dantooine", "bastion", "myrkr",
    "kesh", "etti iv", "gilatter viii", "dathomir", "ilum",
    "jakku", "crait", "exegol", "chandrila",
}


def _parse_travel_destination(user_input: str) -> tuple[str | None, str | None]:
    """Parse travel destination. Returns (destination, planet_name_or_none).

    If the destination matches a known planet name, it's flagged as interplanetary travel.
    """
    low = (user_input or "").strip().lower()
    for prefix in ("go to ", "travel to ", "head to ", "to "):
        if prefix in low:
            idx = low.index(prefix) + len(prefix)
            rest = (user_input or "").strip()[idx:].strip()
            if rest:
                # take first phrase (up to comma or period)
                rest = re.split(r"[,.]", rest)[0].strip()
                if rest:
                    # Check if destination is a known planet
                    rest_lower = rest.lower()
                    for planet in _KNOWN_PLANETS:
                        if rest_lower == planet or rest_lower.startswith(planet):
                            # Capitalize planet name properly
                            return rest, rest.title()
                    return rest, None
    return None, None


def _parse_item_name(user_input: str) -> str | None:
    """Naive: word after 'take ' or 'grab '."""
    low = (user_input or "").strip().lower()
    for prefix in ("take ", "grab "):
        if low.startswith(prefix):
            rest = (user_input or "").strip()[len(prefix):].strip()
            if rest:
                rest = re.split(r"[\s,.]", rest)[0].strip()
                if rest:
                    return rest
    return None


def _player_id(state: GameState) -> str:
    """Character id for the player."""
    if state.player and getattr(state.player, "character_id", None):
        return state.player.character_id
    return state.player_id


def _first_npc_id(state: GameState) -> str | None:
    """First present NPC id (for attack target)."""
    if not state.present_npcs:
        return None
    n = state.present_npcs[0]
    return n.get("id")


def _select_attack_target(state: GameState, user_input: str) -> str | None:
    """Select attack target by explicit mention first, then most-hostile NPC."""
    npcs = state.present_npcs or []
    if not npcs:
        return None

    low = (user_input or "").lower()
    for npc in npcs:
        npc_id = npc.get("id")
        if not npc_id:
            continue
        name = str(npc.get("name") or "").strip().lower()
        role = str(npc.get("role") or "").strip().lower()
        if name and name in low:
            return npc_id
        if role and role in low:
            return npc_id

    def _hostility_key(npc: dict) -> tuple[int, str]:
        rel = npc.get("relationship_score")
        try:
            rel_int = int(rel)
        except (TypeError, ValueError):
            rel_int = 0
        name = str(npc.get("name") or "")
        return rel_int, name

    for npc in sorted(npcs, key=_hostility_key):
        npc_id = npc.get("id")
        if npc_id:
            return npc_id
    return None


def resolve(state: GameState) -> MechanicOutput:
    """Resolve state into validated MechanicOutput: action_type, dc, roll, success, events, narrative_facts."""
    seed = _get_seed(state)
    rng = random.Random(seed) if seed is not None else random
    user_input = (state.user_input or "").strip()
    intent = state.intent
    action_type = _classify_action(user_input, intent)

    if action_type == "TALK":
        tone, ad, frd, cad, crr = _choice_impact_for_action("TALK", True)
        return MechanicOutput(
            action_type="TALK",
            time_cost_minutes=get_time_cost("TALK"),
            events=[],
            outcome_summary="Dialogue (skip mechanic).",
            tone_tag=tone,
            alignment_delta=ad,
            faction_reputation_delta=frd,
            companion_affinity_delta=cad,
            companion_reaction_reason=crr,
        )
    if action_type == "IDLE":
        return MechanicOutput(
            action_type="IDLE",
            time_cost_minutes=0,
            events=[],
            narrative_facts=["No input."],
            outcome_summary="No input.",
            tone_tag=TONE_TAG_NEUTRAL,
            alignment_delta={},
            faction_reputation_delta={},
            companion_affinity_delta={},
            companion_reaction_reason={},
        )

    # Physics: modifier, DC, roll
    modifier = _get_modifier(state, action_type)
    dc = _compute_dc(state, action_type, user_input)
    roll = rng.randint(1, 20)

    # 3.3: Contextual advantage/disadvantage
    inventory = (state.player.inventory if state.player else []) or []
    campaign = getattr(state, "campaign", None) or {}
    world_time = int(campaign.get("world_time_minutes") or 0) if isinstance(campaign, dict) else 0
    env_mods = environmental_modifiers(
        action_type=action_type,
        location=state.current_location or "",
        user_input=user_input,
        inventory=inventory,
        world_time_minutes=world_time,
    )
    env_bonus = sum(int(m.get("value", 0)) for m in env_mods)
    total = roll + modifier + env_bonus
    success = total >= dc

    events: List[Event] = []
    narrative_facts: List[str] = []
    time_cost_minutes = get_time_cost(action_type)

    player_id = _player_id(state)
    current_location = state.current_location or "unknown"

    if action_type == "TRAVEL":
        dest, to_planet = _parse_travel_destination(user_input)
        if dest:
            move_payload: dict = {
                "character_id": player_id,
                "from_location": current_location,
                "to_location": dest,
            }
            if to_planet:
                move_payload["to_planet"] = to_planet
                # Interplanetary travel takes longer (hyperspace jump)
                time_cost_minutes = TRAVEL_HYPERSPACE_MINUTES
                # V2.10: Check starship ownership for transport method
                _starship = getattr(state, "player_starship", None)
                if _starship and _starship.get("has_starship"):
                    narrative_facts.append(f"Hyperspace jump to {to_planet}.")
                else:
                    # No ship: player must hire passage (NPC transport)
                    _passage_cost = rng.randint(100, 500)
                    narrative_facts.append(f"Arranged passage to {to_planet} (cost: {_passage_cost} credits).")
                    narrative_facts.append("The player does not have their own ship — they are traveling as a passenger.")
                    events.append(Event(
                        event_type="FLAG_SET",
                        payload={"key": "hired_passage", "value": True},
                    ))
            events.append(Event(
                event_type="MOVE",
                payload=move_payload,
            ))
        else:
            time_cost_minutes = 0
            narrative_facts.append("No destination specified.")

    elif action_type == "ATTACK":
        target_id = _select_attack_target(state, user_input)
        if target_id:
            events.append(Event(
                event_type="FLAG_SET",
                payload={"key": "public_violence", "value": True},
            ))
            if success:
                amount = rng.randint(1, 6)
                events.append(Event(
                    event_type="DAMAGE",
                    payload={
                        "character_id": target_id,
                        "amount": amount,
                        "source": player_id,
                    },
                ))
                events.append(Event(
                    event_type="RELATIONSHIP",
                    payload={"npc_id": target_id, "delta": -1, "reason": "attacked"},
                ))
            else:
                backlash = rng.randint(1, 3)
                events.append(Event(
                    event_type="DAMAGE",
                    payload={
                        "character_id": player_id,
                        "amount": backlash,
                        "source": target_id,
                    },
                ))
                events.append(Event(
                    event_type="FLAG_SET",
                    payload={"key": "combat_alert", "value": True},
                ))
                narrative_facts.append("Your attack leaves you exposed.")
        else:
            narrative_facts.append("No clear target present.")

    elif action_type == "SNEAK":
        if success:
            narrative_facts.append("You remain undetected.")
        else:
            narrative_facts.append("You were noticed.")

    elif action_type == "PERSUADE":
        npc_id = _first_npc_id(state)
        if npc_id and success:
            events.append(Event(
                event_type="RELATIONSHIP",
                payload={"npc_id": npc_id, "delta": 1, "reason": "persuaded"},
            ))
        elif npc_id and not success:
            events.append(Event(
                event_type="RELATIONSHIP",
                payload={"npc_id": npc_id, "delta": -1, "reason": "failed_persuasion"},
            ))
        elif not npc_id:
            narrative_facts.append("No one present to persuade.")

    elif action_type == "INVESTIGATE":
        if success:
            events.append(Event(
                event_type="FLAG_SET",
                payload={"key": "clue_found", "value": True},
            ))

    elif action_type == "INTERACT":
        item = _parse_item_name(user_input)
        if item:
            events.append(Event(
                event_type="ITEM_GET",
                payload={
                    "owner_id": player_id,
                    "item_name": item,
                    "quantity_delta": 1,
                    "attributes": {},
                },
            ))

    # V2.5: Compute stress, critical outcome, world reaction
    stress = _compute_stress_delta(action_type, success, roll, events)
    critical = _compute_critical_outcome(roll)
    world_reaction = _compute_world_reaction_needed(events)

    # Critical failure: add complication event + narrative fact
    if critical == "CRITICAL_FAILURE":
        events.append(Event(
            event_type="FLAG_SET",
            payload={"key": "complication_active", "value": True},
        ))
        narrative_facts.append("CRITICAL FAILURE: something goes terribly wrong.")

    # Critical success: add narrative fact about exceptional outcome
    if critical == "CRITICAL_SUCCESS":
        narrative_facts.append("CRITICAL SUCCESS: exceptional outcome with bonus effects.")

    # Build outcome summary with modifier details
    mod_str = f"{roll}+{_get_modifier(state, action_type)}"
    if env_bonus:
        sign = "+" if env_bonus > 0 else ""
        mod_str += f"{sign}{env_bonus}env"
    outcome_summary = f"{action_type}: {'success' if success else 'failure'}" + (
        f" (roll {mod_str} vs DC {dc})" if dc is not None else ""
    )
    checks = []
    if dc is not None:
        checks.append({"dc": dc, "roll": roll, "result": "success" if success else "failure"})
    # 3.3: Add environmental modifier narrative facts for narrator context
    for m in env_mods:
        src = m.get("source", "")
        val = int(m.get("value", 0))
        direction = "advantage" if val > 0 else "disadvantage"
        narrative_facts.append(f"Environmental {direction}: {src} ({'+' if val > 0 else ''}{val})")

    tone, ad, frd, cad, crr = _choice_impact_for_action(action_type, success)
    return MechanicOutput(
        action_type=action_type,
        time_cost_minutes=time_cost_minutes,
        events=events,
        outcome_summary=outcome_summary[:200],
        dc=dc,
        roll=roll,
        success=success,
        narrative_facts=narrative_facts,
        checks=checks,
        modifiers=env_mods,
        tone_tag=tone,
        alignment_delta=ad,
        faction_reputation_delta=frd,
        companion_affinity_delta=cad,
        companion_reaction_reason=crr,
        stress_delta=stress,
        critical_outcome=critical,
        world_reaction_needed=world_reaction,
    )


class MechanicAgent:
    """Resolves game mechanics from user input and state; returns strict MechanicOutput. Authoritative for physics."""

    def __init__(self, llm: object | None = None) -> None:
        self._llm = llm

    def resolve(self, state: GameState) -> MechanicOutput:
        """Resolve state into validated MechanicOutput (strict JSON contract)."""
        return resolve(state)
