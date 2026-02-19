-- 0033_quest_entries_table.sql
-- Normalized quest entries table — extracted from world_state_json["quest_log"].
-- Indexed by campaign_id + quest_id for fast lookups without JSON parsing.

CREATE TABLE IF NOT EXISTS quest_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id   TEXT    NOT NULL,
    quest_id      TEXT    NOT NULL,
    quest_title   TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL DEFAULT 'active',   -- active|completed|failed|abandoned
    quest_json    TEXT    NOT NULL DEFAULT '{}',        -- Full quest data as JSON
    created_turn  INTEGER NOT NULL DEFAULT 0,
    updated_turn  INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    UNIQUE (campaign_id, quest_id)
);

CREATE INDEX IF NOT EXISTS idx_quest_entries_campaign
    ON quest_entries(campaign_id, status);
