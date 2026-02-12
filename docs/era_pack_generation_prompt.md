# Era Pack Generation Prompt for Claude Sonnet

Use this prompt to generate or improve Star Wars era packs for Storyteller AI. Copy everything below the line and provide it to Claude Sonnet along with your era specification.

---

# ROLE

You are an expert Star Wars lore master and interactive narrative designer specializing in the Storyteller AI system. Your task is to create or improve a complete era pack for an interactive Star Wars story engine.

# TASK

Generate a complete, lore-accurate, gameplay-rich era pack for the **[ERA_NAME]** era of Star Wars.

**Era Specification:**
- **Era Key:** [UPPERCASE_ERA_KEY] (e.g., CLONE_WARS, HIGH_REPUBLIC, NEW_REPUBLIC)
- **Time Period:** [BBY/ABY range, e.g., "22-19 BBY"]
- **Canon:** [Legends / Canon / Mixed]
- **Tone:** [e.g., "Military epic; brotherhood and betrayal; the fall of ideals"]
- **Key Conflicts:** [List 2-4 major tensions]
- **Notable Characters:** [List canonical characters that should appear]
- **Key Locations:** [List planets/locations that should be included]

**Existing Era Pack Status:** [NEW / EXISTS_NEEDS_IMPROVEMENT]
- If EXISTS: Read all files in `data/static/era_packs/[era_key]/` and PRESERVE all existing content while adding depth, fixing errors, and filling gaps.
- If NEW: Generate from scratch following all templates and conventions.

---

# TECHNICAL SPECIFICATIONS

## System Context

**Storyteller AI Architecture:**
- FastAPI backend + LangGraph pipeline (Router → Mechanic → Encounter → WorldSim → CompanionReaction → ArcPlanner → SceneFrame → Director → Narrator → NarrativeValidator → SuggestionRefiner → Commit)
- Local LLM via Ollama (mistral-nemo for prose, qwen3 for lightweight tasks)
- SQLite event sourcing, LanceDB for RAG
- SvelteKit frontend (Svelte 5)
- KOTOR-style dialogue wheel (4 suggestions per turn)
- Tone system: PARAGON (blue/heroic), INVESTIGATE (gold/thoughtful), RENEGADE (red/ruthless), NEUTRAL (gray)

**Output Format:**
- Generate valid YAML for all 12 files: `era.yaml`, `locations.yaml`, `npcs.yaml`, `companions.yaml`, `factions.yaml`, `backgrounds.yaml`, `namebanks.yaml`, `quests.yaml`, `events.yaml`, `rumors.yaml`, `facts.yaml`, `meters.yaml`
- Follow the exact schemas from `data/static/era_packs/_template/`
- Preserve all comments and structure from templates

---

# GENERATION GUIDELINES

## 1. ERA METADATA (`era.yaml`)

- `era_id`: UPPERCASE_SNAKE_CASE (e.g., CLONE_WARS, HIGH_REPUBLIC)
- `schema_version`: 2
- `start_location_pool`: 3-5 diverse starting locations (safe house, cantina, military base, spaceport, etc.)
- `metadata.display_name`: User-facing name (e.g., "The Clone Wars")
- `metadata.time_period`: Specific date range with canon reference
- `metadata.summary`: 3-5 sentences capturing political landscape, major conflicts, and galaxy state
- `metadata.tone`: Short phrase (e.g., "Military epic; brotherhood and betrayal")
- `metadata.key_conflicts`: 2-4 major tensions (faction vs faction, ideological struggles)
- `metadata.themes`: 2-4 thematic throughlines (e.g., "The cost of war", "Loyalty vs. duty")

## 2. LOCATIONS (`locations.yaml`)

**Target: 12-20 locations** (mix of planets, buildings, sub-locations)

### Location Variety
- **Hub locations:** Cantinas, spaceports, markets (3-4)
- **Faction bases:** Rebel safe houses, Imperial garrisons, Jedi temples (3-4)
- **Story locations:** Quest-specific sites, hidden caches, ancient ruins (3-4)
- **Mobile locations:** Ships, space stations (2-3)
- **Sub-locations:** Hangars inside bases, command rooms, meditation chambers (3-5)

### Per Location Requirements
- **Atmospheric descriptions:** 4-6 sentences with sensory details (sights, sounds, smells)
- **Tags:** 3-5 relevant keywords for spawn matching
- **Region:** Outer Rim / Mid Rim / Core / Mobile
- **Controlling factions:** Which factions control this location
- **Security:** Appropriate security_level (0-100), patrol_intensity, inspection_chance
- **Services:** Realistic facilities (cantina, market, arms_dealer, medbay, etc.)
- **Access points:** 2-4 entry points with bypass methods (credentials, stealth, bribe, Force, etc.)
- **Encounter table:** 2-4 NPC templates with weighted spawns
- **Travel links:** Connect to 1-3 other locations
- **Scene types:** Appropriate allowed scene types (dialogue, combat, stealth, investigation, etc.)

### Critical Rules
- Location IDs: `loc-snake_case` (e.g., `loc-jedi_temple`, `loc-coruscant_underworld`)
- Sub-locations use `parent_id` to reference parent
- All `controlling_factions` must exist in `factions.yaml`
- All `encounter_table.template_id` must reference templates in `npcs.yaml`
- All `travel_links` must reference existing location IDs

## 3. NPCS (`npcs.yaml`)

### ANCHORS (Canonical Characters)
**Target: 8-15 major canonical characters**

- Include era-defining characters (e.g., for Clone Wars: Anakin, Obi-Wan, Ahsoka, Palpatine, Dooku, etc.)
- Each anchor needs:
  - **name**, **aliases**, **banned_aliases** (for entity matching)
  - **match_rules**: Appropriate matching config (require_surname for common names)
  - **faction_id**, **default_location_id**, **home_locations**
  - **voice** (belief, wound, taboo, rhetorical_style, tell) — all 5 fields required
  - **levers** (bribeable, intimidatable, charmable) — quote 'false' values!
  - **authority** (clearance_level 0-5, can_grant_access locations)
  - **knowledge** (rumors, quest_facts, secrets) — link to other files
  - **tags**, **traits**, **motivation**, **secret**

### ROTATING (Era-Specific Named NPCs)
**Target: 5-10 recurring named characters**

- Original characters specific to this era pack (information brokers, recurring contacts, local leaders)
- Same structure as anchors but can be less detailed
- Provide gameplay utility (quest givers, rumor sources, social interaction practice)

### TEMPLATES (Procedural Archetypes)
**Target: 8-12 templates covering common encounter types**

Must include:
- **Military/guards:** Faction-specific soldiers (e.g., `tpl-clone_trooper`, `tpl-battle_droid`)
- **Civilians:** Merchants, refugees, locals (e.g., `tpl-civilian`, `tpl-merchant`)
- **Underworld:** Smugglers, bounty hunters, criminals (e.g., `tpl-smuggler`, `tpl-bounty_hunter`)
- **Specialists:** Techs, medics, slicers (e.g., `tpl-tech_specialist`)

Each template needs:
- **role** (REQUIRED), **archetype**, **namebank** reference
- **species** list (3-5 species options for variety)
- **motivations**, **secrets**, **traits** (lists for random selection)
- **spawn** rules (location_tags_any, min_alert, max_alert)
- **voice**, **levers**, **authority** (same as anchors)

### Critical Rules
- Template IDs: `tpl-descriptive_name` or plain snake_case
- Lever values MUST be quoted strings: `'false'` not `false`
- All 5 voice fields required when voice object present
- Namebank keys must exist in `namebanks.yaml`

## 4. COMPANIONS (`companions.yaml`)

**Target: 3-6 companions** with diverse backgrounds, skills, and personalities

### Per Companion Requirements
- **ID:** `comp-<era_key>-<name>` (e.g., `comp-cw-ahsoka`, `comp-hr-porter`)
- **Voice characterization:** belief, wound, taboo, rhetorical_style, tell
- **Voice tags:** Must be valid values from VOICE_TAG_SPEECH_PATTERNS:
  - `clipped_military`, `drawling_smuggler`, `formal_courtly`, `gruff_veteran`, `mystic_cryptic`, `scholarly_precise`, `street_tough`, `warm_maternal`, `sardonic_wit`, `zealous_convert`, `tech_jargon`, `bounty_hunter_terse`, `pirate_boisterous`, `noble_diplomatic`, `child_innocent`, `droid_logical`, `alien_broken_basic`, `merchant_haggling`
- **Traits:** Three axes (-100 to 100):
  - `idealist_pragmatic`: negative = idealistic, positive = pragmatic
  - `merciful_ruthless`: negative = merciful, positive = ruthless
  - `lawful_rebellious`: negative = lawful, positive = rebellious
- **Influence triggers:** 4-6 triggers matching player intents (threaten, help, lie, negotiate) or meaning_tags
- **Banter settings:**
  - `frequency`: low / normal / high
  - `style`: Must match BANTER_POOL keys: `dry_wit`, `earnest`, `sarcastic`, `philosophical`, `competitive`, `protective`, `teasing`, `mentor`
  - `triggers`: 3-6 topic keywords
- **Recruitment:** unlock_conditions, first_meeting_location (must exist in locations.yaml)
- **Affordances:** enables_affordances list (e.g., `[astrogation, sensor_sweep, slice_terminal]`)
- **Personal quest:** Optional personal_quest_id linking to quests.yaml

### Companion Diversity Checklist
- [ ] Mix of species (Human, Twi'lek, droid, etc.)
- [ ] Mix of roles (combat, tech, social, Force-sensitive)
- [ ] Mix of factions (protagonist, neutral, reformed antagonist)
- [ ] Mix of trait profiles (idealist vs pragmatic, merciful vs ruthless)
- [ ] Staggered first_meeting_location (spread throughout locations)

## 5. FACTIONS (`factions.yaml`)

**Target: 4-6 factions** covering the political spectrum

### Required Factions
1. **faction_neutral** (always include) — Independents, unaffiliated
2. **Primary protagonist faction** (Rebels, Republic, Jedi Order, etc.)
3. **Primary antagonist faction** (Empire, Separatists, Sith Empire, etc.)
4. **Secondary factions:** Criminal syndicates, rival governments, neutral powers

### Per Faction Requirements
- **ID:** snake_case (e.g., `rebel_alliance`, `separatist_alliance`, `hutt_cartel`)
- **name**, **tags**, **home_locations**
- **goals:** 2-4 objectives driving this faction's actions (used in Director prompts)
- **metadata.flavor:** One-line description

### Faction Relationships Matrix
- **relationships:** -100 (mortal enemies) to +100 (close allies)
  - Make symmetric: if A hates B at -80, B should hate A around -80
- **cascades:** Multipliers for reputation propagation (-1.0 to 1.0)
  - Example: Gain +10 with Rebels, cascade -0.6 to Empire = -6 Empire rep
  - Neutral factions typically have no cascades

## 6. BACKGROUNDS (`backgrounds.yaml`)

**Target: 3-6 backgrounds** representing different player archetypes

### Per Background Requirements
- **ID:** snake_case (e.g., `jedi_padawan`, `clone_trooper`, `smuggler`)
- **name**, **description**, **icon** (icon matches frontend assets)
- **starting_stats:** Combat, Stealth, Charisma, Tech, General (total ~10 points)
- **starting_starship:** null (ships earned in-story, V2.10+)
- **starting_reputation:** Optional faction reputation modifiers
- **questions:** 2 questions with 3 choices each

### Question Structure
1. **First question:** Unconditional, sets faction/location
   - 3 choices covering PARAGON / NEUTRAL / RENEGADE tones
   - Each choice has `effects.faction_hint`, `effects.location_hint`, `effects.thread_seed`
2. **Second question:** Conditional on first question's tone
   - Use `condition: "question_id.tone == TONE"`
   - Refines the opening narrative

### Choice Requirements
- **label:** The choice text (1-2 sentences)
- **concept:** Internal concept for Architect (describes the character)
- **tone:** PARAGON / INVESTIGATE / RENEGADE / NEUTRAL
- **effects.thread_seed:** Opening narrative hook (2-3 sentences for Director)

## 7. NAMEBANKS (`namebanks.yaml`)

**Target: 15-20 name pools** for procedural NPC generation

### Required Pools
- **Faction-specific:** `rebel_names`, `imperial_names`, `jedi_names`, etc.
- **Species-specific:** `human_first_names_male`, `human_first_names_female`, `human_surnames`, `twilek_names`, `rodian_names`, `wookiee_names`, `droid_names`, etc.
- **Role-specific:** `military_ranks`, `criminal_titles`, `imperial_titles`, `jedi_titles`, `sith_titles`
- **Regional:** `corellian_surnames`, `alderaanian_surnames`, `outer_rim_surnames`, `core_world_surnames`

### Per Pool Requirements
- 15-30 names per pool for variety
- Lore-accurate names matching Star Wars naming conventions
- Mix of canon names and original names that "sound Star Wars"

## 8. QUESTS (`quests.yaml`)

**Target: 4-8 quests** providing multi-stage story arcs

### Quest Types to Include
- **Main story quest:** Ties to era's central conflict
- **Faction quests:** 2-3 quests for major factions
- **Companion personal quests:** 1 quest per companion with personal_quest_id
- **Side quests:** 1-2 optional exploration/discovery quests

### Per Quest Requirements
- **ID:** snake_case (e.g., `quest_sabotage_depot`, `quest_rescue_senator`)
- **title**, **description**
- **entry_conditions:** When quest becomes available (e.g., `{turn: {min: 5}}`)
- **stages:** 3-5 stages with objectives
  - Each stage has `stage_id`, `objective`, `success_conditions`, optional `fail_conditions`
- **consequences:** Effects on completion (e.g., `{reputation_rebel_alliance: '+20'}`)

## 9. EVENTS (`events.yaml`)

**Target: 3-6 world events** triggered by conditions

### Event Types
- **Heat events:** Imperial inspections, raids (trigger on high heat_global)
- **Reputation events:** Faction recognition, bounties (trigger on reputation thresholds)
- **Story events:** Era-specific major events (Order 66, Battle of X, etc.)

### Per Event Requirements
- **ID:** snake_case (e.g., `event_imperial_inspection`, `event_order_66`)
- **type:** `hard` (mandatory cutscene) or `soft` (background flavor)
- **triggers:** Meter thresholds (e.g., `{heat_global: {min: 60}}`)
- **location_selector:** Where event fires (e.g., `{tags_any: [imperial, military]}`)
- **effects:** Changes applied (e.g., `{heat_by_location: '+15'}`)
- **broadcast_rules:** `{visible_to: all}` or `{visible_to: present}`

## 10. RUMORS (`rumors.yaml`)

**Target: 8-15 rumors** for NPC dialogue

### Rumor Categories
- **Lore rumors:** Background info about the era (3-4)
- **Quest hooks:** Lead to quest content (3-4)
- **Faction rumors:** Intel on faction activities (2-3)
- **Location rumors:** Secret locations, hidden caches (2-3)
- **Character rumors:** Info on major NPCs (1-2)

### Per Rumor Requirements
- **ID:** snake_case (e.g., `rumor_death_star_plans`, `rumor_jedi_survivor`)
- **text:** 1-3 sentences, atmospheric and intriguing
- **tags:** 2-4 thematic tags
- **scope:** `global` (heard anywhere) or `location` (specific location)
- **credibility:** `rumor` (unverified) / `likely` (probably true) / `confirmed` (factual)

## 11. FACTS (`facts.yaml`)

**Target: 8-12 knowledge graph seed facts**

### Fact Types
- **Control facts:** Faction X controls Location Y (3-4)
- **Alliance facts:** Faction X allied with Faction Y (2-3)
- **Location facts:** NPC X hides in Location Y (2-3)
- **Secret facts:** Hidden information (1-2)

### Per Fact Requirements
- **ID:** snake_case (e.g., `fact_empire_controls_coruscant`, `fact_jedi_hiding_tatooine`)
- **subject:** Entity ID (faction, NPC, location)
- **predicate:** Relationship verb (`controls`, `allied_with`, `hides_in`, `seeks`, etc.)
- **object:** Entity ID
- **confidence:** 0.0-1.0 (1.0 = confirmed fact, 0.5 = uncertain intel)

## 12. METERS (`meters.yaml`)

**Standard meter configuration** (usually doesn't need customization)

```yaml
meters:
  reputation_by_faction:
    min: -100
    max: 100
    default: 0
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
  control_shift:
    enabled: false
```

---

# CRITICAL YAML GOTCHAS

## 1. Boolean Quoting
```yaml
# WRONG - boolean False
bribeable: false

# CORRECT - string "false"
bribeable: 'false'
```

## 2. Integer Anchors
```yaml
# WRONG - parsed as int
anchor: 81

# CORRECT
anchor: "81"
```

## 3. Em Dashes and Colons
```yaml
# WRONG
description: War — it never ends.

# CORRECT (single-quote the whole line)
description: 'War -- it never ends.'
```

## 4. Multiline Strings
```yaml
# Use | for literal blocks
description: |
  Line one.
  Line two.
  Line three.
```

## 5. Starting Starships
```yaml
# V2.10+: ships earned in-story, not starting equipment
starting_starship: null
```

---

# LORE ACCURACY REQUIREMENTS

1. **Canon Consistency:**
   - Respect established character personalities, relationships, and arcs
   - Use correct titles, ranks, and organizational names
   - Place characters in appropriate locations for the time period
   - Honor faction alignments and conflicts

2. **Atmospheric Authenticity:**
   - Location descriptions should feel "Star Wars" (blend of tech and lived-in wear)
   - NPC dialogue tags match character archetypes (clipped military, drawling smuggler, etc.)
   - Species distribution matches era demographics
   - Technology level appropriate to time period

3. **Name Conventions:**
   - Human names: Western-influenced but exotic (Kanan, Hera, Cassian)
   - Twi'lek: Apostrophes common (Hera Syndulla, Bib Fortuna)
   - Wookiee: Guttural, lots of consonants (Chewbacca, Tarfful)
   - Droid: Alphanumeric (R2-D2, BB-8, K-2SO)
   - Imperial: Germanic/authoritative (Tarkin, Thrawn, Krennic)

4. **Faction Goals:**
   - Must reflect era-specific conflicts and power dynamics
   - Avoid anachronisms (don't reference Rebels in Old Republic era)

---

# GAMEPLAY BALANCE REQUIREMENTS

## Location Distribution
- [ ] 3-4 safe/neutral hubs for social gameplay
- [ ] 3-4 hostile/secure locations for stealth/combat
- [ ] 2-3 quest-specific story locations
- [ ] 2-3 travel/mobile locations (ships, stations)

## NPC Template Coverage
- [ ] Guard/patrol templates for 2-3 major factions
- [ ] Civilian templates for social locations
- [ ] Specialist templates (medic, tech, slicer)
- [ ] Underworld templates (smuggler, bounty hunter, criminal)

## Companion Roster
- [ ] At least one Force-sensitive (if appropriate to era)
- [ ] At least one tech specialist
- [ ] At least one combat specialist
- [ ] At least one social/charisma specialist
- [ ] Mix of species and genders

## Background Variety
- [ ] At least one military background
- [ ] At least one underworld/criminal background
- [ ] At least one civilian/neutral background
- [ ] Cover PARAGON, NEUTRAL, and RENEGADE starting paths

---

# OUTPUT FORMAT

Generate complete YAML files for all 12 era pack components. For each file:

1. **Preserve template structure:** Keep all comments, section headers, and formatting from `_template/`
2. **Validate cross-references:** Ensure all IDs referenced across files exist
3. **Check YAML syntax:** Quote boolean 'false', avoid unescaped colons/em-dashes
4. **Include inline comments:** For complex entries, add brief clarifying comments

**Delivery Format:**
```yaml
# ============================================================
# [filename].yaml -- [Purpose]
# ============================================================
[Full file content with all entries]
```

Provide all 12 files in order:
1. `era.yaml`
2. `locations.yaml`
3. `npcs.yaml`
4. `companions.yaml`
5. `factions.yaml`
6. `backgrounds.yaml`
7. `namebanks.yaml`
8. `quests.yaml`
9. `events.yaml`
10. `rumors.yaml`
11. `facts.yaml`
12. `meters.yaml`

---

# FINAL CHECKLIST

Before submitting, verify:

- [ ] All cross-references are valid (locations, factions, NPCs, rumors, facts, quests)
- [ ] All lever values are quoted strings: `'false'` not `false`
- [ ] All voice objects have all 5 required fields
- [ ] All companion voice_tags are from the valid list
- [ ] All companion banter styles are from the valid list
- [ ] All encounter_table template_ids reference actual templates
- [ ] All namebank references exist in namebanks.yaml
- [ ] All location IDs use `loc-` prefix
- [ ] All companion IDs use `comp-<era>-` prefix
- [ ] All template IDs use `tpl-` prefix or descriptive snake_case
- [ ] Starting starship is `null` for all backgrounds
- [ ] Parent location IDs reference existing locations
- [ ] Travel links are valid location IDs
- [ ] Faction goals are era-appropriate
- [ ] NPC descriptions are atmospheric (4-6 sentences)
- [ ] Quest stage IDs are unique within each quest
- [ ] Rumor credibility levels are valid (rumor/likely/confirmed)
- [ ] Fact confidence scores are 0.0-1.0
- [ ] No YAML syntax errors (em-dashes, unquoted colons, etc.)

---

# READY TO GENERATE

I am ready to generate a complete, lore-accurate, gameplay-rich era pack for **[ERA_NAME]**.

**What I need from you:**
1. **Era specification** (name, time period, canon type, tone, key conflicts)
2. **Notable characters** to include
3. **Key locations** to include
4. **Existing era pack status** (new or improvement needed)

Once you provide these details, I will generate all 12 YAML files following every guideline above.
