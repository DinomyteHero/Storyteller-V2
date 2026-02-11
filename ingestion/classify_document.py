"""Document classifier: heuristic-first, LLM-optional auto-tagging for doc_type, era, section_kind.

Usage:
  result = classify_document(path, extracted_text, default_era)
  # result: {doc_type, era, section_kind_guess, confidence, signals_used}
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from shared.lore_metadata import (
    DOC_TYPE_NOVEL,
    DOC_TYPE_SOURCEBOOK,
    DOC_TYPE_ADVENTURE,
    DOC_TYPE_MAP,
    DOC_TYPE_UNKNOWN,
    SECTION_KIND_GEAR,
    SECTION_KIND_HOOK,
    SECTION_KIND_FACTION,
    SECTION_KIND_LOCATION,
    SECTION_KIND_LORE,
    SECTION_KIND_DIALOGUE,
    SECTION_KIND_UNKNOWN,
)
from ingestion.era_aliases import DEFAULT_ERA_ALIASES, normalize_aliases, normalize_segment
from ingestion.era_normalization import era_variants

logger = logging.getLogger(__name__)

# Era path segments (normalized for matching)
ERA_SEGMENTS = {
    "old_republic": "Old Republic",
    "clone_wars": "Clone Wars",
    "gaw": "GAW",
    "new_republic": "New Republic",
    "lotf": "LOTF",
    "legacy": "LOTF",
    "high_republic": "High Republic",
}


def _path_to_lower(path: Path) -> str:
    """Full path as lowercase string for matching."""
    return str(path).lower().replace("\\", "/")


def _path_segments(path: Path) -> list[str]:
    """Normalized path segments for matching."""
    parts = []
    for part in Path(path).parts:
        norm = normalize_segment(part)
        if norm:
            parts.append(norm)
    return parts


def _doc_type_from_path(path: Path) -> tuple[str, float, list[str]]:
    """Heuristic doc_type from path/filename. Returns (doc_type, confidence, signals_used)."""
    lower = _path_to_lower(path)
    signals: list[str] = []

    # Folder contains novel, books, legends
    if "novel" in lower or "books" in lower or "legends" in lower:
        signals.append("path:novel/books/legends")
        return (DOC_TYPE_NOVEL, 0.85, signals)

    # Filename keywords
    name = path.name.lower()
    if "sourcebook" in name or "rulebook" in name or "supplement" in name:
        signals.append("path:sourcebook/rulebook/supplement")
        return (DOC_TYPE_SOURCEBOOK, 0.9, signals)
    if "adventure" in name or "module" in name or "scenario" in name:
        signals.append("path:adventure/module/scenario")
        return (DOC_TYPE_ADVENTURE, 0.9, signals)
    if "map" in name or "atlas" in name or "sector" in name:
        signals.append("path:map/atlas/sector")
        return (DOC_TYPE_MAP, 0.9, signals)

    # Fallback: unknown
    return (DOC_TYPE_UNKNOWN, 0.3, ["path:no_match"])


def _section_kind_from_text(text: str | None) -> tuple[str, float, list[str]]:
    """Heuristic section_kind from first ~2000 chars. Returns (section_kind, confidence, signals_used)."""
    if not text or not text.strip():
        return (SECTION_KIND_UNKNOWN, 0.2, ["text:empty"])

    sample = (text[:2000] + " ").lower()
    signals: list[str] = []

    # Gear headings
    gear_pats = [r"\b(equipment|gear|weapons?|armor|items?)\s*[:\n]"]
    for p in gear_pats:
        if re.search(p, sample, re.I):
            signals.append("heading:gear")
            return (SECTION_KIND_GEAR, 0.85, signals)

    # Hook / adventure structure
    hook_pats = [r"adventure\s+summary", r"act\s+[i123]+\b", r"\bencounter\s*[:\n]"]
    for p in hook_pats:
        if re.search(p, sample, re.I):
            signals.append("heading:hook")
            return (SECTION_KIND_HOOK, 0.85, signals)

    # Faction / organizations
    if re.search(r"\b(faction|organizations?)\s*[:\n]", sample, re.I):
        signals.append("heading:faction")
        return (SECTION_KIND_FACTION, 0.85, signals)

    # Location
    if re.search(r"\b(planet|location|regions?)\s*[:\n]", sample, re.I):
        signals.append("heading:location")
        return (SECTION_KIND_LOCATION, 0.85, signals)

    # Novel/lore: "Chapter" + narrative prose
    if re.search(r"\bchapter\s+\d+", sample, re.I) and (
        " said " in sample or " asked " in sample or '"' in sample or "—" in sample
    ):
        signals.append("heading:chapter+narrative")
        return (SECTION_KIND_LORE, 0.75, signals)

    if re.search(r"\bchapter\b", sample, re.I):
        signals.append("heading:chapter")
        return (SECTION_KIND_LORE, 0.6, signals)

    return (SECTION_KIND_UNKNOWN, 0.3, ["text:no_heading_match"])


def _era_from_path(path: Path, era_aliases: dict[str, str] | None = None) -> str | None:
    """Infer era from path segments and alias map. Returns None if unknown."""
    aliases = dict(DEFAULT_ERA_ALIASES)
    aliases.update(normalize_aliases(era_aliases))
    segments = _path_segments(path)
    for seg in segments:
        for variant in era_variants(seg):
            if variant in aliases:
                return aliases[variant]
    for seg in segments:
        for variant in era_variants(seg):
            if variant in ERA_SEGMENTS:
                return ERA_SEGMENTS[variant]
    return None


def _llm_classify_fallback(path: Path, text_sample: str | None, heuristic: dict) -> dict | None:
    """
    Optional LLM fallback. Returns parsed JSON dict or None on failure.
    Uses backend AgentLLM if configured; safe: invalid JSON -> None, keep heuristic.
    """
    try:
        from backend.app.config import MODEL_CONFIG
        from backend.app.core.agents.base import AgentLLM, ensure_json

        # Use biographer role (always present) for classifier fallback
        if "biographer" not in MODEL_CONFIG:
            return None
        llm = AgentLLM("biographer")

        sys_prompt = (
            "You are a document classifier. Output ONLY valid JSON with keys: doc_type, era, section_kind, confidence. "
            "doc_type: novel | sourcebook | adventure | map | unknown. "
            "section_kind: gear | hook | faction | location | lore | dialogue | unknown. "
            "era: e.g. LOTF, Clone Wars, Old Republic, or null if unknown. confidence: 0.0-1.0. No other text."
        )
        user = f"Path: {path.name}\n\nFirst 1500 chars:\n{(text_sample or '')[:1500]}"
        raw = llm.complete(sys_prompt, user, json_mode=True)
        parsed = ensure_json(raw) if raw else None
        if parsed:
            data = json.loads(parsed)
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.debug("LLM classify fallback failed: %s", e)
    return None


def classify_document(
    path: Path,
    extracted_text: str | None,
    default_era: str | None,
    era_aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Auto-detect doc_type, era, and section_kind with heuristic-first logic and optional LLM fallback.

    Returns:
        dict with: doc_type, era, section_kind_guess, confidence, signals_used.
    """
    path = Path(path)
    dt, dt_conf, dt_signals = _doc_type_from_path(path)
    sk, sk_conf, sk_signals = _section_kind_from_text(extracted_text)
    era = default_era if default_era and str(default_era).strip() else _era_from_path(path, era_aliases)

    signals_used = dt_signals + sk_signals
    # Overall confidence: average of doc_type and section_kind
    confidence = (dt_conf + sk_conf) / 2.0

    result: dict[str, Any] = {
        "doc_type": dt,
        "era": era,
        "section_kind_guess": sk,
        "confidence": round(confidence, 2),
        "signals_used": signals_used,
    }

    # Optional LLM fallback: only if confidence < 0.7 AND LLM configured.
    # Never downgrade a non-unknown heuristic result with a lower-confidence LLM answer.
    if confidence < 0.7:
        llm_out = _llm_classify_fallback(path, extracted_text, result)
        if llm_out and isinstance(llm_out, dict):
            llm_conf = float(llm_out.get("confidence", 0.0))
            # Only adopt LLM doc_type if it improves on an unknown heuristic or has higher confidence
            llm_dt = llm_out.get("doc_type")
            if llm_dt in (DOC_TYPE_NOVEL, DOC_TYPE_SOURCEBOOK, DOC_TYPE_ADVENTURE, DOC_TYPE_MAP) and (
                dt == DOC_TYPE_UNKNOWN or llm_conf > dt_conf
            ):
                result["doc_type"] = llm_dt
            # Only adopt LLM section_kind if it improves on unknown or beats heuristic confidence
            llm_sk = llm_out.get("section_kind")
            if llm_sk in (
                SECTION_KIND_GEAR, SECTION_KIND_HOOK, SECTION_KIND_FACTION,
                SECTION_KIND_LOCATION, SECTION_KIND_LORE, SECTION_KIND_DIALOGUE,
            ) and (sk == SECTION_KIND_UNKNOWN or llm_conf > sk_conf):
                result["section_kind_guess"] = llm_sk
            if llm_out.get("era") is not None and str(llm_out.get("era", "")).strip():
                result["era"] = str(llm_out["era"]).strip()
            if llm_conf > confidence:
                result["confidence"] = min(0.9, llm_conf)
            result["signals_used"] = result["signals_used"] + ["llm_fallback"]

    return result
