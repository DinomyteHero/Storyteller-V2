# 08 — Alignment Checklist

Use this checklist to validate whether the implementation matches the intended Storyteller AI V5.0 design goals.

Legend:
- ✅ Implemented and verified in code
- ⚠️ Partially implemented or has caveats
- ❌ Not yet implemented
- 🔄 Changed in V5.0

---

## Core Invariants

| Invariant | Status | Notes |
| ----------- | -------- | ------- |
| **Single Transaction Boundary** — only `CommitNode` writes to DB | ✅ | `backend/app/core/nodes/commit.py` is the only node that calls `conn.commit()`. All other nodes are pure functions. |
| **Deterministic Mechanic** — `MechanicAgent` uses zero LLM calls | ✅ | `backend/app/core/agents/mechanic.py` is pure Python. |
| **Prose-Only Narrator** — `final_text` contains only prose, no embedded choice text | ✅ | `embedded_suggestions = None` always. `_strip_structural_artifacts()` and `_truncate_overlong_prose()` enforced in `narrator_postprocess.py`. |
| **Event Sourcing** — `turn_events` is append-only | ✅ | No DELETE or UPDATE on `turn_events`. `apply_projection()` replays from event log. |
| **Connection-Agnostic Graph** — LangGraph pipeline contains no captured DB connections | ✅ | Connection injected via `state["__runtime_conn"]` at `run_turn()` invocation time. Not a closure capture. |
| **Immutable Compiled Graph** — pipeline compiled once, singleton | ✅ | `_COMPILED_GRAPH` singleton in `graph.py`. Re-compiled per test (`PYTEST_CURRENT_TEST` env). |

---

## V5.0 Architecture

| Feature | Status | Notes |
| --------- | -------- | ------- |
| **Setting-agnostic agents** — no hardcoded universe names in agent prompts | 🔄 ⚠️ | `get_setting_rules(state)` added; Director and ChoiceCrafter use `SettingRules`. Remaining agents are progressively updated. Some prompts may still contain SW-specific text. |
| **ChoiceCrafter (authoritative)** — replaces SuggestionRefiner | 🔄 ✅ | `choice_crafter_node.py` + `choice_crafter_agent.py`. No deterministic fallback. Raises `AgentFailureError` on failure. |
| **EraMoments system** — scripted narrative triggers from era packs | 🔄 ✅ | `moments_node` between `companion_reaction` and `arc_planner`. Non-fatal. Once-only enforcement via `fired_moments`. |
| **AgentFailureError / authoritative_call()** — structured agent failure handling | 🔄 ✅ | `error_handling.py`. `run_turn()` catches `AgentFailureError` and returns structured error. |
| **ContentRepository singleton** — thread-safe era pack loading | 🔄 ✅ | `content/repository.py`. Thread-safe via `threading.RLock`. |
| **PartyState canonical model** — multi-axis companion relationship | 🔄 ✅ | `party_state.py`. `world_state_json["party_state"]` is canonical. Legacy fields still written for compat. |
| **Hub/Downtime system** — hub locations activate downtime mode | 🔄 ✅ | `hub_system.py`. Director gets hub-mode prompt injection. |
| **QuestTracker** — deterministic quest state machine | 🔄 ✅ | `quest_tracker.py`. Called in Commit node. Supports entry conditions, stage conditions, resolution paths. |
| **Truth Ledger** — persistent fact store | 🔄 ⚠️ | `truth_ledger.py` implemented. DB tables (`truth_facts`, `truth_events`) **not yet in migrations 0001-0021**. Pending migration 0022. |

---

## Agent System

| Feature | Status | Notes |
| --------- | -------- | ------- |
| **Director generates text-only output** — no JSON schema, no suggestion generation in LLM call | ✅ | Post-V5.0: Director LLM call is text-only. ChoiceCrafter owns choice generation. |
| **Narrator max 250 words** | ✅ | Enforced by `_truncate_overlong_prose()` in `narrator_postprocess.py`. |
| **4-tone diversity** — PARAGON, INVESTIGATE, RENEGADE, NEUTRAL all represented | ✅ | `ensure_tone_diversity()` in `suggestion_engine.py` pads/replaces to guarantee all 4 tones. |
| **3-tier risk classification** — SAFE, RISKY, DANGEROUS | ✅ | `classify_suggestion()` in `suggestion_engine.py`. Used by MechanicAgent for DC modifiers. |
| **Action linting** — suggestions validated against NPC/item/location reality | ✅ | `lint_actions()` in `action_lint.py`. Called in `choice_crafter_node.py`. |
| **ChoiceCrafter context richness** — scene frame, NPC utterance, companion hint, history, arc | ✅ | All context fields built in `choice_crafter_node.py` and passed to `generate_choices()`. |

---

## World Systems

| Feature | Status | Notes |
| --------- | -------- | ------- |
| **Living World tick** — WorldSim fires on time tick or travel | ✅ | `world_sim.py`: `floor(t0/tick) != floor(t1/tick)` or TRAVEL action. |
| **Deterministic faction engine** — no LLM fallback for faction simulation | ✅ | `faction_engine.simulate_faction_tick()`. WorldMindAgent is the optional LLM enhancement. |
| **Encounter throttling** — prevent NPC spam per location | ✅ | `encounter_throttle.py`. Throttle state persisted via `NPC_INTRODUCTION_RECORDED` events. |
| **Companion reactions** — alignment/faction deltas, banter, tensions | ✅ | `companion_reactions.py`. No LLM; deterministic. |
| **Episodic memory** — compressed narrative summaries for continuity | ✅ | `episodic_memory.py`. Stored in `episodic_memories` table. Retrieved by Director/Narrator. |
| **Genre triggers** — 11 genres, keyword-based activation | ✅ | `genre_triggers.py`. Used by Director for style retrieval lane selection. |
| **Era transitions** — REBELLION/NEW_REPUBLIC/etc. detection | ✅ | `era_transition.py`. Triggers era summary generation and `era_transition_pending` flag. |
| **Starship system** — no starting ship, earned in-story | ✅ | `starships.py`. `STARSHIP_ACQUIRED` event. `starships` table. API endpoints. |
| **Psychology system** — psych_profile (mood, stress, trauma) | ✅ | `characters.psych_profile_json`. Stress delta in MechanicAgent. `PsychArchivistAgent` for updates. |
| **Rumor/news feed** — world sim rumors surfaced as ME-style briefing | ✅ | `is_public_rumor=1` events → `rumors_to_news_feed()` → `world_state_json["news_feed"]`. |

---

## RAG System

| Feature | Status | Notes |
| --------- | -------- | ------- |
| **4-lane style retrieval** — Base + Era + Genre + Archetype | ✅ | `retrieve_style_layered()` in `style_retriever.py`. |
| **Lore retrieval** — novel/sourcebook chunks with era/doc_type filters | ✅ | `lore_retriever.py`. Filter by `era`, `doc_type`, `section_kind`. |
| **Character voice retrieval** — dialogue samples per NPC | ✅ | `character_voice_retriever.py`. Era-scoped. |
| **KG retrieval** — runtime entity/triple lookup | ✅ | `kg_retriever.py`. Optional; requires prior KG extraction. |
| **Director/Narrator share RAG results** — avoid duplicate retrieval | ✅ | `shared_kg_character_context`, `shared_episodic_memories` passed from Director to Narrator. |
| **Token budgeting** — per-agent context budget with warnings | ✅ | `context_budget.py`. Emits warnings when trimming occurs. |

---

## API & Infrastructure

| Feature | Status | Notes |
| --------- | -------- | ------- |
| **V2 REST API** — campaign/turn/content endpoints | ✅ | `v2_campaigns.py`. 18+ endpoints. |
| **SSE streaming** — turn/stream endpoint | ✅ | `GET /v2/campaigns/{id}/turn/stream`. Streams narration chunks. |
| **Auto-setup endpoint** — `POST /v2/setup/auto` | ✅ | CampaignArchitect + BiographerAgent pipeline. |
| **Health check** — `/health` + `/health/detail` | ✅ | Checks Ollama, LanceDB, era packs, LLM roles. |
| **Auth middleware** — bearer token or X-API-Key | ✅ | `main.py`. Disabled in `STORYTELLER_DEV_MODE=1`. |
| **Rate limiting** — 10 turn requests/min per IP | ✅ | `main.py` rate limiter middleware. |
| **CORS allowlist** | ✅ | `STORYTELLER_CORS_ALLOW_ORIGINS` env. |

---

## Content System

| Feature | Status | Notes |
| --------- | -------- | ------- |
| **Era packs** — YAML-defined content (locations, NPCs, companions, quests, factions, moments) | ✅ | 5 shipped packs. `_template/` for authoring. |
| **SettingRules in era packs** — setting-agnostic agent config | ✅ | `SettingRules` model in `era_pack_models.py`. Stored in `world_state_json["setting_rules"]`. |
| **EraMoments in era packs** — scripted trigger moments | ⚠️ | `EraMoment` model exists. Not all shipped packs define moments yet. |
| **Quest definitions in era packs** — YAML quests with stages | ⚠️ | `EraQuest` model exists. Packs vary in quest coverage. |
| **Ingestion pipeline** — PDF/EPUB/TXT → LanceDB | ✅ | `ingestion/ingest_lore.py`. Parent/child chunking. |
| **Style ingestion** — `data/style/` → LanceDB | ✅ | `scripts/ingest_style.py`. |
| **Era pack validation** | ✅ | `scripts/validate_era_packs.py`. Run as part of `make check`. |

---

## Checklist: Before Shipping a New Turn

Before merging changes that affect the pipeline, verify:

- [ ] `MechanicAgent` makes no LLM calls (grep for `llm.call` in `agents/mechanic.py`)
- [ ] `CommitNode` is the only node with `conn.commit()` (grep for `conn.commit` in `nodes/`)
- [ ] `final_text` never contains embedded choice text (test: `test_narrator_banter_weave.py`)
- [ ] `suggested_actions` always has exactly 4 items after ChoiceCrafter
- [ ] `ensure_tone_diversity()` enforces all 4 tones
- [ ] `AgentFailureError` is caught in `run_turn()` — not re-raised
- [ ] Truth Ledger migration exists before calling `upsert_facts()`
- [ ] New agents that must succeed are declared authoritative and use `authoritative_call()`
- [ ] New agents that are optional return `state` unchanged on exception (non-fatal)
- [ ] Era pack changes pass `python scripts/validate_era_packs.py`
- [ ] Pipeline topology in `graph.py` matches `docs/02_turn_lifecycle.md`
