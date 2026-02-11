"""V2 campaign API: create campaign, get state, run turn (LangGraph engine)."""
from __future__ import annotations

import json
import logging
import random
import uuid
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app.constants import SUGGESTED_ACTIONS_TARGET
from backend.app.config import DEFAULT_DB_PATH, DEV_CONTEXT_STATS, ENABLE_BIBLE_CASTING
from backend.app.core.error_handling import log_error_with_context, create_error_response
from backend.app.world.era_pack_loader import get_era_pack

logger = logging.getLogger(__name__)
from backend.app.db.connection import get_connection
from backend.app.core.state_loader import build_initial_gamestate, load_player_by_id, load_campaign
from backend.app.core.companions import build_initial_companion_state, get_companion_by_id
from backend.app.core.companion_reactions import affinity_to_mood_tag
from backend.app.models.news import NEWS_FEED_MAX
from backend.app.core.transcript_store import get_rendered_turns
from backend.app.core.graph import run_turn
from backend.app.core.event_store import append_events, get_recent_public_rumors
from backend.app.core.projections import apply_projection
from backend.app.models.state import GameState, ActionSuggestion
from backend.app.models.events import Event
from backend.app.core.agents import CampaignArchitect, BiographerAgent

router = APIRouter(prefix="/v2", tags=["v2-campaigns"])

# Default location pool (starting_location is always included)
DEFAULT_LOCATIONS = [
    "loc-cantina",
    "loc-marketplace",
    "loc-docking-bay",
    "loc-lower-streets",
    "loc-hangar",
    "loc-spaceport",
]

# NPC cast: 1 Villain, 1 Rival, 2 Merchants, 2 Informants, 6 Generic (guards, locals, pilots, etc.)
NPC_CAST = [
    {"name": "Draven Koss", "role": "Villain", "secret_agenda": "Seeks to dominate the sector through ruthless control."},
    {"name": "Vekk Tano", "role": "Rival", "secret_agenda": "Wants to beat you to the prize — ambitious and relentless."},
    {"name": "Nura Besh", "role": "Merchant", "secret_agenda": "Deals in black market goods through Twi'lek trade networks."},
    {"name": "Gorrak Mun", "role": "Merchant", "secret_agenda": "Holds a grudge against the syndicate — Sullustan never forgets."},
    {"name": "Whisper", "role": "Informant", "secret_agenda": "Bothan spymaster — sells secrets to the highest bidder."},
    {"name": "Zeel Kaat", "role": "Informant", "secret_agenda": "Devaronian who works for multiple factions."},
    {"name": "TK-4471", "role": "Guard", "secret_agenda": "Bribable but loyal to the post."},
    {"name": "Hera Solus", "role": "Local", "secret_agenda": "Mirialan who knows more than she lets on."},
    {"name": "Renn Voss", "role": "Pilot", "secret_agenda": "Smuggles on the side — fast hands, faster ship."},
    {"name": "Grumthar", "role": "Barkeep", "secret_agenda": "Ithorian barkeep — eavesdrops for the right price."},
    {"name": "Pix", "role": "Mechanic", "secret_agenda": "Jawa tinkerer — sells intel on ship traffic."},
    {"name": "Sarik Vey", "role": "Stranger", "secret_agenda": "Chiss operative — just passing through, or so they claim."},
]


def _active_factions_from_era(time_period: str | None) -> list[dict]:
    """Derive active_factions from Era Pack (deterministic)."""
    if not time_period:
        return []
    pack = get_era_pack(time_period)
    if not pack:
        return []
    out: list[dict] = []
    for f in pack.factions:
        loc = f.home_locations[0] if f.home_locations else "loc-cantina"
        goal = f.goals[0] if f.goals else ""
        out.append({
            "name": f.name,
            "location": loc,
            "current_goal": goal,
            "resources": 5,
            "is_hostile": "hostile" in (f.tags or []),
        })
    return out


def _location_pool(starting_location: str) -> list[str]:
    """Return a small set of locations including starting_location."""
    pool = list(dict.fromkeys([starting_location] + DEFAULT_LOCATIONS))
    return pool


def _create_npc_cast(conn, campaign_id: str, starting_location: str) -> None:
    """Insert 12 NPCs: 1 Villain, 1 Rival, 2 Merchants, 2 Informants, 6 Generic. Do not leak secret_agenda."""
    pool = _location_pool(starting_location)
    for i, npc_def in enumerate(NPC_CAST):
        nid = str(uuid.uuid4())
        location_id = random.choice(pool)
        role = npc_def["role"]
        if role == "Villain":
            rel = random.randint(0, 20)
        elif role == "Rival":
            rel = random.randint(10, 30)
        else:
            rel = random.randint(0, 50)
        conn.execute(
            """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'), datetime('now'))""",
            (
                nid,
                campaign_id,
                npc_def["name"],
                role,
                location_id,
                "{}",
                10,
                rel,
                npc_def["secret_agenda"],
            ),
        )


# --- Request / Response models ---


class CreateCampaignRequest(BaseModel):
    title: str = "New Campaign"
    time_period: str | None = None
    genre: str | None = None
    player_name: str = "Player"
    starting_location: str = "Unknown"
    player_stats: dict[str, int] = Field(default_factory=dict)
    hp_current: int = 10


class CreateCampaignResponse(BaseModel):
    campaign_id: str
    player_id: str


class SetupAutoRequest(BaseModel):
    time_period: str | None = None
    genre: str | None = None
    themes: list[str] = Field(default_factory=list)
    player_concept: str = "A hero in a vast world"
    # Optional starting location controls (Star Wars era packs)
    starting_location: str | None = None
    randomize_starting_location: bool = False
    # Era-specific background (Phase 1: SWTOR-style character creation)
    background_id: str | None = None
    background_answers: dict | None = None  # {question_id: choice_index, ...}
    # V2.8: Player gender for pronoun handling
    player_gender: str | None = None  # "male" or "female"
    # V2.10: Cross-campaign legacy — link to player profile
    player_profile_id: str | None = None


class SetupAutoResponse(BaseModel):
    campaign_id: str
    player_id: str
    skeleton: dict
    character_sheet: dict


class TurnRequest(BaseModel):
    user_input: str
    debug: bool = False
    include_state: bool = False


class PartyStatusItem(BaseModel):
    """Companion status for UI. Optional in turn response."""
    id: str
    name: str
    affinity: int
    loyalty_progress: int
    mood_tag: str | None = None
    # V2.20: PartyState fields (optional for backward compat)
    influence: int | None = None
    trust: int | None = None
    respect: int | None = None
    fear: int | None = None


class TurnResponse(BaseModel):
    """UI contract: required fields always present. state and debug are optional."""
    narrated_text: str
    suggested_actions: list[ActionSuggestion]
    player_sheet: dict
    inventory: list
    quest_log: dict
    world_time_minutes: int | None = None
    state: dict | None = None
    debug: dict | None = None
    # Optional companion/alignment UI (render if present)
    party_status: list[PartyStatusItem] | None = None
    alignment: dict | None = None  # {light_dark, paragon_renegade}
    faction_reputation: dict | None = None
    # ME-style comms/briefing (UI contract: list of {id, headline, body, source_tag, urgency, related_factions})
    news_feed: list[dict] | None = None
    # Dev-only context stats (token budgeting info)
    context_stats: dict | None = None
    # Warning messages (LLM/RAG fallbacks, degradations)
    warnings: list[str] = Field(default_factory=list)
    # V2.17: Canonical DialogueTurn (scene + NPC utterance + player responses)
    dialogue_turn: dict | None = None


def _get_conn():
    """Return DB connection. Migrations are applied once at API startup."""
    return get_connection(DEFAULT_DB_PATH)


def _ensure_campaign_and_player(conn, campaign_id: str, player_id: str) -> None:
    """Raise HTTP 404 if campaign or player not found."""
    if load_campaign(conn, campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if load_player_by_id(conn, campaign_id, player_id) is None:
        raise HTTPException(status_code=404, detail="Player not found")


def _create_npc_cast_from_skeleton(conn, campaign_id: str, skeleton: dict, starting_location: str) -> None:
    """Insert NPCs from skeleton.npc_cast; locations from skeleton.locations or DEFAULT_LOCATIONS."""
    pool = list(dict.fromkeys([starting_location] + (skeleton.get("locations") or DEFAULT_LOCATIONS)))
    npc_cast = skeleton.get("npc_cast") or NPC_CAST
    for npc_def in npc_cast[:12]:
        nid = str(uuid.uuid4())
        location_id = random.choice(pool)
        role = npc_def.get("role", "NPC")
        if role == "Villain":
            rel = random.randint(0, 20)
        elif role == "Rival":
            rel = random.randint(10, 30)
        else:
            rel = random.randint(0, 50)
        conn.execute(
            """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'), datetime('now'))""",
            (
                nid,
                campaign_id,
                npc_def.get("name", "NPC"),
                role,
                location_id,
                "{}",
                10,
                rel,
                npc_def.get("secret_agenda"),
            ),
        )


@router.get("/era/{era_id}/locations")
def get_era_locations(era_id: str):
    """Return known locations for an era pack (for UI starting-area selection)."""
    pack = get_era_pack(era_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Era pack not found")
    return {
        "era_id": pack.era_id,
        "locations": [loc.model_dump(mode="json") for loc in (pack.locations or [])],
    }


@router.get("/era/{era_id}/backgrounds")
def get_era_backgrounds(era_id: str):
    """Return available backgrounds and their question chains for the given era."""
    logger.info(f"Received request for era backgrounds: era_id={era_id}")
    pack = get_era_pack(era_id)
    if not pack:
        logger.error(f"Era pack not found for era_id={era_id}")
        raise HTTPException(status_code=404, detail="Era pack not found")
    logger.info(f"Loaded era pack {pack.era_id} with {len(pack.backgrounds or [])} backgrounds")
    return {
        "era_id": pack.era_id,
        "backgrounds": [bg.model_dump(mode="json") for bg in (pack.backgrounds or [])],
    }


@router.get("/era/{era_id}/companions")
def get_era_companions(era_id: str):
    """Return companion previews for character creation screen."""
    from backend.app.core.companions import load_companions
    companions = load_companions(era=era_id)
    previews = []
    for c in companions[:5]:  # Max 5 companions per era
        voice = c.get("voice") or {}
        previews.append({
            "id": c.get("id", ""),
            "name": c.get("name", "Unknown"),
            "species": c.get("species", ""),
            "archetype": c.get("archetype", ""),
            "motivation": c.get("motivation", ""),
            "voice_belief": voice.get("belief", ""),
        })
    return {"era_id": era_id, "companions": previews}


@router.get("/debug/era-packs")
def debug_era_packs():
    """Debug endpoint showing loaded era packs and their backgrounds count."""
    from backend.app.world.era_pack_loader import load_all_era_packs
    from shared.config import ERA_PACK_DIR
    from pathlib import Path

    pack_dir = Path(ERA_PACK_DIR)
    try:
        packs = load_all_era_packs()
        return {
            "pack_dir": str(pack_dir),
            "pack_dir_exists": pack_dir.exists(),
            "count": len(packs),
            "packs": [
                {
                    "era_id": p.era_id,
                    "backgrounds_count": len(p.backgrounds or []),
                    "locations_count": len(p.locations or []),
                    "companions_count": len(p.companions or []),
                }
                for p in packs
            ]
        }
    except Exception as e:
        logger.exception("Failed to load era packs for debug endpoint")
        return {
            "pack_dir": str(pack_dir),
            "pack_dir_exists": pack_dir.exists(),
            "error": str(e),
            "error_type": type(e).__name__
        }


def _is_safe_start_location(tags: list[str] | None, threat_level: str | None) -> bool:
    tags_lower = {str(t).strip().lower() for t in (tags or []) if str(t).strip()}
    if "prison" in tags_lower:
        return False
    if "dangerous" in tags_lower:
        return False
    if (threat_level or "").strip().lower() in {"high", "extreme"}:
        return False
    return True


def _pick_start_location_from_pack(pack, player_concept: str, *, safe_only: bool = True) -> str:
    """Pick a reasonable starting location from an EraPack (deterministic, concept-biased)."""
    import re

    locs = list(pack.locations or [])
    if safe_only:
        safe = [l for l in locs if _is_safe_start_location(l.tags, l.threat_level)]
        if safe:
            locs = safe
    if not locs:
        return "loc-cantina"

    concept_tokens = set(re.findall(r"[a-z0-9]+", (player_concept or "").lower()))
    if not concept_tokens:
        return locs[0].id

    def _score(loc) -> int:
        tokens = set(re.findall(r"[a-z0-9]+", (loc.name or "").lower()))
        tokens |= set(re.findall(r"[a-z0-9]+", (loc.description or "").lower()))
        tokens |= {str(t).strip().lower() for t in (loc.tags or []) if str(t).strip()}
        if loc.planet:
            tokens.add(str(loc.planet).strip().lower())
        if loc.region:
            tokens.add(str(loc.region).strip().lower())
        return len(concept_tokens & tokens)

    best = max(locs, key=_score)
    return best.id


@router.post("/setup/auto", response_model=SetupAutoResponse)
def setup_auto(body: SetupAutoRequest):
    """Create campaign via Architect + Biographer; return campaign_id, player_id, skeleton, character_sheet."""
    from backend.app.core.agents.base import AgentLLM
    conn = _get_conn()
    try:
        try:
            _arch = CampaignArchitect(llm=AgentLLM("architect"))
        except Exception as e:
            logger.warning("Failed to initialize CampaignArchitect with LLM, using fallback: %s", e, exc_info=True)
            _arch = CampaignArchitect(llm=None)
        try:
            _bio = BiographerAgent(llm=AgentLLM("biographer"))
        except Exception as e:
            logger.warning("Failed to initialize BiographerAgent with LLM, using fallback: %s", e, exc_info=True)
            _bio = BiographerAgent(llm=None)
        skeleton = _arch.build(time_period=body.time_period, themes=body.themes)

        era_for_setup = body.time_period or skeleton.get("time_period")
        era_pack_for_setup = get_era_pack(era_for_setup) if era_for_setup else None
        available_locations = (
            [loc.id for loc in (era_pack_for_setup.locations or [])]
            if (era_pack_for_setup and era_pack_for_setup.locations)
            else skeleton.get("locations")
        )
        character_sheet = _bio.build(
            body.player_concept,
            skeleton.get("time_period"),
            available_locations=available_locations,
        )

        # Safety net: if biographer produced generic background but we have
        # structured background data from the CYOA flow, reconstruct it.
        _bg = character_sheet.get("background", "")
        if (
            body.background_id
            and (not _bg or _bg.startswith("A traveler"))
        ):
            concept = (body.player_concept or "").strip()
            if concept and "--" in concept:
                after_dash = concept.split("--", 1)[1].strip()
                if after_dash:
                    character_sheet["background"] = (
                        after_dash[0].upper() + after_dash[1:]
                        if after_dash
                        else after_dash
                    )
                    if not character_sheet["background"].endswith((".", "!", "?")):
                        character_sheet["background"] += "."

        campaign_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())
        title = skeleton.get("title", "New Campaign")
        time_period = skeleton.get("time_period")
        
        # Extract character info early (needed for NPC generation)
        name = character_sheet.get("name", "Hero")
        stats = character_sheet.get("stats") or {}
        hp_current = int(character_sheet.get("hp_current", 10))
        starting_location = character_sheet.get("starting_location", "loc-cantina")

        # Starting location override / randomization (use era pack if available)
        if era_pack_for_setup and era_pack_for_setup.locations:
            if body.starting_location:
                starting_location = body.starting_location
            elif body.randomize_starting_location:
                safe_ids = [
                    l.id for l in era_pack_for_setup.locations
                    if _is_safe_start_location(l.tags, l.threat_level)
                ] or [l.id for l in era_pack_for_setup.locations]
                starting_location = random.choice(safe_ids)
            else:
                # Avoid very dangerous/prison starts unless explicitly requested.
                loc_obj = era_pack_for_setup.location_by_id(starting_location)
                if loc_obj and not _is_safe_start_location(loc_obj.tags, loc_obj.threat_level):
                    starting_location = _pick_start_location_from_pack(era_pack_for_setup, body.player_concept, safe_only=True)
            character_sheet["starting_location"] = starting_location

        # Resolve starting planet: from character sheet, or look up via era pack
        starting_planet = character_sheet.get("starting_planet") or None
        if not starting_planet and time_period:
            era_pack = era_pack_for_setup if (era_pack_for_setup and era_pack_for_setup.era_id == time_period) else get_era_pack(time_period)
            if era_pack:
                loc_obj = era_pack.location_by_id(starting_location)
                if loc_obj and loc_obj.planet:
                    starting_planet = loc_obj.planet
                    character_sheet["starting_planet"] = starting_planet
        
        # Persist world_state_json: active_factions from SetupOutput (top-level or world_state_json)
        active_factions = skeleton.get("active_factions")
        if not isinstance(active_factions, list):
            world_state = skeleton.get("world_state_json")
            active_factions = (world_state.get("active_factions") if isinstance(world_state, dict) else None) or []
        if not isinstance(active_factions, list):
            active_factions = []

        create_default_npcs = not ENABLE_BIBLE_CASTING
        if ENABLE_BIBLE_CASTING:
            era_factions = _active_factions_from_era(time_period)
            if era_factions:
                active_factions = era_factions
            else:
                # Fallback: create default NPCs if no era pack found
                create_default_npcs = True
        companion_state = build_initial_companion_state(world_time_minutes=0, era=time_period)
        world_state = {"active_factions": active_factions, **companion_state}
        # V2.10: Auto-genre assignment (background + location tags → genre)
        if body.genre:
            world_state["genre"] = body.genre
        else:
            try:
                from backend.app.core.genre_triggers import assign_initial_genre
                loc_tags: list[str] = []
                if era_pack_for_setup:
                    loc_obj = era_pack_for_setup.location_by_id(starting_location)
                    if loc_obj:
                        loc_tags = loc_obj.tags or []
                auto_genre = assign_initial_genre(body.background_id, loc_tags)
                if auto_genre:
                    world_state["genre"] = auto_genre
                    logger.info("Auto-assigned genre '%s' from background=%s, location_tags=%s", auto_genre, body.background_id, loc_tags)
            except Exception as _genre_err:
                logger.debug("Genre auto-assignment failed (non-fatal): %s", _genre_err)
        # V2.10: Seed faction standings from player legacy if profile linked
        if body.player_profile_id:
            try:
                legacy_rows = conn.execute(
                    "SELECT faction_standings_json FROM campaign_legacy WHERE player_profile_id = ? ORDER BY completed_at DESC LIMIT 3",
                    (body.player_profile_id,),
                ).fetchall()
                if legacy_rows:
                    combined: dict[str, int] = {}
                    for lr in legacy_rows:
                        standings = json.loads(lr[0] or "{}")
                        for faction, score in standings.items():
                            combined[faction] = combined.get(faction, 0) + int(score)
                    # Dampen by 50% and average across campaigns
                    for faction in combined:
                        combined[faction] = combined[faction] // (2 * len(legacy_rows))
                    existing_rep = world_state.get("faction_reputation", {})
                    for faction, delta in combined.items():
                        existing_rep[faction] = existing_rep.get(faction, 0) + delta
                    world_state["faction_reputation"] = existing_rep
                    logger.info("Seeded faction reputation from %d legacy campaign(s)", len(legacy_rows))
            except Exception as _legacy_err:
                logger.debug("Legacy faction seeding failed (non-fatal): %s", _legacy_err)

        # V2.12: Generate opening beats — structured 3-turn opening sequence
        npc_cast = skeleton.get("npc_cast") or []
        _villain = next((n for n in npc_cast if (n.get("role") or "").lower() == "villain"), None)
        _informant = next((n for n in npc_cast if (n.get("role") or "").lower() == "informant"), None)
        _first_npc = next((n for n in npc_cast if n.get("role")), None)
        _first_desc = f"a {(_first_npc.get('role') or 'stranger').lower()}" if _first_npc else "a stranger"
        _villain_desc = f"a {(_villain.get('role') or 'figure').lower()}" if _villain else "a dangerous-looking figure"
        loc_readable = (starting_location or "").replace("loc-", "").replace("-", " ").replace("_", " ").strip() or "here"

        # V2.13: Opening beats shifted to match actual DB turn numbers (setup = turn 1,
        # first playable = turn 2). ARRIVAL + ENCOUNTER merged for a richer opening.
        world_state["opening_beats"] = [
            {
                "turn": 2,
                "beat": "ARRIVAL_AND_ENCOUNTER",
                "goal": (
                    f"Orient the player in {loc_readable} — atmosphere, senses, mood — "
                    f"then {_first_desc} demands attention. Establish setting AND first NPC interaction in one scene."
                ),
                "hook": f"{_first_desc} initiates contact or a visible situation draws the player in.",
                "npcs_visible": [_first_npc.get("name")] if _first_npc else [],
            },
            {
                "turn": 3,
                "beat": "INCITING_INCIDENT",
                "goal": "The campaign's central tension becomes clear. Something happens that cannot be ignored — a threat, an opportunity, or a moral dilemma.",
                "hook": f"{_villain_desc} makes their presence known, a faction conflict erupts, or critical information surfaces.",
                "npcs_visible": [n.get("name") for n in npc_cast[:3] if n.get("name")],
            },
        ]

        # V2.12: Lightweight act outline from NPC cast
        villain_name = _villain.get("name", "the antagonist") if _villain else "the antagonist"
        rival = next((n for n in npc_cast if (n.get("role") or "").lower() == "rival"), None)
        rival_name = rival.get("name", "a rival") if rival else "a rival"
        informant_name = _informant.get("name", "an informant") if _informant else "an informant"
        world_state["act_outline"] = {
            "act_1_setup": f"Player discovers signs of {villain_name}'s operation. {informant_name} may hold key information. Alliances and enemies begin to form.",
            "act_2_rising": f"Escalating conflict with {villain_name}. {rival_name} complicates matters. Player's earlier choices shape available paths.",
            "act_3_climax": f"Final confrontation. Player's relationships and decisions determine the outcome.",
            "key_npcs": {
                "villain": villain_name,
                "rival": rival_name,
                "informant": informant_name,
            },
        }

        world_state_json_str = json.dumps(world_state)
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO campaigns (id, title, time_period, world_state_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (campaign_id, title, time_period or None, world_state_json_str, now_str, now_str),
        )
        # V2.10: Link campaign to player profile
        if body.player_profile_id:
            conn.execute(
                "UPDATE campaigns SET player_profile_id = ? WHERE id = ?",
                (body.player_profile_id, campaign_id),
            )
        background = character_sheet.get("background") or ""

        # Parse CYOA answers from player_concept if present
        # Format: "Name -- motivation, origin, inciting_incident, edge"
        cyoa_answers_json = None
        concept = (body.player_concept or "").strip()
        if concept and "--" in concept:
            parts = concept.split("--", 1)[1].strip().split(",")
            # Defensively parse up to 4 CYOA elements
            cyoa_dict = {}
            if len(parts) >= 1:
                cyoa_dict["motivation"] = parts[0].strip()
            if len(parts) >= 2:
                cyoa_dict["origin"] = parts[1].strip()
            if len(parts) >= 3:
                cyoa_dict["inciting_incident"] = parts[2].strip()
            if len(parts) >= 4:
                cyoa_dict["edge"] = parts[3].strip()
            if cyoa_dict:
                cyoa_answers_json = json.dumps(cyoa_dict)

        conn.execute(
            """INSERT INTO characters (id, campaign_id, name, role, location_id, planet_id, stats_json, hp_current, relationship_score, secret_agenda, credits, background, cyoa_answers_json, gender, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, datetime('now'), datetime('now'))""",
            (player_id, campaign_id, name, "Player", starting_location, starting_planet, json.dumps(stats), hp_current, None, None, background, cyoa_answers_json, body.player_gender),
        )
        if create_default_npcs:
            _create_npc_cast_from_skeleton(conn, campaign_id, skeleton, starting_location)
        conn.commit()
        initial_events = [Event(event_type="FLAG_SET", payload={"key": "campaign_started", "value": True})]
        # Seed the ledger with player background so the arc planner has material from turn 1
        concept = (body.player_concept or "").strip()
        if concept and "--" in concept:
            bg_text = concept.split("--", 1)[1].strip()
            if bg_text:
                initial_events.append(
                    Event(event_type="STORY_NOTE", payload={"text": f"Background: {bg_text}"})
                )
        append_events(conn, campaign_id, 1, initial_events)
        apply_projection(conn, campaign_id, initial_events)
        return SetupAutoResponse(campaign_id=campaign_id, player_id=player_id, skeleton=skeleton, character_sheet=character_sheet)
    except HTTPException:
        raise
    except Exception as e:
        log_error_with_context(
            error=e,
            node_name="setup",
            campaign_id=None,
            turn_number=None,
            agent_name="setup_auto",
            extra_context={"time_period": body.time_period, "themes": body.themes},
        )
        raise
    finally:
        conn.close()


@router.post("/campaigns", response_model=CreateCampaignResponse)
def create_campaign(body: CreateCampaignRequest):
    """Create a new campaign and player character. Returns campaign_id and player_id."""
    conn = _get_conn()
    try:
        campaign_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        companion_state = build_initial_companion_state(world_time_minutes=0, era=body.time_period)
        create_default_npcs = not ENABLE_BIBLE_CASTING
        if ENABLE_BIBLE_CASTING:
            active_factions = _active_factions_from_era(body.time_period)
            # Fallback: create default NPCs if no era pack found
            if not active_factions:
                create_default_npcs = True
        else:
            active_factions = []
        world_state = {"active_factions": active_factions, **companion_state}
        if body.genre:
            world_state["genre"] = body.genre
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO campaigns (id, title, time_period, world_state_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (campaign_id, body.title, body.time_period or None, json.dumps(world_state), now_str, now_str),
        )
        conn.execute(
            """INSERT INTO characters (id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'), datetime('now'))""",
            (
                player_id,
                campaign_id,
                body.player_name,
                "Player",
                body.starting_location,
                json.dumps(body.player_stats),
                body.hp_current,
                None,
                None,
            ),
        )
        if create_default_npcs:
            _create_npc_cast(conn, campaign_id, body.starting_location)
        conn.commit()

        # Optional: initial FLAG_SET at turn 1 so get_current_turn_number works sensibly
        initial_events = [
            Event(event_type="FLAG_SET", payload={"key": "campaign_started", "value": True})
        ]
        append_events(conn, campaign_id, 1, initial_events)
        apply_projection(conn, campaign_id, initial_events)
        return CreateCampaignResponse(campaign_id=campaign_id, player_id=player_id)
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}/state", response_model=GameState)
def get_campaign_state(
    campaign_id: str,
    player_id: str = Query(..., description="Player character ID"),
):
    """Return current GameState for the campaign (history populated via state_loader)."""
    conn = _get_conn()
    try:
        _ensure_campaign_and_player(conn, campaign_id, player_id)
        state = build_initial_gamestate(conn, campaign_id, player_id)
        return state
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}/world_state")
def get_campaign_world_state(campaign_id: str):
    """Return world_state_json (flags/quest state) for the campaign."""
    conn = _get_conn()
    try:
        camp = load_campaign(conn, campaign_id)
        if camp is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return {"campaign_id": campaign_id, "world_state": camp.get("world_state_json") or {}}
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}/rumors")
def get_campaign_rumors(
    campaign_id: str,
    limit: int = Query(5, ge=1, le=20, description="Max public rumors to return"),
):
    """Return the last `limit` public rumor texts (TurnEvents where is_public_rumor=True), newest first."""
    conn = _get_conn()
    try:
        if load_campaign(conn, campaign_id) is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        rumors = get_recent_public_rumors(conn, campaign_id, limit=limit)
        return {"campaign_id": campaign_id, "rumors": rumors}
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}/transcript")
def get_campaign_transcript(
    campaign_id: str,
    limit: int = Query(50, ge=1, le=200, description="Max rendered turns to return"),
):
    """Return rendered transcript for the campaign (turns ordered by turn_number desc)."""
    conn = _get_conn()
    try:
        if load_campaign(conn, campaign_id) is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        turns = get_rendered_turns(conn, campaign_id, limit=limit)
        return {"campaign_id": campaign_id, "turns": turns}
    finally:
        conn.close()


def _pad_suggestions_to_three(actions: list) -> list:
    """Backward-compat alias. Use _pad_suggestions_for_ui()."""
    return _pad_suggestions_for_ui(actions)


def _pad_suggestions_for_ui(actions: list) -> list:
    """Pass through suggestions for the UI. SuggestionRefiner owns the 4-item contract."""
    if not actions:
        return []
    from backend.app.core.action_lint import lint_actions

    padded, _notes = lint_actions(actions or [])
    return padded[:SUGGESTED_ACTIONS_TARGET]


@router.post("/campaigns/{campaign_id}/turn", response_model=TurnResponse)
def post_turn(
    campaign_id: str,
    player_id: str = Query(..., description="Player character ID"),
    body: TurnRequest | None = None,
):
    """Run one turn. Returns narrated_text, suggested_actions (padded), player_sheet, inventory, quest_log. state optional."""
    if body is None:
        body = TurnRequest(user_input="")
    conn = _get_conn()
    try:
        _ensure_campaign_and_player(conn, campaign_id, player_id)
        state = build_initial_gamestate(conn, campaign_id, player_id)
        state.user_input = body.user_input
        try:
            result = run_turn(conn, state)
        except Exception as e:
            log_error_with_context(
                error=e,
                node_name="turn",
                campaign_id=campaign_id,
                turn_number=state.turn_number,
                agent_name="run_turn",
                extra_context={"user_input": body.user_input[:100] if body.user_input else None},
            )
            # Re-raise to be caught by global exception handler
            raise
        # V2.8: Pre-generate Director suggestions for the next turn (background)
        camp = load_campaign(conn, campaign_id) or {}
        _ws_raw = camp.get("world_state_json")
        if isinstance(_ws_raw, str):
            try:
                _ws_raw = json.loads(_ws_raw) if _ws_raw else {}
            except json.JSONDecodeError:
                _ws_raw = {}
        _ws_raw = _ws_raw if isinstance(_ws_raw, dict) else {}
        # V3.0: Extract actual quest_log from world_state (populated by QuestTracker)
        quest_log = _ws_raw.get("quest_log") or {}
        player_sheet = result.player.model_dump(mode="json") if result.player else {}
        inventory = (result.player.inventory or []) if result.player else []
        # V2.15: Suggestions come from Director's generate_suggestions() only.
        raw_actions = result.suggested_actions or []
        suggested_actions = _pad_suggestions_for_ui(raw_actions)

        world_time_minutes = None
        if result.campaign and isinstance(result.campaign, dict):
            world_time_minutes = result.campaign.get("world_time_minutes")
        if world_time_minutes is None and camp:
            world_time_minutes = camp.get("world_time_minutes")

        debug_out = None
        if body.debug:
            world_state = _ws_raw if isinstance(_ws_raw, dict) else {}
            active_factions = world_state.get("active_factions")
            if active_factions is None and result.campaign and isinstance(result.campaign.get("world_state_json"), dict):
                active_factions = result.campaign["world_state_json"].get("active_factions")
            debug_out = {
                "router_intent": getattr(result, "intent", None),
                "router_route": getattr(result, "route", None),
                "router_action_class": getattr(result, "action_class", None),
                "router_output": result.router_output.model_dump(mode="json") if getattr(result, "router_output", None) else None,
                "mechanic_output": result.mechanic_result.model_dump(mode="json") if result.mechanic_result else None,
                "director_instructions": getattr(result, "director_instructions", None),
                "present_npcs": getattr(result, "present_npcs", None),
                "world_sim_events": getattr(result, "world_sim_events", None) or [],
                "new_rumors": getattr(result, "new_rumors", None) or [],
                "active_factions": active_factions,
            }

        state_out = None
        if body.include_state:
            state_out = result.model_dump(mode="json")

        party_status: list[PartyStatusItem] | None = None
        alignment_out: dict | None = None
        faction_reputation_out: dict | None = None
        camp = result.campaign if isinstance(result.campaign, dict) else {}
        if camp:
            party_ids = camp.get("party") or []
            if party_ids:
                party_status = []
                for cid in party_ids:
                    comp = get_companion_by_id(cid)
                    name = comp.get("name", cid) if comp else cid
                    affinity = (camp.get("party_affinity") or {}).get(cid, 0)
                    loyalty = (camp.get("loyalty_progress") or {}).get(cid, 0)
                    mood_tag = affinity_to_mood_tag(affinity)
                    party_status.append(
                        PartyStatusItem(id=cid, name=name, affinity=affinity, loyalty_progress=loyalty, mood_tag=mood_tag)
                    )
                # V2.20: Overlay PartyState data (influence, trust, respect, fear)
                ws = camp.get("world_state_json")
                if isinstance(ws, str):
                    import json as _json
                    try:
                        ws = _json.loads(ws)
                    except Exception:
                        ws = {}
                ps_raw = (ws or {}).get("party_state") if isinstance(ws, dict) else None
                if ps_raw and isinstance(ps_raw, dict):
                    cs_map = ps_raw.get("companion_states") or {}
                    for item in party_status:
                        cs = cs_map.get(item.id)
                        if cs and isinstance(cs, dict):
                            item.influence = cs.get("influence", 0)
                            item.trust = cs.get("trust", 0)
                            item.respect = cs.get("respect", 0)
                            item.fear = cs.get("fear", 0)
            aln = camp.get("alignment")
            if isinstance(aln, dict):
                alignment_out = {"light_dark": aln.get("light_dark", 0), "paragon_renegade": aln.get("paragon_renegade", 0)}
            fr = camp.get("faction_reputation")
            if isinstance(fr, dict) and fr:
                faction_reputation_out = dict(fr)
        news_feed_out = None
        if camp:
            nf = camp.get("news_feed")
            if isinstance(nf, list) and nf:
                news_feed_out = [item if isinstance(item, dict) else getattr(item, "model_dump", lambda **kw: item)(mode="json") for item in nf[:NEWS_FEED_MAX]]

        context_stats_out = None
        if DEV_CONTEXT_STATS and result.context_stats:
            context_stats_out = result.context_stats
        warnings_out = getattr(result, "warnings", None) or []

        return TurnResponse(
            narrated_text=result.final_text or "",
            suggested_actions=suggested_actions,
            player_sheet=player_sheet,
            inventory=inventory,
            quest_log=quest_log or {},
            world_time_minutes=world_time_minutes,
            state=state_out,
            debug=debug_out,
            party_status=party_status,
            alignment=alignment_out,
            faction_reputation=faction_reputation_out,
            news_feed=news_feed_out,
            context_stats=context_stats_out,
            warnings=warnings_out,
            dialogue_turn=getattr(result, "dialogue_turn", None),
        )
    except HTTPException:
        # Re-raise HTTP exceptions (e.g., 404 from _ensure_campaign_and_player)
        raise
    except Exception as e:
        # Log and re-raise to be caught by global exception handler
        log_error_with_context(
            error=e,
            node_name="turn",
            campaign_id=campaign_id,
            turn_number=None,
            agent_name="post_turn",
            extra_context={"player_id": player_id},
        )
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# V2.8: Streaming Narrator endpoint (SSE)
# ---------------------------------------------------------------------------


def _run_pre_narrator_pipeline(conn, state: GameState) -> dict:
    """Run pipeline nodes up to (but not including) Narrator.

    Calls each node function directly on the state dict, replicating the
    LangGraph topology without using graph.invoke(). This allows the SSE
    endpoint to stream the Narrator separately.

    Returns the state dict ready for Narrator input.
    """
    from backend.app.core.nodes import state_to_dict
    from backend.app.core.nodes.router import router_node, meta_node
    from backend.app.core.nodes.mechanic import make_mechanic_node
    from backend.app.core.nodes.encounter import make_encounter_node
    from backend.app.core.nodes.world_sim import make_world_sim_node
    from backend.app.core.nodes.companion import companion_reaction_node
    from backend.app.core.nodes.arc_planner import arc_planner_node
    from backend.app.core.nodes.scene_frame import scene_frame_node
    from backend.app.core.nodes.director import make_director_node

    s = state_to_dict(state)
    s["__runtime_conn"] = conn

    # Router
    s = router_node(s)

    # META shortcut: return early so caller handles META path
    if s.get("intent") == "META":
        return s

    # TALK skips Mechanic, goes to Encounter
    if s.get("intent") != "TALK":
        mechanic_node = make_mechanic_node()
        s = mechanic_node(s)

    encounter_node = make_encounter_node()
    s = encounter_node(s)

    world_sim_node = make_world_sim_node()
    s = world_sim_node(s)

    s = companion_reaction_node(s)
    s = arc_planner_node(s)
    s = scene_frame_node(s)

    director_node = make_director_node()
    s = director_node(s)

    return s


def _run_post_narrator_pipeline(conn, state_dict: dict, final_text: str, lore_citations: list) -> dict:
    """Run narrative validation + suggestion refinement + commit after streaming completes."""
    from backend.app.core.nodes.narrative_validator import narrative_validator_node
    from backend.app.core.nodes.suggestion_refiner import make_suggestion_refiner_node
    from backend.app.core.nodes.commit import make_commit_node

    state_dict["final_text"] = final_text
    state_dict["lore_citations"] = lore_citations

    state_dict = narrative_validator_node(state_dict)

    suggestion_refiner = make_suggestion_refiner_node()
    state_dict = suggestion_refiner(state_dict)

    commit_node = make_commit_node()
    state_dict = commit_node(state_dict)

    return state_dict


@router.post("/campaigns/{campaign_id}/turn_stream")
def post_turn_stream(
    campaign_id: str,
    player_id: str = Query(..., description="Player character ID"),
    body: TurnRequest | None = None,
):
    """Stream narration via Server-Sent Events.

    Runs the full pipeline synchronously up to (but not including) Narrator,
    then streams Narrator tokens as SSE ``token`` events. After streaming
    completes, runs post-processing + commit and returns final metadata
    (suggested_actions, player_sheet, etc.) as the last SSE ``done`` event.

    SSE event format:
      - ``data: {"type": "token", "text": "..."}``  — individual token
      - ``data: {"type": "done", "narrated_text": "...", "suggested_actions": [...], ...}``
      - ``data: {"type": "error", "message": "..."}``  — on failure
    """
    if body is None:
        body = TurnRequest(user_input="")

    conn = _get_conn()

    # Validate campaign/player before starting the stream
    try:
        _ensure_campaign_and_player(conn, campaign_id, player_id)
    except HTTPException:
        conn.close()
        raise

    def event_stream():
        try:
            from backend.app.core.nodes import dict_to_state
            from backend.app.core.agents.narrator import (
                _strip_structural_artifacts,
                _strip_embedded_suggestions,
                _truncate_overlong_prose,
                _enforce_pov_consistency,
            )
            from backend.app.core.agents import NarratorAgent
            from backend.app.core.agents.base import AgentLLM
            from backend.app.core.nodes.narrator import _is_high_stakes_combat
            from backend.app.rag.kg_retriever import KGRetriever
            from backend.app.core.warnings import add_warning

            state = build_initial_gamestate(conn, campaign_id, player_id)
            state.user_input = body.user_input

            # Run pre-narrator pipeline (Router → ... → Director)
            pre_state = _run_pre_narrator_pipeline(conn, state)

            # Handle META shortcut (no streaming needed)
            if pre_state.get("intent") == "META":
                from backend.app.core.nodes.router import meta_node
                from backend.app.core.nodes.commit import make_commit_node
                pre_state = meta_node(pre_state)
                commit_fn = make_commit_node()
                result_dict = commit_fn(pre_state)
                result_dict.pop("__runtime_conn", None)
                result_gs = dict_to_state(result_dict)
                raw_actions = result_gs.suggested_actions or []
                suggested_actions = _pad_suggestions_for_ui(raw_actions)
                yield f"data: {json.dumps({'type': 'done', 'narrated_text': result_gs.final_text or '', 'suggested_actions': [a.model_dump(mode='json') if hasattr(a, 'model_dump') else a for a in suggested_actions]})}\n\n"
                return

            # Stream Narrator
            gs = dict_to_state(pre_state)

            # Build KG context (same logic as narrator_node)
            shared_char_ctx = pre_state.get("shared_kg_character_context", "")
            shared_event_ctx = pre_state.get("shared_kg_relevant_events", "")
            shared_mem_block = pre_state.get("shared_episodic_memories", "")
            kg_retriever = KGRetriever()

            if shared_char_ctx or shared_event_ctx:
                campaign_dict = getattr(gs, "campaign", None) or {}
                era = (campaign_dict.get("time_period") or campaign_dict.get("era") or "rebellion").strip() or "rebellion"
                loc_ctx = kg_retriever.get_location_context(gs.current_location or "", era)
                kg_parts = [p for p in [shared_char_ctx, loc_ctx, shared_event_ctx] if p]
                kg_context = "## Knowledge Graph Context\n" + "\n\n".join(kg_parts) if kg_parts else ""
            else:
                kg_context = kg_retriever.get_context_for_narrator(gs)

            if shared_mem_block:
                kg_context = (kg_context + "\n\n" + shared_mem_block) if kg_context else shared_mem_block
            else:
                try:
                    from backend.app.core.episodic_memory import EpisodicMemory
                    epi = EpisodicMemory(conn, gs.campaign_id or "")
                    query_text = (gs.user_input or "") + " " + (gs.current_location or "")
                    npc_names = [n.get("name", "") for n in (gs.present_npcs or []) if n.get("name")]
                    memories = epi.recall(
                        query_text=query_text,
                        current_turn=int(gs.turn_number or 0),
                        location_id=gs.current_location,
                        npcs=npc_names,
                        max_results=4,
                    )
                    mem_block = epi.format_for_prompt(memories, max_chars=500)
                    if mem_block:
                        kg_context = (kg_context + "\n\n" + mem_block) if kg_context else mem_block
                except Exception:
                    pass

            # Create NarratorAgent for streaming
            from backend.app.config import ENABLE_CHARACTER_FACETS
            from backend.app.rag.lore_retriever import retrieve_lore
            from backend.app.rag.character_voice_retriever import get_voice_snippets
            from backend.app.rag.retrieval_bundles import NARRATOR_DOC_TYPES, NARRATOR_SECTION_KINDS
            from backend.app.rag.style_retriever import retrieve_style_layered

            def lore_retriever_fn(query, top_k=6, era=None, related_npcs=None):
                return retrieve_lore(query, top_k=top_k, era=era, doc_types=NARRATOR_DOC_TYPES, section_kinds=NARRATOR_SECTION_KINDS, related_npcs=related_npcs)

            voice_retriever_fn = None
            if ENABLE_CHARACTER_FACETS:
                voice_retriever_fn = lambda cids, era, k=6: get_voice_snippets(cids, era, k=k)

            def style_retriever_fn(query, top_k=3, era_id=None, genre=None, archetype=None):
                return retrieve_style_layered(query, top_k=top_k, era_id=era_id, genre=genre, archetype=archetype)

            try:
                narrator_llm = AgentLLM("narrator")
            except Exception:
                narrator_llm = None

            narrator = NarratorAgent(
                llm=narrator_llm,
                lore_retriever=lore_retriever_fn,
                voice_retriever=voice_retriever_fn,
                style_retriever=style_retriever_fn,
            )

            # Stream tokens
            accumulated = ""
            for token in narrator.generate_stream(gs, kg_context=kg_context):
                accumulated += token
                yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"

            # Post-process accumulated text
            # V2.15: Post-process streamed prose (no suggestion extraction needed)
            final_text = _strip_structural_artifacts(accumulated)
            final_text = _strip_embedded_suggestions(final_text)
            final_text = _enforce_pov_consistency(final_text)
            final_text = _truncate_overlong_prose(final_text)

            # Append companion banter if available
            campaign_data = dict(pre_state.get("campaign") or {})
            banter_queue = list(campaign_data.get("banter_queue") or [])
            if banter_queue and not _is_high_stakes_combat(pre_state):
                first = banter_queue[0]
                line = first.get("text", first) if isinstance(first, dict) else first
                if line:
                    clean_line = str(line).strip().strip('"').strip("'").strip()
                    if clean_line:
                        final_text = f"{final_text}\n\n---\n\n*{clean_line}*"
                campaign_data = {**campaign_data, "banter_queue": banter_queue[1:]}
                pre_state["campaign"] = campaign_data

            # Run post-narrator pipeline (NarrativeValidator + Commit)
            result_dict = _run_post_narrator_pipeline(conn, pre_state, final_text, [])
            result_dict.pop("__runtime_conn", None)
            result_gs = dict_to_state(result_dict)

            # V2.15: Suggestions come from Director's generate_suggestions() only.
            raw_actions = result_gs.suggested_actions or []
            suggested_actions = _pad_suggestions_for_ui(raw_actions)

            camp = load_campaign(conn, campaign_id) or {}
            _ws_sse_raw = camp.get("world_state_json")
            if isinstance(_ws_sse_raw, str):
                try:
                    _ws_sse_raw = json.loads(_ws_sse_raw) if _ws_sse_raw else {}
                except json.JSONDecodeError:
                    _ws_sse_raw = {}
            _ws_sse_raw = _ws_sse_raw if isinstance(_ws_sse_raw, dict) else {}
            # V3.0: Extract actual quest_log from world_state
            quest_log = _ws_sse_raw.get("quest_log") or {}

            player_sheet = result_gs.player.model_dump(mode="json") if result_gs.player else {}
            inventory = (result_gs.player.inventory or []) if result_gs.player else []

            world_time_minutes = None
            if result_gs.campaign and isinstance(result_gs.campaign, dict):
                world_time_minutes = result_gs.campaign.get("world_time_minutes")
            if world_time_minutes is None and camp:
                world_time_minutes = camp.get("world_time_minutes")

            warnings_out = getattr(result_gs, "warnings", None) or []

            done_payload = {
                "type": "done",
                "narrated_text": final_text,
                "suggested_actions": [
                    a.model_dump(mode="json") if hasattr(a, "model_dump") else a
                    for a in suggested_actions
                ],
                "player_sheet": player_sheet,
                "inventory": inventory,
                "quest_log": quest_log or {},
                "world_time_minutes": world_time_minutes,
                "warnings": warnings_out,
                "dialogue_turn": getattr(result_gs, "dialogue_turn", None),
            }
            yield f"data: {json.dumps(done_payload)}\n\n"

        except Exception as e:
            logger.exception("SSE turn_stream failed for campaign %s", campaign_id)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)[:200]})}\n\n"
        finally:
            conn.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# V2.10: Player Profiles & Cross-Campaign Legacy
# ---------------------------------------------------------------------------


class CreatePlayerProfileRequest(BaseModel):
    display_name: str


class PlayerProfileResponse(BaseModel):
    id: str
    display_name: str
    created_at: str


class CompleteCampaignRequest(BaseModel):
    outcome_summary: str = ""
    character_fate: str = ""


@router.post("/player/profiles", response_model=PlayerProfileResponse)
def create_player_profile(body: CreatePlayerProfileRequest):
    """Create a new player profile for cross-campaign persistence."""
    conn = _get_conn()
    try:
        profile_id = str(uuid.uuid4())
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO player_profiles (id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (profile_id, body.display_name, now_str, now_str),
        )
        conn.commit()
        return PlayerProfileResponse(id=profile_id, display_name=body.display_name, created_at=now_str)
    finally:
        conn.close()


@router.get("/player/profiles")
def list_player_profiles():
    """List all player profiles."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, display_name, created_at FROM player_profiles ORDER BY created_at DESC"
        ).fetchall()
        return {
            "profiles": [
                {"id": r[0], "display_name": r[1], "created_at": r[2]}
                for r in rows
            ]
        }
    finally:
        conn.close()


@router.get("/player/{player_profile_id}/legacy")
def get_player_legacy(player_profile_id: str):
    """Fetch past campaign outcomes for a player profile."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, campaign_id, era, background_id, genre, outcome_summary, "
            "faction_standings_json, major_decisions_json, character_fate, arc_stage_reached, completed_at "
            "FROM campaign_legacy WHERE player_profile_id = ? ORDER BY completed_at DESC",
            (player_profile_id,),
        ).fetchall()
        legacy = []
        for row in rows:
            cols = ["id", "campaign_id", "era", "background_id", "genre", "outcome_summary",
                    "faction_standings_json", "major_decisions_json", "character_fate",
                    "arc_stage_reached", "completed_at"]
            d = dict(zip(cols, row))
            d["faction_standings"] = json.loads(d.pop("faction_standings_json", "{}"))
            d["major_decisions"] = json.loads(d.pop("major_decisions_json", "[]"))
            legacy.append(d)
        return {"player_profile_id": player_profile_id, "legacy": legacy}
    finally:
        conn.close()


@router.post("/campaigns/{campaign_id}/complete")
def complete_campaign(campaign_id: str, body: CompleteCampaignRequest):
    """Mark a campaign as completed and save legacy data for cross-campaign influence."""
    conn = _get_conn()
    try:
        campaign = load_campaign(conn, campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        profile_id = campaign.get("player_profile_id")
        if not profile_id:
            raise HTTPException(
                status_code=400,
                detail="Campaign has no player profile; legacy cannot be saved. "
                       "Create a player profile and link it to the campaign first.",
            )
        ws = campaign.get("world_state_json")
        if isinstance(ws, str):
            try:
                ws = json.loads(ws)
            except json.JSONDecodeError:
                ws = {}
        ws = ws if isinstance(ws, dict) else {}
        legacy_id = str(uuid.uuid4())
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO campaign_legacy (id, player_profile_id, campaign_id, era, background_id, genre, "
            "outcome_summary, faction_standings_json, major_decisions_json, character_fate, arc_stage_reached, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                legacy_id,
                profile_id,
                campaign_id,
                campaign.get("time_period"),
                ws.get("background_id"),
                ws.get("genre"),
                body.outcome_summary,
                json.dumps(ws.get("faction_reputation", {})),
                json.dumps(ws.get("major_decisions", [])),
                body.character_fate,
                (ws.get("arc_state", {}).get("current_stage", "SETUP") if isinstance(ws.get("arc_state"), dict) else "SETUP"),
                now_str,
            ),
        )
        conn.commit()
        return {"status": "completed", "legacy_id": legacy_id, "campaign_id": campaign_id}
    finally:
        conn.close()
