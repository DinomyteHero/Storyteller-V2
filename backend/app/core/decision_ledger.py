"""Decision Ledger: first-class semantic tracking of player decisions.

Records what the player chose, what they rejected, the promised consequences,
and whether those consequences have been delivered. Used by the Narrator,
ChoiceCrafter, and DecisionLedgerAgent to maintain narrative coherence.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def record_decision(
    conn: sqlite3.Connection,
    campaign_id: str,
    turn_number: int,
    chosen_text: str,
    chosen_tone: str,
    rejected_options: list[dict[str, Any]],
    consequence_hint: str | None = None,
    impact_tier: str = "ripple",
    context_summary: str | None = None,
    tags: list[str] | None = None,
) -> int | None:
    """Insert a decision record. Returns the new row id, or None on failure."""
    try:
        cur = conn.execute(
            """INSERT INTO decision_ledger
               (campaign_id, turn_number, chosen_text, chosen_tone,
                rejected_options_json, consequence_hint, impact_tier,
                context_summary, tags_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                campaign_id,
                turn_number,
                chosen_text[:500],
                (chosen_tone or "NEUTRAL").upper(),
                json.dumps(rejected_options[:10], default=str),
                (consequence_hint or "")[:500],
                impact_tier if impact_tier in ("ripple", "wave", "tsunami") else "ripple",
                (context_summary or "")[:500],
                json.dumps(tags or [], default=str),
            ),
        )
        return cur.lastrowid
    except sqlite3.OperationalError:
        # Table may not exist yet (pre-migration)
        logger.debug("decision_ledger table not available, skipping record")
        return None


def get_recent_decisions(
    conn: sqlite3.Connection,
    campaign_id: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the most recent decisions, newest first."""
    try:
        cur = conn.execute(
            """SELECT id, turn_number, chosen_text, chosen_tone,
                      rejected_options_json, consequence_hint, impact_tier,
                      context_summary, outcome_delivered, outcome_turn, tags_json
               FROM decision_ledger
               WHERE campaign_id = ?
               ORDER BY turn_number DESC
               LIMIT ?""",
            (campaign_id, limit),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        return []

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append({
            "id": row[0],
            "turn_number": row[1],
            "chosen_text": row[2],
            "chosen_tone": row[3],
            "rejected_options": _safe_json(row[4]),
            "consequence_hint": row[5],
            "impact_tier": row[6],
            "context_summary": row[7],
            "outcome_delivered": bool(row[8]),
            "outcome_turn": row[9],
            "tags": _safe_json(row[10]),
        })
    return results


def get_undelivered_promises(
    conn: sqlite3.Connection,
    campaign_id: str,
    min_impact: str = "ripple",
) -> list[dict[str, Any]]:
    """Return undelivered decisions, optionally filtered by minimum impact tier."""
    tier_order = {"ripple": 0, "wave": 1, "tsunami": 2}
    min_rank = tier_order.get(min_impact, 0)

    try:
        cur = conn.execute(
            """SELECT id, turn_number, chosen_text, chosen_tone,
                      consequence_hint, impact_tier, tags_json
               FROM decision_ledger
               WHERE campaign_id = ? AND outcome_delivered = 0
               ORDER BY turn_number ASC""",
            (campaign_id,),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        return []

    results: list[dict[str, Any]] = []
    for row in rows:
        tier = row[5] or "ripple"
        if tier_order.get(tier, 0) >= min_rank:
            results.append({
                "id": row[0],
                "turn_number": row[1],
                "chosen_text": row[2],
                "chosen_tone": row[3],
                "consequence_hint": row[4],
                "impact_tier": tier,
                "tags": _safe_json(row[6]),
            })
    return results


def mark_delivered(
    conn: sqlite3.Connection,
    campaign_id: str,
    decision_id: int,
    outcome_turn: int,
) -> None:
    """Mark a decision's consequence as delivered."""
    try:
        conn.execute(
            """UPDATE decision_ledger
               SET outcome_delivered = 1, outcome_turn = ?
               WHERE id = ? AND campaign_id = ?""",
            (outcome_turn, decision_id, campaign_id),
        )
    except sqlite3.OperationalError:
        logger.debug("decision_ledger table not available for mark_delivered")


def get_decisions_by_tags(
    conn: sqlite3.Connection,
    campaign_id: str,
    tags: list[str],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return decisions that match any of the given tags (JSON array contains check)."""
    if not tags:
        return []

    try:
        # Build OR conditions for tag matching via JSON
        conditions = " OR ".join(
            "tags_json LIKE ?" for _ in tags
        )
        params: list[Any] = [campaign_id]
        params.extend(f'%"{tag}"%' for tag in tags)

        cur = conn.execute(
            f"""SELECT id, turn_number, chosen_text, chosen_tone,
                       consequence_hint, impact_tier, tags_json,
                       outcome_delivered
                FROM decision_ledger
                WHERE campaign_id = ? AND ({conditions})
                ORDER BY turn_number DESC
                LIMIT ?""",
            (*params, limit),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        return []

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append({
            "id": row[0],
            "turn_number": row[1],
            "chosen_text": row[2],
            "chosen_tone": row[3],
            "consequence_hint": row[4],
            "impact_tier": row[5],
            "tags": _safe_json(row[6]),
            "outcome_delivered": bool(row[7]),
        })
    return results


def get_relevant_decisions_for_scene(
    conn: sqlite3.Connection,
    campaign_id: str,
    current_turn: int,
    scene_tags: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the most narratively relevant decisions for the current scene.

    Scoring: impact_tier weight + recency + tag overlap with scene.
    """
    recent = get_recent_decisions(conn, campaign_id, limit=30)
    if not recent:
        return []

    tier_weight = {"tsunami": 10, "wave": 5, "ripple": 1}
    scene_tag_set = set(scene_tags or [])

    scored: list[tuple[float, dict[str, Any]]] = []
    for d in recent:
        # Impact weight
        score = float(tier_weight.get(d["impact_tier"], 1))

        # Recency bonus (closer to current turn = higher)
        turns_ago = max(1, current_turn - d["turn_number"])
        score += 5.0 / turns_ago

        # Undelivered promise bonus
        if not d["outcome_delivered"] and d["consequence_hint"]:
            score += 3.0

        # Tag overlap bonus
        decision_tags = set(d.get("tags") or [])
        overlap = len(decision_tags & scene_tag_set)
        score += overlap * 2.0

        scored.append((score, d))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:limit]]


def format_decisions_for_prompt(
    decisions: list[dict[str, Any]],
    max_entries: int = 5,
) -> str:
    """Format decision entries for injection into LLM prompts."""
    if not decisions:
        return ""

    lines: list[str] = []
    for d in decisions[:max_entries]:
        parts = [f"Turn {d['turn_number']}: You chose to {d['chosen_text']} ({d['chosen_tone']})."]

        # Show what was rejected (most contrasting option)
        rejected = d.get("rejected_options") or []
        if rejected:
            # Pick the most contrasting rejected option (different tone if possible)
            contrasting = [r for r in rejected if r.get("tone", "").upper() != d["chosen_tone"]]
            if contrasting:
                rej = contrasting[0]
            else:
                rej = rejected[0]
            rej_text = rej.get("text", "")
            if rej_text:
                parts.append(f"You rejected: \"{rej_text}\".")

        # Consequence promise
        hint = d.get("consequence_hint", "")
        if hint:
            delivered = d.get("outcome_delivered", False)
            if delivered:
                parts.append(f"Consequence: {hint} [DELIVERED turn {d.get('outcome_turn', '?')}].")
            else:
                parts.append(f"Promise: {hint} [PENDING].")

        lines.append(" ".join(parts))

    return "\n".join(lines)


def _safe_json(raw: Any) -> list[Any]:
    """Parse a JSON string into a list, or return empty list."""
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (TypeError, json.JSONDecodeError):
        return []
