-- Add planet_id column to characters table for lightweight planet tracking
ALTER TABLE characters ADD COLUMN planet_id TEXT;
