-- Living World (V2.5): world_time_minutes, psych_profile, is_public_rumor
-- Idempotent: migrate.py ignores duplicate column errors

ALTER TABLE campaigns ADD COLUMN world_time_minutes INTEGER DEFAULT 0;

ALTER TABLE characters ADD COLUMN psych_profile TEXT DEFAULT '{}';

ALTER TABLE turn_events ADD COLUMN is_public_rumor INTEGER DEFAULT 0;
