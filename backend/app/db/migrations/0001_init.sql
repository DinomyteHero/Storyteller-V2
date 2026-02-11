-- LLD schema: campaigns, characters, inventory, turn_events
-- Idempotent: IF NOT EXISTS

CREATE TABLE IF NOT EXISTS campaigns (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  time_period TEXT,
  world_state_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS characters (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  location_id TEXT,
  stats_json TEXT NOT NULL DEFAULT '{}',
  hp_current INTEGER NOT NULL DEFAULT 0,
  relationship_score INTEGER,
  secret_agenda TEXT,
  credits INTEGER DEFAULT 0,
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE TABLE IF NOT EXISTS inventory (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  item_name TEXT NOT NULL,
  quantity INTEGER NOT NULL DEFAULT 1,
  attributes_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY (owner_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS turn_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL,
  turn_number INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  is_hidden INTEGER NOT NULL DEFAULT 0,
  timestamp TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE INDEX IF NOT EXISTS idx_turn_events_campaign_turn ON turn_events(campaign_id, turn_number);
CREATE INDEX IF NOT EXISTS idx_characters_campaign_location ON characters(campaign_id, location_id);
CREATE INDEX IF NOT EXISTS idx_inventory_owner ON inventory(owner_id);
