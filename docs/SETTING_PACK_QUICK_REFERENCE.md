# Setting Pack Quick Reference

This document consolidates all setting pack documentation into a single quick reference guide.

## Overview

Setting Packs are YAML-based content bundles that define the worldbuilding, NPCs, quests, factions, and tone for a specific Star Wars Legends era. Each pack contains 12 files that work together to create a cohesive narrative experience.

**Current Setting Packs:**

- `_template` - Reference structure for creating new packs
- `rebellion` - Galactic Civil War (0 BBY - 4 ABY) - **Canonical reference pack**

**Removed Setting Packs (can be regenerated):**

- `dark_times`, `kotor`, `legacy`, `new_jedi_order`, `new_republic`

---

## Setting Pack Structure

Each setting pack lives in `/data/static/setting_packs/{era_id}/` and contains **12 YAML files**:

| File | Purpose | Required |
| ------ | --------- | ---------- |
| `era.yaml` | Era metadata, time period, tone, galactic state | ✅ Yes |
| `companions.yaml` | Recruitable party members (max 5) | ✅ Yes |
| `quests.yaml` | Quest templates and objectives | ✅ Yes |
| `meters.yaml` | Tracking meters (alignment, stress, etc.) | ✅ Yes |
| `npcs.yaml` | NPC templates for encounters | ✅ Yes |
| `namebanks.yaml` | Name generation banks by species/culture | ✅ Yes |
| `factions.yaml` | Major factions and their goals | ✅ Yes |
| `events.yaml` | Random world events | ✅ Yes |
| `locations.yaml` | Locations with travel links | ✅ Yes |
| `rumors.yaml` | Rumor/gossip generation templates | ✅ Yes |
| `facts.yaml` | World facts and lore snippets | ✅ Yes |
| `backgrounds.yaml` | Character creation backgrounds (SWTOR-style) | ✅ Yes |

---

## Quickstart: Using Setting Packs

### 1. List Available Eras

```bash
curl http://localhost:8000/v2/debug/setting-packs
```

### 2. Get Era Locations

```bash
curl http://localhost:8000/v2/era/rebellion/locations
```

### 3. Get Era Backgrounds

```bash
curl http://localhost:8000/v2/era/rebellion/backgrounds
```

### 4. Get Era Companions

```bash
curl http://localhost:8000/v2/era/rebellion/companions
```

### 5. Create Campaign with Setting Pack

```bash
curl -X POST http://localhost:8000/v2/setup/auto \
  -H "Content-Type: application/json" \
  -d '{

    "time_period": "rebellion",
    "genre": "espionage_thriller",
    "themes": ["trust", "sacrifice"],
    "player_concept": "Rebel spy",
    "background_id": "spy_defector"
  }'
```

---

## File Format Examples

### 1. era.yaml

```yaml
era_id: rebellion
name: "The Rebellion"
time_period: "0 BBY - 4 ABY"
description: "The Galactic Civil War between the Rebel Alliance and the Galactic Empire."

galactic_state:
  primary_conflict: "Rebel Alliance vs. Galactic Empire"
  key_locations: ["Yavin IV", "Hoth", "Endor", "Tatooine"]
  major_events: ["Battle of Yavin", "Battle of Hoth", "Battle of Endor"]

tone:
  mood: "desperate_heroism"
  aesthetic: "lived_in_universe"
  themes: ["hope", "sacrifice", "tyranny_vs_freedom"]
```

### 2. companions.yaml

```yaml
companions:

  - id: comp-cassian

    name: "Cassian Andor"
    species: "Human"
    archetype: "spy"
    motivation: "Will do anything for the Rebellion"
    recruitment_location: "loc-rebel-base"
    voice:
      belief: "The Rebellion needs people who can make hard choices"
      wound: "Killed his own informants to protect the mission"
      rhetorical_style: "Terse, pragmatic, mission-focused"
```

### 3. quests.yaml

```yaml
quests:

  - id: quest-scarif

    title: "Scarif Infiltration"
    description: "Retrieve the Death Star plans from the Imperial archive."
    quest_type: "main_story"
    entry_location: "loc-rebel-base"
    stages:

      - id: stage-1

        description: "Assemble infiltration team"
        success_condition: "recruit_companion:cassian"

      - id: stage-2

        description: "Infiltrate Scarif security perimeter"
        success_condition: "reach_location:loc-scarif-citadel"
```

### 4. backgrounds.yaml

```yaml
backgrounds:

  - id: spy_defector

    name: "Imperial Defector"
    description: "You served the Empire, saw its atrocities, and defected to the Rebellion."
    starting_stats:
      deception: 12
      intelligence: 10
      strength: 8
    questions:

      - id: q1_motivation

        text: "Why did you defect?"
        choices:

          - id: moral_awakening

            label: "Witnessed an Imperial massacre"
            stat_bonus: {wisdom: +2}

          - id: betrayed

            label: "The Empire betrayed you"
            stat_bonus: {charisma: +2}
```

---

## Setting Pack Generation

### Using the Template

1. Copy the `_template` directory:

   ```bash
   cp -r data/static/setting_packs/_template data/static/setting_packs/new_era
   ```

2. Edit `era.yaml` with the new era's metadata

3. Fill in each of the 12 YAML files with era-specific content

4. Validate the pack:

   ```bash
   python scripts/validate_setting_pack.py new_era
   ```

### Regenerating Deleted Setting Packs

The following setting packs were removed but can be regenerated:

```bash
# Using the LLM generation prompt

python -m backend.app.scripts.generate_setting_pack \
  --era_id kotor \
  --time_period "3956 BBY" \
  --primary_conflict "Jedi vs. Sith" \
  --output data/static/setting_packs/kotor
```

Or manually using the template in `/docs/setting_pack_template.md`.

---

## Feature Flags

### ENABLE_BIBLE_CASTING (Default: ON)

When enabled, NPCs are cast from setting pack `npcs.yaml` templates rather than generated by LLM.

```python
ENABLE_BIBLE_CASTING = 1  # Use setting pack deterministic casting
```

**Impact:**

- NPCs are pulled from setting pack `npcs.yaml`
- Factions are derived from `factions.yaml`
- Deterministic, reproducible NPC generation
- No LLM calls for casting

---

## Validation

### Validate Single Setting Pack

```bash
python scripts/validate_setting_pack.py rebellion
```

### Validate All Setting Packs

```bash
python scripts/validate_setting_packs.py
```

### Audit Setting Pack Completeness

```bash
python scripts/audit_setting_packs.py
```

---

## Setting Pack Loader

Era packs are loaded via `/backend/app/world/setting_pack_loader.py`:

```python
from backend.app.world.setting_pack_loader import get_setting_pack

# Load an setting pack

pack = get_setting_pack("rebellion")

# Access components

locations = pack.locations
companions = pack.companions
factions = pack.factions
backgrounds = pack.backgrounds

# Lookup by ID

location = pack.location_by_id("loc-cantina")
companion = pack.companion_by_id("comp-cassian")
background = pack.background_by_id("spy_defector")
```

---

## Schema Reference

For detailed schema documentation, see:

- `/docs/setting_pack_template.md` - Comprehensive template with examples
- `/docs/setting_pack_schema_reference.md` - Schema validation rules
- `/docs/setting_pack_generation_prompt.md` - LLM prompt for automated generation

---

## Design Principles

### 1. Deterministic Content

Era packs provide deterministic content that doesn't require LLM calls. This ensures:

- Consistent worldbuilding across playthroughs
- No LLM downtime impact
- Reproducible for testing
- Lore-accurate to Star Wars Legends

### 2. Bible-Based Casting

NPCs, factions, and locations are defined upfront in the "bible" (setting pack YAML files) rather than procedurally generated. This ensures:

- Canonical character roles (Vader as Villain, Leia as Leader, etc.)
- Faction relationships grounded in lore
- Locations that feel authentic to the era

### 3. Layered Retrieval

Era packs work alongside RAG retrieval:

- **Era pack** provides structure (NPCs, quests, factions)
- **RAG lore retrieval** provides narrative flavor (novel snippets, sourcebook lore)
- **Style guides** provide tone and voice (`/data/style/era/`)

### 4. Modular Expansion

New eras can be added without code changes:

- Drop new YAML bundle into `/data/static/setting_packs/{era_id}/`
- System auto-detects and loads
- UI shows era in selection dropdown

---

## File Size Guidelines

| File | Target Lines | Max Size |
| ------ | -------------- | ---------- |
| `era.yaml` | 30-50 | 2 KB |
| `companions.yaml` | 200-300 (5 companions) | 15 KB |
| `quests.yaml` | 300-500 | 25 KB |
| `meters.yaml` | 100-150 | 8 KB |
| `npcs.yaml` | 500-800 | 40 KB |
| `namebanks.yaml` | 200-400 | 15 KB |
| `factions.yaml` | 150-250 | 12 KB |
| `events.yaml` | 200-300 | 15 KB |
| `locations.yaml` | 400-600 | 30 KB |
| `rumors.yaml` | 300-500 | 20 KB |
| `facts.yaml` | 300-500 | 20 KB |
| `backgrounds.yaml` | 400-600 | 30 KB |

**Total per pack:** ~200-250 KB

---

## Common Patterns

### Location with Travel Links

```yaml
locations:

  - id: loc-cantina

    name: "Mos Eisley Cantina"
    planet: "Tatooine"
    tags: ["cantina", "underworld"]
    threat_level: moderate
    travel_links:

      - to_location_id: loc-spaceport

        travel_time_minutes: 10

      - to_location_id: loc-marketplace

        travel_time_minutes: 15
```

### NPC with Voice Profile

```yaml
npcs:

  - id: npc-vader

    name: "Darth Vader"
    role: "Villain"
    faction: "Galactic Empire"
    voice:
      belief: "Order through strength"
      wound: "Lost everything to the dark side"
      rhetorical_style: "Ominous, commanding, never wastes words"
```

### Quest with Multiple Stages

```yaml
quests:

  - id: quest-rescue-leia

    title: "Rescue Princess Leia"
    stages:

      - id: stage-1

        description: "Infiltrate the Death Star"

      - id: stage-2

        description: "Locate detention block AA-23"

      - id: stage-3

        description: "Escape with Leia"
```

---

## Troubleshooting

### Setting Pack Not Loading

1. Check file naming: all 12 files must be present
2. Validate YAML syntax: `yamllint data/static/setting_packs/{era_id}/`
3. Check era_id consistency across files
4. Verify `ERA_PACK_DIR` environment variable

### NPC Casting Fails

1. Ensure `ENABLE_BIBLE_CASTING=1` in config
2. Verify `npcs.yaml` has at least 12 NPCs
3. Check NPC roles: need Villain, Rival, Merchant, Informant roles
4. Validate faction links in NPCs

### Locations Missing

1. Check `locations.yaml` has safe starting locations (low/moderate threat)
2. Verify travel_links connect to each other
3. Ensure starting_location exists in pack
4. Check location tags don't block starting (no "prison" or "dangerous" tags for safe starts)

---

## See Also

- `/data/static/setting_packs/_template/` - Reference template
- `/data/static/setting_packs/rebellion/` - Canonical example
- `/backend/app/world/setting_pack_loader.py` - Loader implementation
- `/backend/app/world/setting_pack_models.py` - Pydantic models
- `/docs/setting_pack_template.md` - Full template documentation
- `/docs/PACK_AUTHORING.md` - Pack authoring guide
