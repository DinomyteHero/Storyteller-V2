# Style Guide Generation Prompt Template

Use this prompt with Claude, Gemini, or GPT to generate a new era-specific style guide.
Replace all `{{PLACEHOLDER}}` values before submitting.

---

## HOW STYLE GUIDES ARE USED

Style guide files are ingested into LanceDB and searched **semantically** by the Director agent at runtime. The Director builds a query from the current scene (location, player action, intent) and retrieves the most relevant style paragraphs to guide its narrative beat selection and action suggestions.

**Key implications for writing:**

- Each paragraph should be **self-contained** — it may be retrieved independently of surrounding paragraphs.
- Use clear, descriptive language — the retrieval system matches by meaning, not headings.
- Include concrete sensory words and examples — vague guidance gets vague results.
- The Narrator does NOT directly use style retrieval, but receives Director instructions shaped by it.

**File format:** Plain markdown. Chunked by double newlines (paragraphs). No special schema required. Saved as `data/style/{{era_id_lowercase}}_style.md`.

---

## PROMPT

You are a creative writing director for a text-based narrative RPG set in the Star Wars Legends **{{ERA_NAME}}** era (approximately {{TIMEFRAME}}).

The game works like this: each turn, a **Director agent** selects narrative beats and suggests 3 player actions, then a **Narrator agent** writes 2-4 paragraphs of scene prose. Your style guide shapes the Director's decisions about tone, pacing, and what makes scenes feel right for this era.

### YOUR TASK

Write a style guide in markdown format following the exact section structure below. This guide will be chunked by paragraph and searched semantically — every paragraph must stand alone as useful guidance.

### SECTION STRUCTURE

Write the following sections with the exact headings shown. Each section should contain 2-5 paragraphs of concrete, actionable guidance.

---

#### 1. `# {{Era Name}} Style Guide`

One-line premise that captures the emotional core of this era in a single sentence.

#### 2. `## Tone`

3-4 paragraphs, each covering a different tonal dimension. Think about:

- What is the dominant emotional tension? (e.g., hope vs oppression, survival vs extinction, trust vs betrayal)
- What does the physical world feel like? (used-future grime, sleek political corridors, war-torn rubble, alien biotech horror)
- What is the player's power fantasy? (scrappy underdog, powerful Jedi, political operator, war hero)
- What should NEVER appear in this era's tone? (explicit anti-patterns to avoid)

Each paragraph should be independently retrievable. Start each with a clear topic sentence.

#### 3. `## Pacing`

2-3 paragraphs covering:

- Paragraph length and rhythm (short and punchy? longer and atmospheric?)
- How turns should end (decision points, cliffhangers, ticking clocks, moral weight)
- Escalation pattern (how tension builds across a scene or session)

#### 4. `## Scene Beats`

A default 3-5 step pattern for how scenes unfold. Write this as a numbered list with brief explanation for each step. The Director uses this to structure its beat selection.

Example format:

```text
1) Establish the space (one concrete sensory detail).
2) Reveal the pressure (what's at stake right now).
3) Present a choice (two obvious paths, one clever path).
4) Show a cost (what does acting or waiting risk).
```

Tailor the pattern to this era's gameplay feel.

#### 5. `## Dialogue`

3-4 paragraphs covering distinct speech registers that appear in this era:

- How does each major faction talk? (military brevity, political formality, underworld slang, alien speech patterns)
- What verbal tics or patterns distinguish this era from others?
- What to avoid (modern slang, anachronisms, out-of-character speech)

Each paragraph should focus on one speech register so it can be retrieved independently.

#### 6. `## Sensory Lexicon`

A curated list of 20-30 reusable sensory fragments organized by sense (sound, smell, sight, touch). These are texture the Narrator can weave into prose. Format as bullet lists grouped by category.

Focus on sounds, smells, textures, and visual details **unique to this era** — what distinguishes a New Republic Senate from an Imperial Star Destroyer, or a Vong worldship from a Jedi Academy.

#### 7. `## Canon Guardrails`

2-3 paragraphs covering:

- What to do when lore context is missing (use rumors, reports, hearsay — never invent canon)
- Named-entity usage rules (only reference characters/events that are grounded in scene context)
- Era-specific pitfalls (common mistakes an AI might make about this era)

#### 8. `## Output Format Tips`

2-3 short paragraphs covering:

- Write like a scene, not an encyclopedia
- Avoid markdown formatting in narrative output
- Suggested actions should be concrete verbs with immediate intent

### DESIGN GUIDELINES

1. **Era-Specific, Not Generic:** Every paragraph should feel like it could ONLY apply to this era. "Write short paragraphs" is generic. "Keep paragraphs short and clipped — this era runs on urgency, not reflection" is era-specific.

2. **Concrete Over Abstract:** Instead of "the tone should be dark," write "every scene should carry the weight of a galaxy losing — supply crates are half-empty, medics work in hallways, and no one sleeps enough."

3. **Retrievable Paragraphs:** Since paragraphs are searched semantically, front-load each one with a clear topic. A paragraph about "military dialogue" should start with "Military dialogue in this era..." not "Another important consideration is..."

4. **Sensory Specificity:** The sensory lexicon is one of the most-retrieved sections. Make entries vivid and distinctive. "Blaster fire" appears in every era — what makes THIS era's blaster fire different?

5. **Avoid Spoilers as Style:** Secrets and plot points belong in the era pack, not the style guide. The style guide shapes HOW stories are told, not WHAT stories are told.

6. **Length Target:** 40-60 lines total. Long enough to give rich guidance, short enough that each paragraph is dense with value.

### REFERENCE: REBELLION ERA STYLE GUIDE

For calibration, here is what the existing Rebellion style guide contains:

```markdown
# Rebellion Style Guide (MVP)

Premise: cinematic pulp in a used, dangerous galaxy where hope is an act of defiance.

## Tone
- Oppression vs spark: every scene should remind the player what the Empire does to ordinary people.
- Used-future texture: grime, improvisation, patched cables, oil-slick decks, scuffed armor, dented bulkheads.
- Competence fantasy (earned): the player can win, but only by being clever, brave, or connected.

## Pacing
- Keep paragraphs short (1–4 lines). Favor crisp beats over long exposition.
- End most turns with a decision point or a ticking clock.
- Escalate in three steps: pressure -> complication -> consequence.

## Scene Beats (default pattern)
1) Establish the space (sound/light/smell, one concrete detail).
2) Reveal the pressure (patrol, shortage, deadline, informant).
3) Present a choice (two obvious paths, one clever path).
4) Show a cost (risk, reputation, time, suspicion).

## Dialogue
- Military brevity: clipped orders, minimal words, implied authority.
- Scoundrel banter: humor as armor; deflect, bluff, charm.
- Rebel comms: coded phrases, understatement, caution with names and places.
- Avoid modern slang; keep it timeless and practical.

## Sensory Lexicon (reusable texture)
- comlink crackle, feedback squeal, distant siren wail
- hydraulics hiss, coolant tang, hot metal stink
- blaster scorch, ozone bite, ionized air
- bootfalls on durasteel, vibro-hum, generator thrum
- dust grit, heat shimmer, stale caf, smoke-laced breath

## Canon Guardrails (runtime behavior)
- If lore context is missing: phrase specifics as rumor, reports, or what people say.
- Don't invent precise biographies or exact historical claims unless supported by retrieved lore.
- Keep named-entity usage grounded in the scene context (who is present, what factions are active).

## Output Format Tips (for gameplay)
- Write like a scene, not like a wiki.
- Avoid markdown in the final narrative output.
- Suggested actions should be concrete verbs with immediate intent (e.g., bribe the dockmaster, tail the courier, slice the checkpoint console).
```

### CONSTRAINTS

- Use the exact section headings listed above (the system does not parse headings, but consistent structure helps human reviewers).
- Keep total length between 40-60 lines. Dense paragraphs, no filler.
- Every sensory lexicon entry should be 3-6 words — a reusable fragment, not a sentence.
- Do not reference specific plot events or character arcs — style guides shape tone, not story.
- Do not include markdown code fences in the output — the file IS markdown.
- Output ONLY the style guide content. No commentary, no explanation.

---

## POST-GENERATION CHECKLIST

After receiving the style guide output:

1. Save as `data/style/{{era_id_lowercase}}_style.md`
2. Review each paragraph for standalone retrievability — does it make sense without surrounding context?
3. Check the sensory lexicon for era-specificity — could these fragments ONLY appear in this era?
4. Verify dialogue guidance covers all major factions in the era pack
5. Ensure tone paragraphs don't accidentally spoil plot points
6. Ingest into LanceDB: `python -m backend.app.rag.style_ingest --dir ./data/style --db ./data/lancedb`
7. Test retrieval: `python -c "from backend.app.rag.style_retriever import retrieve_style; print(retrieve_style('pacing tone'))"`
8. Verify the era pack's `style_ref` path matches: `data/style/{{era_id_lowercase}}_style.md`
