# 06 — API & Routes

## Server Setup

**Primary wiring file:** `backend/main.py`

- Framework: FastAPI
- App metadata: `title="Storyteller AI API"`, `version="2.0.0"`
- V2 campaign router mounted at `/v2`
- Starship router mounted at `/v2/starships`
- EraForge router mounted at `/v2/eraforge`
- Export router mounted at `/v2/export`
- Settings router mounted at `/v2/settings`
- CORS origins come from `STORYTELLER_CORS_ALLOW_ORIGINS` (with localhost defaults when unset)
- Optional bearer/API-key auth is enabled only when `STORYTELLER_API_TOKEN` is set
- In-memory turn rate limit: **10 requests/minute per IP** on endpoints containing `/turn`

## Health & Root Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/` | API banner + version |
| `GET` | `/health` | Basic liveness response |
| `GET` | `/health/detail` | Detailed diagnostics (Ollama, data root, LanceDB tables, era packs, role models) |

## V2 Campaign / Content Endpoints

**Implementation:** `backend/app/api/v2_campaigns.py`

### Content & Era discovery

**Implementation:** `backend/app/api/v2_content.py`

- `GET /v2/content/catalog`
- `GET /v2/content/default`
- `GET /v2/content/{setting_id}/{period_id}/summary`
- `GET /v2/era/{era_id}/locations`
- `GET /v2/era/{era_id}/backgrounds`
- `GET /v2/era/{era_id}/species` — List available species for a given era
- `GET /v2/era/{era_id}/companions`
- `GET /v2/model_config` — Current LLM model configuration
- `GET /v2/debug/era-packs`

### Campaign creation and lookup

**Implementation:** `backend/app/api/v2_campaigns.py`

- `POST /v2/setup/auto`
- `POST /v2/campaigns`
- `GET /v2/campaigns`
- `GET /v2/campaigns/{campaign_id}/state`
- `GET /v2/campaigns/{campaign_id}/world_state`
- `GET /v2/campaigns/{campaign_id}/summary` — Story summary (`StorySummaryResponse`)
- `GET /v2/campaigns/{campaign_id}/locations`
- `GET /v2/campaigns/{campaign_id}/rumors`
- `GET /v2/campaigns/{campaign_id}/transcript`
- `PATCH /v2/campaigns/{campaign_id}/character` — Rename player character (`PatchCharacterRequest`)
- `POST /v2/campaigns/{campaign_id}/memories/crystallize` — Crystallize a memory (`CrystallizeMemoryRequest`)

### Turn execution

**Implementation:** `backend/app/api/v2_turn.py`

- `POST /v2/campaigns/{campaign_id}/turn`
- `POST /v2/campaigns/{campaign_id}/turn_stream` (SSE streaming)
- `POST /v2/campaigns/{campaign_id}/classify` — Classify player intent without executing a turn (`ClassifyRequest` → `ClassifyResponse`)
- `GET /v2/campaigns/{campaign_id}/validation_failures` — List recent validation failures (query: `limit`, default 20)

### Player profiles & legacy hooks

- `POST /v2/player/profiles`
- `GET /v2/player/profiles`
- `GET /v2/player/{player_profile_id}/legacy`

### Campaign progression helpers

**Implementation:** `backend/app/api/v2_player.py`

- `POST /v2/campaigns/{campaign_id}/complete`
- `POST /v2/campaigns/{campaign_id}/rewind?to_turn=N` — Rewind campaign to turn N. Restores world state from `turn_snapshots` and deletes all turn data after turn N. Returns 400 if no snapshot exists for the target turn.
- `POST /v2/campaigns/{campaign_id}/prologue/complete` — Mark prologue complete and build origin_context manifest
- `POST /v2/campaigns/{campaign_id}/era_transition` — Trigger era transition (`EraTransitionRequest`)
- `GET /v2/campaigns/{campaign_id}/codex` — Campaign codex (known NPCs, factions, lore)
- `GET /v2/campaigns/{campaign_id}/settings` — Per-campaign settings (`CampaignSettingsResponse`)
- `PATCH /v2/campaigns/{campaign_id}/settings` — Update campaign settings (narrator_mode, cloud_preset, custom_preset_id, preferred_provider, agent_overrides)

### Saga management (V7.0+, UI surfaced V11.0)

- `POST /v2/sagas` — Create a new saga (player_id, universe_id, title)
- `GET /v2/player/{player_profile_id}/sagas` — List player's sagas with campaign counts
- `GET /v2/sagas/{saga_id}` — Saga detail with campaign timeline

### Library & Lore Source management

**Implementation:** `backend/app/api/v2_library.py`

- `GET /v2/library/books` — List ingested documents
- `POST /v2/library/ingest` — Upload + ingest a file (PDF/EPUB/TXT) in background
- `GET /v2/library/ingest/{job_id}/status` — Poll ingestion job status
- `GET /v2/library/sources` — List lore source collections (V11.0)
- `POST /v2/library/sources` — Create a lore source collection (V11.0)
- `DELETE /v2/library/sources/{source_id}` — Delete source + remove chunks from LanceDB (V11.0)

### V11.0 Response Additions

`PartyStatusItem` now includes:
- `portrait_url` — URL to companion portrait image (when `ENABLE_PORTRAITS=1`)

`TurnResponse` now includes:
- `location_art_url` — URL to location key art image (when `ENABLE_PORTRAITS=1`)

## Starship Endpoints

**Implementation:** `backend/app/api/starships.py`

- `GET /v2/starships/definitions` — List all starship definitions (optional `era` query param for filtering)
- `GET /v2/starships/definitions/{ship_type}` — Get specific starship definition
- `GET /v2/starships/campaign/{campaign_id}` — List player's starships in campaign
- `POST /v2/starships/campaign/{campaign_id}/acquire` — Acquire a starship
- `PATCH /v2/starships/{ship_id}/upgrade` — Apply upgrade to starship
- `PATCH /v2/starships/{ship_id}/rename` — Rename a starship
- `DELETE /v2/starships/{ship_id}` — Remove a starship

## EraForge Endpoints (V12.0)

**Implementation:** `backend/app/api/v2_eraforge.py`

- `POST /v2/eraforge/suggest` — Suggest era pack parameters based on user description (`EraForgeSuggestRequest` → `EraForgeSuggestResponse`)
- `POST /v2/eraforge/generate` — Generate a new era pack from parameters (`EraForgeGenerateRequest` → `EraForgeGenerateResponse`)
- `POST /v2/eraforge/refine-canon` — Refine canon events for a generated era pack (`EraForgeRefineCanonRequest` → `EraForgeRefineCanonResponse`)
- `GET /v2/eraforge/packs` — List user-generated era packs

## Export Endpoints (V12.0)

**Implementation:** `backend/app/api/v2_export.py`

- `GET /v2/export/novel?campaign_id={id}` — Export campaign transcript as a Markdown novel (returns `PlainTextResponse`)

## Settings Endpoints (V12.0)

**Implementation:** `backend/app/api/v2_settings.py`

### Cloud provider management

- `GET /v2/settings/providers` — List available LLM providers with key status
- `PUT /v2/settings/providers/{provider_id}/key` — Store API key for a provider (`SetKeyRequest`)
- `DELETE /v2/settings/providers/{provider_id}/key` — Remove stored API key
- `POST /v2/settings/providers/{provider_id}/test` — Test provider connectivity (`TestResult`)

### LLM presets

- `GET /v2/settings/presets` — List all presets (system + user-created)
- `POST /v2/settings/presets` — Create a new user preset (`CreatePresetRequest`)
- `PUT /v2/settings/presets/{preset_id}` — Update a user preset (`UpdatePresetRequest`)
- `DELETE /v2/settings/presets/{preset_id}` — Delete a user preset (system presets cannot be deleted)

### Resolved configuration

- `GET /v2/settings/campaigns/{campaign_id}/resolved_config` — Get the fully resolved LLM configuration for a campaign (merges system defaults → preset → campaign overrides)

### App preferences

- `GET /v2/settings/preferences` — Get app-level preferences
- `PUT /v2/settings/preferences` — Update app-level preferences (`PreferencesRequest`)

## Key Request Model Notes

`SetupAutoRequest` and campaign creation models (in `backend/app/api/campaign_models.py`) currently support:

- legacy and canonical period identifiers (`time_period`, `setting_id`, `period_id`)
- campaign tuning (`campaign_mode`, `campaign_scale`, `difficulty`)
- optional background/CYOA selections (`background_id`, `background_answers`)
- optional cross-campaign profile linking (`player_profile_id`)

## V7.0 Request/Response Notes

### Idempotency

Turn endpoints (`/turn`, `/turn_stream`) support an `Idempotency-Key` header. If the same key is resubmitted, the server returns the cached response from `turn_idempotency` without re-executing the pipeline. Status transitions: `processing` → `completed`.

### Rewind

`POST /v2/campaigns/{campaign_id}/rewind?to_turn=N` atomically:
1. Restores `world_state_json` from `turn_snapshots` at turn N
2. Deletes `turn_events`, `rendered_turns`, `turn_snapshots`, and related data for turns > N
3. Resets `campaigns.turn_number` to N

Returns 400 if no snapshot exists for the target turn (only turns after V7.0 deployment have snapshots).

### Turn Response Additions

`TurnResponse` (in `campaign_models.py`) includes:
- `mechanic_notes` — Dice result, difficulty, success/failure, and tone from ResolutionAgent (when an action resolves)
- `agent_timings` — Per-agent execution timings (when `DEV_CONTEXT_STATS=1`)
