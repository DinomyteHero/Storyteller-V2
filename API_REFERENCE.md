# Storyteller AI — API Reference (V2.20)

This document is the **API contract** for the FastAPI backend. Source of truth:
- `backend/main.py` (app wiring + error handlers)
- `backend/app/api/v2_campaigns.py` (routes + request/response models)
- `backend/app/models/state.py` (shared state + `ActionSuggestion` shape)

**Base path:** `/v2` for gameplay endpoints (e.g. `POST /v2/setup/auto`, `POST /v2/campaigns/{id}/turn`).

Health endpoints outside `/v2`:
- `GET /` → `{"message":"Storyteller AI API","version":"2.0.0"}`
- `GET /health` → `{"status":"healthy"}`

---

## Error Responses (All Endpoints)

Non-2xx responses use a structured error payload:

```json
{
  "error_code": "string",
  "message": "string",
  "node": "string (optional)",
  "details": {}
}
```

---

## Common Schemas

### `ActionSuggestion` (used in `suggested_actions`)

- `label` (string): short UI label (verb-first, 4-8 words)
- `intent_text` (string): text the UI sends as `user_input` if clicked
- `category` (string): `SOCIAL` | `EXPLORE` | `COMMIT`
- `risk_level` (string): `SAFE` | `RISKY` | `DANGEROUS`
- `strategy_tag` (string): `OPTIMAL` | `ALTERNATIVE`
- `tone_tag` (string): `PARAGON` | `INVESTIGATE` | `RENEGADE` | `NEUTRAL`
- `intent_style` (string): short UI flavor tag (e.g. `"calm"`, `"firm"`)
- `consequence_hint` (string): short UI hint (e.g. `"learn more"`)
- `risk_factors` (string[]): list of factors contributing to the risk assessment
- `meaning_tag` (string): semantic meaning classification (e.g. `"reveal_values"`, `"probe_belief"`, `"pragmatic"`). Defaults to empty string.

Contract:
- The API always returns **exactly 4** suggestions (`SUGGESTED_ACTIONS_TARGET = 4`), padded/linted if needed.
- The SuggestionRefiner node is the sole source of suggestions. When `ENABLE_SUGGESTION_REFINER=1` (default), it uses `qwen3:8b` to generate scene-aware suggestions from the Narrator's prose context. On failure, minimal emergency fallback responses are used.
- `generate_suggestions()` in `director_validation.py` still exists but is **not called** from the pipeline.
- Categories are intended to be distinct (SOCIAL/EXPLORE/COMMIT).
- `ensure_tone_diversity()` re-tags NEUTRAL suggestions to fill PARAGON/INVESTIGATE/RENEGADE gaps.

### `PlayerResponse` (used in `dialogue_turn.player_responses`)

- `id` (string): response identifier (e.g. `"resp_1"`)
- `display_text` (string): UI label for the dialogue wheel option
- `action` (object): `{type, intent, target, tone}` — the player action descriptor
- `tone_tag` (string): `PARAGON` | `INVESTIGATE` | `RENEGADE` | `NEUTRAL`
- `risk_level` (string): `SAFE` | `RISKY` | `DANGEROUS`
- `consequence_hint` (string): hidden hint (debug only). Defaults to empty string.
- `meaning_tag` (string): semantic meaning classification (e.g. `"reveal_values"`, `"probe_belief"`). Defaults to empty string.

### `SceneFrame` (used in `dialogue_turn.scene_frame`)

- `location_id` (string): current location identifier
- `location_name` (string): display name
- `present_npcs` (array): NPCs with `id`, `name`, `role`, `voice_profile` (dict with keys: `belief`, `wound`, `taboo`, `rhetorical_style`, `tell`)
- `immediate_situation` (string): what is happening right now
- `player_objective` (string): what the player is trying to do
- `allowed_scene_type` (string): `dialogue` | `combat` | `exploration` | `travel` | `stealth`
- `scene_hash` (string): SHA256 hash for deduplication
- `topic_primary` (string): KOTOR-soul topic anchor
- `topic_secondary` (string | null): secondary topic
- `subtext` (string): emotional undercurrent
- `npc_agenda` (string): what the primary NPC wants
- `scene_style_tags` (string[]): stylistic tags (e.g. `"Socratic"`, `"noir"`)
- `pressure` (object): `{alert, heat}` — scene pressure levels

### `NPCUtterance` (used in `dialogue_turn.npc_utterance`)

- `speaker_id` (string): NPC identifier (or `"narrator"` for narrator observations)
- `speaker_name` (string): display name
- `text` (string): 1-3 lines of focused NPC dialogue as a single string
- `subtext_hint` (string): what the NPC is really thinking (debug only). Defaults to empty string.
- `rhetorical_moves` (string[]): debate tactics used (e.g. `["challenge", "probe"]`). Debug only.

### `DialogueTurn` (V2.17 canonical turn output)

- `scene_frame` (SceneFrame): immutable scene context
- `npc_utterance` (NPCUtterance | null): focused NPC dialogue
- `player_responses` (PlayerResponse[]): KOTOR-style dialogue wheel options
- `validation` (object | null): validation report (non-blocking)

### `player_sheet` (serialized `CharacterSheet`)

- `character_id` (string)
- `name` (string)
- `gender` (string | null): `"male"` or `"female"`
- `background` (string | null): background archetype id
- `planet_id` (string | null): starting planet
- `cyoa_answers` (object | null): answers from character-creation CYOA flow
- `stats` (object): string → int
- `hp_current` (int)
- `location_id` (string | null)
- `credits` (int | null)
- `inventory` (array): lightweight list of items (see `inventory` below)
- `psych_profile` (object): `{current_mood, stress_level, active_trauma, ...}` (keys may vary)

### `GameState` (additional fields of note)

- `player_starship` (object | null): acquired starship details (no starting ships; earned in-story)
- `known_npcs` (string[]): NPC ids the player has encountered so far
- `embedded_suggestions` (null): always `null` (Narrator writes prose only; suggestions are deterministic or LLM-refined)
- `companion_reactions` (object): per-companion reaction summaries from the latest turn
- `dialogue_turn` (DialogueTurn | null): canonical V2.17 turn output (scene_frame + npc_utterance + player_responses)
- `scene_frame` (SceneFrame | null): transient, cleared each turn
- `player_responses` (PlayerResponse[] | null): transient, cleared each turn

### `inventory`

Always present as a list. Each entry is an object like:

```json
{"item_name": "Medkit", "quantity": 2}
```

Additional keys may appear (from `attributes_json`).

### `news_feed` entries (ME-style comms/briefing)

If present, each entry is a dict with:
- `id` (string)
- `timestamp_world_minutes` (int)
- `source_tag` (string): e.g. `CIVNET`, `INTERCEPT`, `UNDERWORLD`, `REPUBLIC`, `SITH`
- `headline` (string)
- `body` (string)
- `related_factions` (string[])
- `urgency` (string): `LOW` | `MED` | `HIGH`
- `is_public_rumor` (bool)

---

## Endpoints

### 1) `POST /v2/setup/auto`

Auto-generates a campaign via the Architect + Biographer.

**Request**

```json
{
  "time_period": "LOTF",
  "genre": "space opera",
  "themes": ["smuggling", "factions"],
  "player_concept": "A wary pilot with a past",
  "player_gender": "male",
  "background_id": "smuggler",
  "background_answers": {"q1": "a1", "q2": "a2"},
  "player_profile_id": "uuid (optional)"
}
```

All fields are optional except where needed for CYOA flow.

- `player_gender` (string | null): `"male"` or `"female"`. Injected into Director + Narrator prompts for pronoun consistency.
- `background_id` (string | null): selects a background archetype from the era pack.
- `background_answers` (object | null): answers to background-specific CYOA questions.
- `player_profile_id` (string | null): references a saved player profile.
- `randomize_starting_location` (bool, default `false`): when true, picks a random safe starting location from the era pack.

**Response**

```json
{
  "campaign_id": "uuid",
  "player_id": "uuid",
  "skeleton": { "title": "...", "time_period": "...", "locations": [], "npc_cast": [], "active_factions": [] },
  "character_sheet": { "name": "...", "stats": {}, "hp_current": 10, "starting_location": "loc-tavern", "gender": "male", "background": "smuggler", "planet_id": "nar-shaddaa" }
}
```

Notes:
- When `ENABLE_BIBLE_CASTING=1` (default), the persisted campaign `active_factions` are derived from the Era Pack in `data/static/era_packs/` (LLM-generated factions are ignored for persistence).
- When `ENABLE_BIBLE_CASTING=1`, the backend does **not** pre-insert a static NPC cast at setup; NPCs are introduced during play (encounter system).

---

### 2) `POST /v2/campaigns`

Manual campaign creation (no Architect/Biographer).

**Request**

```json
{
  "title": "New Campaign",
  "time_period": "REBELLION",
  "genre": "space opera",
  "player_name": "Rex",
  "starting_location": "loc-tavern",
  "player_stats": {},
  "hp_current": 10
}
```

**Response**

```json
{ "campaign_id": "uuid", "player_id": "uuid" }
```

---

### 3) `GET /v2/campaigns/{campaign_id}/state`

Get the current `GameState`.

**Query params**
- `player_id` (required)

**Response**
- Full `GameState` JSON (see `backend/app/models/state.py`).

---

### 4) `GET /v2/campaigns/{campaign_id}/world_state`

Returns the campaign's `world_state_json` blob.

**Response**

```json
{ "campaign_id": "uuid", "world_state": { "active_factions": [], "...": "..." } }
```

---

### 5) `GET /v2/campaigns/{campaign_id}/rumors`

Returns the most recent public rumor texts.

**Query params**
- `limit` (optional, 1-20; default 5)

**Response**

```json
{ "campaign_id": "uuid", "rumors": ["..."] }
```

---

### 6) `GET /v2/campaigns/{campaign_id}/transcript`

Returns rendered turns (newest first).

**Query params**
- `limit` (optional, 1-200; default 50)

**Response**

```json
{ "campaign_id": "uuid", "turns": [ { "turn_number": 1, "text": "...", "citations": [], "suggested_actions": [] } ] }
```

---

### 7) `POST /v2/campaigns/{campaign_id}/turn`

Run one gameplay turn.

**Query params**
- `player_id` (required)

**Request**

```json
{
  "user_input": "I search the back alley for clues",
  "debug": false,
  "include_state": false
}
```

**Response (`TurnResponse`)**

Required fields (always present):
- `narrated_text` (string): 5-8 sentences of novel-like prose
- `suggested_actions` (`ActionSuggestion[]`, exactly 4): KOTOR-style dialogue wheel options (deterministic or LLM-refined)
- `player_sheet` (object)
- `inventory` (array)
- `quest_log` (object): active quest states from the QuestTracker. Keys are quest IDs, values are `{quest_id, status, current_stage_idx, stages_completed[], activated_turn}`
- `warnings` (string[]): warnings/fallback notes (may be empty)

Optional fields:
- `world_time_minutes` (int | null)
- `party_status` (array of `PartyStatusItem` | null): companion roster with affinity, loyalty, influence, trust/respect/fear
- `alignment` (object | null): `{light_dark, paragon_renegade}`
- `faction_reputation` (object | null): string → int
- `news_feed` (array | null)
- `dialogue_turn` (DialogueTurn | null): V2.17 canonical turn output (SceneFrame + NPCUtterance + PlayerResponses)
- `companion_reactions` (object | null): per-companion reaction text from the turn
- `debug` (object | null): only when `debug=true`
- `state` (object | null): only when `include_state=true`
- `context_stats` (object | null): only when `DEV_CONTEXT_STATS=1` and stats are available

### `PartyStatusItem` (used in `party_status`)

- `id` (string): companion identifier
- `name` (string): display name
- `affinity` (int): 0-100 affinity score
- `loyalty_progress` (int): 0=STRANGER, 1=TRUSTED, 2=LOYAL
- `mood_tag` (string | null): current mood (INTRIGUED, PLEASED, NEUTRAL, WARY, DISAPPROVES, HOSTILE)
- `influence` (int | null): V2.20 influence score (-100 to +100). Only populated after companion interactions via PartyState.
- `trust` (int | null): V2.20 trust axis (-100 to +100)
- `respect` (int | null): V2.20 respect axis (-100 to +100)
- `fear` (int | null): V2.20 fear axis (-100 to +100)

Note: The `GameState` includes `arc_guidance` (arc stage, tension level, priority threads), `validation_notes` (narrative validator warnings), and `companion_reactions_summary` but these are typically only exposed via `debug` or `include_state` options.

`debug` currently includes:
- `router_intent`, `router_route`, `router_action_class`
- `router_output` (object | null)
- `mechanic_output` (object | null)
- `director_instructions` (string | null)
- `present_npcs` (array | null)
- `scene_frame` (SceneFrame | null): V2.17 scene context
- `world_sim_events` (array)
- `new_rumors` (array)
- `active_factions` (array | null)
- `arc_guidance` (object | null): arc stage, tension, priority threads
- `validation_notes` (string[] | null): narrative validator warnings
- `companion_reactions_summary` (string | null): summary of companion reactions for the turn

---

### 8) `GET /v2/campaigns/{campaign_id}/turn_stream`

SSE streaming endpoint for gameplay turns. Returns the same data as the synchronous turn endpoint, but streamed as Server-Sent Events.

**Query params**
- `player_id` (required)
- `user_input` (required): the player action text
- `debug` (optional, bool)
- `include_state` (optional, bool)

**Response**: Server-Sent Events stream. Each event has a `data` field containing a JSON chunk. The final event contains the complete `TurnResponse`.

---

### 9) Starship Endpoints (`/v2/starships/`)

Starships are earned in-story (quest, purchase, salvage, faction reward, theft). No player starts with a ship.

#### `GET /v2/starships/definitions`
Returns all available starship definitions. Optional `?era=` query parameter to filter by era.

**Response:** `StarshipDefinition[]` (direct array)

#### `GET /v2/starships/definitions/{ship_type}`
Returns a single starship definition by type ID (e.g. `ship-reb-yt1300`).

#### `GET /v2/starships/campaign/{campaign_id}`
List all starships owned by a campaign. Returns full ship data with definitions and available upgrades.

**Response:** `PlayerStarshipResponse[]`

#### `POST /v2/starships/campaign/{campaign_id}/acquire`
Acquire a starship for a campaign. `campaign_id` is a path parameter.

**Request**
```json
{
  "ship_type": "ship-reb-yt1300",
  "custom_name": "Stellar Dawn",
  "acquired_method": "quest | purchase | salvage | faction | theft"
}
```

#### `PATCH /v2/starships/{ship_id}/upgrade`
Install an upgrade on a player's starship. Uses PATCH, not POST.

**Request**
```json
{
  "slot": "weapons | shields | hyperdrive | crew_quarters | utility",
  "upgrade": "string"
}
```

#### `PATCH /v2/starships/{ship_id}/rename`
Rename a player's starship. Uses PATCH, not POST. `custom_name` as query parameter.

#### `DELETE /v2/starships/{ship_id}`
Remove a starship from a player's possession.

---

### 10) Era Pack Endpoints

#### `GET /v2/era/{era_id}/backgrounds`

Retrieve all character creation backgrounds for a specific era.

**Path Parameters:**
- `era_id` (string): Era identifier (REBELLION, NEW_REPUBLIC, NEW_JEDI_ORDER, LEGACY, DARK_TIMES, KOTOR)

**Response:**

```json
[
  {
    "id": "bg_rebel_soldier",
    "name": "Rebel Soldier",
    "description": "You served in the Alliance military...",
    "icon": "soldier",
    "starting_stats": {"combat": 2, "tactics": 1},
    "starting_starship": null,
    "starting_reputation": {"rebellion": 20, "empire": -30},
    "questions": [
      {
        "id": "q1_motivation",
        "title": "Why did you join the Rebellion?",
        "subtitle": "This shapes your core motivation",
        "condition": null,
        "choices": [
          {
            "label": "To fight tyranny",
            "concept": "idealistic rebel",
            "tone": "PARAGON",
            "effects": {
              "faction_hint": "rebellion",
              "location_hint": "loc-yavin_base",
              "thread_seed": "lost_family",
              "stat_bonus": {"leadership": 1}
            }
          }
        ]
      }
    ]
  }
]
```

**Background Question Conditional Logic:**
- `condition`: Python expression evaluated against previous choices (e.g., `"q1 == 0"` shows if choice 0 was selected for question q1)
- `loyalty.tone == PARAGON`: Shows if player chose PARAGON tone in previous question

---

#### `GET /v2/era/{era_id}/locations`

Retrieve all locations for a specific era (used for campaign creation starting location selection).

**Path Parameters:**
- `era_id` (string): Era identifier

**Response:**

```json
[
  {
    "id": "loc-cantina",
    "name": "Mos Eisley Cantina",
    "planet": "Tatooine",
    "region": "Outer Rim",
    "description": "A crowded spaceport cantina...",
    "threat_level": "moderate",
    "tags": ["cantina", "public", "criminal"],
    "controlling_factions": ["hutts"]
  }
]
```

**Notes:**
- Used by frontend for starting location selection during campaign creation
- Backend filters out prison/dangerous locations for safe starts via `_is_safe_start_location()`

---

#### `GET /v2/era/{era_id}/companions`

Retrieve companion previews for character creation screen.

**Path Parameters:**
- `era_id` (string): Era identifier

**Response:**

```json
{
  "era_id": "REBELLION",
  "companions": [
    {
      "id": "comp-reb-kessa",
      "name": "Kessa Vane",
      "species": "Zabrak",
      "archetype": "Alliance scout",
      "motivation": "To map safe hyperspace routes...",
      "voice_belief": "Every route saved is a hundred lives saved"
    }
  ]
}
```

**Notes:**
- Returns up to 5 companions per era
- Used by the character creation page to preview potential party members

---

### 11) Player Profile Endpoints

#### `POST /v2/player/profiles`
Create a player profile for cross-campaign persistence.

**Request**
```json
{ "display_name": "Rex" }
```

**Response**
```json
{ "id": "uuid", "display_name": "Rex", "created_at": "2026-01-15T12:00:00Z" }
```

#### `GET /v2/player/profiles`
List all player profiles.

**Response**
```json
{ "profiles": [{ "id": "uuid", "display_name": "Rex", "created_at": "..." }] }
```

#### `GET /v2/player/{player_profile_id}/legacy`
Fetch past campaign outcomes for a player profile.

**Response**
```json
{
  "player_profile_id": "uuid",
  "legacy": [{
    "id": "uuid",
    "campaign_id": "uuid",
    "era": "REBELLION",
    "background_id": "smuggler",
    "genre": "space opera",
    "outcome_summary": "...",
    "faction_standings": {},
    "major_decisions": [],
    "character_fate": "...",
    "arc_stage_reached": "RESOLUTION",
    "completed_at": "..."
  }]
}
```

---

### 12) Campaign Completion

#### `POST /v2/campaigns/{campaign_id}/complete`
Mark a campaign as completed and save legacy data.

**Request**
```json
{
  "outcome_summary": "optional summary text",
  "character_fate": "optional fate description"
}
```

**Response**
```json
{ "status": "completed", "legacy_id": "uuid", "campaign_id": "uuid" }
```

---

### 13) Debug Endpoint

#### `GET /v2/debug/era-packs`
Shows loaded era pack metadata (development only).

**Response**
```json
{
  "pack_dir": "./data/static/era_packs",
  "pack_dir_exists": true,
  "count": 6,
  "packs": [{
    "era_id": "REBELLION",
    "backgrounds_count": 6,
    "locations_count": 57,
    "companions_count": 8
  }]
}
```

---

## Additional Notes

### Quest System

The `quest_log` field in `TurnResponse` is populated by the `QuestTracker` system (`backend/app/core/quest_tracker.py`). Quests are defined in era pack YAML files (`quests.yaml`) and tracked deterministically:

- **Entry conditions**: `turn.min`, `location`, `event_type`, `npc_met`
- **Stage conditions**: `npc_met`, `action_taken`, `event_type`, `stage_completed`, `item_acquired`
- **Statuses**: `available` | `active` | `completed` | `failed`

Quest notifications appear in the `warnings` array prefixed with `[QUEST]`.

**Example `quest_log` entry:**
```json
{
  "quest-rebel-hideout": {
    "quest_id": "quest-rebel-hideout",
    "status": "active",
    "current_stage_idx": 1,
    "stages_completed": [0],
    "activated_turn": 5
  }
}
```

### Enhanced Suggestions

`generate_suggestions()` in `director_validation.py` now incorporates:
- **Memory-aware**: Detects player tone streaks (3+ same tone) and adapts labels
- **Companion-aware**: When a trusted companion (influence > 50) is in the party, generates companion-specific suggestions based on archetype
- **Location-specific**: Uses era pack location services (`bounty_board`, `medbay`, etc.), hidden access points, and travel links to generate contextual options
- **Return visit awareness**: Adapts labels when player revisits a location

### SuggestionRefiner Context

The `SuggestionRefiner` LLM prompt now includes:
- `COMPANIONS`: companion names with trust level and archetype
- `PLAYER PATTERN`: tone streak information (e.g., "Player chose PARAGON 3+ turns in a row")

---

## Auth & Security Notes

- No authentication is implemented.
- CORS is wide open (`allow_origins=["*"]`).

Treat this as **local-only** unless you add auth and restrict CORS.
