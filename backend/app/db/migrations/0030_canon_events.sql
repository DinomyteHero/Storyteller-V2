-- 0030_canon_events.sql
-- Tracks which canon events have been triggered in a campaign (Historical mode).
-- Static event definitions live in data/static/era_packs/{era_id}/canon_events.json.

CREATE TABLE IF NOT EXISTS canon_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id   TEXT    NOT NULL,
    era_id        TEXT    NOT NULL,
    event_id      TEXT    NOT NULL,          -- matches id in canon_events.json
    triggered_at_turn INTEGER NOT NULL,      -- turn number when triggered
    arc_stage     TEXT    NOT NULL,           -- SETUP|RISING|CLIMAX|RESOLUTION
    event_text    TEXT    NOT NULL,           -- narrative description injected into context
    is_immutable  INTEGER NOT NULL DEFAULT 1, -- always immutable for Historical mode
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    UNIQUE (campaign_id, event_id)            -- each event fires at most once per campaign
);

CREATE INDEX IF NOT EXISTS idx_canon_events_campaign
    ON canon_events(campaign_id, triggered_at_turn);
