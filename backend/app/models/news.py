"""Mass Effect-style comms/briefing: NewsItem from rumor events."""
from __future__ import annotations

import re
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NewsUrgency(str, Enum):
    LOW = "LOW"
    MED = "MED"
    HIGH = "HIGH"


# Source tags for ME-style briefing feed
SOURCE_CIVNET = "CIVNET"
SOURCE_INTERCEPT = "INTERCEPT"
SOURCE_UNDERWORLD = "UNDERWORLD"
SOURCE_REPUBLIC = "REPUBLIC"
SOURCE_SITH = "SITH"
SOURCE_TAGS = (SOURCE_CIVNET, SOURCE_INTERCEPT, SOURCE_UNDERWORLD, SOURCE_REPUBLIC, SOURCE_SITH)


class NewsItem(BaseModel):
    """Single briefing/comms entry (ME-style)."""
    id: str = Field(..., description="Unique id")
    timestamp_world_minutes: int = Field(default=0, ge=0)
    source_tag: str = Field(default=SOURCE_CIVNET, description="CIVNET | INTERCEPT | UNDERWORLD | REPUBLIC | SITH")
    headline: str = Field(default="", max_length=80)
    body: str = Field(default="", description="1–3 short lines")
    related_factions: list[str] = Field(default_factory=list)
    urgency: NewsUrgency = Field(default=NewsUrgency.LOW)
    is_public_rumor: bool = Field(default=True)


NEWS_FEED_MAX = 20
NEWS_FEED_MIN = 10


def _headline_from_text(text: str, max_len: int = 80) -> str:
    """Punchy headline: first sentence or first max_len chars."""
    text = (text or "").strip()
    if not text:
        return "Intel received."
    # First sentence
    match = re.match(r"^([^.!?]+[.!?]?)", text)
    if match:
        line = match.group(1).strip()
    else:
        line = text
    if len(line) > max_len:
        line = line[: max_len - 3].rstrip() + "..."
    return line or "Intel received."


def _body_from_text(text: str, max_lines: int = 3) -> str:
    """1–3 short lines from full text."""
    text = (text or "").strip()
    if not text:
        return "No details."
    # Split on sentence boundaries or newlines
    parts = re.split(r"[.!?\n]+", text)
    lines = [p.strip() for p in parts if len(p.strip()) > 5][:max_lines]
    return "\n".join(lines) if lines else text[:200]


def _source_tag_from_text(text: str) -> str:
    """Derive source_tag from keywords (ME-style)."""
    low = (text or "").lower()
    if re.search(r"\b(intercept|intercepted|comm\s+traffic|encrypted)\b", low):
        return SOURCE_INTERCEPT
    if re.search(r"\b(underworld|syndicate|smuggler|black\s+market)\b", low):
        return SOURCE_UNDERWORLD
    if re.search(r"\b(republic|senate|jedi\s+order|military)\b", low):
        return SOURCE_REPUBLIC
    if re.search(r"\b(sith|empire|dark\s+side)\b", low):
        return SOURCE_SITH
    return SOURCE_CIVNET


def _urgency_from_text(text: str) -> NewsUrgency:
    """Derive urgency from keywords."""
    low = (text or "").lower()
    if re.search(r"\b(attack|alert|crisis|hostile|invasion|outbreak)\b", low):
        return NewsUrgency.HIGH
    if re.search(r"\b(sighting|incident|disturbance|rumor|reported)\b", low):
        return NewsUrgency.MED
    return NewsUrgency.LOW


def _related_factions_from_text(text: str, active_faction_names: list[str]) -> list[str]:
    """Extract faction names mentioned in text that appear in active_factions."""
    if not text or not active_faction_names:
        return []
    low = text.lower()
    out = []
    for name in active_faction_names:
        if not name:
            continue
        # Case-insensitive substring match (e.g. "Red Hand" in "red hand cult activity")
        if name.lower() in low:
            out.append(name)
    return out


def rumor_to_news_item(
    text: str,
    world_time_minutes: int,
    active_faction_names: list[str] | None = None,
    news_id: str | None = None,
) -> NewsItem:
    """Convert a rumor string into a NewsItem (ME-style briefing)."""
    text = (text or "").strip()
    active_faction_names = active_faction_names or []
    return NewsItem(
        id=news_id or f"news-{uuid.uuid4().hex[:8]}",
        timestamp_world_minutes=world_time_minutes,
        source_tag=_source_tag_from_text(text),
        headline=_headline_from_text(text, max_len=80),
        body=_body_from_text(text, max_lines=3),
        related_factions=_related_factions_from_text(text, active_faction_names),
        urgency=_urgency_from_text(text),
        is_public_rumor=True,
    )


def rumors_to_news_feed(
    rumor_texts: list[str],
    world_time_minutes: int,
    active_faction_names: list[str] | None = None,
    existing_feed: list[dict[str, Any]] | list[NewsItem] | None = None,
    max_items: int = NEWS_FEED_MAX,
) -> list[dict[str, Any]]:
    """Convert rumor list to NewsItems and prepend to feed; return bounded list (latest first)."""
    active_faction_names = active_faction_names or []
    existing = list(existing_feed or [])
    # Normalize existing to dicts
    existing_dicts = []
    for item in existing:
        if isinstance(item, NewsItem):
            existing_dicts.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            existing_dicts.append(item)
        else:
            continue
    new_items = [
        rumor_to_news_item(t, world_time_minutes, active_faction_names).model_dump(mode="json")
        for t in (rumor_texts or [])
        if (t or "").strip()
    ]
    combined = new_items + existing_dicts
    return combined[:max_items]
