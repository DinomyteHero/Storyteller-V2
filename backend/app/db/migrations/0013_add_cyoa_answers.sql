-- Migration: Add CYOA answers storage to characters table
-- Purpose: Store Choose-Your-Own-Adventure character creation answers separately
-- Author: Claude
-- Date: 2026-02-07

-- Add column to store CYOA answers as JSON
-- Format: {"motivation": "...", "origin": "...", "inciting_incident": "...", "edge": "..."}
ALTER TABLE characters ADD COLUMN cyoa_answers_json TEXT;
