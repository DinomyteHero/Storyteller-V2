"""Transcript store: write and read rendered turns (narrator text + citations + suggested_actions)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.app.models.state import ActionSuggestion


def write_rendered_turn(
    conn: sqlite3.Connection,
    campaign_id: str,
    turn_number: int,
    text: str,
    citations: list[dict] | None = None,
    suggested_actions: list[dict] | list[ActionSuggestion] | None = None,
    commit: bool = True,
) -> None:
    """Insert one rendered turn row. If commit=False, caller manages transaction."""
    citations = citations if citations is not None else []
    suggested_actions = suggested_actions if suggested_actions is not None else []
    if suggested_actions and hasattr(suggested_actions[0], "model_dump"):
        suggested_actions = [a.model_dump(mode="json") for a in suggested_actions]
    conn.execute(
        """INSERT INTO rendered_turns (campaign_id, turn_number, text, citations_json, suggested_actions_json)
           VALUES (?, ?, ?, ?, ?)""",
        (
            campaign_id,
            turn_number,
            text,
            json.dumps(citations),
            json.dumps(suggested_actions),
        ),
    )
    if commit:
        conn.commit()


def get_rendered_turns(
    conn: sqlite3.Connection,
    campaign_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return rendered turns for campaign, ordered by turn_number desc. Each dict: turn_number, text, citations, suggested_actions, created_at."""
    cur = conn.execute(
        """SELECT turn_number, text, citations_json, suggested_actions_json, created_at
           FROM rendered_turns
           WHERE campaign_id = ?
           ORDER BY turn_number DESC
           LIMIT ?""",
        (campaign_id, limit),
    )
    out = []
    for row in cur.fetchall():
        turn_number, text, citations_json, suggested_actions_json, created_at = row
        try:
            citations = json.loads(citations_json) if citations_json else []
        except (TypeError, json.JSONDecodeError):
            citations = []
        try:
            suggested_actions = json.loads(suggested_actions_json) if suggested_actions_json else []
        except (TypeError, json.JSONDecodeError):
            suggested_actions = []
        out.append({
            "turn_number": turn_number,
            "text": text or "",
            "citations": citations,
            "suggested_actions": suggested_actions,
            "created_at": created_at,
        })
    return out
