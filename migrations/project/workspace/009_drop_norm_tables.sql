-- 011_drop_norm_tables.sql
-- ===========================================================================
-- _norm-Tabellen entfernen — durch canonical_path-Approach obsolet geworden.
-- ===========================================================================
-- Historisch existierten als Workaround fuer das Unicode-/Pfad-Match-
-- Problem (NFD vs NFC, ': ' vs '/'):
--
--   agent_sources_norm (filename_raw, filename_norm, rel_path)
--   agent_sp_projektdoku_norm (sp_id, name_raw, name_norm, path)
--   agent_sp_mek_norm (sp_id, name_raw, name_norm, path)
--   agent_sp_zueblin_norm (sp_id, name_raw, name_norm, path)
--
-- Die _norm-Spalten waren verlustbehaftete Vereinfachungen (lowercased +
-- degermanisiert), die nur den Match fuer SOLL/IST + Cross-Check moeglich
-- gemacht haben.
--
-- Mit Migration 011 (agent_sources.canonical_path) ist diese Kruecke
-- obsolet: ein direkter JOIN auf canonical_path liefert dasselbe Ergebnis
-- byte-exakt und ohne Information-Loss.
--
-- DROP IF EXISTS — nicht alle Projekte hatten die Tabellen, je nach
-- historischem Stand.

DROP TABLE IF EXISTS agent_sources_norm;
DROP TABLE IF EXISTS agent_sp_projektdoku_norm;
DROP TABLE IF EXISTS agent_sp_mek_norm;
DROP TABLE IF EXISTS agent_sp_zueblin_norm;
