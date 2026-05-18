-- 012_doc_markdown_canonical_path.sql
-- ===========================================================================
-- agent_doc_markdown: canonical_path-Spalte fuer Unicode-Konsistenz
-- ===========================================================================
-- Folge-Migration zu 011_canonical_path.sql (agent_sources). Damit Disco
-- auch beim Markdown-Lookup mit kanonischen NFC-Pfaden arbeiten kann
-- (statt FS-Form). Notwendig fuer:
--  - doc_markdown_read({canonical_path: ...})
--  - search-Index-Lookups die via canonical matchen
--  - Pipeline-Cross-Checks gegen agent_sources.canonical_path
--
-- Zeitliche Asymmetrie: rel_path bleibt erhalten als Backwards-Compat.
-- Die meisten Lookups gehen via file_id, da brauchen wir canonical_path
-- nicht — nur fuer den rel_path-basierten Pfad in doc_markdown_read.

ALTER TABLE agent_doc_markdown ADD COLUMN canonical_path TEXT;

CREATE INDEX IF NOT EXISTS idx_doc_markdown_canonical_path
    ON agent_doc_markdown(canonical_path);
