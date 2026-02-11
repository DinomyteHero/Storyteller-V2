"""Deterministic NPC tagging for lore chunks using Era Packs."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.config import MANIFESTS_DIR
from backend.app.world.era_pack_models import EraPack, EraNpcEntry, NpcMatchRules

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AliasPattern:
    npc_id: str
    alias: str
    alias_key: str
    pattern: re.Pattern
    is_ambiguous: bool


def _compile_pattern(alias: str, case_sensitive: bool = False) -> re.Pattern:
    """Build regex with word boundaries and flexible whitespace."""
    escaped = re.escape(alias)
    escaped = escaped.replace("\\ ", "\\s+")
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = rf"\b{escaped}\b"
    return re.compile(pattern, flags)


def _alias_tokens(alias: str) -> int:
    return len([t for t in re.split(r"\s+", alias.strip()) if t])


def _surname_from_name(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    return parts[-1] if len(parts) >= 2 else ""


def _alias_allowed(
    alias: str,
    *,
    rules: NpcMatchRules,
    canonical_name: str,
    mode: str,
) -> bool:
    token_count = _alias_tokens(alias)
    min_tokens = max(1, int(rules.min_tokens or 1))
    if token_count < min_tokens:
        return False
    if mode == "strict" and token_count < 2 and not rules.allow_single_token:
        return False
    if rules.require_surname:
        surname = _surname_from_name(canonical_name)
        if surname:
            # Require surname token in alias (case-insensitive)
            tokens = [t.lower() for t in re.split(r"\s+", alias) if t]
            if surname.lower() not in tokens:
                return False
    return True


def _build_alias_index(era_pack: EraPack, mode: str) -> list[AliasPattern]:
    """Build compiled alias patterns, marking ambiguous aliases."""
    alias_to_ids: dict[str, set[str]] = {}
    npc_entries: list[EraNpcEntry] = list(era_pack.npcs.anchors) + list(era_pack.npcs.rotating)

    # First pass: collect alias -> npc_ids
    for npc in npc_entries:
        aliases = [npc.name] + list(npc.aliases or [])
        banned = {a.strip().lower() for a in (npc.banned_aliases or []) if isinstance(a, str)}
        for alias in aliases:
            if not isinstance(alias, str):
                continue
            alias_clean = alias.strip()
            if not alias_clean:
                continue
            if alias_clean.lower() in banned:
                continue
            if not _alias_allowed(alias_clean, rules=npc.match_rules, canonical_name=npc.name, mode=mode):
                continue
            key = alias_clean.lower()
            alias_to_ids.setdefault(key, set()).add(npc.id)

    patterns: list[AliasPattern] = []
    # Second pass: compile patterns and mark ambiguous
    for npc in npc_entries:
        aliases = [npc.name] + list(npc.aliases or [])
        banned = {a.strip().lower() for a in (npc.banned_aliases or []) if isinstance(a, str)}
        for alias in aliases:
            if not isinstance(alias, str):
                continue
            alias_clean = alias.strip()
            if not alias_clean:
                continue
            if alias_clean.lower() in banned:
                continue
            if not _alias_allowed(alias_clean, rules=npc.match_rules, canonical_name=npc.name, mode=mode):
                continue
            key = alias_clean.lower()
            is_ambiguous = len(alias_to_ids.get(key, set())) > 1
            try:
                pat = _compile_pattern(alias_clean, case_sensitive=npc.match_rules.case_sensitive)
                patterns.append(AliasPattern(npc_id=npc.id, alias=alias_clean, alias_key=key, pattern=pat, is_ambiguous=is_ambiguous))
            except re.error as e:
                logger.warning("Invalid alias regex for %r (%s): %s", alias_clean, npc.id, e)
                continue
    return patterns


def scan_text_for_npcs(
    text: str,
    patterns: list[AliasPattern],
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Return (related_npcs, collisions) for a text chunk."""
    if not text or not text.strip():
        return [], {}
    seen: set[str] = set()
    ordered: list[str] = []
    collisions: dict[str, dict[str, Any]] = {}
    for pat in patterns:
        if not pat.pattern.search(text):
            continue
        if pat.is_ambiguous:
            item = collisions.setdefault(pat.alias_key, {"alias": pat.alias, "npc_ids": set(), "count": 0})
            item["npc_ids"].add(pat.npc_id)
            item["count"] += 1
            continue
        if pat.npc_id in seen:
            continue
        seen.add(pat.npc_id)
        ordered.append(pat.npc_id)
    # Normalize collision npc_ids to list
    for v in collisions.values():
        v["npc_ids"] = sorted(v["npc_ids"])
    return ordered, collisions


def _resolve_manifests_dir() -> Path:
    root = Path(__file__).resolve().parents[1]
    p = Path(MANIFESTS_DIR)
    if not p.is_absolute():
        p = root / p
    return p


def write_collision_report(
    collisions: dict[str, dict[str, Any]],
    *,
    era_id: str,
    mode: str,
) -> Path | None:
    if not collisions:
        return None
    out_dir = _resolve_manifests_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"ingest_collisions_{timestamp}.json"
    # Sort by count desc
    items = sorted(collisions.values(), key=lambda x: int(x.get("count", 0)), reverse=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "era_id": era_id,
        "mode": mode,
        "collisions": items[:100],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def apply_npc_tags_to_chunks(
    chunks: list[dict],
    *,
    era_pack: EraPack | None,
    enabled: bool = True,
    mode: str = "strict",
) -> tuple[list[dict], dict[str, Any]]:
    """Apply related_npcs tagging to canonical chunks. Returns (chunks, stats)."""
    stats = {
        "enabled": bool(enabled and era_pack),
        "mode": mode,
        "tagged": 0,
        "collisions": 0,
        "collision_report_path": "",
    }
    if not enabled or not era_pack:
        return chunks, stats

    patterns = _build_alias_index(era_pack, mode=mode)
    collisions_accum: dict[str, dict[str, Any]] = {}

    for chunk in chunks:
        text = chunk.get("text") or ""
        related, collisions = scan_text_for_npcs(text, patterns)
        meta = chunk.get("metadata") or {}
        meta["related_npcs"] = related
        chunk["metadata"] = meta
        stats["tagged"] += 1
        # Aggregate collisions
        for key, item in collisions.items():
            agg = collisions_accum.setdefault(key, {"alias": item.get("alias"), "npc_ids": set(), "count": 0})
            agg["npc_ids"].update(item.get("npc_ids", []))
            agg["count"] += int(item.get("count", 0))

    for v in collisions_accum.values():
        v["npc_ids"] = sorted(v["npc_ids"])
    stats["collisions"] = sum(int(v.get("count", 0)) for v in collisions_accum.values())

    report_path = write_collision_report(collisions_accum, era_id=era_pack.era_id, mode=mode)
    if report_path:
        stats["collision_report_path"] = str(report_path)
    return chunks, stats
