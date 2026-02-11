"""ContextBudget: assembles prompt context with token budgeting and trimming.

Ensures prompts do not silently exceed the context window by trimming
least-important context first and reserving output tokens.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.agent_utils import format_lore_bullets, format_voice_snippets
from backend.app.constants import (
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
    TOKEN_ESTIMATE_WORDS_PER_TOKEN,
)


def estimate_tokens(text: str) -> int:
    """
    Simple token estimation heuristic: chars/4 or words*1.3, whichever is larger.
    This is a rough approximation suitable for local models.
    """
    if not text:
        return 0
    chars = len(text)
    words = len(text.split())
    # Use the larger estimate to be conservative
    return max(chars // TOKEN_ESTIMATE_CHARS_PER_TOKEN, int(words * TOKEN_ESTIMATE_WORDS_PER_TOKEN))


@dataclass
class BudgetReport:
    """Statistics about context assembly and trimming."""

    estimated_tokens: int = 0
    max_context_tokens: int = 0
    max_input_tokens: int = 0
    reserved_output_tokens: int = 0

    original_style_chunks: int = 0
    original_voice_snippets: int = 0
    original_lore_chunks: int = 0
    original_history_items: int = 0
    original_kg_tokens: int = 0
    original_era_summaries: int = 0

    final_style_chunks: int = 0
    final_voice_snippets: int = 0
    final_lore_chunks: int = 0
    final_history_items: int = 0
    final_kg_tokens: int = 0
    final_era_summaries: int = 0

    dropped_style_chunks: int = 0
    dropped_voice_snippets: int = 0
    dropped_lore_chunks: int = 0
    dropped_history_items: int = 0
    dropped_kg_context: bool = False
    dropped_era_summaries: int = 0

    hard_cut: bool = False

    def trimmed(self) -> bool:
        return any(
            [
                self.dropped_style_chunks,
                self.dropped_voice_snippets,
                self.dropped_lore_chunks,
                self.dropped_history_items,
                self.dropped_kg_context,
                self.dropped_era_summaries,
                self.hard_cut,
            ]
        )

    def warning_message(self) -> str | None:
        if not self.trimmed():
            return None
        parts: list[str] = []
        if self.dropped_style_chunks:
            parts.append(_plural("style snippet", self.dropped_style_chunks))
        if self.dropped_era_summaries:
            parts.append(_plural("era summary", self.dropped_era_summaries))
        if self.dropped_kg_context:
            parts.append("dropped KG context")
        if self.dropped_voice_snippets:
            parts.append(_plural("voice snippet", self.dropped_voice_snippets))
        if self.dropped_lore_chunks:
            parts.append(_plural("lore chunk", self.dropped_lore_chunks))
        if self.dropped_history_items:
            parts.append(_plural("old turn", self.dropped_history_items))
        if self.hard_cut:
            parts.append("applied hard cut")
        if not parts:
            return None
        return f"Context trimmed: {_join_with_and(parts)} to fit context window."

    def to_context_stats(self) -> dict[str, Any]:
        """Return a JSON-serializable stats dict for dev/debug."""
        return {
            "estimated_tokens": self.estimated_tokens,
            "max_context_tokens": self.max_context_tokens,
            "max_input_tokens": self.max_input_tokens,
            "reserved_output_tokens": self.reserved_output_tokens,
            "trimmed_style": self.dropped_style_chunks > 0,
            "trimmed_kg": self.dropped_kg_context,
            "trimmed_voice": self.dropped_voice_snippets > 0,
            "trimmed_lore": self.dropped_lore_chunks > 0,
            "trimmed_history": self.dropped_history_items > 0,
            "hard_cut": self.hard_cut,
            "original_style_chunks": self.original_style_chunks,
            "original_voice_snippets": self.original_voice_snippets,
            "original_lore_chunks": self.original_lore_chunks,
            "original_history_items": self.original_history_items,
            "original_kg_tokens": self.original_kg_tokens,
            "original_era_summaries": self.original_era_summaries,
            "final_style_chunks": self.final_style_chunks,
            "final_voice_snippets": self.final_voice_snippets,
            "final_lore_chunks": self.final_lore_chunks,
            "final_history_items": self.final_history_items,
            "final_kg_tokens": self.final_kg_tokens,
            "final_era_summaries": self.final_era_summaries,
            "dropped_style_chunks": self.dropped_style_chunks,
            "dropped_voice_snippets": self.dropped_voice_snippets,
            "dropped_lore_chunks": self.dropped_lore_chunks,
            "dropped_history_items": self.dropped_history_items,
            "dropped_kg_context": self.dropped_kg_context,
            "dropped_era_summaries": self.dropped_era_summaries,
        }


def build_context(
    parts: dict[str, Any],
    max_input_tokens: int,
    reserve_output_tokens: int,
    *,
    role: str = "",
    max_voice_snippets_per_char: int | None = None,
    min_lore_chunks: int = 0,
    user_input_label: str | None = None,
    empty_voice_text: str | None = None,
    empty_lore_text: str | None = None,
    section_order: list[str] | None = None,
) -> tuple[list[dict[str, str]], BudgetReport]:
    """
    Build a list of messages with token budgeting and trimming.

    parts keys:
      - system (str)
      - state (str)
      - history (list[str])
      - lore_chunks (list[dict]) with score/text
      - style_chunks (list[dict])
      - voice_snippets (dict[str, list])
      - user_input (str)
    """
    system_prompt = parts.get("system") or ""
    state_summary = parts.get("state") or ""
    history_items = list(parts.get("history") or [])
    era_summaries = list(parts.get("era_summaries") or [])
    lore_chunks = list(parts.get("lore_chunks") or [])
    style_chunks = list(parts.get("style_chunks") or [])
    voice_snippets = dict(parts.get("voice_snippets") or {})
    kg_context = (parts.get("kg_context") or "").strip()
    user_input = (parts.get("user_input") or "").strip()

    kg_tokens = estimate_tokens(kg_context) if kg_context else 0

    report = BudgetReport(
        max_context_tokens=max_input_tokens + reserve_output_tokens,
        max_input_tokens=max_input_tokens,
        reserved_output_tokens=reserve_output_tokens,
        original_style_chunks=len(style_chunks),
        original_voice_snippets=_count_voice_snippets(voice_snippets),
        original_lore_chunks=len(lore_chunks),
        original_history_items=len(history_items),
        original_kg_tokens=kg_tokens,
        original_era_summaries=len(era_summaries),
    )

    if section_order is None:
        section_order = ["history", "era_summaries", "voice", "kg", "style", "lore"]

    def _render_user_text() -> str:
        blocks: list[str] = []
        if state_summary:
            blocks.append(state_summary)
        if user_input:
            if user_input_label:
                blocks.append(f"{user_input_label} {user_input}".strip())
            else:
                blocks.append(user_input)
        rendered = {
            "history": _format_history(history_items),
            "era_summaries": _format_era_summaries(era_summaries),
            "voice": format_voice_snippets(voice_snippets, empty_voice_text or ""),
            "kg": kg_context,
            "style": _format_style_chunks(style_chunks),
            "lore": format_lore_bullets(lore_chunks, empty_lore_text or ""),
        }
        for key in section_order:
            text = rendered.get(key, "")
            if text:
                blocks.append(text)
        return "\n\n".join(blocks)

    system_tokens = estimate_tokens(system_prompt)
    max_user_tokens = max(0, max_input_tokens - system_tokens)

    user_text = _render_user_text()
    user_tokens = estimate_tokens(user_text)

    # Trimming order depends on role (Narrator: style -> voice -> lore -> history).
    # Director uses style -> lore -> history (no voice trimming by default).
    if user_tokens > max_user_tokens:
        if style_chunks:
            report.dropped_style_chunks = len(style_chunks)
            style_chunks = []
            user_text = _render_user_text()
            user_tokens = estimate_tokens(user_text)

    if user_tokens > max_user_tokens and kg_context:
        report.dropped_kg_context = True
        kg_context = ""
        user_text = _render_user_text()
        user_tokens = estimate_tokens(user_text)

    if user_tokens > max_user_tokens and era_summaries:
        report.dropped_era_summaries = len(era_summaries)
        era_summaries = []
        user_text = _render_user_text()
        user_tokens = estimate_tokens(user_text)

    if user_tokens > max_user_tokens and max_voice_snippets_per_char is not None:
        trimmed_voice, dropped = _trim_voice_snippets(voice_snippets, max_voice_snippets_per_char)
        if dropped:
            report.dropped_voice_snippets = dropped
            voice_snippets = trimmed_voice
            user_text = _render_user_text()
            user_tokens = estimate_tokens(user_text)

    if user_tokens > max_user_tokens and lore_chunks:
        target_min = max(0, min_lore_chunks)
        # Drop the lowest-scoring lore chunk first (if possible).
        if len(lore_chunks) > target_min:
            lore_chunks = _drop_lowest_score_lore(lore_chunks, drop_count=1)
            report.dropped_lore_chunks += 1
            user_text = _render_user_text()
            user_tokens = estimate_tokens(user_text)

    if user_tokens > max_user_tokens and history_items:
        while user_tokens > max_user_tokens and history_items:
            history_items = history_items[1:]
            report.dropped_history_items += 1
            user_text = _render_user_text()
            user_tokens = estimate_tokens(user_text)

    if user_tokens > max_user_tokens and lore_chunks:
        target_min = max(0, min_lore_chunks)
        while user_tokens > max_user_tokens and len(lore_chunks) > target_min:
            lore_chunks = _drop_lowest_score_lore(lore_chunks, drop_count=1)
            report.dropped_lore_chunks += 1
            user_text = _render_user_text()
            user_tokens = estimate_tokens(user_text)

    if user_tokens > max_user_tokens:
        excess = user_tokens - max_user_tokens
        chars_to_cut = max(0, excess * TOKEN_ESTIMATE_CHARS_PER_TOKEN)
        if chars_to_cut and len(user_text) > chars_to_cut + 20:
            user_text = (
                user_text[: max(0, len(user_text) - chars_to_cut - 50)]
                + "\n\n[Context truncated due to token budget]"
            )
        else:
            user_text = user_text[: max(0, len(user_text) - chars_to_cut)]
        report.hard_cut = True
        user_tokens = estimate_tokens(user_text)

    report.final_style_chunks = len(style_chunks)
    report.final_voice_snippets = _count_voice_snippets(voice_snippets)
    report.final_lore_chunks = len(lore_chunks)
    report.final_history_items = len(history_items)
    report.final_kg_tokens = estimate_tokens(kg_context) if kg_context else 0
    report.final_era_summaries = len(era_summaries)
    report.estimated_tokens = system_tokens + user_tokens

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    return messages, report


def _plural(label: str, count: int) -> str:
    if count == 1:
        return f"dropped 1 {label}"
    return f"dropped {count} {label}s"


def _join_with_and(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _count_voice_snippets(snippets_by_char: dict[str, list]) -> int:
    total = 0
    for snips in snippets_by_char.values():
        if snips:
            total += len(snips)
    return total


def _trim_voice_snippets(
    snippets_by_char: dict[str, list],
    max_per_char: int,
) -> tuple[dict[str, list], int]:
    if max_per_char <= 0:
        return {cid: [] for cid in snippets_by_char}, _count_voice_snippets(snippets_by_char)
    trimmed: dict[str, list] = {}
    dropped = 0
    for cid, snips in snippets_by_char.items():
        if not snips:
            trimmed[cid] = []
            continue
        if len(snips) <= max_per_char:
            trimmed[cid] = list(snips)
            continue
        trimmed[cid] = list(snips[:max_per_char])
        dropped += len(snips) - max_per_char
    return trimmed, dropped


def _drop_lowest_score_lore(lore_chunks: list[dict], drop_count: int) -> list[dict]:
    if drop_count <= 0 or not lore_chunks:
        return lore_chunks
    scored = []
    for idx, chunk in enumerate(lore_chunks):
        score = chunk.get("score")
        try:
            score_val = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score_val = 0.0
        scored.append((score_val, idx))
    scored.sort(key=lambda item: item[0])
    drop_indices = {idx for _, idx in scored[:drop_count]}
    return [chunk for idx, chunk in enumerate(lore_chunks) if idx not in drop_indices]


def _format_history(history: list[str]) -> str:
    if not history:
        return ""
    return "\n".join(f"- {h}" for h in history if h)


def _format_style_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return ""
    lines: list[str] = []
    for c in chunks:
        text = (c.get("text") or "").strip()
        if text:
            lines.append(text[:400])
    return "\n".join(lines) if lines else ""


def _format_era_summaries(summaries: list[str]) -> str:
    """Format compressed era summaries for inclusion in prompt context."""
    if not summaries:
        return ""
    header = "## Long-term memory (compressed earlier turns)"
    return header + "\n" + "\n".join(f"- {s}" for s in summaries)
