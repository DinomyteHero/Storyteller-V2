# {RULE_SYSTEM_DISPLAY_NAME} — Rule System Document
# Rule System ID: {rule_system_id}
# Version: 1.0
# Compatible with: Storyteller-V2 ResolutionAgent
#
# INSTRUCTIONS FOR AUTHORING A NEW RULE SYSTEM
# =============================================
# 1. Replace all {PLACEHOLDERS} with your universe's specifics.
# 2. Keep section headers exactly as written (## STATS, ## ACTION CLASSIFICATION, etc.)
#    — the ResolutionAgent expects these headings.
# 3. Every section marked [REQUIRED] must be filled in.
# 4. Sections marked [OPTIONAL] can be removed if not applicable.
# 5. After authoring, add an entry to catalog.yaml and a setting.yaml for your universe.
# 6. Ingest into LanceDB for RAG retrieval (optional but recommended for long rule systems):
#    python -m ingestion.ingest_rules \
#      --input data/static/rule_systems/{rule_system_id}.md \
#      --rule-system {rule_system_id} --setting-id {setting_id}
#
# DELETE THESE INSTRUCTIONS before using in production.

---

## OVERVIEW [REQUIRED]

{RULE_SYSTEM_DISPLAY_NAME} is the resolution system for {SETTING_NAME} campaigns.
It governs how player actions are judged, how the world reacts, and how narrative
consequences are generated.

**Genre:** {GENRE — e.g. epic fantasy, space opera, political intrigue, horror}
**Tone:** {TONE — e.g. gritty and low-magic, mythic and operatic, pulpy adventure}
**Primary Conflict:** {WHAT DRIVES DRAMA — e.g. survival vs. empire, corrupting power, political scheming}

---

## STATS [REQUIRED]

Characters are defined by six stats rated 1–10 (3 is average, 7 is exceptional, 10 is legendary).

| Stat | Governs |
|------|---------|
| {STAT_1} | {WHAT IT COVERS — social actions, combat, etc.} |
| {STAT_2} | {WHAT IT COVERS} |
| {STAT_3} | {WHAT IT COVERS} |
| {STAT_4} | {WHAT IT COVERS} |
| {STAT_5} | {WHAT IT COVERS} |
| {STAT_6} | {WHAT IT COVERS — setting-specific, e.g. Force / Grace / Intrigue} |

**Derived stats:**
- **HP (Hit Points):** 10 + Physique (or {STAT_3}). Reaching 0 triggers a Consequence event.
- **Stress:** Tracks mental/emotional strain. Reaching max stress triggers a Breakdown.
- **Credits / Resources:** Setting-specific currency for gear, bribes, travel.

---

## ACTION CLASSIFICATION [REQUIRED]

Every player action maps to an action type that determines which stat governs resolution.

| Action Type | Governing Stat | Examples |
|-------------|----------------|---------|
| SOCIAL | {STAT_1} | Persuasion, deception, negotiation, leadership |
| STEALTH | {STAT_2} | Sneaking, hiding, tailing a target, disguise |
| COMBAT | {STAT_3} | Melee attacks, physical defense, wrestling |
| TECHNICAL | {STAT_4} | Hacking, medicine, crafting, navigation, engineering |
| RESIST | {STAT_5} | Withstanding fear, pain, corruption, dark temptation |
| {SPECIAL} | {STAT_6} | {SETTING-SPECIFIC — e.g. Force use, One Ring temptation, political scheming} |
| EXPLORE | {BEST_FIT_STAT} | Investigation, searching, tracking, survival |
| MOVE | {BEST_FIT_STAT} | Athletics, climbing, swimming, chasing, fleeing |

**Fallback:** When an action doesn't fit a category, use the stat most relevant to the
player's declared approach. Always favor narrative intent over strict categorization.

---

## DIFFICULTY BANDS [REQUIRED]

Set difficulty based on context, NPC opposition, environment, and player character stats.

| Band | Target Number | When to Use |
|------|--------------|-------------|
| Trivial | 2 | Routine tasks with no meaningful opposition |
| Easy | 3 | Simple tasks; a trained person succeeds reliably |
| Moderate | 5 | Requires skill and focus; average characters might fail |
| Hard | 7 | Genuinely challenging; failure is plausible even for experts |
| Formidable | 9 | Near the edge of human capability |
| Extreme | 11+ | Legendary feats; near-impossible without special circumstances |

**Modifiers (adjust difficulty up or down):**
- Relevant character background / specialization: −1
- Environmental advantage (high ground, cover, surprise): −1
- Environmental disadvantage (darkness, exhaustion, injury): +1
- NPC is prepared, alert, or superior: +1
- Character is wounded, stressed, or off-balance: +1
- Player has allies actively assisting: −1

---

## NARRATIVE DICE RESOLUTION [REQUIRED]

Roll virtual narrative dice (resolved by the ResolutionAgent internally). The result
falls on a spectrum from Despair to Triumph:

| Result | Narrative Meaning |
|--------|-------------------|
| **Triumph** | Succeed brilliantly + unexpected bonus (information gained, enemy resource lost, etc.) |
| **Success** | Clean success. Goal achieved, no complications. |
| **Success + Threat** | Succeed but with a complication (costs resources, makes noise, partial damage, etc.) |
| **Failure + Advantage** | Fail the goal but gain something (intel, opening for next action, complication for enemy) |
| **Failure** | Goal not achieved. Clear consequence follows. |
| **Despair** | Fail + significant setback (alarm raised, ally hurt, resource lost, morale broken) |

**Probability guidance (stat vs difficulty):**
- Stat ≥ Difficulty +3: Triumph or Success (85–95%)
- Stat = Difficulty: Success or Success+Threat (60–70%)
- Stat ≤ Difficulty −2: Failure or Despair (60–80%)

**Mixed result guidance:**
Prefer Success+Threat and Failure+Advantage for interesting narrative tension.
Pure Triumph and Despair should punctuate exceptional moments, not be routine.

---

## EVENT GENERATION RULES [REQUIRED]

Generate a narrative event (in the output `events` array) when:
1. The dice result is Despair or Triumph
2. A Threat causes a side-effect that warrants world notice
3. An Advantage opens a new story opportunity
4. The action directly affects an NPC, faction, or location state
5. A world-reaction flag is raised (see WORLD REACTION FLAG)

Events are short (1–2 sentences), third-person, present-tense:
- "A guard patrol rounds the corner, drawn by the sound of the scuffle."
- "The data terminal unlocks; a priority Imperial communiqué is visible on screen."

---

## ALIGNMENT AND MORAL IMPACT [REQUIRED]

Track the moral weight of player choices on a dual axis:

**{MORAL_AXIS_1}** (e.g. Light–Dark, Honor–Dishonor, Corruption–Purity):
- Range: −10 (fully {DARK_POLE}) to +10 (fully {LIGHT_POLE})
- +1 for choices aligned with {LIGHT_POLE} values
- −1 for choices aligned with {DARK_POLE} values
- Extreme values (±8+) affect NPC reactions and unlock/lock story options

**{MORAL_AXIS_2}** (e.g. Paragon–Renegade, Lawful–Chaotic):
- Range: −5 to +5
- Affects reputation with {FACTION_TYPE} factions

---

## FACTION IMPACT [REQUIRED]

Most consequential actions affect at least one faction's standing with the player.

| Standing | Range | Consequences |
|----------|-------|-------------|
| Allied | 80–100 | Active support; quests offered; discounts and safe houses |
| Friendly | 60–79 | Helpful; will assist if asked; no active opposition |
| Neutral | 40–59 | Indifferent; business as usual |
| Unfriendly | 20–39 | Suspicious; may report player to rivals or authorities |
| Hostile | 0–19 | Active opposition; ambushes, bounties, blocked access |

**Delta guidelines:**
- Minor action (helped one member, passed false information): ±3–5
- Significant action (completed a mission, betrayed an agent): ±10–20
- Major action (destroyed a resource, rescued a key figure): ±20–40

---

## COMPANION IMPACT [REQUIRED]

Companions track affinity (−100 to +100). Changes based on:
- Alignment with companion's personal values / backstory
- Whether the player consulted or ignored them
- Outcome: companions feel the cost of failures too

**Delta guidelines:**
- Action aligns with companion's core values: +5 to +15
- Action conflicts with companion's values: −5 to −20
- Player explicitly asks companion's opinion and follows it: +5
- Player explicitly ignores companion's strong objection: −10

---

## STRESS DELTA [REQUIRED]

Stress tracks mental/emotional strain (0 = calm, max = breakdown threshold).

| Situation | Stress Delta |
|-----------|-------------|
| Triumph | −2 (relief, euphoria) |
| Success | −1 |
| Failure | +1 |
| Despair | +3 |
| Witnessing a traumatic event | +2 to +5 |
| Rest, recovery, or comfort scene | −3 to −5 |
| {SETTING_SPECIFIC_STRESS_SOURCE} | {DELTA} |

---

## WORLD REACTION FLAG [REQUIRED]

Set `world_reaction_needed: true` when the action:
- Draws attention from authorities, enemies, or civilians
- Changes a location's status (guards alerted, crowd dispersed, building damaged)
- Triggers a faction response that should propagate to the WorldMindAgent
- Produces a rumor or visible consequence other characters would notice

Otherwise set `world_reaction_needed: false`.

---

## NARRATIVE FACTS [REQUIRED]

Extract 1–3 narrative facts from each resolved action — declarative statements about
what is now true in the world. These feed the Truth Ledger / Continuity Agent.

Format: short, declarative, present-tense.
Examples:
- "{Character} is now known to faction {X} as a {description}."
- "The {location} is now {state — on fire, locked down, evacuated}."
- "{NPC} has learned that the player is {fact}."

---

## TONE TAG [REQUIRED]

Assign one tone tag to each resolved action. The Narrator uses this to calibrate prose style.

| Tag | When to Use |
|-----|-------------|
| TRIUMPH | Transcendent success; heroic moment |
| PARAGON | Noble, principled action regardless of outcome |
| GRITTY | Success through pain, cost, or moral compromise |
| TENSION | High-stakes moment; outcome not yet certain |
| SETBACK | Failure that reveals character or sets up future drama |
| DARK | Action aligned with {DARK_POLE} values or with significant cost |
| COMEDIC | Absurd, ironic, or unexpectedly funny outcome |
| CONTEMPLATIVE | Quiet moment; introspection or observation |

---

## INVALID ACTIONS [REQUIRED]

Refuse to resolve actions that:
1. Contradict already-established narrative facts (e.g. killing an NPC who is confirmed dead)
2. Are physically impossible in this setting (e.g. using a lightsaber in a world where they don't exist)
3. Violate fundamental world rules (e.g. using {STAT_6} power in a setting where it doesn't apply)
4. Break the fiction contract (e.g. "I reload my save file")

For invalid actions, return: `{ "valid": false, "reason": "..." }` and prompt the player
to reframe their action.

---

## SPECIAL MECHANICS [OPTIONAL — FILL IN OR REMOVE]

### {SPECIAL_MECHANIC_NAME} (e.g. One Ring Corruption, Force Temptation, Winter Severity)

{DESCRIBE THE SPECIAL MECHANIC: when it triggers, what it costs, how it's tracked, what
extreme values mean narratively. Include delta values for the corruption/temptation track.}

**Trigger:** {WHEN THIS MECHANIC ACTIVATES}
**Track:** 0 (unaffected) to 10 (fully {CORRUPTED/LOST/CONSUMED})
**Effects at threshold:**
- 3+: {EARLY SIGNS}
- 6+: {MID-STAGE EFFECTS}
- 9+: {SEVERE CONSEQUENCES}

---

## OUTPUT CONTRACT [REQUIRED]

Every resolution must return a JSON object with these fields. Do not omit any field.

```json
{
  "action_type": "SOCIAL",
  "stat_used": "{STAT_NAME}",
  "difficulty": "Moderate",
  "dice_result": "Success+Threat",
  "success": true,
  "narrative_facts": [
    "The guard lets the player pass but radios ahead to alert the checkpoint.",
    "The player is now known to the garrison as a suspicious traveler."
  ],
  "tone_tag": "TENSION",
  "alignment_delta": {
    "{moral_axis_1}": 0,
    "{moral_axis_2}": 1
  },
  "faction_delta": {
    "{faction_id}": -5
  },
  "companion_affinity_delta": {
    "{companion_id}": 3
  },
  "stress_delta": 1,
  "hp_delta": 0,
  "time_cost_minutes": 5,
  "world_reaction_needed": true,
  "events": [
    "A crackle on the guard's comm unit — the checkpoint ahead has been warned."
  ],
  "valid": true,
  "reason": ""
}
```

**Field notes:**
- `alignment_delta`: Use the exact axis keys defined in ALIGNMENT AND MORAL IMPACT
- `faction_delta`: Only include factions actually affected
- `companion_affinity_delta`: Only include companions present in the scene
- `events`: Empty array `[]` if no events were generated
- `valid: false` + `reason` when the action cannot be resolved (see INVALID ACTIONS)
