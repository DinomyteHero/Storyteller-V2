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

# Arc stage to chapter heading map
ARC_STAGE_CHAPTERS: dict[str, str] = {
    "SETUP": "Chapter I: Beginnings",
    "RISING": "Chapter II: Rising Action",
    "CLIMAX": "Chapter III: The Turning Point",
    "RESOLUTION": "Chapter IV: Resolution",
}


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
) -> dict[int, str]:
    """Return a mapping of turn_number -> new arc stage from turn_events.

    Looks for events whose payload contains an arc_stage field or whose
    event_type signals an arc stage change.
    """
    cur = conn.execute(
        """SELECT turn_number, event_type, payload_json
           FROM turn_events
           WHERE campaign_id = ?
           ORDER BY turn_number ASC""",
        (campaign_id,),
    )
    transitions: dict[int, str] = {}
    prev_stage: str | None = None
    for row in cur.fetchall():
        turn_number = row[0]
        event_type = row[1] or ""
        payload_json = row[2] or "{}"
        try:
            payload = json.loads(payload_json) if isinstance(payload_json, str) else (payload_json or {})
        except (TypeError, json.JSONDecodeError):
            payload = {}
        # Check for arc_stage in payload
        stage = payload.get("arc_stage") or ""
        if not stage and "ARC" in event_type.upper():
            stage = payload.get("stage") or payload.get("new_stage") or ""
        stage = stage.upper().strip() if stage else ""
        if stage and stage in ARC_STAGE_CHAPTERS and stage != prev_stage:
            transitions[turn_number] = stage
            prev_stage = stage
    return transitions


def _build_novel_markdown(
    campaign: dict,
    turns: list[dict],
    choices: dict[int, list[str]],
    arc_transitions: dict[int, str],
) -> str:
    """Assemble the full Markdown document."""
    lines: list[str] = []

    # Header
    title = campaign.get("title") or "Untitled Campaign"
    era = campaign.get("time_period") or "Unknown Era"
    lines.append(f"# {title}")
    lines.append(f"*{era}*")
    lines.append("")

    # Sort turns ascending by turn_number
    sorted_turns = sorted(turns, key=lambda t: t.get("turn_number", 0))

    current_chapter: str | None = None

    for turn in sorted_turns:
        tn = turn.get("turn_number", 0)
        text = (turn.get("text") or "").strip()
        if not text:
            continue

        # Check for arc stage transition at this turn
        if tn in arc_transitions:
            stage = arc_transitions[tn]
            chapter_heading = ARC_STAGE_CHAPTERS.get(stage, f"Chapter: {stage}")
            if chapter_heading != current_chapter:
                current_chapter = chapter_heading
                lines.append("")
                lines.append(f"## {chapter_heading}")
                lines.append("")

        # Insert chapter heading for first turn if no transition has fired yet
        if current_chapter is None:
            current_chapter = ARC_STAGE_CHAPTERS.get("SETUP", "Chapter I: Beginnings")
            lines.append(f"## {current_chapter}")
            lines.append("")

        # Player choices as blockquotes
        if tn in choices:
            for choice_text in choices[tn]:
                lines.append(f"> *{choice_text}*")
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
