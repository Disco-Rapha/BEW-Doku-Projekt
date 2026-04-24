-- Projekt-DB-Template 009: `kind`-Tag fuer agent_sources + agent_pdf_inventory
--
-- Hintergrund:
--   Bis einschliesslich Migration 008 war die Pipeline sources-only:
--     sources/ → sources_register → agent_sources → (ad-hoc run_python) →
--     agent_pdf_inventory → pdf_routing_decision → pdf_to_markdown
--   Der context/-Ordner (Normen, Kataloge, Richtlinien) lief daneben mit
--   einem separaten Skill (context-onboarding), aber PDFs dort konnten
--   nicht durch die Flow-Pipeline fliessen, weil keine Inventory-Zeile
--   fuer sie existierte.
--
-- Diese Migration fuegt eine Diskriminator-Spalte `kind` hinzu (Default
-- 'source' fuer alle Bestandsdaten — 100% rueckwaerts-kompatibel).
-- Der Scanner (sources_register) bekommt in Anschluss einen optionalen
-- `scope`-Parameter ('sources' | 'context' | 'both'), der Dateien aus
-- dem jeweiligen Unterbaum scannt und mit dem passenden `kind` tagged.
-- Dadurch laufen Context-PDFs durch **dieselben** Flows wie Source-PDFs —
-- nur mit anderem Tag.
--
-- Alle Aenderungen sind additiv (ALTER TABLE ADD COLUMN mit Default).
-- Keine Drops, keine Renames, keine harten Cutover.

BEGIN;

-- ----------------------------------------------------------------
-- agent_sources: Spalte `kind`
-- ----------------------------------------------------------------
-- Bestandsdaten bekommen automatisch 'source'. Neue context-Scans
-- schreiben 'context'.
ALTER TABLE agent_sources ADD COLUMN kind TEXT NOT NULL DEFAULT 'source';

CREATE INDEX IF NOT EXISTS idx_agent_sources_kind
    ON agent_sources(kind);

-- ----------------------------------------------------------------
-- agent_pdf_inventory: Spalte `kind`
-- ----------------------------------------------------------------
-- Wird beim Inventory-Sync aus agent_sources.kind kopiert.
ALTER TABLE agent_pdf_inventory ADD COLUMN kind TEXT NOT NULL DEFAULT 'source';

CREATE INDEX IF NOT EXISTS idx_pdf_inventory_kind
    ON agent_pdf_inventory(kind);

COMMIT;
