"""App config: per-role model selection (Ollama-only), DB/table constants, env overrides.

Specialist swapping: only one local model loaded per agent call to avoid >12GB VRAM.
Per-role env overrides: STORYTELLER_{ROLE}_PROVIDER, STORYTELLER_{ROLE}_MODEL,
STORYTELLER_{ROLE}_BASE_URL (fallback: {ROLE}_*).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from shared.config import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    ERA_PACK_DIR,
    LORE_DATA_DIR,
    MANIFESTS_DIR,
    STYLE_DATA_DIR,
    ENABLE_CHARACTER_FACETS,
    _env_flag,
)

logger = logging.getLogger(__name__)


NPC_RENDER_MODEL = os.environ.get("NPC_RENDER_MODEL", "qwen3:8b").strip()


def _role_env(key: str, role: str, default: str = "") -> str:
    """Env override: STORYTELLER_{ROLE}_{KEY} first, then {ROLE}_{KEY} fallback."""
    role_upper = role.upper()
    val = os.environ.get(f"STORYTELLER_{role_upper}_{key}", "").strip()
    if not val:
        val = os.environ.get(f"{role_upper}_{key}", default).strip()
    return val or default


def _model_config() -> dict[str, dict[str, str]]:
    # Quality-first local defaults: ollama + Qwen 2.5 (14b for heavy roles, 7b for lighter)
    # Quality-critical roles use mistral-nemo (7GB); lightweight roles use qwen3:4b (~2GB).
    # Only one model loads at a time (specialist swapping), so peak VRAM = mistral-nemo at ~7GB.
    base: dict[str, dict[str, str]] = {
        "architect": {"provider": "ollama", "model": "qwen3:4b"},
        "director": {"provider": "ollama", "model": "mistral-nemo:latest"},
        "narrator": {"provider": "ollama", "model": "mistral-nemo:latest"},
        "casting": {"provider": "ollama", "model": "qwen3:4b"},
        "biographer": {"provider": "ollama", "model": "qwen3:4b"},
        "mechanic": {"provider": "ollama", "model": "qwen3:8b"},
        "ingestion_tagger": {"provider": "ollama", "model": "qwen3:8b"},
        "npc_render": {"provider": "ollama", "model": NPC_RENDER_MODEL},
        "kg_extractor": {"provider": "ollama", "model": "qwen3:4b"},
        "suggestion_refiner": {"provider": "ollama", "model": "qwen3:8b"},
        "embedding": {"provider": "ollama", "model": "nomic-embed-text"},
    }
    out = {}
    for role, cfg in base.items():
        c = dict(cfg)
        override_provider = _role_env("PROVIDER", role)
        if override_provider:
            c["provider"] = override_provider
        override_model = _role_env("MODEL", role)
        if override_model:
            c["model"] = override_model
        override_url = _role_env("BASE_URL", role)
        if override_url:
            c["base_url"] = override_url
        out[role] = c
    return out


MODEL_CONFIG = _model_config()

# Hardware profile presets: suggested model assignments by GPU tier.
# Only one model is loaded at a time (specialist swapping), so the
# constraint is *peak VRAM for the largest loaded model*.
#   qwen3:8b     ~5 GB  (fits all GPUs)
#   mistral-nemo ~7 GB  (fits 4070 12GB, 3080 10GB)
#   qwen2.5:14b  ~10 GB (fits 4070 12GB, tight on 3080 10GB)
HARDWARE_PROFILES: dict[str, dict[str, str]] = {
    "rtx_4070_12gb": {
        "narrator": "mistral-nemo:latest",
        "director": "mistral-nemo:latest",
        "architect": "qwen3:4b",
        "casting": "qwen3:4b",
        "biographer": "qwen3:4b",
        "ingestion_tagger": "qwen3:8b",
        "kg_extractor": "qwen3:4b",
        "suggestion_refiner": "qwen3:8b",
    },
    "rtx_3080_10gb": {
        "narrator": "qwen3:8b",
        "director": "qwen3:8b",
        "architect": "qwen3:4b",
        "casting": "qwen3:4b",
        "biographer": "qwen3:4b",
        "ingestion_tagger": "qwen3:8b",
        "kg_extractor": "qwen3:4b",
        "suggestion_refiner": "qwen3:8b",
    },
    "rtx_4090_24gb": {
        "narrator": "mistral-nemo:latest",
        "director": "mistral-nemo:latest",
        "architect": "mistral-nemo:latest",
        "casting": "qwen3:8b",
        "biographer": "qwen3:8b",
        "ingestion_tagger": "qwen3:8b",
        "kg_extractor": "qwen3:8b",
        "suggestion_refiner": "qwen3:8b",
    },
}


def _log_resolved_model_config() -> None:
    """Log resolved per-role model config at startup (no secrets)."""
    lines = ["LLM config (per role):"]
    for role, cfg in sorted(MODEL_CONFIG.items()):
        provider = cfg.get("provider", "")
        model = cfg.get("model", "")
        base_url = cfg.get("base_url", "")
        url_display = "custom" if base_url else "default"
        lines.append(f"  {role}: provider={provider} model={model} base_url={url_display}")
    logger.info("\n".join(lines))


_log_resolved_model_config()

# Data root directory (parent of static/, lore/, style/, etc.)
DATA_ROOT = Path(os.environ.get("STORYTELLER_DATA_ROOT", "./data"))

DEFAULT_DB_PATH = os.environ.get("STORYTELLER_DB_PATH", "./data/storyteller.db")
LORE_TABLE_NAME = os.environ.get("LORE_TABLE_NAME", "lore_chunks")
STYLE_TABLE_NAME = os.environ.get("STYLE_TABLE_NAME", "style_chunks")
CHARACTER_VOICE_TABLE_NAME = os.environ.get("CHARACTER_VOICE_TABLE_NAME", "character_voice_chunks")


def resolve_vectordb_path(db_path: str | Path | None = None) -> Path:
    """
    Resolve LanceDB path in a way that matches ingestion defaults.

    Precedence:
    1) explicit db_path argument
    2) VECTORDB_PATH env var
    3) prefer ./data/lancedb unless only legacy ./lancedb exists
    """
    if db_path:
        return Path(db_path)
    env_val = os.environ.get("VECTORDB_PATH", "").strip()
    if env_val:
        return Path(env_val)
    preferred = Path("./data/lancedb")
    legacy = Path("lancedb")
    if preferred.exists() or not legacy.exists():
        return preferred
    return legacy

# Feature flags (progressive rollout)
ENABLE_BIBLE_CASTING = _env_flag("ENABLE_BIBLE_CASTING", default=True)
ENABLE_PROCEDURAL_NPCS = _env_flag("ENABLE_PROCEDURAL_NPCS", default=True)
NPC_RENDER_ENABLED = _env_flag("NPC_RENDER_ENABLED", default=False)
ENABLE_SUGGESTION_REFINER = _env_flag("ENABLE_SUGGESTION_REFINER", default=True)

# World simulation (V2.5): tick interval in hours (default 4 = 240 min)
# Override via WORLD_TICK_INTERVAL_HOURS env. See backend.app.time_economy for action costs.
from backend.app.time_economy import WORLD_TICK_INTERVAL_HOURS

# Psychological profile defaults for characters (V2.5)
PSYCH_PROFILE_DEFAULTS: dict[str, str | int | None] = {
    "current_mood": "neutral",
    "stress_level": 0,
    "active_trauma": None,
}

# Token budgeting: per-role max context tokens and reserved output tokens
# Aligned to model sizes: 14b roles (architect/director/narrator) get larger budgets;
# 7b roles (casting/biographer/mechanic) get smaller. Override via env:
# STORYTELLER_{ROLE}_MAX_CONTEXT_TOKENS, STORYTELLER_{ROLE}_RESERVED_OUTPUT_TOKENS
# (fallback: {ROLE}_MAX_CONTEXT_TOKENS, {ROLE}_RESERVED_OUTPUT_TOKENS)
# Optional direct input override: STORYTELLER_{ROLE}_MAX_INPUT_TOKENS or {ROLE}_MAX_INPUT_TOKENS
_ROLE_TOKEN_BUDGETS: dict[str, dict[str, int]] = {
    # 14b models: larger context for narrative/director/architect work
    "architect": {"max_context_tokens": 8192, "reserved_output_tokens": 2048},
    "director": {"max_context_tokens": 8192, "reserved_output_tokens": 2048},
    "narrator": {"max_context_tokens": 8192, "reserved_output_tokens": 2048},
    # 7b models: lighter context for casting/biographer/mechanic
    "casting": {"max_context_tokens": 4096, "reserved_output_tokens": 1024},
    "biographer": {"max_context_tokens": 4096, "reserved_output_tokens": 1024},
    "mechanic": {"max_context_tokens": 4096, "reserved_output_tokens": 1024},
    "npc_render": {"max_context_tokens": 2048, "reserved_output_tokens": 512},
    # Ingestion tagger: moderate context, low output
    "ingestion_tagger": {"max_context_tokens": 4096, "reserved_output_tokens": 512},
    # Knowledge graph extractor: moderate context, moderate output
    "kg_extractor": {"max_context_tokens": 6144, "reserved_output_tokens": 2048},
    # Suggestion refiner: small context (prose + scene), small output (JSON array)
    "suggestion_refiner": {"max_context_tokens": 2048, "reserved_output_tokens": 512},
}


def _role_env_int(key: str, role: str) -> int | None:
    """Read int env: STORYTELLER_{ROLE}_{KEY} first, then {ROLE}_{KEY}. Returns None if unset/invalid."""
    role_upper = role.upper()
    for prefix in ("STORYTELLER_", ""):
        env_val = os.environ.get(f"{prefix}{role_upper}_{key}", "").strip()
        if env_val:
            try:
                return int(env_val)
            except ValueError:
                pass
    return None


def get_role_max_context_tokens(role: str) -> int:
    """Get max context tokens for a role (env override or default)."""
    env_val = _role_env_int("MAX_CONTEXT_TOKENS", role)
    if env_val is not None:
        return env_val
    budget = _ROLE_TOKEN_BUDGETS.get(role, {})
    return budget.get("max_context_tokens", 3000)


def get_role_reserved_output_tokens(role: str) -> int:
    """Get reserved output tokens for a role (env override or default)."""
    env_val = _role_env_int("RESERVED_OUTPUT_TOKENS", role)
    if env_val is not None:
        return env_val
    budget = _ROLE_TOKEN_BUDGETS.get(role, {})
    return budget.get("reserved_output_tokens", 1000)


def get_role_max_input_tokens(role: str) -> int:
    """Get max input tokens for a role (env override or derived from context - reserved)."""
    env_val = _role_env_int("MAX_INPUT_TOKENS", role)
    if env_val is not None:
        return env_val
    max_context = get_role_max_context_tokens(role)
    reserved = get_role_reserved_output_tokens(role)
    return max(0, max_context - reserved)


# Dev-only flag to include context stats in TurnResponse
DEV_CONTEXT_STATS = os.environ.get("DEV_CONTEXT_STATS", "").strip().lower() in ("1", "true", "yes")

# Convenience defaults (computed at import time). Prefer get_role_max_input_tokens in runtime code.
DIRECTOR_MAX_INPUT_TOKENS = get_role_max_input_tokens("director")
NARRATOR_MAX_INPUT_TOKENS = get_role_max_input_tokens("narrator")

# Ingestion tagger (local LLM) flag: optional, off by default.
INGESTION_TAGGER_ENABLED = os.environ.get("INGESTION_TAGGER_ENABLED", "").strip().lower() in ("1", "true", "yes")
