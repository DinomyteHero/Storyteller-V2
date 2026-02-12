"""NPC persistent memory system.

Tracks NPC-specific interactions across turns so NPCs remember player
behavior (betrayals, help, trade, combat). Used by the Director node
to inject NPC-specific memory context into scene framing.

Storage: npc_memory table in SQLite (append-only, aligns with event sourcing).
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

# Event types that generate NPC memories
_NPC_EVENT_TYPES = frozenset({
    "DIALOGUE", "RELATIONSHIP", "DAMAGE", "HEAL",
    "NPC_SPAWN", "NPC_ACTION", "TRADE", "BETRAYAL",
})

# Sentiment mapping for event types (default 0 = neutral)
_EVENT_SENTIMENT: dict[str, int] = {
    "BETRAYAL": -8,
    "DAMAGE": -5,
    "HEAL": 5,
    "TRADE": 3,
    "RELATIONSHIP": 0,  # Determined by delta in payload
    "DIALOGUE": 1,
    "NPC_SPAWN": 0,
    "NPC_ACTION": 0,
}


def ensure_npc_memory_table(conn: sqlite3.Connection) -> None:
    """Create the npc_memory table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS npc_memory (
            campaign_id TEXT NOT NULL,
            npc_name TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            sentiment INTEGER DEFAULT 0,
            PRIMARY KEY (campaign_id, npc_name, turn_number, event_type)
        )
    """)


def record_npc_interaction(
    conn: sqlite3.Connection,
    campaign_id: str,
    npc_name: str,
    turn_number: int,
    event_type: str,
    summary: str,
    sentiment: int = 0,
) -> None:
    """Record a single NPC interaction memory."""
    try:
        conn.execute(
            """INSERT OR REPLACE INTO npc_memory
               (campaign_id, npc_name, turn_number, event_type, summary, sentiment)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (campaign_id, npc_name, turn_number, event_type, summary[:200], sentiment),
        )
    except Exception as e:
        logger.warning("Failed to record NPC memory for %s: %s", npc_name, e)


def recall_npc_memory(
    conn: sqlite3.Connection,
    campaign_id: str,
    npc_name: str,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve recent memories for an NPC, ordered by recency."""
    try:
        rows = conn.execute(
            """SELECT turn_number, event_type, summary, sentiment
               FROM npc_memory
               WHERE campaign_id = ? AND npc_name = ?
               ORDER BY turn_number DESC
               LIMIT ?""",
            (campaign_id, npc_name, max_results),
        ).fetchall()
        return [
            {
                "turn_number": r[0],
                "event_type": r[1],
                "summary": r[2],
                "sentiment": r[3],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("Failed to recall NPC memory for %s: %s", npc_name, e)
        return []


def format_npc_memory_for_prompt(memories: list[dict[str, Any]], npc_name: str) -> str:
    """Format NPC memories into a prompt-ready string for Director/Narrator context."""
    if not memories:
        return ""
    lines = [f"## {npc_name}'s Memory of the Player"]
    total_sentiment = 0
    for m in memories:
        sentiment = m.get("sentiment", 0)
        total_sentiment += sentiment
        lines.append(f"- Turn {m['turn_number']}: {m['summary']}")

    # Add disposition summary
    if total_sentiment >= 5:
        lines.append(f"Overall disposition: FRIENDLY (sentiment: {total_sentiment:+d})")
    elif total_sentiment <= -5:
        lines.append(f"Overall disposition: HOSTILE (sentiment: {total_sentiment:+d})")
    else:
        lines.append(f"Overall disposition: NEUTRAL (sentiment: {total_sentiment:+d})")

    return "\n".join(lines)


def extract_npc_memories_from_events(
    events: list[Any],
    present_npcs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Extract NPC-relevant memories from turn events.

    Returns list of dicts with: npc_name, event_type, summary, sentiment.
    """
    memories: list[dict[str, Any]] = []
    npc_names = set()
    if present_npcs:
        for npc in present_npcs:
            name = npc.get("name", "") if isinstance(npc, dict) else ""
            if name:
                npc_names.add(name)

    for e in events:
        if isinstance(e, dict):
            etype = str(e.get("event_type", "")).upper()
            payload = e.get("payload") or {}
        else:
            etype = str(getattr(e, "event_type", "")).upper()
            payload = getattr(e, "payload", None) or {}

        if etype not in _NPC_EVENT_TYPES:
            continue

        npc_name = ""
        summary = ""
        sentiment = _EVENT_SENTIMENT.get(etype, 0)

        if etype == "DIALOGUE":
            speaker = payload.get("speaker", "")
            if speaker and speaker != "Player" and speaker in npc_names:
                npc_name = speaker
                text = (payload.get("text") or "")[:80]
                summary = f"Player spoke with {npc_name}: {text}"
        elif etype == "RELATIONSHIP":
            npc_id = payload.get("npc_id", "")
            delta = int(payload.get("delta", 0))
            if npc_id:
                npc_name = npc_id
                sentiment = max(-10, min(10, delta))
                summary = f"Relationship changed by {delta:+d}"
        elif etype == "DAMAGE":
            target = payload.get("target", "")
            if target and target in npc_names:
                npc_name = target
                amount = payload.get("amount", 0)
                summary = f"Player dealt {amount} damage to {npc_name}"
        elif etype == "HEAL":
            target = payload.get("target", "")
            if target and target in npc_names:
                npc_name = target
                amount = payload.get("amount", 0)
                summary = f"Player healed {npc_name} for {amount}"
        elif etype == "NPC_ACTION":
            text = (payload.get("text") or "").strip()
            npc_id = payload.get("npc_id", "")
            if npc_id and text:
                npc_name = npc_id
                summary = text[:100]

        if npc_name and summary:
            memories.append({
                "npc_name": npc_name,
                "event_type": etype,
                "summary": summary,
                "sentiment": sentiment,
            })

    return memories
