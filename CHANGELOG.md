# Changelog

All notable changes to Storyteller AI are documented in this file.

Internal architecture versions (V1–V12) represent iterative milestones during development. The public release begins at **v1.0.0**.

---

## v1.0.1 — 2026-02-22

QA hardening pass: critical bug fix, test reliability improvements, robustness fixes, and DeepSeek cloud preset.

### Critical Fix (P0)

- **`PlayerStarship.campaign_id` type mismatch** — Pydantic model had `campaign_id: int` but migration 0040 changed the DB column to TEXT (UUIDs). Fixed to `campaign_id: str`. Any starship API call would have failed with a validation error.

### DeepSeek System Preset

- **New "deepseek" cloud preset** — Routes all LLM roles to DeepSeek (~$0.02/turn). Uses DeepSeek V3 (quality) for most roles; DeepSeek R1 (premium) for narrative-critical roles (Director, Narrator, Bible, Prologue). Requires `DEEPSEEK_API_KEY`.
- **Provider-specific preset auto-pinning** — When a preset name matches a registered cloud provider (e.g., "deepseek"), `preferred_provider` is automatically set, ensuring tier resolution always selects the correct provider.
- **Frontend integration** — DeepSeek appears in SettingsPanel cloud preset selector and campaign settings.
- **VALID_CLOUD_PRESETS** updated: `local`, `budget`, `balanced`, `quality`, `cloud_all`, `deepseek`, `custom`.

### Test Reliability (P1)

- **`test_world_sim.py`** — Replaced stale `simulate_faction_tick` mock patches with `WorldMindAgent` mocks (3 test functions). The world sim node now uses `WorldMindAgent(llm=...).simulate()`.
- **`test_worldsim_events.py`** — Same `WorldMindAgent` mock fix.
- **`test_turn_idempotency.py`** — Fixed patch targets from `v2_campaigns` to `v2_turn` (turn endpoints moved).
- **`test_v2_campaigns.py`** — Fixed `DEFAULT_DB_PATH` and `MAX_USER_INPUT_CHARS` patch targets to `v2_turn`.
- **`test_warnings_turn_response.py`** — Fixed `DEFAULT_DB_PATH` patch target to `v2_turn`.
- **`test_turn_stream_pre_pipeline_order.py`** — Fixed monkeypatch targets from source modules to `backend.app.core.graph.*` (graph.py binds references at import time). Fixed import from `v2_campaigns` to `v2_turn`.
- **`test_setting_pack_v2.py`** — Skipped test for removed `enrich_era_pack_v2.py` script (functionality moved to EraForge agent).
- **`test_setting_rules.py`** — Updated from `CampaignArchitect.build()` to `CampaignBibleAgent.build()`.

### Robustness (P2)

- **Party state corruption handling** — `load_party_state()` now type-checks all legacy fields (`party`, `party_affinity`, `party_traits`, `loyalty_progress`) before migration. Logs specific validation errors. Skips corrupt companion entries individually instead of crashing.
- **Inventory FK cascade** — Migration 0043: recreated `inventory` table with `ON DELETE CASCADE` on `owner_id` FK. Deleting a character now cascades to their inventory.
- **Frontend test stability** — Fixed `campaigns.test.ts` (added `browser: true` mock, `localStorage.clear()`), `DialogueWheel.test.ts` (added cleanup), and `vitest.config.ts` (replaced `sveltekit()` with `svelte()` plugin, disabled CSS preprocessing).

### Improvements (P3)

- **Expanded PERSUASION_VERBS** — Added 32 new verb conjugations (8 verb families: seduce, manipulate, coerce, charm, flatter, plead, grovel, cajole) for more accurate intent routing of persuasion actions.
- **Database indexes** — Migration 0043 adds performance indexes on `turn_events(event_type)`, `truth_facts(fact_key)`, and `turn_idempotency(idempotency_key)`.

### Database

- 43 migrations (0001–0043, 0024 absent)
- New: migration 0042 (decision ledger), migration 0043 (inventory cascade + indexes)

---

## v1.0.0 — 2026-02-21

First public release. Local-first, setting-agnostic narrative RPG engine powered by LLM agents and a LangGraph state-machine pipeline.

### Core Engine

- **15-node LangGraph turn pipeline**: router → mechanic → encounter → world_sim → moments → arc_planner → interlude → scene_frame → director → companion_reaction → narrator → narrative_validator → choice_crafter → commit
- **Single transaction boundary**: only the Commit node writes to the database; all prior nodes are pure state transforms
- **Event sourcing**: write-once append-only `turn_events` log with projections to normalized tables (inventory, relationships, quest log, factions)
- **Idempotent turns**: `Idempotency-Key` header prevents duplicate execution
- **Rewind/undo**: restore campaign state to any prior turn via snapshots
- **Turn streaming**: SSE endpoint for token-by-token narrative delivery

### LLM Agent Architecture (V4.0–V5.0)

- **30+ specialized agents** replacing all deterministic systems with LLM-backed resolution
- **ResolutionAgent**: LLM Game Master for action resolution (replaced deterministic d20 engine)
- **WorldMindAgent**: LLM world simulation for faction movements, NPC actions, rumor propagation
- **ContinuityAgent**: Truth Ledger 2.0 for narrative consistency tracking
- **QuestWeaverAgent**: dynamic quest generation and progression
- **MemoryAgent**: NPC narrative memory system
- **ProgressionAgent + PsychArchivistAgent**: character growth and psychological profiling
- **BaseAgent class**: lightweight base with lazy LLM init and JSON/text completion helpers
- **Deferred maintenance agents**: heavy agents (Memory, QuestWeaver, Progression, PsychArchivist, Revelation, CallbackCrystallizer, PlayerProfile) run post-commit to keep turn latency low

### Campaign Bible System (V6.0)

- **CampaignBibleAgent**: generative screenplay bible replaces static era content
- **ArcScreenplayAgent**: per-arc narrative blueprints
- **OriginScreenplayAgent**: playable backstory generation
- GM Context system with pacing instructions and tone guidance

### Multi-Arc Narrative (V7.0–V9.0)

- **ArcWeaverAgent**: evaluates arc transitions and seeds new arcs
- **Interlude node**: breathing room between arc resolution and new arc setup
- **Moments system**: scripted narrative triggers from era pack `moments.yaml`
- **Turn snapshots**: world state captured per turn for rewind support
- **Canon events timeline**: historical event tracking for narrative grounding
- **NPC state extraction**: schema-based NPC state persistence
- Novel-length storytelling support with campaign settings (narrator mode, pacing)

### Narrative Intelligence (V10.0)

- **NarrativeValidator node**: automated prose quality checking with repair
- **Creative deviation tracking**: monitors and corrects narrative drift
- **Scene loop detection**: prevents repetitive scene patterns
- **Bridge paragraphs**: smooth transitions between turns

### Player Experience (V11.0)

- **Origin Story engine**: playable backstory before prologue (`/origin` route)
- **Cinematic prologue**: crawl intro with skip button and direct-to-play flow
- **First-run wizard**: guided setup with Ollama status, model pull commands, hard-block when dependencies missing
- **Universe UX**: rich era descriptions, species/background selection, companion preview
- **Lore ingestion UI**: Library page with source management, upload, and ingestion status
- **Optional NPC portraits + location key art** (behind `ENABLE_PORTRAITS` flag)
- **Character codex/journal**: in-play journal drawer with NPC, faction, and lore entries
- **HudBar component**: extracted gameplay HUD with location, time, companion info
- **Skeleton loaders**: loading states throughout the creation and play flows

### Cloud Provider System (V12.0)

- **5 cloud LLM providers**: Anthropic (Claude), OpenAI (GPT), xAI (Grok), DeepSeek, Google (Gemini)
- **Settings UI**: manage API keys, test connectivity, per-role model configuration
- **Preset system**: Budget / Balanced / Quality / Cloud All / DeepSeek tiers with automatic provider resolution
- **User-created presets**: custom per-role provider/model assignments stored in DB
- **Per-campaign LLM configuration**: override presets at the campaign level
- **Provider key storage**: DB-backed with environment variable fallback
- **App preferences**: persistent app-level settings

### EraForge (V12.0)

- **EraForge endpoints**: suggest, generate, and refine custom era packs via LLM
- **Generated packs**: appear in era selection and support full campaign creation

### Export (V12.0)

- **Novel export**: `GET /v2/export/novel` exports campaign transcript as Markdown

### Content System

- **Setting-agnostic architecture**: modular era packs with `SettingRules` contamination prevention
- **4-lane RAG style retrieval**: Base, Era, Genre, Archetype style lanes via LanceDB
- **Lore retrieval**: contextual lore grounding from ingested PDF/EPUB/TXT sources
- **Knowledge graph extraction**: entity/relationship extraction for runtime retrieval
- **11 CLI commands**: `doctor`, `setup`, `dev`, `ingest`, `query`, `extract_knowledge`, `organize_ingest`, `models`, `style_audit`, `build_style_pack`, `generate_era_content`

### Shipped Era Packs

- Star Wars Legends: Rebellion, Old Republic, New Republic, New Jedi Order, Dark Times
- Additional universes supported via custom era packs and EraForge

### API

- FastAPI backend with 70+ endpoints across 9 route modules
- Bearer/API-key auth (optional, enabled when `STORYTELLER_API_TOKEN` is set)
- In-memory rate limiting (10 req/min per IP on turn endpoints)
- `X-Request-ID` response header for request tracing
- OpenAPI documentation at `/docs`

### Frontend

- SvelteKit 5 with static adapter
- KOTOR 2-inspired visual theme (Old Republic aesthetic)
- Routes: home, create, origin, prologue, play, complete, library, settings
- Playwright E2E tests covering 5 critical player journeys

### Database

- SQLite with WAL mode for concurrent reads
- 43 migrations (0001–0043, 0024 absent)
- Key tables: campaigns, characters, inventory, turn_events, rendered_turns, truth_facts, truth_events, turn_snapshots, canon_events, npc_states, quest_entries, pending_world_state_patches, player_starships, provider_keys, user_presets, app_preferences, decision_ledger

### Deployment

- `run_app.py` unified launcher with preflight checks, auto npm install, port detection
- `start_app.bat` Windows shortcut
- `scripts/bootstrap.sh` one-step setup for Linux/macOS
- Docker + Docker Compose support
- `.env.example` and `.env.production.example` templates

### Testing

- `pytest` with `release_gate`, `narrative`, and `smoke` markers
- Narrative regression harness with deterministic test seeds
- Frontend unit tests (Vitest) and E2E tests (Playwright)
- `make check` quick sanity gate, `make test` full suite

---

*For architecture details, see the `docs/` directory.*
