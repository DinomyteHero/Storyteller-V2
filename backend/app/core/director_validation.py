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
    _CONSEQUENCE_HINTS,
    _INTENT_STYLES,
    _PARAGON_VERBS,
    _INVESTIGATE_VERBS,
    _RENEGADE_VERBS,
    _RISKY_VERBS,
    _DANGEROUS_VERBS,
    _SOCIAL_VERBS,
    _COMMIT_VERBS,
    _humanize_location_for_suggestion,
    classify_suggestion,
    ensure_tone_diversity,
    fallback_suggestions,
    generate_suggestions,
    action_suggestion_to_player_response,
    action_suggestions_to_player_responses,
    _detect_tone_streak,
    _exploration_suggestions,
    _get_companion_context,
    _get_location_affordances,
    _has_visited_location,
    _post_combat_failure_suggestions,
    _post_combat_success_suggestions,
    _post_stealth_failure_suggestions,
    _post_stealth_success_suggestions,
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
    "_jaccard_similarity",
    "_tokenize_for_similarity",
    # suggestion_engine
    "_CONSEQUENCE_HINTS",
    "_INTENT_STYLES",
    "_PARAGON_VERBS",
    "_INVESTIGATE_VERBS",
    "_RENEGADE_VERBS",
    "_RISKY_VERBS",
    "_DANGEROUS_VERBS",
    "_SOCIAL_VERBS",
    "_COMMIT_VERBS",
    "_humanize_location_for_suggestion",
    "classify_suggestion",
    "ensure_tone_diversity",
    "fallback_suggestions",
    "generate_suggestions",
    "action_suggestion_to_player_response",
    "action_suggestions_to_player_responses",
    "_detect_tone_streak",
    "_exploration_suggestions",
    "_get_companion_context",
    "_get_location_affordances",
    "_has_visited_location",
    "_post_combat_failure_suggestions",
    "_post_combat_success_suggestions",
    "_post_stealth_failure_suggestions",
    "_post_stealth_success_suggestions",
]
