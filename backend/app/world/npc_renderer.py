"""Optional LLM rendering pass for NPCs (bounded output)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field

from backend.app.config import NPC_RENDER_ENABLED
from backend.app.core.agents.base import AgentLLM, ensure_json


class NpcRenderOutput(BaseModel):
    intro: str = ""
    dialogue_lines: list[str] = Field(default_factory=list)
    quest_hook: str | None = None


def _count_sentences(text: str) -> int:
    if not text:
        return 0
    parts = re.split(r"[.!?]+", text.strip())
    return len([p for p in parts if p.strip()])


def _validate_output(output: NpcRenderOutput) -> bool:
    intro = (output.intro or "").strip()
    if not intro:
        return False
    if _count_sentences(intro) < 2 or _count_sentences(intro) > 4:
        return False
    lines = output.dialogue_lines or []
    if len(lines) != 3:
        return False
    for ln in lines:
        if not ln or len(str(ln)) > 140:
            return False
    if output.quest_hook and len(output.quest_hook) > 200:
        return False
    return True


def _fallback_render(npc: dict[str, Any]) -> dict[str, Any]:
    name = npc.get("name", "The NPC")
    role = npc.get("role", "NPC")
    location = npc.get("location_id", "the area")
    traits = (npc.get("stats_json") or {}).get("traits") or []
    trait_text = ", ".join(traits[:2]) if traits else "quiet"
    motivation = (npc.get("stats_json") or {}).get("motivation") or "keep moving"
    intro = (
        f"{name} is a {trait_text} {role.lower()} lingering around {location}. "
        f"They seem focused on one thing: {motivation}."
    )
    dialogue_lines = [
        f"\"Name's {name}.\"",
        "\"I hear things around here - maybe you do too.\"",
        "\"Keep your guard up; nothing is simple.\"",
    ]
    quest_hook = None
    return {"intro": intro, "dialogue_lines": dialogue_lines, "quest_hook": quest_hook}


def render_npc(
    npc: dict[str, Any],
    *,
    llm: AgentLLM | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Render a bounded intro + dialogue lines for an NPC. Returns dict with intro/dialogue_lines/quest_hook."""
    if enabled is None:
        enabled = NPC_RENDER_ENABLED
    if not enabled:
        return _fallback_render(npc)

    if llm is None:
        llm = AgentLLM("npc_render")

    system = (
        "You are an NPC rendering assistant. Output ONLY valid JSON with keys: "
        "intro (2-4 sentences), dialogue_lines (array of exactly 3 short lines), "
        "quest_hook (optional, <=1 sentence). No markdown, no extra text."
    )
    user = (
        "NPC seed:\n"
        f"{json.dumps(npc)}\n\n"
        "Generate grounded, short, in-world text. Do not invent factions or places not in the seed."
    )
    try:
        raw = llm.complete(system, user, json_mode=True)
        js = ensure_json(raw)
        if not js:
            return _fallback_render(npc)
        data = json.loads(js)
        output = NpcRenderOutput.model_validate(data)
        if not _validate_output(output):
            return _fallback_render(npc)
        return output.model_dump(mode="json")
    except Exception:
        logger.exception("NPC render failed for %s, using fallback", npc.get("name", "unknown"))
        return _fallback_render(npc)
