-- Add characters.created_at timestamp (idempotent: duplicate column ignored by migrate.py)
ALTER TABLE characters ADD COLUMN created_at TEXT DEFAULT (datetime('now'));
