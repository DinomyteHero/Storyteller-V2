-- Knowledge Graph tables (V2.5+)
-- Entities: characters, locations, factions, ships, artifacts, events
-- Triples: subject-predicate-object relationships between entities
-- Summaries: book-level, chapter-level, character-arc, location dossiers
-- Checkpoints: extraction resume support

CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    era TEXT NOT NULL DEFAULT 'rebellion',
    properties_json TEXT NOT NULL DEFAULT '{}',
    source_books_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kg_entities_type ON kg_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_kg_entities_era ON kg_entities(era);
CREATE INDEX IF NOT EXISTS idx_kg_entities_name ON kg_entities(canonical_name);

CREATE TABLE IF NOT EXISTS kg_triples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_id TEXT NOT NULL,
    era TEXT NOT NULL DEFAULT 'rebellion',
    source_book TEXT,
    source_chunk_id TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    weight REAL NOT NULL DEFAULT 1.0,
    properties_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (subject_id) REFERENCES kg_entities(id),
    FOREIGN KEY (object_id) REFERENCES kg_entities(id)
);

CREATE INDEX IF NOT EXISTS idx_kg_triples_subject ON kg_triples(subject_id);
CREATE INDEX IF NOT EXISTS idx_kg_triples_object ON kg_triples(object_id);
CREATE INDEX IF NOT EXISTS idx_kg_triples_predicate ON kg_triples(predicate);
CREATE INDEX IF NOT EXISTS idx_kg_triples_era ON kg_triples(era);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kg_triples_unique
    ON kg_triples(subject_id, predicate, object_id);

CREATE TABLE IF NOT EXISTS kg_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_type TEXT NOT NULL,
    entity_id TEXT,
    book_title TEXT,
    chapter_title TEXT,
    chapter_index INTEGER,
    era TEXT NOT NULL DEFAULT 'rebellion',
    summary_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kg_summaries_type ON kg_summaries(summary_type);
CREATE INDEX IF NOT EXISTS idx_kg_summaries_entity ON kg_summaries(entity_id);
CREATE INDEX IF NOT EXISTS idx_kg_summaries_book ON kg_summaries(book_title);
CREATE INDEX IF NOT EXISTS idx_kg_summaries_era ON kg_summaries(era);

CREATE TABLE IF NOT EXISTS kg_extraction_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_title TEXT NOT NULL,
    chapter_title TEXT,
    chunk_id TEXT,
    phase TEXT NOT NULL DEFAULT 'extraction',
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(book_title, chapter_title, phase)
);
