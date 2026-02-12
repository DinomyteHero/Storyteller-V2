"""Text normalization utilities."""


def normalize_identifier(value: str) -> str:
    """
    Normalize string to lowercase identifier format.

    Converts dashes to underscores and strips whitespace.
    Used for era IDs, setting IDs, and other configuration identifiers.

    Args:
        value: The string to normalize

    Returns:
        Normalized identifier string (lowercase, underscores instead of dashes)

    Examples:
        >>> normalize_identifier("star-wars-legends")
        'star_wars_legends'
        >>> normalize_identifier("  Rebellion  ")
        'rebellion'
    """
    return str(value).strip().lower().replace("-", "_")
