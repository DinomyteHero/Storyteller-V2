"""ProgressionAgent: LLM-driven narrative character progression.

Runs every ~10 turns. Evaluates what the player has been doing — their
narrative achievements, stress endured, relationships built, skills used —
and proposes meaningful stat growth plus a new narrative ability.

This replaces numeric XP grinding with emergent, story-grounded advancement.
No two characters level the same way.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from backend.app.core.agents.base import AgentLLM, ensure_json

logger = logging.getLogger(__name__)

# Max stored progression milestones
MAX_PROGRESSION_HISTORY = 20
# Max narrative abilities
MAX_NARRATIVE_ABILITIES = 10
# Max stat increase per milestone
MAX_STAT_DELTA = 2


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------


def _format_stats(stats: dict[str, int]) -> str:
    if not stats:
        return "(No stats defined)"
    return ", ".join(f"{k}: {v}" for k, v in sorted(stats.items()))


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(No prior progression — this is the first milestone)"
    entries = history[-5:]
    lines = []
    for m in entries:
        turn = m.get("turn", "?")
        theme = m.get("growth_theme", "")
        justification = m.get("justification", "")
        lines.append(f"  Turn {turn} [{theme}]: {justification}")
    return "\n".join(lines)


def _build_system_prompt() -> str:
    return """\
You are the Progression Archivist for a narrative RPG. Your role is to award
meaningful character growth based on what the player has actually done in the story.

You receive:
- The player's current stats and any narrative abilities already unlocked
- Their psychological profile (mood, stress, trauma)
- Their background and what kind of character they are
- A summary of recent story events, established facts, and consequence hints
- Past progression milestones (to avoid repetition)

You must output a JSON object with these fields:

1. STAT_CHANGES — A dict of stat names mapped to integer deltas (+1 or +2 only).
   Award 1-3 stats per milestone. Only award stats that already exist in the player's
   current stats. Growth must be earned by narrative action, not arbitrary.

2. NEW_ABILITY — A single short narrative ability string, or null.
   Example: "Underworld Contacts", "Ghost Protocol (can attempt vanish once per scene)",
   "Silver Tongue (advantage on persuasion in social standoffs)".
   Null if no ability is meaningfully earned this arc.

3. NARRATIVE_JUSTIFICATION — One sentence explaining what the player did to earn
   this progression. Ground it in specific recent events from the facts/narrative.

4. GROWTH_THEME — One of: "combat", "social", "survival", "knowledge", "leadership",
   "spiritual", "criminal", "diplomatic"

CRITICAL RULES:
- STAT_CHANGES values must be +1 or +2. Never negative. Never 0.
- Only include stats that appear in the player's current stats dict.
- NEW_ABILITY should be specific and tied to the story — not generic "+3 to skill".
- NARRATIVE_JUSTIFICATION must reference something that actually happened.
- Do not repeat abilities the player already has.

Return ONLY a single valid JSON object. No markdown. No preamble.

[JSON OUTPUT SCHEMA]
{
  "stat_changes": {"stat_name": int, ...},   // 1-3 existing stats, values +1 or +2
  "new_ability": string | null,               // one narrative ability or null
  "narrative_justification": string,          // <=30 words
  "growth_theme": string                      // one of the listed themes
}"""


def _build_user_prompt(
    player_stats: dict[str, int],
    narrative_abilities: list[str],
    psych_profile: dict,
    background: str,
    progression_history: list[dict],
    established_facts: list[str],
    consequence_hints: list[str],
    recent_narrative: str,
    turn_number: int,
) -> str:
    stats_block = _format_stats(player_stats)
    history_block = _format_history(progression_history)
    abilities_block = (
        ", ".join(narrative_abilities) if narrative_abilities else "(None yet)"
    )
    facts_block = (
        "\n".join(f"  - {f}" for f in established_facts[:10])
        if established_facts
        else "  (No established facts)"
    )
    hints_block = (
        "\n".join(f"  - {h}" for h in consequence_hints[:5])
        if consequence_hints
        else "  (None)"
    )
    psych_str = (
        f"mood={psych_profile.get('current_mood', 'neutral')}, "
        f"stress={psych_profile.get('stress_level', 0)}, "
        f"trauma={psych_profile.get('active_trauma') or 'none'}"
    )
    prose_excerpt = recent_narrative[:600] if recent_narrative else "(No recent narrative)"

    return f"""\
[TURN {turn_number}: PROGRESSION MILESTONE]

[PLAYER STATS]
{stats_block}

[NARRATIVE ABILITIES (already unlocked -- do not repeat)]
{abilities_block}

[PSYCH PROFILE]
{psych_str}

[BACKGROUND]
{background or "(Unknown)"}

[ESTABLISHED FACTS (what has happened in the story)]
{facts_block}

[CONSEQUENCE HINTS (active obligations)]
{hints_block}

[RECENT NARRATIVE]
{prose_excerpt}

[PAST PROGRESSION MILESTONES]
{history_block}

Award narrative character progression for this arc. What stats grew through use?
What new ability did the player earn through their actions? Ground it in the story.
Output only the JSON object."""


# ---------------------------------------------------------------------------
# Output normalization
# ---------------------------------------------------------------------------


def _normalize_output(
    raw: dict,
    current_stats: dict[str, int],
    narrative_abilities: list[str],
) -> tuple[dict[str, int], str | None, str, str]:
    """Validate and normalize LLM output.

    Returns:
        (stat_changes, new_ability, justification, theme)
    """
    raw_changes = raw.get("stat_changes") or {}
    stat_changes: dict[str, int] = {}
    if isinstance(raw_changes, dict):
        for stat, delta in raw_changes.items():
            stat = str(stat).strip()
            try:
                delta = int(delta)
            except (ValueError, TypeError):
                continue
            if stat not in current_stats:
                logger.debug("ProgressionAgent: ignoring unknown stat %r", stat)
                continue
            delta = max(1, min(MAX_STAT_DELTA, delta))
            stat_changes[stat] = delta

    new_ability = raw.get("new_ability")
    if new_ability is not None:
        new_ability = str(new_ability).strip()[:150]
        if not new_ability or new_ability.lower() in {a.lower() for a in narrative_abilities}:
            new_ability = None

    justification = str(raw.get("narrative_justification") or "").strip()[:200] or "Story growth."
    theme = str(raw.get("growth_theme") or "survival").strip().lower()

    return stat_changes, new_ability, justification, theme


# ---------------------------------------------------------------------------
# ProgressionAgent
# ---------------------------------------------------------------------------


class ProgressionAgent:
    """LLM-driven narrative character progression.

    Awards stat growth and narrative abilities every ~10 turns based on
    what the player has actually done in the story. Mutates world_state
    and writes directly to the characters DB table.

    No deterministic fallback. If the LLM fails, the exception propagates.
    """

    def __init__(self) -> None:
        self._llm = AgentLLM("progression")

    def advance(
        self,
        world_state: dict[str, Any],
        player_stats: dict[str, int],
        psych_profile: dict[str, Any],
        background: str,
        turn_number: int,
        recent_narrative: str,
        conn: sqlite3.Connection,
        campaign_id: str,
        player_id: str,
    ) -> str | None:
        """Run a progression milestone.

        Mutates world_state (progression_history, narrative_abilities).
        Writes updated stats_json to the characters table inside the
        caller's transaction (no commit here).

        Returns:
            A player-facing notification string, or None if nothing changed.
        """
        ledger = world_state.get("ledger") or {}
        established_facts = list(ledger.get("established_facts") or [])
        consequence_hints = list(ledger.get("consequence_hints") or [])
        progression_history = list(world_state.get("progression_history") or [])
        narrative_abilities = list(world_state.get("narrative_abilities") or [])

        if not player_stats:
            logger.debug("ProgressionAgent: no stats found — skipping")
            return None

        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(
            player_stats=player_stats,
            narrative_abilities=narrative_abilities,
            psych_profile=psych_profile,
            background=background,
            progression_history=progression_history,
            established_facts=established_facts,
            consequence_hints=consequence_hints,
            recent_narrative=recent_narrative,
            turn_number=turn_number,
        )

        logger.debug(
            "ProgressionAgent: evaluating milestone at turn %d "
            "(stats=%d, abilities=%d, history=%d)",
            turn_number,
            len(player_stats),
            len(narrative_abilities),
            len(progression_history),
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
                "ProgressionAgent: JSON parse failed: %s. Raw (truncated): %r",
                exc,
                str(raw_text)[:300],
            )
            raise ValueError(
                f"ProgressionAgent: LLM returned unparseable JSON. "
                f"Raw (truncated): {str(raw_text)[:200]}"
            ) from exc

        stat_changes, new_ability, justification, theme = _normalize_output(
            raw_json, player_stats, narrative_abilities
        )

        if not stat_changes and not new_ability:
            logger.info(
                "ProgressionAgent: no meaningful progression at turn %d", turn_number
            )
            return None

        # Apply stat changes to a copy and write to DB
        updated_stats = dict(player_stats)
        for stat, delta in stat_changes.items():
            updated_stats[stat] = updated_stats.get(stat, 0) + delta

        conn.execute(
            "UPDATE characters SET stats_json = ? WHERE id = ? AND campaign_id = ?",
            (json.dumps(updated_stats), player_id, campaign_id),
        )
        logger.info(
            "ProgressionAgent: wrote stats_json for player %s (campaign %s): %s",
            player_id,
            campaign_id,
            stat_changes,
        )

        # Append new ability
        if new_ability:
            narrative_abilities.append(new_ability)
            if len(narrative_abilities) > MAX_NARRATIVE_ABILITIES:
                narrative_abilities = narrative_abilities[-MAX_NARRATIVE_ABILITIES:]
            world_state["narrative_abilities"] = narrative_abilities

        # Record milestone
        milestone = {
            "turn": turn_number,
            "stat_changes": stat_changes,
            "new_ability": new_ability,
            "justification": justification,
            "growth_theme": theme,
        }
        progression_history.append(milestone)
        if len(progression_history) > MAX_PROGRESSION_HISTORY:
            progression_history = progression_history[-MAX_PROGRESSION_HISTORY:]
        world_state["progression_history"] = progression_history

        # Build player-facing notification
        parts = []
        if stat_changes:
            stat_str = ", ".join(f"{s} +{d}" for s, d in stat_changes.items())
            parts.append(f"Stats improved: {stat_str}")
        if new_ability:
            parts.append(f"New ability: {new_ability}")
        notification = " | ".join(parts) if parts else None

        logger.info(
            "ProgressionAgent: milestone at turn %d — %s, theme=%s",
            turn_number,
            notification,
            theme,
        )
        return notification
