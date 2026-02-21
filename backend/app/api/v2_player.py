"""V2 player profiles, legacy, sagas, and campaign lifecycle endpoints."""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.config import DEFAULT_DB_PATH
from backend.app.content.repository import CONTENT_REPOSITORY
from backend.app.db.connection import get_connection
from backend.app.core.state_loader import load_campaign, load_player_by_id
from backend.app.api.campaign_models import (
    SagaCreateRequest, SagaSummary, SagaCampaignSummary, SagaDetailResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2", tags=["v2-player"])


def _get_conn():
    return get_connection(DEFAULT_DB_PATH)


# ── Player profiles ─────────────────────────────────────────────────

class CreatePlayerProfileRequest(BaseModel):
    display_name: str


class PlayerProfileResponse(BaseModel):
    id: str
    display_name: str
    created_at: str


@router.post("/player/profiles", response_model=PlayerProfileResponse)
def create_player_profile(body: CreatePlayerProfileRequest) -> PlayerProfileResponse:
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
def list_player_profiles() -> dict[str, Any]:
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
            ],
        }
    finally:
        conn.close()


@router.get("/player/{player_profile_id}/legacy")
def get_player_legacy(player_profile_id: str) -> dict[str, Any]:
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
            cols = [
                "id", "campaign_id", "era", "background_id", "genre", "outcome_summary",
                "faction_standings_json", "major_decisions_json", "character_fate",
                "arc_stage_reached", "completed_at",
            ]
            d = dict(zip(cols, row))
            d["faction_standings"] = json.loads(d.pop("faction_standings_json", "{}"))
            d["major_decisions"] = json.loads(d.pop("major_decisions_json", "[]"))
            legacy.append(d)
        return {"player_profile_id": player_profile_id, "legacy": legacy}
    finally:
        conn.close()


# ── Sagas ────────────────────────────────────────────────────────────

@router.post("/sagas", response_model=SagaSummary)
def create_saga(body: SagaCreateRequest) -> SagaSummary:
    """Create a saga container for linked campaigns."""
    conn = _get_conn()
    try:
        saga_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO sagas (id, player_id, universe_id, title, created_at, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (saga_id, body.player_id, body.universe_id, body.title),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, player_id, universe_id, title, created_at, updated_at FROM sagas WHERE id = ?",
            (saga_id,),
        ).fetchone()
        return SagaSummary(
            saga_id=str(row["id"]), player_id=str(row["player_id"]),
            universe_id=str(row["universe_id"]), title=str(row["title"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
            campaign_count=0,
        )
    finally:
        conn.close()


@router.get("/player/{player_profile_id}/sagas")
def list_sagas(player_profile_id: str) -> dict[str, Any]:
    """List sagas for a player, with campaign counts."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT s.id, s.player_id, s.universe_id, s.title, s.created_at, s.updated_at,
                      COUNT(c.id) AS campaign_count
               FROM sagas s
               LEFT JOIN campaigns c ON c.saga_id = s.id
               WHERE s.player_id = ?
               GROUP BY s.id, s.player_id, s.universe_id, s.title, s.created_at, s.updated_at
               ORDER BY s.updated_at DESC""",
            (player_profile_id,),
        ).fetchall()
        return {
            "sagas": [
                SagaSummary(
                    saga_id=str(r["id"]), player_id=str(r["player_id"]),
                    universe_id=str(r["universe_id"]), title=str(r["title"]),
                    created_at=r["created_at"], updated_at=r["updated_at"],
                    campaign_count=int(r["campaign_count"] or 0),
                ).model_dump(mode="json")
                for r in rows
            ],
        }
    finally:
        conn.close()


@router.get("/sagas/{saga_id}", response_model=SagaDetailResponse)
def get_saga_detail(saga_id: str) -> SagaDetailResponse:
    """Fetch saga metadata and ordered campaign timeline."""
    conn = _get_conn()
    try:
        saga = conn.execute(
            "SELECT id, player_id, universe_id, title, created_at, updated_at FROM sagas WHERE id = ?",
            (saga_id,),
        ).fetchone()
        if not saga:
            raise HTTPException(status_code=404, detail="Saga not found")
        campaigns = conn.execute(
            """SELECT c.id, c.title, c.time_period, c.saga_chapter, c.updated_at,
                      cl.legacy_json
               FROM campaigns c
               LEFT JOIN character_legacies cl ON cl.campaign_id = c.id
               WHERE c.saga_id = ?
               ORDER BY c.saga_chapter ASC, c.updated_at ASC""",
            (saga_id,),
        ).fetchall()
        items: list[SagaCampaignSummary] = []
        for row in campaigns:
            excerpt = None
            try:
                if row["legacy_json"]:
                    legacy_doc = json.loads(row["legacy_json"])
                    excerpt = str(legacy_doc.get("crystallized_memories_summary") or "")[:220] or None
            except (json.JSONDecodeError, TypeError, KeyError):
                excerpt = None
            items.append(
                SagaCampaignSummary(
                    campaign_id=str(row["id"]), title=str(row["title"]),
                    time_period=str(row["time_period"]) if row["time_period"] else None,
                    saga_chapter=int(row["saga_chapter"] or 1),
                    updated_at=row["updated_at"], legacy_excerpt=excerpt,
                )
            )
        return SagaDetailResponse(
            saga=SagaSummary(
                saga_id=str(saga["id"]), player_id=str(saga["player_id"]),
                universe_id=str(saga["universe_id"]), title=str(saga["title"]),
                created_at=saga["created_at"], updated_at=saga["updated_at"],
                campaign_count=len(items),
            ),
            campaigns=items,
        )
    finally:
        conn.close()


# ── Campaign rewind ──────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/rewind")
def rewind_campaign(
    campaign_id: str,
    to_turn: int = Query(..., ge=1, description="Turn number to rewind to (inclusive)"),
) -> dict[str, Any]:
    """Rewind a campaign to a previous turn."""
    conn = _get_conn()
    try:
        from backend.app.core.rewind import rewind_campaign_to_turn
        result = rewind_campaign_to_turn(conn, campaign_id, to_turn)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


# ── Campaign completion ──────────────────────────────────────────────

class CompleteCampaignRequest(BaseModel):
    outcome_summary: str = ""
    character_fate: str = ""


@router.post("/campaigns/{campaign_id}/complete")
def complete_campaign(campaign_id: str, body: CompleteCampaignRequest) -> dict[str, Any]:
    """Mark a campaign as completed and save legacy data."""
    from backend.app.constants import INTER_CAMPAIGN_SCALE_MAP

    conn = _get_conn()
    try:
        campaign = load_campaign(conn, campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        profile_id = campaign.get("player_profile_id")
        if not profile_id:
            raise HTTPException(
                status_code=400,
                detail="Campaign has no player profile; legacy cannot be saved.",
            )
        ws = campaign.get("world_state_json")
        if isinstance(ws, str):
            try:
                ws = json.loads(ws)
            except json.JSONDecodeError:
                ws = {}
        ws = ws if isinstance(ws, dict) else {}
        saga_id = campaign.get("saga_id")
        saga_chapter = int(campaign.get("saga_chapter") or 1)

        arc_stage_reached = (
            ws.get("arc_state", {}).get("current_stage", "SETUP")
            if isinstance(ws.get("arc_state"), dict)
            else "SETUP"
        )
        recommended_next_scale = INTER_CAMPAIGN_SCALE_MAP.get(arc_stage_reached, "medium")

        conclusion_plan = ws.get("conclusion_plan") or {}
        dangling_hooks = conclusion_plan.get("dangling_hooks", []) if isinstance(conclusion_plan, dict) else []
        next_campaign_pitch = ""
        try:
            from backend.app.core.agents.base import AgentLLM
            llm = AgentLLM("campaign_init")
            hooks_text = "; ".join(dangling_hooks[:5]) if dangling_hooks else "no unresolved threads"
            pitch_prompt = (
                "Based on a completed RPG campaign, write a 1-2 sentence hook for the NEXT campaign.\n"
                f"Arc stage reached: {arc_stage_reached}\n"
                f"Outcome: {body.outcome_summary or 'unknown'}\n"
                f"Character fate: {body.character_fate or 'unknown'}\n"
                f"Dangling plot threads: {hooks_text}\n"
                f"Recommended scale: {recommended_next_scale}\n\n"
                "Write ONLY the pitch text (1-2 sentences). No JSON, no formatting."
            )
            raw = llm.complete(
                "You write compelling RPG campaign hooks. Output plain text only.",
                pitch_prompt,
            )
            if raw and isinstance(raw, str) and len(raw.strip()) > 10:
                next_campaign_pitch = raw.strip()[:500]
        except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError) as _pitch_err:
            logger.warning("Next campaign pitch generation failed (non-fatal): %s", _pitch_err)

        if not next_campaign_pitch:
            if dangling_hooks:
                next_campaign_pitch = f"Unfinished business awaits: {dangling_hooks[0]}"
            else:
                next_campaign_pitch = "A new chapter begins. The galaxy remembers your choices."

        major_decisions = list(ws.get("major_decisions", []))
        major_decisions.append({
            "type": "campaign_completion",
            "recommended_next_scale": recommended_next_scale,
            "next_campaign_pitch": next_campaign_pitch,
            "arc_stage_reached": arc_stage_reached,
        })

        legacy_id = str(uuid.uuid4())
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO campaign_legacy (id, player_profile_id, campaign_id, era, background_id, genre, "
            "outcome_summary, faction_standings_json, major_decisions_json, character_fate, arc_stage_reached, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                legacy_id, profile_id, campaign_id, campaign.get("time_period"),
                ws.get("background_id"), ws.get("genre"), body.outcome_summary,
                json.dumps(ws.get("faction_reputation", {})),
                json.dumps(major_decisions), body.character_fate,
                arc_stage_reached, now_str,
            ),
        )
        character_name = "Unknown Hero"
        try:
            p_row = conn.execute(
                "SELECT name FROM characters WHERE campaign_id = ? AND role = 'Player' LIMIT 1",
                (campaign_id,),
            ).fetchone()
            if p_row and p_row["name"]:
                character_name = str(p_row["name"])
        except (sqlite3.OperationalError, KeyError, TypeError):
            logger.debug("Character name lookup failed (non-fatal)", exc_info=True)

        character_legacy_doc: dict[str, Any] = {}
        character_legacy_id: int | None = None
        try:
            from backend.app.core.agents.legacy_agent import LegacyAgent
            cryst_rows = conn.execute(
                """SELECT summary FROM crystallized_memories
                   WHERE campaign_id = ? ORDER BY turn_number DESC LIMIT 8""",
                (campaign_id,),
            ).fetchall()
            crystallized_summaries = [str(r["summary"]) for r in cryst_rows if r and r["summary"]]
            character_legacy_doc = LegacyAgent().generate(
                character_name=character_name, saga_chapter=saga_chapter,
                world_state=ws, outcome_summary=body.outcome_summary,
                character_fate=body.character_fate,
                crystallized_summaries=crystallized_summaries,
            )
            _ins = conn.execute(
                """INSERT INTO character_legacies (player_id, campaign_id, saga_id, legacy_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (profile_id, campaign_id, saga_id, json.dumps(character_legacy_doc), now_str),
            )
            character_legacy_id = int(getattr(_ins, "lastrowid", 0) or 0) or None
        except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError, TypeError) as _char_legacy_err:
            logger.warning("Character legacy generation failed (non-fatal): %s", _char_legacy_err)
        conn.commit()
        return {
            "status": "completed", "legacy_id": legacy_id, "campaign_id": campaign_id,
            "recommended_next_scale": recommended_next_scale,
            "next_campaign_pitch": next_campaign_pitch,
            "character_legacy": character_legacy_doc,
            "character_legacy_id": character_legacy_id,
            "player_profile_id": profile_id,
            "saga_id": saga_id, "saga_chapter": saga_chapter,
        }
    finally:
        conn.close()


# ── Era transition ───────────────────────────────────────────────────

class EraTransitionRequest(BaseModel):
    to_era: str
    player_id: str | None = None


@router.post("/campaigns/{campaign_id}/era_transition")
def era_transition(campaign_id: str, body: EraTransitionRequest) -> dict[str, Any]:
    """Execute an era transition and generate a bridge interstitial scene."""
    from backend.app.core.era_transition import execute_transition, ADJACENT_TRANSITIONS
    from backend.app.core.agents.era_transition_scene_agent import EraTransitionSceneAgent
    from backend.app.core.arc_consequence_tracker import capture as capture_consequences

    conn = _get_conn()
    try:
        campaign = load_campaign(conn, campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        ws = campaign.get("world_state_json")
        if isinstance(ws, str):
            try:
                ws = json.loads(ws)
            except json.JSONDecodeError:
                ws = {}
        ws = ws if isinstance(ws, dict) else {}

        current_era = ws.get("era_id") or ws.get("era") or ""
        to_era = body.to_era.upper().strip()

        try:
            new_ws = execute_transition(ws, current_era, to_era)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        player_id = body.player_id or campaign.get("player_id") or ""
        player: dict[str, Any] = {}
        if player_id:
            try:
                player = load_player_by_id(conn, campaign_id, player_id) or {}
            except (sqlite3.OperationalError, KeyError, TypeError):
                logger.debug("Player load failed for era transition (non-fatal)", exc_info=True)

        arc_consequences = capture_consequences(ws, player, [], [])

        available_locations: list[str] = []
        try:
            era_pack = CONTENT_REPOSITORY.get_era_pack(to_era.lower())
            if era_pack and era_pack.locations:
                available_locations = [loc.id for loc in era_pack.locations]
        except (FileNotFoundError, KeyError, TypeError, ValueError):
            logger.debug("Era pack location lookup failed (non-fatal)", exc_info=True)

        transition_bridge = ""
        try:
            transition_bridge = ADJACENT_TRANSITIONS.get(
                (current_era.upper(), to_era.upper()), ""
            ) or f"The galaxy shifts from {current_era} to {to_era}."
        except (KeyError, TypeError, ValueError):
            logger.debug("Transition bridge lookup failed (non-fatal)", exc_info=True)

        setting_rules = None
        try:
            era_pack_obj = CONTENT_REPOSITORY.get_era_pack(to_era.lower())
            if era_pack_obj:
                setting_rules = era_pack_obj.setting_rules
        except (FileNotFoundError, KeyError, TypeError, ValueError):
            logger.debug("Setting rules lookup failed (non-fatal)", exc_info=True)

        agent = EraTransitionSceneAgent()
        transition_scene = agent.generate(
            from_era=current_era, to_era=to_era,
            arc_consequences=arc_consequences, player=player,
            setting_rules=setting_rules, transition_bridge=transition_bridge,
            available_locations=available_locations,
        )

        new_ws["era_id"] = to_era
        new_ws["era"] = to_era
        new_ws["transition_scene"] = transition_scene

        conn.execute(
            "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
            (json.dumps(new_ws), campaign_id),
        )
        conn.commit()

        logger.info("era_transition campaign_id=%s from=%s to=%s", campaign_id, current_era, to_era)
        return {
            "campaign_id": campaign_id, "from_era": current_era, "new_era": to_era,
            "transition_scene": transition_scene,
            "career_file": new_ws.get("career_file", {}),
        }
    finally:
        conn.close()


# ── Prologue completion ──────────────────────────────────────────────

class CompletePrologueRequest(BaseModel):
    player_id: str | None = None


@router.post("/campaigns/{campaign_id}/prologue/complete")
def complete_prologue(campaign_id: str, body: CompletePrologueRequest | None = None) -> dict[str, Any]:
    """Mark the prologue as complete and build the origin_context manifest."""
    from backend.app.core.prologue_engine import build_origin_context_manifest

    conn = _get_conn()
    try:
        campaign = load_campaign(conn, campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        ws = campaign.get("world_state_json")
        if isinstance(ws, str):
            try:
                ws = json.loads(ws)
            except json.JSONDecodeError:
                ws = {}
        ws = ws if isinstance(ws, dict) else {}

        if not ws.get("prologue_mode"):
            return {
                "campaign_id": campaign_id, "status": "already_completed",
                "message": "Prologue was not active or already completed.",
                "origin_context": ws.get("origin_context", {}),
            }

        player_id = (body.player_id if body else None) or campaign.get("player_id") or ""
        player: dict[str, Any] = {}
        if player_id:
            try:
                player = load_player_by_id(conn, campaign_id, player_id) or {}
            except (sqlite3.OperationalError, KeyError, TypeError):
                logger.debug("Player load failed for prologue completion (non-fatal)", exc_info=True)

        origin_context = build_origin_context_manifest(ws, player)

        ws["origin_context"] = origin_context
        ws["prologue_mode"] = False
        ws["prologue_completed"] = True

        conn.execute(
            "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
            (json.dumps(ws), campaign_id),
        )
        conn.commit()

        logger.info(
            "prologue_complete campaign_id=%s background=%s species=%s",
            campaign_id, origin_context.get("background_id", "unknown"),
            origin_context.get("species_id", "unknown"),
        )
        return {
            "campaign_id": campaign_id, "status": "completed",
            "origin_context": origin_context,
        }
    finally:
        conn.close()


# ── Codex discovery ──────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/codex")
def get_campaign_codex(campaign_id: str) -> dict[str, Any]:
    """Return unlocked codex entries for a campaign."""
    from backend.app.core.codex_discovery import get_unlocked_codex_entries

    conn = _get_conn()
    try:
        campaign = load_campaign(conn, campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        ws = campaign.get("world_state_json")
        if isinstance(ws, str):
            try:
                ws = json.loads(ws)
            except json.JSONDecodeError:
                ws = {}
        ws = ws if isinstance(ws, dict) else {}

        era_id = (campaign.get("time_period") or ws.get("era_id") or "").strip()
        era_pack = None
        total_available = 0
        if era_id:
            try:
                era_pack = CONTENT_REPOSITORY.get_pack(era_id)
                if era_pack:
                    total_available = len(era_pack.codex or [])
            except (FileNotFoundError, KeyError, TypeError, ValueError):
                logger.debug("Codex era pack lookup failed (non-fatal)", exc_info=True)

        unlocked = get_unlocked_codex_entries(ws, era_pack)

        return {
            "campaign_id": campaign_id, "unlocked": unlocked,
            "unlocked_count": len(unlocked), "total_available": total_available,
        }
    finally:
        conn.close()


# ── Campaign settings ────────────────────────────────────────────────

class CampaignSettings(BaseModel):
    narrator_mode: str = "concise"
    cloud_preset: str = "local"


class CampaignSettingsResponse(BaseModel):
    narrator_mode: str
    cloud_preset: str


@router.get("/campaigns/{campaign_id}/settings", response_model=CampaignSettingsResponse)
def get_campaign_settings(campaign_id: str):
    """Get campaign settings (narrator_mode, cloud_preset)."""
    conn = _get_conn()
    try:
        campaign = load_campaign(conn, campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        ws = campaign.get("world_state_json") or {}
        if isinstance(ws, str):
            ws = json.loads(ws)
        narrator_mode = ws.get("narrator_mode", "concise")
        cloud_preset = ws.get("cloud_preset", "local")
        from backend.app.constants import VALID_NARRATOR_MODES
        if narrator_mode not in VALID_NARRATOR_MODES:
            narrator_mode = "concise"
        from backend.app.config import VALID_CLOUD_PRESETS
        if cloud_preset not in VALID_CLOUD_PRESETS:
            cloud_preset = "local"
        return CampaignSettingsResponse(narrator_mode=narrator_mode, cloud_preset=cloud_preset)
    finally:
        conn.close()


@router.patch("/campaigns/{campaign_id}/settings", response_model=CampaignSettingsResponse)
def patch_campaign_settings(campaign_id: str, body: CampaignSettings):
    """Update campaign settings. Persists to world_state_json."""
    from backend.app.constants import VALID_NARRATOR_MODES
    from backend.app.config import VALID_CLOUD_PRESETS

    if body.narrator_mode not in VALID_NARRATOR_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid narrator_mode. Must be one of: {VALID_NARRATOR_MODES}",
        )
    if body.cloud_preset not in VALID_CLOUD_PRESETS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid cloud_preset. Must be one of: {VALID_CLOUD_PRESETS}",
        )

    conn = _get_conn()
    try:
        campaign = load_campaign(conn, campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        ws = campaign.get("world_state_json") or {}
        if isinstance(ws, str):
            ws = json.loads(ws)
        ws["narrator_mode"] = body.narrator_mode
        ws["cloud_preset"] = body.cloud_preset
        conn.execute(
            "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
            (json.dumps(ws), campaign_id),
        )
        conn.commit()
        return CampaignSettingsResponse(
            narrator_mode=body.narrator_mode,
            cloud_preset=body.cloud_preset,
        )
    finally:
        conn.close()
