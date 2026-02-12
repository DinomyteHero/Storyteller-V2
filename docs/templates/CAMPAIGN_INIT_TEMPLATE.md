# Campaign Initialization Template

This document provides templates and examples for creating new campaigns in Storyteller AI V2.20+.

## Campaign Creation Flow

### 1. Automated Setup (Recommended)

**Endpoint:** `POST /v2/setup/auto`

The automated setup flow uses CampaignArchitect and BiographerAgent to generate a complete campaign.

#### Request Schema

```json
{
  "time_period": "rebellion",
  "genre": "espionage_thriller",
  "themes": ["trust", "sacrifice", "duty"],
  "player_concept": "Rogue One-style operative -- infiltration expert, haunted by past failure, seeks redemption",
  "starting_location": "loc-cantina",
  "randomize_starting_location": false,
  "background_id": "spy_defector",
  "background_answers": {
    "motivation": "redemption",
    "origin": "imperial_academy",
    "inciting_incident": "betrayed_by_handler",
    "edge": "deception_mastery"
  },
  "player_gender": "female",
  "player_profile_id": null,
  "campaign_mode": "historical"
}
```text

#### Response Schema

```json
{
  "campaign_id": "uuid",
  "player_id": "uuid",
  "skeleton": {
    "title": "Campaign Title",
    "time_period": "rebellion",
    "locations": ["loc-cantina", "loc-marketplace", ...],
    "npc_cast": [
      {
        "name": "Draven Koss",
        "role": "Villain",
        "secret_agenda": "Seeks to dominate the sector through ruthless control."
      },
      ...
    ],
    "active_factions": [
      {
        "name": "Rebel Alliance",
        "location": "loc-cantina",
        "current_goal": "Recruit operatives",
        "resources": 5,
        "is_hostile": false
      },
      ...
    ]
  },
  "character_sheet": {
    "name": "Player Name",
    "background": "Character background narrative",
    "starting_location": "loc-cantina",
    "starting_planet": "Tatooine",
    "stats": {
      "strength": 8,
      "dexterity": 12,
      "intelligence": 10
    },
    "hp_current": 10
  }
}
```text

### 2. Manual Setup (Advanced)

**Endpoint:** `POST /v2/campaigns`

For direct campaign creation without LLM assistance.

#### Request Schema

```json
{
  "title": "New Campaign",
  "time_period": "rebellion",
  "genre": "espionage_thriller",
  "player_name": "Player",
  "starting_location": "loc-cantina",
  "player_stats": {
    "strength": 10,
    "dexterity": 10,
    "intelligence": 10
  },
  "hp_current": 10
}
```text

---

## Campaign world_state_json Structure

The `world_state_json` field stores all campaign-specific metadata. Here's the complete structure with V2.20+ fields:

```json
{
  // Faction System
  "active_factions": [
    {
      "name": "Rebel Alliance",
      "location": "loc-cantina",
      "current_goal": "Recruit operatives for Scarif mission",
      "resources": 5,
      "is_hostile": false
    }
  ],
  "faction_reputation": {
    "Rebel Alliance": 25,
    "Galactic Empire": -50,
    "Hutt Cartel": 0
  },

  // Companion System
  "party": ["comp-k2so", "comp-cassian"],
  "party_affinity": {
    "comp-k2so": 40,
    "comp-cassian": 60
  },
  "loyalty_progress": {
    "comp-k2so": 2,
    "comp-cassian": 5
  },
  "banter_queue": [],
  "party_state": {
    "companion_states": {
      "comp-k2so": {
        "influence": 30,
        "trust": 50,
        "respect": 40,
        "fear": 10
      }
    }
  },

  // Alignment & Morality
  "alignment": {
    "light_dark": 15,
    "paragon_renegade": 20
  },

  // Arc & Narrative State
  "arc_state": {
    "current_stage": "SETUP",
    "act": 1,
    "tension_level": 3
  },
  "arc_seed": {
    "source": "llm_setup_seed",
    "active_themes": ["trust", "sacrifice", "duty"],
    "opening_threads": [
      "Rebel intelligence points to an Imperial facility on Scarif",
      "Your handler disappeared after the last mission",
      "The Empire knows someone inside Rebel Intelligence is feeding them intel"
    ],
    "climax_question": "Will you sacrifice your cover to save your team?",
    "arc_intent": "Three-act espionage thriller with trust erosion"
  },

  // Opening Beats (V2.13+)
  "opening_beats": [
    {
      "turn": 2,
      "beat": "ARRIVAL_AND_ENCOUNTER",
      "goal": "Orient player in cantina, establish first NPC contact",
      "hook": "Informant signals urgently from corner booth",
      "npcs_visible": ["Whisper"]
    },
    {
      "turn": 3,
      "beat": "INCITING_INCIDENT",
      "goal": "Campaign's central tension becomes clear",
      "hook": "Imperial raid on cantina — spy must choose: fight or flee",
      "npcs_visible": ["Draven Koss", "Whisper", "TK-4471"]
    }
  ],

  // Act Outline (V2.12+)
  "act_outline": {
    "act_1_setup": "Player discovers signs of Draven Koss's operation. Whisper may hold key information.",
    "act_2_rising": "Escalating conflict with Draven Koss. Vekk Tano complicates matters.",
    "act_3_climax": "Final confrontation. Relationships and decisions determine outcome.",
    "key_npcs": {
      "villain": "Draven Koss",
      "rival": "Vekk Tano",
      "informant": "Whisper"
    }
  },

  // Scene Management
  "scene_id": "scene-abc123",
  "beats_remaining": 4,
  "force_scene_transition": false,
  "mode": "SIM",

  // Passage System (V2.19+)
  "passage_pack_id": null,
  "current_passage_id": null,

  // Genre & Style
  "genre": "espionage_thriller",
  "background_id": "spy_defector",

  // Quest System (V3.0)
  "quest_log": {
    "active": [
      {
        "id": "quest-scarif-intel",
        "title": "Scarif Intelligence",
        "description": "Retrieve Imperial facility schematics",
        "stage": "stage-1",
        "progress": 1,
        "target": 3
      }
    ],
    "completed": [],
    "failed": []
  },

  // V3.0: Generated Campaign World
  "generated_locations": [
    {
      "id": "gen-loc-hidden-cantina",
      "name": "The Hidden Cantina",
      "description": "A dimly lit underworld bar where information flows",
      "tags": ["cantina", "underworld"],
      "threat_level": "low",
      "planet": "Tatooine",
      "scene_types": ["dialogue"],
      "services": ["cantina"],
      "travel_links": [{"to_location_id": "loc-cantina"}],
      "origin": "generated"
    }
  ],
  "generated_npcs": [
    {
      "id": "gen-npc-vex",
      "name": "Vex",
      "role": "Informant",
      "faction_id": null,
      "default_location_id": "gen-loc-hidden-cantina",
      "traits": ["paranoid", "well-connected"],
      "motivation": "Survival through information brokering",
      "secret": "Former Imperial Intelligence analyst",
      "species": "Bothan",
      "voice": {
        "belief": "Everyone has a price",
        "wound": "Watched family executed for treason",
        "rhetorical_style": "Speaks in clipped, nervous sentences"
      }
    }
  ],
  "generated_quests": [
    {
      "id": "gen-quest-deadletter",
      "title": "Dead Letter Drop",
      "description": "Retrieve classified data from compromised drop point",
      "entry_location": "gen-loc-hidden-cantina",
      "key_npc": "gen-npc-vex",
      "stages": [
        {"id": "stage-1", "description": "Meet Vex at the Hidden Cantina"},
        {"id": "stage-2", "description": "Retrieve data from Imperial comm tower"},
        {"id": "stage-3", "description": "Decode encrypted transmission"}
      ]
    }
  ],
  "world_generation": {
    "seed": 12345678,
    "llm_assisted": true,
    "fallback_used": false
  },
  "campaign_mode": "historical",

  // Campaign Blueprint (V3.0, optional)
  "campaign_blueprint": {
    "conflict_web": {
      "primary": "Rebel Alliance vs. Galactic Empire",
      "secondary": ["Player vs. Imperial handler", "Rebels vs. Internal leak"]
    },
    "relationship_graph": {
      "player": {
        "draven_koss": "hunted",
        "whisper": "tentative_trust",
        "cassian": "partnership"
      }
    },
    "thematic_throughline": "Trust must be earned in a galaxy of lies"
  },

  // News Feed (Mass Effect-style comms)
  "news_feed": [
    {
      "id": "news-001",
      "headline": "Imperial garrison reinforcements arrive on Scarif",
      "body": "Intelligence reports increased Star Destroyer presence...",
      "source_tag": "rebel_intelligence",
      "urgency": "high",
      "related_factions": ["Galactic Empire", "Rebel Alliance"]
    }
  ],

  // Flags & Custom State
  "flags": {
    "campaign_started": true,
    "met_informant": false,
    "imperial_alert_level": 2
  },

  // Major Decisions (for legacy tracking)
  "major_decisions": [
    {
      "turn": 5,
      "choice": "Sacrificed cover to save Cassian",
      "impact": "Empire now hunting player actively"
    }
  ]
}
```text

---

## Database Schema Quick Reference

### Core Tables (from 0001_init.sql)

```sql
CREATE TABLE campaigns (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  time_period TEXT,
  world_state_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE characters (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  location_id TEXT,
  stats_json TEXT NOT NULL DEFAULT '{}',
  hp_current INTEGER NOT NULL DEFAULT 0,
  relationship_score INTEGER,
  secret_agenda TEXT,
  credits INTEGER DEFAULT 0,
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE TABLE turn_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL,
  turn_number INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  is_hidden INTEGER NOT NULL DEFAULT 0,
  timestamp TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);
```text

### Extended Tables (from migrations 0002-0021)

- `rendered_turns` - Turn narration cache
- `objectives` - Quest/objective tracking
- `episodic_memories` - Long-term memory with embeddings
- `knowledge_graph_*` - Entity/relation tracking
- `suggestion_cache` - Pregenerated suggestions
- `starships` - Player ship ownership
- `player_profiles` - Cross-campaign profiles
- `campaign_legacy` - Completed campaign data

See `/backend/app/db/migrations/` for full schema evolution.

---

## Campaign Modes (V3.0)

### Historical Mode (Default)

```json
{
  "campaign_mode": "historical"
}
```text
- Canon events are immutable
- Player operates in the margins of galactic history
- NPCs and quests fit within established lore
- Player can fail missions and face real consequences
- Galactic-scale events proceed as canon

### Sandbox Mode

```json
{
  "campaign_mode": "sandbox"
}
```text
- Player choices can reshape galactic history
- Canon events are starting conditions, not certainties
- Factions can be altered by player actions
- Generated content includes leverage points for player agency
- "What if" alternate history scenarios enabled

---

## Examples

### Example 1: Rogue One-Style Espionage Campaign

```json
{
  "time_period": "rebellion",
  "genre": "espionage_thriller",
  "themes": ["sacrifice", "trust", "hope"],
  "player_concept": "Rebel spy infiltrating Imperial intelligence -- former stormtrooper, guilt-ridden, seeks redemption",
  "background_id": "imperial_defector",
  "campaign_mode": "historical"
}
```text

### Example 2: Sandbox Political Intrigue

```json
{
  "time_period": "rebellion",
  "genre": "political_thriller",
  "themes": ["power", "betrayal", "legacy"],
  "player_concept": "Senator's aide navigating alliance politics -- idealist, connected, must choose sides",
  "background_id": "political_operative",
  "campaign_mode": "sandbox"
}
```text

### Example 3: KOTOR-Style Classic Hero's Journey

```json
{
  "time_period": "rebellion",
  "genre": "hero_journey",
  "themes": ["identity", "redemption", "destiny"],
  "player_concept": "Force-sensitive scavenger discovering hidden heritage -- orphan, untrained, hunted by Inquisitors",
  "background_id": "force_awakening",
  "campaign_mode": "historical"
}
```text

---

## Testing a New Campaign

```bash
# 1. Create campaign via API

curl -X POST http://localhost:8000/v2/setup/auto \
  -H "Content-Type: application/json" \
  -d '{

    "time_period": "rebellion",
    "genre": "espionage_thriller",
    "themes": ["trust"],
    "player_concept": "Rebel spy",
    "campaign_mode": "historical"
  }'

# 2. Get campaign state

curl "http://localhost:8000/v2/campaigns/{campaign_id}/state?player_id={player_id}"

# 3. Run first turn

curl -X POST "http://localhost:8000/v2/campaigns/{campaign_id}/turn?player_id={player_id}" \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Look around the cantina", "debug": true}'
```text

---

## See Also

- `/docs/architecture.md` - Full system architecture
- `/docs/era_pack_template.md` - Era pack structure
- `/backend/app/api/v2_campaigns.py` - Campaign API implementation
- `/backend/app/core/campaign_init.py` - Campaign world generation
- `API_REFERENCE.md` - Full API contract
