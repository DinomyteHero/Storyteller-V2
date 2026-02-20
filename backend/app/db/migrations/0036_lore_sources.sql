-- V11.0: Lore sources — tracks user-uploaded reference material with source-level metadata.
-- Allows grouping ingestion jobs by source and supports source-level deletion from LanceDB.

CREATE TABLE IF NOT EXISTS lore_sources (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    setting_id  TEXT NOT NULL DEFAULT '',
    period_id   TEXT NOT NULL DEFAULT '',
    file_count  INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'active',   -- active | deleting | deleted
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- Link ingestion_jobs to a source (nullable for backward compat with pre-V11 jobs)
ALTER TABLE ingestion_jobs ADD COLUMN source_id TEXT REFERENCES lore_sources(id);
