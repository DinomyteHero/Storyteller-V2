-- V7.0: Saga hierarchy for linked campaigns.
CREATE TABLE IF NOT EXISTS sagas (
    id TEXT PRIMARY KEY,
    player_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

ALTER TABLE campaigns ADD COLUMN saga_id TEXT REFERENCES sagas(id);
ALTER TABLE campaigns ADD COLUMN saga_chapter INTEGER DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_sagas_player
    ON sagas(player_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_campaigns_saga
    ON campaigns(saga_id, saga_chapter);
