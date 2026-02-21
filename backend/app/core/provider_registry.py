"""Cloud provider registry: single source of truth for all supported LLM providers.

Defines provider metadata, model catalogs, and key resolution helpers.
Used by the provider resolver, settings API, and frontend to enumerate
available providers and their capabilities.

V12.0: Cloud-agnostic provider system — Anthropic, OpenAI, xAI, DeepSeek, Google.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider + Model Registry
# ---------------------------------------------------------------------------

CLOUD_PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {
        "label": "Claude (Anthropic)",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "client_type": "anthropic",
        "models": {
            "claude-sonnet-4-5-20250929": {"label": "Claude Sonnet 4.5", "tier": "quality"},
            "claude-haiku-4-5-20251001": {"label": "Claude Haiku 4.5", "tier": "fast"},
            "claude-opus-4-6": {"label": "Claude Opus 4.6", "tier": "premium"},
        },
    },
    "openai": {
        "label": "ChatGPT (OpenAI)",
        "base_url": "https://api.openai.com",
        "api_key_env": "OPENAI_API_KEY",
        "client_type": "openai_compat",
        "models": {
            "gpt-4o": {"label": "GPT-4o", "tier": "quality"},
            "gpt-4o-mini": {"label": "GPT-4o Mini", "tier": "fast"},
            "gpt-4.1": {"label": "GPT-4.1", "tier": "premium"},
        },
    },
    "xai": {
        "label": "Grok (xAI)",
        "base_url": "https://api.x.ai",
        "api_key_env": "XAI_API_KEY",
        "client_type": "openai_compat",
        "models": {
            "grok-3": {"label": "Grok 3", "tier": "quality"},
            "grok-3-mini": {"label": "Grok 3 Mini", "tier": "fast"},
        },
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "client_type": "openai_compat",
        "models": {
            "deepseek-chat": {"label": "DeepSeek V3", "tier": "quality"},
            "deepseek-reasoner": {"label": "DeepSeek R1", "tier": "premium"},
        },
    },
    "google": {
        "label": "Gemini (Google)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GOOGLE_API_KEY",
        "client_type": "openai_compat",
        "models": {
            "gemini-2.5-flash": {"label": "Gemini 2.5 Flash", "tier": "quality"},
            "gemini-2.5-pro": {"label": "Gemini 2.5 Pro", "tier": "premium"},
            "gemini-2.0-flash-lite": {"label": "Gemini 2.0 Flash Lite", "tier": "fast"},
        },
    },
}

# Default preference order when multiple providers have keys.
# Users can override via preferred_provider setting.
PROVIDER_PRIORITY: list[str] = ["anthropic", "openai", "xai", "deepseek", "google"]

# Tier priority for model selection within a provider.
TIER_PRIORITY: dict[str, list[str]] = {
    "fast": ["fast", "quality", "premium"],
    "quality": ["quality", "premium", "fast"],
    "premium": ["premium", "quality", "fast"],
}

# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def get_provider(provider_id: str) -> dict[str, Any] | None:
    """Return provider metadata or None if not in registry."""
    return CLOUD_PROVIDERS.get(provider_id)


def get_all_providers() -> dict[str, dict[str, Any]]:
    """Return the full provider registry."""
    return dict(CLOUD_PROVIDERS)


def get_models_for_provider(provider_id: str) -> list[dict[str, str]]:
    """Return list of models for a provider: [{"id": ..., "label": ..., "tier": ...}]."""
    provider = CLOUD_PROVIDERS.get(provider_id)
    if not provider:
        return []
    return [
        {"id": model_id, "label": meta["label"], "tier": meta["tier"]}
        for model_id, meta in provider["models"].items()
    ]


def get_best_model_for_tier(provider_id: str, tier: str) -> str | None:
    """Return the best model ID for a given tier from a provider.

    Tries the requested tier first, then falls back through tier priority.
    Returns None if the provider has no models or doesn't exist.
    """
    provider = CLOUD_PROVIDERS.get(provider_id)
    if not provider:
        return None
    models = provider["models"]
    for try_tier in TIER_PRIORITY.get(tier, [tier]):
        for model_id, meta in models.items():
            if meta["tier"] == try_tier:
                return model_id
    # Last resort: return first model
    if models:
        return next(iter(models))
    return None


# ---------------------------------------------------------------------------
# API key resolution (DB → env var)
# ---------------------------------------------------------------------------


def _get_db_key(provider_id: str, conn: sqlite3.Connection | None) -> str | None:
    """Look up API key from provider_keys table. Returns None if missing or table doesn't exist."""
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT api_key FROM provider_keys WHERE provider_id = ?",
            (provider_id,),
        ).fetchone()
        if row:
            return row["api_key"] if isinstance(row, sqlite3.Row) else row[0]
    except sqlite3.OperationalError:
        # Table doesn't exist yet (pre-migration)
        pass
    return None


def _get_env_key(provider_id: str) -> str | None:
    """Look up API key from environment variable."""
    provider = CLOUD_PROVIDERS.get(provider_id)
    if not provider:
        return None
    env_var = provider["api_key_env"]
    val = os.environ.get(env_var, "").strip()
    return val or None


def resolve_api_key(provider_id: str, conn: sqlite3.Connection | None = None) -> str | None:
    """Resolve API key for a provider. Checks DB first, then env var.

    Returns None if no key is available from either source.
    """
    # 1. Check DB (user-entered via UI)
    db_key = _get_db_key(provider_id, conn)
    if db_key:
        return db_key
    # 2. Fall back to env var
    return _get_env_key(provider_id)


def get_key_source(provider_id: str, conn: sqlite3.Connection | None = None) -> str | None:
    """Return where the key comes from: 'db', 'env', or None."""
    if _get_db_key(provider_id, conn):
        return "db"
    if _get_env_key(provider_id):
        return "env"
    return None


def mask_key(key: str) -> str:
    """Mask an API key for display: show first 4 and last 4 chars."""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


# ---------------------------------------------------------------------------
# Provider availability
# ---------------------------------------------------------------------------


def get_available_providers(conn: sqlite3.Connection | None = None) -> list[str]:
    """Return provider_ids that have an API key (from DB or env)."""
    available = []
    for provider_id in CLOUD_PROVIDERS:
        if resolve_api_key(provider_id, conn):
            available.append(provider_id)
    return available


def get_provider_status(provider_id: str, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Return status dict for a single provider (for API responses)."""
    provider = CLOUD_PROVIDERS.get(provider_id)
    if not provider:
        return {"provider_id": provider_id, "error": "Unknown provider"}
    key = resolve_api_key(provider_id, conn)
    source = get_key_source(provider_id, conn)
    return {
        "provider_id": provider_id,
        "label": provider["label"],
        "has_key": key is not None,
        "key_source": source,
        "key_preview": mask_key(key) if key else "",
        "models": get_models_for_provider(provider_id),
    }


def get_all_provider_statuses(conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Return status dicts for all registered providers."""
    return [get_provider_status(pid, conn) for pid in CLOUD_PROVIDERS]
