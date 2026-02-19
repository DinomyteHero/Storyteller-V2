-- 0031_turn_snapshots.sql
-- World state snapshots per turn for rewind/undo capability.
-- Stored after each successful commit so we can restore to any turn.

CREATE TABLE IF NOT EXISTS turn_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id    TEXT    NOT NULL,
    turn_number    INTEGER NOT NULL,
    world_state_json TEXT  NOT NULL,    -- Full world_state JSON at end of this turn
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    UNIQUE (campaign_id, turn_number)
);

CREATE INDEX IF NOT EXISTS idx_turn_snapshots_campaign
    ON turn_snapshots(campaign_id, turn_number);
