# Content System

This document describes Storyteller's world-agnostic content architecture.

## Model: `setting_id` + `period_id`

Runtime content is keyed by two normalized identifiers:

- `setting_id`: world/domain key (for example `star_wars_legends`, `lotr`, `got`)
- `period_id`: period key within that setting (for example `rebellion`, `third_age`)

`ContentRepository` loads and caches merged content using `(setting_id, period_id)` keys.

## Pack roots and stacking

Pack roots are resolved from `SETTING_PACK_PATHS` (semicolon-separated). Roots are merged in declaration order.

Default root order (if env var is unset):

1. `./data/static/setting_packs/core`
2. `./data/static/setting_packs/addons`
3. `./data/static/setting_packs/overrides`

For each root, loader looks for:

```text
{root}/{setting_id}/periods/{period_id}/
```text

### Concrete directory tree example

```text
data/static/setting_packs/
  core/
    lotr/
      periods/
        third_age/
          era.yaml
          factions.yaml
          locations.yaml
          npcs.yaml
  addons/
    lotr/
      periods/
        third_age/
          locations/
            rohan.yaml
          quests/
            riders_of_the_mark.yaml
  overrides/
    lotr/
      periods/
        third_age/
          npcs.yaml
```text

## Merge rules

The loader applies deterministic merge behavior:

- **dict + dict** → deep merge (recursive)
- **list + list**:
  - if all entries are dicts with `id`, merge by `id`
  - otherwise, incoming list replaces base list
- **id-based list merge**:
  - matching `id`: deep-merge existing + incoming item
  - new `id`: append
  - `disabled: true`: remove existing item with that `id`

### `extends`

`extends` is resolved post-merge for:

- `npcs.templates`
- `missions.templates`

Rules:

- base item must exist
- cycles are rejected
- child fields deep-merge over inherited base

## Repository and resolvers

### `ContentRepository`

- `get_content(setting_id, period_id)` → merged+validated content
- `get_indices(setting_id, period_id)` → cached indices for fast lookup
- `get_pack(era_id)` → legacy adapter (`era_id` mapped into setting/period)

### Resolvers

- `NpcResolver`
  - scene cast selection from anchors + rotating pool
  - deterministic procedural NPC generation with seeded RNG
- `LocationResolver`
  - location lookup/filtering, graph traversal helpers
- `MissionResolver`
  - authored quest offers + procedural templates from metadata

## Entity ID conventions

Use stable, normalized IDs that are safe for long-term references:

- lowercase snake_case preferred
- globally unique within each section
- avoid semantic churn (do not include mutable display names)
- never recycle IDs for unrelated entities

Recommended prefixes where useful:

- `loc_...` for locations
- `npc_...` for NPC templates/anchors
- `quest_...` for quests
- `faction_...` for factions

## Recommended world-agnostic tags/taxonomy

Use tags for discoverability and resolver filtering, not lore prose.

Suggested tag families:

- **tone**: `optimistic`, `grim`, `mystery`, `political`
- **activity**: `trade`, `combat`, `intrigue`, `exploration`
- **environment**: `urban`, `wilderness`, `frontier`, `underground`
- **social layer**: `elite`, `criminal`, `military`, `religious`
- **risk level**: `safe`, `contested`, `hostile`

Guidelines:

- keep tags short and reusable
- prefer controlled vocab over ad hoc synonyms
- document new tag families in pack-level docs

## Legacy compatibility

If no new-layout pack is found and `setting_id == DEFAULT_SETTING_ID`, loader falls back to `ERA_PACK_DIR` legacy era packs.

Use this for migration only; new content should target setting-pack layout.

## Related docs

- [PACK_AUTHORING](./PACK_AUTHORING.md)
- [RUNBOOK](./RUNBOOK.md)
- [MIGRATION_FROM_ERA_PACKS](./MIGRATION_FROM_ERA_PACKS.md)
