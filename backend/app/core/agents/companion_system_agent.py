"""CompanionSystemAgent: Authoritative LLM-driven companion reaction system.

Merges the deterministic compute_companion_reactions() (keyword matching for affinity)
AND the cosmetic CompanionVoiceAgent (spoken lines overlay) into a single authoritative
agent that determines BOTH affinity deltas AND spoken reactions.

No deterministic fallbacks. If the LLM fails, the exception propagates to the caller.

V5.0: Setting-agnostic. Replaces companion_voice_agent.py entirely.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.app.core.agents.base import AgentLLM
from backend.app.core.companion_reactions import companion_arc_stage

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
You are the Companion Director for an interactive narrative RPG. For each companion in
the player's party, you determine their authentic emotional and relational response to
what the player just did.

## RULES

1. PER-COMPANION — Output one entry per companion. Each entry includes:
   - affinity_delta: integer from -5 to +5 (how this action affected their feelings)
   - spoken_reaction: 1-2 sentences in the companion's authentic voice (max 25 words)
   - emotional_state: one of calm|angry|worried|grateful|conflicted|amused|determined|fearful
   - tension_with: null, or another companion_id if they disagree with that companion

2. PERSONALITY-DRIVEN — Each companion's reaction MUST match their personality traits:
   - An idealist companion is upset by ruthless choices, pleased by compassionate ones
   - A pragmatist companion respects efficiency, dislikes naive optimism
   - A lawful companion disapproves of crime; a rebellious one approves
   - Match the companion's speech_pattern and dialect exactly

3. ARC-STAGE AWARENESS — Relationship depth affects reaction quality:
   - STRANGER: cautious, reserved, observing. Short reactions. Small deltas (-2 to +2)
   - ALLY: more open, willing to express opinion. Moderate deltas (-3 to +3)
   - TRUSTED: emotionally invested, references shared history. Full deltas (-4 to +4)
   - LOYAL: deep familiarity, callbacks to past events, strong opinions. Full range (-5 to +5)

4. INTER-COMPANION TENSION — If two companions would disagree about the player's choice
   (e.g., one approves, one disapproves), flag the tension. This creates dramatic party dynamics.

5. BANTER — Optionally, one companion may address another companion directly (not the player).
   This creates the feeling of a living party with internal dynamics.

## OUTPUT FORMAT

Output ONLY a JSON object. No markdown, no explanation.

{"reactions": [
  {"companion_id": "id", "affinity_delta": -5..5, "spoken_reaction": "string",
   "emotional_state": "calm|angry|worried|grateful|conflicted|amused|determined|fearful",
   "tension_with": null|"companion_id", "banter_line": null|"string"}
]}
"""


def _build_context(
    companions: list[dict[str, Any]],
    mechanic_result: dict[str, Any],
    recent_narrative: str = "",
) -> str:
    """Build user prompt with companion profiles and action context."""
    parts = []

    # What happened
    outcome_summary = mechanic_result.get("outcome_summary") or "an action was taken"
    tone_tag = mechanic_result.get("tone_tag") or "NEUTRAL"
    action_type = mechanic_result.get("action_type") or ""
    success = mechanic_result.get("success")
    outcome_word = "succeeded" if success else "failed" if success is False else "acted"

    parts.append(f"PLAYER ACTION: {action_type} — {outcome_word}")
    parts.append(f"OUTCOME: {outcome_summary}")
    parts.append(f"PLAYER TONE: {tone_tag}")

    if recent_narrative:
        parts.append(f"\nRECENT PROSE (context): {recent_narrative[-400:]}")

    # Companion profiles
    parts.append("\nCOMPANIONS IN PARTY:")
    for comp in companions:
        cid = comp["id"]
        name = comp["name"]
        personality = comp.get("personality", "reserved")
        speech_pattern = comp.get("speech_pattern", "direct")
        values = comp.get("values", "survival")
        arc_stage = comp.get("arc_stage", "STRANGER")
        affinity = comp.get("affinity", 0)

        parts.append(f"\n- {name} (id: {cid})")
        parts.append(f"  Personality: {personality}")
        parts.append(f"  Speech: {speech_pattern}")
        parts.append(f"  Values: {values}")
        parts.append(f"  Relationship: {arc_stage} (affinity {affinity}/100)")

    parts.append("\nGenerate reactions for each companion:")
    return "\n".join(parts)


def _parse_reactions(raw: str) -> list[dict[str, Any]] | None:
    """Parse LLM output into validated reaction dicts."""
    if not raw or not raw.strip():
        return None

    cleaned = raw.strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    data = None
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    if data is None:
        from backend.app.core.json_repair import extract_json_array
        # Try extracting from a wrapping object
        try:
            # Look for {"reactions": [...]}
            brace_start = cleaned.find("{")
            if brace_start >= 0:
                data = json.loads(cleaned[brace_start:])
        except (json.JSONDecodeError, TypeError):
            pass

    if data is None:
        return None

    # Extract the reactions array
    reactions = None
    if isinstance(data, dict):
        reactions = data.get("reactions")
    elif isinstance(data, list):
        reactions = data

    if not isinstance(reactions, list) or not reactions:
        return None

    # Validate each reaction
    valid = []
    for r in reactions:
        if not isinstance(r, dict):
            continue
        cid = r.get("companion_id")
        if not isinstance(cid, str) or not cid:
            continue

        delta = r.get("affinity_delta", 0)
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            delta = 0
        delta = max(-5, min(5, delta))

        spoken = str(r.get("spoken_reaction") or "").strip()
        emotional = str(r.get("emotional_state") or "calm").strip().lower()
        if emotional not in ("calm", "angry", "worried", "grateful", "conflicted",
                             "amused", "determined", "fearful"):
            emotional = "calm"

        tension_with = r.get("tension_with")
        if tension_with is not None and not isinstance(tension_with, str):
            tension_with = None

        banter = r.get("banter_line")
        if banter is not None:
            banter = str(banter).strip() or None

        valid.append({
            "companion_id": cid,
            "affinity_delta": delta,
            "spoken_reaction": spoken,
            "emotional_state": emotional,
            "tension_with": tension_with,
            "banter_line": banter,
        })

    return valid if valid else None


def generate_companion_reactions(
    *,
    party: list[str],
    party_traits: dict[str, dict[str, int]],
    affinity_map: dict[str, int],
    mechanic_result: Any,
    companion_getter: Any,
    recent_narrative: str = "",
    llm: Any | None = None,
) -> list[dict[str, Any]]:
    """Generate authoritative companion reactions via LLM.

    Returns list of dicts with: companion_id, affinity_delta, spoken_reaction,
    emotional_state, tension_with, banter_line.

    Raises on failure — no deterministic fallback.

    V12.0: Optional ``llm`` parameter allows cloud-resolved AgentLLM injection.
    """
    if not party or not mechanic_result:
        return []

    # Normalize mechanic_result
    if isinstance(mechanic_result, dict):
        mr = mechanic_result
    elif hasattr(mechanic_result, "model_dump"):
        mr = mechanic_result.model_dump(mode="json")
    else:
        mr = {"outcome_summary": str(mechanic_result), "tone_tag": "NEUTRAL"}

    # Build companion profiles
    companions = []
    for cid in party:
        comp = companion_getter(cid) if callable(companion_getter) else None
        if not comp:
            continue

        name = comp.get("name") or cid
        voice = comp.get("voice_profile") or comp.get("personality") or {}
        if isinstance(voice, str):
            voice = {"personality": voice}

        affinity = affinity_map.get(cid, 0)
        arc = companion_arc_stage(affinity)

        companions.append({
            "id": cid,
            "name": name,
            "personality": voice.get("personality") or voice.get("speech_style") or "reserved",
            "speech_pattern": voice.get("speech_pattern") or voice.get("dialect") or "direct",
            "values": voice.get("values") or voice.get("core_values") or "survival",
            "arc_stage": arc,
            "affinity": affinity,
        })

    if not companions:
        return []

    if llm is None:
        llm = AgentLLM("companion_system")
    user_prompt = _build_context(companions, mr, recent_narrative)

    raw = llm.complete(_SYSTEM_PROMPT, user_prompt, json_mode=True, raw_json_mode=True)
    logger.debug("CompanionSystem raw output (first 600 chars): %s", (raw or "")[:600])

    reactions = _parse_reactions(raw)

    # Retry once
    if reactions is None:
        logger.info("CompanionSystem: first attempt failed to parse, retrying")
        correction = (
            "Your previous output was not valid JSON. Output ONLY a JSON object with "
            '"reactions" array. Each element: companion_id, affinity_delta (-5..5), '
            "spoken_reaction (1-2 sentences), emotional_state, tension_with, banter_line.\n\n"
            + user_prompt
        )
        raw2 = llm.complete(_SYSTEM_PROMPT, correction, json_mode=True, raw_json_mode=True)
        reactions = _parse_reactions(raw2)

    if reactions is None:
        raise ValueError(
            f"CompanionSystem: LLM failed to produce valid reactions after retry. "
            f"Raw (first 300 chars): {(raw or '')[:300]}"
        )

    # Filter to only companions that are actually in the party
    party_set = set(party)
    reactions = [r for r in reactions if r["companion_id"] in party_set]

    logger.info("CompanionSystem: generated reactions for %d companions", len(reactions))
    return reactions
