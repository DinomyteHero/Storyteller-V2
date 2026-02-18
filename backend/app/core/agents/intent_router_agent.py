"""IntentRouterAgent: LLM-driven intent classification with safety guardrails.

Classifies player input into META (help/save/load), TALK (pure dialogue), or
ACTION (requires mechanical resolution). Deterministic safety guardrails are applied
AFTER the LLM to enforce invariants that must never be bypassed.

V5.0: Setting-agnostic. Hybrid approach: LLM intent + deterministic safety.
"""
from __future__ import annotations

import json
import logging
import re

from backend.app.core.agents.base import AgentLLM

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You classify player input for an interactive narrative RPG.

## CATEGORIES

- META: System commands — help, save, load, quit, menu
- TALK: Pure dialogue with no world-changing intent — greeting, asking a question,
  making conversation. The world state does NOT change.
- ACTION: Anything that requires mechanical resolution — combat, stealth, persuasion,
  movement, using items, investigating, casting abilities. The world state CHANGES.

## RULES

- When unsure, classify as ACTION. It is always safe to resolve mechanically.
- Dialogue that tries to CHANGE someone's behavior (persuade, threaten, bribe, deceive,
  negotiate) is ACTION, not TALK.
- Dialogue that is purely informational (ask a question, greet, chat) is TALK.
- Physical actions (fight, sneak, steal, move, search) are always ACTION.
- "I say hello" = TALK. "I convince him to let us pass" = ACTION.

## OUTPUT

Output ONLY a JSON object:
{"intent": "META|TALK|ACTION", "rationale": "brief explanation"}
"""


def classify_intent(user_input: str) -> dict[str, str]:
    """Classify user input intent via LLM.

    Returns dict with 'intent' (META|TALK|ACTION) and 'rationale'.
    Raises on LLM failure.
    """
    llm = AgentLLM("intent_router")

    raw = llm.complete(
        _SYSTEM_PROMPT,
        f'Player says: "{user_input}"\n\nClassify:',
        json_mode=True,
        raw_json_mode=True,
    )

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
        brace = cleaned.find("{")
        if brace >= 0:
            try:
                result = json.loads(cleaned[brace:])
            except (json.JSONDecodeError, TypeError):
                pass

    if result is None or not isinstance(result, dict):
        raise ValueError(f"IntentRouter: LLM failed to produce valid JSON. Raw: {(raw or '')[:200]}")

    intent = str(result.get("intent") or "ACTION").upper()
    if intent not in ("META", "TALK", "ACTION"):
        intent = "ACTION"  # Default to safe

    return {
        "intent": intent,
        "rationale": str(result.get("rationale") or ""),
    }
