-- V7.0: Crystallized memories for long-running campaigns.
-- These are high-signal moments that remain retrievable regardless of compression.
CREATE TABLE IF NOT EXISTS crystallized_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    memory_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    full_text TEXT,
    npcs_involved TEXT DEFAULT '[]',
    location TEXT,
    emotional_tag TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE INDEX IF NOT EXISTS idx_crystallized_campaign
    ON crystallized_memories(campaign_id);

CREATE INDEX IF NOT EXISTS idx_crystallized_campaign_turn
    ON crystallized_memories(campaign_id, turn_number DESC);
