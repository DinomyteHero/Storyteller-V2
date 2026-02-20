"""Interlude node: lightweight deterministic scene between arcs (no LLM, no DB).

V8.0: Provides breathing room between arc RESOLUTION and new arc SETUP.
Injects downtime context (news, rumors, companion banter) into director_instructions
so the narrator produces a reflective, low-stakes transition scene.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.constants import INTERLUDE_TIME_SKIP_HOURS

logger = logging.getLogger(__name__)


def interlude_node(state: dict[str, Any]) -> dict[str, Any]:
    """Inject interlude context when between arcs. Pass-through otherwise.

    This node runs after arc_planner and before scene_frame. When
    interlude_active is True, it constructs downtime context from world_state
    (news, rumors, banter) and sets director_instructions to guide the narrator
    toward a reflective, low-stakes scene.

    When interlude_active is False, it's a no-op pass-through.
    """
    arc_guidance = state.get("arc_guidance") or {}
    if not arc_guidance.get("interlude_active"):
        return state

    campaign = state.get("campaign") or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    if not isinstance(ws, dict):
        ws = {}

    # Gather downtime context from world state
    news_feed = campaign.get("news_feed") or ws.get("news_feed") or []
    news_items = [
        n.get("headline", str(n)) if isinstance(n, dict) else str(n)
        for n in news_feed[:2]
    ]

    active_rumors = state.get("active_rumors") or ws.get("active_rumors") or []
    if isinstance(active_rumors, list):
        rumor_items = [str(r) for r in active_rumors[:3]]
    else:
        rumor_items = []

    banter_queue = ws.get("banter_queue") or []
    banter_line = str(banter_queue[0]) if banter_queue else ""

    # Build arc transition context
    arc_history = arc_guidance.get("arc_history") or []
    saga_context = arc_guidance.get("saga_context") or ""
    current_arc = arc_guidance.get("current_arc_number", 1)
    interlude_remaining = (arc_guidance.get("arc_state") or {}).get("interlude_remaining", 0)

    # Construct director instructions for the interlude scene
    parts = ["INTERLUDE SCENE — Between Arcs"]
    parts.append(f"Arc {current_arc - 1} has concluded. A new chapter is about to begin.")

    if saga_context:
        parts.append(f"Previous arc: {saga_context}")

    parts.append("")
    parts.append("Time passes. Show the character in downtime:")

    if news_items:
        parts.append(f"  Recent news: {'; '.join(news_items)}")
    if rumor_items:
        parts.append(f"  Rumors circulating: {'; '.join(rumor_items)}")
    if banter_line:
        parts.append(f"  Companion moment: {banter_line}")

    parts.append("")
    parts.append(
        "Focus on atmosphere, character reflection, and companion interactions. "
        "No combat or major plot advancement. End with a sense of something new beginning — "
        "a distant signal, an unexpected visitor, or a quiet resolve."
    )

    if interlude_remaining <= 0:
        parts.append(
            "This is the FINAL interlude turn. Transition smoothly into the next arc's opening."
        )

    director_instructions = "\n".join(parts)

    # Advance world time for the interlude skip
    pending_time = state.get("pending_world_time_minutes") or 0
    interlude_time_minutes = INTERLUDE_TIME_SKIP_HOURS * 60
    new_pending_time = pending_time + interlude_time_minutes

    logger.info(
        "Interlude node: arc %d, remaining=%d, time_skip=%dh",
        current_arc, interlude_remaining, INTERLUDE_TIME_SKIP_HOURS,
    )

    return {
        **state,
        "director_instructions": director_instructions,
        "pending_world_time_minutes": new_pending_time,
    }
