# Setting Pack Generation Prompt Template

Use this prompt with Claude, Gemini, or GPT to generate a new setting pack YAML file.
Replace all `{{PLACEHOLDER}}` values before submitting.

---

## PROMPT

You are a Star Wars Legends game designer building an setting pack for a text-based narrative RPG set in the **{{ERA_NAME}}** era (approximately {{TIMEFRAME}}).

The game is similar to Mass Effect / KOTOR: the player explores locations, talks to NPCs, makes choices that affect faction standings, and engages in combat/stealth/social encounters. Each turn, a Director agent picks narrative beats and suggests 3 player actions, and a Narrator agent writes the scene prose.

### YOUR TASK

Generate a complete setting pack in YAML format following the exact schema below. This is a one-time game design artifact — prioritize characters and locations that create interesting **gameplay dynamics** (faction tension, moral dilemmas, information brokering, shifting loyalties) over encyclopedic completeness.

### DESIGN GUIDELINES

1. **NPCs (15-25 total):**
   - **Anchors (8-12):** Major characters always present. Mix of allies, antagonists, and wildcards. Must include at least one from each major faction.
   - **Rotating (5-10):** Characters that cycle in/out based on story progression. Good for recurring encounters without overpopulating scenes.
   - **Templates (5-8):** Anonymous NPC generators (patrols, merchants, informants) that spawn dynamically with randomized names/motivations. Include at least one per faction + some civilian/neutral templates.

2. **Factions (4-7):** Include the major power players plus at least one underworld/neutral faction. Every faction needs clear goals that can conflict with other factions.

3. **Locations (6-10):** Hub locations where gameplay happens. Include at least one per major faction plus neutral ground. Each needs a distinct gameplay purpose (cantina for intel, market for trade, military base for heists, etc.).

4. **Namebanks:** Provide 10+ names per pool. Create separate pools for each major faction/species grouping.

5. **Character Design:**
   - `traits`: Exactly 3 adjectives that define behavior in dialogue and NPC rendering
   - `motivation`: One sentence — what drives them THIS era, not their whole biography. This gets stored and used by the NPC renderer for intro text.
   - `secret`: A hidden element discoverable through gameplay — creates quest hooks. This is passed to the Director/Narrator but hidden from the player until discovered.
   - `voice_tags`: 2-3 tags for speech pattern generation (e.g., "clipped", "formal", "drawling"). Used by the NPC renderer.
   - `archetype`: A 2-4 word role description (e.g., "Reluctant spy", "Idealistic commander"). Shown to the Director as companion context.
   - `species`: The character's species. Affects NPC rendering. Use "Human" if human.
   - `home_locations`: 2-3 location IDs where this NPC can appear. The first one should be their primary haunt. This lets NPCs show up in multiple places organically.

6. **Match Rules:** For NPC name detection in player input (ingestion-time only):
   - `min_tokens: 2` for most characters (requires two-word match like "Han Solo")
   - `allow_single_token: true` only for very distinctive single names (e.g., "Vader", "Thrawn", "Yoda", "Chewbacca")
   - `require_surname: true` when first name alone is too common or ambiguous
   - `case_sensitive: false` (default, almost never change this)
   - Use `banned_aliases` to prevent overmatch on generic titles (e.g., "Chancellor", "Agent", "Commander" alone should NOT match a specific NPC)

7. **Faction Design:**
   - `tags`: The tag `hostile` has runtime meaning — factions tagged `hostile` start as enemies to the player. Use deliberately.
   - `goals`: List 2-3 goals. The FIRST goal becomes the faction's initial `current_goal` at campaign start. Make it actionable and specific.
   - `hostility_matrix`: A map of `{other_faction_id: score}` where scores range from -100 (sworn enemies) to +100 (close allies). 0 is neutral. This drives faction dynamics — overlapping hostilities create gameplay tension.

8. **Location Design:**
   - `description`: One evocative sentence describing the atmosphere. Used by the Narrator for scene-setting.
   - `threat_level`: One of `low`, `moderate`, `high`, `extreme`. Guides encounter difficulty.
   - `controlling_factions`: Which faction(s) control this area. Affects which NPCs spawn here and patrol behavior.
   - `tags`: Semantic tags used to match NPCs to locations during encounter selection. An NPC with tag "docks" is more likely to appear at a location tagged "docks".

### EXACT YAML SCHEMA

```yaml
era_id: {{ERA_ID}}          # UPPERCASE, e.g., REBELLION, OLD_REPUBLIC, CLONE_WARS
style_ref: data/style/{{era_id_lowercase}}_style.md

factions:
  - id: faction_slug         # lowercase_with_underscores
    name: "Human Readable Name"
    tags: [tag1, tag2]       # IMPORTANT: "hostile" tag means enemy to player at start
    home_locations: [loc-slug1, loc-slug2]
    goals:
      - "FIRST goal becomes initial current_goal — make it specific and actionable"
      - "Secondary goal that creates tension with other factions"
    hostility_matrix:        # Score per other faction: -100 (enemies) to +100 (allies)
      other_faction_id: -80
      another_faction_id: 30

locations:
  - id: loc-slug             # Always prefixed with "loc-"
    name: "Human Readable Name"
    tags: [tag1, tag2]       # Semantic tags (tavern, market, imperial, etc.)
    region: "Region Name"    # Outer Rim, Core, Mid Rim, Inner Rim, Unknown Regions, Mobile
    controlling_factions: [faction_slug]
    description: "One evocative sentence describing atmosphere and feel"
    threat_level: moderate   # low, moderate, high, extreme

npcs:
  anchors:
    - id: character_slug     # lowercase_with_underscores, matches character_aliases.yml
      name: "Full Name"
      aliases: ["Title Name", "Short Name"]     # How the character might be referred to
      banned_aliases: ["Title"]                  # Generic titles that should NOT match alone
      tags: [faction_tag, role_tag]
      faction_id: faction_slug
      default_location_id: loc-slug              # Primary spawn point
      home_locations: [loc-slug, loc-other]      # All locations this NPC can appear
      role: "Role Title"
      archetype: "2-4 word archetype"
      species: "Species Name"                    # Human, Twi'lek, Wookiee, etc.
      match_rules:
        min_tokens: 2
        allow_single_token: false
        # require_surname: true                  # Only if needed
      traits: ["adjective1", "adjective2", "adjective3"]   # Exactly 3
      motivation: "One sentence — what drives them now"
      secret: "Hidden element the player can discover"
      voice_tags: ["tag1", "tag2"]

  rotating:
    # Same structure as anchors

  templates:
    - id: template_slug
      role: "Role Title"
      archetype: "2-4 word archetype"
      traits: ["trait1", "trait2", "trait3"]
      motivations:           # Plural — multiple options for randomization
        - "motivation option 1"
        - "motivation option 2"
        - "motivation option 3"
      secrets:               # Plural — multiple options for randomization
        - "secret option 1"
        - "secret option 2"
      voice_tags: ["tag1", "tag2"]
      species: ["Species1", "Species2"]    # List — one picked randomly per spawn
      tags: [faction_tag, role_tag]        # Must overlap with location tags for matching
      namebank: namebank_id

namebanks:
  faction_names: ["Name1", "Name2", "Name3", "Name4", "Name5",
                   "Name6", "Name7", "Name8", "Name9", "Name10"]
```

### AVAILABLE KNOWLEDGE GRAPH DATA

After running KG extraction on the {{ERA_NAME}} novels, here are the top entities by relationship count. Use this data to inform your NPC and location selections:

{{PASTE_KG_CANDIDATE_REPORT_HERE}}

To generate this report after KG extraction, run:

```python
python -c "
from backend.app.kg.store import KGStore
store = KGStore('data/storyteller.db')
# Top characters by relationship count
chars = store.get_entities_by_type('CHARACTER', era='{{era_id_lowercase}}')
for c in sorted(chars, key=lambda x: len(store.get_triples_for_entity(x['id'], era='{{era_id_lowercase}}')), reverse=True)[:30]:
    triples = store.get_triples_for_entity(c['id'], era='{{era_id_lowercase}}')
    print(f\"{c['canonical_name']}: {len(triples)} relationships\")
print()
# Top locations
locs = store.get_entities_by_type('LOCATION', era='{{era_id_lowercase}}')
for l in sorted(locs, key=lambda x: len(store.get_triples_for_entity(x['id'], era='{{era_id_lowercase}}')), reverse=True)[:15]:
    triples = store.get_triples_for_entity(l['id'], era='{{era_id_lowercase}}')
    print(f\"{l['canonical_name']}: {len(triples)} associations\")
print()
# Factions
facs = store.get_entities_by_type('FACTION', era='{{era_id_lowercase}}')
for f in sorted(facs, key=lambda x: len(store.get_triples_for_entity(x['id'], era='{{era_id_lowercase}}')), reverse=True)[:10]:
    triples = store.get_triples_for_entity(f['id'], era='{{era_id_lowercase}}')
    print(f\"{f['canonical_name']}: {len(triples)} connections\")
"
```

### CONSTRAINTS

- Every `faction_id` referenced by an NPC must exist in the `factions` list.
- Every `default_location_id` and every entry in `home_locations` must exist in the `locations` list.
- Every `namebank` referenced by a template must exist in `namebanks`.
- NPC `id` values must use `lowercase_with_underscores` format (e.g., `luke_skywalker`, `darth_vader`).
- Location `id` values must be prefixed with `loc-` (e.g., `loc-cantina`, `loc-bridge`).
- Faction `id` values use `lowercase_with_underscores` (e.g., `rebel_alliance`, `galactic_empire`).
- Do not invent characters or locations that don't exist in Star Wars Legends canon for this era.
- Focus on characters that appear across multiple novels — they have the richest relationship networks for gameplay.
- `hostility_matrix` must be symmetric-ish: if A hates B at -80, B should hate A at roughly -80 too (small asymmetry is fine for flavor).
- Template `tags` should overlap with location `tags` so the encounter system can match them. A "patrol" template with tag "street" will appear at locations tagged "street".
- Output ONLY the YAML. No commentary, no markdown fences, no explanation.

### REFERENCE: EXISTING REBELLION SETTING PACK STATS

For calibration, here is what the existing Rebellion setting pack contains:

- 6 factions (2 Imperial, 1 Rebel, 1 Underworld, 1 Civilian Resistance, 1 Corporate)
- 9 locations (3 low threat, 3 moderate, 2 high, 1 extreme)
- 8 anchor NPCs, 9 rotating NPCs, 8 templates
- 4 namebanks (rebel, imperial, underworld, droid) with 10 names each

---

## POST-GENERATION CHECKLIST

After receiving the YAML output:

1. Save as `data/static/era_packs/{{era_id_lowercase}}.yaml`
2. Validate with: `python -c "from backend.app.world.era_pack_loader import load_era_pack; print(load_era_pack('{{ERA_ID}}'))"`
3. Verify all cross-references:
   - Every NPC `faction_id` exists in `factions`
   - Every NPC `default_location_id` and `home_locations` entry exists in `locations`
   - Every template `namebank` exists in `namebanks`
4. Add character aliases to `data/character_aliases.yml` for any new NPCs
5. Review and tune:
   - `hostility_matrix` values — are the faction dynamics interesting?
   - `secret` fields — are they specific enough to create quest hooks?
   - `motivation` fields — do they create conflicting interests between NPCs?
   - `description` on locations — are they atmospheric and distinct?
   - `threat_level` on locations — do they create a gradient from safe havens to dangerous zones?
6. Adjust `match_rules` based on how distinctive each character's name is
7. Run `storyteller doctor` to validate the full setting pack loads correctly
8. Run tests: `pytest backend/tests/` to verify no regressions
