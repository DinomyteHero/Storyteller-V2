# Storyteller V1.0 Roadmap — Remaining Work

Last updated: V12.0 release packaging pass (2026-02-21, post-`0ecbfbe`).

Items from the original roadmap that have been completed are removed. This document tracks only remaining work. Section 4 (Launch Readiness Audit) contains the authoritative must-fix list; sections 1–3 cover polish, cleanup, and packaging that are distinct from launch-gate items.

---

## 1. POLISH BACKLOG

### 1.1 Pre-Release (Must Fix)

| # | Issue | File(s) | Effort |
|---|-------|---------|--------|
| 1 | ~~**37 generic `except Exception` blocks**~~ **DONE** — All 37 blocks narrowed to specific exception types or annotated with `# Intentional broad catch:` comments. 6 intentional broad catches remain (SSE error boundary, worker thread, debug endpoint, pipeline reraise). | `api/v2_campaigns.py`, `v2_turn.py`, `v2_player.py`, `v2_library.py`, `v2_content.py`, `v2_eraforge.py`, `campaign_setup.py` | ~~High~~ Done |

### 1.2 Polish (Should Fix)

| # | Issue | File(s) | Effort |
|---|-------|---------|--------|
| 1 | **Prologue is cinematic-only, not playable** — `/prologue` has an interactive crawl sequence with skip and phase transitions, but no player agency (no choices, no turns). Consider wiring playable prologue turns or interactive moments into the crawl-to-play transition so the player's first experience is participatory, not passive. | `prologue/+page.svelte` | Medium |
| 2 | **Ollama status not visible in gameplay HUD** — only shown in layout banner, not in `HudBar.svelte` | `play/+page.svelte`, `HudBar.svelte` | Low |

### 1.3 Post-Release (v1.1 Backlog)

| # | What | Priority |
|---|------|----------|
| 1 | Quick-start archetypes ("The Reluctant Hero", "The Ruthless Mercenary") — pre-built character templates, not just random quick-start | Medium |
| 2 | "Browse Universes" redesign — split Library into browse vs. manage modes | Medium |
| 3 | Query caching for CampaignBibleAgent (per setting_id) | Medium |
| 4 | World state snapshot pagination (snapshot every N turns, prune old snapshots) | Low |

> **Note:** Frontend E2E integration tests were previously listed here but have been promoted to a must-fix launch gate. See [4.7 #6](#47-additional-pre-release-tasks-from-code-audit).

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

#### B. ~~Standardize Error Handling~~ DONE

~~Multiple patterns in use (`log_error_with_context()`, direct `logger.exception()`, generic `except Exception`).~~ All 37 generic `except Exception` blocks across 7 API files have been narrowed to specific exception types (Category A: JSON parsing, B: LLM init, C: critical path with reraise, D: cleanup) or annotated with `# Intentional broad catch:` comments for blocks that genuinely need broad catching (SSE error boundary, worker threads, debug endpoints, pipeline reraise with `log_error_with_context`).

### 2.2 Medium Priority Cleanup

| # | What | Why |
|---|------|-----|
| 1 | Add `py.typed` marker | Signals to downstream consumers that the package is typed |
| 2 | Document agent naming conventions | No standard for agent file names vs. class names (e.g., `narrator.py` vs `choice_crafter_agent.py`) |

---

## 3. DISTRIBUTABLE PACKAGING (Executable Wrapper)

> **Decision made:** Launcher-supported v1.0 (ship with `start_app.bat`/`run_app.py` + browser). Native packaging (Tauri/Electron) deferred to v1.1+. `run_app.py` now auto-installs frontend `node_modules` if missing. Clean-machine validation confirmed on Windows.

Options under consideration:

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

*Assessed against: Storyteller-V2 at V11.0 (commit `6e2abcb`)*

---

## 4. V1.0 LAUNCH READINESS AUDIT (ADDENDUM)

### 4.1 Current Readiness (Critical Review)

| Area | Status | Why this matters for players | What is still left |
|---|---|---|---|
| Core architecture (turn pipeline, commit boundary, rewind, idempotency) | Strong | Prevents story corruption and duplicate turns | Keep existing release checklist gates enforced on every candidate build |
| Runtime resilience + observability | Medium Risk | Hidden failures become "story feels broken" to users | Remove remaining generic `except Exception` usage and standardize structured error handling across authoritative agents/routes |
| Narrative quality consistency | Medium Risk | Inconsistent prose/choices causes immediate churn in narrative games | Add a formal narrative regression suite (golden-turn scenarios + rubric scoring for continuity, agency, tone, and choice usefulness) |
| Content completeness per universe/era | High Risk | Sparse packs make the world feel empty/repetitive | Define and enforce a minimum content contract for every era pack shipped in v1.0 |
| First-run onboarding (models/dependencies) | High Risk | "It does not work on first launch" is a top consumer drop-off point | Add an in-app dependency preflight gate (model presence, vector tables, health checks) before players can start a campaign |
| Distribution/installation path | High Risk | Public launch requires a reproducible install/start experience | Choose one v1 path now (native wrapper vs launcher) and complete clean-machine validation on Windows/macOS |
| Frontend behavioral confidence | Medium Risk | Regressions in creation/play/resume are player-visible and trust-breaking | Add frontend integration tests for setup, turn submit/stream, resume, and rewind |
| Documentation consistency | Medium Risk | Contradictory docs create operator mistakes and support burden | Reconcile discrepancies between roadmap/alignment/risk docs (especially ChoiceCrafter fallback behavior and setting-agnostic migration status) |

### 4.2 Must-Fix Before Public v1.0

| # | Must-fix item | Exit criteria (go/no-go gate) | Status |
|---|---|---|---|
| 1 | Finalize launch packaging strategy | One documented and automated path for install/start on clean machines, tested end-to-end on target OSes | **DONE** — Launcher scripts validated, `run_app.py` auto-npm-install, QUICKSTART.md documented |
| 2 | Narrative regression harness | Promote existing tests into CI release gates with score thresholds. Add golden-turn scenario seeds. | **PARTIALLY DONE** — Release-gate markers and `--release-gate` runner added. Golden-turn scenario expansion (20+ seeds, rubric scoring) deferred to v1.1. |
| 3 | Era pack minimum viability contract | Define minimum content thresholds per pack. Set `ERA_PACK_LENIENT_VALIDATION` to `False` for release builds. | **OPEN** — Remaining pre-release work |
| 4 | Error handling hardening | No silent generic catches in critical API paths; request-scoped error logs include `request_id`, `campaign_id`, and failure class | **DONE** — 37 blocks narrowed, `request_id` added to critical-path error logs |
| 5 | First-run readiness gate | In-product preflight blocks play until required model/service dependencies are available or clearly guided | **DONE** — Hard-block on Ready step, model pull guidance, `ondismiss` UX |
| 6 | End-to-end UX regression coverage | Automated tests cover campaign creation, first turn, streaming turn, resume, and rewind without manual-only validation | **DONE** — 5 Playwright E2E specs covering all critical journeys |

### 4.3 Consumer Pain Points (And Mitigations to Track in v1)

| Pain point from player perspective | Likely root cause | Mitigation to add/track in roadmap |
|---|---|---|
| "I installed it but cannot actually play." | Missing model pull or misconfigured provider | In-app startup diagnostics + one-click remediation guidance before entering campaign flow |
| "The world feels shallow in some universes." | Incomplete era pack data | Publish only era packs that meet minimum content contract; mark others as "preview/experimental" |
| "The game forgot what happened earlier." | Narrative continuity drift under long sessions | Narrative regression suite focused on long-horizon continuity and callback consistency |
| "Choices are repetitive or not relevant." | Weak contextual grounding in edge cases | Add choice-quality evals (novelty, relevance, tone spread) to release gate and nightly checks |
| "Turns sometimes fail and I do not know what to do." | Non-actionable user-facing error states | Standardized player-facing fallback/retry messaging with request ID surfaced in UI |
| "I waited too long after clicking submit." | Latency spikes or post-narrator dead time | Enforce latency SLOs and maintain clear progress states for all turn phases |
| "I am not sure my progress is safe." | Low confidence in save/commit visibility | Keep save confidence indicator and add explicit recovery guidance for interrupted turns |
| "Different settings feel inconsistent in tone/rules." | Setting-agnostic migration still partial | Complete `SettingRules` adoption in all remaining prompts/agents before v1 public launch |

### 4.4 Suggested Launch SLOs (Add as explicit release gates)

> **Prerequisite:** Establish baseline measurements for each metric before using as release gates. Current per-node timings are collected but no aggregate SLO dashboard exists. Without a baseline, these thresholds are aspirational and may need adjustment.

| Metric | Suggested v1 threshold |
|---|---|
| Turn success rate (non-user-error requests) | >= 99.0% |
| p95 turn latency (standard turn) | <= 10s |
| p99 turn latency | <= 18s |
| Retry-required turn rate | < 2% |
| Crash-free play sessions | >= 99.5% |
| Narrative regression pass rate (golden scenarios) | 100% on blocking checks, >= 90% on scored checks |

### 4.5 30-Day Post-Launch Watchlist

| # | Item | Why it should be pre-committed now |
|---|---|---|
| 1 | Structured player feedback intake tied to campaign + turn metadata | Needed to convert subjective narrative complaints into reproducible bugs |
| 2 | Weekly narrative quality review (sampled transcripts) | Detect tone drift, repetition, and continuity failures before ratings decline |
| 3 | Era pack depth expansion cadence | Prevent "content exhaustion" for early adopters |
| 4 | Packaging hardening if launcher is used for v1.0 | Provides path from "works for technical users" to mainstream usability |

### 4.6 Code-Verified Findings (No-Assumption Pass)

| Finding | Code evidence | Roadmap implication |
|---|---|---|
| API generic exception usage is broader than one file | `backend/app/api/v2_campaigns.py` (13), `backend/app/api/v2_turn.py` (9), `backend/app/api/v2_player.py` (9), plus `v2_library.py`, `v2_content.py`, `v2_eraforge.py`, `campaign_setup.py` | **RESOLVED** — All 37 blocks narrowed to specific types or annotated |
| ChoiceCrafter behavior/docs are internally inconsistent | `backend/app/core/agents/choice_crafter_agent.py` and `backend/app/core/nodes/choice_crafter_node.py` still claim "No deterministic fallbacks", but node contains `_make_fallback_choices()` degraded path | **RESOLVED** — Docstrings updated to document fallback behavior |
| First-run onboarding exists but is a soft gate | `frontend/src/lib/components/FirstRunWizard.svelte` checks health and can be skipped; `frontend/src/routes/+page.svelte` shows wizard by localStorage flag only | **RESOLVED** — Hard-block on Ready step when Ollama unreachable, model pull guidance added, `ondismiss` callback wired |
| Launcher path is already implemented | `start_app.bat` and `run_app.py` exist with runtime preflight support | **RESOLVED** — Launcher scripts validated, auto-npm-install added to `run_app.py` |
| Narrative quality tests already exist | `backend/tests/test_deterministic_harness.py`, `test_narrative_validator.py`, `test_narrative_coherence.py`, `test_player_agency.py`, `scripts/run_deterministic_tests.py` | **RESOLVED** — `release_gate` markers added, `--release-gate` flag in test runner, `pyproject.toml` marker config |
| Frontend E2E/integration coverage is not present | Frontend has Vitest/unit tests (`frontend/src/lib/components/__tests__`, `frontend/src/lib/stores/__tests__`) but no Playwright/Cypress flow tests in repo | **RESOLVED** — Playwright E2E specs added for 5 critical journeys (create, first turn, streaming, resume, rewind) |
| Era pack depth risk is confirmed in data and config | `data/static/era_packs/*` packs are mostly 3-4 files each; `shared/config.py` sets `ERA_PACK_LENIENT_VALIDATION` default `True` | **OPEN** — Keep era pack viability as launch blocker for consumer-facing quality |
| Setting-agnostic migration remains partial | `backend/app/world/era_pack_models.py` `SettingRules` defaults are Star Wars-centric (lines 938–967: `setting_name="Star Wars Legends"`, Star Wars species list, `bypass_methods=["force", "force_dark", "sith_amulet"]`). Additional hardcoded references in: `kg/extractor.py:23` ("Star Wars Legends novels"), `kg/synthesis.py:19,31` ("Star Wars lore compiler"), `core/agents/biographer.py:151` (Jedi Temple), `core/genre_triggers.py:39` ("New Jedi Order era") | **PARTIALLY RESOLVED** — `kg/extractor.py`, `kg/synthesis.py` parameterized; `biographer.py` documented; `genre_triggers.py` override system added. `era_pack_models.py` Star Wars defaults remain as they are the correct defaults for the shipped SettingRules. |
| First-run wizard dismiss path is ambiguous for users | `FirstRunWizard.svelte` `dismiss()` only sets local storage; no explicit close event emitted to parent route | **RESOLVED** — `ondismiss` prop added, immediate UI close on dismiss |

### 4.7 Additional Pre-Release Tasks from Code Audit

| # | Task | Priority | Status |
|---|---|---|---|
| 1 | Broaden API exception hardening from one file to all V2 route modules (`v2_campaigns`, `v2_turn`, `v2_player`, `v2_library`, `v2_content`, `v2_eraforge`, `campaign_setup`) | Must | **DONE** — All 37 blocks narrowed; 6 intentional broad catches annotated |
| 2 | Resolve ChoiceCrafter docstring drift: update agent and node docstrings to acknowledge `_make_fallback_choices()` degraded path | Must | **DONE** — Docstrings updated in both files |
| 3 | Define strict first-run gating policy: hard block when Ollama unreachable, soft warn on missing models with guidance | Must | **DONE** — Hard-block on Ready step, model pull guidance with copy-to-clipboard |
| 4 | Promote existing narrative tests into official release gates | Must | **DONE** — `pytestmark = [pytest.mark.release_gate]` on 4 test files, `pyproject.toml` markers, `--release-gate` flag in `run_deterministic_tests.py` |
| 5 | Decide v1 distribution scope: launcher-supported v1.0 | Must | **DONE** — Launcher scripts validated, `run_app.py` auto-installs npm deps |
| 6 | Add frontend E2E coverage for critical player journeys (create, first turn, stream turn, resume, rewind) | Must | **DONE** — Playwright installed, 5 E2E specs in `frontend/e2e/`, `npm run test:e2e` script |
| 7 | Fix first-run wizard dismiss/close behavior | Should | **DONE** — `ondismiss` prop wired, immediate close without page reload |
| 8 | Add model pull guidance/automation to first-run flow | Must | **DONE** — Missing model list, copy-to-clipboard `ollama pull` commands, "Check Again" button |
| 9 | Complete setting-agnostic cleanup beyond `era_pack_models.py` | Should | **DONE** — `kg/extractor.py`, `kg/synthesis.py` parameterized; `biographer.py` documented; `genre_triggers.py` merge-based override system |

---

## 5. V1.0 RELEASE PACKAGING PLAN

### 5.1 Release Scope

The v1.0 release ships as a **launcher-supported local application** (not a native binary). Users install prerequisites manually, then use `run_app.py` or `start_app.bat` to launch. The target audience for v1 is technical users and AI/narrative system engineers who can manage a Python + Node.js + Ollama environment.

### 5.2 Pre-Release Packaging Checklist

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Bump `pyproject.toml` version to `1.0.0` | **DONE** | Updated from `0.1.0` |
| 2 | Finalize `.env.example` with all V12.0 vars | **DONE** | Added auth, rule system, period, suggestion refiner, ingest root, setting pack paths |
| 3 | Ensure `run_app.py --validate-packs` passes on all shipped era packs | **DONE** | All packs pass in lenient mode; missing location refs are runtime-resolved |
| 4 | Verify clean-machine install (Windows) | **DONE** | Scripts verified: `run_app.py` preflight, auto npm install, venv detection all working |
| 5 | Verify clean-machine install (macOS) | **OPEN** | Same path on macOS — needs manual verification on macOS hardware |
| 6 | Create `CHANGELOG.md` entry for v1.0 | **DONE** | Comprehensive changelog covering all V1–V12 features |
| 7 | Tag release commit as `v1.0.0` | **OPEN** | After all gates pass |
| 8 | Generate `.tar.gz` / `.zip` source distribution | **OPEN** | `git archive` or GitHub release |

### 5.3 Release Artifacts

```
storyteller-v1.0.0/
├── backend/                 # Python backend (FastAPI + LangGraph)
├── frontend/                # SvelteKit frontend (source; built on first launch)
├── ingestion/               # Lore ingestion pipeline
├── shared/                  # Shared utilities
├── storyteller/             # CLI module
├── data/
│   └── static/              # Era packs, setting packs, companions, starships
├── scripts/
│   └── bootstrap.sh         # One-step setup script
├── .env.example             # Environment template
├── .env.production.example  # Production template
├── pyproject.toml            # Python config (version 1.0.0)
├── Makefile                 # Build automation
├── run_app.py               # Unified launcher (auto-installs npm deps)
├── start_app.bat            # Windows shortcut
├── Dockerfile               # Docker build
├── docker-compose.yml       # Full-stack Docker Compose
├── QUICKSTART.md            # Getting started guide
├── README.md                # Project overview
└── CHANGELOG.md             # Version history
```

**Excluded from release:** `venv/`, `data/storyteller.db`, `data/lancedb/`, `node_modules/`, `__pycache__/`, `.git/`, test files (optional inclusion).

### 5.4 Installation Flow (User-Facing)

```
1. Install prerequisites:
   - Python 3.11+
   - Node.js 18+
   - Ollama (https://ollama.ai)

2. Extract release archive

3. First-time setup:
   $ cd storyteller-v1.0.0
   $ cp .env.example .env        # Edit if needed
   $ pip install -e .             # Install Python deps
   $ ollama pull mistral-nemo     # Pull primary LLM
   $ ollama pull qwen3:8b         # Pull secondary LLM
   $ ollama pull qwen3:4b         # Pull lightweight LLM

4. Launch:
   $ python run_app.py --dev      # Starts backend + frontend
   # OR on Windows:
   $ start_app.bat

5. Open browser to http://localhost:5173
```

---

## 6. MANUAL TESTING STRATEGY

### 6.1 Test Tiers

| Tier | What | How | When |
|------|------|-----|------|
| **T0: Automated Gates** | Unit + integration tests, release-gate markers | `make test`, `python -m pytest -m release_gate` | Every commit / PR |
| **T1: Smoke Test** | End-to-end pipeline validation | `python -m pytest backend/tests/test_e2e_smoke_flow.py` | Every release candidate |
| **T2: Manual Functional** | Full player journey walkthrough | Human tester follows script below | Every release candidate |
| **T3: Exploratory** | Freeform play sessions, edge cases | 30-60 min unscripted gameplay | Before final v1.0 tag |

### 6.2 Manual Test Script (T2)

Execute each scenario sequentially. Record PASS/FAIL and any notes.

#### Scenario 1: Fresh Install & First Run

```
[ ] Install from clean machine (no prior Storyteller data)
[ ] Run `pip install -e .` — no errors
[ ] Run `python run_app.py --dev` — backend starts, frontend builds
[ ] Open http://localhost:5173 — home page loads
[ ] First-run wizard appears
[ ] Wizard shows Ollama status (connected or guidance to install)
[ ] Wizard shows required models (with pull commands if missing)
[ ] After models are available, wizard allows proceeding
```

#### Scenario 2: Campaign Creation

```
[ ] Click "New Campaign" or equivalent
[ ] Select a universe/setting (Star Wars or Forgotten Realms)
[ ] Select an era pack
[ ] Character creation: name, species, background selection
[ ] Campaign scale selection (Short/Medium/Long/Epic)
[ ] Campaign creates successfully — redirected to prologue or play
[ ] Prologue/origin story renders (if applicable)
```

#### Scenario 3: Core Gameplay Loop

```
[ ] First turn: type an action and submit
[ ] Turn processes — loading indicator visible
[ ] Narrator prose appears (5-8 sentences, reasonable quality)
[ ] 4 player choices appear (diverse tones: Paragon/Investigate/Renegade/Neutral)
[ ] HUD shows location, time, companion info
[ ] Select a choice — next turn processes correctly
[ ] Repeat for 5+ turns — no crashes, no "stuck" states
```

#### Scenario 4: Streaming Turn

```
[ ] Submit a turn that uses streaming (/turn_stream)
[ ] Prose streams token-by-token (visible progressive rendering)
[ ] After stream completes, choices appear
[ ] No duplicate text or missing segments
```

#### Scenario 5: World Simulation

```
[ ] Play enough turns to cross a world tick boundary (~4 in-game hours)
[ ] News feed updates with world events
[ ] Rumors appear in context
[ ] NPC movements/faction changes reflect in world state
```

#### Scenario 6: Companion System

```
[ ] Companion is present in party
[ ] Companion reactions appear in narrative context
[ ] Banter lines appear occasionally (non-combat turns)
[ ] Affinity changes based on player choices (check via /state endpoint)
```

#### Scenario 7: Quest System

```
[ ] Quest activates based on trigger conditions
[ ] Quest progress tracked in quest log
[ ] Quest completion updates world state
```

#### Scenario 8: Save/Resume/Rewind

```
[ ] Close browser tab mid-session
[ ] Reopen — campaign appears in campaign list
[ ] Resume campaign — state is correct (turn number, location, NPCs)
[ ] Rewind to previous turn — world state restored correctly
[ ] Continue play after rewind — no corruption
```

#### Scenario 9: Settings & Cloud LLM (V12.0)

```
[ ] Navigate to Settings page
[ ] Provider list shows available providers
[ ] Can enter and test an API key (if cloud provider available)
[ ] Can create a custom LLM preset
[ ] Can assign preset to a campaign
[ ] Turns execute using configured provider/model
```

#### Scenario 10: Library & Lore Ingestion

```
[ ] Navigate to Library page
[ ] Upload a text/PDF file for ingestion
[ ] Ingestion job starts and completes
[ ] Ingested lore appears in subsequent turns (RAG retrieval)
[ ] Can create/delete lore source collections
```

#### Scenario 11: EraForge (V12.0)

```
[ ] Use EraForge to suggest a new era pack
[ ] Generate the era pack from suggestions
[ ] Generated pack appears in era selection
[ ] Can create a campaign using the generated pack
```

#### Scenario 12: Campaign Completion

```
[ ] Play a campaign to arc completion (or use /complete endpoint)
[ ] Epilogue renders correctly
[ ] Campaign marked as completed
[ ] Can start a new campaign (saga continuity if applicable)
```

#### Scenario 13: Error Recovery

```
[ ] Stop Ollama mid-turn — verify graceful error message, not crash
[ ] Restart Ollama — verify turns resume normally
[ ] Submit empty input — verify validation error returned
[ ] Submit extremely long input — verify 413 response
[ ] Rapid-fire turn submissions — verify rate limiting (429)
```

### 6.3 Automated Test Commands Reference

```bash
# Full test suite
make test

# Release-gate tests only
python -m pytest -m release_gate -q

# Backend unit tests
python -m pytest backend/tests -q

# Ingestion tests
python -m pytest ingestion -q --ignore=ingestion/test_tagger_pipeline.py

# E2E smoke test (requires running backend)
python -m pytest backend/tests/test_e2e_smoke_flow.py -q

# Frontend unit tests
cd frontend && npm test -- --run

# Frontend E2E (requires running app)
cd frontend && npm run test:e2e

# Specific test suites
python -m pytest backend/tests/test_turn_stream_pre_pipeline_order.py -q
python -m pytest backend/tests/test_turn_idempotency.py -q
python -m pytest backend/tests/test_health_detail.py -q

# Quick sanity check
make check
```

### 6.4 Known Test Gaps (Track for v1.1)

| Gap | Risk | Mitigation |
|-----|------|------------|
| No automated narrative quality scoring | Medium | Manual review of 10+ turn transcripts per release candidate |
| Era pack content depth not validated beyond file presence | Medium | Manual playthrough of each shipped era pack (2-3 turns each) |
| No load/stress testing | Low (single-user local app) | Monitor p95 latency during manual testing |
| Cloud provider integration not testable in CI | Low | Manual test with at least one cloud provider before release |

---

*Assessed against: Storyteller-V2 at v1.0.0-rc (2026-02-21)*
