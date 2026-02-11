-- V2.8: Director suggestion pre-generation cache
CREATE TABLE IF NOT EXISTS suggestion_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    arc_stage TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    output_json TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(campaign_id, location_id, arc_stage, turn_number)
);
