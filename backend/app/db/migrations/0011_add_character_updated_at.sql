-- Add characters.updated_at timestamp (idempotent: duplicate column ignored by migrate.py)
ALTER TABLE characters ADD COLUMN updated_at TEXT DEFAULT (datetime('now'));
