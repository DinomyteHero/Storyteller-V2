"""Narrative validator node: post-narration validation against ledger and mechanic facts (no LLM, no DB)."""
from __future__ import annotations

import logging
import re
from typing import Any

from backend.app.core.warnings import add_warning

logger = logging.getLogger(__name__)

# Success language patterns that should not appear when mechanic_result.success=False
_SUCCESS_PATTERNS = [
    re.compile(r"\bsucceed(?:s|ed)?\b", re.I),
    re.compile(r"\bmanage[ds]?\s+to\b", re.I),
    re.compile(r"\baccomplish(?:es|ed)?\b", re.I),
    re.compile(r"\bpull(?:s|ed)?\s+(?:it\s+)?off\b", re.I),
    re.compile(r"\bnailed\s+it\b", re.I),
]

# Failure language patterns that should not appear when mechanic_result.success=True
_FAILURE_PATTERNS = [
    re.compile(r"\bfail(?:s|ed)?\b", re.I),
    re.compile(r"\bmiss(?:es|ed)?\b", re.I),
    re.compile(r"\bfumble[ds]?\b", re.I),
]


def _check_mechanic_consistency(
    final_text: str,
    mechanic_result: dict[str, Any] | None,
) -> list[str]:
    """Check that final_text does not contradict mechanic outcome."""
    warnings: list[str] = []
    if not mechanic_result or not final_text:
        return warnings
    success = mechanic_result.get("success")
    if success is None:
        return warnings  # No check/roll this turn

    if success is False:
        for pat in _SUCCESS_PATTERNS:
            if pat.search(final_text):
                warnings.append(
                    f"NarrativeValidator: narrator used success language ('{pat.pattern}') "
                    f"but mechanic_result.success=False."
                )
                break  # one warning per category

    if success is True:
        for pat in _FAILURE_PATTERNS:
            if pat.search(final_text):
                warnings.append(
                    f"NarrativeValidator: narrator used failure language ('{pat.pattern}') "
                    f"but mechanic_result.success=True."
                )
                break

    return warnings


def _check_constraint_contradictions(
    final_text: str,
    constraints: list[str],
) -> list[str]:
    """Disabled (V3.0): too many false positives in Star Wars context.

    Previously checked for negation keywords near constraint keywords in a 40-char
    window, but the heuristic was too crude and flagged legitimate prose constantly.
    Kept as no-op for API compatibility.
    """
    return []


def _check_dialogue_turn_validity(state: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Validate DialogueTurn components. Returns (warnings, repairs_applied)."""
    warnings: list[str] = []
    repairs: list[str] = []

    # Check 1: player_responses count (3-6)
    responses = state.get("player_responses") or []
    if responses and len(responses) < 3:
        warnings.append(f"Only {len(responses)} player_responses (need 3-6)")
    if len(responses) > 6:
        state["player_responses"] = responses[:6]
        repairs.append("Trimmed player_responses to 6")

    # Check 2: response display_text non-empty
    for r in responses:
        if isinstance(r, dict) and not (r.get("display_text") or "").strip():
            warnings.append(f"Empty display_text in response {r.get('id')}")

    # Check 3: targets valid vs scene_frame
    scene_frame = state.get("scene_frame") or {}
    npc_ids = {n.get("id", "") for n in scene_frame.get("present_npcs", []) if n.get("id")}
    for r in responses:
        if not isinstance(r, dict):
            continue
        action = r.get("action") or {}
        target = action.get("target")
        if target and target not in npc_ids and action.get("intent") not in ("observe", "leave", "travel"):
            warnings.append(f"Response {r.get('id')} targets '{target}' not in scene NPCs")

    # Check 4: npc_utterance speaker valid
    npc_utterance = state.get("npc_utterance") or {}
    speaker = npc_utterance.get("speaker_id", "")
    if speaker and speaker != "narrator" and npc_ids and speaker not in npc_ids:
        warnings.append(f"NPC utterance speaker '{speaker}' not in scene NPCs")

    # Check 5: narration doesn't contain numbered lists
    final_text = state.get("final_text") or ""
    if re.search(r"^\s*[1-4]\.\s+[A-Z]", final_text, re.MULTILINE):
        warnings.append("Narration contains numbered list pattern")
    if re.search(r"what (?:do you do|will you do|would you do)\??", final_text, re.I):
        warnings.append("Narration contains 'What do you do?' meta-prompt")

    # ── V2.18: KOTOR-soul depth checks (warning-only, non-blocking) ──

    # Check 6: Topic anchoring — NPC utterance references topic_primary
    topic = scene_frame.get("topic_primary", "") if isinstance(scene_frame, dict) else ""
    utt_text = (npc_utterance.get("text") or "").lower()
    if topic and utt_text and topic.lower() not in utt_text:
        # Loose check: any word from topic appears in utterance
        topic_words = set(topic.lower().split())
        utt_words = set(re.findall(r"[a-z]+", utt_text))
        if not (topic_words & utt_words):
            warnings.append(f"NPC utterance does not reference scene topic '{topic}'")

    # Check 7: Response topic anchoring — responses reference NPC utterance or topic
    if topic and utt_text and len(responses) >= 3:
        anchor_words = set(re.findall(r"[a-z]{3,}", utt_text))
        if topic:
            anchor_words |= set(topic.lower().split())
        unanchored = 0
        for r in responses:
            if not isinstance(r, dict):
                continue
            display = (r.get("display_text") or "").lower()
            resp_words = set(re.findall(r"[a-z]{3,}", display))
            if not (anchor_words & resp_words):
                unanchored += 1
        if unanchored > len(responses) // 2:
            warnings.append(f"{unanchored}/{len(responses)} responses don't reference NPC utterance or topic")

    # Check 8: Voice consistency — NPC has voice_profile with tell
    if speaker and speaker != "narrator":
        present_npcs = scene_frame.get("present_npcs") or []
        for npc in present_npcs:
            if npc.get("id") == speaker:
                vp = npc.get("voice_profile") or {}
                if vp.get("tell") and utt_text:
                    # Just log for monitoring — don't warn unless tell is completely absent
                    # This is informational for future repair iterations
                    pass
                break

    # Check 9: Depth policy — meaning_tag variety (>=3 distinct for 4+ options)
    if len(responses) >= 4:
        meaning_tags = set()
        for r in responses:
            if isinstance(r, dict):
                mt = r.get("meaning_tag", "")
                if mt:
                    meaning_tags.add(mt)
        if meaning_tags and len(meaning_tags) < 3:
            warnings.append(f"Only {len(meaning_tags)} distinct meaning_tags for {len(responses)} responses (need >=3)")

    # Check 10: Depth policy — tone variety (>=3 distinct for 4+ options)
    if len(responses) >= 4:
        tone_tags = set()
        for r in responses:
            if isinstance(r, dict):
                tt = r.get("tone_tag", "")
                if tt:
                    tone_tags.add(tt)
        if tone_tags and len(tone_tags) < 3:
            warnings.append(f"Only {len(tone_tags)} distinct tone_tags for {len(responses)} responses (need >=3)")

    # Check 11: NPC line count — max 4 lines
    if utt_text:
        line_count = len([l for l in utt_text.strip().split("\n") if l.strip()])
        if line_count > 4:
            warnings.append(f"NPC utterance has {line_count} lines (max 4)")

    # Check 12: Response word count — max 16 words each
    for r in responses:
        if not isinstance(r, dict):
            continue
        display = (r.get("display_text") or "").strip()
        word_count = len(display.split())
        if word_count > 16:
            warnings.append(f"Response {r.get('id')} has {word_count} words (max 16)")

    return warnings, repairs


def narrative_validator_node(state: dict[str, Any]) -> dict[str, Any]:
    """Post-narration validation: check final_text against mechanic and ledger. Non-blocking."""
    final_text = state.get("final_text") or ""
    mechanic_result = state.get("mechanic_result") or {}

    # Get ledger constraints
    campaign = state.get("campaign") or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ledger = ws.get("ledger") if isinstance(ws, dict) else {}
    if not isinstance(ledger, dict):
        ledger = {}
    constraints = ledger.get("constraints") or []

    validation_warnings: list[str] = []

    # Check 1: Mechanic consistency
    validation_warnings.extend(
        _check_mechanic_consistency(final_text, mechanic_result)
    )

    # Check 2: Constraint contradictions
    validation_warnings.extend(
        _check_constraint_contradictions(final_text, constraints)
    )

    # Check 3: V2.17 DialogueTurn component validity
    dt_warnings, dt_repairs = _check_dialogue_turn_validity(state)
    validation_warnings.extend(dt_warnings)
    if dt_repairs:
        for r in dt_repairs:
            logger.info("NarrativeValidator repair: %s", r)

    # Propagate warnings (non-blocking: let narration through)
    existing_warnings = list(state.get("warnings") or [])
    for w in validation_warnings:
        if w not in existing_warnings:
            existing_warnings.append(w)
        logger.warning(w)

    return {
        **state,
        "warnings": existing_warnings,
        "validation_notes": validation_warnings,
    }
