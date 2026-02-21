-- V12.0: User-created LLM presets.
-- Each preset stores per-role provider+model configs as a JSON dict.
-- System presets (budget/balanced/quality) are defined in code, not this table.
CREATE TABLE IF NOT EXISTS user_presets (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    description   TEXT NOT NULL DEFAULT '',
    role_configs  TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
