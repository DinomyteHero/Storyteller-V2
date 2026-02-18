"""Director validation, fallbacks, and context builders -- thin re-export hub.

All implementation lives in:
  - director_context.py   (context builders, validation, similarity)
  - suggestion_engine.py  (CYOA suggestion classification / generation)

This module re-exports every public name so existing imports keep working.
"""
from backend.app.core.director_context import (  # noqa: F401
    LoreChunk,
    StyleChunk,
    VALID_TONE_TAGS,
    adventure_hooks_from_lore,
    build_era_factions_companions_context,
    build_style_query,
    directives_from_style_context,
    normalize_tone,
    sanitize_instructions_for_narrator,
    style_context_from_chunks,
    validate_suggestions,
    _jaccard_similarity,
    _tokenize_for_similarity,
)

from backend.app.core.suggestion_engine import (  # noqa: F401
    _humanize_location_for_suggestion,
    classify_suggestion,
    ensure_tone_diversity,
    generate_suggestions,
    fallback_suggestions,
    action_suggestion_to_player_response,
    action_suggestions_to_player_responses,
    _detect_tone_streak,
)

__all__ = [
    # director_context
    "LoreChunk",
    "StyleChunk",
    "VALID_TONE_TAGS",
    "adventure_hooks_from_lore",
    "build_era_factions_companions_context",
    "build_style_query",
    "directives_from_style_context",
    "normalize_tone",
    "sanitize_instructions_for_narrator",
    "style_context_from_chunks",
    "validate_suggestions",
    # suggestion_engine (public API)
    "classify_suggestion",
    "ensure_tone_diversity",
    "generate_suggestions",
    "fallback_suggestions",
    "action_suggestion_to_player_response",
    "action_suggestions_to_player_responses",
    "_detect_tone_streak",
]
