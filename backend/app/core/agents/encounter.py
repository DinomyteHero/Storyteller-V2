"""Encounter manager: checks which NPCs are present at a location (Bible + procedural, deterministic)."""
from __future__ import annotations

import os
import random
import sqlite3
from typing import Any

from backend.app.config import ENABLE_BIBLE_CASTING, ENABLE_PROCEDURAL_NPCS, NPC_RENDER_ENABLED
from backend.app.constants import get_scale_profile
from backend.app.world.era_pack_loader import get_era_pack
from backend.app.world.era_pack_models import EraPack, EraNpcEntry
from backend.app.world.npc_generator import generate_npc, derive_seed
from backend.app.world.npc_renderer import render_npc


MAX_PRESENT_NPCS = 2

# 2.5: Dynamic NPC cap by location type — crowded/public locations get more NPCs
MAX_NPCS_BY_LOC_TAG: dict[str, int] = {
    "cantina": 4,
    "marketplace": 4,
    "spaceport": 3,
    "crowded": 4,
    "public": 3,
    "hangar": 3,
}

# 2.5: Background figure templates by location tag — atmospheric, non-interactable
BACKGROUND_FIGURES: dict[str, list[str]] = {
    "cantina": [
        "a grizzled spacer nursing a drink in the corner",
        "two off-duty soldiers arguing over a game of dejarik",
        "a hooded figure watching the room from a shadowed booth",
        "a Twi'lek server weaving between tables",
        "a Rodian counting credits at the bar",
    ],
    "marketplace": [
        "a Jawa merchant hawking salvaged parts",
        "a mother herding children past the stalls",
        "an elderly Gran inspecting produce with three critical eyes",
        "a pair of uniformed inspectors checking cargo manifests",
        "a street musician playing something melancholy on a hallikset",
    ],
    "spaceport": [
        "maintenance droids scuttling across the tarmac",
        "a customs officer arguing with a freighter captain",
        "a group of passengers waiting near a boarding gate",
        "a fuel technician running diagnostics on a docking clamp",
        "a courier droid beeping urgently as it rolls past",
    ],
    "hangar": [
        "a mechanic buried elbow-deep in a starfighter's engine",
        "a loadlifter droid stacking crates with mechanical precision",
        "a pilot running pre-flight checks in a nearby cockpit",
    ],
    "underworld": [
        "a scarred enforcer leaning against the wall, arms crossed",
        "a nervous slicer hunched over a datapad",
        "a masked figure exchanging a small package in the shadows",
    ],
    "default": [
        "a few locals going about their business",
        "a droid trundling past on some errand",
        "a figure in the distance, watching",
    ],
}


def _seed_from_env() -> int | None:
    """Use seeded RNG if ENCOUNTER_SEED env is set for deterministic spawns."""
    seed = os.environ.get("ENCOUNTER_SEED")
    if seed is not None and str(seed).strip():
        try:
            return int(seed.strip())
        except ValueError:
            return None
    return None


def _row_to_safe_npc(row) -> dict:
    """Build safe dict: id, name, role, relationship_score, location_id, has_secret_agenda. No secret_agenda text."""
    if hasattr(row, "keys"):
        d = dict(row)
    else:
        return {}
    agenda = d.get("secret_agenda")
    has_agenda = agenda is not None and str(agenda).strip() != ""
    return {
        "id": d.get("id"),
        "name": d.get("name"),
        "role": d.get("role"),
        "relationship_score": d.get("relationship_score"),
        "location_id": d.get("location_id"),
        "has_secret_agenda": has_agenda,
    }


def _payload_to_safe_npc(payload: dict[str, Any]) -> dict[str, Any]:
    agenda = payload.get("secret_agenda")
    has_agenda = agenda is not None and str(agenda).strip() != ""
    return {
        "id": payload.get("character_id") or payload.get("id"),
        "name": payload.get("name", "Wanderer"),
        "role": payload.get("role", "NPC"),
        "relationship_score": payload.get("relationship_score", 0),
        "location_id": payload.get("location_id"),
        "has_secret_agenda": has_agenda,
    }


def _infer_faction_id(era_pack: EraPack | None, location_id: str) -> str | None:
    if not era_pack:
        return None
    loc = era_pack.location_by_id(location_id)
    if not loc or not loc.controlling_factions:
        return None
    return loc.controlling_factions[0]


# Tags that indicate a high-authority NPC unlikely to appear in low-status locations
_AUTHORITY_TAGS = {"strategist", "admiral", "commander", "politician", "diplomat", "governor"}
# Tags for underworld/informal locations where authority figures wouldn't casually appear
_UNDERWORLD_LOC_TAGS = {"underworld", "cantina", "hideout", "criminal", "lawless"}
# Tags for NPCs that naturally fit informal/underworld scenes
_UNDERWORLD_NPC_TAGS = {"smuggler", "criminal", "bounty_hunter", "opportunist", "mercenary", "information_broker"}

# Minimum score an NPC needs to be considered a candidate — requires at least a
# location match OR faction match. Prevents random tag-only or anchor-only leakage.
_MIN_CANDIDATE_SCORE = 2

# Rarity-based minimum scores: legendary NPCs (Vader, Luke, Tarkin) should only
# appear at their home locations; rare NPCs need strong location/faction fit.
_RARITY_MIN_SCORES = {
    "legendary": 5,  # Needs home location (3) + faction (2) at minimum
    "rare": 3,       # Needs strong location or faction relevance
    "common": _MIN_CANDIDATE_SCORE,
}


def _arc_stage_bonus(npc: EraNpcEntry, arc_stage: str) -> int:
    """Return a small score bonus (0-1) based on whether this NPC type fits the arc stage."""
    npc_tags = set(npc.tags or [])
    archetype = (npc.archetype or "").lower()
    role = (npc.role or "").lower()

    if arc_stage == "SETUP":
        # Prefer information sources, locals, allies — NPCs who create hooks
        if npc_tags & {"information_broker", "merchant", "local", "civilian", "smuggler"}:
            return 1
        if any(k in archetype for k in ("broker", "neutral", "ally", "mentor")):
            return 1
    elif arc_stage == "RISING":
        # Prefer faction-connected NPCs who deepen existing threads
        if npc_tags & {"operative", "rebel", "imperial", "intelligence"}:
            return 1
    elif arc_stage == "CLIMAX":
        # Prefer antagonistic or high-stakes NPCs
        if npc_tags & {"dangerous", "hostile", "bounty_hunter", "warrior"}:
            return 1
        if any(k in archetype for k in ("hunter", "enforcer", "villain", "rival")):
            return 1
    elif arc_stage == "RESOLUTION":
        # Prefer ally/neutral NPCs for aftermath and reflection
        if npc_tags & {"allied", "neutral", "civilian", "mentor"}:
            return 1
        if any(k in archetype for k in ("ally", "mentor", "hero", "neutral")):
            return 1
    return 0


def get_dynamic_npc_cap(location_tags: set[str], campaign_scale: str | None = None) -> int:
    """Return the dynamic NPC cap for a location based on its tags and campaign scale."""
    profile = get_scale_profile(campaign_scale)
    for tag, base_cap in MAX_NPCS_BY_LOC_TAG.items():
        if tag in location_tags:
            return max(1, round(base_cap * profile.npc_cap_multiplier))
    return profile.max_present_npcs


def _get_pack_background_figures(era_id: str) -> dict[str, list[str]]:
    """Load background_figures from era pack if available, else empty dict."""
    try:
        from backend.app.world.era_pack_loader import get_era_pack
        pack = get_era_pack(era_id)
        if pack and pack.background_figures:
            return dict(pack.background_figures)
    except Exception:
        pass
    return {}


def generate_background_figures(
    location_tags: set[str],
    era_id: str = "REBELLION",
    rng: random.Random | None = None,
    count: int = 3,
) -> list[str]:
    """Generate deterministic background figure descriptions for atmosphere.

    These are non-interactable — just flavor text for the narrator.
    V3.1: Checks era pack background_figures first, falls back to built-in dict.
    """
    rng = rng or random
    # Try era-pack-specific figures first
    pack_figures = _get_pack_background_figures(era_id)
    source = pack_figures if pack_figures else BACKGROUND_FIGURES
    pool: list[str] = []
    for tag in location_tags:
        pool.extend(source.get(tag, []))
    if not pool:
        pool = list(source.get("default", BACKGROUND_FIGURES.get("default", [])))
    rng.shuffle(pool)
    return pool[:count]


def choose_present_npcs(
    state: dict[str, Any],
    era_pack: EraPack,
    *,
    location_id: str | None = None,
    existing_ids: set[str] | None = None,
    rng: random.Random | None = None,
    max_npcs: int = MAX_PRESENT_NPCS,
) -> list[EraNpcEntry]:
    """Deterministically choose NPCs for the current location from the Era Pack.

    Scoring:
      +3  NPC's default_location or home_locations match
      +2  NPC's faction controls this location
      +1  NPC tags overlap with location tags
      +1  Arc-stage bonus (NPC archetype fits current narrative stage)
      -2  Scene fitness penalty (authority figure in underworld den, etc.)

    Minimum score depends on NPC rarity:
      legendary (Vader, Luke, Tarkin) >= 5  (must be at home location)
      rare     (Ackbar, Wedge, Boba)  >= 3  (strong location/faction fit)
      common   (everyone else)        >= 2  (standard threshold)
    Anchor status no longer grants a free bonus — NPCs must earn placement
    through location/faction/tag relevance.
    """
    location_id = location_id or state.get("current_location")
    if not location_id:
        return []
    existing_ids = existing_ids or set()
    loc = era_pack.location_by_id(location_id)
    loc_tags = set(loc.tags) if loc else set()
    loc_factions = set(loc.controlling_factions) if loc else set()

    # Read arc stage from previous turn's persisted state
    campaign = state.get("campaign") or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ws = ws if isinstance(ws, dict) else {}
    arc_state = ws.get("arc_state") or {}
    arc_stage = arc_state.get("current_stage", "SETUP")

    # Determine if this is an underworld/informal location
    is_underworld_loc = bool(loc_tags & _UNDERWORLD_LOC_TAGS)

    candidates: list[tuple[int, EraNpcEntry]] = []
    for npc in era_pack.all_npcs():
        if npc.id in existing_ids:
            continue
        score = 0

        # Core location relevance
        if npc.default_location_id == location_id or location_id in (npc.home_locations or []):
            score += 3
        if npc.faction_id and npc.faction_id in loc_factions:
            score += 2
        if loc_tags and set(npc.tags or []) & loc_tags:
            score += 1

        # Scene fitness: penalize authority figures in underworld locations
        # (e.g., Grand Moff Tarkin shouldn't casually appear in a smuggler's den)
        npc_tags = set(npc.tags or [])
        archetype_lower = (npc.archetype or "").lower()
        if is_underworld_loc:
            if npc_tags & _AUTHORITY_TAGS or any(k in archetype_lower for k in ("strategist", "commander", "admiral")):
                score -= 2
            # Boost NPCs that naturally fit underworld scenes
            if npc_tags & _UNDERWORLD_NPC_TAGS:
                score += 1

        # Arc-stage bias: nudge selection toward narratively appropriate NPCs
        score += _arc_stage_bonus(npc, arc_stage)

        # Rarity-gated score threshold — legendary NPCs need higher relevance
        npc_rarity = getattr(npc, "rarity", "common") or "common"
        min_score = _RARITY_MIN_SCORES.get(npc_rarity, _MIN_CANDIDATE_SCORE)
        if score >= min_score:
            candidates.append((score, npc))

    if not candidates:
        return []
    if rng:
        rng.shuffle(candidates)
    candidates.sort(key=lambda x: x[0], reverse=True)
    picked = [npc for _score, npc in candidates[:max_npcs]]
    return picked


def _npc_entry_to_payload(npc: EraNpcEntry, location_id: str, era_pack: EraPack) -> dict[str, Any]:
    stats_json = {
        "origin": "bible",
        "generated": False,
        "era_id": era_pack.era_id,
        "tags": list(npc.tags or []),
        "faction_id": npc.faction_id,
        "default_location_id": npc.default_location_id,
        "voice_tags": list(npc.voice_tags or []),
        "archetype": npc.archetype,
        "traits": list(npc.traits or []),
    }
    return {
        "character_id": npc.id,
        "name": npc.name,
        "role": npc.role or "NPC",
        "relationship_score": 0,
        "secret_agenda": npc.secret,
        "location_id": location_id,
        "stats_json": stats_json,
        "hp_current": 10,
    }


def _read_campaign_scale(state: dict[str, Any] | None) -> str | None:
    """Extract campaign_scale from the pipeline state's world_state_json."""
    if not state:
        return None
    campaign = state.get("campaign") or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ws = ws if isinstance(ws, dict) else {}
    return ws.get("campaign_scale")


class EncounterManager:
    """Queries characters at a location for a campaign. Does not expose secret_agenda."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _apply_npc_lifecycle(
        self,
        npcs: list[dict],
        state: dict[str, Any] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """Apply NPC lifecycle rules to present NPCs.

        Hostile NPCs (relationship_score < -50) have a 30% chance to flee the scene.
        Returns (remaining_npcs, departure_payloads) where departure_payloads are
        NPC_DEPART event payloads for the commit node.
        """
        if not npcs:
            return npcs, []
        state = state or {}
        turn_number = int(state.get("turn_number") or 0)
        campaign_id = state.get("campaign_id", "")
        seed = _seed_from_env()
        if seed is None:
            seed = derive_seed(campaign_id, turn_number, counter=99)
        rng = random.Random(seed)

        remaining: list[dict] = []
        departures: list[dict] = []
        for npc in npcs:
            rel_score = int(npc.get("relationship_score") or 0)
            if rel_score < -50 and rng.random() < 0.30:
                departures.append({
                    "character_id": npc.get("id"),
                    "name": npc.get("name", "Unknown"),
                    "reason": "hostile_flee",
                    "relationship_score": rel_score,
                })
            else:
                remaining.append(npc)
        return remaining, departures

    def _existing_npc_ids(self, campaign_id: str) -> set[str]:
        cur = self._conn.execute(
            "SELECT id FROM characters WHERE campaign_id = ? AND role != 'Player'",
            (campaign_id,),
        )
        return {row[0] for row in cur.fetchall() if row and row[0]}

    def check(
        self,
        campaign_id: str,
        location_id: str | None,
        state: dict[str, Any] | None = None,
    ) -> tuple[list[dict], list[dict], dict | None, list[dict], list[str]]:
        """
        Return (npcs, spawn_payloads, spawn_request, departure_payloads, background_figures).

        - npcs: list of safe NPC dicts at location (excluding Player).
        - spawn_payloads: NPC_SPAWN payloads to persist (commit-only writes).
        - spawn_request: legacy casting request (LLM), only when both Bible/procedural are disabled.
        - departure_payloads: NPC_DEPART payloads for hostile NPCs that fled.
        - background_figures: atmospheric non-interactable figure descriptions.
        """
        if location_id is None:
            return [], [], None, [], []

        cur = self._conn.execute(
            """
            SELECT id, name, role, location_id, relationship_score, secret_agenda
            FROM characters
            WHERE campaign_id = ? AND location_id = ? AND role != 'Player'
            ORDER BY role, name
            """,
            (campaign_id, location_id),
        )
        rows = cur.fetchall()
        npcs = [_row_to_safe_npc(row) for row in rows]
        if npcs:
            remaining, departures = self._apply_npc_lifecycle(npcs, state=state)
            return remaining, [], None, departures, []

        # Legacy behavior when both flags are off: 10% chance to request LLM casting
        if not ENABLE_BIBLE_CASTING and not ENABLE_PROCEDURAL_NPCS:
            seed = _seed_from_env()
            rng = random.Random(seed) if seed is not None else random
            if rng.random() >= 0.10:
                return [], [], None, [], []
            return [], [], {"campaign_id": campaign_id, "location_id": location_id}, [], []

        state = state or {}
        campaign = state.get("campaign") or {}
        era = (campaign.get("time_period") or campaign.get("era") or "REBELLION")
        era = str(era).strip() if isinstance(era, str) else "REBELLION"
        era_pack = get_era_pack(era)

        turn_number = int(state.get("turn_number") or 0)
        seed = _seed_from_env()
        if seed is None:
            seed = derive_seed(campaign_id, turn_number, counter=0)
        rng = random.Random(seed)

        spawn_payloads: list[dict] = []
        present: list[dict] = []

        existing_ids = self._existing_npc_ids(campaign_id)

        # 2.5: Dynamic NPC cap based on location type + campaign scale
        loc = era_pack.location_by_id(location_id) if era_pack else None
        loc_tags = set(loc.tags) if loc else set()
        campaign_scale = _read_campaign_scale(state)
        dynamic_cap = get_dynamic_npc_cap(loc_tags, campaign_scale=campaign_scale)

        # 2.5: Generate background figures for atmosphere (count scaled)
        scale_profile = get_scale_profile(campaign_scale)
        bg_figures = generate_background_figures(loc_tags, era_id=era, rng=rng, count=scale_profile.background_figure_count)

        if ENABLE_BIBLE_CASTING and era_pack:
            selected = choose_present_npcs(
                state,
                era_pack,
                location_id=location_id,
                existing_ids=existing_ids,
                rng=rng,
                max_npcs=dynamic_cap,
            )
            for npc in selected:
                payload = _npc_entry_to_payload(npc, location_id, era_pack)
                spawn_payloads.append(payload)
                present.append(_payload_to_safe_npc(payload))
            if present:
                return present, spawn_payloads, None, [], bg_figures

        if ENABLE_PROCEDURAL_NPCS:
            faction_id = _infer_faction_id(era_pack, location_id) if era_pack else None
            # Extract Hero's Journey archetype hint from arc guidance
            arc_guidance = state.get("arc_guidance") or {}
            arch_hints = arc_guidance.get("archetype_hints") or []
            archetype_hint = arch_hints[0].get("archetype") if arch_hints else None
            payload = generate_npc(
                era_pack=era_pack,
                location_id=location_id,
                faction_id=faction_id,
                campaign_id=campaign_id,
                turn_number=turn_number,
                counter=0,
                archetype_hint=archetype_hint,
            )
            if NPC_RENDER_ENABLED:
                render = render_npc(payload)
                stats = payload.get("stats_json") or {}
                stats["render"] = render
                payload["stats_json"] = stats
            spawn_payloads.append(payload)
            present.append(_payload_to_safe_npc(payload))
            return present, spawn_payloads, None, [], bg_figures

        return [], [], None, [], bg_figures
