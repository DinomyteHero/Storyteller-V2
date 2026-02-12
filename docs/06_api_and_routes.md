# 06 — API & Routes

## Server Setup

**File:** `backend/main.py`

- Framework: FastAPI
- CORS: All origins allowed (`allow_origins=["*"]`)
- Default port: 8000
- V2 router mounted at `/v2` (always active)
- Starship router mounted at `/v2/starships` (always active)

## Endpoints

### Health & Root

| Method | Path | Response |
|--------|------|----------|
| `GET` | `/` | `{"message": "Storyteller AI API", "version": "2.0.0"}` |
| `GET` | `/health` | `{"status": "healthy"}` |

### V2 Campaign API

**File:** `backend/app/api/v2_campaigns.py`

#### `POST /v2/setup/auto` — Auto-Generate Campaign

Creates a campaign using LLM-generated skeleton + character sheet.

**Request (`SetupAutoRequest`):**
```json
{
  "time_period": "Old Republic Era",       // optional
  "genre": "space opera",                  // optional
  "themes": ["political intrigue"],         // optional
  "player_concept": "A bounty hunter",      // optional, default: "A hero in a vast world"
  "starting_location": null,               // optional: explicit starting location ID
  "randomize_starting_location": false,    // optional: pick random safe location from era pack
  "background_id": "force_sensitive",      // optional: era-specific background ID
  "background_answers": {"q1": 0, "q2": 1}, // optional: CYOA character creation answers
  "player_gender": "male",                 // optional: "male" or "female" (drives pronoun usage)
  "player_profile_id": null                // optional: cross-campaign player profile UUID
}
```text

**Response:**
```json
{
  "campaign_id": "uuid",
  "player_id": "uuid",
  "skeleton": { /* campaign skeleton from Architect */ },
  "character_sheet": { /* from Biographer */ }
}
```text

**Process (high level):** CampaignArchitect.build() -> BiographerAgent.build() -> INSERT campaign + player -> initial FLAG_SET event.

Notes:
- With `ENABLE_BIBLE_CASTING=1` (default), the persisted `active_factions` are derived deterministically from Era Packs (`data/static/era_packs/`) and the backend does **not** pre-insert a static 12-NPC cast at setup (NPCs are introduced during play).
- With `ENABLE_BIBLE_CASTING=0`, the backend can insert an initial static NPC cast (from the skeleton) at setup.

#### `POST /v2/campaigns` — Manual Campaign Creation

**Request:**
```json
{
  "title": "New Campaign",
  "time_period": null,
  "genre": null,
  "player_name": "Player",
  "starting_location": "Unknown",
  "player_stats": {},
  "hp_current": 10
}
```text

**Response:**
```json
{
  "campaign_id": "uuid",
  "player_id": "uuid"
}
```text

**Process:** INSERT campaign with companion state (+ Era Pack factions when enabled) -> INSERT player character -> initial FLAG_SET event.

#### `GET /v2/campaigns/{campaign_id}/state` — Get Campaign State

**Query params:** `player_id` (required)

**Response:** Full `GameState` Pydantic model (serialized to JSON).

#### `GET /v2/campaigns/{campaign_id}/world_state` — Get World State

**Response:**
```json
{
  "campaign_id": "uuid",
  "world_state": { /* world_state_json contents */ }
}
```text

#### `GET /v2/campaigns/{campaign_id}/rumors` — Get Public Rumors

**Query params:** `limit` (1-20, default 5)

**Response:**
```json
{
  "campaign_id": "uuid",
  "rumors": [ /* list of recent public rumor texts */ ]
}
```text

#### `GET /v2/campaigns/{campaign_id}/transcript` — Get Turn Transcript

**Query params:** `limit` (1-200, default 50)

**Response:**
```json
{
  "campaign_id": "uuid",
  "turns": [
    {
      "turn_number": 1,
      "text": "Rendered narration...",
      "citations": [],
      "suggested_actions": []
    }
  ]
}
```text

#### `GET /v2/era/{era_id}/locations` — Get Era Locations

Returns known locations for an era pack (for UI starting-area selection).

**Response:**
```json
{
  "era_id": "rebellion",
  "locations": [ /* list of location dicts */ ]
}
```text

#### `GET /v2/era/{era_id}/backgrounds` — Get Era Backgrounds

Returns available backgrounds and their question chains for the given era (CYOA character creation).

**Response:**
```json
{
  "era_id": "rebellion",
  "backgrounds": [ /* list of background dicts with question chains */ ]
}
```text

#### `POST /v2/campaigns/{campaign_id}/turn` — Run One Turn

**This is the core gameplay endpoint.**

**Query params:** `player_id` (required)

**Request:**
```json
{
  "user_input": "I search the back alley for clues",
  "debug": false,        // optional: include debug info
  "include_state": false  // optional: include full GameState
}
```text

**Response (`TurnResponse`):**
```json
{
  "narrated_text": "The alley is dark and narrow...",
  "suggested_actions": [
    {
      "label": "Investigate further",
      "intent_text": "I examine the markings on the wall",
      "category": "EXPLORE",
      "risk_level": "SAFE",
      "strategy_tag": "OPTIMAL",
      "tone_tag": "INVESTIGATE",
      "intent_style": "probing",
      "consequence_hint": "learn more",
      "companion_reactions": {},
      "risk_factors": []
    }
    // ... 4 total (padded/trimmed to exactly 4)
  ],
  "player_sheet": {
    "character_id": "uuid",
    "name": "Player Name",
    "stats": {"STR": 14, "DEX": 12},
    "hp_current": 10,
    "location_id": "loc-cantina",
    "planet_id": "Nar Shaddaa",
    "credits": 500,
    "inventory": [],
    "psych_profile": {"stress_level": 3},
    "background": "Former smuggler",
    "cyoa_answers": {"motivation": 1, "origin": 0},
    "gender": "male"
  },
  "inventory": [ /* item list */ ],
  "quest_log": { /* world_state_json flags */ },
  "world_time_minutes": 488,
  "warnings": [],

  // Optional fields (present when applicable):
  "party_status": [
    {"id": "comp-1", "name": "Kira", "affinity": 15, "loyalty_progress": 3, "mood_tag": "Neutral"}
  ],
  "alignment": {"light_dark": 2, "paragon_renegade": -1},
  "faction_reputation": {"Republic": 10, "Syndicate": -5},
  "news_feed": [
    {
      "id": "news-abc123",
      "timestamp_world_minutes": 480,
      "source_tag": "CIVNET",
      "headline": "Trade disruption reported at Docks",
      "body": "Local merchants report unusual activity...",
      "related_factions": ["Syndicate"],
      "urgency": "MED",
      "is_public_rumor": true
    }
  ],

  // Optional debug (when debug=true):
  "debug": {
    "router_intent": "ACTION",
    "router_route": "MECHANIC",
    "router_action_class": "PHYSICAL_ACTION",
    "router_output": { /* RouterOutput dict */ },
    "mechanic_output": { /* MechanicOutput dict */ },
    "director_instructions": "Build tension...",
    "present_npcs": [ /* NPC list */ ],
    "world_sim_events": [],
    "new_rumors": [],
    "active_factions": []
  },

  // Optional full state (when include_state=true):
  "state": { /* Full GameState dict */ },

  // Dev-only (when DEV_CONTEXT_STATS=1):
  "context_stats": { /* token budgeting report */ }
}
```text

`warnings` is always present (may be empty). `context_stats` is optional and only populated when `DEV_CONTEXT_STATS=1`.

**Process:**
1. `build_initial_gamestate(conn, campaign_id, player_id)` — load state from DB
2. Set `state.user_input` from request
3. `run_turn(conn, state)` — execute full LangGraph pipeline
4. Post-process: pad suggestions to 4, extract party status, alignment, news feed
5. Return `TurnResponse`

**Suggestion handling (V2.15):** Suggestions come from the Director node's `generate_suggestions()` call (deterministic, no LLM). `embedded_suggestions` from the Narrator is always `None`. The `_pad_suggestions_for_ui()` function runs `lint_actions()` to validate and pad to exactly `SUGGESTED_ACTIONS_TARGET` (4).

#### `POST /v2/campaigns/{campaign_id}/turn_stream` — SSE Streaming Turn

Streams narration via Server-Sent Events. Runs the full pipeline synchronously up to (but not including) Narrator, then streams Narrator tokens as SSE events. After streaming completes, runs post-processing + commit and returns final metadata as the last SSE event.

**Query params:** `player_id` (required)

**Request:** Same as `/turn` (`TurnRequest`)

**SSE event format:**
```text
data: {"type": "token", "text": "..."}         — individual token
data: {"type": "done", "narrated_text": "...", "suggested_actions": [...], ...}  — final metadata
data: {"type": "error", "message": "..."}      — on failure
```text

**Notes:**
- META input shortcuts directly to commit (no streaming needed)
- Narrator post-processing (`_strip_structural_artifacts`, `_truncate_overlong_prose`, `_enforce_pov_consistency`) runs after streaming completes
- Suggestions are padded to 4 via `_pad_suggestions_for_ui()` in the `done` event

### V2 Starship API

**File:** `backend/app/api/starships.py`

Mounted at `/v2/starships`. Manages player-owned starship acquisition, customization, and upgrades.

#### `GET /v2/starships/definitions` — List Starship Definitions

**Query params:** `era` (optional, filter by era)

**Response:** List of `StarshipDefinition` objects from `data/static/starships.yaml`.

#### `GET /v2/starships/definitions/{ship_type}` — Get Starship Definition

**Response:** Single `StarshipDefinition` object.

#### `GET /v2/starships/campaign/{campaign_id}` — List Player Starships

**Response:** List of `PlayerStarshipResponse` objects with definition and available upgrades.

```json
[
  {
    "starship": {
      "id": 1,
      "campaign_id": 42,
      "ship_type": "yt_1300",
      "custom_name": "Millennium Falcon",
      "upgrades": {"weapons": "quad_laser", "shields": null},
      "acquired_at": "2026-01-15T10:30:00Z",
      "acquired_method": "quest_reward"
    },
    "definition": { /* StarshipDefinition */ },
    "available_upgrades": {
      "weapons": ["ion_cannon"],
      "shields": ["deflector_mk2", "deflector_mk3"],
      "hyperdrive": ["class_1", "class_0.5"],
      "crew_quarters": ["expanded"],
      "utility": ["smuggling_hold", "medical_bay"]
    }
  }
]
```text

#### `POST /v2/starships/campaign/{campaign_id}/acquire` — Acquire Starship

**Request (`PlayerStarshipCreate`):**
```json
{
  "ship_type": "yt_1300",
  "custom_name": "My Ship",
  "acquired_method": "quest_reward"
}
```text

**Response:** `PlayerStarshipResponse` (ship + definition + available upgrades).

#### `PATCH /v2/starships/{ship_id}/upgrade` — Install Upgrade

**Request (`PlayerStarshipUpgradeRequest`):**
```json
{
  "slot": "weapons",
  "upgrade": "quad_laser"
}
```text

**Response:** `PlayerStarshipResponse` (updated ship + remaining upgrades).

**Validation:** Slot must be one of `weapons`, `shields`, `hyperdrive`, `crew_quarters`, `utility`. Upgrade must be available for the ship type.

#### `PATCH /v2/starships/{ship_id}/rename` — Rename Starship

**Query params:** `custom_name` (new name)

**Response:** `{"message": "Starship {id} renamed to '{name}'"}`

#### `DELETE /v2/starships/{ship_id}` — Delete Starship

**Response:** `{"message": "Starship {id} deleted successfully"}`

## Key Data Models

### `ActionSuggestion`

**File:** `backend/app/models/state.py`

```python
class ActionSuggestion(BaseModel):
    label: str                    # Short UI label, e.g. "Intimidate the guard"
    intent_text: str              # What gets sent as user_input if clicked
    category: str = "EXPLORE"     # SOCIAL | EXPLORE | COMMIT
    risk_level: str = "SAFE"      # SAFE | RISKY | DANGEROUS (3-tier)
    strategy_tag: str = "OPTIMAL" # OPTIMAL | ALTERNATIVE
    tone_tag: str = "NEUTRAL"     # PARAGON | RENEGADE | INVESTIGATE | NEUTRAL
    intent_style: str = ""        # "calm", "firm", "probing", "empathetic", "tactical", etc.
    consequence_hint: str = ""    # "may gain trust", "may escalate", "learn more"
    companion_reactions: dict[str, int] = {}  # {companion_id: affinity_delta}
    risk_factors: list[str] = []              # ["Outnumbered 3-to-1", "No cover"]
```text

### `CharacterSheet`

**File:** `backend/app/models/state.py`

```python
class CharacterSheet(BaseModel):
    character_id: str
    name: str
    stats: dict[str, int] = {}
    hp_current: int = 0
    location_id: str | None = None
    planet_id: str | None = None      # e.g., "Tatooine", "Coruscant"
    credits: int | None = None
    inventory: list[dict] = []
    psych_profile: dict = {}          # current_mood, stress_level, active_trauma
    background: str | None = None     # POV identity from BiographerAgent
    cyoa_answers: dict | None = None  # CYOA character creation answers
    gender: str | None = None         # "male" or "female" — drives pronoun usage
```text

### `TurnResponse`

**File:** `backend/app/api/v2_campaigns.py`

```python
class TurnResponse(BaseModel):
    narrated_text: str
    suggested_actions: list[ActionSuggestion]  # always 4 items
    player_sheet: dict
    inventory: list
    quest_log: dict
    world_time_minutes: int | None = None
    state: dict | None = None                  # when include_state=true
    debug: dict | None = None                  # when debug=true
    party_status: list[PartyStatusItem] | None = None
    alignment: dict | None = None
    faction_reputation: dict | None = None
    news_feed: list[dict] | None = None
    context_stats: dict | None = None          # when DEV_CONTEXT_STATS=1
    warnings: list[str] = []
```text

Note: `embedded_suggestions` is always `None` as of V2.15 (Narrator writes prose only; suggestions are deterministic).

## Auth & Security

> **WARNING:** No authentication is implemented and CORS is wide open (`allow_origins=["*"]`). This is acceptable for **local-only development**. Any public or networked deployment MUST add authentication and restrict CORS origins. Campaign/player UUIDs serve as implicit access tokens but provide no real security.

**No rate limiting** is implemented. No request validation beyond Pydantic model parsing.

**Error responses** follow this structure:
```json
{
  "error_code": "string",
  "message": "string",
  "node": "string (optional, which pipeline node failed)",
  "details": {}
}
```text

HTTP status codes: `200` for success, `400` for bad request (missing params), `404` for campaign/player not found, `500` for internal errors (LLM failures, DB errors).

## Example Requests

```bash
# Health check

curl http://localhost:8000/health

# Auto-create campaign (with gender and background)

curl -X POST http://localhost:8000/v2/setup/auto \
  -H "Content-Type: application/json" \
  -d '{"player_concept": "A smuggler pilot", "themes": ["space opera"], "player_gender": "male", "background_id": "smuggler"}'

# Run a turn

curl -X POST "http://localhost:8000/v2/campaigns/CAMPAIGN_ID/turn?player_id=PLAYER_ID" \
  -H "Content-Type: application/json" \
  -d '{"user_input": "I check the ship sensors for nearby traffic"}'

# Run a turn with SSE streaming

curl -X POST "http://localhost:8000/v2/campaigns/CAMPAIGN_ID/turn_stream?player_id=PLAYER_ID" \
  -H "Content-Type: application/json" \
  -d '{"user_input": "I draw my blaster"}'

# Get current state

curl "http://localhost:8000/v2/campaigns/CAMPAIGN_ID/state?player_id=PLAYER_ID"

# Get news feed / world state

curl "http://localhost:8000/v2/campaigns/CAMPAIGN_ID/world_state"

# Get recent rumors

curl "http://localhost:8000/v2/campaigns/CAMPAIGN_ID/rumors?limit=5"

# Get transcript (last 50 turns)

curl "http://localhost:8000/v2/campaigns/CAMPAIGN_ID/transcript?limit=50"

# Run turn with debug info

curl -X POST "http://localhost:8000/v2/campaigns/CAMPAIGN_ID/turn?player_id=PLAYER_ID" \
  -H "Content-Type: application/json" \
  -d '{"user_input": "I draw my blaster", "debug": true}'

# List starship definitions

curl "http://localhost:8000/v2/starships/definitions"

# List starship definitions for an era

curl "http://localhost:8000/v2/starships/definitions?era=rebellion"

# List player starships for a campaign

curl "http://localhost:8000/v2/starships/campaign/CAMPAIGN_ID"

# Acquire a starship

curl -X POST "http://localhost:8000/v2/starships/campaign/CAMPAIGN_ID/acquire" \
  -H "Content-Type: application/json" \
  -d '{"ship_type": "yt_1300", "custom_name": "My Ship", "acquired_method": "quest_reward"}'

# Upgrade a starship

curl -X PATCH "http://localhost:8000/v2/starships/SHIP_ID/upgrade" \
  -H "Content-Type: application/json" \
  -d '{"slot": "weapons", "upgrade": "quad_laser"}'

# Rename a starship

curl -X PATCH "http://localhost:8000/v2/starships/SHIP_ID/rename?custom_name=New%20Name"

# Delete a starship

curl -X DELETE "http://localhost:8000/v2/starships/SHIP_ID"

# Get era locations (for UI starting-area selection)

curl "http://localhost:8000/v2/era/rebellion/locations"

# Get era backgrounds (for CYOA character creation)

curl "http://localhost:8000/v2/era/rebellion/backgrounds"
```text
