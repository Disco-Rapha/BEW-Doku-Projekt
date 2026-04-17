-- Projekt-DB-Template 002: agent_source_relations
--
-- Beziehungen zwischen Registry-Eintraegen. Eine Datei kann zu mehreren
-- anderen Dateien in Beziehung stehen (Duplikat-Set, Versionskette,
-- Format-Konversion, Annotationen, Teilmenge eines Dokumenten-Sets).
--
-- Erlaubte 'kind'-Werte (Konvention, nicht per CHECK eingeschraenkt um
-- erweiterbar zu bleiben):
--   duplicate-of            — gleicher sha256, anderer Pfad
--   replaces / replaced-by  — Versionskette
--   derived-from            — DWG→PDF, Excel→CSV, Scan→OCR-PDF
--   annotated-version-of    — Original + Kommentare/Stempel
--   part-of-set             — logisch zusammengehoerig (Montage+Stueckliste+Pruefplan)
--   sourced-from            — externe Herkunft (to_source_id kann NULL sein,
--                             dann steht die Quelle in note)

BEGIN;

CREATE TABLE IF NOT EXISTS agent_source_relations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_source_id  INTEGER NOT NULL REFERENCES agent_sources(id) ON DELETE CASCADE,
    to_source_id    INTEGER REFERENCES agent_sources(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 1.0,
    detected_by     TEXT NOT NULL DEFAULT 'agent',
                    -- 'duplicate-hash' | 'filename-heuristic'
                    -- | 'agent-inferred' | 'user' | 'begleit-excel'
    detected_at     TEXT NOT NULL DEFAULT (datetime('now')),
    note            TEXT
);

-- Ein Paar (from, to, kind) darf nur einmal existieren — idempotent schreibbar.
-- Bei to_source_id=NULL (z.B. sourced-from mit Freitext) greift der Unique nicht,
-- deshalb zusaetzlich ein expression-basierter Index.
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_relations_unique_with_to
    ON agent_source_relations(from_source_id, to_source_id, kind)
    WHERE to_source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_source_relations_kind
    ON agent_source_relations(kind);
CREATE INDEX IF NOT EXISTS idx_source_relations_from
    ON agent_source_relations(from_source_id);
CREATE INDEX IF NOT EXISTS idx_source_relations_to
    ON agent_source_relations(to_source_id);

COMMIT;
