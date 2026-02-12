"""Doc-type lanes: retrieval filter bundles for each agent.

Active bundles:
  - Narrator: novels/sourcebooks for lore/location/faction; character_voice_chunks for dialogue.
  - Director: adventure + hook for pacing/scenario context.

Note: Mechanic is deterministic (zero LLM/RAG calls per architectural invariant 3),
so no Mechanic retrieval bundle is defined.
"""

# Narrator bundle: doc_type in {novel, sourcebook}, section_kind in {lore, location, faction}
NARRATOR_DOC_TYPES = ["novel", "sourcebook"]
NARRATOR_SECTION_KINDS = ["lore", "location", "faction"]

# Director bundle: doc_type=adventure, section_kind=hook
DIRECTOR_DOC_TYPE = "adventure"
DIRECTOR_SECTION_KIND = "hook"
