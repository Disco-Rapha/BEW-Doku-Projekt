-- Projekt-DB-Template 004 (datastore): PDF-Inventar-Tabelle (Ebene 2)
--
--   agent_pdf_inventory — Inventar aller PDFs (rel_path, Hash, Gewerk,
--                         Dateigroesse). Eingang fuer pdf_routing_decision.
--
-- Die Routing-Entscheidung pro PDF (work_pdf_routing) ist eine reine
-- Reasoning-/Arbeits-Tabelle (Ebene 3) und liegt deshalb in der
-- workspace.db — siehe migrations/project/workspace/004_pdf_routing.sql.
--
-- Warum Template statt Runner-CREATE-IF-NOT-EXISTS?
--   Damit das Schema in jedem Projekt identisch ist — unabhaengig davon,
--   welche Flow-Version gerade in `library/` liegt. Aenderungen am Schema
--   kommen kuenftig als Template-Migration 006, nicht als stille ALTER-
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

COMMIT;
