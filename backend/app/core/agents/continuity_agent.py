"""ContinuityAgent: LLM-managed Truth Ledger 2.0.

Augments the deterministic update_ledger() pass with semantic intelligence.
The LLM reads this turn's narrative prose, player action, and mechanic outcome
alongside the existing ledger, then:

1. Extracts precise narrative facts established this turn (beyond mechanical events)
2. Identifies which existing facts are superseded by new ones (e.g., NPC died →
   remove "NPC X is a potential ally")
3. Marks which open threads were resolved
4. Opens new narrative threads (questions, tensions) raised by this turn
5. Generates consequence hints — promises made, deadlines set, obligations created —
   surfaced as "must remember" notes for the Director

The consequence_hints field is added to the ledger as a new named list.
format_ledger_for_prompt() is extended to render it.

No deterministic fallbacks. If the LLM fails, the exception propagates.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.core.agents.base import AgentLLM, ensure_json
from backend.app.constants import LEDGER_MAX_FACTS, LEDGER_MAX_THREADS

logger = logging.getLogger(__name__)

# Maximum consequence hints to keep in the ledger
LEDGER_MAX_CONSEQUENCE_HINTS = 5


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------


def _format_existing_ledger(ledger: dict) -> str:
    facts = (ledger.get("established_facts") or [])[:12]
    threads = (ledger.get("open_threads") or [])[:6]
    goals = (ledger.get("active_goals") or [])[:5]
    constraints = (ledger.get("constraints") or [])[:5]
    hints = (ledger.get("consequence_hints") or [])[:5]

    lines = []
    if facts:
        lines.append("Established facts:")
        lines.extend(f"  [{i}] {f}" for i, f in enumerate(facts))
    if threads:
        lines.append("Open threads:")
        lines.extend(f"  [{i}] {t}" for i, t in enumerate(threads))
    if goals:
        lines.append("Active goals:")
        lines.extend(f"  - {g}" for g in goals)
    if constraints:
        lines.append("Constraints (must not contradict):")
        lines.extend(f"  - {c}" for c in constraints)
    if hints:
        lines.append("Consequence hints (ongoing obligations):")
        lines.extend(f"  - {h}" for h in hints)
    if not lines:
        lines = ["(Ledger is empty — this is the first turn.)"]
    return "\n".join(lines)


def _format_turn_events(events: list[dict]) -> str:
    """Format notable events from this turn for the LLM."""
    notable = []
    for e in events:
        etype = str(e.get("event_type", "")).upper()
        payload = e.get("payload") or {}
        if etype == "MOVE":
            loc = payload.get("to_location") or payload.get("location_id", "")
            if loc:
                notable.append(f"Player moved to: {loc}")
        elif etype == "DAMAGE":
            notable.append(f"Took {payload.get('amount', 0)} damage")
        elif etype == "HEAL":
            notable.append(f"Healed {payload.get('amount', 0)}")
        elif etype == "ITEM_GET":
            item = payload.get("item_name", "unknown item")
            notable.append(f"Gained: {item}")
        elif etype == "ITEM_LOSE":
            item = payload.get("item_name", "unknown item")
            notable.append(f"Lost: {item}")
        elif etype == "RELATIONSHIP":
            npc = payload.get("npc_id", "unknown")
            delta = payload.get("delta", 0)
            notable.append(f"Relationship with {npc}: {delta:+d}")
        elif etype == "FLAG_SET":
            key = payload.get("key", "")
            val = payload.get("value", "")
            if key:
                notable.append(f"Flag: {key}={val}")
        elif etype == "NPC_SPAWN":
            name = payload.get("name", "")
            role = payload.get("role", "")
            if name:
                notable.append(f"NPC introduced: {name} ({role})")
        elif etype in ("RUMOR_SPREAD", "RUMOR"):
            text = (payload.get("text") or "").strip()[:80]
            if text:
                notable.append(f"Rumor spread: {text}")
    return "\n".join(f"- {n}" for n in notable) if notable else "(No notable events)"


def _build_system_prompt() -> str:
    return """\
You are the Narrative Continuity Archivist for a narrative RPG. Your role is to
maintain the Truth Ledger — a precise record of what has happened, what remains
unresolved, and what obligations the player character has created.

You receive:
- The current ledger (established facts, open threads, consequence hints)
- This turn's narrated prose
- The player's action and its mechanical outcome
- Notable game events from this turn

You must output a JSON object with these fields:

1. NEW_FACTS — Precise new facts established this turn that are NOT already in the ledger.
   Focus on narrative significance: NPC deaths, location changes, alliances made/broken,
   secrets revealed, oaths taken. NOT duplicate of mechanical events already in the ledger.

2. SUPERSEDED_FACTS — Exact text of existing facts that are now false or outdated.
   For example: if the player just killed "Draven Koss", remove any fact stating he's alive.
   Use EXACT text from the existing facts list (index shown in brackets).

3. RESOLVED_THREADS — Exact text of open threads that were addressed or closed this turn.
   A thread is resolved when the question it poses has been answered by narrative events.

4. NEW_THREADS — New unresolved tensions, questions, or hooks opened this turn.
   Write as compelling narrative questions or tensions, not generic filler.

5. CONSEQUENCE_HINTS — Active obligations, promises, and deadlines the player has created.
   Examples: "Promised Kira to return with intel by dawn", "Owes Mira 500 credits",
   "ISB now knows the player's face — hunters incoming". Max 2 per turn, only when earned.

CRITICAL RULES:
- Only extract facts with real narrative weight. Skip trivial events.
- SUPERSEDED_FACTS must be exact text matches from the [indexed] fact list.
- RESOLVED_THREADS must be exact text matches from the open threads list.
- NEW_THREADS must be specific and tied to what just happened — no generic filler.
- CONSEQUENCE_HINTS are precious — only generate when a real obligation was created.
- Be concise: facts ≤15 words, hints ≤20 words.

Return ONLY a single valid JSON object. No markdown. No preamble.

[JSON OUTPUT SCHEMA]
{
  "new_facts": [string],           // 0-4 precise new narrative facts
  "superseded_facts": [string],    // exact text of facts to remove
  "resolved_threads": [string],    // exact text of threads to close
  "new_threads": [string],         // 0-2 new narrative threads/tensions
  "consequence_hints": [string]    // 0-2 active obligations for Director attention
}"""


def _build_user_prompt(
    existing_ledger: dict,
    final_text: str,
    user_input: str,
    outcome_summary: str,
    dice_result: str,
    events: list[dict],
) -> str:
    ledger_block = _format_existing_ledger(existing_ledger)
    events_block = _format_turn_events(events)
    prose_excerpt = final_text[:600] if final_text else "(No narrative text this turn.)"

    return f"""\
[CURRENT LEDGER]
{ledger_block}

[THIS TURN'S EVENTS]
{events_block}

[PLAYER ACTION]
"{user_input}"

[RESOLUTION OUTCOME]
{dice_result} — {outcome_summary}

[NARRATED PROSE (excerpt)]
{prose_excerpt}

Update the Truth Ledger for this turn. What new facts were established?
What existing facts are now false? What threads were resolved? What new
tensions were opened? What obligations did the player create?
Output only the JSON object."""


# ---------------------------------------------------------------------------
# Output normalization
# ---------------------------------------------------------------------------


def _normalize_output(
    raw: dict,
    existing_ledger: dict,
) -> dict:
    """Apply ContinuityAgent output to the existing ledger. Returns updated ledger."""
    ledger = dict(existing_ledger)

    facts = list(ledger.get("established_facts") or [])
    threads = list(ledger.get("open_threads") or [])
    goals = list(ledger.get("active_goals") or [])
    constraints = list(ledger.get("constraints") or [])
    tone_tags = list(ledger.get("tone_tags") or [])
    active_themes = list(ledger.get("active_themes") or [])
    existing_hints = list(ledger.get("consequence_hints") or [])

    # Remove superseded facts (exact text match)
    superseded = [str(s).strip() for s in (raw.get("superseded_facts") or []) if s]
    if superseded:
        # Match ignoring [Wn] weight prefixes
        import re as _re
        def _bare(s: str) -> str:
            return _re.sub(r"^\[W\d\]", "", s).strip()
        bare_superseded = {_bare(s) for s in superseded}
        facts = [f for f in facts if _bare(f) not in bare_superseded]
        logger.debug("ContinuityAgent: removed %d superseded facts", len(superseded))

    # Remove resolved threads (exact text match)
    resolved = [str(r).strip() for r in (raw.get("resolved_threads") or []) if r]
    if resolved:
        import re as _re
        def _bare(s: str) -> str:
            return _re.sub(r"^\[W\d\]", "", s).strip()
        bare_resolved = {_bare(r) for r in resolved}
        threads = [t for t in threads if _bare(t) not in bare_resolved]
        logger.debug("ContinuityAgent: closed %d threads", len(resolved))

    # Add new facts
    new_facts = [str(f).strip()[:200] for f in (raw.get("new_facts") or []) if f and str(f).strip()]
    for fact in new_facts:
        if fact not in facts:
            facts.append(fact)
    if len(facts) > LEDGER_MAX_FACTS:
        facts = facts[-LEDGER_MAX_FACTS:]

    # Add new threads
    new_threads = [str(t).strip()[:200] for t in (raw.get("new_threads") or []) if t and str(t).strip()]
    for thread in new_threads[:2]:
        if thread not in threads:
            threads.append(thread)
    if len(threads) > LEDGER_MAX_THREADS:
        threads = threads[-LEDGER_MAX_THREADS:]

    # Merge consequence hints (prepend new ones, keep most recent cap)
    new_hints = [str(h).strip()[:200] for h in (raw.get("consequence_hints") or []) if h and str(h).strip()]
    merged_hints = new_hints + [h for h in existing_hints if h not in new_hints]
    consequence_hints = merged_hints[:LEDGER_MAX_CONSEQUENCE_HINTS]

    return {
        "established_facts": facts,
        "open_threads": threads,
        "active_goals": goals,
        "constraints": constraints,
        "tone_tags": tone_tags,
        "active_themes": active_themes,
        "consequence_hints": consequence_hints,
    }


# ---------------------------------------------------------------------------
# ContinuityAgent
# ---------------------------------------------------------------------------


class ContinuityAgent:
    """LLM-managed Truth Ledger 2.0.

    Runs after update_ledger() (deterministic mechanical extraction) to apply
    a semantic intelligence pass: pruning stale facts, extracting narrative
    significance, and generating consequence hints that tie the Director back
    to promises and obligations created by the player.

    No deterministic fallback. If the LLM fails, the exception propagates.
    """

    def __init__(self) -> None:
        self._llm = AgentLLM("continuity")

    def update(
        self,
        world_state: dict[str, Any],
        final_text: str,
        user_input: str,
        mechanic_result: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None:
        """Update world_state['ledger'] with LLM-curated entries.

        Mutates world_state in place (same pattern as MemoryAgent).

        Args:
            world_state: The campaign world state dict (mutated in place).
            final_text: The narrated prose from this turn.
            user_input: The player's raw input.
            mechanic_result: The MechanicOutput dict for this turn.
            events: All turn events (list of dicts with event_type + payload).
        """
        existing_ledger = world_state.get("ledger") or {}
        outcome_summary = str(mechanic_result.get("outcome_summary") or "").strip()[:200]
        dice_result = str(mechanic_result.get("dice_result") or "Success").strip()

        if not final_text and not events:
            return  # Nothing to update

        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(
            existing_ledger=existing_ledger,
            final_text=final_text,
            user_input=user_input,
            outcome_summary=outcome_summary,
            dice_result=dice_result,
            events=events,
        )

        logger.debug(
            "ContinuityAgent: updating ledger for turn "
            "(facts=%d, threads=%d, hints=%d)",
            len(existing_ledger.get("established_facts") or []),
            len(existing_ledger.get("open_threads") or []),
            len(existing_ledger.get("consequence_hints") or []),
        )

        raw_text = self._llm.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
        )

        try:
            raw_json = json.loads(ensure_json(raw_text))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error(
                "ContinuityAgent: JSON parse failed: %s. Raw (truncated): %r",
                exc, str(raw_text)[:300],
            )
            raise ValueError(
                f"ContinuityAgent: LLM returned unparseable JSON. "
                f"Raw (truncated): {str(raw_text)[:200]}"
            ) from exc

        updated = _normalize_output(raw_json, existing_ledger)
        world_state["ledger"] = updated

        logger.info(
            "ContinuityAgent: +%d facts, -%d superseded, -%d threads closed, "
            "+%d threads, %d consequence hints",
            len(raw_json.get("new_facts") or []),
            len(raw_json.get("superseded_facts") or []),
            len(raw_json.get("resolved_threads") or []),
            len(raw_json.get("new_threads") or []),
            len(updated.get("consequence_hints") or []),
        )
