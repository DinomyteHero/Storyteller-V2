# 03 — State and Persistence

## Design: Event Sourcing

The system uses a **write-once event log** as the source of truth:

- `turn_events` rows are **immutable** once written.
- Normalized tables (`characters`, `inventory`, etc.) and `campaigns.world_state_json` are **projections** that are rebuilt from events via `apply_projection()` (in `backend/app/core/state_reducer.py` / aliased as `projections.py`).
- **Single transaction boundary:** only `CommitNode` ever calls `conn.commit()`. All preceding pipeline nodes are pure functions.

This design means:

- The pipeline can fail at any stage before Commit without leaving partial state.
- Game state can always be reconstructed from the event log.
- The `rendered_turns` table provides the audit trail of what the player actually saw.

## The Pipeline Packet: `GameState`

`GameState` (defined in `backend/app/models/state.py`) is a Pydantic model that flows through the LangGraph pipeline as a Python `dict` (`state_to_dict()` / `dict_to_state()` converts between representations). It is **never persisted as a blob** — only event payloads and world_state_json are persisted.

Key fields:

```python
class GameState(BaseModel):
    # Identity
    campaign_id: str
    player_id: str
    turn_number: int

    # Player character
    player: CharacterSheet

    # Campaign metadata + world state
    campaign: dict          # includes world_state_json, news_feed, etc.

    # Location
    current_location: str
    current_planet: str
    effective_location: str

    # Turn input/output
    user_input: str
    intent: str             # "META" | "TALK" | "ACTION"
    final_text: str         # Narrator prose output
    suggested_actions: list[ActionSuggestion]
    player_responses: list  # PlayerResponse dicts (V5.0 ChoiceCrafter output)

    # Pipeline transients
    mechanic_result: dict | None
    director_instructions: str
    arc_guidance: dict
    scene_frame: dict       # topic_primary, subtext, npc_agenda
    npc_utterance: dict     # For ChoiceCrafter context

    # NPC state
    present_npcs: list[dict]
    known_npcs: list[str]
    spawn_events: list[dict]

    # World sim
    active_rumors: list[str]
    world_sim_events: list[dict]
    pending_world_time_minutes: int

    # Companion system
    last_user_inputs: list[str]  # recent inputs for tone streak detection

    # Runtime (not persisted)
    __runtime_conn: sqlite3.Connection   # non-serializable; stripped before return

    # Warnings + context
    warnings: list[str]
    context_stats: dict
    router_output: dict
```

## SQLite Database Schema

Schema is applied via `backend/app/db/migrate.py`, which runs all SQL files in `backend/app/db/migrations/` in order. **34 migrations** are currently applied (0001 through 0034, with 0024 absent — the sequence jumps from 0023 to 0025).

### Core Tables

#### `campaigns`

Stores campaign metadata and all mutable world state.

```sql
campaigns (
    id TEXT PRIMARY KEY,
    title TEXT,
    time_period TEXT,   -- era/period identifier (e.g., "rebellion")
    world_state_json TEXT,  -- JSON blob: see "World State JSON Structure" below
    world_time_minutes INTEGER DEFAULT 0,
    turn_number INTEGER DEFAULT 0,
    -- player_id, difficulty, campaign_mode, campaign_scale
    created_at TEXT,
    updated_at TEXT
)
```

`world_state_json` is the primary mutable world container (described in detail below).

#### `characters`

Stores both player characters and NPCs.

```sql
characters (
    id TEXT PRIMARY KEY,
    campaign_id TEXT REFERENCES campaigns(id),
    name TEXT,
    character_type TEXT,  -- "player" | "npc" | "companion"
    stats_json TEXT,      -- JSON: character stats
    hp_current INTEGER,
    hp_max INTEGER,
    location_id TEXT,
    planet_id TEXT,
    credits INTEGER DEFAULT 0,
    background TEXT,
    gender TEXT,
    cyoa_answers TEXT,    -- JSON: choose-your-own-adventure answers
    psych_profile_json TEXT,  -- JSON: {current_mood, stress_level, active_trauma}
    created_at TEXT,
    updated_at TEXT
)
```

#### `turn_events` (Append-Only)

The immutable event log.

```sql
turn_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT REFERENCES campaigns(id),
    turn_number INTEGER,
    event_type TEXT,      -- e.g., "MOVE", "COMBAT", "DIALOGUE", "NPC_SPAWN", "STARSHIP_ACQUIRED", etc.
    payload_json TEXT,    -- JSON: event-specific payload
    is_hidden INTEGER DEFAULT 0,   -- hidden events not shown to player
    is_public_rumor INTEGER DEFAULT 0,  -- rumor events surfaced in news feed
    created_at TEXT
)
```

Events are **never updated or deleted**. `is_hidden=1` events are for internal state tracking (e.g., encounter throttle, NPC introductions). `is_public_rumor=1` events feed the news briefing system.

#### `inventory`

Item ownership. Normalized from `ITEM_ACQUIRED` / `ITEM_LOST` events via projections.

```sql
inventory (
    campaign_id TEXT,
    character_id TEXT,
    item_name TEXT,
    quantity INTEGER DEFAULT 1,
    item_data_json TEXT,
    PRIMARY KEY (campaign_id, character_id, item_name)
)
```

#### `rendered_turns`

Audit trail of exactly what the player saw.

```sql
rendered_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT,
    turn_number INTEGER,
    final_text TEXT,
    suggested_actions_json TEXT,
    intent TEXT,
    created_at TEXT
)
```

#### `episodic_memories`

Compressed narrative memories (summaries of 5-turn windows). Retrieved by Director and Narrator for continuity grounding.

```sql
episodic_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT,
    turn_range TEXT,          -- e.g., "1-5"
    summary TEXT,
    summary_embedding BLOB,   -- optional vector embedding (migration 0021)
    created_at TEXT
)
```

#### `starships`

Player-acquired starships (earned in-story; no starting ship).

```sql
starships (
    id TEXT PRIMARY KEY,
    campaign_id TEXT REFERENCES campaigns(id),
    player_id TEXT,
    name TEXT,
    class TEXT,
    stats_json TEXT,
    acquisition_type TEXT  -- "quest" | "purchase" | "salvage" | "faction" | "theft"
)
```

#### `player_profiles`

Cross-campaign player legacy data.

```sql
player_profiles (
    player_id TEXT PRIMARY KEY,
    name TEXT,
    legacy_json TEXT
)
```

#### `npc_states` (V7.0 — extracted from world_state_json)

Normalized NPC state, indexed for per-NPC queries. Extracted from `world_state_json["npc_states"]` on each commit; hydrated back into world_state on load.

```sql
npc_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    npc_id TEXT NOT NULL,
    npc_name TEXT NOT NULL DEFAULT '',
    state_json TEXT NOT NULL DEFAULT '{}',
    last_seen_turn INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    UNIQUE (campaign_id, npc_id)
)
```

#### `quest_entries` (V7.0 — extracted from world_state_json)

Normalized quest entries, indexed for per-quest queries. Extracted from `world_state_json["quest_log"]` on each commit.

```sql
quest_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    quest_id TEXT NOT NULL,
    quest_title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',   -- active|completed|failed|abandoned
    quest_json TEXT NOT NULL DEFAULT '{}',
    created_turn INTEGER NOT NULL DEFAULT 0,
    updated_turn INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    UNIQUE (campaign_id, quest_id)
)
```

#### `turn_idempotency` (V7.0)

Idempotency ledger for `/turn` and `/turn_stream` replay safety. Prevents duplicate commits when the same request is retried.

```sql
turn_idempotency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',  -- processing | completed
    response_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(campaign_id, player_id, endpoint, idempotency_key)
)
```

#### `pending_world_state_patches` (V7.0)

Deferred maintenance agent output. Agents that run post-commit (MemoryAgent, QuestWeaver, ProgressionAgent, PsychArchivist) write JSON patches here. Applied on next turn load via `apply_pending_patches()`.

```sql
pending_world_state_patches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    patch_json TEXT NOT NULL,
    applied INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
)
```

#### `canon_events` (V7.0)

Tracks which canon events have been triggered in a campaign (Historical mode only). Static event definitions live in `data/static/era_packs/{era_id}/canon_events.json`.

```sql
canon_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    era_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    triggered_at_turn INTEGER NOT NULL,
    arc_stage TEXT NOT NULL,           -- SETUP|RISING|CLIMAX|RESOLUTION
    event_text TEXT NOT NULL,
    is_immutable INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    UNIQUE (campaign_id, event_id)
)
```

#### `turn_snapshots` (V7.0)

World state snapshots per turn for rewind/undo capability. Stored after each successful commit.

```sql
turn_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    world_state_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    UNIQUE (campaign_id, turn_number)
)
```

#### `crystallized_memories` (V7.0)

High-signal memories that remain retrievable regardless of compression in long-running campaigns.

```sql
crystallized_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    memory_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    full_text TEXT,
    npcs_involved TEXT DEFAULT '[]',
    location TEXT,
    emotional_tag TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
)
```

#### `character_legacies` (V7.0)

Structured character legacy snapshots for saga continuity across linked campaigns.

```sql
character_legacies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    saga_id TEXT,
    legacy_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
)
```

#### `sagas` (V7.0)

Saga hierarchy for linked campaigns. Campaigns can be grouped into player-owned sagas.

```sql
sagas (
    id TEXT PRIMARY KEY,
    player_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
```

Adds `saga_id` and `saga_chapter` columns to the `campaigns` table.

#### Knowledge Graph Tables (Optional)

Populated by the offline KG extraction pipeline (`storyteller extract-knowledge`).

```sql
kg_entities (
    id TEXT PRIMARY KEY,
    campaign_id TEXT,
    canonical_name TEXT,
    entity_type TEXT,    -- e.g., "PERSON", "LOCATION", "ORGANIZATION"
    aliases_json TEXT,
    attributes_json TEXT
)

kg_triples (
    id TEXT PRIMARY KEY,
    campaign_id TEXT,
    subject_id TEXT REFERENCES kg_entities(id),
    predicate TEXT,
    object_id TEXT,
    confidence REAL,
    source_chunk_id TEXT
)
```

#### Truth Ledger Tables (V5.0)

```sql
truth_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT,
    fact_key TEXT,
    fact_value_json TEXT,
    updated_at TEXT,
    source_turn_id TEXT,
    UNIQUE(campaign_id, fact_key)
)

truth_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT,
    turn_id TEXT,
    event_json TEXT,
    created_at TEXT
)
```

`truth_facts` is an upsert-keyed store: `fact_key` is unique per campaign. Updated by `truth_ledger.upsert_facts()` inside the Commit node. Used for `contradiction_errors()` checks in the Narrative Validator.

---

## World State JSON Structure

`campaigns.world_state_json` is the single blob that holds all non-event, mutable world state. Updated exclusively by the Commit node.

```json
{
  "active_factions": [...],          // List of EraFaction state dicts
  "npc_states": {...},               // {npc_id: {location_id, mood, goals, last_seen_turn}}
  "party_state": {                   // V5.0 PartyState (canonical companion data)
    "active_companions": ["comp_id"],
    "companion_states": {
      "comp_id": {
        "companion_id": "comp_id",
        "influence": 30,             // -100..100 (primary axis)
        "trust": 10,                 // -100..100
        "respect": 20,               // -100..100
        "fear": 0,                   // -100..100
        "loyalty_progress": 45,      // 0..100
        "traits": {},
        "memories": [],
        "banter_last_turn": 5
      }
    }
  },
  "party": [...],                    // Legacy: list of companion ids (still written for compat)
  "party_affinity": {...},           // Legacy: {comp_id: influence_int}
  "party_traits": {...},             // Legacy: {comp_id: {trait: val}}
  "loyalty_progress": {...},         // Legacy: {comp_id: int}
  "quest_log": {                     // V5.0 QuestTracker runtime state
    "quest_id": {
      "quest_id": "quest_id",
      "status": "active",            // available | active | completed | failed
      "current_stage_idx": 1,
      "stages_completed": ["stage_1"],
      "activated_turn": 3
    }
  },
  "fired_moments": ["moment_id"],    // V5.0 once-only EraMoment enforcement
  "completed_quests": ["quest_id"],  // Shorthand set for EraMoment trigger checks
  "alignment": {"light": 10, "dark": 0},
  "faction_reputation": {"rebel_alliance": 5, "galactic_empire": -3},
  "known_npcs": ["npc_id"],         // NPCs player has encountered (persist after Commit)
  "arc_state": {                     // Hero's Journey arc tracking
    "current_stage": "SETUP",
    "beat_index": 2,
    "active_threads": [...]
  },
  "ledger": {                        // Narrative ledger for Director/Narrator grounding
    "established_facts": [...],
    "open_threads": [...],
    "consequence_hints": [...]       // Used by ChoiceCrafter (V5.0)
  },
  "news_feed": [...],               // ME-style briefing items (from world sim rumors)
  "faction_memory": {...},          // Multi-turn faction plan tracking
  "banter_queue": [],               // Pending banter lines (consumed by Narrator)
  "companion_reactions_summary": "...", // Injected into Narrator context
  "inter_party_tensions": [...],    // Tension context for Director
  "era_summaries": {...},           // Compressed era transition summaries
  "opening_beats": [...],           // Prologue opening beats
  "act_outline": {...},             // CampaignArchitect arc scaffold
  "setting_rules": {...},           // SettingRules for setting-agnostic agents (V5.0)
  "current_location": "loc-id",
  "current_planet": "Tatooine",
  "hub_mode": false,                // Explicit hub mode override (normally derived from era pack)
  "stress_level": 15,               // Player stress (0-100; reduced by rest in hub)
  "player_condition": {"fatigue": 5},
  "last_rest_turn": 3,
  "flags": {},                      // Arbitrary boolean flags for quest conditions
  "inventory": [...],               // World-state inventory snapshot (also in inventory table)

  // ── V10.0 Narrative Intelligence fields ──
  "revelation_queue": [             // RevelationAgent output: queued secrets for dramatic reveal
    {
      "id": "rev-45-0",
      "content": "Kira has been secretly reporting to the Inquisitor",
      "source": "npc_agenda",
      "source_npc": "kira-solari",
      "dramatic_value": 8,           // 1-10
      "optimal_conditions": ["player trusts Kira", "climax reached"],
      "turn_queued": 45,
      "revealed": false
    }
  ],
  "callback_seeds": [               // CallbackCrystallizerAgent output: memorable moments for echo
    {
      "turn": 23,
      "moment": "Kira chose to stay despite everything",
      "echo_text": "Something in her voice reminds you...",
      "emotional_context": "sacrifice",  // betrayal|sacrifice|triumph|loss|revelation|humor
      "trigger_conditions": ["when Kira is present", "at climax"],
      "used_count": 0                // Max CALLBACK_MAX_USES (2)
    }
  ],
  "player_behavior_profile": {      // PlayerProfileAgent output: choice pattern analysis
    "preferred_tone": {"PARAGON": 0.4, "INVESTIGATE": 0.3},
    "preferred_action": {"TALK": 0.5, "DO": 0.3},
    "risk_tolerance": "moderate",    // cautious | moderate | bold
    "companion_engagement": 0.6,     // 0.0-1.0
    "creativity_ratio": 0.2,         // free-text vs structured
    "engagement_trend": "stable",    // stable | declining | rising
    "play_style": "diplomat",        // diplomat | fighter | explorer | socialite
    "possible_boredom": false,
    "turn_analyzed": 30
  },
  "choice_history": [               // Commit-appended metadata per turn for profiling
    {"turn": 1, "tone": "PARAGON", "action_type": "TALK", "risk": "SAFE",
     "is_free_text": false, "input_length": 42, "creative_deviation": false}
  ],
  "companion_revelations": {        // Companion wound/reveal layer state (V10.0 Feature 6)
    "comp-reb-kira": {
      "stage": "deep",              // surface | deep | core
      "turn": 25,
      "trigger_text": "Under stress — the truth slips out...",
      "revealed_this_turn": false
    }
  },
  "arc_mood_profile": "heroic",     // heroic | noir | tragic | kishotenketsu | mystery
  "arc_consequences": {             // ArcConsequenceTracker output (V5.0 + V10.0 thematic_signature)
    "arc_number": 2,
    "thematic_signature": {         // V10.0: cross-arc thematic resonance
      "dominant_themes": ["cost_of_loyalty", "redemption"],
      "theme_from_decisions": ["sacrifice"],
      "arc_number": 1
    }
  }
}
```

### PartyState vs Legacy Fields

`world_state_json["party_state"]` is the **canonical** companion runtime data source (V5.0). The legacy fields (`party`, `party_affinity`, `party_traits`, `loyalty_progress`) are still written by `save_party_state()` for backward compatibility with any code that reads them directly.

`load_party_state()` in `backend/app/core/party_state.py` reads from `party_state` first, then falls back to legacy fields if `party_state` is absent.

---

## Event Projection

`backend/app/core/state_reducer.py` (aliased as `projections.py`) contains:

```python
def apply_projection(conn, campaign_id):
    """Replay all turn_events for campaign_id and update normalized tables."""
    events = conn.execute(
        "SELECT event_type, payload_json FROM turn_events WHERE campaign_id=? ORDER BY id",
        (campaign_id,)
    ).fetchall()
    for row in events:
        _dispatch(conn, campaign_id, row["event_type"], json.loads(row["payload_json"]))
```

Event handlers currently dispatched:

| Event Type | Projection Action |
| ------------ | ------------------- |
| `MOVE` | Update `characters.location_id`, `characters.planet_id` |
| `DAMAGE` | Update `characters.hp_current` |
| `HEAL` | Update `characters.hp_current` (capped at `hp_max`) |
| `ITEM_ACQUIRED` | Upsert `inventory` row |
| `ITEM_LOST` | Delete or decrement `inventory` row |
| `CREDITS_GAINED` | Increment `characters.credits` |
| `CREDITS_LOST` | Decrement `characters.credits` (floor 0) |
| `RELATIONSHIP_CHANGED` | Update `relationships` table |
| `NPC_SPAWN` | Insert `characters` row (if not exists) |
| `STARSHIP_ACQUIRED` | Insert `starships` row |
| `NPC_INTRODUCTION_RECORDED` | Update encounter throttling state |
| `LAST_LOCATION_UPDATED` | Update encounter throttling state |

---

## State Loader

`backend/app/core/state_loader.py` reconstructs `GameState` from the DB at the start of each turn:

```python
def build_initial_gamestate(conn, campaign_id, player_id) -> GameState:
    apply_projection(conn, campaign_id)   # 1. Ensure projections are current
    campaign = load_campaign(conn, campaign_id)   # 2. Load campaign row + world_state_json
    player = load_player_by_id(conn, campaign_id, player_id)   # 3. Load character row
    known_npcs = load_known_npcs(conn, campaign_id)   # 4. Load known NPC list
    player_starship = load_player_starship(conn, campaign_id, player_id)  # 5. Load ship if any
    return GameState(campaign_id=campaign_id, ...)
```

---

## Truth Ledger

`backend/app/core/truth_ledger.py` exposes:

```python
def upsert_facts(conn, campaign_id, turn_id, facts: list[Fact]) -> None:
    """Write/update facts in truth_facts table (upsert by fact_key)."""

def get_facts(conn, campaign_id) -> dict[str, Any]:
    """Read all facts for a campaign."""

def ledger_summary(conn, campaign_id, limit=12) -> list[str]:
    """Return most-recently-updated facts as formatted strings."""

def contradiction_errors(claims: dict, facts: dict) -> list[str]:
    """Check incoming claims against established facts. Returns list of contradiction strings."""
```

The Truth Ledger is **distinct from** the narrative `ledger.py`, which handles prompt-grounding data (open_threads, established_facts strings, consequence_hints). The Truth Ledger persists machine-readable key-value facts for automated contradiction detection.

---

## Quest Tracker (V5.0)

`backend/app/core/quest_tracker.py` implements a deterministic quest state machine:

```python
class QuestTracker:
    def process_turn(self, quest_log, turn_number, location_id, events, world_state):
        """Check entry conditions for new quests and stage conditions for active quests.
        Returns (updated_quest_log, notifications)."""
```

Called by the Commit node via `process_quests_for_turn(world_state, era, turn_number, location_id, events)`. Updates `world_state["quest_log"]` in-place.

**Supported entry conditions:** `turn.min`, `turn.max`, `location`, `event_type`, `npc_met`

**Supported stage completion conditions:** `npc_met`, `action_taken`, `event_type`, `stage_completed`, `item_acquired`, `flag_equals`, `reputation_min`, `reputation_max`, `alignment_min`, `alignment_max`

**Stage resolution paths:** Each stage can define multiple `resolution_paths` (with per-path conditions and `next_stage_idx`), enabling non-linear quest branching.

---

## Migration History

| Migration | Purpose |
| ----------- | --------- |
| 0001 | Core tables: campaigns, characters, inventory, turn_events, relationships, npc_states, suggestion_cache |
| 0002 | rendered_turns table |
| 0003 | characters.credits column |
| 0004 | Living world: objectives table |
| 0005 | Knowledge graph tables (kg_entities, kg_triples) |
| 0006-0012 | Timestamps (created_at, updated_at) on campaigns and characters |
| 0013 | characters.cyoa_answers column |
| 0014 | episodic_memories table |
| 0015 | characters.gender column |
| 0016 | suggestion_cache table |
| 0017 | starships table |
| 0018 | player_profiles table (cross-campaign legacy) |
| 0019 | TurnContract schema additions |
| 0020 | Campaign turn versioning + world_time_minutes |
| 0021 | episodic_memories.summary_embedding column |
| 0022 | campaigns.campaign_bible_json column (CampaignBible output) |
| 0023 | truth_facts.is_immutable column (historical canon enforcement) |
| 0025 | crystallized_memories table (high-signal memory preservation) |
| 0026 | character_legacies table (saga continuity snapshots) |
| 0027 | sagas table + campaigns.saga_id/saga_chapter columns |
| 0028 | turn_idempotency table (replay safety for /turn endpoints) |
| 0029 | pending_world_state_patches table (deferred maintenance agents) |
| 0030 | canon_events table (historical timeline event triggers) |
| 0031 | turn_snapshots table (world state snapshots for rewind/undo) |
| 0032 | npc_states table — normalized from world_state_json (V7.0 schema extraction) |
| 0033 | quest_entries table — normalized from world_state_json (V7.0 schema extraction) |
| 0034 | generated_era_packs table |

> **Note:** Migration 0024 does not exist — the numbering jumps from 0023 to 0025.
