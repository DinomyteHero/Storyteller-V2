-- Add campaigns.updated_at timestamp (idempotent: duplicate column ignored by migrate.py)
ALTER TABLE campaigns ADD COLUMN updated_at TEXT DEFAULT (datetime('now'));
