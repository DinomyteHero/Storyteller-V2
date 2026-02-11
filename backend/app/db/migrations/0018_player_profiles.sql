-- V2.10: Player profiles and cross-campaign legacy system
-- Player profiles persist across campaigns for legacy tracking.

-- Player profiles table: persistent identity across campaigns
CREATE TABLE IF NOT EXISTS player_profiles (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Campaign legacy: outcomes of completed campaigns for cross-campaign influence
CREATE TABLE IF NOT EXISTS campaign_legacy (
    id TEXT PRIMARY KEY,
    player_profile_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    era TEXT,
    background_id TEXT,
    genre TEXT,
    outcome_summary TEXT DEFAULT '',
    faction_standings_json TEXT NOT NULL DEFAULT '{}',
    major_decisions_json TEXT NOT NULL DEFAULT '[]',
    character_fate TEXT DEFAULT '',
    arc_stage_reached TEXT DEFAULT 'SETUP',
    completed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (player_profile_id) REFERENCES player_profiles(id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

-- Link campaigns to player profiles
ALTER TABLE campaigns ADD COLUMN player_profile_id TEXT DEFAULT NULL;

-- Indexes for efficient legacy queries
CREATE INDEX IF NOT EXISTS idx_campaign_legacy_player ON campaign_legacy(player_profile_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_profile ON campaigns(player_profile_id);
