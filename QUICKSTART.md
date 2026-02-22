# Quick Start Guide — Storyteller AI v1.0

This guide covers setup, configuration, and running your first campaign.

---

## Prerequisites

1. **Python 3.11+**
2. **Node.js + npm** (for SvelteKit frontend)
3. **Ollama** installed and running (`ollama serve`)

### Required Ollama Models

Pull these before starting (matches V11.0 default role configuration):

```bash
# Quality-critical roles (Director + Narrator)
ollama pull mistral-nemo:latest

# Medium roles (ChoiceCrafter, Mechanic, CompanionSystem, WorldMind, QuestWeaver,
# Memory, Prologue, ArcScreenplay, Bible, EraForge, SuggestionRefiner)
ollama pull qwen3:8b

# Lightweight roles (Architect, Biographer, Casting, KG Extraction, Continuity,
# Progression, PsychArchivist, IntentRouter, ArcWeaver, CampaignInit,
# RevelationAgent, CallbackCrystallizer)
ollama pull qwen3:4b

# Embeddings (required for RAG retrieval)
ollama pull nomic-embed-text
```

---

## Step 0 — Fast bootstrap (recommended for new machines)

```bash
bash scripts/bootstrap.sh
make check
```

This installs Python dependencies, copies `.env.production.example` → `.env` (if no `.env` exists), and runs health checks. Frontend `node_modules` are auto-installed on first launch.

---

## Step 1 — Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

Run the first-time setup helper:

```bash
python -m storyteller setup
```

`storyteller setup` creates the standard data directories (`data/`, `data/lancedb/`, `data/static/era_packs/`), copies `.env.example` → `.env` when missing, and runs `storyteller doctor`.

---

## Step 2 — Configure Environment

Copy the template and edit:

```bash
cp .env.example .env
```

Minimum variables for local dev:

```bash
# Paths
STORYTELLER_DB_PATH=./data/storyteller.db
VECTORDB_PATH=./data/lancedb
ERA_PACK_DIR=./data/static/era_packs

# Ollama endpoint
OLLAMA_BASE_URL=http://127.0.0.1:11434

# Per-role LLM model config (V11.0 defaults)
STORYTELLER_DIRECTOR_MODEL=mistral-nemo:latest
STORYTELLER_NARRATOR_MODEL=mistral-nemo:latest
STORYTELLER_ARCHITECT_MODEL=qwen3:4b
STORYTELLER_CHOICE_CRAFTER_MODEL=qwen3:8b

# Feature flags
ENABLE_BIBLE_CASTING=1         # Era pack NPC selection (recommended)
ENABLE_PROCEDURAL_NPCS=1       # Fallback NPC generation
# ENABLE_PORTRAITS=0           # V11.0: Optional NPC portraits + location key art (default off)

# Development (disables API auth)
STORYTELLER_DEV_MODE=1
```

**Note:** `ENABLE_SUGGESTION_REFINER=1` is on by default and can be disabled if you want raw LLM choices without refinement.

---

## Step 3 — Start the Stack

### Cross-platform (recommended)

```bash
python run_app.py --dev
```

Runs preflight checks, then starts both the FastAPI backend and SvelteKit frontend.

### Windows shortcut

```bat
.\start_app.bat
```

### Useful variants

```bash
python run_app.py --check              # Validate config without starting
python run_app.py --api-only --dev     # Backend only (no UI)
python run_app.py --ui-only            # Frontend only
python run_app.py --dev --port 8001    # Custom port
python run_app.py --validate-packs     # Validate era packs then start
```

### Alternative CLI launcher

```bash
python -m storyteller dev
```

### Run components separately

```bash
# Backend
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (in a separate terminal)
cd frontend && npm install && npm run dev -- --port 5173

# Ollama (if not already running)
ollama serve
```

---

## Step 4 — Verify Services

| Service | URL |
| -------- | --- |
| API root | `http://localhost:8000/` |
| Health check | `http://localhost:8000/health` |
| Detailed diagnostics | `http://localhost:8000/health/detail` |
| OpenAPI docs | `http://localhost:8000/docs` |
| SvelteKit UI | `http://localhost:5173` |

Quick check:

```bash
curl http://localhost:8000/health
```

The `/health/detail` endpoint reports: Ollama connectivity, model availability, LanceDB table status, era pack count, and per-role LLM config.

---

## Step 5 — Create a Campaign and Run Turns

### Option A: Auto-setup (recommended)

Let the engine generate a campaign skeleton and character sheet from a concept:

```bash
curl -X POST http://localhost:8000/v2/setup/auto \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Quickstart Campaign",
    "time_period": "rebellion",
    "player_name": "Rex",
    "player_concept": "A former Clone trooper trying to escape his past"
  }'
```

### Option B: Manual creation

```bash
# Discover available content
curl http://localhost:8000/v2/content/catalog
curl http://localhost:8000/v2/content/default

# Create campaign
curl -X POST http://localhost:8000/v2/campaigns \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Quickstart Campaign",
    "time_period": "rebellion",
    "player_name": "Rex",
    "starting_location": "loc-cantina"
  }'
```

### Run a Turn

Use the `campaign_id` and `player_id` from the creation response:

```bash
curl -X POST "http://localhost:8000/v2/campaigns/{campaign_id}/turn?player_id={player_id}" \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Look around the cantina for any Imperials"}'
```

The response includes:
- `final_text` — Narrator prose (5-8 sentences)
- `suggested_actions` — 4 ChoiceCrafter-generated player choices (PARAGON/INVESTIGATE/RENEGADE/NEUTRAL)
- `party_status` — companion affinity + mood
- `warnings` — pipeline warnings (context trimming, validation notes, agent failures)

### Streaming Turn (SSE)

```bash
curl -N "http://localhost:8000/v2/campaigns/{campaign_id}/turn/stream?player_id={player_id}&user_input=Look+around"
```

---

## Step 6 — Optional: Lore Ingestion (RAG)

Without ingestion, the system works but narration won't be grounded in lore. To enable RAG retrieval:

### Ingest lore sources (PDF/EPUB/TXT)

```bash
# Via CLI
python -m storyteller ingest --pipeline lore --input ./data/lore/rebellion --era rebellion --yes

# Direct ingestion (advanced)
python -m ingestion.ingest_lore \
  --input ./data/lore/rebellion \
  --db ./data/lancedb \
  --setting-id star_wars_legends \
  --period-id rebellion \
  --recursive
```

### Ingest style guides

```bash
python scripts/ingest_style.py --dir ./data/style --db ./data/lancedb
```

### Rebuild vector DB from scratch

```bash
python scripts/rebuild_lancedb.py --confirm
```

---

### Manage lore sources (V11.0)

The Library page ("Sources" tab) and creation wizard support source-level management of ingested material:

```bash
# List all lore sources
curl http://localhost:8000/v2/library/sources

# Create a named source collection
curl -X POST http://localhost:8000/v2/library/sources \
  -H "Content-Type: application/json" \
  -d '{"name": "Dune novels", "setting_id": "dune", "period_id": "butlerian_jihad"}'

# Delete a source (removes its chunks from LanceDB)
curl -X DELETE http://localhost:8000/v2/library/sources/{source_id}
```

Sources can also be uploaded during campaign creation via the optional "Add Reference Material" step on the review page.

---

## Step 7 — Optional: Knowledge Graph Extraction

After lore ingestion, extract a knowledge graph for runtime character/entity retrieval:

```bash
python -m storyteller extract-knowledge --era rebellion --db ./data/storyteller.db
```

---

## Feature Notes

### EraMoments

EraMoments are scripted narrative triggers defined in `data/static/era_packs/{era}/moments.yaml` (when present in the era pack). They fire once when conditions are met (companion affinity, arc stage, location, quest completion, alignment). No configuration needed — they activate automatically during turns. Era packs without a `moments.yaml` file silently skip this system.

### Hub/Downtime Mode

Hub locations (cantinas, safehouses, guild halls) automatically activate downtime mode when the player is at a location with `hub` in its `services` list (defined in `locations.yaml`). The Director receives hub context injection with available options: rest, gather_intel, resupply, talk_{companion}.

### Quest Tracker

Quests defined in `data/static/era_packs/{era}/quests.yaml` (when present) activate and progress automatically based on turn events, location, NPCs met, and actions taken. Quest status is tracked in `world_state_json["quest_log"]` and updated each turn by the Commit node.

### Deferred Maintenance Agents (V7.0)

Heavy maintenance agents (MemoryAgent, QuestWeaver, ProgressionAgent, PsychArchivist) run post-commit via `pending_world_state_patches` table. This reduces transaction hold time from 10-20s to ~2s on maintenance turns. Patches are applied on next turn load via `apply_pending_patches()`.

### Rewind/Undo (V7.0)

`POST /v2/campaigns/{campaign_id}/rewind?to_turn=N` restores world state from the `turn_snapshots` table and deletes all turn data after turn N. Only turns committed after V7.0 deployment have snapshots.

### AgentFailureError

If an authoritative LLM agent (Narrator or ChoiceCrafter) fails after retry, the turn returns:
- `final_text`: `"[SYSTEM] A narrative agent failed: {agent_name}. ..."`
- `suggested_actions`: `[]`
- `warnings`: `["[AGENT_FAILURE] {agent_name}: {error}"]`

The database is **not written** (failure occurs before the Commit node). Retrying the same turn input is safe.

---

## Troubleshooting

**Ollama unreachable**
```bash
ollama serve
curl http://127.0.0.1:11434/api/tags
```

**Models not found**
```bash
ollama list
ollama pull mistral-nemo:latest
ollama pull qwen3:8b
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

**Era pack not found**
```bash
python scripts/validate_era_packs.py
echo $ERA_PACK_DIR  # Should point to data/static/era_packs
```

**LanceDB tables missing (RAG returns empty)**
```bash
# Check status
curl http://localhost:8000/health/detail
# Run ingestion
python -m ingestion.ingest_lore --input data/lore/ --db data/lancedb --recursive
```

**`[SYSTEM] A narrative agent failed`**
- Check Ollama is running and the model is available
- Check `/health/detail` for per-role model status
- Retry the turn — no state was written

**General dependency or environment issues**
```bash
python -m storyteller doctor
```
