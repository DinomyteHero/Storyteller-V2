"""Settings API: provider key management, user presets, resolved config.

V12.0: Cloud-agnostic provider system — manage API keys, create custom presets,
and view resolved per-agent configuration.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.config import DEFAULT_DB_PATH
from backend.app.core.provider_registry import (
    CLOUD_PROVIDERS,
    get_all_provider_statuses,
    get_provider,
    get_provider_status,
    mask_key,
    resolve_api_key,
)
from backend.app.db.connection import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/settings", tags=["settings"])


def _get_conn():
    return get_connection(DEFAULT_DB_PATH)


# ---------------------------------------------------------------------------
# Provider key management
# ---------------------------------------------------------------------------


class SetKeyRequest(BaseModel):
    api_key: str


class TestResult(BaseModel):
    ok: bool
    latency_ms: int = 0
    error: str | None = None
    model_used: str | None = None


@router.get("/providers")
def list_providers() -> list[dict[str, Any]]:
    """List all cloud providers with key status and available models."""
    conn = _get_conn()
    try:
        return get_all_provider_statuses(conn)
    finally:
        conn.close()


@router.put("/providers/{provider_id}/key")
def set_provider_key(provider_id: str, body: SetKeyRequest) -> dict[str, Any]:
    """Set or update an API key for a cloud provider."""
    if provider_id not in CLOUD_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")
    if not body.api_key.strip():
        raise HTTPException(status_code=422, detail="API key cannot be empty")

    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO provider_keys (provider_id, api_key, created_at, updated_at)
               VALUES (?, ?, datetime('now'), datetime('now'))
               ON CONFLICT(provider_id) DO UPDATE SET
                 api_key = excluded.api_key,
                 updated_at = datetime('now')""",
            # KNOWN LIMITATION (v1.0): API keys stored in plaintext in SQLite.
            # Encryption at rest planned for v1.1.
            (provider_id, body.api_key.strip()),
        )
        conn.commit()
        logger.info("API key set for provider %s", provider_id)
        return get_provider_status(provider_id, conn)
    finally:
        conn.close()


@router.delete("/providers/{provider_id}/key")
def remove_provider_key(provider_id: str) -> dict[str, Any]:
    """Remove an API key from the database. Env var fallback still works."""
    if provider_id not in CLOUD_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")

    conn = _get_conn()
    try:
        conn.execute("DELETE FROM provider_keys WHERE provider_id = ?", (provider_id,))
        conn.commit()
        logger.info("API key removed for provider %s", provider_id)
        return get_provider_status(provider_id, conn)
    finally:
        conn.close()


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: str) -> TestResult:
    """Test connectivity to a cloud provider by making a minimal API call."""
    if provider_id not in CLOUD_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")

    conn = _get_conn()
    try:
        api_key = resolve_api_key(provider_id, conn)
    finally:
        conn.close()

    if not api_key:
        return TestResult(ok=False, error="No API key configured for this provider")

    provider = CLOUD_PROVIDERS[provider_id]
    # Pick the fastest/cheapest model for the test
    test_model = None
    for model_id, meta in provider["models"].items():
        if meta["tier"] == "fast":
            test_model = model_id
            break
    if not test_model:
        if not provider["models"]:
            return TestResult(ok=False, error=f"Provider {provider_id} has no models configured")
        test_model = next(iter(provider["models"]))

    from backend.app.core.llm_provider import create_provider

    start = time.perf_counter()
    try:
        client = create_provider(
            provider=provider_id,
            model=test_model,
            base_url=provider["base_url"],
            api_key=api_key,
            timeout=30.0,
        )
        result = client.complete("Say 'hello' in one word.", system_prompt="You are a test assistant.")
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        if result and len(result.strip()) > 0:
            return TestResult(ok=True, latency_ms=elapsed_ms, model_used=test_model)
        return TestResult(ok=False, error="Empty response from provider", model_used=test_model)
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.warning("Provider test failed for %s: %s", provider_id, e)
        return TestResult(ok=False, latency_ms=elapsed_ms, error=str(e)[:500], model_used=test_model)


# ---------------------------------------------------------------------------
# User presets CRUD
# ---------------------------------------------------------------------------


class CreatePresetRequest(BaseModel):
    name: str
    description: str = ""
    role_configs: dict[str, dict[str, str]]  # {"narrator": {"provider": "openai", "model": "gpt-4o"}}


class UpdatePresetRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    role_configs: dict[str, dict[str, str]] | None = None


def _validate_role_configs(role_configs: dict[str, dict[str, str]]) -> None:
    """Validate that all provider+model combos in role_configs are valid."""
    from backend.app.config import MODEL_CONFIG

    for role, cfg in role_configs.items():
        if role not in MODEL_CONFIG and role != "ollama":
            raise HTTPException(status_code=422, detail=f"Unknown agent role: {role}")
        provider_id = cfg.get("provider", "")
        model = cfg.get("model", "")
        if provider_id == "ollama":
            continue  # Local models are not validated against registry
        if provider_id not in CLOUD_PROVIDERS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown provider '{provider_id}' for role '{role}'. "
                f"Valid: ollama, {', '.join(CLOUD_PROVIDERS.keys())}",
            )
        provider = CLOUD_PROVIDERS[provider_id]
        if model and model not in provider["models"]:
            valid_models = list(provider["models"].keys())
            raise HTTPException(
                status_code=422,
                detail=f"Unknown model '{model}' for provider '{provider_id}'. Valid: {valid_models}",
            )


def _preset_row_to_dict(row) -> dict[str, Any]:
    """Convert a DB row to a preset response dict."""
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "role_configs": json.loads(row["role_configs"]),
        "is_system": False,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _system_presets_as_dicts() -> list[dict[str, Any]]:
    """Return system presets formatted as response dicts."""
    from backend.app.config import SYSTEM_PRESETS

    result = []
    for preset_id, roles in SYSTEM_PRESETS.items():
        result.append({
            "id": preset_id,
            "name": {"cloud_all": "Cloud All"}.get(preset_id, preset_id.capitalize()),
            "description": {
                "budget": "Narrator on cloud (~$0.01/turn)",
                "balanced": "Core roles on cloud (~$0.02/turn)",
                "quality": "All narrative roles on cloud (~$0.05/turn)",
                "cloud_all": "All roles on cloud — no Ollama required (~$0.08/turn)",
            }.get(preset_id, ""),
            "role_configs": roles,
            "is_system": True,
            "created_at": None,
            "updated_at": None,
        })
    return result


@router.get("/presets")
def list_presets() -> list[dict[str, Any]]:
    """List system presets and user-created presets."""
    system = _system_presets_as_dicts()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, description, role_configs, created_at, updated_at FROM user_presets ORDER BY name"
        ).fetchall()
        user = [_preset_row_to_dict(row) for row in rows]
    except Exception:
        user = []
    finally:
        conn.close()
    return system + user


@router.post("/presets")
def create_preset(body: CreatePresetRequest) -> dict[str, Any]:
    """Create a custom user preset."""
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Preset name cannot be empty")
    _validate_role_configs(body.role_configs)

    preset_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO user_presets (id, name, description, role_configs, created_at, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (preset_id, body.name.strip(), body.description, json.dumps(body.role_configs)),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM user_presets WHERE id = ?", (preset_id,)).fetchone()
        return _preset_row_to_dict(row)
    except Exception as e:
        conn.rollback()
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=409, detail=f"Preset name '{body.name}' already exists")
        raise
    finally:
        conn.close()


@router.put("/presets/{preset_id}")
def update_preset(preset_id: str, body: UpdatePresetRequest) -> dict[str, Any]:
    """Update a user preset. Cannot modify system presets."""
    from backend.app.config import SYSTEM_PRESETS

    if preset_id in SYSTEM_PRESETS:
        raise HTTPException(status_code=403, detail="Cannot modify system presets")

    conn = _get_conn()
    try:
        existing = conn.execute("SELECT * FROM user_presets WHERE id = ?", (preset_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Preset not found")

        updates = []
        params = []
        if body.name is not None:
            updates.append("name = ?")
            params.append(body.name.strip())
        if body.description is not None:
            updates.append("description = ?")
            params.append(body.description)
        if body.role_configs is not None:
            _validate_role_configs(body.role_configs)
            updates.append("role_configs = ?")
            params.append(json.dumps(body.role_configs))

        if updates:
            updates.append("updated_at = datetime('now')")
            params.append(preset_id)
            conn.execute(
                f"UPDATE user_presets SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()

        row = conn.execute("SELECT * FROM user_presets WHERE id = ?", (preset_id,)).fetchone()
        return _preset_row_to_dict(row)
    finally:
        conn.close()


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: str) -> dict[str, str]:
    """Delete a user preset. Clears references from any campaigns using it."""
    from backend.app.config import SYSTEM_PRESETS

    if preset_id in SYSTEM_PRESETS:
        raise HTTPException(status_code=403, detail="Cannot delete system presets")

    conn = _get_conn()
    try:
        existing = conn.execute("SELECT * FROM user_presets WHERE id = ?", (preset_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Preset not found")

        # Clear references from campaigns using this preset
        rows = conn.execute("SELECT id, world_state_json FROM campaigns").fetchall()
        for row in rows:
            ws = json.loads(row["world_state_json"]) if row["world_state_json"] else {}
            if ws.get("custom_preset_id") == preset_id:
                ws["cloud_preset"] = "local"
                ws["custom_preset_id"] = None
                conn.execute(
                    "UPDATE campaigns SET world_state_json = ? WHERE id = ?",
                    (json.dumps(ws), row["id"]),
                )

        conn.execute("DELETE FROM user_presets WHERE id = ?", (preset_id,))
        conn.commit()
        return {"status": "deleted", "id": preset_id}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Resolved config per campaign
# ---------------------------------------------------------------------------


@router.get("/campaigns/{campaign_id}/resolved_config")
def get_resolved_config(campaign_id: str) -> dict[str, Any]:
    """Return the fully resolved provider+model config for every agent role in a campaign."""
    from backend.app.config import MODEL_CONFIG
    from backend.app.core.provider_resolver import resolve_agent_config

    conn = _get_conn()
    try:
        from backend.app.core.state_loader import load_campaign

        campaign = load_campaign(conn, campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaign not found")

        ws = campaign.get("world_state_json") or {}
        if isinstance(ws, str):
            ws = json.loads(ws)

        campaign_settings = {
            "cloud_preset": ws.get("cloud_preset", "local"),
            "custom_preset_id": ws.get("custom_preset_id"),
            "preferred_provider": ws.get("preferred_provider"),
            "agent_overrides": ws.get("agent_overrides"),
        }

        roles = {}
        for role in MODEL_CONFIG:
            resolved = resolve_agent_config(role, campaign_settings, conn)
            roles[role] = {
                "provider": resolved.get("provider", "ollama"),
                "model": resolved.get("model", ""),
                "source": resolved.get("_source", "default"),
            }

        return {"campaign_id": campaign_id, "roles": roles}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# App preferences (synced from frontend settings UI)
# ---------------------------------------------------------------------------

_PREFERENCE_DEFAULTS: dict[str, str] = {
    "enable_choice_fallbacks": "true",
}


class PreferencesRequest(BaseModel):
    preferences: dict[str, str]


@router.get("/preferences")
def get_preferences() -> dict[str, Any]:
    """Return all app preferences with defaults applied."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM app_preferences").fetchall()
        prefs = {row["key"]: row["value"] for row in rows}
    except Exception:
        prefs = {}
    finally:
        conn.close()
    # Apply defaults for known preferences
    for key, default in _PREFERENCE_DEFAULTS.items():
        prefs.setdefault(key, default)
    return {"preferences": prefs}


@router.put("/preferences")
def update_preferences(body: PreferencesRequest) -> dict[str, Any]:
    """Upsert one or more app preferences."""
    conn = _get_conn()
    try:
        for key, value in body.preferences.items():
            conn.execute(
                """INSERT INTO app_preferences (key, value, updated_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(key) DO UPDATE SET
                     value = excluded.value,
                     updated_at = datetime('now')""",
                (key, value),
            )
        conn.commit()
        rows = conn.execute("SELECT key, value FROM app_preferences").fetchall()
        prefs = {row["key"]: row["value"] for row in rows}
    except Exception:
        prefs = {}
    finally:
        conn.close()
    for key, default in _PREFERENCE_DEFAULTS.items():
        prefs.setdefault(key, default)
    return {"preferences": prefs}
