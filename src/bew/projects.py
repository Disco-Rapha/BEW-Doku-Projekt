"""CRUD-Operationen für die projects-Tabelle."""

from __future__ import annotations

import sqlite3
from typing import Any

from .config import settings
from .db import connect


def create_project(
    name: str,
    description: str | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Legt ein neues Projekt an. Wirft ValueError wenn der Name bereits existiert."""
    conn = connect(db_path or settings.db_path)
    try:
        cur = conn.execute(
            "INSERT INTO projects (name, description) VALUES (?, ?)",
            (name, description),
        )
        conn.commit()
        project_id = cur.lastrowid
        return get_project(project_id, conn=conn)
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"Projekt '{name}' existiert bereits.") from exc
    finally:
        conn.close()


def get_project(project_id: int, conn: sqlite3.Connection | None = None, db_path=None) -> dict[str, Any]:
    """Gibt ein Projekt als dict zurück. Wirft KeyError wenn nicht gefunden."""
    _owned = conn is None
    if _owned:
        conn = connect(db_path or settings.db_path)
    try:
        row = conn.execute(
            "SELECT id, name, description, status, created_at, updated_at "
            "FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Projekt ID {project_id} nicht gefunden.")
        return dict(row)
    finally:
        if _owned:
            conn.close()


def list_projects(include_archived: bool = False, db_path=None) -> list[dict[str, Any]]:
    """Gibt alle Projekte zurück. Ohne archived=True nur status='active'."""
    conn = connect(db_path or settings.db_path)
    try:
        if include_archived:
            rows = conn.execute(
                "SELECT id, name, description, status, created_at, updated_at "
                "FROM projects ORDER BY name"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, description, status, created_at, updated_at "
                "FROM projects WHERE status = 'active' ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def archive_project(project_id: int, db_path=None) -> None:
    """Setzt status='archived' für ein Projekt."""
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute(
            "UPDATE projects SET status = 'archived', updated_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        conn.commit()
    finally:
        conn.close()


def count_documents(project_id: int, db_path=None) -> int:
    """Anzahl der Dokumente in einem Projekt."""
    conn = connect(db_path or settings.db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return row[0]
    finally:
        conn.close()
