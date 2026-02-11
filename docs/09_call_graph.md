# 09 - Call Graph & Architecture Map

This document is a **"where does this code run from?"** map:

- The main entry points (UI, API, CLI, ingestion)
- The end-to-end **turn execution** path
- A node-by-node reference for the **LangGraph** pipeline

It intentionally avoids line numbers (they go stale quickly). Use file paths + function names.

---

## 1) Entry Points

### Legacy Python UI

- **Entry:** `streamlit_app.py` (repo root)
- **Backend client:** `ui/api_client.py` (HTTP calls into FastAPI)

### FastAPI Backend

- **App:** `backend/main.py` (FastAPI app + CORS + exception handlers)
- **Router:** `backend/app/api/v2_campaigns.py` (all V2 endpoints)
- **DB schema:** `backend/app/db/schema.sql` + `backend/app/db/migrations/` (applied via `backend/app/db/migrate.py`)

### Storyteller CLI

- **Entry:** `python -m storyteller` (see `storyteller/__main__.py`)
- **Dispatcher:** `storyteller/cli.py`
- **Commands:** `storyteller/commands/` (`setup`, `doctor`, `dev`, `ingest`, `query`, `extract-knowledge`)

### Ingestion

- **Entry:** `python -m ingestion <command>` (see `ingestion/__main__.py`)
  - `ingest` (flat TXT/EPUB)
  - `query`
  - ~~`build_character_facets`~~ (not functional)
- **Lore ingestion:** `python -m ingestion.ingest_lore ...` (PDF/EPUB/TXT hierarchical pipeline)
- **KG extraction:** `python -m storyteller extract-knowledge ...` (fills SQLite `kg_*` tables from ingested lore chunks)

---

## 2) Turn Execution (End-to-End)

Primary execution path for gameplay is the V2 turn endpoint:

```
Legacy Python UI
  -> POST /v2/campaigns/{campaign_id}/turn?player_id=...
      backend/app/api/v2_campaigns.py:post_turn()
        -> _get_conn() (apply_schema + open sqlite connection)
        -> backend/app/core/state_loader.py:build_initial_gamestate()
        -> backend/app/core/graph.py:run_turn(conn, GameState)
            -> nodes.state_to_dict(state) + inject state["__runtime_conn"] = conn
            -> compiled LangGraph invokes nodes (see §3)
            -> strips "__runtime_conn" and returns updated GameState
        -> builds TurnResponse (pads suggestions to exactly 4; optional debug/state)
```

**Important detail:** `__runtime_conn` is a **runtime-only** handle. Nodes that need DB access read it from `state["__runtime_conn"]`. It must never be persisted or returned in API responses.

---

## 3) LangGraph Topology (`backend/app/core/graph.py`)

The graph is built once (lazy singleton via `_get_compiled_graph()`) and invoked per turn.

### Branching (Router)

- **META**: `router -> meta -> commit -> END`
- **TALK** (dialogue-only): `router -> encounter -> world_sim -> companion_reaction -> arc_planner -> director -> narrator -> narrative_validator -> commit -> END`
- **ACTION**: `router -> mechanic -> encounter -> world_sim -> companion_reaction -> arc_planner -> director -> narrator -> narrative_validator -> commit -> END`

### Topology Diagram

```mermaid
flowchart LR
  router[router] -->|META| meta[meta] --> commit[commit] --> end((END))
  router -->|TALK| encounter[encounter]
  router -->|ACTION| mechanic[mechanic] --> encounter
  encounter --> world_sim[world_sim] --> companion[companion_reaction]
  companion --> arc[arc_planner] --> director[director] --> narrator[narrator]
  narrator --> validator[narrative_validator] --> commit
```

---

## 4) Node Reference (Reads/Writes + Dependencies)

All nodes live under `backend/app/core/nodes/`. The LangGraph state is a `dict` derived from `GameState` (see `backend/app/core/nodes/__init__.py`).

### Router (`backend/app/core/nodes/router.py`)

- **Node:** `router_node(state)`
- **Reads:** `user_input`
- **Writes:** `intent`, `route`, `action_class`, `intent_text`, `router_output`
- **Special:** on true dialogue-only input, synthesizes a minimal `mechanic_result` (time cost = `DIALOGUE_ONLY_MINUTES`)
- **Calls into:** `backend/app/core/router.py:route()`

### Meta (`backend/app/core/nodes/router.py`)

- **Node:** `meta_node(state)`
- **Reads:** `intent_text` / `user_input`
- **Writes:** `final_text`, `suggested_actions` (exactly 4), `lore_citations` (empty)
- **Pure/deterministic:** no DB and no LLM

### Mechanic (`backend/app/core/nodes/mechanic.py`)

- **Node:** `make_mechanic_node() -> mechanic_node(state)`
- **Reads:** `intent`, `user_input`, existing `GameState` fields (via `dict_to_state`)
- **Writes:** `mechanic_result`
- **Calls into:** `backend/app/core/agents/mechanic.py:MechanicAgent.resolve()` (deterministic; no LLM)

### Encounter (`backend/app/core/nodes/encounter.py`)

- **Node:** `make_encounter_node() -> encounter_node(state)`
- **Reads:** `__runtime_conn`, `campaign_id`, effective/current location, `mechanic_result`, `warnings`
- **Writes:** `present_npcs`, `spawn_events`, `throttle_events`, `active_rumors`
- **Calls into:**
  - `backend/app/core/agents/encounter.py:EncounterManager.check()` (deterministic encounter selection)
  - `backend/app/core/encounter_throttle.py:*` (rate limiting + anonymous extras)
  - **Legacy/escape hatch:** `CastingAgent.spawn()` only when `spawn_request` exists and throttling allows

### World Simulation (`backend/app/core/nodes/world_sim.py`)

- **Node:** `make_world_sim_node() -> world_sim_node(state)`
- **Reads:** `__runtime_conn` (optional read), `campaign.world_time_minutes`, `mechanic_result.time_cost_minutes`, `campaign_id`
- **Writes:** `pending_world_time_minutes`, `world_sim_events`, `world_sim_rumors`, `world_sim_factions_update`, `world_sim_ran`, `campaign.news_feed`, `new_rumors`
- **Runs when:** a tick boundary is crossed **or** travel occurred this turn
- **Calls into:**
  - `backend/app/world/faction_engine.py:simulate_faction_tick()` (deterministic path: zero LLM, seeded RNG for faction moves and rumor generation)
  - `backend/app/core/agents/architect.py:CampaignArchitect.simulate_off_screen()` (LLM fallback path with deterministic fallback)
  - `backend/app/models/news.py:rumors_to_news_feed()` (deterministic shaping)

### Companion Reaction (`backend/app/core/nodes/companion.py`)

- **Node:** `companion_reaction_node(state)`
- **Reads:** `mechanic_result`, `campaign.party`, `campaign.party_traits`
- **Writes:** campaign fields such as `party_affinity`, `loyalty_progress`, `banter_queue`, `alignment`, `faction_reputation`
- **Calls into:** `backend/app/core/companion_reactions.py:*` (deterministic heuristics)

### Arc Planner (`backend/app/core/nodes/arc_planner.py`)

- **Node:** `arc_planner_node(state)`
- **Reads:** `turn_number`, `campaign.world_state_json.ledger`, `campaign.world_state_json.arc_state`
- **Writes:** `arc_guidance` (arc stage, tension level, priority threads, pacing hints, suggested action weights, active themes, hero_beat, archetype_hints, theme_guidance, era_transition_pending)
- **Deterministic:** No DB writes, no LLM. Pure function based on ledger content and turn counts. Tracks Hero's Journey beats, genre triggers, and era transition readiness.

### Director (`backend/app/core/nodes/director.py`)

- **Node:** `make_director_node() -> director_node(state)`
- **Reads:** current `GameState` (via `dict_to_state`), including `arc_guidance`
- **Writes:** `director_instructions`, `suggested_actions` (4), `warnings`, `shared_kg_character_context`, `shared_episodic_memories`
- **Calls into:**
  - `backend/app/core/agents/director.py:DirectorAgent.plan()` (LLM for text-only scene instructions; no JSON schema, no retries for suggestions)
  - `backend/app/core/agents/director.py:generate_suggestions(state, mechanic_result)` (100% deterministic: uses NPCs, arc stage, mechanic result, tone for pure-Python suggestion generation)
  - `backend/app/rag/style_retriever.py:retrieve_style_layered()` (4-lane: Base SW + Era + Genre + Archetype)
  - `backend/app/rag/lore_retriever.py:retrieve_lore()` (director lane filters via `backend/app/rag/retrieval_bundles.py`)
  - `backend/app/rag/kg_retriever.py:KGRetriever.get_context_for_narrator()` (shared KG character context, passed to Narrator)
  - `backend/app/core/episodic_memory.py` (shared episodic memories, passed to Narrator)
  - `backend/app/core/director_validation.py:*` + `backend/app/core/action_lint.py:lint_actions()`

### Narrator (`backend/app/core/nodes/narrator.py`)

- **Node:** `make_narrator_node() -> narrator_node(state)`
- **Reads:** current `GameState` (via `dict_to_state`), `shared_kg_character_context`, `shared_episodic_memories`
- **Writes:** `final_text`, `lore_citations`, `campaign.banter_queue` (pops when used), `warnings`, `embedded_suggestions` (always `None`)
- **Prose-only:** Narrator generates 5-8 sentences of narrative prose, max 250 words. No suggestion generation — `embedded_suggestions=None` always. Uses shared RAG data (KG context, episodic memories) from Director node to avoid duplicate retrieval.
- **Calls into:**
  - `backend/app/core/agents/narrator.py:NarratorAgent.generate()` (LLM with deterministic fallback)
  - `backend/app/core/agents/narrator.py:_strip_structural_artifacts()` (post-processing: strips option blocks, meta-game sections, character sheet fields)
  - `backend/app/core/agents/narrator.py:_truncate_overlong_prose()` (caps at 250 words, breaks at sentence boundary)
  - `backend/app/rag/lore_retriever.py:retrieve_lore()` (narrator lane filters via `backend/app/rag/retrieval_bundles.py`)

### Narrative Validator (`backend/app/core/nodes/narrative_validator.py`)

- **Node:** `narrative_validator_node(state)`
- **Reads:** `final_text`, `mechanic_result`, `campaign.world_state_json.ledger.constraints`
- **Writes:** `validation_notes`, `warnings` (appends any validation issues)
- **Deterministic:** No DB writes, no LLM. Checks for mechanic consistency and constraint contradictions. Non-blocking (warnings only).

### Commit (`backend/app/core/nodes/commit.py`)

- **Node:** `make_commit_node() -> commit_node(state)`
- **Reads:** `__runtime_conn`, `campaign_id`, `player_id`, `intent`, `user_input`, `mechanic_result`, `spawn_events`, `throttle_events`, `world_sim_events`, `final_text`, `suggested_actions`, `arc_guidance.arc_state`, `episodic_memories`, `known_npcs`, `companion_memories`, `era_summaries`
- **Writes:** **all DB mutations** (single transaction boundary), then returns a refreshed `GameState` dict
- **Persists:**
  - Events: `backend/app/core/event_store.py:append_events()` (including STARSHIP_ACQUIRED, era transition events)
  - Projections: `backend/app/core/projections.py:apply_projection()`
  - Transcript: `backend/app/core/transcript_store.py:write_rendered_turn()`
  - Episodic memories: `backend/app/core/episodic_memory.py` (long-term recall entries)
  - World state JSON: `arc_state`, `known_npcs`, `companion_memories`, `era_summaries`, `faction_memory`, `npc_states`
  - State refresh: `backend/app/core/state_loader.py:build_initial_gamestate()` + `load_turn_history()`

---

## 5) Campaign Setup Flows

### Manual Campaign Creation

```
POST /v2/campaigns
  -> inserts campaigns row (world_state_json seeded with companion state and (optionally) Era Pack factions)
  -> inserts player character row
  -> inserts static NPC cast only when ENABLE_BIBLE_CASTING=0 (legacy path)
  -> appends initial FLAG_SET event + applies projection
```

### Auto Setup (Architect + Biographer)

```
POST /v2/setup/auto
  -> CampaignArchitect.build()  (LLM optional; deterministic fallback)
  -> BiographerAgent.build()    (LLM optional; deterministic fallback)
  -> inserts campaigns + player
  -> inserts static NPC cast only when ENABLE_BIBLE_CASTING=0 (legacy path)
  -> appends initial FLAG_SET event + applies projection
```

When `ENABLE_BIBLE_CASTING=1`, the canonical cast/factions/locations are sourced from Era Packs under `data/static/era_packs/` (loaded via `backend/app/world/era_pack_loader.py`).

---

## 6) Read-Only Endpoints

- `GET /v2/campaigns/{campaign_id}/state` -> `build_initial_gamestate(...)`
- `GET /v2/campaigns/{campaign_id}/world_state` -> `load_campaign(...)`
- `GET /v2/campaigns/{campaign_id}/rumors` -> `get_recent_public_rumors(...)`
- `GET /v2/campaigns/{campaign_id}/transcript` -> `get_rendered_turns(...)`
