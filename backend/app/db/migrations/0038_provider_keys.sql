-- V12.0: Cloud-agnostic provider key storage.
-- API keys entered via the Settings UI are persisted here.
-- Keys are resolved at runtime: DB first, then env var fallback.
CREATE TABLE IF NOT EXISTS provider_keys (
    provider_id   TEXT PRIMARY KEY,
    api_key       TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
