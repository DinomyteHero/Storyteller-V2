# Quick Start Guide

This guide reflects the current repository layout and launch scripts.

## Prerequisites

1. **Python 3.11+**
2. **Node.js + npm** (for SvelteKit frontend)
3. **Ollama** installed and available on PATH (for LLM-backed flows)

Recommended model pulls (matching default role configuration):

```bash
ollama pull mistral-nemo:latest
ollama pull qwen3:4b
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

---

## 0) Fast bootstrap (recommended)

```bash
bash scripts/bootstrap.sh
make check
```

## 1) Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

Optional first-run setup helper:

```bash
python -m storyteller setup
```

`storyteller setup` creates the standard data directories and runs basic health checks.

---

## 2) Configure environment

Create `.env` (or export variables in shell). Minimum useful variables:

```bash
# Runtime paths
export STORYTELLER_DB_PATH="./data/storyteller.db"
export VECTORDB_PATH="./data/lancedb"
export ERA_PACK_DIR="./data/static/era_packs"

# Ollama endpoint
export OLLAMA_BASE_URL="http://127.0.0.1:11434"

# Optional API auth for non-dev mode
# export STORYTELLER_DEV_MODE=0
# export STORYTELLER_API_TOKEN="replace-me"
```

If you keep `STORYTELLER_DEV_MODE=1` (default), API auth is disabled for local development.

---

## 3) Start the stack

### Recommended unified launcher

```bash
python run_app.py --dev
```

Useful variants:

```bash
python run_app.py --check
python run_app.py --api-only --dev
python run_app.py --ui-only --ui-port 5173
python run_app.py --validate-packs --dev
```

### Alternative CLI launcher

```bash
python -m storyteller dev
```

### Windows helper

```bat
.\start_app.bat
```

---

## 4) Verify services

- API root: `http://localhost:8000/`
- API health: `http://localhost:8000/health`
- API diagnostics: `http://localhost:8000/health/detail`
- OpenAPI: `http://localhost:8000/docs`
- UI (dev): `http://localhost:5173`

Quick API check:

```bash
curl http://localhost:8000/health
```

---

## 5) Create a campaign and run a turn

```bash
# Create campaign
curl -X POST "http://localhost:8000/v2/campaigns" \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Quickstart Campaign",
    "time_period":"rebellion",
    "player_name":"Rex",
    "starting_location":"loc-cantina"
  }'
```

Use returned `campaign_id` and `player_id`:

```bash
curl -X POST "http://localhost:8000/v2/campaigns/<campaign_id>/turn?player_id=<player_id>" \
  -H "Content-Type: application/json" \
  -d '{"user_input":"Look around"}'
```

---

## 6) Optional ingestion commands

CLI ingestion (recommended):

```bash
python -m storyteller ingest --pipeline lore --input ./data/lore/rebellion --out-db ./data/lancedb --era rebellion --yes
```

Direct lore ingestion (advanced):

```bash
python -m ingestion.ingest_lore --input ./data/lore/rebellion --db ./data/lancedb --setting-id star_wars_legends --period-id rebellion --time-period REBELLION --era-mode ui --recursive
```

Legacy simple pipeline (deprecated, explicit opt-in):

```bash
python -m storyteller ingest --pipeline simple --allow-legacy --input sample_data --out-db ./data/lancedb
```

Style ingestion:

```bash
python scripts/ingest_style.py --dir ./data/style --db ./data/lancedb

# Playability quality gates (content + lore coverage)
python scripts/check_period_playability.py --db ./data/lancedb
```

---

## Troubleshooting

### Ollama unreachable

```bash
ollama serve
curl http://127.0.0.1:11434/api/tags
```

### Era pack not found

- Ensure `ERA_PACK_DIR` points to `data/static/era_packs`.
- Validate packs:

```bash
python scripts/validate_era_packs.py
```

### Dependency or environment issues

```bash
python -m storyteller doctor
```
