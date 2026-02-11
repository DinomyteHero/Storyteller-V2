-- Episodic memory table for long-term recall across turns.
-- Stores compressed turn summaries with keyword-based retrieval.
CREATE TABLE IF NOT EXISTS episodic_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    location_id TEXT,
    npcs_present_json TEXT NOT NULL DEFAULT '[]',
    key_events_json TEXT NOT NULL DEFAULT '[]',
    stress_level INTEGER DEFAULT 0,
    arc_stage TEXT,
    hero_beat TEXT,
    keywords TEXT NOT NULL DEFAULT '',
    is_pivotal INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_episodic_campaign ON episodic_memories(campaign_id);
CREATE INDEX IF NOT EXISTS idx_episodic_pivotal ON episodic_memories(campaign_id, is_pivotal);
