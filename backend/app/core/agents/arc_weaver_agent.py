"""ArcWeaverAgent: LLM-driven narrative arc analysis.

Replaces the deterministic turn-counting arc planner with semantic narrative analysis.
The LLM reads story history, ledger facts, open threads, and consequence hints to
determine whether the story is ready to advance to the next arc stage.

Hybrid approach: deterministic min/max turn guards are hard constraints. The LLM
proposes transitions within the valid window. This gives creative freedom within
safe bounds.

V5.0: Setting-agnostic. No hardcoded setting references.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.app.core.agents.base import AgentLLM

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a Narrative Architect analyzing story pacing for an interactive RPG.

Given the current arc stage and narrative state, determine if the story is ready to
advance to the next stage.

## ARC STAGES

1. SETUP → RISING: When inciting incidents have occurred, the player has committed to
   a goal, and enough world-building is established. The player knows who the key players
   are and what's at stake.

2. RISING → CLIMAX: When stakes are at their highest, multiple narrative threads converge,
   and the player faces an unavoidable confrontation. Tension should feel like it cannot
   be sustained much longer.

3. CLIMAX → RESOLUTION: When the central conflict has been addressed (win or lose), and
   the world is settling into a new state.

## PACING RULES

- Do NOT advance too quickly. Let tension build naturally.
- A story that rushes to climax feels hollow. A story that lingers too long in setup feels boring.
- If the player seems to be exploring side content, that's fine — let SETUP or RISING breathe.
- If the player is driving hard toward conflict, accelerate.

## OUTPUT FORMAT

Output ONLY a JSON object:
{"should_advance": true|false, "justification": "1-2 sentence explanation",
 "pacing_note": "brief guidance for the narrator this turn",
 "theme_note": "optional thematic observation or null"}
"""


def evaluate_arc_transition(
    *,
    current_stage: str,
    turns_in_stage: int,
    ledger_facts: list[str],
    open_threads: list[str],
    consequence_hints: list[str],
    recent_narrative: str = "",
    player_tone_pattern: str = "",
    llm: Any | None = None,
) -> dict[str, Any]:
    """Evaluate whether the arc should advance using LLM semantic analysis.

    Returns dict with: should_advance, justification, pacing_note, theme_note.
    Raises on LLM failure.

    V12.0: Optional ``llm`` parameter allows cloud-resolved AgentLLM injection.
    """
    if llm is None:
        llm = AgentLLM("arc_weaver")

    parts = [
        f"CURRENT STAGE: {current_stage}",
        f"TURNS IN STAGE: {turns_in_stage}",
    ]

    if ledger_facts:
        parts.append(f"ESTABLISHED FACTS ({len(ledger_facts)}):")
        for f in ledger_facts[-10:]:
            parts.append(f"  - {f}")

    if open_threads:
        parts.append(f"OPEN THREADS ({len(open_threads)}):")
        for t in open_threads[-8:]:
            parts.append(f"  - {t}")

    if consequence_hints:
        parts.append(f"ACTIVE OBLIGATIONS ({len(consequence_hints)}):")
        for h in consequence_hints[:5]:
            parts.append(f"  - {h}")

    if recent_narrative:
        parts.append(f"\nRECENT NARRATIVE:\n{recent_narrative[-500:]}")

    if player_tone_pattern:
        parts.append(f"PLAYER PATTERN: {player_tone_pattern}")

    parts.append(f"\nShould the story advance from {current_stage} to the next stage?")
    user_prompt = "\n".join(parts)

    raw = llm.complete(_SYSTEM_PROMPT, user_prompt, json_mode=True, raw_json_mode=True)
    logger.debug("ArcWeaver raw (first 400 chars): %s", (raw or "")[:400])

    # Parse
    cleaned = (raw or "").strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    result = None
    try:
        result = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    if result is None:
        # Try extracting object
        brace_start = cleaned.find("{")
        if brace_start >= 0:
            try:
                result = json.loads(cleaned[brace_start:])
            except (json.JSONDecodeError, TypeError):
                pass

    if result is None or not isinstance(result, dict):
        logger.info("ArcWeaver: failed to parse, retrying")
        correction = (
            "Output ONLY valid JSON: "
            '{"should_advance": true|false, "justification": "...", '
            '"pacing_note": "...", "theme_note": null|"..."}\n\n'
            + user_prompt
        )
        raw2 = llm.complete(_SYSTEM_PROMPT, correction, json_mode=True, raw_json_mode=True)
        cleaned2 = (raw2 or "").strip()
        cleaned2 = re.sub(r"<think>.*?</think>", "", cleaned2, flags=re.DOTALL).strip()
        try:
            result = json.loads(cleaned2)
        except (json.JSONDecodeError, TypeError):
            pass

    if result is None or not isinstance(result, dict):
        raise ValueError(
            f"ArcWeaver: LLM failed to produce valid JSON after retry. "
            f"Raw: {(raw or '')[:300]}"
        )

    return {
        "should_advance": bool(result.get("should_advance", False)),
        "justification": str(result.get("justification") or ""),
        "pacing_note": str(result.get("pacing_note") or ""),
        "theme_note": result.get("theme_note"),
    }
