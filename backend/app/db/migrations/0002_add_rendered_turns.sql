-- Rendered transcript cache: one row per turn
-- Idempotent: IF NOT EXISTS

CREATE TABLE IF NOT EXISTS rendered_turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL,
  turn_number INTEGER NOT NULL,
  text TEXT NOT NULL,
  citations_json TEXT NOT NULL DEFAULT '[]',
  suggested_actions_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE INDEX IF NOT EXISTS idx_rendered_turns_campaign_turn ON rendered_turns(campaign_id, turn_number);
