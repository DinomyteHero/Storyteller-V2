# Era Pack Schema Reference (V2.20)

**Version:** 2.20
**Last Updated:** February 2026
**Status:** Canonical

This document defines the complete schema for Storyteller AI era pack YAML files, based on the Pydantic models in `backend/app/world/era_pack_models.py`.

---

## Table of Contents

1. [Overview](#overview)
2. [File Structure](#file-structure)
3. [era.yaml](#erayaml)
4. [factions.yaml](#factionsyaml)
5. [locations.yaml](#locationsyaml)
6. [npcs.yaml](#npcsyaml)
7. [backgrounds.yaml](#backgroundsyaml)
8. [namebanks.yaml](#namebbanksyaml)
9. [quests.yaml](#questsyaml)
10. [events.yaml](#eventsyaml)
11. [rumors.yaml](#rumorsyaml)
12. [meters.yaml](#metersyaml)
13. [facts.yaml](#factsyaml)
14. [companions.yaml](#companionsyaml)
15. [Common Enums](#common-enums)
16. [Validation Rules](#validation-rules)
17. [Common Gotchas](#common-gotchas)

---

## Overview

An era pack is a collection of YAML files defining all content for a specific Star Wars time period. Era packs are loaded from `data/static/era_packs/{era_id}/`.

**Supported Eras (V2.20):**
- `REBELLION` - Age of Rebellion (0-4 ABY)
- `NEW_REPUBLIC` - New Republic (5-19 ABY)
- `NEW_JEDI_ORDER` - New Jedi Order (25-29 ABY)
- `LEGACY` - Legacy Era (130-138 ABY)
- `DARK_TIMES` - The Dark Times (19-0 BBY)
- `KOTOR` - Knights of the Old Republic (~3954 BBY)

---

## File Structure

Each era pack directory must contain:

```text
data/static/era_packs/{era_id}/
├── era.yaml              # Required: era metadata, file index, start locations
├── factions.yaml         # Required: faction definitions
├── locations.yaml        # Required: location affordances
├── npcs.yaml             # Required: NPCs (anchors, rotating, templates)
├── backgrounds.yaml      # Required: character creation backgrounds
├── namebanks.yaml        # Required: name generation pools
├── quests.yaml           # Required: quest structures
├── events.yaml           # Required: world events
├── rumors.yaml           # Required: rumor pool
├── meters.yaml           # Required: faction reputation mechanics
├── facts.yaml            # Required: knowledge base entries
└── companions.yaml       # Required: era-specific companions
```text

---

## era.yaml

**Top-level keys:**

```yaml
era_id: REBELLION                    # Required: Unique era identifier (UPPERCASE)
schema_version: 2                    # Required: Always 2 for V2.20
style_ref: data/style/rebellion_style.md  # Optional: Path to style guide

file_index:                          # Required: Maps section names to filenames
  era: era.yaml
  locations: locations.yaml
  npcs: npcs.yaml
  factions: factions.yaml
  backgrounds: backgrounds.yaml
  namebanks: namebanks.yaml
  quests: quests.yaml
  events: events.yaml
  rumors: rumors.yaml
  meters: meters.yaml
  facts: facts.yaml
  companions: companions.yaml

start_location_pool:                 # Required: Safe starting locations for new campaigns
  - loc-cantina
  - loc-bazaar_market
  - loc-safe_house

global_event_templates: []           # Optional: Global event IDs
travel_graph: []                     # Optional: Era-level travel links
default_scene_pacing: {}             # Optional: Scene pacing overrides

metadata:                            # Required: Human-readable era info
  display_name: Age of Rebellion
  time_period: 0–4 ABY (Legends)
  calendar_note: After the Battle of Yavin...
  summary: |
    The galaxy lives under the boot of the Galactic Empire...
  tone: Gritty hope; underdog resistance; imperial oppression
  key_conflicts:
    - Alliance vs. Empire
    - Jedi legacy vs. Imperial purge

  themes:
    - Restoration of the Republic
    - Sacrifice and compartmentalization
```text

**Required Fields:**
- `era_id` (string, UPPERCASE)
- `schema_version` (int, always 2)
- `file_index` (dict mapping section → filename)
- `start_location_pool` (list of location_ids)
- `metadata.display_name` (string)
- `metadata.time_period` (string)
- `metadata.summary` (string)

---

## factions.yaml

**Structure:**

```yaml
factions:
  - id: rebellion                    # Required: Unique faction ID

    name: Alliance to Restore the Republic  # Required
    tags:                            # Optional: Faction tags
      - military
      - rebellion

    home_locations:                  # Optional: Faction bases (must exist in locations.yaml)
      - loc-yavin_base
      - loc-hoth_base

    goals:                           # Optional: Faction objectives
      - Overthrow the Empire
      - Restore the Republic

    hostility_matrix:                # Optional: Faction relationships
      empire: -80                    # Hostile (-100 to 100)
      hutts: -20                     # Distrustful
    metadata: {}                     # Optional: Extension point
```text

**Required Fields:**
- `id` (string)
- `name` (string)

**Validation:**
- `home_locations` must reference existing location IDs (warning in lenient mode)
- `hostility_matrix` keys should reference other faction IDs

---

## locations.yaml

**Structure:**

```yaml
locations:
  - id: loc-cantina                  # Required: Unique location ID

    name: Mos Eisley Cantina         # Required
    planet: Tatooine                 # Optional: Planet name
    region: Outer Rim                # Optional: Region
    description: |                   # Optional: 1-2 sentence description
      A crowded spaceport cantina frequented by smugglers, bounty hunters,
      and spacers of all kinds.
    parent_id: loc-mos_eisley        # Optional: Parent location ID
    threat_level: moderate           # Optional: low|moderate|high|extreme
    tags:                            # Optional: Location tags
      - cantina
      - public
      - criminal

    controlling_factions:            # Optional: Faction IDs
      - hutts

    keywords:                        # Optional: RAG keywords
      - cantina
      - smugglers
      - spaceport

    scene_types:                     # Optional: Allowed scene types
      - dialogue
      - stealth
      - combat

    security:                        # Optional: Security config
      controlling_faction: hutts     # Optional: Faction ID
      security_level: 30             # 0-100 (default: 50)
      patrol_intensity: low          # low|medium|high|constant|none
      inspection_chance: low         # low|medium|high

    services:                        # Optional: Available services
      - cantina
      - market
      - transport

    access_points:                   # Optional: Entry/exit points
      - id: cantina_front_door

        type: door                   # door|hatch|vent|window|etc.
        visibility: public           # public|restricted|hidden|secret
        bypass_methods:              # How to bypass if locked
          - violence
          - bribe
          - charm

    encounter_table:                 # Optional: Random NPCs
      - template_id: cantina_patron

        weight: 10
        conditions: null             # Optional: Spawn conditions
      - template_id: bounty_hunter

        weight: 2

    travel_links:                    # Optional: Connected locations
      - to_location_id: loc-spaceport

        method: travel               # Optional: travel|fast_travel|hyperspace
        risk: low                    # Optional: low|medium|high
        cost: 50                     # Optional: Credit cost
      - loc-docking_bay              # Shorthand: just location ID

    metadata: {}                     # Optional: Extension point
```text

**Required Fields:**
- `id` (string)
- `name` (string)

**Allowed Values:**
- `scene_types`: dialogue, stealth, combat, travel, investigation, puzzle, philosophical_dialogue, meditation, tech_investigation, survival, exploration, training
- `services`: briefing_room, medbay, arms_dealer, slicer, transport, bounty_board, safehouse, market, cantina
- `access_points.bypass_methods`: violence, sneak, stealth, climb, navigate, bribe, charm, intimidate, deception, credential, hack, slice, disable, force, force_dark, logic_puzzle, sith_amulet
- `security.patrol_intensity`: low, medium, high, constant, none
- `security.inspection_chance`: low, medium, high

**Validation:**
- `parent_id` must reference an existing location ID
- `travel_links.to_location_id` must reference existing location IDs (warning in lenient)
- `encounter_table.template_id` must reference NPCs in templates section (warning in lenient)
- `access_points.id` must be unique within the location
- `encounter_table` weights must sum to > 0
- `security.security_level` must be 0-100

---

## npcs.yaml

NPCs are divided into three sections:
- **anchors**: Canonical, unique NPCs (e.g., Luke Skywalker)
- **rotating**: Recurring but non-unique NPCs (e.g., Imperial Officer Jans)
- **templates**: Procedural NPC generators (e.g., "imperial_officer")

**Structure:**

```yaml
anchors:
  - id: luke_skywalker               # Required: Unique NPC ID

    name: Luke Skywalker             # Required
    aliases:                         # Optional: Alternative names
      - Luke
      - Skywalker

    banned_aliases: []               # Optional: Names to never match
    match_rules:                     # Optional: Alias matching config
      min_tokens: 1
      require_surname: false
      case_sensitive: false
      allow_single_token: true
    species: Human                   # Optional
    faction_id: rebellion            # Optional: Faction ID
    default_location_id: loc-yavin_base  # Optional: Default location
    home_locations:                  # Optional: Locations NPC frequents
      - loc-yavin_base
      - loc-dagobah

    role: Jedi Knight                # Optional: NPC role
    archetype: Idealistic hero       # Optional: Archetype
    traits:                          # Optional: Personality traits
      - hopeful
      - brave
      - idealistic

    motivation: Restore the Jedi Order and defeat the Empire  # Optional
    secret: His father is Darth Vader  # Optional
    voice_tags:                      # Optional: Speech patterns (must be in VOICE_TAG_SPEECH_PATTERNS)
      - earnest
      - hopeful

    rarity: legendary                # common|rare|legendary
    tags:                            # Optional: Tags for filtering
      - jedi
      - hero

    voice:                           # Optional: Deep characterization
      belief: The Force guides those who trust in it
      wound: Lost his aunt and uncle to the Empire
      taboo: Will not kill an unarmed opponent
      rhetorical_style: earnest
      tell: Looks away when uncertain

    spawn:                           # Optional: Spawn rules (for rotating NPCs)
      location_tags_any:             # Spawn in locations with these tags
        - rebel_base

      location_types_any: []         # Spawn in these location types
      min_alert: 0                   # Min security level (0-100)
      max_alert: 100                 # Max security level (0-100)
      conditions: null               # Optional: Custom spawn logic

    levers:                          # Optional: Social manipulation
      bribeable: "false"             # "false"|"low"|"medium"|"high" (MUST BE STRING)
      intimidatable: "false"
      charmable: "low"
      triggers: null                 # Optional: Custom lever logic

    authority:                       # Optional: Access permissions
      clearance_level: 3             # 0-5
      can_grant_access:              # Access points this NPC can unlock
        - rebel_hangar_door

    knowledge:                       # Optional: What NPC knows
      rumors:                        # Rumor IDs
        - rumor_death_star_weakness

      quest_facts:                   # Quest IDs or "quest_id:stage_id"
        - quest_rescue_leia:stage_1

      secrets:                       # Fact IDs
        - fact_vader_identity

    metadata: {}                     # Optional: Extension point

rotating:
  # Same structure as anchors

templates:
  - id: cantina_patron               # Required: Template ID

    role: Patron                     # Required: Role name
    archetype: Spacer                # Optional
    traits: [gruff, secretive]       # Optional
    motivations: [survival]          # Optional: List of motivations
    secrets: [smuggling]             # Optional: List of secrets
    voice_tags: [gruff, terse]       # Optional: Must be in VOICE_TAG_SPEECH_PATTERNS
    species: [Human, Twi'lek, Rodian]  # Optional: Random species
    tags: [civilian]                 # Optional
    namebank: cantina                # Optional: Namebank to use

    voice: null                      # Optional: Same as anchors
    spawn: null                      # Optional: Same as anchors
    levers:                          # Optional: Same as anchors
      bribeable: "medium"
      intimidatable: "low"
      charmable: "low"
    authority:                       # Optional: Same as anchors
      clearance_level: 0
    knowledge:                       # Optional: Same as anchors
      rumors: []

    metadata: {}                     # Optional
```text

**Required Fields (anchors/rotating):**
- `id` (string)
- `name` (string)

**Required Fields (templates):**
- `id` (string)
- `role` (string)

**Validation:**
- `faction_id` must reference existing faction
- `default_location_id` must reference existing location (warning in lenient)
- `home_locations` must reference existing locations (warning in lenient)
- `voice_tags` must be in VOICE_TAG_SPEECH_PATTERNS (see Common Enums)
- `levers.*` must be strings: "false", "low", "medium", "high"
- `authority.clearance_level` must be 0-5
- `spawn.min_alert` and `max_alert` must be 0-100
- `knowledge.rumors` must reference rumor IDs
- `knowledge.secrets` must reference fact IDs
- `knowledge.quest_facts` must reference quest IDs or "quest_id:stage_id"

---

## backgrounds.yaml

**Structure:**

```yaml
backgrounds:
  - id: bg_rebel_soldier             # Required: Background ID

    name: Rebel Soldier              # Required
    description: |                   # Optional
      You served in the Alliance military...
    icon: soldier                    # Optional: Icon identifier
    starting_stats:                  # Optional: Initial stat bonuses
      combat: 2
      tactics: 1
    starting_starship: yt1300        # Optional: Starting ship ID
    starting_reputation:             # Optional: Faction rep modifiers
      rebellion: 20
      empire: -30

    questions:                       # Optional: Character creation questions
      - id: q1_motivation            # Required: Question ID

        title: Why did you join the Rebellion?  # Required
        subtitle: This shapes your core motivation  # Optional
        condition: null              # Optional: Conditional logic (e.g., "loyalty.tone == PARAGON")
        choices:
          - label: To fight tyranny  # Required

            concept: idealistic rebel  # Required
            tone: PARAGON            # Optional: PARAGON|INVESTIGATE|RENEGADE|NEUTRAL
            effects:                 # Optional: Choice effects
              faction_hint: rebellion
              location_hint: loc-yavin_base
              thread_seed: lost_family
              stat_bonus:
                leadership: 1
```text

**Required Fields:**
- `id` (string)
- `name` (string)
- `questions[].id` (string)
- `questions[].title` (string)
- `questions[].choices[].label` (string)
- `questions[].choices[].concept` (string)

**Conditional Logic:**

Questions can have a `condition` field (Python expression):
- `"loyalty.tone == PARAGON"` - Show if player chose PARAGON tone
- `"q1 == 0"` - Show if player chose choice 0 for question q1

---

## namebanks.yaml

**Structure:**

```yaml
namebanks:
  cantina:
    - Boba
    - Greedo
    - Ponda Baba

  imperial:
    - Tarkin
    - Veers
    - Piett

  rebel:
    - Dodonna
    - Draven
    - Rieek an
```text

**Format:** Dict of `{namebank_id: [name_list]}`

---

## quests.yaml

**Structure:**

```yaml
quests:
  - id: quest_rescue_leia            # Required: Quest ID

    title: Rescue Princess Leia      # Required: Quest title
    description: |                   # Optional: Quest description
      The Rebel Alliance has learned that Princess Leia Organa...
    entry_conditions: null           # Optional: Trigger conditions

    stages:
      - stage_id: stage_1            # Required: Stage ID (NOT "stage")

        objective: Find a pilot      # Optional: Stage objective
        objectives: null             # Optional: Structured objectives
        branch_points: null          # Optional: Branching logic
        success_conditions: null     # Optional: Completion conditions
        fail_conditions: null        # Optional: Failure conditions
        on_enter_effects: null       # Optional: Effects on stage start
        on_exit_effects: null        # Optional: Effects on stage end

      - stage_id: stage_2

        objective: Infiltrate the Death Star
        # ...

    consequences: null               # Optional: Quest completion effects
```text

**Required Fields:**
- `id` (string)
- `title` (string)
- `stages[].stage_id` (string) - **CRITICAL:** Must be `stage_id`, NOT `stage`

---

## events.yaml

**Structure:**

```yaml
events:
  - id: event_imperial_raid          # Required: Event ID

    type: location_event             # Required: Event type
    triggers: null                   # Optional: Trigger conditions
    location_selector: null          # Optional: Location selection logic
    effects: null                    # Optional: Event effects
    broadcast_rules: null            # Optional: Narrative broadcast rules
```text

**Required Fields:**
- `id` (string)
- `type` (string)

---

## rumors.yaml

**Structure:**

```yaml
rumors:
  - id: rumor_death_star             # Required: Rumor ID

    text: |                          # Required: Rumor text (NOT "content")
      I heard the Empire is building a weapon that can destroy planets...
    tags:                            # Optional: Rumor tags
      - empire
      - military

    scope: global                    # Optional: global|location
    credibility: rumor               # Optional: rumor|likely|confirmed
```text

**Required Fields:**
- `id` (string)
- `text` (string) - **CRITICAL:** Must be `text`, NOT `content`

**Allowed Values:**
- `scope`: global, location
- `credibility`: rumor, likely, confirmed

**Schema Migration:**

Old schema used `content`, `reliability`, `name`, `category`. New schema uses `text`, `credibility`, `tags`, `scope`.

---

## meters.yaml

**Structure:**

```yaml
meters:
  reputation_by_faction:
    min: -100
    max: 100
    default: 0
    decay_per_tick: null

  heat_global:
    min: 0
    max: 100
    default: 0
    decay_per_tick: 1

  heat_by_location:
    min: 0
    max: 100
    default: 0
    decay_per_tick: 2

  control_shift: {}
```text

**Required Fields:**
- `reputation_by_faction` (EraMetersBounds)
- `heat_global` (EraMetersBounds)
- `heat_by_location` (EraMetersBounds)

**EraMetersBounds fields:**
- `min` (int, required)
- `max` (int, required)
- `default` (int, required)
- `decay_per_tick` (int, optional)

**Validation:**
- `min` <= `max`
- `default` must be within `[min, max]`

---

## facts.yaml

**Structure:**

```yaml
facts:
  - id: fact_vader_identity          # Required: Fact ID

    subject: Darth Vader             # Required: Subject entity
    predicate: is                    # Required: Relationship
    object: Anakin Skywalker         # Required: Object entity
    confidence: 0.95                 # Optional: Confidence (0.0-1.0)
```text

**Required Fields:**
- `id` (string)
- `subject` (string)
- `predicate` (string)
- `object` (string)

---

## companions.yaml

**Structure:**

```yaml
companions:
  - id: companion_soldier            # Required: Companion ID

    name: Kira Thane                 # Required
    species: Human                   # Optional (default: Human)
    gender: female                   # Optional
    archetype: Loyal protector       # Optional
    faction_id: rebellion            # Optional: Faction ID
    role_in_party: companion         # Optional: companion|specialist|mentor|rival

    voice_tags:                      # Optional: Must be in VOICE_TAG_SPEECH_PATTERNS
      - warm
      - protective

    motivation: Protect those who cannot protect themselves  # Optional
    speech_quirk: Uses military slang  # Optional

    voice:                           # Optional: Deep characterization
      belief: Duty means protecting the weak
      wound: Lost entire squad to Imperial ambush
      taboo: Never abandons a comrade
      rhetorical_style: clipped
      tell: Touches blaster when nervous

    traits:                          # Optional: Trait axes for reactions
      idealist_pragmatic: 30         # -100 (idealist) to 100 (pragmatic)
      merciful_ruthless: -20         # -100 (merciful) to 100 (ruthless)
      lawful_rebellious: -40         # -100 (lawful) to 100 (rebellious)
    default_affinity: 0              # Optional: Starting affinity

    recruitment:                     # Optional: How to recruit
      unlock_conditions: Complete quest_rescue_outpost  # Optional
      first_meeting_location: loc-yavin_base  # Optional: Location ID
      first_scene_template: null     # Optional: Scene template ID

    tags: [soldier, combat]          # Optional
    enables_affordances:             # Optional: Abilities this companion enables
      - tactical_analysis
      - breach_door

    blocks_affordances:              # Optional: Actions this companion prevents
      - imperial_salute

    influence:                       # Optional: Influence mechanics
      starts_at: 0
      min: -100
      max: 100
      triggers:                      # Optional: Influence modifiers
        - intent: threaten_innocent

          delta: -10
        - intent: protect_ally

          delta: 5

    banter:                          # Optional: Banter config
      frequency: normal              # low|normal|high
      style: warm                    # warm|snarky|stoic|etc.
      triggers:                      # Optional: Banter triggers
        - jedi
        - empire

    personal_quest_id: quest_kira_revenge  # Optional: Personal quest ID

    metadata: {}                     # Optional: Extension (e.g., old schema fields)
```text

**Required Fields:**
- `id` (string)
- `name` (string)

**Validation:**
- `faction_id` must reference existing faction (warning in lenient)
- `recruitment.first_meeting_location` must reference existing location (warning in lenient)
- `personal_quest_id` must reference existing quest (warning in lenient)
- `voice_tags` must be in VOICE_TAG_SPEECH_PATTERNS (strict validation)

**Schema Migration:**

Old LEGACY companions have deprecated fields:
- `personality_traits` (list) → Transform to `traits` dict
- `banter_style` (string) → Move to `banter.style`
- `recruitment_trigger` (string) → Move to `recruitment.unlock_conditions`
- `loyalty_progression` (dict) → Discard or store in `metadata`
- `special_abilities` (list) → Transform to `enables_affordances` or discard
- `relationships` (list) → Store in `metadata`
- `narrative_arc` (string) → Store in `metadata`

---

## Common Enums

### Scene Types (ALLOWED_SCENE_TYPES)

```text
dialogue, stealth, combat, travel, investigation, puzzle,
philosophical_dialogue, meditation, tech_investigation,
survival, exploration, training
```text

### Services (ALLOWED_SERVICES)

```text
briefing_room, medbay, arms_dealer, slicer, transport,
bounty_board, safehouse, market, cantina
```text

### Bypass Methods (ALLOWED_BYPASS_METHODS)

```text
violence, sneak, stealth, climb, navigate, bribe, charm,
intimidate, deception, credential, hack, slice, disable,
force, force_dark, logic_puzzle, sith_amulet
```text

### Lever Ratings (LeverRating)

```text
"false", "low", "medium", "high"
```text
**CRITICAL:** Must be strings in YAML, not booleans!

### Patrol Intensity (ALLOWED_PATROL_INTENSITY)

```text
low, medium, high, constant, none
```text

### Voice Tags (VOICE_TAG_SPEECH_PATTERNS)

**40 valid tags:**
```text
earnest, hopeful, warm, weary, nervous, defensive, apologetic,
commanding, authoritative, regal, formal, diplomatic,
sarcastic, wry, snarky, dry,
menacing, cold, icy, fierce, passionate,
fast, measured, deliberate, clipped, terse,
growling, mechanical, rasping, hissing, deep, smooth, serene, mystical, expressive,
calculating, analytical, academic, tactical, professional,
young, grave, uncertain, disdainful, clear, gravelly, gruff, beeps, wise
```text

See `backend/app/core/personality_profile.py` lines 18-86 for full definitions.

---

## Validation Rules

### Lenient vs Strict Mode

Controlled by `ERA_PACK_LENIENT_VALIDATION` in `shared/config.py`.

**Lenient Mode (default in V2.20):**
- Missing cross-references → Log warning
- Invalid enum values → Validation error (strict)
- Missing voice tags → Validation error (strict as of plan)

**Strict Mode:**
- Any validation failure → ValueError
- Required for production-ready era packs

### Cross-Reference Validation

The following references are validated:
- Location `parent_id` → Must exist in locations
- Location `travel_links.to_location_id` → Must exist (warning in lenient)
- Location `encounter_table.template_id` → Must exist in NPC templates (warning in lenient)
- Faction `home_locations` → Must exist in locations (warning in lenient)
- NPC `faction_id` → Must exist in factions
- NPC `default_location_id` → Must exist in locations (warning in lenient)
- NPC `home_locations` → Must exist in locations (warning in lenient)
- NPC `knowledge.rumors` → Must exist in rumors
- NPC `knowledge.secrets` → Must exist in facts
- NPC `knowledge.quest_facts` → Must exist in quests
- Companion `faction_id` → Must exist in factions (warning in lenient)
- Companion `recruitment.first_meeting_location` → Must exist in locations (warning in lenient)
- Companion `personal_quest_id` → Must exist in quests (warning in lenient)
- Background `starting_starship` → Should exist in starship registry
- Era `start_location_pool` → Must exist in locations (warning in lenient)

---

## Common Gotchas

### 1. YAML Boolean vs String

**Problem:** YAML interprets `false` as a boolean, but schema expects string `"false"`.

**Wrong:**
```yaml
levers:
  bribeable: false  # This is a boolean!
```text

**Right:**
```yaml
levers:
  bribeable: "false"  # This is a string
```text

### 2. Integer Aliases Need Quoting

**Problem:** YAML anchor aliases with integers are interpreted as numbers.

**Wrong:**
```yaml
&ref81 some_value
```text

**Right:**
```yaml
&ref_81 some_value  # Use underscore or quote
```text

### 3. Em Dashes in Quoted Strings

**Problem:** Em dashes in double-quoted YAML strings can break parsing.

**Wrong:**
```yaml
description: "The Empire—ruthless and vast—controls the galaxy."
```text

**Right:**
```yaml
description: 'The Empire—ruthless and vast—controls the galaxy.'
# OR

description: The Empire—ruthless and vast—controls the galaxy.
```text

### 4. Quest Stage ID vs Stage

**Problem:** Old schema used `stage`, new schema requires `stage_id`.

**Wrong:**
```yaml
stages:
  - stage: stage_1  # WRONG

    objective: Find pilot
```text

**Right:**
```yaml
stages:
  - stage_id: stage_1  # CORRECT

    objective: Find pilot
```text

### 5. Rumor Text vs Content

**Problem:** Old schema used `content`, new schema requires `text`.

**Wrong:**
```yaml
rumors:
  - id: rumor1

    content: I heard...  # WRONG
```text

**Right:**
```yaml
rumors:
  - id: rumor1

    text: I heard...  # CORRECT
```text

### 6. Voice Tags Must Be Validated

**Problem:** Companions/NPCs with invalid voice tags cause validation errors.

**Wrong:**
```yaml
voice_tags:
  - scholarly  # NOT in VOICE_TAG_SPEECH_PATTERNS
```text

**Right:**
```yaml
voice_tags:
  - academic  # Valid tag
```text

**Valid voice tags list:** See Common Enums section above or `personality_profile.py`.

### 7. Canonical NPCs Go in Anchors/Rotating, Not Templates

**Problem:** Placing unique NPCs like "Luke Skywalker" in templates section.

**Wrong:**
```yaml
templates:
  - id: luke_skywalker  # WRONG - should be in anchors

    role: Jedi Knight
```text

**Right:**
```yaml
anchors:
  - id: luke_skywalker  # CORRECT

    name: Luke Skywalker
```text

### 8. Background Starting Ship Field Name

**Problem:** Using `starship_id` instead of `starting_starship`.

**Wrong:**
```yaml
backgrounds:
  - id: bg_pilot

    starship_id: yt1300  # WRONG
```text

**Right:**
```yaml
backgrounds:
  - id: bg_pilot

    starting_starship: yt1300  # CORRECT
```text

---

## Schema Versioning

Current schema version: **2**

Set in `era.yaml`:
```yaml
schema_version: 2
```text

Schema changes are tracked in `docs/era_pack_migration_guide.md`.

---

## See Also

- `backend/app/world/era_pack_models.py` - Canonical Pydantic schemas
- `backend/app/world/era_pack_loader.py` - Loader implementation
- `backend/app/core/personality_profile.py` - Voice tag definitions
- `docs/era_pack_migration_guide.md` - Migration guide for old YAML
- `ERA_PACK_CLEANUP_STATUS.md` - Current data quality status
