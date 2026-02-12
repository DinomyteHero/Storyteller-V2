# Era Style Guide — LLM Prompt Template

Use this prompt to generate in-depth era style guides. Copy everything below the line, fill in the bracketed placeholders, and submit to your LLM.

---

You are writing an in-depth Era Style Guide for a Star Wars tabletop RPG AI narrator system. This document will be chunked into ~384-word paragraphs, embedded as vectors, and retrieved at runtime to ground the AI's narrative output in the correct era. It serves as the FOUNDATIONAL LAYER — a genre overlay (noir, horror, heist, etc.) will be layered on top, so this document must establish the era's identity strongly enough that genre flavor adds to it rather than replacing it.

The document is consumed by two AI agents:
- The DIRECTOR agent extracts 2-4 concrete directive sentences to shape scene planning and action suggestions.
- The NARRATOR agent uses retrieved chunks as prose-shaping context for sensory detail, dialogue tone, and atmospheric grounding.

Write the style guide for: [ERA NAME]
Time period context: [BRIEF DESCRIPTION OF WHEN THIS ERA TAKES PLACE AND MAJOR EVENTS]

Use the following section structure. Write in second person imperative ("Use...", "Avoid...", "Show...") so every sentence can function as a standalone directive when extracted. Each section should be substantial (3-6 dense paragraphs) because the chunker merges short paragraphs — isolated one-liners get lost.

---

SECTION STRUCTURE:

# [Era Name] Era Style Guide

Premise: [One sentence elevator pitch — the core dramatic tension of this era stated as a storytelling mode, not a plot summary.]

## Era Identity

What defines this era at its core. The thesis statement expanded. What makes a story set HERE feel fundamentally different from one set in any other era. The central conflict is not a specific war or villain but a DRAMATIC PATTERN — what kind of stories this era naturally generates. What does the player FEEL when playing in this era? What questions does every scene implicitly ask?

Write 3-4 paragraphs covering:
- The defining dramatic tension (not plot events, but the emotional/thematic engine)
- How this era differs from adjacent eras in the timeline
- The player's relationship to power — are they an underdog, an insider, a witness?
- What makes this era's conflicts personal rather than abstract

## Power Structures & Factions

Who holds power, who contests it, and how ordinary people navigate between them. This section grounds NPC behavior and faction dynamics. Every interaction the player has is shaped by where the characters sit in this power hierarchy.

Write 3-4 paragraphs covering:
- The dominant governing force and how it exerts control (military, bureaucratic, cultural)
- The opposition and how it operates (open warfare, insurgency, political maneuvering)
- The underworld and criminal economy — how it relates to both sides
- Where ordinary civilians sit — are they oppressed, prosperous, caught between forces?
- How loyalty and allegiance work — is it ideological, tribal, transactional?

## Technology & Daily Life

The material texture of this era. What does the galaxy FEEL like to live in? This section provides the concrete sensory vocabulary the Narrator uses to ground scenes in physical reality. Technology level, economic conditions, what's common vs rare.

Write 3-4 paragraphs covering:
- State of technology — is it advancing, decaying, jury-rigged, cutting-edge?
- Communication and travel — how do people move, talk, get information?
- Economic conditions — is trade flowing, restricted, black-market-dominated?
- What daily life looks like for a non-combatant — the baseline "normal" the player disrupts
- Visual and material aesthetic — clean/dirty, new/worn, military/civilian

## The Force Landscape

The state of Force users, mysticism, and supernatural elements in this era. This shapes how the game handles Force-sensitive characters, Jedi/Sith encounters, and the metaphysical texture of the setting.

Write 2-3 paragraphs covering:
- State of the Jedi Order — thriving, fractured, hidden, extinct, rebuilding?
- Sith and dark side presence — open, hidden, philosophical, predatory?
- How ordinary people perceive the Force — reverence, fear, skepticism, ignorance?
- What Force encounters FEEL like in this era — wonder, dread, controversy, normalcy?

## Tone

How to write prose in this era. Emotional register, narrative voice, what the writing should feel like to read. This is the section most directly consumed as directives.

Write 3-4 paragraphs covering:
- The dominant emotional register (urgent, paranoid, hopeful, weary, etc.)
- The player's competence fantasy — how do they win? (cleverness, power, investigation, diplomacy)
- What to AVOID — anti-patterns that would break era feel
- How victories and defeats should feel — pyrrhic, earned, hollow, triumphant?

## Pacing

Paragraph rhythm, scene structure timing, how tension builds and releases.

Write 2-3 paragraphs covering:
- Paragraph length and rhythm guidance
- How to end turns — cliffhangers, revelations, ticking clocks, moral dilemmas?
- Escalation pattern — how does tension build across a scene? (three-beat, slow burn, sudden)

## Scene Beats

Numbered structural template (4-5 steps) for composing a typical scene in this era. Each beat should be one paragraph describing what to establish and how.

## Dialogue

How different character types speak in this era. Speech patterns, verbal tics, what's said vs what's meant.

Write 3-5 paragraphs, one per major character archetype:
- Authority figures (military, political, religious)
- Underworld / criminal types
- Civilians / common people
- Force users (if present)
- The player character's expected register

## Sensory Lexicon

Curated vocabulary lists organized by sense. These are directly used by the Narrator for atmospheric prose. Provide 5-6 entries per sense category, each a short evocative phrase (3-8 words).

Categories: Sound, Smell, Sight, Touch, Taste (optional)

## Era Pitfalls & Anti-Patterns

What this era is NOT. Explicit warnings about common mistakes that would flatten the era's identity, especially when a genre overlay is active. This section is critical for maintaining era integrity under genre pressure.

Write 2-3 paragraphs covering:
- The single biggest misconception about this era's tone
- How genre overlays can accidentally override era identity (and how to prevent it)
- Characters/factions/concepts from other eras that should NOT bleed in
- The line between "inspired by" and "contradicts" this era's core tension

## Canon Guardrails

How to handle gaps in lore retrieval, timeline sensitivity, and named-entity usage.

Write 2-3 paragraphs covering:
- How to phrase specifics when lore context is missing (rumor, report, hearsay?)
- Timeline awareness — what has happened, what hasn't yet, what's concurrent
- Named-entity discipline — who might plausibly be referenced, who absolutely shouldn't

## Output Format Tips

Prose style and action suggestion formatting guidance specific to this era.

Write 1-2 paragraphs covering:
- Show vs tell balance
- Markdown avoidance in narrative
- Action suggestion verb style (concrete, specific to era vocabulary)

---

WRITING RULES:
- Every sentence should be usable as a standalone directive when extracted
- Use imperative second person: "Show the player...", "Avoid...", "Frame dialogue as..."
- Be specific to THIS era — don't write generic writing advice
- Reference in-universe concepts, locations, and character types by name where appropriate
- Do NOT reproduce copyrighted prose — use original phrasing throughout
- Aim for 1500-2500 words total (this chunks into ~4-7 retrievable segments)
- Write paragraphs of 80-150 words each — this matches the chunker's merge target
