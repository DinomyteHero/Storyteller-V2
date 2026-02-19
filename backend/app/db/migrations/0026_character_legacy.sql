-- V7.0: Structured character legacy snapshots used for saga continuity.
CREATE TABLE IF NOT EXISTS character_legacies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    saga_id TEXT,
    legacy_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE INDEX IF NOT EXISTS idx_character_legacies_player
    ON character_legacies(player_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_character_legacies_campaign
    ON character_legacies(campaign_id);
