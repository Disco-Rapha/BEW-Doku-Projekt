-- Migration 002: Projekte, Quellen und SharePoint-Connector-Daten
--
-- Neue Tabellen:  projects, sources, source_folders
-- Erweiterung:    documents um project_id, source_id, source_item_id,
--                 source_path, markdown_path
--
-- Bestehende Dokumente erhalten NULL für die neuen FK-Spalten.
-- Das ist beabsichtigt: Phase-0-Dokumente (manuell registriert) werden
-- in Phase 1 ggf. einem Projekt/einer Quelle zugeordnet.

BEGIN;

-- Projekte: Top-Level-Container für alle Quellen und Dokumente
CREATE TABLE projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'active',   -- active | archived
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX idx_projects_name ON projects(name);

-- Quellen: gehört zu genau einem Projekt
-- config_json enthält quellentyp-spezifische Einstellungen:
--   sharepoint_library: { site_url, library_name, drive_id (nach erstem Sync) }
CREATE TABLE sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'sharepoint_library',
    config_json     TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'active',   -- active | paused | error
    last_synced_at  TEXT,                             -- NULL = noch nie synchronisiert
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_sources_project ON sources(project_id);
CREATE UNIQUE INDEX idx_sources_project_name ON sources(project_id, name);

-- Ordnerhierarchie aus der Quelle (Adjacency-List für Baumnavigation)
CREATE TABLE source_folders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    parent_id   INTEGER REFERENCES source_folders(id) ON DELETE CASCADE,
    sp_item_id  TEXT NOT NULL,       -- SharePoint DriveItem.id
    name        TEXT NOT NULL,       -- Ordnername
    sp_path     TEXT NOT NULL,       -- Vollpfad in der SP-Bibliothek
    sp_web_url  TEXT,                -- Direktlink im Browser
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_source_folders_source ON source_folders(source_id);
CREATE INDEX idx_source_folders_parent ON source_folders(parent_id);
CREATE UNIQUE INDEX idx_source_folders_sp_item ON source_folders(source_id, sp_item_id);

-- documents erweitern: FKs zu projects/sources und SharePoint-Metadaten
-- Bestehende Zeilen erhalten NULL für alle neuen Spalten.
ALTER TABLE documents ADD COLUMN project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL;
ALTER TABLE documents ADD COLUMN source_id       INTEGER REFERENCES sources(id) ON DELETE SET NULL;
ALTER TABLE documents ADD COLUMN source_item_id  TEXT;   -- SP DriveItem.id
ALTER TABLE documents ADD COLUMN source_path     TEXT;   -- Pfad in der SP-Bibliothek
ALTER TABLE documents ADD COLUMN markdown_path   TEXT;   -- relativ zu data/markdown/

CREATE INDEX idx_documents_project ON documents(project_id);
CREATE INDEX idx_documents_source  ON documents(source_id);

-- Partieller Unique-Index: verhindert Duplikate bei SP-Dokumenten,
-- lässt aber NULL (Phase-0-Dokumente ohne Quelle) unbeschränkt
CREATE UNIQUE INDEX idx_documents_source_item
    ON documents(source_id, source_item_id)
    WHERE source_item_id IS NOT NULL;

COMMIT;
