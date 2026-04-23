-- Projekt-DB-Template 004 (workspace): PDF-Routing-Tabelle (Ebene 3)
--
--   work_pdf_routing — Pro PDF: Engine-Entscheidung (docling-standard /
--                      azure-di / azure-di-hr) plus Seiten-Statistik.
--                      Wird von `flows/library/pdf_routing_decision/` gefuellt
--                      und von `pdf_to_markdown/` gelesen (JOIN mit
--                      ds.agent_pdf_inventory).
--
-- Warum workspace.db und nicht datastore.db?
--   `work_*` ist eine Reasoning-/Zwischen-Tabelle (Ebene 3), keine
--   Quell-Content-Tabelle. Die Engine-Entscheidung gehoert zum agentischen
--   Arbeitsprozess im Projekt, nicht zum Rohbestand. Damit bleibt
--   datastore.db ein reines Content-/Provenance-Repository.
--
-- FK-Hinweis:
--   file_id referenziert ds.agent_pdf_inventory.id (datastore.db). SQLite
--   unterstuetzt keine cross-DB-FKs, daher nur als Konvention dokumentiert,
--   nicht deklariert.

BEGIN;

-- ----------------------------------------------------------------
-- work_pdf_routing — Routing-Entscheidung pro PDF
-- ----------------------------------------------------------------
-- Primary Key = file_id (logische FK auf ds.agent_pdf_inventory.id) —
-- Upsert via INSERT OR REPLACE erlaubt Rerun ohne Duplikate.
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
