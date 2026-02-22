# 09 — Call Graph & Architecture Map

This document is a **"where does this code run from?"** map:

- The main entry points (web UI, API, CLI, ingestion)
- What calls what during a live turn
- Which modules are invoked synchronously vs. lazily vs. never during normal operation

---

## Primary Entry Points

### 1. Player UI → API Turn Request

```
Browser/SvelteKit UI (frontend/)
  └─ POST /v2/campaigns/{campaign_id}/turn?player_id={player_id}
       └─ backend/app/api/v2_campaigns.py:turn_endpoint()
            ├─ backend/app/core/state_loader.py:build_initial_gamestate()
            │    ├─ backend/app/core/state_reducer.py:apply_projection()
            │    │    └─ SQLite turn_events → normalized tables
            │    └─ SQLite campaigns, characters → GameState fields
            └─ backend/app/core/graph.py:run_turn(conn, state)
                 ├─ [catch AgentFailureError → return structured error GameState]
                 └─ _get_compiled_graph().invoke(initial_state)
                      └─ [LangGraph StateGraph pipeline — see Turn Pipeline below]
```

### 2. `POST /v2/setup/auto` (Campaign Auto-Setup)

```
POST /v2/setup/auto
  └─ backend/app/api/campaign_setup.py:auto_setup()
       ├─ backend/app/core/agents/architect.py:CampaignArchitect.build_campaign_blueprint()
       ├─ backend/app/core/agents/biographer.py:BiographerAgent.generate_background()
       ├─ (optional) backend/app/core/agents/casting.py:CastingAgent.cast_npcs()
       └─ SQLite INSERT campaigns + characters
```

### 3. CLI Dev Launcher

```
python run_app.py --dev
  ├─ scripts/preflight.py (Ollama check, data dirs, DB migrations)
  ├─ uvicorn backend.main:app (FastAPI backend)
  └─ npm run dev (SvelteKit UI)
```

### 4. Ingestion Pipeline

```
python -m ingestion.ingest_lore --input ./data/lore/...
  └─ ingestion/ingest_lore.py
       ├─ ingestion/chunking.py (parent/child chunking)
       ├─ ingestion/embedding.py (sentence-transformers embeddings)
       ├─ ingestion/tagger.py (optional LLM tagging)
       ├─ ingestion/npc_tagging.py (entity tagging)
       └─ ingestion/store.py (LanceDB insertion)
```

---

## Turn Pipeline Call Graph (V12.0)

Full call graph for an `intent=ACTION` turn:

```
graph.run_turn(conn, state)
  │
  ├─ nodes/router.py:router_node(state)
  │    └─ core/router.py:classify_intent(user_input)
  │         └─ [keyword matching + rules — no LLM by default]
  │         └─ (optional) agents/intent_router_agent.py:assist_routing()  [non-authoritative LLM]
  │
  ├─ nodes/mechanic.py:mechanic_node(state)  [if intent=ACTION]
  │    └─ agents/mechanic.py:MechanicAgent.resolve(state)
  │         ├─ [pure Python: action_type, DC, roll, time_cost, events, stress_delta]
  │         └─ agents/resolution_agent.py:ResolutionAgent  [LLM-backed narrative resolution, V12.0]
  │
  ├─ nodes/encounter.py:encounter_node(state)
  │    └─ agents/encounter.py:EncounterManager.select_npcs(conn, ...)
  │         ├─ content/repository.py:CONTENT_REPOSITORY.get_pack(era_id)
  │         │    └─ content/loader.py:load_stacked_period_content(...)
  │         │         └─ data/static/era_packs/{era}/*.yaml (YAML parsing)
  │         ├─ SQLite: SELECT characters WHERE campaign_id + location (read-only)
  │         └─ core/encounter_throttle.py:check_throttle(conn, ...)
  │
  ├─ nodes/world_sim.py:world_sim_node(state)  [if tick boundary or travel]
  │    ├─ agents/world_mind_agent.py:WorldMindAgent.simulate(...)  [non-authoritative LLM]
  │    │    └─ LLM call (WORLD_MIND_MODEL) → WorldSimOutput
  │    ├─ [fallback: empty WorldSimOutput on LLM failure]
  │    └─ models/news.py:rumors_to_news_feed(rumors)
  │
  ├─ nodes/moments.py:moments_node(state)
  │    └─ content/repository.py:CONTENT_REPOSITORY.get_pack(era_id)
  │         └─ [check EraMoment triggers: arc_stage, turn_number, affinity, location, quest, alignment]
  │         └─ [fire moment: inject narrative_beat into arc_guidance.scene_instructions]
  │
  ├─ nodes/arc_planner.py:arc_planner_node(state)
  │    └─ [deterministic: Hero's Journey beats, tension level, pacing hints]
  │         ├─ core/genre_triggers.py:detect_genre(user_input)
  │         ├─ core/era_transition.py:check_era_transition(world_state)
  │         └─ core/story_position.py:compute_story_position(...)
  │
  ├─ nodes/interlude.py:interlude_node(state)  [V12.0 — NEW]
  │    └─ [interlude scene generation between arcs]
  │
  ├─ nodes/scene_frame.py:scene_frame_node(state)
  │    └─ [extract topic_primary, subtext, npc_agenda from scene state]
  │
  ├─ nodes/director.py:director_node(state)
  │    └─ agents/director.py:DirectorAgent.generate_instructions(state)
  │         ├─ core/hub_system.py:is_hub_location(world_state, era_pack)
  │         │    └─ [inject hub context if hub location]
  │         ├─ rag/style_retriever.py:retrieve_style_layered(era, genre, archetype)
  │         │    └─ LanceDB: style_chunks table
  │         ├─ rag/lore_retriever.py:retrieve_lore(query, era, ...)
  │         │    └─ LanceDB: lore_chunks table
  │         ├─ rag/kg_retriever.py:retrieve_kg_context(...)  [optional]
  │         │    └─ SQLite: kg_entities, kg_triples
  │         ├─ core/episodic_memory.py:get_recent_memories(conn, ...)
  │         │    └─ SQLite: episodic_memories
  │         ├─ core/personality_profile.py:build_profile(present_npcs)
  │         ├─ core/setting_context.py:get_setting_rules(state)
  │         └─ llm_client.py:LLMClient.chat(DIRECTOR_MODEL)  [non-authoritative LLM, text-only]
  │
  ├─ nodes/companion.py:companion_reaction_node(state)
  │    └─ core/companion_reactions.py:compute_reactions(state)
  │         ├─ [alignment deltas, faction reputation deltas]
  │         ├─ [banter_queue append from BANTER_POOL]
  │         └─ compute_inter_party_tensions(party, companion_states)
  │
  ├─ nodes/narrator.py:narrator_node(state)
  │    └─ agents/narrator.py:NarratorAgent.generate(state)  [AUTHORITATIVE LLM]
  │         ├─ rag/lore_retriever.py:retrieve_lore(...)  [different filters from Director]
  │         │    └─ LanceDB: lore_chunks
  │         ├─ rag/character_voice_retriever.py:retrieve_voice(...)
  │         │    └─ LanceDB: character_voice_chunks
  │         ├─ core/pronouns.py:pronoun_block(player)
  │         ├─ core/context_budget.py:allocate_context(...)
  │         ├─ llm_client.py:LLMClient.chat(NARRATOR_MODEL)
  │         │    └─ [on failure: retry 1x → AgentFailureError]
  │         └─ agents/narrator_postprocess.py:post_process(raw_text)
  │              ├─ _strip_structural_artifacts(text)
  │              ├─ _truncate_overlong_prose(text, max_words=250)
  │              ├─ _enforce_pov_consistency(text)
  │              └─ _flag_unknown_entities(text, present_npcs)
  │
  ├─ nodes/narrative_validator.py:narrative_validator_node(state)
  │    └─ [deterministic checks: mechanic consistency, ledger constraints]
  │         └─ core/truth_ledger.py:contradiction_errors(claims, facts)
  │
  ├─ nodes/choice_crafter_node.py:choice_crafter_node(state)  [V5.0 — AUTHORITATIVE]
  │    ├─ core/setting_context.py:get_setting_rules(state)
  │    ├─ core/companions.py:get_companion_by_id(cid)
  │    ├─ core/suggestion_engine.py:_detect_tone_streak(history, last_inputs)
  │    ├─ agents/choice_crafter_agent.py:generate_choices(...)  [AUTHORITATIVE LLM]
  │    │    └─ llm_client.py:LLMClient.chat(CHOICE_CRAFTER_MODEL)
  │    │         └─ [on failure: retry 1x → AgentFailureError]
  │    ├─ core/suggestion_engine.py:classify_suggestion(text, meaning_tag)
  │    ├─ core/suggestion_engine.py:ensure_tone_diversity(suggestions)
  │    ├─ core/action_lint.py:lint_actions(actions, game_state, ...)
  │    └─ core/suggestion_engine.py:action_suggestions_to_player_responses(linted, scene_frame)
  │
  └─ nodes/commit.py:commit_node(state)
       ├─ SQLite: UPDATE campaigns SET world_time_minutes, world_state_json
       ├─ event_store.py:append_events(conn, campaign_id, turn_number, events)
       ├─ state_reducer.py:apply_projection(conn, campaign_id)
       │    └─ [dispatch event handlers: MOVE, DAMAGE, ITEM_ACQUIRED, etc.]
       ├─ core/episodic_memory.py:maybe_compress_turn(conn, ...)
       ├─ core/transcript_store.py:save_rendered_turn(conn, ...)
       ├─ core/quest_tracker.py:process_quests_for_turn(world_state, era, ...)
       │    └─ content/repository.py:CONTENT_REPOSITORY.get_pack(era_id)
       ├─ core/truth_ledger.py:upsert_facts(conn, campaign_id, turn_id, facts)
       ├─ [V7.0] turn_snapshots: write world state snapshot for rewind
       ├─ [V7.0] core/canon_scheduler.py: check/record canon events (Historical mode)
       ├─ [V7.0] core/consequence_propagator.py: process ripple/wave/tsunami consequences
       ├─ state_loader.py:build_initial_gamestate(conn, ...)  [reload from DB]
       └─ [V7.0+ POST-COMMIT] core/deferred_agents.py:run_deferred_maintenance()
            ├─ agents/memory_agent.py:MemoryAgent (every turn with prose + NPCs)
            ├─ agents/quest_weaver_agent.py:QuestWeaverAgent (maintenance turns)
            ├─ agents/progression_agent.py:ProgressionAgent (maintenance turns)
            ├─ agents/psych_archivist_agent.py:PsychArchivistAgent (maintenance turns)
            ├─ [V10.0] agents/revelation_agent.py:RevelationAgent (every 5 turns)
            ├─ [V10.0] agents/callback_crystallizer_agent.py:CallbackCrystallizerAgent (every 10 turns)
            └─ [V10.0] agents/player_profile_agent.py:PlayerProfileAgent (every 10 turns, deterministic)
            └─ writes to pending_world_state_patches table (applied on next turn load)
```

---

## What Runs on Every Turn vs. Conditionally

| Module | Every Turn | Conditional |
| ------- | :---: | --------- |
| `router_node` | ✅ | — |
| `mechanic_node` | — | Only `intent=ACTION` |
| `encounter_node` | ✅ | — |
| `world_sim_node` (WorldSim) | — | Only on tick boundary or TRAVEL |
| `moments_node` | ✅ | EraMoments only fire if triggers match |
| `arc_planner_node` | ✅ | — |
| `interlude_node` | — | Only during arc transitions (V12.0) |
| `scene_frame_node` | ✅ | — |
| `director_node` | ✅ | — |
| `companion_reaction_node` | ✅ | — |
| `narrator_node` | ✅ | — |
| `narrative_validator_node` | ✅ | — |
| `choice_crafter_node` | ✅ | — |
| `commit_node` | ✅ | — |
| `meta_node` | — | Only `intent=META` |
| LanceDB style retrieval | ✅ | — |
| LanceDB lore retrieval (Director) | ✅ | — |
| LanceDB lore retrieval (Narrator) | ✅ | — |
| LanceDB character voice retrieval | ✅ | — |
| KG retrieval | — | Optional (when KG populated) |
| `WorldMindAgent.simulate()` | — | Only on WorldSim trigger (tick boundary, travel, or world_reaction_needed) |
| `IntentRouterAgent` LLM call | — | Only on low-confidence routing |
| Episodic memory compression | — | Every 5 turns |
| `RevelationAgent` (V10.0) | — | Every 5 turns (post-commit, deferred) |
| `CallbackCrystallizerAgent` (V10.0) | — | Every 10 turns (post-commit, deferred) |
| `PlayerProfileAgent` (V10.0) | — | Every 10 turns, min 10 turns (post-commit, deterministic) |

---

## Modules Never Called at Runtime (Dev/Offline Only)

| Module | When Used |
| ------- | --------- |
| `ingestion/ingest_lore.py` | Offline: `storyteller ingest` |
| `ingestion/tagger.py` | Offline, optional: `INGESTION_TAGGER_ENABLED=1` |
| `kg/extractor.py` | Offline: `storyteller extract-knowledge` |
| `kg/entity_resolution.py` | Offline: `storyteller extract-knowledge` |
| `kg/synthesis.py` | Offline: `storyteller extract-knowledge` |
| `scripts/validate_era_packs.py` | CI/manual validation |
| `scripts/ingest_style.py` | Offline style ingestion |
| `scripts/rebuild_lancedb.py` | Rebuild vector DB |
| `storyteller/commands/doctor.py` | `storyteller doctor` health check |
| `storyteller/commands/setup.py` | `storyteller setup` first-time setup |

---

## Content Repository Load Path

```
Any node that needs era-pack content calls:
  content/repository.py:CONTENT_REPOSITORY.get_pack(era_id)
    └─ (cached) → return EraPack from _pack_cache
    └─ (miss) → content/loader.py:load_stacked_period_content(setting_id, period_id)
                  └─ data/static/era_packs/{era}/era.yaml
                  └─ data/static/era_packs/{era}/companions.yaml
                  └─ data/static/era_packs/{era}/npcs.yaml
                  └─ data/static/era_packs/{era}/locations.yaml
                  └─ data/static/era_packs/{era}/quests.yaml
                  └─ data/static/era_packs/{era}/factions.yaml
                  └─ data/static/era_packs/{era}/moments.yaml  (V5.0)
                  └─ data/static/era_packs/{era}/...
                  └─ world/era_pack_models.py:EraPack.model_validate(merged_yaml)
```

---

## LLM Call Summary Per Turn

| LLM Role | Model | Authoritative | When |
| --------- | ------- | :---: | ---- |
| Director (text-only) | `mistral-nemo:latest` | No | Every turn (with fallback) |
| Narrator | `mistral-nemo:latest` | Yes | Every turn |
| ChoiceCrafter | `qwen3:8b` | Yes | Every turn |
| WorldMind | `qwen3:8b` | No | WorldSim trigger only |
| CompanionSystem | `qwen3:8b` | No | Companion interaction triggers |
| Memory | `qwen3:8b` | No | Every turn with prose + NPCs (post-commit) |
| QuestWeaver | `qwen3:8b` | No | Maintenance turns (post-commit) |
| Prologue | `qwen3:8b` | No | Campaign creation only |
| ArcScreenplay | `qwen3:8b` | No | Arc start only |
| Bible | `qwen3:8b` | No | Campaign setup only |
| IntentRouter | `qwen3:4b` | No | Low-confidence routing only |
| Architect (blueprint) | `qwen3:4b` | No | Campaign setup only |
| Biographer | `qwen3:4b` | No | Campaign setup only |
| Continuity | `qwen3:4b` | No | Maintenance turns (post-commit) |
| Progression | `qwen3:4b` | No | Maintenance turns (post-commit) |
| PsychArchivist | `qwen3:4b` | No | Maintenance turns (post-commit) |
| RevelationAgent (V10.0) | `qwen3:4b` | No | Every 5 turns (post-commit) |
| CallbackCrystallizer (V10.0) | `qwen3:4b` | No | Every 10 turns (post-commit) |

**Maximum LLM calls per normal turn (no WorldSim):** 3 (Director + Narrator + ChoiceCrafter)

**Maximum LLM calls per WorldSim turn:** 4 (+ WorldMindAgent)

**V10.0 deferred agent calls (post-commit, non-blocking):** +1 (RevelationAgent every 5 turns) or +2 (+ CallbackCrystallizer every 10 turns). PlayerProfileAgent is deterministic (no LLM).

---

## Error Handling Call Graph

```
run_turn(conn, state)
  try:
    graph.invoke(state)
  except AgentFailureError as afe:
    ← raised by: NarratorAgent or ChoiceCrafterAgent after 2 failed attempts
    ← via: error_handling.py:authoritative_call(agent_name, fn, ...)
    return error GameState:
      final_text = "[SYSTEM] A narrative agent failed: {afe.agent_name}. ..."
      suggested_actions = []
      warnings += ["[AGENT_FAILURE] {afe.agent_name}: {afe.original_error}"]
```
