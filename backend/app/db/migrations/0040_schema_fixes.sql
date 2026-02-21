-- Migration 0040: Schema fixes for v1.0 release

-- Fix player_starships.campaign_id type (INTEGER -> TEXT to match UUID campaign IDs)
CREATE TABLE IF NOT EXISTS player_starships_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    ship_type TEXT NOT NULL,
    custom_name TEXT,
    upgrades_json TEXT NOT NULL DEFAULT '{}',
    acquired_at TEXT NOT NULL DEFAULT (datetime('now')),
    acquired_method TEXT NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);
INSERT INTO player_starships_new SELECT * FROM player_starships;
DROP TABLE player_starships;
ALTER TABLE player_starships_new RENAME TO player_starships;

-- Re-create indexes for player_starships
CREATE INDEX IF NOT EXISTS idx_starships_campaign ON player_starships(campaign_id);
CREATE INDEX IF NOT EXISTS idx_player_starships_type ON player_starships(ship_type);

-- Missing index on truth_events(campaign_id)
CREATE INDEX IF NOT EXISTS idx_truth_events_campaign ON truth_events(campaign_id);

-- Missing indexes on other campaign-scoped tables
CREATE INDEX IF NOT EXISTS idx_episodic_memories_campaign ON episodic_memories(campaign_id);
CREATE INDEX IF NOT EXISTS idx_suggestion_cache_campaign ON suggestion_cache(campaign_id);
CREATE INDEX IF NOT EXISTS idx_objectives_campaign ON objectives(campaign_id);
CREATE INDEX IF NOT EXISTS idx_turn_idempotency_campaign ON turn_idempotency(campaign_id);
