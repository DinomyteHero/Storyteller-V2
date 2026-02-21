-- 0037: Add index on truth_facts(campaign_id) for faster fact lookups
-- in long campaigns with 100+ turns.
CREATE INDEX IF NOT EXISTS idx_truth_facts_campaign ON truth_facts(campaign_id);
