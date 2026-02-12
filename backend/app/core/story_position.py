"""Story-position timeline helpers.

Phase 1-3 foundation:
- Phase 1: stable player-facing canonical year label
- Phase 2: retrieval guardrails (source/chapter windows)
- Phase 3: lightweight milestone/divergence tracking
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# World-time -> story progression tuning.
# 1 chapter every N in-world minutes. Conservative default keeps progression slow.
CHAPTER_PROGRESS_MINUTES = 240
CHAPTERS_PER_YEAR = 8


@dataclass(frozen=True)
class TimelineAnchor:
    """Starting-year anchor for a setting period."""

    start_year: int
    suffix: str


# Defaults are intentionally broad and setting-agnostic.
# More settings can be added without touching core logic.
_PERIOD_ANCHORS: dict[str, TimelineAnchor] = {
    "old_republic": TimelineAnchor(start_year=-3954, suffix="BBY"),
    "high_republic": TimelineAnchor(start_year=-250, suffix="BBY"),
    "clone_wars": TimelineAnchor(start_year=-22, suffix="BBY"),
    "rebellion": TimelineAnchor(start_year=0, suffix="ABY"),
    "new_republic": TimelineAnchor(start_year=5, suffix="ABY"),
    "new_jedi_order": TimelineAnchor(start_year=25, suffix="ABY"),
    "legacy": TimelineAnchor(start_year=130, suffix="ABY"),
}


def _norm_period(period_id: str | None) -> str:
    return str(period_id or "").strip().lower().replace("-", "_")


def _anchor_for_period(period_id: str | None) -> TimelineAnchor:
    key = _norm_period(period_id)
    return _PERIOD_ANCHORS.get(key, TimelineAnchor(start_year=0, suffix="YEAR"))


def _format_year(year_value: int, suffix: str) -> str:
    if suffix in ("ABY", "BBY"):
        if year_value < 0:
            return f"{abs(year_value)} BBY"
        return f"{year_value} ABY"
    return str(year_value)


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def initialize_story_position(
    *,
    setting_id: str | None,
    period_id: str | None,
    campaign_mode: str,
    world_time_minutes: int = 0,
) -> dict[str, Any]:
    """Create initial story-position payload for world_state_json."""
    anchor = _anchor_for_period(period_id)
    base_year = anchor.start_year
    chapter = max(1, (_parse_int(world_time_minutes, 0) // CHAPTER_PROGRESS_MINUTES) + 1)
    year_offset = max(0, (chapter - 1) // CHAPTERS_PER_YEAR)
    year_value = base_year + year_offset
    return {
        "setting_id": (setting_id or "").strip().lower(),
        "period_id": _norm_period(period_id),
        "campaign_mode": (campaign_mode or "historical").strip().lower(),
        "current_chapter": chapter,
        "canonical_year_sort": year_value,
        "canonical_year_label": _format_year(year_value, anchor.suffix),
        "milestones": [],
        "divergence_log": [],
        "retrieval_guardrails": {
            "max_chapter_index": chapter,
            "allowed_sources": [],
        },
    }


def advance_story_position(
    *,
    story_position: dict[str, Any] | None,
    world_time_minutes: int,
    campaign_mode: str,
    event_types: list[str] | None = None,
) -> dict[str, Any]:
    """Advance chapter/year and record light milestones/divergence signals."""
    current = dict(story_position or {})
    period_id = current.get("period_id")
    anchor = _anchor_for_period(period_id)
    chapter = max(1, (_parse_int(world_time_minutes, 0) // CHAPTER_PROGRESS_MINUTES) + 1)
    year_offset = max(0, (chapter - 1) // CHAPTERS_PER_YEAR)
    year_value = anchor.start_year + year_offset

    milestones = list(current.get("milestones") or [])
    prev_chapter = _parse_int(current.get("current_chapter"), 1)
    if chapter > prev_chapter:
        milestones.append({"type": "chapter_advanced", "to_chapter": chapter})
        milestones = milestones[-20:]

    divergence_log = list(current.get("divergence_log") or [])
    mode = (campaign_mode or current.get("campaign_mode") or "historical").strip().lower()
    if mode == "sandbox":
        for ev in (event_types or []):
            up = str(ev or "").upper()
            if up in {"ERA_TRANSITION", "FACTION_DESTROYED", "FACTION_COLLAPSE", "REGIME_CHANGE"}:
                divergence_log.append({"event_type": up, "chapter": chapter})
    divergence_log = divergence_log[-50:]

    guardrails = dict(current.get("retrieval_guardrails") or {})
    guardrails["max_chapter_index"] = chapter
    if "allowed_sources" not in guardrails or not isinstance(guardrails.get("allowed_sources"), list):
        guardrails["allowed_sources"] = []

    current.update(
        {
            "campaign_mode": mode,
            "current_chapter": chapter,
            "canonical_year_sort": year_value,
            "canonical_year_label": _format_year(year_value, anchor.suffix),
            "milestones": milestones,
            "divergence_log": divergence_log,
            "retrieval_guardrails": guardrails,
        }
    )
    return current


def canonical_year_label_from_campaign(
    *,
    campaign: dict[str, Any] | None,
    world_state: dict[str, Any] | None,
) -> str | None:
    """Get player-facing year label with safe fallback for older campaigns."""
    ws = world_state or {}
    pos = ws.get("story_position") if isinstance(ws, dict) else None
    if isinstance(pos, dict):
        label = str(pos.get("canonical_year_label") or "").strip()
        if label:
            return label

    period_id = (campaign or {}).get("time_period")
    world_time_minutes = _parse_int((campaign or {}).get("world_time_minutes"), 0)
    fallback = initialize_story_position(
        setting_id=ws.get("setting_id") if isinstance(ws, dict) else None,
        period_id=period_id,
        campaign_mode=(ws.get("campaign_mode") if isinstance(ws, dict) else "historical") or "historical",
        world_time_minutes=world_time_minutes,
    )
    return str(fallback.get("canonical_year_label") or "").strip() or None

