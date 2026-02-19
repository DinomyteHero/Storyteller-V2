-- 0032_npc_states_table.sql
-- Normalized NPC states table — extracted from world_state_json["npc_states"].
-- Indexed by campaign_id + npc_id for fast lookups without JSON parsing.

CREATE TABLE IF NOT EXISTS npc_states (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id   TEXT    NOT NULL,
    npc_id        TEXT    NOT NULL,
    npc_name      TEXT    NOT NULL DEFAULT '',
    state_json    TEXT    NOT NULL DEFAULT '{}',    -- Full NPC state as JSON
    last_seen_turn INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    UNIQUE (campaign_id, npc_id)
);

CREATE INDEX IF NOT EXISTS idx_npc_states_campaign
    ON npc_states(campaign_id, last_seen_turn DESC);
