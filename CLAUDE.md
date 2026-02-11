# CLAUDE.md — Project Constraints & Coding Standards

This file defines the coding standards, architectural invariants, and constraints for Storyteller AI. Any AI assistant (or contributor) working on this codebase should follow these rules.

## Tech Stack

- **Language:** Python 3.11+
- **Web Framework:** FastAPI + Uvicorn
- **Pipeline Orchestration:** LangGraph (`StateGraph`)
- **Data Validation:** Pydantic V2 (use `model_validate`, `model_dump`, not V1 methods)
- **Primary DB:** SQLite (event sourcing + projections)
- **Vector DB:** LanceDB (RAG retrieval)
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- **Default LLM:** Ollama (local; multi-model: `mistral-nemo:latest` for Director/Narrator, `qwen3:4b` for Architect/Biographer/Casting/KG, `qwen3:8b` for Mechanic/Ingestion/SuggestionRefiner, `nomic-embed-text` for embedding)
- **Frontend:** SvelteKit (`frontend/` — Svelte 5, SvelteKit 2, Vite 6)

## Architectural Invariants

These are non-negotiable constraints. Do not violate them.

1. **Ollama-Only.** Cloud LLM providers are deprecated. All LLM calls go through `AgentLLM` → `llm_client.py` → Ollama HTTP API. Do not add OpenAI, Anthropic, or other cloud provider paths.

2. **Single Transaction Boundary.** Only the Commit node (`backend/app/core/nodes/commit.py` via `make_commit_node()`) writes to the database. All other pipeline nodes are pure functions that pass state forward via the LangGraph state dict. No DB mutations in Router, Mechanic, Encounter, WorldSim, CompanionReaction, ArcPlanner, SceneFrame, Director, Narrator, NarrativeValidator, or SuggestionRefiner nodes.

3. **Deterministic Mechanic.** `MechanicAgent` uses zero LLM calls. Dice rolls, DC computation, time costs, and event generation are pure Python. Do not add LLM calls to the Mechanic.

4. **Event Sourcing.** The `turn_events` table is append-only. Never update or delete events. Normalized tables (`characters`, `inventory`, `campaigns.world_state_json`) are projections derived from events via `apply_projection()`.

5. **Graceful Degradation.** Every LLM-dependent agent must have a deterministic fallback. If the LLM is down or returns invalid output, the game must continue with safe defaults. All `except Exception` blocks in agents must log with `logger.exception()`.

6. **Per-Role LLM Config.** Agent model selection is per-role via `STORYTELLER_{ROLE}_MODEL` environment variables. See `backend/app/config.py` for the role list (includes: architect, director, narrator, casting, biographer, mechanic, ingestion_tagger, npc_render, kg_extractor, embedding).

7. **JSON Retry Pattern.** LLM agents that expect JSON output must: (a) use `json_mode=True` in `AgentLLM.complete()`, (b) attempt `ensure_json()` repair on the response, (c) retry once with a correction prompt on parse failure, (d) fall back to deterministic output on double failure.

8. **Graph Compiled Once.** The LangGraph `StateGraph` is compiled via `_get_compiled_graph()` (lazy singleton). Do not rebuild the graph per turn. The DB connection is injected at runtime via `state["__runtime_conn"]` and stripped from the result before returning a `GameState`.

9. **Prose-Only Narrator (V2.15).** The Narrator generates only prose text (5-8 sentences, max 250 words). It does NOT generate action suggestions.

10. **KOTOR Dialogue Wheel (4 suggestions).** The SuggestionRefiner node is the sole source of suggestions. It generates `SUGGESTED_ACTIONS_TARGET` (4) LLM-powered suggestions per turn using `qwen3:8b`. It reads the Narrator's prose and scene context to produce KOTOR-style player dialogue options. On parse failure, it retries once with a correction prompt. On double failure, minimal emergency fallback responses are used. Feature-flagged via `ENABLE_SUGGESTION_REFINER`. Note: `generate_suggestions()` in `director_validation.py` still exists but is **not called** from the pipeline.

## Pipeline Node Order

```
Router → Mechanic → Encounter → WorldSim → CompanionReaction → ArcPlanner → SceneFrame → Director → Narrator → NarrativeValidator → SuggestionRefiner → Commit
```

- **META** input shortcuts directly to Commit
- **TALK** (DIALOGUE_ONLY) skips Mechanic, goes to Encounter
- **ACTION** goes through all nodes

## Feature Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `ENABLE_BIBLE_CASTING` | `1` (on) | Use Era Pack deterministic NPC casting instead of LLM CastingAgent |
| `ENABLE_PROCEDURAL_NPCS` | `1` (on) | Deterministic procedural NPC generation fallback |
| `ENABLE_SUGGESTION_REFINER` | `1` (on) | LLM-based suggestion refinement (V2.16+) |
| `ENABLE_CHARACTER_FACETS` | `0` (off) | Character facets system (disabled/incomplete) |
| `ENABLE_CLOUD_BLUEPRINT` | `0` (off) | Cloud LLM for strategic campaign blueprint at bootup (V3.0) |

## Code Conventions

- **Imports:** Use absolute imports from `backend.app.*`, `ingestion.*`, etc.
- **Models:** Define Pydantic V2 models in `backend/app/models/`. Use `model_validate()` and `model_dump()`.
- **Constants:** Tuning constants go in `backend/app/constants.py` (not magic numbers in code).
- **State keys:** LangGraph state is a flat `dict[str, Any]`. Use descriptive key names matching `GameState` fields.
- **Logging:** Use `logging.getLogger(__name__)`. Log agent fallbacks at `WARNING` or `ERROR` level.
- **Error handling:** Structured error responses via `backend/app/core/error_handling.py`. Never swallow exceptions silently — at minimum log them.
- **Warnings:** Use `add_warning(target, message)` from `backend/app/core/warnings.py` to surface degradation to the API response.
- **Seeded RNG:** All randomness in deterministic systems (mechanic, companion reactions, faction engine, NPC generation) must be seeded by `turn_number` (or derived hash) for replay/testing.

## RAG Conventions

- **Lore retrieval:** `backend/app/rag/lore_retriever.py` — supports metadata filters (era, planet, faction, doc_type, section_kind, characters)
- **Style retrieval:** `backend/app/rag/style_retriever.py` — 4-lane layered retrieval (Base SW + Era + Genre + Archetype) via `retrieve_style_layered()`
- **Style mappings:** `backend/app/rag/style_mappings.py` — static maps from source_title to era/genre/archetype classification
- **Character voice:** `backend/app/rag/character_voice_retriever.py` — era-scoped snippets by (character_id, era) with fallback to any era
- **Retrieval bundles:** `backend/app/rag/retrieval_bundles.py` — defines which doc_type/section_kind lanes each agent uses
- **Token budgeting:** Use `build_context(...)` from `backend/app/core/context_budget.py` (used by both Director and Narrator). Enable `DEV_CONTEXT_STATS=1` to include budgeting stats in `TurnResponse.context_stats`.

## Testing

- Backend tests live in `backend/tests/`
- Ingestion tests live in `ingestion/`
- Use `pytest` as the test runner: `python -m pytest backend/tests/ -q --tb=short`
- Test files follow `test_*.py` naming convention
- 587 tests passing across 48 test files (V2.20)

## Key File Locations

| Purpose | Path |
|---------|------|
| FastAPI entry point | `backend/main.py` |
| LangGraph pipeline topology | `backend/app/core/graph.py` |
| LangGraph node implementations | `backend/app/core/nodes/` |
| Router | `backend/app/core/router.py` |
| Agent base class | `backend/app/core/agents/base.py` |
| Per-role config | `backend/app/config.py` |
| Tuning constants | `backend/app/constants.py` |
| DB schema + migrations | `backend/app/db/schema.sql`, `backend/app/db/migrations/` |
| Runtime KG retrieval | `backend/app/rag/kg_retriever.py` |
| Pydantic state models | `backend/app/models/state.py` |
| Event model | `backend/app/models/events.py` |
| Starship models | `backend/app/models/starship.py` |
| Director validation + suggestions | `backend/app/core/director_validation.py` |
| Suggestion refiner node | `backend/app/core/nodes/suggestion_refiner.py` |
| SceneFrame node | `backend/app/core/nodes/scene_frame.py` |
| DialogueTurn contract | `backend/app/models/dialogue_turn.py` |
| Companion system | `backend/app/core/companions.py`, `backend/app/core/companion_reactions.py` |
| PartyState (V2.20) | `backend/app/core/party_state.py` |
| BanterManager (V2.20) | `backend/app/core/banter_manager.py` |
| Narrative ledger | `backend/app/core/ledger.py` |
| Pronoun system | `backend/app/core/pronouns.py` |
| Personality profiles | `backend/app/core/personality_profile.py` |
| Genre triggers | `backend/app/core/genre_triggers.py` |
| Era transitions | `backend/app/core/era_transition.py` |
| Episodic memory | `backend/app/core/episodic_memory.py` |
| Faction engine | `backend/app/world/faction_engine.py` |
| Era pack loader + models | `backend/app/world/era_pack_loader.py`, `backend/app/world/era_pack_models.py` |
| NPC generator | `backend/app/world/npc_generator.py` |
| Style mappings | `backend/app/rag/style_mappings.py` |
| Quest tracker | `backend/app/core/quest_tracker.py` |
| Ingestion pipeline | `ingestion/ingest_lore.py` |
| SvelteKit UI | `frontend/` |

## Documentation

- **Architecture:** `docs/architecture.md` (Living Loop, data models, agent roles, RAG pipeline)
- **API contract:** `API_REFERENCE.md` (canonical field shapes for V2 endpoints)
- **Deep docs:** `docs/00-09` (numbered, sequential learning path)
- **Known issues:** `docs/07_known_issues_and_risks.md`
- **Alignment checklist:** `docs/08_alignment_checklist.md`
- **Ingestion guide:** `docs/lore_pipeline_guide.md` (canonical ingestion reference)
- **User guide:** `docs/user_guide.md` (player-facing: time, psychology, tone, companions)
