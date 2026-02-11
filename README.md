# Storyteller AI

Storyteller AI is a local-first narrative RPG engine powered by a FastAPI backend, SvelteKit frontend, and deterministic world content loaded from YAML-based Era Packs.

**Current System (V2.20):**
- Star Wars Legends narrative campaigns with LLM-powered storytelling
- Era Pack system for deterministic world content (`/data/static/era_packs/`)
- Event sourcing architecture with SQLite persistence
- RAG-powered lore retrieval from ingested novels
- Ollama-only local LLM execution (no cloud dependencies)

**Repository Status:**
- Streamlined to `_template` + `rebellion` era packs (others can be regenerated)
- Removed legacy migration scripts and obsolete tooling
- Consolidated documentation and templates

---

## Project Overview

Storyteller AI combines deterministic game systems with LLM-powered narrative generation:

- **Backend:** FastAPI server (`backend.main:app`) with LangGraph pipeline orchestration
- **Frontend:** SvelteKit UI with typewriter narration and KOTOR-style dialogue wheel
- **Content:** Era Pack YAML bundles define NPCs, locations, quests, and factions
- **Narrative:** Ollama-based Director/Narrator agents with RAG lore retrieval
- **Persistence:** Event sourcing with SQLite (append-only events + projections)

**Key Features:**
- Historical/Sandbox campaign modes
- Deterministic mechanics (dice, time, encounters)
- Companion affinity and party dynamics
- Multi-lane RAG retrieval (lore, style, character voice, knowledge graph)
- Streaming narration via SSE

---

## Key Concepts

### Era Packs

Era Packs are YAML-based content bundles that define a playable Star Wars Legends time period. Each pack contains 12 files:

- `era.yaml` - Era metadata, tone, galactic state
- `companions.yaml` - Recruitable party members
- `quests.yaml`, `npcs.yaml`, `locations.yaml`, `factions.yaml`
- `backgrounds.yaml` - SWTOR-style character creation
- `namebanks.yaml`, `meters.yaml`, `events.yaml`, `rumors.yaml`, `facts.yaml`

**Current Era Packs:**
- `_template` - Reference structure for authoring new packs
- `rebellion` - Galactic Civil War (0 BBY - 4 ABY) - canonical example

**Location:** `/data/static/era_packs/{era_id}/`

See `/docs/ERA_PACK_QUICK_REFERENCE.md` for complete documentation.

### Campaign Creation

Campaigns are created via:
- `POST /v2/setup/auto` - Automated setup with CampaignArchitect + BiographerAgent
- `POST /v2/campaigns` - Manual campaign creation

Each campaign includes:
- Player character with background and stats
- 12 NPCs (Villain, Rival, Merchants, Informants, Guards)
- Active factions from the era pack
- Arc scaffold (themes, opening threads, climax question)
- Generated world content (locations, NPCs, quests)

### Deterministic Systems

- **Mechanic:** Zero LLM calls — pure Python dice rolls, DC checks, time costs
- **Encounter throttling:** Seeded by turn number for reproducible spawns
- **Companion reactions:** Deterministic affinity deltas based on player choices
- **NPC generation:** Fallback procedural generation from templates
- **Faction engine:** Seeded faction behavior

---

## Quickstart

### Prerequisites

- Python 3.11+
- Node.js + npm (for the SvelteKit UI)
- Ollama (if running local LLM-backed flows)

### Install / setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

Optional helper:

```bash
python -m storyteller setup --skip-deps
```

> Note: `storyteller setup` attempts to copy `.env.example` if present. This repository may not include one, so configure env vars directly in your shell.

### Configure environment variables

Essential variables (see `backend/app/config.py` for full list):

```bash
# Database
export DEFAULT_DB_PATH="./storyteller.db"

# Era Packs
export ERA_PACK_DIR="./data/static/era_packs"

# Ollama LLM (per-role model configuration)
export STORYTELLER_DIRECTOR_MODEL="mistral-nemo:latest"
export STORYTELLER_NARRATOR_MODEL="mistral-nemo:latest"
export STORYTELLER_ARCHITECT_MODEL="qwen3:4b"

# Feature Flags
export ENABLE_BIBLE_CASTING=1              # Use era pack deterministic NPC casting
export ENABLE_SUGGESTION_REFINER=1         # LLM-powered KOTOR dialogue suggestions
export DEV_CONTEXT_STATS=0                 # Include RAG context budgeting stats
```

Optional:

```bash
export OLLAMA_BASE_URL="http://localhost:11434"
```

### Run API + UI

Preferred wrapper (cross-platform):

```bash
python run_app.py --dev
```

Windows shortcut:

```bat
.\start_app.bat
```

Quick checks without starting processes:

```bash
python run_app.py --check
```

Useful launch modes:

```bash
python run_app.py --api-only --dev     # Backend only
python run_app.py --ui-only --ui-port 5173  # Frontend only
python run_app.py --dev --host 0.0.0.0 --port 8000
```

Core wrapper flags:

- `--dev` - Enable hot reload
- `--api-only`, `--ui-only`, `--no-ui`
- `--host`, `--port`, `--ui-port`
- `--check` - Validate configuration without starting

Or run components separately:

```bash
# Backend
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev -- --port 5173

# Ollama (if not running)
ollama serve
```

---

## Era Pack Authoring

For detailed authoring guidance, see:

- [`docs/ERA_PACK_QUICK_REFERENCE.md`](docs/ERA_PACK_QUICK_REFERENCE.md)
- [`docs/era_pack_template.md`](docs/era_pack_template.md)
- [`docs/era_pack_schema_reference.md`](docs/era_pack_schema_reference.md)

### Creating a New Era Pack

1. Copy the template:
   ```bash
   cp -r data/static/era_packs/_template data/static/era_packs/kotor
   ```

2. Edit `era.yaml` with the new era's metadata

3. Fill in each of the 12 YAML files with era-specific content

4. Validate the pack:
   ```bash
   python scripts/validate_era_pack.py kotor
   ```

### Directory Structure

```text
data/static/era_packs/
  _template/           # Reference structure
  rebellion/           # Canonical example (Galactic Civil War)
    era.yaml
    companions.yaml
    quests.yaml
    meters.yaml
    npcs.yaml
    namebanks.yaml
    factions.yaml
    events.yaml
    locations.yaml
    rumors.yaml
    facts.yaml
    backgrounds.yaml
```

---

## Validation + Testing

### Validate Era Packs

```bash
# Validate all era packs
python scripts/validate_era_packs.py

# Validate single pack
python scripts/validate_era_pack.py rebellion

# Audit pack completeness
python scripts/audit_era_packs.py
```

### Run Tests

```bash
# All backend tests (587 tests, V2.20)
python -m pytest backend/tests -q

# Specific test suites
python -m pytest backend/tests/test_director.py -v
python -m pytest backend/tests/test_narrator.py -v

# Deterministic harness
python scripts/run_deterministic_tests.py

# Smoke test
python scripts/smoke_test.py
```

---

## Troubleshooting

- **`Era pack not found for era_id='...'`**
  - Confirm `ERA_PACK_DIR` points to `/data/static/era_packs`
  - Verify the era_id directory exists and contains all 12 YAML files
  - Check YAML syntax: `python scripts/validate_era_pack.py {era_id}`

- **LLM connection failures**
  - Ensure Ollama is running: `ollama serve`
  - Check model availability: `ollama list`
  - Pull required models: `ollama pull mistral-nemo:latest && ollama pull qwen3:4b`

- **Database migration errors**
  - Delete `storyteller.db` and restart (for development only)
  - Check migrations: `ls backend/app/db/migrations/`
  - Verify schema: `sqlite3 storyteller.db ".schema campaigns"`

- **Frontend won't start**
  - Install dependencies: `cd frontend && npm install`
  - Check port availability: `lsof -i :5173`
  - Clear cache: `rm -rf frontend/.svelte-kit`

See [`docs/RUNBOOK.md`](docs/RUNBOOK.md) for operational details.

---

## Documentation

### Core Documentation (Sequential Learning Path)
- [`docs/00_overview.md`](docs/00_overview.md) - High-level overview
- [`docs/01_repo_map.md`](docs/01_repo_map.md) - Repository structure
- [`docs/02_turn_lifecycle.md`](docs/02_turn_lifecycle.md) - Turn execution flow
- [`docs/03_state_and_persistence.md`](docs/03_state_and_persistence.md) - Event sourcing
- [`docs/04_agents_and_models.md`](docs/04_agents_and_models.md) - Agent roles & LLMs
- [`docs/05_rag_and_ingestion.md`](docs/05_rag_and_ingestion.md) - RAG pipeline
- [`docs/06_api_and_routes.md`](docs/06_api_and_routes.md) - API endpoints
- [`docs/07_known_issues_and_risks.md`](docs/07_known_issues_and_risks.md) - Known issues
- [`docs/08_alignment_checklist.md`](docs/08_alignment_checklist.md) - Architectural alignment
- [`docs/09_call_graph.md`](docs/09_call_graph.md) - Call graph & dependencies

### Deep Dives
- [`docs/architecture.md`](docs/architecture.md) - Complete system architecture
- [`docs/user_guide.md`](docs/user_guide.md) - Player-facing documentation
- [`docs/lore_pipeline_guide.md`](docs/lore_pipeline_guide.md) - Lore ingestion

### Templates
- [`docs/templates/CAMPAIGN_INIT_TEMPLATE.md`](docs/templates/CAMPAIGN_INIT_TEMPLATE.md) - Campaign creation
- [`docs/templates/DB_SEED_TEMPLATE.md`](docs/templates/DB_SEED_TEMPLATE.md) - Database seeding
- [`docs/ERA_PACK_QUICK_REFERENCE.md`](docs/ERA_PACK_QUICK_REFERENCE.md) - Era pack guide

### Root Documentation
- [`README.md`](README.md) - This file
- [`CLAUDE.md`](CLAUDE.md) - Project constraints & coding standards
- [`QUICKSTART.md`](QUICKSTART.md) - Quick start guide
- [`API_REFERENCE.md`](API_REFERENCE.md) - API contract

---

## Architecture Highlights

- **Event Sourcing:** Append-only `turn_events` table + projections to normalized tables
- **Single Transaction Boundary:** Only the Commit node writes to the database
- **Graceful Degradation:** Every LLM-dependent agent has deterministic fallbacks
- **JSON Retry Pattern:** LLM agents use `json_mode=True` + `ensure_json()` repair + retry
- **Per-Role LLM Config:** Agent model selection via `STORYTELLER_{ROLE}_MODEL` env vars
- **Ollama-Only:** No cloud LLM dependencies (OpenAI/Anthropic paths removed)
- **RAG Token Budgeting:** `build_context()` manages retrieval budget across lore/style/voice/KG

See [`CLAUDE.md`](CLAUDE.md) for complete architectural invariants and constraints.

---

## License

See LICENSE file for details.
