# Storyteller-V2: Implementation Plan

*Based on findings from [COMPREHENSIVE_REVIEW.md](./COMPREHENSIVE_REVIEW.md)*

*Updated with corrections from cross-review validation (see [Corrections Log](#corrections-log) at end of document).*

---

## Plan Structure

This plan is organized into **7 phases**, ordered by impact and dependency. Each phase contains discrete tasks with:
- **Goal**: What we're solving and why
- **Files**: Exact files to create or modify
- **Implementation**: Step-by-step technical specification
- **Acceptance Criteria**: How we know it's done
- **Dependencies**: What must be complete first

Phases are designed so that each one delivers standalone value. You can ship Phase 1 alone and the game is meaningfully better.

---

## Phase 1: Critical Fixes (Correctness & UX Gaps)

*Goal: Fix issues that break the setting-agnostic contract, degrade the player experience, or diverge between code paths.*

### ~~1.1 Add Truth Ledger Migration~~ RESOLVED

**Status:** Not needed. Tables already exist in `backend/app/db/migrations/0019_turn_contract_passages.sql` (lines 1-16). The `07_known_issues_and_risks.md` doc entry claiming they're missing is stale and should be updated.

**Action item:** Update `docs/07_known_issues_and_risks.md` to mark Known Issue #7 as resolved. Remove from active issues.

**Dependencies:** None.

---

### 1.2 Improve ChoiceCrafter Fallback to 4 Choices

**Problem:** The ChoiceCrafter currently has a 2-choice degraded fallback (`_make_fallback_choices()` in `choice_crafter_node.py:148-174`). When the LLM fails, the player gets only PARAGON + INVESTIGATE options -- missing RENEGADE and NEUTRAL entirely. This breaks the KOTOR dialogue wheel contract (always 4 tones) and limits player expression on failure.

**Files to modify:**
- `backend/app/core/nodes/choice_crafter_node.py`

**Implementation:**

Replace `_make_fallback_choices()` (lines 148-174) with a 4-choice version:

```python
def _make_fallback_choices(
    final_text: str,
    loc: str,
    immediate_situation: str = "",
) -> list[dict[str, str]]:
    """Deterministic 4-choice fallback when LLM fails.

    Returns contextually grounded choices covering all 4 KOTOR tones,
    preserving the dialogue wheel contract even during degraded operation.
    """
    situation = immediate_situation or (
        final_text[-120:].strip() if final_text else "the current situation"
    )
    loc_short = loc.replace("loc-", "").replace("-", " ") if loc else "here"
    return [
        {
            "text": f"Act decisively in response to {situation[:60]}",
            "tone": "PARAGON",
            "meaning": "pragmatic",
            "risk": "RISKY",
            "consequence_hint": "Your bold action shapes what happens next.",
        },
        {
            "text": f"Investigate {loc_short} for more information",
            "tone": "INVESTIGATE",
            "meaning": "seek_history",
            "risk": "SAFE",
            "consequence_hint": "Taking stock reveals something important.",
        },
        {
            "text": f"Force the issue — push hard and see what breaks",
            "tone": "RENEGADE",
            "meaning": "make_demand",
            "risk": "DANGEROUS",
            "consequence_hint": "Aggression has consequences, but so does hesitation.",
        },
        {
            "text": f"Wait and observe from a safe position",
            "tone": "NEUTRAL",
            "meaning": "deflect",
            "risk": "SAFE",
            "consequence_hint": "Patience sometimes reveals what haste would miss.",
        },
    ]
```

**Acceptance Criteria:**
- When ChoiceCrafter LLM fails, player sees exactly 4 choices (all tones represented)
- DialogueWheel renders correctly with all 4 tone colors
- Warning "ChoiceCrafter: LLM failed; showing degraded options" still appears
- Existing tests pass; add a new test for the 4-choice fallback

**Dependencies:** None.

---

### 1.3 Audit and Fix Star Wars Residue in Narrator Prompts

**Problem:** Despite V5.0's setting-agnostic design, `narrator_prompt.py` contains hardcoded Star Wars references that leak into non-Star-Wars settings. A Forgotten Realms player seeing "cantina" or "the Force" breaks immersion.

**Files to modify:**
- `backend/app/core/agents/narrator_prompt.py`

**Specific references to fix:**

| Location | Current Content | Fix |
|----------|----------------|-----|
| Lines 29-43: `_LOCATION_NARRATIVE_NAMES` | Hardcoded map including `"loc-jedi-temple": "the Jedi Temple"` | Make this a fallback; prefer location names from `SettingRules` or ContentRepository. Remove Jedi Temple from defaults. |
| Lines 45-84: `_ERA_FALLBACK_ATMOSPHERE` | 4 hardcoded Star Wars eras (REBELLION, LEGACY, NEW_REPUBLIC, NEW_JEDI_ORDER) with SW-specific prose | Move these to era pack YAML as `atmosphere_fragments`. Add a generic fallback for unknown eras. |
| Line 539-541: KOTOR voice rules | "Channel Kreia, Atton, Jolee Bindo" | Gate behind `setting_genre == "science fantasy"`. For other settings, use genre-appropriate references (e.g., "Channel the narrative voice of classic {setting_genre} fiction"). |
| Line 564-565: Example character | "A scarred Twi'lek in a pilot's jacket" | Use a generic example: "A scarred figure in a worn jacket" or pull from SettingRules.common_species. |

**Implementation approach:**

1. Add an `atmosphere_fragments` field to era pack YAML schema (`era_pack_models.py`):
```yaml
# In era.yaml:
atmosphere_fragments:
  opening: "The air{planet_str} carried..."
  ambient: "The hum of..."
  tension: "..."
  calm: "..."
  hook: "..."
```

2. In `narrator_prompt.py`, replace the hardcoded `_ERA_FALLBACK_ATMOSPHERE` dict with a loader:
```python
def _get_atmosphere(state: dict) -> dict[str, str]:
    """Load atmosphere from era pack, falling back to generic."""
    era_pack = _get_era_pack(state)
    if era_pack and hasattr(era_pack, "atmosphere_fragments"):
        return era_pack.atmosphere_fragments
    # Generic fallback (no setting-specific references)
    return {
        "opening": "The air{planet_str} carried the weight of recent events.",
        "ambient": "Background noise filled the space — voices, machinery, the rhythm of daily life.",
        "tension": "Something felt wrong. The atmosphere tightened.",
        "calm": "For a moment, everything was still.",
        "hook": "The next chapter waited, just beyond the threshold.",
    }
```

3. For `_LOCATION_NARRATIVE_NAMES`, add a resolver that checks era pack locations first:
```python
def _resolve_location_name(loc_id: str, state: dict) -> str:
    """Resolve location ID to narrative name, preferring era pack data."""
    # Try era pack locations first
    era_pack = _get_era_pack(state)
    if era_pack:
        for loc in getattr(era_pack, "locations", []):
            if loc.get("id") == loc_id:
                return loc.get("name", loc_id)
    # Fall back to generic mappings (no setting-specific names)
    return _GENERIC_LOCATION_NAMES.get(loc_id, loc_id.replace("loc-", "").replace("-", " "))
```

**Acceptance Criteria:**
- A Forgotten Realms campaign never sees "cantina," "the Force," "Jedi Temple," "stormtrooper," or any Star Wars term in narrator prose
- Star Wars campaigns still get their era-specific atmosphere (loaded from era pack YAML)
- Unknown/new era packs get a clean generic atmosphere
- Run existing narrator tests to ensure no regressions

**Dependencies:** None (can be done in parallel with 1.1 and 1.2).

---

### 1.4 Unify Streaming Path with Main Graph Pipeline

**Problem:** The SSE streaming endpoint (`/v2/campaigns/{id}/turn_stream`) at `v2_campaigns.py:1311` uses a **different post-narrator pipeline** than the main graph. Specifically, `_run_post_narrator_pipeline()` at line 1291 calls the **legacy `suggestion_refiner`** (line 1302) instead of the V5.0 `choice_crafter_node`. This means streamed turns get different (lower-quality, deterministic) choices than non-streamed turns.

**Files to modify:**
- `backend/app/api/v2_campaigns.py` — replace `make_suggestion_refiner_node()` with `make_choice_crafter_node()` in `_run_post_narrator_pipeline()`

**Implementation:**

In `_run_post_narrator_pipeline()` (line 1291-1308), replace:
```python
from backend.app.core.nodes.suggestion_refiner import make_suggestion_refiner_node
suggestion_refiner = make_suggestion_refiner_node()
state_dict = suggestion_refiner(state_dict)
```

With:
```python
from backend.app.core.nodes.choice_crafter_node import make_choice_crafter_node
choice_crafter = make_choice_crafter_node()
state_dict = choice_crafter(state_dict)
```

Verify that the `choice_crafter_node` receives the same state keys that the main graph provides (scene_frame, director_instructions, present_npcs, etc.). If the streaming path skips scene_frame or director nodes, those need to be wired in too.

**Acceptance Criteria:**
- Streamed turns produce the same 4-tone LLM-driven choices as non-streamed turns
- Fallback behavior (2->4 choice degradation) applies identically in both paths
- No regression in streaming latency (choice crafter may add ~5s over the deterministic refiner)
- Legacy suggestion_refiner import can be removed if no other code path uses it

**Dependencies:** 1.2 (ChoiceCrafter improvements, since both paths should use the same fallback).

---

### 1.5 Add Per-Agent Latency Telemetry

**Problem:** Turn latency is the #1 UX issue, but we're making decisions about which agents to optimize based on assumptions rather than data. The commit node at `commit.py:133-336` triggers multiple LLM agents (ContinuityAgent, MemoryAgent, QuestWeaver, Progression, PsychArchivist) but there's no per-agent timing data to know which ones actually contribute to latency.

**Files to modify:**
- `backend/app/core/agents/base.py` — add timing wrapper to `AgentLLM.complete()` / `AgentLLM.generate()`
- `backend/app/core/graph.py` — log per-node timing in `run_turn()`
- `backend/app/models/narration.py` — add `agent_timings` field to `TurnResponse`

**Implementation:**

1. Wrap every LLM call in `AgentLLM` with timing:
```python
import time

def complete(self, system_prompt, user_prompt, **kwargs):
    start = time.perf_counter()
    result = self._complete_impl(system_prompt, user_prompt, **kwargs)
    elapsed = time.perf_counter() - start
    logger.info("LLM call [%s] completed in %.2fs", self.role, elapsed)
    # Store in thread-local or state for aggregation
    return result
```

2. In `run_turn()`, wrap each node call with timing and aggregate:
```python
timings = {}
for node_name, node_fn in pipeline:
    start = time.perf_counter()
    state = node_fn(state)
    timings[node_name] = round(time.perf_counter() - start, 3)
state["agent_timings"] = timings
```

3. Include timings in TurnResponse when `DEV_CONTEXT_STATS=1`:
```json
{
    "agent_timings": {
        "router": 0.12,
        "mechanic": 0.05,
        "encounter": 0.08,
        "world_sim": 0.0,
        "director": 5.23,
        "narrator": 12.41,
        "choice_crafter": 6.88,
        "commit": 3.45
    }
}
```

**Acceptance Criteria:**
- Every node and LLM call has timing data logged
- Timings included in API response when `DEV_CONTEXT_STATS=1`
- No performance overhead >10ms from the timing instrumentation itself
- Data enables evidence-based decisions about cloud routing and agent batching

**Dependencies:** None.

---

### 1.6 Add Ollama Unavailable UI State

**Problem:** If Ollama isn't running, every LLM call fails silently. The player sees cryptic `[SYSTEM] A narrative agent failed` errors with no guidance.

**Files to modify:**
- `frontend/src/lib/api/client.ts` — add health check on app load
- `frontend/src/lib/stores/ui.ts` — add `ollamaStatus` state
- `frontend/src/routes/+layout.svelte` — show banner when Ollama is down
- `backend/main.py` — ensure `/health/detail` returns Ollama connectivity clearly

**Implementation:**

1. On frontend mount (`+layout.svelte`), call `/health/detail` and parse Ollama status
2. If Ollama is unreachable, show a persistent top-banner:
   ```
   ⚠ Story engine unavailable — Ollama is not running.
   Start it with: ollama serve
   ```
3. Poll every 10 seconds while banner is shown; auto-dismiss when Ollama comes back
4. Disable the "Send" button and dialogue wheel while Ollama is down

**Acceptance Criteria:**
- Player sees a clear, actionable message when Ollama is down
- Banner auto-dismisses when Ollama starts
- No turn can be submitted while Ollama is unreachable
- Works on both desktop and mobile layouts

**Dependencies:** None.

---

## Phase 2: Core Loop Polish

*Goal: Make the "read -> choose -> read" loop feel exceptional. This is the most impactful phase for player experience.*

### 2.1 Dynamic Narrator Word Limits

**Problem:** The 250-word hard cap in `narrator_postprocess.py:_truncate_overlong_prose()` treats all scenes equally. A climactic betrayal gets the same word budget as walking through a marketplace. This flattens dramatic peaks.

**Files to modify:**
- `backend/app/core/agents/narrator_postprocess.py` — make `max_words` parameter dynamic
- `backend/app/core/nodes/narrator.py` — pass scene-appropriate word limit
- `backend/app/core/nodes/scene_frame.py` — compute `scene_weight` for the current turn

**Implementation:**

1. In `scene_frame.py`, compute a `scene_weight` based on existing signals:
```python
def _compute_scene_weight(gs: GameState) -> str:
    """Classify scene weight: STANDARD, ELEVATED, or CLIMAX."""
    arc_stage = gs.campaign.get("world_state_json", {}).get("arc_stage", "SETUP")
    beat = gs.campaign.get("world_state_json", {}).get("current_beat", "")
    has_companion_event = bool(gs.get("companion_event"))
    mechanic_events = gs.get("mechanic_events", [])
    has_combat = any(e.get("type") == "COMBAT" for e in mechanic_events)

    # Climax scenes: arc climax beats, companion loyalty events, combat
    if beat in ("ORDEAL", "RESURRECTION") or arc_stage == "CLIMAX":
        return "CLIMAX"
    if has_companion_event or has_combat or beat in ("APPROACH_INMOST_CAVE", "REWARD"):
        return "ELEVATED"
    return "STANDARD"
```

2. Map scene weight to word limits:
```python
SCENE_WORD_LIMITS = {
    "STANDARD": 250,
    "ELEVATED": 350,
    "CLIMAX": 450,
}
```

3. Pass `scene_weight` through the state dict from `scene_frame` -> `narrator` -> `_truncate_overlong_prose()`

4. Update the narrator system prompt to mention the limit dynamically:
   - STANDARD: "Write 5-8 sentences of narrative prose."
   - ELEVATED: "Write 6-10 sentences of vivid narrative prose. This is an important moment."
   - CLIMAX: "Write 8-12 sentences of immersive, dramatic prose. This is a pivotal moment in the story."

**Acceptance Criteria:**
- Standard exploration scenes stay at ~250 words
- Arc climax beats (ORDEAL, RESURRECTION) get up to 450 words
- Elevated scenes (combat, companion events) get up to 350 words
- No regression on existing narrator tests
- Post-processing truncation respects the dynamic limit

**Dependencies:** None.

---

### 2.2 Reduce Turn Latency — Parallel Director + ChoiceCrafter Context Prep

**Problem:** The 13-node pipeline is fully sequential. A turn takes 20-40 seconds on local hardware. The biggest bottleneck is 3 serial LLM calls: Director (~5-10s) + Narrator (~9-18s) + ChoiceCrafter (~5-10s).

**Files to modify:**
- `backend/app/core/graph.py` — restructure LangGraph topology for partial parallelism
- `backend/app/core/nodes/choice_crafter_node.py` — accept pre-computed context

**Implementation:**

The ChoiceCrafter currently waits for the Narrator to finish, but it primarily needs: scene_frame, director_instructions, NPC context, arc state, and location — most of which are available *before* the Narrator runs.

**Step 1: Pre-compute ChoiceCrafter context during scene_frame**

In `scene_frame` node, also assemble the ChoiceCrafter's context payload and store it in state:
```python
state["choice_crafter_pre_context"] = {
    "scene_frame": scene_frame,
    "director_instructions": state.get("director_instructions", ""),
    "npc_descriptions": npc_descriptions,
    "arc_stage": arc_stage,
    "location": location,
    "companion_reactions": state.get("companion_reactions", []),
}
```

**Step 2: Pass narrator prose to ChoiceCrafter as a late-binding input**

The ChoiceCrafter's primary unique input from the Narrator is `final_text`. Keep the pipeline sequential but restructure so the ChoiceCrafter does all its prep work (prompt assembly, context trimming) while waiting for the narrator. Only the actual LLM call depends on the prose.

**Step 3 (future, more aggressive): Run Narrator + ChoiceCrafter in parallel**

Use LangGraph's parallel branch support to run the ChoiceCrafter on director_instructions alone (without narrator prose), then post-process to ensure choices are grounded in the actual narrative. This trades slight choice quality for significant latency reduction.

**Estimated impact:** 5-10 seconds saved per turn (ChoiceCrafter context assembly moves from serial to parallel).

**Acceptance Criteria:**
- Turn latency measurably decreases (log timing before/after)
- Choice quality is not degraded (manual review of 20 sample turns)
- Pipeline still respects single transaction boundary (Commit node unchanged)

**Dependencies:** None (but pair well with 2.1).

---

### 2.3 "Forge Your Own Path" Free Text Redesign

**Problem:** The free text input competes with the dialogue wheel, creating an identity crisis. Is this a choice-based game or a text adventure?

**Files to modify:**
- `frontend/src/routes/play/+page.svelte` — redesign free text position and framing

**Implementation:**

1. Move the free text input BELOW the dialogue wheel with visual separation
2. Label it "Forge Your Own Path" with subtitle: "Describe your own action instead"
3. Collapse it by default — show as a single clickable line that expands to a textarea
4. When expanded, slightly dim the dialogue wheel choices (not disable — player can still click them)
5. Add keyboard shortcut: `5` or `F` to toggle the free text input

**Acceptance Criteria:**
- Free text input is visually subordinate to the dialogue wheel
- New label clearly frames it as an alternative, not the primary input
- Keyboard shortcut works
- Accessibility: screen reader announces "Option 5: Forge your own path"

**Dependencies:** None.

---

### 2.4 "Story So Far" Catch-Up Summary

**Problem:** Players returning after days away see truncated 200-char turn snippets that don't help them remember the story context.

**Files to modify:**
- `backend/app/api/v2_campaigns.py` — add `/v2/campaigns/{id}/summary` endpoint
- `backend/app/core/episodic_memory.py` — add `generate_story_summary()` function
- `frontend/src/routes/play/+page.svelte` — add "Story So Far" button/section

**Implementation:**

1. New backend endpoint `GET /v2/campaigns/{id}/summary`:
   - Loads the last 5 episodic memory entries
   - Loads the current arc stage and active quest names
   - Loads the narrative ledger's open threads
   - Assembles a structured summary:
     ```json
     {
       "arc_stage": "RISING",
       "current_beat": "TESTS_ALLIES_ENEMIES",
       "open_threads": ["The missing cargo", "Companion's secret"],
       "recent_memories": [
         "You arrived at the marketplace and met a mysterious informant...",
         "A tense negotiation with the local faction leader..."
       ],
       "active_quests": ["Find the stolen plans", "Earn the trust of Faction X"]
     }
     ```

2. Frontend: Show a "Story So Far" expandable section at the top of the play page, above the narrative. Collapsed by default, shows arc stage as a one-line indicator. Expand to see the full summary.

**Acceptance Criteria:**
- Players can see a meaningful summary of their campaign state in 2-3 seconds
- Summary includes arc stage, active quests, and recent narrative memories
- Works for campaigns at any stage (including turn 1)

**Dependencies:** None.

---

## Phase 3: Long-Running Adventures Infrastructure

*Goal: Build the systems needed for Luke/Kirk-style multi-campaign character persistence.*

### 3.1 Address Long-Campaign Performance: world_state_json Growth + Commit-Node Agent Sprawl

**Problem (corrected):** The original review claimed `apply_projection()` replays full event history per turn. This is **incorrect** -- `projections.py:apply_projection()` operates on the current turn's events only, writing directly to SQLite. The `state_reducer.py:reduce_events()` is a pure in-memory function used for testing/reconstruction, not the main pipeline.

The **actual** scaling concerns for long campaigns are:

1. **`world_state_json` blob growth**: Everything accumulates in one JSON column -- party state, faction reputation, NPC states, quest log, ledger, banter queue, era summaries, world_sim_events (capped at 50), etc. As campaigns grow, this blob grows, and it's loaded/parsed/saved every turn.

2. **Commit node LLM agent sprawl**: The commit node at `commit.py:133-336` triggers multiple LLM agents inside the "single transaction boundary": ContinuityAgent (line 139), MemoryAgent, QuestWeaver, Progression, PsychArchivist. These add latency to every turn, even though most are non-critical.

3. **Era summary compression reads**: `commit.py:160-171` reads events since the last compression point via `_get_events()`. As campaigns grow, the gap between compressions grows.

**Files to modify:**
- `backend/app/core/nodes/commit.py` — move non-critical agents to a deferred batch
- `backend/app/constants.py` — add batch frequency constants

**Implementation:**

1. **Batch non-critical commit agents**: Move ContinuityAgent, PsychArchivist, Progression, and QuestWeaver out of the per-turn commit path. Run them as a "maintenance batch" every N turns:

```python
# In commit_node:
MAINTENANCE_AGENT_FREQUENCY = 5  # Run non-critical agents every 5 turns

if next_turn_number % MAINTENANCE_AGENT_FREQUENCY == 0:
    # Run ContinuityAgent, PsychArchivist, Progression, QuestWeaver
    ...
else:
    # Skip non-critical agents this turn (save 3-10 seconds)
    ...
```

2. **Cap world_state_json subsections**: Add FIFO limits to the largest growing sections:
   - `world_sim_events`: already capped at 50 (good)
   - `era_summaries`: capped at `MEMORY_MAX_ERA_SUMMARIES` (5) (good)
   - `npc_states`: cap at 30 most-recently-interacted NPCs
   - `companion_memories`: cap at `COMPANION_MAX_MEMORIES` (10) per companion (already exists)

3. **Future (Phase 3+):** Extract `quest_log`, `npc_states`, and `party_state` into dedicated tables for O(1) indexed access instead of JSON parsing.

**Acceptance Criteria:**
- Turn latency decreases by 3-10 seconds on "heavy" turns (when maintenance agents would have fired)
- Non-critical agents still run every 5 turns (no data loss, just less frequent updates)
- world_state_json blob size stays bounded even at 500+ turns
- All existing tests pass

**Dependencies:** 1.5 (telemetry data to validate which agents to batch).

---

### 3.2 Tiered Memory System

**Problem:** Current memory is too aggressive: 300 chars per era summary x 5 max = 1,500 chars total. A 200-turn campaign compresses to one paragraph. Key relationships and emotional beats are lost.

**Files to modify:**
- `backend/app/constants.py` — new memory tier constants
- `backend/app/core/episodic_memory.py` — implement tiered storage and retrieval
- `backend/app/db/migrations/0025_memory_tiers.sql` — new table for crystallized memories

**Implementation:**

1. **New constants:**
```python
# Tiered memory system
MEMORY_HOT_TURNS = 10           # Full text, always in context
MEMORY_WARM_TURNS = 50          # 1-sentence summaries, retrieved by relevance
MEMORY_COLD_MAX_SUMMARIES = 20  # 3-5 sentence arc summaries, stored permanently
MEMORY_COLD_SUMMARY_MAX_CHARS = 800  # Up from 300
MEMORY_CRYSTALLIZED_MAX = 25    # Player-marked or system-detected important moments
```

2. **New migration** — `0025_memory_tiers.sql`:
```sql
-- V7.0: Crystallized memories — important moments that are never compressed.
CREATE TABLE IF NOT EXISTS crystallized_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    memory_type TEXT NOT NULL,  -- 'player_marked', 'companion_event', 'arc_climax', 'death', 'betrayal'
    summary TEXT NOT NULL,
    full_text TEXT,
    npcs_involved TEXT,  -- JSON array
    location TEXT,
    emotional_tag TEXT,  -- 'triumph', 'loss', 'revelation', 'bond', 'conflict'
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_crystallized_campaign
    ON crystallized_memories(campaign_id);
```

3. **Auto-crystallize important moments** in the Commit node:
   - Companion loyalty threshold events (affinity crosses TRUSTED or LOYAL)
   - Arc climax beats (ORDEAL, RESURRECTION)
   - Character death events
   - Quest completion events
   - Player can manually mark turns via a "Remember This" button in the UI

4. **Retrieval priority** in `episodic_memory.recall()`:
   - Always include relevant crystallized memories (highest priority)
   - Then warm memories by relevance score
   - Then cold arc summaries for background context
   - Budget: crystallized gets 40% of token budget, warm gets 40%, cold gets 20%

**Acceptance Criteria:**
- A 500-turn campaign retains its 25 most important moments in full detail
- Crystallized memories appear in narrator context for relevant scenes
- Players can mark moments as important via UI button
- Memory retrieval is relevance-weighted (crystallized > warm > cold)

**Dependencies:** 3.1 (snapshot system should be in place for long campaigns).

---

### 3.3 Character Legacy System

**Problem:** When a campaign ends, almost nothing meaningful transfers to the next campaign. The completion page shows stats and a "next campaign pitch" but no emotional or relational continuity.

**Files to create:**
- `backend/app/core/agents/legacy_agent.py` — generates Character Legacy document
- `backend/app/db/migrations/0026_character_legacy.sql`

**Files to modify:**
- `backend/app/api/v2_campaigns.py` — add legacy generation to completion flow
- `backend/app/core/agents/campaign_bible_agent.py` — accept legacy as input for new campaigns
- `frontend/src/routes/complete/+page.svelte` — display legacy document

**Implementation:**

1. **New migration** — `0026_character_legacy.sql`:
```sql
CREATE TABLE IF NOT EXISTS character_legacies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    saga_id TEXT,
    legacy_json TEXT NOT NULL,  -- structured legacy document
    created_at TEXT DEFAULT (datetime('now'))
);
```

2. **Legacy document structure** (generated by LegacyAgent at campaign end):
```json
{
    "character_name": "Kira Voss",
    "saga_chapter": 1,
    "key_relationships": [
        {"name": "Commander Thane", "relationship": "mentor", "status": "alive", "sentiment": "deep respect, tinged with guilt over failing to save his squadron"},
        {"name": "Vex", "relationship": "rival-turned-ally", "status": "unknown", "sentiment": "grudging respect after the siege of Nar Shaddaa"}
    ],
    "unresolved_threads": [
        "The encrypted datapad from the dead operative — never decoded",
        "Faction X's ultimatum: choose a side by the next summit"
    ],
    "emotional_state": "Hardened but hopeful. Carries guilt from the Ord Mantell mission but found renewed purpose in the Alliance.",
    "reputation": "Known in the Outer Rim as a reliable operator. The Empire has a low-priority bounty. Hutt Cartel considers her a useful neutral party.",
    "philosophy_shift": "Started as a pragmatic survivor. Now believes some causes are worth dying for — but still picks her battles carefully.",
    "key_possessions": [
        {"item": "Thane's signet ring", "significance": "Reminder of what leadership costs"},
        {"item": "Modified DL-44", "significance": "Won in a sabacc game on Nar Shaddaa — first real score"}
    ],
    "crystallized_memories_summary": "Escaped the destruction of Echo Station. Earned Commander Thane's trust by holding the line at Ord Mantell. Lost two squad members in the Kessel extraction. Discovered Vex was a double agent — and chose to let her go."
}
```

3. **Integration with CampaignBibleAgent:**

When creating a new campaign with a legacy, inject the legacy document into the bible generation prompt:
```
RETURNING CHARACTER CONTEXT:
{character_name} is continuing their story from a previous campaign.
Key relationships: {formatted_relationships}
Unresolved threads: {formatted_threads}
Emotional state: {emotional_state}

INSTRUCTION: Weave at least 2 of these unresolved threads into the new campaign's quest arcs.
Reference at least 1 key relationship (as a returning NPC, a mentioned name, or an echo).
The character's emotional state should influence the opening tone.
```

**Acceptance Criteria:**
- Campaign completion generates a Character Legacy document
- Legacy is displayed on the completion page
- New campaigns can reference a legacy from a previous campaign
- At least 2 unresolved threads carry forward into the new campaign's bible
- Player sees narrative continuity ("Commander Thane sends a transmission..." in Campaign 2)

**Dependencies:** Phase 1 complete. Ideally 3.2 (crystallized memories feed into legacy generation).

---

### 3.4 Saga / Campaign / Universe Hierarchy

**Problem:** There's no structural concept for a series of connected campaigns. The player_profiles table exists but isn't wired to a "saga" concept.

**Files to create:**
- `backend/app/db/migrations/0027_sagas.sql`

**Files to modify:**
- `backend/app/api/v2_campaigns.py` — saga CRUD endpoints
- `backend/app/api/campaign_models.py` — saga models
- `frontend/src/routes/+page.svelte` — saga-aware campaign listing

**Implementation:**

1. **New migration:**
```sql
CREATE TABLE IF NOT EXISTS sagas (
    id TEXT PRIMARY KEY,
    player_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,  -- era pack setting_id (e.g., "star_wars_legends", "forgotten_realms")
    title TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

ALTER TABLE campaigns ADD COLUMN saga_id TEXT REFERENCES sagas(id);
ALTER TABLE campaigns ADD COLUMN saga_chapter INTEGER DEFAULT 1;
```

2. **Frontend changes:**
   - Home page groups campaigns by saga
   - "Continue Saga" button after campaign completion → creates new campaign in same saga
   - Saga view shows a timeline of completed campaigns with legacy summaries

**Acceptance Criteria:**
- Campaigns can belong to a saga
- Campaign completion offers "Continue Saga" (creates next chapter in same saga)
- Sagas carry the Character Legacy chain forward
- Home page groups campaigns by saga with chapter numbers

**Dependencies:** 3.3 (Character Legacy).

---

## Phase 4: Historical & Sandbox Mode Enforcement

*Goal: Make Historical mode actually enforce canon, and make Sandbox mode feel consequential.*

### 4.1 Canon Timeline as Immutable Truth Facts

**Problem:** Historical mode tells the CampaignBibleAgent "canon is immutable" in the prompt, but there's no runtime enforcement. The Narrator can still contradict canon events.

**Files to create:**
- `backend/app/db/migrations/0023_truth_immutable.sql` — add `is_immutable` column to existing truth_facts table

**Files to modify:**
- `backend/app/core/campaign_init.py` — seed immutable facts from era timeline at campaign creation
- `backend/app/core/truth_ledger.py` — respect `is_immutable` flag in upserts and contradiction checks

**Implementation:**

1. New migration to add immutability column (truth_facts table already exists via 0019):
```sql
-- V7.0: Add immutability flag for canon facts in Historical campaign mode.
ALTER TABLE truth_facts ADD COLUMN is_immutable INTEGER DEFAULT 0;
```

2. At campaign creation (Historical mode only), seed facts from `legends_timeline.key_events`:
```python
if campaign_mode == "historical":
    for event in era_pack.legends_timeline.get("key_events", []):
        truth_ledger.upsert_facts(conn, campaign_id, {
            f"canon_event_{hash(event)[:8]}": event
        }, is_immutable=True)
```

3. In `contradiction_errors()`, immutable facts can never be overridden:
```python
if existing_fact.is_immutable and new_value != existing_fact.value:
    errors.append(f"CANON VIOLATION: Cannot change '{fact_key}' — this is established {historical_lore_label}")
```

4. Surface canon violations as Director constraints:
```
HARD CONSTRAINT: The following events are canon and MUST NOT be contradicted:
- The Death Star was destroyed at the Battle of Yavin in 0 BBY
- Emperor Palpatine died at the Battle of Endor in 4 ABY
```

**Acceptance Criteria:**
- Historical campaigns seed canon events as immutable truth facts
- Narrator context includes canon constraints
- `contradiction_errors()` catches and flags canon violations
- Sandbox campaigns do NOT seed immutable facts (canon is mutable)

**Dependencies:** None (truth_facts table already exists in migration 0019).

---

### 4.2 Canon Character Proximity Zones

**Problem:** In Historical mode, players shouldn't be able to alter canonical characters' fates or be present at canon-critical moments. But they should be able to see and briefly interact with these characters for immersion.

**Files to modify:**
- `backend/app/world/era_pack_models.py` — add `canon_characters` schema to era packs
- `backend/app/core/nodes/encounter.py` — enforce proximity rules
- Era pack YAML files — add `canon_characters` definitions

**Implementation:**

1. Add `canon_characters` to era pack schema:
```yaml
# In era.yaml:
canon_characters:
  - name: Luke Skywalker
    proximity: cameo        # cameo | interaction | exclusion
    locations: [loc-cantina, loc-rebel-base]
    exclusion_events: ["Battle of Yavin trench run", "Bespin confrontation"]
  - name: Darth Vader
    proximity: cameo
    locations: [loc-imperial-ship]
    exclusion_events: ["Bespin confrontation", "Endor throne room"]
```

2. In `encounter_node`, check proximity rules before allowing NPC appearance:
   - **Cameo**: Can appear in scene description ("You spot a young man in pilot's gear across the hangar"). No dialogue options.
   - **Interaction**: Can have brief dialogue. Player cannot make choices that affect this NPC's fate.
   - **Exclusion**: Player is redirected away from exclusion events ("Your orders pull you to a different sector during the battle").

**Acceptance Criteria:**
- Canon characters appear as flavor text in Historical campaigns
- Players cannot influence canon characters' fates
- Exclusion events redirect the player narratively
- Sandbox mode ignores proximity rules entirely

**Dependencies:** 4.1 (canon enforcement infrastructure).

---

### 4.3 Sandbox Impact Tiers (Ripple / Wave / Tsunami)

**Problem:** Sandbox mode needs guardrails. Without them, players can make absurd galactic changes on Turn 3.

**Files to modify:**
- `backend/app/core/agents/choice_crafter_agent.py` — tag choices with impact tier
- `backend/app/core/nodes/mechanic.py` — scale DC and requirements by impact tier
- `backend/app/constants.py` — impact tier definitions

**Implementation:**

1. Define impact tiers:
```python
SANDBOX_IMPACT_TIERS = {
    "ripple": {"dc_modifier": 0, "min_arc_stage": "SETUP", "description": "Local effects only"},
    "wave": {"dc_modifier": 5, "min_arc_stage": "RISING", "description": "Regional consequences"},
    "tsunami": {"dc_modifier": 10, "min_arc_stage": "CLIMAX", "description": "Galaxy-altering event"},
}
```

2. ChoiceCrafter tags high-impact choices:
   - Killing a named faction leader = wave
   - Destroying infrastructure = wave
   - Actions affecting canon events = tsunami
   - Tsunami choices require multi-turn quest chains (can't happen in one action)

3. MechanicAgent applies DC modifiers based on impact tier

**Acceptance Criteria:**
- Sandbox choices are tagged with impact tiers
- Tsunami-level changes require CLIMAX arc stage and high DC
- Players can reshape the world but it takes narrative work

**Dependencies:** 1.2 (ChoiceCrafter improvements).

---

## Phase 5: Immersion Enhancements

*Goal: Transform the experience from "reading a story" to "living in a world."*

### 5.1 Ambient Audio System

**Files to create:**
- `frontend/src/lib/audio/AudioManager.ts` — audio playback manager
- `frontend/src/lib/audio/ambientMap.ts` — location-type to audio track mapping
- `frontend/static/audio/` — royalty-free ambient loops (5-10 tracks)

**Implementation:**

1. Create an `AudioManager` singleton that:
   - Plays looping ambient tracks based on current location type
   - Cross-fades between tracks on location change (2-second fade)
   - Respects a user preference toggle (off by default)
   - Volume slider in settings

2. Location-type mapping:
```typescript
const AMBIENT_MAP: Record<string, string> = {
    "cantina": "/audio/ambient-cantina.ogg",
    "tavern": "/audio/ambient-tavern.ogg",
    "starship": "/audio/ambient-ship-hum.ogg",
    "forest": "/audio/ambient-forest.ogg",
    "city": "/audio/ambient-city.ogg",
    "combat": "/audio/ambient-tension.ogg",
    "default": "/audio/ambient-neutral.ogg",
};
```

3. On each turn response, extract location type from `scene_frame` and update the ambient track.

**Acceptance Criteria:**
- Ambient audio plays and loops per location type
- Smooth cross-fade on location change
- User can toggle audio on/off and adjust volume
- No audio plays by default (opt-in)
- Mobile-compatible (respects autoplay restrictions)

**Dependencies:** None (can run in parallel with any phase).

---

### 5.2 Local Image Generation for Character Portraits

**Files to create:**
- `backend/app/image/portrait_generator.py` — Stable Diffusion integration
- `backend/app/api/v2_portraits.py` — portrait generation endpoint

**Files to modify:**
- `frontend/src/routes/create/+page.svelte` — show portrait on character sheet
- `frontend/src/lib/components/game/CompanionSidebar.svelte` — show companion portraits

**Implementation:**

1. Use `diffusers` library with SDXL Turbo or Flux Schnell (runs on RTX 4070):
```python
from diffusers import AutoPipelineForText2Image
import torch

pipe = AutoPipelineForText2Image.from_pretrained(
    "stabilityai/sdxl-turbo",
    torch_dtype=torch.float16,
    variant="fp16",
)
pipe.to("cuda")

def generate_portrait(species: str, gender: str, background: str, setting_genre: str) -> bytes:
    prompt = f"Portrait of a {gender} {species}, {background}, {setting_genre} style, detailed face, dramatic lighting"
    image = pipe(prompt=prompt, num_inference_steps=4, guidance_scale=0.0).images[0]
    # Return as PNG bytes
```

2. Generate portrait once at character creation (not per-turn)
3. Store as a file in `data/portraits/{campaign_id}.png`
4. Serve via static file route or base64 in API response

**Hardware consideration:** SDXL Turbo generates 512x512 in ~1 second on a 4070. Ollama must release VRAM first, so generate portrait BEFORE starting the first turn's LLM calls.

**Acceptance Criteria:**
- Character portrait generated at creation (optional, toggle-able)
- Portrait appears in info drawer and character sheet
- Generation takes <3 seconds on RTX 4070
- No VRAM conflict with Ollama (sequential, not parallel)

**Dependencies:** None (but nice to have Phase 1 complete for overall polish).

---

## Phase 6: Quality-of-Life & Polish

### 6.1 Quick Start Character Creation

**Files to modify:**
- `frontend/src/routes/create/+page.svelte` — add Quick Start path
- `backend/app/api/campaign_setup.py` — add defaults-based setup

**Implementation:**

1. Add a "Quick Start" button on the first creation screen
2. Auto-selects: random name, random gender, default era (Rebellion), random species, random background, all default CYOA answers, medium difficulty
3. Skips directly to the character sheet review step
4. Player can still edit the name and review before starting

**Acceptance Criteria:**
- Player can go from launch to playing in <30 seconds
- Quick Start produces a viable, interesting character
- Player can still customize the name before starting

**Dependencies:** None.

---

### 6.2 Agent Execution Matrix Documentation

**Files to create:**
- `docs/10_agent_execution_matrix.md`

**Implementation:**

Document which agents fire on which turn types and at what frequency:

| Agent | Turn Type | Frequency | LLM? | Authoritative? |
|-------|-----------|-----------|------|----------------|
| IntentRouter | ALL | Every turn | Yes (fast) | No |
| MechanicAgent | ACTION | Every ACTION turn | No | No |
| EncounterManager | ACTION, TALK | Every turn | No | No |
| WorldMindAgent | ALL | Every 4h in-game | Yes | No |
| CompanionSystemAgent | ACTION, TALK | Every turn | Yes | No |
| DirectorAgent | ACTION, TALK | Every turn | Yes | No |
| NarratorAgent | ACTION, TALK | Every turn | Yes | **Yes** |
| ChoiceCrafterAgent | ACTION, TALK | Every turn | Yes | **Yes** (with fallback) |
| PsychArchivistAgent | ALL | Every 5 turns | Yes | No |
| ProgressionAgent | ALL | Every 10 turns | Yes | No |
| QuestWeaverAgent | ACTION | On quest-relevant turns | Yes | No |
| ArcWeaverAgent | ALL | On arc transitions | Yes | No |
| ContinuityAgent | ALL | Every 5 turns | Yes | No |
| MemoryAgent | ALL | Every turn | Yes | No |

**Total LLM calls per normal turn:** 3-4 (Director + Narrator + ChoiceCrafter + sometimes WorldMind)
**Total LLM calls on "heavy" turn:** 6-8 (above + PsychArchivist + Progression + QuestWeaver + Continuity)

**Acceptance Criteria:**
- Matrix is accurate (verified against `graph.py` and node implementations)
- Each agent's firing conditions are documented
- Total call counts per turn type are clear

**Dependencies:** None.

---

### 6.3 Frontend Test Foundation

**Files to create:**
- `frontend/vitest.config.ts`
- `frontend/src/lib/components/__tests__/DialogueWheel.test.ts`
- `frontend/src/lib/stores/__tests__/streaming.test.ts`
- `frontend/src/lib/stores/__tests__/game.test.ts`

**Implementation:**

1. Set up Vitest + @testing-library/svelte
2. Write initial tests for the 3 most critical components:
   - **DialogueWheel**: Renders 4 choices, keyboard shortcuts work, tone colors correct
   - **streaming store**: startStreaming/appendToken/finishStreaming state transitions
   - **game store**: Campaign load/reset, turn number increment

**Acceptance Criteria:**
- `npm test` runs in frontend and passes
- At least 10 initial tests covering the core game loop components
- CI runs frontend tests alongside backend tests

**Dependencies:** None.

---

## Phase Summary & Dependency Graph

```
Phase 1 (Critical Fixes) ─── No dependencies, do first
  ├── 1.1 [RESOLVED] Truth Ledger Migration — tables already exist in 0019
  ├── 1.2 ChoiceCrafter 4-Choice Fallback
  ├── 1.3 Star Wars Residue Audit
  ├── 1.4 Unify Streaming Path (legacy suggestion_refiner → choice_crafter) ← needs 1.2
  ├── 1.5 Per-Agent Latency Telemetry
  └── 1.6 Ollama Unavailable UI

Phase 2 (Core Loop Polish) ─── After Phase 1
  ├── 2.1 Dynamic Narrator Word Limits
  ├── 2.2 Parallel Context Prep (latency)
  ├── 2.3 Free Text Redesign
  └── 2.4 Story So Far Summary

Phase 3 (Long-Running Adventures) ─── 3.1 needs 1.5; 3.3 needs 3.2; 3.4 needs 3.3
  ├── 3.1 Long-Campaign Perf (commit agent batching + world_state_json caps) ← needs 1.5 telemetry
  ├── 3.2 Tiered Memory System
  ├── 3.3 Character Legacy System ← needs 3.2
  └── 3.4 Saga Hierarchy ← needs 3.3

Phase 4 (Historical/Sandbox) ─── 4.2 needs 4.1; 4.3 needs 1.2
  ├── 4.1 Canon Timeline Enforcement (immutable truth facts)
  ├── 4.2 Proximity Zones ← needs 4.1
  └── 4.3 Sandbox Impact Tiers ← needs 1.2

Phase 5 (Immersion) ─── Independent, can run in parallel
  ├── 5.1 Ambient Audio
  └── 5.2 Local Image Generation

Phase 6 (Polish) ─── Independent, can run anytime
  ├── 6.1 Quick Start Creation
  ├── 6.2 Agent Execution Matrix Docs
  └── 6.3 Frontend Test Foundation
```

---

## Estimated Effort

| Phase | Tasks | Estimated Complexity | Recommended Order |
|-------|-------|---------------------|-------------------|
| Phase 1 | 5 active tasks (+1 resolved) | Low-Medium | **First** (correctness + data collection) |
| Phase 2 | 4 tasks | Medium | **Second** (biggest UX impact) |
| Phase 3 | 4 tasks | High | **Third** (enables the long-term vision) |
| Phase 4 | 3 tasks | Medium-High | **Fourth** (refines game modes) |
| Phase 5 | 2 tasks | Medium | **Anytime** (independent) |
| Phase 6 | 3 tasks | Low-Medium | **Anytime** (independent) |

**Total: 21 active tasks across 6 phases (+1 resolved).**

Phase 1 is the foundation — correctness fixes plus telemetry to make data-driven decisions about latency. Phase 2 is the highest-impact for player experience. Phase 3 is the highest-impact for the long-term vision. Phases 5 and 6 can be interleaved at any point.

---

## Corrections Log

*Corrections applied after cross-review validation:*

| Original Claim | Correction | Source |
|----------------|------------|--------|
| "Truth Ledger tables missing from migrations" (Blocker) | Tables exist in `0019_turn_contract_passages.sql`. Known issues doc entry is stale. | Verified: `0019_turn_contract_passages.sql:1-16` |
| "ChoiceCrafter has no fallback — game gets stuck" (Blocker) | Fallback exists (`_make_fallback_choices()` at `choice_crafter_node.py:148`). Degrades to 2 choices, not a hard stop. Upgraded to "UX issue, not blocker." | Verified: `choice_crafter_node.py:148-174, 283` |
| "`apply_projection()` is O(N) full history replay per turn" (Medium-High) | `projections.py:apply_projection()` operates on current turn's events only. `state_reducer.py:reduce_events()` is O(N) but only used for testing/reconstruction, not per-turn. Real scaling concerns: world_state_json growth + commit-node LLM agent sprawl. | Verified: `projections.py:67-283`, `commit.py:133-336` |
| "Streaming path uses main graph pipeline" (Implicit assumption) | Streaming path at `v2_campaigns.py:1302` uses legacy `suggestion_refiner`, not the V5.0 `choice_crafter_node`. Two divergent code paths exist. | Verified: `v2_campaigns.py:1291-1308` |
| "Turn latency is 3 LLM calls" (Understated) | Commit node triggers additional LLM agents: ContinuityAgent, MemoryAgent, QuestWeaver, Progression, PsychArchivist. Heavy turns may have 6-8+ LLM calls. | Verified: `commit.py:133, 272, 336` |
