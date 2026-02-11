-- Migration 0017: Add player starships table
-- Supports player-owned starships with customization and upgrades

CREATE TABLE IF NOT EXISTS player_starships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    ship_type TEXT NOT NULL,  -- References starship ID from starships.yaml (e.g., "ship-reb-yt1300")
    custom_name TEXT,  -- Player's custom ship name (optional)
    upgrades_json TEXT NOT NULL DEFAULT '{}',  -- JSON object with installed upgrades
    acquired_at TEXT NOT NULL DEFAULT (datetime('now')),
    acquired_method TEXT NOT NULL,  -- "background", "purchase", "quest", "salvage", "faction_reward"
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);

-- Index for fast lookup by campaign
CREATE INDEX IF NOT EXISTS idx_player_starships_campaign ON player_starships(campaign_id);

-- Index for starship type lookup
CREATE INDEX IF NOT EXISTS idx_player_starships_type ON player_starships(ship_type);
