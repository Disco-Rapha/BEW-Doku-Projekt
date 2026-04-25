-- Projekt-DB-Template Migration workspace/005: Routing-Generalisierung
--
-- work_pdf_routing wird zur generischen Routing-Tabelle fuer alle Formate.
-- Bestandsdaten (PDF) bleiben erhalten, file_kind='pdf' als Default.

BEGIN;

ALTER TABLE work_pdf_routing RENAME TO work_extraction_routing;

-- file_kind: pdf | excel | dwg | image
ALTER TABLE work_extraction_routing ADD COLUMN file_kind TEXT NOT NULL DEFAULT 'pdf';

-- Versionierung der Routing-Heuristik (z.B. 'router-v2.0')
ALTER TABLE work_extraction_routing ADD COLUMN router_version TEXT;

-- Format-spezifische Heuristik-Werte als JSON
-- (PDF nutzt heute eigene Spalten n_scan_pages etc., die bleiben fuer
--  Backward-Compat. Neue Formate schreiben in heuristics_json.)
ALTER TABLE work_extraction_routing ADD COLUMN heuristics_json TEXT;

DROP INDEX IF EXISTS idx_pdf_routing_engine;
DROP INDEX IF EXISTS idx_pdf_routing_run;

CREATE INDEX IF NOT EXISTS idx_extraction_routing_kind
    ON work_extraction_routing(file_kind);
CREATE INDEX IF NOT EXISTS idx_extraction_routing_engine
    ON work_extraction_routing(engine);
CREATE INDEX IF NOT EXISTS idx_extraction_routing_run
    ON work_extraction_routing(run_id);

COMMIT;
