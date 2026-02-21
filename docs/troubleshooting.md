# Storyteller AI - Troubleshooting Guide

## Quick Health Check

The backend exposes a health endpoint:

```
GET http://localhost:8000/health/detail
```

This returns the status of all subsystems (Ollama, database, LanceDB). Always start here when debugging.

---

## Startup Issues

### Backend won't start

**Symptom:** `uvicorn` fails to launch or crashes immediately.

**Fixes:**
1. Ensure Python 3.11+ is installed: `python --version`
2. Install dependencies: `pip install -r backend/requirements.txt`
3. Check port 8000 isn't already in use: `lsof -i :8000`
4. Run directly: `cd backend && python -m uvicorn main:app --reload`

### Frontend won't start

**Symptom:** `npm run dev` fails.

**Fixes:**
1. Ensure Node 18+ is installed: `node --version`
2. Install deps: `cd frontend && npm install`
3. Default dev server runs on port 5173

---

## Ollama Issues

### "Story engine unavailable - Ollama is not running"

This banner appears on the frontend when the health check detects Ollama is down.

**Fixes:**
1. Start Ollama: `ollama serve`
2. Verify it's running: `curl http://localhost:11434/api/tags`
3. If using a custom host, set `OLLAMA_HOST` env var

### "Model not found" errors during gameplay

**Symptom:** 404 errors in backend logs when agents try to use a model.

**Fixes:**
1. Pull required models:
   ```bash
   ollama pull llama3.1:8b      # Default narrator model
   ollama pull mistral:7b        # Alternative
   ```
2. Check which models are configured in `backend/app/core/config.py` under `MODEL_CONFIG`
3. Override model names with env vars: `STORYTELLER_NARRATOR_MODEL=llama3.1:8b`

### Ollama responses are very slow

**Fixes:**
1. Ensure GPU acceleration is working: check `ollama ps` for GPU layers
2. Use smaller models (7B/8B) if running on CPU-only
3. Reduce narrator mode from "Epic" to "Concise" in game settings

---

## Database Issues

### "database is locked" errors

**Symptom:** SQLite lock errors during concurrent requests.

**Fixes:**
1. This is expected under heavy load with SQLite - reduce concurrent requests
2. Check for zombie backend processes: `ps aux | grep uvicorn`
3. Kill stale processes and restart

### Missing tables or columns

**Symptom:** SQL errors about unknown tables/columns.

**Fixes:**
1. Migrations run automatically on startup via `run_migrations()` in `backend/app/db/core.py`
2. Check migration files in `backend/app/db/migrations/` - they should apply in order (0001-0037)
3. If the database is corrupted, back it up and delete it to get a fresh start:
   ```bash
   cp backend/data/storyteller.db backend/data/storyteller.db.bak
   rm backend/data/storyteller.db
   # Restart backend - migrations will create fresh tables
   ```

---

## LanceDB / Vector Search Issues

### Lore search returns no results

**Symptom:** Narration doesn't reference ingested lore books.

**Fixes:**
1. Check that books were ingested: look in `backend/data/lancedb/` for data files
2. Re-run ingestion: use the Library page to upload and process source material
3. Verify the embedding model is available in Ollama

### Ingestion job stuck in "running" state

**Fixes:**
1. Check `ingestion_jobs` table for the job status
2. Restart the backend - stale jobs will be picked up
3. Check backend logs for embedding errors

---

## Gameplay Issues

### Turns take too long (30+ seconds)

The turn pipeline runs 14 LLM agents sequentially. This is expected on CPU-only setups.

**Optimization options:**
1. Use GPU-accelerated Ollama
2. Switch to cloud LLMs for quality-critical agents (Settings > Cloud Quality)
3. Use "Concise" narrator mode
4. Smaller models (7B) are faster but produce simpler prose

### "Rate limit exceeded" error

**Default:** 10 requests per 60 seconds.

**Fixes:**
1. Wait and retry
2. Adjust limits via env vars:
   ```bash
   STORYTELLER_RATE_LIMIT_WINDOW=120  # seconds
   STORYTELLER_RATE_LIMIT_MAX=20       # max requests
   ```

### Campaign creation fails

**Symptom:** Error during "Begin Adventure" on the creation wizard.

**Fixes:**
1. Check that Ollama is running and the required model is pulled
2. Check backend logs for the specific agent that failed
3. Ensure the era pack exists in `data/static/era_packs/`

### Choices don't appear after narration

**Symptom:** Narration renders but no suggested actions are shown.

**Fixes:**
1. The Choices Agent may have failed silently - check backend logs
2. Refresh the page - the last turn response should be cached
3. You can always type a custom action in the text input

---

## Cloud LLM Issues

### API key errors

**Symptom:** "Authentication failed" or 401 errors when using cloud presets.

**Fixes:**
1. Set the correct env var for your provider:
   ```bash
   ANTHROPIC_API_KEY=sk-ant-...
   OPENAI_API_KEY=sk-...
   ```
2. Verify the key is valid with a direct API test
3. Check that the cloud preset is correctly configured in Settings

### Wrong model being used

**Fixes:**
1. Check `MODEL_CONFIG` in `backend/app/core/config.py` for defaults
2. Override per-agent with env vars: `STORYTELLER_{ROLE}_PROVIDER`, `STORYTELLER_{ROLE}_MODEL`
3. Cloud presets (local/budget/balanced/quality) override model routing for specific agents

---

## Frontend Issues

### Page is blank or shows "Something Went Wrong"

**Fixes:**
1. Check browser console (F12) for JavaScript errors
2. Verify the backend is running at `http://localhost:8000`
3. Check CORS settings - the backend allows origins: `http://localhost:5173`, `http://localhost:5174`, `http://localhost:4173`
4. Try a hard refresh: Ctrl+Shift+R

### Theme not applying

**Fixes:**
1. Themes are stored in localStorage under `storyteller-ui`
2. Clear localStorage and refresh to reset to defaults
3. Check that `+layout.svelte` is injecting theme CSS variables

### Campaign list shows "Backend campaign list unavailable"

**Fixes:**
1. Backend is not reachable - check that it's running on port 8000
2. The home screen will fall back to local cache from localStorage
3. Campaigns stored locally may be missing `playerId` and can't be resumed

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `STORYTELLER_DEV_MODE` | `false` | Enables dev features, extra logging |
| `STORYTELLER_RATE_LIMIT_WINDOW` | `60` | Rate limit window in seconds |
| `STORYTELLER_RATE_LIMIT_MAX` | `10` | Max requests per window |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `ANTHROPIC_API_KEY` | _(none)_ | Anthropic API key for cloud LLMs |
| `OPENAI_API_KEY` | _(none)_ | OpenAI API key for cloud LLMs |
| `STORYTELLER_{ROLE}_PROVIDER` | `ollama` | LLM provider per agent role |
| `STORYTELLER_{ROLE}_MODEL` | _(varies)_ | Model name per agent role |

Agent roles: `NARRATOR`, `DIRECTOR`, `MECHANIC`, `CHOICES`, `BIOGRAPHER`, `LORE`, `ARCHIVIST`, `PROLOGUE`, `ARC_PLANNER`, `NPC_VOICE`, `WORLD_PAINTER`, `TRUTH_AUDITOR`

---

## Getting Help

If none of the above resolves your issue:
1. Check backend logs (stdout/stderr from uvicorn)
2. Check browser developer console (F12 > Console)
3. File an issue with logs and reproduction steps
