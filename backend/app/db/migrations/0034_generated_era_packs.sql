-- 0034_generated_era_packs.sql
-- EraForge: stores LLM-generated era packs for reuse across campaigns.
-- Each row represents a complete era pack equivalent to a static YAML pack.
-- The era_pack_json column contains the full EraPack-compatible structure
-- (backgrounds, species, setting_rules, timeline, canon_characters, metadata).

CREATE TABLE IF NOT EXISTS generated_era_packs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_id      TEXT    NOT NULL,              -- normalized key, e.g. "game_of_thrones"
    period_id       TEXT    NOT NULL,              -- normalized key, e.g. "war_of_five_kings"
    display_name    TEXT    NOT NULL DEFAULT '',    -- human-readable, e.g. "War of the Five Kings"
    summary         TEXT    NOT NULL DEFAULT '',    -- 2-3 sentence era summary
    era_pack_json   TEXT    NOT NULL DEFAULT '{}',  -- full EraPack-compatible JSON blob
    source_prompt   TEXT    NOT NULL DEFAULT '',    -- original user prompt, e.g. "Game of Thrones"
    version         INTEGER NOT NULL DEFAULT 1,     -- for variant support: same setting+period, different generation
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (setting_id, period_id, version)
);

CREATE INDEX IF NOT EXISTS idx_generated_era_packs_lookup
    ON generated_era_packs(setting_id, period_id);
