# Migration from Era Packs to Setting Packs

This project historically used `era_id` and `data/static/era_packs/...` paths.

The current content system is world-agnostic and uses:

- `setting_id`
- `period_id`
- stackable roots via `SETTING_PACK_PATHS`

Legacy-era loading still exists for compatibility, but migration to setting packs is recommended.

## What changed

## Naming

- **Old**: era, era pack, `era_id`
- **New**: setting + period, setting pack, (`setting_id`, `period_id`)

## Pathing

- **Old**: `data/static/era_packs/{era_id}/...`
- **New**: `{pack_root}/{setting_id}/periods/{period_id}/...`

Where `pack_root` is one entry in `SETTING_PACK_PATHS`.

## Loading model

- **Old**: single directory selected by era
- **New**: layered merge from multiple roots (`core -> addons -> overrides`)

## Resolver/data access

- **Old style callers** can still pass `era_id`
- **New style callers** should pass `setting_id` + `period_id`

## Migration mapping approach

Use this practical mapping:

- old `era_id` value -> new `period_id`
- choose a `setting_id` (for existing content: usually `star_wars_legends`)

Example:

- `era_id=rebellion` -> `(setting_id=star_wars_legends, period_id=rebellion)`

## Step-by-step migration

1. **Create root structure**

```text
data/static/setting_packs/core/star_wars_legends/periods/rebellion/
```text

2. **Copy existing files** from `data/static/era_packs/rebellion/` into the new period folder.

3. **Keep filenames/sections consistent** (`era.yaml`, `locations.yaml`, `npcs.yaml`, etc.).

4. **Introduce addons/overrides gradually** into separate roots instead of editing core content directly.

5. **Validate**:

```bash
python scripts/validate_setting_packs.py
```text

6. **Optionally define explicit mappings** with `ERA_TO_SETTING_PERIOD_MAP` YAML while callers still pass `era_id`.

## Common migration mistakes and fixes

### Mistake: wrong directory shape

- **Symptom**: `No setting pack found for setting='...' period='...'`
- **Fix**: ensure path is `{root}/{setting_id}/periods/{period_id}/...`

### Mistake: using commas in `SETTING_PACK_PATHS`

- **Symptom**: roots not discovered
- **Fix**: use semicolons (`;`) as delimiter

### Mistake: duplicate IDs across layers without intent

- **Symptom**: unexpected merged fields
- **Fix**: review id-based merge behavior; use explicit override files and clear IDs

### Mistake: broken `extends`

- **Symptom**: validation/loader errors about missing base or cycle
- **Fix**: ensure base exists in merged result and inheritance graph is acyclic

### Mistake: forgetting fallback behavior

- **Symptom**: app still works but loads legacy content
- **Fix**: configure `SETTING_PACK_PATHS` and ensure those directories exist before relying on results

## Recommended rollout

- migrate one period at a time
- validate after each period
- keep legacy paths only as temporary safety net
- switch integrations to `setting_id` + `period_id` inputs

## Related docs

- [CONTENT_SYSTEM](./CONTENT_SYSTEM.md)
- [PACK_AUTHORING](./PACK_AUTHORING.md)
- [RUNBOOK](./RUNBOOK.md)
