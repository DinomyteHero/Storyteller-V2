"""Narrator agent: generates narrative from state, mechanic result, director instructions, lore (grounded)."""
from __future__ import annotations

import re
import logging
from typing import Callable, Iterator

from backend.app.models.state import GameState
from backend.app.models.narration import NarrationOutput, NarrationCitation
from backend.app.models.dialogue_turn import NPCUtterance
from backend.app.core.agents.base import AgentLLM, ensure_json
from backend.app.config import (
    DEV_CONTEXT_STATS,
    get_role_max_input_tokens,
    get_role_reserved_output_tokens,
)
from backend.app.core.context_budget import BudgetReport, build_context
from backend.app.core.error_handling import log_error_with_context
from backend.app.core.ledger import format_ledger_for_prompt
from backend.app.core.agent_utils import (
    call_retriever,
    collect_related_npc_ids,
    format_lore_bullets,
    format_voice_snippets,
)
from backend.app.core.warnings import add_warning

logger = logging.getLogger(__name__)

# Lore chunk dict: text, source_title, chapter_title, chunk_id, metadata, score
LoreChunk = dict

# Voice snippet for character voice retrieval
VoiceSnippet = dict  # character_id, era, text, chunk_id


_LOCATION_NARRATIVE_NAMES: dict[str, str] = {
    "loc-cantina": "a cantina",
    "loc-tavern": "a cantina",  # legacy alias
    "loc-marketplace": "the marketplace",
    "loc-market": "the marketplace",  # legacy alias
    "loc-docking-bay": "the docking bay",
    "loc-docks": "the docking bay",  # legacy alias
    "loc-lower-streets": "the lower streets",
    "loc-street": "the lower streets",  # legacy alias
    "loc-hangar": "the hangar bay",
    "loc-spaceport": "the spaceport",
    "loc-command-center": "the command center",
    "loc-med-bay": "the med bay",
    "loc-jedi-temple": "the Jedi Temple",
}


def _humanize_location(loc_id: str | None) -> str:
    """Convert a raw location ID into a narrative-friendly Star Wars name.

    Uses a known lookup table first, then falls back to generic cleanup.
    Examples: loc-cantina -> a cantina, loc-docking-bay -> the docking bay.
    """
    if not loc_id:
        return ""
    raw = loc_id.strip()
    if not raw:
        return ""
    # Check known narrative names first
    display = _LOCATION_NARRATIVE_NAMES.get(raw.lower())
    if display:
        return display
    # Fallback: strip prefix and format
    cleaned = raw
    for prefix in ("loc-", "loc_", "location-", "location_"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    cleaned = cleaned.replace("-", " ").replace("_", " ").strip()
    if not cleaned:
        return raw
    # If single common word, add article
    words = cleaned.split()
    if len(words) == 1:
        return f"the {cleaned}"
    return cleaned.title()


def _build_lore_query(state: GameState) -> str:
    """Build a lore retrieval query from location, user input, and mechanic summary."""
    parts = []
    loc = state.current_location
    if loc:
        parts.append(loc)
    user = (state.user_input or "").strip()
    if user:
        parts.append(user)
    if state.mechanic_result:
        parts.append(state.mechanic_result.action_type)
        for fact in (state.mechanic_result.narrative_facts or [])[:3]:
            parts.append(fact)
    return " ".join(parts) if parts else "setting scene"


def _summarize_mechanic_events(state: GameState) -> str:
    """Summarize mechanic_result events as facts for the narrator (no invention)."""
    if not state.mechanic_result or not state.mechanic_result.events:
        return "(No mechanical events this turn.)"
    lines = []
    for ev in state.mechanic_result.events:
        t = getattr(ev, "event_type", None) or (ev.get("event_type") if isinstance(ev, dict) else "")
        p = getattr(ev, "payload", None) or (ev.get("payload") if isinstance(ev, dict) else {}) or {}
        if t == "DAMAGE":
            amt = p.get("amount", 0)
            lines.append(f"You take {amt} damage.")
        elif t == "HEAL":
            amt = p.get("amount", 0)
            lines.append(f"You are healed for {amt}.")
        elif t == "MOVE" or t == "TRAVEL":
            to_loc = p.get("to_location", "")
            lines.append(f"You travel to {to_loc}.")
        elif t == "DIALOGUE":
            text = p.get("text", "")[:80]
            lines.append(f"Player said: {text}")
        else:
            lines.append(f"[{t}] {p}")
    return "\n".join(lines) if lines else "(No mechanical events this turn.)"


def _collect_character_ids(state: GameState) -> list[str]:
    """Collect character IDs for voice retrieval: present NPCs, party members, optionally player."""
    ids: list[str] = []
    seen: set[str] = set()
    npcs = state.present_npcs or []
    for n in npcs:
        cid = n.get("id")
        if cid and str(cid).strip() and cid not in seen:
            ids.append(str(cid).strip())
            seen.add(cid)
    campaign = state.campaign or {}
    party = campaign.get("party") or []
    for cid in party:
        if cid and str(cid).strip() and cid not in seen:
            ids.append(str(cid).strip())
            seen.add(cid)
    return ids






def _quote_excerpt(text: str, max_words: int = 20) -> str:
    """Return first max_words words of text."""
    words = text.split()
    return " ".join(words[:max_words]) if words else ""



_PATTERN_FIRE_COUNTS: dict[str, int] = {}
"""Track how often each cleanup pattern fires. Inspect via get_pattern_fire_counts()
to identify patterns that can be retired as prompts improve."""


def _track_sub(name: str, text: str, pattern: str, repl: str = "", flags: int = 0) -> str:
    """Apply regex substitution and track if the pattern matched."""
    result = re.sub(pattern, repl, text, flags=flags)
    if result != text:
        _PATTERN_FIRE_COUNTS[name] = _PATTERN_FIRE_COUNTS.get(name, 0) + 1
    return result


def get_pattern_fire_counts() -> dict[str, int]:
    """Return current pattern fire counts for monitoring prompt quality improvement."""
    return dict(_PATTERN_FIRE_COUNTS)


def _strip_structural_artifacts(text: str) -> str:
    """Strip structural markdown artifacts that LLMs inject into narrative prose.

    Local models (especially qwen/llama) often add section headers, JSON code
    blocks, and metadata sections instead of clean prose. This aggressively
    removes all of those patterns so only narrative prose remains.

    Pattern fire counts are tracked in _PATTERN_FIRE_COUNTS for monitoring.
    """
    result = text

    # Strip fenced code blocks (```json ... ```, ```text ... ```, etc.)
    result = _track_sub("fenced_code_blocks", result, r"```[\w]*\s*\n?.*?```", flags=re.DOTALL)

    # Strip inline JSON objects that span multiple lines: { "key": ... }
    # Only if they look like LLM structured output (contain "text", "event", "description", etc.)
    result = _track_sub(
        "inline_json_objects", result,
        r'\{\s*"(?:text|event|description|dialogue|narrative|scene|next_turn|actions?|suggestions?)"'
        r"\s*:.*?\}",
        flags=re.DOTALL,
    )

    # Strip markdown bold headers: **Scene:**, **Narrative:**, **Next Turn:**, **Opening:**, etc.
    result = _track_sub(
        "markdown_bold_headers", result,
        r"\*{1,2}(?:Scene|Narrative|Next Turn|Opening|Opening Scene|Summary|"
        r"Description|Dialogue|Action|Actions|Response|Output|Result|"
        r"Turn \d+|Current Scene|Setting|Atmosphere|Continue|Continuation):?\*{1,2}\s*:?\s*",
        flags=re.IGNORECASE,
    )

    # Strip bare section headers without markdown bold: "Scene:", "Narrative:", etc. at line start
    result = re.sub(
        r"^(?:Scene|Narrative|Next Turn|Opening|Summary|Description|Dialogue|"
        r"Action|Response|Output|Result|Setting|Atmosphere|Continue|Continuation)\s*:\s*",
        "",
        result,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # Strip "JSON with Citations:" helper headings (some models emit this without actual JSON)
    result = re.sub(
        r"^\s*JSON\s+with\s+Citation(?:s)?\s*:\s*$",
        "",
        result,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # Strip "---" horizontal rule separators that aren't companion banter markers
    # (Companion banter uses "\n\n---\n\n" which is handled by render_scene)
    result = re.sub(r"^-{3,}\s*$", "", result, flags=re.MULTILINE)

    # Strip lines that are purely markdown headers: ## Something, # Something
    result = re.sub(r"^#{1,3}\s+.+$", "", result, flags=re.MULTILINE)

    # Strip trailing/leading metadata like "Turn: 1", "Location: cantina", etc.
    result = re.sub(
        r"^(?:Turn|Location|Time|Character|Player|NPC|Era|Campaign)\s*:\s*.+$",
        "",
        result,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # Strip <think>...</think> tags from reasoning models (qwen3, deepseek, etc.)
    result = _track_sub("think_tags", result, r"<think>.*?</think>", flags=re.DOTALL)

    # V2.15: Strip "Option N (Tone):" inline choice blocks that LLMs inject
    result = re.sub(
        r"\n*\s*Option\s+\d+\s*\([^)]*\)\s*:.*?(?=\nOption\s+\d|\n\n|\Z)",
        "",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # V2.15: Strip meta-game sections that break immersion
    # "Scene Continuation", "Potential Complications", "Next Steps", etc.
    # Everything from the section header to end-of-text is garbage.
    result = re.sub(
        r"\n+\s*\*{0,2}(?:Scene\s+Continuation|Potential\s+Complications?|Next\s+Steps?|"
        r"Stress\s+Level\s+Monitoring|Character\s+(?:Sheet|Profile|Description)|"
        r"Voice(?:\s+Description)?|Personality(?:\s+Description)?|Background\s+Info(?:rmation)?|"
        r"Regardless\s+of\s+(?:player|your)\s+choice|NPC\s+Reactions?):?\*{0,2}.*",
        "",
        result,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # V2.15: Strip character sheet / stat block field lines
    result = re.sub(
        r"^\s*(?:Name|Species|Class|Traits?|Stats?|Appearance|Voice)\s*:.*$",
        "",
        result,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # V2.16b: Strip leaked LLM self-instructions (model echoing system prompt)
    result = _track_sub(
        "leaked_self_instructions", result,
        r"^\s*(?:Begin\s+with|Start\s+with|Open\s+with|Write\s+about|"
        r"Describe\s+the|Focus\s+on|Include|Make\s+sure|Remember\s+to|"
        r"Note\s+that|Keep\s+in\s+mind)\s+.*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # Collapse multiple blank lines into max 2
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


def _truncate_overlong_prose(text: str, max_words: int = 250) -> str:
    """Safety net: truncate prose that exceeds max_words to the last complete sentence.

    Local LLMs sometimes generate 500+ word dumps with character sheets,
    meta-game sections, and continuation prose. This caps the output to
    a reasonable CYOA-page length.

    V2.16b: Preserves paragraph breaks (\\n\\n) during truncation instead of
    collapsing everything into a single paragraph.
    """
    words = text.split()
    if len(words) <= max_words:
        return text
    # Split into paragraphs + separators, preserving \n\n boundaries
    parts = re.split(r"(\n\n+)", text)
    result_parts: list[str] = []
    word_count = 0
    for part in parts:
        # Separator chunk (blank lines) — keep as-is
        if re.match(r"\n\n+", part):
            result_parts.append(part)
            continue
        part_words = part.split()
        if word_count + len(part_words) <= max_words:
            result_parts.append(part)
            word_count += len(part_words)
        else:
            # Partial paragraph: take remaining words up to budget
            remaining = max_words - word_count
            if remaining > 0:
                partial = " ".join(part_words[:remaining])
                # Find last sentence boundary in partial
                last_sentence = max(partial.rfind("."), partial.rfind("!"), partial.rfind("?"))
                if last_sentence > len(partial) // 2:
                    partial = partial[:last_sentence + 1]
                result_parts.append(partial)
            break
    return "".join(result_parts).strip()


def _strip_embedded_suggestions(text: str) -> str:
    """Strip suggestion-like blocks from narrative text, keeping only prose.

    V2.16: Simplified — the Narrator is instructed to write prose only
    (via _prose_stop_rule), so most suggestion formats are rare. These
    patterns are retained as cheap insurance against model drift.
    """
    # Strip meta-narrator endings first ("What will you do?" etc.)
    text = _enforce_pov_consistency(text)

    # ── Numbered list at end: "1. Action text\n2. Action text\n..." ──
    text = re.sub(
        r"\n\s*\d+\.\s+.+(?:\n\s*\d+\.\s+.+){1,}\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # ── "What do you do?" header ──
    text = re.sub(
        r"\n*\*{0,2}What do you do\??\*{0,2}\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # ── Mid-text suggestion blocks: header + following list ──
    header_re = re.compile(
        r"^\s*\*{0,2}(?:Suggested\s+[Aa]ctions?|Possible\s+[Aa]ctions?|Options|You could|Your\s+(?:options|choices))\b.*$",
        re.IGNORECASE,
    )
    list_item_re = re.compile(r"^\s*(?:[-*]|\d+\.)\s+.+$")
    lines = text.splitlines()
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        if header_re.match(lines[i]):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            k = j
            item_count = 0
            while k < len(lines) and list_item_re.match(lines[k]):
                item_count += 1
                k += 1
            if item_count >= 2:
                i = k
                if i < len(lines) and not lines[i].strip():
                    i += 1
                continue
        out_lines.append(lines[i])
        i += 1
    text = "\n".join(out_lines)

    return text.rstrip()


# ---------------------------------------------------------------------------
# V2.17: NPC utterance extraction from ---NPC_LINE--- separator
# ---------------------------------------------------------------------------

_NPC_LINE_SEP = "---NPC_LINE---"

# Flexible regex: matches ---NPC_LINE---, -- NPC_LINE --, —NPC_LINE—, etc.
_NPC_LINE_REGEX = re.compile(
    r"-{2,3}\s*NPC[_\s-]?LINE\s*-{2,3}",
    re.IGNORECASE,
)


def _extract_npc_utterance(
    raw_text: str,
    present_npcs: list[dict],
) -> tuple[str, NPCUtterance]:
    """Split raw narrator output into prose + NPCUtterance.

    Expected format from the LLM:
        [Prose paragraphs]
        ---NPC_LINE---
        SPEAKER: Draven Koss
        "I've been expecting you."

    Returns (prose_text, NPCUtterance).

    Fallback: if separator is missing, the entire text is treated as prose
    and the NPCUtterance is a narrator observation from the last sentence.
    """
    # Try flexible regex first (handles LLM format variations)
    sep_match = _NPC_LINE_REGEX.search(raw_text)
    if sep_match:
        parts = [raw_text[:sep_match.start()], raw_text[sep_match.end():]]
        prose = parts[0].strip()
        npc_block = parts[1].strip()

        # Parse SPEAKER: line
        speaker_name = "Narrator"
        speaker_id = "narrator"
        dialogue_text = npc_block

        speaker_match = re.match(
            r"SPEAKER:\s*(.+?)(?:\n|$)", npc_block, re.I
        )
        if speaker_match:
            speaker_name = speaker_match.group(1).strip()
            dialogue_text = npc_block[speaker_match.end():].strip()

        # Clean up dialogue text (remove wrapping quotes)
        dialogue_text = dialogue_text.strip().strip('"').strip("'").strip("\u201c\u201d").strip()

        # Resolve speaker_id against present_npcs
        if speaker_name.lower() != "narrator":
            for npc in present_npcs:
                npc_name = npc.get("name", "")
                if npc_name and npc_name.lower() == speaker_name.lower():
                    speaker_id = npc.get("id") or npc.get("character_id") or npc_name
                    speaker_name = npc_name
                    break
            else:
                # Name not found in present_npcs — keep as-is but use "narrator" id
                speaker_id = speaker_name.lower().replace(" ", "_")

        # Cap utterance length
        if len(dialogue_text) > 500:
            # Break at sentence boundary
            truncated = dialogue_text[:497]
            last_period = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
            if last_period > len(truncated) // 2:
                dialogue_text = truncated[:last_period + 1]
            else:
                dialogue_text = truncated.rstrip() + "..."

        return prose, NPCUtterance(
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            text=dialogue_text,
        )

    # Fallback: no separator found — extract last sentence as narrator observation
    prose = raw_text.strip()
    sentences = re.split(r'(?<=[.!?])\s+', prose)
    if sentences:
        last_sentence = sentences[-1].strip()
        return prose, NPCUtterance(
            speaker_id="narrator",
            speaker_name="Narrator",
            text=last_sentence[:500],
        )

    return prose, NPCUtterance(
        speaker_id="narrator",
        speaker_name="Narrator",
        text="The scene unfolds before you.",
    )


_META_NARRATOR_PATTERNS: list[re.Pattern] = [
    re.compile(r"\n*\s*What will you do.*\?\s*$", re.I),
    re.compile(r"\n*\s*What will your next move be.*\?\s*$", re.I),
    re.compile(r"\n*\s*The choice is yours.*$", re.I),
    re.compile(r"\n*\s*You have options here.*$", re.I),
    re.compile(r"\n*\s*What would you like to do.*\?\s*$", re.I),
    re.compile(r"\n*\s*The decision is yours.*$", re.I),
    re.compile(r"\n*\s*It'?s your (?:move|call|choice).*$", re.I),
    re.compile(r"\n*\s*What'?s your (?:move|next move|play).*\?\s*$", re.I),
    re.compile(r"\n*\s*[Cc]hoose wisely.*$", re.I),
    re.compile(r",\s*Hero[\.\!\?]?\s*$", re.I),
    re.compile(r"\n*\s*Each option leads you.*$", re.I),
    re.compile(r"\n*\s*The fate of .+ may (?:just )?depend on it.*$", re.I),
    # V2.13: Additional meta-narrator patterns observed in gameplay
    re.compile(r"\n*\s*So,?\s+what'?s?\s+it\s+gonna\s+be\??\s*$", re.I),
    re.compile(r"\n*\s*What\s+would\s+you\s+choose.*\?\s*$", re.I),
    re.compile(r"\n*\s*Do\s+(?:you|they)\s+take\s+(?:the|this)\s+.+\?\s*$", re.I),
    re.compile(r"\n*\s*(?:What|How)\s+do\s+you\s+(?:respond|react|decide)\??\s*$", re.I),
    re.compile(r"\n*\s*(?:Time|Now)\s+to\s+(?:decide|choose|make\s+(?:a|your)\s+(?:move|call|choice)).*$", re.I),
    re.compile(r"\n*\s*And\s+so,\s+\w+\s+made\s+\w+\s+choice.*$", re.I),
    re.compile(r"\n*\s*What\s+would\s+(?:you|he|she)\s+choose\??\s*$", re.I),
    re.compile(r"\n*\s*(?:Here|There)\s+(?:were|are)\s+(?:three|two|several)\s+paths.*$", re.I),
    # V2.16b: LLM instruction leakage patterns (model echoing system prompt)
    re.compile(r"\n*\s*Begin\s+with\s+a\s+sensory[- ]rich\s+description.*$", re.I),
    re.compile(r"\n*\s*The\s+player\s+can\s+choose\s+to\b.*$", re.I),
    re.compile(r"\n*\s*(?:You|The\s+player)\s+(?:may|can|could|might)\s+(?:choose|decide|opt)\s+to\b.*$", re.I),
    re.compile(r"\n*\s*(?:Consider|Remember)\s+(?:that|to)\s+.*$", re.I),
    # V2.20: Strip "What should [NAME] do" prompts (with all text following)
    re.compile(r"\n+\s*What\s+should\s+\w+\s+do.*", re.I | re.DOTALL),
]


def _enforce_pov_consistency(text: str) -> str:
    """Strip meta-narrator endings that break POV (e.g., 'What will you do, Corran?').

    These are game-master intrusions that break immersion. The Director
    generates choices separately — the Narrator should never embed them.
    """
    result = text
    for pattern in _META_NARRATOR_PATTERNS:
        result = pattern.sub("", result)
    return result.rstrip()


def _build_story_state_summary(state: GameState) -> str:
    """Build story state summary (never trimmed)."""
    loc = _humanize_location(state.current_location) or "the scene"
    campaign_id = state.campaign_id or ""
    npcs = state.present_npcs or []
    npc_lines = [f"- {n.get('name', 'Unknown')} ({n.get('role', '')})" for n in npcs if n.get("name")]
    npc_names_list = [n.get("name") for n in npcs if n.get("name")]
    if npc_lines:
        allowed_names_str = ", ".join(npc_names_list)
        npc_block = (
            f"ALLOWED NPC NAMES: {allowed_names_str}\n"
            + "\n".join(npc_lines)
            + "\nDo NOT use any character name not in this list. For unnamed background characters, describe them generically (e.g., 'a dock worker', 'the bartender')."
        )
    else:
        npc_block = "(No named NPCs present. Use only generic descriptions for any background characters.)"

    mechanic_summary = _summarize_mechanic_events(state)
    director_instructions = (state.director_instructions or "").strip() or "Keep pacing brisk. End with a decision point."
    # V2.15: Strip ALL suggestion-related guidance from Director instructions.
    # The Narrator writes prose only — it doesn't need suggestion context.
    director_instructions = re.sub(
        r"[^\n]*(?:Include|Consider|At least).*?[Ss]uggested?\s+(?:actions?|options?)[^\n]*\n?",
        "",
        director_instructions,
    )
    director_instructions = re.sub(
        r"\*{0,2}Suggested\s+[Aa]ctions?:?\*{0,2}\s*\n(?:(?!\n\n).)*",
        "",
        director_instructions,
        flags=re.DOTALL,
    )
    # Strip SUGGESTION CONTEXT sections entirely (no longer needed by Narrator)
    director_instructions = re.sub(
        r"## SUGGESTION CONTEXT[^\n]*\n(?:(?!##).)*",
        "",
        director_instructions,
        flags=re.DOTALL,
    )
    director_instructions = re.sub(r"\n{3,}", "\n\n", director_instructions).strip()
    if not director_instructions:
        director_instructions = "Keep pacing brisk. End with a decision point."

    # V2.5: Character psych_profile for tone
    psych = {}
    if state.player and getattr(state.player, "psych_profile", None):
        psych = state.player.psych_profile or {}
    current_mood = psych.get("current_mood", "neutral")
    stress_level = int(psych.get("stress_level", 0) or 0)
    psych_block = f"current_mood: {current_mood}, stress_level: {stress_level}, active_trauma: {psych.get('active_trauma') or 'none'}"

    # V2.5: Active rumors (last 3 is_public_rumor events)
    active_rumors = getattr(state, "active_rumors", None) or []
    rumors_block = "\n".join(f"- {r}" for r in active_rumors[:3]) if active_rumors else "(No recent public rumors.)"

    ledger = {}
    campaign = state.campaign or {}
    ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
    if isinstance(ws, dict):
        ledger = ws.get("ledger") or {}
    ledger_block = format_ledger_for_prompt(ledger)

    # V2.5: Open threads for narrative continuity
    open_threads = ledger.get("open_threads") or []
    if open_threads:
        threads_block = "\n".join(f"- {t}" for t in open_threads[:2])
    else:
        threads_block = "(No open threads.)"

    # V2.5: Critical outcome from mechanic
    critical_outcome_block = ""
    if state.mechanic_result:
        co = getattr(state.mechanic_result, "critical_outcome", None)
        if co == "CRITICAL_FAILURE":
            critical_outcome_block = (
                "## Critical Outcome\n"
                "CRITICAL FAILURE. Narrate dramatic consequences, complications, and environmental changes.\n\n"
            )
        elif co == "CRITICAL_SUCCESS":
            critical_outcome_block = (
                "## Critical Outcome\n"
                "CRITICAL SUCCESS. Narrate exceptional success with bonus effects.\n\n"
            )

    # V2.5: Explicit constraints and established facts
    constraints_list = ledger.get("constraints") or []
    facts_list = (ledger.get("established_facts") or [])[:5]
    constraints_line = ", ".join(constraints_list) if constraints_list else "(none)"
    facts_line = ", ".join(facts_list) if facts_list else "(none)"

    # Build recent narrative recap for continuity
    recent_narrative = getattr(state, "recent_narrative", None) or []
    if recent_narrative:
        narrative_recap = "\n\n".join(recent_narrative[-2:])  # last 2 turns max
    else:
        narrative_recap = "(This is the beginning of the story.)"

    # V2.6: POV character block (identity grounding for narrative perspective)
    pov_block = ""
    if state.player:
        player_name = state.player.name or "the protagonist"
        player_bg = getattr(state.player, "background", None) or ""
        pov_block = f"## POV Character\nName: {player_name}."
        if player_bg:
            pov_block += f" {player_bg}"
        # V2.8: Pronoun injection for gender-correct narration
        player_gender = getattr(state.player, "gender", None)
        if player_gender:
            from backend.app.core.pronouns import pronoun_block as _pronoun_block
            _pblock = _pronoun_block(player_name, player_gender)
            if _pblock:
                pov_block += f"\n{_pblock}"
        pov_block += (
            "\nWrite from this character's perspective — what THEY see, hear, sense, and feel. "
            "Ground every scene in their viewpoint. The reader experiences the world through their eyes."
        )
        # V2.7: Grammar check for confusing character names
        if player_name in ["Hero", "Protagonist", "Player", "Character"]:
            pov_block += (
                f"\n\nGRAMMAR NOTE: The character's name is '{player_name}'. "
                f"When writing dialogue, use it as a proper noun: 'You in, {player_name}?' NOT 'You {player_name}?'. "
                f"In narration, use: '{player_name} noticed...' NOT 'You {player_name}...'"
            )
        # V2.7: Player agency hard rule
        pov_block += (
            "\n\n## PLAYER AGENCY (HARD RULE)\n"
            "NEVER narrate the player character taking actions without player input. "
            "Describe what they PERCEIVE, HEAR, SENSE — not what they DO. "
            "Example GOOD: 'Corran felt the weight of the blaster at his hip.'\n"
            "Example BAD: 'Corran drew his blaster and fired.'\n"
            "End scenes with a MOMENT (sensory detail, NPC reaction, environment change), "
            "not an action the player hasn't chosen."
        )
        pov_block += "\n\n"

    # V2.10: Starship context for transport-aware narration
    _starship = getattr(state, "player_starship", None)
    if _starship and _starship.get("has_starship"):
        _ship_type = _starship.get("ship_type", "their ship")
        starship_block = f"Player's starship: {_ship_type}. They can pilot it and travel freely."
    else:
        starship_block = "Player has NO starship. Off-planet travel requires hiring passage, stowing away, or NPC transport."

    result = (
        f"## Story So Far (CRITICAL — your prose MUST continue from this)\n"
        f"{narrative_recap}\n\n"
        f"{pov_block}"
        f"## Campaign / Location\n"
        f"Campaign: {campaign_id}\n"
        f"Location: {loc}\n"
        f"{starship_block}\n\n"
        f"## Narrative Ledger (HARD CONSTRAINTS -- must obey)\n"
        f"{ledger_block}\n"
        f"CONSTRAINTS (MUST NOT CONTRADICT): {constraints_line}\n"
        f"ESTABLISHED FACTS (treat as canon): {facts_line}\n"
        f"If you are unsure about a fact, phrase it as rumor/speculation. Never contradict established facts.\n\n"
        f"## Open threads (reference 1-2 subtly to maintain continuity)\n"
        f"{threads_block}\n\n"
        f"## Character psych_profile (use for tone)\n"
        f"{psych_block}\n\n"
        f"## Present NPCs (ONLY these characters exist in this scene)\n"
        f"{npc_block}\n\n"
    )
    # 2.5: Background figures for atmosphere
    bg_figures = getattr(state, "background_figures", None) or []
    if bg_figures:
        bg_lines = "\n".join(f"- {f}" for f in bg_figures[:3])
        result += (
            f"## Background Figures (atmosphere only — NOT interactable, do NOT name them)\n"
            f"{bg_lines}\n"
            f"Mention 1-2 of these in passing to make the scene feel populated. They are scenery, not characters.\n\n"
        )
    result += (
        f"## Mechanic outcome (events--treat as facts)\n"
        f"{mechanic_summary}\n\n"
        f"{critical_outcome_block}"
        f"## Director instructions\n"
        f"{director_instructions}\n\n"
    )
    # Companion reactions block (1.2): inject companion emotional state into narration context
    companion_reactions_block = ""
    if isinstance(campaign, dict):
        cr_summary = campaign.get("companion_reactions_summary") or ""
        if cr_summary:
            companion_reactions_block = (
                f"## Companion Reactions This Turn\n"
                f"{cr_summary}\n"
                f"Weave companion reactions naturally into the scene — show them through body language, "
                f"facial expressions, and brief dialogue. Do NOT list them mechanically.\n\n"
            )
    result += companion_reactions_block
    # 3.2: Inter-party tensions block (companions at odds with each other)
    tensions_narrator = ""
    if isinstance(campaign, dict):
        tensions_narrator = campaign.get("inter_party_tensions_narrator") or ""
    if tensions_narrator:
        result += (
            f"## Inter-Party Tensions\n"
            f"{tensions_narrator}\n"
            f"Show this tension through body language or brief exchanges between companions.\n\n"
        )

    result += (
        f"## Active rumors (reference subtly if appropriate; do not derail scene)\n"
        f"{rumors_block}\n\n"
    )
    # Phase 3: Active themes for thematic resonance
    active_themes = ledger.get("active_themes") or []
    if active_themes:
        theme_names = ", ".join(t.replace("_", " ") for t in active_themes[:3])
        result += (
            f"## Active themes (weave subtly into prose)\n"
            f"{theme_names}\n\n"
        )

    # V2.18: Scene context for KOTOR-soul depth (topic anchoring, NPC agenda, subtext)
    scene_frame = getattr(state, "scene_frame", None) or {}
    if isinstance(scene_frame, dict):
        topic = scene_frame.get("topic_primary", "")
        topic_secondary = scene_frame.get("topic_secondary", "")
        subtext = scene_frame.get("subtext", "")
        npc_agenda = scene_frame.get("npc_agenda", "")
        style_tags = scene_frame.get("scene_style_tags") or []
        pressure = scene_frame.get("pressure") or {}
        if topic or subtext or npc_agenda:
            result += "## Scene Context (V2.18 — KOTOR-soul depth)\n"
            if topic:
                topic_line = topic
                if topic_secondary:
                    topic_line += f" / {topic_secondary}"
                result += f"- Topic: {topic_line}\n"
            if subtext:
                result += f"- Subtext (what this scene is REALLY about): {subtext}\n"
            if npc_agenda:
                result += f"- NPC Agenda (what the NPC wants from the player): {npc_agenda}\n"
            if style_tags:
                result += f"- Scene Style: {', '.join(style_tags)}\n"
            if pressure:
                alert = pressure.get("alert", "")
                heat = pressure.get("heat", "")
                if alert or heat:
                    parts = []
                    if alert:
                        parts.append(f"Alert: {alert}")
                    if heat:
                        parts.append(f"Heat: {heat}")
                    result += f"- Pressure: {' | '.join(parts)}\n"
            result += (
                "Use this context to guide NPC dialogue tone and topic. "
                "The NPC's spoken line (after ---NPC_LINE---) MUST relate to the topic above.\n\n"
            )

        # V2.18: Voice profile for present NPCs
        present_npcs = scene_frame.get("present_npcs") or []
        voice_profiles = []
        for npc in present_npcs:
            vp = npc.get("voice_profile") or {}
            if vp:
                name = npc.get("name", "Unknown")
                vp_parts = []
                if vp.get("belief"):
                    vp_parts.append(f"Belief: {vp['belief']}")
                if vp.get("wound"):
                    vp_parts.append(f"Wound: {vp['wound']}")
                if vp.get("taboo"):
                    vp_parts.append(f"Taboo: {vp['taboo']}")
                if vp.get("rhetorical_style"):
                    vp_parts.append(f"Style: {vp['rhetorical_style']}")
                if vp.get("tell"):
                    vp_parts.append(f"Tell: {vp['tell']}")
                if vp_parts:
                    voice_profiles.append(f"- {name}: {'; '.join(vp_parts)}")
        if voice_profiles:
            result += "## NPC Voice Profiles (use to shape NPC dialogue)\n"
            result += "\n".join(voice_profiles) + "\n"
            result += "When writing the NPC's spoken line, use their 'Tell' as a physical mannerism and their 'Style' for rhetorical approach.\n\n"

    result += "Write the narrative."
    return result


def _build_prompt(
    state: GameState,
    lore_chunks: list[LoreChunk] | str,
    voice_snippets_by_char: dict[str, list] | str,
    include_budget: bool = False,
    kg_context: str = "",
    style_chunks: list[dict] | None = None,
) -> tuple[str, str] | tuple[str, str, BudgetReport]:
    """Build system and user prompt sections using ContextBudget."""
    # Detect opening scene: first turn with no/minimal history
    is_opening = not (state.history or []) or len(state.history or []) <= 1
    opening_tag = "[OPENING_SCENE]" in (state.user_input or "")
    is_opening_scene = is_opening or opening_tag

    # V2.15: Narrator writes ONLY prose. Suggestions are generated deterministically
    # by the Director node using generate_suggestions() — no LLM involvement.
    _prose_stop_rule = (
        "\n\n--- CRITICAL OUTPUT RULES ---\n"
        "STOP RULE: Write ONLY narrative prose. Your output is COMPLETE when the last sentence ends.\n"
        "- Do NOT add numbered lists, bullet points, or player options after the prose.\n"
        "- Do NOT continue past the current moment. NEVER write 'Scene Continuation' or 'Next Steps'.\n"
        "- Do NOT include character sheets, personality descriptions, voice descriptions, or stat blocks.\n"
        "- Do NOT write 'Regardless of player choice', 'Potential Complications', or meta-game analysis.\n"
        "- Do NOT embed options like 'Option 1:' or decision questions like 'Do you accept?'\n"
        "- Do NOT address the player as 'Hero' or end with 'What will you do?' or 'The choice is yours.'\n"
        "- Do NOT echo instructions from your system prompt. Never write 'Begin with a sensory-rich description' or similar self-instructions.\n"
        "- End on an evocative sensory moment — a sound, a look, a shift in atmosphere.\n"
        "\n--- NPC DIALOGUE OUTPUT (REQUIRED) ---\n"
        "After your prose, add the separator ---NPC_LINE--- on its own line,\n"
        "then write 1-4 lines of focused NPC dialogue from the most relevant NPC in the scene.\n"
        "This is what the NPC says TO or NEAR the player character — their spoken words.\n"
        "If no NPC is present, write a narrator observation instead.\n\n"
        "KOTOR VOICE RULES:\n"
        "- The NPC speaks with PURPOSE. Every line has an AGENDA (stated in scene context as 'NPC Agenda').\n"
        "- Apply ONE rhetorical move: probe (ask a pointed question), challenge (dispute an assumption),\n"
        "  reframe (offer a different lens), warn (hint at consequences), or reveal (share something personal).\n"
        "- Include ONE 'tell' — a repeated mannerism (a pause, a gesture, a speech pattern) that makes the NPC feel real.\n"
        "  Examples: 'pauses before answering', 'jaw tightens', 'eyes narrow', 'voice drops half a register'.\n"
        "- The dialogue should make the player THINK, not just react. Channel Kreia, Atton, Jolee Bindo.\n"
        "- Philosophical depth comes from SUBTEXT, not length. 1-4 lines max.\n"
        "- The NPC must speak ON TOPIC (the scene's topic from context).\n"
        "- Do NOT repeat information already in the prose — the dialogue should ADD something new.\n\n"
        "FORMAT:\n"
        "[Your prose paragraphs here]\n"
        "---NPC_LINE---\n"
        "SPEAKER: {NPC name from Present NPCs list, or 'Narrator' if no NPCs}\n"
        "\"{What the NPC says aloud — on topic, with subtext}\"\n\n"
        "RULES:\n"
        "- The SPEAKER must be an NPC from the '## Present NPCs' list, or 'Narrator'.\n"
        "- Match the NPC's voice (accent, vocabulary, mannerisms) from voice snippets if available.\n"
        "AFTER THE NPC LINE, STOP. WRITE NOTHING ELSE."
    )

    if is_opening_scene:
        system = (
            "You are the narrator for a story game. THIS IS THE OPENING SCENE — the very first moment the player experiences.\n\n"
            "PERSPECTIVE: Write in close third-person POV through the player character (see 'POV Character' in context). "
            "Everything is filtered through THEIR senses and emotions. Use their name. "
            "Example: 'Tycho felt the heat of the cantina hit him as he stepped inside.' NOT 'The cantina was hot.'\n\n"
            "Your job is to write a CINEMATIC INTRODUCTION that:\n"
            "1. ORIENTS THE PLAYER FIRST: Before anything happens, ground them. Where are they? What do they see and feel? "
            "Start with atmosphere and location — the player needs to know where they are before things happen.\n"
            "2. INTRODUCES NPCS NATURALLY: When an NPC appears, briefly describe them visually. "
            "Example: 'A scarred Twi'lek in a pilot's jacket leaned against the bar — an officer, by the look of the insignia.' "
            "Do NOT reference NPCs by name as if the player already knows them, unless the backstory says they do.\n"
            "3. CREATES A HOOK: Something happens that invites the player to act. Keep it simple — a conversation overheard, "
            "a figure approaching, a problem visible in the scene.\n"
            "4. DOES NOT ASSUME PLAYER ACTIONS: Describe what they perceive, not what they do. End with a moment that invites a choice. "
            "NEVER narrate the player character taking actions without player input — describe what they sense, not what they decide.\n"
            "5. Write 5-8 vivid sentences. Keep it grounded — this is the BEGINNING, not the middle of an action sequence.\n"
            "6. Write as flowing prose paragraphs (2-3 paragraphs, separated by blank lines). "
            "Do NOT split the narrative into labeled sections like "
            "'Scene Description:' or 'Suggested Actions:'. Blend setting, atmosphere, character motivation, "
            "NPC introductions, and tension into ONE flowing narrative. Think: the opening page of a novel, "
            "not a game manual with headers.\n\n"
            "PLAYER BACKGROUND: The POV Character section contains the character's background. "
            "Reference it subtly: if they come from the underworld, the opening should feel like THEIR "
            "underworld. If they lost someone, hint at that weight. Don't state it outright — "
            "let the atmosphere reflect their past.\n\n"
            "--- HARD RULES ---\n"
            "- OUTPUT FORMAT: Write ONLY narrative prose. Plain text paragraphs separated by blank lines.\n"
            "  Do NOT use markdown headers (**, ##), JSON, code blocks, section labels, or any structural formatting.\n"
            "  Do NOT write 'Scene:', 'Narrative:', 'Next Turn:', 'Opening:', or any labels.\n"
            "  Just write the story as flowing prose paragraphs.\n"
            "- NPC NAMES: You may ONLY use NPC names listed in '## Present NPCs'. "
            "Do NOT invent, hallucinate, or reference ANY character names not in that list. "
            "If you need an unnamed background character, describe them by appearance or role "
            "(e.g., 'a dock worker', 'the bartender', 'a passing spacer').\n"
            "- FACTION NEUTRALITY: Do NOT assume the player's allegiance. The player may choose to side "
            "with ANY faction (Rebellion, Empire, criminal syndicates, independent). Narrate the world "
            "as presenting opportunities from multiple sides. Do not frame one faction as 'the good guys'.\n"
            "  * BAD: 'Ozzel, from wanted posters' (assumes anti-Empire stance)\n"
            "  * GOOD: 'an Imperial officer — Ozzel, by the rank insignia'\n"
            "  * BAD: 'the Rebel smuggler Hero knew' (assumes Rebel sympathy)\n"
            "  * GOOD: 'a smuggler Hero had crossed paths with before'\n"
            "- LORE: Use the provided lore context to enrich the scene. If lore context is empty, do NOT claim canon facts; use atmosphere and sensory detail instead.\n"
            "- VOICE: When characters speak, match their voice to provided voice snippets if available.\n"
            "- Do NOT mention game mechanics, dice rolls, or mechanical outcomes in the opening.\n"
            "- STYLE: If style directives are provided, use them to shape prose rhythm, atmosphere, and sensory detail.\n\n"
            "--- CYOA PROSE STYLE ---\n"
            "Write as if this is a page in a Choose Your Own Adventure novel. "
            "Use vivid second-person-adjacent close-third POV — the reader IS the character. "
            "End the scene on a beat of tension or mystery — an evocative IMAGE, not a decision menu. "
            "A door creaking open, a shadow moving at the edge of vision, a hand drifting to a weapon. "
            "NEVER present numbered options, lettered choices, or dialogue menus inside the prose. "
            "The reader should FEEL the tension, not be handed a list."
        ) + _prose_stop_rule
    else:
        system = (
            "You are the narrator for an ongoing story game. You are writing the NEXT CHAPTER of a continuous narrative.\n\n"
            "PERSPECTIVE: Write in close third-person POV through the player character (see 'POV Character' in context). "
            "Everything is filtered through THEIR senses — what they see, hear, smell, feel. Use their name. "
            "The reader experiences the world as this character. Never break POV.\n\n"
            "NARRATIVE CONTINUITY (CRITICAL):\n"
            "- The 'Story So Far' section contains the actual prose from recent turns. Your text MUST read as a natural continuation.\n"
            "- Reference what happened before: if the player talked to someone, acknowledge the conversation. If they moved, describe arriving.\n"
            "- Maintain consistent tone, setting details, and character behavior across turns.\n"
            "- The player should feel like they're reading a novel, not a series of disconnected scenes.\n\n"
            "RULES:\n"
            "1. GROUNDING (STRICT): You MUST only narrate based on MechanicResult and the event log. Do NOT invent success/failure or outcomes.\n"
            "2. If the mechanic outcome indicates the action was invalid or unclear, ask the player to rephrase.\n"
            "3. PLAYER AGENCY (CRITICAL): NEVER narrate the player character taking actions they didn't choose. "
            "Describe what they perceive, sense, feel — not what they decide or do next. "
            "End with a MOMENT (sensory detail, NPC reaction, environment change), not an action the player hasn't chosen.\n"
            "4. LORE: Use the provided lore context to enrich the scene. If lore context is empty or missing, do NOT claim canon facts.\n"
            "5. TONE: Adjust tone based on character's current_mood and stress_level. High stress (>7) = shorter sentences, sensory overload. Low stress = more reflective prose.\n"
            "6. RUMORS: Subtly reference background rumors if appropriate, but do not derail the scene.\n"
            "7. VOICE: When characters speak, match their voice to provided voice snippets if available.\n"
            "8. Output 5-8 sentences of narrative prose ending with an evocative moment.\n"
            "9. Write as flowing prose paragraphs (2-3 paragraphs, separated by blank lines). "
            "Never split output into sections, headers, or labeled blocks. "
            "The narrative should read like a page from a novel: setting, consequences, NPC reactions, and tension "
            "woven into flowing prose. No 'Scene Description:', no 'Suggested Actions:', no structural labels.\n\n"
            "PARAGRAPH STRUCTURE (follow this rhythm):\n"
            "- Lead with a sensory hook (what the character perceives FIRST — a sound, a smell, a visual detail)\n"
            "- Develop the scene (NPC reactions, environmental details, consequences unfolding)\n"
            "- End with forward momentum (a question raised, tension introduced, or a change in the situation)\n"
            "Do NOT end with a summary or restatement. End on something that makes the player want to act.\n\n"
            "NPC REACTIONS (CRITICAL):\n"
            "- NPCs are NOT robots. When something significant happens, show their EMOTIONAL response.\n"
            "- Use body language, facial expressions, voice tone: 'Her jaw tightened', 'His hand drifted to his blaster', "
            "'The Wookiee let out a low growl', 'Lando's smile faltered for just a moment'.\n"
            "- If the player confronts someone, show them reacting — flinching, going pale, getting angry, stepping back.\n"
            "- If an NPC offers a deal, show investment: leaning forward, lowering voice, glancing around nervously.\n"
            "- If surprised, show SURPRISE — widened eyes, a sharp intake of breath, stumbling over words.\n\n"
            "MECHANIC ACTION NARRATION (CRITICAL):\n"
            "- When the MechanicResult reports an action (attack, sneak, persuade, intimidate), you MUST narrate the action itself.\n"
            "- COMBAT: describe the fight — blaster fire, ducking behind cover, the crack of impact, adrenaline.\n"
            "- STEALTH failure: describe getting caught — a guard turns, a spotlight catches them, a door alarm triggers.\n"
            "- INTIMIDATION: describe the confrontation — getting in someone's face, slamming a fist on a table, the room going quiet.\n"
            "- Do NOT skip the action and jump to aftermath. Show the MOMENT of action as it unfolds.\n\n"
            "--- HARD RULES ---\n"
            "- OUTPUT FORMAT: Write ONLY narrative prose. Plain text paragraphs separated by blank lines.\n"
            "  Do NOT use markdown headers (**, ##), JSON, code blocks, section labels, or any structural formatting.\n"
            "  Do NOT write 'Scene:', 'Narrative:', 'Next Turn:', 'Opening:', or any labels.\n"
            "  Just write the story as flowing prose paragraphs.\n"
            "- NPC NAMES: You may ONLY use NPC names listed in '## Present NPCs'. "
            "Do NOT invent, hallucinate, or reference ANY character names not in that list. "
            "If you need an unnamed background character, describe them by appearance or role "
            "(e.g., 'a dock worker', 'the bartender', 'a passing spacer').\n"
            "- FACTION NEUTRALITY: Do NOT assume the player's allegiance. The player may choose to side "
            "with ANY faction (Rebellion, Empire, criminal syndicates, independent). Narrate the world "
            "as presenting opportunities from multiple sides. Do not frame one faction as 'the good guys'.\n"
            "  * BAD: 'Ozzel, from wanted posters' (assumes anti-Empire stance)\n"
            "  * GOOD: 'an Imperial officer — Ozzel, by the rank insignia'\n"
            "  * BAD: 'the Rebel smuggler Hero knew' (assumes Rebel sympathy)\n"
            "  * GOOD: 'a smuggler Hero had crossed paths with before'\n"
            "- Only describe outcomes from Mechanic as facts. Do not invent mechanical results.\n"
            "- Only state character-history specifics if those facts appear in retrieved voice/lore citations. Otherwise, phrase uncertainty.\n"
            "- Prefer era-specific phrasing and voice guidance from voice snippets when available.\n"
            "- STYLE: If style directives are provided, use them to shape prose rhythm, atmosphere, and sensory detail.\n\n"
            "--- CYOA PROSE STYLE ---\n"
            "Write as if this is a page in a Choose Your Own Adventure novel. "
            "Use vivid second-person-adjacent close-third POV — the reader IS the character. "
            "End the scene on a beat of tension or mystery — an evocative IMAGE, not a decision menu. "
            "A door creaking open, a shadow moving at the edge of vision, a hand drifting to a weapon. "
            "NEVER present numbered options, lettered choices, or dialogue menus inside the prose. "
            "The reader should FEEL the tension, not be handed a list."
        ) + _prose_stop_rule

    story_state_summary = _build_story_state_summary(state)
    recent_history = state.history or []

    empty_voice_text = format_voice_snippets({}, "(No character voice samples available.)")
    empty_lore_text = format_lore_bullets([], "(No lore context--phrase uncertain information as rumor or possibility.)")
    if isinstance(lore_chunks, str):
        empty_lore_text = lore_chunks
        lore_chunks = []
    if isinstance(voice_snippets_by_char, str):
        empty_voice_text = voice_snippets_by_char
        voice_snippets_by_char = {}

    max_input_tokens = get_role_max_input_tokens("narrator")
    reserve_output_tokens = get_role_reserved_output_tokens("narrator")
    parts = {
        "system": system,
        "state": story_state_summary,
        "history": recent_history,
        "era_summaries": state.era_summaries or [],
        "lore_chunks": lore_chunks,
        "style_chunks": style_chunks or [],
        "voice_snippets": voice_snippets_by_char,
        "kg_context": kg_context,
        "user_input": state.user_input or "",
    }
    messages, budget_report = build_context(
        parts,
        max_input_tokens=max_input_tokens,
        reserve_output_tokens=reserve_output_tokens,
        role="narrator",
        max_voice_snippets_per_char=2,
        min_lore_chunks=1,
        user_input_label="User input:",
        empty_voice_text=empty_voice_text,
        empty_lore_text=empty_lore_text,
    )
    system_prompt_final = messages[0]["content"]
    user_prompt = messages[1]["content"]

    if include_budget:
        return system_prompt_final, user_prompt, budget_report
    return system_prompt_final, user_prompt


def _citations_from_chunks(chunks: list[LoreChunk], used_in_narrative: bool = True) -> list[NarrationCitation]:
    """Build citation list from lore chunks; quote = first ~20 words of each chunk."""
    out = []
    for c in chunks:
        title = c.get("source_title") or c.get("metadata", {}).get("book_title") or "Source"
        chunk_id = c.get("chunk_id") or ""
        text = (c.get("text") or "").strip()
        if not text:
            continue
        quote = _quote_excerpt(text, 20)
        out.append(NarrationCitation(source_title=title, chunk_id=chunk_id, quote=quote))
    return out


def _parse_llm_narration(raw: str, fallback_chunks: list[LoreChunk]) -> NarrationOutput:
    """Parse LLM response into NarrationOutput; fallback to plain text + citations from chunks.

    Handles multiple LLM output patterns:
    - Clean prose (ideal)
    - JSON with "text" field
    - Mixed prose + JSON code blocks (extract prose, ignore JSON)
    - Markdown-structured output with **headers** (strip headers, keep prose)
    """
    text = raw.strip()
    citations: list[NarrationCitation] = []

    # Try JSON extraction first
    json_str = ensure_json(text)
    if json_str:
        try:
            import json
            data = json.loads(json_str)
            if isinstance(data.get("text"), str):
                text = data["text"]
            elif isinstance(data.get("narrative"), str):
                text = data["narrative"]
            elif isinstance(data.get("description"), str):
                text = data["description"]
            elif isinstance(data.get("scene"), str):
                text = data["scene"]
            if isinstance(data.get("citations"), list):
                for cit in data["citations"]:
                    if isinstance(cit, dict) and cit.get("source_title") and cit.get("chunk_id"):
                        citations.append(NarrationCitation(
                            source_title=str(cit["source_title"]),
                            chunk_id=str(cit["chunk_id"]),
                            quote=str(cit.get("quote", ""))[:200],
                        ))
        except Exception as e:
            logger.debug("Failed to parse citations from LLM response: %s", e, exc_info=True)

    # If the text still contains fenced code blocks, the LLM mixed prose with JSON.
    # Extract the prose portions outside code blocks.
    if "```" in text:
        prose_parts = []
        in_code = False
        for line in text.split("\n"):
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            if not in_code:
                prose_parts.append(line)
        extracted = "\n".join(prose_parts).strip()
        if extracted:
            text = extracted

    if not citations and fallback_chunks:
        citations = _citations_from_chunks(fallback_chunks)
    return NarrationOutput(text=text, citations=citations)


class NarratorAgent:
    """Incorporates mechanic_result (show don't tell), director_instructions, lore (grounded), voice snippets."""

    def __init__(
        self,
        llm: AgentLLM | None = None,
        lore_retriever: Callable[..., list[LoreChunk]] | None = None,
        voice_retriever: Callable[[list[str], str, int], dict[str, list]] | None = None,
        style_retriever: Callable[..., list[dict]] | None = None,
    ) -> None:
        self._llm = llm
        self._lore_retriever = lore_retriever
        self._voice_retriever = voice_retriever
        self._style_retriever = style_retriever

    def generate(self, state: GameState, kg_context: str = "") -> NarrationOutput:
        """Produce narrative (grounded in mechanic events + lore); return NarrationOutput with optional citations."""
        warnings_list = getattr(state, "warnings", None)
        # If Mechanic returned invalid_action, do not invent outcomes—ask for rephrase only
        if state.mechanic_result and getattr(state.mechanic_result, "invalid_action", False):
            msg = getattr(state.mechanic_result, "rephrase_message", None) or "That action is unclear—try rephrasing."
            return NarrationOutput(text=msg, citations=[])

        # Retrieve lore
        lore_chunks: list[LoreChunk] = []
        campaign = state.campaign or {}
        era = (campaign.get("time_period") or campaign.get("era") or "REBELLION")
        if isinstance(era, str):
            era = era.strip() or "REBELLION"
        else:
            era = "REBELLION"

        if self._lore_retriever is not None:
            query = _build_lore_query(state)
            related_ids = collect_related_npc_ids(state)
            lore_chunks = call_retriever(
                self._lore_retriever,
                query,
                top_k=6,
                era=era,
                related_npcs=related_ids if related_ids else None,
                warnings=warnings_list,
            )
            if related_ids and not lore_chunks:
                lore_chunks = call_retriever(
                    self._lore_retriever,
                    query,
                    top_k=6,
                    era=era,
                    warnings=warnings_list,
                )

        # Retrieve voice snippets for present NPCs and party
        voice_snippets_by_char: dict[str, list] = {}
        if self._voice_retriever is not None:
            char_ids = _collect_character_ids(state)
            if char_ids:
                raw = call_retriever(self._voice_retriever, char_ids, era, k=6, warnings=warnings_list)
                for cid, snips in raw.items():
                    voice_snippets_by_char[cid] = [
                        {"character_id": s.character_id, "era": s.era, "text": s.text, "chunk_id": s.chunk_id}
                        if hasattr(s, "text") else s
                        for s in snips
                    ]

        # Retrieve style chunks for narrative shaping
        style_chunks: list[dict] = []
        if self._style_retriever is not None:
            from backend.app.core.director_validation import build_style_query
            style_query = build_style_query(state)
            campaign = getattr(state, "campaign", None) or {}
            _era_id = campaign.get("time_period") or campaign.get("era") or None
            _genre = campaign.get("genre") or None
            _archetype = campaign.get("archetype") or None
            style_chunks = call_retriever(self._style_retriever, style_query, 3, era_id=_era_id, genre=_genre, archetype=_archetype, warnings=warnings_list)

        system, user, budget_report = _build_prompt(
            state,
            lore_chunks,
            voice_snippets_by_char,
            include_budget=True,
            kg_context=kg_context,
            style_chunks=style_chunks,
        )

        warn = budget_report.warning_message()
        if warn:
            add_warning(state, warn)

        # Store context_stats in state for later retrieval (if DEV_CONTEXT_STATS enabled)
        if DEV_CONTEXT_STATS:
            state.context_stats = budget_report.to_context_stats()

        has_lore = bool(lore_chunks)
        has_voice = bool(voice_snippets_by_char and any(voice_snippets_by_char.values()))

        if self._llm is not None:
            try:
                raw = self._llm.generate(system_prompt=system, user_prompt=user)
                output = _parse_llm_narration(raw, lore_chunks)
                cleaned_text = _strip_structural_artifacts(output.text)

                # V2.15: Narrator writes prose only. Strip any suggestions the LLM
                # may still inject despite the simplified prompt (safety net).
                cleaned_text = _strip_embedded_suggestions(cleaned_text)

                cleaned_text = _enforce_pov_consistency(cleaned_text)
                cleaned_text = _truncate_overlong_prose(cleaned_text)
                output = NarrationOutput(
                    text=cleaned_text,
                    citations=output.citations,
                    embedded_suggestions=None,
                )
                return output
            except Exception as e:
                log_error_with_context(
                    error=e,
                    node_name="narrator",
                    campaign_id=state.campaign_id,
                    turn_number=state.turn_number,
                    agent_name="NarratorAgent.generate",
                    extra_context={"location": state.current_location},
                )
                logger.warning("NarratorAgent LLM generation failed, using fallback")
                add_warning(state, "LLM error: Narrator used fallback output.")
        # No LLM or LLM failed: deterministic fallback
        # Build a readable narrative fallback (not raw pipeline data)
        mechanic_summary = _summarize_mechanic_events(state)
        loc = _humanize_location(state.current_location) or "your surroundings"
        npcs = state.present_npcs or []

        # Check if this is the opening scene
        is_opening_fb = not (state.history or []) or len(state.history or []) <= 1
        opening_tag_fb = "[OPENING_SCENE]" in (state.user_input or "")

        # Resolve POV character name for third-person fallback
        pov_name = "the protagonist"
        if state.player and getattr(state.player, "name", None):
            pov_name = state.player.name

        if is_opening_fb or opening_tag_fb:
            # Opening scene fallback: more atmospheric
            planet = ""
            campaign = state.campaign or {}
            ws = campaign.get("world_state_json") if isinstance(campaign, dict) else {}
            if isinstance(ws, dict):
                planet = ws.get("starting_planet") or ""
            planet_str = f" on {planet}" if planet else ""

            parts = [f"The air{planet_str} carried the weight of a galaxy in motion."]
            parts.append(f"{pov_name} stepped into {loc}, taking in the scene.")

            # Mention present NPCs atmospherically
            npc_names = [n.get("name") for n in npcs if n.get("name")]
            if npc_names:
                if len(npc_names) == 1:
                    parts.append(f"A figure caught {pov_name}'s eye — {npc_names[0]}, watching from across the room.")
                else:
                    parts.append(f"Several figures populated the space: {', '.join(npc_names[:-1])} and {npc_names[-1]}.")

            parts.append("Something stirred at the edge of awareness. The story began here.")
            paragraph = " ".join(parts)
            text = paragraph
        else:
            # Normal fallback
            parts = [f"{pov_name} surveyed {loc}."]

            # Add mechanic outcomes as narrative (not raw labels)
            if mechanic_summary and mechanic_summary != "(No mechanical events this turn.)":
                parts.append(mechanic_summary)

            # Mention present NPCs
            npc_names = [n.get("name") for n in npcs if n.get("name")]
            if npc_names:
                if len(npc_names) == 1:
                    parts.append(f"{npc_names[0]} is nearby.")
                else:
                    parts.append(f"{', '.join(npc_names[:-1])} and {npc_names[-1]} are nearby.")

            # Add atmosphere based on stress level
            psych = {}
            if state.player and getattr(state.player, "psych_profile", None):
                psych = state.player.psych_profile or {}
            stress_level = int(psych.get("stress_level", 0) or 0)
            if stress_level > 7:
                parts.append("The air feels tense.")
            elif stress_level < 3:
                parts.append("The moment is calm, expectant.")

            paragraph = " ".join(parts)
            text = paragraph
        text = _strip_embedded_suggestions(text)
        text = _enforce_pov_consistency(text)
        citations = _citations_from_chunks(lore_chunks)
        return NarrationOutput(text=text, citations=citations)

    def generate_stream(self, state: GameState, kg_context: str = "") -> Iterator[str]:
        """Stream narrative tokens. Yields individual token strings.

        Builds the same prompt as generate() but uses complete_stream() for
        incremental token delivery. Post-processing (_strip_structural_artifacts,
        etc.) must be applied on the accumulated text by the caller after the
        stream completes.

        Falls back to yielding the full deterministic fallback text if no LLM
        is available.
        """
        warnings_list = getattr(state, "warnings", None)

        # If Mechanic returned invalid_action, yield the rephrase message
        if state.mechanic_result and getattr(state.mechanic_result, "invalid_action", False):
            msg = getattr(state.mechanic_result, "rephrase_message", None) or "That action is unclear—try rephrasing."
            yield msg
            return

        # Retrieve lore
        lore_chunks: list[LoreChunk] = []
        campaign = state.campaign or {}
        era = (campaign.get("time_period") or campaign.get("era") or "REBELLION")
        if isinstance(era, str):
            era = era.strip() or "REBELLION"
        else:
            era = "REBELLION"

        if self._lore_retriever is not None:
            query = _build_lore_query(state)
            related_ids = collect_related_npc_ids(state)
            lore_chunks = call_retriever(
                self._lore_retriever,
                query,
                top_k=6,
                era=era,
                related_npcs=related_ids if related_ids else None,
                warnings=warnings_list,
            )
            if related_ids and not lore_chunks:
                lore_chunks = call_retriever(
                    self._lore_retriever,
                    query,
                    top_k=6,
                    era=era,
                    warnings=warnings_list,
                )

        # Retrieve voice snippets
        voice_snippets_by_char: dict[str, list] = {}
        if self._voice_retriever is not None:
            char_ids = _collect_character_ids(state)
            if char_ids:
                raw = call_retriever(self._voice_retriever, char_ids, era, k=6, warnings=warnings_list)
                for cid, snips in raw.items():
                    voice_snippets_by_char[cid] = [
                        {"character_id": s.character_id, "era": s.era, "text": s.text, "chunk_id": s.chunk_id}
                        if hasattr(s, "text") else s
                        for s in snips
                    ]

        # Retrieve style chunks
        style_chunks: list[dict] = []
        if self._style_retriever is not None:
            from backend.app.core.director_validation import build_style_query
            style_query = build_style_query(state)
            campaign = getattr(state, "campaign", None) or {}
            _era_id = campaign.get("time_period") or campaign.get("era") or None
            _genre = campaign.get("genre") or None
            _archetype = campaign.get("archetype") or None
            style_chunks = call_retriever(self._style_retriever, style_query, 3, era_id=_era_id, genre=_genre, archetype=_archetype, warnings=warnings_list)

        system, user = _build_prompt(
            state,
            lore_chunks,
            voice_snippets_by_char,
            include_budget=False,
            kg_context=kg_context,
            style_chunks=style_chunks,
        )

        if self._llm is not None:
            try:
                yield from self._llm.complete_stream(system_prompt=system, user_prompt=user)
                return
            except Exception as e:
                log_error_with_context(
                    error=e,
                    node_name="narrator",
                    campaign_id=state.campaign_id,
                    turn_number=state.turn_number,
                    agent_name="NarratorAgent.generate_stream",
                    extra_context={"location": state.current_location},
                )
                logger.warning("NarratorAgent streaming failed, using fallback")
                add_warning(state, "LLM error: Narrator streaming used fallback output.")

        # Fallback: yield the full deterministic text from generate()
        output = self.generate(state, kg_context=kg_context)
        yield output.text

    def generate_with_correction(self, state: GameState, correction: str, kg_context: str = "") -> NarrationOutput:
        """Re-generate narrative with a correction prompt appended. Used for narrator feedback loop (max 1 retry)."""
        warnings_list = getattr(state, "warnings", None)
        lore_chunks: list[LoreChunk] = []
        campaign = state.campaign or {}
        era = (campaign.get("time_period") or campaign.get("era") or "REBELLION")
        if isinstance(era, str):
            era = era.strip() or "REBELLION"
        else:
            era = "REBELLION"

        if self._lore_retriever is not None:
            query = _build_lore_query(state)
            related_ids = collect_related_npc_ids(state)
            lore_chunks = call_retriever(
                self._lore_retriever, query, top_k=6, era=era,
                related_npcs=related_ids if related_ids else None,
                warnings=warnings_list,
            )

        voice_snippets_by_char: dict[str, list] = {}
        if self._voice_retriever is not None:
            char_ids = _collect_character_ids(state)
            if char_ids:
                raw = call_retriever(self._voice_retriever, char_ids, era, k=6, warnings=warnings_list)
                for cid, snips in raw.items():
                    voice_snippets_by_char[cid] = [
                        {"character_id": s.character_id, "era": s.era, "text": s.text, "chunk_id": s.chunk_id}
                        if hasattr(s, "text") else s
                        for s in snips
                    ]

        style_chunks: list[dict] = []
        if self._style_retriever is not None:
            from backend.app.core.director_validation import build_style_query
            style_query = build_style_query(state)
            campaign = getattr(state, "campaign", None) or {}
            _era_id = campaign.get("time_period") or campaign.get("era") or None
            _genre = campaign.get("genre") or None
            _archetype = campaign.get("archetype") or None
            style_chunks = call_retriever(self._style_retriever, style_query, 3, era_id=_era_id, genre=_genre, archetype=_archetype, warnings=warnings_list)

        system, user, budget_report = _build_prompt(
            state, lore_chunks, voice_snippets_by_char,
            include_budget=True, kg_context=kg_context, style_chunks=style_chunks,
        )
        # Append correction instruction to user prompt
        user = user + f"\n\nCORRECTION REQUIRED: {correction}\nRewrite the narrative to fix the above issue."

        has_lore = bool(lore_chunks)
        has_voice = bool(voice_snippets_by_char and any(voice_snippets_by_char.values()))

        if self._llm is not None:
            raw = self._llm.generate(system_prompt=system, user_prompt=user)
            output = _parse_llm_narration(raw, lore_chunks)
            cleaned_text = _strip_structural_artifacts(output.text)
            cleaned_text = _strip_embedded_suggestions(cleaned_text)
            output = NarrationOutput(
                text=cleaned_text,
                citations=output.citations,
            )
            return output
        # Fallback: no LLM available for correction
        return NarrationOutput(text="(Correction unavailable — no LLM.)", citations=[])
