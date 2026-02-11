-- Add embedding vector column to episodic_memories for vector similarity recall.
-- Stored as JSON-serialized float array (384-dim). NULL if embeddings unavailable.
ALTER TABLE episodic_memories ADD COLUMN embedding_json TEXT;
-- Add narrative_summary for richer context without full narrative text.
ALTER TABLE episodic_memories ADD COLUMN narrative_summary TEXT NOT NULL DEFAULT '';
