# Storyteller-V2: Comprehensive Review & Analysis

*Reviewed by: Senior Engineer, Game Designer, Story Writer, UX/UI Designer, and RPG enthusiast*

---

## Table of Contents

1. [What You're Building & Vision Assessment](#1-what-youre-building)
2. [Architecture Deep-Dive & Honest Feedback](#2-architecture)
3. [User Experience Analysis](#3-ux-analysis)
4. [Cost-Saving & The Hybrid Approach](#4-cost-saving)
5. [Hardware Constraints (RTX 4070 / 32GB DDR4 / Ryzen 7)](#5-hardware)
6. [Long-Running Adventures (The Star Wars / Star Trek Problem)](#6-long-running)
7. [Historical vs Sandbox Mode Analysis](#7-historical-vs-sandbox)
8. [What You Do Well (Strengths)](#8-strengths)
9. [Critical Issues & Risks](#9-critical-issues)
10. [Recommendations & Roadmap Priorities](#10-recommendations)

---

## 1. What You're Building & Vision Assessment <a id="1-what-youre-building"></a>

### The Vision

Storyteller-V2 is a **local-first, setting-agnostic narrative RPG engine** that aims to deliver a KOTOR-quality interactive fiction experience powered by LLMs. The core value proposition: a living, breathing story world that runs on your own hardware with no recurring API costs.

### Honest Assessment of the Vision

This is one of the most ambitious solo/small-team game projects I've seen in the AI-narrative space. The scope is enormous -- you've essentially built:

- A 13-node LangGraph pipeline that orchestrates deterministic mechanics + LLM storytelling
- A full SvelteKit frontend with KOTOR-inspired dialogue wheel
- An event-sourced persistence layer with 22 migrations
- A RAG pipeline with 4-lane style retrieval
- A companion system with 108 defined companions
- A living world simulation with faction politics
- An era pack system that already spans Star Wars AND Forgotten Realms
- A quest state machine, truth ledger, psychological profiling, and Hero's Journey arc planner

The ambition is clear: you want the narrative depth of a BioWare RPG, the replayability of a roguelike, and the cost profile of a local application. That's a genuinely compelling target.

**However, the project has a scope/completion tension.** V5.0 is architecturally sophisticated, but many systems exist at the "designed and scaffolded" level rather than the "battle-tested and polished" level. You've built wide rather than deep -- which is the right approach for proving the concept, but means the *experience* doesn't yet match the *architecture*.

---

## 2. Architecture Deep-Dive & Honest Feedback <a id="2-architecture"></a>

### What's Genuinely Excellent

**Single Transaction Boundary**
`backend/app/core/nodes/commit.py` is the only node that writes to SQLite. All other 12 nodes are pure functions. This is a textbook-quality pattern for a pipeline like this. If the Narrator fails, the DB is untouched. If the Director hallucinates, the game state is clean. This one decision prevents an entire class of corruption bugs.

**Event Sourcing**
The append-only `turn_events` table with projections rebuilt via `apply_projection()` in `state_reducer.py` is the right call for a narrative game. You can replay any campaign from scratch. You can add new projection logic without migrating old data. This is production-grade persistence design.

**Setting-Agnostic Era Packs**
The V6.0 era pack format (`era.yaml` + `backgrounds.yaml` + `species.yaml`, with CampaignBibleAgent generating the rest) is clean. The Forgotten Realms pack proves the architecture works beyond Star Wars. The `SettingRules` injection via `get_setting_rules(state)` means agents don't hardcode universe knowledge.

**Per-Role LLM Configuration**
`backend/app/config.py` lets you assign different models (and providers) to each agent role independently. This is the key enabler for your cost-saving strategy. The specialist swapping design (only one model loaded at a time) is smart for your 12GB VRAM constraint.

### Structural Concerns

**1. apply_projection() is O(N) over full event history (`state_reducer.py`)**

This is flagged in your known issues doc, but it's more urgent than "medium severity" suggests. A narrative RPG naturally produces long campaigns. At 200 turns, each turn replays 200 events. At 1000 turns (which your Luke/Leia/Kirk long-adventure vision implies), that's 1000+ events replayed per turn -- before any LLM call even starts.

**Recommendation:** Implement snapshot-based projections. Every N turns (say 50), snapshot the current projected state. On load, replay only from the last snapshot. This is a standard pattern in event-sourced systems and would make long campaigns viable.

**2. world_state_json is a monolithic JSON blob**

Everything lives in one `TEXT` column: party state, faction reputation, NPC states, quest log, ledger, banter queue, companion triggers, alignment, settings rules, campaign bible, and more. As the game grows, this blob will grow. Parsing it on every turn is already O(N) with the event replay.

**Recommendation:** For the short term this works. Long-term, extract hot-path data (party_state, npc_states, quest_log) into dedicated tables with proper indexing. This also enables querying across campaigns (e.g., "show me all campaigns where faction X is hostile").

**3. The Agent Explosion Problem**

You currently have ~20+ agent roles defined in `config.py`. Each has its own model assignment, timeout, token budget, and retry logic. The `core/agents/` directory has 20+ files. Many of these agents (PsychArchivist, Progression, ArcWeaver, Continuity, QuestWeaver) run conditionally on certain turns.

The concern: as you add more agents, the pipeline becomes harder to reason about. Which agents fire on which turns? What's the total LLM call count for a "heavy" turn? The graph in `graph.py` is already 1000+ lines.

**Recommendation:** Create a clear agent execution matrix: a table showing which agents fire on which turn types (ACTION/TALK/META) and at what frequency. This should be in your docs and enforced in code. Consider grouping infrequent agents into a "maintenance pass" that runs every N turns rather than checking every turn.

**4. Prompt Size and Token Budget Tension**

The narrator prompt (`narrator_prompt.py`) assembles an enormous context: story state summary, POV character block, campaign/location, narrative ledger, constraints, established facts, open threads, dynamic quests, psych profile, present NPCs with memory, mechanic events, director instructions, companion reactions, inter-party tensions, active rumors, active themes, scene context with voice profiles, and lore/style/voice RAG chunks.

With a default token budget of 8192 tokens max context for the narrator (6144 input after reserving 2048 for output), you're fighting a constant battle to fit everything. The trimming cascade in `context_budget.py` handles this, but it means that on complex scenes, the narrator is regularly operating with truncated context.

On local models like mistral-nemo (32K context window but only 8192 budgeted), you're leaving a lot of context window unused. On small models like qwen3:4b (4K-8K effective), the budget is extremely tight.

**Recommendation:** Consider dynamically adjusting token budgets based on scene complexity. A simple dialogue turn doesn't need the same context depth as a climactic confrontation with 3 NPCs and faction implications. Also consider raising the narrator budget to 12K-16K since mistral-nemo supports it -- the quality improvement from more context would be significant.

### Code Quality Assessment

- **Documentation:** Excellent. 13 markdown docs, inline comments, docstrings. Well above average for a project this size.
- **Type Safety:** Pydantic V2 models throughout. Type hints on almost everything. Strong.
- **Test Coverage:** 467+ passing tests. Backend agents, companion system, RAG retrieval, faction engine, arc planner all have tests. Solid foundation.
- **Error Handling:** `AgentFailureError` with `authoritative_call()` pattern is clean. Non-authoritative graceful degradation is well-implemented.
- **Code Organization:** Clear separation between agents, nodes, models, RAG, persistence. The `core/` directory is large but well-structured.

---

## 3. User Experience Analysis <a id="3-ux-analysis"></a>

### The Good: What Works Well

**KOTOR Dialogue Wheel**
`frontend/src/lib/components/choices/DialogueWheel.svelte` implements a vertical card-based choice system with 4 tones (PARAGON/INVESTIGATE/RENEGADE/NEUTRAL), risk levels, consequence hints, and companion reaction previews. This is the single most important UX decision in the game, and it's well-executed:
- Keyboard shortcuts (1-4) for fast selection
- Hover reveals risk/consequence details (progressive disclosure)
- Tone colors provide instant emotional reading
- Staggered entrance animations give each choice weight

This creates a genuine "which path do I choose?" moment every turn, which is the core loop of a narrative RPG.

**Theme System**
5 themes (Old Republic, Clean Dark, Rebel Amber, Alliance Blue, Holocron Archive) with full CSS custom property support. The KOTOR 2 chamfered corners and scanline overlays are a nice touch. Players who want immersion get it; players who want readability can switch to Clean Dark.

**Info Drawer**
The tabbed right-side drawer (Character / Companions / Factions / Inventory / Quests / Comms / Journal) consolidates all game state without cluttering the main narrative view. The mobile-responsive bottom-sheet variant is well-thought-out.

**Accessibility**
ARIA labels, live regions for screen reader announcements, keyboard navigation, focus management, reduced-motion support. This is genuinely above-average for a game project. The screen reader announcing "Choices are now available. Press 1 through 4 to select" is a thoughtful touch.

### Pain Points (from a player perspective)

**1. Turn Latency is the #1 UX Problem**

With 3 LLM calls per turn (Director + Narrator + ChoiceCrafter), plus RAG retrieval, plus event projection, the total turn time on local hardware is likely **15-40 seconds** depending on model and context size. For a narrative game where the core loop is "read story -> make choice -> read story," this is a significant drag on flow state.

The SSE streaming helps (you see text arrive), but the choice crafter runs *after* the narrator, so even with streaming, there's a dead gap between "narrative finishes" and "choices appear."

**Recommendations:**
- **Pre-generate choices in parallel with narration** if architecturally feasible. The scene_frame and director_instructions are available before the narrator runs -- the ChoiceCrafter could theoretically run from those same inputs simultaneously.
- **Show a "thinking" animation** for the choice gap specifically (not just a spinner -- something thematic, like a holocomm loading or a character contemplating).
- **Cache speculative choices**: When the player hovers over a choice but hasn't clicked yet, begin speculatively assembling the next turn's context in the background.

**2. The Opening Experience is Overwhelming**

Character creation is multi-step (name -> gender -> era -> species -> background -> CYOA questions -> difficulty -> companion preview -> review). For a new player, this is a lot of decisions before they've seen any story. They're choosing species and backgrounds for a world they haven't experienced yet.

**Recommendations:**
- **"Quick Start" option**: Auto-generate a character with sensible defaults. Let the player jump into the story in 2 clicks. They can customize later or restart with full creation.
- **In-media-res opening**: Show a brief prologue *before* character creation. Let the player experience the tone and world first, then ask them to build their character. BioWare does this (Mass Effect 2 opens with the Normandy being destroyed before you customize Shepard).

**3. Narrative Text is Capped at 250 Words**

`narrator_prompt.py` enforces "5-8 sentences, max 250 words." For some scenes -- particularly climactic confrontations, emotional revelations, or complex multi-NPC encounters -- this feels restrictive. KOTOR's major dialogue scenes could run much longer.

**Recommendation:** Make the word limit dynamic based on scene type. Opening scenes, arc climaxes (ORDEAL beat), and companion loyalty missions should allow 400-500 words. Standard exploration turns can stay at 200-250.

**4. No Audio Feedback**

The frontend is entirely silent. No ambient music, no sound effects, no dialogue beeps. For a game targeting immersion ("get immersed into a different world"), this is a significant gap. Audio is one of the most powerful immersion tools -- a cantina ambient track, a lightsaber hum, rain on a viewport -- can transform text from "reading" to "experiencing."

**Recommendations:**
- **Phase 1**: Ambient background loops per location type (cantina, starship, forest, city). 5-10 tracks from royalty-free libraries. Low-effort, high-impact.
- **Phase 2**: UI sound effects (choice select, turn submit, notification chime). Subtle, KOTOR-inspired.
- **Phase 3**: Dynamic music that shifts with genre triggers (noir -> jazz, war -> drums, horror -> silence + drone). You already have genre detection in `genre_triggers.py`.

**5. No Visual Storytelling**

No character portraits, scene illustrations, or maps. The game is pure text. For players who read novels, this is fine. For players who grew up on visual RPGs, this is a barrier to immersion.

**Recommendations:**
- **Character Portraits**: At character creation, generate a portrait via Stable Diffusion (local on your RTX 4070) or use a small portrait library. Show it in the info drawer.
- **Scene Mood Images**: Generate a single atmospheric image per location type (not per turn -- too expensive). Show it as a subtle background or header. Your 4070 can run SDXL Turbo or Flux Schnell locally.
- **Map**: A simple node-based travel map showing visited locations and connections. Doesn't need to be generated -- can be procedurally laid out from the location graph.

**6. Free Text Input Feels Like an Afterthought**

The game offers both the dialogue wheel AND a free text input. This creates an identity crisis: is this a choice-based game (like KOTOR) or an open-ended text adventure (like AI Dungeon)? The free text input sits below the dialogue wheel with a plain "What do you do?" prompt.

**Recommendation:** Make the free text input a deliberate "5th option" rather than an alternative system. Label it "Forge Your Own Path" with a brief tooltip: "Ignore the choices above and describe your own action." This frames it as the rebellious choice rather than a competing input method.

**7. The "Previously..." Section Needs Work**

Past turns are shown as an accordion with "first 200 chars of text." For a player returning to a saved game after days away, 200 truncated characters per turn doesn't help them remember where they were.

**Recommendation:** Show a "Story So Far" summary (3-5 sentences) generated from era summaries or the episodic memory system. Your memory compression system already produces these -- surface them in the UI as a "Catch-up" feature.

---

## 4. Cost-Saving & The Hybrid Approach <a id="4-cost-saving"></a>

### Your Current Cost Model

| Usage | Provider | Cost |
|-------|----------|------|
| Per-turn (Director + Narrator + ChoiceCrafter) | Ollama (local) | $0 |
| Per-turn (WorldSim, on tick turns) | Ollama (local) | $0 |
| Campaign creation (CampaignBibleAgent) | Ollama default, cloud optional | $0 - $0.10 |
| Lore ingestion | Local embeddings | $0 |
| RAG retrieval | Local LanceDB | $0 |

**The local-only cost is genuinely $0 per session.** This is a real achievement. The only costs are electricity and the initial hardware investment.

### The Hybrid Trade-off

Your hybrid approach (local for per-turn, optional cloud for one-shot high-value calls) is sound. The key insight is correct: **per-turn costs scale linearly with playtime, but one-shot costs are fixed per campaign.** A CampaignBibleAgent call via Claude costs ~$0.05-0.15 and sets up the entire campaign. That's excellent value.

### Cost-Saving Analysis

**Where local models currently hurt quality:**

1. **Choice Crafter (qwen3:8b)**: The quality of the 4 choices is directly proportional to how engaging each turn feels. A mediocre choice set makes the game feel like "pick the obvious good option." A great choice set makes you agonize. Cloud models (Claude, GPT-4o) produce significantly better choices because they understand narrative subtext, moral ambiguity, and dramatic irony.

2. **Narrator (mistral-nemo)**: mistral-nemo is a capable model for prose, but it struggles with:
   - Maintaining consistent character voice across long conversations
   - Subtle emotional beats (a character hiding their feelings while saying something positive)
   - Complex multi-NPC scenes where each character needs a distinct reaction
   Cloud narrators produce noticeably richer prose.

3. **Campaign Bible (qwen3:8b local)**: The campaign bible is the single highest-leverage LLM call. It generates the conflict web, NPC relationships, quest hooks, and thematic throughline for the entire campaign. A mediocre bible means a mediocre campaign. This is where cloud quality pays for itself.

**Recommended Hybrid Strategy for Cost-Conscious Quality:**

| Role | Recommended | Estimated cost/campaign |
|------|-------------|------------------------|
| Campaign Bible | Cloud (Claude Sonnet / GPT-4o) | $0.05-0.15 (one-shot) |
| Director | Local (mistral-nemo) | $0 |
| Narrator | Local (mistral-nemo) | $0 |
| Choice Crafter | Local (qwen3:8b) | $0 |
| World Sim | Local (qwen3:8b) | $0 |
| All others | Local | $0 |

**Total per campaign: ~$0.10.** That's essentially free for a campaign that might last 100+ hours.

**If budget allows $1-5/campaign for premium quality:**

| Role | Recommended | Estimated cost/campaign |
|------|-------------|------------------------|
| Campaign Bible | Cloud (Claude Opus/Sonnet) | $0.10-0.30 |
| Director | Local (mistral-nemo) | $0 |
| Narrator | Cloud for climax scenes only | $0.50-2.00 |
| Choice Crafter | Cloud for key decisions | $0.30-1.00 |
| All others | Local | $0 |

This would require a "scene importance" detector that routes high-stakes scenes to cloud and routine scenes to local. You already have the arc planner and genre triggers to identify these moments.

---

## 5. Hardware Constraints (RTX 4070 / 32GB DDR4 / Ryzen 7) <a id="5-hardware"></a>

### Your Setup Analysis

| Component | Spec | Implication |
|-----------|------|-------------|
| GPU | RTX 4070 12GB VRAM | Can run mistral-nemo (7GB) or qwen3:8b (5GB) but not both simultaneously |
| RAM | 32GB DDR4 | Comfortable for the full stack (FastAPI + SvelteKit + SQLite + LanceDB + Ollama) |
| CPU | Ryzen 7 | Good for deterministic mechanics, event projection, and RAG retrieval |

### Current Fit

Your specialist swapping design (one model loaded at a time, peak VRAM ~7GB) is well-optimized for this GPU. The RTX 4070 has good inference speed for 7B-12B models via Ollama.

### Bottleneck Analysis

1. **Model loading/unloading**: When the pipeline switches from mistral-nemo (narrator) to qwen3:8b (choice crafter), Ollama may need to swap models. On 12GB VRAM, if both could fit (~12GB total), Ollama keeps them loaded. If not, there's a 2-5 second model load penalty per swap. With your current config (mistral-nemo 7GB + qwen3:8b 5GB = 12GB), it's tight but may fit.

2. **Inference speed**: mistral-nemo on a 4070 generates ~20-40 tokens/sec. For a 250-word narrator response (~350 tokens), that's ~9-18 seconds of pure inference. Add director (~5-10s) and choice crafter (~5-10s), and a full turn is 20-40 seconds of LLM time alone.

3. **RAG retrieval**: LanceDB vector search is CPU-bound. On a Ryzen 7, this is fast (sub-second for the retrieval sizes you're using).

4. **Image generation potential**: Your 4070 can run SDXL Turbo (generates 512x512 in ~1 second) or Flux Schnell. This makes local image generation viable for scene illustrations without any cloud cost.

### Optimization Recommendations

- **Keep Ollama's OLLAMA_NUM_PARALLEL=1** to avoid VRAM fragmentation.
- **Consider quantized models**: mistral-nemo Q4_K_M (~4GB) frees VRAM for keeping both models loaded simultaneously, potentially eliminating swap latency. Quality loss is measurable but modest for creative writing tasks.
- **Pre-load the next model**: While the narrator is generating, signal Ollama to warm up the choice crafter model in the remaining VRAM.
- **Batch inference for non-critical agents**: Run PsychArchivist, Progression, and other maintenance agents in a batch pass every N turns rather than checking every turn.

---

## 6. Long-Running Adventures (The Star Wars / Star Trek Problem) <a id="6-long-running"></a>

### The Vision

You want characters like Luke, Leia, Han, and Captain Kirk -- characters who persist across multiple story arcs, grow and change over time, and have adventures spanning different eras and contexts. This is fundamentally a **serial fiction** problem, not a single-campaign problem.

### Current State

Your architecture has some building blocks for this:
- **Era Transitions**: `era_transition.py` handles REBELLION -> NEW_REPUBLIC -> NEW_JEDI_ORDER progression
- **Episodic Memory**: `episodic_memory.py` compresses old turns into retrievable summaries
- **Era Summaries**: Every 100 turns (configurable), turns are compressed into 300-char summaries (max 5 retained)
- **Player Profiles**: Migration 0018 creates `player_profiles` for cross-campaign identity
- **Campaign Completion**: `/complete` page shows campaign summary with "Next Campaign Pitch"

### Critical Gaps

**1. Cross-Campaign Memory is Shallow**

When Campaign A ends and Campaign B begins with the same character, what carries over? Currently: player name, stats, and possibly a summary. But the *emotional* continuity -- "I'm still angry at Faction X because they betrayed my mentor in Campaign A" -- requires much deeper transfer.

**Recommendation:** Create a "Character Legacy" document at campaign end. This is a structured summary (generated by a dedicated agent) of:
- Key relationships (who do they trust, who do they distrust, and why)
- Unresolved emotional threads (grief, guilt, revenge, love)
- Reputation and accomplishments (how the world sees them)
- Personal philosophy shifts (how their choices changed them)
- Key possessions and their sentimental value

This legacy document becomes the seed for the next campaign's BiographerAgent prompt.

**2. Era Summaries Are Too Compressed**

300 characters per era summary, max 5 summaries = 1,500 characters of long-term memory. For a character who's lived through years of adventures, this is barely a paragraph. You'll lose the emotional resonance of past adventures.

**Recommendation:** Implement a tiered memory system:
- **Hot memory** (last 10 turns): Full text, always in context
- **Warm memory** (last 50 turns): 1-sentence summaries per turn, retrieved by relevance
- **Cold memory** (older): 3-5 paragraph summaries per arc/campaign, stored permanently
- **Crystallized memories**: Player-marked "important moments" that are never compressed -- the scene where their mentor died, the first time they used the Force, the betrayal at Cloud City

**3. Character Growth Feels Mechanical**

The `ProgressionAgent` handles stat growth, but narrative character growth (personality shifts, relationship evolution, moral development) is tracked only through the psych profile (mood, stress, trauma) and alignment indicators. There's no system for "this character started naive and became cynical" or "this character learned to trust again."

**Recommendation:** Implement a "Character Arc Ledger" -- distinct from the narrative ledger -- that tracks:
- Moral position over time (not just current alignment, but the trajectory)
- Key beliefs and when they were challenged or changed
- Relationship arcs with specific characters (not just affinity numbers)
- Internal conflicts (duty vs. desire, revenge vs. forgiveness)

The PsychArchivistAgent already scratches this surface. Promote it to a first-class system.

**4. The Serial Structure Needs Explicit Design**

Star Wars has Episodes. Star Trek has Seasons. Your game needs an equivalent structural metaphor.

**Recommendation:** Implement a three-tier structure:
- **Campaign** = A single story arc (Episode IV, Season 1). Has a beginning, middle, end. 50-200 turns.
- **Saga** = A series of connected campaigns with the same character (the Original Trilogy, TNG Seasons 1-7). Shares Character Legacy across campaigns.
- **Universe** = The setting itself (Star Wars, Forgotten Realms). Multiple sagas can exist in the same universe.

This gives players a natural stopping point (campaign end) while maintaining the thread of a longer story (saga). Each campaign can have its own genre, stakes, and supporting cast while the protagonist's arc continues.

---

## 7. Historical vs Sandbox Mode Analysis <a id="7-historical-vs-sandbox"></a>

### Current Implementation

`campaign_init.py` defines two modes:
- **Historical**: "Canon events are immutable. Generated content fits within established lore. Player choices affect personal story, not galactic history."
- **Sandbox**: "Player choices can reshape the galaxy. Generated content may diverge from canon. Factions can be altered by player actions."

The mode is set at campaign creation and affects the CampaignBibleAgent's generation prompt.

### Assessment

**Historical Mode** (your Hogwarts student example) is conceptually strong but implementation-thin. The current system tells the CampaignBibleAgent "canon events are immutable" in the prompt, but there's no runtime enforcement. Nothing prevents the Narrator from writing "you convinced Dumbledore to cancel the Triwizard Tournament" if the player's actions push that direction.

**Sandbox Mode** is easier to implement because there are fewer constraints. The LLM can freely extrapolate consequences. But it needs guardrails to prevent absurdity ("you convinced the Emperor to abolish the Empire on Turn 3").

### Recommendations for Historical Mode

**1. Canon Event Timeline as Hard Constraints**

The `legends_timeline` in `era.yaml` lists key events with dates. These should be promoted to Truth Ledger facts that the Narrator cannot contradict:

```
IMMUTABLE_FACT: "The Death Star was destroyed at the Battle of Yavin in 0 BBY"
IMMUTABLE_FACT: "Emperor Palpatine died at the Battle of Endor in 4 ABY"
```

The existing `contradiction_errors()` system in `truth_ledger.py` can enforce this if the timeline events are seeded as immutable facts at campaign creation.

**2. Proximity Zones**

Canon characters (Luke, Leia, Han) should have "proximity rules":
- **Cameo zone**: The player can be in the same location at the same time. They see Luke in the cantina. They hear Leia's transmission. One-way observation only.
- **Interaction zone**: Brief, inconsequential interaction. The player helps Han fix a conduit. Luke asks for directions. No plot impact.
- **Exclusion zone**: The player cannot be present at canon-critical moments. You can't be in the trench run. You can't be in the throne room at Endor.

This creates the feeling of living in the same world without breaking the timeline.

**3. Ripple vs. Wave System for Sandbox**

In sandbox mode, player actions should have categorized impact levels:
- **Ripple**: Local effects. Killing a local crime lord changes this planet's power dynamics but doesn't affect the galactic war.
- **Wave**: Regional effects. Destroying an Imperial supply depot weakens the Empire's grip on this sector.
- **Tsunami**: Galactic effects. Assassinating a key Imperial admiral changes the outcome of a major battle.

Tsunamis should be rare, costly (high DC, multi-quest chains), and have dramatic narrative weight. The arc planner should treat a potential tsunami as a climax-worthy event.

---

## 8. What You Do Well (Strengths) <a id="8-strengths"></a>

1. **The pipeline architecture is genuinely production-grade.** Single transaction boundary, event sourcing, authoritative vs. non-authoritative agents, graceful degradation. This is not a toy project -- it's serious software engineering.

2. **The prompt engineering is sophisticated.** The narrator prompt in `narrator_prompt.py` is one of the most detailed and carefully constrained LLM prompts I've seen for creative writing. The KOTOR voice rules, the player agency hard rule, the faction neutrality enforcement -- these show deep understanding of what makes LLM narration go wrong and how to prevent it.

3. **Setting-agnostic design is the right long-term bet.** The fact that the same engine runs Star Wars and Forgotten Realms proves the architecture works. Every new era pack is content, not code.

4. **The KOTOR dialogue wheel is the right UX metaphor.** 4 tones with risk levels and consequence hints creates meaningful choices without overwhelming the player. The investigation option specifically is smart -- it gives players a "safe" way to learn more before committing.

5. **The living world system is a genuine differentiator.** Time-as-currency, faction simulation, news feeds, and rumors make the world feel alive even when the player isn't interacting with those systems. This is what separates "interactive fiction" from "chatbot with a story prompt."

6. **Documentation quality is exceptional.** 13 docs, comprehensive README, inline comments, clear architecture diagrams. Anyone onboarding to this project can understand it quickly.

7. **Accessibility is treated as a first-class concern.** ARIA labels, screen reader support, keyboard navigation, reduced motion. Most game projects ignore this entirely.

8. **The deterministic mechanics layer means fair gameplay.** Dice rolls, DCs, and time costs are pure Python -- no LLM randomness in the rules. A stealth check succeeds or fails based on math, not on whether the LLM felt creative.

---

## 9. Critical Issues & Risks <a id="9-critical-issues"></a>

### Blocking Issues

**1. ChoiceCrafter has no fallback (Known Issue #1)**
If the ChoiceCrafter LLM fails, the player gets an error and empty choices. The game is stuck. For a game that wants to be played offline/locally, this is a session-killer. Add 4 generic fallback choices ("Investigate further", "Talk to someone nearby", "Take a cautious approach", "Take a bold approach") when the LLM fails.

**2. Truth Ledger tables not in migrations (Known Issue #7)**
`truth_facts` and `truth_events` tables are referenced in code but missing from migrations 0001-0022. This means the contradiction detection system -- one of V5.0's flagship features -- will crash at runtime on a fresh install. This needs a migration immediately.

**3. No frontend tests**
Zero test files in `frontend/`. The SvelteKit UI is a critical surface (it's what players interact with), and it has no automated validation. Component rendering, keyboard shortcuts, state management, and accessibility should all have tests.

### High-Priority Concerns

**4. The "Star Wars residue" problem**
Despite the setting-agnostic architecture, Star Wars references still leak through:
- `narrator_prompt.py:31-43`: `_LOCATION_NARRATIVE_NAMES` has "cantina" as default.
- `narrator_prompt.py:48-84`: `_ERA_FALLBACK_ATMOSPHERE` has Star Wars era names (REBELLION, NEW_REPUBLIC, etc.)
- The `NPC_RENDER_MODEL`, starship system, opening crawl component, and various prompt fragments assume sci-fi context.
- A Forgotten Realms player seeing "cantina" instead of "tavern" or a Star Wars crawl for a D&D game would break immersion immediately.

**5. Memory system is too aggressive with compression**
300 chars per era summary x 5 max = 1,500 chars total long-term memory. For your "adventures across eras" vision, this is dangerously low. A character's 200-turn campaign gets compressed to ~300 characters. Key relationships, emotional beats, and plot developments will be lost.

**6. No graceful handling of Ollama being unavailable**
If Ollama isn't running, every LLM call fails. The health check endpoint reports this, but the player-facing experience is just error messages. There should be a clear UI state: "LLM service unavailable -- please start Ollama" with a link to instructions.

---

## 10. Recommendations & Roadmap Priorities <a id="10-recommendations"></a>

### Immediate (Bug Fixes / Blockers)

1. **Add Truth Ledger migration** (`0023_truth_ledger.sql`) -- the contradiction system can't work without its tables.
2. **Add ChoiceCrafter fallback choices** -- 4 generic actions when LLM fails.
3. **Audit Star Wars residue in narrator_prompt.py** -- ensure setting-agnostic fallbacks use `SettingRules` for location names and era atmospheres.

### Short-Term (Quality of Life)

4. **Implement projection snapshots** for long campaigns (solve O(N) replay).
5. **Add a "Quick Start" character creation flow** -- reduce time-to-play for new users.
6. **Add ambient audio** -- even 5 location-type loops would transform immersion.
7. **Increase narrator word limit dynamically** for climax/opening scenes.
8. **Add frontend test foundation** (Vitest + Testing Library for Svelte).

### Medium-Term (Feature Completions)

9. **Implement Character Legacy system** for cross-campaign continuity.
10. **Implement Saga/Campaign/Universe hierarchy** for long-running adventures.
11. **Add Historical mode enforcement** via immutable Truth Ledger facts from timeline.
12. **Add local image generation** for character portraits and scene moods (SDXL Turbo on 4070).
13. **Implement "scene importance" routing** for hybrid cloud/local quality on key moments.

### Long-Term (Vision)

14. **Community era pack marketplace** -- let others create and share settings.
15. **Multiplayer** -- two players in the same campaign (this is a massive undertaking but would be unique).
16. **Voice integration** -- TTS for NPC dialogue (local models like Piper are free and run on CPU).
17. **Mod support** -- let players modify rule systems, add items, create custom companions.

---

## Summary

Storyteller-V2 is an architecturally impressive project with strong fundamentals. The pipeline design, event sourcing, and setting-agnostic era packs are all production-quality decisions. The KOTOR-inspired UX is the right creative direction.

The main tensions are:
1. **Breadth vs. depth**: Many systems are scaffolded but not fully polished. Focus on making the core loop (read -> choose -> read) feel exceptional before expanding further.
2. **Local quality vs. cost**: Local models produce adequate but not great creative writing. The hybrid approach is the right answer -- use cloud for high-leverage, low-frequency calls (campaign bible) and local for high-frequency, lower-stakes calls (per-turn narration).
3. **Long-term persistence**: The vision of Luke/Kirk-style long-running adventures requires deeper memory and cross-campaign systems than currently exist. The foundation is there (event sourcing, player profiles, era transitions) but the memory and legacy transfer systems need significant work.

The project is in a strong position. The architecture can support the vision -- it just needs focused execution on the experience layer and the long-term persistence systems.
