# Player Experience Review — Skeptical RPG Player Perspective

**Reviewer stance:** A player who has sunk 500+ hours into KOTOR 1/2, Mass Effect trilogy, Baldur's Gate 3, Divinity: Original Sin 2, and tabletop campaigns. Someone who will poke at every seam, question every abstraction, and get frustrated by friction between "I want to play" and actually playing.

---

## 1. YOUR PROPOSED FLOW — HONEST ASSESSMENT

Your proposed flow:

> Start the Game and Choose the Universe → Load in lore novels → Choose the Timeline → Choose historical or sandbox → Character Creator (species, background, handcraft) → API call for prologue generation → Prologue → First adventure

**Verdict: The bones are right, but the order and some steps need rethinking.**

Here's what I'd change and why:

### 1.1 Flow Order Problems

**Problem: Lore upload too early.**
You have "Load in any lore novels" as step 2, right after choosing the universe. A player who just wants to jump in hasn't committed to anything yet — they picked "Star Wars" and now you're asking them to go find PDF files on their hard drive? That's a cold shower. The excitement graph looks like:

```
Excitement:  Pick Universe ↑↑↑  →  "Upload PDFs" ↓↓↓  →  (player closes tab)
```

**Fix:** Lore upload should be *optional and late* — after the character is built but before the prologue fires. Or better yet, accessible anytime from a Library sidebar. Your current code actually does this correctly (Step 4 in the wizard is optional reference material upload, after backgrounds). **Don't move it earlier.**

**Problem: "Historical or Sandbox" is a confusing fork.**
Most RPG players don't think in these terms. "Historical" implies "I'm going to experience a pre-written story" and "Sandbox" implies "do whatever." Neither is what your engine actually does — your engine generates *adaptive narrative campaigns* with arc structures. Calling it "sandbox" undersells the narrative engine; calling it "historical" suggests a railroad.

**Fix:** Replace this with **Campaign Tone / Story Type** selection. Think Mass Effect's "I want to be a Paragon/Renegade" vibe, not a game-design taxonomy. Options like:
- **Guided Narrative** — "A story unfolds around you. The galaxy has plans." (Arc-driven, Director-heavy)
- **Open Galaxy** — "You choose the path. The galaxy reacts." (Sandbox-leaning, player-directed)
- **Legacy Campaign** — "Continue a previous character's saga." (Saga continuation)

### 1.2 What's Actually Good About Your Flow

- **Universe → Timeline → Character** is the correct macro-order. You establish *where* before *who*.
- **Species + Background + CYOA branching** before the API call is smart — it means the Biographer/CampaignBible agents have rich context to work with.
- **Prologue as a separate playable beat** before the first adventure is excellent. It's the KOTOR opening planet approach, and it works.
- **The API call generating the prologue asynchronously** while the player reviews their character sheet is a good UX pattern — perceived wait time drops.

---

## 2. CURRENT IMPLEMENTATION — PAIN POINTS

I walked through every screen in the actual codebase. Here's what a skeptical player would hit:

### 2.1 Home Screen (`/` — +page.svelte)

**What works:**
- "Continue Story" button with last-played campaign info is great. Respects the player's time.
- "New Story" / "Load Campaign" / "Browse Universes" is a clean menu.

**Pain points:**
- **No sense of atmosphere.** The home screen is a centered column of buttons on a dark background. Compare this to Baldur's Gate 3's main menu (animated scene, music, mood) or even a CRPG title screen. You need *something* — a slow-scrolling starfield, a piece of ambient art, a short lore quote that rotates. The player's first impression sets the tone for the entire session.
- **"Browse Universes" goes to `/library`** — which is a source/ingestion management page, not a "browse and get excited about worlds" page. The naming mismatch is a trust violation. A player clicking "Browse Universes" expects to see rich descriptions, art, tone previews. They get a file upload interface.
- **Settings modal is purely technical** (theme, streaming toggle, debug info). No gameplay settings — no "how much do you want the engine to hold your hand" slider, no narrative preferences, no content warnings/filters.

### 2.2 Creation Wizard (`/create` — +page.svelte)

**What works well:**
- Progress bar with dots is clean and intuitive.
- Universe selection cards (when multiple universes exist) are well-structured.
- Species cards with stat bonuses are informative.
- Background CYOA questions are genuinely compelling — the writing is strong (the Imperial Officer loyalty question is chef's kiss).
- KOTOR-style tone coloring on choices (PARAGON blue, RENEGADE red) gives moral weight.
- Quick Start button that randomizes everything is a great escape hatch.
- Character sheet reveal at the end with editable name is satisfying.

**Pain points:**

1. **Step 1 crams too much together.** Name + Gender + Era are all on one screen. These are three separate decisions with different weights. The era selection especially deserves its own dedicated step with rich descriptions, not a list of cards crammed below a name field. The era descriptions (`ERA_DESCRIPTIONS`) are brief one-liners — for a player choosing between "Age of Rebellion" and "Dark Times," they need to understand what the *experience* will feel like, not just the year range.

2. **Gender is binary with no explanation.** Male/Female buttons with no context. The code reveals this is purely for pronoun selection (`player_gender` feeds narrator pronoun handling). Tell the player that. Better yet, offer a pronoun selector or a "How should the narrator refer to you?" framing. RPG players in 2026 will notice this.

3. **No visual preview of what you're building.** The entire wizard is text-on-dark-background. There's no character silhouette, no faction emblem, no location art, no mood imagery. Compare to how Dragon Age: Origins shows you the origin story *as you pick it* — the player sees the world they're about to enter. Your backgrounds have incredible narrative hooks (thread seeds), but the player never sees them during creation.

4. **Companion preview is buried at the bottom of the review screen.** 108 companions is a massive selling point, but they appear as a scrollable list of cards *after* the player has already built their character. By then, they've committed. The companions should influence the character creation — "If you pick Rebel Operative, you might encounter Kira Carrick, a jaded intelligence officer who..."

5. **Difficulty selection feels like an afterthought.** It's a row of three cards at the bottom of the review screen, below the companion list and reference material upload. For players who care about difficulty (and RPG players do), this should be more prominent and earlier — ideally right after era selection or as part of the initial setup.

6. **No "Campaign Length" or "Story Scale" option.** Your engine supports `campaign_scale: small/medium/large/epic` (2-5 arcs), but the player never gets to choose this. A player who has 2 hours wants a different experience than one who wants a 40-hour epic. Expose this.

7. **The "Begin Adventure" button calls `setupAuto()` which blocks for potentially 15-30 seconds** (Biographer + CampaignBible + Prologue agents, three sequential LLM calls on Ollama). The only feedback is the button text changing to "Setting up..." No progress indicator, no "what's happening" explanation. A skeptical player will think it crashed.

8. **Reference material upload UX is bare-bones.** A raw `<input type="file">` with no drag-and-drop, no preview, no explanation of what formats work well vs. poorly. The polling-based upload status is functional but feels unpolished. This is a power-user feature being presented to all users.

### 2.3 Prologue (`/prologue` — +page.svelte)

**What works:**
- Clean, cinematic presentation. Dark background, gold accents, chapter label.
- NPC cast list with motivations is a nice touch.
- "Skip Prologue" escape hatch respects player time.

**Pain points:**

1. **The prologue is static text, not playable.** Your proposal says "beginning backstory that's playable," but the current implementation is a read-only briefing page. It shows the prologue screenplay data (title, opening narration, inciting moment, departure trigger) but the player just reads it and clicks "Begin Your Story." The actual playable opening happens when `startAdventure()` calls `runTurn(cid, pid, '[OPENING_SCENE]')` — which dumps the player straight into `/play` with the first narrated turn.

2. **No transition between prologue and play.** The player reads the prologue, clicks "Begin," and gets teleported to the play screen with a narrated opening. There's no crawl, no fade, no dramatic transition. The `OpeningCrawl.svelte` component exists but isn't wired into the prologue→play transition.

3. **NPC cast reveals too much.** Showing NPC motivations upfront ("— wants to recruit you for a dangerous mission") kills dramatic tension. Show names and roles, but let motivations emerge through play.

### 2.4 Play Screen (`/play` — +page.svelte)

This is where the actual game lives, and honestly? **It's the strongest part of the experience.** The play screen is well-architected:

- ApproachCards with tone coloring, risk levels, and consequence hints are excellent.
- Free-text input ("Forge Your Own Path") for creative deviation is exactly what tabletop players want.
- Companion sidebar with affinity tracking.
- Quest tracker.
- Mechanic notes (dice rolls, DCs) for transparency.
- Consequence overlay for dramatic moments.
- Living world intel strip (news, rumors) from world simulation.
- Typewriter effect for immersive narration reveal.

**Pain points:**

1. **First-time player overwhelm.** The play screen has a LOT of UI elements — narrative panel, approach cards, companion sidebar, quest tracker, HUD bar with location/time/HP, settings, debug. There's a `TutorialOverlay.svelte` but it needs to be carefully tuned to not just *explain* the UI but to *introduce it gradually*. Hide the companion sidebar and quest tracker for the first 3 turns, then slide them in when they become relevant.

2. **No journal/codex.** Players who take a break and come back have no way to review what's happened beyond scrolling the transcript. "Story So Far" exists but is a summary API call, not a persistent journal. RPG players expect a codex: characters met, locations visited, lore discovered, choices made.

3. **Rewind is hidden.** The rewind/undo feature (restore to a previous turn) is a powerful safety net, but it's buried. Players who make a choice they regret should see a subtle "undo last turn" option, not have to hunt for it.

---

## 3. THE CAMPAIGN SETUP WIZARD — WHAT IT SHOULD LOOK LIKE

Here's my recommended flow, keeping you honest about what's built vs. what's needed:

### Revised Flow

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 0: UNIVERSE SELECTION                                 │
│  ─────────────────────────────────────────                  │
│  Visual cards with universe art, tone description, and      │
│  "X eras available" badge.                                  │
│  + "Create Custom Universe" link → Library/EraForge         │
│  Already built: Yes (universe cards in Step 0)              │
│  Needs: Art/atmosphere, richer descriptions                 │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: ERA / TIMELINE SELECTION                           │
│  ────────────────────────────────                           │
│  Full-width cards with era summary, tone, key conflicts.    │
│  Each card shows a flavor quote and 2-3 bullet points.      │
│  Already built: Partially (era cards exist but are thin)    │
│  Needs: Rich era descriptions from era.yaml metadata,       │
│         key_conflicts and themes surfaced in the UI         │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: CAMPAIGN PREFERENCES                               │
│  ────────────────────────────                               │
│  - Story Type: Guided Narrative / Open Galaxy / Legacy       │
│  - Campaign Length: Short (1 arc) / Standard (2-3) / Epic   │
│  - Difficulty: Easy / Normal / Hard                          │
│  Already built: Difficulty only (review screen)              │
│  Needs: Story type selector, campaign length selector,       │
│         move difficulty here from review screen              │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: CHARACTER IDENTITY                                  │
│  ────────────────────────                                   │
│  - Name (with random generator)                              │
│  - Pronouns / narrator reference style                       │
│  Already built: Yes (name + gender on Step 1)                │
│  Needs: Split from era, pronoun framing                      │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: SPECIES SELECTION                                   │
│  ────────────────────────                                   │
│  Species cards with stat bonuses and flavor text.            │
│  Show how species affects starting position.                 │
│  Already built: Yes (SpeciesCard.svelte)                     │
│  Needs: Lore flavor text on species cards, visual variety    │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: BACKGROUND SELECTION                                │
│  ────────────────────────────                               │
│  Background cards with description, starting stats,          │
│  and a "story hook preview" showing the thread_seed.         │
│  "As an Imperial Officer, your story begins with..."         │
│  Already built: Yes (background cards)                       │
│  Needs: Thread seed preview, companion hints per background  │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5b-N: BACKGROUND CYOA QUESTIONS                        │
│  ────────────────────────────────────                       │
│  Branching questions with tone-colored cards.                │
│  Each choice shows concept text + effect hints.              │
│  Already built: Yes (fully functional, conditional logic)    │
│  Needs: Minor — this is the strongest part of creation       │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP FINAL: CHARACTER SHEET REVIEW                          │
│  ──────────────────────────────────                         │
│  Full character sheet with:                                  │
│  - Editable name (LLM-suggested)                             │
│  - Generated background prose                                │
│  - Stats (with species + background breakdown)               │
│  - Starting location + planet                                │
│  - Companion preview (2-3 likely companions)                 │
│  - Optional: Upload reference material (collapsed section)   │
│  - "Start Your Story" button with progress indicator         │
│  Already built: Partially (sheet reveal exists)              │
│  Needs: Progress indicator during setup, companion hints     │
│         tied to background, reference upload as collapsible   │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  PROLOGUE (PLAYABLE)                                         │
│  ───────────────────                                        │
│  Opening crawl animation → First narrated scene with         │
│  choice cards. The prologue IS the first 2-3 turns,          │
│  not a static briefing page.                                 │
│  Already built: Partially (prologue page exists but static)  │
│  Needs: Wire OpeningCrawl into prologue→play transition,     │
│         make prologue a playable scene not a briefing        │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  MAIN GAME (/play)                                           │
│  ─────────────────                                          │
│  Full gameplay loop begins.                                  │
│  Already built: Yes (strongest part of the app)              │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. PRIORITIZED RECOMMENDATIONS

### Tier 1 — Do These First (High Impact, Reasonable Effort)

| # | What | Why | Effort |
|---|------|-----|--------|
| 1 | **Setup progress indicator** | Players think it crashed during the 15-30s `setupAuto` call. Add a multi-stage progress bar: "Generating character..." → "Building world..." → "Writing prologue..." | Low |
| 2 | **Split Step 1** (Name/Gender/Era) into separate steps | Each decision deserves focus. Era selection especially needs room to breathe with rich descriptions. | Low |
| 3 | **Campaign preferences step** | Expose `campaign_scale` (story length) and story type to the player. This is one of your engine's best features and it's invisible. | Medium |
| 4 | **Make prologue playable** | Wire the prologue screenplay into the play loop as the first 2-3 turns instead of a static briefing. Use `OpeningCrawl` as the transition animation. | Medium |
| 5 | **Home screen atmosphere** | Add a background visual (starfield, ambient art), a rotating lore quote, maybe a subtle ambient sound. First impressions matter enormously. | Low |

### Tier 2 — Polish (Medium Impact)

| # | What | Why | Effort |
|---|------|-----|--------|
| 6 | **Thread seed preview in background selection** | Show players a taste of their opening story hook: "Your adventure begins: *A Rebel operative has made contact through a dead drop...*" This is already in the data but not surfaced. | Low |
| 7 | **Companion hints during creation** | After background selection, show 2-3 companions the player is likely to encounter based on their choices. The `companion_affinity_bonus` data in backgrounds already establishes these links. | Medium |
| 8 | **Pronoun/narrator framing** | Replace "Male/Female" with "How should the narrator refer to your character?" with he/him, she/her, they/them options. Straightforward code change in gender handling. | Low |
| 9 | **Progressive UI reveal on play screen** | Hide companion sidebar and quest tracker for turns 1-3. Introduce them with a subtle animation when they first become relevant (first companion encounter, first quest). Reduce first-session overwhelm. | Medium |
| 10 | **Rich era descriptions** | Your `era.yaml` has `summary`, `tone`, `key_conflicts`, and `themes` — all of which are unused in the frontend era cards. Surface them. | Low |

### Tier 3 — Future Polish (Lower Priority)

| # | What | Why | Effort |
|---|------|-----|--------|
| 11 | **Character codex/journal** | Persistent in-game reference for NPCs met, locations, lore, choices. Tabletop players expect this. | High |
| 12 | **Quick-start archetypes** | Pre-built character templates ("The Reluctant Hero," "The Ruthless Mercenary") that auto-fill background + CYOA. One-click to a fully-realized character. | Medium |
| 13 | **"Browse Universes" redesign** | Make `/library` dual-purpose: a "Browse & Get Excited" mode for new players and a "Manage Sources" mode for power users. Currently it's purely the latter. | High |
| 14 | **NPC motivation hiding in prologue** | Remove motivation strings from the prologue NPC cast. Let the player discover them through play. | Low |
| 15 | **Drag-and-drop lore upload** | Replace the raw file input with a drag-and-drop zone, format badges (PDF/EPUB/TXT), and clearer ingestion feedback. | Medium |

---

## 5. WHAT'S ALREADY GREAT (Don't Break These)

Giving credit where it's due — these are things that would make a skeptical RPG player nod in approval:

1. **The CYOA background system.** The writing quality in `backgrounds.yaml` is genuinely strong. The Imperial Officer loyalty question with its three-way fork (true believer / secret rebel / opportunist) is exactly the kind of meaningful choice that makes character creation feel consequential. The conditional follow-up questions based on tone are KOTOR-caliber.

2. **The approach card system in gameplay.** 3-6 choices with tone tags, risk levels, consequence hints, and action types. This is better than most commercial RPGs. The "Forge Your Own Path" free-text option on top is the tabletop escape hatch that narrative games desperately need.

3. **The living world simulation.** Factions moving off-screen, news feed, rumors, time economy — this is what separates a narrative engine from a chatbot. The fact that the world ticks every 4 in-game hours regardless of player action creates genuine immersion.

4. **The 14-node LangGraph pipeline with deterministic mechanics.** The fact that dice rolls, DC checks, and combat resolution are deterministic (no LLM) while narrative, direction, and choices are LLM-generated is architecturally sound. You get the reliability of tabletop mechanics with the creativity of AI storytelling.

5. **Setting-agnostic architecture.** Era packs + SettingRules mean this engine genuinely works for Star Wars, D&D, or any custom universe. That's rare.

6. **The rewind system.** Turn snapshots with full world state restoration. Most narrative games are one-way; this gives players the safety net they need to experiment.

7. **Multi-arc campaigns with saga continuity.** Cross-campaign memory, legacy characters, saga chapters — this is Mass Effect's import system but for AI-generated stories.

---

## 6. OVERALL VERDICT

**Your engine is far more sophisticated than your onboarding reveals.** The backend has features (campaign scale, arc moods, dramatic irony, callback crystallization, player behavioral profiling) that the frontend never surfaces or lets the player interact with. The campaign setup wizard works but doesn't sell the experience — it feels like filling out a form rather than stepping into a universe.

The core gameplay loop (`/play`) is strong. The character creation CYOA is strong. The narrative intelligence is genuinely impressive. What's missing is the *connective tissue* — the atmospheric moments, the progressive reveals, the sense of ceremony that makes a player feel like they're not just configuring an engine but beginning an adventure.

**The single highest-impact change you can make:** Add a real progress indicator during `setupAuto()` and make the prologue playable rather than a static briefing. These two changes alone would transform the "form → wait → read → play" experience into "form → anticipation → immersion → play."

---

*Review based on codebase analysis of Storyteller-V2 at V11.0 (v2.16).*
*Frontend: SvelteKit 5.0 + TypeScript. Backend: FastAPI + LangGraph + SQLite.*
