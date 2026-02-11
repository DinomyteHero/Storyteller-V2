"""Doc-type lanes: retrieval filter bundles for each agent.

Narrator: novels/sourcebooks for lore/location/faction; character_voice_chunks for dialogue.
Director: adventure + hook for pacing/scenario context.
Mechanic (if it consults lore): sourcebooks for rules/gear.
"""

# Narrator bundle: doc_type in {novel, sourcebook}, section_kind in {lore, location, faction}
NARRATOR_DOC_TYPES = ["novel", "sourcebook"]
NARRATOR_SECTION_KINDS = ["lore", "location", "faction"]

# Director bundle: doc_type=adventure, section_kind=hook
DIRECTOR_DOC_TYPE = "adventure"
DIRECTOR_SECTION_KIND = "hook"

# Mechanic bundle (for future use): doc_type=sourcebook, section_kind in {rules, gear}
MECHANIC_DOC_TYPE = "sourcebook"
MECHANIC_SECTION_KINDS = ["rules", "gear"]
