# Dialogue System Architecture

## Overview

This document explains how Storyteller AI generates NPC dialogue, tracks conversations, and maintains dialogue state across turns. This is the technical companion to `player_ux_flow.md`.

---

## 1. Complete Dialogue Generation Pipeline

```mermaid
flowchart TD
    Input[Player Input: TALK Intent<br/>e.g., Ask the barkeep about rumors] --> Router[ROUTER NODE<br/>Classifies as DIALOGUE_ONLY<br/>Sets intent=TALK]

    Router --> SkipMech[SKIP MECHANIC<br/>No dice rolls for pure dialogue<br/>Fast path enabled]

    SkipMech --> Encounter[ENCOUNTER NODE<br/>Determines present NPCs<br/>Sources:<br/>- Era pack deterministic<br/>- CastingAgent spawned<br/>- Campaign generated<br/>- Anonymous extras]

    Encounter --> WorldSim[WORLDSIM NODE<br/>Tick world clock<br/>Faction movements]

    WorldSim --> Companion[COMPANION REACTION<br/>Track affinity deltas<br/>based on dialogue tone]

    Companion --> ArcPlan[ARC PLANNER<br/>Determine narrative stage<br/>influences NPC agenda]

    ArcPlan --> SceneFrame[SCENEFRAME NODE<br/>CRITICAL: Builds immutable snapshot<br/>• Loads NPC data from DB<br/>• Builds voice profiles<br/>• Derives KOTOR topics<br/>• Sets scene pressure<br/>• Determines NPC agenda]

    SceneFrame --> SceneDetail[SceneFrame Output:<br/>• present_npcs list with voice profiles<br/>• topic_primary/secondary<br/>• subtext emotional layer<br/>• npc_agenda what NPC wants<br/>• scene_style_tags<br/>• pressure heat/alert levels]

    SceneDetail --> Director[DIRECTOR NODE<br/>LLM reads scene context<br/>Generates narrative instructions<br/>NOT SHOWN to Narrator]

    Director --> Narrator[NARRATOR NODE<br/>LLM AGENT qwen3:8b<br/>Generates:<br/>1. Prose paragraphs 5-8 sentences<br/>2. ---NPC_LINE--- separator<br/>3. NPC utterance 1-3 sentences]

    Narrator --> VoiceRetrieval[Narrator Context Retrieval:<br/>• Lore from LanceDB<br/>• Voice snippets for NPCs<br/>• Style guidance era/genre/archetype<br/>• Director instructions]

    VoiceRetrieval --> NarratorOutput[Narrator Output:<br/>Prose: Several paragraphs...<br/>---NPC_LINE---<br/>SPEAKER: Grumthar the Barkeep<br/>He eyes you suspiciously.<br/>I don't talk to strangers.]

    NarratorOutput --> Extract[_extract_npc_utterance<br/>Parses separator<br/>Validates speaker in present_npcs<br/>Falls back to narrator observation]

    Extract --> NPCUtter[NPCUtterance Object:<br/>• speaker_id: npc-barkeep<br/>• speaker_name: Grumthar<br/>• text: dialogue line<br/>• subtext_hint: debug info<br/>• rhetorical_moves: challenge, probe]

    NPCUtter --> Validator[NARRATIVE VALIDATOR<br/>Checks consistency<br/>Logs warnings]

    Validator --> SuggRefine[SUGGESTION REFINER NODE<br/>LLM AGENT qwen3:8b<br/>Reads:<br/>• Narrator prose + NPC utterance<br/>• Scene context<br/>• Player stats for gating<br/>Generates 4 KOTOR options]

    SuggRefine --> PlayerResp[4 PlayerResponse Objects:<br/>resp_1: PARAGON blue<br/>resp_2: INVESTIGATE gold<br/>resp_3: RENEGADE red<br/>resp_4: NEUTRAL gray<br/><br/>Each with:<br/>• display_text<br/>• action intent/target/tone<br/>• risk_level<br/>• consequence_hint<br/>• meaning_tag]

    PlayerResp --> Commit[COMMIT NODE<br/>ONLY node that writes DB<br/>Appends events to turn_events:<br/>• Event: DIALOGUE<br/>• Payload: speaker, text, turn#<br/>• Immutable append-only]

    Commit --> Response[TurnResponse<br/>Returns DialogueTurn:<br/>• scene_frame<br/>• npc_utterance<br/>• player_responses 4<br/>• narrated_prose<br/>• validation]

    Response --> UI[UI Renders:<br/>✓ Narrative prose journal<br/>✓ NPC dialogue bubble<br/>✓ 4 KOTOR dialogue wheel options<br/>✓ Companion reactions<br/>✓ Quest updates]

    style Router fill:#FFE5B4
    style SceneFrame fill:#DDA0DD
    style Narrator fill:#B0E0E6
    style SuggRefine fill:#FFB6C1
    style Commit fill:#90EE90
    style UI fill:#90EE90
```text

---

## 2. SceneFrame Node: Dialogue Context Builder

The **SceneFrame node** is the linchpin of dialogue quality. It runs **before** Director/Narrator and builds an **immutable scene snapshot** that all downstream agents consume.

```mermaid
flowchart TD
    Start[SceneFrame Node Receives State] --> LoadNPCs[Load present_npcs from state<br/>Set by Encounter node]

    LoadNPCs --> BuildVoice[For each NPC:<br/>_build_voice_profile]

    BuildVoice --> VoiceSource{Voice Data Source?}

    VoiceSource -->|Era Pack NPC| EraVoice[Extract from era pack JSON:<br/>• motivation → belief<br/>• secret → wound<br/>• taboo inferred from traits<br/>• voice_tags → rhetorical_style<br/>• mannerisms → tell]

    VoiceSource -->|Companion| CompVoice[Extract from companion data:<br/>• personality → belief<br/>• backstory → wound<br/>• taboo from personality<br/>• voice_tags → rhetorical_style<br/>• banter_style → tell]

    VoiceSource -->|Generated NPC| GenVoice[Extract from generated data:<br/>• role/background → belief<br/>• hidden motivations → wound<br/>• default taboo<br/>• default rhetorical_style<br/>• default tell]

    EraVoice --> VoiceProfile[VoiceProfile Dict:<br/>belief: core value 120 chars<br/>wound: hidden pain 120 chars<br/>taboo: forbidden topic<br/>rhetorical_style: socratic/blunt/evasive<br/>tell: mannerism pauses/smirks/fidgets]
    CompVoice --> VoiceProfile
    GenVoice --> VoiceProfile

    VoiceProfile --> NPCRef[NPCRef Object:<br/>id: npc-barkeep<br/>name: Grumthar<br/>role: Barkeep<br/>voice_profile: VoiceProfile dict]

    NPCRef --> Topic[Derive KOTOR Topics<br/>V2.18 Soul System]

    Topic --> TopicLogic{Topic Derivation?}

    TopicLogic -->|Primary| PrimaryT[From NPC role mapping:<br/>mentor → identity<br/>authority → duty<br/>merchant → debt<br/>rebel → trust<br/>criminal → loyalty]

    TopicLogic -->|Secondary| SecondaryT[From arc stage:<br/>setup → curiosity<br/>rising → conflict<br/>climax → sacrifice<br/>resolution → forgiveness]

    PrimaryT --> Subtext[Generate Subtext:<br/>The question of topic<br/>hangs in the air]
    SecondaryT --> Subtext

    Subtext --> Agenda[Determine NPC Agenda<br/>What NPC wants from player]

    Agenda --> AgendaLogic{Agenda Derivation?}

    AgendaLogic -->|Setup stage| AgendaSetup[test_player<br/>establish_boundaries<br/>signal_availability]

    AgendaLogic -->|Rising stage| AgendaRising[request_commitment<br/>challenge_assumptions<br/>reveal_stakes]

    AgendaLogic -->|Climax stage| AgendaClimax[demand_choice<br/>force_reckoning<br/>escalate_conflict]

    AgendaLogic -->|Resolution stage| AgendaResolution[offer_closure<br/>accept_outcome<br/>pass_wisdom]

    AgendaSetup --> Pressure[Compute Scene Pressure]
    AgendaRising --> Pressure
    AgendaClimax --> Pressure
    AgendaResolution --> Pressure

    Pressure --> PressureCalc[Pressure Components:<br/>alert: Quiet/Watchful/Lockdown<br/>heat: Low/Noticed/Wanted<br/>Based on:<br/>• Location threat level<br/>• Faction heat<br/>• Active hostiles]

    PressureCalc --> StyleTags[Assign scene_style_tags<br/>Based on:<br/>• Genre noir/space-opera/horror<br/>• NPC rhetorical style<br/>• Arc stage<br/>Examples: socratic, military, noir]

    StyleTags --> Output[SceneFrame Output Serialized:<br/>location_id<br/>location_name<br/>present_npcs: list NPCRef<br/>immediate_situation: str<br/>player_objective: str<br/>topic_primary: str<br/>topic_secondary: str<br/>subtext: str<br/>npc_agenda: str<br/>scene_style_tags: list str<br/>allowed_scene_type: dialogue<br/>pressure: dict]

    Output --> ImmutableState[IMMUTABLE SCENE SNAPSHOT<br/>All downstream nodes read this<br/>None modify it]

    style VoiceProfile fill:#DDA0DD
    style NPCRef fill:#FFB6C1
    style Output fill:#90EE90
    style ImmutableState fill:#90EE90
```text

---

## 3. Voice Profile System

```mermaid
flowchart LR
    subgraph "Voice Profile Components"
        Belief[BELIEF<br/>Core value/motivation<br/>Example: Survival above all<br/>Max 120 chars]
        Wound[WOUND<br/>Hidden pain/secret<br/>Example: Lost family to Empire<br/>Max 120 chars]
        Taboo[TABOO<br/>Forbidden topic<br/>Example: Never speak of Alderaan<br/>Short phrase]
        Rhetoric[RHETORICAL STYLE<br/>Speech pattern<br/>Options:<br/>• socratic questioning<br/>• blunt direct<br/>• evasive indirect<br/>• formal military<br/>• street slang<br/>• mystic cryptic]
        Tell[TELL<br/>Physical mannerism<br/>Example:<br/>• pauses before answering<br/>• avoids eye contact<br/>• smirks when lying<br/>• fidgets with hands]
    end

    subgraph "Usage in Dialogue Generation"
        Narrator[Narrator LLM Prompt] --> Include[Includes for each NPC:<br/>Name + Role + Voice Profile<br/><br/>Example:<br/>Grumthar the Barkeep<br/>Belief: Trust is earned through deeds<br/>Wound: Owes debt to crime syndicate<br/>Taboo: Never mentions the Hutts<br/>Rhetoric: blunt direct with criminals<br/>Tell: wipes bar when nervous]

        Include --> Guide[Guides LLM to generate:<br/>✓ In-character dialogue<br/>✓ Appropriate rhetoric<br/>✓ Subtle tells in description<br/>✓ Avoids taboo topics<br/>✓ Reflects wound/belief]
    end

    Belief --> Narrator
    Wound --> Narrator
    Taboo --> Narrator
    Rhetoric --> Narrator
    Tell --> Narrator

    style Belief fill:#B0E0E6
    style Wound fill:#FFB6C1
    style Taboo fill:#FF6B6B
    style Rhetoric fill:#DDA0DD
    style Tell fill:#FFE5B4
```text

**Voice Profile Sources by NPC Type:**

| NPC Type | Belief | Wound | Taboo | Rhetoric | Tell |
|----------|--------|-------|-------|----------|------|
| **Era Pack** | `motivation` field | `secret` field | Inferred from traits | Mapped from `voice_tags` | `mannerisms` field |
| **Companion** | `personality` field | `backstory` field | Inferred from personality | Mapped from `voice_tags` | `banter_style` mapped |
| **Generated** | Role-based template | Random secret | Generic | Default for role | Generic fidget/pause |
| **Anonymous** | Generic cautious | None | None | Neutral | None |

---

## 4. NPC Utterance Extraction

```mermaid
flowchart TD
    NarrOutput[Narrator LLM Output:<br/>Full text block with prose + NPC line] --> Check{Contains<br/>---NPC_LINE---?}

    Check -->|Yes| Split[Split on separator:<br/>prose = before<br/>npc_section = after]
    Check -->|No| Fallback1[FALLBACK 1:<br/>Extract last sentence as<br/>narrator observation]

    Split --> ParseSpeaker[Parse SPEAKER line:<br/>Regex: SPEAKER:\s*the\s+name<br/>or SPEAKER: name]

    ParseSpeaker --> ValidateSpeaker{Speaker in<br/>present_npcs?}

    ValidateSpeaker -->|Yes| ExtractText[Extract dialogue text:<br/>Lines after SPEAKER line<br/>Strip whitespace<br/>Max 500 chars]
    ValidateSpeaker -->|No| Fallback2[FALLBACK 2:<br/>Use narrator<br/>speaker_id=narrator<br/>text=last sentence]

    ExtractText --> BuildUtterance[Build NPCUtterance:<br/>speaker_id: npc-id<br/>speaker_name: extracted name<br/>text: dialogue text<br/>subtext_hint: empty<br/>rhetorical_moves: empty]

    Fallback1 --> BuildUtterance
    Fallback2 --> BuildUtterance

    BuildUtterance --> Return[Return NPCUtterance object]

    style ValidateSpeaker fill:#FFD700
    style BuildUtterance fill:#90EE90
```text

**Code Reference:** `backend/app/core/agents/narrator.py` → `_extract_npc_utterance()`

**Example Narrator Output:**
```text
The cantina is thick with smoke and the smell of spice. You
approach the bar where the Devaronian barkeep is polishing
glasses with a grimy rag. He looks up as you approach, his
red eyes narrowing with suspicion.

---NPC_LINE---

SPEAKER: Grumthar the Barkeep
"You got business, or you just here to gawk? I don't got
time for tourists."
```text

**Parsed Result:**
```python
NPCUtterance(
    speaker_id="npc-barkeep-grumthar",
    speaker_name="Grumthar the Barkeep",
    text='"You got business, or you just here to gawk? I don\'t got time for tourists."',
    subtext_hint="",
    rhetorical_moves=[]
)
```text

---

## 5. Character Voice Retrieval (RAG)

```mermaid
flowchart TD
    Request[Narrator requests voice snippets<br/>for present NPCs] --> Input[get_voice_snippets<br/>character_ids: list str<br/>era: str<br/>k: int = 6]

    Input --> Loop[For each character_id]

    Loop --> Encode[Encode query:<br/>sentence-transformers/all-MiniLM-L6-v2<br/>Query: voice sample for character_id]

    Encode --> Search[Search LanceDB:<br/>Table: character_voice_chunks<br/>Filter: character_id=id AND era=era<br/>Vector similarity top k]

    Search --> CheckCount{Results >= k/2?}

    CheckCount -->|Yes| UseResults[Use retrieved snippets]
    CheckCount -->|No| Widen[FALLBACK: Widen search<br/>Filter: character_id=id ANY era<br/>Accept cross-era voice samples]

    Widen --> UseWide[Use widened results]

    UseResults --> VoiceSnippet[VoiceSnippet objects:<br/>• character_id<br/>• era<br/>• text 500+ chars dialogue sample<br/>• chunk_id]
    UseWide --> VoiceSnippet

    VoiceSnippet --> Aggregate[Aggregate all character results<br/>dict character_id → list VoiceSnippet]

    Aggregate --> Return[Return to Narrator<br/>Used in LLM context]

    style Search fill:#DDA0DD
    style VoiceSnippet fill:#B0E0E6
```text

**Storage:** `lancedb/` directory, table `character_voice_chunks`

**Voice Snippet Example:**
```python
VoiceSnippet(
    character_id="char-luke-skywalker",
    era="rebellion",
    text='"I\'m not afraid." He squared his shoulders, lightsaber igniting with a snap-hiss. "You\'re going to find that I\'m full of surprises."',
    chunk_id="luke_voice_003"
)
```text

---

## 6. Conversation State Tracking

```mermaid
flowchart TD
    subgraph "Ephemeral State (Per-Turn)"
        LangGraphState[LangGraph State Dict<br/>Flows through pipeline<br/>NOT persisted directly<br/><br/>Key fields:<br/>• history: list str<br/>• recent_narrative: list str<br/>• last_user_inputs: list str<br/>• present_npcs: list dict<br/>• scene_frame: SceneFrame]
    end

    subgraph "Persistent State (Database)"
        TurnEvents[turn_events table<br/>APPEND-ONLY<br/>Event sourcing log<br/><br/>Columns:<br/>• id<br/>• campaign_id<br/>• turn_number<br/>• event_type<br/>• payload_json<br/>• is_hidden<br/>• is_public_rumor<br/>• timestamp]
    end

    subgraph "Events for Dialogue"
        DialogueEvent[Event: DIALOGUE<br/>payload:<br/>speaker: Player<br/>text: user input<br/>turn_number: N<br/><br/>Generated by Mechanic<br/>Written by Commit]

        TurnEvent[Event: TURN<br/>payload:<br/>user_input: str<br/>intent: TALK<br/>is_hidden: true<br/><br/>Meta-event for audit]

        NPCSpeakEvent[Event: NPC_SPEAK<br/>NOT IMPLEMENTED<br/>Could store NPC utterances]
    end

    DialogueEvent --> TurnEvents
    TurnEvent --> TurnEvents

    TurnEvents --> LoadState[On state load:<br/>Query recent events<br/>Rebuild conversation history]

    LoadState --> RebuildHistory[rebuild_history function:<br/>1. Query last N DIALOGUE events<br/>2. Extract speaker + text<br/>3. Build history: list str<br/>4. Set recent_narrative from prose]

    RebuildHistory --> StateReady[GameState ready<br/>history field populated<br/>Used by Director/Narrator]

    StateReady --> NextTurn[Next turn uses history<br/>for narrative continuity]

    NextTurn --> LangGraphState

    LangGraphState --> Pipeline[Pipeline processes turn]

    Pipeline --> CommitNode[Commit Node writes new events]

    CommitNode --> TurnEvents

    style TurnEvents fill:#90EE90
    style DialogueEvent fill:#B0E0E6
    style RebuildHistory fill:#DDA0DD
```text

**Key Insight:** No mutable conversation state object exists. All conversation continuity comes from:
1. **Event log** (authoritative source)
2. **Ephemeral state dict** (rebuilt each turn from events)
3. **History field** (recent narrative paragraphs)

---

## 7. Player Response Generation

```mermaid
flowchart TD
    Start[SuggestionRefiner Node] --> ReadContext[Read from state:<br/>• Narrator prose + NPC utterance<br/>• Scene frame context<br/>• Player stats Charisma/Tech/Combat<br/>• Active quests<br/>• Companion party]

    ReadContext --> LLMCall[LLM qwen3:8b generates<br/>4 ActionSuggestion objects<br/>JSON mode enabled]

    LLMCall --> Suggestions[ActionSuggestion schema:<br/>• label: short text<br/>• intent_text: full description<br/>• category: SOCIAL/EXPLORE/COMMIT<br/>• risk_level: SAFE/RISKY/DANGEROUS<br/>• tone_tag: PARAGON/INVESTIGATE/unkown<br/>• strategy_tag: OPTIMAL/BOLD/SAFE<br/>• consequence_hint: flavor text]

    Suggestions --> CheckParse{JSON parse<br/>success?}

    CheckParse -->|Yes| Convert[action_suggestions_to_player_responses<br/>Converts to PlayerResponse format]
    CheckParse -->|No| Retry[Retry with correction prompt<br/>1 retry allowed]

    Retry --> CheckRetry{Retry parse<br/>success?}

    CheckRetry -->|Yes| Convert
    CheckRetry -->|No| Emergency[FALLBACK:<br/>Use minimal emergency responses<br/>Continue, Investigate, Leave, Attack]

    Emergency --> Convert

    Convert --> StatGate[Apply stat gating:<br/>If Charisma >= 7: add CHARM option<br/>If Tech >= 7: add HACK option<br/>If Combat >= 7: add INTIMIDATE option<br/>Replace neutral option]

    StatGate --> MeaningTag[Add meaning_tag V2.18:<br/>Semantic classification:<br/>• reveal_values<br/>• probe_belief<br/>• challenge_premise<br/>• seek_common_ground<br/>• deflect_with_humor<br/>• commit_to_action<br/>• express_vulnerability]

    MeaningTag --> PlayerResp[4 PlayerResponse objects:<br/>id: resp_1, resp_2, resp_3, resp_4<br/>display_text: UI label<br/>action:<br/>  type: say<br/>  intent: ask/agree/bluff/threaten<br/>  target: npc-id or null<br/>  tone: PARAGON/RENEGADE/INVESTIGATE/NEUTRAL<br/>risk_level: SAFE/RISKY/DANGEROUS<br/>consequence_hint: may gain trust<br/>tone_tag: PARAGON/RENEGADE/etc<br/>meaning_tag: reveal_values/etc]

    PlayerResp --> Return[Return to Commit node<br/>Included in DialogueTurn]

    style LLMCall fill:#FFB6C1
    style StatGate fill:#FFD700
    style PlayerResp fill:#90EE90
```text

**Code Reference:**
- `backend/app/core/nodes/suggestion_refiner.py` → `make_suggestion_refiner_node()`
- `backend/app/core/director_validation.py` → `action_suggestions_to_player_responses()`

---

## 8. DialogueTurn Response Structure

```mermaid
classDiagram
    class DialogueTurn {
        +str turn_id
        +SceneFrame scene_frame
        +NPCUtterance npc_utterance
        +list~PlayerResponse~ player_responses
        +str narrated_prose
        +ValidationReport validation
    }

    class SceneFrame {
        +str location_id
        +str location_name
        +list~NPCRef~ present_npcs
        +str immediate_situation
        +str player_objective
        +str topic_primary
        +str topic_secondary
        +str subtext
        +str npc_agenda
        +list~str~ scene_style_tags
        +str allowed_scene_type
        +dict pressure
    }

    class NPCRef {
        +str id
        +str name
        +str role
        +dict voice_profile
    }

    class VoiceProfile {
        +str belief
        +str wound
        +str taboo
        +str rhetorical_style
        +str tell
    }

    class NPCUtterance {
        +str speaker_id
        +str speaker_name
        +str text
        +str subtext_hint
        +list~str~ rhetorical_moves
    }

    class PlayerResponse {
        +str id
        +str display_text
        +PlayerAction action
        +str risk_level
        +str consequence_hint
        +str tone_tag
        +str meaning_tag
    }

    class PlayerAction {
        +str type
        +str intent
        +str target
        +str tone
    }

    DialogueTurn --> SceneFrame
    DialogueTurn --> NPCUtterance
    DialogueTurn --> PlayerResponse
    SceneFrame --> NPCRef
    NPCRef --> VoiceProfile
    PlayerResponse --> PlayerAction
```text

---

## 9. Dialogue Event Sourcing Flow

```mermaid
sequenceDiagram
    participant Player
    participant API
    participant Pipeline
    participant Mechanic
    participant Narrator
    participant Commit
    participant DB

    Player->>API: POST /turn<br/>user_input: "Ask barkeep about rumors"
    API->>Pipeline: LangGraph invoke(state)
    Pipeline->>Mechanic: Generate DIALOGUE event
    Mechanic-->>Pipeline: Event payload: {speaker: Player, text: input}
    Pipeline->>Narrator: Generate prose + NPC utterance
    Narrator-->>Pipeline: Prose + NPCUtterance extracted
    Pipeline->>Commit: Write events to DB
    Commit->>DB: INSERT turn_events<br/>event_type=DIALOGUE<br/>payload={speaker, text, turn}
    Commit->>DB: INSERT turn_events<br/>event_type=TURN<br/>payload={user_input, intent}
    DB-->>Commit: Events persisted
    Commit-->>Pipeline: State updated with commit confirmation
    Pipeline-->>API: DialogueTurn response
    API-->>Player: JSON response with<br/>npc_utterance + player_responses

    Note over Player,DB: Next Turn
    Player->>API: GET /state
    API->>DB: Query turn_events<br/>WHERE campaign_id<br/>ORDER BY turn_number DESC<br/>LIMIT 10
    DB-->>API: Recent DIALOGUE events
    API->>API: rebuild_history()<br/>Build history: list[str]
    API-->>Player: GameState with history populated

    Note over API,Pipeline: Turn continues with history context
```text

---

## 10. Key Architectural Invariants

From `CLAUDE.md`:

**1. Prose-Only Narrator (V2.15)**

> The Narrator generates only prose text (5-8 sentences, max 250 words). It does NOT generate action suggestions.

**2. KOTOR Dialogue Wheel (4 suggestions)**

> The SuggestionRefiner node is the sole source of suggestions. It generates 4 LLM-powered suggestions per turn.

**3. Single Transaction Boundary**

> Only the Commit node writes to the database. All other nodes are pure functions.

**4. Event Sourcing**

> The `turn_events` table is append-only. Never update or delete events.

**5. SceneFrame Immutability**

> SceneFrame is built once per turn and read by all downstream nodes. No node modifies it.

**6. JSON Retry Pattern**

> LLM agents that expect JSON output must:
> - Use `json_mode=True`
> - Attempt `ensure_json()` repair
> - Retry once with correction prompt
> - Fall back to deterministic output on double failure

**7. Deterministic Fallbacks**

> Every LLM-dependent agent must have a deterministic fallback. If the LLM fails, the game continues with safe defaults.

---

## 11. Conversation Continuity Mechanisms

```mermaid
flowchart LR
    subgraph "Turn N-2"
        T1[Player: Ask about the war<br/>NPC: War is all we know]
    end

    subgraph "Turn N-1"
        T2[Player: What happened to you?<br/>NPC: Lost family to Empire]
    end

    subgraph "Turn N (Current)"
        T3[Player selecting response]
    end

    T1 --> History1[DIALOGUE event written<br/>speaker: Player<br/>text: Ask about war]
    T1 --> History2[NPC utterance stored in prose<br/>Not separate event yet]

    T2 --> History3[DIALOGUE event written<br/>speaker: Player<br/>text: What happened to you?]

    History1 --> DB[(turn_events table)]
    History3 --> DB

    DB --> Load[State loader queries:<br/>SELECT * FROM turn_events<br/>WHERE campaign_id = X<br/>AND event_type = 'DIALOGUE'<br/>ORDER BY turn_number DESC<br/>LIMIT 10]

    Load --> Rebuild[rebuild_history:<br/>history = <br/>Turn N-2: Ask about war<br/>Turn N-1: What happened to you?]

    Rebuild --> Context[Narrator receives history<br/>as context in prompt]

    Context --> T3

    T3 --> Continuity[Narrator can reference:<br/>• Previous player questions<br/>• Established NPC responses<br/>• Emotional trajectory<br/>• Revealed secrets]

    style DB fill:#90EE90
    style Context fill:#DDA0DD
```text

**State Fields for Continuity:**
- `history: list[str]` — Last 2-3 narrative paragraphs (prose only)
- `recent_narrative: list[str]` — Rebuilt from turn_events
- `last_user_inputs: list[str]` — Last N player inputs for tone streak detection

**Limitations:**
- No explicit conversation tree or branching paths
- No dialogue choice memory (player can't reference "that thing I said 5 turns ago")
- NPC memory is implicit through LLM context window, not explicit KB

---

## 12. Complete Dialogue Data Flow

```mermaid
flowchart TB
    Input[Player Input: TALK] --> Router[Router: DIALOGUE_ONLY]
    Router --> Encounter[Encounter: Load NPCs]
    Encounter --> NPCDB[(NPCs from DB:<br/>Era pack<br/>Campaign generated<br/>Companions)]

    NPCDB --> SceneFrame[SceneFrame: Build voice profiles]
    SceneFrame --> VoiceDB[(Voice profiles:<br/>belief, wound, taboo<br/>rhetoric, tell)]

    VoiceDB --> Director[Director: Generate instructions]
    Director --> Narrator[Narrator: Generate prose + NPC line]

    Narrator --> LoreRAG[(LanceDB Lore:<br/>Retrieve context)]
    Narrator --> VoiceRAG[(LanceDB Voice:<br/>Retrieve snippets)]
    Narrator --> StyleRAG[(LanceDB Style:<br/>Retrieve guidance)]

    LoreRAG --> NarratorLLM[Narrator LLM qwen3:8b]
    VoiceRAG --> NarratorLLM
    StyleRAG --> NarratorLLM

    NarratorLLM --> Parse[Parse prose | NPC utterance]
    Parse --> NPCUtter[NPCUtterance object]

    NPCUtter --> SuggRefine[SuggestionRefiner: Generate 4 options]
    SuggRefine --> SuggLLM[Refiner LLM qwen3:8b]
    SuggLLM --> PlayerResp[4 PlayerResponse objects]

    PlayerResp --> Commit[Commit: Write events]
    Commit --> EventsDB[(turn_events table<br/>DIALOGUE events)]

    EventsDB --> Response[DialogueTurn response]
    Response --> UI[UI renders:<br/>• Prose<br/>• NPC dialogue<br/>• 4 player options]

    UI --> NextTurn[Player selects option]
    NextTurn --> LoadState[Next turn: Load state]
    LoadState --> EventsDB
    EventsDB --> History[Rebuild history from events]
    History --> Router

    style SceneFrame fill:#DDA0DD
    style NarratorLLM fill:#B0E0E6
    style EventsDB fill:#90EE90
    style UI fill:#FFD700
```text

---

## 13. File Reference Quick Guide

| Component | File Path | Purpose |
|-----------|-----------|---------|
| **DialogueTurn model** | `backend/app/models/dialogue_turn.py` | Canonical turn output contract |
| **SceneFrame node** | `backend/app/core/nodes/scene_frame.py` | Builds immutable scene snapshot |
| **Narrator agent** | `backend/app/core/agents/narrator.py` | Generates prose + NPC utterance |
| **SuggestionRefiner node** | `backend/app/core/nodes/suggestion_refiner.py` | Generates 4 player responses |
| **Voice retriever** | `backend/app/rag/character_voice_retriever.py` | RAG for character voice snippets |
| **Director validation** | `backend/app/core/director_validation.py` | Converts suggestions to responses |
| **Encounter node** | `backend/app/core/nodes/encounter.py` | Determines present NPCs |
| **Commit node** | `backend/app/core/nodes/commit.py` | ONLY node that writes DB |
| **Event models** | `backend/app/models/events.py` | Event type definitions |
| **State models** | `backend/app/models/state.py` | GameState packet structure |
| **LangGraph pipeline** | `backend/app/core/graph.py` | Pipeline topology |
| **DB schema** | `backend/app/db/schema.sql` | turn_events table definition |

---

## 14. Debugging Dialogue Issues

**Common Problems and Solutions:**

| Issue | Likely Cause | Debug Steps |
|-------|--------------|-------------|
| **No NPC speaks** | `present_npcs` empty | Check Encounter node output, verify era pack NPCs exist |
| **NPC speaks but wrong voice** | Voice profile missing/malformed | Check SceneFrame output, verify voice_profile dict populated |
| **NPC speaks out of character** | Wrong rhetoric style or missing taboo | Verify voice_profile.rhetorical_style and taboo fields |
| **Narrator observation instead of NPC** | `---NPC_LINE---` separator missing | Check Narrator LLM output, verify separator in prompt |
| **Player options don't match context** | SuggestionRefiner not reading NPC utterance | Check refiner input, verify `npc_utterance` passed to prompt |
| **Conversation feels disconnected** | History not loaded | Query turn_events, verify DIALOGUE events persisted |
| **Duplicate/repetitive responses** | LLM temperature too low | Adjust model config, verify temperature >= 0.7 |

**Debug Tools:**
- `debug=true` in `/turn` request: Returns full pipeline diagnostics
- `DEV_CONTEXT_STATS=1`: Shows token budgeting and RAG retrieval stats
- Check logs: `backend/logs/` for agent-level warnings

---

## 15. Future Enhancements (Roadmap)

**Potential improvements to dialogue system:**

1. **Explicit NPC_SPEAK events** — Store NPC utterances as separate events (not just embedded in prose)
2. **Conversation tree memory** — Track dialogue choices and reference them later
3. **Dynamic voice profile updates** — NPCs change rhetoric/taboo based on player actions
4. **Multi-NPC conversations** — Support 3+ way dialogues with turn-taking
5. **Dialogue skill checks** — Persuasion/Intimidation/Deception rolls that gate options
6. **Voice snippet quality scoring** — Rank voice samples by relevance to current scene
7. **Subtext extraction** — Parse NPC utterance for emotional subtext automatically
8. **Conversation pacing** — Detect when dialogue drags, inject action beats
9. **Cross-turn topic tracking** — Remember what topics have been discussed, avoid repetition
10. **NPC memory persistence** — Explicit KB of what each NPC knows about player

---

## Glossary

**DialogueTurn:** Complete turn output containing scene frame, NPC utterance, and player response options

**SceneFrame:** Immutable snapshot of scene context built before Director/Narrator/SuggestionRefiner run

**Voice Profile:** 5-component character description (belief, wound, taboo, rhetorical style, tell) that guides NPC dialogue

**NPCUtterance:** Parsed NPC dialogue line with speaker attribution, extracted from Narrator output

**PlayerResponse:** Structured player dialogue option for KOTOR wheel (display text, action intent, tone, risk, consequences)

**Voice Snippet:** RAG-retrieved example dialogue from canonical sources (movies, novels, games) to guide NPC voice

**KOTOR Topics:** Primary/secondary soul-level conversation themes (trust, debt, identity, sacrifice, etc.) from V2.18

**NPC Agenda:** What the NPC wants from the player in this scene, derived from arc stage (test, request, demand, offer)

**Scene Pressure:** Alert level + heat level indicating danger/urgency, affects dialogue tone

**Meaning Tag:** Semantic classification of player response (reveal_values, probe_belief, etc.) for analytics

**Event Sourcing:** Append-only turn_events log, all conversation state derived from events

**Immutable Scene Snapshot:** SceneFrame built once per turn, read by all nodes, never modified

---

## See Also

- `/docs/player_ux_flow.md` — Player-facing experience flow
- `/docs/architecture.md` — Overall system architecture
- `/API_REFERENCE.md` — API contracts for DialogueTurn
- `/docs/07_known_issues_and_risks.md` — Known dialogue system limitations
- `/docs/lore_pipeline_guide.md` — How voice snippets are ingested
