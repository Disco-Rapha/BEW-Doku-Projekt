-- Migration 001: Initiales Schema
--
-- Anlegen der Basistabellen für das BEW Doku Projekt.
-- Metadaten-Felder (Titel, Autor, Summary, VGB-Zuordnungen) kommen
-- in späteren Migrationen, sobald Modul 1 und 2 konzipiert sind.

BEGIN;

-- Dokumente: Stammtabelle für jedes registrierte PDF
CREATE TABLE documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256          TEXT NOT NULL UNIQUE,       -- Content-Hash zur Deduplikation
    original_name   TEXT NOT NULL,
    relative_path   TEXT NOT NULL,              -- relativ zu data/raw/
    size_bytes      INTEGER NOT NULL,
    mime_type       TEXT,
    status          TEXT NOT NULL DEFAULT 'registered',
                        -- registered | parsed | enriched | failed
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_documents_status ON documents(status);

-- Verarbeitungs-Log: pro Azure-Call ein Eintrag
CREATE TABLE processing_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    step            TEXT NOT NULL,              -- 'azure_doc_intel', 'azure_openai_metadata', ...
    status          TEXT NOT NULL,              -- 'ok' | 'error'
    tokens_used     INTEGER,
    duration_ms     INTEGER,
    error_message   TEXT,
    payload_json    TEXT,                       -- Rohergebnis / Request zur Nachvollziehbarkeit
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_events_document ON processing_events(document_id);
CREATE INDEX idx_events_step_status ON processing_events(step, status);

-- Schema-Version wird in db.py verwaltet, hier nur der erste Eintrag

COMMIT;
