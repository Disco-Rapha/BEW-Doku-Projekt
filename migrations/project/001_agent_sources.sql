-- Projekt-DB-Template Migration 001: agent_sources Registry
--
-- Diese Migrationen laufen auf JEDER Projekt-data.db (nicht auf der
-- zentralen system.db). Sie sind idempotent und werden bei jedem
-- `disco project init` angewendet.
--
-- Zweck:
--   agent_sources         — Registry aller Dateien in sources/, mit Hash + Status
--   agent_source_metadata — Zusatz-Metadaten (aus Begleit-Excel/CSV, key/value)
--   agent_source_scans    — Historie der Scan-Laeufe fuer Audit

BEGIN;

-- ----------------------------------------------------------------
-- agent_sources — Registry pro Datei
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_sources (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Identifikation
    rel_path          TEXT NOT NULL UNIQUE,   -- z.B. "Elektro/Planung/foo.pdf"
    filename          TEXT NOT NULL,          -- "foo.pdf"
    folder            TEXT NOT NULL DEFAULT '', -- "Elektro/Planung" (leer = Wurzel)
    extension         TEXT,                   -- "pdf" (lowercase, ohne Punkt)

    -- Datei-Metadaten
    size_bytes        INTEGER NOT NULL DEFAULT 0,
    sha256            TEXT,                   -- Hex-Digest, NULL fuer Ordner-Marker
    mtime             TEXT,                   -- ISO8601 vom Filesystem

    -- Registry-Metadaten
    first_seen_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_changed_at   TEXT,                   -- letzter sha256-Wechsel
    status            TEXT NOT NULL DEFAULT 'active',
                      -- 'active'   — Datei existiert gerade
                      -- 'deleted'  — war mal da, jetzt nicht mehr im FS
                      -- 'replaced' — reserviert, jetzt nicht benutzt

    -- SharePoint-Felder (leer wenn nur lokal)
    sp_item_id        TEXT,
    sp_web_url        TEXT,
    sp_modified_by    TEXT,
    sp_content_type   TEXT,

    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_sources_status
    ON agent_sources(status);
CREATE INDEX IF NOT EXISTS idx_agent_sources_folder
    ON agent_sources(folder);
CREATE INDEX IF NOT EXISTS idx_agent_sources_extension
    ON agent_sources(extension);
CREATE INDEX IF NOT EXISTS idx_agent_sources_sha256
    ON agent_sources(sha256);

-- ----------------------------------------------------------------
-- agent_source_metadata — Begleit-Metadaten (key/value pro Datei)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_source_metadata (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id        INTEGER NOT NULL REFERENCES agent_sources(id) ON DELETE CASCADE,
    key              TEXT NOT NULL,            -- z.B. "Disziplin", "Gewerk", "DCC"
    value            TEXT,
    source_of_truth  TEXT NOT NULL DEFAULT 'user',
                     -- 'sharepoint'    — aus SP-Metadaten
                     -- 'begleit-excel' — aus Zusatz-Excel des Kunden
                     -- 'agent'         — vom Agent abgeleitet/klassifiziert
                     -- 'user'          — manuell gesetzt
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Pro (source, key, source_of_truth) nur ein Wert — Updates ueberschreiben.
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_metadata_unique
    ON agent_source_metadata(source_id, key, source_of_truth);
CREATE INDEX IF NOT EXISTS idx_source_metadata_key
    ON agent_source_metadata(key);

-- ----------------------------------------------------------------
-- agent_source_scans — Historie der Scans
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_source_scans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_type    TEXT NOT NULL,                -- 'initial'|'incremental'|'fs-only'|'sp-delta'
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT,
    n_new        INTEGER NOT NULL DEFAULT 0,
    n_changed    INTEGER NOT NULL DEFAULT 0,
    n_deleted    INTEGER NOT NULL DEFAULT 0,
    n_unchanged  INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    notes        TEXT
);

CREATE INDEX IF NOT EXISTS idx_source_scans_started
    ON agent_source_scans(started_at);

COMMIT;
