"""Canonical truth ledger persistence + summarization."""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def ensure_truth_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS truth_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            fact_key TEXT NOT NULL,
            fact_value_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_truth_ledger_campaign_turn ON truth_ledger(campaign_id, turn_number)"
    )


def append_truth_facts(
    conn: sqlite3.Connection,
    campaign_id: str,
    turn_number: int,
    facts: dict[str, Any],
) -> None:
    if not facts:
        return
    ensure_truth_ledger(conn)
    for key, value in facts.items():
        conn.execute(
            "INSERT INTO truth_ledger (campaign_id, turn_number, fact_key, fact_value_json) VALUES (?, ?, ?, ?)",
            (campaign_id, int(turn_number), str(key), json.dumps(value, ensure_ascii=False)),
        )


def load_canonical_facts(conn: sqlite3.Connection, campaign_id: str) -> dict[str, Any]:
    ensure_truth_ledger(conn)
    rows = conn.execute(
        """
        SELECT fact_key, fact_value_json
        FROM truth_ledger
        WHERE campaign_id = ?
        ORDER BY turn_number ASC, id ASC
        """,
        (campaign_id,),
    ).fetchall()
    facts: dict[str, Any] = {}
    for row in rows:
        raw = row[1]
        try:
            facts[row[0]] = json.loads(raw)
        except Exception:
            facts[row[0]] = raw
    return facts


def campaign_summary_from_facts(facts: dict[str, Any], max_items: int = 10) -> str:
    if not facts:
        return "No canonical facts recorded yet."
    lines: list[str] = []
    for idx, (k, v) in enumerate(sorted(facts.items())):
        if idx >= max_items:
            break
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def detect_contradictions(text: str, facts: dict[str, Any]) -> list[str]:
    """Simple contradiction checks against canonical booleans/names."""
    lower = (text or "").lower()
    issues: list[str] = []
    for key, value in facts.items():
        if not isinstance(value, bool):
            continue
        tail = key.split(".")[-1].replace("_", " ")
        if not tail:
            continue
        if value and f"not {tail}" in lower:
            issues.append(f"Narration contradicts truth ledger key '{key}'")
        if (not value) and (f"{tail} is true" in lower or f"{tail} alive" in lower):
            issues.append(f"Narration contradicts truth ledger key '{key}'")
    return issues
