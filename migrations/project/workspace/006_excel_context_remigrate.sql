-- 006_excel_context_remigrate.sql
-- ===========================================================================
-- context-Excels: Default von SQL-Tabellen-Import zu Markdown-Extraktion
-- ===========================================================================
-- Vor 2026-05-07 routete der extraction_routing_decision-Flow alle
-- context-Excels automatisch via 'excel-table-import' — was zu Wildwuchs
-- in workspace.db (60+ context_*-Tabellen pro Projekt, viele ungenutzt)
-- gefuehrt hat. Ab jetzt: einheitlich 'excel-openpyxl' (Markdown).
--
-- Diese Migration loescht alle bestehenden Routing-Eintraege mit
-- engine='excel-table-import'. Beim naechsten extraction_routing_decision-
-- Lauf werden die betroffenen Files neu klassifiziert (jetzt zu
-- excel-openpyxl) und der naechste extraction-Lauf zieht das Markdown.
--
-- Bestehende SQL-Tabellen unter context_* bleiben unveraendert —
-- nicht-destruktiv. Wenn die Markdown-Extraktion durch ist, kann der
-- User einzelne context_*-Tabellen manuell droppen, sobald er sicher
-- ist dass nichts mehr dagegen joint.
--
-- Idempotent: bei wiederholtem Lauf wirkt das DELETE auf eine leere
-- Treffer-Menge (keine excel-table-import-Eintraege mehr da).

DELETE FROM work_extraction_routing
WHERE engine = 'excel-table-import';
