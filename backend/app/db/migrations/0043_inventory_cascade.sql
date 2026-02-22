-- Migration 0043: Add ON DELETE CASCADE to inventory FK + missing indexes

-- Recreate inventory with ON DELETE CASCADE on owner_id
CREATE TABLE IF NOT EXISTS inventory_new (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (owner_id) REFERENCES characters(id) ON DELETE CASCADE
);
INSERT OR IGNORE INTO inventory_new SELECT * FROM inventory;
DROP TABLE IF EXISTS inventory;
ALTER TABLE inventory_new RENAME TO inventory;

-- Re-create existing index
CREATE INDEX IF NOT EXISTS idx_inventory_owner ON inventory(owner_id);

-- Missing performance indexes
CREATE INDEX IF NOT EXISTS idx_turn_events_type ON turn_events(event_type);
CREATE INDEX IF NOT EXISTS idx_truth_facts_key ON truth_facts(fact_key);
CREATE INDEX IF NOT EXISTS idx_turn_idempotency_key ON turn_idempotency(idempotency_key);
