#!/usr/bin/env python3
"""Hotfix: agent_source_locations.source_id-FK korrigieren.

Bug-Ursache: Migrate_pipeline_v2 erstellte agent_source_locations mit
FK auf agent_sources, dann ALTER TABLE agent_sources RENAME TO
agent_sources_pre_migration. SQLite hat die FK-Referenz beim RENAME
mitumgeschrieben → die Locations-FK zeigt jetzt auf pre_migration
statt auf das neue agent_sources.

Solange agent_sources_pre_migration zufällig die nötigen IDs enthält
(Bestandsprojekte), greift die FK glücklich. Bei frischen Projekten
oder neuen Sources mit ID > pre_migration.max(id) schlägt FK fehl.

Fix: agent_source_locations neu anlegen mit korrekter FK, Daten
kopieren, alte Tabelle droppen. Idempotent (skip wenn FK schon stimmt).

Usage:
    scripts/fix_fk_pipeline_v2.py <project-path>
    scripts/fix_fk_pipeline_v2.py --all-prod
    scripts/fix_fk_pipeline_v2.py --all-dev
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def get_fk_target(conn: sqlite3.Connection, table: str) -> str | None:
    """Liefert den Tabellen-Namen, auf den die FK von <table>.source_id zeigt."""
    rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    for r in rows:
        # PRAGMA-Result: (id, seq, table, from, to, on_update, on_delete, match)
        if r[3] == "source_id":
            return r[2]
    return None


def fix_one(project_path: Path) -> tuple[str, str]:
    """Fix für ein Projekt. Returns (status, detail)."""
    ds = project_path / "datastore.db"
    if not ds.exists():
        return ("skip", "datastore.db fehlt")

    conn = sqlite3.connect(str(ds), isolation_level=None)
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='agent_source_locations'"
        ).fetchone():
            return ("skip", "agent_source_locations nicht vorhanden")

        target = get_fk_target(conn, "agent_source_locations")
        if target == "agent_sources":
            return ("ok", "FK schon korrekt")
        if target != "agent_sources_pre_migration":
            return ("warn", f"FK zeigt auf {target!r} (unerwartet) — manuell prüfen")

        # FK falsch → Tabelle neu erstellen
        n = conn.execute("SELECT COUNT(*) FROM agent_source_locations").fetchone()[0]

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            # 1. Neue Tabelle mit korrekter FK
            conn.execute("""
                CREATE TABLE agent_source_locations_fixed (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id         INTEGER NOT NULL REFERENCES agent_sources(id),
                    rel_path          TEXT NOT NULL,
                    logical_path      TEXT,
                    origin            TEXT NOT NULL DEFAULT 'local-folder',
                    status            TEXT NOT NULL DEFAULT 'active',
                    first_seen_at     TEXT NOT NULL,
                    last_seen_at      TEXT NOT NULL,
                    mtime             TEXT,
                    filename          TEXT NOT NULL,
                    folder            TEXT NOT NULL DEFAULT '',
                    extension         TEXT,
                    canonical_path    TEXT,
                    sp_item_id        TEXT,
                    sp_web_url        TEXT,
                    sp_modified_by    TEXT,
                    sp_content_type   TEXT,
                    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            # 2. Daten kopieren
            conn.execute("""
                INSERT INTO agent_source_locations_fixed
                  (id, source_id, rel_path, logical_path, origin, status,
                   first_seen_at, last_seen_at, mtime, filename, folder, extension,
                   canonical_path, sp_item_id, sp_web_url, sp_modified_by,
                   sp_content_type, created_at, updated_at)
                SELECT
                  id, source_id, rel_path, logical_path, origin, status,
                  first_seen_at, last_seen_at, mtime, filename, folder, extension,
                  canonical_path, sp_item_id, sp_web_url, sp_modified_by,
                  sp_content_type, created_at, updated_at
                FROM agent_source_locations
            """)
            # 3. Indizes droppen (Index-Namen würden kollidieren)
            for idx in (
                "idx_locations_source", "idx_locations_rel_path",
                "idx_locations_status", "idx_locations_origin",
                "idx_locations_folder", "idx_locations_extension",
                "idx_locations_canonical_path",
            ):
                conn.execute(f"DROP INDEX IF EXISTS {idx}")
            # 4. Alte Tabelle weg, neue umbenennen
            conn.execute("DROP TABLE agent_source_locations")
            conn.execute("ALTER TABLE agent_source_locations_fixed RENAME TO agent_source_locations")
            # 5. Indizes neu anlegen
            for sql in (
                "CREATE INDEX idx_locations_source ON agent_source_locations(source_id)",
                "CREATE INDEX idx_locations_rel_path ON agent_source_locations(rel_path)",
                "CREATE INDEX idx_locations_status ON agent_source_locations(status)",
                "CREATE INDEX idx_locations_origin ON agent_source_locations(origin)",
                "CREATE INDEX idx_locations_folder ON agent_source_locations(folder)",
                "CREATE INDEX idx_locations_extension ON agent_source_locations(extension)",
                "CREATE INDEX idx_locations_canonical_path ON agent_source_locations(canonical_path)",
            ):
                conn.execute(sql)
            conn.execute("COMMIT")

            new_target = get_fk_target(conn, "agent_source_locations")
            return ("fixed", f"FK auf {new_target!r}, {n} Locations migriert")
        except Exception as e:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def cmd_one(project_path: Path) -> int:
    status, detail = fix_one(project_path)
    print(f"  {project_path.name:50s}  [{status:6s}]  {detail}")
    return 0 if status in ("ok", "fixed", "skip") else 1


def cmd_all(workspace_root: Path) -> int:
    projects_dir = workspace_root / "projects"
    if not projects_dir.exists():
        print(f"ERROR: {projects_dir} nicht gefunden")
        return 1
    errors = 0
    for proj_path in sorted(projects_dir.iterdir()):
        if not proj_path.is_dir():
            continue
        try:
            status, detail = fix_one(proj_path)
            print(f"  {proj_path.name:50s}  [{status:6s}]  {detail}")
            if status not in ("ok", "fixed", "skip"):
                errors += 1
        except Exception as e:
            print(f"  {proj_path.name:50s}  [error]  {e}")
            errors += 1
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("project_path", nargs="?", type=Path)
    grp.add_argument("--all-prod", action="store_true")
    grp.add_argument("--all-dev", action="store_true")
    args = ap.parse_args(argv)

    if args.all_prod:
        print(f"==== Fix FK auf allen Prod-Projekten (~/Disco/projects/) ====")
        return cmd_all(Path.home() / "Disco")
    if args.all_dev:
        print(f"==== Fix FK auf allen Dev-Projekten (~/Disco-dev/projects/) ====")
        return cmd_all(Path.home() / "Disco-dev")
    if args.project_path:
        return cmd_one(args.project_path.expanduser().resolve())
    return 1


if __name__ == "__main__":
    sys.exit(main())
