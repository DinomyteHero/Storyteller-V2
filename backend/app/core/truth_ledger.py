"""Truth ledger persistence and contradiction checks."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.app.models.turn_contract import Fact


def upsert_facts(conn: sqlite3.Connection, campaign_id: str, turn_id: str, facts: list[Fact]) -> None:
    for fact in facts:
        conn.execute(
            """
            INSERT INTO truth_facts (campaign_id, fact_key, fact_value_json, updated_at, source_turn_id)
            VALUES (?, ?, ?, datetime('now'), ?)
            ON CONFLICT(campaign_id, fact_key) DO UPDATE SET
                fact_value_json=excluded.fact_value_json,
                updated_at=excluded.updated_at,
                source_turn_id=excluded.source_turn_id
            """,
            (campaign_id, fact.fact_key, json.dumps(fact.fact_value), turn_id),
        )


def record_event(conn: sqlite3.Connection, campaign_id: str, turn_id: str, event: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO truth_events (campaign_id, turn_id, event_json, created_at) VALUES (?, ?, ?, datetime('now'))",
        (campaign_id, turn_id, json.dumps(event)),
    )


def get_facts(conn: sqlite3.Connection, campaign_id: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT fact_key, fact_value_json FROM truth_facts WHERE campaign_id = ?",
        (campaign_id,),
    ).fetchall()
    out: dict[str, Any] = {}
    for row in rows:
        try:
            out[row["fact_key"]] = json.loads(row["fact_value_json"])
        except Exception:
            out[row["fact_key"]] = row["fact_value_json"]
    return out


def ledger_summary(conn: sqlite3.Connection, campaign_id: str, limit: int = 12) -> list[str]:
    rows = conn.execute(
        """
        SELECT fact_key, fact_value_json FROM truth_facts
        WHERE campaign_id = ?
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (campaign_id, limit),
    ).fetchall()
    summary: list[str] = []
    for row in rows:
        value = row["fact_value_json"]
        try:
            value = json.loads(value)
        except Exception:
            pass
        summary.append(f"{row['fact_key']}: {value}")
    return summary


def contradiction_errors(claims: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    for k, v in claims.items():
        if k in facts and facts[k] != v:
            errs.append(f"Contradiction for fact '{k}': ledger={facts[k]!r} vs claim={v!r}")
    return errs
