"""PsychArchivistAgent: LLM-driven psychological arc management.

Runs every ~5 turns. Reads recent narrative, events, and the player's
current emotional state, then produces a richer, story-grounded psych_profile
and an emotional arc note for the Narrator to use as tonal guidance.

This replaces static stress_delta arithmetic with a nuanced LLM assessment
of the character's inner life — trauma, mood shifts, resilience, and growth.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from backend.app.core.agents.base import AgentLLM, ensure_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------


def _format_events_for_psych(events: list[dict]) -> str:
    """Extract psychologically significant events from the turn list."""
    notable = []
    for e in events:
        etype = str(e.get("event_type", "")).upper()
        payload = e.get("payload") or {}
        if etype == "DAMAGE":
            notable.append(f"Took {payload.get('amount', 0)} damage — physical trauma risk")
        elif etype == "PLAYER_PSYCH_UPDATE":
            delta = payload.get("stress_delta", 0)
            if delta > 0:
                notable.append(f"Stress increased by {delta}")
            elif delta < 0:
                notable.append(f"Stress reduced by {abs(delta)}")
        elif etype == "RELATIONSHIP":
            npc = payload.get("npc_id", "?")
            delta = payload.get("delta", 0)
            if delta > 0:
                notable.append(f"Bond with {npc} strengthened")
            elif delta < 0:
                notable.append(f"Conflict or loss with {npc}")
        elif etype in ("NPC_DEATH", "COMPANION_DEATH"):
            name = payload.get("name") or payload.get("npc_id", "someone")
            notable.append(f"Witnessed death of {name}")
        elif etype == "SCALE_CHANGE":
            notable.append(
                f"Campaign stakes escalated "
                f"({payload.get('from_scale')} -> {payload.get('to_scale')})"
            )
        elif etype == "ERA_TRANSITION":
            notable.append(
                f"Era transition: {payload.get('from_era')} -> {payload.get('to_era')} "
                f"— world fundamentally changed"
            )
    return (
        "\n".join(f"  - {n}" for n in notable)
        if notable
        else "  (No significant stress events)"
    )


def _build_system_prompt() -> str:
    return """\
You are the Psychological Archivist for a narrative RPG. Your role is to maintain
a nuanced, story-grounded psychological profile for the player character based on
what they have lived through.

You receive:
- The player's current psych_profile (mood, stress, trauma, arc note)
- Their background and character identity
- Recent narrative prose (what they just experienced)
- Significant psychological events this turn (damage, loss, relationships, stakes)
- Established story facts and active obligations
- The current arc stage (pacing context)

You must output a JSON object with these fields:

1. CURRENT_MOOD — A specific, evocative emotional state (not just "neutral").
   Examples: "wary optimism", "cold determination", "barely-contained grief",
   "detached focus", "hollow victory", "cautious trust", "battle-worn resolve".

2. STRESS_LEVEL — Integer 0-10.
   0 = centered, at peace.  5 = visibly strained, making harder choices.
   8 = on the edge, reactive.  10 = breaking point, needs rest or anchor.
   Stress should DECREASE when: rest/victory/connection. INCREASE when: loss/escalation/failure.
   Reflect the narrative honestly — do not rubber-band to 5.

3. ACTIVE_TRAUMA — A specific unresolved wound from the story, or null.
   Examples: "witnessed Kira's death in the ambush", "betrayed by Mira after trusting her",
   "failed to save the refugees — carries survivor guilt". Null if character is healing.
   Only update when something significant happened — keep existing trauma if unchanged.

4. EMOTIONAL_ARC_NOTE — A short director note (<=25 words) for the Narrator, describing
   the character's current inner state in narrative terms. Used to colour prose voice.
   Examples: "She's running on fumes and spite — every choice feels like the last one.",
   "The victory rings hollow; he's not sure what he's fighting for anymore."

CRITICAL RULES:
- CURRENT_MOOD must be specific and earned by this turn's events. Not generic.
- STRESS_LEVEL must change by <=3 per evaluation cycle. No sudden swings without cause.
- ACTIVE_TRAUMA persists across turns — only clear it if healing is narrated.
- EMOTIONAL_ARC_NOTE must feel like a character note a human director would write.

Return ONLY a single valid JSON object. No markdown. No preamble.

[JSON OUTPUT SCHEMA]
{
  "current_mood": string,
  "stress_level": int,              // 0-10
  "active_trauma": string | null,
  "emotional_arc_note": string      // <=25 words, director tone
}"""


def _build_user_prompt(
    current_psych_profile: dict,
    background: str,
    recent_narrative: str,
    established_facts: list[str],
    consequence_hints: list[str],
    arc_stage: str,
    turn_number: int,
    events: list[dict],
) -> str:
    psych_str = (
        f"current_mood: {current_psych_profile.get('current_mood', 'neutral')}\n"
        f"stress_level: {current_psych_profile.get('stress_level', 0)}\n"
        f"active_trauma: {current_psych_profile.get('active_trauma') or 'none'}\n"
        f"emotional_arc_note: "
        f"{current_psych_profile.get('emotional_arc_note') or '(none set)'}"
    )
    events_block = _format_events_for_psych(events)
    facts_block = (
        "\n".join(f"  - {f}" for f in established_facts[:8])
        if established_facts
        else "  (None)"
    )
    hints_block = (
        "\n".join(f"  - {h}" for h in consequence_hints[:4])
        if consequence_hints
        else "  (None)"
    )
    prose_excerpt = recent_narrative[:700] if recent_narrative else "(No recent narrative)"

    return f"""\
[TURN {turn_number} | ARC STAGE: {arc_stage}]

[CURRENT PSYCH PROFILE]
{psych_str}

[BACKGROUND]
{background or "(Unknown)"}

[PSYCHOLOGICAL EVENTS THIS TURN]
{events_block}

[ESTABLISHED FACTS]
{facts_block}

[ACTIVE OBLIGATIONS (consequence hints)]
{hints_block}

[RECENT NARRATIVE PROSE]
{prose_excerpt}

Assess the player character's psychological state after these events.
Update their mood, stress, trauma, and write a brief arc note for the Narrator.
Output only the JSON object."""


# ---------------------------------------------------------------------------
# Output normalization
# ---------------------------------------------------------------------------


def _normalize_output(raw: dict, current_psych: dict) -> dict:
    """Validate and normalize PsychArchivistAgent output."""
    current_mood = str(
        raw.get("current_mood") or current_psych.get("current_mood") or "neutral"
    ).strip()[:100]

    raw_stress = raw.get("stress_level")
    try:
        new_stress = int(raw_stress)
    except (ValueError, TypeError):
        new_stress = int(current_psych.get("stress_level") or 0)
    current_stress = int(current_psych.get("stress_level") or 0)
    # Clamp delta to ±3 per cycle for psychological realism
    delta = max(-3, min(3, new_stress - current_stress))
    stress_level = max(0, min(10, current_stress + delta))

    # Active trauma: preserve if LLM returns null (persists unless cleared)
    raw_trauma = raw.get("active_trauma")
    if raw_trauma is None:
        active_trauma = current_psych.get("active_trauma")
    elif isinstance(raw_trauma, str) and raw_trauma.strip():
        active_trauma = raw_trauma.strip()[:200]
    else:
        active_trauma = None

    emotional_arc_note = str(raw.get("emotional_arc_note") or "").strip()[:200] or None

    return {
        "current_mood": current_mood,
        "stress_level": stress_level,
        "active_trauma": active_trauma,
        "emotional_arc_note": emotional_arc_note,
    }


# ---------------------------------------------------------------------------
# PsychArchivistAgent
# ---------------------------------------------------------------------------


class PsychArchivistAgent:
    """LLM-driven psychological arc management.

    Runs every ~5 turns to evaluate and update the player character's
    psych_profile with nuanced emotional state derived from narrative events.
    Also generates an 'emotional_arc_note' that the Narrator uses to colour
    the prose voice with the character's current inner life.

    No deterministic fallback. If the LLM fails, the exception propagates.
    """

    def __init__(self) -> None:
        self._llm = AgentLLM("psych_archivist")

    def update(
        self,
        world_state: dict[str, Any],
        current_psych_profile: dict[str, Any],
        background: str,
        turn_number: int,
        recent_narrative: str,
        events: list[dict[str, Any]],
        arc_stage: str,
        conn: sqlite3.Connection,
        campaign_id: str,
        player_id: str,
    ) -> None:
        """Update psych_profile and write emotional_arc_note to world_state.

        Writes the updated psych_profile to the characters table inside the
        caller's transaction (no commit here). Mutates world_state in place.

        Args:
            world_state: Campaign world state dict (mutated in place).
            current_psych_profile: The player's current psych dict.
            background: Player character background string.
            turn_number: Current turn number.
            recent_narrative: Recent narrated prose for context.
            events: All turn events as dicts with event_type + payload.
            arc_stage: Current narrative arc stage string.
            conn: SQLite connection (pre-transaction, no commit called here).
            campaign_id: Campaign identifier.
            player_id: Player character identifier.
        """
        ledger = world_state.get("ledger") or {}
        established_facts = list(ledger.get("established_facts") or [])
        consequence_hints = list(ledger.get("consequence_hints") or [])

        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(
            current_psych_profile=current_psych_profile,
            background=background,
            recent_narrative=recent_narrative,
            established_facts=established_facts,
            consequence_hints=consequence_hints,
            arc_stage=arc_stage,
            turn_number=turn_number,
            events=events,
        )

        logger.debug(
            "PsychArchivistAgent: evaluating psych at turn %d (mood=%r, stress=%d)",
            turn_number,
            current_psych_profile.get("current_mood", "?"),
            int(current_psych_profile.get("stress_level") or 0),
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
                "PsychArchivistAgent: JSON parse failed: %s. Raw (truncated): %r",
                exc,
                str(raw_text)[:300],
            )
            raise ValueError(
                f"PsychArchivistAgent: LLM returned unparseable JSON. "
                f"Raw (truncated): {str(raw_text)[:200]}"
            ) from exc

        updated_psych = _normalize_output(raw_json, current_psych_profile)

        # Write psych_profile to DB (inside caller's open transaction)
        conn.execute(
            "UPDATE characters SET psych_profile = ? WHERE id = ? AND campaign_id = ?",
            (json.dumps(updated_psych), player_id, campaign_id),
        )
        logger.info(
            "PsychArchivistAgent: updated psych for player %s "
            "(mood=%r, stress=%d, arc_note=%r)",
            player_id,
            updated_psych["current_mood"],
            updated_psych["stress_level"],
            (updated_psych.get("emotional_arc_note") or "")[:60],
        )

        # Surface emotional_arc_note to world_state so Narrator can read it
        if updated_psych.get("emotional_arc_note"):
            world_state["emotional_arc_note"] = updated_psych["emotional_arc_note"]

        # Mirror snapshot for within-session reads (e.g. narrator_prompt)
        world_state["psych_profile_snapshot"] = updated_psych
