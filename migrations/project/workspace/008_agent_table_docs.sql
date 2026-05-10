-- Migration 008 — agent_table_docs
--
-- Schicht 3 der Memory-Reform 2026-05-09: Tabellen-Wissen wandert weg
-- aus DISCO.md (`## Projekt-Tabellen`-Kapitel) hin zu einer eigenen
-- Tabelle, die Disco direkt per SQL abfragen kann.
--
-- Pro Projekt-Tabelle (`work_*`/`agent_*`/`context_*`) ein Eintrag mit
-- Beschreibung + Schema-Summary + Beispiel-Query + Quell-Files. Pflege
-- über Tools `table_doc_set` / `table_doc_get`.

CREATE TABLE IF NOT EXISTS agent_table_docs (
    table_name      TEXT PRIMARY KEY,
    layer           TEXT NOT NULL
                    CHECK (layer IN ('workspace', 'datastore', 'context')),
    description     TEXT NOT NULL,         -- 1-3 Zeilen, was steht drin
    schema_summary  TEXT,                  -- z.B. "kks_code TEXT PK, status TEXT, ..."
    example_query   TEXT,                  -- typischer SELECT
    source_files    TEXT,                  -- z.B. "imported from sources/_meta/ibl-2026.xlsx"
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_table_docs_layer
    ON agent_table_docs(layer);
