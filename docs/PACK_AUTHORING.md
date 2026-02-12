# Pack Authoring Guide

This guide explains how to create and evolve setting packs using the `setting_id` + `period_id` model.

For architecture details, start with [CONTENT_SYSTEM](./CONTENT_SYSTEM.md).

## 1) Add a new setting (example: LOTR or GOT)

Pick a stable `setting_id` and create it under one or more pack roots.

Example (`lotr` in core root):

```text
data/static/setting_packs/core/
  lotr/
    periods/
      third_age/
        era.yaml
        locations.yaml
        npcs.yaml
        quests.yaml
```text

Minimum practical starting files:

- `era.yaml` (or `manifest.yaml` / `pack.yaml`) with top-level pack metadata
- `locations.yaml`
- `npcs.yaml`
- `quests.yaml`

> The loader accepts `manifest.yaml`, `era.yaml`, or `pack.yaml` as the base file.

## 2) Add a new period to an existing setting

Create a new period directory:

```text
data/static/setting_packs/core/lotr/periods/war_of_the_ring/
```text

Then add the same section files (`era.yaml`, `locations.yaml`, etc.) for that period.

## 3) Addons and overrides

Layer additional content without modifying core files.

### Addon example

```text
data/static/setting_packs/addons/lotr/periods/third_age/locations/rohan.yaml
```text

This appends or merges location objects by `id`.

### Override example

```yaml
# data/static/setting_packs/overrides/lotr/periods/third_age/npcs.yaml

npcs:
  templates:
    - id: npc_ranger_generic

      disabled: true
    - id: npc_ranger_veteran

      extends: npc_ranger_base
      role: scout_captain
      tags: [wilderness, elite]
```text

What this does:

- removes `npc_ranger_generic` from merged output
- creates/updates `npc_ranger_veteran` by extending `npc_ranger_base`

## 4) Concrete layering example (core + addon + override)

Assume this root order:

```bash
SETTING_PACK_PATHS="./data/static/setting_packs/core;./data/static/setting_packs/addons;./data/static/setting_packs/overrides"
```text

Merge flow for `(setting_id=lotr, period_id=third_age)`:

1. Load base entities from `core/lotr/periods/third_age`
2. Merge additive records from `addons/lotr/periods/third_age`
3. Apply last-mile patches/removals from `overrides/lotr/periods/third_age`

Result is deterministic and cached by `ContentRepository`.

## 5) Best practices

- **Small files**: prefer section subdirectories (`locations/*.yaml`, `quests/*.yaml`) for manageable diffs.
- **Stable IDs**: never change IDs casually; references depend on them.
- **Deterministic naming**: avoid random or date-based IDs.
- **Explicit tags**: use controlled vocab and keep tags world-agnostic.
- **Use `extends` intentionally**: inherit shared templates, override only what changes.
- **Use `disabled: true` for removals**: safer than deleting base records in shared roots.

## 6) Validate while authoring

Run validator after any pack change:

```bash
python scripts/validate_setting_packs.py
```text

Validate against specific roots:

```bash
python scripts/validate_setting_packs.py --paths "./data/static/setting_packs/core;./data/static/setting_packs/overrides"
```text

## 7) Legacy-era interoperability

Legacy `era_id` callers still work via adapter mapping to `(setting_id, period_id)`. Prefer new APIs/data paths for all new content.

See migration details in [MIGRATION_FROM_ERA_PACKS](./MIGRATION_FROM_ERA_PACKS.md).
