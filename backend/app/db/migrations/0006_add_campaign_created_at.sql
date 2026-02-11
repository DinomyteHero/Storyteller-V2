-- Add campaigns.created_at timestamp (idempotent: duplicate column ignored by migrate.py)
ALTER TABLE campaigns ADD COLUMN created_at TEXT DEFAULT (datetime('now'));
