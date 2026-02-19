"""Truth ledger persistence and contradiction checks."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.app.models.turn_contract import Fact


def _has_is_immutable_column(conn: sqlite3.Connection) -> bool:
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(truth_facts)").fetchall()}
        return "is_immutable" in cols
    except Exception:
        return False


def upsert_facts(
    conn: sqlite3.Connection,
    campaign_id: str,
    turn_id: str,
    facts: list[Fact],
    *,
    is_immutable: bool = False,
) -> None:
    has_immutable = _has_is_immutable_column(conn)
    for fact in facts:
        if has_immutable:
            existing = conn.execute(
                "SELECT fact_value_json, is_immutable FROM truth_facts WHERE campaign_id = ? AND fact_key = ?",
                (campaign_id, fact.fact_key),
            ).fetchone()
            if existing:
                prev = existing["fact_value_json"]
                prev_val = prev
                try:
                    prev_val = json.loads(prev)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
                if int(existing["is_immutable"] or 0) == 1 and prev_val != fact.fact_value:
                    # Immutable facts cannot be overwritten.
                    continue
            conn.execute(
                """
                INSERT INTO truth_facts (campaign_id, fact_key, fact_value_json, updated_at, source_turn_id, is_immutable)
                VALUES (?, ?, ?, datetime('now'), ?, ?)
                ON CONFLICT(campaign_id, fact_key) DO UPDATE SET
                    fact_value_json=CASE
                        WHEN truth_facts.is_immutable = 1 THEN truth_facts.fact_value_json
                        ELSE excluded.fact_value_json
                    END,
                    updated_at=excluded.updated_at,
                    source_turn_id=CASE
                        WHEN truth_facts.is_immutable = 1 THEN truth_facts.source_turn_id
                        ELSE excluded.source_turn_id
                    END,
                    is_immutable=CASE
                        WHEN truth_facts.is_immutable = 1 THEN 1
                        ELSE excluded.is_immutable
                    END
                """,
                (campaign_id, fact.fact_key, json.dumps(fact.fact_value), turn_id, 1 if is_immutable else 0),
            )
            continue
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
        except (json.JSONDecodeError, TypeError, ValueError):
            out[row["fact_key"]] = row["fact_value_json"]
    return out


def get_facts_with_meta(conn: sqlite3.Connection, campaign_id: str) -> tuple[dict[str, Any], dict[str, bool]]:
    has_immutable = _has_is_immutable_column(conn)
    if has_immutable:
        rows = conn.execute(
            "SELECT fact_key, fact_value_json, is_immutable FROM truth_facts WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT fact_key, fact_value_json FROM truth_facts WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchall()
    values: dict[str, Any] = {}
    immutable: dict[str, bool] = {}
    for row in rows:
        try:
            values[row["fact_key"]] = json.loads(row["fact_value_json"])
        except (json.JSONDecodeError, TypeError, ValueError):
            values[row["fact_key"]] = row["fact_value_json"]
        immutable[row["fact_key"]] = bool(int(row["is_immutable"])) if has_immutable else False
    return values, immutable


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
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        summary.append(f"{row['fact_key']}: {value}")
    return summary


def contradiction_errors(
    claims: dict[str, Any],
    facts: dict[str, Any],
    immutable_facts: dict[str, bool] | None = None,
    historical_lore_label: str = "established lore",
) -> list[str]:
    errs: list[str] = []
    immutable = immutable_facts or {}
    for k, v in claims.items():
        if k in facts and facts[k] != v:
            if immutable.get(k):
                errs.append(
                    f"CANON VIOLATION: Cannot change '{k}' - this is established {historical_lore_label}"
                )
            else:
                errs.append(f"Contradiction for fact '{k}': ledger={facts[k]!r} vs claim={v!r}")
    return errs
