# Era Pack V2 Migration Guide

## Overview

This guide covers migrating all era packs to the V2 schema with full gameplay-grade metadata.

## Status

| Era Pack | Status | Date | Report |
|----------|--------|------|--------|
| Rebellion | ✅ Complete | Feb 2026 | [Report](REBELLION_V2_MIGRATION_REPORT.md) |
| New Republic | ⏳ Pending | - | - |
| New Jedi Order | ⏳ Pending | - | - |
| Legacy | ⏳ Pending | - | - |

## Quick Start

### 1. Backup First (Manual)

```bash
# Create a timestamped backup of the entire era_packs directory
cd data/static
tar -czf era_packs_backup_$(date +%Y%m%d_%H%M%S).tar.gz era_packs/
```

### 2. Run Migration Script

```bash
# Dry-run first (preview changes)
python tools/migrate_rebellion_pack_v2.py --dry-run

# Apply migration
python tools/migrate_rebellion_pack_v2.py

# Validate only (no changes)
python tools/migrate_rebellion_pack_v2.py --report-only
```

### 3. Review Manual Authoring Report

Check the console output for "MANUAL AUTHORING NEEDED" section. All flagged items should be reviewed by a human author.

### 4. Test Load

```python
from backend.app.world.era_pack_loader import load_era_pack
pack = load_era_pack("rebellion")
print(f"✓ Loaded {len(pack.locations)} locations, {len(pack.all_npcs())} NPCs")
```

### 5. Run Backend Tests

```bash
python -m pytest backend/tests/ -q --tb=short
```

Expected: 515+ tests passing (V2.17 baseline)

## Migration Script Details

### Features

- **Idempotent**: Safe to run multiple times (skips already-enriched data)
- **Deterministic**: Same input → same output (no randomness)
- **Backup-safe**: Creates `.bak` files automatically
- **Validates**: Checks schema conformance after migration
- **Reports**: Lists items needing manual authoring

### What It Does

#### 1. Location Enrichment

- **Keywords**: Adds 5-12 grounding phrases based on location type
- **Scene Types**: Infers from location type/tags (dialogue, stealth, combat, travel, investigation)
- **Access Points**: Adds 1-2 entry points with bypass methods
- **Encounter Table**: Builds weighted table by matching location tags to NPC template tags

#### 2. NPC Enrichment

- **Voice Metadata**: Adds 5 fields (belief, wound, taboo, rhetorical_style, tell) to all NPCs
- **Spawn Rules**: Adds spawn conditions to templates/rotating NPCs (location_tags, alert range)

#### 3. Starter Content Creation

- **Rumors**: Generates 5-10 rumors if file is empty
- **Events**: Generates 2-3 events if file is empty
- **Quests**: Generates 1 starter quest if file is empty
- **Facts**: Generates 2-5 facts if file is empty

#### 4. Era Index Update

- Updates `era.yaml` file_index to reference all pack files

### Enrichment Logic

#### Location Keywords

Deterministic mappings by location type:

```python
LOCATION_TYPE_KEYWORDS = {
    "garrison": ["ID scanners", "durasteel corridors", "patrol boots", "sealed doors", "security lights"],
    "checkpoint": ["checkpoint scanners", "ID verification", "uniformed guards", "inspection zone", "clearance codes"],
    "cantina": ["stale smoke", "low music", "back booths", "credit chips", "watchful eyes"],
    "base": ["briefing boards", "hangar fuel", "quiet urgency", "patched uniforms", "coded comms"],
    # ... etc
}
```

Supplemented with: tags, region, planet, threat_level (unique, capped at 12 total)

#### NPC Voice Defaults

Role-based templates:

```python
ROLE_VOICE_DEFAULTS = {
    "imperial": {
        "belief": "Order must be maintained at all costs.",
        "wound": "They learned that dissent is punished swiftly.",
        "taboo": "disloyalty",
        "rhetorical_style": "coldly_practical",
        "tell": "stands rigidly at attention",
    },
    "rebel": {
        "belief": "Freedom is worth any sacrifice.",
        "wound": "They've lost comrades to Imperial cruelty.",
        "taboo": "betraying the cause",
        "rhetorical_style": "earnest",
        "tell": "glances over shoulder habitually",
    },
    # ... etc
}
```

#### Access Points

Type-based patterns:

```python
LOCATION_TYPE_ACCESS_POINTS = {
    "garrison": [
        {"id": "main_gate", "type": "door", "visibility": "public", "bypass_methods": ["credential", "bribe", "charm"]},
        {"id": "service_entrance", "type": "door", "visibility": "restricted", "bypass_methods": ["stealth", "hack", "disable"]},
    ],
    # ... etc
}
```

#### Encounter Tables

Weighted scoring:
1. Match location tags to NPC template tags
2. Score by number of overlapping tags
3. Sort descending by weight
4. Take top 5 matches
5. Ensure minimum 3 entries with fallback templates

## Migrating Other Era Packs

### Option 1: Generalize the Script

Update `migrate_rebellion_pack_v2.py` to accept a command-line argument for pack name:

```python
# Add to argparse
parser.add_argument("--pack", default="rebellion", help="Era pack to migrate (rebellion, new_republic, etc)")

# Update in main()
pack_dir = Path(__file__).parent.parent / "data" / "static" / "era_packs" / args.pack
```

Then run:

```bash
python tools/migrate_rebellion_pack_v2.py --pack new_republic
python tools/migrate_rebellion_pack_v2.py --pack new_jedi_order
python tools/migrate_rebellion_pack_v2.py --pack legacy
```

### Option 2: Copy and Customize

For era-specific enrichment logic:

```bash
cp tools/migrate_rebellion_pack_v2.py tools/migrate_new_republic_pack_v2.py
# Edit pack_dir, update ROLE_VOICE_DEFAULTS for New Republic era NPCs
python tools/migrate_new_republic_pack_v2.py
```

### Option 3: Batch Migration

Create a wrapper script:

```bash
#!/bin/bash
for pack in rebellion new_republic new_jedi_order legacy; do
    echo "Migrating $pack..."
    python tools/migrate_pack_v2.py --pack "$pack"
done
```

## Schema Reference

### V2 Required Fields

#### Location (EraLocation)

```yaml
id: str
name: str
tags: list[str]
scene_types: list[str]  # ← V2 required
security:               # ← V2 required
  controlling_faction: str | null
  security_level: int (0-100)
  patrol_intensity: str (low/medium/high)
  inspection_chance: str (low/medium/high)
services: list[str]     # ← V2 optional but recommended
access_points:          # ← V2 required
  - id: str
    type: str
    visibility: str
    bypass_methods: list[str]
encounter_table:        # ← V2 required
  - template_id: str
    weight: int
keywords: list[str]     # ← V2 required (5-12 recommended)
```

#### NPC Entry (EraNpcEntry)

```yaml
id: str
name: str
tags: list[str]
voice:                  # ← V2 required
  belief: str
  wound: str
  taboo: str
  rhetorical_style: str
  tell: str
spawn:                  # ← V2 optional (for rotating)
  location_tags_any: list[str]
  location_types_any: list[str]
  min_alert: int (0-100)
  max_alert: int (0-100)
levers:                 # ← V2 required
  bribeable: str (low/medium/high/false)
  intimidatable: str
  charmable: str
authority:              # ← V2 required
  clearance_level: int (0-5)
  can_grant_access: list[str]
knowledge:              # ← V2 required
  rumors: list[str]
  quest_facts: list[str]
  secrets: list[str]
```

#### NPC Template (EraNpcTemplate)

Same as EraNpcEntry but:
- `spawn` is REQUIRED for templates
- `name` field is NOT present (generated at runtime from namebank)

#### Era Index (era.yaml)

```yaml
era_id: str
schema_version: 2
file_index:             # ← V2 required
  era: era.yaml
  locations: locations.yaml
  npcs: npcs.yaml
  factions: factions.yaml
  backgrounds: backgrounds.yaml
  namebanks: namebanks.yaml
  meters: meters.yaml
  rumors: rumors.yaml
  events: events.yaml
  quests: quests.yaml
  facts: facts.yaml     # ← optional
start_location_pool: list[str]
```

## Validation Checks

The migration script validates:

1. **ID References**
   - faction_id → factions
   - location_id → locations
   - template_id → templates
   - rumor_id → rumors
   - quest_id + stage_id → quests.stages

2. **Bounds**
   - security_level: 0-100
   - min_alert / max_alert: 0-100
   - clearance_level: 0-5
   - encounter_table weights: > 0

3. **Token Validation**
   - bypass_methods: in ALLOWED_BYPASS_METHODS
   - scene_types: in ALLOWED_SCENE_TYPES
   - services: in ALLOWED_SERVICES

4. **Required Fields**
   - All locations have keywords (5+)
   - All locations have scene_types (1+)
   - All locations have access_points (1+)
   - All locations have encounter_table (1+)
   - All NPCs have voice field
   - All templates have spawn field

## Troubleshooting

### "Unknown bypass_methods token: X"

Add the token to `ALLOWED_BYPASS_METHODS` in `backend/app/world/era_pack_models.py`.

Current allowed: violence, sneak, stealth, climb, bribe, charm, intimidate, deception, credential, hack, slice, disable, force

### "encounter_table references missing npc template id: X"

The location's encounter_table references a template that doesn't exist. Either:
1. Add the template to `npcs.yaml` → templates
2. Remove the encounter_table entry
3. Replace with a valid template_id

### "NPC X: missing voice field"

The NPC was not enriched. Re-run migration or manually add voice block:

```yaml
voice:
  belief: "..."
  wound: "..."
  taboo: "..."
  rhetorical_style: "..."
  tell: "..."
```

### "Location X: insufficient keywords"

Add more keywords manually or re-run migration with updated LOCATION_TYPE_KEYWORDS mapping.

### Validation passes but pack won't load

Check `backend/app/world/era_pack_loader.py` logs:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
from backend.app.world.era_pack_loader import load_era_pack
pack = load_era_pack("rebellion")
```

## Manual Authoring Priorities

After migration, prioritize manual review for:

### High Priority (Player-facing NPCs)

- Legendary NPCs (Luke, Leia, Han, Vader, etc.)
- Faction leaders (Mon Mothma, Admiral Ackbar, Tarkin, etc.)
- Quest-critical NPCs (any NPC referenced in quests)

### Medium Priority (Common Encounters)

- Templates that spawn frequently (stormtrooper_patrol, rebel_operative, smuggler, cantina_patron)
- Named NPCs in starting locations

### Low Priority (Rare/Background)

- Rotating NPCs with rare spawn conditions
- Background NPCs (dockworkers, protocol droids, etc.)

## File-by-File Checklist

After migrating an era pack, verify each file:

- [ ] `era.yaml`: file_index complete, start_location_pool has valid IDs
- [ ] `locations.yaml`: All 30+ locations have keywords, scene_types, access_points, encounter_table
- [ ] `npcs.yaml`: All NPCs (anchors + rotating + templates) have voice field
- [ ] `factions.yaml`: No changes needed (already V2-compatible)
- [ ] `backgrounds.yaml`: No changes needed
- [ ] `namebanks.yaml`: No changes needed
- [ ] `meters.yaml`: Exists with bounds defined
- [ ] `rumors.yaml`: Has 5+ starter rumors
- [ ] `events.yaml`: Has 2+ starter events
- [ ] `quests.yaml`: Has 1+ starter quest
- [ ] `facts.yaml`: Has 2+ starter facts (optional)

## Testing Checklist

- [ ] Script runs without errors
- [ ] Validation passes (no Pydantic errors)
- [ ] Pack loads successfully (load_era_pack works)
- [ ] Backend tests pass (pytest)
- [ ] First campaign turn completes successfully
- [ ] Encounter spawning works
- [ ] NPC dialogue uses voice metadata
- [ ] Location affordances surface access_points
- [ ] Quest system tracks quest stages

## References

- **Migration Script**: `tools/migrate_rebellion_pack_v2.py`
- **Schema Models**: `backend/app/world/era_pack_models.py`
- **Pack Loader**: `backend/app/world/era_pack_loader.py`
- **Rebellion Report**: `tools/REBELLION_V2_MIGRATION_REPORT.md`
- **Project Memory**: `MEMORY.md` (V2.17 section)

## Support

If you encounter issues:

1. Check this guide first
2. Review Rebellion migration report for examples
3. Check CLAUDE.md for architectural constraints
4. Review backend/tests/ for schema examples
5. Create issue with: error message, pack name, file snippet

## Changelog

- **2026-02-09**: Initial version (Rebellion pack migrated)
- **2026-02-09**: Added "stealth" to ALLOWED_BYPASS_METHODS
- **2026-02-09**: Created comprehensive migration guide
