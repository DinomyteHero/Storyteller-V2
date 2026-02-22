-- Decision Ledger: first-class tracking of player decisions, rejected alternatives,
-- and promised consequences. Enables semantic choice memory across the campaign.
CREATE TABLE IF NOT EXISTS decision_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL,
  turn_number INTEGER NOT NULL,
  chosen_text TEXT NOT NULL,
  chosen_tone TEXT NOT NULL,
  rejected_options_json TEXT NOT NULL DEFAULT '[]',
  consequence_hint TEXT,
  impact_tier TEXT NOT NULL DEFAULT 'ripple',
  context_summary TEXT,
  outcome_delivered INTEGER NOT NULL DEFAULT 0,
  outcome_turn INTEGER,
  tags_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);
CREATE INDEX IF NOT EXISTS idx_decision_ledger_campaign ON decision_ledger(campaign_id, turn_number);
CREATE INDEX IF NOT EXISTS idx_decision_ledger_undelivered ON decision_ledger(campaign_id, outcome_delivered)
  WHERE outcome_delivered = 0;
