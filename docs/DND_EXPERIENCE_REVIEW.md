# DnD Experience Review: How Close Are We?

## Executive Summary

Storyteller-V2 is **surprisingly close** to a fully immersive DnD-like experience with
stats hidden behind a narrative CYOA interface. The bones are strong — you have a
narrative dice system, companion loyalty, faction reputation, a living world sim, quest
branching, and a 4-stage Hero's Journey arc engine. What's missing isn't the engine;
it's the **data density** and the **content generation pipeline** that would make the world
feel as deep as a Baldur's Gate or KOTOR campaign.

**Score: ~70% of the way to the vision.** The remaining 30% is almost entirely about
enriching the data layer — not rewriting the engine.

### Design Philosophy: A Campaign Is a Character's Career

A campaign **is** the character. Think Jim Butcher's Harry Dresden across 17+ novels,
Captain Kirk from TOS through six films, or Jack Reacher walking into town after town.
The player doesn't start a "3-part story" — they start a **career**. Each arc is one
novel/movie in that career: self-contained but shaped by everything that came before.

Each gameplay arc should feel like a **movie or book** — a self-contained story with its
own cast, locations, stakes, and narrative structure. The player doesn't just "play a
Star Wars game" — they play through *The Smuggler's Gambit*, then *Shadows Over Kessel*,
then *The Last Stand at Dantooine*, and however many more novels their character's career
demands. Each arc has an opening crawl, a rising tension, a climax, and consequences
that ripple into the next. There is no predetermined end — the character's story
continues until they retire, die, or become legend.

**The series model:**
- **Dresden Files:** Same character, growing power, accumulating allies/enemies/scars.
  Book 1 is a noir mystery. Book 12 is a war. The *character* is the through-line.
- **Star Trek (Kirk):** Same captain, same crew, episodic adventures that build a
  career. Some arcs are standalone; others form multi-arc sagas (Wrath of Khan →
  Search for Spock → Voyage Home).
- **The Expanse:** Same crew, escalating stakes. Early arcs are local conflicts;
  later arcs are galaxy-shaping events. Characters grow and change across the series.

### Hybrid Architecture: Cloud LLM + Ingestion

This project uses a **hybrid approach** to content generation:

| Layer | Approach | Why |
|-------|----------|-----|
| **Data packs** (NPCs, locations, factions, quests, items) | **Cloud LLM pre-generation** | Structured output is cleaner and faster. LLMs excel at generating rich, schema-compliant game entities. |
| **Narrative grounding** (prose style, sensory details, canon fidelity) | **Ingestion + RAG** | Runtime narrator needs source-faithful prose that can't be pre-generated exhaustively. |
| **Per-arc content** (this movie's cast, screenplay, stakes) | **Cloud LLM per-arc generation** | Each new arc gets a fresh "screenplay" generated from the era pack pool. |
| **Campaign-specific content** (player backstories, homebrew lore) | **Lightweight ingestion** | User-provided material that no LLM has seen. |

Ingestion is kept for what it's irreplaceable at: **runtime narrative grounding via RAG**.
Cloud LLM pre-generation handles what it's better at: **structured data pack creation**.

---

## Part 1: Gap Analysis — What's Working, What's Missing

### What's Already Working Well

| System | Maturity | Notes |
|--------|----------|-------|
| Narrative Dice (8-outcome spectrum) | Solid | Triumph → Despair range is better than a flat d20. Feels like FFG Star Wars. |
| Stat-to-Difficulty mapping | Solid | 6-stat system with band modifiers. Clean. |
| KOTOR Dialogue Wheel (4 tones) | Solid | PARAGON/INVESTIGATE/RENEGADE/NEUTRAL. Meaning tags add depth. |
| Companion Affinity/Loyalty | Solid | BioWare-grade: trait axes, banter, loyalty missions, personal quests. |
| Faction Reputation | Solid | Hostility matrix, per-action deltas. |
| Arc Pacing (Hero's Journey) | Solid | 4-stage with LLM semantic transitions via ArcWeaver. |
| Living World (deterministic faction sim) | Solid | Off-screen moves, rumors, news feed. No LLM cost. |
| Quest System (state machine) | Good | Multi-stage with branching resolution paths. |
| Alignment Tracking | Good | light_dark + paragon_renegade dual-axis. |
| Psychological Profile | Good | Stress, trauma, mood — unique differentiator. |
| NPC Voice Profiles | Good | belief/wound/taboo/rhetorical_style/tell — deep characterization. |
| RAG Lore Retrieval | Good | Hierarchical chunks, metadata filters, 4-lane style. |
| Ingestion Pipeline | Good | PDF/EPUB/TXT → chunk → embed → LanceDB. NPC tagging. |

### What's Missing or Thin

| Gap | Impact | Difficulty to Fix |
|-----|--------|-------------------|
| **No skill/proficiency system** | Players can't specialize or grow in specific areas | Medium |
| **No ability/feat/perk tree** | Progression agent suggests abilities but there's no structured unlock tree | Medium |
| **Equipment has no mechanical weight** | Items exist in inventory but don't have stats, slots, or synergies | Medium |
| **No encounter difficulty scaling** | No CR-like system; encounters don't scale to player level | Low |
| **Quest consequences are shallow** | `reputation_rebel_alliance: '+10'` but no world-state mutations, NPC deaths, location changes | Medium |
| **No crafting/economy system** | Credits exist but there's no shop, pricing, or trade mechanic | Low-Medium |
| **Era packs lack environmental storytelling** | Locations have services/security but no atmosphere, sensory details, or dynamic events tied to weather/time | Low |
| **No "codex" or lore discovery system** | Players can't unlock lore entries; knowledge is invisible | Low |
| **No procedural quest generation** | All quests are hand-authored in YAML; can't generate from ingested lore | Medium-High |
| **Travel is flat** | Travel links exist but there are no random encounters, fuel costs, or journey events | Low |
| **No "camp" or downtime system** | BioWare games have the Normandy/Ebon Hawk; we have no party hub with companion conversations | Low |
| **No "movie/book" arc packaging** | Each arc doesn't feel like a self-contained cinematic experience with its own cast and structure | Medium |
| **No species/race selection** | Character creation skips species entirely; narrator has no physical/cultural identity to work with | Low-Medium |
| **No playable prologue/origin story** | Character background is a form, not an experience; players don't *play* their origin | Medium |
| **Character creation is shallow** | 2-3 questions, no species, background doubles as class — doesn't feel like an MMO character creator | Medium |

---

## Part 2: Character Creation — The MMO Experience

### Design Goal

Character creation should feel like starting a new character in **SWTOR or Dragon Age:
Origins** — not like filling out a form. The player should make meaningful narrative
choices that shape who they are, then *play through* their origin story before the
first movie/book arc begins.

**Current state:** The `EraBackground` model supports 2-3 branching questions with
PARAGON/RENEGADE/NEUTRAL tones, starting stats, faction hints, and thread seeds. The
`BiographerAgent` converts this into a character sheet. This is a good foundation, but
it's not an experience — it's a questionnaire.

**Target state:** A multi-step character creation flow that feels like the first 15
minutes of a BioWare game, followed by a playable prologue that IS your origin story.

### The Character Creation Flow

```
Step 1: Choose Your Species/Race
    ↓
Step 2: Choose Your Class/Archetype
    ↓
Step 3: Answer the Deep Questions (5-7 narrative choices)
    ↓
Step 4: Name & Identity
    ↓
Step 5: Review & Confirm
    ↓
→ Prologue begins (playable origin story, 5-10 turns)
    ↓
→ Arc 1 begins (first movie/book)
```

### Step 1: Species/Race Selection

**What's needed:** A `species` catalog in the era pack that the Cloud LLM generates
alongside NPCs and locations.

```yaml
# In era pack: species.yaml (NEW, Cloud LLM generated)
species:
  - id: human
    name: Human
    description: >
      The galaxy's most adaptable species. Found on every world, in every
      faction, on every side of every conflict. What humans lack in natural
      ability they make up for in sheer stubbornness.
    cultural_notes: >
      Humans dominate the Empire and form the backbone of the Rebellion.
      Core Worlders tend toward formality; Outer Rim humans are rougher,
      more independent.
    stat_affinity: null  # No stat bonus — balanced
    narrative_hooks:
      - "Easily blends into any crowd"
      - "No species prejudice works against them — or for them"
    appearance_traits:
      hair: [black, brown, blonde, red, gray, white]
      build: [slight, average, stocky, tall, imposing]

  - id: twilek
    name: Twi'lek
    description: >
      Graceful, colorful, and survivors above all else. Centuries of
      enslavement have made Twi'leks resourceful, charming, and deeply
      distrustful of promises.
    cultural_notes: >
      Ryloth's clan-based society values community over individualism.
      Many Twi'leks in the galaxy are far from home — by choice or by force.
    stat_affinity: { charisma: 1 }  # Natural charm
    narrative_hooks:
      - "Lekku body language adds subtext to every conversation"
      - "Other species underestimate them — a useful weapon"
    appearance_traits:
      skin_color: [blue, green, red, orange, pale, purple]
      lekku_style: [draped, wrapped, adorned, plain]

  - id: wookiee
    name: Wookiee
    description: >
      Seven feet of loyalty, rage, and mechanical genius. Wookiees
      remember every debt and every wrong — sometimes for centuries.
    cultural_notes: >
      Kashyyyk's wroshyr-tree cities bred a species that values honor
      above life. A Wookiee life debt is absolute.
    stat_affinity: { combat: 1 }  # Raw physical power
    narrative_hooks:
      - "Most species can't understand Shyriiwook — a translator or patience is needed"
      - "Imperial enslavement of Kashyyyk makes every stormtrooper a personal enemy"
    appearance_traits:
      fur_color: [brown, black, auburn, gray, white]
      height: [tall, very_tall, towering]
```

**Why species matters for narrative:**
- The narrator uses `appearance_traits` and `cultural_notes` to describe the player
  authentically — a Twi'lek smuggler is described differently than a human smuggler
- `narrative_hooks` give the director and narrator per-species story angles
- `stat_affinity` provides a soft nudge, not a hard requirement — narrative-first
- NPC reactions can vary by species (Imperial racism toward aliens, underworld
  connections for certain species)

### Step 2: Class/Archetype Selection

**Current:** The `EraBackground` model (Smuggler, Bounty Hunter, etc.) serves as both
"class" and "background." This works but conflates two distinct concepts:

- **Class** = what you *do* (combat role, skill focus, story archetype)
- **Background** = where you *come from* (origin, culture, motivation)

In SWTOR, a Smuggler is a class. But there are many *kinds* of smugglers — one with a
conscience, one for profit, one running from something. The class defines the archetype;
the background questions define the individual.

**Proposed enhancement:** Elevate the current `EraBackground` to be the class/archetype,
and add deeper background questions that define the individual within that archetype.

```yaml
# Enhanced backgrounds.yaml (renamed role: class/archetype)
classes:
  - id: smuggler
    name: Smuggler
    tagline: "Fast ship, faster mouth, flexible morals"
    description: >
      You live between the cracks of the galaxy — running cargo the
      Empire doesn't want moved, for people who can't afford to be
      seen. Every hyperspace jump is a gamble, every docking bay a
      potential trap.
    icon: smuggler
    story_archetype: trickster  # Maps to narrative patterns
    starting_stats: { Combat: 2, Stealth: 3, Charisma: 3, Tech: 2, General: 0 }
    starting_reputation: { rebel_alliance: 10, underworld: 40 }
    starting_abilities:
      - id: fast_talk
        name: Fast Talk
        description: "Talk your way out of (almost) anything"
        stat: Charisma
        difficulty_modifier: -1
      - id: smugglers_luck
        name: Smuggler's Luck
        description: "Once per arc, reroll a failed check"
        uses_per_arc: 1
    prologue_scenario: prologue-smuggler  # Links to prologue screenplay
    narrative_tone: >
      Quippy, streetwise, morally gray. Thinks three moves ahead but
      pretends to wing it. Han Solo meets Malcolm Reynolds.

  - id: force_sensitive
    name: Force-Sensitive Exile
    tagline: "The Force is strong in you. The Empire noticed."
    description: >
      You feel things others can't — a tremor in the air before danger,
      a whisper of possibility in moments of despair. The Jedi are gone,
      and the Inquisitors hunt anyone who might replace them.
    icon: jedi
    story_archetype: reluctant_hero
    starting_stats: { Combat: 2, Stealth: 2, Charisma: 2, Tech: 1, General: 3 }
    starting_reputation: { galactic_empire: -20 }
    starting_abilities:
      - id: force_sense
        name: Force Sense
        description: "Sense danger, emotions, and hidden truths"
        stat: General
        difficulty_modifier: -1
      - id: telekinesis
        name: Telekinesis
        description: "Move objects with the Force"
        stat: General
        difficulty_modifier: 0
    prologue_scenario: prologue-force-exile
    narrative_tone: >
      Contemplative, burdened, quietly powerful. Speaks carefully.
      Carries the weight of a destroyed order.
```

### Step 3: The Deep Questions (5-7 Narrative Choices)

The current system supports 2-3 questions. This should expand to 5-7, with later
questions conditionally branching based on earlier answers. Each question should feel
like a **narrative choice**, not stat allocation.

**Design principles:**
- Questions shape *who you are*, not *what numbers you have*
- Effects are hidden — the player sees a story choice, not "+1 Charisma"
- Later questions branch based on earlier tones (PARAGON path opens different
  follow-ups than RENEGADE)
- Each answer seeds narrative hooks for the prologue and Arc 1

**Example question chain for Smuggler class:**

```yaml
questions:
  - id: motivation
    title: "Why do you fly?"
    subtitle: "Everyone has a reason to risk their neck in hyperspace."
    choices:
      - label: "To help people who can't help themselves"
        concept: "a smuggler with a conscience who runs refugees past blockades"
        tone: PARAGON
        effects:
          faction_hint: rebel_alliance
          alignment_nudge: { light_dark: +5 }
          thread_seed: "A network of safe houses depends on your runs"
          companion_affinity_bonus: [{ comp-reb-mercy: 20 }]
      - label: "Credits. Pure and simple."
        concept: "a smuggler who lives for the next score and the next drink"
        tone: NEUTRAL
        effects:
          faction_hint: underworld
          stat_bonus: { Tech: 1 }
          thread_seed: "You owe someone dangerous a lot of money"
      - label: "Because the Empire took everything else"
        concept: "a smuggler with a vendetta, using the black market to fund revenge"
        tone: RENEGADE
        effects:
          faction_hint: rebel_alliance
          alignment_nudge: { paragon_renegade: -5 }
          thread_seed: "An Imperial officer destroyed your homeworld"
          psych_seed: { active_trauma: "loss_of_home" }

  - id: left_behind
    title: "Who did you leave behind?"
    subtitle: "The cockpit is lonely. Someone's face haunts the quiet moments."
    choices:
      - label: "A sibling who chose the Empire"
        concept: "estranged from family over ideology"
        tone: NEUTRAL
        effects:
          npc_seed: { role: rival, relationship: sibling, faction: galactic_empire }
          thread_seed: "Your sibling is rising through Imperial ranks"
      - label: "A mentor who taught you everything, then disappeared"
        concept: "searching for answers about a vanished teacher"
        tone: INVESTIGATE
        effects:
          npc_seed: { role: mentor, status: missing }
          thread_seed: "Rumors of your mentor surface on the Outer Rim"
      - label: "No one. That's the point."
        concept: "a loner who burns bridges before anyone can betray them"
        tone: RENEGADE
        effects:
          psych_seed: { stress_level: 3 }
          stat_bonus: { Stealth: 1 }

  - id: regret
    title: "What keeps you up at night?"
    subtitle: "Everyone in this business has a story they don't tell at cantinas."
    choices:
      - label: "A cargo run that went wrong — people got hurt"
        concept: "haunted by a past failure with collateral damage"
        tone: PARAGON
        effects:
          psych_seed: { active_trauma: "collateral_guilt" }
          alignment_nudge: { light_dark: +3 }
          thread_seed: "Survivors of that run are still out there"
      - label: "A betrayal I saw coming but didn't stop"
        concept: "learned the hard way that loyalty is a liability"
        tone: NEUTRAL
        effects:
          stat_bonus: { Stealth: 1 }
          thread_seed: "The betrayer thinks you're dead"
      - label: "Nothing. Sleep like a baby."
        concept: "either deeply compartmentalized or genuinely cold"
        tone: RENEGADE
        effects:
          psych_seed: { stress_level: -2 }
          alignment_nudge: { paragon_renegade: -3 }

  - id: survival
    title: "The Empire cracked down on your sector. How did you survive?"
    subtitle: "Imperial patrols doubled overnight. Most runners got caught."
    condition: null  # Always shown
    choices:
      - label: "Bribed the right people and kept my head down"
        concept: "survival through cunning and well-placed credits"
        tone: NEUTRAL
        effects:
          stat_bonus: { Charisma: 1 }
          faction_hint: underworld
      - label: "Ran a blockade that nobody thought possible"
        concept: "became a legend in the underworld for one impossible run"
        tone: PARAGON
        effects:
          reputation_bonus: { underworld: 20 }
          thread_seed: "That run made you famous — fame attracts attention"
      - label: "Sold out another smuggler to save my own skin"
        concept: "carries the guilt (or doesn't) of trading a colleague's freedom"
        tone: RENEGADE
        effects:
          npc_seed: { role: enemy, relationship: betrayed_colleague }
          thread_seed: "The smuggler you sold out just got released from Kessel"

  - id: cargo
    title: "What's in the hidden compartment right now?"
    subtitle: "Every smuggler has a secret hold. Yours isn't empty."
    choices:
      - label: "Stolen Imperial intelligence — I don't even know what it says"
        concept: "sitting on information that could change the war"
        tone: INVESTIGATE
        effects:
          item_seed: { id: "stolen_intel", type: key_item }
          thread_seed: "Both the Rebellion and the Empire want what you have"
          quest_seed: "The contents of the data chip"
      - label: "A lightsaber. Don't ask where I got it."
        concept: "carrying a Jedi relic with a history you don't fully understand"
        tone: NEUTRAL
        effects:
          item_seed: { id: "found_lightsaber", type: key_item }
          thread_seed: "Someone is looking for that lightsaber"
      - label: "Medical supplies for a planet under blockade"
        concept: "using the smuggling network for something that matters"
        tone: PARAGON
        effects:
          faction_hint: rebel_alliance
          alignment_nudge: { light_dark: +5, paragon_renegade: +3 }
          thread_seed: "The blockaded planet is running out of time"
```

### Step 4: Name & Identity

After class selection and questions, the player provides:
- **Name** (or let the Cloud LLM suggest from era pack namebanks)
- **Gender** (for pronoun system — already supported)
- **Appearance traits** (selected from species options, used by narrator for description)

This is lightweight — the narrative choices in Steps 2-3 carry the weight.

### What the Cloud LLM Generates for Character Creation

As part of the era pack (Layer 1), the Cloud LLM generates:
- **Species catalog** with cultural notes, stat affinities, and appearance traits
- **Class/archetype definitions** with starting stats, abilities, and narrative tone
- **Deep question chains** (5-7 per class) with branching and rich effects
- **Prologue scenarios** (one per class — see next section)

This means spinning up a new universe automatically includes a complete character
creation experience. No hand-authoring needed.

---

## Part 3: The Prologue — Playing Your Origin Story

### Design Goal

After character creation, the player doesn't jump straight into Arc 1. They play through
a **short origin story** (5-10 turns) that establishes who their character is through
gameplay, not exposition. This is the single most impactful thing you can do to make
players care about their character before the first movie/book arc begins.

**Inspirations:**
- **Dragon Age: Origins** — Each background has a unique 30-minute playable origin
- **SWTOR** — Each class has its own starting planet with a class-specific story
- **Mass Effect** — The "Earthborn/Spacer/Colonist" choice shapes Shepard's prologue
- **Cyberpunk 2077** — Corpo/Street Kid/Nomad prologues set the tone

### How the Prologue Works

```
Character Creation complete
    ↓
Cloud LLM generates prologue screenplay from:
    ├→ Era pack (Layer 1)
    ├→ Player's class/archetype
    ├→ Player's question answers (thread seeds, NPC seeds, item seeds)
    └→ Prologue scenario template (from class definition)
    ↓
Prologue screenplay:
    ├→ Setting: One location, intimate scale
    ├→ Cast: 2-4 NPCs (mentor/ally/rival/contact)
    ├→ Mini-arc: SETUP → INCITING_INCIDENT → DEPARTURE
    ├→ 1-2 key choices with visible consequences
    └→ Ends with: the reason the player leaves for the wider galaxy
    ↓
Player plays 5-10 turns of origin story
    ↓
Prologue consequences captured:
    ├→ Key NPC relationship established (mentor saved/lost, rival created)
    ├→ Defining moral choice made (alignment set)
    ├→ Starting equipment/reputation finalized
    ├→ Companion potentially introduced
    └→ Inciting incident that hooks into Arc 1
    ↓
ArcScreenplayGenerator receives prologue context
    ↓
Arc 1 opens — player arrives in the wider world, shaped by their origin
```

### Prologue Screenplay Schema

```yaml
# Generated by Cloud LLM per class/archetype, per player
prologue:
  id: prologue-smuggler-001
  class_id: smuggler
  title: "Last Run from Corellia"

  setting:
    location: loc-coronet-docks
    planet: Corellia
    atmosphere:
      lighting: dim
      mood: tense
      sensory_details:
        - "Engine oil and ozone mix with the salt air of Coronet Bay"
        - "Customs droids scan every crate; your falsified manifest won't hold up long"

  cast:
    - npc_id: prologue-fixer-renn
      name: Renn Voss
      role: quest_giver
      description: "A grizzled Corellian fixer who's given you work for years"
      relationship_to_player: mentor_figure
      voice_profile:
        rhetorical_style: blunt
        belief: "Everyone has a price; know yours before someone else sets it"
        wound: "Lost a partner to an Imperial sting twenty years ago"
    - npc_id: prologue-officer-kael
      name: Lieutenant Kael
      role: antagonist
      description: "An ambitious young Imperial customs officer — smart, ruthless, rising fast"
      relationship_to_player: pursuer

  mini_arc:
    setup:
      description: >
        You're loading cargo at Coronet Docks when Renn Voss approaches with
        one last job — bigger than anything he's offered before, and clearly
        dangerous. Imperial patrols have tripled this week.
      turn_budget: 2-3

    inciting_incident:
      description: >
        Mid-job, Lieutenant Kael arrives with a squad. He knows something's
        wrong but not exactly what. The player must choose: bluff, hide,
        fight, or abandon the cargo.
      key_choice:
        question: "Kael is closing in. What do you do?"
        options:
          - action: "Talk your way past him (Charisma)"
            outcome_success: "Kael lets you go but remembers your face"
            outcome_failure: "Kael sees through you — chase sequence"
          - action: "Slip away through the maintenance tunnels (Stealth)"
            outcome_success: "Clean getaway; Renn handles the rest"
            outcome_failure: "You escape but Renn gets captured"
          - action: "Create a distraction and run for the ship (Combat)"
            outcome_success: "Explosive exit; you're now wanted on Corellia"
            outcome_failure: "Blaster fight; you escape but you're wounded"
      turn_budget: 3-4

    departure:
      description: >
        The job is done (or botched). Either way, Corellia is too hot now.
        Renn — if he's still free — gives you coordinates for a contact
        in the Outer Rim who needs a pilot with "flexible ethics."
      establishes:
        - "Why the player left home"
        - "A key NPC relationship (Renn: alive/captured, Kael: pursuing)"
        - "The player's default approach to problems (talk/sneak/fight)"
      turn_budget: 2-3

  consequences:
    # Fed into ArcScreenplayGenerator as "origin context"
    npc_states:
      prologue-fixer-renn: { status: "alive|captured", relationship: "mentor" }
      prologue-officer-kael: { status: "pursuing", threat_level: "low|medium|high" }
    player_approach: "talk|sneak|fight"  # Inferred from choices
    items_gained: ["manifest_chip"]  # From question chain item_seed
    departure_reason: "Corellia is too hot; heading to the Outer Rim"
    narrative_thread: "Renn's contact in the Outer Rim needs a pilot"
```

### Why the Prologue Matters

1. **Players care about characters they've played, not characters they've described.**
   A 5-turn origin where you *choose* to save your mentor is more impactful than a
   backstory paragraph that says "you're loyal to your mentor."

2. **It teaches the game.** The prologue is a natural tutorial — the player learns
   the dialogue wheel, dice resolution, and choice consequences in a low-stakes
   environment before the first arc raises the stakes.

3. **It generates Arc 1 hooks.** The prologue's consequences (who survived, what you
   chose, what you carry) become the raw material for Arc 1's screenplay. The
   ArcScreenplayGenerator doesn't need to invent motivation from scratch — the player
   already has it.

4. **It differentiates playthroughs from turn 1.** Two smuggler players who make
   different prologue choices start Arc 1 in meaningfully different positions — different
   NPC relationships, different items, different reputations.

5. **It makes the origin story the opening crawl.** Instead of "A long time ago in a
   galaxy far, far away..." being generic text, Arc 1's opening crawl can reference
   what actually happened: "Fleeing Corellia after a job gone wrong, a smuggler with a
   stolen manifest heads for the Outer Rim — unaware that the data in their hidden
   compartment could change the course of the war..."

### Prologue → Arc 1 Handoff

The prologue's consequence manifest feeds directly into the ArcScreenplayGenerator:

```yaml
# Passed to Cloud LLM for Arc 1 generation
origin_context:
  class: smuggler
  species: human
  prologue_title: "Last Run from Corellia"
  prologue_consequences:
    npc_states:
      renn_voss: { alive: true, relationship: mentor, location: corellia }
      lt_kael: { pursuing: true, threat_level: medium }
    defining_choice: "Talked past Kael — player prefers charm over violence"
    alignment_after_prologue: { light_dark: 8, paragon_renegade: 2 }
    items: [manifest_chip, stolen_intel]
    departure_thread: "Heading to Ord Mantell to meet Renn's contact"
  character_voice: "Quippy under pressure, avoids violence when possible"
  question_chain_seeds:
    - "Smuggler with a conscience — runs refugees"
    - "Mentor figure (Renn) who taught them the trade"
    - "Haunted by a cargo run that went wrong"
    - "Survived the crackdown by running an impossible blockade"
    - "Carrying stolen Imperial intelligence"
```

Arc 1's screenplay then builds on this — Renn's contact becomes an NPC in the cast,
Lt. Kael becomes a recurring antagonist, the stolen intel becomes a plot driver.

---

## Part 4: The Three-Layer Content Model

### How Content Flows from Universe to Gameplay

Content exists at three layers, each with its own generation strategy and lifecycle:

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: UNIVERSE CANON (Era Pack)                         │
│  Generated: Once, by Cloud LLM or hand-authored             │
│  Contains: Everything that *could* exist in this era        │
│  Think: The Star Wars encyclopedia                          │
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  LAYER 2: MOVIE/BOOK (Arc Screenplay)                 │ │
│  │  Generated: Per arc, by Cloud LLM                     │ │
│  │  Contains: This story's cast, locations, stakes,      │ │
│  │            structure, and emotional beats              │ │
│  │  Think: A movie script drawn from the encyclopedia    │ │
│  │                                                       │ │
│  │  ┌─────────────────────────────────────────────────┐  │ │
│  │  │  LAYER 3: RUNTIME (Emergent Play)              │  │ │
│  │  │  Generated: During play, by engine + RAG       │  │ │
│  │  │  Contains: Player choices, consequences,       │  │ │
│  │  │            emergent events, narrator prose      │  │ │
│  │  │  Think: What actually happens on screen        │  │ │
│  │  └─────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Layer 1: Universe Canon (Era Pack)

**What it is:** The complete pool of entities for a given era — every notable NPC,
location, faction, quest seed, item, and world fact. This is your studio backlot: all
the sets, costumes, and actors available for any film.

**How it's created:**

```
Cloud LLM prompt: "Generate a complete era pack for the Rebellion era of Star Wars.
Include 30+ NPCs with voice profiles, 15+ locations with atmosphere, 6+ factions
with goals and relationships, 20+ quest seeds, items, and world facts.
Output must conform to the era_pack schema."
    ↓
Human reviews and curates output
    ↓
Committed to data/static/era_packs/{era_id}/
    ↓
Validated against era_pack_models.py schemas
```

**How often:** Once per era. Updated when you want to expand the universe.

**What Cloud LLM generates:**
- NPCs with full voice profiles (belief, wound, taboo, rhetorical_style, tell)
- Locations with atmosphere, points of interest, sensory details
- Factions with goals, resources, territory, hostility relationships
- Quest seeds with branching resolution paths and consequence modeling
- Items with mechanical effects and rarity
- World facts, rumors, namebanks, backgrounds
- NPC relationship webs
- Moment triggers (companion emotional beats)
- Codex entries

**What ingestion provides instead:** Nothing at this layer. Cloud LLM is better at
structured entity generation than extraction-from-prose. The old Phase 2 entity
extraction pipeline is replaced by direct Cloud LLM generation.

### Layer 2: Movie/Book (Arc Screenplay)

**What it is:** When the player starts a new story arc, the Cloud LLM generates a
**screenplay** — the specific cast, locations, stakes, and narrative structure for
*this story*. It doesn't regenerate the universe; it casts a new film from the same
studio backlot.

**The "character career" mental model:**

A campaign is a character's ongoing career — like a book series. Each arc is one
novel/movie in that career. There is no predetermined number of arcs. The character
keeps going until they retire, die, or the player decides their story is told.

- **Arc 1:** *The Smuggler's Gambit* — First job, establishing the character
- **Arc 2:** *Shadows Over Kessel* — Darker tone, old enemies resurface
- **Arc 3:** *The Inquisitor's Trail* — Galactic stakes, companions tested
- **Arc 7:** *The Battle of Dantooine* — The character is a legend now; everything converges
- **Arc 12:** *One Last Run* — Maybe. Or maybe there's one more after that.

Like the Dresden Files, early arcs can be relatively standalone noirs. As the character
accumulates allies, enemies, scars, and reputation, later arcs naturally escalate —
not because of a predetermined plot, but because the character's growing history
creates larger and more interconnected stakes.

**What grows across arcs (the character's "career file"):**
- **Relationship history** — NPCs met, allies made, enemies created, debts owed
- **Reputation** — Faction standings shift novel by novel
- **Companion bonds** — Loyalty deepens (or fractures) over multiple arcs
- **Psychological weight** — Trauma accumulates, stress patterns emerge
- **World mutations** — Locations destroyed, factions shifted, regimes changed
- **The character themselves** — Stats grow, abilities unlock, alignment drifts

Each arc generates its own metadata because each movie needs its own:

```
Cloud LLM Arc Generation (per new arc):
    ↓
├→ Arc Screenplay
│   ├→ title: "The Smuggler's Gambit"
│   ├→ tone: heist_thriller
│   ├→ opening_crawl: "The Empire tightens its grip..."
│   ├→ act_structure:
│   │   ├→ act_1: { setup, inciting_incident, turn_budget: 10-15 }
│   │   ├→ act_2: { rising_action, midpoint_twist, turn_budget: 15-25 }
│   │   └→ act_3: { climax, resolution, turn_budget: 8-12 }
│   └→ central_tension: "A stolen Imperial manifest reveals a secret
│       that both the Rebellion and a Hutt cartel will kill for"
│
├→ This Movie's Cast (subset + tailored from era pack)
│   ├→ 8-12 NPCs selected from era pack pool
│   ├→ Relationships woven for THIS story (ally, rival, secret)
│   ├→ Per-NPC arc role: protagonist_ally, antagonist, wild_card, mentor
│   └→ Per-NPC arc agenda: what do they want in THIS story?
│
├→ This Movie's Locations (4-6 from era pack, tailored)
│   ├→ Selected for geographic narrative flow
│   ├→ Act-mapped: "Act 1 opens at the cantina, Act 2 moves to the spaceport"
│   └→ Atmosphere adjusted for arc tone
│
├→ This Movie's Quests (2-4 from era pack seeds, fully fleshed)
│   ├→ Main quest: the spine of this arc
│   ├→ Side quests: optional but enriching
│   └→ Each with per-path consequences that affect the NEXT arc
│
├→ This Movie's Moments (6-10 triggered narrative beats)
│   ├→ Companion reactions to arc-specific events
│   ├→ Callbacks to previous arcs (if sequel)
│   └→ Emotional beats timed to act structure
│
└→ Arc-End Consequences (what ripples forward)
    ├→ Which NPCs survived / changed allegiance
    ├→ World state mutations
    ├→ Companion loyalty shifts
    └→ Seeds for the next arc
```

**Yes — each new arc gets a fresh Cloud LLM generation pass.** But it's a focused,
constrained generation: "Given this era pack pool, these carry-forward consequences
from the last arc, and this player's character + companion state, generate a screenplay
for the next movie."

**Why this works:**
1. **Each arc feels authored** — not random, not generic. It has a title, a tone, an
   opening crawl, a three-act structure.
2. **Replayability** — same era pack, different screenplay every time. Two players in
   the Rebellion era get different movies.
3. **Consequence threading** — Arc 2's screenplay knows what happened in Arc 1. NPCs
   who died stay dead. Factions you betrayed remember.
4. **Bounded generation cost** — each arc is one Cloud LLM call (or a small chain),
   not continuous generation. The output is structured YAML, not freeform prose.

### Layer 3: Runtime (Emergent Play)

**What it is:** What actually happens as the player makes choices within the screenplay.
The engine takes the screenplay and lets the player reshape it.

**What powers it:**
- **Ingestion + RAG** provides the narrator with source-faithful prose, sensory details,
  and canon-accurate descriptions at runtime. This is where ingestion is irreplaceable.
- **The existing engine** (resolution, world sim, companion system, arc pacing) runs
  the gameplay loop.
- **The screenplay** provides structure, but the player can break it. The ArcWeaver
  adapts. The director pivots. The narrator weaves in retrieved lore.

**What RAG provides that Cloud LLM can't:**
- Prose that sounds like a specific author's writing, not generic LLM output
- Sensory details from specific source material (how *this author* describes Mos Eisley)
- Canon-faithful responses to unexpected player questions ("What does the Bothan
  spy network actually look like?")
- Grounding that prevents hallucination when the narrator needs to describe something
  the screenplay didn't anticipate

---

## Part 5: Ingestion — Scoped to RAG

### What Ingestion Does Now (Keep As-Is)

```
Source Files (PDF/EPUB/TXT)
    ↓
Extract text → Classify document type
    ↓
Chunk (parent 1024 tokens / child 256 tokens)
    ↓
Tag metadata (era, planet, faction, doc_type, section_kind)
    ↓
Match NPC names against era pack aliases (deterministic)
    ↓
[Optional] Cloud LLM metadata enrichment (narrative_role, spoiler_tier, canon_weight)
    ↓
Embed (sentence-transformers/all-MiniLM-L6-v2, 384-dim)
    ↓
Store in LanceDB → Write manifest
```

### What Changed

1. **Ingestion no longer needs an entity extraction phase.** The old Phase 2 proposal
   (extract NPCs/locations/quests from chunks) is replaced by Cloud LLM direct
   generation. Cloud LLM produces cleaner structured output than extraction-from-prose.

2. **The optional LLM tagger can use a Cloud LLM** instead of a local 8B model. This is
   a one-time cost per source book and produces much better metadata enrichment
   (narrative_role, spoiler_tier, canon_weight).

3. **Ingestion's sole job is now feeding the narrator.** It creates the vector store
   that the 4-lane style retrieval system queries at runtime. That's it. No gameplay
   entity extraction.

### When Ingestion Matters Most

| Scenario | Ingestion Value |
|----------|----------------|
| Established universe (Star Wars, LOTR) | **High** — fans expect canon fidelity, ingested source material keeps narrator honest |
| Player provides homebrew lore | **High** — no LLM has seen this material |
| Player provides backstory documents | **Medium** — lightweight ingest to ground narrator in player's character |
| Generic/original setting | **Low** — Cloud LLM can generate everything; no source material to ingest |

### The One Risk of Cloud-LLM-First

Cloud LLM pre-generation works brilliantly for **established universes** where the LLM
has deep training data. It works less well for:

- Obscure or niche settings the LLM hasn't seen much of
- Homebrew/original worlds with specific lore
- Very recent source material past the LLM's training cutoff

For those cases, ingestion + a targeted extraction pass remains a fallback. But for
the common case — established universes — Cloud LLM generation is faster, cleaner,
and requires less infrastructure.

---

## Part 6: How to Adapt for Any Universe

### The Current Architecture Is Already Universe-Agnostic (Mostly)

The `SettingRules` model in `era_pack_models.py` is the right abstraction. It lets you
override everything from `setting_name` to `common_species` to `bypass_methods`. The
`rule_system_id` field points to a pluggable rules markdown file.

### What Needs to Change for True Universe Portability

#### 1. Stats Must Be Configurable Per-Universe

**Current:** The 6 stats (Presence, Cunning, Physique, Intellect, Willpower, Force) are
hardcoded in `storyteller_core.md`. The stat names are referenced by the resolution agent.

**Problem:** A Lord of the Rings campaign doesn't have "Force". A cyberpunk setting needs
"Netrunning". A Harry Potter setting needs "Magic" categories.

**Solution:** Add a `stat_schema` section to the setting or era pack:

```yaml
# In era.yaml or setting.yaml
stat_schema:
  stats:
    - id: might
      label: Might
      governs: "Combat, athletics, feats of strength"
      role: physique  # maps to storyteller_core role for resolution
    - id: lore
      label: Lore
      governs: "History, arcane knowledge, languages, crafting"
      role: intellect
    - id: shadow
      label: Shadow
      governs: "Stealth, deception, thievery, poison"
      role: cunning
    - id: heart
      label: Heart
      governs: "Persuasion, inspiration, resistance to despair"
      role: presence
    - id: wits
      label: Wits
      governs: "Perception, tactics, quick thinking, investigation"
      role: willpower
    # No "Force" equivalent — this is Middle-earth
  optional_stats: []  # No Force-like stat for this setting
```

The resolution agent already handles stat mapping ("if the era pack uses different stat
names, map by function"). Making this explicit in the data pack means:
- The biographer knows which stats to assign during character creation
- The UI can display the right stat names
- The progression agent knows the growth ceiling

#### 2. Bypass Methods Must Be Fully Data-Driven

**Current:** `_CORE_BYPASS_METHODS` are hardcoded, with setting-specific methods loaded
from an env var. This works but is fragile.

**Solution:** Move bypass methods into the era pack:

```yaml
# In era.yaml
bypass_methods:
  core:
    - violence
    - sneak
    - bribe
    - charm
    - intimidate
    - hack
    - disable
  setting_specific:
    - magic_arcane    # D&D
    - magic_divine    # D&D
    - wild_shape      # D&D Druid
    - channel_divinity # D&D Cleric
```

#### 3. Services and Scene Types Need Per-Universe Vocabularies

**Current:** `ALLOWED_SERVICES` and `ALLOWED_SCENE_TYPES` are hardcoded sets.

**Problem:** A medieval fantasy setting has "blacksmith", "temple", "tavern", "guild_hall".
A cyberpunk setting has "netrunner_den", "ripperdoc", "fixer". These don't map to
"briefing_room" or "medbay".

**Solution:** Two approaches (use both):

**a) Expand the core set to be genre-generic:**
```python
ALLOWED_SERVICES = {
    # Combat/Security
    "arms_dealer", "armory", "blacksmith", "weapons_shop",
    # Medical
    "medbay", "healer", "temple", "ripperdoc",
    # Social
    "cantina", "tavern", "inn", "market", "bazaar", "guild_hall",
    # Information
    "bounty_board", "quest_board", "notice_board", "informant",
    "library", "archive", "slicer", "netrunner_den",
    # Logistics
    "transport", "stable", "dock", "hangar", "safehouse",
    # Unique
    "briefing_room", "throne_room", "council_chamber",
}
```

**b) Allow era packs to register custom services:**
```yaml
# In era.yaml
custom_services:
  - id: ripperdoc
    label: Ripperdoc
    category: medical
    description: "Cybernetic implant installation and repair"
  - id: fixer
    label: Fixer
    category: information
    description: "Job broker and underworld contact"
```

#### 4. The Rule System File Should Be Fully Swappable

**Current:** `storyteller_core.md` is well-designed and setting-agnostic in principle.
The `rule_systems/catalog.yaml` supports multiple systems.

**What's needed:** A `dnd_5e_simplified.md` or `lotr_core.md` that mirrors the structure
but with system-appropriate mechanics. The resolution agent already reads the rule file
dynamically — this just needs content.

**Example for a D&D-like system:**
```markdown
# D&D SIMPLIFIED — Resolution Rules

## STATS
| Stat | Governs |
|------|---------|
| Strength | Melee combat, athletics, carrying capacity |
| Dexterity | Ranged combat, stealth, acrobatics, initiative |
| Constitution | HP, endurance, resisting poison/disease |
| Intelligence | Arcana, history, investigation, wizard spells |
| Wisdom | Perception, insight, survival, cleric/druid spells |
| Charisma | Persuasion, deception, intimidation, sorcerer/warlock/bard spells |

## DIFFICULTY
| DC | Band |
|----|------|
| 5  | Trivial |
| 10 | Easy |
| 15 | Moderate |
| 20 | Hard |
| 25 | Formidable |
| 30 | Extreme |

## DICE RESOLUTION
Roll d20 + stat modifier. Compare to DC. Nat 20 = Triumph. Nat 1 = Despair.
```

---

## Part 7: Era Pack Improvements

### Current State

The Rebellion era pack has:
- 12 YAML files (era, locations, npcs, factions, backgrounds, namebanks, quests, events, rumors, meters, facts, companions)
- Good NPC voice profiles (belief/wound/taboo)
- Good quest branching (resolution_paths)
- 8 quests with moral weight

### What's Insufficient

#### 1. Locations Lack Atmosphere

**Current:**
```yaml
- id: loc-cantina
  name: Local Cantina
  tags: [social, underworld]
  services: [cantina, bounty_board]
  security:
    controlling_faction: null
    security_level: 20
```

**What a game designer would want:**
```yaml
- id: loc-cantina
  name: The Rusty Hydrospanner
  tags: [social, underworld, dim_lighting, crowded]
  description: >
    A smoke-filled cantina in the lower levels where the music never stops
    and the bartender asks no questions. Booth curtains hide a dozen
    conversations the Empire would kill to overhear.
  atmosphere:
    lighting: dim
    noise_level: loud
    crowd_density: packed
    mood: tense_but_alive
    sensory_details:
      - "The hiss of cheap drinks being poured"
      - "Jizz-wailer band playing off-key in the corner"
      - "Smoke from death sticks curling around the overhead fans"
  time_variants:
    day:
      crowd_density: sparse
      mood: sleepy
      encounter_modifier: -1
    night:
      crowd_density: packed
      mood: dangerous
      encounter_modifier: +2
  points_of_interest:
    - id: poi-back_booth
      name: The back booth
      description: "A private booth with a curtain. Regulars know to knock twice."
      scene_types: [dialogue, investigation]
    - id: poi-cargo_hatch
      name: Cargo hatch behind the bar
      description: "Leads to the basement. The bartender pretends it doesn't exist."
      bypass_methods: [bribe, charm, sneak]
  services: [cantina, bounty_board, informant, safehouse]
  security:
    controlling_faction: hutt_cartel
    security_level: 15
    patrol_intensity: none
    inspection_chance: none
```

#### 2. Quests Need Deeper Consequence Modeling

**Current consequences:**
```yaml
consequences:
  reputation_rebel_alliance: '+10'
```

**What BioWare-grade consequences look like:**
```yaml
consequences:
  per_path:
    surgical_strike:
      reputation: { rebel_alliance: +20, galactic_empire: -15 }
      alignment: { light_dark: +1, paragon_renegade: +2 }
      world_mutations:
        - type: location_change
          target: loc-imperial_garrison
          change: { security_level: 20, controlling_faction: rebel_alliance }
        - type: npc_state
          target: npc-garrison_commander
          change: { status: captured, location: loc-yavin_base }
      companion_reactions:
        comp-reb-kessa: { delta: +3, reason: "Admires the precision" }
        comp-reb-jareth: { delta: -1, reason: "Wanted more aggression" }
      unlocks:
        - quest_id: quest_garrison_aftermath
        - rumor_id: rumor_empire_retaliation
      narrative_seeds:
        - "The garrison commander is now a prisoner who may trade secrets"
        - "Civilians are grateful but afraid of Imperial reprisal"
    full_assault:
      reputation: { rebel_alliance: +15, galactic_empire: -25, civilian: -10 }
      alignment: { light_dark: -2, paragon_renegade: -2 }
      world_mutations:
        - type: location_destroyed
          target: loc-imperial_garrison
        - type: npc_death
          target: npc-garrison_civilians
      companion_reactions:
        comp-reb-kessa: { delta: -4, reason: "Horrified by civilian cost" }
      narrative_seeds:
        - "The garrison is rubble. Smoke rises for days."
        - "Refugees stream out. Some curse the Rebellion."
```

#### 3. NPCs Need Relationship Webs

**Currently:** NPCs have `faction_id` and `knowledge.rumors/secrets`, but no explicit
relationships to other NPCs.

**What's needed:**
```yaml
# In npcs.yaml, per NPC
relationships:
  - npc_id: darth_vader
    type: fears
    intensity: high
    note: "Knows Vader is hunting Force-sensitives"
  - npc_id: mon_mothma
    type: loyal_to
    intensity: medium
    note: "Believes in the cause but hasn't met her"
  - npc_id: informant_drell
    type: owes_favor
    intensity: high
    note: "Drell saved their life on Ord Mantell"
```

This feeds the director's NPC agenda system and makes conversations feel interconnected
rather than siloed.

#### 4. Facts Need Categories and Temporal Scope

**Current:**
```yaml
- id: fact_001
  subject: Death Star
  predicate: was_destroyed_at
  object: Yavin
```

**What's needed:**
```yaml
- id: fact_001
  subject: Death Star
  predicate: was_destroyed_at
  object: Battle of Yavin
  category: historical_event  # historical_event | world_rule | character_fact | location_fact
  temporal_scope: { after: "0 ABY" }
  contradicts: [fact_death_star_operational]  # explicit contradiction tracking
  narrator_note: "This is public knowledge. Everyone knows."
  discoverable: false  # player already knows this
```

---

## Part 8: The Movie/Book Arc System

### How Arc Generation Works

When a player finishes an arc (or starts their first one), the system generates the
next "movie":

```
Inputs to Arc Generation:
├→ Era pack (Layer 1 — the full pool of entities)
├→ Player state (character, companions, alignment, psychological profile)
├→ Previous arc consequences (who survived, world mutations, faction shifts)
├→ Campaign metadata (scale, tone preferences, arc number)
└→ [Optional] Ingested lore context for canon grounding

    ↓ Cloud LLM Generation ↓

Arc Screenplay Output:
├→ arc_metadata:
│   ├→ title: "The Smuggler's Gambit"
│   ├→ arc_number: 1
│   ├→ tone: heist_thriller
│   ├→ opening_crawl: |
│   │     The Empire tightens its grip on the Outer Rim.
│   │     A lone smuggler with a dangerous past receives
│   │     an offer that could change the course of the war...
│   ├→ estimated_turns: 35-50
│   └→ act_structure:
│       ├→ act_1_setup:
│       │   ├→ description: "Player arrives at Ord Mantell, meets the crew"
│       │   ├→ key_npcs: [npc-karrde, npc-mara_jade]
│       │   ├→ key_locations: [loc-cantina, loc-karrde_compound]
│       │   └→ inciting_incident: "A dying smuggler hands over a data chip"
│       ├→ act_2_confrontation:
│       │   ├→ description: "The data chip reveals an Imperial convoy route"
│       │   ├→ midpoint_twist: "Mara Jade has her own agenda for the chip"
│       │   └→ escalation: "The Empire learns the chip is missing"
│       └→ act_3_resolution:
│           ├→ description: "The heist — intercept the convoy or sell the info"
│           ├→ climax_location: loc-imperial_convoy
│           └→ branching_endings:
│               ├→ heroic: "Intercept the convoy, free the prisoners"
│               ├→ mercenary: "Sell to the highest bidder"
│               └→ betrayal: "Trade the chip to the Empire for immunity"
│
├→ cast (this movie's NPCs):
│   ├→ npc-karrde:
│   │   ├→ arc_role: quest_giver
│   │   ├→ arc_agenda: "Wants the data chip for his own intelligence network"
│   │   └→ arc_relationship_to_player: employer (for now)
│   ├→ npc-mara_jade:
│   │   ├→ arc_role: wild_card
│   │   ├→ arc_agenda: "Serving the Emperor's final command"
│   │   └→ arc_relationship_to_player: uneasy_ally
│   └→ ... (6-10 more)
│
├→ locations (this movie's geography):
│   ├→ act_1: [loc-ord_mantell_port, loc-cantina, loc-karrde_compound]
│   ├→ act_2: [loc-myrkr_forest, loc-imperial_listening_post]
│   └→ act_3: [loc-imperial_convoy, loc-escape_point]
│
├→ quests (this movie's quest structure):
│   ├→ main_quest: quest-the_smugglers_gambit
│   │   ├→ stages: [receive_chip, decode_chip, plan_heist, execute_heist]
│   │   └→ branching_resolution_paths: [heroic, mercenary, betrayal]
│   └→ side_quests:
│       ├→ quest-mara_jades_secret (discover her hidden agenda)
│       └→ quest-karrdes_debt (help Karrde with a side problem for better terms)
│
├→ moments (this movie's emotional beats):
│   ├→ moment-mara_respect: { trigger: { complete: quest-mara_jades_secret, tone: paragon }, ... }
│   ├→ moment-karrde_warning: { trigger: { act: 2, alignment: { light_dark: { below: -10 } } }, ... }
│   └→ ... (6-8 more)
│
└→ arc_end_consequences:
    ├→ heroic_ending:
    │   ├→ npcs_affected: { npc-karrde: "respects you", npc-mara_jade: "owes you" }
    │   ├→ world_mutations: [imperial_convoy_destroyed, prisoners_freed]
    │   └→ next_arc_seeds: ["The Empire sends an Inquisitor to find you", "Freed prisoners join the Rebellion"]
    ├→ mercenary_ending:
    │   ├→ npcs_affected: { npc-karrde: "sees you as reliable", npc-mara_jade: "distrusts you" }
    │   └→ next_arc_seeds: ["Your reputation as a mercenary grows", "The prisoners' fate weighs on you"]
    └→ betrayal_ending:
        ├→ npcs_affected: { npc-karrde: "enemy", npc-mara_jade: "complex respect" }
        └→ next_arc_seeds: ["Karrde puts a bounty on you", "The Empire considers you an asset"]
```

### What Gets Generated Per Arc vs What's Reused

| Content | Per Arc? | Source |
|---------|----------|--------|
| Arc title, tone, opening crawl | **Yes, new** | Cloud LLM generates fresh |
| Act structure (3-act screenplay) | **Yes, new** | Cloud LLM generates from era pack + player state |
| NPC selection | **Reused from era pack** | Cloud LLM selects 8-12 from the pool |
| NPC arc roles and agendas | **Yes, new** | Cloud LLM tailors for this story |
| NPC base voice profiles | **Reused from era pack** | Static — personality doesn't change per arc |
| Location selection | **Reused from era pack** | Cloud LLM selects 4-6 from the pool |
| Location atmosphere adjustments | **Yes, new** | Cloud LLM may adjust mood/tone for arc |
| Main quest | **Yes, new** | Cloud LLM generates from quest seeds + arc structure |
| Side quests | **Mixed** | Some from era pack seeds, some new |
| Moments | **Yes, new** | Tailored to this arc's emotional beats |
| Items/equipment | **Reused from era pack** | Static pool |
| Factions | **Reused from era pack** | Goals may shift based on previous arc consequences |
| World facts | **Accumulated** | Base facts + mutations from previous arcs |

### The Career File: Cumulative Consequence Threading

Each arc adds to a growing **career file** — the complete history of the character's
journey. This is not just "what happened last arc" but "everything this character has
ever done." Like a character sheet in a tabletop campaign that's been running for years,
or the accumulated continuity of a long-running book series.

When generating the next arc, the Cloud LLM receives the full career file:

```yaml
# The character's career file — grows with every arc
career_file:
  character:
    name: "Kira Voss"
    class: smuggler
    species: twilek
    arc_count: 4
    career_turns_played: 162

  # Prologue consequences (always available — this is the origin)
  origin:
    prologue_title: "Last Run from Corellia"
    defining_choice: "Saved Renn, talked past Kael"
    departure_thread: "Headed to Ord Mantell"

  # Cumulative arc history (summarized, not raw)
  arc_history:
    - arc: 1
      title: "The Smuggler's Gambit"
      summary: "Stole an Imperial manifest; chose to free prisoners over profit"
      ending: heroic
      key_consequences: [imperial_convoy_destroyed, prisoners_freed]
    - arc: 2
      title: "Shadows Over Kessel"
      summary: "Betrayed by a contact; lost Renn to Imperial capture"
      ending: pyrrhic_victory
      key_consequences: [renn_voss_captured, kessel_mining_operation_exposed]
    - arc: 3
      title: "The Inquisitor's Trail"
      summary: "Hunted by an Inquisitor; discovered latent Force sensitivity"
      ending: narrow_escape
      key_consequences: [inquisitor_knows_player_face, force_training_begun]

  # Current state of ALL NPCs the character has ever interacted with
  npc_relationships:
    npc-karrde: { met_in: arc_1, current: trusted_ally, alive: true }
    npc-mara_jade: { met_in: arc_1, current: complex_respect, alive: true }
    npc-renn_voss: { met_in: prologue, current: captured, alive: true, location: imperial_prison }
    npc-lt_kael: { met_in: prologue, current: nemesis, alive: true, promoted: true }
    npc-inquisitor_vex: { met_in: arc_3, current: active_hunter, alive: true }

  # Cumulative world state
  world_mutations:
    - imperial_convoy_destroyed (arc 1)
    - kessel_mining_operation_exposed (arc 2)
    - inquisitor_dispatched_to_outer_rim (arc 3)
  faction_reputation:
    rebel_alliance: 45
    galactic_empire: -60
    underworld: 30

  # Player state
  player_state:
    alignment: { light_dark: 18, paragon_renegade: 5 }
    stress: 6
    active_trauma: [loss_of_mentor, hunted]
    companion_loyalty: { comp-reb-kessa: LOYAL, comp-reb-jareth: TRUSTED }

  # Open narrative threads (unresolved from ANY arc)
  open_threads:
    - "Renn Voss is still in an Imperial prison" (from arc 2)
    - "The Inquisitor knows your face" (from arc 3)
    - "Your Force sensitivity is untrained and dangerous" (from arc 3)
    - "Lt. Kael has been promoted and assigned to find you" (from prologue, escalated)
    - "Mara Jade's true mission remains unresolved" (from arc 1)
```

The Cloud LLM uses the career file to generate the next arc as a natural continuation.
It can:
- **Resolve long-standing threads** (Arc 4 might be about rescuing Renn)
- **Escalate simmering conflicts** (Lt. Kael, now a Commander, closes in)
- **Introduce new threats** informed by accumulated reputation
- **Pay off character growth** (the untrained Force sensitivity becomes central)
- **Bring back characters from earlier arcs** for callbacks and payoffs

The longer the career, the richer the source material for the next arc. Like a book
series that gets better as it goes because the author has more history to draw from.

---

## Part 9: The BioWare Question — DnD Mechanics + Deep Narrative

### My Honest Assessment

You're targeting the intersection of two things that are historically hard to combine:

1. **DnD:** Mechanical depth, character builds, tactical combat, progression systems
2. **BioWare:** Companion loyalty, branching story arcs, moral consequences, emotional beats

Most games pick one. Baldur's Gate 3 is the rare exception that does both, and it took
6 years and 400+ developers.

### What Storyteller-V2 Should Optimize For

**Lean toward BioWare, not DnD.** Here's why:

1. **Your engine is narrative-first.** The resolution agent, the narrator, the 4-tone
   dialogue wheel — these are narrative tools. Adding deep tactical combat would fight
   the architecture.

2. **LLMs are bad at tactical combat.** An LLM can't reliably adjudicate a grid-based
   combat with positioning, flanking, and opportunity attacks. But it's excellent at
   "you succeeded with a complication — the guard lets you through but radios ahead."

3. **Stats-in-the-background is the right call.** CYOA players don't want to see damage
   calculations. They want to feel that their character build matters through the
   narrative. "Your high Cunning lets you spot the hidden passage" is more satisfying
   than "+3 to Perception check."

4. **The psychological system is your differentiator.** BioWare never tracked stress,
   trauma, and mood. This is where you can go deeper than they did. Imagine: a companion
   confrontation triggered not by a plot flag but because your stress is at 8 and your
   companion is WARY — they're genuinely worried about you.

### The Experience You Should Target

**Think: KOTOR meets Disco Elysium meets Mass Effect 2.**

- **KOTOR:** 4-tone dialogue wheel, companion influence, light/dark alignment
- **Disco Elysium:** Internal dialogue, psychological profiling, skills that "speak to you"
- **Mass Effect 2:** Loyalty missions, the Normandy as a hub, suicide mission stakes

### Specific Recommendations for BioWare-Grade Storytelling

#### 1. Add a "Ship/Hub" System (The Ebon Hawk / Normandy)

Between missions, the player returns to a hub location where they can:
- Talk to companions (unlocks banter, loyalty quests)
- Check the news feed (already exists as ME-style briefing)
- Review the quest log
- Access the codex
- Plan the next move

This is cheap to implement — it's just a special location with companion conversation
triggers. But it transforms the pacing from "quest → quest → quest" into "quest → breathe
→ deepen relationships → quest."

```yaml
# In era.yaml
hub_location:
  id: loc-ebon_hawk  # or loc-rebel_base or loc-player_ship
  type: player_hub
  allows:
    - companion_conversations
    - news_review
    - quest_planning
    - rest (stress recovery: -2 per rest)
```

#### 2. Implement "Downtime Turns"

A turn where the player explicitly chooses to rest, talk to companions, or reflect.
The mechanic: skip world time forward, recover stress, trigger companion events.

This is how BioWare games created emotional beats — not during combat, but in the quiet
moments between missions.

#### 3. Make Companion Personal Quests Multi-Stage Arcs

**Current:** `personal_quest_id` points to a single quest.

**BioWare-grade:** Each companion has a 3-stage personal arc:
1. **Introduction** (unlock at ALLY) — Companion reveals something about their past
2. **Crisis** (unlock at TRUSTED) — A threat from their past forces action
3. **Resolution** (unlock at LOYAL) — The player helps them confront it; outcome affects
   the companion permanently (and potentially the ending)

This maps directly to the existing quest system — just chain 3 quests with affinity-gated
entry conditions.

#### 4. Add "Moment" Events

Small, non-quest narrative beats that fire based on conditions:
- Companion comments on the player's alignment shift
- NPC reacts differently because the player's faction reputation changed
- A callback to an earlier choice surfaces organically

```yaml
moments:
  - id: moment_kessa_alignment
    trigger:
      alignment: { light_dark: { below: -20 } }
      companion_present: comp-reb-kessa
      companion_loyalty: { min: ALLY }
    text: >
      Kessa pulls you aside after the others have gone.
      "I've noticed something changing in you. The choices you're making...
      they're not the person I signed on with."
    effects:
      companion_affinity: { comp-reb-kessa: -2 }
      stress_delta: +1
      thread_seed: "Kessa questions the player's moral direction"
```

#### 5. Add a "Codex" Discovery System

When the player encounters something tied to ingested lore, unlock a codex entry:

```yaml
codex_entries:
  - id: codex-death_star
    title: "The Death Star"
    category: technology
    discoverable_via:
      - chunk_section_kind: lore
      - chunk_characters_contains: "Death Star"
    short_text: "The Empire's planet-killing battle station..."
    full_text_chunk_ids: ["chunk_abc123", "chunk_def456"]
```

This creates the feeling of a living encyclopedia that grows as you play — exactly like
Mass Effect's codex or Dragon Age's journal.

---

## Part 10: Enriching the Era Pack — Proposed Schema V3

### New Files to Add

| File | Purpose |
|------|---------|
| `stat_schema.yaml` | Universe-specific stat definitions |
| `items.yaml` | Equipment, consumables, key items with mechanical effects |
| `moments.yaml` | Triggered narrative micro-events |
| `codex.yaml` | Discoverable lore entries |
| `relationships.yaml` | NPC-to-NPC relationship web |
| `encounter_tables.yaml` | Global + per-location encounter definitions |

### Enhanced `era.yaml` Root

```yaml
era_id: REBELLION
schema_version: 3
file_index:
  era: era.yaml
  stat_schema: stat_schema.yaml      # NEW
  locations: locations.yaml
  npcs: npcs.yaml
  factions: factions.yaml
  backgrounds: backgrounds.yaml
  namebanks: namebanks.yaml
  quests: quests.yaml
  companions: companions.yaml
  events: events.yaml
  rumors: rumors.yaml
  meters: meters.yaml
  facts: facts.yaml
  items: items.yaml                  # NEW
  moments: moments.yaml             # NEW
  codex: codex.yaml                  # NEW
  relationships: relationships.yaml  # NEW

# NEW: Hub/downtime configuration
hub_location: loc-player_ship
downtime_rules:
  stress_recovery_per_rest: 2
  companion_conversation_limit: 2
  triggers_world_tick: true

# NEW: Campaign pacing overrides
pacing:
  suggested_arc_length: 35-50  # turns per movie/book arc
  quest_density: medium         # low/medium/high
  combat_frequency: moderate    # rare/moderate/frequent
```

### Enhanced Location Model (additions to existing)

```yaml
# Additions to EraLocation
atmosphere:
  lighting: str           # bright, dim, dark, flickering, natural
  noise_level: str        # silent, quiet, moderate, loud, deafening
  crowd_density: str      # empty, sparse, moderate, packed, crushing
  mood: str               # peaceful, tense, festive, dangerous, eerie
  sensory_details: list[str]  # 2-4 evocative one-liners

time_variants:
  day: { crowd_density, mood, encounter_modifier }
  night: { crowd_density, mood, encounter_modifier }

points_of_interest:
  - id: str
    name: str
    description: str
    scene_types: list[str]
    bypass_methods: list[str]  # optional, for hidden/restricted POIs
```

### New Items Model

```yaml
items:
  - id: item-dl44-blaster
    name: DL-44 Heavy Blaster Pistol
    type: weapon          # weapon, armor, consumable, key_item, tool
    rarity: common        # common, uncommon, rare, legendary
    description: "Han Solo's weapon of choice. Reliable and powerful."
    mechanical_effects:
      - stat_bonus: { physique: 1 }  # for ATTACK actions
      - difficulty_modifier: -1       # reduce band by 1
    value: 500            # credits
    tags: [ranged, blaster, one_handed]
    discoverable_at: [loc-arms_dealer, loc-smuggler_den]
```

---

## Part 11: Implementation Roadmap

### Phase 0: Character Creation & Prologue System (The First Impression)

The player's first experience defines whether they keep playing. Make it cinematic.

1. Add `species.yaml` to era pack schema — Cloud LLM generates species catalog with
   cultural notes, stat affinities, appearance traits, and narrative hooks
2. Elevate `EraBackground` to class/archetype with `starting_abilities`, `story_archetype`,
   `prologue_scenario`, and `narrative_tone` fields
3. Expand question chains from 2-3 to 5-7 per class — add `alignment_nudge`, `psych_seed`,
   `npc_seed`, `item_seed`, and `quest_seed` to `BackgroundChoiceEffect`
4. Build `PrologueScreenplayGenerator` — Cloud LLM generates a per-class origin scenario
   (5-10 turns, mini-arc: SETUP → INCITING_INCIDENT → DEPARTURE)
5. Build prologue turn loop that runs the existing engine in a constrained mode
   (simplified world sim, 2-4 NPCs, single location)
6. Build prologue → Arc 1 handoff: `origin_context` manifest captures prologue consequences
   and feeds them into `ArcScreenplayGenerator`

**Effort:** ~1-2 weeks. High-impact: this IS the player's first impression of the game.

### Phase 1: Era Pack Enrichment via Cloud LLM (Highest Impact, Lowest Risk)

Use a Cloud LLM to regenerate/enrich existing era packs with the V3 schema:

1. Generate `atmosphere` and `points_of_interest` for all existing locations
2. Generate `per_path` consequences for all existing quests
3. Generate NPC `relationships` webs
4. Generate `items.yaml` for each era pack
5. Generate `moments.yaml` for companion-triggered events
6. Generate `codex.yaml` discoverable lore entries
7. Generate `species.yaml` and enriched class/archetype definitions with prologue scenarios
8. Generate deep question chains (5-7 per class) with rich branching and effects
9. Human review and commit all generated content

**Effort:** ~1-2 days per era pack (Cloud LLM does the heavy lifting, human curates).

### Phase 2: Arc Screenplay Generator (The Movie/Book Engine)

1. Build `ArcScreenplayGenerator` — Cloud LLM generates a complete arc screenplay
   from era pack + player state + previous arc consequences
2. Define the screenplay schema (act structure, cast, locations, quests, moments)
3. Build `ArcConsequenceTracker` — captures arc-end state for sequel generation
4. Integrate with existing `CampaignArchitect` and `ArcWeaver`
5. Build the "opening crawl" generation for each new arc

**Effort:** ~1-2 weeks. This is the signature feature — what makes every playthrough
feel like a movie.

### Phase 3: Ingestion Simplification

1. Remove entity extraction ambitions from ingestion pipeline
2. Keep RAG-grade chunking as-is (it's good)
3. Add Cloud LLM metadata enrichment pass (narrative_role, spoiler_tier, canon_weight)
   as an optional one-time step per source book
4. Ensure 4-lane style retrieval works with enriched metadata

**Effort:** ~2-3 days. Mostly simplification, not new code.

### Phase 4: Gameplay Depth

1. Add hub/downtime system (special location type + rest mechanic)
2. Add codex discovery (link lore chunks to unlockable entries)
3. Add `moments.yaml` processing in the turn pipeline
4. Expand equipment to have mechanical weight (difficulty modifiers)

**Effort:** ~1-2 weeks. Some engine changes needed (new node in LangGraph pipeline).

### Phase 5: Multi-Universe Validation

1. Build a second era pack for a non-Star-Wars setting (LOTR, cyberpunk, or original)
   — generated entirely via Cloud LLM from a prompt
2. Validate `stat_schema.yaml` portability
3. Validate `bypass_methods` and `services` extensibility
4. Validate the arc screenplay generator works for the new universe
5. Write a `setting_pack_guide.md` for community contributors

**Effort:** ~1 week. This proves the architecture works across universes.

---

## Part 12: Setting Up a New Universe — The Full Flow

With the hybrid approach, spinning up a new universe looks like this:

### Step 1: Cloud LLM Generates the Era Pack (Layer 1)

```
Prompt: "Generate a complete Rebellion-era Star Wars era pack conforming to
         the V3 schema. Include 30+ NPCs, 15+ locations, 6+ factions..."
    ↓
Cloud LLM outputs structured YAML
    ↓
Human reviews, curates, commits to data/static/era_packs/rebellion/
```

**Time: Hours, not weeks.** Compare to hand-authoring 12+ YAML files.

### Step 2: Ingest Source Material for Narrative Grounding (Optional)

```
python -m ingestion.ingest --input ./data/lore/rebellion/ --era rebellion
    ↓
Source books → chunks → embeddings → LanceDB
    ↓
[Optional] Cloud LLM enriches chunk metadata (one-time pass)
```

**Time: Minutes per source book.** Only needed for canon-faithful universes.

### Step 3: Character Creation (MMO-Style)

```
Player chooses era
    ↓
Species selection (Twi'lek? Human? Wookiee?)
    ↓
Class/archetype selection (Smuggler? Force Exile? Bounty Hunter?)
    ↓
Deep question chain (5-7 narrative choices that shape who you are)
    ↓
Name, gender, appearance
    ↓
Character sheet generated (stats from class + question bonuses)
```

### Step 4: Prologue — Play Your Origin Story

```
PrologueScreenplayGenerator produces origin scenario from:
    class + question answers + era pack
    ↓
"Prologue: Last Run from Corellia" (5-10 turns)
    ↓
Player plays through origin: meets key NPCs, faces first choice,
    experiences the inciting incident
    ↓
Prologue consequences captured:
    NPC relationships, moral choices, items, departure thread
```

### Step 5: Arc 1 Generated — First Movie/Book

```
ArcScreenplayGenerator receives:
    era pack + prologue consequences + player state
    ↓
"Episode I: The Smuggler's Gambit" — opening crawl, cast, locations, quests
    ↓
Opening crawl references what happened in prologue:
    "Fleeing Corellia after a job gone wrong..."
    ↓
Gameplay begins
```

### Step 6: Gameplay — Engine + RAG (Layer 3)

```
Player makes choices → Resolution → World sim → Narrator
    ↓
RAG retrieves source-faithful prose for narrator grounding
    ↓
Moments fire based on conditions
    ↓
Arc structure guides pacing (acts, midpoint, climax)
```

### Step 7: Arc Ends — Consequences Captured → Next Movie

```
Player reaches arc climax → Resolution
    ↓
ArcConsequenceTracker captures: NPC states, world mutations, faction shifts
    ↓
Hub/downtime interlude (breathe, talk to companions, reflect)
    ↓
ArcScreenplayGenerator produces Arc 2 from consequences + era pack
    ↓
"Episode II: Shadows Over Kessel" begins
```

### The Complete Player Journey

```
Character Creation (species, class, 5-7 narrative questions)
    ↓
Prologue: "Last Run from Corellia" (5-10 turns — playable origin)
    ↓
Arc 1: "The Smuggler's Gambit" (35-50 turns)
    ↓
Hub/Downtime interlude (companions, rest, codex, planning)
    ↓
Arc 2: "Shadows Over Kessel" (35-50 turns)
    ↓
Hub/Downtime interlude
    ↓
Arc 3: "The Inquisitor's Trail" (35-50 turns)
    ↓
Hub/Downtime interlude
    ↓
...as many arcs as the character's career demands...
    ↓
Arc N: "One Last Run" — when the player decides, or the narrative converges
```

**There is no predetermined end.** The career continues as long as the player wants.
Each arc's screenplay is richer than the last because the career file grows — more
NPCs, more history, more threads to weave. Like a book series that improves as the
author accumulates lore.

---

## Part 13: Final Opinion

### Where You Are

You've built something genuinely impressive. The narrative dice system, the BioWare-grade
companion mechanics, the deterministic world sim, the 4-tone dialogue wheel, the
psychological profiling — these are systems that AAA studios build with teams of dozens.
You've done it with a LangGraph pipeline and local LLMs.

### What Would Transform It

The three highest-impact changes, in order:

1. **Character creation + playable prologue.** The player's first 15 minutes define
   whether they keep playing. An MMO-grade character creator (species, class, deep
   narrative questions) followed by a playable origin story makes the player *care*
   about their character before the first arc even begins. This is Phase 0 because
   nothing else matters if the player doesn't feel invested from turn 1.

2. **The movie/book arc system.** Right now, campaigns are open-ended. The arc
   generator transforms them into structured cinematic experiences where each
   playthrough feels authored — with a title, an opening crawl, a three-act
   structure, and consequences that thread into sequels. This is what turns "a game
   engine" into "an experience."

3. **Cloud LLM era pack generation.** This removes the hand-authoring bottleneck and
   makes it possible to spin up any universe in hours. Combined with ingestion for
   RAG grounding, you get the best of both worlds: structured gameplay data from
   Cloud LLM + source-faithful narrator prose from ingestion.

### The BioWare Standard

The old BioWare games (KOTOR, Mass Effect 2, Dragon Age: Origins) were great not because
of combat mechanics. They were great because:

1. **You became your character from the first moment** — the prologue system delivers this
2. **Every companion felt like a person** — you have this (voice profiles + loyalty arcs)
3. **Every choice echoed forward** — the arc consequence system delivers this
4. **The quiet moments mattered** — you need the hub/downtime system
5. **The world reacted to you** — you have the faction sim + moments/callbacks
6. **You could lose people** — companion departure/death on critical failures adds
   real stakes
7. **Each game felt like a movie** — the arc screenplay system delivers this

You're closer than you think. The engine is built. Now give it the character creation
experience, the playable prologue, the movie/book arc system, and feed it richer data
via Cloud LLM. Let ingestion ground the narrator in source material. It will sing.
