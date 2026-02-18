"""CompanionVoiceAgent — V4.1.

Generates contextual spoken reactions for each active companion using their voice profile,
relationship arc stage, and what just happened in the turn. Results are stored in
world_state_json["companion_spoken_reactions"] = {companion_id: spoken_line}.

This replaces the silent "+N affinity" display with actual character voice.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.core.llm_provider import LLMMessage, get_llm_provider
from backend.app.core.companion_reactions import companion_arc_stage

logger = logging.getLogger(__name__)

_PROVIDER = None


def _get_provider():
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = get_llm_provider("narrator")  # reuse narrator provider (fast model)
    return _PROVIDER


_SYSTEM_PROMPT = """You are a character voice writer for an interactive narrative RPG.
Your job: write a brief spoken reaction (1-2 sentences, max 20 words) for a companion character,
in their authentic voice, responding to what the player just did.

Rules:
- Write in first person ("I...", "We...", "You...") as the companion speaking
- Match the companion's personality and relationship arc stage exactly
- Reference what actually happened — don't be generic
- STRANGER companions react cautiously; LOYAL companions react with deep familiarity
- If affinity_delta > 0, the companion is pleased/impressed; if < 0, they're troubled/critical
- Output ONLY valid JSON with the structure: {"companion_id": "...", "spoken_line": "..."}
- spoken_line must be 1-2 short sentences, punchy, in-world dialect"""


def _build_prompt(
    companion_id: str,
    companion_name: str,
    voice_profile: dict,
    arc_stage: str,
    affinity: int,
    affinity_delta: int,
    outcome_summary: str,
    tone_tag: str,
    mechanic_success: bool | None,
) -> str:
    personality = voice_profile.get("personality") or voice_profile.get("speech_style") or "reserved"
    speech_pattern = voice_profile.get("speech_pattern") or voice_profile.get("dialect") or "direct"
    values = voice_profile.get("values") or voice_profile.get("core_values") or "survival"

    approval = "pleased" if affinity_delta > 0 else ("troubled" if affinity_delta < 0 else "neutral")
    outcome_word = "succeeded" if mechanic_success else "failed" if mechanic_success is False else "acted"

    return f"""Companion: {companion_name} ({companion_id})
Personality: {personality}
Speech pattern: {speech_pattern}
Core values: {values}
Relationship stage: {arc_stage} (affinity {affinity}/100, delta this turn: {affinity_delta:+d})

What just happened: {outcome_summary}
Player tone: {tone_tag}
Player {outcome_word}.
Companion feeling: {approval}

Write {companion_name}'s spoken reaction (1-2 sentences, ≤20 words).
JSON only: {{"companion_id": "{companion_id}", "spoken_line": "..."}}"""


def generate_spoken_reactions(
    party: list[str],
    party_traits: dict[str, dict[str, int]],
    affinity_map: dict[str, int],
    affinity_deltas: dict[str, int],
    mechanic_result: Any,
    companion_getter: Any,  # callable: get_companion_by_id
) -> dict[str, str]:
    """Generate spoken reactions for all active companions. Returns {companion_id: spoken_line}.

    Non-fatal: any per-companion failure just skips that companion."""
    if not party or not mechanic_result:
        return {}

    # Extract mechanic context
    if isinstance(mechanic_result, dict):
        outcome_summary = mechanic_result.get("outcome_summary") or "an action was taken"
        tone_tag = mechanic_result.get("tone_tag") or "NEUTRAL"
        success = mechanic_result.get("success")
    else:
        outcome_summary = getattr(mechanic_result, "outcome_summary", None) or "an action was taken"
        tone_tag = getattr(mechanic_result, "tone_tag", None) or "NEUTRAL"
        success = getattr(mechanic_result, "success", None)

    reactions: dict[str, str] = {}
    provider = _get_provider()

    for companion_id in party:
        try:
            comp = companion_getter(companion_id)
            if not comp:
                continue

            comp_name = comp.get("name") or companion_id
            voice_profile = comp.get("voice_profile") or comp.get("personality") or {}
            if isinstance(voice_profile, str):
                # Some companions store voice as a string descriptor
                voice_profile = {"personality": voice_profile}

            affinity = affinity_map.get(companion_id, 0)
            delta = affinity_deltas.get(companion_id, 0)
            arc_stage = companion_arc_stage(affinity)

            prompt_text = _build_prompt(
                companion_id=companion_id,
                companion_name=comp_name,
                voice_profile=voice_profile,
                arc_stage=arc_stage,
                affinity=affinity,
                affinity_delta=delta,
                outcome_summary=outcome_summary,
                tone_tag=tone_tag,
                mechanic_success=success,
            )

            messages = [
                LLMMessage(role="system", content=_SYSTEM_PROMPT),
                LLMMessage(role="user", content=prompt_text),
            ]
            raw = provider.complete(messages, temperature=0.85, max_tokens=100)
            if not raw:
                continue

            # Parse JSON response
            raw_stripped = raw.strip()
            if raw_stripped.startswith("```"):
                # Strip code fences if present
                lines = raw_stripped.split("\n")
                raw_stripped = "\n".join(
                    line for line in lines if not line.startswith("```")
                )
            parsed = json.loads(raw_stripped)
            spoken_line = str(parsed.get("spoken_line") or "").strip()
            if spoken_line:
                reactions[companion_id] = spoken_line

        except Exception:
            logger.debug("CompanionVoiceAgent: failed for %s", companion_id, exc_info=True)

    return reactions
