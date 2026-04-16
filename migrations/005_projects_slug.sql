-- Migration 005: projects bekommt eine eigene slug-Spalte
--
-- Hintergrund: Der "Slug" eines Projekts (= Verzeichnisname unter
-- ~/Disco/projects/<slug>/) war bisher nur implizit aus name ableitbar.
-- Bei freier User-Wahl bricht diese Ableitung — z.B. wenn der User Slug
-- 'smoketest-ablauf' waehlt, aber Name "Smoke-Test Ablauf" eintraegt
-- (slugify(name) = 'smoke-test-ablauf', != 'smoketest-ablauf').
--
-- Loesung: explizite slug-Spalte. UNIQUE per partiellem Index, damit
-- alte Eintraege ohne Slug (NULL) nicht kollidieren.
--
-- Backfill: bestehende Projekte bekommen einen Slug aus REPLACE/LOWER
-- des Namens (einfache, ASCII-only Naeherung — fuer "Vattenfall Reuter"
-- und "Testprojekt" passt das exakt zur _project_slug-Logik in Python).

BEGIN;

ALTER TABLE projects ADD COLUMN slug TEXT;

-- Backfill: simple slugify direkt in SQL (lowercase + Spaces zu Dash).
-- Komplexere Faelle (Umlaute) muss spaeter ein Python-Helper handhaben,
-- aber bei den vorhandenen Daten reicht das.
UPDATE projects
   SET slug = REPLACE(LOWER(name), ' ', '-')
 WHERE slug IS NULL;

-- Eindeutigkeit nur fuer nicht-NULL-Slugs (defensives Pattern).
CREATE UNIQUE INDEX idx_projects_slug
    ON projects(slug)
    WHERE slug IS NOT NULL;

COMMIT;
