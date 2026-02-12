# Database Seed Template

This document provides SQL templates for creating test campaigns and seeding the database for development/testing.

## Database Schema Evolution

Storyteller AI uses SQLite with an event sourcing architecture. The schema is managed through 21 migrations:

### Migration Sequence

| Migration | Purpose |
| ----------- | --------- |
| `0001_init.sql` | Core tables: campaigns, characters, inventory, turn_events |
| `0002_add_rendered_turns.sql` | Turn narration cache |
| `0003_add_credits.sql` | Character credits field |
| `0004_living_world.sql` | Living world tracking (objectives, etc.) |
| `0005_knowledge_graph.sql` | Entity/relation tables for KG |
| `0006_add_campaign_created_at.sql` | Campaign timestamp |
| `0007_add_campaign_updated_at.sql` | Campaign update tracking |
| `0008_add_planet.sql` | Character planet location |
| `0009_add_background.sql` | Character background narrative |
| `0010_add_character_created_at.sql` | Character creation timestamp |
| `0011_add_character_updated_at.sql` | Character update timestamp |
| `0012_add_turn_events_created_at.sql` | Event creation timestamp |
| `0013_add_cyoa_answers.sql` | CYOA background choices |
| `0014_episodic_memories.sql` | Long-term memory table |
| `0015_add_gender.sql` | Character gender for pronouns |
| `0016_suggestion_cache.sql` | Pregenerated suggestions |
| `0017_starships.sql` | Player ship ownership |
| `0018_player_profiles.sql` | Cross-campaign profiles + legacy tracking |
| `0019_turn_contract_passages.sql` | Passage mode support |
| `0020_campaign_turn_versioning.sql` | Turn versioning and world time |
| `0021_episodic_memory_embedding.sql` | Memory embeddings for retrieval |

---

## Minimal Test Campaign Seed

### 1. Create Test Campaign

```sql
-- Insert test campaign

INSERT INTO campaigns (
  id,
  title,
  time_period,
  world_state_json,
  created_at,
  updated_at
) VALUES (
  'test-campaign-001',
  'Test Campaign - Rebellion Era',
  'rebellion',
  json('{
    "active_factions": [
      {
        "name": "Rebel Alliance",
        "location": "loc-cantina",
        "current_goal": "Recruit operatives",
        "resources": 5,
        "is_hostile": false
      },
      {
        "name": "Galactic Empire",
        "location": "loc-imperial-garrison",
        "current_goal": "Maintain order",
        "resources": 10,
        "is_hostile": true
      }
    ],
    "party": [],
    "party_affinity": {},
    "loyalty_progress": {},
    "alignment": {"light_dark": 0, "paragon_renegade": 0},
    "faction_reputation": {"Rebel Alliance": 0, "Galactic Empire": 0},
    "arc_state": {"current_stage": "SETUP", "act": 1, "tension_level": 0},
    "genre": "espionage_thriller",
    "scene_id": "scene-initial",
    "beats_remaining": 4,
    "mode": "SIM",
    "flags": {"campaign_started": true}
  }'),
  datetime('now'),
  datetime('now')
);
```

### 2. Create Test Player Character

```sql
-- Insert test player

INSERT INTO characters (
  id,
  campaign_id,
  name,
  role,
  location_id,
  planet_id,
  stats_json,
  hp_current,
  relationship_score,
  secret_agenda,
  credits,
  background,
  gender,
  created_at,
  updated_at
) VALUES (
  'test-player-001',
  'test-campaign-001',
  'Test Hero',
  'Player',
  'loc-cantina',
  'Tatooine',
  json('{"strength": 10, "dexterity": 12, "intelligence": 10, "wisdom": 8, "charisma": 11}'),
  10,
  NULL,
  NULL,
  100,
  'A capable operative with ties to Rebel Intelligence.',
  'male',
  datetime('now'),
  datetime('now')
);
```

### 3. Create Test NPCs

```sql
-- Villain

INSERT INTO characters (
  id,
  campaign_id,
  name,
  role,
  location_id,
  stats_json,
  hp_current,
  relationship_score,
  secret_agenda,
  credits,
  created_at,
  updated_at
) VALUES (
  'npc-villain-001',
  'test-campaign-001',
  'Commander Vex',
  'Villain',
  'loc-imperial-garrison',
  '{}',
  15,
  -30,

  'Seeks to crush Rebel cells on Tatooine through intelligence gathering.',
  500,
  datetime('now'),
  datetime('now')
);

-- Informant

INSERT INTO characters (
  id,
  campaign_id,
  name,
  role,
  location_id,
  stats_json,
  hp_current,
  relationship_score,
  secret_agenda,
  credits,
  created_at,
  updated_at
) VALUES (
  'npc-informant-001',
  'test-campaign-001',
  'Whisper',
  'Informant',
  'loc-cantina',
  '{}',
  10,
  20,
  'Bothan spymaster who sells secrets to the highest bidder.',
  250,
  datetime('now'),
  datetime('now')
);

-- Merchant

INSERT INTO characters (
  id,
  campaign_id,
  name,
  role,
  location_id,
  stats_json,
  hp_current,
  relationship_score,
  secret_agenda,
  credits,
  created_at,
  updated_at
) VALUES (
  'npc-merchant-001',
  'test-campaign-001',
  'Nura Besh',
  'Merchant',
  'loc-marketplace',
  '{}',
  10,
  10,
  'Deals in black market goods through Twi''lek trade networks.',
  400,
  datetime('now'),
  datetime('now')
);
```

### 4. Seed Initial Events

```sql
-- Initial FLAG_SET event

INSERT INTO turn_events (
  campaign_id,
  turn_number,
  event_type,
  payload_json,
  is_hidden,
  created_at
) VALUES (
  'test-campaign-001',
  1,
  'FLAG_SET',
  json('{"key": "campaign_started", "value": true}'),
  0,
  datetime('now')
);

-- Story note (background seed)

INSERT INTO turn_events (
  campaign_id,
  turn_number,
  event_type,
  payload_json,
  is_hidden,
  created_at
) VALUES (
  'test-campaign-001',
  1,
  'STORY_NOTE',
  json('{"text": "Background: A capable operative with ties to Rebel Intelligence."}'),
  0,
  datetime('now')
);
```

### 5. Seed Initial Objective

```sql
INSERT INTO objectives (
  id,
  campaign_id,
  title,
  description,
  success_conditions_json,
  progress_json,
  status,
  created_at,
  updated_at
) VALUES (
  'obj-test-001',
  'test-campaign-001',
  'Establish your foothold',
  'Secure intelligence and identify the primary opposition.',
  json('{"type": "discover_opposition"}'),
  json('{"progress": 0, "target": 3}'),
  'active',
  datetime('now'),
  datetime('now')
);
```

---

## Full Campaign Seed (Rebellion Era)

```sql
-- Complete rebellion-era campaign with all features

INSERT INTO campaigns (
  id,
  title,
  time_period,
  world_state_json,
  created_at,
  updated_at
) VALUES (
  'full-rebellion-001',
  'Operation Stardust - Scarif Intelligence',
  'rebellion',
  json('{
    "active_factions": [
      {"name": "Rebel Alliance", "location": "loc-rebel-base", "current_goal": "Retrieve Death Star plans", "resources": 5, "is_hostile": false},
      {"name": "Galactic Empire", "location": "loc-imperial-citadel", "current_goal": "Secure the archive", "resources": 15, "is_hostile": true}
    ],
    "party": ["comp-cassian", "comp-k2so"],
    "party_affinity": {"comp-cassian": 50, "comp-k2so": 30},
    "loyalty_progress": {"comp-cassian": 3, "comp-k2so": 1},
    "alignment": {"light_dark": 10, "paragon_renegade": 5},
    "faction_reputation": {"Rebel Alliance": 40, "Galactic Empire": -60},
    "arc_state": {"current_stage": "RISING_ACTION", "act": 1, "tension_level": 4},
    "arc_seed": {
      "source": "llm_setup_seed",
      "active_themes": ["sacrifice", "hope", "trust"],
      "opening_threads": [
        "Rebel intelligence points to a massive Imperial project on Scarif",
        "Your handler has gone dark after infiltrating an Imperial facility",
        "A defecting scientist claims the Empire is building a planet-killer"
      ],
      "climax_question": "Will you sacrifice everything to bring hope to the galaxy?",
      "arc_intent": "Rogue One-style suicide mission with mounting stakes"
    },
    "opening_beats": [
      {"turn": 2, "beat": "ARRIVAL_AND_ENCOUNTER", "goal": "Establish mission urgency and first contact", "hook": "Cassian briefs you on the Scarif situation", "npcs_visible": ["Cassian Andor"]},
      {"turn": 3, "beat": "INCITING_INCIDENT", "goal": "The mission becomes personal", "hook": "Your handler''s last transmission reveals the Death Star''s existence", "npcs_visible": ["Cassian Andor", "K-2SO"]}
    ],
    "act_outline": {
      "act_1_setup": "Assemble team and infiltrate Scarif",
      "act_2_rising": "Navigate Imperial security while locating the archive",
      "act_3_climax": "Transmit plans before Imperial arrival",
      "key_npcs": {"villain": "Director Krennic", "rival": "Imperial Security Chief", "informant": "Defecting Scientist"}
    },
    "genre": "espionage_thriller",
    "scene_id": "scene-briefing-room",
    "beats_remaining": 4,
    "mode": "SIM",
    "quest_log": {
      "active": [
        {"id": "quest-scarif", "title": "Scarif Infiltration", "description": "Retrieve Death Star plans from Imperial archive", "stage": "stage-1", "progress": 0, "target": 5}
      ],
      "completed": [],
      "failed": []
    },
    "generated_locations": [
      {
        "id": "gen-loc-safe-house",
        "name": "Rebel Safe House",
        "description": "Hidden safehouse in the lower city",
        "tags": ["hideout", "safe"],
        "threat_level": "low",
        "planet": "Jedha",
        "scene_types": ["dialogue"],
        "services": [],
        "travel_links": [{"to_location_id": "loc-cantina"}]
      }
    ],
    "generated_npcs": [
      {
        "id": "gen-npc-bodhi",
        "name": "Bodhi Rook",
        "role": "Defector",
        "faction_id": null,
        "default_location_id": "gen-loc-safe-house",
        "traits": ["anxious", "determined"],
        "motivation": "Redemption for enabling Imperial atrocities",
        "secret": "Carries classified Imperial cargo manifest",
        "species": "Human",
        "voice": {"belief": "Everyone deserves a chance to make things right", "wound": "Participated in Death Star cargo operations", "rhetorical_style": "Nervous, over-explains"}
      }
    ],
    "campaign_mode": "historical",
    "news_feed": [
      {"id": "news-001", "headline": "Imperial garrison reinforcements arrive on Scarif", "body": "Star Destroyer presence increases around orbital gate", "source_tag": "rebel_intelligence", "urgency": "high", "related_factions": ["Galactic Empire", "Rebel Alliance"]}
    ],
    "flags": {"campaign_started": true, "knows_death_star_exists": true, "cassian_trust_level": 2}
  }'),
  datetime('now'),
  datetime('now')
);
```

---

## Testing Database Integrity

### 1. Verify Campaign Exists

```sql
SELECT id, title, time_period, created_at FROM campaigns WHERE id = 'test-campaign-001';
```

### 2. Verify Player Character

```sql
SELECT c.id, c.name, c.role, c.location_id, c.hp_current, c.credits
FROM characters c
WHERE c.campaign_id = 'test-campaign-001' AND c.role = 'Player';
```

### 3. Verify NPCs

```sql
SELECT c.id, c.name, c.role, c.location_id, c.relationship_score
FROM characters c
WHERE c.campaign_id = 'test-campaign-001' AND c.role != 'Player'
ORDER BY c.relationship_score DESC;
```

### 4. Verify Turn Events

```sql
SELECT turn_number, event_type, payload_json, created_at
FROM turn_events
WHERE campaign_id = 'test-campaign-001'
ORDER BY turn_number, id;
```

### 5. Verify Objectives

```sql
SELECT id, title, description, status, progress_json
FROM objectives
WHERE campaign_id = 'test-campaign-001' AND status = 'active';
```

---

## Cleanup Test Data

```sql
-- Delete test campaign and all related data

DELETE FROM turn_events WHERE campaign_id LIKE 'test-campaign-%';
DELETE FROM rendered_turns WHERE campaign_id LIKE 'test-campaign-%';
DELETE FROM objectives WHERE campaign_id LIKE 'test-campaign-%';
DELETE FROM episodic_memories WHERE campaign_id LIKE 'test-campaign-%';
DELETE FROM characters WHERE campaign_id LIKE 'test-campaign-%';
DELETE FROM campaigns WHERE id LIKE 'test-campaign-%';

-- Verify cleanup

SELECT COUNT(*) as remaining FROM campaigns WHERE id LIKE 'test-campaign-%';
```

---

## Schema Inspection Commands

### List All Tables

```sql
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
```

### Inspect Campaigns Table

```sql
PRAGMA table_info(campaigns);
```

### Check Indexes

```sql
SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index';
```

### View Foreign Keys

```sql
PRAGMA foreign_keys;
PRAGMA foreign_key_list(characters);
```

---

## See Also

- `/backend/app/db/schema.sql` - Reference schema
- `/backend/app/db/migrations/` - All 21 migration files
- `/docs/03_state_and_persistence.md` - Event sourcing architecture
- `/docs/templates/CAMPAIGN_INIT_TEMPLATE.md` - Campaign creation guide
