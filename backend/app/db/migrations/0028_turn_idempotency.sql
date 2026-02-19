-- Turn idempotency ledger for /turn and /turn_stream replay safety.
CREATE TABLE IF NOT EXISTS turn_idempotency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing', -- processing | completed
    response_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(campaign_id, player_id, endpoint, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_turn_idempotency_campaign
    ON turn_idempotency(campaign_id, player_id, endpoint);
