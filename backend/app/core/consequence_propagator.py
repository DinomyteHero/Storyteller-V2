"""Sandbox Consequence Propagation — follow-on effects for impactful actions.

When a player performs a wave- or tsunami-tier action in Sandbox mode,
a pending consequence is created. The ConsequencePropagator:
  1. Decrements remaining turns on each active consequence.
  2. Expires consequences that have exhausted their duration.
  3. Returns active consequences for Director/WorldSim context injection.

Consequences live in ``world_state_json["pending_consequences"]`` as a list of dicts.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.constants import (
    CONSEQUENCE_DURATION,
    CONSEQUENCE_MAX_ACTIVE,
    SANDBOX_IMPACT_TIERS,
    SANDBOX_ARC_STAGE_ORDER,
)

logger = logging.getLogger(__name__)


def create_consequence(
    world_state: dict[str, Any],
    impact_tier: str,
    action_summary: str,
    arc_stage: str,
) -> dict[str, Any] | None:
    """Create a new pending consequence from a high-impact action.

    Only creates consequences for ``wave`` and ``tsunami`` tiers.
    Returns the created consequence dict, or None if not applicable.
    """
    if impact_tier not in ("wave", "tsunami"):
        return None

    duration = CONSEQUENCE_DURATION.get(impact_tier, 0)
    if duration <= 0:
        return None

    # Check arc stage gate
    tier_def = SANDBOX_IMPACT_TIERS.get(impact_tier, {})
    min_stage = str(tier_def.get("min_arc_stage", "SETUP")).upper()
    stage_order = SANDBOX_ARC_STAGE_ORDER
    if stage_order.get(arc_stage.upper(), 0) < stage_order.get(min_stage, 0):
        return None

    consequence = {
        "impact_tier": impact_tier,
        "action_summary": action_summary[:200],
        "remaining_turns": duration,
        "total_turns": duration,
        "arc_stage_created": arc_stage.upper(),
    }

    pending = world_state.get("pending_consequences") or []

    # Cap active consequences
    if len(pending) >= CONSEQUENCE_MAX_ACTIVE:
        # Drop the oldest ripple-tier or lowest-remaining consequence
        pending.sort(key=lambda c: (c.get("remaining_turns", 0), c.get("impact_tier", "") != "tsunami"))
        pending = pending[1:]  # Drop the first (lowest priority)

    pending.append(consequence)
    world_state["pending_consequences"] = pending

    logger.info(
        "Created %s-tier consequence: %s (duration=%d turns)",
        impact_tier, action_summary[:60], duration,
    )
    return consequence


def tick_consequences(world_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Decrement and expire consequences. Returns list of still-active consequences.

    Call this at the start of each turn to advance the consequence clock.
    Expired consequences are removed from world_state.
    """
    pending = world_state.get("pending_consequences") or []
    if not pending:
        return []

    active: list[dict[str, Any]] = []
    expired: list[dict[str, Any]] = []

    for consequence in pending:
        remaining = consequence.get("remaining_turns", 0)
        if remaining > 1:
            consequence["remaining_turns"] = remaining - 1
            active.append(consequence)
        else:
            expired.append(consequence)

    if expired:
        logger.info("Expired %d consequences", len(expired))

    world_state["pending_consequences"] = active
    return active


def get_active_consequences(world_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return currently active consequences (read-only, no mutation)."""
    return list(world_state.get("pending_consequences") or [])


def format_for_director(consequences: list[dict[str, Any]]) -> str:
    """Format active consequences as context text for Director/WorldSim prompts."""
    if not consequences:
        return ""

    lines = ["ACTIVE CONSEQUENCES (affect the world this turn):"]
    for i, c in enumerate(consequences, 1):
        tier = c.get("impact_tier", "unknown").upper()
        summary = c.get("action_summary", "Unknown action")
        remaining = c.get("remaining_turns", 0)
        total = c.get("total_turns", remaining)
        lines.append(
            f"  {i}. [{tier}] {summary} "
            f"(turn {total - remaining + 1}/{total})"
        )
    return "\n".join(lines)
