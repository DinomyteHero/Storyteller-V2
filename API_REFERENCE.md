# Storyteller AI — API Reference

This file documents the current API surface exposed by the FastAPI app.

Primary sources:
- `backend/main.py`
- `backend/app/api/v2_campaigns.py`
- `backend/app/api/starships.py`

## Base URLs

- Root API metadata: `GET /`
- Health: `GET /health`
- Campaign APIs: `/v2/...`
- Starship APIs: `/v2/starships/...`

## Authentication behavior

- If `STORYTELLER_API_TOKEN` is **unset** (default dev behavior), API routes are open.
- If `STORYTELLER_API_TOKEN` is set, use either:
  - `Authorization: Bearer <token>`
  - `X-API-Key: <token>`
- In dev mode, docs endpoints remain open.

## Error payload shape

Errors are returned in a structured object:

```json
{
  "error_code": "string",
  "message": "string",
  "node": "string",
  "details": {}
}
```

---

## Core Endpoints (`/v2`)

### Content discovery (canonical)

- `GET /v2/content/catalog`
- `GET /v2/content/default`
- `GET /v2/content/{setting_id}/{period_id}/summary`

### Legacy era discovery (compatibility)

- `GET /v2/era/{era_id}/locations`
- `GET /v2/era/{era_id}/backgrounds`
- `GET /v2/era/{era_id}/companions`
- `GET /v2/debug/era-packs` (debug helper)

### Campaign setup + lifecycle

- `POST /v2/setup/auto`
- `POST /v2/campaigns`
- `GET /v2/campaigns/{campaign_id}/state?player_id=...`
- `GET /v2/campaigns/{campaign_id}/world_state`
- `GET /v2/campaigns/{campaign_id}/locations`
- `GET /v2/campaigns/{campaign_id}/rumors?limit=...`
- `GET /v2/campaigns/{campaign_id}/transcript?limit=...`
- `POST /v2/campaigns/{campaign_id}/turn?player_id=...`
- `POST /v2/campaigns/{campaign_id}/turn_stream?player_id=...`
- `GET /v2/campaigns/{campaign_id}/validation_failures`
- `POST /v2/campaigns/{campaign_id}/complete`

### Player profile + legacy

- `POST /v2/player/profiles`
- `GET /v2/player/profiles`
- `GET /v2/player/{player_profile_id}/legacy`

### Passage mode

- `POST /v2/campaigns/{campaign_id}/start_passage`
- `POST /v2/campaigns/{campaign_id}/choose`

---

## Starship Endpoints (`/v2/starships`)

- `GET /v2/starships/definitions`
- `GET /v2/starships/definitions/{ship_type}`
- `GET /v2/starships/campaign/{campaign_id}`
- `POST /v2/starships/campaign/{campaign_id}/acquire`
- `DELETE /v2/starships/{ship_id}`

---

## Key Request/Response Notes

## `POST /v2/campaigns`

Creates a campaign + player without auto world generation.

Example request:

```json
{
  "title": "New Campaign",
  "time_period": "rebellion",
  "genre": "space opera",
  "player_name": "Rex",
  "starting_location": "loc-cantina",
  "difficulty": "normal"
}
```

Example response:

```json
{
  "campaign_id": "uuid",
  "player_id": "uuid"
}
```

## `POST /v2/setup/auto`

Auto-builds a campaign skeleton + initial character sheet through setup agents.

Request supports both canonical and legacy selectors:
- canonical: `setting_id` + `period_id`
- legacy: `time_period`

Invalid content selections return HTTP 400 with a structured error payload.

## `POST /v2/campaigns/{campaign_id}/turn`

Runs one turn.

Request body:

```json
{
  "user_input": "Look around",
  "debug": false,
  "include_state": false
}
```

Turn response always includes:
- `narrated_text`
- `suggested_actions`
- `player_sheet`
- `inventory`
- `quest_log`
- `warnings`

May also include:
- `world_time_minutes`
- `party_status`
- `alignment`
- `faction_reputation`
- `news_feed`
- `dialogue_turn`
- `turn_contract`
- `debug` (when requested)
- `state` (when requested)
- `context_stats` (when enabled)

---

## Streaming turns

`POST /v2/campaigns/{campaign_id}/turn_stream` returns a streaming response for progressive turn delivery.

---

## Compatibility note

For exact payload schemas, refer to Pydantic models in:
- `backend/app/api/v2_campaigns.py`
- `backend/app/models/state.py`
- `backend/app/models/turn_contract.py`
- `backend/app/models/starship.py`

OpenAPI remains the most precise runtime contract:
- `http://localhost:8000/docs`
