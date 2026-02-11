# Quick Start Guide

## Prerequisites

1. **Python 3.11+**: `python --version`
2. **Ollama installed** (local LLM): https://ollama.com/download
3. **Ollama running**: `ollama serve` (or use `.\start_dev.bat` / `python -m storyteller dev`, which can try to start it)
4. **Pull the required models**:
   ```bash
   ollama pull mistral-nemo        # Director + Narrator (quality-critical, ~7GB VRAM)
   ollama pull qwen3:4b            # Architect, Casting, Biographer, KG Extractor (lightweight)
   ```

Notes:
- `mistral-nemo:latest` handles Director and Narrator (the two quality-critical roles).
- `qwen3:4b` handles all lightweight roles (Architect, Casting, Biographer, KG Extractor).
- Only one model is loaded at a time (specialist swapping). An RTX 4070 12GB or equivalent is sufficient.
- Embeddings default to `sentence-transformers/all-MiniLM-L6-v2` (downloads automatically on first ingest/retrieval).

---

## Fastest Path (Windows)

```powershell
.\setup_dev.bat
.\start_dev.bat
```

Open:
- Backend: `http://localhost:8000` (OpenAPI UI: `http://localhost:8000/docs`)
- SvelteKit UI: `http://localhost:5173`

---

## Cross-Platform Setup (Recommended)

```bash
python -m venv venv
# Activate:
#   Windows PowerShell: .\venv\Scripts\Activate.ps1
#   Windows CMD:       .\venv\Scripts\activate.bat
#   macOS/Linux:       source venv/bin/activate

pip install -e .
python -m storyteller setup
python -m storyteller dev
```

`storyteller setup`:
- Creates `data/`, `data/lancedb/`, `data/lore/`, `data/style/`, `data/manifests/`
- Copies `.env.example` to `.env` (if missing)
- Runs `storyteller doctor` (environment health check)

---

## (Optional) Run DB Migration

```powershell
python -m backend.app.db.migrate --db ./data/storyteller.db
```

- Safe to run multiple times; migrations are tracked in `schema_migrations`.

---

## Ingest Starter Content

### Option A: Sample Data (Flat TXT/EPUB)

```powershell
python -m ingestion.ingest --input_dir sample_data --era LOTF --source_type novel --out_db ./data/lancedb
```

### Option B: Rebellion Starter Pack (Hierarchical + Style)

This repo includes:
- Era Pack (Bible): `data/static/era_packs/rebellion/` (12 YAML files)
- Style guide: `data/style/era/rebellion_style.md`
- Optional local lore directory for ingestion: `data/lore/rebellion/` (create if missing)

```powershell
# Lore (hierarchical; UI-era key)
python -m ingestion.ingest_lore --input ./data/lore/rebellion --db ./data/lancedb --time-period REBELLION --era-mode ui --recursive

# Style
python scripts/ingest_style.py --input_dir ./data/style --era REBELLION --source_type style --out_db ./data/lancedb
```

Rebellion tip: in campaign setup, choose Era = `REBELLION` (or set `DEFAULT_ERA=REBELLION`).

---

## Character Aliases (Optional)

Character alias tagging during ingestion is supported via `data/character_aliases.yml`.

**Status:** The core system works without aliases enabled. Keep `ENABLE_CHARACTER_FACETS=0` unless you are explicitly testing experimental retrieval behavior.

---

## Verify (Optional)

```powershell
python scripts/verify_lore_store.py --db ./data/lancedb
python -m storyteller query "ISB tactics" --k 5 --era REBELLION
```

Optional (advanced): build SQLite knowledge-graph tables from ingested lore:

```powershell
python -m storyteller extract-knowledge --era rebellion --resume
```

---

## Minimal API Test (PowerShell)

```powershell
# Create campaign (manual)
$create = Invoke-RestMethod -Uri "http://localhost:8000/v2/campaigns" -Method Post -Body '{"title":"Test","player_name":"Rex","starting_location":"loc-tavern"}' -ContentType "application/json"
$cid = $create.campaign_id
$pid = $create.player_id

# Run a turn
Invoke-RestMethod -Uri "http://localhost:8000/v2/campaigns/$cid/turn?player_id=$pid" -Method Post -Body '{"user_input":"Look around"}' -ContentType "application/json"
```

The turn response always includes `narrated_text`, `suggested_actions` (exactly 4 KOTOR-style dialogue options), `player_sheet`, `inventory`, `quest_log`, and `warnings`. It can optionally include `debug`, `state`, `party_status`, `alignment`, `faction_reputation`, and `news_feed`.

### Gameplay interaction

Storyteller AI uses a **KOTOR-style dialogue wheel** -- there is no free-text input. Each turn returns exactly 4 `suggested_actions` with tone tags (`PARAGON`, `INVESTIGATE`, `RENEGADE`, `NEUTRAL`). The player picks one, and its `intent_text` is sent as `user_input` for the next turn.

During character creation (via `POST /v2/setup/auto`), the player selects a **gender** (`player_gender`: `"male"` or `"female"`) which is used for pronoun consistency throughout the narrative.

---

## Troubleshooting

### "Vector database is empty"
- Run ingestion first (`ingestion.ingest` or `ingestion.ingest_lore`), and ensure `VECTORDB_PATH` matches the same `--out_db` / `--db` path.

### "Failed to connect to Ollama"
- Ensure Ollama is running: `ollama serve`
- Verify a model is available: `ollama list`
- Pull the required models: `ollama pull mistral-nemo` and `ollama pull qwen3:4b`

### Slow first run
- First ingest/retrieval downloads the sentence-transformers model (~80MB).
- LLM speed depends on your Ollama model size.

### "Activate.ps1 is not digitally signed" (Windows)
Run in PowerShell:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Using run_with_venv.bat
For guaranteed venv usage without manual activation:
```cmd
.\run_with_venv.bat -m storyteller dev
.\run_with_venv.bat scripts\ingest_style.py
```
Note: Do not include `python` in the command -- the wrapper adds it automatically.
