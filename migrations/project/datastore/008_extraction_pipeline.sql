-- Projekt-DB-Template Migration datastore/008: Extraction-Pipeline-Generalisierung
--
-- Hintergrund:
--   Die PDF-Pipeline wird auf eine generische Doc-Pipeline gehoben.
--   Vier Formate (PDF, Excel, DWG, Bild) gehen durch denselben Routing-
--   und Extraktions-Flow. Output: ein einheitliches Markdown-Package.
--
--   Siehe docs/architektur-ebenen.md (Ebene 2 — Content) und CLAUDE.md.
--
-- Schritte:
--   1. agent_pdf_markdown      → agent_doc_markdown (+ file_kind, n_units, meta_json)
--   2. agent_pdf_page_offsets  → agent_doc_unit_offsets (+ unit_label, page_num→unit_num)
--   3. Indizes umbenennen
--
-- Bestandsdaten (PDF) bleiben erhalten — additive Migration. file_kind=
-- 'pdf' als Default, n_units wird aus den Page-Offsets backgefuellt.

BEGIN;

-- ----------------------------------------------------------------
-- 1. agent_pdf_markdown -> agent_doc_markdown
-- ----------------------------------------------------------------
ALTER TABLE agent_pdf_markdown RENAME TO agent_doc_markdown;

-- file_kind: pdf | excel | dwg | image (Bestand alles 'pdf')
ALTER TABLE agent_doc_markdown ADD COLUMN file_kind TEXT NOT NULL DEFAULT 'pdf';

-- n_units: Seiten (PDF) / Sheets (Excel) / 1 (DWG/Bild)
ALTER TABLE agent_doc_markdown ADD COLUMN n_units INTEGER;

-- meta_json: format-spezifisches als JSON
ALTER TABLE agent_doc_markdown ADD COLUMN meta_json TEXT;

-- Backfill n_units fuer Bestand: count der Page-Offsets pro file_id
UPDATE agent_doc_markdown
SET n_units = COALESCE(
    (SELECT COUNT(*)
     FROM agent_pdf_page_offsets po
     WHERE po.file_id = agent_doc_markdown.file_id),
    0
);

-- Indizes umbenennen (drop+create, weil SQLite kein RENAME INDEX hat)
DROP INDEX IF EXISTS idx_pdf_markdown_engine;
DROP INDEX IF EXISTS idx_pdf_markdown_run;
DROP INDEX IF EXISTS idx_pdf_markdown_hash;
DROP INDEX IF EXISTS idx_pdf_markdown_extractor_version;

CREATE INDEX IF NOT EXISTS idx_doc_markdown_kind
    ON agent_doc_markdown(file_kind);
CREATE INDEX IF NOT EXISTS idx_doc_markdown_engine
    ON agent_doc_markdown(engine);
CREATE INDEX IF NOT EXISTS idx_doc_markdown_run
    ON agent_doc_markdown(run_id);
CREATE INDEX IF NOT EXISTS idx_doc_markdown_hash
    ON agent_doc_markdown(source_hash);
CREATE INDEX IF NOT EXISTS idx_doc_markdown_extractor_version
    ON agent_doc_markdown(extractor_version);


-- ----------------------------------------------------------------
-- 2. agent_pdf_page_offsets -> agent_doc_unit_offsets
-- ----------------------------------------------------------------
ALTER TABLE agent_pdf_page_offsets RENAME TO agent_doc_unit_offsets;

-- Spalte page_num → unit_num (semantisch generischer)
ALTER TABLE agent_doc_unit_offsets RENAME COLUMN page_num TO unit_num;

-- unit_label: 'p1'/'p2' bei PDF, Sheet-Name bei Excel, 'all'/'image' bei DWG/Bild
ALTER TABLE agent_doc_unit_offsets ADD COLUMN unit_label TEXT;

-- Backfill: PDF-Seiten bekommen unit_label = 'p<N>'
UPDATE agent_doc_unit_offsets
SET unit_label = 'p' || CAST(unit_num AS TEXT)
WHERE unit_label IS NULL;

DROP INDEX IF EXISTS idx_pdf_page_offsets_file;
CREATE INDEX IF NOT EXISTS idx_doc_unit_offsets_file
    ON agent_doc_unit_offsets(file_id);

COMMIT;
