"""CRUD für chat_threads und chat_messages (Migration 004).

Funktionsumfang:
  - Thread anlegen / lesen / listen / archivieren / löschen
  - Foundry-Thread-ID nachträglich setzen (wird erst beim ersten Foundry-Call bekannt)
  - Messages anhängen und listen
  - Tool-Calls und -Ergebnisse als JSON persistieren

Konventionen analog zu `projects.py` und `sources.py`:
  - JSON wird als String gespeichert, auf Lese-Seite wieder geparst
  - `datetime('now')` via SQLite, keine Python-Zeitstempel
  - Optionaler `db_path`-Parameter für Tests
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Literal

from ..config import settings
from ..db import connect


Role = Literal["user", "assistant", "tool", "system"]


# ----------------------------------------------------------------
# Threads
# ----------------------------------------------------------------


def create_thread(
    title: str = "Neuer Chat",
    project_id: int | None = None,
    model_used: str | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Legt einen neuen Chat-Thread an.

    foundry_thread_id bleibt zunächst NULL — wird beim ersten Agent-Call
    via `set_foundry_thread_id()` nachgetragen.
    """
    model = model_used or settings.foundry_model_deployment
    conn = connect(db_path or settings.db_path)
    try:
        cur = conn.execute(
            "INSERT INTO chat_threads (title, project_id, model_used) "
            "VALUES (?, ?, ?)",
            (title, project_id, model),
        )
        conn.commit()
        return get_thread(cur.lastrowid, conn=conn)
    finally:
        conn.close()


def get_thread(
    thread_id: int,
    conn: sqlite3.Connection | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Gibt einen Thread als dict zurück. Wirft KeyError wenn nicht gefunden."""
    _owned = conn is None
    if _owned:
        conn = connect(db_path or settings.db_path)
    try:
        row = conn.execute(
            "SELECT id, title, foundry_thread_id, project_id, model_used, "
            "       status, created_at, updated_at "
            "FROM chat_threads WHERE id = ?",
            (thread_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Chat-Thread ID {thread_id} nicht gefunden.")
        return dict(row)
    finally:
        if _owned:
            conn.close()


def get_thread_by_foundry_id(
    foundry_thread_id: str,
    db_path=None,
) -> dict[str, Any] | None:
    """Sucht einen Thread anhand der Foundry-Thread-ID. None wenn keiner existiert."""
    conn = connect(db_path or settings.db_path)
    try:
        row = conn.execute(
            "SELECT id, title, foundry_thread_id, project_id, model_used, "
            "       status, created_at, updated_at "
            "FROM chat_threads WHERE foundry_thread_id = ?",
            (foundry_thread_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_threads(
    include_archived: bool = False,
    project_id: int | None = None,
    limit: int = 100,
    db_path=None,
) -> list[dict[str, Any]]:
    """Listet Threads, neueste zuerst.

    Args:
        include_archived: wenn False, nur status='active'.
        project_id: wenn gesetzt, nur Threads für dieses Projekt.
        limit: maximale Anzahl (Default 100).
    """
    where: list[str] = []
    params: list[Any] = []
    if not include_archived:
        where.append("status = 'active'")
    if project_id is not None:
        where.append("project_id = ?")
        params.append(project_id)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    conn = connect(db_path or settings.db_path)
    try:
        rows = conn.execute(
            f"SELECT id, title, foundry_thread_id, project_id, model_used, "
            f"       status, created_at, updated_at "
            f"FROM chat_threads {where_sql} "
            f"ORDER BY updated_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_foundry_thread_id(
    thread_id: int,
    foundry_thread_id: str,
    db_path=None,
) -> None:
    """Trägt die Foundry-Thread-ID nach dem ersten Agent-Call nach."""
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute(
            "UPDATE chat_threads "
            "SET foundry_thread_id = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (foundry_thread_id, thread_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_thread_title(thread_id: int, title: str, db_path=None) -> None:
    """Aktualisiert den Thread-Titel (z.B. Auto-Titel nach erster User-Nachricht)."""
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute(
            "UPDATE chat_threads "
            "SET title = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (title, thread_id),
        )
        conn.commit()
    finally:
        conn.close()


def archive_thread(thread_id: int, db_path=None) -> None:
    """Setzt status='archived' (weicher Delete — Messages bleiben erhalten)."""
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute(
            "UPDATE chat_threads "
            "SET status = 'archived', updated_at = datetime('now') "
            "WHERE id = ?",
            (thread_id,),
        )
        conn.commit()
    finally:
        conn.close()


def delete_thread(thread_id: int, db_path=None) -> None:
    """Löscht einen Thread komplett (inkl. aller Messages via CASCADE).

    Achtung: Der zugehörige Foundry-Thread wird NICHT gelöscht — das müsste
    separat über den AIProjectClient erfolgen.
    """
    conn = connect(db_path or settings.db_path)
    try:
        conn.execute("DELETE FROM chat_threads WHERE id = ?", (thread_id,))
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------
# Messages
# ----------------------------------------------------------------


def append_message(
    thread_id: int,
    role: Role,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_results: dict[str, Any] | list[dict[str, Any]] | None = None,
    foundry_message_id: str | None = None,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
    db_path=None,
) -> dict[str, Any]:
    """Hängt eine Nachricht an einen Thread an.

    Eine Assistant-Nachricht kann reinen Text, reine Tool-Calls oder beides tragen.
    Eine Tool-Nachricht trägt typisch nur `tool_results`.

    Returns:
        Das geschriebene Message-Dict inkl. id und created_at.
    """
    if role not in ("user", "assistant", "tool", "system"):
        raise ValueError(f"Ungültige Rolle: {role!r}")

    tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
    tool_results_json = (
        json.dumps(tool_results, ensure_ascii=False) if tool_results is not None else None
    )

    conn = connect(db_path or settings.db_path)
    try:
        cur = conn.execute(
            "INSERT INTO chat_messages "
            "  (thread_id, role, content, tool_calls_json, tool_results_json, "
            "   foundry_message_id, tokens_input, tokens_output) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                thread_id,
                role,
                content,
                tool_calls_json,
                tool_results_json,
                foundry_message_id,
                tokens_input,
                tokens_output,
            ),
        )
        # updated_at des Threads mitziehen, damit list_threads korrekt sortiert
        conn.execute(
            "UPDATE chat_threads SET updated_at = datetime('now') WHERE id = ?",
            (thread_id,),
        )
        conn.commit()
        return _get_message(cur.lastrowid, conn=conn)
    finally:
        conn.close()


def list_messages(
    thread_id: int,
    limit: int | None = None,
    db_path=None,
) -> list[dict[str, Any]]:
    """Gibt alle Messages eines Threads chronologisch zurück.

    JSON-Felder (tool_calls, tool_results) werden geparst zurückgegeben.
    """
    conn = connect(db_path or settings.db_path)
    try:
        sql = (
            "SELECT id, thread_id, role, content, tool_calls_json, "
            "       tool_results_json, foundry_message_id, "
            "       tokens_input, tokens_output, created_at "
            "FROM chat_messages WHERE thread_id = ? "
            "ORDER BY id ASC"
        )
        params: tuple[Any, ...] = (thread_id,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (thread_id, limit)
        rows = conn.execute(sql, params).fetchall()
        return [_hydrate_message(dict(r)) for r in rows]
    finally:
        conn.close()


def _get_message(message_id: int, conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, thread_id, role, content, tool_calls_json, "
        "       tool_results_json, foundry_message_id, "
        "       tokens_input, tokens_output, created_at "
        "FROM chat_messages WHERE id = ?",
        (message_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Message ID {message_id} nicht gefunden.")
    return _hydrate_message(dict(row))


def _hydrate_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Parst die JSON-Strings zurück zu Python-Strukturen."""
    tc = msg.pop("tool_calls_json", None)
    tr = msg.pop("tool_results_json", None)
    msg["tool_calls"] = json.loads(tc) if tc else None
    msg["tool_results"] = json.loads(tr) if tr else None
    return msg
