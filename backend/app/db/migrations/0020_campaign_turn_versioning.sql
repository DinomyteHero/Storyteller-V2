-- Add optimistic concurrency fields for campaign turn commits.
-- next_turn_number tracks the next unallocated turn index per campaign.
-- version increments on each successful turn allocation/commit CAS update.

ALTER TABLE campaigns ADD COLUMN next_turn_number INTEGER;
ALTER TABLE campaigns ADD COLUMN version INTEGER NOT NULL DEFAULT 0;

-- Backfill for existing rows based on event history. This is safe to run multiple
-- times because migrate.py records each migration once.
UPDATE campaigns
SET next_turn_number = (
  SELECT COALESCE(MAX(turn_number), 0) + 1
  FROM turn_events te
  WHERE te.campaign_id = campaigns.id
)
WHERE next_turn_number IS NULL;
