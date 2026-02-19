-- Deferred maintenance agent patches: agents that run post-commit write
-- their world_state mutations here. Applied on next turn load.
CREATE TABLE IF NOT EXISTS pending_world_state_patches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    patch_json TEXT NOT NULL,
    applied INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE INDEX IF NOT EXISTS idx_pending_patches_campaign
    ON pending_world_state_patches(campaign_id, applied);
