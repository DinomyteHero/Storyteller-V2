"""Local ingestion tagger for lore chunks (optional)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from backend.app.config import MODEL_CONFIG
from backend.app.core.agents.base import AgentLLM
from shared.config import _env_flag

logger = logging.getLogger(__name__)


def tagger_enabled() -> bool:
    return _env_flag("INGESTION_TAGGER_ENABLED") or _env_flag("STORYTELLER_INGESTION_TAGGER_ENABLED")


def tagger_model_name() -> str:
    cfg = MODEL_CONFIG.get("ingestion_tagger") or {}
    return cfg.get("model", "") or ""


class Entities(BaseModel):
    characters: list[str] = Field(default_factory=list)
    factions: list[str] = Field(default_factory=list)
    planets: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)


class Timeline(BaseModel):
    era: str | None = None
    start: str | None = None
    end: str | None = None
    confidence: float | None = None


class TaggerOutput(BaseModel):
    doc_type: str | None = None
    section_kind: str | None = None
    entities: Entities = Field(default_factory=Entities)
    timeline: Timeline = Field(default_factory=Timeline)
    summary_1s: str | None = None
    injection_risk: str | None = None


@dataclass
class TaggerResult:
    output: TaggerOutput | None
    error: str | None = None


def tag_chunk(text: str, *, llm: AgentLLM | None = None, existing: dict | None = None) -> TaggerResult:
    if not text:
        return TaggerResult(output=None, error="empty text")
    if llm is None:
        llm = AgentLLM("ingestion_tagger")
    system = (
        "You are a metadata tagger for lore chunks. "
        "Return ONLY valid JSON matching this schema:\n"
        "{"
        '"doc_type": "<string|null>", '
        '"section_kind": "<string|null>", '
        '"entities": {"characters":[...], "factions":[...], "planets":[...], "items":[...]}, '
        '"timeline": {"era": "<string|null>", "start": "<string|null>", "end": "<string|null>", "confidence": <float|null>}, '
        '"summary_1s": "<one sentence|null>", '
        '"injection_risk": "<low|med|high|unknown>"'
        "}\n"
        "Conservative rules: If unsure, set fields to null or 'unknown' and LOWER confidence. "
        "Use empty lists when no entities are present. No markdown, no extra text."
    )
    existing_meta = existing or {}
    meta_hint = {
        "doc_type": existing_meta.get("doc_type") or "",
        "section_kind": existing_meta.get("section_kind") or "",
        "era": existing_meta.get("era") or existing_meta.get("time_period") or "",
        "source": existing_meta.get("source") or existing_meta.get("book_title") or "",
    }
    user = (
        "Chunk text:\n"
        f"{text}\n\n"
        "Existing metadata (use as hints, do not invent):\n"
        f"{json.dumps(meta_hint)}"
    )
    try:
        raw = llm.complete(system, user, json_mode=True)
        data = json.loads(str(raw))
        output = TaggerOutput.model_validate(data)
        return TaggerResult(output=output)
    except Exception as e:
        logger.warning("Tagger failed: %s", e)
        return TaggerResult(output=None, error=str(e))


def apply_tagger_to_chunks(
    chunks: list[dict],
    *,
    enabled: bool | None = None,
    llm: AgentLLM | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Apply tagger to canonical chunks, returning updated chunks and stats."""
    if enabled is None:
        enabled = tagger_enabled()
    stats = {
        "enabled": bool(enabled),
        "model": tagger_model_name(),
        "tagged": 0,
        "failed": 0,
    }
    if not enabled:
        return chunks, stats
    for chunk in chunks:
        text = chunk.get("text") or ""
        meta = chunk.get("metadata") or {}
        result = tag_chunk(text, llm=llm, existing=meta)
        if not result.output:
            stats["failed"] += 1
            continue
        _apply_output_to_metadata(meta, result.output)
        chunk["metadata"] = meta
        stats["tagged"] += 1
    return chunks, stats


def _apply_output_to_metadata(meta: dict, output: TaggerOutput) -> None:
    doc_type = _clean_value(output.doc_type)
    if doc_type:
        meta["doc_type"] = doc_type
    section_kind = _clean_value(output.section_kind)
    if section_kind:
        meta["section_kind"] = section_kind

    entities = output.entities.model_dump(mode="json")
    meta["entities"] = entities
    meta["entities_json"] = json.dumps(entities)

    timeline = output.timeline
    era = _clean_value(timeline.era)
    if era:
        meta["era"] = era
        if not meta.get("time_period"):
            meta["time_period"] = era
    meta["timeline_start"] = _clean_value(timeline.start) or ""
    meta["timeline_end"] = _clean_value(timeline.end) or ""
    meta["timeline_confidence"] = float(timeline.confidence) if timeline.confidence is not None else None

    meta["summary_1s"] = (output.summary_1s or "").strip()
    meta["injection_risk"] = _clean_value(output.injection_risk) or "unknown"


def _clean_value(val: str | None) -> str | None:
    if not val:
        return None
    v = str(val).strip()
    if not v:
        return None
    if v.lower() in ("unknown", "null", "none", "n/a"):
        return None
    return v
