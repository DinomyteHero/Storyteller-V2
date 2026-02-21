"""V2 content catalog and era pack endpoints."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.content.repository import CONTENT_REPOSITORY
from backend.app.api.campaign_setup import _catalog_items, _resolve_requested_period

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2", tags=["v2-content"])


# ── Content catalog ──────────────────────────────────────────────────

@router.get("/content/catalog")
def get_content_catalog() -> dict[str, Any]:
    """Return discovered setting/period catalog for dynamic frontend selectors."""
    return {"items": _catalog_items()}


@router.get("/content/default")
def get_content_default() -> dict[str, Any]:
    setting_id, period_id, legacy_era_id = _resolve_requested_period(
        setting_id=None, period_id=None, time_period=None,
    )
    return {"setting_id": setting_id, "period_id": period_id, "legacy_era_id": legacy_era_id}


@router.get("/content/{setting_id}/{period_id}/summary")
def get_content_summary(setting_id: str, period_id: str) -> dict[str, Any]:
    s, p, legacy = _resolve_requested_period(
        setting_id=setting_id, period_id=period_id, time_period=None,
    )
    pack = CONTENT_REPOSITORY.get_content(s, p)
    playable = bool(pack.locations) and bool(pack.backgrounds)
    return {
        "setting_id": s,
        "period_id": p,
        "legacy_era_id": legacy,
        "backgrounds_count": len(pack.backgrounds or []),
        "locations_count": len(pack.locations or []),
        "companions_count": len(pack.companions or []),
        "quests_count": len(pack.quests or []),
        "playable": playable,
    }


# ── Era pack data ────────────────────────────────────────────────────

@router.get("/era/{era_id}/locations")
def get_era_locations(era_id: str) -> dict[str, Any]:
    """Return known locations for an era pack (for UI starting-area selection)."""
    try:
        pack = CONTENT_REPOSITORY.get_pack(era_id) if era_id else None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Era pack not found")
    if not pack:
        raise HTTPException(status_code=404, detail="Era pack not found")
    return {
        "era_id": pack.era_id,
        "locations": [loc.model_dump(mode="json") for loc in (pack.locations or [])],
    }


@router.get("/era/{era_id}/species")
def get_era_species(era_id: str) -> dict[str, Any]:
    """Return playable species for the given era."""
    try:
        pack = CONTENT_REPOSITORY.get_pack(era_id) if era_id else None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Era pack not found")
    if not pack:
        raise HTTPException(status_code=404, detail="Era pack not found")
    return {
        "era_id": pack.era_id,
        "species": [s.model_dump(mode="json") for s in (pack.species or [])],
    }


@router.get("/era/{era_id}/backgrounds")
def get_era_backgrounds(era_id: str) -> dict[str, Any]:
    """Return available backgrounds and their question chains for the given era."""
    logger.info(f"Received request for era backgrounds: era_id={era_id}")
    try:
        pack = CONTENT_REPOSITORY.get_pack(era_id) if era_id else None
    except FileNotFoundError:
        logger.error(f"Era pack not found for era_id={era_id}")
        raise HTTPException(status_code=404, detail="Era pack not found")
    if not pack:
        logger.error(f"Era pack not found for era_id={era_id}")
        raise HTTPException(status_code=404, detail="Era pack not found")
    logger.info(f"Loaded era pack {pack.era_id} with {len(pack.backgrounds or [])} backgrounds")
    return {
        "era_id": pack.era_id,
        "backgrounds": [bg.model_dump(mode="json") for bg in (pack.backgrounds or [])],
    }


@router.get("/era/{era_id}/companions")
def get_era_companions(era_id: str) -> dict[str, Any]:
    """Return companion previews for character creation screen."""
    from backend.app.core.companions import load_companions

    companions = load_companions(era=era_id)
    previews = []
    for c in companions[:5]:
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
def debug_era_packs() -> dict[str, Any]:
    """Debug endpoint showing loaded era packs and their backgrounds count."""
    from shared.config import ERA_PACK_DIR
    from pathlib import Path

    pack_dir = Path(ERA_PACK_DIR)
    try:
        packs = CONTENT_REPOSITORY.load_all_packs()
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
            ],
        }
    except Exception as e:  # Intentional broad catch: debug endpoint surfaces all errors
        logger.exception("Failed to load era packs for debug endpoint")
        return {
            "pack_dir": str(pack_dir),
            "pack_dir_exists": pack_dir.exists(),
            "error": str(e),
            "error_type": type(e).__name__,
        }


# ── Model config (per-agent LLM configuration) ──────────────────────

class AgentModelConfig(BaseModel):
    role: str
    provider: str
    model: str
    base_url: str = ""


class ModelConfigResponse(BaseModel):
    agents: list[AgentModelConfig]


@router.get("/model_config")
async def get_model_config():
    """Return the current per-agent model configuration and available cloud providers."""
    from backend.app.config import MODEL_CONFIG

    agents = []
    for role, cfg in sorted(MODEL_CONFIG.items()):
        agents.append(AgentModelConfig(
            role=role,
            provider=cfg.get("provider", "ollama"),
            model=cfg.get("model", ""),
            base_url=cfg.get("base_url", ""),
        ))

    # V12.0: Include provider registry and available providers
    available_providers: list[dict] = []
    try:
        from backend.app.core.provider_registry import get_all_provider_statuses
        from backend.app.config import DEFAULT_DB_PATH
        from backend.app.db.connection import get_connection
        conn = get_connection(DEFAULT_DB_PATH)
        try:
            available_providers = get_all_provider_statuses(conn)
        finally:
            conn.close()
    except Exception:
        pass

    return {
        "agents": [a.model_dump() for a in agents],
        "available_providers": available_providers,
    }
