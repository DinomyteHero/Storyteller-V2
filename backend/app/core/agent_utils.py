"""Shared utilities for agent helpers (formatting, retrieval, id filtering)."""
from __future__ import annotations

import re
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.models.state import GameState


def is_probable_uuid(value: str) -> bool:
    if not value:
        return False
    return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", value, re.I))


def collect_related_npc_ids(state: "GameState", max_ids: int = 2) -> list[str]:
    """Pick stable NPC ids for lore filtering (skip UUIDs and generated ids)."""
    ids: list[str] = []
    seen: set[str] = set()
    for n in state.present_npcs or []:
        cid = str(n.get("id") or "").strip()
        if not cid or cid in seen:
            continue
        if cid.startswith("gen_") or cid.startswith("proc_"):
            continue
        if is_probable_uuid(cid):
            continue
        ids.append(cid)
        seen.add(cid)
        if len(ids) >= max_ids:
            break
    return ids


def call_retriever(fn: Callable, *args, warnings: list[str] | None = None, **kwargs):
    """Call retriever with optional warnings kwarg for failure signaling."""
    if warnings is None:
        return fn(*args, **kwargs)
    try:
        return fn(*args, warnings=warnings, **kwargs)
    except TypeError:
        return fn(*args, **kwargs)


def format_voice_snippets(
    snippets_by_char: dict[str, list],
    empty_text: str = "",
    *,
    max_snippet_len: int = 200,
) -> str:
    """Format voice snippets for prompts."""
    if not snippets_by_char or not any(snippets_by_char.values()):
        return empty_text
    lines: list[str] = []
    for cid, snips in snippets_by_char.items():
        if not snips:
            continue
        texts: list[str] = []
        for s in snips:
            t = s.get("text") if isinstance(s, dict) else getattr(s, "text", "")
            if t:
                texts.append(str(t)[:max_snippet_len])
        if texts:
            lines.append(f"- **{cid}**: " + " | ".join(texts))
    if not lines:
        return empty_text
    return "\n".join(lines)


def format_lore_bullets(
    chunks: list[dict],
    empty_text: str = "",
    *,
    max_chunk_len: int = 400,
) -> str:
    """Format lore chunks as bulleted lines with source identifiers."""
    if not chunks:
        return empty_text
    lines: list[str] = []
    for i, c in enumerate(chunks):
        title = c.get("source_title") or c.get("metadata", {}).get("book_title") or "Source"
        chunk_id = c.get("chunk_id") or ""
        text = (c.get("text") or "").strip()
        if text:
            suffix = "..." if len(text) > max_chunk_len else ""
            lines.append(f"- [{title}] (chunk {chunk_id or i}): {text[:max_chunk_len]}{suffix}")
    return "\n".join(lines) if lines else empty_text
