-- Add turn_events.created_at timestamp (legacy table uses `timestamp`; code writes `created_at`)
-- Idempotent: duplicate column ignored by migrate.py
ALTER TABLE turn_events ADD COLUMN created_at TEXT DEFAULT (datetime('now'));
