# 03 — State Management & Persistence

## GameState (What Flows Through the Graph)

**Model:** `backend/app/models/state.py` (`class GameState`)

The LangGraph pipeline operates on a JSON-serializable `GameState`. At graph entry, it is converted to a dict via:

- `backend/app/core/nodes/__init__.py:state_to_dict()`
- `backend/app/core/nodes/__init__.py:dict_to_state()`

### Field Groups (How to Think About It)

`GameState` mixes three kinds of data:

1. **Persistent snapshots** (loaded from SQLite at the start of a turn):

   - `campaign_id`, `player_id`, `turn_number`, `current_location`
   - `campaign` (dict: `title`, `time_period`, `world_time_minutes`, `world_state_json`, ...)
   - `player` (serialized `CharacterSheet`: stats/HP/location/inventory/psych_profile)
   - `player_starship` (`dict | None`): starship data if acquired (V2.10); `None` if no ship
   - `known_npcs` (`list[str]`): NPC IDs the player has encountered (loaded from `world_state_json`)
   - `era_summaries` (dict): compressed summaries of narrative arcs per era
   - `recent_narrative` (str): recent narration text for continuity

2. **Cross-turn memory** (kept in the state packet for prompt continuity):

   - `history`: list of compact event summaries (strings), derived from `turn_events` (hidden excluded)
   - `last_user_inputs`: list of raw inputs (currently optional/spotty depending on caller)

3. **Per-turn transient fields** (produced by nodes and usually reset each turn):

   - Routing: `intent`, `route`, `action_class`, `router_output`
   - Mechanics: `mechanic_result`
   - Encounter: `present_npcs`, spawn/throttle event staging
   - Living World: `pending_world_time_minutes`, `world_sim_*`, `new_rumors`, `active_rumors`
   - Arc Planning: `arc_guidance` (arc stage, tension, pacing hints, priority threads)
   - Narrative: `director_instructions`, `suggested_actions`, `final_text`, `lore_citations`, `validation_notes`
   - Suggestions: `embedded_suggestions` (always `None` in V2.15; suggestions are deterministic via Director)
   - Shared retrieval: `shared_kg_*` (KG context), `shared_episodic_memories` (episodic memory context)
   - Telemetry: `context_stats` (dev-only), `warnings`

**Important invariant:** only Commit writes to the DB. Other nodes mutate the in-memory state only.

---

## Key Pydantic Models

### CharacterSheet

**File:** `backend/app/models/state.py`

Key fields:

- `name`, `species`, `role`, `location_id`
- `stats_json`, `hp_current`, `credits`
- `psych_profile` (current_mood, stress_level, active_trauma)
- `background` (str): character background selection (V2.9)
- `cyoa_answers` (dict): CYOA character creation answers (V2.13)
- `gender` (str): `"male"` or `"female"` (V2.8)
- `planet_id` (str): starting/current planet

### ActionSuggestion

**File:** `backend/app/models/state.py`

Key fields:

- `intent_text` (str): verb-first 4-8 word label
- `tone` (str): `PARAGON` | `INVESTIGATE` | `RENEGADE` | `NEUTRAL`
- `risk_level` (str): `SAFE` | `RISKY` | `DANGEROUS` (3-tier, V2.9)
- `category` (str): `SOCIAL` | `COMBAT` | `EXPLORATION` | `STEALTH` | etc.
- `companion_reactions` (dict): per-companion reaction predictions
- `risk_factors` (list[str]): human-readable risk descriptions

### MechanicOutput

**File:** `backend/app/models/state.py`

Key fields:

- `action_type`, `events`, `narrative_facts`, `time_cost_minutes`
- `success` (bool): whether the action succeeded
- `outcome_summary` (str): human-readable outcome
- `modifiers` (list[dict]): applied DC modifiers (environmental, arc stage, etc.)
- `stress_delta` (int): change to stress level
- `critical_outcome` (str | None): critical success/failure description
- `world_reaction_needed` (bool): whether WorldSim should react

---

## SQLite Schema (Key Tables)

Schema reference: `backend/app/db/schema.sql` (applied via migrations in `backend/app/db/migrations/`).

Migrations: `0001` through `0018` (see `backend/app/db/migrations/`).

### `campaigns`

| Column | Type | Notes |
| -------- | ------ | ------ |
| `id` | TEXT (PK) | Campaign UUID |
| `title` | TEXT | Campaign title |
| `time_period` | TEXT | Era/setting |
| `world_time_minutes` | INTEGER | Accumulated in-world time |
| `world_state_json` | TEXT (JSON) | Living world state blob (see below) |
| `created_at` | TEXT | ISO timestamp (migration 0006) |
| `updated_at` | TEXT | ISO timestamp (migration 0007) |

### `characters`

| Column | Type | Notes |
| -------- | ------ | ------ |
| `id` | TEXT (PK) | Character UUID |
| `campaign_id` | TEXT (FK) | Parent campaign |
| `name` | TEXT | Display name |
| `role` | TEXT | `Player`, `NPC`, etc. |
| `location_id` | TEXT | Current location |
| `stats_json` | TEXT (JSON) | Stat block |
| `hp_current` | INTEGER | Current HP |
| `relationship_score` | INTEGER | NPC relationship with player |
| `secret_agenda` | TEXT | Hidden NPC motivation (never exposed in `present_npcs`) |
| `credits` | INTEGER | Currency |
| `psych_profile` | TEXT (JSON) | Player psychology (e.g. mood/stress/trauma) |
| `planet` | TEXT | Planet/location name (migration 0008) |
| `background` | TEXT | Character background (migration 0009) |
| `created_at` | TEXT | ISO timestamp (migration 0010) |
| `updated_at` | TEXT | ISO timestamp (migration 0011) |
| `gender` | TEXT | `"male"` or `"female"` (migration 0015) |

### `inventory`

| Column | Type | Notes |
| -------- | ------ | ------ |
| `id` | TEXT (PK) | `{owner_id}:{item_name}` |
| `owner_id` | TEXT | Character id |
| `item_name` | TEXT | Item name |
| `quantity` | INTEGER | Stack count |
| `attributes_json` | TEXT (JSON) | Item attributes |

### `turn_events` (Event Store)

| Column | Type | Notes |
| -------- | ------ | ------ |
| `id` | INTEGER (PK) | Auto-increment |
| `campaign_id` | TEXT | Parent campaign |
| `turn_number` | INTEGER | Turn index |
| `event_type` | TEXT | MOVE/DAMAGE/FLAG_SET/RUMOR_SPREAD/STARSHIP_ACQUIRED/etc. |
| `payload_json` | TEXT (JSON) | Event-specific payload |
| `is_hidden` | INTEGER | Hidden from player/history |
| `is_public_rumor` | INTEGER | Included in `/v2/.../rumors` |
| `timestamp` | TEXT | ISO timestamp |
| `created_at` | TEXT | ISO timestamp (migration 0012) |

### `rendered_turns` (Transcript)

Stores the player-facing narration and UI suggestions per turn.

| Column | Type | Notes |
| -------- | ------ | ------ |
| `campaign_id` | TEXT | Parent campaign |
| `turn_number` | INTEGER | Turn index |
| `text` | TEXT | Narration prose |
| `citations_json` | TEXT (JSON) | Lore citations |
| `suggested_actions_json` | TEXT (JSON) | Suggested actions (4, deterministic) |
| `created_at` | TEXT | Timestamp |

### `episodic_memories` (V2.14)

Migration `0014_episodic_memories.sql`.

| Column | Type | Notes |
| -------- | ------ | ------ |
| `id` | INTEGER (PK) | Auto-increment |
| `campaign_id` | TEXT | Parent campaign |
| `turn_number` | INTEGER | Turn when memory was created |
| `summary` | TEXT | Compressed narrative summary |
| `importance` | REAL | Memory importance score |
| `created_at` | TEXT | ISO timestamp |

### `suggestion_cache` (V2.16)

Migration `0016_suggestion_cache.sql`.

| Column | Type | Notes |
| -------- | ------ | ------ |
| `id` | INTEGER (PK) | Auto-increment |
| `campaign_id` | TEXT | Parent campaign |
| `turn_number` | INTEGER | Turn number |
| `suggestions_json` | TEXT (JSON) | Cached suggestion data |
| `created_at` | TEXT | ISO timestamp |

### `player_starships` (V2.10)

Migration `0017_starships.sql`.

| Column | Type | Notes |
| -------- | ------ | ------ |
| `id` | TEXT (PK) | Starship UUID |
| `campaign_id` | TEXT | Parent campaign |
| `player_id` | TEXT | Owner character |
| `ship_name` | TEXT | Ship name |
| `ship_class` | TEXT | Ship class/type |
| `attributes_json` | TEXT (JSON) | Ship stats and properties |
| `acquired_method` | TEXT | quest/purchase/salvage/faction/theft |
| `created_at` | TEXT | ISO timestamp |

### `player_profiles` (V2.18)

Migration `0018_player_profiles.sql`.

| Column | Type | Notes |
| -------- | ------ | ------ |
| `id` | TEXT (PK) | Profile UUID |
| `campaign_id` | TEXT | Parent campaign |
| `player_id` | TEXT | Character |
| `profile_json` | TEXT (JSON) | Player preference/style profile |
| `created_at` | TEXT | ISO timestamp |

### `cyoa_answers` (V2.13)

Migration `0013_add_cyoa_answers.sql`.

| Column | Type | Notes |
| -------- | ------ | ------ |
| `id` | INTEGER (PK) | Auto-increment |
| `campaign_id` | TEXT | Parent campaign |
| `player_id` | TEXT | Character |
| `question_key` | TEXT | CYOA question identifier |
| `answer_value` | TEXT | Selected answer |
| `created_at` | TEXT | ISO timestamp |

### Knowledge Graph tables (optional pipeline)

Migration `0005_knowledge_graph.sql` adds:

- `kg_entities`
- `kg_triples`
- `kg_summaries`
- `kg_extraction_checkpoints`

These are populated by `python -m storyteller extract-knowledge` and are used at runtime by `backend/app/rag/kg_retriever.py` for Director/Narrator prompt context.

---

## Projections + Transaction Strategy

Commit-only writes are implemented in `backend/app/core/nodes/commit.py`.

Within one SQLite transaction, Commit:

1. Advances `campaigns.world_time_minutes`
2. Updates `campaigns.world_state_json` (factions + party + news + ledger + **arc_state** + throttling state + **known_npcs** + **companion_memories** + **era_summaries** + **opening_beats** + **act_outline** + **faction_memory** + **npc_states**)
3. Appends events (`turn_events`)
4. Applies projections (`backend/app/core/projections.py`) to normalized tables
5. Applies encounter throttle effects (writes to `world_state_json`)
6. Writes transcript (`rendered_turns`)
7. Persists episodic memories (`episodic_memories`)
8. Updates `known_npcs` in `world_state_json`
9. Persists era transitions and era summaries

If anything fails: rollback and return a structured API error (FastAPI global exception handler).

---

## Narrative Ledger

**File:** `backend/app/core/ledger.py`

The ledger is a structured summary built from events each turn and stored in `world_state_json.ledger`. It is used to ground LLM prompts without replaying raw event history.

It tracks capped lists such as:

- `established_facts`
- `open_threads`
- `active_goals`
- `constraints`
- `tone_tags`
- `active_themes` — themes activated via keyword matching in `_themes_from_text()` when narration contains 2+ matching keywords

**Weighted threads:** Open threads use `[W1]`/`[W2]`/`[W3]` prefix for semantic weighting. `weighted_thread_count()` in the arc planner uses these weights for tension calculation. Theme reinforcement keywords are tracked to sustain active themes across turns.

Commit updates the ledger every turn (`update_ledger(...)`) using the staged event list plus the finalized narration text.

---

## `world_state_json` (Internal Schema)

`campaigns.world_state_json` is a JSON object. Common keys:

### Living World

- `active_factions`: list of faction dicts (seeded from Era Packs when `ENABLE_BIBLE_CASTING=1`)
- `news_feed`: list of ME-style briefing items
- `new_rumors_raw`: list of raw rumor strings from the most recent WorldSim run
- `faction_memory`: dict of faction_id -> multi-turn plan tracking (goals, progress, last action)
- `npc_states`: dict of npc_id -> autonomous NPC state (location, goals, 20% movement per tick)

### Party / Alignment

- `party`: list of companion IDs (strings)
- `party_traits`: dict of companion_id -> trait dict
- `party_affinity`: dict of companion_id -> int
- `loyalty_progress`: dict of companion_id -> int
- `alignment`: `{light_dark: int, paragon_renegade: int}`
- `faction_reputation`: dict of faction_name -> int
- `banter_queue`: list of queued banter lines/dicts
- `companion_memories`: dict of companion_id -> list of memory strings

### Encounter Throttling (NPC pacing)

Persisted via events staged in Encounter and applied inside Commit:

- `introduced_npcs`: list of NPC ids already introduced
- `introduction_log`: list of `{npc_id, introduced_at_minutes, trigger}`
- `last_location_id`: last effective location (for "location changed" gating)
- `npc_introduction_triggers`: optional list (single-use; cleared after location update)

### Prompt Grounding & Arc Tracking

- `ledger`: structured ledger object (see above)
- `arc_state`: arc stage tracking (`current_stage`, `stage_start_turn`)
- `known_npcs`: list of NPC IDs the player has encountered (names shown; unknowns get descriptive roles)
- `era_summaries`: dict of era -> compressed narrative summary

### Campaign Opening (V2.12)

- `opening_beats`: 3-beat structure (ARRIVAL, ENCOUNTER, INCITING_INCIDENT) for turns 1-3
- `act_outline`: lightweight 3-act story arc with key NPCs (villain/rival/informant)

This schema is intentionally flexible; unknown keys are tolerated to allow iterative feature rollout.

---

## `cleared_for_next_turn()` Note

`GameState.cleared_for_next_turn()` resets transient fields (including WorldSim keys) and preserves persistent + memory fields. The canonical runtime path reloads state from SQLite after Commit, but this helper is used by tests and tooling.
