-- Migration 003: SharePoint Metadata Snapshot + Delta Sync
--
-- Änderungen:
--   1. documents: sha256 nullable, neue SP-Metadaten-Spalten, selected_for_indexing
--      (SQLite erfordert Tabellen-Neuerstellung für NOT NULL → nullable)
--   2. Neue Tabelle document_sp_fields (beliebige SP-Bibliotheksspalten)
--   3. sources: sp_delta_link für inkrementelle Delta-Syncs
--
-- Neue Status-Werte in documents.status:
--   discovered | downloading | downloaded | indexing | indexed
--   needs_reindex | deleted | failed
--   (alte Werte registered|parsed|enriched bleiben für Rückwärtskompatibilität)

BEGIN;

-- ----------------------------------------------------------------
-- 1. documents neu aufbauen (sha256 nullable + neue Spalten)
-- ----------------------------------------------------------------
CREATE TABLE documents_new (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256          TEXT,                       -- NULL bis zum Download (war NOT NULL)
    original_name   TEXT NOT NULL,
    relative_path   TEXT NOT NULL DEFAULT '',
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    mime_type       TEXT,
    status          TEXT NOT NULL DEFAULT 'discovered',

    -- SP-Metadaten aus Graph API (kein Dateidownload erforderlich)
    sp_modified_at    TEXT,     -- lastModifiedDateTime
    sp_created_at     TEXT,     -- createdDateTime
    sp_modified_by    TEXT,     -- lastModifiedBy.user.displayName
    sp_created_by     TEXT,     -- createdBy.user.displayName
    sp_web_url        TEXT,     -- direkter Browser-Link zum Dokument
    sp_quick_xor_hash TEXT,     -- Hash für Änderungserkennung ohne Download
    sp_content_type   TEXT,     -- SharePoint Content-Type Name
    sp_list_item_id   TEXT,     -- SharePoint ListItem.id

    -- Selektion für Indexierungs-Queue
    selected_for_indexing INTEGER NOT NULL DEFAULT 0,   -- 0 = nein, 1 = ja

    -- FKs aus Migration 002
    project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    source_id       INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    source_item_id  TEXT,       -- SharePoint DriveItem.id
    source_path     TEXT,       -- Pfad in der SP-Bibliothek
    markdown_path   TEXT,       -- relativ zu data/markdown/

    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Daten aus alter Tabelle übernehmen
INSERT INTO documents_new (
    id, sha256, original_name, relative_path, size_bytes, mime_type, status,
    project_id, source_id, source_item_id, source_path, markdown_path,
    created_at, updated_at
)
SELECT
    id, sha256, original_name, relative_path, size_bytes, mime_type, status,
    project_id, source_id, source_item_id, source_path, markdown_path,
    created_at, updated_at
FROM documents;

DROP TABLE documents;
ALTER TABLE documents_new RENAME TO documents;

-- Indizes (alle aus 001 + 002 neu anlegen)
CREATE INDEX idx_documents_status   ON documents(status);
CREATE INDEX idx_documents_project  ON documents(project_id);
CREATE INDEX idx_documents_source   ON documents(source_id);
CREATE INDEX idx_documents_selected ON documents(selected_for_indexing)
    WHERE selected_for_indexing = 1;

-- Partieller Unique-Index: SP-Dokumente eindeutig, Phase-0-Dokumente ohne Quelle erlaubt
CREATE UNIQUE INDEX idx_documents_source_item
    ON documents(source_id, source_item_id)
    WHERE source_item_id IS NOT NULL;

-- ----------------------------------------------------------------
-- 2. SharePoint-Bibliotheksspalten (key/value pro Dokument)
-- ----------------------------------------------------------------
CREATE TABLE document_sp_fields (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    field_name  TEXT NOT NULL,
    field_value TEXT,                           -- alle Werte als Text gespeichert
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX idx_sp_fields_doc_name ON document_sp_fields(document_id, field_name);
CREATE INDEX idx_sp_fields_name            ON document_sp_fields(field_name);

-- ----------------------------------------------------------------
-- 3. Delta-Link pro Quelle
-- ----------------------------------------------------------------
ALTER TABLE sources ADD COLUMN sp_delta_link TEXT;

COMMIT;
