# Runbook

Operational reference for running Storyteller AI locally with the setting-pack content system.

## Local startup

### Option A: unified dev command

```bash
python -m storyteller dev
```

Starts backend (uvicorn) and UI (SvelteKit) where possible.

### Option B: run services separately

Backend:

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --port 5173
```

## Environment variables

### Content system

- `SETTING_PACK_PATHS`
  - semicolon-separated pack roots in merge order
  - default: `./data/static/setting_packs/core;./data/static/setting_packs/addons;./data/static/setting_packs/overrides`
- `DEFAULT_SETTING_ID`
  - used by legacy-era adapter and default fallback lookups
  - default: `star_wars_legends`
- `ERA_PACK_DIR`
  - legacy fallback directory
  - default: `./data/static/era_packs`
- `ERA_TO_SETTING_PERIOD_MAP`
  - optional YAML path for explicit legacy `era_id` -> (`setting_id`, `period_id`) mapping

### Runtime/API

- `STORYTELLER_DB_PATH` (SQLite path)
- `VECTORDB_PATH` (LanceDB directory)
- `STORYTELLER_DEV_MODE` (default dev behavior)
- `STORYTELLER_API_TOKEN` (required for non-dev authenticated mode)
- `STORYTELLER_CORS_ALLOW_ORIGINS` (comma-separated origins)

### Feature flags (commonly used)

- `ENABLE_BIBLE_CASTING`
- `ENABLE_PROCEDURAL_NPCS`
- `ENABLE_SUGGESTION_REFINER`

## Validation steps

### Validate all discovered setting packs

```bash
python scripts/validate_setting_packs.py
```

### Validate specific roots only

```bash
python scripts/validate_setting_packs.py --paths "./data/static/setting_packs/core;./data/static/setting_packs/overrides"
```

### Run backend tests

```bash
python -m pytest backend/tests -q
```

## Common operational issues

### 1) `No setting pack found ...`

- Verify `SETTING_PACK_PATHS` is set and points to existing directories.
- Verify directory shape is `{root}/{setting_id}/periods/{period_id}/`.
- Verify normalized naming (loader normalizes keys to lowercase snake-like identifiers).

### 2) Validation script reports per-pack `ERR`

Typical causes:

- malformed YAML
- duplicate/broken IDs
- missing `extends` base
- cyclic `extends`

Fix pack data and re-run validator.

### 3) Legacy data unexpectedly loaded

If new layout is absent and setting equals `DEFAULT_SETTING_ID`, loader can fall back to `ERA_PACK_DIR`. Add explicit setting-pack roots or update env configuration.

### 4) `storyteller dev` does not launch UI

- ensure Node.js/npm is installed
- ensure `frontend/` exists
- run frontend manually to inspect npm errors

## Cross-references

- [README](../README.md)
- [CONTENT_SYSTEM](./CONTENT_SYSTEM.md)
- [PACK_AUTHORING](./PACK_AUTHORING.md)
- [MIGRATION_FROM_ERA_PACKS](./MIGRATION_FROM_ERA_PACKS.md)
