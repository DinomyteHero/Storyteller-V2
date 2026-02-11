"""Structured narrator output: text and optional citations."""
from __future__ import annotations

from pydantic import BaseModel, Field


class NarrationCitation(BaseModel):
    """Single citation: source and short quote (<=20 words)."""
    source_title: str
    chunk_id: str
    quote: str = Field(..., max_length=200, description="Excerpt, ideally <=20 words")


class NarrationOutput(BaseModel):
    """Structured narrator response: narrative text and optional lore citations."""
    text: str
    citations: list[NarrationCitation] = Field(default_factory=list)
    embedded_suggestions: list[dict] | None = Field(
        default=None,
        description="Numbered suggestions extracted from narrative text (if present)"
    )
