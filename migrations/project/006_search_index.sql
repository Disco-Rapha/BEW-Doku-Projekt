-- Projekt-DB-Template 006: Volltext-Suche (FTS5) mit Seiten-Chunks
--
-- Phase 0 von Discos Such-Infrastruktur:
--   - Seitenweise Chunks (Seite eines PDFs = ein Chunk)
--   - Markdown-Dateien: ganze Datei = ein Chunk (kein Seitenbegriff)
--   - Kontext-Praeambel pro Chunk (Dokumentname + Seite + naechste
--     Ueberschrift) fuer besseres BM25-Ranking
--   - Tokenizer unicode61 mit remove_diacritics=2 fuer deutsche Texte
--   - Prefix-Index (2/3/4) fuer Teilwort-Queries wie "schall*"
--
-- Phase 1 (Embeddings via sqlite-vec) faellt spaeter eine parallele
-- Tabelle; die Chunk-Struktur bleibt identisch.
--
-- Tabellen:
--   agent_search_docs        — Registry pro indizierter Datei (Hash + Zaehler)
--   agent_search_chunks_fts  — FTS5 virtual table, primaere Speicherung
--
-- Der Agent darf beide Tabellen lesen (sqlite_query). Geschrieben wird
-- ausschliesslich ueber das Tool `build_search_index` — der Namespace
-- agent_* laesst das technisch zu, aber die Konvention ist: Hands off
-- per SQL, damit doc-Zaehler und FTS konsistent bleiben.

BEGIN;

-- ----------------------------------------------------------------
-- agent_search_docs — ein Eintrag pro indizierter Datei
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_search_docs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identifikation
    rel_path        TEXT NOT NULL UNIQUE,  -- z.B. "sources/Elektro/foo.pdf"
    kind            TEXT NOT NULL,         -- 'sources' | 'context' | 'exports' | 'work'
    filename        TEXT NOT NULL,
    extension       TEXT,                  -- 'pdf','md','txt',...

    -- Invalidierung: wenn sich sha256 aendert, muessen die Chunks neu
    sha256          TEXT,                  -- Hex-Digest der Quelldatei
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    total_pages     INTEGER NOT NULL DEFAULT 0,  -- bei MDs: 1
    n_chunks        INTEGER NOT NULL DEFAULT 0,

    -- Indexing-Metadaten
    indexed_at      TEXT NOT NULL DEFAULT (datetime('now')),
    indexer_version TEXT NOT NULL DEFAULT 'v1',
    error           TEXT,                  -- gefuellt wenn Extraktion scheiterte

    CHECK (kind IN ('sources','context','exports','work'))
);

CREATE INDEX IF NOT EXISTS idx_search_docs_kind
    ON agent_search_docs(kind);
CREATE INDEX IF NOT EXISTS idx_search_docs_sha
    ON agent_search_docs(sha256);

-- ----------------------------------------------------------------
-- agent_search_chunks_fts — FTS5 virtual table (primaere Speicherung)
-- ----------------------------------------------------------------
--
-- Spalten:
--   text      — eigentlicher Seiten-/Chunk-Text (tokenisiert)
--   heading   — naechstliegende Ueberschrift vor dem Chunk (tokenisiert)
--   doc_id    — FK auf agent_search_docs.id (UNINDEXED, nur Lookup)
--   doc_path  — Anzeige im Treffer (UNINDEXED)
--   kind      — fuer Filter im SELECT (UNINDEXED, 'sources'|'context'|...)
--   page_num  — Seitenzahl 1-basiert (UNINDEXED, Viewer-Deep-Link)
--
-- UNINDEXED heisst: wird im FTS-Index nicht tokenisiert, aber bei
-- SELECT * ausgeliefert. Perfekt fuer Metadaten, die wir zur Anzeige
-- brauchen, aber nicht mit-durchsuchen wollen.
--
-- Tokenizer:
--   unicode61 remove_diacritics 2 — deutsche Umlaute werden stabil
--   behandelt (ae=ä, o=ö etc.), Mehrbyte-Codepunkte sauber zerlegt.
--
-- prefix = '2 3 4':
--   erlaubt effiziente Prefix-Queries "sch*", "werk*" bis 4 Zeichen.
CREATE VIRTUAL TABLE IF NOT EXISTS agent_search_chunks_fts USING fts5(
    text,
    heading,
    doc_id UNINDEXED,
    doc_path UNINDEXED,
    kind UNINDEXED,
    page_num UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2',
    prefix = '2 3 4'
);

COMMIT;
