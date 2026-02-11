# Storyteller V2 — Strategic Implementation Plan

> Based on a comprehensive codebase review as senior engineer + game designer, evaluating against KOTOR-level storytelling depth.

---

## The Core Thesis

The game's storytelling depth is currently bottlenecked by three things:

1. **Content is static** — locations, NPCs, and quests are hardcoded in era pack YAMLs
2. **Prompts are fighting the models** — 1,400-word narrator prompts with 36 cleanup regexes indicate the models are struggling
3. **The UI surfaces ~35% of what the backend computes** — companion reactions, faction shifts, quest branching, and world state all exist but are invisible to the player

---

## Phase 1: Content Foundation (Weeks 1–4)

*"Feed the machine before you tune the engine"*

### 1A. Novel-Scale Corpus Ingestion

The ingestion pipeline (`ingestion/ingest_lore.py`) is already production-grade: EPUB/PDF/TXT → hierarchical chunking (1024 parent / 256 child tokens) → deterministic NPC tagging → LanceDB storage. **It can handle 100+ books today** (~60k chunks, ~200MB in LanceDB, ~10 minutes).

**Steps:**

1. Organize novels by era:
   ```
   data/lore/novels/
   ├── kotor/
   ├── rebellion/
   ├── new_republic/
   ├── legacy/
   └── lotr/
   ```

2. Batch ingest:
   ```bash
   python -m ingestion.ingest_lore \
     --input data/lore/novels --recursive \
     --era-mode folder --tag-npcs \
     --npc-tagging-mode lenient --source-type novel
   ```

3. Expand NPC alias tables in era packs to improve NPC-to-chunk linkage.

4. Add a `universe` metadata field to the ingestion schema (`ingestion/store.py`) to support non-Star Wars content (LOTR, etc.). Filter by it during retrieval in `lore_retriever.py`.

### 1B. Campaign World Generation Pass

**This is the most impactful architectural addition.** Currently there is no per-campaign world generation — locations and NPCs are shared across all campaigns via static era pack YAMLs.

**New system:** `CampaignInitializer` (`backend/app/core/campaign_init.py`)

Runs once at campaign creation after `POST /v2/setup/auto`:

```
Player creates campaign (era, background, companions)
    ↓
CampaignInitializer:
  1. Load era pack (base locations, anchor NPCs, factions)
  2. RAG-query ingested novels for the chosen era (top 20 lore chunks)
  3. LLM generates campaign-specific additions:
     - 4-6 new locations (taverns, hideouts, ruins) seeded from novel lore
     - 8-12 new NPCs with voice profiles drawn from novel characters
     - 3-5 quest hooks derived from novel plot threads
     - Faction tensions calibrated to novel-era conflicts
  4. Validate and merge with era pack base content
  5. Store in campaigns.world_state_json as "campaign_world"
    ↓
Game begins with a rich, unique world per playthrough
```

**Why at creation time, not on-the-fly:**
- LLM generation takes 5–15s per call on local models — unacceptable mid-turn
- Pre-generation ensures internal consistency (NPCs reference locations that exist, quests reference NPCs that exist)
- Deterministic seed (`campaign_id`) means the same ID regenerates the same world
- The era pack remains the skeleton; the campaign initializer fills in the muscle

**Schema additions to `world_state_json`:**
- `generated_locations`: list (same schema as `EraLocation`)
- `generated_npcs`: list (same schema as `EraNpcEntry`)
- `generated_quests`: list (same schema as `EraQuest`)

Encounter node (`nodes/encounter.py`) and `EncounterManager` check both era pack AND generated content.

### 1C. Era Pack Authoring Tools

Create `tools/era_pack_generator.py`:
- Input: era name + ingested novel corpus
- LLM generates draft era pack YAML from RAG-retrieved lore
- Output: standard `data/static/era_packs/{era_id}/` file structure
- Human reviews, edits, commits
- Validates via `EraPack.load_and_validate()` in strict mode

**This turns novel ingestion into a content pipeline:** ingest books → generate era pack → review → commit → play.

---

## Phase 2: Prompt Engineering (Weeks 3–6)

*"Make the small models punch above their weight"*

### 2A. Prompt Compression for Local Models

**Problem:** Narrator system prompt is ~350 tokens. Full context (lore + history + NPCs + companions + ledger) reaches 6K+ in an 8K window, leaving <2K for output.

**Solution — tiered prompt architecture:**

| Tier | Included When | Size |
|------|--------------|------|
| **Core** | Always | ~150 tokens — voice, POV rules, output format |
| **Opening** | First turn only | ~100 tokens — sensory orientation, hook creation |
| **Combat** | Scene type = combat | ~80 tokens — combat prose rules |
| **Companion** | Companion present | ~60 tokens — companion voice notes |
| **NPC Dialogue** | NPC utterance expected | ~80 tokens — KOTOR voice rules, `---NPC_LINE---` format |

**Target:** Reduce system prompt from ~350 to ~200 tokens, freeing ~150 tokens for more lore/context.

### 2B. Few-Shot Examples for JSON Agents

Currently only SuggestionRefiner has few-shot examples. Add 1–2 complete examples to:

| Agent | File | Current System Prompt | Change |
|-------|------|----------------------|--------|
| CastingAgent | `casting.py:53-58` | ~100 words, schema only | Add example NPC JSON |
| Architect.build() | `architect.py:91-106` | ~300 words, schema only | Add minimal campaign skeleton |
| Biographer | `biographer.py:130-142` | ~200 words, schema only | Add example character sheet |
| KG Extractor | `extractor.py:23-72` | ~600 words, exhaustive predicates | Add 1 complete extraction example |

### 2C. Chain-of-Thought for Complex Reasoning

Add structured reasoning prompts to Director for complex scenes:

```
Given the scene context above, reason through:
1. What is the primary dramatic tension?
2. Which NPC has the strongest motivation to act?
3. What should the player discover or decide this turn?
Then write your scene instructions.
```

qwen3 models already support `<think>` blocks natively. SuggestionRefiner already strips them (`suggestion_refiner.py:276-282`). Extend this pattern.

### 2D. Post-Processing Reduction Tracking

The 36 regex patterns in `_strip_structural_artifacts` are a symptom. Add pattern fire counters:

```python
pattern_fire_counts: dict[str, int] = {}
```

Log to warnings in dev mode. Goal: reduce active patterns from 36 to <15 as prompt quality improves. Drop patterns that haven't fired in 1000+ turns.

---

## Phase 3: Frontend Surface Area (Weeks 4–8)

*"Show the player what the backend already knows"*

### 3A. Break Up the Monolith

Extract from `play/+page.svelte` (1,578 lines):

| New Component | Responsibility |
|--------------|---------------|
| `HudBar.svelte` | Top sticky bar: location, time, HP, credits, stress, heat, alert |
| `NarrativeViewport.svelte` | Prose display with typewriter and streaming |
| `CompanionSidebar.svelte` | Always-visible companion reactions |
| `QuestTracker.svelte` | Floating objective indicator |
| `AlignmentIndicator.svelte` | Paragon/Renegade meter |

### 3B. Companion Sidebar (Priority 1)

The backend computes rich companion reactions every turn (`companion_reactions.py`: approval/disapproval on trait axes, arc stage changes, inter-party tensions, 17 banter styles). **None of this is visible during gameplay** — it's buried in the drawer Companions tab.

**New `CompanionSidebar.svelte`:**
- Always visible on desktop (right side, 280px)
- Shows 2–3 active companions:
  - Portrait/icon + name
  - Affinity trend arrow (↑ improving / ↓ declining)
  - Last reaction text ("Bastila approves" / "Mission is uneasy")
  - Arc stage badge (STRANGER → ALLY → TRUSTED → LOYAL)
- Collapses to bottom sheet on mobile
- **Data source:** `TurnResponse.party_status` already contains all data

### 3C. Alignment Meter (Priority 2)

Every choice is tagged PARAGON/INVESTIGATE/RENEGADE/NEUTRAL. Companion system tracks trait axes. But there's no visual morality meter.

**New `AlignmentIndicator.svelte`:**
- Horizontal bar in HUD: blue (Paragon) ← → red (Renegade)
- Shifts based on cumulative tone choices
- Small pip shows last choice direction
- **Backend addition:** `alignment_score` in `TurnResponse` — cumulative from tone tag history

### 3D. Quest Objective Tracker (Priority 3)

**New `QuestTracker.svelte`:**
- Floating card (top-right, below HUD)
- Active quest name + current objective text
- Progress dots (stage 1 of 4)
- Pulses on quest update
- **Backend addition:** `current_objective_text` on quest log entries from `EraQuest` stage descriptions

### 3E. World Map (Stretch Goal)

**New `WorldMap.svelte`:**
- Modal triggered by HUD button or M key
- Available locations from era pack + generated locations
- Current location highlighted
- Travel connections as lines (from `EraLocation.travel_links`)
- Faction-controlled zones color-coded
- Click to travel (triggers MOVE action)
- **New endpoint:** `GET /v2/campaigns/{id}/locations` exposing merged location data

---

## Phase 4: Hybrid Model Strategy (Weeks 6–10)

*"Local for speed, cloud for quality — when the player opts in"*

### 4A. Provider Abstraction Layer

Create `backend/app/core/llm_provider.py`:

```python
class LLMProvider(Protocol):
    def complete(self, system: str, user: str, json_mode: bool = False) -> str: ...
    def complete_stream(self, system: str, user: str) -> Iterator[str]: ...
```

Refactor `LLMClient` → `OllamaClient(LLMProvider)`. Add:
- `AnthropicClient(LLMProvider)` — Claude models
- `OpenAIClient(LLMProvider)` — GPT-4 / OpenAI-compatible APIs

Extend `AgentLLM._get_client()` (`base.py:43-60`) with new provider branches.

### 4B. Per-Role Provider Configuration

Already supported by config.py's env override system:

```bash
# Cloud narrator, local everything else
STORYTELLER_NARRATOR_PROVIDER=anthropic
STORYTELLER_NARRATOR_MODEL=claude-sonnet-4-5-20250929
STORYTELLER_DIRECTOR_PROVIDER=ollama
STORYTELLER_DIRECTOR_MODEL=mistral-nemo:latest
```

### 4C. Fallback Chains

```bash
STORYTELLER_{ROLE}_FALLBACK_PROVIDER=ollama
STORYTELLER_{ROLE}_FALLBACK_MODEL=mistral-nemo:latest
```

Primary fails → fallback local model → deterministic fallback (existing pattern).

### 4D. Token Budget Scaling

| Provider | Max Context | Reserved Output |
|----------|------------|----------------|
| Ollama (8K) | 8,192 | 2,048 |
| Claude (200K) | 32,000 | 4,096 |
| GPT-4 (128K) | 24,000 | 4,096 |

Implement in `config.py:get_role_max_context_tokens()` keyed by provider.

### 4E. UI Setting

- **"Storytelling Quality"**: Local (free, faster) / Enhanced (cloud, requires API key)
- API keys stored in browser localStorage
- Backend validates on first cloud call, falls back to local on failure

---

## Phase 5: Backend Architecture Refinements (Ongoing)

### 5A. World State Schema Normalization

As campaign generation grows `world_state_json`, normalize:
- Generated locations → `campaign_locations` table (`campaign_id`, `location_id`, `location_json`)
- Generated NPCs → existing `characters` table with `origin = 'generated'`
- Keep coordination data (last_location_id, introduced_npcs) in world_state_json

### 5B. Episodic Memory Upgrade

Replace keyword-overlap recall (`episodic_memory.py`) with vector similarity:
- At turn end, embed narrator prose into per-campaign LanceDB memory table
- At retrieval, find semantically similar past turns
- Enables "remember when we were in that cantina?" callbacks

### 5C. Dynamic Location Generation at Runtime

Extend `EncounterManager` for runtime location discovery:
- Player explores beyond known locations → lighter LLM call generates a new location
- Uses campaign's generated world as seed context
- `LOCATION_DISCOVERED` event → commit node applies projection

### 5D. Multi-Universe Support

For LOTR and other non-Star Wars content:
- `universe_id` on campaigns table
- `universe` filter on all RAG retrievers
- Era packs become `{universe}/{era}/` in filesystem
- Pipeline stays the same — content changes, architecture doesn't

---

## Priority Matrix

| Item | Impact | Effort | Phase |
|------|--------|--------|-------|
| Novel ingestion (1A) | High | Low | 1 |
| Campaign world generation (1B) | **Critical** | High | 1 |
| Era pack authoring tools (1C) | Medium | Medium | 1 |
| Prompt compression (2A) | High | Medium | 2 |
| Few-shot examples (2B) | Medium | Low | 2 |
| Chain-of-thought (2C) | Medium | Low | 2 |
| Frontend monolith breakup (3A) | High | Medium | 3 |
| Companion sidebar (3B) | High | Low | 3 |
| Alignment meter (3C) | Medium | Low | 3 |
| Quest tracker (3D) | Medium | Low | 3 |
| World map (3E) | High | High | 3 |
| Provider abstraction (4A) | Medium | Medium | 4 |
| Fallback chains (4C) | Medium | Low | 4 |
| World state normalization (5A) | Medium | Medium | 5 |
| Episodic memory upgrade (5B) | Medium | Medium | 5 |
| Multi-universe support (5D) | Medium | Low | 5 |

---

## Critical Path

```
Phase 1A (ingest novels)
    ↓
Phase 1B (campaign world gen) ──→ Phase 3E (world map)
    ↓                                ↓
Phase 2A-C (prompt tuning) ──→ Phase 4A (hybrid LLM)
    ↓
Phase 3A (frontend breakup) → Phase 3B-D (companion/quest/alignment)
```

**Phase 1A is the unlock.** Everything else builds on a rich content corpus.

**Phases 2 and 3 run in parallel** — backend prompt work and frontend work have no conflicts.

**Phase 4 is optional but transformative** — cloud-quality narration with local-speed UI responsiveness.

---

## End-State Player Experience

With all phases complete:

1. **Create a campaign** → System generates a unique world with 15+ locations, 20+ NPCs, 5+ quest hooks from ingested novels
2. **Open the star map** → See the galaxy, faction territories, travel routes
3. **Enter a cantina** → Meet NPCs with voice profiles derived from novel characters
4. **Make a choice** → KOTOR dialogue wheel with consequence hints, companion previews, skill checks
5. **Watch companions react** → Sidebar shows approval shifts, loyalty upgrades
6. **Track alignment** → Paragon/Renegade meter shifts with accumulated choices
7. **Follow quest threads** → Floating objective tracker with progress, pulses on updates

That's KOTOR-level storytelling depth powered by ingested novels, per-campaign generated worlds, and a UI that surfaces the rich computation the backend already performs.
