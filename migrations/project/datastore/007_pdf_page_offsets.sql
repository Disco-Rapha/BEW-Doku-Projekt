-- Projekt-DB-Template datastore/007: Seitenindex + Pipeline-Versionierung
--
-- Hintergrund:
--   Vor dieser Migration war agent_pdf_markdown ein opaker Markdown-Blob
--   pro PDF. Seitenzahlen konnten nur durch Scanning der `<!-- Seite N -->`-
--   HTML-Kommentare wiedergefunden werden (und auch nur bei Azure-DI,
--   Docling setzt diese Marker nicht).
--
--   Fuer Citations, PDF-Deep-Links und "zeig mir Seite 7"-Queries
--   brauchen wir einen echten Offset-Index pro Seite.
--
--   Gleichzeitig beginnen wir ab 2026-04-24 mit grossflaechigen
--   Extraktions-Laeufen. Die erzeugten Markdown-Inhalte bleiben lange im
--   System. Wenn wir spaeter die Pipeline aendern (neue Engine, neuer
--   DI-Mode, anderer Post-Processing-Schritt), wollen wir zielgerichtet
--   nur die veralteten Rows re-extrahieren — nicht pauschal alles.
--   Dafuer braucht es eine explizite Version pro Row.
--
-- Designentscheidung "voller Blob bleibt erhalten":
--   agent_pdf_markdown.md_content wird NICHT aufgeteilt. Multi-Page-
--   Tabellen, die Azure-DI zusammengefuehrt hat, bleiben zusammengefuehrt.
--   Der Seitenindex beschreibt nur, welche Zeichenbereiche im Blob zu
--   welcher Seite gehoeren. Content-Lookups liefern weiter die volle
--   Wahrheit, Seiten-Lookups nur einen Ausschnitt.
--
-- Additiv & rueckwaerts-kompatibel:
--   - Neue Spalten an agent_pdf_markdown sind NULL-faehig. Bestandsdaten
--     funktionieren weiter, haben einfach keine extractor_version.
--   - Neue Tabelle agent_pdf_page_offsets ist optional — fehlt ein
--     Eintrag fuer ein file_id, faellt der Reader auf "volles Dokument"
--     zurueck (kein Seiten-Lookup moeglich, aber Content ist da).
--   - Kein Backfill. Re-Extraktion erfolgt ueber den Flow
--     `pdf_to_markdown` mit force_rerun=true.

BEGIN;

-- ----------------------------------------------------------------
-- agent_pdf_markdown: Versions-Tracking
-- ----------------------------------------------------------------
-- extractor_version: Code-Kennzeichen (z.B. "2026-04-24"). Der Flow-
--   Runner schreibt den Wert des Moduls src/disco/pdf.EXTRACTOR_VERSION
--   mit. Aenderungen am Extraktionsverhalten (Engine-Config, Post-
--   Processing, Marker-Insertion, Bugfixes) bumpen diese Konstante —
--   dadurch sind Rows mit veralteter Extraktion per SQL auffindbar.
--
-- Bewusst NICHT mitgefuehrt in dieser Migration:
--   - Engine-API-Version (z.B. Azure-DI-API-Version): fuer jetzt ueber
--     extractor_version abgedeckt. Wenn wir spaeter feinere Aufloesung
--     brauchen (z.B. "nur die mit DI-API 2024-11-30 re-extrahieren"),
--     kommt eine Folgemigration mit engine_version.
ALTER TABLE agent_pdf_markdown ADD COLUMN extractor_version TEXT;

CREATE INDEX IF NOT EXISTS idx_pdf_markdown_extractor_version
    ON agent_pdf_markdown(extractor_version);

-- ----------------------------------------------------------------
-- agent_pdf_page_offsets: Seite -> Zeichen-Offset-Range
-- ----------------------------------------------------------------
-- Zweck: O(1)-Lookup "Was steht auf Seite N von Datei X?".
--
-- Invarianten:
--   - char_start <= char_end
--   - char_end ist exklusiv (Python-Slice-Semantik: md[start:end])
--   - page_num >= 1
--   - PK (file_id, page_num) — pro (Datei, Seite) genau ein Eintrag
--
-- Befuellung:
--   Azure-DI-Runs liefern page.spans[].offset. markdown.py berechnet
--   daraus die Offsets im final (mit Markern versehenen) Markdown-Blob
--   und gibt sie als meta["page_offsets"] zurueck. runner.py persistiert
--   sie hier.
--   Docling liefert aktuell keine Marker/Offsets — dann bleibt die
--   Tabelle fuer diese file_id leer. Der Reader faellt auf "volles
--   Dokument" zurueck.
CREATE TABLE IF NOT EXISTS agent_pdf_page_offsets (
    file_id    INTEGER NOT NULL,
    page_num   INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end   INTEGER NOT NULL,
    PRIMARY KEY (file_id, page_num)
);

CREATE INDEX IF NOT EXISTS idx_pdf_page_offsets_file
    ON agent_pdf_page_offsets(file_id);

COMMIT;
