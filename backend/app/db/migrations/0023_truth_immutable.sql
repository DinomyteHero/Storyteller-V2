-- V7.0: Immutable truth facts for historical canon enforcement.
ALTER TABLE truth_facts ADD COLUMN is_immutable INTEGER NOT NULL DEFAULT 0;
