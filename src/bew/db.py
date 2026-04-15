"""SQLite-Verbindung und Migrations-Runner.

Einfacher, versionsbasierter Migrations-Mechanismus:
- Migrationen liegen als `migrations/NNN_name.sql` vor.
- Die DB führt eine Tabelle `schema_version` mit angewendeten Versionen.
- `init_db()` wendet alle noch nicht angewendeten Migrationen an.
- Bestehende Migrationen sind immutable; Änderungen gehen in eine neue Datei.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .config import settings


SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

MIGRATION_FILENAME_RE = re.compile(r"^(\d+)_.+\.sql$")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Öffnet eine Verbindung mit Foreign Keys aktiviert."""
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _discover_migrations(migrations_dir: Path) -> list[tuple[int, Path]]:
    items: list[tuple[int, Path]] = []
    for p in sorted(migrations_dir.glob("*.sql")):
        m = MIGRATION_FILENAME_RE.match(p.name)
        if not m:
            continue
        items.append((int(m.group(1)), p))
    items.sort(key=lambda t: t[0])
    return items


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    cur = conn.execute("SELECT version FROM schema_version;")
    return {row[0] for row in cur.fetchall()}


def init_db(db_path: Path | None = None) -> dict:
    """Legt DB an und wendet alle ausstehenden Migrationen an.

    Returns:
        Dict mit 'db_path', 'applied' (Liste neu angewendeter Versionen),
        'current_version'.
    """
    path = db_path or settings.db_path
    conn = connect(path)
    try:
        conn.executescript(SCHEMA_VERSION_DDL)
        conn.commit()

        applied = _applied_versions(conn)
        newly_applied: list[int] = []

        for version, file_path in _discover_migrations(settings.migrations_dir):
            if version in applied:
                continue
            sql = file_path.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?);", (version,)
            )
            conn.commit()
            newly_applied.append(version)

        cur = conn.execute("SELECT MAX(version) FROM schema_version;")
        current = cur.fetchone()[0] or 0

        return {
            "db_path": str(path),
            "applied": newly_applied,
            "current_version": current,
        }
    finally:
        conn.close()


def status(db_path: Path | None = None) -> dict:
    """Gibt Schema-Version und Tabellenliste zurück."""
    path = db_path or settings.db_path
    if not path.exists():
        return {"db_path": str(path), "exists": False}
    conn = connect(path)
    try:
        version_row = conn.execute(
            "SELECT MAX(version) FROM schema_version;"
        ).fetchone()
        version = version_row[0] if version_row else None
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name;"
            ).fetchall()
        ]
        return {
            "db_path": str(path),
            "exists": True,
            "current_version": version,
            "tables": tables,
        }
    finally:
        conn.close()
