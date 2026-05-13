-- 011_canonical_path.sql
-- ===========================================================================
-- agent_sources: canonical_path-Spalte fuer Unicode/Pfad-Normalisierung
-- ===========================================================================
-- Bisheriger rel_path enthaelt Filesystem-Repraesentation (auf macOS = NFD,
-- mit ' : ' als OneDrive-Folder-Sep-Substitution fuer SharePoint-Slashes).
-- Das fuehrt zu stillen Mismatches gegen SP-Excel-Importe (NFC + '/').
-- Trockenlauf 2026-05-13: 87% NFD-Anteil in rea-denox, 70% in campus-reuter,
-- u.a.
--
-- canonical_path: NFC-normalisierter Pfad mit '/' als Trenner — die
-- DB-interne Wahrheit. Disco arbeitet ausschliesslich mit canonical_path,
-- Filesystem-Tools haben einen Resolver (disco.fs.path_resolver) der intern
-- zwischen canonical und FS-actual konvertiert.
--
-- rel_path bleibt BESTEHEN als Filesystem-Repraesentation — Backwards-
-- Compatibility waehrend der Tool-Migration. Sobald alle Tools auf
-- canonical_path umgestellt sind, kann rel_path in einer spaeteren
-- Migration entfernt werden.
--
-- Index auf canonical_path: UNIQUE-Constraint kommt NICHT direkt (weil
-- bei rea-denox 44 Kollisionen aus alten NFD/NFC-Doppel-Records mit
-- active+deleted-Status existieren — die werden vom Backfill-Skript
-- konsolidiert). Stattdessen normaler Index fuer Lookup-Performance.
--
-- Backfill: separates Python-Skript `scripts/backfill_canonical_path.py`,
-- nicht als SQL-Migration weil unicodedata.normalize aus Python kommt.

ALTER TABLE agent_sources ADD COLUMN canonical_path TEXT;

-- Index fuer Lookup-Performance. Kein UNIQUE, weil Kollisionen aus
-- active+deleted-Doppel-Records erst vom Backfill aufgeloest werden.
CREATE INDEX IF NOT EXISTS idx_agent_sources_canonical_path
    ON agent_sources(canonical_path);
