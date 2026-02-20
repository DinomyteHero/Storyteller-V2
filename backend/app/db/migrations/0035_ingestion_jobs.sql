-- Library: ingestion job tracking for uploaded documents.
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id           TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending | running | complete | failed
    setting_id   TEXT NOT NULL DEFAULT '',
    period_id    TEXT NOT NULL DEFAULT '',
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
