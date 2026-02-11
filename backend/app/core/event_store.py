"""Event store for turn_events table. Uses sqlite3 only (no ORM)."""
import json
from datetime import datetime, timezone
from typing import Any

from backend.app.models.events import Event


def get_current_turn_number(conn: Any, campaign_id: str) -> int:
    """Return MAX(turn_number) for this campaign, else 0."""
    cur = conn.execute(
        "SELECT COALESCE(MAX(turn_number), 0) AS n FROM turn_events WHERE campaign_id = ?",
        (campaign_id,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def append_events(
    conn: Any,
    campaign_id: str,
    turn_number: int,
    events: list[Event],
    commit: bool = True,
) -> None:
    """Insert events into turn_events. If commit=False, caller manages transaction.

    Uses timestamp as ISO; payload_json = json.dumps(event.payload); is_hidden and is_public_rumor as 0/1.
    """
    ts = datetime.now(timezone.utc).isoformat()
    rows = [
        (
            campaign_id,
            turn_number,
            e.event_type,
            json.dumps(e.payload),
            1 if e.is_hidden else 0,
            1 if getattr(e, "is_public_rumor", False) else 0,
            ts,
        )
        for e in events
    ]
    conn.executemany(
        """INSERT INTO turn_events (campaign_id, turn_number, event_type, payload_json, is_hidden, is_public_rumor, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    if commit:
        conn.commit()


def get_recent_public_rumors(conn: Any, campaign_id: str, limit: int = 3) -> list[str]:
    """Return the last `limit` public rumor texts (is_public_rumor=1), newest first.
    For RUMOR events uses payload.text; for others uses payload or event_type as fallback.
    """
    cur = conn.execute(
        """SELECT event_type, payload_json
           FROM turn_events
           WHERE campaign_id = ? AND (is_public_rumor = 1 OR is_public_rumor = '1')
           ORDER BY turn_number DESC, id DESC
           LIMIT ?""",
        (campaign_id, limit),
    )
    out: list[str] = []
    for row in cur.fetchall():
        event_type = row[0] or ""
        payload = json.loads(row[1]) if row[1] else {}
        text = payload.get("text") if isinstance(payload, dict) else ""
        if not text and isinstance(payload, dict):
            text = str(payload)[:300]
        if not text:
            text = f"[{event_type}]"
        out.append(text.strip() or "[rumor]")
    return out


def get_events(
    conn: Any,
    campaign_id: str,
    since_turn: int = 0,
    include_hidden: bool = True,
) -> list[dict]:
    """Return events for campaign from since_turn onward.

    Ordered by turn_number then id asc. payload_json returned as parsed dict.
    Each row: event_type, payload, is_hidden, turn_number, id.
    If include_hidden is False, only non-hidden events are returned (for player-facing history).
    """
    if include_hidden:
        cur = conn.execute(
            """SELECT id, turn_number, event_type, payload_json, is_hidden
               FROM turn_events
               WHERE campaign_id = ? AND turn_number >= ?
               ORDER BY turn_number ASC, id ASC""",
            (campaign_id, since_turn),
        )
    else:
        cur = conn.execute(
            """SELECT id, turn_number, event_type, payload_json, is_hidden
               FROM turn_events
               WHERE campaign_id = ? AND turn_number >= ? AND (is_hidden = 0 OR is_hidden IS NULL)
               ORDER BY turn_number ASC, id ASC""",
            (campaign_id, since_turn),
        )
    out = []
    for row in cur.fetchall():
        payload = json.loads(row[3]) if row[3] else {}
        out.append({
            "id": row[0],
            "turn_number": row[1],
            "event_type": row[2],
            "payload": payload,
            "is_hidden": bool(row[4]),
        })
    return out
