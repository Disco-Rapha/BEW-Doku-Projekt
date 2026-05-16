#!/usr/bin/env python3
"""Pipeline-Reform v2: Hash-zentrierte datastore.db Migration.

Migriert ein Projekt von pfad-zentriertem agent_sources auf hash-zentriert
+ separate agent_source_locations-Tabelle. Konsolidiert markdown/unit_offsets/
metadata pro unique sha256 und biegt workspace.db-Referenzen um.

Usage:
    scripts/migrate_pipeline_v2.py inspect <project-path>
    scripts/migrate_pipeline_v2.py migrate <project-path> [--dry-run]
    scripts/migrate_pipeline_v2.py verify <project-path>

Beispiel:
    scripts/migrate_pipeline_v2.py inspect ~/Disco-dev/staging/vgb-referenzlisten
    scripts/migrate_pipeline_v2.py migrate ~/Disco-dev/staging/vgb-referenzlisten
    scripts/migrate_pipeline_v2.py verify  ~/Disco-dev/staging/vgb-referenzlisten

Sicherheits-Eigenschaften:
- Pre-Check: bricht ab, wenn bereits migriert (agent_sources_pre_migration existiert)
- Transaktional: ROLLBACK bei Fehler in datastore-Phase
- Alte Tabelle bleibt als agent_sources_pre_migration (Rollback per RENAME)
- Workspace-Phase: ATTACH datastore, dynamische Spalten-Erkennung
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# -------------------------------------------------------------------------
# Schemas (nur die NEUEN Tabellen — die alte agent_sources wird umbenannt)
# -------------------------------------------------------------------------

DDL_NEW_AGENT_SOURCES = """
CREATE TABLE agent_sources (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256            TEXT NOT NULL UNIQUE,
    size_bytes        INTEGER NOT NULL DEFAULT 0,
    kind              TEXT NOT NULL DEFAULT 'source',
    status            TEXT NOT NULL DEFAULT 'active',
    first_seen_at     TEXT NOT NULL,
    last_seen_at      TEXT NOT NULL,
    last_changed_at   TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

DDL_NEW_AGENT_SOURCES_INDEXES = [
    "CREATE INDEX idx_agent_sources_sha256 ON agent_sources(sha256);",
    "CREATE INDEX idx_agent_sources_status ON agent_sources(status);",
    "CREATE INDEX idx_agent_sources_kind ON agent_sources(kind);",
]

DDL_LOCATIONS = """
CREATE TABLE agent_source_locations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    -- FK zeigt zu Migrations-Zeit auf agent_sources_new — nach RENAME
    -- agent_sources_new → agent_sources wird SQLite die Referenz
    -- automatisch mit umschreiben. So vermeiden wir den FK-Bug, dass
    -- die Referenz beim RENAME agent_sources → agent_sources_pre_migration
    -- "mitwandert" und am falschen Ziel hängen bleibt.
    source_id         INTEGER NOT NULL REFERENCES agent_sources_new(id),
    rel_path          TEXT NOT NULL,
    logical_path      TEXT,
    origin            TEXT NOT NULL DEFAULT 'local-folder',
    status            TEXT NOT NULL DEFAULT 'active',
    first_seen_at     TEXT NOT NULL,
    last_seen_at      TEXT NOT NULL,
    mtime             TEXT,
    -- Ableitbare Felder (für Filter):
    filename          TEXT NOT NULL,
    folder            TEXT NOT NULL DEFAULT '',
    extension         TEXT,
    canonical_path    TEXT,
    -- SharePoint-Snapshot:
    sp_item_id        TEXT,
    sp_web_url        TEXT,
    sp_modified_by    TEXT,
    sp_content_type   TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

DDL_LOCATIONS_INDEXES = [
    "CREATE INDEX idx_locations_source ON agent_source_locations(source_id);",
    "CREATE INDEX idx_locations_rel_path ON agent_source_locations(rel_path);",
    "CREATE INDEX idx_locations_status ON agent_source_locations(status);",
    "CREATE INDEX idx_locations_origin ON agent_source_locations(origin);",
    "CREATE INDEX idx_locations_folder ON agent_source_locations(folder);",
    "CREATE INDEX idx_locations_extension ON agent_source_locations(extension);",
    "CREATE INDEX idx_locations_canonical_path ON agent_source_locations(canonical_path);",
]


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def banner(text: str) -> None:
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def section(text: str) -> None:
    print(f"\n--- {text} ---")


def table_exists(conn: sqlite3.Connection, name: str, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def column_is_unique(conn: sqlite3.Connection, table: str, col: str) -> bool:
    """True wenn col PRIMARY KEY oder durch UNIQUE-Index allein abgedeckt ist."""
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


def find_source_id_columns(conn: sqlite3.Connection, schema: str = "main") -> list[tuple[str, list[str]]]:
    """Findet alle Tabellen in 'schema', die source_id/file_id-Spalten haben.

    Returns: [(table_name, [col1, col2, ...]), ...]
    """
    tables = [
        r[0] for r in conn.execute(
            f"SELECT name FROM {schema}.sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE '_disco%' AND name NOT LIKE 'agent_search%'"
        ).fetchall()
    ]
    candidates = (
        "source_id", "file_id",
        "original_source_id", "canonical_source_id",
        # Erweiterte Liste — gelernt aus Prod-Migration 2026-05-16
        # (0-dcc-prediction-trainer + metadaten-prediction-opt hatten weitere
        # Source-ID-Spalten-Varianten, die beim ersten Pass nicht erkannt
        # wurden und nachträglich per fix_workspace_backfill_pipeline_v2.py
        # gemapped werden mussten).
        "current_source_id", "current_file_id",
        "foreign_source_id", "foreign_file_id",
        "source_export_file_id", "source_file_id",
        "col_source_id", "markdown_file_id",
    )
    out = []
    for tbl in tables:
        cols = [
            r[1] for r in conn.execute(f"PRAGMA {schema}.table_info('{tbl}')").fetchall()
        ]
        matching = [c for c in cols if c in candidates]
        if matching:
            out.append((tbl, matching))
    return out


# -------------------------------------------------------------------------
# Inspect
# -------------------------------------------------------------------------

def cmd_inspect(project_path: Path) -> int:
    ds = project_path / "datastore.db"
    ws = project_path / "workspace.db"
    if not ds.exists():
        print(f"ERROR: {ds} nicht gefunden")
        return 1

    banner(f"Inspect: {project_path.name}")

    with sqlite3.connect(ds) as conn:
        section("datastore.db — agent_sources Statistik")
        r = conn.execute("SELECT COUNT(*) FROM agent_sources").fetchone()
        print(f"  total rows         : {r[0]}")
        r = conn.execute("SELECT COUNT(*) FROM agent_sources WHERE sha256 IS NOT NULL").fetchone()
        print(f"  with sha256        : {r[0]}")
        r = conn.execute("SELECT COUNT(DISTINCT sha256) FROM agent_sources WHERE sha256 IS NOT NULL").fetchone()
        print(f"  unique sha256      : {r[0]}")
        r = conn.execute("SELECT COUNT(*) FROM agent_sources WHERE sha256 IS NULL").fetchone()
        print(f"  without sha256     : {r[0]}  (werden NICHT migriert!)")

        section("datastore.db — Source-referenzierende Tabellen")
        for tbl in ("agent_doc_markdown", "agent_doc_unit_offsets", "agent_source_metadata", "agent_source_relations"):
            if table_exists(conn, tbl):
                cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                print(f"  {tbl:35s} {cnt}")

        # Markdown: wie viele Hashes haben mehrere Markdown-Zeilen?
        if table_exists(conn, "agent_doc_markdown"):
            r = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT s.sha256
                    FROM agent_doc_markdown m
                    JOIN agent_sources s ON s.id = m.file_id
                    WHERE s.sha256 IS NOT NULL
                    GROUP BY s.sha256
                    HAVING COUNT(*) > 1
                )
            """).fetchone()
            print(f"  hashes with >1 markdown row: {r[0]}  (Konsolidierung nötig)")

    if ws.exists():
        with sqlite3.connect(ws) as conn:
            section("workspace.db — Tabellen mit source_id/file_id Spalten")
            for tbl, cols in find_source_id_columns(conn):
                cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                print(f"  {tbl:50s} {cnt:8d}  cols: {cols}")

    print()
    return 0


# -------------------------------------------------------------------------
# Migrate
# -------------------------------------------------------------------------

def cmd_migrate(project_path: Path, dry_run: bool = False) -> int:
    ds = project_path / "datastore.db"
    ws = project_path / "workspace.db"
    if not ds.exists():
        print(f"ERROR: {ds} nicht gefunden")
        return 1

    banner(f"Migrate: {project_path.name}  (dry_run={dry_run})")

    # Pre-Check
    with sqlite3.connect(ds) as conn:
        if table_exists(conn, "agent_sources_pre_migration"):
            print("ABBRUCH: agent_sources_pre_migration existiert bereits — Projekt schon migriert?")
            print("         Wenn du neu migrieren willst, vorher manuell aufräumen.")
            return 2
        if table_exists(conn, "agent_source_locations"):
            print("ABBRUCH: agent_source_locations existiert bereits — Projekt schon migriert?")
            return 2

    # Phase 1: datastore.db
    section("Phase 1: datastore.db — Schema-Migration")
    migrate_datastore(ds, dry_run=dry_run)

    # Phase 2: workspace.db
    if ws.exists():
        section("Phase 2: workspace.db — Source-ID-Mapping")
        migrate_workspace(ws, ds, dry_run=dry_run)
    else:
        print("\n(workspace.db nicht vorhanden — Phase 2 übersprungen)")

    print("\nMigration abgeschlossen. Verify mit:")
    print(f"  scripts/migrate_pipeline_v2.py verify {project_path}")
    return 0


def migrate_datastore(ds_path: Path, dry_run: bool) -> None:
    # isolation_level=None → expliziter manueller Transaktions-Modus,
    # damit executescript NICHT implizit commitet.
    conn = sqlite3.connect(ds_path, isolation_level=None)
    conn.row_factory = sqlite3.Row  # für r["spalten_name"]-Zugriff
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")

        # 1. Neue Tabellen anlegen — einzelne execute() statt executescript
        # (executescript würde trotz isolation_level=None den manuellen BEGIN
        # ignorieren und einen eigenen Commit machen — gefährlich für ROLLBACK)
        print("  1. Lege neue Tabellen an (agent_sources_new, agent_source_locations)")
        conn.execute(DDL_NEW_AGENT_SOURCES.replace("agent_sources", "agent_sources_new"))
        conn.execute(DDL_LOCATIONS)

        # 2. unique sha256 → eine Zeile in agent_sources_new
        print("  2. Konsolidiere sources pro unique sha256")
        conn.execute("""
            INSERT INTO agent_sources_new
                (sha256, size_bytes, kind, status, first_seen_at, last_seen_at,
                 last_changed_at, created_at, updated_at)
            SELECT
                sha256,
                MAX(size_bytes),
                MIN(kind),  -- pragmatisch: 'context' < 'source' alphabetisch, also context gewinnt wenn beide
                CASE WHEN MAX(CASE WHEN status='active' THEN 1 ELSE 0 END) = 1
                     THEN 'active' ELSE 'deleted' END,
                MIN(first_seen_at),
                MAX(last_seen_at),
                MAX(last_changed_at),
                MIN(created_at),
                MAX(updated_at)
            FROM agent_sources
            WHERE sha256 IS NOT NULL
            GROUP BY sha256
        """)
        n = conn.execute("SELECT COUNT(*) FROM agent_sources_new").fetchone()[0]
        print(f"     → {n} unique-hash sources angelegt")

        # 3. ID-Mapping
        print("  3. Erstelle _migration_source_id_map (alt → neu)")
        conn.execute("""
            CREATE TABLE _migration_source_id_map AS
            SELECT old.id AS old_id, new.id AS new_id, old.sha256
            FROM agent_sources old
            JOIN agent_sources_new new ON new.sha256 = old.sha256
        """)
        conn.execute("CREATE INDEX idx_mig_map_old ON _migration_source_id_map(old_id)")
        conn.execute("CREATE INDEX idx_mig_map_new ON _migration_source_id_map(new_id)")
        n = conn.execute("SELECT COUNT(*) FROM _migration_source_id_map").fetchone()[0]
        print(f"     → {n} Mapping-Einträge")

        # 4. Locations befüllen (pro alte source-Zeile eine location)
        print("  4. Fülle agent_source_locations (pro alter source-Zeile eine Location)")
        conn.execute("""
            INSERT INTO agent_source_locations
                (source_id, rel_path, origin, status, first_seen_at, last_seen_at,
                 mtime, filename, folder, extension, canonical_path,
                 sp_item_id, sp_web_url, sp_modified_by, sp_content_type,
                 created_at, updated_at)
            SELECT
                m.new_id,
                old.rel_path,
                'local-folder',
                old.status,
                old.first_seen_at, old.last_seen_at,
                old.mtime,
                old.filename, old.folder, old.extension, old.canonical_path,
                old.sp_item_id, old.sp_web_url, old.sp_modified_by, old.sp_content_type,
                old.created_at, old.updated_at
            FROM agent_sources old
            JOIN _migration_source_id_map m ON m.old_id = old.id
        """)
        n = conn.execute("SELECT COUNT(*) FROM agent_source_locations").fetchone()[0]
        print(f"     → {n} Locations angelegt")

        # 5. agent_doc_markdown konsolidieren (pro neue source_id eine kanonische Zeile)
        if table_exists(conn, "agent_doc_markdown"):
            print("  5. Konsolidiere agent_doc_markdown (kanonische Zeile pro Hash)")
            # 5a. Orphan-Cleanup: file_ids die nicht (mehr) in _migration_source_id_map sind
            #     (= zeigen auf nicht-existente oder hash-lose sources — Pipeline-Reste)
            orphans = conn.execute("""
                DELETE FROM agent_doc_markdown
                WHERE file_id NOT IN (SELECT old_id FROM _migration_source_id_map)
            """).rowcount
            if orphans > 0:
                print(f"     - {orphans} orphan markdown-Zeilen entfernt (Pipeline-Reste)")

            # 5b. Strategie: pro new_id wähle die markdown-Zeile mit MAX(LENGTH(md_content))
            conn.execute("""
                CREATE TEMP TABLE _md_winner AS
                SELECT m.file_id AS old_file_id, m.rowid AS old_rowid, mp.new_id AS new_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY mp.new_id
                           ORDER BY LENGTH(COALESCE(m.md_content,'')) DESC, m.file_id ASC
                       ) AS rn
                FROM agent_doc_markdown m
                JOIN _migration_source_id_map mp ON mp.old_id = m.file_id
            """)
            # 5c. Lösche nicht-kanonische
            conn.execute("""
                DELETE FROM agent_doc_markdown
                WHERE rowid IN (SELECT old_rowid FROM _md_winner WHERE rn > 1)
            """)
            # 5d. Update file_id auf new_id (Zwei-Pass via Negativ-Range)
            conn.execute("""
                UPDATE agent_doc_markdown
                SET file_id = -1 * (SELECT new_id FROM _migration_source_id_map WHERE old_id = agent_doc_markdown.file_id)
                WHERE file_id IN (SELECT old_id FROM _migration_source_id_map)
            """)
            conn.execute("UPDATE agent_doc_markdown SET file_id = -file_id WHERE file_id < 0")
            conn.execute("DROP TABLE _md_winner")
            n = conn.execute("SELECT COUNT(*) FROM agent_doc_markdown").fetchone()[0]
            print(f"     → {n} markdown-Zeilen (eine pro Hash)")

        # 6. agent_doc_unit_offsets konsolidieren (PK: (file_id, unit_num))
        if table_exists(conn, "agent_doc_unit_offsets"):
            print("  6. Konsolidiere agent_doc_unit_offsets")
            # Orphan-Cleanup
            orphans = conn.execute("""
                DELETE FROM agent_doc_unit_offsets
                WHERE file_id NOT IN (SELECT old_id FROM _migration_source_id_map)
            """).rowcount
            if orphans > 0:
                print(f"     - {orphans} orphan offset-Zeilen entfernt")
            # PRE-DEDUPE: pro künftiger (new_id, unit_num) bleibt eine Zeile
            # (Mehrere Duplikat-Quellen mit denselben offsets würden sonst kollidieren)
            pre_dedup = conn.execute("""
                DELETE FROM agent_doc_unit_offsets
                WHERE rowid NOT IN (
                    SELECT MIN(o.rowid)
                    FROM agent_doc_unit_offsets o
                    JOIN _migration_source_id_map mp ON mp.old_id = o.file_id
                    GROUP BY mp.new_id, o.unit_num
                )
            """).rowcount
            if pre_dedup > 0:
                print(f"     - {pre_dedup} duplicate offset-Zeilen entfernt (vor Mapping)")
            # Map old file_id → new (Zwei-Pass via Negativ-Range)
            conn.execute("""
                UPDATE agent_doc_unit_offsets
                SET file_id = -1 * (
                    SELECT new_id FROM _migration_source_id_map WHERE old_id = agent_doc_unit_offsets.file_id
                )
                WHERE file_id IN (SELECT old_id FROM _migration_source_id_map)
            """)
            conn.execute("UPDATE agent_doc_unit_offsets SET file_id = -file_id WHERE file_id < 0")
            n = conn.execute("SELECT COUNT(*) FROM agent_doc_unit_offsets").fetchone()[0]
            print(f"     → {n} offset-Zeilen")

        # 7. agent_source_metadata mappen + dedupen
        if table_exists(conn, "agent_source_metadata"):
            print("  7. Mappe + dedupe agent_source_metadata")
            # Orphan-Cleanup
            orphans = conn.execute("""
                DELETE FROM agent_source_metadata
                WHERE source_id NOT IN (SELECT old_id FROM _migration_source_id_map)
            """).rowcount
            if orphans > 0:
                print(f"     - {orphans} orphan metadata-Zeilen entfernt")
            # PRE-DEDUPE: pro künftiger (new_id, key, source_of_truth) bleibt die NEUESTE
            # (UNIQUE-Index würde sonst beim Mapping kollidieren)
            pre_dedup = conn.execute("""
                DELETE FROM agent_source_metadata
                WHERE rowid NOT IN (
                    SELECT MIN(m.rowid)
                    FROM agent_source_metadata m
                    JOIN _migration_source_id_map mp ON mp.old_id = m.source_id
                    GROUP BY mp.new_id, m.key, m.source_of_truth
                    HAVING m.updated_at = MAX(m.updated_at)
                )
            """).rowcount
            if pre_dedup > 0:
                print(f"     - {pre_dedup} duplicate metadata-Zeilen entfernt (vor Mapping)")
            # Zwei-Pass via Negativ-Range gegen UNIQUE-Konflikt
            conn.execute("""
                UPDATE agent_source_metadata
                SET source_id = -1 * (SELECT new_id FROM _migration_source_id_map WHERE old_id = agent_source_metadata.source_id)
                WHERE source_id IN (SELECT old_id FROM _migration_source_id_map)
            """)
            conn.execute("UPDATE agent_source_metadata SET source_id = -source_id WHERE source_id < 0")
            n = conn.execute("SELECT COUNT(*) FROM agent_source_metadata").fetchone()[0]
            print(f"     → {n} metadata-Zeilen")

        # 8. agent_source_relations droppen (Duplikate sind jetzt implizit)
        if table_exists(conn, "agent_source_relations"):
            print("  8. DROP agent_source_relations (Duplikate sind jetzt strukturell)")
            n = conn.execute("SELECT COUNT(*) FROM agent_source_relations").fetchone()[0]
            conn.execute("DROP TABLE agent_source_relations")
            print(f"     → {n} Relations entfernt")

        # 9. Umbenennen: alt → *_pre_migration, neu → in Position
        print("  9. RENAME agent_sources → agent_sources_pre_migration, _new → agent_sources")
        # Indizes auf der alten Tabelle erst löschen (Index-Namen-Konflikt)
        for idx in (
            "idx_agent_sources_status", "idx_agent_sources_folder",
            "idx_agent_sources_extension", "idx_agent_sources_sha256",
            "idx_agent_sources_kind", "idx_agent_sources_canonical_path",
        ):
            conn.execute(f"DROP INDEX IF EXISTS {idx}")
        conn.execute("ALTER TABLE agent_sources RENAME TO agent_sources_pre_migration")
        conn.execute("ALTER TABLE agent_sources_new RENAME TO agent_sources")
        # Indizes neu anlegen für die neue agent_sources
        for sql in DDL_NEW_AGENT_SOURCES_INDEXES:
            conn.execute(sql)
        # Indizes für agent_source_locations
        for sql in DDL_LOCATIONS_INDEXES:
            conn.execute(sql)

        # 10. agent_pdf_inventory rebuild — Inventory wird in der Migration
        #     nicht direkt remapped (eigene Welt). Nach Hash-Konsolidierung
        #     zeigen alte Inventory-IDs auf nicht-existente Sources.
        #     Lösung: DELETE+REBUILD für alle kinds, die migriert wurden.
        if table_exists(conn, "agent_pdf_inventory"):
            print("  10. Rebuild agent_pdf_inventory (clean slate für Hash-Welt)")
            n_old = conn.execute(
                "SELECT COUNT(*) FROM agent_pdf_inventory"
            ).fetchone()[0]
            conn.execute("DELETE FROM agent_pdf_inventory")
            # Re-insert: pro PDF-Source mit aktiver PDF-Location eine Zeile
            rows = conn.execute("""
                SELECT s.id, s.sha256, s.size_bytes, s.kind,
                       (SELECT l.rel_path FROM agent_source_locations l
                        WHERE l.source_id = s.id AND l.status='active'
                          AND LOWER(l.extension) = 'pdf'
                        ORDER BY l.id LIMIT 1) AS rel_path,
                       (SELECT l.filename FROM agent_source_locations l
                        WHERE l.source_id = s.id AND l.status='active'
                          AND LOWER(l.extension) = 'pdf'
                        ORDER BY l.id LIMIT 1) AS filename,
                       (SELECT l.folder FROM agent_source_locations l
                        WHERE l.source_id = s.id AND l.status='active'
                          AND LOWER(l.extension) = 'pdf'
                        ORDER BY l.id LIMIT 1) AS folder
                FROM agent_sources s
                WHERE s.status = 'active'
                  AND EXISTS (
                    SELECT 1 FROM agent_source_locations l
                    WHERE l.source_id = s.id AND l.status='active'
                      AND LOWER(l.extension) = 'pdf'
                  )
            """).fetchall()
            n_inserted = 0
            for r in rows:
                rel = r["rel_path"] or ""
                role_prefix = "context" if r["kind"] == "context" else "sources"
                full_rel = rel if rel.startswith(f"{role_prefix}/") else f"{role_prefix}/{rel}"
                file_name = r["filename"] or rel.rsplit("/", 1)[-1]
                gewerk = (r["folder"] or "").split("/")[0] if r["folder"] else None
                try:
                    conn.execute(
                        "INSERT INTO agent_pdf_inventory "
                        "(id, rel_path, file_name, file_name_norm, gewerk, "
                        " size_bytes, sha256, kind) "
                        "VALUES (?, ?, ?, LOWER(TRIM(?)), ?, ?, ?, ?)",
                        (r["id"], full_rel, file_name, file_name, gewerk,
                         r["size_bytes"], r["sha256"], r["kind"]),
                    )
                    n_inserted += 1
                except Exception:
                    continue  # rel_path-UNIQUE-Konflikt (theoretisch)
            print(f"     → {n_inserted} PDF-Einträge (vorher: {n_old})")

        if dry_run:
            print("\n  [DRY-RUN] ROLLBACK — keine Änderungen geschrieben")
            conn.execute("ROLLBACK")
        else:
            conn.execute("COMMIT")
            print("\n  ✓ datastore.db Migration committed")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"\n  ✗ ERROR: {e}")
        print("    ROLLBACK durchgeführt — datastore.db unverändert")
        raise
    finally:
        conn.close()


def migrate_workspace(ws_path: Path, ds_path: Path, dry_run: bool) -> None:
    """Biegt source_id/file_id-Referenzen in workspace.db auf neue Hash-IDs um."""
    conn = sqlite3.connect(ws_path, isolation_level=None)
    conn.execute(f"ATTACH DATABASE '{ds_path}' AS ds")

    if not table_exists(conn, "_migration_source_id_map", schema="ds"):
        print("  ✗ ds._migration_source_id_map nicht gefunden — wurde datastore migriert?")
        conn.close()
        return

    tables = find_source_id_columns(conn)
    if not tables:
        print("  (keine source_id/file_id-Spalten gefunden)")
        conn.close()
        return

    print(f"  Gefundene Tabellen: {len(tables)}")
    try:
        conn.execute("BEGIN")
        for tbl, cols in tables:
            for col in cols:
                # Wie viele Zeilen werden gemappt?
                cnt = conn.execute(f"""
                    SELECT COUNT(*) FROM {tbl}
                    WHERE {col} IN (SELECT old_id FROM ds._migration_source_id_map)
                """).fetchone()[0]
                if cnt == 0:
                    print(f"    {tbl}.{col}: 0 (kein Mapping nötig)")
                    continue

                # Pre-Dedupe: wenn Spalte UNIQUE/PK ist, würde Mapping
                # mehrerer alter IDs auf dieselbe neue ID einen Konflikt
                # auslösen. Behalte pro new_id die Zeile mit kleinstem rowid.
                is_unique = column_is_unique(conn, tbl, col)
                pre = 0
                if is_unique:
                    pre = conn.execute(f"""
                        DELETE FROM {tbl}
                        WHERE rowid NOT IN (
                            SELECT MIN(t.rowid)
                            FROM {tbl} t
                            JOIN ds._migration_source_id_map mp ON mp.old_id = t.{col}
                            GROUP BY mp.new_id
                        )
                        AND {col} IN (SELECT old_id FROM ds._migration_source_id_map)
                    """).rowcount

                # Zwei-Pass-Mapping via Negativ-Range (gegen mid-update Konflikte
                # zwischen alter und neuer ID-Welt)
                conn.execute(f"""
                    UPDATE {tbl}
                    SET {col} = -1 * (
                        SELECT new_id FROM ds._migration_source_id_map
                        WHERE old_id = {tbl}.{col}
                    )
                    WHERE {col} IN (SELECT old_id FROM ds._migration_source_id_map)
                """)
                conn.execute(f"""
                    UPDATE {tbl}
                    SET {col} = -{col}
                    WHERE {col} < 0
                """)
                if pre > 0:
                    print(f"    {tbl}.{col}: {cnt} Zeilen gemappt  (pre-dedupe: -{pre} Duplikate)")
                else:
                    print(f"    {tbl}.{col}: {cnt} Zeilen gemappt")

        if dry_run:
            print("\n  [DRY-RUN] ROLLBACK — keine Änderungen geschrieben")
            conn.execute("ROLLBACK")
        else:
            conn.execute("COMMIT")
            print("\n  ✓ workspace.db Migration committed")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"\n  ✗ ERROR: {e}")
        raise
    finally:
        conn.close()


# -------------------------------------------------------------------------
# Verify
# -------------------------------------------------------------------------

def cmd_verify(project_path: Path) -> int:
    ds = project_path / "datastore.db"
    ws = project_path / "workspace.db"
    if not ds.exists():
        print(f"ERROR: {ds} nicht gefunden")
        return 1

    banner(f"Verify: {project_path.name}")
    ok = True

    with sqlite3.connect(ds) as conn:
        section("datastore.db — neue Struktur vorhanden?")
        for tbl in ("agent_sources", "agent_source_locations", "agent_sources_pre_migration", "_migration_source_id_map"):
            exists = table_exists(conn, tbl)
            print(f"  {'✓' if exists else '✗'} {tbl}")
            if not exists and tbl in ("agent_sources", "agent_source_locations"):
                ok = False

        section("datastore.db — Konsistenz-Checks")
        # 1. sha256 ist UNIQUE in agent_sources
        r = conn.execute(
            "SELECT COUNT(*) - COUNT(DISTINCT sha256) FROM agent_sources"
        ).fetchone()[0]
        print(f"  {'✓' if r == 0 else '✗'} sha256-Duplikate in agent_sources: {r}")
        if r != 0:
            ok = False

        # 2. Jede location hat existierende source_id
        r = conn.execute("""
            SELECT COUNT(*) FROM agent_source_locations l
            WHERE NOT EXISTS (SELECT 1 FROM agent_sources s WHERE s.id = l.source_id)
        """).fetchone()[0]
        print(f"  {'✓' if r == 0 else '✗'} Orphan locations: {r}")
        if r != 0:
            ok = False

        # 3. agent_doc_markdown.file_id zeigt auf agent_sources.id
        if table_exists(conn, "agent_doc_markdown"):
            r = conn.execute("""
                SELECT COUNT(*) FROM agent_doc_markdown m
                WHERE NOT EXISTS (SELECT 1 FROM agent_sources s WHERE s.id = m.file_id)
            """).fetchone()[0]
            print(f"  {'✓' if r == 0 else '✗'} Orphan markdown-Zeilen: {r}")
            if r != 0:
                ok = False

            # 4. pro file_id genau eine markdown-Zeile (PK)
            r = conn.execute("""
                SELECT COUNT(*) - COUNT(DISTINCT file_id) FROM agent_doc_markdown
            """).fetchone()[0]
            print(f"  {'✓' if r == 0 else '✗'} markdown file_id Duplikate: {r}")
            if r != 0:
                ok = False

        # 5. agent_source_relations gedroppt?
        gone = not table_exists(conn, "agent_source_relations")
        print(f"  {'✓' if gone else '✗'} agent_source_relations gedroppt: {gone}")

        section("datastore.db — Zeilen-Counts nach Migration")
        for tbl in ("agent_sources", "agent_source_locations", "agent_doc_markdown",
                    "agent_doc_unit_offsets", "agent_source_metadata",
                    "agent_sources_pre_migration"):
            if table_exists(conn, tbl):
                n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                print(f"  {tbl:40s} {n}")

    if ws.exists():
        with sqlite3.connect(ws) as conn:
            conn.execute(f"ATTACH DATABASE '{ds}' AS ds")
            section("workspace.db — orphan-Check pro Tabelle")
            print("  (Orphans differenziert in 'pre-existing' vs 'migration-induced')")
            tables = find_source_id_columns(conn)
            pre_existing_total = 0
            for tbl, cols in tables:
                for col in cols:
                    # Total orphans
                    r_total = conn.execute(f"""
                        SELECT COUNT(*) FROM {tbl}
                        WHERE {col} IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM ds.agent_sources s WHERE s.id = {tbl}.{col})
                    """).fetchone()[0]
                    # Davon: pre-existing (auch nicht in pre_migration)
                    r_pre = conn.execute(f"""
                        SELECT COUNT(*) FROM {tbl}
                        WHERE {col} IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM ds.agent_sources s WHERE s.id = {tbl}.{col})
                          AND NOT EXISTS (SELECT 1 FROM ds.agent_sources_pre_migration p WHERE p.id = {tbl}.{col})
                    """).fetchone()[0]
                    r_induced = r_total - r_pre
                    if r_total == 0:
                        print(f"  ✓ {tbl}.{col}: 0 orphans")
                    elif r_induced == 0:
                        print(f"  ⚠ {tbl}.{col}: {r_total} orphans (alle pre-existing, harmlos)")
                        pre_existing_total += r_total
                    else:
                        print(f"  ✗ {tbl}.{col}: {r_total} orphans  ({r_induced} migration-induced, {r_pre} pre-existing)")
                        ok = False
            if pre_existing_total > 0:
                print(f"\n  → Insgesamt {pre_existing_total} pre-existing orphans (von vor der Migration, kein Schaden)")

    section("Verify-Ergebnis")
    print("  ✓ ALLE CHECKS OK" if ok else "  ✗ FEHLER GEFUNDEN")
    return 0 if ok else 3


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_in = sub.add_parser("inspect", help="Vor-Analyse")
    p_in.add_argument("project_path", type=Path)

    p_mig = sub.add_parser("migrate", help="Migration durchführen")
    p_mig.add_argument("project_path", type=Path)
    p_mig.add_argument("--dry-run", action="store_true")

    p_ver = sub.add_parser("verify", help="Validierung nach Migration")
    p_ver.add_argument("project_path", type=Path)

    args = ap.parse_args(argv)
    pp = args.project_path.expanduser().resolve()

    if args.cmd == "inspect":
        return cmd_inspect(pp)
    if args.cmd == "migrate":
        return cmd_migrate(pp, dry_run=args.dry_run)
    if args.cmd == "verify":
        return cmd_verify(pp)
    return 1


if __name__ == "__main__":
    sys.exit(main())
