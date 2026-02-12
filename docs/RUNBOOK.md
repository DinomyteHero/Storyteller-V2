# Runbook

Operational reference for running Storyteller AI locally with the V2.20 Era Pack system.

## Local startup

### Option A: unified launcher (recommended)

```bash
python run_app.py --dev
```text

Starts backend and frontend with development reload behavior.

### Option B: run services separately

Backend:

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```text

Frontend:

```bash
cd frontend
npm install
npm run dev -- --port 5173
```text

### Option C: CLI launcher

```bash
python -m storyteller dev
```text

Useful if you prefer CLI-based orchestration.

## Environment variables

### Core paths

- `DEFAULT_DB_PATH` — SQLite file path (default `./storyteller.db`)
- `VECTORDB_PATH` — LanceDB directory (default `./data/lancedb`)
- `ERA_PACK_DIR` — Era pack directory (default `./data/static/era_packs`)
- `OLLAMA_BASE_URL` — Ollama server URL (default `http://localhost:11434`)

### Runtime/API

- `STORYTELLER_DEV_MODE` — dev behavior toggles
- `STORYTELLER_API_TOKEN` — required for non-dev authenticated mode
- `STORYTELLER_CORS_ALLOW_ORIGINS` — comma-separated origins

### Feature flags (commonly used)

- `ENABLE_BIBLE_CASTING`
- `ENABLE_PROCEDURAL_NPCS`
- `ENABLE_SUGGESTION_REFINER`
- `ENABLE_CHARACTER_FACETS` (experimental)

## Validation steps

### Validate era packs

```bash
python scripts/validate_era_packs.py
```text

### Validate custom pack roots

```bash
python scripts/validate_era_pack.py --paths "./data/static/era_packs"
```text

### Run backend tests

```bash
python -m pytest backend/tests -q
```text

## Common operational issues

### 1) `No such era pack ...`

- Verify `ERA_PACK_DIR` points to an existing directory.
- Check expected structure: `{ERA_PACK_DIR}/{era_id}/{file}.yaml`.
- Confirm the era includes all required files (use validators above).

### 2) Era pack validator reports errors

Typical causes:

- malformed YAML
- duplicate/broken IDs
- missing required keys in one of the 12 pack files

Fix pack data and re-run validator.

### 3) `storyteller dev` does not launch UI

- ensure Node.js/npm is installed
- ensure `frontend/` exists
- run frontend manually to inspect npm errors

### 4) `Failed to connect to Ollama`

- ensure Ollama is running: `ollama serve`
- verify models are available: `ollama list`
- pull required models: `ollama pull mistral-nemo` and `ollama pull qwen3:4b`

### 5) `Vector database is empty`

- run ingestion first (`ingestion.ingest` or `ingestion.ingest_lore`)
- ensure `VECTORDB_PATH` matches the path used during ingestion

## Cross-references

- [README](../README.md)
- [Quickstart](../QUICKSTART.md)
- [Era Pack Quick Reference](./SETTING_PACK_QUICK_REFERENCE.md)
- [Pack Authoring](./PACK_AUTHORING.md)
- [API Reference](../API_REFERENCE.md)
