"""FastAPI-Anwendung: REST-API + WebSocket + statisches Frontend."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..agent.core import get_agent_service
from ..chat import repo as chat_repo
from ..config import settings
from ..db import connect
from ..projects import list_projects, create_project, archive_project, count_documents as proj_doc_count
from ..sources import list_sources, create_source, get_source, parse_config, count_documents as src_doc_count
from .agent import stream_response  # Alt-Agent (Claude) — Fallback fuer Phase-0-Kompatibilitaet

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="BEW Doku Projekt", docs_url="/api/docs")

# Statische Dateien
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Haupt-UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# REST-API: Projekte
# ---------------------------------------------------------------------------

@app.get("/api/projects")
async def api_list_projects():
    projects = list_projects()
    return [
        {**p, "document_count": proj_doc_count(p["id"])}
        for p in projects
    ]


@app.post("/api/projects")
async def api_create_project(body: dict):
    name = body.get("name", "").strip()
    description = body.get("description", "").strip() or None
    if not name:
        return {"error": "Name fehlt"}, 400
    try:
        p = create_project(name, description)
        return {**p, "document_count": 0}
    except ValueError as exc:
        return {"error": str(exc)}


@app.delete("/api/projects/{project_id}")
async def api_archive_project(project_id: int):
    archive_project(project_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# REST-API: Quellen
# ---------------------------------------------------------------------------

@app.get("/api/projects/{project_id}/sources")
async def api_list_sources(project_id: int):
    sources = list_sources(project_id)
    return [
        {**s, "document_count": src_doc_count(s["id"]), "config": parse_config(s)}
        for s in sources
    ]


@app.post("/api/projects/{project_id}/sources")
async def api_create_source(project_id: int, body: dict):
    name = body.get("name", "").strip()
    site_url = body.get("site_url", "").strip()
    library = body.get("library_name", "Dokumente").strip()
    if not name or not site_url:
        return {"error": "name und site_url sind erforderlich"}
    try:
        s = create_source(project_id, name, site_url, library)
        return {**s, "document_count": 0, "config": parse_config(s)}
    except ValueError as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# REST-API: Snapshot + Delta Sync
# ---------------------------------------------------------------------------

# Laufende Sync-Jobs: source_id → {"status": "running"|"done"|"error", "result": ...}
_sync_jobs: dict[int, dict[str, Any]] = {}


def _run_snapshot_bg(source_id: int) -> None:
    """Snapshot im Hintergrund-Thread."""
    from ..sharepoint.auth import MSALTokenManager
    from ..sharepoint.graph import GraphClient
    from ..sharepoint.sync import SharePointSyncer, SyncError

    _sync_jobs[source_id] = {"status": "running", "mode": "snapshot"}
    conn = connect()
    try:
        source = get_source(source_id)
        mgr = MSALTokenManager(settings.msal_tenant_id, settings.msal_client_id)
        graph = GraphClient(mgr)
        syncer = SharePointSyncer(conn, graph, source)
        result = syncer.run_snapshot()
        _sync_jobs[source_id] = {"status": "done", "mode": "snapshot", "result": asdict(result)}
    except Exception as exc:
        logger.exception("Snapshot Fehler source %d", source_id)
        _sync_jobs[source_id] = {"status": "error", "mode": "snapshot", "error": str(exc)}
    finally:
        conn.close()


def _run_delta_bg(source_id: int) -> None:
    """Delta-Sync im Hintergrund-Thread."""
    from ..sharepoint.auth import MSALTokenManager
    from ..sharepoint.graph import GraphClient
    from ..sharepoint.sync import SharePointSyncer, SyncError

    _sync_jobs[source_id] = {"status": "running", "mode": "delta"}
    conn = connect()
    try:
        source = get_source(source_id)
        mgr = MSALTokenManager(settings.msal_tenant_id, settings.msal_client_id)
        graph = GraphClient(mgr)
        syncer = SharePointSyncer(conn, graph, source)
        result = syncer.run_delta()
        _sync_jobs[source_id] = {"status": "done", "mode": "delta", "result": asdict(result)}
    except Exception as exc:
        logger.exception("Delta Fehler source %d", source_id)
        _sync_jobs[source_id] = {"status": "error", "mode": "delta", "error": str(exc)}
    finally:
        conn.close()


@app.post("/api/sources/{source_id}/snapshot")
async def api_snapshot(source_id: int):
    """Startet einen Metadata-Snapshot (Hintergrund). Kein Dateidownload."""
    if not settings.msal_tenant_id or not settings.msal_client_id:
        return {"error": "MSAL_TENANT_ID / MSAL_CLIENT_ID nicht konfiguriert."}
    job = _sync_jobs.get(source_id, {})
    if job.get("status") == "running":
        return {"status": "already_running", "mode": job.get("mode")}
    threading.Thread(target=_run_snapshot_bg, args=(source_id,), daemon=True).start()
    return {"status": "gestartet", "mode": "snapshot", "source_id": source_id}


@app.post("/api/sources/{source_id}/delta")
async def api_delta(source_id: int):
    """Startet einen Delta-Sync (Hintergrund). Nur Änderungen seit letztem Snapshot."""
    if not settings.msal_tenant_id or not settings.msal_client_id:
        return {"error": "MSAL_TENANT_ID / MSAL_CLIENT_ID nicht konfiguriert."}
    job = _sync_jobs.get(source_id, {})
    if job.get("status") == "running":
        return {"status": "already_running", "mode": job.get("mode")}
    threading.Thread(target=_run_delta_bg, args=(source_id,), daemon=True).start()
    return {"status": "gestartet", "mode": "delta", "source_id": source_id}


@app.get("/api/sources/{source_id}/sync-status")
async def api_sync_status(source_id: int):
    """Aktueller Status eines laufenden oder abgeschlossenen Sync-Jobs."""
    return _sync_jobs.get(source_id, {"status": "idle"})


@app.post("/api/sources/{source_id}/import-json")
async def api_import_json(source_id: int, file: UploadFile = File(...)):
    """Importiert einen SharePoint REST-API JSON-Export (Hintergrund-Thread).

    Akzeptiert eine JSON-Datei die mit dem Browser-Export-Script erstellt wurde.
    """
    job = _sync_jobs.get(source_id, {})
    if job.get("status") == "running":
        return {"status": "already_running", "mode": job.get("mode")}

    content = await file.read()

    def _run(raw: bytes) -> None:
        from ..sharepoint.import_json import SharePointJSONImporter
        _sync_jobs[source_id] = {"status": "running", "mode": "import"}
        # Temporäre Datei anlegen
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        conn = connect()
        try:
            importer = SharePointJSONImporter(conn, source_id)
            result = importer.run(tmp_path)
            _sync_jobs[source_id] = {
                "status": "done",
                "mode": "import",
                "result": asdict(result),
            }
        except Exception as exc:
            logger.exception("JSON-Import Fehler source %d", source_id)
            _sync_jobs[source_id] = {
                "status": "error",
                "mode": "import",
                "error": str(exc),
            }
        finally:
            conn.close()
            tmp_path.unlink(missing_ok=True)

    threading.Thread(target=_run, args=(content,), daemon=True).start()
    return {"status": "gestartet", "mode": "import", "source_id": source_id, "filename": file.filename}


@app.get("/api/sources/{source_id}/sp-fields")
async def api_sp_fields(source_id: int):
    """Alle bekannten SP-Feldnamen dieser Quelle (für Spalten-Toggle in UI)."""
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT f.field_name
            FROM document_sp_fields f
            JOIN documents d ON d.id = f.document_id
            WHERE d.source_id = ?
            ORDER BY f.field_name
            """,
            (source_id,),
        ).fetchall()
        return [r["field_name"] for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# REST-API: Dokumente
# ---------------------------------------------------------------------------

@app.get("/api/projects/{project_id}/documents")
async def api_list_documents(
    project_id: int,
    source_id: int | None = None,
    search: str | None = None,
    status: str | None = None,
    limit: int = 5000,
    include_sp_fields: bool = False,
):
    conn = connect()
    try:
        params: list = [project_id]
        where = "d.project_id = ?"
        if source_id:
            where += " AND d.source_id = ?"
            params.append(source_id)
        if search:
            where += " AND d.original_name LIKE ?"
            params.append(f"%{search}%")
        if status:
            where += " AND d.status = ?"
            params.append(status)
        rows = conn.execute(
            f"SELECT d.id, d.original_name, d.status, d.size_bytes, "
            f"d.source_path, d.source_id, d.sp_web_url, d.sp_modified_at, "
            f"d.sp_modified_by, d.sp_content_type, d.selected_for_indexing "
            f"FROM documents d WHERE {where} ORDER BY d.source_path, d.original_name LIMIT ?",
            params + [limit],
        ).fetchall()
        docs = [dict(r) for r in rows]

        if include_sp_fields and docs:
            doc_ids = [d["id"] for d in docs]
            placeholders = ",".join("?" * len(doc_ids))
            field_rows = conn.execute(
                f"SELECT document_id, field_name, field_value "
                f"FROM document_sp_fields WHERE document_id IN ({placeholders})",
                doc_ids,
            ).fetchall()
            fields_by_doc: dict[int, dict] = {}
            for r in field_rows:
                fields_by_doc.setdefault(r["document_id"], {})[r["field_name"]] = r["field_value"]
            for doc in docs:
                doc["sp_fields"] = fields_by_doc.get(doc["id"], {})

        return docs
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/documents/select")
async def api_select_documents(project_id: int, body: dict):
    """Setzt selected_for_indexing für eine Liste von Dokument-IDs."""
    ids = body.get("ids", [])
    selected = 1 if body.get("selected", True) else 0
    if not ids:
        return {"updated": 0}
    conn = connect()
    try:
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE documents SET selected_for_indexing = ?, updated_at = datetime('now') "
            f"WHERE id IN ({placeholders}) AND project_id = ?",
            [selected] + list(ids) + [project_id],
        )
        conn.commit()
        return {"updated": len(ids), "selected": bool(selected)}
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/documents/select-all")
async def api_select_all_documents(project_id: int, body: dict):
    """Setzt selected_for_indexing für alle Dokumente eines Projekts/einer Quelle."""
    selected = 1 if body.get("selected", True) else 0
    source_id = body.get("source_id")
    conn = connect()
    try:
        if source_id:
            conn.execute(
                "UPDATE documents SET selected_for_indexing = ?, updated_at = datetime('now') "
                "WHERE project_id = ? AND source_id = ? AND status NOT IN ('deleted')",
                (selected, project_id, source_id),
            )
        else:
            conn.execute(
                "UPDATE documents SET selected_for_indexing = ?, updated_at = datetime('now') "
                "WHERE project_id = ? AND status NOT IN ('deleted')",
                (selected, project_id),
            )
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE project_id = ? AND selected_for_indexing = 1",
            (project_id,),
        ).fetchone()[0]
        return {"selected_total": count}
    finally:
        conn.close()


@app.get("/api/stats")
async def api_stats():
    conn = connect()
    try:
        stats = {
            "projects": conn.execute("SELECT COUNT(*) FROM projects WHERE status='active'").fetchone()[0],
            "sources": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
            "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "folders": conn.execute("SELECT COUNT(*) FROM source_folders").fetchone()[0],
        }
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM documents GROUP BY status"
        ).fetchall()
        stats["by_status"] = {r["status"]: r["n"] for r in rows}
        return stats
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# REST-API: Chat-Threads (Phase 2a)
# ---------------------------------------------------------------------------

@app.get("/api/threads")
async def api_list_threads(
    include_archived: bool = False,
    project_id: int | None = None,
    limit: int = 100,
):
    return chat_repo.list_threads(
        include_archived=include_archived,
        project_id=project_id,
        limit=limit,
    )


@app.post("/api/threads")
async def api_create_thread(body: dict):
    title = (body.get("title") or "Neuer Chat").strip() or "Neuer Chat"
    project_id = body.get("project_id")
    return chat_repo.create_thread(title=title, project_id=project_id)


@app.get("/api/threads/{thread_id}")
async def api_get_thread(thread_id: int):
    try:
        return chat_repo.get_thread(thread_id)
    except KeyError:
        return {"error": f"Thread {thread_id} nicht gefunden."}


@app.get("/api/threads/{thread_id}/messages")
async def api_thread_messages(thread_id: int):
    try:
        chat_repo.get_thread(thread_id)
    except KeyError:
        return {"error": f"Thread {thread_id} nicht gefunden."}
    return chat_repo.list_messages(thread_id)


@app.patch("/api/threads/{thread_id}")
async def api_update_thread(thread_id: int, body: dict):
    title = body.get("title")
    if title:
        chat_repo.update_thread_title(thread_id, title.strip() or "Neuer Chat")
    return chat_repo.get_thread(thread_id)


@app.delete("/api/threads/{thread_id}")
async def api_archive_thread(thread_id: int, hard: bool = False):
    """Archiviert (soft) oder loescht (hard) einen Thread.

    Foundry-seitig bleibt die Response-History bestehen — nur unser lokaler
    Mirror wird entfernt. Fuer kompletten Cleanup muesste auch die
    Foundry-Conversation geloescht werden (aktuell nicht implementiert).
    """
    if hard:
        chat_repo.delete_thread(thread_id)
    else:
        chat_repo.archive_thread(thread_id)
    return {"ok": True, "mode": "hard" if hard else "archive"}


# ---------------------------------------------------------------------------
# REST-API: Workspace / Projekte / Explorer
# ---------------------------------------------------------------------------

@app.get("/api/workspace/projects")
async def api_workspace_projects():
    """Liste aller Projekte im Disco-Workspace (mit Datei-Zaehlern)."""
    from ..workspace import list_workspace_projects
    return list_workspace_projects()


@app.get("/api/workspace/projects/{slug}/tree")
async def api_workspace_tree(slug: str, max_depth: int = 4):
    """Verzeichnisbaum eines Projekts (rekursiv, ohne Inhalte).

    Liefert ein Tree-Dict mit Knoten:
      {name, path (relativ zum Projekt), type: 'dir'|'file',
       size?, modified?, children?: [...]}
    """
    from ..workspace import validate_slug
    from ..config import settings
    from datetime import datetime

    try:
        slug = validate_slug(slug)
    except ValueError as exc:
        return {"error": str(exc)}

    root = (settings.projects_dir / slug).resolve()
    if not root.exists() or not root.is_dir():
        return {"error": f"Projekt '{slug}' nicht gefunden"}

    def _build(p: Path, depth: int) -> dict:
        node = {
            "name": p.name if p != root else slug,
            "path": str(p.relative_to(root)) if p != root else "",
            "type": "dir",
        }
        if depth >= max_depth:
            node["children"] = []
            node["truncated"] = True
            return node
        children: list[dict] = []
        try:
            entries = sorted(
                p.iterdir(),
                key=lambda x: (not x.is_dir(), x.name.lower()),
            )
        except OSError:
            entries = []
        for child in entries:
            if child.is_dir():
                children.append(_build(child, depth + 1))
            else:
                try:
                    st = child.stat()
                    children.append({
                        "name": child.name,
                        "path": str(child.relative_to(root)),
                        "type": "file",
                        "size": st.st_size,
                        "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    })
                except OSError:
                    continue
        node["children"] = children
        return node

    return _build(root, 0)


def _resolve_project_root(slug: str) -> Path:
    """Helper: Slug -> abs. Projekt-Pfad. Wirft HTTPException-aequivalent."""
    from ..workspace import validate_slug
    slug = validate_slug(slug)
    root = (settings.projects_dir / slug).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Projekt '{slug}' nicht gefunden")
    return root


def _safe_path_in_root(root: Path, rel_path: str) -> Path:
    """Path-Traversal-Schutz: rel_path muss unter root bleiben."""
    if not rel_path:
        raise ValueError("path ist erforderlich")
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError(f"Pfad ausserhalb des Projekts: {rel_path!r}")
    if not candidate.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {rel_path!r}")
    return candidate


# Mime-Map fuer haeufige Endungen — Browser entscheidet danach
_MIME_BY_EXT = {
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".xls": "application/vnd.ms-excel",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
}


@app.get("/api/workspace/projects/{slug}/file")
async def api_workspace_file(slug: str, path: str):
    """Liefert eine Datei aus einem Projekt aus.

    Content-Type wird per Endung gesetzt; Browser/UI entscheidet anhand davon
    wie gerendert wird (Markdown/CSV/PDF/Excel/...).
    """
    from fastapi.responses import FileResponse, PlainTextResponse

    try:
        root = _resolve_project_root(slug)
        target = _safe_path_in_root(root, path)
    except (ValueError, FileNotFoundError) as exc:
        return PlainTextResponse(str(exc), status_code=404)

    ext = target.suffix.lower()
    mime = _MIME_BY_EXT.get(ext, "application/octet-stream")
    # Schutz: keine riesigen Files inline ausliefern
    size = target.stat().st_size
    if size > 50 * 1024 * 1024:  # 50 MB
        return PlainTextResponse(
            f"Datei zu gross fuer Inline-View ({size:,} B). Limit 50 MB.",
            status_code=413,
        )
    return FileResponse(str(target), media_type=mime, filename=target.name)


@app.get("/api/workspace/projects/{slug}/db/tables")
async def api_workspace_db_tables(slug: str):
    """Liste der Tabellen in der Projekt-data.db (ohne Internals)."""
    try:
        root = _resolve_project_root(slug)
    except (ValueError, FileNotFoundError) as exc:
        return {"error": str(exc)}
    db = root / "data.db"
    if not db.exists():
        return []
    import sqlite3
    c = sqlite3.connect(str(db))
    try:
        rows = c.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_disco_%' "
            "ORDER BY name"
        ).fetchall()
        out: list[dict] = []
        for (name,) in rows:
            cnt = c.execute(f"SELECT COUNT(*) FROM \"{name}\"").fetchone()[0]
            cols = [r[1] for r in c.execute(f"PRAGMA table_info(\"{name}\")").fetchall()]
            out.append({"name": name, "row_count": cnt, "columns": cols})
    finally:
        c.close()
    return out


@app.get("/api/workspace/projects/{slug}/db/rows")
async def api_workspace_db_rows(
    slug: str,
    table: str,
    limit: int = 100,
    offset: int = 0,
    order_by: str | None = None,
    order_dir: str = "ASC",
):
    """Paginiertes SELECT * aus einer Tabelle der Projekt-DB."""
    import re as _re
    if not _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table or ""):
        return {"error": f"Ungueltiger Tabellenname: {table!r}"}
    if order_by is not None and not _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", order_by):
        return {"error": f"Ungueltige Sortierspalte: {order_by!r}"}
    if order_dir.upper() not in ("ASC", "DESC"):
        return {"error": "order_dir muss ASC oder DESC sein"}

    try:
        root = _resolve_project_root(slug)
    except (ValueError, FileNotFoundError) as exc:
        return {"error": str(exc)}
    db = root / "data.db"
    if not db.exists():
        return {"error": "data.db existiert nicht"}

    import sqlite3
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    try:
        # Existenz pruefen
        if not c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone():
            return {"error": f"Tabelle '{table}' nicht gefunden"}
        total = c.execute(f"SELECT COUNT(*) FROM \"{table}\"").fetchone()[0]
        sql = f"SELECT * FROM \"{table}\""
        if order_by:
            sql += f" ORDER BY \"{order_by}\" {order_dir.upper()}"
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        rows = c.execute(sql).fetchall()
        cols = [d[0] for d in (c.execute(sql).description or [])]
        return {
            "table": table,
            "total": total,
            "limit": int(limit),
            "offset": int(offset),
            "columns": cols,
            "rows": [dict(r) for r in rows],
        }
    finally:
        c.close()


@app.get("/api/workspace/projects/{slug}/threads")
async def api_workspace_threads(slug: str, include_archived: bool = False):
    """Alle Chat-Threads, die einem Projekt zugeordnet sind."""
    from ..workspace import validate_slug
    try:
        slug = validate_slug(slug)
    except ValueError as exc:
        return {"error": str(exc)}

    # slug -> project_id
    c = connect()
    try:
        row = c.execute(
            "SELECT id FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
    finally:
        c.close()
    if not row:
        return {"error": f"Projekt '{slug}' nicht in der system.db"}

    return chat_repo.list_threads(
        include_archived=include_archived,
        project_id=row["id"],
        limit=200,
    )


# ---------------------------------------------------------------------------
# WebSocket: Chat-Agent (Foundry)
# ---------------------------------------------------------------------------

@app.websocket("/ws/chat")
async def ws_chat(
    websocket: WebSocket,
    thread_id: int = Query(..., description="BEW-lokale Thread-ID aus /api/threads"),
):
    """Streamt Agent-Events fuer einen Chat-Thread.

    Protokoll:
      Client -> Server:  {"text": "Nachricht vom Benutzer"}
      Server -> Client:  typisierte JSON-Events aus AgentService.run_turn
                         (text_delta, tool_call_start, tool_result,
                          code_interpreter, file_search, error, done).
    """
    await websocket.accept()

    # Thread muss existieren (sonst sofort 1008 / close)
    try:
        chat_repo.get_thread(thread_id)
    except KeyError:
        await websocket.send_text(
            json.dumps({"type": "error", "message": f"Thread {thread_id} nicht gefunden."})
        )
        await websocket.close(code=1008)
        return

    svc = get_agent_service()

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            user_text = (payload.get("text") or "").strip()
            if not user_text:
                continue

            # sync-Generator aus AgentService in Worker-Thread laufen lassen,
            # Events via asyncio.Queue zurueck in den WebSocket-Loop bringen.
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()
            SENTINEL = object()

            def _worker() -> None:
                try:
                    for event in svc.run_turn(thread_id, user_text):
                        loop.call_soon_threadsafe(queue.put_nowait, event.to_dict())
                except Exception as exc:
                    logger.exception("AgentService-Fehler")
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "error", "message": f"Agent-Fehler: {exc}"},
                    )
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

            threading.Thread(target=_worker, daemon=True).start()

            while True:
                ev = await queue.get()
                if ev is SENTINEL:
                    break
                await websocket.send_text(json.dumps(ev, ensure_ascii=False))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("WebSocket-Fehler")
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": str(exc)})
            )
        except Exception:
            pass
