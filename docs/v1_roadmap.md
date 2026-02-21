# Storyteller V1.0 Roadmap

Comprehensive roadmap covering: playable origin stories, v1.0 polish, codebase reorganization, distributable packaging, and in-game LLM configuration.

---

## 1. PLAYABLE ORIGIN STORIES (Dragon Age: Origins Model)

### The Vision

Instead of choosing a background via CYOA cards and immediately jumping to the main campaign, the player **plays through a 3-5 turn origin sequence** that establishes their character's identity through gameplay choices, not form fields.

**Example flow for an Imperial Defector:**
1. Player selects "Imperial Defector" background in creation wizard
2. Player answers CYOA questions (rank: ISB Agent, catalyst: witnessed atrocities)
3. Instead of jumping to the main campaign, the game drops them **into a playable scene from their past** — they're standing in an Imperial briefing room, being ordered to interrogate a Rebel prisoner
4. Over 3-5 turns, the player makes choices that establish who they are (do they follow orders? do they help the prisoner escape? do they play both sides?)
5. These choices carry forward as `origin_context` — shaping Arc 1's opening, companion reactions, and faction standing
6. After the origin, the **existing prologue system** kicks in (inciting incident → departure → main campaign)

### What Already Exists

The infrastructure is surprisingly strong:

| Component | Status | Details |
|-----------|--------|---------|
| `prologue_engine.py` | Built | 3-stage constrained sequence (SETUP → INCITING_INCIDENT → DEPARTURE) with deterministic stage advancement |
| `prologue_arc_state` | Built | Tracks current stage, stage start turn, stages visited |
| `build_prologue_arc_guidance()` | Built | Injects stage-specific pacing hints, tension levels, and action weights into the Director |
| `is_prologue_complete()` | Built | Auto-detects when all stages visited with minimum turns spent |
| `build_origin_context_manifest()` | Built | Captures facts, threads, NPCs from the origin into a handoff dict |
| `origin_context` → Arc 1 | Built | `ArcScreenplayAgent` reads `origin_context` to shape the first arc |
| `arc_planner_node` branching | Built | Detects `prologue_mode` and takes a different code path |
| Background CYOA with `thread_seed` | Built | Each background choice already generates a narrative hook |
| `PrologueScreenplayAgent` | Built | Generates opening scene blueprint with NPC cast, inciting moment, tone |

### What Needs to Be Built

The existing prologue system handles the **inciting incident** (what kicks off the adventure). The origin story is a **new layer that comes before it** — it's about who you were before the adventure started.

```
Current:    Character Creation → [Static Prologue Briefing] → Main Campaign
Proposed:   Character Creation → [Playable Origin (NEW)] → [Playable Prologue] → Main Campaign
```

#### 1.1 Origin Screenplay Agent (New Agent)

A new agent that generates a **playable backstory blueprint** from the background + CYOA answers. Different from `PrologueScreenplayAgent` — it generates a scene from the character's **past**, not the inciting incident.

**Input:** Background ID, species, CYOA choice effects, setting rules
**Output:** `OriginScreenplay` — a structured blueprint for a 3-5 turn playable backstory

```python
class OriginScreenplay(BaseModel):
    origin_title: str                    # "The Last Briefing"
    setting_description: str             # "An ISB briefing room aboard the Star Destroyer Adjudicator"
    opening_narration: str               # 2-3 sentences setting the scene
    npc_cast: list[OriginNpc]            # 2-3 NPCs present in the origin
    central_dilemma: str                 # The moral/practical choice the player faces
    resolution_paths: list[str]          # 2-3 ways the origin can resolve
    departure_moment: str                # What event ends the origin and transitions to present day
    tone: str                            # From background tone mapping
    time_context: str                    # "Three months before the events of the main story"
```

**Key design principle:** The origin should present **one central dilemma** with 2-3 resolution paths. It's not a mini-campaign — it's a focused character-defining moment.

#### 1.2 Origin Engine (New Module)

Mirrors `prologue_engine.py` but with origin-specific stages:

```python
ORIGIN_STAGES = ["SCENE_SET", "DILEMMA", "RESOLUTION"]
```

- **SCENE_SET** (1-2 turns): Establish the setting, introduce NPCs, let the player explore
- **DILEMMA** (1-2 turns): Present the central moral/practical choice
- **RESOLUTION** (1 turn): Player's choice plays out, consequences shown, time-skip to present

Stage characteristics:
- SCENE_SET: Tension CALM, Action weight SOCIAL 0.6 / EXPLORE 0.4
- DILEMMA: Tension ESCALATING, inject `central_dilemma` into Director guidance
- RESOLUTION: Tension RESOLVING, inject `departure_moment` as transition trigger

#### 1.3 Origin Context Capture

When the origin completes, capture:
- **Choices made** during the origin (tone distribution, key decisions)
- **NPCs encountered** (carry forward to main campaign — the ISB officer you defied might hunt you)
- **Established facts** from the origin's truth ledger
- **Personality signal** (did the player prioritize compassion, pragmatism, or ruthlessness?)

This feeds into `origin_context` which already flows to Arc 1.

#### 1.4 Frontend Changes

- **New route: `/origin`** — playable origin sequence using the same play UI components (ApproachCards, narrative panel, NPC speech)
- **Origin-specific HUD:** Simplified — no quest tracker, no companion sidebar (these haven't been unlocked yet). Just narrative + choices + a "time period" indicator showing this is a flashback
- **Transition animation:** When origin completes, a time-skip visual ("Three months later...") before transitioning to the prologue
- **Skip option:** "Skip Origin" button for players who want to jump straight to the action (origin context generated from CYOA answers alone, as it works today)

#### 1.5 Flow Integration

```
Creation Wizard
  → setupAuto() now also calls OriginScreenplayAgent
  → Player redirected to /origin (if origin_mode enabled)
  → 3-5 playable turns establishing backstory
  → Origin completes → origin_context captured
  → Time-skip transition visual
  → /prologue (existing system — inciting incident)
  → 3-5 turns of prologue (SETUP → INCITING_INCIDENT → DEPARTURE)
  → Prologue completes → /play (main campaign begins)
```

**Total onboarding turns:** 6-10 turns before the main campaign starts, but every turn is playable and establishes the character. Compare to Dragon Age: Origins which has 30-60 minute origin stories.

#### 1.6 Effort Estimate

| Task | Effort |
|------|--------|
| `OriginScreenplayAgent` (new agent) | Medium |
| `origin_engine.py` (mirrors prologue_engine) | Medium — can reuse prologue_engine patterns heavily |
| `arc_planner` branching for origin_mode | Low — same pattern as prologue_mode branching |
| `/origin` route (frontend) | Medium — reuse play components with simplified HUD |
| setupAuto integration | Low — add one more agent call |
| Time-skip transition component | Low |
| Skip origin button | Low |

---

## 2. V1.0 POLISH CHECKLIST

### 2.1 Pre-Release (Must Fix)

| # | Issue | File(s) | Effort |
|---|-------|---------|--------|
| 1 | **No setup progress indicator** — 15-30s `setupAuto()` call shows only "Setting up..." text | `create/+page.svelte` | Low |
| 2 | **15+ generic `except Exception` blocks** in main API file — swallow errors, break observability | `api/v2_campaigns.py` | Medium |
| 3 | **Missing DB index** on `truth_facts(campaign_id)` — queries slow for long campaigns | New migration file | Low |
| 4 | **`console.warn`/`console.error`** in production code | `SettingsPanel.svelte` lines 73, 93 | Low |
| 5 | **No global error boundary** — catastrophic failures show blank screen | `+error.svelte` (new) | Low |
| 6 | **`MAX_USER_INPUT_CHARS` not validated** in Pydantic model — validated only at DB insert | `campaign_models.py` | Low |
| 7 | **No enum validation** for `campaign_scale`, `difficulty`, `campaign_mode` — accepts any string | `campaign_models.py` | Low |
| 8 | **DEV_MODE defaults to True** — should require explicit opt-in for production | `main.py` line 45 | Low |
| 9 | **Rate limit hardcoded** (10/min) — should be configurable via ENV | `main.py` line 355 | Low |

### 2.2 Polish (Should Fix)

| # | Issue | File(s) | Effort |
|---|-------|---------|--------|
| 10 | **Home screen lacks atmosphere** — no art, no ambient visuals, no mood | `+page.svelte` | Medium |
| 11 | **Era cards use thin descriptions** — rich metadata (summary, tone, key_conflicts, themes) exists in era.yaml but isn't surfaced | `create/+page.svelte` | Low |
| 12 | **Gender selector is binary** with no context — should be pronoun framing | `create/+page.svelte` | Low |
| 13 | **Prologue page is static** — should be playable turns, not a read-only briefing | `prologue/+page.svelte` | Medium |
| 14 | **Thread seed not shown** in background selection — the best hook text is hidden | `create/+page.svelte` | Low |
| 15 | **Campaign scale invisible** — engine supports small/medium/large/epic but player never chooses | `create/+page.svelte` | Low |
| 16 | **Companion preview buried** — appears after character is committed, should influence creation | `create/+page.svelte` | Medium |
| 17 | **No skeleton/loading screens** for campaign load and creation | Multiple frontend files | Medium |
| 18 | **No "loading choices..." indicator** between narrator finish and choice_crafter render | `play/+page.svelte` | Low |
| 19 | **Ollama status not visible in gameplay HUD** — only shown in layout banner | `play/+page.svelte` | Low |

### 2.3 Documentation (Before Ship)

| # | What | Effort |
|---|------|--------|
| 20 | **Troubleshooting guide** — common Ollama/LanceDB issues, model download instructions | Low |
| 21 | **ER diagram** for database schema (add to `docs/03_state_and_persistence.md`) | Low |
| 22 | **API backward compatibility policy** — v2 prefix suggests v1 existed | Low |

### 2.4 Post-Release (v1.1 Backlog)

| # | What | Priority |
|---|------|----------|
| 23 | Character codex/journal (NPCs met, locations, lore, choices) | High |
| 24 | Quick-start archetypes ("The Reluctant Hero", "The Ruthless Mercenary") | Medium |
| 25 | "Browse Universes" redesign — split browse vs. manage modes | Medium |
| 26 | Frontend integration tests (creation wizard, turn submission, campaign resume) | Medium |
| 27 | Query caching for CampaignBibleAgent (per setting_id) | Medium |
| 28 | World state snapshot pagination (snapshot every 10 turns, keep last 3) | Low |
| 29 | LanceDB RAG query limits (add LIMIT 100) | Low |

---

## 3. CODEBASE REORGANIZATION (Senior Engineer Handoff)

### 3.1 Current State: 7/10

The codebase is **well-organized overall** — clear module hierarchy, no circular imports, clean dependency graph, minimal dead code. A Senior Engineer would be productive in this codebase within a day. But there are specific areas that need cleanup:

### 3.2 High Priority Refactors

#### A. Split `v2_campaigns.py` (3,024 lines → 3-4 files)

This is the single largest maintainability issue. Every API route lives in one file.

```
Current:
  api/v2_campaigns.py     (3,024 lines — everything)

Proposed:
  api/v2_campaigns.py     (~800 lines — turn execution, state/transcript)
  api/v2_setup.py          (~600 lines — setupAuto, campaign creation)
  api/v2_settings.py       (~400 lines — settings, cloud preset, narrator mode)
  api/v2_progression.py    (~500 lines — completion, rewind, era_transition, prologue)
  api/campaign_helpers.py  (~400 lines — shared utilities, validation)
```

#### B. Move Prompt Templates to YAML/Markdown

`narrator_prompt.py` is 1,150 lines of Python that's mostly string templates. This is hostile to non-engineers who might want to tune the narrative voice.

```
Current:
  core/agents/narrator_prompt.py  (1,150 lines of Python strings)

Proposed:
  prompts/
    narrator/
      system.md           # System prompt template
      style_guide.md       # Show-don't-tell rules
      constraints.md       # Length, POV, tone rules
    director/
      system.md
    choice_crafter/
      system.md
  core/agents/narrator_prompt.py  (~200 lines — template loader + variable injection)
```

#### C. Create `BaseAgent` Class

30+ agents share boilerplate (instantiate `AgentLLM`, call `call_with_json_reliability`, handle fallback). A base class reduces duplication:

```python
class BaseAgent:
    """Common pattern for all LLM-backed agents."""

    role: str               # Subclass sets this
    schema_class: type      # Pydantic output schema

    def __init__(self, llm: AgentLLM | None = None):
        self._llm = llm or AgentLLM(self.role)

    def generate(self, **kwargs) -> dict:
        result = call_with_json_reliability(
            llm=self._llm,
            role=self.role,
            schema_class=self.schema_class,
            system_prompt=self._build_system_prompt(**kwargs),
            user_prompt=self._build_user_prompt(**kwargs),
            fallback_fn=lambda: self._fallback(**kwargs),
        )
        return result

    def _build_system_prompt(self, **kwargs) -> str: ...   # Subclass implements
    def _build_user_prompt(self, **kwargs) -> str: ...     # Subclass implements
    def _fallback(self, **kwargs) -> dict: ...             # Subclass implements
```

#### D. Consolidate Config + Constants

`config.py` (365 lines) and `constants.py` (814 lines) both reference token budgets and model settings. Consolidate:

```
Current:
  config.py       (365 lines — env parsing, MODEL_CONFIG, cloud presets)
  constants.py    (814 lines — ROLE_TOKEN_BUDGETS, action costs, prompt fragments)

Proposed:
  config/
    __init__.py          # Re-exports for backward compat
    env.py               # Environment variable parsing
    models.py            # MODEL_CONFIG, cloud presets, provider resolution
    budgets.py           # Token budgets, context limits
    constants.py         # Game constants (action costs, tone mappings)
```

#### E. Standardize Error Handling

Multiple patterns in use (`log_error_with_context()`, direct `logger.exception()`, generic `except Exception`). Standardize:

```python
# Decorator for agent error handling
@with_agent_error_handling(agent_name="NarratorAgent", fallback_fn=narrator_fallback)
def generate(self, ...):
    ...
```

### 3.3 Medium Priority Cleanup

| # | What | Why |
|---|------|-----|
| 1 | Remove duplicate `smuggler` / `bounty_hunter` entries in `rebellion/backgrounds.yaml` | Two definitions exist (original + V2.9 expansion) — should be merged into one definitive version per background |
| 2 | Type-hint ingestion scripts | `ingestion/ingest_lore.py` and related scripts lack type annotations |
| 3 | Add `py.typed` marker | Signals to downstream consumers that the package is typed |
| 4 | Document agent naming conventions | No standard for agent file names vs. class names (e.g., `narrator.py` vs `choice_crafter_agent.py`) |
| 5 | Extract play page components | `play/+page.svelte` (2,830 lines) could extract HUD bar, transcript panel, and drawer logic into sub-components |

### 3.4 What a Senior Engineer Would Approve Of

These are strengths to preserve during reorganization:

- **Shared module pattern** — `shared/` keeps ingestion decoupled from app logic
- **AgentLLM abstraction** — universal provider wrapper with per-role config
- **Single transaction boundary** — only `CommitNode` calls `conn.commit()`
- **Event sourcing** — append-only turn_events with snapshot-based rewind
- **Setting-agnostic architecture** — era packs + SettingRules
- **3-tier model config** (defaults → env overrides → per-campaign presets)

---

## 4. DISTRIBUTABLE PACKAGING (Executable Wrapper)

### 4.1 Recommended Approach: Tauri

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

### 4.2 Build Pipeline

```
1. Build frontend:     npm run build        → frontend/build/ (static files)
2. Bundle backend:     pyinstaller ...      → dist/storyteller-api (single binary)
3. Bundle Tauri:       cargo tauri build    → dist/Storyteller.exe / .dmg / .AppImage
```

### 4.3 First-Run Experience

When the user launches the app for the first time:

1. **Ollama check** — detect if Ollama is installed and running
   - If yes: show green status, list available models
   - If no: show setup wizard with download link + instructions
2. **Model download** — prompt to pull required models (`mistral-nemo:latest`, `qwen3:8b`)
3. **Optional cloud setup** — "Want higher quality? Connect a cloud API key" (see Section 5)
4. **Ready to play** — redirect to home screen

### 4.4 Alternative: Electron

If Tauri proves too complex (Rust toolchain requirement), Electron works:

```
storyteller-electron/
├── main.js                   # Electron main process
├── preload.js                # IPC bridge
├── frontend/                 # SvelteKit static build
└── backend/                  # Bundled Python backend
```

Downside: ~150MB+ binary, higher memory usage.

### 4.5 Alternative: Simple Launcher Script

Lowest effort — ship a launcher script (`.bat` / `.sh` / `.command`) that:
1. Starts the Python backend (`uvicorn backend.app.main:app`)
2. Opens the browser to `localhost:3000`
3. Manages lifecycle (shutdown on close)

This is viable for v1.0 if native app packaging is out of scope.

---

## 5. IN-GAME LLM CONFIGURATION UI

### 5.1 What Already Exists

The system already has a sophisticated 3-tier model configuration:

| Tier | How It Works | Status |
|------|-------------|--------|
| **Defaults** | `MODEL_CONFIG` dict in `config.py` — 30+ roles with default provider/model | Built |
| **Env Overrides** | `STORYTELLER_{ROLE}_PROVIDER/MODEL/API_KEY/BASE_URL` per role | Built |
| **Campaign Presets** | `cloud_preset` in SettingsPanel — local/budget/balanced/quality | Built (UI + backend) |

The SettingsPanel already shows:
- Narrator mode (concise/novel/epic)
- Cloud quality preset with cost estimates ($0/turn → $0.05/turn)
- These persist per-campaign in `world_state_json`

### 5.2 What Needs to Be Built

#### A. API Key Management Page

**New route: `/settings` (global, not per-campaign)**

```
┌─────────────────────────────────────────────────────┐
│  LLM Providers                                      │
│  ───────────────                                    │
│                                                     │
│  Ollama (Local)                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ Base URL: [http://localhost:11434        ]   │    │
│  │ Status:   ● Connected (3 models loaded)     │    │
│  │ Models:   mistral-nemo:latest, qwen3:8b,    │    │
│  │           qwen3:4b                          │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  Anthropic (Cloud)                                  │
│  ┌─────────────────────────────────────────────┐    │
│  │ API Key:  [sk-ant-...••••••••           ]   │    │
│  │ Status:   ● Connected                       │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  OpenAI (Cloud)                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ API Key:  [sk-...••••••••               ]   │    │
│  │ Status:   ○ Not configured                  │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  OpenAI-Compatible (Custom)                         │
│  ┌─────────────────────────────────────────────┐    │
│  │ Base URL: [                              ]  │    │
│  │ API Key:  [                              ]  │    │
│  │ Status:   ○ Not configured                  │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  [Test All Connections]     [Save]                   │
└─────────────────────────────────────────────────────┘
```

**Backend:**
- New endpoint: `POST /v2/settings/providers` — save provider configs
- New endpoint: `GET /v2/settings/providers` — load provider configs
- New endpoint: `POST /v2/settings/providers/test` — test connection to a provider
- Store in SQLite table `provider_configs(provider TEXT PK, base_url TEXT, api_key_encrypted TEXT, updated_at TEXT)`
- API keys encrypted at rest using a local machine key (Fernet symmetric encryption)

#### B. Per-Agent Model Assignment (Advanced Settings)

**Accessible from: Settings → Advanced → Agent Configuration**

Two modes:

**Simple Mode (Presets):**
```
┌─────────────────────────────────────────────────────┐
│  Quality Preset                                     │
│  ──────────────                                     │
│                                                     │
│  ○ All Local         — Free, Ollama only            │
│  ○ Budget Cloud      — $0.01/turn, narrator on      │
│                        cloud                        │
│  ○ Balanced          — $0.02/turn, 4 key agents     │
│                        on cloud                     │
│  ○ Full Cloud        — $0.05/turn, all narrative    │
│                        agents on cloud              │
│  ● Custom            — Configure each agent below   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Advanced Mode (Per-Agent):**
```
┌─────────────────────────────────────────────────────┐
│  Agent Configuration                                │
│  ───────────────────                                │
│                                                     │
│  ┌──────────────┬──────────────┬──────────────────┐ │
│  │ Agent        │ Provider     │ Model            │ │
│  ├──────────────┼──────────────┼──────────────────┤ │
│  │ Director     │ [Ollama ▾]   │ [mistral-nemo ▾] │ │
│  │ Narrator     │ [Anthropic▾] │ [claude-sonn ▾]  │ │
│  │ Choice Craft │ [Ollama ▾]   │ [qwen3:8b    ▾]  │ │
│  │ Mechanic     │ [Ollama ▾]   │ [qwen3:8b    ▾]  │ │
│  │ Companion    │ [Ollama ▾]   │ [qwen3:8b    ▾]  │ │
│  │ World Sim    │ [Ollama ▾]   │ [qwen3:4b    ▾]  │ │
│  │ Biographer   │ [Ollama ▾]   │ [qwen3:8b    ▾]  │ │
│  │ ...          │              │                  │ │
│  └──────────────┴──────────────┴──────────────────┘ │
│                                                     │
│  [Reset to Defaults]          [Save]                │
└─────────────────────────────────────────────────────┘
```

**Backend changes:**
- New endpoint: `GET /v2/settings/agents` — returns current per-role config
- New endpoint: `PATCH /v2/settings/agents` — updates per-role config
- New endpoint: `GET /v2/settings/agents/available-models` — lists available models per provider (Ollama: query `/api/tags`, Cloud: hardcoded list)
- Config resolution: UI settings → env overrides → defaults (UI takes highest priority)
- Store in SQLite table `agent_configs(role TEXT PK, provider TEXT, model TEXT, updated_at TEXT)`

#### C. Integration with Existing System

The current `AgentLLM.__init__()` already accepts `config_override`. The change is straightforward:

```python
# Current flow:
AgentLLM(role="narrator")
  → Reads MODEL_CONFIG["narrator"]
  → Checks env overrides (STORYTELLER_NARRATOR_*)
  → Applies campaign cloud_preset override

# New flow:
AgentLLM(role="narrator")
  → Reads MODEL_CONFIG["narrator"]              # Tier 1: defaults
  → Checks env overrides (STORYTELLER_NARRATOR_*) # Tier 2: env
  → Checks DB agent_configs table                 # Tier 3: UI settings (NEW)
  → Applies campaign cloud_preset override        # Tier 4: per-campaign
```

### 5.3 First-Run Setup Wizard

For the executable version, a setup wizard on first launch:

```
Step 1: "Welcome to Storyteller AI"
  → Brief intro, what you need to play

Step 2: "Local AI Engine (Ollama)"
  → Detect Ollama installation
  → If missing: download link + instructions
  → If present: check required models, offer to pull missing ones

Step 3: "Cloud AI (Optional)"
  → "For higher quality narration, connect a cloud provider"
  → API key input for Anthropic/OpenAI
  → "Skip — I'll use local models only"

Step 4: "Ready!"
  → Show detected configuration summary
  → "Start Playing" button
```

---

## 6. IMPLEMENTATION PRIORITY

### Phase 1: V1.0 Release (Core Polish)

**Goal:** Ship a stable, polished single-player experience.

| Week | Tasks |
|------|-------|
| 1 | Fix 9 pre-release items (Section 2.1): progress indicator, error handling, missing validations, dev mode default |
| 1 | Split `v2_campaigns.py` into 4 files (Section 3.2A) |
| 2 | Polish creation wizard: rich era descriptions, thread seed preview, pronoun framing, campaign scale selector |
| 2 | Make prologue playable (wire into play loop instead of static briefing) |
| 3 | Home screen atmosphere + error boundary + skeleton loaders |
| 3 | Documentation: troubleshooting guide, ER diagram |

### Phase 2: Origin Stories + LLM Config UI

**Goal:** Playable backstories and user-facing model configuration.

| Week | Tasks |
|------|-------|
| 4 | Build `OriginScreenplayAgent` + `origin_engine.py` |
| 4 | Build `/origin` route with simplified play UI |
| 5 | Build `/settings` page with provider management |
| 5 | Build per-agent model assignment (advanced settings) |
| 6 | Build first-run setup wizard |
| 6 | Integration testing: full flow from origin → prologue → play |

### Phase 3: Executable Packaging

**Goal:** Distributable application.

| Week | Tasks |
|------|-------|
| 7 | PyInstaller bundling of Python backend |
| 7 | Tauri app shell with sidecar process management |
| 8 | First-run Ollama detection + model download UI |
| 8 | Cross-platform builds (Windows .exe, macOS .dmg, Linux .AppImage) |
| 9 | Testing + packaging pipeline |

### Phase 4: Senior Engineer Handoff Prep

**Goal:** Codebase ready for external review.

| Week | Tasks |
|------|-------|
| 10 | Move prompt templates to YAML/Markdown |
| 10 | Create `BaseAgent` class, migrate 5 key agents |
| 11 | Consolidate config/constants into `config/` package |
| 11 | Standardize error handling patterns |
| 12 | Merge duplicate background entries, add type hints to ingestion |
| 12 | Extract play page sub-components |

---

## 7. RISK ASSESSMENT

| Risk | Severity | Mitigation |
|------|----------|------------|
| Origin stories add 3-5 turns before gameplay — players might find it too slow | Medium | Always offer "Skip Origin" button. Keep origins to 3 turns max for the skip-prone player. |
| Per-agent model config complexity confuses casual users | Low | Hide behind "Advanced" toggle. Default to simple preset mode. |
| Tauri sidecar process management is fragile on Windows | Medium | Fall back to launcher script if sidecar fails. Test extensively on Windows. |
| API key storage security in SQLite | Medium | Fernet encryption with machine-local key. Never log keys. Warn users in UI. |
| Splitting `v2_campaigns.py` could introduce import issues | Low | Use FastAPI router includes pattern. Test all endpoints after split. |
| Prompt templates in YAML lose Python string formatting power | Low | Use Jinja2 or simple `{variable}` interpolation in YAML templates. |

---

*Compiled from: player experience review, prologue system exploration, v1.0 readiness audit, codebase organization audit, and model configuration system analysis.*
*Assessed against: Storyteller-V2 at V11.0 (v2.16)*
