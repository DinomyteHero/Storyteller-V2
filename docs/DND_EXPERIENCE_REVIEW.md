# DnD Experience Review: How Close Are We?

## Executive Summary

Storyteller-V2 is **surprisingly close** to a fully immersive DnD-like experience with
stats hidden behind a narrative CYOA interface. The bones are strong — you have a
narrative dice system, companion loyalty, faction reputation, a living world sim, quest
branching, and a 4-stage Hero's Journey arc engine. What's missing isn't the engine;
it's the **data density** and **ingestion-to-gameplay bridge** that would make the world
feel as deep as a Baldur's Gate or KOTOR campaign.

**Score: ~70% of the way to the vision.** The remaining 30% is almost entirely about
enriching the data layer — not rewriting the engine.

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
| **Ingestion doesn't auto-populate data packs** | Books go into vector DB, but NPCs/locations/factions/quests aren't extracted | High (but highest value) |
| **No procedural quest generation** | All quests are hand-authored in YAML; can't generate from ingested lore | Medium-High |
| **Travel is flat** | Travel links exist but there are no random encounters, fuel costs, or journey events | Low |
| **No "camp" or downtime system** | BioWare games have the Normandy/Ebon Hawk; we have no party hub with companion conversations | Low |

---

## Part 2: How Ingestion Works Now

### Current Pipeline

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
[Optional] LLM tagger (entities, timeline, summary, injection risk)
    ↓
Embed (sentence-transformers/all-MiniLM-L6-v2, 384-dim)
    ↓
Store in LanceDB → Write manifest
```

### What Metadata Gets Captured

Per-chunk: `era`, `setting_id`, `period_id`, `planet`, `faction`, `doc_type`, `section_kind`,
`characters`, `related_npcs`, `source_type`, `book_title`, `chapter`.

Optional (LLM tagger): `entities` (characters, factions, planets, items), `timeline`
(era, start, end, confidence), `summary_1s`, `injection_risk`.

### The Problem

The ingestion pipeline is optimized for **RAG retrieval** — getting the right text chunks
into the narrator's context window at the right time. It does this well.

But it does **nothing to populate the gameplay layer**. When you ingest the Thrawn Trilogy,
the system learns that "Thrawn" appears in text chunks. It does NOT learn:

- Thrawn is an NPC with Intellect 9, Cunning 8, voice: cold analytical
- The Chimaera is a Star Destroyer you could board
- Myrkr is a location with Force-blocking ysalamiri (unique mechanic)
- Karrde's organization is a faction with specific goals and resources
- There's a quest-worthy scenario about infiltrating Wayland

All of that currently requires **hand-authoring YAML** in the era pack. That's the bottleneck.

---

## Part 3: Should We Change the Ingestion Process?

**Yes, but not by replacing it — by adding a second pass.**

### Proposal: Two-Phase Ingestion

**Phase 1 (existing):** RAG-grade chunking. Keep exactly as-is. This feeds the narrator
and director their contextual lore. It's good.

**Phase 2 (new): Entity Extraction → Data Pack Seeding**

After Phase 1 completes, run a structured extraction pass over the ingested chunks:

```
Phase 1 output (lore_chunks in LanceDB)
    ↓
LLM Extraction Pass (structured JSON output)
    ├→ NPCs: name, species, faction, archetype, traits, voice profile, locations
    ├→ Locations: name, region, planet, services, security, atmosphere, sensory details
    ├→ Factions: name, goals, resources, relationships, territory
    ├→ Items/Equipment: name, type, rarity, mechanical effect
    ├→ Quest Seeds: situation, stakes, key NPCs, locations, branching options
    ├→ World Facts: canonical truths the narrator must respect
    ├→ Rumors: things NPCs might whisper about
    └→ Relationship Graph: who knows whom, who opposes whom
    ↓
Merge into era pack YAML (with human review/override)
    ↓
Validate against era_pack_models.py schemas
```

### Why This Works

1. **Phase 1 is fast and cheap** — no LLM needed (except optional tagger)
2. **Phase 2 is expensive but one-time** — run it once per source book, review output, commit
3. **Human stays in the loop** — auto-extracted NPCs/locations are drafts, not final
4. **Existing validation catches errors** — Pydantic models enforce referential integrity

### Implementation Sketch

```python
# New: ingestion/extract_entities.py
def extract_npcs_from_chunks(chunks: list[dict], era_pack: EraPack) -> list[EraNpcEntry]:
    """Run LLM extraction over lore chunks to identify NPCs.

    Deduplicates against existing era pack anchors/rotating NPCs.
    Returns draft NPC entries for human review.
    """

def extract_locations_from_chunks(chunks: list[dict], era_pack: EraPack) -> list[EraLocation]:
    """Extract locations with atmosphere, services, and security from lore."""

def extract_quest_seeds(chunks: list[dict], era_pack: EraPack) -> list[EraQuest]:
    """Identify quest-worthy scenarios from narrative content."""
```

---

## Part 4: How to Adapt for Any Universe

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

## Part 5: Era Pack Improvements

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
  # ... existing fields
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

## Part 6: Populating Data Packs via Ingestion and Campaign Start

### Can We Auto-Populate Data Packs from Ingestion?

**Yes, and this is the highest-value improvement you can make.**

### Strategy: Three-Tier Data Population

#### Tier 1: Ingestion-Time Extraction (One-Time, Per Source Book)

When ingesting a new source book, run a structured extraction pass:

```bash
python -m ingestion.extract_entities \
  --input ./data/lore/rebellion \
  --era-pack rebellion \
  --output ./data/static/era_packs/rebellion/drafts/ \
  --extract npcs,locations,factions,items,quest_seeds,facts
```

This produces **draft YAML files** that a human reviews before merging into the era pack.
The LLM extracts structured data from the lore chunks, deduplicates against existing
era pack entries, and fills in the full schema (voice profiles, levers, spawn rules).

**Cost:** ~$2-5 per sourcebook using a local 8B model. One-time.

**Output quality:** 70-80% usable as-is, 20-30% needs human editing. But even the 70%
saves hundreds of hours of manual YAML authoring.

#### Tier 2: Campaign-Start Generation (Per Campaign, Automated)

When a new campaign starts, the `CampaignArchitect` already generates some content.
Expand this to:

1. **Select subset from era pack** based on campaign scale:
   - SMALL: 3 locations, 5 NPCs, 2 quests
   - EPIC: 12 locations, 24 NPCs, 8 quests

2. **Procedurally enrich selected content** using the era pack as a template:
   - Generate unique variants of template NPCs (names from namebanks, randomized traits)
   - Place NPCs at locations based on faction alignment
   - Seed initial rumors based on active faction goals
   - Generate the opening scenario from quest entry conditions

3. **Build the relationship web** from faction data:
   - Allies share rumors
   - Enemies have conflicting goals
   - NPCs in the same faction know each other

This is cheap (one architect call + deterministic placement) and makes each campaign
feel unique even with the same era pack.

#### Tier 3: Runtime Discovery (During Play, On-Demand)

As the player explores, the system can:

1. **Spawn template NPCs** at locations based on encounter tables (already exists)
2. **Generate new rumors** from faction simulation (already exists)
3. **Unlock quest hooks** when entry conditions are met (already exists)
4. **Discover lore entries** — NEW: when RAG retrieves a lore chunk that matches a
   "discoverable fact", add it to a player-facing codex

This tier is mostly in place. The main addition is the codex/discovery system.

---

## Part 7: The BioWare Question — DnD Mechanics + Deep Narrative

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

## Part 8: Enriching the Era Pack — Proposed Schema V3

### New Files to Add

| File | Purpose |
|------|---------|
| `stat_schema.yaml` | Universe-specific stat definitions |
| `items.yaml` | Equipment, consumables, key items with mechanical effects |
| `moments.yaml` | Triggered narrative micro-events |
| `codex.yaml` | Discoverable lore entries |
| `relationships.yaml` | NPC-to-NPC relationship web |
| `encounter_tables.yaml` | Global + per-location encounter definitions |
| `atmosphere.yaml` | Sensory details and environmental storytelling per location |

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
  suggested_arc_length: 40-60  # turns
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

## Part 9: Implementation Roadmap

### Phase 1: Enrich the Data Layer (Highest Impact, Lowest Risk)

1. Add `atmosphere` and `points_of_interest` to existing locations
2. Add `per_path` consequences to existing quests
3. Add NPC `relationships` to existing NPCs
4. Create `items.yaml` for each era pack
5. Create `moments.yaml` for companion-triggered events

**Effort:** ~2-3 days per era pack. No engine changes needed — just richer YAML.

### Phase 2: Ingestion-to-Data-Pack Bridge

1. Build `ingestion/extract_entities.py` — LLM extraction from lore chunks
2. Add CLI command: `python -m storyteller extract --era rebellion --output drafts/`
3. Build merge tool: `python -m storyteller merge-drafts --era rebellion --review`
4. Add validation: ensure extracted entities match `era_pack_models.py` schemas

**Effort:** ~1 week. This is the highest-value engineering work.

### Phase 3: Campaign-Start Enrichment

1. Expand `CampaignArchitect` to build relationship webs from faction data
2. Add procedural NPC variant generation from templates + namebanks
3. Seed initial rumors from faction goals
4. Generate opening scenario from quest entry conditions

**Effort:** ~3-4 days. Mostly expanding existing architect code.

### Phase 4: Gameplay Depth

1. Add hub/downtime system (special location type + rest mechanic)
2. Add codex discovery (link lore chunks to unlockable entries)
3. Add `moments.yaml` processing in the turn pipeline
4. Expand equipment to have mechanical weight (difficulty modifiers)

**Effort:** ~1-2 weeks. Some engine changes needed (new node in LangGraph pipeline).

### Phase 5: Multi-Universe Validation

1. Build a second era pack for a non-Star-Wars setting (LOTR, cyberpunk, or original)
2. Validate `stat_schema.yaml` portability
3. Validate `bypass_methods` and `services` extensibility
4. Write a `setting_pack_guide.md` for community contributors

**Effort:** ~1 week. This proves the architecture works across universes.

---

## Part 10: Final Opinion

### Where You Are

You've built something genuinely impressive. The narrative dice system, the BioWare-grade
companion mechanics, the deterministic world sim, the 4-tone dialogue wheel, the
psychological profiling — these are systems that AAA studios build with teams of dozens.
You've done it with a LangGraph pipeline and local LLMs.

### What Would Transform It

The single highest-impact change is **closing the gap between ingested lore and gameplay
data**. Right now, you have a library (the vector store) and a game board (the era pack),
and they're populated separately. The moment ingestion can seed the game board — even as
rough drafts — you unlock the ability to spin up a campaign in any universe from source
material alone.

### The BioWare Standard

The old BioWare games (KOTOR, Mass Effect 2, Dragon Age: Origins) were great not because
of combat mechanics. They were great because:

1. **Every companion felt like a person** — you have this (voice profiles + loyalty arcs)
2. **Every choice echoed forward** — you're partway here (alignment + faction rep), but
   need deeper consequence modeling
3. **The quiet moments mattered** — you need the hub/downtime system
4. **The world reacted to you** — you have the faction sim, but need moments/callbacks
5. **You could lose people** — companion departure/death on critical failures would add
   real stakes

You're closer than you think. The engine is built. Now feed it richer data and it will
sing.
