CREATE TABLE IF NOT EXISTS truth_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL,
  turn_number INTEGER NOT NULL,
  fact_key TEXT NOT NULL,
  fact_value_json TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_truth_ledger_campaign_turn
  ON truth_ledger(campaign_id, turn_number);
