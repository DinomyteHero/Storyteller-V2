"""Cloud resolution helper for pipeline nodes.

Provides a single function for nodes to get a turn-scoped AgentLLM
with the full provider resolution chain applied (override → preset → env → default).

V12.0: Cloud-agnostic provider system.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def get_campaign_settings(gs: Any) -> dict[str, Any]:
    """Extract cloud LLM settings from a GameState for the resolver."""
    return {
        "cloud_preset": getattr(gs, "cloud_preset", None),
        "custom_preset_id": getattr(gs, "custom_preset_id", None),
        "preferred_provider": getattr(gs, "preferred_provider", None),
        "agent_overrides": getattr(gs, "agent_overrides", None),
    }


def make_turn_llm(
    role: str,
    gs: Any,
    conn: sqlite3.Connection | None = None,
):
    """Create a turn-scoped AgentLLM with full resolution chain.

    This is the primary entry point for pipeline nodes.  It reads cloud
    settings from the GameState and resolves provider+model through the
    full chain: override → preset → env → default.

    Falls back to a default AgentLLM(role) if resolution fails.
    """
    from backend.app.core.provider_resolver import make_agent_llm

    settings = get_campaign_settings(gs)
    try:
        return make_agent_llm(role, settings, conn)
    except Exception as e:
        logger.warning("Cloud resolution failed for %s, using default: %s", role, e)
        from backend.app.core.agents.base import AgentLLM
        return AgentLLM(role)
