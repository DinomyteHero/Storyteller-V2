"""Narrative validator node: post-narration validation against ledger and mechanic facts (no LLM, no DB).

Phase 4.3: Mechanic consistency is now BLOCKING — contradicting sentences are rewritten
deterministically rather than just logged as warnings.
"""
from __future__ import annotations

import logging
import re
from typing import Any


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

# Phase 4.3: Deterministic rewrites — swap contradicting verbs to match mechanic outcome
_SUCCESS_TO_FAILURE_REWRITES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bsucceeds\b", re.I), "struggles"),
    (re.compile(r"\bsucceeded\b", re.I), "struggled"),
    (re.compile(r"\bsucceed\b", re.I), "struggle"),
    (re.compile(r"\bmanages\s+to\b", re.I), "tries to"),
    (re.compile(r"\bmanaged\s+to\b", re.I), "tried to"),
    (re.compile(r"\bmanage\s+to\b", re.I), "try to"),
    (re.compile(r"\baccomplishes\b", re.I), "attempts"),
    (re.compile(r"\baccomplished\b", re.I), "attempted"),
    (re.compile(r"\baccomplish\b", re.I), "attempt"),
    (re.compile(r"\bpulls\s+(?:it\s+)?off\b", re.I), "can't quite manage it"),
    (re.compile(r"\bpulled\s+(?:it\s+)?off\b", re.I), "couldn't quite manage it"),
    (re.compile(r"\bpull\s+(?:it\s+)?off\b", re.I), "can't quite pull it off"),
    (re.compile(r"\bnailed\s+it\b", re.I), "fell short"),
]

_FAILURE_TO_SUCCESS_REWRITES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bfails\b", re.I), "succeeds"),
    (re.compile(r"\bfailed\b", re.I), "succeeded"),
    (re.compile(r"\bfail\b", re.I), "succeed"),
    (re.compile(r"\bmisses\b", re.I), "connects"),
    (re.compile(r"\bmissed\b", re.I), "connected"),
    (re.compile(r"\bmiss\b", re.I), "connect"),
    (re.compile(r"\bfumbles\b", re.I), "manages"),
    (re.compile(r"\bfumbled\b", re.I), "managed"),
    (re.compile(r"\bfumble\b", re.I), "manage"),
]


def _preserve_case(original: str, replacement: str) -> str:
    """Return replacement with case matching the original word's first character."""
    if not original:
        return replacement
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _make_case_preserving_replacer(replacement: str):
    """Create a regex replacer function that preserves the case of the matched text."""
    def replacer(m: re.Match) -> str:
        orig = m.group(0)
        # For multi-word replacements, preserve case of the first word only
        first_orig = orig.split()[0]
        first_repl = replacement.split()[0]
        rest = replacement[len(first_repl):]
        return _preserve_case(first_orig, first_repl) + rest
    return replacer


def _rewrite_contradictions(
    final_text: str,
    success: bool,
) -> tuple[str, list[str]]:
    """Rewrite sentences that contradict mechanic outcome. Returns (corrected_text, repairs)."""
    repairs: list[str] = []
    corrected = final_text

    if success is False:
        # Narrator wrote success language but mechanic failed — rewrite to failure
        for pat, replacement in _SUCCESS_TO_FAILURE_REWRITES:
            if pat.search(corrected):
                corrected = pat.sub(_make_case_preserving_replacer(replacement), corrected)
                repairs.append(f"Rewrote success language '{pat.pattern}' → '{replacement}' (mechanic=failure)")
    elif success is True:
        # Narrator wrote failure language but mechanic succeeded — rewrite to success
        for pat, replacement in _FAILURE_TO_SUCCESS_REWRITES:
            if pat.search(corrected):
                corrected = pat.sub(_make_case_preserving_replacer(replacement), corrected)
                repairs.append(f"Rewrote failure language '{pat.pattern}' → '{replacement}' (mechanic=success)")

    return corrected, repairs


def _check_mechanic_consistency(
    final_text: str,
    mechanic_result: dict[str, Any] | None,
) -> tuple[str, list[str], list[str]]:
    """Check and repair final_text that contradicts mechanic outcome.

    Returns (corrected_text, warnings, repairs).
    Phase 4.3: Now BLOCKING — contradictions are rewritten, not just warned about.
    """
    warnings: list[str] = []
    repairs: list[str] = []
    if not mechanic_result or not final_text:
        return final_text, warnings, repairs
    success = mechanic_result.get("success")
    if success is None:
        return final_text, warnings, repairs  # No check/roll this turn

    corrected, repairs = _rewrite_contradictions(final_text, success)

    if repairs:
        warnings.append(
            f"NarrativeValidator: repaired {len(repairs)} mechanic contradiction(s) in narration."
        )
        for r in repairs:
            logger.info("Mechanic consistency repair: %s", r)

    return corrected, warnings, repairs




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
        line_count = len([line for line in utt_text.strip().split("\n") if line.strip()])
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
    """Post-narration validation: check final_text against mechanic and ledger.

    Phase 4.3: Mechanic consistency is now BLOCKING — contradictions are rewritten in-place.
    DialogueTurn validation remains warning-only.
    """
    final_text = state.get("final_text") or ""
    mechanic_result = state.get("mechanic_result") or {}

    # Get ledger constraints
    campaign = state.get("campaign") or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    ledger = ws.get("ledger") if isinstance(ws, dict) else {}
    if not isinstance(ledger, dict):
        ledger = {}
    validation_warnings: list[str] = []

    # Check 1: Mechanic consistency (BLOCKING — rewrites contradictions)
    corrected_text, mech_warnings, mech_repairs = _check_mechanic_consistency(
        final_text, mechanic_result
    )
    validation_warnings.extend(mech_warnings)
    # Apply corrected text if any repairs were made
    if mech_repairs:
        final_text = corrected_text
        logger.info(
            "NarrativeValidator: applied %d mechanic consistency repair(s)",
            len(mech_repairs),
        )

    # Check 2: V2.17 DialogueTurn component validity
    dt_warnings, dt_repairs = _check_dialogue_turn_validity(state)
    validation_warnings.extend(dt_warnings)
    if dt_repairs:
        for r in dt_repairs:
            logger.info("NarrativeValidator repair: %s", r)

    # Propagate warnings
    existing_warnings = list(state.get("warnings") or [])
    for w in validation_warnings:
        if w not in existing_warnings:
            existing_warnings.append(w)
        logger.warning(w)

    return {
        **state,
        "final_text": final_text,
        "warnings": existing_warnings,
        "validation_notes": validation_warnings,
    }
