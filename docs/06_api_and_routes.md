# 06 — API & Routes

## Server Setup

**Primary wiring file:** `backend/main.py`

- Framework: FastAPI
- App metadata: `title="Storyteller AI API"`, `version="2.0.0"`
- V2 campaign router mounted at `/v2`
- Starship router mounted at `/starships`
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

- `GET /v2/content/catalog`
- `GET /v2/content/default`
- `GET /v2/content/{setting_id}/{period_id}/summary`
- `GET /v2/era/{era_id}/locations`
- `GET /v2/era/{era_id}/backgrounds`
- `GET /v2/era/{era_id}/companions`
- `GET /v2/debug/era-packs`

### Campaign creation and lookup

- `POST /v2/setup/auto`
- `POST /v2/campaigns`
- `GET /v2/campaigns`
- `GET /v2/campaigns/{campaign_id}/state`
- `GET /v2/campaigns/{campaign_id}/world_state`
- `GET /v2/campaigns/{campaign_id}/locations`
- `GET /v2/campaigns/{campaign_id}/rumors`
- `GET /v2/campaigns/{campaign_id}/transcript`
- `GET /v2/campaigns/{campaign_id}/validation_failures`

### Turn execution

- `POST /v2/campaigns/{campaign_id}/turn`
- `POST /v2/campaigns/{campaign_id}/turn_stream` (SSE streaming)

### Player profiles & legacy hooks

- `POST /v2/player/profiles`
- `GET /v2/player/profiles`
- `GET /v2/player/{player_profile_id}/legacy`

### Campaign progression helpers

- `POST /v2/campaigns/{campaign_id}/complete`
- `POST /v2/campaigns/{campaign_id}/rewind?to_turn=N` — Rewind campaign to turn N. Restores world state from `turn_snapshots` and deletes all turn data after turn N. Returns 400 if no snapshot exists for the target turn.
- `POST /v2/campaigns/{campaign_id}/prologue/complete` — Mark prologue complete and build origin_context manifest

## Starship Endpoints

**Implementation:** `backend/app/api/starships.py`

- `GET /starships/definitions`
- `GET /starships/definitions/{ship_type}`
- `GET /starships/campaign/{campaign_id}`
- `POST /starships/campaign/{campaign_id}/acquire`
- `PATCH /starships/{ship_id}/upgrade`
- `PATCH /starships/{ship_id}/rename`
- `DELETE /starships/{ship_id}`

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
