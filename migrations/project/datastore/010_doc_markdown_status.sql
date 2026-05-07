-- 010_doc_markdown_status.sql
-- ===========================================================================
-- agent_doc_markdown: Failed-Tracking + Retry-Counter
-- ===========================================================================
-- Phase 3 vom Pipeline-Konzept (Konzept-Diskussion 2026-05-07): Extraction
-- soll zwischen "noch nicht extrahiert" (pending) und "Extraktion
-- fehlgeschlagen" (failed) unterscheiden koennen, damit die Pipeline-Ampel
-- in Schritt 5 ehrlich 🟡 zeigen kann statt nur 🔴/🟢.
--
-- Zwei Spalten ergaenzt, beide additiv (idempotent), backward-compatible.
-- Bestehende Eintraege haben error=NULL, retry_count=0 — gelten als
-- erfolgreich extrahiert (was sie ja sind, sonst waeren sie nicht in
-- agent_doc_markdown).

-- error: Free-Form-Text der Fehlermeldung. NULL = kein Fehler.
-- Engine-spezifische Strings erlaubt — kein ENUM, damit neue Engines
-- keine Schema-Migration brauchen.
ALTER TABLE agent_doc_markdown ADD COLUMN error TEXT;

-- retry_count: wie oft die Extraction fuer diese Datei schon versucht
-- wurde (inkl. erfolgreicher Laeufe). Wird vom Extraction-Flow bei
-- jedem Item-Call hochgezaehlt, unabhaengig vom Ergebnis.
ALTER TABLE agent_doc_markdown
    ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_doc_markdown_error
    ON agent_doc_markdown(error)
    WHERE error IS NOT NULL;
