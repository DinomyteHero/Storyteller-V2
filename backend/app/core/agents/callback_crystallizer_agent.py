"""CallbackCrystallizerAgent: LLM-driven peak moment identification (V10.0 Feature 3).

Runs every ~10 turns. Scans recent narrative for peak moments — turns where
something memorable happened (CLIMAX/ELEVATED scenes, large affinity deltas,
wave/tsunami impacts, dramatic NPC state changes). Stores these as "callback
seeds" with trigger conditions the Director uses to echo them later.

The key insight: a human author plants callbacks deliberately. "Something in
her voice reminded you of another time, another lie." This agent identifies
which moments deserve to be echoed and when.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM, ensure_json
from backend.app.constants import CALLBACK_SEEDS_MAX

logger = logging.getLogger(__name__)


def _build_system_prompt() -> str:
    return """\
You are the Callback Crystallizer for a narrative RPG. Your role is to identify
PEAK MOMENTS in recent narrative — moments so vivid, emotional, or pivotal that
they deserve to be echoed later in the story.

A great callback is NOT a plot summary. It's a specific image, phrase, or emotional
beat that resonates when recalled:
- "I never said I was the hero" (a line that cuts deeper the second time)
- "The smell of burned circuits and betrayal" (a sensory anchor)
- "She turned away, and you let her" (a moment of inaction that haunts)

You receive recent narrative prose and significant events. For each peak moment
you identify, provide:

1. MOMENT: A 1-sentence description of what happened.
2. ECHO_TEXT: A short phrase or image (max 15 words) that could be woven into
   future prose as a callback. NOT a quote — a resonance.
3. EMOTIONAL_CONTEXT: One of: betrayal, sacrifice, triumph, loss, revelation,
   humor, tenderness, defiance, guilt, wonder.
4. TRIGGER_CONDITIONS: 1-3 conditions for when this callback would land best.

Return a JSON array. Only crystallize truly memorable moments (0-3 per evaluation).
Most turns have NO peak moments — that's normal. Quality over quantity.

[JSON OUTPUT SCHEMA]
[
  {
    "moment": "description of what happened",
    "echo_text": "a phrase or image to echo later",
    "emotional_context": "betrayal|sacrifice|triumph|loss|revelation|humor|tenderness|defiance|guilt|wonder",
    "trigger_conditions": ["condition1", "condition2"]
  }
]

Return ONLY a valid JSON array. Empty array [] is fine if nothing is memorable.
No markdown. No preamble."""


def _build_user_prompt(
    recent_narrative: str,
    events: list[dict],
    arc_stage: str,
    turn_number: int,
    existing_seeds_count: int,
) -> str:
    # Extract notable events
    notable = []
    for e in events:
        if not isinstance(e, dict):
            continue
        etype = str(e.get("event_type", "")).upper()
        payload = e.get("payload") or {}
        if etype == "RELATIONSHIP":
            delta = payload.get("delta", 0)
            npc = payload.get("npc_id", "?")
            if abs(int(delta or 0)) >= 3:
                notable.append(f"Major relationship shift with {npc} (delta={delta})")
        elif etype in ("NPC_DEATH", "COMPANION_DEATH", "DEATH"):
            name = payload.get("name") or payload.get("npc_id", "someone")
            notable.append(f"Death of {name}")
        elif etype == "BETRAYAL":
            notable.append(f"Betrayal: {payload.get('text', 'unknown')}")
        elif etype == "FLAG_SET":
            flag = payload.get("flag", "")
            if "reveal" in flag.lower() or "betray" in flag.lower() or "sacrifice" in flag.lower():
                notable.append(f"Significant flag: {flag}")

    events_block = "\n".join(f"  - {n}" for n in notable) if notable else "  (No notable events)"

    return f"""\
[TURN {turn_number} | ARC STAGE: {arc_stage}]
[EXISTING CALLBACK SEEDS: {existing_seeds_count}]

[NOTABLE EVENTS]
{events_block}

[RECENT NARRATIVE PROSE]
{recent_narrative[:900] if recent_narrative else "(No recent narrative)"}

Identify peak moments worthy of future callbacks. Return empty array if nothing
is truly memorable. Quality matters — only crystallize moments that would resonate
if echoed 20-50 turns later."""


def _normalize_output(raw: list, turn_number: int) -> list[dict]:
    """Validate and normalize callback seed entries."""
    results = []
    valid_contexts = {"betrayal", "sacrifice", "triumph", "loss", "revelation",
                      "humor", "tenderness", "defiance", "guilt", "wonder"}
    for item in raw:
        if not isinstance(item, dict):
            continue
        moment = str(item.get("moment") or "").strip()
        echo_text = str(item.get("echo_text") or "").strip()
        if not moment or not echo_text:
            continue
        context = str(item.get("emotional_context") or "").strip().lower()
        if context not in valid_contexts:
            context = "revelation"
        triggers = [str(c)[:100] for c in (item.get("trigger_conditions") or [])[:3]]
        results.append({
            "turn": turn_number,
            "moment": moment[:200],
            "echo_text": echo_text[:100],
            "emotional_context": context,
            "trigger_conditions": triggers,
            "used_count": 0,
        })
    return results[:3]  # Max 3 per evaluation


class CallbackCrystallizerAgent:
    """LLM-driven peak moment identification and callback seed storage.

    Scans recent narrative for memorable moments and stores them as callback
    seeds. The Director consults these seeds each turn and weaves echoes
    into the narrative when trigger conditions match.
    """

    def __init__(self, llm=None) -> None:
        self._llm = llm if llm is not None else AgentLLM("callback_crystallizer")

    def crystallize(
        self,
        world_state: dict[str, Any],
        recent_narrative: str,
        turn_number: int,
        events: list[dict[str, Any]],
        arc_stage: str,
    ) -> None:
        """Scan recent narrative for peak moments and update callback_seeds."""
        existing_seeds = world_state.get("callback_seeds") or []

        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(
            recent_narrative=recent_narrative,
            events=events,
            arc_stage=arc_stage,
            turn_number=turn_number,
            existing_seeds_count=len(existing_seeds),
        )

        raw_text = self._llm.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
        )

        try:
            raw_json = json.loads(ensure_json(raw_text))
            if isinstance(raw_json, dict):
                raw_json = raw_json.get("callbacks") or raw_json.get("seeds") or [raw_json]
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error("CallbackCrystallizerAgent: JSON parse failed: %s", exc)
            return

        if not isinstance(raw_json, list):
            raw_json = []

        new_seeds = _normalize_output(raw_json, turn_number)

        # Merge with existing, keeping newest and most-used at priority
        merged = existing_seeds + new_seeds
        # Cap at max, prioritizing newest (higher turn number)
        merged.sort(key=lambda s: s.get("turn", 0), reverse=True)
        world_state["callback_seeds"] = merged[:CALLBACK_SEEDS_MAX]

        logger.info(
            "CallbackCrystallizerAgent: turn %d — %d new seeds, %d total",
            turn_number,
            len(new_seeds),
            len(world_state["callback_seeds"]),
        )
