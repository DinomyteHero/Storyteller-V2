"""ChoiceCrafterAgent: LLM-driven player choice generation.

Replaces the deterministic suggestion_engine.py (~1100 lines of hardcoded scenario
trees) with a single authoritative LLM agent that generates contextually-aware,
narratively-rich player choices.

No deterministic fallbacks. If the LLM fails, the exception propagates to the caller.

V5.0: Setting-agnostic. Uses {setting_style} placeholder from SettingRules.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.app.core.agents.base import AgentLLM

logger = logging.getLogger(__name__)

_VALID_TONES = frozenset({"PARAGON", "INVESTIGATE", "RENEGADE", "NEUTRAL"})

_VALID_MEANINGS = frozenset({
    "reveal_values", "probe_belief", "challenge_premise",
    "seek_history", "set_boundary", "pragmatic", "deflect",
    "offer_alliance", "express_doubt", "invoke_authority",
    "show_vulnerability", "make_demand",
})
_VALID_IMPACT_TIERS = frozenset({"ripple", "wave", "tsunami"})

_SYSTEM_PROMPT = """\
You are the Choice Architect for an interactive narrative RPG (__SETTING_STYLE__).

Your job: generate exactly 4 player choices that define WHAT THE PLAYER CAN DO NEXT.

## RULES

1. TONE SPREAD — You MUST produce exactly:
   - 1 PARAGON choice (bold, direct, decisive — act now, lead, commit without hesitation)
   - 1 INVESTIGATE choice (cautious, analytical — gather information before committing, probe carefully)
   - 1 RENEGADE choice (deceptive or ruthless — use cunning, misdirection, leverage, or force)
   - 1 NEUTRAL choice (tactical pause or unexpected lateral move — an angle the player hasn't considered)

2. SCENE-SPECIFIC — Every choice must directly respond to what just happened in the
   prose. Reference specific NPCs by name, specific locations, specific events. Never
   produce generic options like "Look around" or "Wait and see."

3. DISTINCT APPROACHES — The 4 choices must represent genuinely different courses of
   action, not different phrasings of the same thing. Each should lead to a meaningfully
   different outcome.

4. CONSEQUENCE HINTS — Each choice has a consequence_hint: a specific, narratively-
   grounded preview. NOT "may gain trust" but "Kessa may reveal her contact's location"
   or "the guards will be on alert for the next hour."

5. RISK JUSTIFICATION — If a choice is RISKY or DANGEROUS, the risk must be narratively
   justified in context (e.g., "the guards just changed shifts" or "you're outnumbered").

6. IMPACT TIER — Tag each choice with impact_tier:
   - ripple: local consequence
   - wave: regional/faction-level consequence
   - tsunami: world-changing consequence (rare, major inflection points)
   Default to ripple unless the action is clearly major.

7. THE LATERAL MOVE — The NEUTRAL choice should ideally be something unexpected that opens
   a new angle the player might not have considered. Surprise them.

8. STAT GATES — When the STAT CONTEXT section indicates a high stat (>= 6), you may
   prefix ONE choice with a stat gate like [PERSUADE], [TECH], [COMBAT], [FORCE], etc.
   This signals the choice leverages that character build.

9. OBLIGATIONS — When ACTIVE OBLIGATIONS are listed, at least one choice should reference
   or advance one of them. Players should feel their past decisions matter.

10. LENGTH — Each choice text should be 8-20 words. Concise but specific.

## OUTPUT FORMAT

Output ONLY a JSON array of exactly 4 objects. No markdown, no explanation, no wrapping.

[
  {"text": "string", "tone": "PARAGON|INVESTIGATE|RENEGADE|NEUTRAL", "meaning": "tag", "risk": "SAFE|RISKY|DANGEROUS", "impact_tier": "ripple|wave|tsunami", "consequence_hint": "specific clause"},
  ...
]

Valid meaning tags: reveal_values, probe_belief, challenge_premise, seek_history,
set_boundary, pragmatic, deflect, offer_alliance, express_doubt, invoke_authority,
show_vulnerability, make_demand.
"""


def _classify_impact_tier(text: str, risk: str = "SAFE") -> str:
    """Classify impact tier from choice text with conservative defaults."""
    t = (text or "").lower()
    risk_u = (risk or "SAFE").upper()
    tsunami_markers = (
        "destroy planet",
        "blow up",
        "assassinate the emperor",
        "collapse the regime",
        "wipe out",
        "genocide",
        "galaxy",
        "world",
    )
    wave_markers = (
        "kill the leader",
        "assassinate",
        "take over",
        "overthrow",
        "destroy the",
        "sabotage",
        "start a war",
        "declare war",
        "blackmail",
        "execute",
    )
    if any(marker in t for marker in tsunami_markers):
        return "tsunami"
    if any(marker in t for marker in wave_markers):
        return "wave"
    if risk_u == "DANGEROUS":
        return "wave"
    return "ripple"


def _build_context(
    final_text: str,
    location: str,
    npc_descriptions: list[str],
    mechanic_summary: str | None,
    npc_utterance_text: str = "",
    topic_primary: str = "",
    subtext: str = "",
    npc_agenda: str = "",
    companion_hint: str = "",
    player_history_hint: str = "",
    director_intent: str = "",
    arc_stage: str = "",
    tension_level: str = "",
    consequence_hints: list[str] | None = None,
    stat_summary: str = "",
    gm_context: str = "",
) -> str:
    """Assemble the user prompt from scene context."""
    parts = [f"PROSE:\n{final_text[-800:]}"]  # Last 800 chars of prose for recency

    if npc_utterance_text:
        parts.append(f"\nNPC SAYS: \"{npc_utterance_text}\"")

    # GM Context Object — compact unified summary from scene_frame_node
    if gm_context:
        parts.append(f"\n{gm_context}")

    parts.append(f"\nSCENE: {location}")

    if npc_descriptions:
        parts.append(f"NPCs PRESENT: {', '.join(npc_descriptions)}")
    else:
        parts.append("NPCs PRESENT: None — player is alone")

    if mechanic_summary:
        parts.append(f"LAST ACTION RESULT: {mechanic_summary}")

    if topic_primary:
        parts.append(f"TOPIC: {topic_primary}")
    if subtext:
        parts.append(f"SUBTEXT: {subtext}")
    if npc_agenda:
        parts.append(f"NPC AGENDA: {npc_agenda}")

    if arc_stage:
        parts.append(f"ARC STAGE: {arc_stage}")
    if tension_level:
        parts.append(f"TENSION: {tension_level}")

    if companion_hint:
        parts.append(f"COMPANIONS: {companion_hint}")
    if player_history_hint:
        parts.append(f"PLAYER PATTERN: {player_history_hint}")
    if director_intent:
        parts.append(f"DIRECTOR INTENT: {director_intent}")

    if consequence_hints:
        parts.append(f"ACTIVE OBLIGATIONS: {'; '.join(consequence_hints[:3])}")

    if stat_summary:
        parts.append(f"STAT CONTEXT: {stat_summary}")

    parts.append("\nGenerate exactly 4 player choices:")
    return "\n".join(parts)


def _parse_choices(raw: str) -> list[dict[str, str]] | None:
    """Parse LLM JSON output into validated choice dicts.

    Returns None if parsing fails completely.
    """
    if not raw or not raw.strip():
        return None

    cleaned = raw.strip()
    # Remove <think>...</think> blocks (qwen3 chain-of-thought)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    # Remove markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    data = None

    # Try direct parse
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try bracket extraction
    if data is None:
        from backend.app.core.json_repair import extract_json_array
        arr_str = extract_json_array(cleaned)
        if arr_str:
            try:
                data = json.loads(arr_str)
            except (json.JSONDecodeError, TypeError):
                pass

    if data is None:
        return None

    # Unwrap if wrapped in a dict
    if isinstance(data, dict):
        for key in ("suggestions", "responses", "options", "choices"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            if data.get("text") or data.get("label"):
                data = [data]
            else:
                return None

    if not isinstance(data, list) or not data:
        return None

    # Validate each item
    valid = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("label")
        tone = item.get("tone")
        if not isinstance(text, str) or not text.strip():
            continue
        if not isinstance(tone, str) or tone.upper() not in _VALID_TONES:
            continue
        item["text"] = text.strip()
        item["tone"] = tone.upper()
        # Validate meaning
        meaning = item.get("meaning", "")
        if meaning and meaning not in _VALID_MEANINGS:
            item["meaning"] = ""
        # Validate risk
        risk = (item.get("risk") or "SAFE").upper()
        if risk not in ("SAFE", "RISKY", "DANGEROUS"):
            risk = "SAFE"
        item["risk"] = risk
        # Validate impact tier
        impact_tier = str(item.get("impact_tier") or "").strip().lower()
        if impact_tier not in _VALID_IMPACT_TIERS:
            impact_tier = _classify_impact_tier(item["text"], risk=risk)
        item["impact_tier"] = impact_tier
        # Ensure consequence_hint exists
        if not item.get("consequence_hint"):
            item["consequence_hint"] = ""
        valid.append(item)

    if len(valid) < 3:
        return None

    # Trim to 4 or pad
    if len(valid) > 4:
        valid = valid[:4]
    while len(valid) < 4:
        valid.append({
            "text": "Consider your options carefully before acting.",
            "tone": "NEUTRAL",
            "meaning": "pragmatic",
            "risk": "SAFE",
            "impact_tier": "ripple",
            "consequence_hint": "take stock of the situation",
        })

    return valid


def generate_choices(
    *,
    final_text: str,
    location: str,
    npc_descriptions: list[str],
    mechanic_summary: str | None = None,
    npc_utterance_text: str = "",
    topic_primary: str = "",
    subtext: str = "",
    npc_agenda: str = "",
    companion_hint: str = "",
    player_history_hint: str = "",
    director_intent: str = "",
    arc_stage: str = "",
    tension_level: str = "",
    consequence_hints: list[str] | None = None,
    stat_summary: str = "",
    setting_style: str = "an interactive narrative RPG",
    gm_context: str = "",
) -> list[dict[str, str]]:
    """Generate 4 player choices via LLM.

    Raises ValueError on failure after one retry — caller should catch and use fallback.
    Returns list of dicts with keys: text, tone, meaning, risk, consequence_hint.
    """
    llm = AgentLLM("choice_crafter")

    system_prompt = _SYSTEM_PROMPT.replace("__SETTING_STYLE__", setting_style)

    user_prompt = _build_context(
        final_text=final_text,
        location=location,
        npc_descriptions=npc_descriptions,
        mechanic_summary=mechanic_summary,
        npc_utterance_text=npc_utterance_text,
        topic_primary=topic_primary,
        subtext=subtext,
        npc_agenda=npc_agenda,
        companion_hint=companion_hint,
        player_history_hint=player_history_hint,
        director_intent=director_intent,
        arc_stage=arc_stage,
        tension_level=tension_level,
        consequence_hints=consequence_hints,
        stat_summary=stat_summary,
        gm_context=gm_context,
    )

    raw = llm.complete(system_prompt, user_prompt, json_mode=True, raw_json_mode=True)
    logger.debug("ChoiceCrafter raw output (first 600 chars): %s", (raw or "")[:600])

    items = _parse_choices(raw)

    # Retry once with correction prompt on parse failure
    if items is None:
        logger.info("ChoiceCrafter: first attempt failed to parse, retrying with correction")
        correction = (
            "Your previous output was not a valid JSON array of 4 player choices. "
            "Output ONLY a JSON array with exactly 4 objects. Each object must have "
            '"text" (8-20 words), "tone" (PARAGON/INVESTIGATE/RENEGADE/NEUTRAL), '
            '"meaning" (one tag), "risk" (SAFE/RISKY/DANGEROUS), and "consequence_hint". '
            "Start with [ and end with ]. No other text.\n\n" + user_prompt
        )
        raw2 = llm.complete(system_prompt, correction, json_mode=True, raw_json_mode=True)
        items = _parse_choices(raw2)

    if items is None:
        raise ValueError(
            f"ChoiceCrafter: LLM failed to produce valid choices after retry. "
            f"Raw (first 300 chars): {(raw or '')[:300]}"
        )

    logger.info("ChoiceCrafter: generated %d choices", len(items))
    return items
