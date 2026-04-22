-- Projekt-DB-Template 007: PDF-Pipeline-Tabellen
--
-- Diese Tabellen bilden die Eingangs-Stufen der PDF-Pipeline und werden
-- von den Library-Flows unter `src/disco/flows/library/` erwartet:
--
--   agent_pdf_inventory   — Inventar aller PDFs (rel_path, Hash, Gewerk,
--                            Dateigroesse). Eingang fuer pdf_routing_decision.
--   work_pdf_routing      — Pro PDF: Engine-Entscheidung (docling-standard /
--                            azure-di / azure-di-hr) plus Seiten-Statistik.
--                            Wird auch vom pdf_routing_decision-Runner selbst
--                            angelegt, aber hier ist die Schema-Wahrheit.
--
-- Warum Template statt Runner-CREATE-IF-NOT-EXISTS?
--   Damit das Schema in jedem Projekt identisch ist — unabhaengig davon,
--   welche Flow-Version gerade in `library/` liegt. Aenderungen am Schema
--   kommen kuenftig als Template-Migration 008, nicht als stille ALTER-
--   TABLE-Patches im Runner.
--
-- Wer fuellt agent_pdf_inventory?
--   Aktuell per run_python (Ad-hoc-Scan ueber sources/). Ein eigenes
--   pdf_inventory-Flow-Skript folgt spaeter. Die Tabelle wird leer
--   angelegt — jedes Projekt befuellt sie selbst.

BEGIN;

-- ----------------------------------------------------------------
-- agent_pdf_inventory — Eingang der PDF-Pipeline
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_pdf_inventory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path        TEXT UNIQUE,         -- relativ zum Projekt-Root
    file_name       TEXT,                 -- Dateiname ohne Pfad
    file_name_norm  TEXT,                 -- lower(trim(NFC(file_name))) — fuer Joins
    gewerk          TEXT,                 -- optional: Gewerk/Abschnitt aus dem Pfad
    size_bytes      INTEGER,
    sha256          TEXT                  -- Hex-Digest der Quelldatei
);

CREATE INDEX IF NOT EXISTS idx_pdf_inventory_sha
    ON agent_pdf_inventory(sha256);
CREATE INDEX IF NOT EXISTS idx_pdf_inventory_fname_norm
    ON agent_pdf_inventory(file_name_norm);
CREATE INDEX IF NOT EXISTS idx_pdf_inventory_gewerk
    ON agent_pdf_inventory(gewerk);

-- ----------------------------------------------------------------
-- work_pdf_routing — Routing-Entscheidung pro PDF
-- ----------------------------------------------------------------
-- Primary Key = file_id (FK auf agent_pdf_inventory.id) — Upsert via
-- INSERT OR REPLACE erlaubt Rerun ohne Duplikate.
CREATE TABLE IF NOT EXISTS work_pdf_routing (
    file_id                INTEGER PRIMARY KEY,
    rel_path               TEXT NOT NULL,
    n_pages                INTEGER,

    -- Pro Seite: text / scan / vector-drawing / mixed / empty
    kind_counts_json       TEXT,
    n_scan_pages           INTEGER,
    n_vdrawing_pages       INTEGER,
    n_text_pages           INTEGER,
    n_mixed_pages          INTEGER,
    share_scan_or_vdrawing REAL,

    -- 3-Tier-Signale (v2)
    max_page_width_pt      REAL,         -- max Seitenbreite (pt) — Plan-Format-Detect
    n_large_image_pages    INTEGER,      -- Seiten mit image_coverage > 0.60

    -- Entscheidung
    engine                 TEXT,         -- 'docling-standard' | 'azure-di' | 'azure-di-hr'
    reason                 TEXT,

    -- Run-Metadaten
    duration_ms            REAL,
    run_id                 INTEGER,
    created_at             TEXT
);

CREATE INDEX IF NOT EXISTS idx_pdf_routing_engine
    ON work_pdf_routing(engine);
CREATE INDEX IF NOT EXISTS idx_pdf_routing_run
    ON work_pdf_routing(run_id);

COMMIT;
