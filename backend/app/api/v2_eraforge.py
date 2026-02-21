"""EraForge API: LLM-powered era pack auto-generator.

Three-phase flow:
1. POST /v2/eraforge/suggest — propose time periods for a setting
2. POST /v2/eraforge/generate — generate full era pack → stored in DB
3. POST /v2/eraforge/refine-canon — adjust canon character proximity after background selection
4. GET  /v2/eraforge/packs — list all generated packs
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
import sqlite3

from backend.app.api.eraforge_models import (
    EraForgeGenerateRequest,
    EraForgeGenerateResponse,
    EraForgeRefineCanonRequest,
    EraForgeRefineCanonResponse,
    EraForgeSuggestRequest,
    EraForgeSuggestResponse,
)
from backend.app.content.repository import CONTENT_REPOSITORY
from backend.app.core.agents.base import AgentLLM
from backend.app.core.agents.era_forge_agent import EraForgeAgent
from backend.app.db.connection import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/eraforge", tags=["eraforge"])


def _get_agent() -> EraForgeAgent:
    """Create an EraForgeAgent with the configured LLM."""
    try:
        llm = AgentLLM("era_forge")
    except (ConnectionError, TimeoutError, OSError, RuntimeError):
        logger.warning("EraForge LLM init failed; agent will use fallback mode.")
        llm = None
    return EraForgeAgent(llm=llm)


# ---------------------------------------------------------------------------
# Phase 1: Period Discovery
# ---------------------------------------------------------------------------


@router.post("/suggest", response_model=EraForgeSuggestResponse)
def suggest_periods(body: EraForgeSuggestRequest) -> EraForgeSuggestResponse:
    """Propose 3-5 time periods for a user-described setting."""
    agent = _get_agent()
    result = agent.suggest_periods(body.setting_prompt)
    return EraForgeSuggestResponse(**result)


# ---------------------------------------------------------------------------
# Phase 2: Pack Generation
# ---------------------------------------------------------------------------


@router.post("/generate", response_model=EraForgeGenerateResponse)
def generate_pack(
    body: EraForgeGenerateRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> EraForgeGenerateResponse:
    """Generate a full era pack and store it in the DB."""
    agent = _get_agent()
    pack_data = agent.generate_pack(
        setting_id=body.setting_id,
        setting_name=body.setting_name,
        setting_genre=body.setting_genre,
        period_id=body.period_id,
        display_name=body.display_name,
        time_period=body.time_period,
        summary=body.summary,
        tone=body.tone,
        key_conflicts=body.key_conflicts,
        source_prompt=body.source_prompt,
    )

    # Determine next version number for this (setting_id, period_id)
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) AS max_ver FROM generated_era_packs "
        "WHERE setting_id = ? AND period_id = ?",
        (body.setting_id, body.period_id),
    ).fetchone()
    next_version = (row["max_ver"] if row else 0) + 1

    # Insert into DB
    cursor = conn.execute(
        "INSERT INTO generated_era_packs "
        "(setting_id, period_id, display_name, summary, era_pack_json, source_prompt, version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            body.setting_id,
            body.period_id,
            body.display_name,
            body.summary,
            json.dumps(pack_data, ensure_ascii=False),
            body.source_prompt,
            next_version,
        ),
    )
    conn.commit()
    pack_id = cursor.lastrowid

    # Clear content cache so the new pack is discoverable
    CONTENT_REPOSITORY.clear_cache()

    backgrounds = pack_data.get("backgrounds") or []
    species = pack_data.get("species") or []
    canon_chars = pack_data.get("canon_characters") or []

    return EraForgeGenerateResponse(
        setting_id=body.setting_id,
        period_id=body.period_id,
        display_name=body.display_name,
        version=next_version,
        pack_id=pack_id,
        backgrounds_count=len(backgrounds),
        species_count=len(species),
        canon_characters_count=len(canon_chars),
    )


# ---------------------------------------------------------------------------
# Phase 3: Canon Character Refinement
# ---------------------------------------------------------------------------


@router.post("/refine-canon", response_model=EraForgeRefineCanonResponse)
def refine_canon(
    body: EraForgeRefineCanonRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> EraForgeRefineCanonResponse:
    """Adjust canon character proximity based on the player's chosen background."""
    # Load pack from DB
    row = conn.execute(
        "SELECT era_pack_json FROM generated_era_packs WHERE id = ?",
        (body.pack_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Generated pack {body.pack_id} not found")

    try:
        pack_data = json.loads(row["era_pack_json"])
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Failed to parse stored pack JSON")

    canon_chars = pack_data.get("canon_characters") or []
    if not canon_chars:
        return EraForgeRefineCanonResponse(
            pack_id=body.pack_id,
            canon_characters_count=0,
            adjustments_made=0,
        )

    # Build before-state for comparison
    before_proximity = {cc.get("name"): cc.get("proximity") for cc in canon_chars}

    # Refine via agent
    agent = _get_agent()
    refined = agent.refine_canon_characters(
        canon_chars,
        background_id=body.background_id,
        background_name=body.background_name,
        background_description=body.background_description,
        location_hints=body.location_hints,
        faction_hints=body.faction_hints,
    )

    # Count proximity adjustments
    adjustments = 0
    for cc in refined:
        name = cc.get("name")
        new_prox = cc.get("proximity")
        if name in before_proximity and before_proximity[name] != new_prox:
            adjustments += 1

    # Update pack JSON in DB
    pack_data["canon_characters"] = refined
    conn.execute(
        "UPDATE generated_era_packs SET era_pack_json = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(pack_data, ensure_ascii=False), body.pack_id),
    )
    conn.commit()

    # Clear content cache
    CONTENT_REPOSITORY.clear_cache()

    return EraForgeRefineCanonResponse(
        pack_id=body.pack_id,
        canon_characters_count=len(refined),
        adjustments_made=adjustments,
    )


# ---------------------------------------------------------------------------
# List generated packs
# ---------------------------------------------------------------------------


@router.get("/packs")
def list_generated_packs(
    conn: sqlite3.Connection = Depends(get_db),
) -> list[dict]:
    """List all generated era packs."""
    rows = conn.execute(
        "SELECT id, setting_id, period_id, display_name, summary, version, "
        "source_prompt, created_at, updated_at "
        "FROM generated_era_packs ORDER BY setting_id, period_id, version DESC",
    ).fetchall()
    return [
        {
            "id": row["id"],
            "setting_id": row["setting_id"],
            "period_id": row["period_id"],
            "display_name": row["display_name"],
            "summary": row["summary"],
            "version": row["version"],
            "source_prompt": row["source_prompt"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
