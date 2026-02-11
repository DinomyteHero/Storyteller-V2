-- Reference schema (LLD). Actual schema applied via migrations/0001_init.sql, 0002_*, 0003_*, 0004_*.

-- campaigns(id, title, time_period, world_state_json, world_time_minutes)
-- world_state_json defaults to '{}'; world_time_minutes INTEGER DEFAULT 0

-- characters(id, campaign_id, name, role, location_id, stats_json, hp_current, relationship_score, secret_agenda, credits, psych_profile)
-- credits INTEGER DEFAULT 0; psych_profile TEXT (JSON) DEFAULT '{}'

-- inventory(id, owner_id, item_name, quantity, attributes_json)

-- turn_events(id, campaign_id, turn_number, event_type, payload_json, is_hidden, is_public_rumor, timestamp)
-- is_public_rumor INTEGER DEFAULT 0

-- rendered_turns(id, campaign_id, turn_number, text, citations_json, suggested_actions_json, created_at)
