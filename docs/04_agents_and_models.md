# 04 — Agents & LLM Plumbing

## Agent Summary (Current)

| Component | File | Deterministic? | LLM? | Output | Fallback Behavior |
|----------|------|----------------|------|--------|-------------------|
| **Router** | `backend/app/core/router.py` + `backend/app/core/nodes/router.py` | Yes | No | `RouterOutput` | Always deterministic routing |
| **MechanicAgent** | `backend/app/core/agents/mechanic.py` | Yes | No | `MechanicOutput` | Always deterministic |
| **EncounterManager** | `backend/app/core/agents/encounter.py` | Yes (DB + deterministic RNG) | No (default) | present NPCs + optional spawn payloads | Returns empty/purely anonymous NPCs when throttled |
| **ArcPlannerNode** | `backend/app/core/nodes/arc_planner.py` | Yes | No | `arc_guidance` (arc stage, tension, pacing) | Always deterministic |
| **FactionEngine** | `backend/app/world/faction_engine.py` | Yes | No | `WorldSimOutput` (faction moves, news) | Always deterministic |
| **NpcGenerator** | `backend/app/world/npc_generator.py` | Yes | No | NPC dict (name, role, traits, voice_tags) | Always deterministic |
| **PersonalityProfile** | `backend/app/core/personality_profile.py` | Yes | No | Prompt blocks (speech patterns, behavior notes) | Always deterministic |
| **CampaignArchitect** | `backend/app/core/agents/architect.py` | No | Yes (Ollama) | `SetupOutput` + `WorldSimOutput` | Deterministic skeleton / no-op WorldSim output |
| **DirectorAgent** | `backend/app/core/agents/director.py` | No | Yes (Ollama) | `director_instructions` (text-only scene guidance) | Deterministic fallback + warnings |
| **NarratorAgent** | `backend/app/core/agents/narrator.py` | No | Yes (Ollama) | Prose (5-8 sentences, max 250 words). `embedded_suggestions` always `None`. | Deterministic narration fallback + warnings |
| **NarrativeValidatorNode** | `backend/app/core/nodes/narrative_validator.py` | Yes | No | `validation_notes` + warnings | Always deterministic, non-blocking |
| **SuggestionRefinerNode** | `backend/app/core/nodes/suggestion_refiner.py` | No | Yes (Ollama) | 4 scene-aware KOTOR suggestions | Deterministic suggestions from Director (fallback) |
| **BiographerAgent** | `backend/app/core/agents/biographer.py` | No | Yes (Ollama) | character sheet dict | Static default character sheet |
| **CastingAgent (legacy)** | `backend/app/core/agents/casting.py` | No | Yes (Ollama) | NPC payload dict | Generic "Wanderer" NPC payload |

Notes:
- **CastingAgent is legacy-only** in normal gameplay: the default encounter path introduces NPCs via Era Packs and/or deterministic procedural generation (`ENABLE_BIBLE_CASTING=1`, `ENABLE_PROCEDURAL_NPCS=1`). LLM casting is only used when both flags are off.
- **DirectorAgent** no longer generates JSON suggestions. It produces text-only scene instructions (pacing, beat, NPC emphasis). All player-facing suggestions are generated deterministically via `generate_suggestions()` in `backend/app/core/director_validation.py`.
- **NarratorAgent** (V2.15) writes prose only. The `_suggestion_request` prompt block was replaced with `_prose_stop_rule` — strict "STOP after last sentence" instructions. The `_extract_embedded_suggestions()` function is no longer called; `embedded_suggestions` is always `None`. Post-processing is hardened with `_strip_structural_artifacts()`, `_truncate_overlong_prose()` (max 250 words, sentence boundary), and `_enforce_pov_consistency()`.
- **FactionEngine** runs during WorldSim to advance faction plans, generate news events, and shift NPC dispositions. Fully deterministic (seeded RNG).
- **NpcGenerator** creates procedural NPCs from era pack name banks and templates. Uses seeded RNG (`derive_seed()`) for deterministic generation.
- **PersonalityProfile** transforms NPC data (voice_tags, traits, archetype, motivation, speech_quirk) into structured prompt blocks injected into Director and Narrator context.
- **SuggestionRefinerNode** (V2.16) reads the Narrator's `final_text` prose and scene context to generate 4 scene-aware KOTOR-style suggestions via `qwen3:4b`. Feature-flagged via `ENABLE_SUGGESTION_REFINER` (default: `True`). 3-layer fallback: AgentLLM JSON retry -> node validation -> deterministic suggestions from Director survive on failure.
- Node glue lives under `backend/app/core/nodes/` (Director/Narrator nodes also lint/pad suggestions and surface warnings).

---

## LLM Provider Plumbing

### `AgentLLM` (Ollama-only)

**File:** `backend/app/core/agents/base.py`

`AgentLLM(role)` is the central LLM wrapper. It:
- Reads per-role config from `backend/app/config.py` (`MODEL_CONFIG`)
- Only supports `provider=ollama`
- Supports JSON mode (`json_mode=True`) with a single deterministic repair retry

### Default Model Assignments

| Tier | Model | Roles | VRAM |
|------|-------|-------|------|
| Quality-critical | `mistral-nemo:latest` | Director, Narrator | ~7 GB |
| Medium | `qwen3:8b` | Mechanic, Ingestion Tagger, NPC Render | ~5 GB |
| Lightweight | `qwen3:4b` | Architect, Casting, Biographer, KG Extractor, Suggestion Refiner | ~2 GB |
| Embedding | `nomic-embed-text` | Embedding (reserved; runtime uses sentence-transformers) | minimal |

Only one model is loaded at a time (specialist swapping), so peak VRAM equals the largest loaded model.

### Token Budgets

| Model class | Max context tokens | Reserved output tokens |
|-------------|-------------------|----------------------|
| 14b models | 8192 | 2048 |
| 7b models | 4096 | 1024 |

### Hardware Profiles

Defined in `backend/app/config.py` (`HARDWARE_PROFILES`):

| GPU | Director/Narrator | Architect/Casting/Biographer | Mechanic/Tagger/KG |
|-----|-------------------|------------------------------|---------------------|
| RTX 4070 12GB | `mistral-nemo:latest` | `qwen3:4b` | `qwen3:8b` / `qwen3:4b` |
| RTX 3080 10GB | `qwen3:8b` | `qwen3:4b` | `qwen3:8b` / `qwen3:4b` |
| RTX 4090 24GB | `mistral-nemo:latest` | `mistral-nemo:latest` | `qwen3:8b` |

### Roles

Roles present in `MODEL_CONFIG` (some are for optional workflows):
- `architect`, `director`, `narrator`, `casting`, `biographer`
- `mechanic` (configured but MechanicAgent is deterministic)
- `ingestion_tagger` (optional ingestion enrichment; off by default)
- `npc_render` (optional "render pass" for generated NPCs; off by default)
- `kg_extractor` (knowledge graph extraction pipeline)
- `suggestion_refiner` (V2.16: scene-aware suggestion generation from Narrator prose)
- `embedding` (reserved; runtime embedding currently uses sentence-transformers)

### Per-role env overrides

`backend/app/config.py` supports:
- `STORYTELLER_{ROLE}_PROVIDER` (must be `ollama`)
- `STORYTELLER_{ROLE}_MODEL`
- `STORYTELLER_{ROLE}_BASE_URL`

With fallback to `{ROLE}_MODEL`/`{ROLE}_BASE_URL` for convenience.

---

## Token Budgeting (Director + Narrator)

**File:** `backend/app/core/context_budget.py`

Both Director and Narrator use `build_context(...)` to:
- Estimate tokens conservatively
- Trim least-important context first (style -> voice -> lore -> history -> hard cut)
- Emit a warning when trimming occurs

If `DEV_CONTEXT_STATS=1`, Narrator records a JSON `context_stats` report on the state, which is surfaced in `TurnResponse.context_stats`.

---

## Action Validation + Suggestion Generation

### Deterministic Suggestion Generation (V2.15)

**File:** `backend/app/core/director_validation.py` — `generate_suggestions()`

Player-facing suggestions are 100% deterministic (no LLM). The `generate_suggestions()` function uses scene context to produce exactly `SUGGESTED_ACTIONS_TARGET` (4) action choices.

**Context-aware branches:**

| Branch | Trigger | Suggestion style |
|--------|---------|-----------------|
| Post-combat success | `action_type` is ATTACK/COMBAT and `success=True` | Search fallen, interrogate, tend wounds, press deeper |
| Post-combat failure | `action_type` is ATTACK/COMBAT and `success=False` | Fall back, negotiate, escape, desperate stand |
| Post-stealth success | `action_type` is STEALTH/SNEAK and `success=True` | Eavesdrop, slip past, reveal self, ambush |
| Post-stealth failure | `action_type` is STEALTH/SNEAK and `success=False` | Bluff, surrender, fight free, create distraction |
| Exploration (no NPCs) | `present_npcs` is empty | Search clues, wait and observe, check terminals, keep moving |
| Social (default) | NPCs present | PARAGON offer help, INVESTIGATE press for info, RENEGADE confront, NEUTRAL tactical scan |

**Additional context signals:**
- Player background (Force-sensitive, smuggler, etc.) shapes PARAGON dialogue
- Faction memory shapes INVESTIGATE questions
- Location name shapes RENEGADE threats and tactical scan hints
- Stress level > 7 swaps the last exploration option with "Take a moment to steady yourself"

### Suggestion Classification

**File:** `backend/app/core/director_validation.py` — `classify_suggestion()`

Classifies raw suggestion text into a full `ActionSuggestion` using deterministic keyword analysis:

- **Tone:** Lead verb checked against `_PARAGON_VERBS`, `_INVESTIGATE_VERBS`, `_RENEGADE_VERBS` keyword sets. Falls back to `NEUTRAL`.
- **Risk:** `_DANGEROUS_VERBS` -> DANGEROUS, `_RISKY_VERBS` -> RISKY, else SAFE.
- **Category:** Dialogue quotes -> SOCIAL, `_SOCIAL_VERBS` -> SOCIAL, `_COMMIT_VERBS` -> COMMIT, else EXPLORE.
- **Dialogue detection:** Quoted text (`"..."`) is wrapped as `Say: '...'` for the router (TALK intent).

### Tone Diversity

**File:** `backend/app/core/director_validation.py` — `ensure_tone_diversity()`

Guarantees KOTOR tone spread: at least one each of PARAGON, INVESTIGATE, RENEGADE if possible. Re-tags NEUTRAL suggestions to fill gaps. Also ensures at least one ALTERNATIVE strategy tag.

### Action Linting

**File:** `backend/app/core/action_lint.py` — `lint_actions()`

Validates and pads suggestions to exactly `SUGGESTED_ACTIONS_TARGET` (4):

1. Normalizes input to `ActionSuggestion` instances
2. Drops actions referencing missing NPCs/items
3. Enforces talk-only mode constraints
4. Removes travel-in-combat suggestions
5. Pads back to exactly 4 safe options with context-aware defaults (location name, NPC name)
6. Ensures at least one of each core category (SOCIAL, EXPLORE, COMMIT)

Warnings from validation/linting are collected into `GameState.warnings` and returned by the API.

---

## Companion Reactions System

**File:** `backend/app/core/companion_reactions.py`

### Trait Scoring

Companions react to player choices via deterministic trait-vs-tone scoring. Each companion has traits on three axes:
- `idealist_pragmatic` — idealists like PARAGON, pragmatists like RENEGADE
- `merciful_ruthless` — merciful likes PARAGON, ruthless likes RENEGADE
- `lawful_rebellious` — cautious (low lawful) likes INVESTIGATE

The mechanic result's `tone_tag` is scored against each companion's traits to produce an affinity delta (range: -5 to +5 per turn).

### Affinity Arcs

| Stage | Affinity range | Unlocks |
|-------|---------------|---------|
| STRANGER | <= -10 | Minimal interaction |
| ALLY | -9 to 29 | Normal dialogue |
| TRUSTED | 30 to 69 | COMPANION_REQUEST events (20% per turn), banter with memory |
| LOYAL | 70+ | COMPANION_QUEST events (personal quest hook, one-time) |

### Banter System

**Pool:** 17 banter styles (`BANTER_POOL` in `backend/app/constants.py`): stoic, warm, snarky, defensive, wise, calculating, terse, academic, gruff, apologetic, weary, earnest, diplomatic, beeps, analytical, mystical, formal.

Banter is rate-limited to one line per `BANTER_COOLDOWN_TURNS` (3) turns. Selection uses seeded RNG (`derive_seed()`) for determinism. At TRUSTED/LOYAL arc stages with memories, banter references companion memories via `BANTER_MEMORY_POOL`.

### Inter-Party Tensions

**Function:** `compute_inter_party_tensions()`

When one companion approves (delta >= 2) and another disapproves (delta <= -2) on the same turn, a tension is flagged. Tension context is formatted for both Director (`format_inter_party_tensions_for_director()`) and Narrator (`format_inter_party_tensions_for_narrator()`), capped at 2 tension lines per turn.

### Companion Triggers

**Function:** `check_companion_triggers()`

Milestone-based companion-initiated events:
- **COMPANION_REQUEST:** TRUSTED companion wants to speak (20% per turn, seeded RNG)
- **COMPANION_QUEST:** LOYAL companion reveals personal quest hook (one-time)
- **COMPANION_CONFRONTATION:** Sharp drop conflict detected, companion confronts player

Fired triggers are persisted in `world_state_json["companion_triggers_fired"]` to avoid repeats.

---

## NPC Personality Profiles

**File:** `backend/app/core/personality_profile.py`

### `build_personality_block(npc)`

Transforms NPC data into structured prompt blocks for Director/Narrator context injection. No LLM calls -- pure Python string assembly from constant mappings.

**Input:** NPC dict (from era pack or companion YAML) with fields: `name`, `voice_tags`, `traits`, `archetype`, `motivation`, `speech_quirk`, `banter_style`.

**Output:** Formatted text block:
```
[NPC_NAME -- Personality]
Archetype: <archetype>
Voice: <voice_tags>
Traits: <traits>
Speech pattern: <from VOICE_TAG_SPEECH_PATTERNS lookup, max 2>
Behavior: <from TRAIT_BEHAVIOR_MAP lookup, max 2>
Interaction: <from ARCHETYPE_INTERACTION_MAP lookup>
Quirk: <speech_quirk>
Drives: <motivation>
```

### Constant Mappings

| Map | Count | Purpose |
|-----|-------|---------|
| `VOICE_TAG_SPEECH_PATTERNS` | ~82 tags | Voice tag -> speech pattern description |
| `TRAIT_BEHAVIOR_MAP` | ~46 traits | Trait keyword -> behavioral description |
| `ARCHETYPE_INTERACTION_MAP` | ~30 archetypes | Archetype -> interaction style |

### Scene Context

**Function:** `build_scene_personality_context(present_npcs, era_npc_lookup, companion_lookup, max_npcs=4)`

Builds combined personality context for all NPCs in a scene. Looks up rich data from era pack or companion YAML, merges with present NPC state, and assembles personality blocks (max 4 NPCs per scene for token budget).

---

## Pronoun System

**File:** `backend/app/core/pronouns.py`

### `pronoun_block(name, gender)`

Generates pronoun context for Director/Narrator prompts. Returns empty string when gender is unknown (preserves existing behavior).

**Supported genders:** `male` (he/him/his/himself), `female` (she/her/her/herself).

**Output format:**
```
CHARACTER PRONOUNS: {name} uses {subject}/{object}/{possessive} pronouns.
Always use these pronouns when referring to {name} in narration and dialogue.
```

Injected into both Director and Narrator prompts during turn execution. Gender is set at character creation via `SetupAutoRequest.player_gender` and persisted on `CharacterSheet.gender`.
