# Genre Style Guide — LLM Prompt Template

Use this prompt to generate genre/mode overlay style guides. Copy everything below the line, fill in the bracketed placeholders, and submit to your LLM.

---

You are writing a Genre Style Guide for a Star Wars tabletop RPG AI narrator system. This document will be chunked into ~384-word paragraphs, embedded as vectors, and retrieved at runtime to shape the AI's narrative output. It functions as a GENRE OVERLAY — it is LAYERED ON TOP of an era-specific style guide that provides the setting foundation. This document must add genre flavor WITHOUT contradicting the era baseline underneath.

The document is consumed by two AI agents:

- The DIRECTOR agent extracts 2-4 concrete directive sentences to shape scene planning and action suggestions.
- The NARRATOR agent uses retrieved chunks as prose-shaping context for sensory detail, dialogue tone, and atmospheric grounding.

Write the style guide for genre/mode: [GENRE NAME]
One-line description: [e.g., "Noir detective stories — cynical investigation in morally grey underworlds"]

Use the following section structure. Write in second person imperative ("Use...", "Avoid...", "Show...") so every sentence can function as a standalone directive when extracted.

IMPORTANT: This document must be ERA-AGNOSTIC. Do not reference specific eras, factions, or timeline events. Use phrases like "the local authorities," "the underworld," "the power structure" instead of "the Empire" or "the Rebel Alliance." The era guide will provide those specifics.

---

SECTION STRUCTURE:

## [Genre Name] Style Guide

Premise: [One sentence — the genre's core narrative mode stated as a storytelling approach, set in a "galaxy far, far away" context but not era-specific.]

## Tone

The emotional and atmospheric register this genre brings. How does this genre TRANSFORM whatever era it's applied to? What feelings should the player experience? What lens does this genre put on the existing setting?

Write 3-5 paragraphs covering:

- The dominant emotional register (paranoia, dread, excitement, moral complexity, etc.)
- How the player character relates to the world differently in this genre (observer, survivor, schemer, etc.)
- The genre's relationship to truth, morality, and resolution
- How the genre interacts with Star Wars elements without overriding them
- What to AVOID — genre cliches that would feel wrong in a Star Wars context

## Pacing

How this genre changes the rhythm of scenes compared to default Star Wars storytelling.

Write 2-3 paragraphs covering:

- How scenes open — action first? Observation? Tension?
- How information flows — discovery, conversation, investigation, revelation?
- How turns end — cliffhangers, questions, betrayals, horror beats, moral weight?
- Escalation pattern — what builds toward what?

## Scene Beats

Numbered structural template (4-5 steps) for composing a typical scene in this genre mode. Each beat should be one paragraph. These should be ERA-AGNOSTIC — describe the dramatic function, not era-specific content.

## Dialogue

How this genre transforms character speech patterns. Not specific character types (the era guide handles that) but the GENRE FILTER applied to how everyone talks.

Write 3-4 paragraphs covering:

- The genre's signature dialogue style (clipped, verbose, coded, theatrical, etc.)
- How subtext works — what's said vs what's meant
- How threats, deals, and revelations are delivered
- How the genre handles exposition — does information flow freely or through interrogation?

## Sensory Lexicon

Curated vocabulary lists organized by sense. These provide genre-specific atmospheric language. Provide 5-6 entries per sense category, each a short evocative phrase (3-8 words). These should layer on top of era-specific sensory vocabulary, so focus on GENRE TEXTURE rather than setting-specific objects.

Categories: Sound, Sight, Smell, Touch

## Genre Boundaries

What this genre does NOT do in a Star Wars context. How to prevent the genre from overwhelming the era foundation. This section is critical.

Write 2-3 paragraphs covering:

- Where the genre ends and the era begins — what should the era guide control?
- Genre tropes that DON'T translate well to Star Wars and should be avoided
- How to maintain Star Wars identity while using this genre's tools
- The difference between "Star Wars told AS [genre]" vs "[genre] with Star Wars paint"

---

WRITING RULES:

- Every sentence should be usable as a standalone directive when extracted
- Use imperative second person: "Show the player...", "Avoid...", "Frame scenes as..."
- Be ERA-AGNOSTIC — no references to specific factions, characters, or timeline events
- Be specific to THIS genre — don't write generic writing advice
- Do NOT reproduce copyrighted prose — use original phrasing throughout
- Aim for 1000-1800 words total (this chunks into ~3-5 retrievable segments)
- Write paragraphs of 80-150 words each — this matches the chunker's merge target
- Remember: the era guide provides the WHAT (setting, factions, technology). This guide provides the HOW (narrative mode, emotional lens, genre techniques)
