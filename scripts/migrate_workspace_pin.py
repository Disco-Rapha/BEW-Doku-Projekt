#!/usr/bin/env python3
"""Pipeline-Reform v2 — Phase C: Workspace-Pin-Migration.

Fügt allen work_*-/agent_*-Tabellen in workspace.db, die auf
agent_sources zeigen (Spalten source_id / file_id), zwei neue
Spalten hinzu:
  - source_sha256_pinned  TEXT  — Hash zum Auswertungs-Zeitpunkt
  - evaluated_at          TEXT  — Wann die Auswertung gemacht wurde

und füllt sie für Bestandsdaten:
  - source_sha256_pinned = aktueller Hash der referenzierten Source
  - evaluated_at         = COALESCE(created_at, datetime('now'))

Idempotent: prüft pro Spalte ob sie schon existiert.
Tabellen mit MEHREREN Source-Spalten (z.B. work_duplicate_canonical_export
mit original_source_id + canonical_source_id) werden übersprungen — die
sind meist Audit-Snapshots, da brauchen wir den Pin nicht zwingend.

Usage:
    scripts/migrate_workspace_pin.py inspect <project-path>
    scripts/migrate_workspace_pin.py migrate <project-path>
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Wir mappen "file_id" und "source_id" beide auf agent_sources.id —
# semantisch sind sie identisch im Hash-Modell.
SOURCE_REF_COLUMNS = ("source_id", "file_id")


def banner(text: str) -> None:
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def find_pinnable_tables(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Findet work_*/agent_*-Tabellen mit GENAU einer Source-Ref-Spalte.

    Returns: [(table_name, source_id_column), ...]
    """
    tables = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' "
            "AND (name LIKE 'work_%' OR name LIKE 'agent_%') "
            "AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE '_disco%'"
        ).fetchall()
    ]
    out: list[tuple[str, str]] = []
    for tbl in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{tbl}')").fetchall()]
        matching = [c for c in cols if c in SOURCE_REF_COLUMNS]
        if len(matching) == 1:
            out.append((tbl, matching[0]))
    return out


def col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{table}')").fetchall()]
    return col in cols


def cmd_inspect(project_path: Path) -> int:
    ws = project_path / "workspace.db"
    ds = project_path / "datastore.db"
    if not ws.exists():
        print(f"ERROR: workspace.db nicht gefunden: {ws}")
        return 1
    if not ds.exists():
        print(f"ERROR: datastore.db nicht gefunden: {ds}")
        return 1

    banner(f"Inspect Workspace-Pin: {project_path.name}")
    conn = sqlite3.connect(ws)
    conn.execute(f"ATTACH DATABASE '{ds}' AS ds")

    tables = find_pinnable_tables(conn)
    print(f"\nKandidaten-Tabellen (genau 1 source_id-/file_id-Spalte): {len(tables)}\n")
    for tbl, col in tables:
        n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        has_pin = col_exists(conn, tbl, "source_sha256_pinned")
        has_at = col_exists(conn, tbl, "evaluated_at")
        # Wie viele Zeilen würden gepinnt werden können (= source existiert)?
        if n > 0:
            pinnable = conn.execute(
                f"SELECT COUNT(*) FROM {tbl} t "
                f"WHERE EXISTS (SELECT 1 FROM ds.agent_sources s WHERE s.id = t.{col})"
            ).fetchone()[0]
        else:
            pinnable = 0
        pin_status = "✓" if has_pin else "—"
        at_status = "✓" if has_at else "—"
        print(f"  {tbl:50s} rows={n:6d}  pin={pin_status}  evaluated_at={at_status}  "
              f"pinnable_via_source={pinnable}")

    conn.close()
    return 0


def cmd_migrate(project_path: Path) -> int:
    ws = project_path / "workspace.db"
    ds = project_path / "datastore.db"
    if not ws.exists() or not ds.exists():
        print(f"ERROR: workspace.db oder datastore.db nicht gefunden: {project_path}")
        return 1

    banner(f"Migrate Workspace-Pin: {project_path.name}")
    conn = sqlite3.connect(ws, isolation_level=None)
    conn.execute(f"ATTACH DATABASE '{ds}' AS ds")
    conn.execute("PRAGMA foreign_keys = OFF")

    tables = find_pinnable_tables(conn)
    print(f"\nKandidaten-Tabellen: {len(tables)}")

    try:
        conn.execute("BEGIN")
        for tbl, col in tables:
            n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            actions = []

            # 1. ADD COLUMN source_sha256_pinned (idempotent)
            if not col_exists(conn, tbl, "source_sha256_pinned"):
                conn.execute(
                    f"ALTER TABLE {tbl} ADD COLUMN source_sha256_pinned TEXT"
                )
                actions.append("+pin")

            # 2. ADD COLUMN evaluated_at (idempotent)
            if not col_exists(conn, tbl, "evaluated_at"):
                conn.execute(
                    f"ALTER TABLE {tbl} ADD COLUMN evaluated_at TEXT"
                )
                actions.append("+evaluated_at")

            # 3. Backfill pin (nur leere Pin-Felder updaten — idempotent)
            backfilled_pin = 0
            if n > 0:
                cur = conn.execute(f"""
                    UPDATE {tbl}
                    SET source_sha256_pinned = (
                        SELECT sha256 FROM ds.agent_sources s WHERE s.id = {tbl}.{col}
                    )
                    WHERE source_sha256_pinned IS NULL
                      AND {col} IS NOT NULL
                      AND EXISTS (SELECT 1 FROM ds.agent_sources s WHERE s.id = {tbl}.{col})
                """)
                backfilled_pin = cur.rowcount or 0

            # 4. Backfill evaluated_at (mit created_at falls vorhanden, sonst now)
            backfilled_at = 0
            if n > 0:
                has_created_at = col_exists(conn, tbl, "created_at")
                if has_created_at:
                    cur = conn.execute(f"""
                        UPDATE {tbl}
                        SET evaluated_at = COALESCE(created_at, datetime('now'))
                        WHERE evaluated_at IS NULL
                    """)
                else:
                    cur = conn.execute(f"""
                        UPDATE {tbl}
                        SET evaluated_at = datetime('now')
                        WHERE evaluated_at IS NULL
                    """)
                backfilled_at = cur.rowcount or 0

            if actions or backfilled_pin or backfilled_at:
                act_str = ",".join(actions) if actions else "(cols vorhanden)"
                print(f"  {tbl:50s} {act_str:25s} pin_filled={backfilled_pin:6d} "
                      f"at_filled={backfilled_at:6d}")
            else:
                print(f"  {tbl:50s} (nichts zu tun)")

        conn.execute("COMMIT")
        print("\n✓ Workspace-Pin-Migration committed")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"\n✗ ERROR: {e}")
        print("  ROLLBACK durchgeführt — workspace.db unverändert")
        raise
    finally:
        conn.close()

    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_in = sub.add_parser("inspect")
    p_in.add_argument("project_path", type=Path)
    p_mig = sub.add_parser("migrate")
    p_mig.add_argument("project_path", type=Path)

    args = ap.parse_args(argv)
    pp = args.project_path.expanduser().resolve()

    if args.cmd == "inspect":
        return cmd_inspect(pp)
    if args.cmd == "migrate":
        return cmd_migrate(pp)
    return 1


if __name__ == "__main__":
    sys.exit(main())
