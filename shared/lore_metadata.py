"""Shared constants for lore chunk metadata. Use these to avoid string typos."""

# Document type: source classification
DOC_TYPE_NOVEL = "novel"
DOC_TYPE_SOURCEBOOK = "sourcebook"
DOC_TYPE_ADVENTURE = "adventure"
DOC_TYPE_MAP = "map"
DOC_TYPE_UNKNOWN = "unknown"

DOC_TYPES = frozenset({DOC_TYPE_NOVEL, DOC_TYPE_SOURCEBOOK, DOC_TYPE_ADVENTURE, DOC_TYPE_MAP, DOC_TYPE_UNKNOWN})


# Section kind: content classification within a document
SECTION_KIND_LORE = "lore"
SECTION_KIND_DIALOGUE = "dialogue"
SECTION_KIND_GEAR = "gear"
SECTION_KIND_FACTION = "faction"
SECTION_KIND_LOCATION = "location"
SECTION_KIND_HOOK = "hook"
SECTION_KIND_RULES = "rules"
SECTION_KIND_UNKNOWN = "unknown"

SECTION_KINDS = frozenset({
    SECTION_KIND_LORE, SECTION_KIND_DIALOGUE, SECTION_KIND_GEAR,
    SECTION_KIND_FACTION, SECTION_KIND_LOCATION, SECTION_KIND_HOOK,
    SECTION_KIND_RULES, SECTION_KIND_UNKNOWN,
})


def default_doc_type() -> str:
    return DOC_TYPE_UNKNOWN


def default_section_kind() -> str:
    return SECTION_KIND_UNKNOWN


def default_characters() -> list:
    return []


def default_related_npcs() -> list:
    return []
