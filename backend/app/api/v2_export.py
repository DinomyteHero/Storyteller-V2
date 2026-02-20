"""Novel Export API: export a campaign's narrative as a Markdown document.

Phase 5 — provides a downloadable Markdown file containing the full story
with chapter breaks at arc stage transitions and player choices as blockquotes.
"""
from __future__ import annotations

import json
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from backend.app.db.connection import get_db
from backend.app.core.state_loader import load_campaign
from backend.app.core.transcript_store import get_rendered_turns

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/export", tags=["export"])

# Arc stage to chapter name map (used within _generate_chapter_heading)
_STAGE_NAMES: dict[str, str] = {
    "SETUP": "Beginnings",
    "RISING": "Rising Action",
    "CLIMAX": "The Turning Point",
    "RESOLUTION": "Resolution",
}

_ROMAN_NUMERALS: list[str] = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


def _generate_chapter_heading(arc_number: int, stage: str, arc_count: int) -> str:
    """Generate a chapter heading, with arc prefix for multi-arc campaigns.

    Single-arc: "Chapter I: Beginnings"
    Multi-arc:  "Arc 1, Chapter III: The Turning Point"
    """
    stage_name = _STAGE_NAMES.get(stage, stage.title())
    stages_list = list(_STAGE_NAMES.keys())
    stage_idx = stages_list.index(stage) if stage in stages_list else 0
    # Chapter number = (arc_number - 1) * stages_per_arc + stage_index + 1
    chapter_num = (arc_number - 1) * len(stages_list) + stage_idx + 1
    roman = _ROMAN_NUMERALS[chapter_num - 1] if chapter_num <= len(_ROMAN_NUMERALS) else str(chapter_num)
    if arc_count > 1:
        return f"Arc {arc_number}, Chapter {roman}: {stage_name}"
    return f"Chapter {roman}: {stage_name}"


def _extract_player_choices(
    conn: sqlite3.Connection, campaign_id: str
) -> dict[int, list[str]]:
    """Return a mapping of turn_number -> list of player choice texts from turn_events."""
    cur = conn.execute(
        """SELECT turn_number, event_type, payload_json
           FROM turn_events
           WHERE campaign_id = ?
             AND (event_type LIKE '%CHOICE%' OR event_type LIKE '%PLAYER_ACTION%')
           ORDER BY turn_number ASC""",
        (campaign_id,),
    )
    choices: dict[int, list[str]] = {}
    for row in cur.fetchall():
        turn_number = row[0]
        payload_json = row[2] or "{}"
        try:
            payload = json.loads(payload_json) if isinstance(payload_json, str) else (payload_json or {})
        except (TypeError, json.JSONDecodeError):
            payload = {}
        # Extract choice text from various payload shapes
        text = (
            payload.get("choice_text")
            or payload.get("text")
            or payload.get("user_input")
            or payload.get("action")
            or ""
        )
        if text and isinstance(text, str) and text.strip():
            choices.setdefault(turn_number, []).append(text.strip())
    return choices


def _extract_arc_stage_transitions(
    conn: sqlite3.Connection, campaign_id: str
) -> dict[int, tuple[str, int]]:
    """Return a mapping of turn_number -> (arc_stage, arc_number) from turn_events.

    Looks for events whose payload contains an arc_stage field or whose
    event_type signals an arc stage change. Tracks arc_number for multi-arc campaigns.
    """
    cur = conn.execute(
        """SELECT turn_number, event_type, payload_json
           FROM turn_events
           WHERE campaign_id = ?
           ORDER BY turn_number ASC""",
        (campaign_id,),
    )
    transitions: dict[int, tuple[str, int]] = {}
    prev_stage: str | None = None
    current_arc: int = 1
    for row in cur.fetchall():
        turn_number = row[0]
        event_type = row[1] or ""
        payload_json = row[2] or "{}"
        try:
            payload = json.loads(payload_json) if isinstance(payload_json, str) else (payload_json or {})
        except (TypeError, json.JSONDecodeError):
            payload = {}
        # Track arc number from ARC_TRANSITION events
        if "ARC_TRANSITION" in event_type.upper() or "ARC_START" in event_type.upper():
            arc_num = payload.get("arc_number") or payload.get("new_arc_number")
            if arc_num and isinstance(arc_num, int):
                current_arc = arc_num
        # Check for arc_stage in payload
        stage = payload.get("arc_stage") or ""
        if not stage and "ARC" in event_type.upper():
            stage = payload.get("stage") or payload.get("new_stage") or ""
        stage = stage.upper().strip() if stage else ""
        if stage and stage in _STAGE_NAMES and stage != prev_stage:
            transitions[turn_number] = (stage, current_arc)
            prev_stage = stage
    return transitions


def _build_novel_markdown(
    campaign: dict,
    turns: list[dict],
    choices: dict[int, list[str]],
    arc_transitions: dict[int, tuple[str, int]],
) -> str:
    """Assemble the full Markdown document."""
    lines: list[str] = []

    # Sort turns ascending by turn_number
    sorted_turns = sorted(turns, key=lambda t: t.get("turn_number", 0))

    # Calculate word count and turn count for stats
    total_words = 0
    total_turns = 0
    for turn in sorted_turns:
        text = (turn.get("text") or "").strip()
        if text:
            total_words += len(text.split())
            total_turns += 1

    # Determine total arc count for chapter heading format
    arc_count = max((arc_num for _, arc_num in arc_transitions.values()), default=1)

    # Header
    title = campaign.get("title") or "Untitled Campaign"
    era = campaign.get("time_period") or "Unknown Era"
    lines.append(f"# {title}")
    lines.append(f"*{era}*")
    lines.append("")
    lines.append(f"*{total_words:,} words across {total_turns} turns*")
    lines.append("")

    current_chapter: str | None = None

    for turn in sorted_turns:
        tn = turn.get("turn_number", 0)
        text = (turn.get("text") or "").strip()
        if not text:
            continue

        # Check for arc stage transition at this turn
        if tn in arc_transitions:
            stage, arc_number = arc_transitions[tn]
            chapter_heading = _generate_chapter_heading(arc_number, stage, arc_count)
            if chapter_heading != current_chapter:
                current_chapter = chapter_heading
                lines.append("")
                lines.append(f"## {chapter_heading}")
                lines.append("")

        # Insert chapter heading for first turn if no transition has fired yet
        if current_chapter is None:
            current_chapter = _generate_chapter_heading(1, "SETUP", arc_count)
            lines.append(f"## {current_chapter}")
            lines.append("")

        # Player choices as blockquotes (em-dash prefix for literary feel)
        if tn in choices:
            for choice_text in choices[tn]:
                lines.append(f"> *— {choice_text}*")
                lines.append("")

        # Prose text
        lines.append(text)
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("*Exported from Storyteller AI*")

    return "\n".join(lines)


@router.get("/novel")
async def export_novel(
    campaign_id: str = Query(..., description="The campaign ID to export"),
    conn: sqlite3.Connection = Depends(get_db),
) -> PlainTextResponse:
    """Export the full campaign narrative as a downloadable Markdown document."""
    # 1. Load campaign
    campaign = load_campaign(conn, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail=f"Campaign not found: {campaign_id}")

    # 2. Get all rendered turns (ascending by turn_number)
    rendered = get_rendered_turns(conn, campaign_id, limit=9999)
    # get_rendered_turns returns descending; reverse to ascending
    rendered.sort(key=lambda t: t.get("turn_number", 0))

    # 3. Query player choices and arc stage transitions
    choices = _extract_player_choices(conn, campaign_id)
    arc_transitions = _extract_arc_stage_transitions(conn, campaign_id)

    # 4. Build the Markdown document
    markdown = _build_novel_markdown(campaign, rendered, choices, arc_transitions)

    # 5. Return as downloadable Markdown file
    safe_title = (campaign.get("title") or "story").replace(" ", "_").replace("/", "_")[:50]
    filename = f"{safe_title}_export.md"

    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
