# Era Pack Field Reference

> Comprehensive field-by-field guide for authoring Storyteller AI era packs.
> All examples drawn from the REBELLION era (`data/static/era_packs/rebellion/`).

---

## Directory Structure

Each era pack lives in its own folder under `data/static/era_packs/<era_key>/`:

```
data/static/era_packs/
  rebellion/
    era.yaml          # Era metadata & file index (required)
    locations.yaml    # World locations
    npcs.yaml         # Named NPCs + spawn templates
    companions.yaml   # Recruitable party companions
    factions.yaml     # Faction definitions + relationship matrix
    backgrounds.yaml  # Character creation backgrounds
    namebanks.yaml    # Name pools for NPC generation
    quests.yaml       # Multi-stage quest definitions
    events.yaml       # World event triggers
    rumors.yaml       # NPC-delivered rumors
    facts.yaml        # Knowledge graph seed facts
    meters.yaml       # World meter bounds/defaults
```

---

## 1. `era.yaml` -- Era Metadata

**Purpose:** Root manifest. Declares the era ID, schema version, and indexes all other files. Also defines starting locations, global events, travel graph, and display metadata.

| Field | Type | Required | Description |
|---|---|---|---|
| `era_id` | `str` | **Yes** | Unique era identifier (UPPERCASE convention: `REBELLION`, `OLD_REPUBLIC`) |
| `schema_version` | `int` | No | Schema version; current is `2` |
| `style_ref` | `str` | No | Path to style guide markdown (e.g., `data/style/rebellion_style.md`) |
| `file_index` | `dict[str, str]` | **Yes** | Maps logical name to filename: `era: era.yaml`, `locations: locations.yaml`, etc. |
| `start_location_pool` | `list[str]` | **Yes** | Location IDs eligible as starting positions (referenced by backgrounds) |
| `global_event_templates` | `list[str]` | No | Event IDs that fire globally (usually `[]`) |
| `travel_graph` | `list[TravelLink]` | No | Era-level travel connections (usually `[]`; per-location links preferred) |
| `default_scene_pacing` | `dict` | No | Default pacing parameters (usually `{}`) |
| `metadata` | `dict` | No | Freeform: `display_name`, `time_period`, `summary`, `tone`, `key_conflicts`, `themes` |

**Example:**
```yaml
era_id: REBELLION
schema_version: 2
style_ref: data/style/rebellion_style.md
file_index:
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
start_location_pool:
- loc-cantina
- loc-bazaar_market
- loc-safe_house
metadata:
  display_name: Age of Rebellion
  time_period: 0-4 ABY (Legends)
  tone: Gritty hope; underdog resistance; found family.
```

**Gotchas:**
- `file_index` keys must exactly match the logical names: `era`, `locations`, `npcs`, `factions`, `backgrounds`, `namebanks`, `quests`, `events`, `rumors`, `meters`, `facts`, `companions`.
- `start_location_pool` IDs must exist in `locations.yaml`.

---

## 2. `locations.yaml` -- World Locations

**Purpose:** Defines all locations (planets, buildings, rooms) where scenes can occur. Locations can be hierarchical via `parent_id`.

### Top-level

```yaml
locations:
- id: loc-cantina
  name: Mos Eisley Cantina
  ...
```

### Per-Location Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique ID; convention: `loc-snake_case` |
| `name` | `str` | **Yes** | Display name |
| `tags` | `list[str]` | No | Searchable tags (e.g., `rebel`, `cantina`, `spaceport`) |
| `region` | `str` | No | Galaxy region (e.g., `Outer Rim`, `Mid Rim`, `Core`, `Mobile`) |
| `planet` | `str` | No | Planet name (e.g., `Tatooine`, `Hoth`); `null` for mobile locations |
| `controlling_factions` | `list[str]` | No | Faction IDs that control this location |
| `description` | `str` | No | Prose description for the Narrator (use `\|` for multiline YAML) |
| `threat_level` | `str` | No | One of: `low`, `moderate`, `high`, `extreme` |
| `parent_id` | `str` | No | Parent location ID for sub-locations (e.g., hangar inside a base) |
| `scene_types` | `list[str]` | No | Allowed: `dialogue`, `stealth`, `combat`, `travel`, `investigation`, `puzzle`, `philosophical_dialogue`, `meditation`, `tech_investigation`, `survival`, `exploration`, `training` |
| `security` | `object` | No | Security configuration (see sub-table) |
| `services` | `list[str]` | No | Allowed: `briefing_room`, `medbay`, `arms_dealer`, `slicer`, `transport`, `bounty_board`, `safehouse`, `market`, `cantina` |
| `access_points` | `list[AccessPoint]` | No | Entry/exit points with bypass methods (see sub-table) |
| `encounter_table` | `list[EncounterEntry]` | No | Weighted NPC template spawns |
| `keywords` | `list[str]` | No | Additional search keywords for RAG |
| `travel_links` | `list[str\|TravelLink]` | No | Connected locations (can be bare IDs or objects) |
| `metadata` | `dict` | No | Freeform extension |

### `security` Sub-Object

| Field | Type | Default | Description |
|---|---|---|---|
| `controlling_faction` | `str` | `null` | Faction ID |
| `security_level` | `int` | `50` | 0-100 scale |
| `patrol_intensity` | `str` | `medium` | One of: `low`, `medium`, `high`, `constant`, `none` |
| `inspection_chance` | `str` | `medium` | One of: `low`, `medium`, `high`, `constant`, `none` |

### `access_points[]` Sub-Object

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique within location (e.g., `main_entrance`) |
| `type` | `str` | No | Free-form: `door`, `hatch`, `underground`, `ventilation` |
| `visibility` | `str` | No | `public`, `restricted`, `hidden`, `secret` |
| `bypass_methods` | `list[str]` | No | Allowed values: `violence`, `sneak`, `stealth`, `climb`, `navigate`, `bribe`, `charm`, `intimidate`, `deception`, `credential`, `hack`, `slice`, `disable`, `force`, `force_dark`, `logic_puzzle`, `sith_amulet` |

### `encounter_table[]` Sub-Object

| Field | Type | Required | Description |
|---|---|---|---|
| `template_id` | `str` | **Yes** | References an NPC template ID from `npcs.yaml` |
| `weight` | `int` | No | Spawn weight (must be > 0; default `1`) |
| `conditions` | `any` | No | Optional spawn conditions |

**Example:**
```yaml
- id: loc-cantina
  name: Mos Eisley Cantina
  tags: [cantina, underworld, smuggler]
  region: Outer Rim
  planet: Tatooine
  controlling_factions: [underworld]
  description: |
    A wretched hive of scum and villainy...
  threat_level: moderate
  scene_types: [dialogue, investigation, combat]
  security:
    controlling_faction: underworld
    security_level: 30
    patrol_intensity: low
    inspection_chance: low
  services: [cantina, bounty_board]
  access_points:
  - id: main_entrance
    type: door
    visibility: public
    bypass_methods: [credential]
  - id: back_room
    type: door
    visibility: hidden
    bypass_methods: [bribe, charm]
  encounter_table:
  - template_id: smuggler_contact
    weight: 3
  - template_id: bounty_hunter_solo
    weight: 2
  travel_links:
  - loc-bazaar_market
  - loc-cargo_docks
```

**Gotchas:**
- `services` values are validated against a fixed allowlist; typos cause load failures.
- `bypass_methods` are also validated; use only the values listed above.
- `travel_links` can be bare location ID strings; they auto-convert to `{to_location_id: "loc-xxx"}`.
- Sub-locations use `parent_id` to reference the parent; the parent must exist.

---

## 3. `npcs.yaml` -- NPCs and Templates

**Purpose:** Three categories of NPCs: `anchors` (canonical named characters), `rotating` (named but non-canonical), and `templates` (generic archetypes for spawning).

### Top-level Structure

```yaml
npcs:
  anchors:
  - id: luke_skywalker
    ...
  rotating:
  - id: some_recurring_npc
    ...
  templates:
  - id: stormtrooper_patrol
    ...
```

### Anchor / Rotating NPC Fields (`EraNpcEntry`)

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique NPC ID (snake_case) |
| `name` | `str` | **Yes** | Display name |
| `rarity` | `str` | No | `common`, `uncommon`, `rare`, `legendary` (default: `common`) |
| `aliases` | `list[str]` | No | Alternative names for matching (e.g., `["Luke", "Skywalker"]`) |
| `banned_aliases` | `list[str]` | No | Tokens to exclude from matching (e.g., `["Princess"]`) |
| `match_rules` | `object` | No | Alias matching config (see sub-table) |
| `tags` | `list[str]` | No | Searchable tags |
| `faction_id` | `str` | No | Faction ID this NPC belongs to |
| `default_location_id` | `str` | No | Location ID where NPC is typically found |
| `home_locations` | `list[str]` | No | Location IDs where NPC can appear |
| `role` | `str` | No | Role description (e.g., `Rebel Pilot`) |
| `archetype` | `str` | No | Character archetype (e.g., `Idealistic hero`) |
| `species` | `str` | No | Species name |
| `traits` | `list[str]` | No | Personality traits (e.g., `[brave, impulsive]`) |
| `motivation` | `str` | No | What drives this NPC |
| `secret` | `str` | No | Hidden information the NPC holds |
| `voice_tags` | `list[str]` | No | Speech style tags (e.g., `[earnest, young]`) |
| `voice` | `NpcVoice` | No | Deep voice characterization (see sub-table) |
| `levers` | `NpcLevers` | No | Social interaction levers (see sub-table) |
| `authority` | `NpcAuthority` | No | Access/clearance level (see sub-table) |
| `knowledge` | `NpcKnowledge` | No | Rumors/facts this NPC knows (see sub-table) |
| `metadata` | `dict` | No | Freeform extension |

### `match_rules` Sub-Object

| Field | Type | Default | Description |
|---|---|---|---|
| `min_tokens` | `int` | `1` | Minimum name tokens for a match |
| `require_surname` | `bool` | `false` | Require surname for match |
| `case_sensitive` | `bool` | `false` | Case-sensitive matching |
| `allow_single_token` | `bool` | `false` | Allow single-token match (e.g., "Vader") |

### `voice` Sub-Object

| Field | Type | Required | Description |
|---|---|---|---|
| `belief` | `str` | **Yes** | Core belief (1 sentence) |
| `wound` | `str` | **Yes** | Formative wound (1 sentence) |
| `taboo` | `str` | **Yes** | Personal taboo (short phrase) |
| `rhetorical_style` | `str` | **Yes** | Speaking style: `earnest`, `blunt`, `Socratic`, `coldly_practical`, etc. |
| `tell` | `str` | **Yes** | Physical/verbal mannerism |

### `levers` Sub-Object

| Field | Type | Default | Description |
|---|---|---|---|
| `bribeable` | `str` | `"false"` | `"false"`, `"low"`, `"medium"`, `"high"` |
| `intimidatable` | `str` | `"false"` | `"false"`, `"low"`, `"medium"`, `"high"` |
| `charmable` | `str` | `"false"` | `"false"`, `"low"`, `"medium"`, `"high"` |

### `authority` Sub-Object

| Field | Type | Default | Description |
|---|---|---|---|
| `clearance_level` | `int` | `0` | 0-5 scale |
| `can_grant_access` | `list[str]` | `[]` | Location IDs this NPC can grant access to |

### `knowledge` Sub-Object

| Field | Type | Default | Description |
|---|---|---|---|
| `rumors` | `list[str]` | `[]` | Rumor IDs this NPC can share |
| `quest_facts` | `list[str]` | `[]` | Quest IDs or `quest_id:stage_id` strings |
| `secrets` | `list[str]` | `[]` | Fact IDs this NPC knows as secrets |

### Template NPC Fields (`EraNpcTemplate`)

Templates define archetypes for dynamically spawned NPCs. Key differences from anchors:

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique template ID (e.g., `stormtrooper_patrol`) |
| `role` | `str` | **Yes** | Role label |
| `archetype` | `str` | No | Archetype label |
| `traits` | `list[str]` | No | Personality pool (random selection) |
| `motivations` | `list[str]` | No | Motivation pool |
| `secrets` | `list[str]` | No | Secret pool |
| `voice_tags` | `list[str]` | No | Voice tag pool |
| `species` | `list[str]` | No | Eligible species |
| `tags` | `list[str]` | No | Tags |
| `namebank` | `str` | No | Key into `namebanks.yaml` for name generation |
| `spawn` | `NpcSpawnRules` | No | Spawn conditions (see sub-table) |
| `voice`, `levers`, `authority`, `knowledge` | | No | Same as anchor NPCs |

### `spawn` Sub-Object

| Field | Type | Default | Description |
|---|---|---|---|
| `location_tags_any` | `list[str]` | `[]` | Spawn if location has any of these tags |
| `location_types_any` | `list[str]` | `[]` | Spawn if location matches these types |
| `min_alert` | `int` | `0` | Minimum alert level to spawn (0-100) |
| `max_alert` | `int` | `100` | Maximum alert level to spawn (0-100) |

**Gotchas:**
- Lever values MUST be quoted strings: `bribeable: 'false'`, NOT `bribeable: false` (YAML `false` is boolean, not the string `"false"`).
- Canonical characters go in `anchors` or `rotating`, NEVER in `templates`.
- `encounter_table.template_id` in locations must reference template IDs, not anchor IDs.
- All `voice` sub-fields are required when the `voice` object is present.

---

## 4. `companions.yaml` -- Party Companions

**Purpose:** Recruitable companions with voice, influence, banter, and recruitment rules.

### Top-level

```yaml
companions:
- id: comp-reb-kessa
  name: Kessa Vane
  ...
```

### Per-Companion Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique ID; convention: `comp-<era>-<name>` |
| `name` | `str` | **Yes** | Display name |
| `species` | `str` | No | Species (default: `Human`) |
| `gender` | `str` | No | `male`, `female`, `nonbinary`, etc. |
| `archetype` | `str` | No | Character archetype (e.g., `Alliance scout`) |
| `faction_id` | `str` | No | Faction ID |
| `role_in_party` | `str` | No | `companion`, `specialist`, `mentor`, `rival` (default: `companion`) |
| `voice_tags` | `list[str]` | No | Speech style tags; must be in `VOICE_TAG_SPEECH_PATTERNS` |
| `motivation` | `str` | No | Core motivation |
| `speech_quirk` | `str` | No | Distinctive speech habit |
| `voice` | `EraCompanionVoice` | No | Deep voice characterization (same fields as NPC voice) |
| `traits` | `dict[str, int]` | No | Trait axes: `idealist_pragmatic`, `merciful_ruthless`, `lawful_rebellious` (range: -100 to 100) |
| `default_affinity` | `int` | No | Starting affinity score (default: `0`) |
| `recruitment` | `object` | No | Recruitment conditions (see sub-table) |
| `tags` | `list[str]` | No | Searchable tags |
| `enables_affordances` | `list[str]` | No | Abilities this companion unlocks (e.g., `[astrogation, sensor_sweep]`) |
| `blocks_affordances` | `list[str]` | No | Abilities this companion prevents |
| `influence` | `object` | No | Influence tuning (see sub-table) |
| `banter` | `object` | No | Banter tuning (see sub-table) |
| `personal_quest_id` | `str` | No | Quest ID for companion personal quest |
| `metadata` | `dict` | No | Freeform: `loyalty_hook`, `recruitment_context`, `banter_style`, `faction_interest` |

### `recruitment` Sub-Object

| Field | Type | Required | Description |
|---|---|---|---|
| `unlock_conditions` | `str` | No | Free-text condition (e.g., "Encounter Kessa at a Rebel safe house") |
| `first_meeting_location` | `str` | No | Location ID for first encounter |
| `first_scene_template` | `str` | No | Template ID for intro scene |

### `influence` Sub-Object

| Field | Type | Default | Description |
|---|---|---|---|
| `starts_at` | `int` | `0` | Initial influence value |
| `min` | `int` | `-100` | Minimum influence |
| `max` | `int` | `100` | Maximum influence |
| `triggers` | `list[dict]` | `[]` | Influence change triggers: `{intent: "threaten", delta: -3}` or `{meaning_tag: "reveal_values", delta: 2}` |

### `banter` Sub-Object

| Field | Type | Default | Description |
|---|---|---|---|
| `frequency` | `str` | `normal` | `low`, `normal`, `high` |
| `style` | `str` | `warm` | Must match `BANTER_POOL` keys: `warm`, `snarky`, `stoic`, etc. |
| `triggers` | `list[str]` | `[]` | Topic triggers for banter (e.g., `[hyperspace, navigation]`) |

**Gotchas:**
- `voice_tags` must be values recognized in `VOICE_TAG_SPEECH_PATTERNS` (see `backend/app/core/companions.py`).
- `banter.style` must match keys in `BANTER_POOL` (see `backend/app/core/banter_manager.py`).
- `recruitment.first_meeting_location` must be a valid location ID.
- `personal_quest_id` must reference a quest defined in `quests.yaml`.

---

## 5. `factions.yaml` -- Factions

**Purpose:** Defines all factions and (optionally) the faction relationship matrix with cascade multipliers.

### Top-level

```yaml
factions:
- id: rebel_alliance
  name: Alliance to Restore the Republic
  ...

faction_relationships:
  rebel_alliance:
    relationships:
      galactic_empire: -100
      ...
    cascades:
      galactic_empire: -0.6
      ...
```

### Per-Faction Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique faction ID (snake_case) |
| `name` | `str` | **Yes** | Display name |
| `tags` | `list[str]` | No | Searchable tags (e.g., `[rebel, alliance]`) |
| `home_locations` | `list[str]` | No | Location IDs where faction is based |
| `goals` | `list[str]` | No | Faction goals (used in Director prompts) |
| `metadata` | `dict` | No | Freeform; convention: `{flavor: "..."}` |

### `faction_relationships` Section

| Field | Type | Description |
|---|---|---|
| `<faction_id>.relationships` | `dict[str, int]` | Disposition toward other factions: -100 (enemy) to +100 (ally) |
| `<faction_id>.cascades` | `dict[str, float]` | Cascade multipliers: gaining rep with this faction multiplies delta for cascade targets |

**Gotchas:**
- Always include a `neutral` faction for unaffiliated NPCs.
- Cascade values are multipliers (e.g., `-0.6` means gaining +10 with faction A gives -6 with the cascade target).
- `home_locations` should reference existing location IDs.

---

## 6. `backgrounds.yaml` -- Character Backgrounds

**Purpose:** SWTOR-style branching character creation. Each background has starting stats, and a chain of branching questions that set faction, location, and story thread.

### Top-level

```yaml
backgrounds:
- id: smuggler
  name: "Smuggler"
  ...
```

### Per-Background Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique background ID |
| `name` | `str` | **Yes** | Display name |
| `description` | `str` | No | Flavor text |
| `icon` | `str` | No | Icon key for frontend |
| `starting_stats` | `dict[str, int]` | No | Initial stat values: `Combat`, `Stealth`, `Charisma`, `Tech`, `General` |
| `starting_starship` | `str` | No | Ship ID or `null` (V2.10: ships earned in-story) |
| `starting_reputation` | `dict[str, int]` | No | Initial faction reputation modifiers |
| `questions` | `list[Question]` | No | Branching question chain |

### Question Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Question ID (unique within background) |
| `title` | `str` | **Yes** | Question text shown to player |
| `subtitle` | `str` | No | Helper text |
| `condition` | `str` | No | Show only if condition met (e.g., `"loyalty.tone == PARAGON"`) |
| `choices` | `list[Choice]` | **Yes** | Available answers |

### Choice Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `label` | `str` | **Yes** | Choice text shown to player |
| `concept` | `str` | **Yes** | Internal concept string for the Architect |
| `tone` | `str` | No | `PARAGON`, `INVESTIGATE`, `RENEGADE`, `NEUTRAL` (default: `NEUTRAL`) |
| `effects` | `ChoiceEffect` | No | Effects applied on selection |

### Choice Effect Fields

| Field | Type | Description |
|---|---|---|
| `faction_hint` | `str` | Faction ID for initial alignment |
| `location_hint` | `str` | Starting location ID |
| `thread_seed` | `str` | Opening story hook text |
| `stat_bonus` | `dict[str, int]` | Additional stat modifiers |
| `companion_affinity_bonus` | `list[dict]` | Companion affinity modifiers (e.g., `[{comp-reb-kessa: 20}]`) |

**Gotchas:**
- `starting_starship` should be `null` in V2.10+; ships are earned in-story.
- `condition` strings use dot notation: `"<question_id>.tone == <TONE>"`.
- `location_hint` and `faction_hint` must reference existing IDs.

---

## 7. `namebanks.yaml` -- Name Pools

**Purpose:** Provides name lists for NPC generation, keyed by category.

### Structure

```yaml
namebanks:
  rebel_names: [Kessa, Nia, Taro, ...]
  imperial_names: [Korr, Damar, Sarne, ...]
  underworld_names: [Rake, Jax, Sel, ...]
  civilian_names: [Bren, Mara, Tala, ...]
  droid_names: [R2-D2, C-3PO, K-2SO, ...]
  human_first_names_male: [Dax, Kael, ...]
  human_first_names_female: [Lyssa, Senna, ...]
  human_surnames: [Korin, Raal, ...]
  twilek_names: [Hera, Numa, ...]
  bothan_names: [Borsk, Koth, ...]
  rodian_names: [Greedo, Navik, ...]
  mon_calamari_names: [Ackbar, Cilghal, ...]
  duros_names: [Vex, Korin, ...]
  zabrak_names: [Javik, Sarn, ...]
  trandoshan_names: [Bossk, Garnac, ...]
  kel_dor_names: [Kael, Plo, ...]
  nautolan_names: [Senna, Kit, ...]
  togruta_names: [Zara, Ahsoka, ...]
  gand_names: [Orynn, Zuckuss, ...]
  military_ranks: [General, Admiral, ...]
  criminal_titles: [Boss, Kingpin, ...]
  imperial_titles: [Moff, Grand Moff, ...]
  rebel_titles: [Chief, Leader, ...]
  force_tradition_titles: [Jedi, Padawan, ...]
  corellian_surnames: [Antilles, Solo, ...]
  alderaanian_surnames: [Organa, Panteer, ...]
  outer_rim_surnames: [Rendar, Vrynn, ...]
```

**Conventions:**
- Keys are referenced by NPC templates via the `namebank` field (e.g., `namebank: imperial_names`).
- Include species-specific name lists for diverse NPC generation.
- Include rank/title lists for procedural name construction.
- Minimum 10-15 names per pool for variety.

---

## 8. `quests.yaml` -- Quest Definitions

**Purpose:** Multi-stage quests with entry conditions, objectives, and consequences.

### Top-level

```yaml
quests:
- id: quest_first_contact
  title: First Contact
  ...
```

### Per-Quest Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique quest ID |
| `title` | `str` | **Yes** | Display title |
| `description` | `str` | No | Quest description |
| `entry_conditions` | `dict` | No | Conditions to trigger quest (e.g., `{turn: {min: 3}}`) |
| `stages` | `list[Stage]` | **Yes** | Ordered quest stages |
| `consequences` | `dict` | No | Effects on completion (e.g., `{reputation_rebel_alliance: '+10'}`) |

### Stage Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `stage_id` | `str` | **Yes** | Unique within quest |
| `objective` | `str` | No | Objective description |
| `success_conditions` | `dict` | No | Conditions to advance (e.g., `{npc_met: rebel_contact}`) |
| `fail_conditions` | `dict` | No | Conditions that fail the stage |
| `on_enter_effects` | `dict` | No | Effects triggered on stage entry |
| `on_exit_effects` | `dict` | No | Effects triggered on stage exit |

**Gotchas:**
- `consequences` values should be quoted strings when numeric: `'+10'`, not `+10`.
- Quest IDs are referenced by NPCs (`knowledge.quest_facts`) and companions (`personal_quest_id`).

---

## 9. `events.yaml` -- World Events

**Purpose:** Conditional world events triggered by meter thresholds or other conditions.

### Top-level

```yaml
events:
- id: event_imperial_inspection
  type: hard
  ...
```

### Per-Event Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique event ID |
| `type` | `str` | **Yes** | `hard` (mandatory) or `soft` (optional) |
| `triggers` | `dict` | No | Meter thresholds: `{heat_global: {min: 50}}` |
| `location_selector` | `dict` | No | Where event fires: `{tags_any: [imperial, checkpoint]}` |
| `effects` | `dict` | No | Effects applied: `{heat_by_location: '+10'}` |
| `broadcast_rules` | `dict` | No | Visibility: `{visible_to: all}` or `{visible_to: present}` |

---

## 10. `rumors.yaml` -- Rumors

**Purpose:** Information NPCs can share with the player, tagged and scoped.

### Top-level

```yaml
rumors:
- id: rumor_death_star_plans
  text: The Rebellion has stolen something from the Empire...
  ...
```

### Per-Rumor Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique rumor ID |
| `text` | `str` | **Yes** | Rumor text (1-2 sentences) |
| `tags` | `list[str]` | No | Thematic tags |
| `scope` | `str` | No | `global` or `location` (default: `global`) |
| `credibility` | `str` | No | `rumor`, `likely`, `confirmed` (default: `rumor`) |

**Gotchas:**
- Rumor IDs are referenced by NPCs via `knowledge.rumors`.
- Keep rumor text concise; the Director uses them as narrative hooks.

---

## 11. `facts.yaml` -- Knowledge Graph Facts

**Purpose:** Seed facts for the knowledge graph, expressed as subject-predicate-object triples.

### Top-level

```yaml
facts:
- id: fact_empire_controls_garrisons
  subject: galactic_empire
  predicate: controls
  object: loc-star_destroyer
  confidence: 1.0
```

### Per-Fact Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | **Yes** | Unique fact ID |
| `subject` | `str` | **Yes** | Subject entity (faction ID, NPC ID, etc.) |
| `predicate` | `str` | **Yes** | Relationship verb (e.g., `controls`, `hides_in`, `allied_with`) |
| `object` | `str` | **Yes** | Object entity (location ID, faction ID, etc.) |
| `confidence` | `float` | No | 0.0-1.0 confidence score |

**Gotchas:**
- Fact IDs are referenced by NPCs via `knowledge.secrets`.
- `subject` and `object` should reference valid entity IDs where possible.

---

## 12. `meters.yaml` -- World Meters

**Purpose:** Defines bounds, defaults, and decay rates for persistent world-state meters.

### Structure

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

### Meter Bounds Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `min` | `int` | **Yes** | Minimum value |
| `max` | `int` | **Yes** | Maximum value (must be >= min) |
| `default` | `int` | **Yes** | Starting value (must be within min/max) |
| `decay_per_tick` | `int` | No | How much the meter decays per tick |

### Standard Meters

| Meter | Purpose |
|---|---|
| `reputation_by_faction` | Per-faction reputation (-100 to +100) |
| `heat_global` | Global threat/attention level (0-100) |
| `heat_by_location` | Per-location threat level (0-100) |
| `control_shift` | Territory control mechanics (usually `enabled: false`) |

**Gotchas:**
- `control_shift` uses a different schema (`enabled: false/true`); leave as `{enabled: false}` unless implementing territory control.
- Meter names are referenced by events and the world simulation.

---

## YAML Gotchas

These are common pitfalls when authoring era pack YAML files:

### 1. Boolean Quoting
YAML `false` and `true` are booleans. For string fields that expect `"false"`:
```yaml
# WRONG - parsed as boolean false
bribeable: false

# CORRECT - parsed as string "false"
bribeable: 'false'
```

### 2. Integer Aliases
YAML anchors that look like integers need quoting:
```yaml
# WRONG - parsed as integer 81
anchor: 81

# CORRECT
anchor: "81"
```

### 3. Em Dashes in Strings
Em dashes can break YAML parsing. Single-quote the entire line:
```yaml
# WRONG - may fail
description: The galaxy lives under the boot — crushed and broken.

# CORRECT
description: 'The galaxy lives under the boot -- crushed and broken.'
```

### 4. Colons in Strings
Colons followed by spaces trigger YAML mapping syntax:
```yaml
# WRONG
goal: "War: it never changes"  # This works because it's quoted

# SAFE — always quote strings containing colons
goal: "War: it never changes"
```

### 5. Multiline Strings
Use the `|` (literal block) style for descriptions:
```yaml
description: |
  This preserves newlines.
  Each line is kept as-is.
```

### 6. Starting Starship
In V2.10+, backgrounds no longer grant starting ships:
```yaml
starting_starship: null  # Ships earned in-story
```

### 7. Duplicate IDs
The loader deduplicates by `id`; the last entry wins. Avoid duplicate IDs across `anchors` and `rotating`.

---

## Best Practices for Optimal Gameplay

1. **Location Density:** Aim for 10-20 top-level locations with 2-3 sub-locations each. This gives the Director enough variety without overwhelming the player.

2. **Faction Balance:** Include at least 4-6 factions covering the political spectrum (allied, hostile, neutral, criminal). Always include a `neutral` faction.

3. **NPC Templates:** Create 5-10 templates covering common encounter types (soldiers, merchants, criminals, civilians). These are the backbone of procedural encounters.

4. **Anchor NPCs:** 8-15 canonical named characters. Give them distinct `voice` profiles, meaningful `secrets`, and useful `knowledge` references.

5. **Companions:** 3-6 per era. Ensure diverse `voice_tags`, varied `traits` axes, and staggered `first_meeting_location` values so players encounter them throughout the game.

6. **Backgrounds:** 3-6 backgrounds with 2 questions each. Each question should have 3 choices covering PARAGON / NEUTRAL / RENEGADE tones.

7. **Rumors and Facts:** 5+ rumors, 2+ facts minimum. These feed NPC dialogue and the knowledge graph.

8. **Cross-References:** Ensure all IDs referenced across files actually exist (locations in factions, templates in encounter tables, quests in companion personal quests, etc.).

9. **Description Quality:** Location descriptions should be 3-6 sentences of atmospheric prose. The Narrator uses these directly.

10. **Tag Consistency:** Use consistent tags across locations, NPCs, and factions so spawning and matching work correctly.

---

## Cross-Reference Table: Which Pipeline Nodes Use Which Fields

| File | Field | Used By |
|---|---|---|
| `era.yaml` | `start_location_pool` | Architect (campaign setup) |
| `era.yaml` | `metadata.tone`, `metadata.themes` | Director, Narrator (prompt context) |
| `locations.yaml` | `description` | Narrator (scene prose) |
| `locations.yaml` | `scene_types` | Router (allowed action types) |
| `locations.yaml` | `security` | Mechanic (DC calculations) |
| `locations.yaml` | `services` | Director (available actions) |
| `locations.yaml` | `access_points` | Director (suggestion generation), Mechanic (bypass DCs) |
| `locations.yaml` | `encounter_table` | Encounter node (NPC spawning) |
| `locations.yaml` | `travel_links` | Director (travel suggestions) |
| `locations.yaml` | `keywords` | RAG retrieval (lore matching) |
| `npcs.yaml` (anchors) | `name`, `aliases`, `match_rules` | NarrativeValidator (entity detection) |
| `npcs.yaml` (anchors) | `voice`, `voice_tags` | Director, Narrator (NPC dialogue) |
| `npcs.yaml` (anchors) | `levers` | Director (social interaction options) |
| `npcs.yaml` (anchors) | `knowledge` | Director (information the NPC can reveal) |
| `npcs.yaml` (anchors) | `authority` | Mechanic (access checks) |
| `npcs.yaml` (templates) | `spawn` | Encounter node (NPC spawning) |
| `npcs.yaml` (templates) | `namebank` | NPC generator (name selection) |
| `companions.yaml` | `voice`, `voice_tags` | Narrator (companion dialogue) |
| `companions.yaml` | `traits` | CompanionReaction node (reaction calculation) |
| `companions.yaml` | `influence.triggers` | CompanionReaction (influence deltas) |
| `companions.yaml` | `banter` | BanterManager (banter generation) |
| `companions.yaml` | `recruitment` | Director (recruitment triggers) |
| `companions.yaml` | `enables_affordances` | Director (unlocked actions) |
| `factions.yaml` | `goals` | Director (faction-aware suggestions) |
| `factions.yaml` | `faction_relationships` | Ledger (cascading reputation) |
| `backgrounds.yaml` | `starting_stats` | Architect (character creation) |
| `backgrounds.yaml` | `questions` | Frontend (character creation UI) |
| `backgrounds.yaml` | `effects.thread_seed` | Director (opening narrative hook) |
| `namebanks.yaml` | all pools | NPC generator (name construction) |
| `quests.yaml` | `entry_conditions` | WorldSim (quest activation) |
| `quests.yaml` | `stages` | Director (quest progression) |
| `events.yaml` | `triggers`, `effects` | WorldSim (event firing) |
| `rumors.yaml` | `text`, `tags` | Director (NPC dialogue hooks) |
| `facts.yaml` | triples | KG extractor (knowledge graph seeding) |
| `meters.yaml` | bounds, decay | WorldSim, Mechanic (meter calculations) |
