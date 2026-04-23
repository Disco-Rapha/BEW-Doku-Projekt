-- Projekt-DB-Template 008: PDF-Markdown-Tabelle
--
-- Nach dem Routing (007) durchlaeuft jede PDF genau einmal die Pipeline
-- und wird in Markdown ueberfuehrt. Ab diesem Moment ist die Tabelle die
-- alleinige Wahrheit fuer Inhaltsfragen — Disco greift nicht mehr auf
-- die PDFs zurueck, sondern liest aus `agent_pdf_markdown`.
--
-- Drei zugelassene Engines (vgl. work_pdf_routing.engine):
--   docling-standard  — DocLayNet + TableFormer ACCURATE + EasyOCR (MPS)
--   azure-di          — Azure Document Intelligence prebuilt-layout
--   azure-di-hr       — Azure DI prebuilt-layout + ocrHighResolution
--
-- Leere Markdown-Ausgabe wird als leerer String gespeichert (nicht NULL),
-- damit "extrahiert, aber leer" von "noch nicht extrahiert" unterscheidbar
-- bleibt. Idempotenz ueber source_hash: ist der SHA-256 der Quelldatei
-- unveraendert, kann der Flow den Eintrag ueberspringen.

BEGIN;

-- ----------------------------------------------------------------
-- agent_pdf_markdown — Markdown-Content pro PDF
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_pdf_markdown (
    file_id         INTEGER PRIMARY KEY,   -- FK auf agent_pdf_inventory.id
    rel_path        TEXT NOT NULL,
    engine          TEXT NOT NULL,         -- 'docling-standard' | 'azure-di' | 'azure-di-hr'
    md_content      TEXT NOT NULL,         -- leerer String erlaubt, NULL nicht
    char_count      INTEGER,
    source_hash     TEXT,                  -- sha256 der Quelldatei zum Extraktionszeitpunkt
    duration_ms     REAL,
    run_id          INTEGER,
    created_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_pdf_markdown_engine
    ON agent_pdf_markdown(engine);
CREATE INDEX IF NOT EXISTS idx_pdf_markdown_run
    ON agent_pdf_markdown(run_id);
CREATE INDEX IF NOT EXISTS idx_pdf_markdown_hash
    ON agent_pdf_markdown(source_hash);

COMMIT;
