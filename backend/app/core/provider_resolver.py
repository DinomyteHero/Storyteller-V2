"""Unified provider resolution: picks the right provider+model for each agent role.

Resolution chain (highest priority wins):
1. Manual per-agent override  (campaign_settings["agent_overrides"][role])
2. Active preset              (system tier-based or custom user preset)
3. Env var override           (STORYTELLER_{ROLE}_PROVIDER from MODEL_CONFIG)
4. MODEL_CONFIG default       (Ollama)

V12.0: Cloud-agnostic provider system.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def resolve_agent_config(
    role: str,
    campaign_settings: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Resolve the final provider+model config for an agent role.

    Args:
        role: Agent role name (e.g., "narrator", "director").
        campaign_settings: Dict with keys: cloud_preset, custom_preset_id,
            preferred_provider, agent_overrides.
        conn: Optional DB connection for key/preset lookups.

    Returns:
        Dict with at least "provider" and "model" keys, plus "_source"
        indicating where the config came from.
    """
    from backend.app.config import MODEL_CONFIG

    # 1. Manual per-agent override (highest priority)
    overrides = campaign_settings.get("agent_overrides") or {}
    if role in overrides:
        override = dict(overrides[role])
        provider_id = override.get("provider", "")
        if provider_id and provider_id != "ollama":
            # Inject API key from registry
            from backend.app.core.provider_registry import resolve_api_key, get_provider
            key = resolve_api_key(provider_id, conn)
            if key:
                override["api_key"] = key
            provider_info = get_provider(provider_id)
            if provider_info and "base_url" not in override:
                override["base_url"] = provider_info["base_url"]
        override["_source"] = "override"
        return override

    # 2. Active preset
    cloud_preset = campaign_settings.get("cloud_preset")
    if cloud_preset and cloud_preset != "local":
        preset_config = _resolve_preset_for_role(role, campaign_settings, conn)
        if preset_config:
            preset_config["_source"] = "preset"
            return preset_config

    # 3 + 4. Env var + MODEL_CONFIG defaults (already merged in MODEL_CONFIG)
    if role in MODEL_CONFIG:
        default = dict(MODEL_CONFIG[role])
        default["_source"] = "default"
        return default

    # Unknown role: return empty with Ollama fallback
    return {"provider": "ollama", "model": "", "_source": "default"}


def _resolve_preset_for_role(
    role: str,
    campaign_settings: dict[str, Any],
    conn: sqlite3.Connection | None,
) -> dict[str, Any] | None:
    """Resolve a preset entry for a specific role."""
    cloud_preset = campaign_settings.get("cloud_preset", "local")

    if cloud_preset == "custom":
        return _resolve_custom_preset_for_role(role, campaign_settings, conn)
    else:
        return _resolve_system_preset_for_role(role, cloud_preset, campaign_settings, conn)


def _resolve_system_preset_for_role(
    role: str,
    preset_name: str,
    campaign_settings: dict[str, Any],
    conn: sqlite3.Connection | None,
) -> dict[str, Any] | None:
    """Resolve a system preset's tier to a concrete provider+model."""
    from backend.app.config import SYSTEM_PRESETS
    from backend.app.core.provider_registry import CLOUD_PROVIDERS

    preset = SYSTEM_PRESETS.get(preset_name)
    if not preset or role not in preset:
        return None

    role_spec = preset[role]
    tier = role_spec.get("tier", "quality")
    preferred = campaign_settings.get("preferred_provider")

    # Provider-specific presets (e.g. "deepseek"): auto-pin to that provider
    if not preferred and preset_name in CLOUD_PROVIDERS:
        preferred = preset_name

    return _resolve_tier(tier, preferred, conn)


def _resolve_custom_preset_for_role(
    role: str,
    campaign_settings: dict[str, Any],
    conn: sqlite3.Connection | None,
) -> dict[str, Any] | None:
    """Resolve a custom user preset for a specific role."""
    custom_id = campaign_settings.get("custom_preset_id")
    if not custom_id or not conn:
        return None

    try:
        row = conn.execute(
            "SELECT role_configs FROM user_presets WHERE id = ?",
            (custom_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None

    if not row:
        return None

    role_configs = json.loads(row["role_configs"] if isinstance(row, sqlite3.Row) else row[0])
    if role not in role_configs:
        return None

    cfg = dict(role_configs[role])
    provider_id = cfg.get("provider", "")

    if provider_id and provider_id != "ollama":
        from backend.app.core.provider_registry import resolve_api_key, get_provider
        key = resolve_api_key(provider_id, conn)
        if key:
            cfg["api_key"] = key
        provider_info = get_provider(provider_id)
        if provider_info and "base_url" not in cfg:
            cfg["base_url"] = provider_info["base_url"]

    return cfg


def _resolve_tier(
    tier: str,
    preferred_provider: str | None,
    conn: sqlite3.Connection | None,
) -> dict[str, Any] | None:
    """Given a quality tier, find the best available provider+model.

    Checks preferred_provider first, then iterates providers in priority order.
    """
    from backend.app.core.provider_registry import (
        PROVIDER_PRIORITY,
        get_available_providers,
        get_best_model_for_tier,
        get_provider,
        resolve_api_key,
    )

    available = get_available_providers(conn)
    if not available:
        return None

    # Try preferred provider first
    if preferred_provider and preferred_provider in available:
        result = _try_provider_for_tier(preferred_provider, tier, conn)
        if result:
            return result

    # Iterate in priority order
    for provider_id in PROVIDER_PRIORITY:
        if provider_id not in available:
            continue
        if provider_id == preferred_provider:
            continue  # Already tried
        result = _try_provider_for_tier(provider_id, tier, conn)
        if result:
            return result

    return None


def _try_provider_for_tier(
    provider_id: str,
    tier: str,
    conn: sqlite3.Connection | None,
) -> dict[str, Any] | None:
    """Try to build a config dict for a provider at a given tier."""
    from backend.app.core.provider_registry import (
        get_best_model_for_tier,
        get_provider,
        resolve_api_key,
    )

    model = get_best_model_for_tier(provider_id, tier)
    if not model:
        return None

    provider_info = get_provider(provider_id)
    if not provider_info:
        return None

    key = resolve_api_key(provider_id, conn)
    if not key:
        return None

    return {
        "provider": provider_id,
        "model": model,
        "base_url": provider_info["base_url"],
        "api_key": key,
    }


# ---------------------------------------------------------------------------
# High-level helper for pipeline nodes
# ---------------------------------------------------------------------------


def make_agent_llm(
    role: str,
    campaign_settings: dict[str, Any],
    conn: sqlite3.Connection | None = None,
):
    """Create an AgentLLM with the full resolution chain applied.

    This is the primary entry point for pipeline nodes to get a
    correctly-configured LLM client for any agent role.
    """
    from backend.app.core.agents.base import AgentLLM

    config = resolve_agent_config(role, campaign_settings, conn)
    # Strip internal metadata before passing to AgentLLM
    config_for_llm = {k: v for k, v in config.items() if not k.startswith("_")}

    # Only pass override if it differs from defaults (source != "default")
    source = config.get("_source", "default")
    if source == "default":
        return AgentLLM(role)
    return AgentLLM(role, config_override=config_for_llm)
