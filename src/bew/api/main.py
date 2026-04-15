"""FastAPI-Anwendung: REST-API + WebSocket + statisches Frontend."""

from __future__ import annotations

import json
import logging
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..config import settings
from ..db import connect
from ..projects import list_projects, create_project, archive_project, count_documents as proj_doc_count
from ..sources import list_sources, create_source, get_source, parse_config, count_documents as src_doc_count
from .agent import stream_response

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
    limit: int = 200,
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
# WebSocket: Chat-Agent
# ---------------------------------------------------------------------------

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            messages = payload.get("messages", [])

            async for chunk in stream_response(messages):
                await websocket.send_text(chunk)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("WebSocket-Fehler")
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "text": str(exc)})
            )
        except Exception:
            pass
