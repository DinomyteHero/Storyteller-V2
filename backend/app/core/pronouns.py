"""Pronoun resolution for player characters and companions."""
from __future__ import annotations

PRONOUN_MAP: dict[str, dict[str, str]] = {
    "male": {
        "subject": "he",
        "object": "him",
        "possessive": "his",
        "reflexive": "himself",
    },
    "female": {
        "subject": "she",
        "object": "her",
        "possessive": "her",
        "reflexive": "herself",
    },
}


def pronoun_block(name: str, gender: str | None) -> str:
    """Generate pronoun context block for narrator/director prompts.

    Returns a short instruction string that tells the LLM which pronouns
    to use for the named character. Returns empty string when gender is
    unknown so existing behaviour is preserved.
    """
    if not gender or gender not in PRONOUN_MAP:
        return ""
    p = PRONOUN_MAP[gender]
    return (
        f"CHARACTER PRONOUNS: {name} uses {p['subject']}/{p['object']}/{p['possessive']} pronouns. "
        f"Always use these pronouns when referring to {name} in narration and dialogue."
    )
