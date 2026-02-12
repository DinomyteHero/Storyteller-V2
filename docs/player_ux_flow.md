# Player User Experience Flow Diagram

## Overview

This document visualizes the complete player journey through Storyteller AI, from campaign creation to turn-by-turn gameplay.

---

## 1. Campaign Creation Flow

```mermaid
flowchart TD
    Start([Player Starts Game]) --> Choice{Choose Creation Method}

    Choice --> | Auto Setup| AutoAPI[POST /v2/setup/auto<br/>Player provides:<br/>- Time period<br/>- Genre/themes<br/>- Character concept<br/>- Background<br/>- Gender]
    Choice --> | Manual Setup| ManualAPI[POST /v2/campaigns<br/>Player provides:<br/>- Title<br/>- Player name<br/>- Stats<br/>- Starting location<br/>- HP]

    AutoAPI --> Architect[Architect Agent Generates:<br/>- Campaign skeleton<br/>- Locations<br/>- Factions<br/>- NPCs]
    Architect --> Biographer[Biographer Agent Generates:<br/>- Character sheet<br/>- Stats<br/>- Starting location<br/>- Background story]

    ManualAPI --> DBInit[Initialize Database]
    Biographer --> DBInit

    DBInit --> FirstState[System Creates:<br/>✓ Campaign record<br/>✓ Player character<br/>✓ World state<br/>✓ Initial factions<br/>✓ Era companions<br/>✓ Quest seeds]

    FirstState --> Ready([Campaign Ready<br/>Turn 1 Complete])

    style AutoAPI fill:#e1f5ff
    style ManualAPI fill:#e1f5ff
    style Ready fill:#90EE90
```

---

## 2. Main Gameplay Loop (Turn-by-Turn)

```mermaid
flowchart TD
    PlayerReady([Player Views Game State]) --> ViewState[GET /campaigns/{id}/state<br/><br/>Player sees:<br/>- Character sheet HP/stats/credits<br/>- Current location<br/>- Inventory<br/>- Companion status<br/>- Quest log<br/>- Faction reputation<br/>- World time<br/>- News feed]

    ViewState --> LastTurn{First Turn?}
    LastTurn --> | No| ShowNarrative[Display Previous Turn:<br/>- Narrative prose 5-8 sentences<br/>- 4 KOTOR-style suggestions<br/>- NPC dialogue if present<br/>- Quest/companion updates]
    LastTurn --> | Yes| ShowOpening[Show Campaign Opening]

    ShowNarrative --> PlayerChoice[Player Selects Action<br/>from 4 Suggestions:<br/><br/>Each shows:<br/>- Label text<br/>- Tone PARAGON/RENEGADE/INVESTIGATE/NEUTRAL<br/>- Risk level SAFE/RISKY/DANGEROUS<br/>- Consequence hint]
    ShowOpening --> PlayerChoice

    PlayerChoice --> SubmitTurn[POST /campaigns/{id}/turn<br/>Body: user_input text]

    SubmitTurn --> Pipeline[Pipeline Processing<br/>See detailed flow below]

    Pipeline --> Response[TurnResponse Received:<br/>✓ narrated_text<br/>✓ suggested_actions 4<br/>✓ player_sheet updated<br/>✓ inventory changed<br/>✓ quest_log updated<br/>✓ world_time_minutes<br/>✓ party_status<br/>✓ faction_reputation<br/>✓ news_feed<br/>✓ dialogue_turn if NPC present<br/>✓ warnings]

    Response --> UpdateUI[UI Updates All State:<br/>- Show new narrative<br/>- Display 4 new suggestions<br/>- Update character sheet<br/>- Show companion reactions<br/>- Display quest changes<br/>- Show time passed<br/>- Render NPC dialogue wheel]

    UpdateUI --> NextTurn{Continue?}
    NextTurn --> | Yes| ViewState
    NextTurn --> | No| EndCampaign[POST /campaigns/{id}/complete<br/>Save legacy & outcome]

    EndCampaign --> GameOver([Campaign Complete])

    style PlayerChoice fill:#FFD700
    style Response fill:#90EE90
    style GameOver fill:#FF6B6B
```

---

## 3. Pipeline Processing Detail (Inside Each Turn)

```mermaid
flowchart TD
    Input[Player Input Text] --> Router[ROUTER NODE<br/>Classifies intent:<br/>- META system command<br/>- TALK pure dialogue<br/>- MECHANIC action/persuasion]

    Router --> | META| MetaShortcut[Meta Handler<br/>No time cost<br/>Query only]
    Router --> | TALK| SkipMechanic[Skip Mechanic<br/>Fast dialogue path]
    Router --> | MECHANIC| RunMechanic[MECHANIC NODE<br/>Deterministic Python only<br/>- Roll dice<br/>- Calculate DC<br/>- Resolve success/fail<br/>- Apply damage/effects<br/>- Time cost 8-60 min<br/>- Generate events]

    MetaShortcut --> CommitMeta[COMMIT NODE<br/>Return query result]
    CommitMeta --> OutputMeta[Response: system info]

    SkipMechanic --> Encounter[ENCOUNTER NODE<br/>Determine present NPCs<br/>based on location]
    RunMechanic --> Encounter

    Encounter --> WorldSim[WORLDSIM NODE<br/>Tick world clock<br/>Every ~240 min:<br/>- Factions move<br/>- Rumors emerge<br/>- Locations change]

    WorldSim --> CompReact[COMPANION REACTION<br/>Deterministic affinity deltas<br/>based on:<br/>- Action tone<br/>- Companion personality<br/>- Alignment values]

    CompReact --> ArcPlan[ARC PLANNER<br/>Determine narrative stage:<br/>- Setup<br/>- Rising action<br/>- Climax<br/>- Resolution]

    ArcPlan --> SceneFrame[SCENE FRAME NODE<br/>Build immutable snapshot:<br/>- Location details<br/>- Present NPCs<br/>- Immediate situation<br/>- Player objective<br/>- KOTOR topics<br/>- Scene pressure]

    SceneFrame --> Director[DIRECTOR NODE<br/>LLM generates:<br/>- Narrative instructions<br/>- Tone guidance<br/>- Focus elements<br/>- Emotional beats]

    Director --> Narrator[NARRATOR NODE<br/>LLM writes prose:<br/>- 5-8 sentences<br/>- Max 250 words<br/>- Prose ONLY<br/>- No suggestions]

    Narrator --> Validator[NARRATIVE VALIDATOR<br/>Checks prose quality]

    Validator --> Refiner[SUGGESTION REFINER<br/>LLM generates 4 options:<br/>- KOTOR dialogue wheel style<br/>- Tone tags<br/>- Risk levels<br/>- Consequence hints<br/>- Meaning tags]

    Refiner --> Commit[COMMIT NODE<br/>ONLY node that writes DB:<br/>- Append turn_events<br/>- Update projections<br/>- characters table<br/>- inventory table<br/>- campaigns.world_state]

    Commit --> Output[TurnResponse<br/>Returned to player]

    style Router fill:#FFE5B4
    style RunMechanic fill:#FFB6C1
    style Narrator fill:#B0E0E6
    style Refiner fill:#DDA0DD
    style Commit fill:#90EE90
    style Output fill:#90EE90
```

---

## 4. Action Type Routing & Pipeline Paths

```mermaid
flowchart LR
    subgraph "Action Types"
        Meta[META<br/>check inventory<br/>show map<br/>help]
        Talk[TALK<br/>DIALOGUE_ONLY<br/>Say hello<br/>Ask about X<br/>Greet NPC]
        DAction[DIALOGUE WITH ACTION<br/>Persuade guard<br/>Intimidate enemy<br/>Convince ally<br/>Bribe official]
        PAction[PHYSICAL ACTION<br/>Attack<br/>Steal<br/>Hack<br/>Run<br/>Search<br/>Sneak]
    end

    subgraph "Pipeline Nodes Run"
        N1[Router]
        N2[Mechanic]
        N3[Encounter]
        N4[WorldSim]
        N5[CompanionReaction]
        N6[ArcPlanner]
        N7[SceneFrame]
        N8[Director]
        N9[Narrator]
        N10[NarrativeValidator]
        N11[SuggestionRefiner]
        N12[Commit]
    end

    Meta --> | Direct path| N1
    N1 -.-> | Skip all| N12

    Talk --> N1
    N1 --> N3

    DAction --> N1
    N1 --> N2
    N2 --> N3

    PAction --> N1
    N1 --> N2

    N3 --> N4
    N4 --> N5
    N5 --> N6
    N6 --> N7
    N7 --> N8
    N8 --> N9
    N9 --> N10
    N10 --> N11
    N11 --> N12

    style Meta fill:#FFE5B4
    style Talk fill:#B0E0E6
    style DAction fill:#DDA0DD
    style PAction fill:#FFB6C1
```

**Pipeline Path Summary:**

- **META**: Router → Commit (instant, 0 time cost)
- **TALK**: Router → Encounter → WorldSim → CompanionReaction → ArcPlanner → SceneFrame → Director → Narrator → Validator → SuggestionRefiner → Commit (~8-18 min)
- **DIALOGUE_WITH_ACTION**: Router → **Mechanic** → Encounter → ... → Commit (8-30 min, with roll)
- **PHYSICAL_ACTION**: Router → **Mechanic** → Encounter → ... → Commit (20-60 min, with roll)

---

## 5. What Player Sees Each Turn

```mermaid
flowchart TB
    Turn[Turn Response Arrives] --> Narrative[Narrative Prose<br/>5-8 sentences<br/>250 words max<br/>Written by Narrator LLM]

    Turn --> Suggestions[4 Action Suggestions<br/>KOTOR Dialogue Wheel Style]

    Suggestions --> S1[Option 1: PARAGON<br/>Tone: Blue<br/>Risk: SAFE<br/>Help/diplomacy/empathy]
    Suggestions --> S2[Option 2: INVESTIGATE<br/>Tone: Gold<br/>Risk: SAFE<br/>Observe/ask/learn]
    Suggestions --> S3[Option 3: RENEGADE<br/>Tone: Red<br/>Risk: RISKY<br/>Aggressive/decisive]
    Suggestions --> S4[Option 4: NEUTRAL<br/>Tone: Gray<br/>Risk: Varies<br/>Tactical/action]

    Turn --> State[Updated Game State]

    State --> Char[Character Sheet<br/>- HP current/max<br/>- Stats<br/>- Credits<br/>- Location<br/>- Stress level<br/>- Mood]

    State --> Inv[Inventory<br/>- Items & quantities<br/>- Equipment<br/>- Key items]

    State --> Party[Party Status<br/>Per companion:<br/>- Affinity -100 to +100<br/>- Loyalty stage<br/>- Mood tag<br/>- Influence/trust/respect/fear]

    State --> Quests[Quest Log<br/>- Active quests<br/>- Current stage<br/>- Objectives<br/>- Status]

    State --> World[World State<br/>- Time elapsed minutes<br/>- Faction reputations<br/>- News feed headlines<br/>- Active rumors]

    Turn --> Dialogue{NPC Present?}
    Dialogue --> | Yes| NPCWheel[NPC Dialogue Wheel<br/>- Scene frame context<br/>- NPC utterance<br/>- 4 response options<br/>- Voice profile<br/>- Topics belief/wound/taboo]
    Dialogue --> | No| Continue[Action suggestions only]

    Turn --> Warnings[Warnings Array<br/>- Quest updates<br/>- Companion reactions<br/>- World events<br/>- System messages]

    style Narrative fill:#B0E0E6
    style S1 fill:#87CEEB
    style S2 fill:#FFD700
    style S3 fill:#FF6B6B
    style S4 fill:#D3D3D3
    style NPCWheel fill:#DDA0DD
```

---

## 6. Time & World Progression

```mermaid
flowchart TD
    Action[Player Takes Action] --> TimeCost{Action Type?}

    TimeCost --> | META| T0[Time cost: 0 minutes<br/>No world advancement]
    TimeCost --> | TALK| T1[Time cost: 8-18 minutes<br/>Dialogue duration]
    TimeCost --> | DIALOGUE ACTION| T2[Time cost: 8-30 minutes<br/>Persuasion + conversation]
    TimeCost --> | PHYSICAL ACTION| T3[Time cost: 20-60 minutes<br/>Combat/investigation/travel]

    T0 --> Check
    T1 --> Check{World Time % 240 == 0?}
    T2 --> Check
    T3 --> Check

    Check --> | No| NoTick[Continue normally]
    Check --> | Yes| Tick[WORLD TICK TRIGGERS<br/>Every ~240 minutes / 4 hours]

    Tick --> Factions[Factions Move:<br/>- Execute plans<br/>- Shift control<br/>- Generate events]

    Factions --> Rumors[Rumors Emerge:<br/>- News feed updates<br/>- New headlines<br/>- Faction announcements]

    Rumors --> Locations[Locations Change:<br/>- Threat levels<br/>- Controlling factions<br/>- NPC movements]

    Locations --> Quest[Quest Timers:<br/>- Time-sensitive quests<br/>- Deadline warnings<br/>- Auto-fail expired]

    Quest --> WorldUpdated[World State Updated]

    NoTick --> Continue[Turn Continues]
    WorldUpdated --> Continue

    Continue --> PlayerSees[Player Sees:<br/>✓ Time elapsed shown<br/>✓ News feed changes<br/>✓ Quest warnings<br/>✓ Location updates<br/>✓ Faction reputation shifts]

    style Tick fill:#FFB6C1
    style PlayerSees fill:#90EE90
```

**Key Insight:** Time pressure creates meaningful choices:

- **Rush through actions** = cover more ground, but miss clues and opportunities
- **Take time to investigate** = gather intel, but world advances without you

---

## 7. Companion Reaction System

```mermaid
flowchart TD
    PlayerAction[Player Chooses Action] --> Tone{Action Tone?}

    Tone --> | PARAGON| ToneP[Empathetic/diplomatic<br/>Help others<br/>Uphold ideals]
    Tone --> | RENEGADE| ToneR[Aggressive/decisive<br/>Get results<br/>Break rules]
    Tone --> | INVESTIGATE| ToneI[Cautious/thoughtful<br/>Gather information]
    Tone --> | NEUTRAL| ToneN[Tactical/pragmatic]

    ToneP --> CompCheck[Companion Reaction Node<br/>Deterministic calculation]
    ToneR --> CompCheck
    ToneI --> CompCheck
    ToneN --> CompCheck

    CompCheck --> Match{Match Companion<br/>Personality?}

    Match --> | Strong Match| Approve[Affinity +5 to +15<br/>Mood: PLEASED/SUPPORTIVE<br/>Potential loyalty progress]
    Match --> | Weak Match| Neutral[Affinity +0 to -2<br/>Mood: NEUTRAL/WARY]
    Match --> | Conflict| Disapprove[Affinity -5 to -20<br/>Mood: DISAPPROVING/HOSTILE<br/>May leave party if severe]

    Approve --> Thresholds{Cross Affinity<br/>Threshold?}
    Neutral --> Thresholds
    Disapprove --> Thresholds

    Thresholds --> | Reach +40| Trusted[Loyalty Stage 1: TRUSTED<br/>Unlock personal quest<br/>New dialogue options]
    Thresholds --> | Reach +75| Loyal[Loyalty Stage 2: LOYAL<br/>Combat bonuses<br/>Romance available<br/>Final quest unlocked]
    Thresholds --> | Fall Below -40| Hostile[Companion Leaves Party<br/>May become enemy]
    Thresholds --> | No threshold| Continue[Update party status]

    Trusted --> Display[Display in TurnResponse:<br/>party_status array<br/>- Affinity score<br/>- Loyalty progress<br/>- Mood tag<br/>- Influence/trust/respect axes]
    Loyal --> Display
    Hostile --> Display
    Continue --> Display

    Display --> PlayerSees[Player Sees Reaction:<br/>Companion mood changes<br/>shown in UI<br/>Warnings if threshold crossed]

    style Approve fill:#90EE90
    style Disapprove fill:#FF6B6B
    style Loyal fill:#FFD700
    style Hostile fill:#8B0000
```

**Companion Personality Examples:**

- **Idealist** (e.g., Jedi Knight): Approves PARAGON, disapproves RENEGADE
- **Pragmatist** (e.g., Smuggler): Approves tactical NEUTRAL, tolerates RENEGADE
- **Rebel** (e.g., Freedom Fighter): Approves defiance, disapproves submission
- **Cynic** (e.g., Bounty Hunter): Approves RENEGADE efficiency, mocks PARAGON idealism

---

## 8. Quest & Objective Flow

```mermaid
flowchart TD
    Start[Campaign Start] --> Seed[Era Pack Seeds Initial Quests<br/>5-10 quests available<br/>Status: AVAILABLE]

    Seed --> Discover{How Quest Activates?}

    Discover --> | Player visits location| Trigger1[Quest auto-activates<br/>Status: ACTIVE<br/>Warning shown]
    Discover --> | NPC conversation| Trigger2[NPC offers quest<br/>Player accepts<br/>Status: ACTIVE]
    Discover --> | World event| Trigger3[News feed / rumor<br/>Quest becomes available<br/>Status: AVAILABLE]

    Trigger1 --> Active[Quest in Quest Log<br/>Shows:<br/>- Title<br/>- Current stage<br/>- Objectives<br/>- Progress]
    Trigger2 --> Active
    Trigger3 --> WaitAccept[Quest visible but not active]
    WaitAccept --> Active

    Active --> PlayerAct[Player Takes Actions]

    PlayerAct --> Check{Objective Met?}

    Check --> | No| Advance[Continue quest]
    Check --> | Yes - Stage Complete| NextStage[Advance to next stage<br/>stages_completed += 1<br/>current_stage_idx += 1<br/>Warning: Stage complete]
    Check --> | Yes - Quest Complete| Complete[Status: COMPLETED<br/>Rewards granted:<br/>- Credits<br/>- Items<br/>- Reputation<br/>- Experience]
    Check --> | Fail Condition Met| Failed[Status: FAILED<br/>World state updated<br/>Consequences applied]

    NextStage --> Active

    Complete --> Legacy[Quest outcome saved<br/>in campaign legacy<br/>May affect future campaigns]
    Failed --> Legacy

    Advance --> Time{Time Limit?}
    Time --> | Expired| Failed
    Time --> | Ongoing| Continue[Next turn]

    Complete --> Continue

    Continue --> PlayerView[Player sees in quest_log:<br/>All quests with:<br/>- Status<br/>- Current stage<br/>- Stages completed<br/>- Activated turn#]

    style Complete fill:#90EE90
    style Failed fill:#FF6B6B
    style Legacy fill:#FFD700
```

**Quest Stage Example:**

```json
{
  "quest-rescue-pilot": {
    "status": "active",
    "current_stage_idx": 2,
    "stages_completed": 1,
    "stages": [
      {"description": "Find the crash site", "completed": true},
      {"description": "Locate the pilot", "completed": true},
      {"description": "Escort pilot to safety", "completed": false},
      {"description": "Report to command", "completed": false}
    ]
  }
}
```

---

## 9. Key UX Principles

```mermaid
mindmap
  root((Storyteller UX))
    Constrained Agency
      4 suggestions only
      No free text after setup
      KOTOR dialogue wheel
      Meaningful choices not infinite freedom

    Time Pressure
      Every action costs time
      World advances every 240 min
      Rush = miss opportunities
      Wait = world changes

    Deterministic Core
      Mechanic is pure Python
      No LLM in dice rolls
      Companion reactions predictable
      Replayable outcomes

    Narrative Immersion
      Narrator writes prose only
      5-8 sentences per turn
      Psychology affects tone not outcome
      NPC voice profiles KOTOR style

    Graceful Degradation
      LLM fallbacks always present
      Ollama-first architecture
      Game never crashes from LLM failure
      Minimal emergency suggestions

    Transparent State
      Full GameState visible
      All changes shown to player
      Warnings for important events
      Debug mode available
```

---

## 10. Complete Player Journey Summary

```mermaid
flowchart TB
    subgraph "Phase 1: Setup 5 min"
        P1Start([Player Opens Game]) --> P1Create[Create Campaign<br/>Auto or Manual]
        P1Create --> P1Ready[Campaign Ready<br/>Character Sheet Generated]
    end

    subgraph "Phase 2: Early Game Turns 1-20"
        P2Start[View Opening State] --> P2Explore[Explore starting location<br/>Talk to NPCs<br/>Accept first quest]
        P2Explore --> P2Companions[Recruit 1-2 companions<br/>Learn personalities]
        P2Companions --> P2Tutorial[Learn action types<br/>PARAGON vs RENEGADE<br/>Time management]
    end

    subgraph "Phase 3: Mid Game Turns 20-100"
        P3Quests[Progress multiple quests<br/>Navigate faction conflicts<br/>Build companion loyalty]
        P3Quests --> P3World[World ticks advance<br/>News feed updates<br/>Faction territories shift]
        P3World --> P3Choices[Make alignment choices<br/>LIGHT/DARK<br/>PARAGON/RENEGADE]
        P3Choices --> P3Companion[Companion loyalty missions<br/>Romance options<br/>Personal story arcs]
    end

    subgraph "Phase 4: Late Game Turns 100+"
        P4Climax[Narrative arc climax<br/>Major faction conflicts<br/>High-stakes quests]
        P4Climax --> P4Resolution[Campaign resolution<br/>Companion fates decided<br/>Faction outcomes]
        P4Resolution --> P4Complete[Complete campaign<br/>Save legacy]
    end

    P1Ready --> P2Start
    P2Tutorial --> P3Quests
    P3Companion --> P4Climax
    P4Complete --> P5[Legacy Saved<br/>Start New Campaign]

    style P1Ready fill:#90EE90
    style P3Companion fill:#FFD700
    style P4Complete fill:#FF6B6B
    style P5 fill:#DDA0DD
```

**Average Session Lengths:**

- **Short session:** 5-10 turns, 15-30 minutes real time
- **Medium session:** 20-40 turns, 1-2 hours real time
- **Long campaign:** 100-300 turns, 10-30 hours total playtime

---

## API Endpoint Quick Reference

| Endpoint | Method | Purpose | When Player Uses |
| ---------- | -------- | --------- | ------------------ |
| `/v2/setup/auto` | POST | Auto-generate campaign | First time setup |
| `/v2/campaigns` | POST | Manual campaign creation | First time setup (advanced) |
| `/v2/campaigns/{id}/state` | GET | Fetch full game state | Every session start |
| `/v2/campaigns/{id}/turn` | POST | Execute one turn | Every player action |
| `/v2/campaigns/{id}/turn_stream` | GET | Stream turn with SSE | Real-time narrative mode |
| `/v2/campaigns/{id}/transcript` | GET | View past turns | Review history |
| `/v2/campaigns/{id}/world_state` | GET | Get world flags/factions | Debug/inspect world |
| `/v2/campaigns/{id}/locations` | GET | View location map | Travel planning |
| `/v2/campaigns/{id}/rumors` | GET | Get recent rumors | Intelligence gathering |
| `/v2/campaigns/{id}/complete` | POST | End campaign & save legacy | Campaign finished |
| `/v2/era/{era}/backgrounds` | GET | List character backgrounds | Character creation |
| `/v2/era/{era}/companions` | GET | Preview companions | Party planning |
| `/v2/player/profiles` | GET | List player profiles | Cross-campaign tracking |

---

## Glossary of Player-Facing Terms

**Turn:** One complete action cycle (player input → pipeline → narrative response)

**KOTOR Wheel:** 4-option dialogue system inspired by Knights of the Old Republic, color-coded by tone

**Affinity:** Companion relationship score (-100 to +100)

**Loyalty Stage:** Companion trust level (0=Stranger, 1=Trusted, 2=Loyal)

**World Tick:** Automatic world advancement every ~240 minutes (factions move, rumors emerge)

**Action Type:** Classification of player input (META, TALK, DIALOGUE_WITH_ACTION, PHYSICAL_ACTION)

**Risk Level:** Difficulty indicator (SAFE, RISKY, DANGEROUS) affecting DC rolls

**Tone:** Action alignment (PARAGON=blue, RENEGADE=red, INVESTIGATE=gold, NEUTRAL=gray)

**Time Cost:** Minutes of world time consumed by action (0 for META, 8-60 for others)

**Scene Frame:** Immutable snapshot of current situation (location, NPCs, objectives, topics)

**Mechanic:** Deterministic dice roll and rules resolution (no LLM)

**Narrator:** LLM agent that writes 5-8 sentence prose descriptions

**Suggestion Refiner:** LLM agent that generates 4 KOTOR-style action options

**Era Pack:** Curated content bundle for a Star Wars time period (locations, NPCs, quests, companions)

**Legacy:** Saved campaign outcome that influences future playthroughs

**Projection:** Derived database table (characters, inventory) built from event log

---

## This Diagram's Purpose

This flow diagram is designed to help:

- **Players** understand what the system does turn-by-turn
- **Developers** see the player-facing experience separate from internal pipeline
- **Designers** identify UX touchpoints and state visibility
- **QA** test the complete player journey end-to-end

For internal pipeline architecture details, see `/docs/architecture.md`.
For API contracts and field definitions, see `/API_REFERENCE.md`.
For deep technical docs, see `/docs/00-09` numbered series.
