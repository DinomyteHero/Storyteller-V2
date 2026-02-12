# V2.20 Living World — Technical Architecture

This document describes the **V2.20 Living World** architecture: the Living Loop pipeline (with SceneFrame and SuggestionRefiner nodes), the Clock-Tick engine, event-sourced V2 schema, RAG pipeline (including parent-child chunking in `ingestion/`), runtime KG context injection, LLM-powered suggestion generation via SuggestionRefiner, prose-only Narrator, DialogueTurn contract, PartyState companion influence system, BanterManager, and agent roles (including how the Architect seeds `active_factions` during setup).

**V2 is canonical.** The pipeline is **Ollama-only** for local single-user use. Cloud providers are deprecated in this codebase.

**Default models:** `mistral-nemo:latest` for Director/Narrator (quality-critical roles), `qwen3:4b` for Architect/Biographer/Casting/KG (lightweight roles), `qwen3:8b` for Mechanic/Ingestion/SuggestionRefiner, `nomic-embed-text` for embedding.

**Key dependencies:** PDF processing uses **pymupdf4llm** for layout-preserving extraction. The world tick is controlled by **`WORLD_TICK_INTERVAL_HOURS`** (default: 4; see `backend/app/time_economy.py`).

---

## 1. The Living Loop

The story engine is a **LangGraph** pipeline. Every turn flows through the "Living Loop": **Router → Mechanic (Time Cost) → Encounter → WorldSim (if threshold met) → CompanionReaction → ArcPlanner → SceneFrame (KOTOR-soul context) → Director (Psych + Arc Guidance + Rumors + Deterministic Suggestions) → Narrator (Prose-Only) → NarrativeValidator → SuggestionRefiner → Commit**.

### 1.1 Flow Diagram

```text
                    ┌─────────┐
                    │  Router │  route + action_class (three-way: META, TALK, ACTION)
                    └────┬────┘
                         │
       ┌─────────────────┼────────────────────┐
       │ META            │ DIALOGUE_           │ ACTION (DIALOGUE_WITH_ACTION,
       │                 │ ONLY                │         PHYSICAL_ACTION)
       ▼                 ▼                     ▼
  ┌─────────┐     ┌────────────┐        ┌──────────┐
  │  (skip  │     │ (skip      │        │ Mechanic │  ← Time cost (minutes) per action
  │  to     │     │  Mechanic) │        └────┬─────┘
  │ Commit) │     └─────┬──────┘             │
  └────┬────┘           │                    │
       │                └────────┬───────────┘
       │                         ▼
       │                  ┌────────────┐
       │                  │ Encounter  │  (present_npcs, spawn_events, active_rumors)
                  └─────┬──────┘
                        │
                        ▼
                  ┌────────────┐
                  │ World Sim  │  ← Single simulation: runs when tick boundary crossed OR travel
                  │ (one run)  │     (WORLD_TICK_INTERVAL_HOURS); FactionEngine (deterministic) OR
                  │            │     Architect (LLM fallback) → rumors + news_feed
                  └─────┬──────┘
                        │
                        ▼
                  ┌─────────────────────┐
                  │ Companion Reaction  │  ← Pure (no DB): affinity/loyalty/banter from tone;
                  │ (deterministic)     │     alignment/faction from mechanic; news banter;
                  │                     │     inter-party tensions; 108 companions, 17 banter styles
                  └─────┬───────────────┘
                        │
                        ▼
                  ┌────────────┐
                  │ Arc Planner│  ← Deterministic: Hero's Journey beats, arc stage transitions,
                  │            │     tension, priority threads, genre triggers, era transitions
                  └─────┬──────┘
                        │
                        ▼
                  ┌────────────┐
                  │ Scene Frame│  ← Pure Python: KOTOR-soul context (topic, subtext, NPC agenda,
                  │ (V2.17)    │     pressure, style tags, scene_hash). Injects party companions.
                  └─────┬──────┘
                        │
                        ▼
                  ┌────────────┐
                  │  Director  │  ← Text-only scene instructions (LLM) + 4 deterministic suggestions
                  │            │     (generate_suggestions: pure Python, no LLM, no JSON schema)
                  └─────┬──────┘
                        │
                        ▼
                  ┌────────────┐
                  │  Narrator  │  ← Prose-only: 5-8 sentences, max 250 words. No suggestions.
                  │            │     embedded_suggestions=None always. Uses shared RAG from Director.
                  └─────┬──────┘
                        │
                        ▼
                  ┌───────────────────┐
                  │ Narrative Validator│  ← Post-narration validation: checks final_text against mechanic & ledger (non-blocking)
                  └─────┬──────────────┘
                        │
                        ▼
                  ┌──────────────────────┐
                  │ Suggestion Refiner   │  ← V2.16: LLM (qwen3:4b) reads prose → 4 scene-aware KOTOR
                  │ (feature-flagged)    │     suggestions. Falls back to Director's deterministic output.
                  └─────┬────────────────┘
                        │
                        ▼
                  ┌────────────┐
       └─────────►│   Commit   │  ← Persist events, episodic memories, known_npcs, companion_memories,
                  └─────┬──────┘     era_summaries, starship events; add time_cost to world_time_minutes
                        │            (META path arrives here directly from Router)
                        ▼
                       END
```text

### 1.2 Step-by-Step

1. **Router**

   Classifies user input into **route** (TALK | MECHANIC | META) and **action_class** (DIALOGUE_ONLY | DIALOGUE_WITH_ACTION | PHYSICAL_ACTION | META). **Three-way routing:** META input (help/save/load/quit) shortcuts directly to Commit. The graph skips the Mechanic node **only** when `route == TALK` **and** `action_class == DIALOGUE_ONLY` **and** `requires_resolution == false` (pure speech/questions/persuasion). Otherwise the turn goes to the Mechanic (e.g. "I say hi and stab him" or "I threaten him and pull my blaster" must be resolved by the Mechanic). A deterministic **action-verb guardrail** overrides to non-dialogue-only if the input contains high-signal verbs (stab, shoot, steal, punch, grab, run, sneak, attack, kill, pull, draw, etc.). Router output schema: `intent_text`, `route`, `action_class`, optional `confidence`, optional `rationale_short`. For dialogue-only, the Router pre-fills a minimal `mechanic_result` (time from `DIALOGUE_ONLY_MINUTES`, no dice, no state changes).

2. **Mechanic (Time Cost)**

   For `ACTION`, the Mechanic resolves dice, DCs, events (DAMAGE, MOVE, ITEM_GET, etc.) and **always** sets `time_cost_minutes` from the centralized time economy (`backend/app/time_economy.py`). This drives the world clock. Dynamic difficulty via `_ARC_DC_MODIFIER` (SETUP=-2, CLIMAX=+3). Environmental modifiers from location tags, inventory, and time-of-day.

3. **Encounter**

   Resolves who is present at the current location; may spawn NPCs via CastingAgent. Attaches `present_npcs` and `active_rumors` (last 3 `is_public_rumor` events) for Director/Narrator.

4. **World Sim (single pipeline)**

   There is **one** simulation system per turn. WorldSim runs **before** Commit and writes only to state; Commit persists factions and rumor events. **Triggers** (any one runs the sim once this turn):
   - **Tick boundary crossed:** `t0 = state.campaign.world_time_minutes`, `dt = mechanic_result.time_cost_minutes`, `t1 = t0 + dt`. Run if `floor(t0 / tick) != floor(t1 / tick)` (config: `WORLD_TICK_INTERVAL_HOURS`, default 4 → tick = 240 minutes).
   - **Travel:** Player moved (mechanic_result has MOVE event or `action_type == TRAVEL`).
   - (Future: major events can be added as additional triggers; still one run per turn.)
   - **Computation:** Store `t1` in `state.pending_world_time_minutes`. When any trigger fires: **FactionEngine** (`backend/app/world/faction_engine.py`) runs `simulate_faction_tick()` (deterministic: zero LLM, seeded RNG) for faction moves and rumor generation. Falls back to **Campaign Architect** `simulate_off_screen(...)` (LLM with deterministic fallback) when faction engine is not applicable. Rumors are converted into **NewsItems** (headline, source_tag, urgency, related_factions) and merged into `campaign.news_feed` (bounded, e.g. latest 20). Commit later persists `active_factions`, `news_feed`, `faction_memory`, `npc_states`, and appends RUMOR events. Director and Narrator see sim results the same turn.

5. **Companion Reaction (pure, no DB)**

   After World Sim, **CompanionReactionNode** runs. It is **deterministic** (no LLM, no DB writes). The system supports **108 companions** with full metadata (gender, species, voice_tags, motivation, speech_quirk) and **17 banter styles**. It: (a) applies **alignment_delta** and **faction_reputation_delta** from `mechanic_result` to `campaign.alignment` and `campaign.faction_reputation`; (b) computes **companion affinity deltas** from `mechanic_result.tone_tag` and each companion's traits (idealist/pragmatic, merciful/ruthless, etc.)--if `mechanic_result.companion_affinity_delta` is present for a companion, that overrides; (c) nudges **loyalty_progress** when affinity moves positive; (d) optionally enqueues **banter** (rate-limited) and **news banter** when a NewsItem touches a faction a companion cares about; (e) computes **inter-party tensions** when companions have opposing reactions; (f) triggers companion-initiated events (COMPANION_REQUEST at TRUSTED, COMPANION_QUEST at LOYAL, COMPANION_CONFRONTATION on sharp drops); (g) **V2.20: PartyState influence** — `compute_influence_from_response()` applies per-companion influence deltas based on intent, meaning_tag, and tone matching against era-pack triggers. Influence is stored in `PartyState` (`backend/app/core/party_state.py`) with trust/respect/fear axes. All updates are in-memory; Commit persists them in `world_state_json["party_state"]` (with backward-compatible legacy fields).

6. **Arc Planner (deterministic)**

   Tracks **Hero's Journey beats** with content-aware stage transitions (SETUP → RISING → CLIMAX → RESOLUTION). Outputs `arc_guidance` containing: arc stage, tension level, priority threads, pacing hints, suggested action weights, active themes, **hero_beat**, **archetype_hints**, **theme_guidance**, **era_transition_pending**. Integrates with **genre triggers** (`backend/app/core/genre_triggers.py`) and **era transitions** (`backend/app/core/era_transition.py`).

6b. **SceneFrame (V2.17, pure Python, no LLM, no DB)**
   Inserted between ArcPlanner and Director. Establishes the immutable scene context for downstream nodes: location, present NPCs (with voice profiles from era packs and companion data), immediate situation, allowed scene type, scene hash (SHA256 for deduplication), KOTOR-soul topic anchoring (primary/secondary), subtext, NPC agenda, pressure (alert/heat from world state), and style tags. Active companions from **PartyState** are auto-injected into `present_npcs`. The **BanterManager** (`backend/app/core/banter_manager.py`) may inject a banter micro-scene if safety guards pass (no banter during combat, stealth, or high-pressure states like Watchful/Lockdown/Wanted; per-companion and global cooldowns enforced). Output is stored as `state["scene_frame"]` and used by Director, Narrator, SuggestionRefiner, and Commit (to assemble `DialogueTurn`).

7. **Clock Update (in Commit)**

   Commit sets **world_time_minutes** to the post-action time (no double increment):
   - If `state.pending_world_time_minutes` is set: `UPDATE campaigns SET world_time_minutes = ? WHERE id = ?` with that value (`t1`).
   - Otherwise (fallback): `world_time_minutes = COALESCE(world_time_minutes, 0) + time_cost_minutes`.

8. **Director (Text-Only Instructions + Deterministic Suggestions)**

   Uses **4-lane style RAG** (Base SW + Era + Genre + Archetype), **player psych_profile** (e.g. `stress_level`, `active_trauma`), **gender/pronoun context** (via `pronouns.py`), and **arc_guidance** (arc stage, tension, pacing hints, priority threads, hero_beat) for tone and scene direction. Incorporates **latest 3 NewsItems** from `campaign.news_feed`; if any has urgency HIGH, the prompt nudges at least one suggested action to respond to it. Falls back to **new_rumors** / **active_rumors** when news_feed is empty. The **LLM generates text-only `director_instructions`** (no JSON schema, no retries for suggestions). **Suggestions are 100% deterministic:** `generate_suggestions(state, mechanic_result)` produces exactly **4 suggested_actions** using pure Python -- mechanic results (post-combat success/failure, post-stealth branches), present NPCs, arc stage, tone diversity (PARAGON/INVESTIGATE/RENEGADE), and exploration/high-stress options. Each action has **category** (SOCIAL | EXPLORE | COMMIT), **risk_level** (SAFE | RISKY | DANGEROUS), **tone_tag** (PARAGON | INVESTIGATE | RENEGADE | NEUTRAL). Server validates via `lint_actions()`. Director also prepares **shared_kg_character_context** and **shared_episodic_memories** to pass to Narrator (avoiding duplicate RAG retrieval).

9. **Narrator (Prose-Only)**

   Generates **prose-only** narrative from GameState: mechanic result (facts), director instructions, **lore** RAG, present_npcs, active_rumors, **psych_profile** for tone, **gender/pronoun** context, and **shared RAG data** from Director (KG character context, episodic memories). Outputs `final_text` (returned to the client as **`narrated_text`** in the turn response) and `lore_citations`. **No suggestion generation** -- `embedded_suggestions=None` always. Prose is **5-8 sentences, max 250 words**; `_truncate_overlong_prose()` caps at sentence boundary. Post-processing via `_strip_structural_artifacts()` catches option blocks, meta-game sections, character sheet fields, and meta-narrator patterns. High stress can make prose more fragmented/sensory.

10. **Narrative Validator (deterministic, non-blocking)**
    **NarrativeValidatorNode** runs after Narrator. It is **deterministic** (no LLM, no DB writes) and performs post-narration validation:
    - **Mechanic consistency**: checks that `final_text` doesn't use success language when `mechanic_result.success=False` (or vice versa)
    - **Constraint contradictions**: checks for negation keywords near constraint keywords from the ledger

    Validation warnings are added to `state.warnings` and logged, but the narration is **never blocked** -- this is an observability/quality check, not a gate.

11. **Suggestion Refiner (V2.16+, feature-flagged)**
    **SuggestionRefinerNode** (`backend/app/core/nodes/suggestion_refiner.py`) runs after the Narrative Validator. It is the **sole source of suggestions** in the pipeline. It uses `qwen3:8b` to read the Narrator's `final_text` prose and scene context (location, present NPCs, mechanic outcome), then generates **4 scene-aware KOTOR-style suggestions** that respond to what actually happened in the prose. Feature-flagged via `ENABLE_SUGGESTION_REFINER` (default: `True`). When disabled or on any failure, minimal emergency fallback responses are used. `generate_suggestions()` in `director_validation.py` still exists but is **not called** from the pipeline. 3-layer fallback: AgentLLM JSON retry -> node-level validation (tone/label checks) -> emergency fallback. Output passes through `classify_suggestion()`, `ensure_tone_diversity()`, and `lint_actions()` for consistency.

12. **Commit**
    Writes `turn_events` (including world-sim RUMOR events with `is_public_rumor`, STARSHIP_ACQUIRED events, era transition events), sets `campaigns.world_time_minutes = pending_world_time_minutes` (t1), runs projections, persists `arc_state` in `world_state_json`, persists **episodic_memories**, **known_npcs**, **companion_memories**, **era_summaries**, **faction_memory**, **npc_states**, **PartyState** (`world_state_json["party_state"]`), and writes `rendered_turns`. Assembles the **DialogueTurn** (V2.17) from `scene_frame` + `npc_utterance` + `player_responses` and stores it in the returned GameState. **No** second world sim: travel-triggered updates are handled by the same World Sim node (tick or travel → one simulation run per turn).

---

## 2. Data Models

### 2.1 Campaign

Persisted in `campaigns` table. Relevant columns:

| Column               | Type    | Description |
|----------------------|---------|-------------|
| id                   | TEXT    | Primary key |
| title                | TEXT    | Campaign title |
| time_period          | TEXT    | Era (e.g. LOTF) |
| world_state_json     | TEXT    | JSON; includes `active_factions`, `faction_memory`, `npc_states`, `known_npcs`, `companion_memories`, `era_summaries`, `opening_beats`, `act_outline`. Default `'{}'`. |
| **world_time_minutes** | INTEGER | In-world elapsed time in minutes. Default `0`. Incremented each turn by `mechanic_result.time_cost_minutes`. Drives clock-tick for World Sim. |
| created_at           | TEXT    | ISO timestamp (migration 0006) |
| updated_at           | TEXT    | ISO timestamp (migration 0007) |

**GameState:** `state.campaign` is a dict built from this row; it includes `world_time_minutes` for the World Sim node and for any UI that shows "world time."

### 2.2 Character

Persisted in `characters` table. Relevant columns:

| Column        | Type    | Description |
|---------------|---------|-------------|
| id            | TEXT    | Primary key |
| campaign_id   | TEXT    | FK → campaigns(id) |
| name          | TEXT    | |
| role          | TEXT    | e.g. Player, Villain, Rival, Merchant |
| location_id   | TEXT    | |
| stats_json    | TEXT    | Default `'{}'` |
| hp_current    | INTEGER | Default 0 |
| relationship_score | INTEGER | |
| secret_agenda | TEXT    | |
| credits       | INTEGER | Default 0 |
| gender        | TEXT    | male/female (migration 0015) |
| planet        | TEXT    | Starting planet (migration 0008) |
| background    | TEXT    | Character background (migration 0009) |
| **psych_profile** | TEXT  | JSON. Default `'{}'`. Fields: `current_mood`, `stress_level`, `active_trauma`. Used by Director and Narrator for tone and pacing. |
| created_at    | TEXT    | ISO timestamp (migration 0010) |
| updated_at    | TEXT    | ISO timestamp (migration 0011) |

**In-memory:** `CharacterSheet` in `backend/app/models/state.py` includes `psych_profile: dict`, `gender: str`; the state loader fills it from the DB (`load_player_by_id` → `build_initial_gamestate`). Config defaults: `config.PSYCH_PROFILE_DEFAULTS` (`current_mood`, `stress_level`, `active_trauma`). Gender/pronoun injection via `backend/app/core/pronouns.py:pronoun_block()`.

### 2.3 TurnEvent

Persisted in `turn_events` table. Relevant columns:

| Column             | Type    | Description |
|--------------------|---------|-------------|
| id                 | INTEGER | AUTOINCREMENT primary key |
| campaign_id        | TEXT    | FK → campaigns(id) |
| turn_number        | INTEGER | |
| event_type         | TEXT    | e.g. TURN, MOVE, DAMAGE, ITEM_GET, RUMOR, DIALOGUE, STARSHIP_ACQUIRED, STORY_NOTE |
| payload_json       | TEXT    | JSON. Default `'{}'`. |
| is_hidden          | INTEGER | 0/1. Default 0. |
| **is_public_rumor**| INTEGER | 0/1. Default 0. Set to 1 for RUMOR events from the World Sim (clock-tick). These are the "public rumors" returned by `get_recent_public_rumors` and passed to Director/Narrator. |
| timestamp          | TEXT    | ISO; default `datetime('now')`. |
| created_at         | TEXT    | ISO timestamp (migration 0012) |

`event_store.append_events` writes `is_public_rumor` from `Event.is_public_rumor`.

### 2.4 Additional Tables (Migrations 0005-0018)

| Table / Migration | Description |
|-------------------|-------------|
| `kg_entities`, `kg_triples`, `kg_summaries`, `kg_extraction_checkpoints` (0005) | Knowledge graph storage for entity-relation extraction |
| `cyoa_answers` (0013) | CYOA answer tracking |
| `episodic_memories` (0014) | Long-term episodic memory for cross-session recall |
| `suggestion_cache` (0016) | Deterministic suggestion cache (location+arc_stage key, one-turn TTL) |
| `starships` (0017) | Starship data (earned in-story, not starting equipment) |
| `player_profiles` (0018) | Player preference/profile storage |

---

## 3. Agent Roles

### 3.1 Architect: Seeding `active_factions` During Setup

The **Campaign Architect** (`core/agents/architect.py`) is used in two places:

- **Setup (one-shot):** `POST /v2/setup/auto` calls `CampaignArchitect.build(time_period, themes)`. The Architect returns a skeleton with:
  - `title`, `time_period`, `locations`, `npc_cast` (12 NPCs), and **`active_factions`** (3-5 factions with conflicting goals and specific starting locations).
  - Each faction has: `name`, `location`, `current_goal`, `resources` (1-10), `is_hostile`.
  - **Persistence rule:** when `ENABLE_BIBLE_CASTING=1` (default), the backend derives `active_factions` deterministically from the Era Pack in `data/static/era_packs/` and persists those instead of the LLM skeleton's factions. When `ENABLE_BIBLE_CASTING=0`, the backend persists the skeleton's `active_factions` (or `skeleton.world_state_json.active_factions`).
  - The backend persists `world_state_json = { "active_factions": [...], ...companion_state }` in `campaigns.world_state_json`. `active_factions` are the canonical living-world faction state used by WorldSim and exposed to the UI (quest log / briefing).

- **Clock-tick (World Sim node):** When `world_time_minutes` hits a tick boundary, the World Sim node loads `world_state_json.active_factions` from the DB and runs the **FactionEngine** (`backend/app/world/faction_engine.py:simulate_faction_tick()`) for deterministic faction simulation (zero LLM, seeded RNG). Falls back to `architect.simulate_off_screen(campaign_id, world_state_context, active_factions)` when needed, and persists `updated_factions` back to `world_state_json`.

### 3.2 Other Agents (summary)

| Agent     | Responsibility |
|----------|----------------|
| **Router** | Classify user input into route (TALK | MECHANIC) and action_class (DIALOGUE_ONLY | DIALOGUE_WITH_ACTION | PHYSICAL_ACTION | META). Only DIALOGUE_ONLY skips Mechanic; action-verb guardrail prevents smuggling violence/theft into dialogue. |
| **Mechanic** | Authoritative for physics: action type, dice, DCs, events, **time_cost_minutes**. Dynamic difficulty via `_ARC_DC_MODIFIER`. Environmental modifiers. Narrator only describes Mechanic results. **Note:** `companion_affinity_delta` works via trait scoring; `alignment_delta` and `faction_reputation_delta` are defined in `MechanicOutput` but currently default to empty dicts -- the companion reaction system computes its own deltas from `tone_tag` and traits instead. |
| **Director** | Text-only scene instructions via LLM; uses **4-lane style RAG** (Base SW + Era + Genre + Archetype), **psych_profile**, **gender/pronoun context**, and recent rumors. **Suggestions are 100% deterministic** via `generate_suggestions()`: exactly **4 suggested_actions** using pure Python (mechanic results, NPCs, arc stage, tone). Each action has **category** (SOCIAL | EXPLORE | COMMIT), **risk_level** (SAFE | RISKY | DANGEROUS), **tone_tag** (PARAGON | INVESTIGATE | RENEGADE | NEUTRAL). Server validates via `lint_actions()`. |
| **Narrator** | **Prose-only**: 5-8 sentences, max 250 words. No suggestion generation (`embedded_suggestions=None`). Uses mechanic result, director instructions, lore RAG, gender/pronoun context, shared KG + episodic memory from Director; outputs final_text (returned as **narrated_text** in the turn API) and lore_citations. Post-processing strips structural artifacts and truncates overlong prose. |
| **EncounterManager** | Resolve `present_npcs`. If none exist in the DB, it can introduce NPCs deterministically from Era Packs (`ENABLE_BIBLE_CASTING=1`) and/or via a deterministic procedural generator (`ENABLE_PROCEDURAL_NPCS=1`). NPC personality profiles via `personality_profile.py`. |
| **CastingAgent (legacy)** | LLM-based NPC spawning; only used when both Bible casting and procedural NPCs are disabled (`ENABLE_BIBLE_CASTING=0` and `ENABLE_PROCEDURAL_NPCS=0`). |
| **Biographer** | Used at setup to build the player character from a concept. |
| **FactionEngine** | Deterministic faction simulation (`backend/app/world/faction_engine.py`). Zero LLM calls, seeded RNG. Runs during World Sim tick for faction moves and rumor generation. |
| **ArcPlanner** | Deterministic Hero's Journey beat tracking. Outputs arc stage, hero_beat, archetype_hints, theme_guidance, genre triggers, era_transition_pending. |

---

## 4. RAG Pipeline: Parent-Child Chunking in `ingestion/`

Lore ingestion lives in **`ingestion/`**. It uses an **Enriched RAG** process: **parent-child chunking**, layout-preserving PDF extraction (via **pymupdf4llm**), and context prefixes for retrieval.

### 4.1 Where It Lives

- **Lore ingestion:** `ingestion/ingest_lore.py`

  CLI: `python -m ingestion.ingest_lore --input ./data/lore [--time-period LOTF] [--planet Tatooine] [--faction Empire]`
- **Chunking helpers:** `ingestion/chunking.py` (token counting, `chunk_text_by_tokens`, overlap).

### 4.2 Parent-Child Chunking Strategy

- **Parents:** Documents are first split into **parent** chunks of ~**1024 tokens** (`PARENT_TOKENS = 1024` in `ingest_lore.py`), with 10% overlap, using `chunk_text_by_tokens(..., target_tokens=PARENT_TOKENS, overlap_percent=0.1)`.
- **Children:** Each parent is sub-chunked into **child** chunks of ~**256 tokens** (`CHILD_TOKENS = 256`, `CHILD_OVERLAP = 0.1`).
- **Hierarchy:** Each child has a `parent_id` (UUID of the parent). Stored chunks have a `level` field: `"parent"` or `"child"`.
- **Section label:** Taken from the parent's first markdown header (`#`, `##`, `###`) or first line, truncated to 120 chars (`_parent_section_label`). Used in the child's stored text prefix.

### 4.3 PDF Layout Preservation

PDFs are converted to **Markdown** with layout preservation (headers, tables) using **pymupdf4llm**: in `ingestion/ingest_lore.py`, `_read_pdf(path)` calls `pymupdf4llm.to_markdown(str(path))`. Plain TXT and EPUB are also supported; EPUB uses the existing epub reader (title, chapters).

### 4.4 Context Prefix (Enriched Child Text)

Child text stored in the vector DB is **prefixed** so retrieval carries source and section context:

```text
[Source: {filename}, Section: {parent_header}] {child_text}
```text

This is built in `_hierarchical_chunks` and stored in the `text` field of child chunks.

### 4.5 Metadata and Storage

- **Metadata** on each chunk: `source`, `chapter`, `time_period`, `planet`, `faction` (from CLI and/or `_metadata_heuristic`).
- **Storage:** LanceDB; schema includes `id`, `text`, `level`, `parent_id`, `source`, `chapter`, `time_period`, `planet`, `faction`, `vector`. Retrieval in `backend/app/rag/lore_retriever.py` supports filters such as `time_period`, `planet`, `faction`.

### 4.6 4-Lane Style Retrieval (V2.8+)

Style retrieval uses a **4-lane** architecture in `backend/app/rag/style_retriever.py:retrieve_style_layered()`:

- **Lane 0 (Base SW):** Always-on Star Wars prose foundation from `data/style/base/star_wars_base_style.md`
- **Lane 1 (Era):** Era-specific style guidance (e.g., NJO maps to NEW_JEDI_ORDER)
- **Lane 2 (Genre):** Genre-specific tone and pacing
- **Lane 3 (Archetype):** Character archetype style (e.g., hero_journey_style)

Mappings defined in `backend/app/rag/style_mappings.py` (BASE_STYLE_MAP, ARCHETYPE_STYLE_MAP).

---

## 5. Implementation Notes

- **Deterministic vs LLM-driven:** The following are **deterministic** (no LLM, no DB writes in the node): **Router** (route, action_class, requires_resolution); **Mechanic** (dice, DCs, events, time cost, dynamic difficulty, environmental modifiers); **CompanionReactionNode** (affinity deltas from tone_tag + traits, alignment/faction application from mechanic_result, banter and news banter rate-limited, inter-party tensions, companion-initiated events); **ArcPlannerNode** (Hero's Journey beat tracking, arc stage transitions, tension levels, priority threads, genre triggers, era transitions); **NarrativeValidatorNode** (mechanic consistency checks, constraint validation); **FactionEngine** (zero LLM, seeded RNG faction simulation); **generate_suggestions()** (pure Python suggestion generation from mechanic results, NPCs, arc stage, tone); **news feed shaping** (rumor text → NewsItem headline/source/urgency/related_factions via keyword rules in `backend/app/models/news.py`). The following use **LLM** (Ollama): Architect (world sim fallback path), Director (text-only scene instructions), Narrator (prose-only final_text), SuggestionRefiner (V2.16: scene-aware suggestion generation from prose), CastingAgent (NPC spawn), Biographer (character sheet). The **Mechanic** can emit explicit `companion_affinity_delta` and `alignment_delta`; when present, CompanionReactionNode uses them; otherwise it **computes** affinity from tone_tag and traits.

- **Suggestion System (V2.16+):** The **SuggestionRefiner** (`backend/app/core/nodes/suggestion_refiner.py`, feature-flagged via `ENABLE_SUGGESTION_REFINER`) is the sole source of suggestions. It uses `qwen3:8b` to generate **4** scene-aware KOTOR-style suggestions that respond to the Narrator's prose. On LLM failure, minimal emergency fallback responses are used. `generate_suggestions()` in `director_validation.py` still exists (for tone diversity utilities, classification, etc.) but is **not called** from the pipeline.

- **Narrator (V2.15):** Prose-only. Writes 5-8 sentences, max 250 words. `_truncate_overlong_prose()` caps at sentence boundary. `_strip_structural_artifacts()` removes option blocks, meta-game sections, character sheet fields, meta-narrator patterns. `embedded_suggestions=None` always -- Narrator no longer generates suggestions.

- **Gender/Pronoun System (V2.8):** `backend/app/core/pronouns.py:pronoun_block()` injects he/him/his or she/her/her blocks into Director and Narrator prompts. Gender stored in characters table (migration 0015).

- **Episodic Memory:** `backend/app/core/episodic_memory.py` stores long-term memories in the `episodic_memories` table (migration 0014). Director retrieves shared episodic memories and passes them to Narrator to avoid duplicate queries.

- **Starship Acquisition (V2.10):** No starting ships; earned in-story via quest/purchase/salvage/faction/theft. STARSHIP_ACQUIRED event handler in `backend/app/core/projections.py`. GameState.player_starship field. Director/Narrator/Mechanic receive ship/no-ship context.

- **Personality Profiles:** `backend/app/core/personality_profile.py` generates NPC personality blocks for richer characterization in Director and Narrator prompts.

- **Graph:** `backend/app/core/graph.py` -- `build_graph` adds: router, mechanic, encounter, world_sim, **companion_reaction**, **arc_planner**, director, narrator, **narrative_validator**, **suggestion_refiner**, commit. Conditional edge from router: skip mechanic only when `route == TALK` and `action_class == DIALOGUE_ONLY` and `requires_resolution == false`; else → mechanic. Edges: world_sim → companion_reaction → arc_planner → director → narrator → narrative_validator → suggestion_refiner → commit. **Router:** `backend/app/core/router.py` -- heuristic classification + action-verb and persuasion guardrails; schema in `backend/app/models/state.py` (`RouterOutput`, route, action_class, requires_resolution). **Companion reactions:** `backend/app/core/companion_reactions.py` -- compute_companion_reactions, update_party_state, apply_alignment_and_faction, maybe_enqueue_banter, maybe_enqueue_news_banter, compute_inter_party_tensions. **Arc Planner:** `backend/app/core/nodes/arc_planner.py` -- deterministic Hero's Journey beat tracking, arc stage transitions, tension levels, priority threads, genre triggers, era transitions. **Narrative Validator:** `backend/app/core/nodes/narrative_validator.py` -- post-narration validation (mechanic consistency, constraint checks). **Suggestion Refiner:** `backend/app/core/nodes/suggestion_refiner.py` -- V2.16 scene-aware suggestion generation via `qwen3:8b` LLM; feature-flagged via `ENABLE_SUGGESTION_REFINER`.
- **World Sim (single pipeline):** One simulation per turn. Triggers: tick boundary crossed (`WORLD_TICK_INTERVAL_HOURS`) or travel (MOVE / TRAVEL). World Sim node calls FactionEngine (deterministic) or Campaign Architect (LLM fallback) once; Commit persists factions, faction_memory, npc_states, and rumor events and does **not** call any separate travel-time simulator.
- **Schema:** `backend/app/db/schema.sql` plus migrations `0001_init.sql` through `0018_player_profiles.sql`. Key migrations: `0004_living_world.sql` (world_time_minutes, psych_profile, is_public_rumor), `0005_knowledge_graph.sql` (kg_entities, kg_triples, kg_summaries), `0014_episodic_memories.sql`, `0015_add_gender.sql`, `0016_suggestion_cache.sql`, `0017_starships.sql`, `0018_player_profiles.sql`.
- **Events:** `backend/app/models/events.py` defines `Event` with `is_public_rumor`; `event_store.py` persists it and provides `get_recent_public_rumors`.

---

## 6. Frontend Architecture (V2.20)

The SvelteKit frontend provides a KOTOR-inspired game interface: a single-page narrative viewport with a HUD bar, NPC speech bubbles, prose rendering, a 4-choice dialogue wheel, and a slide-out info drawer for character/companion/faction/quest data.

### 6.1 Tech Stack

- **SvelteKit 2** with **Svelte 5** runes (`$state`, `$derived`, `$derived.by`, `$effect`, `$props`)
- **Vite 6** build tool
- **TypeScript** throughout (strict types mirroring backend Pydantic models)
- Components use Svelte 5 `interface Props` + `$props()` pattern (no legacy `export let`)
- No external component library; all UI is custom with CSS custom properties

### 6.2 Component Hierarchy

```text
+page.svelte (route: /play)
  |
  +-- <header> HUD Bar (inline)
  |     |-- hamburger toggle (drawer)
  |     |-- LOC / DAY / TIME pills
  |     |-- HP / CR / Stress pills
  |     |-- Heat / Alert pills (from SceneFrame.pressure)
  |     +-- Quit button
  |
  +-- <main> Gameplay Main
  |     |-- "Previously..." accordion (collapsed past turns)
  |     |-- Mission Briefing card (opening scene only)
  |     |-- Narrative container
  |     |     |-- Turn header + scene subtitle
  |     |     |-- SceneContext          (topic tag, scene type, pressure pills)
  |     |     |-- NpcSpeech             (NPC name + quoted dialogue)
  |     |     +-- Narrative prose       (typewriter or instant render)
  |     |
  |     +-- DialogueWheel              (4 tone-sorted KOTOR-style choices)
  |
  +-- <aside> Info Drawer (slide-in panel)
        |-- Tab bar: Character | Companions | Factions | Inventory | Quests | Comms | Journal
        |-- Character tab       (name, stats, psych_profile)
        |-- Companions tab      (affinity hearts, loyalty badge, influence/trust/respect/fear meters)
        |-- Factions tab        (reputation bars with tier badges: HOSTILE..ALLIED)
        |-- Inventory tab       (item list with quantities)
        |-- Quests tab          (quest log with status badges and stage progress)
        |-- Comms tab           (news feed: headline, source, urgency, related factions)
        +-- Journal tab         (turn transcript with time deltas)
```text

Extracted components live in `frontend/src/lib/components/`:

| Component | Path | Responsibility |
|-----------|------|----------------|
| DialogueWheel | `choices/DialogueWheel.svelte` | Renders 4 KOTOR-style choices sorted by tone (PARAGON, INVESTIGATE, RENEGADE, NEUTRAL). Accepts both `PlayerResponse[]` (primary) and `ActionSuggestion[]` (fallback). Tone-filled backgrounds, hover-reveal metadata (risk, consequence hint, companion deltas). |
| NpcSpeech | `narrative/NpcSpeech.svelte` | Renders NPC utterance above prose. Shows speaker name + quoted text. Hidden when `speaker_id === "narrator"` or text is empty. |
| SceneContext | `narrative/SceneContext.svelte` | Scene awareness bar: topic tag, scene type icon, pressure pills (alert, heat). Only renders when SceneFrame data is available. |

### 6.3 Store Architecture

Stores live in `frontend/src/lib/stores/`. All use Svelte's `writable` / `derived` primitives.

```text
API Response (TurnResponse)
  |
  v
lastTurnResponse (writable)  <-- set after runTurn() or streamTurn() completes
  |
  +---> suggestedActions (derived)     -- $resp.suggested_actions (legacy flat list)
  +---> playerSheet (derived)          -- $resp.player_sheet
  +---> inventory (derived)            -- $resp.inventory
  +---> partyStatus (derived)          -- $resp.party_status
  +---> factionReputation (derived)    -- $resp.faction_reputation
  +---> newsFeed (derived)             -- $resp.news_feed
  +---> warnings (derived)            -- $resp.warnings
  +---> questLog (derived)             -- $resp.quest_log
  |
  +---> dialogueTurn (derived)         -- $resp.dialogue_turn (V2.17+)
          |
          +---> sceneFrame (derived)       -- $dt.scene_frame
          +---> npcUtterance (derived)     -- $dt.npc_utterance
          +---> playerResponses (derived)  -- $dt.player_responses (primary choices)
```text

| Store file | Purpose | Persistence |
|------------|---------|-------------|
| `game.ts` | Campaign session: IDs, lastTurnResponse, transcript, all derived stores | Memory only |
| `streaming.ts` | SSE streaming state: isStreaming, streamedText, streamError, showCursor | Memory only |
| `ui.ts` | UI preferences: theme, enableStreaming, enableTypewriter, showDebug, drawer state | localStorage |
| `creation.ts` | Character creation wizard state: step, name, gender, era, background, answers | Memory only |
| `campaigns.ts` | Saved campaign registry for the load/resume flow | localStorage |

### 6.4 DialogueTurn Integration

The frontend supports two data paths for player choices, with automatic fallback:

**Primary path (V2.17+ DialogueTurn):**

`TurnResponse.dialogue_turn.player_responses` (array of `PlayerResponse`) provides KOTOR-style choices with `display_text`, `tone_tag`, `risk_level`, `consequence_hint`, `meaning_tag`, and structured `action` (type, intent, target, tone).

**Fallback path (legacy):**

`TurnResponse.suggested_actions` (array of `ActionSuggestion`) provides flat suggestions with `label`, `intent_text`, `tone_tag`, `risk_level`, `consequence_hint`, `companion_reactions`.

The `DialogueWheel` component unifies both into a `UnifiedChoice` interface and renders identically. Selection logic in `+page.svelte` checks `playerResponses.length > 0` before falling back to `suggestedActions`. Keyboard shortcuts (1-4) work with both paths.

TypeScript interfaces in `frontend/src/lib/api/types.ts` mirror backend Pydantic models:

| TypeScript interface | Backend Pydantic model |
|---------------------|----------------------|
| `TurnResponse` | `TurnResponse` (v2_campaigns.py) |
| `DialogueTurn` | `DialogueTurn` (dialogue_turn.py) |
| `SceneFrame` | `SceneFrameSnapshot` (dialogue_turn.py) |
| `NPCUtterance` | `NPCUtterance` (dialogue_turn.py) |
| `PlayerResponse` | `PlayerResponseOption` (dialogue_turn.py) |
| `ActionSuggestion` | `SuggestedAction` (director_validation.py) |

### 6.5 Theme System

Themes are defined in `frontend/src/lib/themes/tokens.ts` as `ThemeTokens` objects. Each theme maps to a set of CSS custom property values. The active theme is injected on `<body>` via `themeToCssVars()`.

**Available themes:** Clean Dark (default), Rebel Amber, Alliance Blue, Holocron Archive.

**Tone color tokens** (consistent across all themes):

| Token | Color | Usage |
|-------|-------|-------|
| `--tone-paragon` | Blue | Light-side / helpful choices |
| `--tone-investigate` | Amber/Gold | Probing / cautious choices |
| `--tone-renegade` | Red | Aggressive / dark-side choices |
| `--tone-neutral` | Gray | Neutral / practical choices |

These tone colors are the dominant visual in DialogueWheel (filled card backgrounds), HUD stress/heat/alert pills, faction reputation tiers, companion loyalty badges, and quest status badges. The KOTOR aesthetic is achieved through dark panel backgrounds (`--bg-panel`), subtle glow effects (`--accent-glow`), optional scanline overlays (`--hud-scanline-opacity`), and monospace data displays (JetBrains Mono for numeric values).

Theme selection is persisted in localStorage via the `ui` store and can be changed from the home page settings.

### 6.6 Key Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Home | Campaign list (saved campaigns from localStorage), New Campaign / Load Campaign buttons, settings panel (theme selection, streaming/typewriter toggles, debug mode) |
| `/create` | Character Creation | Multi-step wizard: era selection (with companion preview), background selection (era-pack CYOA questions with conditional branching), name/gender entry, campaign setup via `POST /v2/setup/auto` |
| `/play` | Game Loop | Main gameplay: HUD bar, narrative viewport (typewriter or SSE streaming), NPC speech, scene context, DialogueWheel choices, info drawer (7 tabs). Keyboard shortcuts: 1-4 (choices), Space/Enter (skip typewriter), i (toggle drawer), j (journal), Escape (close drawer) |

**Data flow on `/play`:**

```text
User clicks choice (or presses 1-4)
  |
  v
handleChoiceInput(userInput, label)
  |
  +-- SSE mode: streamTurn() --> token events --> streamedText store --> prose render
  |                           --> done event --> lastTurnResponse store --> all derived stores
  |
  +-- Batch mode: runTurn() --> lastTurnResponse store --> all derived stores
  |
  v
Typewriter effect (if enabled) --> choicesReady flag --> DialogueWheel renders
```text

**Accessibility:** ARIA labels on all interactive elements, `aria-live` regions for dynamic content, screen reader announcements via `announce()` utility, focus trapping in the info drawer, keyboard navigation for all choices.
