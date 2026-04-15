"""CRUD-Operationen für die sources-Tabelle sowie Hilfsfunktionen für source_folders."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .config import settings
from .db import connect


# ---------------------------------------------------------------------------
# Typisierter Config-Datentyp für SharePoint-Bibliotheken
# ---------------------------------------------------------------------------

def make_sharepoint_config(
    site_url: str,
    library_name: str,
    drive_id: str | None = None,
) -> str:
    """Erstellt den config_json-String für eine SharePoint-Bibliotheksquelle."""
    return json.dumps(
        {
            "site_url": site_url.rstrip("/"),
            "library_name": library_name,
            "drive_id": drive_id,  # wird beim ersten Sync automatisch gesetzt
        },
        ensure_ascii=False,
    )


def parse_config(source: dict[str, Any]) -> dict[str, Any]:
    """Parst config_json und gibt es als dict zurück."""
    return json.loads(source.get("config_json") or "{}")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_source(
    project_id: int,
    name: str,
    site_url: str,
    library_name: str,
    db_path=None,
) -> dict[str, Any]:
    """Legt eine neue SharePoint-Bibliotheksquelle an."""
    config = make_sharepoint_config(site_url, library_name)
    conn = connect(db_path or settings.db_path)
    try:
        cur = conn.execute(
            "INSERT INTO sources (project_id, name, source_type, config_json) "
            "VALUES (?, ?, 'sharepoint_library', ?)",
            (project_id, name, config),
        )
        conn.commit()
        return get_source(cur.lastrowid, conn=conn)
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            f"Quelle '{name}' existiert bereits in Projekt {project_id}."
        ) from exc
    finally:
        conn.close()


def get_source(source_id: int, conn: sqlite3.Connection | None = None, db_path=None) -> dict[str, Any]:
    """Gibt eine Quelle als dict zurück. Wirft KeyError wenn nicht gefunden."""
    _owned = conn is None
    if _owned:
        conn = connect(db_path or settings.db_path)
    try:
        row = conn.execute(
            "SELECT id, project_id, name, source_type, config_json, status, "
            "last_synced_at, created_at, updated_at FROM sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Quelle ID {source_id} nicht gefunden.")
        return dict(row)
    finally:
        if _owned:
            conn.close()


def list_sources(project_id: int, db_path=None) -> list[dict[str, Any]]:
    """Alle aktiven Quellen eines Projekts."""
    conn = connect(db_path or settings.db_path)
    try:
        rows = conn.execute(
            "SELECT id, project_id, name, source_type, config_json, status, "
            "last_synced_at, created_at, updated_at "
            "FROM sources WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_source_status(source_id: int, status: str, db_path=None) -> None:
    """Setzt den Status einer Quelle (active | paused | error)."""
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute(
            "UPDATE sources SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, source_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_last_synced(source_id: int, db_path=None) -> None:
    """Setzt last_synced_at auf jetzt."""
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute(
            "UPDATE sources SET last_synced_at = datetime('now'), "
            "updated_at = datetime('now') WHERE id = ?",
            (source_id,),
        )
        conn.commit()
    finally:
        conn.close()


def update_drive_id(source_id: int, drive_id: str, db_path=None) -> None:
    """Schreibt die aufgelöste drive_id in config_json zurück."""
    conn = connect(db_path or settings.db_path)
    try:
        row = conn.execute(
            "SELECT config_json FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Quelle ID {source_id} nicht gefunden.")
        cfg = json.loads(row["config_json"])
        cfg["drive_id"] = drive_id
        conn.execute(
            "UPDATE sources SET config_json = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(cfg, ensure_ascii=False), source_id),
        )
        conn.commit()
    finally:
        conn.close()


def count_documents(source_id: int, db_path=None) -> int:
    """Anzahl der Dokumente in einer Quelle."""
    conn = connect(db_path or settings.db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        return row[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Ordnerstruktur
# ---------------------------------------------------------------------------

def list_folders(source_id: int, parent_id: int | None = None, db_path=None) -> list[dict[str, Any]]:
    """Gibt Unterordner eines Ordners zurück. parent_id=None liefert Root-Ordner."""
    conn = connect(db_path or settings.db_path)
    try:
        if parent_id is None:
            rows = conn.execute(
                "SELECT id, source_id, parent_id, sp_item_id, name, sp_path, sp_web_url "
                "FROM source_folders WHERE source_id = ? AND parent_id IS NULL ORDER BY name",
                (source_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, source_id, parent_id, sp_item_id, name, sp_path, sp_web_url "
                "FROM source_folders WHERE source_id = ? AND parent_id = ? ORDER BY name",
                (source_id, parent_id),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_folders(source_id: int, db_path=None) -> list[dict[str, Any]]:
    """Gibt alle Ordner einer Quelle zurück (für Baumaufbau im UI)."""
    conn = connect(db_path or settings.db_path)
    try:
        rows = conn.execute(
            "SELECT id, source_id, parent_id, sp_item_id, name, sp_path, sp_web_url "
            "FROM source_folders WHERE source_id = ? ORDER BY sp_path",
            (source_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
