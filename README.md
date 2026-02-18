# Storyteller AI

Storyteller AI is a **local-first, setting-agnostic narrative RPG engine** powered by a FastAPI backend, SvelteKit frontend, and a LangGraph pipeline that orchestrates deterministic game systems with LLM-powered storytelling.

**Current Engine Version: V5.0**

**Project version 0.1.0**

V5.0 is a major architecture revision introducing:
- **Setting-agnostic design** — no hardcoded universe names in agents; all setting content comes from Era Packs and `SettingRules`
- **Authoritative LLM choices** — `ChoiceCrafterAgent` (LLM-driven) replaces the deterministic SuggestionRefiner
- **EraMoments system** — scripted narrative triggers defined in era packs
- **Hub/Downtime system** — hub locations activate downtime mode with rest, intel, and companion options
- **Quest Tracker** — deterministic quest state machine with stage-based completion
- **Truth Ledger** — SQLite-backed persistent fact store with contradiction detection
- **PartyState model** — multi-axis companion relationships (influence, trust, respect, fear)
- **ContentRepository** — thread-safe singleton for era pack loading

---

## What Storyteller AI Does

Storyteller AI runs a turn-by-turn narrative loop:

1. Player selects from a **KOTOR-style dialogue wheel** of 4 choices (PARAGON/INVESTIGATE/RENEGADE/NEUTRAL)
2. The engine **classifies the input** (META/TALK/ACTION) and routes it through the pipeline
3. **Deterministic mechanics** compute dice rolls, DC checks, time costs, and world events — zero LLM calls
4. The **Living World** ticks: every action costs in-game time; when time crosses a threshold, off-screen factions move, rumors spread, and a news briefing updates
5. **Scripted moments** fire when era pack trigger conditions are met (companion affinity, arc stage, location, quest completion)
6. An LLM-powered **Director** generates text-only scene pacing instructions
7. An LLM-powered **Narrator** generates prose narration (5-8 sentences, max 250 words)
8. An LLM-powered **ChoiceCrafter** generates the next 4 player choices from the scene context
9. The **Commit node** writes everything to SQLite in a single atomic transaction

The result is a narrative game that feels alive — persistent companions, faction politics, quest progression, and story arc — running entirely on your local hardware.

---

## Architecture Overview

| Component | Technology |
| ----------- | ----------- |
| Backend | FastAPI + Uvicorn |
| Pipeline | LangGraph `StateGraph` (13-node pipeline) |
| Persistence | SQLite (event sourcing + projections) |
| Vector DB | LanceDB (lore, style, character voice RAG) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (local, 384-dim) |
| Default LLM | Ollama (local) — multi-model setup |
| Frontend | SvelteKit 5.0 + TypeScript |
| Content | YAML Era Packs (locations, NPCs, companions, quests, factions, moments) |

### Pipeline Topology (V5.0)

```
router → mechanic → encounter → world_sim → companion_reaction → moments
       → arc_planner → scene_frame → director → narrator → narrative_validator
       → choice_crafter → commit → END
```

**3 LLM calls per normal turn** (Director + Narrator + ChoiceCrafter). 4 on WorldSim turns. 0 for mechanics, routing, and companion reactions.

---

## Key Features

### Core Design Principles

- **Local-First** — Ollama runs everything locally. No cloud API keys required by default.
- **Single Transaction Boundary** — Only the `CommitNode` writes to the database. All other pipeline nodes are pure functions.
- **Deterministic Mechanics** — `MechanicAgent` is zero-LLM. Dice, DCs, time costs, and events are pure Python.
- **Setting-Agnostic (V5.0)** — All universe-specific content comes from era pack YAML and `SettingRules`. Agents use `get_setting_rules(state)` instead of hardcoded universe references.
- **Authoritative LLM Choices (V5.0)** — `ChoiceCrafterAgent` is fully LLM-driven. On failure, `AgentFailureError` is raised and surfaced to the player — no silent degradation for required outputs.
- **Event Sourcing** — Append-only `turn_events` table. Normalized tables are projections rebuilt from events.

### World Systems

| Feature | Description |
| --------- | ----------- |
| **Living World** | In-game time economy. World ticks every 4 hours (configurable). Factions move, rumors spread, news feed updates. |
| **EraMoments (V5.0)** | Scripted narrative triggers in era packs. Fire once on condition: companion affinity, arc stage, location, quest, alignment. |
| **Hub/Downtime (V5.0)** | Hub locations (cantinas, safehouses) unlock: rest, gather intel, resupply, companion conversations. |
| **Quest Tracker (V5.0)** | Deterministic quest state machine. Stage-based progression with multiple resolution paths. |
| **Companion System** | 108 YAML-defined companions. Banter, inter-party tensions, companion-initiated quests. |
| **PartyState (V5.0)** | Multi-axis companion relationships: influence, trust, respect, fear. Backward-compatible. |
| **Truth Ledger (V5.0)** | SQLite-backed fact store. `contradiction_errors()` detects narrative inconsistencies. |
| **Psychology System** | Player `psych_profile`: current_mood, stress_level, active_trauma. Influences narration tone. |
| **Faction Engine** | Deterministic faction simulation. NPC movement, reputation tracking, faction-aware goals. |
| **Knowledge Graph** | Optional offline KG extraction → runtime entity retrieval. |
| **Episodic Memory** | Compressed narrative summaries retrieved for Director/Narrator continuity grounding. |
| **Starship System** | No starting ships. Earned in-story via quest/purchase/salvage/faction/theft. |

### Narrative System

| Feature | Description |
| --------- | ----------- |
| **Director** | Text-only pacing instructions — scene tone, NPC agenda, arc hooks. Uses 4-lane style RAG. |
| **Narrator** | Prose-only (max 250 words). Post-processing: strip artifacts, enforce POV, flag hallucinated names. |
| **ChoiceCrafter (V5.0)** | LLM-driven 4-choice generation. Context: scene, NPCs, arc, companion, consequence hints, setting rules. |
| **4-Lane Style RAG** | Base style + Era style + Genre style + Archetype style via `retrieve_style_layered()`. |
| **KOTOR Tone Wheel** | PARAGON (blue) / INVESTIGATE (gold) / RENEGADE (red) / NEUTRAL (gray). All 4 tones guaranteed. |
| **3-Tier Risk** | SAFE / RISKY / DANGEROUS. Affects DC modifiers, stress delta, and narration intensity. |
| **Genre Triggers** | 11 genre types (heist, war, romance, etc.) auto-detected from player input. |
| **Era Transitions** | REBELLION → NEW_REPUBLIC → NEW_JEDI_ORDER era detection with transition scenes. |

---

## Era Pack System

Era Packs are YAML bundles that define a playable setting period. The system is **setting-agnostic** — packs are not limited to Star Wars.

**Shipped packs:**

| Pack | Period |
| ------ | ------- |
| `dark_times` | Late Republic collapse / Imperial rise |
| `rebellion` | Galactic Civil War (canonical reference pack) |
| `new_republic` | Post-Endor New Republic transition |
| `new_jedi_order` | Yuuzhan Vong war |
| `_template` | Reference structure for authoring new packs |

**Era Pack files:**

```text
data/static/era_packs/{era_id}/
  era.yaml           # Metadata, tone, galactic state, SettingRules
  companions.yaml    # Recruitable party members (species, voice, motivation)
  npcs.yaml          # Non-player characters with personality profiles
  locations.yaml     # Playable locations with services and access points
  quests.yaml        # Stage-based quest definitions with conditions
  factions.yaml      # Political/military factions with reputation tiers
  moments.yaml       # Scripted EraMoment triggers (V5.0)
  backgrounds.yaml   # Character creation origin stories
  namebanks.yaml     # Procedural name generation
  events.yaml        # World events
  rumors.yaml        # NPC-spread rumors
  facts.yaml         # Established world facts
```

### Authoring a New Era Pack

```bash
cp -r data/static/era_packs/_template data/static/era_packs/your_era
# Edit era.yaml, then fill in each YAML file
python scripts/validate_era_packs.py your_era
```

---

## Quickstart

See [QUICKSTART.md](QUICKSTART.md) for full step-by-step instructions.

**One-command start (cross-platform):**

```bash
pip install -e .
python -m storyteller setup
python run_app.py --dev
```

**Windows:**

```bat
.\start_app.bat
```

**Required Ollama models:**

```bash
ollama pull mistral-nemo      # Director + Narrator (quality-critical)
ollama pull qwen3:4b          # ChoiceCrafter + Architect + Biographer + KG
ollama pull nomic-embed-text  # Embeddings (RAG)
```

---

## Configuration

Key environment variables (see `.env.example` for full list):

```bash
# Database + Content
STORYTELLER_DB_PATH=./data/storyteller.db
ERA_PACK_DIR=./data/static/era_packs
VECTORDB_PATH=./data/lancedb

# Per-role LLM (provider + model, independently configurable)
STORYTELLER_DIRECTOR_MODEL=mistral-nemo:latest
STORYTELLER_NARRATOR_MODEL=mistral-nemo:latest
STORYTELLER_ARCHITECT_MODEL=qwen3:4b
STORYTELLER_CHOICE_CRAFTER_MODEL=qwen3:4b

# Feature flags
ENABLE_BIBLE_CASTING=1         # Era pack deterministic NPC selection
ENABLE_PROCEDURAL_NPCS=1       # Fallback procedural NPC generation
DEV_CONTEXT_STATS=0            # Include RAG context stats in API response

# Development
STORYTELLER_DEV_MODE=1         # Disable auth (dev only)
```

Cloud LLM per role (optional):

```bash
STORYTELLER_NARRATOR_PROVIDER=anthropic
STORYTELLER_NARRATOR_API_KEY=sk-ant-...
```

---

## Validation & Testing

```bash
# Validate all era packs
python scripts/validate_era_packs.py

# Full test suite
python -m pytest backend/tests -q

# Ingestion + CLI tests
python -m pytest tests -q

# Deterministic smoke test
python scripts/run_deterministic_tests.py

# Lightweight API smoke test
python scripts/smoke_test.py

# Health check (runtime)
curl http://localhost:8000/health/detail
```

---

## Troubleshooting

**`Era pack not found`**
- Verify `ERA_PACK_DIR` points to `data/static/era_packs`
- Run: `python scripts/validate_era_packs.py {era_id}`

**LLM connection failures**
- Check Ollama is running: `ollama serve`
- Check model is pulled: `ollama list`
- Pull models: `ollama pull mistral-nemo && ollama pull qwen3:4b`
- Check per-role config: `curl http://localhost:8000/health/detail`

**`[SYSTEM] A narrative agent failed: NarratorAgent`**
- An authoritative LLM agent failed after retry. See `warnings` in the response.
- Check Ollama is accessible and the configured model is available.
- The turn can be retried; the DB was not written (failure is pre-Commit).

**Database migration errors**
- Delete `storyteller.db` and restart (dev only): `rm data/storyteller.db`
- Check migrations: `ls backend/app/db/migrations/`

**Frontend won't start**
- Install deps: `cd frontend && npm install`
- Clear cache: `rm -rf frontend/.svelte-kit`

**LanceDB tables missing (RAG not working)**
- Run the ingestion pipeline first: `python -m ingestion.ingest_lore --input data/lore/`
- Check table status: `curl http://localhost:8000/health/detail`

---

## Architecture Highlights (V5.0)

- **Event Sourcing** — Append-only `turn_events` + projections. State always reconstructable from event log.
- **Single Transaction Boundary** — Only `CommitNode` calls `conn.commit()`. Pipeline failures before Commit leave no partial state.
- **Authoritative vs Non-Authoritative** — Narrator and ChoiceCrafter raise `AgentFailureError` on failure. All other agents degrade gracefully.
- **Setting-Agnostic Agents** — All agents use `get_setting_rules(state)` / `SettingRules` — no hardcoded universe names.
- **ContentRepository** — Thread-safe singleton (`threading.RLock`) keyed by `(setting_id, period_id)`. Loaded lazily, cached app-lifetime.
- **ChoiceCrafter (authoritative)** — LLM-driven choice generation. No deterministic fallback. Rich context: scene frame, NPC utterance, arc, companion, consequence hints.
- **EraMoments** — Once-only triggers defined in era YAML. Inject `narrative_beat` into Director instructions via `moments_node`.
- **PartyState** — Canonical multi-axis companion model in `world_state_json["party_state"]`. Legacy fields still written for backward compatibility.
- **QuestTracker** — Deterministic state machine. Supports entry conditions, stage completion conditions, and branching resolution paths.
- **JSON Reliability** — LLM JSON calls use `ensure_json()` with 3-attempt repair + retry via `json_repair.py`.

---

## Documentation

| Doc | Contents |
| ----- | -------- |
| [`docs/00_overview.md`](docs/00_overview.md) | System overview, design principles, feature highlights, pipeline topology |
| [`docs/01_repo_map.md`](docs/01_repo_map.md) | Complete directory structure, all modules, entry points |
| [`docs/02_turn_lifecycle.md`](docs/02_turn_lifecycle.md) | Node-by-node pipeline walkthrough (V5.0) |
| [`docs/03_state_and_persistence.md`](docs/03_state_and_persistence.md) | Event sourcing, DB schema, world_state_json, migrations |
| [`docs/04_agents_and_models.md`](docs/04_agents_and_models.md) | Agent roles, authoritative vs non-authoritative, LLM config, Pydantic models |
| [`docs/05_rag_and_ingestion.md`](docs/05_rag_and_ingestion.md) | RAG pipeline, ingestion format support, style lanes |
| [`docs/06_api_and_routes.md`](docs/06_api_and_routes.md) | REST API endpoints, request/response models, SSE streaming |
| [`docs/07_known_issues_and_risks.md`](docs/07_known_issues_and_risks.md) | Active issues, resolved issues, risks |
| [`docs/08_alignment_checklist.md`](docs/08_alignment_checklist.md) | V5.0 architectural invariants verification |
| [`docs/09_call_graph.md`](docs/09_call_graph.md) | Full turn call graph, per-turn vs conditional execution |
| [`QUICKSTART.md`](QUICKSTART.md) | Step-by-step setup, model pulls, first campaign |

---

## License

See LICENSE file for details.
