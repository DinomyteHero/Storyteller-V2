"""App config: per-role model selection, cloud presets, DB/table constants, env overrides.

Specialist swapping: only one local model loaded per agent call to avoid >12GB VRAM.
Cloud routing: quality-critical roles can be routed to any supported cloud provider
(Anthropic, OpenAI, xAI, DeepSeek, Google) via STORYTELLER_{ROLE}_PROVIDER env vars.
Per-role env overrides: STORYTELLER_{ROLE}_PROVIDER, STORYTELLER_{ROLE}_MODEL,
STORYTELLER_{ROLE}_BASE_URL (fallback: {ROLE}_*).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from shared.config import (
    _env_flag,
    EMBEDDING_MODEL,  # noqa: F401
    EMBEDDING_DIMENSION,  # noqa: F401
    ERA_PACK_DIR,  # noqa: F401
)

from backend.app.time_economy import WORLD_TICK_INTERVAL_HOURS  # noqa: F401
from shared.ingest_paths import lancedb_dir

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
        # V5.0: Choice Crafter — authoritative LLM choice generation (replaces suggestion_engine)
        # Override to cloud for quality: STORYTELLER_CHOICE_CRAFTER_PROVIDER=anthropic
        "choice_crafter": {"provider": "ollama", "model": "qwen3:8b"},
        # V5.0: Companion System — authoritative LLM companion reactions + voice
        # Override to cloud for quality: STORYTELLER_COMPANION_SYSTEM_PROVIDER=anthropic
        "companion_system": {"provider": "ollama", "model": "qwen3:8b"},
        # V5.0: Arc Weaver — LLM narrative arc analysis (structural, fast)
        "arc_weaver": {"provider": "ollama", "model": "qwen3:4b"},
        # V5.0: Intent Router — LLM intent classification (structural, fast)
        "intent_router": {"provider": "ollama", "model": "qwen3:4b"},
        "embedding": {"provider": "ollama", "model": "nomic-embed-text"},
        # V3.1: Dedicated campaign init role — defaults to architect config.
        # In production, override to cloud: STORYTELLER_CAMPAIGN_INIT_PROVIDER=anthropic
        "campaign_init": {"provider": "ollama", "model": "qwen3:4b"},
        # V4.0: NPC narrative memory — lightweight, runs post-turn
        "memory": {"provider": "ollama", "model": "qwen3:8b"},
        # V4.0: World Mind — contextual world simulation replacing faction engine
        "world_mind": {"provider": "ollama", "model": "qwen3:8b"},
        # V4.0: Continuity — LLM-managed Truth Ledger (fact pruning + consequence hints)
        "continuity": {"provider": "ollama", "model": "qwen3:4b"},
        # V4.0: Quest Weaver — dynamic quest generation and completion evaluation
        "quest_weaver": {"provider": "ollama", "model": "qwen3:8b"},
        # V4.0: Progression — narrative stat growth and ability unlocking (~10 turns)
        "progression": {"provider": "ollama", "model": "qwen3:4b"},
        # V4.0: Psych Archivist — psychological arc + emotional_arc_note (~5 turns)
        "psych_archivist": {"provider": "ollama", "model": "qwen3:4b"},
        # V10.0: Revelation Agent — evaluates hidden info for dramatic timing (~5 turns)
        "revelation_agent": {"provider": "ollama", "model": "qwen3:4b"},
        # V10.0: Callback Crystallizer — identifies peak moments for future echo (~10 turns)
        "callback_crystallizer": {"provider": "ollama", "model": "qwen3:4b"},
        # Origin Story — generates playable backstory blueprint at campaign creation.
        # Override to cloud for quality: STORYTELLER_ORIGIN_PROVIDER=anthropic
        "origin": {"provider": "ollama", "model": "qwen3:8b"},
        # Phase 0.4: Prologue Screenplay — generates opening scene blueprint at campaign creation.
        # Override to cloud for quality: STORYTELLER_PROLOGUE_PROVIDER=anthropic
        "prologue": {"provider": "ollama", "model": "qwen3:8b"},
        # Phase 2.1: Arc Screenplay — generates per-arc narrative blueprint.
        # Override to cloud for quality: STORYTELLER_ARC_SCREENPLAY_PROVIDER=anthropic
        "arc_screenplay": {"provider": "ollama", "model": "qwen3:8b"},
        # V6.0: Campaign Bible — generates the full campaign screenplay bible at setup (one-shot).
        # STRONGLY recommended to override to cloud for quality — this is the highest-value
        # single LLM call in the entire pipeline (sets up the whole campaign).
        # Override: STORYTELLER_BIBLE_PROVIDER=anthropic STORYTELLER_BIBLE_MODEL=claude-opus-4-6
        "bible": {"provider": "ollama", "model": "qwen3:8b"},
        # EraForge: LLM-powered era pack auto-generator (suggest periods, generate packs, refine canon).
        # Cloud LLM strongly recommended — this generates foundational character-creation content.
        # Override: STORYTELLER_ERA_FORGE_PROVIDER=anthropic STORYTELLER_ERA_FORGE_MODEL=claude-sonnet-4-6
        "era_forge": {"provider": "ollama", "model": "qwen3:8b"},
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
        # V3.0: Per-role API key for cloud providers
        override_api_key = _role_env("API_KEY", role)
        if override_api_key:
            c["api_key"] = override_api_key
        # V3.0: Fallback provider chain (try primary, fall back to this)
        fallback_provider = _role_env("FALLBACK_PROVIDER", role)
        if fallback_provider:
            c["fallback_provider"] = fallback_provider
        fallback_model = _role_env("FALLBACK_MODEL", role)
        if fallback_model:
            c["fallback_model"] = fallback_model
        out[role] = c
    return out


MODEL_CONFIG = _model_config()

# V12.0: Provider-agnostic tier-based presets.
# Roles specify a quality tier, not a specific provider.  At runtime the resolver
# picks the best available provider+model based on which API keys are configured.
# See backend.app.core.provider_resolver for resolution logic.
SYSTEM_PRESETS: dict[str, dict[str, dict[str, str]]] = {
    # Budget: only Narrator on cloud (~$0.01/turn)
    "budget": {
        "narrator": {"tier": "quality"},
    },
    # Balanced: quality-critical quartet on cloud (~$0.02/turn)
    "balanced": {
        "director": {"tier": "quality"},
        "narrator": {"tier": "quality"},
        "choice_crafter": {"tier": "fast"},
        "mechanic": {"tier": "fast"},
    },
    # Quality: all narrative + strategic roles on cloud (~$0.05/turn)
    "quality": {
        "director": {"tier": "quality"},
        "narrator": {"tier": "quality"},
        "choice_crafter": {"tier": "quality"},
        "mechanic": {"tier": "quality"},
        "companion_system": {"tier": "quality"},
        "bible": {"tier": "quality"},
        "prologue": {"tier": "quality"},
        "era_forge": {"tier": "quality"},
        "origin": {"tier": "quality"},
        "arc_screenplay": {"tier": "quality"},
    },
    # Cloud All: routes ALL LLM roles to cloud — no Ollama required (~$0.08/turn).
    # Use for laptop testing, cloud deployment, or when Ollama is unavailable.
    "cloud_all": {
        # Narrative (quality-critical)
        "director": {"tier": "quality"},
        "narrator": {"tier": "quality"},
        "choice_crafter": {"tier": "quality"},
        "companion_system": {"tier": "quality"},
        # World building
        "architect": {"tier": "fast"},
        "bible": {"tier": "quality"},
        "world_mind": {"tier": "fast"},
        "era_forge": {"tier": "quality"},
        # Character & memory
        "biographer": {"tier": "fast"},
        "casting": {"tier": "fast"},
        "memory": {"tier": "fast"},
        "psych_archivist": {"tier": "fast"},
        "progression": {"tier": "fast"},
        # Structure & analysis
        "arc_weaver": {"tier": "fast"},
        "arc_screenplay": {"tier": "quality"},
        "intent_router": {"tier": "fast"},
        "continuity": {"tier": "fast"},
        "quest_weaver": {"tier": "fast"},
        # Special
        "prologue": {"tier": "quality"},
        "origin": {"tier": "quality"},
        "mechanic": {"tier": "fast"},
        "suggestion_refiner": {"tier": "fast"},
        "revelation_agent": {"tier": "fast"},
        "callback_crystallizer": {"tier": "fast"},
        # Infrastructure (LLM-based only — embedding uses local sentence-transformers)
        "campaign_init": {"tier": "fast"},
        "kg_extractor": {"tier": "fast"},
        "ingestion_tagger": {"tier": "fast"},
    },
}

VALID_CLOUD_PRESETS: tuple[str, ...] = ("local", "budget", "balanced", "quality", "cloud_all", "custom")


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
    3) default to STORYTELLER_INGEST_ROOT/lancedb (or ./data/lancedb)
       unless only legacy ./lancedb exists
    """
    if db_path:
        return Path(db_path)
    env_val = os.environ.get("VECTORDB_PATH", "").strip()
    if env_val:
        return Path(env_val)
    preferred = lancedb_dir()
    legacy = Path("lancedb")
    if preferred.exists() or not legacy.exists():
        return preferred
    return legacy

# Feature flags (progressive rollout)
ENABLE_BIBLE_CASTING = _env_flag("ENABLE_BIBLE_CASTING", default=True)
ENABLE_PROCEDURAL_NPCS = _env_flag("ENABLE_PROCEDURAL_NPCS", default=True)
NPC_RENDER_ENABLED = _env_flag("NPC_RENDER_ENABLED", default=False)
ENABLE_SUGGESTION_REFINER = _env_flag("ENABLE_SUGGESTION_REFINER", default=True)
ENABLE_CLOUD_BLUEPRINT = _env_flag("ENABLE_CLOUD_BLUEPRINT", default=False)
ENABLE_SCALE_ADVISOR = _env_flag("ENABLE_SCALE_ADVISOR", default=False)
# V11.0: Portrait/key art serving (optional, default off to avoid costs)
ENABLE_PORTRAITS = _env_flag("ENABLE_PORTRAITS", default=False)
# V13.0: Allow generic fallback choices when ChoiceCrafter LLM fails (disable for LLM-only)
ENABLE_CHOICE_FALLBACKS = _env_flag("ENABLE_CHOICE_FALLBACKS", default=True)

# World simulation (V2.5): tick interval in hours (default 4 = 240 min)
# Override via WORLD_TICK_INTERVAL_HOURS env. See backend.app.time_economy for action costs.

# Psychological profile defaults for characters (V2.5)
PSYCH_PROFILE_DEFAULTS: dict[str, str | int | None] = {
    "current_mood": "neutral",
    "stress_level": 0,
    "active_trauma": None,
}

# Token budgeting: per-role defaults imported from constants.py.
# Env overrides: STORYTELLER_{ROLE}_MAX_CONTEXT_TOKENS,
#                STORYTELLER_{ROLE}_RESERVED_OUTPUT_TOKENS,
#                STORYTELLER_{ROLE}_MAX_INPUT_TOKENS
from backend.app.constants import ROLE_TOKEN_BUDGETS as _ROLE_TOKEN_BUDGETS  # noqa: E402


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


def get_role_timeout(role: str) -> float:
    """Get LLM timeout in seconds for a role (env override or default).

    Override via STORYTELLER_{ROLE}_TIMEOUT or {ROLE}_TIMEOUT env vars.
    Defaults: suggestion_refiner=60, narrator=120, director=120, others=300.
    """
    env_val = _role_env("TIMEOUT", role)
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    _ROLE_TIMEOUT_DEFAULTS = {
        "suggestion_refiner": 60.0,
        "choice_crafter": 60.0,
        "narrator": 120.0,
        "director": 120.0,
        "intent_router": 15.0,
    }
    return _ROLE_TIMEOUT_DEFAULTS.get(role, 300.0)


# Dev-only flag to include context stats in TurnResponse
DEV_CONTEXT_STATS = os.environ.get("DEV_CONTEXT_STATS", "").strip().lower() in ("1", "true", "yes")

# Convenience defaults (computed at import time). Prefer get_role_max_input_tokens in runtime code.
DIRECTOR_MAX_INPUT_TOKENS = get_role_max_input_tokens("director")
NARRATOR_MAX_INPUT_TOKENS = get_role_max_input_tokens("narrator")

# Ingestion tagger (local LLM) flag: optional, off by default.
INGESTION_TAGGER_ENABLED = os.environ.get("INGESTION_TAGGER_ENABLED", "").strip().lower() in ("1", "true", "yes")

# V4.0: Rule system configuration
# STORYTELLER_RULE_SYSTEM: id of the active rule system (filename without .md in data/static/rule_systems/)
# Override to "ffg_star_wars", "dnd_5e_simplified", "stargate_d20", etc.
DEFAULT_RULE_SYSTEM = os.environ.get("STORYTELLER_RULE_SYSTEM", "storyteller_core")
RULE_SYSTEMS_DIR = DATA_ROOT / "static" / "rule_systems"
