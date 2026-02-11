"""Narrative ledger utilities (deterministic, cheap)."""
from __future__ import annotations

import logging
import re
from typing import Any

from backend.app.constants import (
    LEDGER_MAX_CONSTRAINTS,
    LEDGER_MAX_FACTS,
    LEDGER_MAX_GOALS,
    LEDGER_MAX_THEMES,
    LEDGER_MAX_THREADS,
    LEDGER_MAX_TONE_TAGS,
    MEMORY_COMPRESSION_CHUNK_SIZE,
    MEMORY_ERA_SUMMARY_MAX_CHARS,
    MEMORY_MAX_ERA_SUMMARIES,
    MEMORY_RECENT_TURNS,
    THEME_REINFORCEMENT_KEYWORDS,
)

logger = logging.getLogger(__name__)

try:
    from backend.app.models.events import Event
except Exception as e:  # pragma: no cover - type-only fallback
    logger.debug("Failed to import Event; using Any fallback: %s", e)
    Event = Any  # type: ignore[assignment]

def default_ledger() -> dict[str, list[str]]:
    return {
        "established_facts": [],
        "open_threads": [],
        "active_goals": [],
        "constraints": [],
        "tone_tags": [],
        "active_themes": [],
    }


def update_ledger(
    previous: dict | None,
    new_events: list[Event] | list[dict] | None,
    narrated_text: str | None,
) -> dict[str, list[str]]:
    ledger = _normalize_ledger(previous)
    events = new_events or []
    narrated_text = narrated_text or ""

    facts = list(ledger.get("established_facts") or [])
    threads = list(ledger.get("open_threads") or [])
    goals = list(ledger.get("active_goals") or [])
    constraints = list(ledger.get("constraints") or [])
    tone_tags = list(ledger.get("tone_tags") or [])

    active_themes = list(ledger.get("active_themes") or [])

    facts, constraints, threads, goals = _apply_events(
        events, facts, constraints, threads, goals
    )
    threads = _threads_from_text(narrated_text, threads, active_themes=active_themes)
    tone_tags = _tone_tags_from_text(narrated_text, tone_tags)
    active_themes = _themes_from_text(narrated_text, active_themes)

    facts = _dedupe_and_trim(facts, LEDGER_MAX_FACTS)
    threads = _dedupe_and_trim(threads, LEDGER_MAX_THREADS)
    goals = _dedupe_and_trim(goals, LEDGER_MAX_GOALS)
    constraints = _dedupe_and_trim(constraints, LEDGER_MAX_CONSTRAINTS)
    tone_tags = _dedupe_and_trim(tone_tags, LEDGER_MAX_TONE_TAGS)
    active_themes = _dedupe_and_trim(active_themes, LEDGER_MAX_THEMES)

    if not tone_tags:
        tone_tags = ["neutral"]

    return {
        "established_facts": facts,
        "open_threads": threads,
        "active_goals": goals,
        "constraints": constraints,
        "tone_tags": tone_tags,
        "active_themes": active_themes,
    }


def format_ledger_for_prompt(ledger: dict | None) -> str:
    ledger = _normalize_ledger(ledger)
    if not any(ledger.values()):
        return "(No ledger yet.)"
    parts = []
    parts.append("Established facts:")
    parts.extend(_bullets(ledger.get("established_facts") or [], limit=LEDGER_MAX_FACTS))
    parts.append("Open threads:")
    parts.extend(_bullets(ledger.get("open_threads") or [], limit=LEDGER_MAX_THREADS))
    parts.append("Active goals:")
    parts.extend(_bullets(ledger.get("active_goals") or [], limit=LEDGER_MAX_GOALS))
    parts.append("Constraints (must not contradict):")
    parts.extend(_bullets(ledger.get("constraints") or [], limit=LEDGER_MAX_CONSTRAINTS))
    parts.append("Tone tags:")
    parts.extend(_bullets(ledger.get("tone_tags") or [], limit=LEDGER_MAX_TONE_TAGS))
    themes = ledger.get("active_themes") or []
    if themes:
        parts.append("Active themes:")
        parts.extend(_bullets(themes, limit=LEDGER_MAX_THEMES))
    return "\n".join(parts)


def _normalize_ledger(ledger: dict | None) -> dict[str, list[str]]:
    base = default_ledger()
    if not isinstance(ledger, dict):
        return base
    for key in base:
        val = ledger.get(key)
        if isinstance(val, list):
            base[key] = [str(v).strip() for v in val if str(v).strip()]
    # Also preserve active_themes from existing ledger (backward compat)
    if "active_themes" not in base:
        base["active_themes"] = []
    return base


def _apply_events(
    events: list[Event] | list[dict],
    facts: list[str],
    constraints: list[str],
    threads: list[str],
    goals: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    for e in events:
        if isinstance(e, dict):
            event_type = str(e.get("event_type", "")).upper()
            payload = e.get("payload") or {}
        else:
            event_type = str(getattr(e, "event_type", "")).upper()
            payload = getattr(e, "payload", None) or {}
        if event_type == "MOVE":
            to_loc = payload.get("to_location") or payload.get("location_id")
            if to_loc:
                facts = _replace_prefix(facts, "Location:", f"Location: {to_loc}")
                constraints = _replace_prefix(constraints, "Location:", f"Location: {to_loc}")
        elif event_type == "DAMAGE":
            amount = payload.get("amount", 0)
            facts.append(f"Damage taken: {amount}.")
        elif event_type == "HEAL":
            amount = payload.get("amount", 0)
            facts.append(f"Healed for {amount}.")
        elif event_type == "ITEM_GET":
            item = payload.get("item_name")
            delta = payload.get("quantity_delta", payload.get("quantity", 1))
            if item:
                facts.append(f"Gained item: {item} x{delta}.")
        elif event_type == "ITEM_LOSE":
            item = payload.get("item_name")
            delta = payload.get("quantity_delta", payload.get("quantity", 1))
            if item:
                facts.append(f"Lost item: {item} x{delta}.")
        elif event_type == "RELATIONSHIP":
            npc_id = payload.get("npc_id")
            delta = payload.get("delta", 0)
            if npc_id:
                facts.append(f"Relationship change with {npc_id}: {delta:+d}.")
        elif event_type == "FLAG_SET":
            key = payload.get("key")
            value = payload.get("value")
            if key:
                facts.append(f"Flag set: {key}={value}.")
                if "quest" in str(key).lower() or "goal" in str(key).lower():
                    goals.append(f"Advance {key}.")
        elif event_type == "NPC_SPAWN":
            name = payload.get("name")
            role = payload.get("role")
            if name:
                facts.append(f"NPC introduced: {name} ({role or 'NPC'}).")
        elif event_type in ("RUMOR", "RUMOR_SPREAD"):
            text = (payload.get("text") or "").strip()
            if text:
                threads.append(f"Rumor: {text}")
        elif event_type == "FACTION_MOVE":
            text = (payload.get("text") or "").strip()
            faction = payload.get("faction")
            if text:
                facts.append(f"Faction move: {text}")
            elif faction:
                facts.append(f"Faction updated: {faction}.")
        elif event_type == "NPC_ACTION":
            text = (payload.get("text") or "").strip()
            if text:
                facts.append(f"NPC action: {text}")
        elif event_type == "STORY_NOTE":
            text = (payload.get("text") or "").strip()
            if text:
                facts.append(text)
        elif event_type == "PLOT_TICK":
            text = (payload.get("text") or "").strip()
            if text:
                threads.append(f"Plot: {text}")
    return facts, constraints, threads, goals


def _score_thread(thread_text: str, active_themes: list[str] | None = None) -> int:
    """Score a thread's narrative significance (1-3).

    Weight 3: Contains named entities (capitalized proper nouns) + length > 40 chars
    Weight 2: Contains theme keywords or named entities or length > 30 chars
    Weight 1: Short/generic threads (navigation questions, filler)
    """
    text = thread_text.strip()
    # Strip existing weight prefix if present
    if re.match(r"^\[W\d\]", text):
        text = text[4:]

    weight = 1
    # Length heuristic: longer threads are more complex
    if len(text) > 40:
        weight = max(weight, 2)
    # Named entity check: capitalized words that aren't sentence starters
    words = text.split()
    has_entity = False
    for i, w in enumerate(words):
        if i == 0:
            continue  # skip sentence start
        cleaned = re.sub(r"[^A-Za-z']", "", w)
        if len(cleaned) >= 3 and cleaned[0].isupper():
            has_entity = True
            break
    if has_entity:
        weight = max(weight, 2)
        if len(text) > 40:
            weight = 3
    # Theme keyword overlap: threads touching active themes are more significant
    if active_themes:
        lower = text.lower()
        for theme_keywords in THEME_REINFORCEMENT_KEYWORDS.values():
            hits = sum(1 for kw in theme_keywords if kw in lower)
            if hits >= 1:
                weight = max(weight, 2)
                break
    return weight


def weighted_thread_count(threads: list[str]) -> int:
    """Count threads by their semantic weight (W3=3, W2=2, W1=1).

    Threads with [W<n>] prefix use their stored weight.
    Threads without prefix default to weight 1.
    """
    total = 0
    for t in threads:
        m = re.match(r"^\[W(\d)\]", t)
        if m:
            total += int(m.group(1))
        else:
            total += 1
    return total


def _threads_from_text(text: str, threads: list[str], active_themes: list[str] | None = None) -> list[str]:
    if not text:
        return threads
    questions = re.findall(r"([^?]{5,160}\?)", text)
    for q in questions[-3:]:
        cleaned = q.strip()
        if cleaned and cleaned not in threads:
            # 2.4: Score thread significance and prefix with weight
            w = _score_thread(cleaned, active_themes)
            weighted = f"[W{w}]{cleaned}"
            # Check dedup without prefix
            bare_threads = [re.sub(r"^\[W\d\]", "", t) for t in threads]
            if cleaned not in bare_threads:
                threads.append(weighted)
    if len(threads) < 3:
        fillers = [
            "[W1]Resolve the immediate scene.",
            "[W1]Clarify the next action.",
            "[W1]Address any new complications.",
        ]
        for f in fillers:
            if len(threads) >= 3:
                break
            if f not in threads:
                threads.append(f)
    return threads


def _tone_tags_from_text(text: str, existing: list[str]) -> list[str]:
    if not text:
        return existing
    lower = text.lower()
    tags = list(existing)
    if re.search(r"\b(urgent|hurry|immediate|now)\b", lower):
        tags.append("urgent")
    if re.search(r"\b(tense|danger|blood|scream|attack|fight)\b", lower):
        tags.append("tense")
    if re.search(r"\b(calm|quiet|gentle|soft|warm)\b", lower):
        tags.append("calm")
    if re.search(r"\b(mystery|mysterious|shadow|whisper|unknown)\b", lower):
        tags.append("mysterious")
    if not tags:
        tags.append("neutral")
    return tags


def _themes_from_text(text: str, existing_themes: list[str]) -> list[str]:
    """Deterministic theme extraction from narrated text using keyword hits.

    A theme activates when 2+ keywords match. Existing themes are stable —
    they remain unless a stronger new theme pushes them out (capped at
    LEDGER_MAX_THEMES).
    """
    if not text:
        return existing_themes
    lower = text.lower()
    scored: list[tuple[str, int]] = []
    for theme, keywords in THEME_REINFORCEMENT_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lower)
        if hits >= 2:
            scored.append((theme, hits))
    scored.sort(key=lambda x: -x[1])
    # Merge: keep existing themes, add new strong ones up to cap
    merged = list(existing_themes)
    for theme, _hits in scored:
        if theme not in merged:
            merged.append(theme)
    if len(merged) > LEDGER_MAX_THEMES:
        merged = merged[:LEDGER_MAX_THEMES]
    return merged


def _dedupe_and_trim(items: list[str], limit: int) -> list[str]:
    out: list[str] = []
    seen = set()
    for item in items:
        if not item:
            continue
        s = str(item).strip()
        if not s or s in seen:
            continue
        out.append(s[:200])
        seen.add(s)
    if limit and len(out) > limit:
        out = out[-limit:]
    return out


def _replace_prefix(items: list[str], prefix: str, value: str) -> list[str]:
    out = [i for i in items if not i.startswith(prefix)]
    out.append(value)
    return out


def _bullets(items: list[str], limit: int) -> list[str]:
    if not items:
        return ["- (none)"]
    out = [f"- {i}" for i in items[:limit]]
    return out


# ---------------------------------------------------------------------------
# Memory compression (deterministic, no LLM)
# ---------------------------------------------------------------------------


def compress_turn_history(
    events_by_turn: list[list[dict]],
    turn_range: tuple[int, int],
) -> str:
    """Compress a range of turns into a single era summary string.

    Pure Python — no LLM.  Extracts key facts from events: locations (MOVE),
    NPCs (NPC_SPAWN), items (ITEM_GET/LOSE), damage/heal totals, flag changes.

    Args:
        events_by_turn: List of event lists, one per turn in the range.
        turn_range: ``(start_turn, end_turn)`` inclusive.

    Returns:
        Compressed summary string capped at ``MEMORY_ERA_SUMMARY_MAX_CHARS``.
    """
    locations: list[str] = []
    npcs: list[str] = []
    items_gained: list[str] = []
    flags: list[str] = []
    total_damage = 0
    total_heal = 0

    for turn_events in events_by_turn:
        for e in turn_events:
            if isinstance(e, dict):
                etype = str(e.get("event_type", "")).upper()
                payload = e.get("payload") or {}
            else:
                etype = str(getattr(e, "event_type", "")).upper()
                payload = getattr(e, "payload", None) or {}

            if etype == "MOVE":
                loc = payload.get("to_location") or payload.get("location_id") or ""
                if loc and loc not in locations:
                    locations.append(loc)
            elif etype == "NPC_SPAWN":
                name = payload.get("name") or ""
                if name and name not in npcs:
                    npcs.append(name)
            elif etype == "ITEM_GET":
                item = payload.get("item_name") or ""
                if item and item not in items_gained:
                    items_gained.append(item)
            elif etype == "DAMAGE":
                total_damage += int(payload.get("amount", 0))
            elif etype == "HEAL":
                total_heal += int(payload.get("amount", 0))
            elif etype == "FLAG_SET":
                key = payload.get("key") or ""
                value = payload.get("value", "")
                if key:
                    flags.append(f"{key}={value}")

    start, end = turn_range
    clauses: list[str] = []
    if locations:
        clauses.append(f"visited {', '.join(locations[:5])}")
    if npcs:
        clauses.append(f"met {', '.join(npcs[:5])}")
    if items_gained:
        clauses.append(f"acquired {', '.join(items_gained[:5])}")
    if total_damage:
        clauses.append(f"took {total_damage} total damage")
    if total_heal:
        clauses.append(f"healed {total_heal} total")
    if flags:
        clauses.append(f"flags: {', '.join(flags[:3])}")
    if not clauses:
        clauses.append("uneventful")

    summary = f"Turns {start}-{end}: {'; '.join(clauses)}."
    return summary[:MEMORY_ERA_SUMMARY_MAX_CHARS]


def update_era_summaries(
    world_state: dict,
    current_turn: int,
    all_events: list[dict],
) -> dict:
    """Update the ``era_summaries`` list in *world_state*.

    Called from the Commit node after appending events.  Checks whether any
    complete chunk of ``MEMORY_COMPRESSION_CHUNK_SIZE`` turns exists beyond the
    recent window that hasn't been compressed yet.

    Args:
        world_state: ``world_state_json`` dict (mutated in place).
        current_turn: The turn number just completed.
        all_events: All events for the campaign (flat list of event dicts).

    Returns:
        The (mutated) *world_state* dict with ``era_summaries`` updated.
    """
    era_summaries: list[str] = list(world_state.get("era_summaries") or [])
    last_compressed_turn = len(era_summaries) * MEMORY_COMPRESSION_CHUNK_SIZE

    # Only compress turns that are outside the recent-turns window.
    compressible_up_to = max(0, current_turn - MEMORY_RECENT_TURNS)

    while last_compressed_turn + MEMORY_COMPRESSION_CHUNK_SIZE <= compressible_up_to:
        chunk_start = last_compressed_turn + 1
        chunk_end = last_compressed_turn + MEMORY_COMPRESSION_CHUNK_SIZE

        # Group events by turn number
        events_by_turn: list[list[dict]] = []
        for t in range(chunk_start, chunk_end + 1):
            turn_events = [
                e for e in all_events
                if _event_turn_number(e) == t
            ]
            events_by_turn.append(turn_events)

        summary = compress_turn_history(events_by_turn, (chunk_start, chunk_end))
        era_summaries.append(summary)
        last_compressed_turn = chunk_end

    # Cap the list
    if len(era_summaries) > MEMORY_MAX_ERA_SUMMARIES:
        era_summaries = era_summaries[-MEMORY_MAX_ERA_SUMMARIES:]

    world_state["era_summaries"] = era_summaries
    return world_state


def _event_turn_number(event: dict | Any) -> int:
    """Extract turn_number from an event dict or Event object."""
    if isinstance(event, dict):
        return int(event.get("turn_number", 0))
    return int(getattr(event, "turn_number", 0))
