CREATE TABLE IF NOT EXISTS truth_facts (
  campaign_id TEXT NOT NULL,
  fact_key TEXT NOT NULL,
  fact_value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  source_turn_id TEXT,
  PRIMARY KEY (campaign_id, fact_key)
);

CREATE TABLE IF NOT EXISTS truth_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL,
  turn_id TEXT NOT NULL,
  event_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS objectives (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  success_conditions_json TEXT NOT NULL DEFAULT '{}',
  progress_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_objectives_campaign_status ON objectives(campaign_id, status);
