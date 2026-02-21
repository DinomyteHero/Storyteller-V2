# Storyteller V1.0 Roadmap — Remaining Work

Last updated: V11.0 codebase audit.

Items from the original roadmap that have been completed are removed. This document tracks only remaining work.

---

## 1. POLISH BACKLOG

### 1.1 Pre-Release (Must Fix)

| # | Issue | File(s) | Effort |
|---|-------|---------|--------|
| 1 | **13+ generic `except Exception` blocks** in API file — swallow errors, break observability | `api/v2_campaigns.py` | Medium |

### 1.2 Polish (Should Fix)

| # | Issue | File(s) | Effort |
|---|-------|---------|--------|
| 1 | **Prologue page is static** — should be playable turns, not a read-only briefing. Current `/prologue` shows screenplay data but the player just reads and clicks "Begin." Wire `OpeningCrawl` into the prologue-to-play transition. | `prologue/+page.svelte` | Medium |
| 2 | **Ollama status not visible in gameplay HUD** — only shown in layout banner, not in `HudBar.svelte` | `play/+page.svelte`, `HudBar.svelte` | Low |

### 1.3 Post-Release (v1.1 Backlog)

| # | What | Priority |
|---|------|----------|
| 1 | Quick-start archetypes ("The Reluctant Hero", "The Ruthless Mercenary") — pre-built character templates, not just random quick-start | Medium |
| 2 | "Browse Universes" redesign — split Library into browse vs. manage modes | Medium |
| 3 | Frontend integration tests (creation wizard, turn submission, campaign resume) | Medium |
| 4 | Query caching for CampaignBibleAgent (per setting_id) | Medium |
| 5 | World state snapshot pagination (snapshot every N turns, prune old snapshots) | Low |

---

## 2. CODEBASE CLEANUP

### 2.1 Remaining Refactors

#### A. Consolidate Config + Constants

`config.py` (~367 lines) and `constants.py` (~585 lines) both reference token budgets and model settings. Consider consolidating into a `config/` package:

```
Proposed:
  config/
    __init__.py          # Re-exports for backward compat
    env.py               # Environment variable parsing
    models.py            # MODEL_CONFIG, cloud presets, provider resolution
    budgets.py           # Token budgets, context limits
    constants.py         # Game constants (action costs, tone mappings)
```

#### B. Standardize Error Handling

Multiple patterns in use (`log_error_with_context()`, direct `logger.exception()`, generic `except Exception`). `error_handling.py` exists but no unified decorator pattern is adopted across all agents.

### 2.2 Medium Priority Cleanup

| # | What | Why |
|---|------|-----|
| 1 | Add `py.typed` marker | Signals to downstream consumers that the package is typed |
| 2 | Document agent naming conventions | No standard for agent file names vs. class names (e.g., `narrator.py` vs `choice_crafter_agent.py`) |

---

## 3. DISTRIBUTABLE PACKAGING (Executable Wrapper)

Not yet started. Options under consideration:

### 3.1 Recommended Approach: Tauri

**Why Tauri over Electron:**
- ~10MB binary vs ~150MB+ for Electron
- Native system tray, file dialogs, OS integration
- Rust backend = can bundle the Python API server as a sidecar process
- Active ecosystem, production-ready

**Architecture:**

```
storyteller-app/
├── src-tauri/
│   ├── src/
│   │   └── main.rs           # Tauri app entry
│   ├── sidecar/
│   │   └── storyteller-api   # Bundled Python backend (PyInstaller or Nuitka)
│   └── tauri.conf.json       # Window config, sidecar registration
├── frontend/                  # Existing SvelteKit app (builds to static)
└── scripts/
    └── bundle.sh              # Build pipeline
```

**How it works:**
1. Tauri launches the SvelteKit frontend as a native window
2. On startup, Tauri spawns the Python backend as a **sidecar process** (bundled via PyInstaller)
3. The backend starts Uvicorn on a random localhost port
4. Frontend connects to the backend via the dynamic port
5. Ollama runs separately (user installs it, or bundled as another sidecar)

### 3.2 Build Pipeline

```
1. Build frontend:     npm run build        → frontend/build/ (static files)
2. Bundle backend:     pyinstaller ...      → dist/storyteller-api (single binary)
3. Bundle Tauri:       cargo tauri build    → dist/Storyteller.exe / .dmg / .AppImage
```

### 3.3 Alternative: Electron

If Tauri proves too complex (Rust toolchain requirement), Electron works but produces ~150MB+ binaries with higher memory usage.

### 3.4 Alternative: Simple Launcher Script

Lowest effort — ship a launcher script (`.bat` / `.sh` / `.command`) that:
1. Starts the Python backend (`uvicorn backend.app.main:app`)
2. Opens the browser to `localhost:3000`
3. Manages lifecycle (shutdown on close)

This is viable for v1.0 if native app packaging is out of scope. Note: `start_app.bat` already exists as a Windows launcher.

---

## COMPLETED (Removed from Roadmap)

The following sections from the original roadmap have been fully implemented and removed:

- **Playable Origin Stories** — `origin_engine.py`, `origin_agent.py`, `/origin` route all built
- **V1.0 Pre-Release fixes** — Setup progress indicator, error boundary, DB index on truth_facts, enum validation, MAX_USER_INPUT_CHARS validation, DEV_MODE default, rate limit configurability, console.warn cleanup
- **V1.0 Polish** — Home screen atmosphere, rich era descriptions, pronoun/gender framing, thread seed preview, campaign scale selection, companion preview, skeleton loaders, loading choices indicator
- **V1.0 Documentation** — Troubleshooting guide (README.md), ER diagram (docs/03)
- **V1.0 Post-Release** — Character codex/journal (journal drawer in play page), LanceDB RAG query limits
- **Split v2_campaigns.py** — Split into v2_campaigns.py, v2_turn.py, v2_content.py, v2_player.py, v2_export.py, v2_eraforge.py, v2_library.py
- **Move prompt templates to external files** — `prompts/v1/` directory with 8 externalized system prompts
- **Create BaseAgent class** — `BaseAgent` in `backend/app/core/agents/base.py`, exported from `__init__.py`
- **Type-hint ingestion scripts** — `chunking.py`, `embedding.py`, `epub_reader.py` all typed
- **Extract HudBar component** — `HudBar.svelte` extracted from play page
- **Duplicate backgrounds** — Merged (no duplicates remain)
- **In-Game LLM Configuration UI** — `/settings` route with per-role model configuration

---

*Assessed against: Storyteller-V2 at V11.0*
