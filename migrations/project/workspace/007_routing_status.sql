-- 007_routing_status.sql
-- ===========================================================================
-- work_extraction_routing: Failed-Tracking + Retry-Counter
-- ===========================================================================
-- Phase 3 vom Pipeline-Konzept (Konzept-Diskussion 2026-05-07): Routing
-- soll zwischen "noch nicht versucht" (pending) und "versucht aber
-- fehlgeschlagen" (failed) unterscheiden koennen, damit die Pipeline-
-- Ampel in Schritt 4 ehrlich 🟡 zeigen kann statt nur 🔴/🟢.
--
-- Zwei Spalten ergaenzt, beide additiv (idempotent), beide
-- backward-compatible — bestehende Routings haben error=NULL,
-- retry_count=0.

-- error: Free-Form-Text der Fehlermeldung. NULL = kein Fehler.
-- Engine-spezifische Strings erlaubt (Azure-DI-Code, libredwg-Signal,
-- pypdf-Exception etc.) — kein ENUM, damit neue Engines keine
-- Schema-Migration brauchen.
ALTER TABLE work_extraction_routing ADD COLUMN error TEXT;

-- retry_count: wie oft das Routing fuer diese Datei schon versucht
-- wurde (inkl. erfolgreicher Laeufe). Wird vom Routing-Flow bei jedem
-- Item-Call hochgezaehlt, unabhaengig vom Ergebnis.
ALTER TABLE work_extraction_routing
    ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_routing_error
    ON work_extraction_routing(error)
    WHERE error IS NOT NULL;
