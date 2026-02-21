"""V2 campaign API: core campaign CRUD, setup_auto, and shared utilities.

Route modules split from this file:
  - v2_turn.py    — Turn execution (post_turn, turn_stream, classify)
  - v2_content.py — Content catalog and era pack data endpoints
  - v2_player.py  — Player profiles, legacy, sagas, campaign lifecycle
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import sqlite3
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.config import DEFAULT_DB_PATH
from backend.app.content.repository import CONTENT_REPOSITORY
from backend.app.db.connection import get_connection
from backend.app.core.state_loader import build_initial_gamestate, load_player_by_id, load_campaign
from backend.app.core.companions import build_initial_companion_state
from backend.app.core.transcript_store import get_rendered_turns
from backend.app.core.event_store import append_events, get_recent_public_rumors
from backend.app.core.projections import apply_projection
from backend.app.core.episodic_memory import generate_story_summary
from backend.app.models.events import Event
from backend.app.core.agents import CampaignBibleAgent, BiographerAgent
from backend.app.core.story_position import initialize_story_position
from backend.app.core.truth_ledger import upsert_facts
from backend.app.core.error_handling import log_error_with_context

# Re-exported from split modules for backward compatibility
from backend.app.api.campaign_models import (  # noqa: F401
    CreateCampaignRequest, CreateCampaignResponse,
    SetupAutoRequest, SetupAutoResponse,
    ContentCatalogEntry, ContentCatalogResponse,
    ContentDefaultResponse, ContentSummaryResponse,
    TurnRequest, PartyStatusItem, TurnResponse,
    CampaignSummary, CampaignListResponse, StorySummaryResponse,
    SagaCreateRequest, SagaSummary, SagaCampaignSummary, SagaDetailResponse,
)
from backend.app.api.campaign_setup import (  # noqa: F401
    _FALLBACK_LOCATIONS, _FALLBACK_NPC_CAST,
    _location_pool,
    _create_npc_cast, _create_npc_cast_from_skeleton,
    _catalog_items, _resolve_requested_period,
    apply_quick_start_defaults,
    _is_safe_start_location, _pick_start_location_from_pack,
    _deterministic_arc_seed, _generate_arc_seed,
)

# Re-export from v2_turn for backward compatibility (tests import these)
from backend.app.api.v2_turn import (  # noqa: F401
    _run_pre_narrator_pipeline,
    _campaign_turn_lock,
    MAX_USER_INPUT_CHARS,
    _seed_default_objective,
    _world_state_dict,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2", tags=["v2-campaigns"])


# ── Shared utilities ─────────────────────────────────────────────────

def _get_conn():
    """Return DB connection. Migrations are applied once at API startup."""
    return get_connection(DEFAULT_DB_PATH)


def _ensure_campaign_and_player(conn, campaign_id: str, player_id: str) -> None:
    """Raise HTTP 404 if campaign or player not found."""
    if load_campaign(conn, campaign_id) is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if load_player_by_id(conn, campaign_id, player_id) is None:
        raise HTTPException(status_code=404, detail="Player not found")


def _timeline_key_events(era_pack: Any | None) -> list[str]:
    """Extract canonical timeline events from era pack."""
    if era_pack is None:
        return []
    timeline = getattr(era_pack, "legends_timeline", None) or getattr(era_pack, "setting_timeline", None) or {}
    if not isinstance(timeline, dict):
        return []
    events = timeline.get("key_events") or []
    out: list[str] = []
    for event in events:
        text = str(event or "").strip()
        if text:
            out.append(text)
    return out


def _merge_canon_constraints_into_world_state(world_state: dict[str, Any], key_events: list[str]) -> None:
    """Expose canon constraints in narrator-visible ledger fields."""
    if not key_events:
        return
    ledger = world_state.get("ledger")
    if not isinstance(ledger, dict):
        ledger = {}
    established = list(ledger.get("established_facts") or [])
    constraints = list(ledger.get("constraints") or [])
    for event in key_events[:8]:
        fact_line = f"Canon: {event}"
        constraint_line = f"Immutable canon event: {event}"
        if fact_line not in established:
            established.append(fact_line)
        if constraint_line not in constraints:
            constraints.append(constraint_line)
    ledger["established_facts"] = established
    ledger["constraints"] = constraints
    world_state["ledger"] = ledger


def _seed_immutable_canon_truth_facts(conn, campaign_id: str, key_events: list[str]) -> None:
    """Persist historical canon events into truth_facts as immutable records."""
    if not key_events:
        return
    from backend.app.models.turn_contract import Fact

    facts = []
    for event in key_events:
        digest = hashlib.sha1(event.encode("utf-8")).hexdigest()[:10]
        facts.append(Fact(fact_key=f"canon_event_{digest}", fact_value=event))
    upsert_facts(conn, campaign_id, "setup", facts, is_immutable=True)


# ── Setup auto ───────────────────────────────────────────────────────

@router.post("/setup/auto", response_model=SetupAutoResponse)
def setup_auto(body: SetupAutoRequest) -> dict[str, Any]:
    """Create campaign via Architect + Biographer; return campaign_id, player_id, skeleton, character_sheet."""
    from backend.app.core.agents.base import AgentLLM

    conn = _get_conn()
    try:
        apply_quick_start_defaults(body)

        # V12.0: Build campaign settings for cloud resolution of setup agents
        _setup_campaign_settings = {
            "cloud_preset": getattr(body, "cloud_preset", None),
            "preferred_provider": getattr(body, "preferred_provider", None),
            "custom_preset_id": getattr(body, "custom_preset_id", None),
            "agent_overrides": getattr(body, "agent_overrides", None),
        }

        def _setup_llm(role: str) -> AgentLLM | None:
            """Resolve LLM for a setup agent via cloud provider chain."""
            try:
                from backend.app.core.provider_resolver import make_agent_llm
                return make_agent_llm(role, _setup_campaign_settings, conn)
            except Exception:
                try:
                    return AgentLLM(role)
                except Exception:
                    return None

        try:
            _bible = CampaignBibleAgent(llm=_setup_llm("bible"))
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            logger.warning("Failed to initialize CampaignBibleAgent with LLM, using fallback: %s", e, exc_info=True)
            _bible = CampaignBibleAgent(llm=None)
        try:
            _bio = BiographerAgent(llm=_setup_llm("biographer"))
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            logger.warning("Failed to initialize BiographerAgent with LLM, using fallback: %s", e, exc_info=True)
            _bio = BiographerAgent(llm=None)

        req_setting, req_period, req_legacy_era = _resolve_requested_period(
            setting_id=body.setting_id, period_id=body.period_id, time_period=body.time_period,
        )
        era_for_setup = req_period
        era_pack_for_setup = CONTENT_REPOSITORY.get_content(req_setting, req_period)
        _setting_rules = era_pack_for_setup.setting_rules if (era_pack_for_setup and hasattr(era_pack_for_setup, "setting_rules")) else None

        available_locations = (
            list(era_pack_for_setup.start_location_pool)
            if (era_pack_for_setup and era_pack_for_setup.start_location_pool)
            else _FALLBACK_LOCATIONS
        )
        character_sheet = _bio.build(
            body.player_concept, era_for_setup,
            available_locations=available_locations, setting_rules=_setting_rules,
        )

        _bg = character_sheet.get("background", "")
        if body.background_id and (not _bg or _bg.startswith("A traveler")):
            concept = (body.player_concept or "").strip()
            if concept and "--" in concept:
                after_dash = concept.split("--", 1)[1].strip()
                if after_dash:
                    character_sheet["background"] = (
                        after_dash[0].upper() + after_dash[1:] if after_dash else after_dash
                    )
                    if not character_sheet["background"].endswith((".", "!", "?")):
                        character_sheet["background"] += "."

        campaign_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())
        time_period = era_for_setup

        name = character_sheet.get("name", "Hero")
        stats = character_sheet.get("stats") or {}
        hp_current = int(character_sheet.get("hp_current", 10))
        starting_location = character_sheet.get("starting_location", "loc-cantina")

        if (
            era_pack_for_setup
            and era_pack_for_setup.canon_characters
            and body.background_id
        ):
            try:
                from backend.app.core.agents.era_forge_agent import EraForgeAgent
                _era_forge_llm = _setup_llm("era_forge")
                _forge_agent = EraForgeAgent(llm=_era_forge_llm)

                _loc_hints: list[str] = []
                _fac_hints: list[str] = []
                _bg_name = ""
                _bg_desc = ""
                if body.background_answers and era_pack_for_setup.backgrounds:
                    for bg in era_pack_for_setup.backgrounds:
                        if bg.id == body.background_id:
                            _bg_name = bg.name
                            _bg_desc = bg.description
                            for q in bg.questions:
                                answer_idx = (body.background_answers or {}).get(q.id)
                                if answer_idx is not None and isinstance(answer_idx, int) and 0 <= answer_idx < len(q.choices):
                                    choice = q.choices[answer_idx]
                                    if choice.effects:
                                        if choice.effects.location_hint:
                                            _loc_hints.append(choice.effects.location_hint)
                                        if choice.effects.faction_hint:
                                            _fac_hints.append(choice.effects.faction_hint)
                            break

                _canon_dicts = [cc.model_dump(mode="json") for cc in era_pack_for_setup.canon_characters]
                _refined = _forge_agent.refine_canon_characters(
                    _canon_dicts,
                    background_id=body.background_id,
                    background_name=_bg_name,
                    background_description=_bg_desc,
                    location_hints=_loc_hints,
                    faction_hints=_fac_hints,
                )
                from backend.app.world.era_pack_models import CanonCharacterRule
                _refined_rules = []
                for rcc in _refined:
                    try:
                        _refined_rules.append(CanonCharacterRule.model_validate(rcc))
                    except (ValueError, TypeError):
                        logger.debug("Canon character rule validation failed for %r", rcc)
                if _refined_rules:
                    era_pack_for_setup = era_pack_for_setup.model_copy(
                        update={"canon_characters": _refined_rules}
                    )
                    logger.info("Canon character refinement applied: %d characters.", len(_refined_rules))
            except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError, TypeError) as _refine_err:
                logger.warning("Canon character refinement failed (non-fatal): %s", _refine_err)

        era_metadata = (
            era_pack_for_setup.metadata if (era_pack_for_setup and era_pack_for_setup.metadata) else {}
        )
        selected_legacy: dict[str, Any] | None = None
        if body.legacy_id:
            try:
                leg_row = conn.execute(
                    "SELECT legacy_json, saga_id FROM character_legacies WHERE id = ?",
                    (int(body.legacy_id),),
                ).fetchone()
                if leg_row:
                    selected_legacy = json.loads(leg_row["legacy_json"] or "{}")
                    if not body.saga_id and leg_row["saga_id"]:
                        body.saga_id = str(leg_row["saga_id"])
            except (sqlite3.OperationalError, json.JSONDecodeError, TypeError, ValueError) as _legacy_load_err:
                logger.debug("Legacy preload failed (non-fatal): %s", _legacy_load_err)
        bible_dict = _bible.build(
            player_concept=body.player_concept or "",
            time_period=time_period,
            character_sheet=character_sheet,
            setting_rules=_setting_rules,
            themes=body.themes,
            era_metadata=dict(era_metadata) if era_metadata else {},
            returning_legacy=selected_legacy,
        )
        title = bible_dict.get("campaign_title", "New Campaign")

        saga_id: str | None = None
        saga_chapter: int = 1
        if body.saga_id:
            saga_row = conn.execute(
                "SELECT id FROM sagas WHERE id = ?", (body.saga_id,),
            ).fetchone()
            if saga_row:
                saga_id = str(saga_row["id"])
        if not saga_id and body.player_profile_id:
            if body.legacy_id:
                saga_row = conn.execute(
                    """SELECT id FROM sagas
                       WHERE player_id = ? AND universe_id = ?
                       ORDER BY updated_at DESC LIMIT 1""",
                    (body.player_profile_id, req_setting),
                ).fetchone()
                if saga_row:
                    saga_id = str(saga_row["id"])
        if saga_id:
            chapter_row = conn.execute(
                "SELECT COALESCE(MAX(saga_chapter), 0) AS max_chapter FROM campaigns WHERE saga_id = ?",
                (saga_id,),
            ).fetchone()
            saga_chapter = int((chapter_row["max_chapter"] if chapter_row else 0) or 0) + 1

        if era_pack_for_setup and era_pack_for_setup.start_location_pool:
            if body.starting_location:
                starting_location = body.starting_location
            elif body.randomize_starting_location:
                starting_location = random.choice(era_pack_for_setup.start_location_pool)
            character_sheet["starting_location"] = starting_location

        starting_planet = character_sheet.get("starting_planet") or None
        if not starting_planet:
            for bible_loc in (bible_dict.get("locations") or []):
                if isinstance(bible_loc, dict) and bible_loc.get("id") == starting_location:
                    starting_planet = bible_loc.get("planet") or None
                    if starting_planet:
                        character_sheet["starting_planet"] = starting_planet
                    break

        active_factions = [
            f if isinstance(f, dict) else (f.model_dump(mode="json") if hasattr(f, "model_dump") else {})
            for f in (bible_dict.get("active_factions") or [])
        ]
        companion_state = build_initial_companion_state(world_time_minutes=0, era=time_period)
        world_state = {"active_factions": active_factions, **companion_state}
        world_state["setting_id"] = req_setting
        world_state["period_id"] = req_period
        world_state["story_position"] = initialize_story_position(
            setting_id=req_setting, period_id=req_period,
            campaign_mode=body.campaign_mode or "historical", world_time_minutes=0,
        )

        _quest_arcs = bible_dict.get("quest_arcs") or []
        world_state["arc_seed"] = {
            "source": "campaign_bible",
            "active_themes": [arc.get("title", "") for arc in _quest_arcs[:3]],
            "opening_threads": [arc.get("hook", "") for arc in _quest_arcs[:3]],
            "climax_question": _quest_arcs[0].get("stakes", "What will you sacrifice for the greater good?") if _quest_arcs else "What will you sacrifice for the greater good?",
            "arc_intent": bible_dict.get("campaign_theme", "adventure"),
            "opening_crawl": bible_dict.get("opening_crawl", ""),
        }
        world_state["campaign_bible"] = bible_dict

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
            except (ImportError, KeyError, TypeError, ValueError) as _genre_err:
                logger.debug("Genre auto-assignment failed (non-fatal): %s", _genre_err)

        if body.player_profile_id:
            try:
                legacy_rows = conn.execute(
                    "SELECT faction_standings_json, major_decisions_json FROM campaign_legacy WHERE player_profile_id = ? ORDER BY completed_at DESC LIMIT 3",
                    (body.player_profile_id,),
                ).fetchall()
                if legacy_rows:
                    combined: dict[str, int] = {}
                    for lr in legacy_rows:
                        standings = json.loads(lr[0] or "{}")
                        for faction, score in standings.items():
                            combined[faction] = combined.get(faction, 0) + int(score)
                    for faction in combined:
                        combined[faction] = combined[faction] // (2 * len(legacy_rows))
                    existing_rep = world_state.get("faction_reputation", {})
                    for faction, delta in combined.items():
                        existing_rep[faction] = existing_rep.get(faction, 0) + delta
                    world_state["faction_reputation"] = existing_rep
                    logger.info("Seeded faction reputation from %d legacy campaign(s)", len(legacy_rows))

                    most_recent_decisions = json.loads(legacy_rows[0][1] or "[]")
                    if isinstance(most_recent_decisions, list):
                        completion_entry = next(
                            (d for d in reversed(most_recent_decisions)
                             if isinstance(d, dict) and d.get("type") == "campaign_completion"),
                            None,
                        )
                        if completion_entry:
                            legacy_scale = completion_entry.get("recommended_next_scale")
                            legacy_pitch = completion_entry.get("next_campaign_pitch", "")
                            if legacy_scale and body.campaign_scale == "medium":
                                world_state["campaign_scale"] = legacy_scale
                                logger.info("Applied legacy recommended scale: %s", legacy_scale)
                            if legacy_pitch:
                                world_state["legacy_campaign_pitch"] = legacy_pitch
                                logger.info("Injected legacy campaign pitch for architect context")
            except (sqlite3.OperationalError, json.JSONDecodeError, TypeError, ValueError) as _legacy_err:
                logger.debug("Legacy faction seeding failed (non-fatal): %s", _legacy_err)

        npc_cast = bible_dict.get("npc_cast") or []
        _villain = next((n for n in npc_cast if (n.get("role") or "").lower() == "villain"), None)
        _informant = next((n for n in npc_cast if (n.get("role") or "").lower() == "informant"), None)
        _first_npc = next((n for n in npc_cast if n.get("role")), None)
        _first_desc = f"a {(_first_npc.get('role') or 'stranger').lower()}" if _first_npc else "a stranger"
        _villain_desc = f"a {(_villain.get('role') or 'figure').lower()}" if _villain else "a dangerous-looking figure"
        loc_readable = (starting_location or "").replace("loc-", "").replace("-", " ").replace("_", " ").strip() or "here"

        world_state["opening_beats"] = [
            {
                "turn": 2, "beat": "ARRIVAL_AND_ENCOUNTER",
                "goal": (
                    f"Orient the player in {loc_readable} — atmosphere, senses, mood — "
                    f"then {_first_desc} demands attention. Establish setting AND first NPC interaction in one scene."
                ),
                "hook": f"{_first_desc} initiates contact or a visible situation draws the player in.",
                "npcs_visible": [_first_npc.get("name")] if _first_npc else [],
            },
            {
                "turn": 3, "beat": "INCITING_INCIDENT",
                "goal": "The campaign's central tension becomes clear. Something happens that cannot be ignored — a threat, an opportunity, or a moral dilemma.",
                "hook": f"{_villain_desc} makes their presence known, a faction conflict erupts, or critical information surfaces.",
                "npcs_visible": [n.get("name") for n in npc_cast[:3] if n.get("name")],
            },
        ]

        villain_name = _villain.get("name", "the antagonist") if _villain else "the antagonist"
        rival = next((n for n in npc_cast if (n.get("role") or "").lower() == "rival"), None)
        rival_name = rival.get("name", "a rival") if rival else "a rival"
        informant_name = _informant.get("name", "an informant") if _informant else "an informant"
        world_state["act_outline"] = {
            "act_1_setup": f"Player discovers signs of {villain_name}'s operation. {informant_name} may hold key information. Alliances and enemies begin to form.",
            "act_2_rising": f"Escalating conflict with {villain_name}. {rival_name} complicates matters. Player's earlier choices shape available paths.",
            "act_3_climax": "Final confrontation. Player's relationships and decisions determine the outcome.",
            "key_npcs": {"villain": villain_name, "rival": rival_name, "informant": informant_name},
        }

        try:
            from backend.app.core.campaign_init import initialize_campaign_world
            campaign_world = initialize_campaign_world(
                campaign_id=campaign_id, era=time_period,
                era_pack=era_pack_for_setup, player_concept=body.player_concept or "",
                starting_location=starting_location, existing_factions=active_factions,
                skeleton=bible_dict,
                campaign_mode=body.campaign_mode or "historical",
                campaign_scale=body.campaign_scale or "medium",
            )
            world_state["generated_locations"] = campaign_world.get("generated_locations", [])
            world_state["generated_npcs"] = campaign_world.get("generated_npcs", [])
            world_state["generated_quests"] = campaign_world.get("generated_quests", [])
            world_state["world_generation"] = campaign_world.get("world_generation", {})
            world_state["campaign_mode"] = campaign_world.get("campaign_mode", "historical")
            world_state["campaign_scale"] = campaign_world.get("campaign_scale", "medium")
            if campaign_world.get("campaign_blueprint"):
                world_state["campaign_blueprint"] = campaign_world["campaign_blueprint"]
            logger.info(
                "Campaign world generated: %d locations, %d NPCs, %d quests",
                len(world_state["generated_locations"]),
                len(world_state["generated_npcs"]),
                len(world_state["generated_quests"]),
            )
        except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError, TypeError) as _world_err:
            logger.warning("Campaign world generation failed (non-fatal): %s", _world_err)
            world_state["generated_locations"] = []
            world_state["generated_npcs"] = []
            world_state["generated_quests"] = []

        if era_pack_for_setup and hasattr(era_pack_for_setup, "setting_rules"):
            world_state["setting_rules"] = era_pack_for_setup.setting_rules.model_dump(mode="json")

        from backend.app.constants import DIFFICULTY_PROFILES
        _difficulty = body.difficulty if body.difficulty in DIFFICULTY_PROFILES else "normal"
        world_state["difficulty_profile"] = DIFFICULTY_PROFILES[_difficulty]

        if body.species_id:
            world_state["species_id"] = body.species_id

        try:
            from backend.app.core.era_transition import initialize_career_file
            world_state["career_file"] = initialize_career_file(
                time_period or body.time_period or "unknown"
            )
        except (ImportError, KeyError, TypeError, ValueError) as _cf_err:
            logger.warning("Career file initialization failed (non-fatal): %s", _cf_err)

        try:
            from backend.app.core.agents.arc_screenplay_agent import ArcScreenplayAgent
            _arc_agent = ArcScreenplayAgent(llm=_setup_llm("arc_screenplay"))
            _arc_screenplay = _arc_agent.generate(
                era_pack=era_pack_for_setup,
                player_concept=body.player_concept or "",
                background_id=body.background_id,
                origin_context=world_state.get("origin_context"),
                setting_rules=era_pack_for_setup.setting_rules if era_pack_for_setup and hasattr(era_pack_for_setup, "setting_rules") else None,
            )
            world_state["arc_screenplay"] = _arc_screenplay
            if _arc_screenplay.get("opening_crawl"):
                arc_seed = world_state.get("arc_seed") if isinstance(world_state.get("arc_seed"), dict) else {}
                arc_seed["opening_crawl"] = _arc_screenplay["opening_crawl"]
                arc_seed["climax_question"] = _arc_screenplay.get("climax_question", "")
                world_state["arc_seed"] = arc_seed
        except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError, TypeError) as _arc_err:
            logger.warning("ArcScreenplayAgent failed (non-fatal): %s", _arc_err)

        try:
            from backend.app.core.agents.prologue_agent import PrologueScreenplayAgent
            from backend.app.core.prologue_engine import initialize_prologue
            _prologue_agent = PrologueScreenplayAgent(llm=_setup_llm("prologue"))
            _prologue_screenplay = _prologue_agent.generate(
                background_id=body.background_id or "",
                species_id=body.species_id or "",
                choice_effects=None,
                setting_rules=era_pack_for_setup.setting_rules if era_pack_for_setup and hasattr(era_pack_for_setup, "setting_rules") else None,
                available_locations=available_locations,
                prologue_scenario=bible_dict.get("opening_hook") or None,
            )
            world_state = initialize_prologue(world_state, _prologue_screenplay)
            logger.info("PrologueScreenplay generated: title=%r, tone=%s", _prologue_screenplay.get("prologue_title"), _prologue_screenplay.get("tone"))
        except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError, TypeError) as _prologue_err:
            logger.warning("PrologueScreenplayAgent failed (non-fatal): %s", _prologue_err)

        canonical_key_events: list[str] = []
        if (body.campaign_mode or "historical").lower() == "historical":
            canonical_key_events = _timeline_key_events(era_pack_for_setup)
            _merge_canon_constraints_into_world_state(world_state, canonical_key_events)

        world_state_json_str = json.dumps(world_state)
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO campaigns (id, title, time_period, world_state_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (campaign_id, title, time_period or None, world_state_json_str, now_str, now_str),
        )
        if body.player_profile_id:
            conn.execute(
                "UPDATE campaigns SET player_profile_id = ? WHERE id = ?",
                (body.player_profile_id, campaign_id),
            )
        if saga_id:
            try:
                conn.execute(
                    "UPDATE campaigns SET saga_id = ?, saga_chapter = ? WHERE id = ?",
                    (saga_id, saga_chapter, campaign_id),
                )
                conn.execute(
                    "UPDATE sagas SET updated_at = datetime('now') WHERE id = ?",
                    (saga_id,),
                )
            except sqlite3.OperationalError as _saga_link_err:
                logger.debug("Saga linkage failed (non-fatal): %s", _saga_link_err)
        background = character_sheet.get("background") or ""

        cyoa_answers_json = None
        concept = (body.player_concept or "").strip()
        if concept and "--" in concept:
            parts = concept.split("--", 1)[1].strip().split(",")
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
        bible_location_ids = [
            loc.get("id", "") if isinstance(loc, dict) else str(loc)
            for loc in (bible_dict.get("locations") or [])
        ] or _FALLBACK_LOCATIONS
        _create_npc_cast_from_skeleton(
            conn, campaign_id,
            {"npc_cast": bible_dict.get("npc_cast", []), "locations": bible_location_ids},
            starting_location,
        )
        conn.execute(
            "UPDATE campaigns SET campaign_bible_json = ? WHERE id = ?",
            (json.dumps(bible_dict), campaign_id),
        )
        if canonical_key_events:
            _seed_immutable_canon_truth_facts(conn, campaign_id, canonical_key_events)
        conn.commit()
        initial_events = [Event(event_type="FLAG_SET", payload={"key": "campaign_started", "value": True})]
        concept = (body.player_concept or "").strip()
        if concept and "--" in concept:
            bg_text = concept.split("--", 1)[1].strip()
            if bg_text:
                initial_events.append(
                    Event(event_type="STORY_NOTE", payload={"text": f"Background: {bg_text}"})
                )
        append_events(conn, campaign_id, 1, initial_events)
        apply_projection(conn, campaign_id, initial_events)
        return SetupAutoResponse(
            campaign_id=campaign_id, player_id=player_id,
            skeleton=bible_dict, character_sheet=character_sheet,
            saga_id=saga_id, saga_chapter=saga_chapter if saga_id else None,
            prologue_mode=bool(world_state.get("prologue_mode", False)),
        )
    except HTTPException:
        raise
    except Exception as e:  # Intentional broad catch: unknown failure modes in setup pipeline
        log_error_with_context(
            error=e, node_name="setup", campaign_id=None, turn_number=None,
            agent_name="setup_auto",
            extra_context={"time_period": (body.time_period or body.period_id or body.setting_id), "themes": body.themes},
        )
        raise
    finally:
        conn.close()


# ── Patch character ──────────────────────────────────────────────────

class PatchCharacterRequest(BaseModel):
    player_id: str
    name: str


@router.patch("/campaigns/{campaign_id}/character")
def patch_character(campaign_id: str, body: PatchCharacterRequest) -> dict[str, Any]:
    """Update mutable character fields (currently: name) after campaign creation."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    if len(name) > 60:
        raise HTTPException(status_code=400, detail="name must be 60 characters or fewer")
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM characters WHERE id = ? AND campaign_id = ? AND role = 'Player'",
            (body.player_id, campaign_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="player character not found")
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE characters SET name = ?, updated_at = ? WHERE id = ? AND campaign_id = ?",
            (name, now_str, body.player_id, campaign_id),
        )
        conn.commit()
        return {"ok": True, "name": name}
    finally:
        conn.close()


# ── Create campaign (minimal path) ──────────────────────────────────

@router.post("/campaigns", response_model=CreateCampaignResponse)
def create_campaign(body: CreateCampaignRequest) -> dict[str, Any]:
    """Create a new campaign and player character. Returns campaign_id and player_id."""
    conn = _get_conn()
    try:
        campaign_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        companion_state = build_initial_companion_state(world_time_minutes=0, era=body.time_period)
        world_state = {"active_factions": [], **companion_state}
        world_state["story_position"] = initialize_story_position(
            setting_id=body.setting_id if hasattr(body, "setting_id") else None,
            period_id=body.time_period,
            campaign_mode="historical", world_time_minutes=0,
        )
        if body.genre:
            world_state["genre"] = body.genre
        world_state["campaign_scale"] = body.campaign_scale or "medium"
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
            (player_id, campaign_id, body.player_name, "Player", body.starting_location,
             json.dumps(body.player_stats), body.hp_current, None, None),
        )
        _create_npc_cast(conn, campaign_id, body.starting_location)
        _seed_default_objective(conn, campaign_id)
        conn.commit()

        initial_events = [
            Event(event_type="FLAG_SET", payload={"key": "campaign_started", "value": True})
        ]
        append_events(conn, campaign_id, 1, initial_events)
        apply_projection(conn, campaign_id, initial_events)
        return CreateCampaignResponse(campaign_id=campaign_id, player_id=player_id)
    finally:
        conn.close()


# ── List / Get campaigns ────────────────────────────────────────────

@router.get("/campaigns", response_model=CampaignListResponse)
def list_campaigns(limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0)):
    """List campaigns so clients can resume previous sessions."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT
                c.id AS campaign_id, c.title AS title, c.time_period AS time_period,
                c.saga_id AS saga_id, c.saga_chapter AS saga_chapter,
                p.id AS player_id, p.name AS player_name,
                COALESCE(
                    (SELECT MAX(te.turn_number) FROM turn_events te WHERE te.campaign_id = c.id), 0
                ) AS current_turn,
                c.updated_at AS updated_at
            FROM campaigns c
            LEFT JOIN characters p ON p.campaign_id = c.id AND p.role = 'Player'
            ORDER BY COALESCE(c.updated_at, c.created_at, c.id) DESC
            LIMIT ? OFFSET ?""",
            (int(limit), int(offset)),
        ).fetchall()
        items = [
            CampaignSummary(
                campaign_id=r["campaign_id"], title=r["title"], time_period=r["time_period"],
                player_id=r["player_id"], player_name=r["player_name"],
                saga_id=r["saga_id"],
                saga_chapter=int(r["saga_chapter"]) if r["saga_chapter"] is not None else None,
                current_turn=int(r["current_turn"] or 0), updated_at=r["updated_at"],
            )
            for r in rows
        ]
        return CampaignListResponse(items=items)
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}/state")
def get_campaign_state(
    campaign_id: str,
    player_id: str = Query(..., description="Player character ID"),
):
    """Return current GameState for the campaign."""
    conn = _get_conn()
    try:
        _ensure_campaign_and_player(conn, campaign_id, player_id)
        state = build_initial_gamestate(conn, campaign_id, player_id)
        return state
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}/world_state")
def get_campaign_world_state(campaign_id: str) -> dict[str, Any]:
    """Return world_state_json for the campaign."""
    conn = _get_conn()
    try:
        camp = load_campaign(conn, campaign_id)
        if camp is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        return {"campaign_id": campaign_id, "world_state": camp.get("world_state_json") or {}}
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}/summary", response_model=StorySummaryResponse)
def get_campaign_story_summary(campaign_id: str) -> StorySummaryResponse:
    """Return a quick narrative recap for players returning to a campaign."""
    conn = _get_conn()
    try:
        camp = load_campaign(conn, campaign_id)
        if camp is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        ws = _world_state_dict(camp)
        summary = generate_story_summary(conn, campaign_id, world_state=ws, max_recent_memories=5)
        return StorySummaryResponse(campaign_id=campaign_id, **summary)
    finally:
        conn.close()


# ── Memory crystallization ──────────────────────────────────────────

class CrystallizeMemoryRequest(BaseModel):
    turn_number: int
    summary: str = ""
    emotional_tag: str = ""


@router.post("/campaigns/{campaign_id}/memories/crystallize")
def crystallize_memory(campaign_id: str, body: CrystallizeMemoryRequest) -> dict[str, Any]:
    """Manual player/system pin for an important memory turn."""
    conn = _get_conn()
    try:
        if load_campaign(conn, campaign_id) is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        row = conn.execute(
            """SELECT payload_json FROM turn_events
               WHERE campaign_id = ? AND turn_number = ? AND is_hidden = 0
               ORDER BY id ASC LIMIT 20""",
            (campaign_id, body.turn_number),
        ).fetchall()
        event_summaries: list[str] = []
        for item in row:
            try:
                payload = json.loads(item["payload_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                payload = {}
            if isinstance(payload, dict):
                txt = payload.get("text") or payload.get("description")
                if isinstance(txt, str) and txt.strip():
                    event_summaries.append(txt.strip())
        summary = (body.summary or "").strip()
        if not summary:
            summary = event_summaries[0] if event_summaries else f"Marked memory from turn {body.turn_number}."
        from backend.app.core.episodic_memory import EpisodicMemory
        epi = EpisodicMemory(conn, campaign_id)
        epi.add_crystallized_memory(
            turn_number=body.turn_number, memory_type="player_marked",
            summary=summary, full_text=" ".join(event_summaries)[:1200],
            npcs_involved=[], location=None,
            emotional_tag=(body.emotional_tag or "").strip() or None,
        )
        conn.commit()
        return {"campaign_id": campaign_id, "turn_number": body.turn_number, "status": "ok"}
    finally:
        conn.close()


# ── Campaign locations / rumors / transcript ─────────────────────────

@router.get("/campaigns/{campaign_id}/locations")
def get_campaign_locations(campaign_id: str) -> dict[str, Any]:
    """Return merged locations (era pack + generated) for the campaign world map."""
    conn = _get_conn()
    try:
        camp = load_campaign(conn, campaign_id)
        if camp is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        ws = camp.get("world_state_json") or {}
        if isinstance(ws, str):
            ws = json.loads(ws)
        era_id = camp.get("time_period")
        locations = []
        if era_id:
            era_pack = CONTENT_REPOSITORY.get_pack(era_id) if era_id else None
            if era_pack and era_pack.locations:
                for loc in era_pack.locations:
                    locations.append({
                        "id": loc.id, "name": loc.name, "tags": loc.tags or [],
                        "planet": loc.planet or "", "threat_level": loc.threat_level or "low",
                        "scene_types": loc.scene_types or [],
                        "travel_links": [
                            {"to_location_id": tl.to_location_id, "travel_time_minutes": tl.travel_time_minutes}
                            for tl in (loc.travel_links or [])
                        ],
                        "origin": "era_pack",
                    })
        gen_locs = ws.get("generated_locations") or []
        for gloc in gen_locs:
            if isinstance(gloc, dict):
                locations.append({**gloc, "origin": gloc.get("origin", "generated")})
        return {"campaign_id": campaign_id, "locations": locations}
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}/rumors")
def get_campaign_rumors(
    campaign_id: str,
    limit: int = Query(5, ge=1, le=20, description="Max public rumors to return"),
):
    """Return the last `limit` public rumor texts, newest first."""
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
    """Return rendered transcript for the campaign."""
    conn = _get_conn()
    try:
        if load_campaign(conn, campaign_id) is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        turns = get_rendered_turns(conn, campaign_id, limit=limit)
        return {"campaign_id": campaign_id, "turns": turns}
    finally:
        conn.close()
