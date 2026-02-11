# Storyteller AI — User Guide (V2.20)

This guide explains how the **Storyteller AI** works for players: the **Time** mechanic, the **Psychology** system, the **KOTOR-style dialogue wheel**, the companion influence system, and the living world systems that make each playthrough unique. The game runs entirely on **local Ollama models** (no cloud LLMs).

---

## 1. The Time Mechanic

### 1.1 Time Passes Each Turn

In the Living World, **every action you take costs time**. Fighting, talking, traveling, searching—each has an in-world duration (in minutes). That time is added to the campaign's **world clock**. So:

- **If you act, time passes.** A short dialogue might cost ~8 minutes; a trip across town, ~45; a fight, ~35; a quick interaction, ~18.
- **If you wait or do nothing** (idle), no time passes; otherwise the world advances with your choices.

The important idea: **the world is not frozen between your moves.** Time is always advancing with your choices, and the story engine uses that clock to drive off-screen events.

### 1.2 World Updates at Tick Boundaries

When the **world clock** crosses a tick boundary (default: every 4 in-world hours = 240 minutes, configurable via **`WORLD_TICK_INTERVAL_HOURS`**), the game runs a **world tick**:

- Factions and powers off-screen get updated (goals, locations, resources).
- **Rumors** can appear—things that happened elsewhere, or that people are talking about. You might hear them in the next scene or in the narrator's description.

So:

- **Use time deliberately.** Rushing might mean you miss clues or opportunities; taking time might let rumors and faction moves catch up.
- **"Waiting" has consequences.** When enough time passes, the world tick runs and the state of the world (and the rumors in it) can change.

In short: **everything costs time, and if you wait, the world moves.**

---

## 2. The Psychology System

### 2.1 Your Character's Mind Matters

Your character has a **psychological profile** that the game tracks: things like **current mood**, **stress level**, and **active trauma** (or ongoing psychological pressure). This is used **only** to shape how the story is told—not to block or force actions.

- **Stress:** When your **stress gets too high**, the narrator's voice can change: shorter sentences, more sensory overload (sounds, smells, things closing in). The narrator can feel less reliable or more reactive, even if the facts of the scene (what actually happened) stay the same.
- **Mood and trauma:** The Director and Narrator use your **current_mood** and **active_trauma** (or similar hooks) to adjust tone and to introduce complications that feel personal—e.g. a scene that touches on your character's past or fears when stress is low and the story has room for it.

So: **if your stress gets too high, the narrator becomes less reliable in tone and style**—more fragmented, more intense—while still describing the outcomes the game mechanics have already decided.

### 2.2 What Stays Grounded

- **Facts don't change.** Damage, movement, items, and other mechanical results are decided by the **Mechanic** and are fixed. The Narrator only describes those outcomes; it doesn't invent new successes or failures.
- **Psychology affects presentation.** You're not "failing" because of stress—you're experiencing the story through a lens that reflects your character's state. High stress = a more unstable, sensory-heavy narrative voice; low stress = more room for reflection and for story beats that tie into your psychology.

In short: **if your stress gets too high, the narrator becomes unreliable in tone and style**—the world and the outcomes stay grounded, but the way you experience them shifts with your character's mind.

---

## 3. Dialogue Wheel & Tone (KOTOR-style)

The game uses a **four-option dialogue wheel** inspired by *Knights of the Old Republic* and *Mass Effect*. Each suggested action has a **tone** and a **category** that affect how the world and your companions react. There is **no free-text input** — the KOTOR suggestion buttons are the sole interaction method.

### 3.1 The Four Options

| Tone | Color | What it tends to do |
|------|-------|---------------------|
| **PARAGON** | Blue | Empathetic, cooperative, diplomatic. "Talk, persuade, help." |
| **INVESTIGATE** | Gold | Gather information, observe, question. "Look, ask, learn." |
| **RENEGADE** | Red | Decisive, forceful, aggressive. "Act, intimidate, commit." |
| **NEUTRAL** | Gray | Tactical, situational, or action-oriented. The 4th option is typically a tactical/action choice. |

- **PARAGON (blue):** Calm, empathetic, or diplomatic. Companions who value idealism or mercy tend to **approve**.
- **INVESTIGATE (gold):** Cautious, curious, or probing. Good for intel; companions who value caution or pragmatism often **approve**.
- **RENEGADE (red):** Firm, ruthless, or decisive. Companions who value pragmatism or results over ideals tend to **approve**.
- **NEUTRAL (gray):** Practical, tactical, or action-focused. A context-dependent option that may involve combat maneuvers, environmental actions, or waiting.

### 3.2 Risk Levels

Each suggested action carries a **risk level** that the Mechanic uses to set difficulty:

| Risk | Meaning |
|------|---------|
| **SAFE** | Low stakes. Unlikely to fail or trigger combat. |
| **RISKY** | Moderate stakes. May require a skill check; failure has consequences. |
| **DANGEROUS** | High stakes. Likely to trigger combat or severe consequences on failure. |

### 3.3 Suggestions Are Deterministic

The Narrator writes only prose (5-8 sentences of novel-quality narrative), and the Director pipeline produces suggestions based on scene context: present NPCs, companion status, mechanic results, stress level, and arc stage. When `ENABLE_SUGGESTION_REFINER` is on (default), a lightweight LLM (qwen3:4b) reads the Narrator's prose and refines the suggestions to respond to what actually happened in the scene. On failure, deterministic suggestions are used as an automatic fallback — the game always has reliable suggestions.

### 3.4 Alignment & Reputation

**Alignment** (KOTOR/ME-style): **Light/Dark** and **Paragon/Renegade** axes nudge from your choices. **Faction reputation** tracks standing with factions; actions add or subtract. Both are **applied deterministically** from the mechanic result; the Narrator reflects your standing in the world.

---

## 4. Companions

### 4.1 Overview

The game includes **108 companions** across all eras, each with a unique personality, species, voice tags, motivation, and speech quirk. Companions join your party based on era, location, and story events. They **approve or disapprove** of your choices based on **tone** (PARAGON, RENEGADE, INVESTIGATE, NEUTRAL) and **their personality traits** (e.g. an idealist approves of PARAGON; a pragmatist may prefer RENEGADE).

### 4.2 Banter Styles

Each companion has a **banter style** that determines how they react to your choices. There are **17 banter styles**:

| Style | Flavor |
|-------|--------|
| **warm** | Gentle, supportive, emotionally present |
| **snarky** | Sarcastic, witty, irreverent |
| **stoic** | Reserved, disciplined, few words |
| **defensive** | Guarded, reluctant to trust |
| **wise** | Philosophical, Force-attuned, reflective |
| **calculating** | Strategic, analytical, cost-benefit thinking |
| **terse** | Minimal words, direct |
| **academic** | Scholarly, data-driven, precise |
| **gruff** | Rough, blunt, tough love |
| **apologetic** | Self-blaming, hesitant, guilty |
| **weary** | Tired, seen-too-much, cynical hope |
| **earnest** | Enthusiastic, optimistic, wholehearted |
| **diplomatic** | Measured, political, consensus-building |
| **beeps** | Droid communication (chirps, warbles, trills) |
| **analytical** | Logical, data-processing, probability-focused |
| **mystical** | Force-sensitive, cryptic, spiritual |
| **formal** | Military bearing, by-the-book, protocol-driven |

Banter lines are selected from a **pre-written pool** (60+ one-liners) using seeded RNG — no LLM calls. At higher affinity levels, companions may reference **shared memories** from earlier turns.

### 4.3 Affinity Arcs

Approval is tracked as **affinity** (-100 to 100). Affinity determines your relationship stage:

| Stage | Affinity Range | What Unlocks |
|-------|---------------|--------------|
| **STRANGER** | -100 to -10 | Minimal interaction. Companion may leave if pushed further. |
| **ALLY** | -9 to 29 | Standard companion behavior. Banter and reactions. |
| **TRUSTED** | 30 to 69 | Private conversation requests. Deeper personal dialogue. |
| **LOYAL** | 70 to 100 | Personal quest hook. The companion shares their deepest secret or goal. |

### 4.4 Inter-Party Tensions

When companions **disagree** on your choices (e.g. one approves and another disapproves of the same action), the system detects **inter-party tensions**. These tensions are surfaced to the Director and Narrator, who may weave companion conflict into the narrative — a heated exchange, a cold silence, or a confrontation between party members.

### 4.5 Companion Events

At key affinity thresholds, companions can trigger special events:

- **COMPANION_REQUEST** (TRUSTED): A personal favor or conversation
- **COMPANION_QUEST** (LOYAL): A loyalty mission tied to the companion's backstory
- **COMPANION_CONFRONTATION** (sharp affinity drop): A heated confrontation when trust breaks down

**Companion reactions are deterministic** — no extra LLM is used for approval or banter.

### 4.6 Influence System (V2.20)

Each companion now tracks **influence** (-100 to +100) alongside **trust**, **respect**, and **fear** axes. Influence changes based on how your choices align with each companion's personality triggers:

- **Intent matching**: Actions that match a companion's values (e.g., helping civilians for an idealist) increase influence
- **Meaning tags**: The semantic meaning behind your choices (reveal_values, pragmatic, deflect, etc.) affects different companions differently
- **Tone matching**: PARAGON/RENEGADE/INVESTIGATE tones interact with each companion's trait profile

The influence system is separate from the legacy affinity score and provides a more nuanced relationship model. You can see your influence, trust, respect, and fear values in the companion roster panel.

### 4.7 Banter Safety Guards (V2.20)

The **BanterManager** ensures companions only banter at appropriate moments. Banter is **never** injected during:

- **Combat** or **stealth** scenes — companions know when to be quiet
- **High-pressure** states: Watchful, Lockdown, or Wanted alert levels
- **Cooldown periods**: A global cooldown (2 turns) and per-companion cooldown (4 turns) prevent banter spam

This ensures banter feels natural and doesn't break dramatic tension.

---

## 5. Starships

### 5.1 Earning Your Ship

You do **not** start with a starship. Ships are earned **in-story** through one of several acquisition methods:

| Method | How |
|--------|-----|
| **Quest reward** | Complete a major story objective to receive a ship |
| **Purchase** | Buy a ship at a shipyard (costs credits) |
| **Salvage** | Find and repair an abandoned or wrecked vessel |
| **Faction reward** | Earn a ship through high faction reputation |
| **Theft** | Steal a ship (high risk, reputation consequences) |

When a ship is acquired, a **STARSHIP_ACQUIRED** event is logged and your `player_starship` field is updated.

### 5.2 No Ship? No Problem

Without a starship, you travel via **NPC transport** — hiring passage on freighters, shuttles, or transports. This typically costs 100-500 credits and may introduce its own story complications (unreliable pilots, pirate attacks, delayed departures).

### 5.3 Ship Context

The Director and Narrator are aware of whether you have a ship. Scenes adapt accordingly: ship-owners get boarding sequences, cockpit scenes, and dogfight encounters. Shipless characters get cantina negotiations, docking bay ambushes, and transport delays.

---

## 6. Hero's Journey Arc

### 6.1 Four-Stage Structure

The story follows a **Hero's Journey** arc with 4 stages and 12 beats:

| Stage | Beats | Focus |
|-------|-------|-------|
| **SETUP** (3-10 turns) | Ordinary World, Call to Adventure, Refusal of the Call | Establish your character, introduce the inciting incident, show initial hesitation |
| **RISING** (5-25 turns) | Meeting the Mentor, Crossing the Threshold, Tests/Allies/Enemies | Commit to the journey, face trials, build alliances and rivalries |
| **CLIMAX** (5-15 turns) | Approach Inmost Cave, Ordeal, Reward | Preparation for the central crisis, the supreme test, seize the prize |
| **RESOLUTION** (3+ turns) | The Road Back, Resurrection, Return with Elixir | Journey home with new dangers, a final test, and transformation |

### 6.2 Content-Aware Transitions

Arc stage transitions are **deterministic** (no LLM). The arc planner checks story threads, facts, and turn count before advancing. For example, SETUP does not advance to RISING until at least 2 story threads and 3 facts are established. The CLIMAX stage requires 4+ active threads.

### 6.3 NPC Archetypes

NPCs are cast into **Hero's Journey archetypes** that match the current beat:

- **MENTOR** — A wise guide who prepares the hero
- **SHADOW** — The primary antagonist or dark reflection
- **THRESHOLD GUARDIAN** — Tests the hero's resolve
- **ALLY** — A loyal friend and supporter
- **SHAPESHIFTER** — An ambiguous figure whose loyalty is uncertain
- **HERALD** — The bringer of change
- **TRICKSTER** — A chaotic figure who disrupts and enlightens

---

## 7. Genre System

### 7.1 Automatic Genre Detection

The game automatically assigns a **narrative genre** based on your background and location. Genre shapes the Director's scene instructions and the Narrator's prose tone. There are **10 genres**:

| Genre | Flavor |
|-------|--------|
| **military_tactical** | Squad tactics, chain of command, battlefield tension |
| **espionage_thriller** | Covert ops, double agents, information warfare |
| **space_western** | Frontier justice, cantina deals, outpost survival |
| **noir_detective** | Underworld contacts, shadowy investigations, moral ambiguity |
| **mythic_quest** | Force temples, ancient prophecies, spiritual journeys |
| **political_thriller** | Senate intrigue, diplomatic maneuvering, power plays |
| **survival_horror** | Hostile environments, dwindling resources, isolation |
| **dark_fantasy** | Sith temples, dark side corruption, forbidden knowledge |
| **heist_caper** | Smuggling runs, elaborate plans, double-crosses |
| **court_intrigue** | Palace politics, courtly manipulation, hidden alliances |

### 7.2 Genre Shifts

Genre can **shift mid-campaign** when your location context changes significantly (e.g. moving from a frontier outpost to a Sith temple shifts from space_western to dark_fantasy). A cooldown of 5 turns prevents jarring whiplash between genres.

---

## 8. Era Progression

### 8.1 Available Eras

The game supports four major eras of the Star Wars Expanded Universe:

| Era | Period | Key Context |
|-----|--------|-------------|
| **REBELLION** | Galactic Civil War | Empire vs Rebellion, Death Star era |
| **NEW_REPUBLIC** | Post-Endor reconstruction | New government, Imperial remnants |
| **NEW_JEDI_ORDER** | Yuuzhan Vong invasion | Extragalactic threat, Jedi Order rebuilding |
| **LEGACY** | ~130 ABY | Sith resurgence, Fel Empire, fragmented galaxy |

### 8.2 Era Transitions

When you complete an era's arc, your character can **carry over** to the next era. Your character sheet, inventory, and companion relationships persist, but the world state resets to reflect the new era's political landscape, factions, and threats.

---

## 9. Character Creation

### 9.1 Gender Selection

During character creation, you choose **male or female**. Your gender selection determines pronouns (he/him or she/her) that are injected into Director and Narrator prompts, ensuring consistent and immersive prose throughout the campaign.

### 9.2 Background Selection

Your background determines your starting skills, credits, location, and initial genre. Each era has its own set of backgrounds (e.g. Rebel Operative, Smuggler, Imperial Defector for the Rebellion era).

---

## 10. Rumors & the Comms Feed

When the world **ticks** (or you travel), **rumors** can appear—turned into a **Comms / Briefing** feed (ME-style): punchy **headlines**, **source** (CIVNET, INTERCEPT, UNDERWORLD), **urgency** (LOW, MED, HIGH). The Director may suggest an action for high-urgency items; companions may comment if a briefing touches a faction they care about. The feed is **bounded** (latest 10-20 items); **shaping is deterministic** (keyword-based), not LLM-generated.

---

## 11. Quick Reference

| Concept | Takeaway |
|--------|----------|
| **Time** | Every action costs in-world time; the world clock advances and drives off-screen events and rumors at set intervals (`WORLD_TICK_INTERVAL_HOURS`). |
| **Waiting** | When you wait or time passes, the world can "tick": factions move, rumors appear. |
| **Stress** | High stress changes how the narrator tells the story (fragmented, sensory, less "reliable" in tone)—not the underlying facts. |
| **Psychology** | Mood and trauma influence tone and which complications the Director and Narrator emphasize. |
| **Dialogue wheel** | 4 options: PARAGON (blue), INVESTIGATE (gold), RENEGADE (red), NEUTRAL (gray). No free-text input. |
| **Risk levels** | SAFE, RISKY, DANGEROUS — determines mechanic difficulty and consequence severity. |
| **Companions** | 108 companions, 17 banter styles, affinity arcs (STRANGER to LOYAL), inter-party tensions. |
| **Starships** | Earned in-story (quest, purchase, salvage, faction, theft). No ship = hire NPC transport. |
| **Hero's Journey** | 4-stage arc (SETUP, RISING, CLIMAX, RESOLUTION) with 12 beats. Content-aware transitions. |
| **Genre** | 10 genres auto-assigned from background/location. Genre shifts mid-campaign when context changes. |
| **Alignment / Reputation** | Light-Dark and Paragon-Renegade nudge from choices; faction reputation from outcomes; both applied deterministically. |
| **Comms feed** | Rumors become briefing items (headline, source, urgency); Director and companions can react; shaping is deterministic. |

---

## 12. For Hosts / Technical Note

- **LLM models:** Quality-critical roles (Director, Narrator) use **mistral-nemo:latest** (~7GB VRAM). Lightweight roles (Architect, Casting, Biographer, KG Extractor) use **qwen3:4b** (~2GB). Specialist roles (Mechanic, Ingestion Tagger) use **qwen3:8b** (~5GB). Only one model is loaded at a time (specialist swapping), so peak VRAM is ~7GB. All models run locally via Ollama.
- **World tick:** How often the world "ticks" (faction updates, new rumors) is controlled by **`WORLD_TICK_INTERVAL_HOURS`** (default: 4 in-world hours = 240 minutes). Set the `WORLD_TICK_INTERVAL_HOURS` environment variable to override (e.g. `2` for faster ticks).
- **Time economy:** Action costs (dialogue, travel, combat, etc.) are centralized in **`backend/app/time_economy.py`**. Default costs are tuned so that, in typical play, a tick occurs roughly every 6-12 turns. Run `python backend/scripts/tick_pacing_sim.py` to simulate pacing and verify.
- **Lore ingestion:** PDF support is in **`ingest_lore`** (not the main `ingest` script). It uses **`pymupdf4llm`** for layout-preserving extraction (headers, tables). Run `python -m ingestion.ingest_lore --input ./data/lore --db ./data/lancedb` for PDF/EPUB/TXT with hierarchical chunking.

---

## 13. Character Alias System

During lore ingestion, chunks are tagged with **`characters[]`**—canonical character IDs (e.g. `luke_skywalker`) that appear in the text. This enables retrieval filters like "chunks mentioning Luke."

### 13.1 How to Add Characters

Edit **`data/character_aliases.yml`**. The format is:

```yaml
canonical_id:
  - "Display Name 1"
  - "Display Name 2"
  - "Alias"
```

Example:

```yaml
luke_skywalker:
  - "Luke"
  - "Luke Skywalker"
  - "Master Skywalker"

leia_organa:
  - "Leia"
  - "Leia Organa"
  - "Leia Organa Solo"
```

- **canonical_id**: The stable ID stored in `characters[]` (use snake_case, e.g. `luke_skywalker`).
- **aliases**: Display names or nicknames that appear in text. Matching is **case-insensitive** and uses **word boundaries**—so "Luke" matches, but "Lukewarm" does not.

### 13.2 Configuration

- **Default path:** `./data/character_aliases.yml`
- **Override:** Set `CHARACTER_ALIASES_PATH` to a different file path.
- **Missing file:** If the alias file is missing or invalid, ingestion uses `characters=[]` (no guesswork).

---

## 14. Character Facets & Era-Specific Voice (Feature Not Implemented)

**Status:** The character facet system is **incomplete** and **disabled by default** (`ENABLE_CHARACTER_FACETS=0`).

### 14.1 Current State

The codebase includes infrastructure for era-scoped character voice profiles, but the implementation is non-functional:

- The `build_character_facets` script produces **generic text statistics** (modal verb counts, sentence length) that apply equally to all characters
- It does **not** generate character-specific voice profiles, personality traits, or knowledge boundaries
- The `character_core` section is always empty (`aliases: [], traits: []`)
- The `use_llm` parameter is hardcoded to `False` and there is no LLM implementation

### 14.2 What Would Need to Be Implemented

To make character facets functional, you would need to:

1. **Implement LLM-based analysis** in `ingestion/build_character_facets.py`:
   - Replace `_deterministic_voice_profile()` with actual character voice analysis (speech patterns, vocabulary, tone per era)
   - Replace `_deterministic_knowledge_scope()` with knowledge boundary analysis (what they know/don't know in each era)
   - Add personality trait extraction to populate `character_core`

2. **Era normalization**: Fix inconsistent era metadata in lore chunks (currently a mix of canonical eras, book series names, and "unknown/default")

3. **Enable the feature**: Set `ENABLE_CHARACTER_FACETS=1` after implementation

### 14.3 Current Recommendation

**Do not run `build_character_facets`** unless you plan to implement the missing functionality. The system works perfectly without it - the Narrator generates appropriate dialogue without needing character voice retrieval.

---

## 15. Canon / Voice Guardrail

The Narrator must **not assert character-history specifics** (e.g. favorite X, always/never, born, grew up, used to) unless supported by retrieved lore or voice snippets. When **neither** exists, a post-processor **softens** risky phrases deterministically:

| Risky phrase | Softened to |
|--------------|-------------|
| favorite | apparent favorite |
| always | often |
| never | rarely |
| born in/on/at | reportedly born in |
| grew up | reportedly grew up |
| used to | is said to have |
| as you remember | as some say |

If lore or voice snippets are present, the post-processor skips softening (we assume possible support). This keeps narration grounded and avoids inventing canon facts.
