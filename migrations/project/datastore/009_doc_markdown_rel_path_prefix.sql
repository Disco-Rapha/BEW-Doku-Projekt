-- Projekt-DB-Template Migration datastore/009: agent_doc_markdown.rel_path-Format vereinheitlichen
--
-- Hintergrund:
--   In Migration 008 (Pipeline-Generalisierung) hat der extraction-Flow
--   `rel_path` aus `agent_sources` direkt uebernommen — also ohne
--   sources/ bzw. context/-Praefix. Damit ist `agent_doc_markdown.rel_path`
--   nicht mit Filesystem-Pfaden joinbar (Search-Index, doc_markdown_read,
--   Viewer haben Filesystem-Pfad als Eingabe).
--
--   Diese Migration repariert Bestandseintraege idempotent: nur Eintraege,
--   die kein 'sources/' oder 'context/' Praefix haben, bekommen eines
--   anhand des `kind`-Felds in `agent_sources` (kind='context' →
--   'context/<rel_path>', sonst 'sources/<rel_path>').
--
--   Schon korrekt formatierte Eintraege (z.B. PDF aus dem Pre-Migration-
--   008-Stand, die hatten von Anfang an Praefix) bleiben unangetastet.
--
-- Provenance-Header in md_content:
--   Die HTML-Kommentar-Bloecke in den Markdown-Inhalten sind hier nicht
--   automatisch repariert. Bestand bleibt mit dem alten Praefix-losen
--   Pfad im Header. Bei Bedarf: `flow_run extraction force_rerun=true`,
--   dann werden die Markdowns inkl. Provenance neu geschrieben.

BEGIN;

UPDATE agent_doc_markdown
SET rel_path = (
    SELECT
        CASE s.kind
            WHEN 'context' THEN 'context/' || agent_doc_markdown.rel_path
            ELSE 'sources/' || agent_doc_markdown.rel_path
        END
    FROM agent_sources s
    WHERE s.id = agent_doc_markdown.file_id
)
WHERE rel_path NOT LIKE 'sources/%'
  AND rel_path NOT LIKE 'context/%'
  AND EXISTS (SELECT 1 FROM agent_sources s WHERE s.id = agent_doc_markdown.file_id);

COMMIT;
