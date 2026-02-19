"""Narrator post-processing helpers.

Functions that clean, validate, and transform raw LLM narrator output
into polished narrative prose.
"""
from __future__ import annotations

import re
import logging

from backend.app.models.narration import NarrationOutput, NarrationCitation
from backend.app.models.dialogue_turn import NPCUtterance
from backend.app.core.agents.base import ensure_json

logger = logging.getLogger(__name__)

# Type alias (duplicated here for self-containment; canonical definition in narrator.py)
LoreChunk = dict

SCENE_WORD_LIMITS: dict[str, int] = {
    "STANDARD": 250,
    "ELEVATED": 350,
    "CLIMAX": 450,
}


def get_word_limit_for_scene_weight(scene_weight: str | None) -> int:
    """Resolve max word budget from scene weight classification."""
    key = (scene_weight or "STANDARD").strip().upper()
    return SCENE_WORD_LIMITS.get(key, SCENE_WORD_LIMITS["STANDARD"])


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

    # -- Numbered list at end: "1. Action text\n2. Action text\n..." --
    text = re.sub(
        r"\n\s*\d+\.\s+.+(?:\n\s*\d+\.\s+.+){1,}\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # -- "What do you do?" header --
    text = re.sub(
        r"\n*\*{0,2}What do you do\??\*{0,2}\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # -- Mid-text suggestion blocks: header + following list --
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

# Flexible regex: matches ---NPC_LINE---, -- NPC_LINE --, etc.
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
