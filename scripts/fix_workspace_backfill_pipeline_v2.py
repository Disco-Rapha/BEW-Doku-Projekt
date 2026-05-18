#!/usr/bin/env python3
"""Workspace-Backfill: übersehene Source-ID-Spalten nachträglich umbiegen.

Hintergrund:
    migrate_pipeline_v2.py kannte beim ID-Mapping nur 4 Spalten-Namen:
    source_id, file_id, original_source_id, canonical_source_id.

    In Prod-Projekten gibt es aber weitere Source-ID-Spalten:
    current_source_id, current_file_id, foreign_source_id,
    foreign_file_id, source_export_file_id, source_file_id,
    col_source_id, markdown_file_id, ...

    Diese Spalten zeigen nach Migration weiter auf alte Source-IDs aus
    der pre-Migration-Welt — was zu "source missing" oder "hash mismatch"
    in Disco-Auswertungen führt (z.B. agent_dcc_truth_documents).

    Dieses Script ergänzt das Mapping mit den übersehenen Spalten.

Strategie:
    Strategie A (für Tabellen mit Hash-Pin):
      - Identifiziere Hash-Spalte (source_hash_sha256, source_hash, sha256)
      - Update Zeilen, deren aktueller (source_id, hash) NICHT zu
        agent_sources(id, sha256) passt, aber im Mapping über sha256
        auffindbar sind.

    Strategie B (Tabellen ohne Hash-Pin):
      - Update Zeilen, deren source_id in pre_migration existiert
        aber nicht in agent_sources (= alte, ungemappte IDs).

Beide Strategien sind idempotent — bei zweitem Lauf greift kein WHERE.

Usage:
    scripts/fix_workspace_backfill_pipeline_v2.py inspect <project-path>
    scripts/fix_workspace_backfill_pipeline_v2.py migrate <project-path>
    scripts/fix_workspace_backfill_pipeline_v2.py migrate --all-prod
    scripts/fix_workspace_backfill_pipeline_v2.py migrate --all-dev
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


# Erweiterte Liste der Source-ID-Spaltennamen.
SOURCE_ID_COLUMNS = (
    "source_id", "file_id",
    "original_source_id", "canonical_source_id",
    "current_source_id", "current_file_id",
    "foreign_source_id", "foreign_file_id",
    "source_export_file_id", "source_file_id",
    "col_source_id", "markdown_file_id",
)

# Mögliche Hash-Pin-Spaltennamen pro Tabelle.
HASH_PIN_COLUMNS = (
    "source_hash_sha256", "source_hash", "source_sha256",
    "source_sha256_pinned", "sha256",
)


def banner(text: str) -> None:
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def find_id_columns(conn: sqlite3.Connection) -> list[tuple[str, list[str], str | None]]:
    """Findet pro Tabelle: source-id-Spalten + ggf. eine Hash-Pin-Spalte.

    Returns: [(table, [id_col1, id_col2, ...], hash_col_or_none), ...]
    """
    tables = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE '_disco%' "
            "AND name NOT LIKE 'agent_search_chunks_fts%'"
        ).fetchall()
    ]
    out = []
    for tbl in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{tbl}')").fetchall()]
        ids = [c for c in cols if c in SOURCE_ID_COLUMNS]
        if not ids:
            continue
        hash_col = next((c for c in cols if c in HASH_PIN_COLUMNS), None)
        out.append((tbl, ids, hash_col))
    return out


def column_is_unique(conn: sqlite3.Connection, table: str, col: str) -> bool:
    """True wenn col PK oder durch UNIQUE-Index allein abgedeckt."""
    pks = [r[1] for r in conn.execute(f"PRAGMA table_info('{table}')").fetchall() if r[5] > 0]
    if pks == [col]:
        return True
    for idx in conn.execute(f"PRAGMA index_list('{table}')").fetchall():
        idx_name, is_unique = idx[1], idx[2]
        if not is_unique:
            continue
        idx_cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{idx_name}')").fetchall()]
        if idx_cols == [col]:
            return True
    return False


def cmd_inspect(project_path: Path) -> int:
    ws = project_path / "workspace.db"
    ds = project_path / "datastore.db"
    if not ws.exists() or not ds.exists():
        print(f"ERROR: workspace.db oder datastore.db nicht gefunden")
        return 1

    banner(f"Inspect Workspace-Backfill: {project_path.name}")
    conn = sqlite3.connect(ws)
    conn.execute(f"ATTACH DATABASE '{ds}' AS ds")

    # Mapping vorhanden?
    has_map = conn.execute(
        "SELECT 1 FROM ds.sqlite_master WHERE type='table' "
        "AND name='_migration_source_id_map'"
    ).fetchone() is not None
    if not has_map:
        print("  _migration_source_id_map nicht vorhanden — Projekt nicht migriert?")
        return 1

    map_count = conn.execute("SELECT COUNT(*) FROM ds._migration_source_id_map").fetchone()[0]
    print(f"  _migration_source_id_map: {map_count} Einträge\n")

    tables = find_id_columns(conn)
    total_to_fix = 0
    for tbl, id_cols, hash_col in tables:
        for col in id_cols:
            # Was wäre zu fixen?
            if hash_col:
                # Strategie A: Hash-Match prüfen
                n_to_fix = conn.execute(f"""
                    SELECT COUNT(*) FROM {tbl} t
                    WHERE t.{col} IS NOT NULL
                      AND t.{hash_col} IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM ds.agent_sources s
                        WHERE s.id = t.{col} AND s.sha256 = t.{hash_col}
                      )
                      AND EXISTS (
                        SELECT 1 FROM ds._migration_source_id_map m
                        WHERE m.sha256 = t.{hash_col}
                      )
                """).fetchone()[0]
                strat = f"A:hash={hash_col}"
            else:
                # Strategie B: old_id-Mapping
                n_to_fix = conn.execute(f"""
                    SELECT COUNT(*) FROM {tbl} t
                    WHERE t.{col} IS NOT NULL
                      AND EXISTS (
                        SELECT 1 FROM ds.agent_sources_pre_migration p
                        WHERE p.id = t.{col}
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM ds.agent_sources s WHERE s.id = t.{col}
                      )
                """).fetchone()[0]
                strat = "B:old_id"

            unique = "UNIQUE" if column_is_unique(conn, tbl, col) else ""
            marker = "✓" if col in ("source_id", "file_id", "original_source_id", "canonical_source_id") else "★"
            print(f"  {marker} {tbl:55s}.{col:25s} {strat:20s} {unique:6s} to_fix={n_to_fix}")
            total_to_fix += n_to_fix

    print(f"\n  Total Zeilen die gefixt würden: {total_to_fix}")
    conn.close()
    return 0


def cmd_migrate(project_path: Path) -> int:
    ws = project_path / "workspace.db"
    ds = project_path / "datastore.db"
    if not ws.exists() or not ds.exists():
        print(f"  ERROR: workspace.db oder datastore.db nicht gefunden")
        return 1

    conn = sqlite3.connect(ws, isolation_level=None)
    conn.execute(f"ATTACH DATABASE '{ds}' AS ds")

    has_map = conn.execute(
        "SELECT 1 FROM ds.sqlite_master WHERE type='table' "
        "AND name='_migration_source_id_map'"
    ).fetchone() is not None
    if not has_map:
        print(f"  {project_path.name}: SKIP (nicht migriert)")
        conn.close()
        return 0

    tables = find_id_columns(conn)
    total_fixed = 0

    try:
        conn.execute("BEGIN")
        for tbl, id_cols, hash_col in tables:
            for col in id_cols:
                is_unique = column_is_unique(conn, tbl, col)
                # Zähle was zu mappen ist
                if hash_col:
                    n = conn.execute(f"""
                        SELECT COUNT(*) FROM {tbl} t
                        WHERE t.{col} IS NOT NULL
                          AND t.{hash_col} IS NOT NULL
                          AND NOT EXISTS (
                            SELECT 1 FROM ds.agent_sources s
                            WHERE s.id = t.{col} AND s.sha256 = t.{hash_col}
                          )
                          AND EXISTS (
                            SELECT 1 FROM ds._migration_source_id_map m
                            WHERE m.sha256 = t.{hash_col}
                          )
                    """).fetchone()[0]
                else:
                    n = conn.execute(f"""
                        SELECT COUNT(*) FROM {tbl} t
                        WHERE t.{col} IS NOT NULL
                          AND EXISTS (
                            SELECT 1 FROM ds.agent_sources_pre_migration p
                            WHERE p.id = t.{col}
                          )
                          AND NOT EXISTS (
                            SELECT 1 FROM ds.agent_sources s WHERE s.id = t.{col}
                          )
                    """).fetchone()[0]
                if n == 0:
                    continue

                # Pre-Dedupe bei UNIQUE-Spalte
                pre_dedup = 0
                pre_conflict_drop = 0
                if is_unique:
                    # Zusätzlich: lösche to-fix-Zeilen, deren Ziel-new_id
                    # in der gleichen Tabelle schon als Wert vorkommt
                    # (Audit-Log: veraltete Zeilen mit alter ID werden
                    # gedroppt, neuere Zeile mit aktueller ID gewinnt).
                    if hash_col:
                        pre_conflict_drop = conn.execute(f"""
                            DELETE FROM {tbl}
                            WHERE rowid IN (
                                SELECT t.rowid FROM {tbl} t
                                JOIN ds._migration_source_id_map mp ON mp.sha256 = t.{hash_col}
                                WHERE t.{col} IS NOT NULL
                                  AND t.{hash_col} IS NOT NULL
                                  AND NOT EXISTS (
                                    SELECT 1 FROM ds.agent_sources s
                                    WHERE s.id = t.{col} AND s.sha256 = t.{hash_col}
                                  )
                                  AND EXISTS (
                                    SELECT 1 FROM {tbl} t2
                                    WHERE t2.{col} = mp.new_id AND t2.rowid != t.rowid
                                  )
                            )
                        """).rowcount or 0
                    else:
                        pre_conflict_drop = conn.execute(f"""
                            DELETE FROM {tbl}
                            WHERE rowid IN (
                                SELECT t.rowid FROM {tbl} t
                                JOIN ds._migration_source_id_map mp ON mp.old_id = t.{col}
                                WHERE t.{col} IS NOT NULL
                                  AND EXISTS (SELECT 1 FROM ds.agent_sources_pre_migration p WHERE p.id = t.{col})
                                  AND NOT EXISTS (SELECT 1 FROM ds.agent_sources s WHERE s.id = t.{col})
                                  AND EXISTS (
                                    SELECT 1 FROM {tbl} t2
                                    WHERE t2.{col} = mp.new_id AND t2.rowid != t.rowid
                                  )
                            )
                        """).rowcount or 0
                    if hash_col:
                        # Behalte pro künftiger new_id (= map.new_id über sha256) MIN(rowid)
                        pre_dedup = conn.execute(f"""
                            DELETE FROM {tbl}
                            WHERE rowid NOT IN (
                                SELECT MIN(t.rowid)
                                FROM {tbl} t
                                JOIN ds._migration_source_id_map mp ON mp.sha256 = t.{hash_col}
                                WHERE t.{col} IS NOT NULL
                                  AND t.{hash_col} IS NOT NULL
                                  AND NOT EXISTS (
                                    SELECT 1 FROM ds.agent_sources s
                                    WHERE s.id = t.{col} AND s.sha256 = t.{hash_col}
                                  )
                                GROUP BY mp.new_id
                            )
                            AND t.{col} IS NOT NULL
                            AND t.{hash_col} IS NOT NULL
                            AND NOT EXISTS (
                                SELECT 1 FROM ds.agent_sources s
                                WHERE s.id = {tbl}.{col} AND s.sha256 = {tbl}.{hash_col}
                            )
                            AND EXISTS (
                                SELECT 1 FROM ds._migration_source_id_map m
                                WHERE m.sha256 = {tbl}.{hash_col}
                            )
                        """).rowcount or 0
                    else:
                        pre_dedup = conn.execute(f"""
                            DELETE FROM {tbl}
                            WHERE rowid NOT IN (
                                SELECT MIN(t.rowid)
                                FROM {tbl} t
                                JOIN ds._migration_source_id_map mp ON mp.old_id = t.{col}
                                WHERE t.{col} IS NOT NULL
                                  AND EXISTS (SELECT 1 FROM ds.agent_sources_pre_migration p WHERE p.id = t.{col})
                                  AND NOT EXISTS (SELECT 1 FROM ds.agent_sources s WHERE s.id = t.{col})
                                GROUP BY mp.new_id
                            )
                            AND {col} IS NOT NULL
                            AND EXISTS (SELECT 1 FROM ds.agent_sources_pre_migration p WHERE p.id = {tbl}.{col})
                            AND NOT EXISTS (SELECT 1 FROM ds.agent_sources s WHERE s.id = {tbl}.{col})
                        """).rowcount or 0

                # Zwei-Pass-Mapping via Negativ-Range (gegen UNIQUE-Konflikt)
                if hash_col:
                    # Strategie A: Hash-basiert
                    conn.execute(f"""
                        UPDATE {tbl}
                        SET {col} = -1 * (
                            SELECT new_id FROM ds._migration_source_id_map m
                            WHERE m.sha256 = {tbl}.{hash_col}
                        )
                        WHERE {col} IS NOT NULL
                          AND {hash_col} IS NOT NULL
                          AND NOT EXISTS (
                            SELECT 1 FROM ds.agent_sources s
                            WHERE s.id = {tbl}.{col} AND s.sha256 = {tbl}.{hash_col}
                          )
                          AND EXISTS (
                            SELECT 1 FROM ds._migration_source_id_map m
                            WHERE m.sha256 = {tbl}.{hash_col}
                          )
                    """)
                else:
                    # Strategie B: old_id-basiert
                    conn.execute(f"""
                        UPDATE {tbl}
                        SET {col} = -1 * (
                            SELECT new_id FROM ds._migration_source_id_map
                            WHERE old_id = {tbl}.{col}
                        )
                        WHERE {col} IS NOT NULL
                          AND EXISTS (SELECT 1 FROM ds.agent_sources_pre_migration p WHERE p.id = {tbl}.{col})
                          AND NOT EXISTS (SELECT 1 FROM ds.agent_sources s WHERE s.id = {tbl}.{col})
                    """)
                conn.execute(f"UPDATE {tbl} SET {col} = -{col} WHERE {col} < 0")

                strat = f"hash={hash_col}" if hash_col else "old_id"
                extras = []
                if pre_conflict_drop:
                    extras.append(f"pre-conflict-drop: -{pre_conflict_drop}")
                if pre_dedup:
                    extras.append(f"pre-dedup: -{pre_dedup}")
                extra = " (" + ", ".join(extras) + ")" if extras else ""
                # Echte Fix-Anzahl nach möglichen Drops
                actual_fixed = max(0, n - pre_conflict_drop - pre_dedup)
                print(f"  {project_path.name:40s} {tbl:50s}.{col:25s} {strat:25s} fixed={actual_fixed}{extra}")
                total_fixed += actual_fixed

        conn.execute("COMMIT")
        if total_fixed > 0:
            print(f"  {project_path.name}: ✓ Backfill committed, {total_fixed} Zeilen umgemappt")
        else:
            print(f"  {project_path.name}: ✓ nothing to do")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"  {project_path.name}: ✗ ERROR {e} — ROLLBACK")
        raise
    finally:
        conn.close()

    return 0


def cmd_migrate_all(workspace_root: Path) -> int:
    projects_dir = workspace_root / "projects"
    errors = 0
    for proj in sorted(projects_dir.iterdir()):
        if not proj.is_dir():
            continue
        try:
            cmd_migrate(proj)
        except Exception:
            errors += 1
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_in = sub.add_parser("inspect")
    p_in.add_argument("project_path", type=Path)
    p_mig = sub.add_parser("migrate")
    g = p_mig.add_mutually_exclusive_group(required=True)
    g.add_argument("project_path", nargs="?", type=Path)
    g.add_argument("--all-prod", action="store_true")
    g.add_argument("--all-dev", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "inspect":
        return cmd_inspect(args.project_path.expanduser().resolve())
    if args.cmd == "migrate":
        if args.all_prod:
            return cmd_migrate_all(Path.home() / "Disco")
        if args.all_dev:
            return cmd_migrate_all(Path.home() / "Disco-dev")
        if args.project_path:
            return cmd_migrate(args.project_path.expanduser().resolve())
    return 1


if __name__ == "__main__":
    sys.exit(main())
