-- Add credits to characters for sidebar (idempotent: run in try/except; ignore duplicate column)
ALTER TABLE characters ADD COLUMN credits INTEGER DEFAULT 0;
