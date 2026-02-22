"""DecisionLedgerAgent: deferred consequence-delivery tracker (V1.1).

Runs every ~5 turns as a deferred maintenance agent. Scans the decision_ledger
for undelivered promises (wave/tsunami impact decisions whose consequences haven't
been woven into the narrative yet). Cross-references recent narrative and events
to determine if the promise was honored. For overdue promises, escalates them
into the revelation_queue or consequence_hints so the Director/Narrator can
address them.

The key insight: a player who chose to betray someone should see consequences
ripple through the story. If the system promised "may provoke a hostile response"
and 10 turns later nothing happened, the story broke its promise.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from backend.app.core.agents.base import AgentLLM, ensure_json
from backend.app.constants import (
    CONSEQUENCE_DURATION,
    DECISION_LEDGER_PROMISE_URGENCY,
    REVELATION_QUEUE_MAX,
)

logger = logging.getLogger(__name__)


def _build_system_prompt() -> str:
    return """\
You are the Decision Consequence Tracker for a narrative RPG. Your role is to
evaluate whether the story has honored its promises to the player.

When a player makes a choice, the game often hints at consequences ("may provoke
a hostile response", "could change the balance of power"). You evaluate whether
recent narrative and events reflect those consequences.

For each undelivered decision you receive, assess:
1. Has the consequence been delivered (even partially) in recent narrative/events?
2. If not, what should happen next to honor the promise?

Return a JSON object:
{
  "delivered": [
    {"decision_id": int, "evidence": "brief description of how it was delivered"}
  ],
  "escalations": [
    {
      "decision_id": int,
      "consequence_text": "what should happen (max 200 chars)",
      "urgency": "immediate|soon|background",
      "dramatic_value": 1-10
    }
  ]
}

Be conservative: only mark as delivered if the consequence is clearly reflected.
Escalate sparingly — only for wave/tsunami decisions that are truly overdue."""


def _build_user_prompt(
    undelivered: list[dict[str, Any]],
    recent_narrative: str,
    recent_events: list[dict[str, Any]],
    turn_number: int,
) -> str:
    decisions_block = []
    for d in undelivered[:8]:
        age = turn_number - d["turn_number"]
        decisions_block.append(
            f"  - [ID {d['id']}] Turn {d['turn_number']} ({age} turns ago): "
            f"Chose \"{d['chosen_text']}\" ({d['chosen_tone']}). "
            f"Promise: \"{d.get('consequence_hint', 'unspecified')}\". "
            f"Impact: {d['impact_tier']}."
        )

    events_block = []
    for e in recent_events[:10]:
        if not isinstance(e, dict):
            continue
        etype = str(e.get("event_type", "")).upper()
        payload_text = str(e.get("payload", ""))[:100]
        events_block.append(f"  - {etype}: {payload_text}")

    return f"""\
[TURN {turn_number}]

[UNDELIVERED DECISION PROMISES]
{chr(10).join(decisions_block) if decisions_block else "  (none)"}

[RECENT EVENTS (last 5 turns)]
{chr(10).join(events_block) if events_block else "  (no notable events)"}

[RECENT NARRATIVE]
{recent_narrative[:600] if recent_narrative else "(no recent narrative)"}

Evaluate which promises have been delivered and which need escalation."""


class DecisionLedgerAgent:
    """Deferred agent that tracks whether decision consequences have been delivered.

    Runs every DECISION_LEDGER_EVAL_INTERVAL turns. Scans for undelivered
    wave/tsunami promises and escalates overdue ones into the revelation_queue
    or consequence_hints.
    """

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm if llm is not None else AgentLLM("decision_ledger")

    def evaluate(
        self,
        conn: sqlite3.Connection,
        campaign_id: str,
        world_state: dict[str, Any],
        recent_narrative: str,
        recent_events: list[dict[str, Any]],
        turn_number: int,
    ) -> None:
        """Evaluate undelivered decisions and escalate overdue promises."""
        from backend.app.core.decision_ledger import (
            get_undelivered_promises,
            mark_delivered,
        )

        undelivered = get_undelivered_promises(conn, campaign_id, min_impact="wave")
        if not undelivered:
            logger.debug("DecisionLedgerAgent: no undelivered wave+ promises")
            return

        # Filter to only overdue ones (past their consequence duration)
        overdue = []
        for d in undelivered:
            tier = d.get("impact_tier", "ripple")
            max_duration = CONSEQUENCE_DURATION.get(tier, 3)
            age = turn_number - d["turn_number"]
            if age > max_duration:
                overdue.append(d)

        if not overdue:
            logger.debug("DecisionLedgerAgent: no overdue promises")
            return

        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(
            undelivered=overdue,
            recent_narrative=recent_narrative,
            recent_events=recent_events,
            turn_number=turn_number,
        )

        raw_text = self._llm.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
        )

        try:
            result = json.loads(ensure_json(raw_text))
            if not isinstance(result, dict):
                result = {}
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error("DecisionLedgerAgent: JSON parse failed: %s", exc)
            return

        # Process delivered decisions
        delivered = result.get("delivered") or []
        for item in delivered:
            if not isinstance(item, dict):
                continue
            decision_id = item.get("decision_id")
            if isinstance(decision_id, int):
                mark_delivered(conn, campaign_id, decision_id, turn_number)
                logger.info(
                    "DecisionLedgerAgent: marked decision %d as delivered (turn %d)",
                    decision_id,
                    turn_number,
                )

        # Process escalations — inject into revelation_queue
        escalations = result.get("escalations") or []
        revelation_queue = list(world_state.get("revelation_queue") or [])

        for item in escalations:
            if not isinstance(item, dict):
                continue
            decision_id = item.get("decision_id")
            consequence_text = str(item.get("consequence_text", ""))[:200]
            dramatic_value = min(10, max(1, int(item.get("dramatic_value", 5))))

            if not consequence_text:
                continue

            # Don't duplicate existing revelations for the same decision
            existing_ids = {
                r.get("source_decision_id")
                for r in revelation_queue
                if r.get("source_decision_id")
            }
            if decision_id in existing_ids:
                continue

            revelation = {
                "id": f"rev-decision-{decision_id}",
                "content": consequence_text,
                "source": "decision_ledger",
                "source_npc": None,
                "source_decision_id": decision_id,
                "dramatic_value": dramatic_value,
                "optimal_conditions": [
                    str(c)[:100]
                    for c in (item.get("optimal_conditions") or ["any scene"])[:3]
                ],
                "turn_queued": turn_number,
                "revealed": False,
            }
            revelation_queue.append(revelation)
            logger.info(
                "DecisionLedgerAgent: escalated decision %s → revelation (dv=%d)",
                decision_id,
                dramatic_value,
            )

        # Also inject overdue urgent promises into consequence_hints
        ledger = world_state.get("ledger") or {}
        hints = list(ledger.get("consequence_hints") or [])
        for item in escalations:
            if not isinstance(item, dict):
                continue
            urgency = str(item.get("urgency", "")).lower()
            if urgency == "immediate":
                hint_text = str(item.get("consequence_text", ""))[:200]
                if hint_text and hint_text not in hints:
                    hints.append(hint_text)

        # Cap and save
        revelation_queue.sort(
            key=lambda r: r.get("dramatic_value", 0), reverse=True
        )
        world_state["revelation_queue"] = revelation_queue[:REVELATION_QUEUE_MAX]
        if hints:
            ledger["consequence_hints"] = hints[:8]
            world_state["ledger"] = ledger

        logger.info(
            "DecisionLedgerAgent: turn %d — %d delivered, %d escalated",
            turn_number,
            len(delivered),
            len(escalations),
        )
