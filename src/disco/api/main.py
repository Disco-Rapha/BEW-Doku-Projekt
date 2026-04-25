"""FastAPI-Anwendung: REST-API + WebSocket + statisches Frontend."""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..agent.core import (
    CHAT_TOKEN_BUDGET,
    PORTAL_AGENT_OVERHEAD_TOKENS,
    _effective_context_tokens,
    get_agent_service,
)
from ..chat import repo as chat_repo
from ..config import settings
from ..db import connect
from ..projects import list_projects, count_documents as proj_doc_count
from ..sources import list_sources, create_source, get_source, parse_config, count_documents as src_doc_count
from ..workspace import (
    archive_project as workspace_archive_project,
    bootstrap_all_project_migrations,
    init_project,
    slugify,
)

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/Shutdown-Hook fuer das Backend.

    Beim Start:
      1. Projekt-DB-Migrationen auf alle bestehenden Projekte anwenden
         (frisch ausgerollte Migrations greifen ohne manuelles Eingreifen).
      2. Notification-Watcher-Loop starten (Disco-System-Trigger bei
         Flow-Ereignissen).
    """
    # 1. Migrations-Bootstrap
    try:
        applied = bootstrap_all_project_migrations()
        if applied:
            for slug, branches in applied.items():
                for branch, files in branches.items():
                    if files:
                        logger.info(
                            "project-migration applied: %s[%s] -> %s",
                            slug,
                            branch,
                            files,
                        )
    except Exception:  # noqa: BLE001
        logger.exception("Bootstrap der Projekt-Migrationen fehlgeschlagen")

    # 2. Notification-Watcher
    watcher_task = asyncio.create_task(_notification_watcher_loop())

    try:
        yield
    finally:
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass


async def _notification_watcher_loop() -> None:
    """Pollt alle Projekte alle 3s nach offenen Flow-Notifications und
    triggert pro Notification einen System-Disco-Turn.

    Wird in lifespan() gestartet. Fehler einzelner Iterationen brechen
    den Loop nicht ab.
    """
    from .. import flow_notifications  # lazy import (Modul-zyklus vermeiden)

    while True:
        try:
            await flow_notifications.process_pending_notifications()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Notification-Watcher-Iteration gescheitert")
        await asyncio.sleep(3.0)


app = FastAPI(title="Disco", docs_url="/api/docs", lifespan=lifespan)

# Statische Dateien
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Haupt-UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    """Liefert index.html mit Environment-Marker-Injection.

    Der Marker (DISCO_ENV) wird als data-env-Attribut im <html>-Tag
    eingeblendet, damit die UI einen Dev/Prod-Badge rendern kann.
    """
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    env = (settings.disco_env or "prod").strip().lower()
    if env not in {"prod", "dev"}:
        env = "dev"  # alles abseits "prod" -> dev-Markierung (defensiv)
    html = html.replace("<html lang=\"de\">", f"<html lang=\"de\" data-env=\"{env}\">", 1)
    return html


@app.get("/api/env")
async def api_env():
    """Liefert Environment-Marker + Workspace + Modell fuer die UI-Footer-Anzeige.

    Wird vom Frontend beim Start aufgerufen; ersetzt die frueheren
    hardcodeten Werte (~/Disco, gpt-5) durch die tatsaechlichen Runtime-
    Werte.
    """
    env = (settings.disco_env or "prod").strip().lower()
    if env not in {"prod", "dev"}:
        env = "dev"

    # Workspace als ~-Pfad anzeigen, falls er unter $HOME liegt.
    try:
        ws = settings.workspace_root
        home = Path.home()
        ws_display = "~/" + str(ws.relative_to(home)) if ws.is_relative_to(home) else str(ws)
    except Exception:
        ws_display = settings.disco_workspace or "~/Disco"

    return {
        "env": env,
        "workspace": ws_display,
        "model": settings.foundry_model_deployment or "",
        "agent_id": settings.foundry_agent_id or "",
    }


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
    """Legt ein neues Projekt an — volle Struktur (Verzeichnis + DB + Templates).

    Body:
        name        (str, pflicht)  — Anzeigename, wird zu Slug verdichtet
        slug        (str, optional) — expliziter Slug; sonst aus Name abgeleitet
        description (str, optional)
    """
    name = (body.get("name") or "").strip()
    raw_slug = (body.get("slug") or "").strip()
    description = (body.get("description") or "").strip() or None
    if not name and not raw_slug:
        return {"error": "Name fehlt"}
    slug = raw_slug or slugify(name)
    display_name = name or slug.replace("-", " ").title()
    try:
        info = init_project(slug=slug, name=display_name, description=description)
        return {**info, "document_count": 0}
    except ValueError as exc:
        return {"error": str(exc)}


@app.post("/api/workspace/projects/{slug}/archive")
async def api_archive_project_by_slug(slug: str):
    """Archiviert ein Projekt: verschiebt Ordner + markiert DB-Status.

    Verzeichnis landet unter `<workspace>/archive/<slug>-<timestamp>/`,
    DB-Eintrag bekommt status='archived'. Reversibel per manuellem
    Zurueckschieben.
    """
    try:
        info = workspace_archive_project(slug)
        return {"ok": True, **info}
    except (ValueError, FileNotFoundError) as exc:
        return {"error": str(exc)}


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
# REST-API: Projekt-Chat (Migration 006 — 1 persistenter Chat pro Projekt)
# ---------------------------------------------------------------------------

# Token-Kapazitaet + Overhead kommen aus agent.core (oben importiert).


def _chat_state_payload(state: dict[str, Any] | None) -> dict[str, Any]:
    """Packt den State + abgeleitete Felder (Prozent, Warnstufe) fuer die UI.

    Der in der UI angezeigte token_estimate ist der effektive Fuellstand
    gegen Azure — bevorzugt aus measured_context_tokens (usage.input_tokens
    der letzten Response, Ground-Truth), sonst token_estimate + Overhead
    (lokale Schaetzung).
    """
    if state is None:
        return {
            "exists": False,
            "token_estimate": PORTAL_AGENT_OVERHEAD_TOKENS,
            "token_estimate_source": "overhead_only",
            "token_budget": CHAT_TOKEN_BUDGET,
            "percent": round(PORTAL_AGENT_OVERHEAD_TOKENS / CHAT_TOKEN_BUDGET, 4),
            "warn_level": "ok",
        }
    raw_tok = int(state.get("token_estimate") or 0)
    measured = state.get("measured_context_tokens")
    tok = _effective_context_tokens(state)
    source = "measured" if measured is not None else "estimate"
    pct = (tok / CHAT_TOKEN_BUDGET) if CHAT_TOKEN_BUDGET else 0.0
    if pct >= 0.90:
        warn = "critical"  # Auto-Kompressions-Vorschlag
    elif pct >= 0.70:
        warn = "warn"      # gelbes Badge
    else:
        warn = "ok"
    return {
        "exists": True,
        **state,
        "token_estimate": tok,
        "token_estimate_source": source,
        "token_estimate_messages": raw_tok,
        "token_overhead": PORTAL_AGENT_OVERHEAD_TOKENS,
        "token_budget": CHAT_TOKEN_BUDGET,
        "percent": round(pct, 4),
        "warn_level": warn,
    }


@app.get("/api/projects/{slug}/chat/state")
async def api_chat_state(slug: str):
    """Aktueller Chat-State eines Projekts (Token-Fill, Warn-Level)."""
    from ..workspace import validate_slug
    try:
        slug = validate_slug(slug)
    except ValueError as exc:
        return {"error": str(exc)}
    state = chat_repo.get_state(slug)
    return _chat_state_payload(state)


@app.get("/api/projects/{slug}/chat/messages")
async def api_chat_messages(slug: str, include_compacted: bool = False):
    """Alle Messages eines Projekt-Chats.

    Per default nur aktive (nicht komprimierte). Mit include_compacted=1
    fuer die UI-Ansicht mit Kompressions-Divider.
    """
    from ..workspace import validate_slug
    try:
        slug = validate_slug(slug)
    except ValueError as exc:
        return {"error": str(exc)}
    if include_compacted:
        return chat_repo.list_all_messages(slug, include_compacted=True)
    return chat_repo.list_active_messages(slug)


@app.post("/api/projects/{slug}/chat/compact")
async def api_chat_compact(slug: str, body: dict | None = None):
    """Compaction v2 — Handover-Brief + letzte Dialog-Paare erhalten.

    Ein /compact macht jetzt:
      - Die letzten N user/assistant-Text-Paare (Default 3) bleiben aktiv.
      - Alles davor wird mit is_compacted=1 markiert.
      - Ein LLM-Call erzeugt eine kurze Handover-Notiz, die als neue
        system-Message VOR den erhaltenen Paaren eingehaengt wird.
      - foundry_response_id + measured_context_tokens werden genullt.

    Body optional:
      - keep_pairs (int, Default 3) — wie viele Dialog-Paare erhalten bleiben.
      - legacy (bool) — falls true, lief die v1-Logik (alles markieren, kein
        Handover, nur Memory-Reload). Abwaertskompatibilitaet.
      - cutoff_message_id (int) — nur im legacy-Mode akzeptiert.
    """
    from ..workspace import validate_slug
    try:
        slug = validate_slug(slug)
    except ValueError as exc:
        return {"error": str(exc)}

    body = body or {}
    legacy = bool(body.get("legacy"))

    if not legacy:
        from ..chat.compaction import DEFAULT_KEEP_PAIRS, run_compaction_with_handover
        keep_pairs = int(body.get("keep_pairs") or DEFAULT_KEEP_PAIRS)
        try:
            result = run_compaction_with_handover(slug, keep_pairs=keep_pairs)
        except Exception as exc:
            logger.exception("Compaction v2 fehlgeschlagen")
            return {"error": f"Compaction fehlgeschlagen: {exc}"}
        return result

    # Legacy-Mode: altes Verhalten unveraendert (alle Messages markieren).
    cutoff = body.get("cutoff_message_id")
    if cutoff is None:
        cutoff = chat_repo.last_active_message_id(slug)
    if cutoff is None:
        return {"error": "Keine aktiven Messages zum Komprimieren."}

    marked = chat_repo.mark_compacted(slug, int(cutoff))
    chat_repo.set_response_id(slug, None)
    chat_repo.clear_measured_context(slug)
    new_estimate = chat_repo.recompute_token_estimate(slug)

    return {
        "ok": True,
        "mode": "legacy",
        "marked_compacted": marked,
        "cutoff_message_id": int(cutoff),
        "new_token_estimate": new_estimate,
    }


@app.delete("/api/projects/{slug}/chat")
async def api_chat_reset(slug: str):
    """Loescht kompletten Chat-State + alle Messages eines Projekts.

    Harte Zuruecksetzung — auch Audit-Trail verschwindet. Nur nutzen, wenn
    der Nutzer es explizit will.
    """
    from ..workspace import validate_slug
    try:
        slug = validate_slug(slug)
    except ValueError as exc:
        return {"error": str(exc)}
    chat_repo.delete_state(slug)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Observability: Tool-Call-Stats + Message-Feedback
# ---------------------------------------------------------------------------


@app.post("/api/chat/messages/{message_id}/feedback")
async def api_message_feedback(message_id: int, body: dict):
    """Speichert ein Feedback-Event (good|bad + optionaler Kommentar)."""
    rating = (body or {}).get("rating")
    comment = (body or {}).get("comment")
    if rating not in ("good", "bad"):
        return {"error": "rating muss 'good' oder 'bad' sein."}
    try:
        fb = chat_repo.add_message_feedback(
            message_id=int(message_id),
            rating=rating,
            comment=comment,
        )
        return {"ok": True, "feedback": fb}
    except KeyError as exc:
        return {"error": str(exc)}


@app.get("/api/chat/messages/feedback")
async def api_message_feedback_latest(ids: str):
    """Holt das jeweils neueste Feedback fuer eine Liste von Message-IDs.

    ids als komma-separierter String: ?ids=1,2,3.
    Antwort: { "12": {"rating": "bad", "comment": "..."}, ... }.
    """
    try:
        message_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        return {"error": "ids muss komma-separierte Integers sein."}
    result = chat_repo.latest_feedback_for_messages(message_ids)
    return {str(k): v for k, v in result.items()}


@app.get("/api/agent-stats")
async def api_agent_stats(project: str | None = None, days: int = 30):
    """Aggregiert Tool-Call-Metriken aus agent_tool_calls.

    Query-Parameter:
      - project: optionaler Slug-Filter (default: global ueber alle Projekte)
      - days: Zeitfenster in Tagen (default: 30)

    Antwort:
      {
        "scope": "<slug oder 'all'>",
        "window_days": N,
        "totals": {"calls": X, "errors": Y, "feedback_good": A, "feedback_bad": B},
        "per_tool": [ {tool_name, calls, errors, error_rate, avg_ms, max_ms}, ... ],
        "recent_errors": [ {tool_name, arguments_summary, result_error_msg, created_at}, ... ],
        "recent_feedback": [ {rating, comment, created_at, project_slug, message_id}, ... ]
      }
    """
    from ..db import connect

    window_clause = "datetime(created_at) >= datetime('now', ?)"
    window_arg = f"-{int(days)} days"

    conn = connect(settings.db_path)
    try:
        where = [window_clause]
        args: list[Any] = [window_arg]
        if project:
            where.append("project_slug = ?")
            args.append(project)
        where_sql = " AND ".join(where)

        totals_row = conn.execute(
            f"SELECT COUNT(*) AS calls, "
            f"       COALESCE(SUM(result_is_error), 0) AS errors "
            f"FROM agent_tool_calls WHERE {where_sql}",
            args,
        ).fetchone()
        totals = {
            "calls": int(totals_row["calls"]) if totals_row else 0,
            "errors": int(totals_row["errors"]) if totals_row else 0,
        }

        per_tool = [
            {
                "tool_name": r["tool_name"],
                "calls": int(r["calls"]),
                "errors": int(r["errors"]),
                "error_rate": (float(r["errors"]) / float(r["calls"])) if r["calls"] else 0.0,
                "avg_ms": int(r["avg_ms"] or 0),
                "max_ms": int(r["max_ms"] or 0),
            }
            for r in conn.execute(
                f"SELECT tool_name, COUNT(*) AS calls, "
                f"       SUM(result_is_error) AS errors, "
                f"       AVG(duration_ms) AS avg_ms, "
                f"       MAX(duration_ms) AS max_ms "
                f"FROM agent_tool_calls WHERE {where_sql} "
                f"GROUP BY tool_name ORDER BY calls DESC",
                args,
            ).fetchall()
        ]

        recent_errors = [
            {
                "id": int(r["id"]),
                "tool_name": r["tool_name"],
                "arguments_summary": r["arguments_summary"],
                "result_error_msg": r["result_error_msg"],
                "project_slug": r["project_slug"],
                "message_id": r["message_id"],
                "created_at": r["created_at"],
            }
            for r in conn.execute(
                f"SELECT id, tool_name, arguments_summary, result_error_msg, "
                f"       project_slug, message_id, created_at "
                f"FROM agent_tool_calls "
                f"WHERE result_is_error = 1 AND {where_sql} "
                f"ORDER BY id DESC LIMIT 15",
                args,
            ).fetchall()
        ]

        # Feedback — separat, andere WHERE-Condition
        fb_where = [window_clause]
        fb_args: list[Any] = [window_arg]
        if project:
            fb_where.append("project_slug = ?")
            fb_args.append(project)
        fb_where_sql = " AND ".join(fb_where)

        fb_totals = conn.execute(
            f"SELECT rating, COUNT(*) AS c FROM chat_message_feedback "
            f"WHERE {fb_where_sql} GROUP BY rating",
            fb_args,
        ).fetchall()
        totals["feedback_good"] = sum(int(r["c"]) for r in fb_totals if r["rating"] == "good")
        totals["feedback_bad"] = sum(int(r["c"]) for r in fb_totals if r["rating"] == "bad")

        recent_feedback = [
            {
                "id": int(r["id"]),
                "message_id": int(r["message_id"]),
                "project_slug": r["project_slug"],
                "rating": r["rating"],
                "comment": r["comment"],
                "created_at": r["created_at"],
            }
            for r in conn.execute(
                f"SELECT id, message_id, project_slug, rating, comment, created_at "
                f"FROM chat_message_feedback "
                f"WHERE {fb_where_sql} "
                f"ORDER BY id DESC LIMIT 20",
                fb_args,
            ).fetchall()
        ]

        return {
            "scope": project or "all",
            "window_days": int(days),
            "totals": totals,
            "per_tool": per_tool,
            "recent_errors": recent_errors,
            "recent_feedback": recent_feedback,
        }
    finally:
        conn.close()


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
    ".dxf": "image/vnd.dxf",
    ".dwg": "image/vnd.dwg",
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


# ---------------------------------------------------------------------------
# DXF-Bereitstellung fuer den DWG-Viewer im UI
# ---------------------------------------------------------------------------
#
# Liefert eine Datei garantiert als DXF aus.
#   - .dxf → direkt
#   - .dwg → via ezdxf.addons.odafc + ODA File Converter, gecached
#            unter <projekt>/.disco/dxf-cache/<sha256>.dxf
#
# Der Viewer (dxf-viewer, MIT, https://github.com/vagran/dxf-viewer) liest
# DXF — DWG-Konvertierung passiert hier serverseitig, transparent fuer
# das Frontend.


import hashlib

_DXF_CACHE_SUBDIR = ".disco/dxf-cache"


def _dxf_cache_path(root: Path, source: Path) -> Path:
    """Cache-Pfad fuer eine DWG-Datei. Hash inkl. mtime → automatischer
    Cache-Bust bei Datei-Aenderung."""
    stat = source.stat()
    h = hashlib.sha256()
    h.update(str(source).encode("utf-8"))
    h.update(b"|")
    h.update(str(stat.st_size).encode("utf-8"))
    h.update(b"|")
    h.update(str(int(stat.st_mtime)).encode("utf-8"))
    digest = h.hexdigest()[:32]
    return root / _DXF_CACHE_SUBDIR / f"{digest}.dxf"


@app.get("/api/workspace/projects/{slug}/file/dxf")
async def api_workspace_file_as_dxf(slug: str, path: str):
    """Liefert die Datei als DXF aus.

    .dxf wird direkt durchgereicht; .dwg wird via ezdxf.addons.odafc
    nach DXF konvertiert (Cache unter `.disco/dxf-cache/`).
    Voraussetzung fuer DWG: ODA File Converter installiert.
    """
    from fastapi.responses import FileResponse, PlainTextResponse

    try:
        root = _resolve_project_root(slug)
        target = _safe_path_in_root(root, path)
    except (ValueError, FileNotFoundError) as exc:
        return PlainTextResponse(str(exc), status_code=404)

    suffix = target.suffix.lower()
    if suffix == ".dxf":
        return FileResponse(
            str(target),
            media_type="image/vnd.dxf",
            filename=target.name,
        )

    if suffix != ".dwg":
        return PlainTextResponse(
            f"Format {suffix!r} kann nicht als DXF geliefert werden.",
            status_code=415,
        )

    cache_path = _dxf_cache_path(root, target)
    if not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from ezdxf.addons import odafc
        except ImportError:
            return PlainTextResponse(
                "ezdxf.addons.odafc nicht verfuegbar — `uv add ezdxf` ausfuehren.",
                status_code=500,
            )
        try:
            odafc.convert(str(target), str(cache_path))
        except Exception as exc:
            return PlainTextResponse(
                f"DWG-Konvertierung fehlgeschlagen — meist fehlt der "
                f"ODA File Converter. Siehe docs/dwg-setup.md. "
                f"Original-Fehler: {exc}",
                status_code=500,
            )

    return FileResponse(
        str(cache_path),
        media_type="image/vnd.dxf",
        filename=target.stem + ".dxf",
    )


_DB_CHOICES = {"workspace", "datastore"}


def _resolve_project_db(root: Path, db: str) -> Path:
    """Liefert den Pfad zur gewuenschten Projekt-DB (workspace.db/datastore.db)."""
    if db not in _DB_CHOICES:
        raise ValueError(f"Unbekannte DB {db!r}. Erlaubt: {sorted(_DB_CHOICES)}.")
    return root / f"{db}.db"


@app.get("/api/workspace/projects/{slug}/db/tables")
async def api_workspace_db_tables(slug: str):
    """Liste der Tabellen in den Projekt-DBs (ohne Internals).

    Liefert eine flache Liste mit beiden DBs — pro Eintrag ist ``db``
    ('workspace'|'datastore') gesetzt, damit das Frontend den Kontext
    beim anschliessenden `/db/rows`-Aufruf mitgeben kann.
    """
    try:
        root = _resolve_project_root(slug)
    except (ValueError, FileNotFoundError) as exc:
        return {"error": str(exc)}

    import sqlite3
    out: list[dict] = []
    for branch in ("datastore", "workspace"):
        db_path = root / f"{branch}.db"
        if not db_path.exists():
            continue
        c = sqlite3.connect(str(db_path))
        try:
            rows = c.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "AND name NOT LIKE '_disco_%' "
                "ORDER BY name"
            ).fetchall()
            for (name,) in rows:
                cnt = c.execute(f"SELECT COUNT(*) FROM \"{name}\"").fetchone()[0]
                cols = [
                    r[1]
                    for r in c.execute(f"PRAGMA table_info(\"{name}\")").fetchall()
                ]
                out.append(
                    {
                        "name": name,
                        "db": branch,
                        "row_count": cnt,
                        "columns": cols,
                    }
                )
        finally:
            c.close()
    return out


@app.get("/api/workspace/projects/{slug}/db/rows")
async def api_workspace_db_rows(
    slug: str,
    table: str,
    db: str = "workspace",
    limit: int = 100,
    offset: int = 0,
    order_by: str | None = None,
    order_dir: str = "ASC",
):
    """Paginiertes SELECT * aus einer Tabelle einer Projekt-DB.

    ``db`` waehlt zwischen ``workspace`` (Ebene 3) und ``datastore``
    (Ebene 1+2). Beide DBs koennen theoretisch gleich heissende Tabellen
    haben, daher ist der Parameter Pflicht (mit Default ``workspace``).
    """
    import re as _re
    if not _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table or ""):
        return {"error": f"Ungueltiger Tabellenname: {table!r}"}
    if order_by is not None and not _re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", order_by):
        return {"error": f"Ungueltige Sortierspalte: {order_by!r}"}
    if order_dir.upper() not in ("ASC", "DESC"):
        return {"error": "order_dir muss ASC oder DESC sein"}
    if db not in _DB_CHOICES:
        return {"error": f"Unbekannte DB {db!r}. Erlaubt: {sorted(_DB_CHOICES)}."}

    try:
        root = _resolve_project_root(slug)
    except (ValueError, FileNotFoundError) as exc:
        return {"error": str(exc)}
    db_path = root / f"{db}.db"
    if not db_path.exists():
        return {"error": f"{db}.db existiert nicht"}

    import sqlite3
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    try:
        # Existenz pruefen
        if not c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone():
            return {"error": f"Tabelle '{table}' nicht in {db}.db gefunden"}
        total = c.execute(f"SELECT COUNT(*) FROM \"{table}\"").fetchone()[0]
        sql = f"SELECT * FROM \"{table}\""
        if order_by:
            sql += f" ORDER BY \"{order_by}\" {order_dir.upper()}"
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        rows = c.execute(sql).fetchall()
        cols = [d[0] for d in (c.execute(sql).description or [])]
        return {
            "table": table,
            "db": db,
            "total": total,
            "limit": int(limit),
            "offset": int(offset),
            "columns": cols,
            "rows": [dict(r) for r in rows],
        }
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Flows — REST-API fuer das Frontend-Sidebar-Panel
# ---------------------------------------------------------------------------


def _resolve_project_path_or_error(slug: str):
    """Gibt (project_root_Path, None) oder (None, error_dict) zurueck."""
    from ..workspace import validate_slug
    try:
        slug = validate_slug(slug)
    except ValueError as exc:
        return None, {"error": str(exc)}
    project_path = settings.projects_dir / slug
    if not project_path.is_dir():
        return None, {"error": f"Projekt '{slug}' nicht gefunden."}
    if not (project_path / "workspace.db").exists():
        return None, {"error": f"workspace.db fehlt in '{slug}'."}
    return project_path, None


def _flow_info_to_dict(info, project_root) -> dict:
    # Library-Flows liegen im Code-Repo, nicht im Projekt; dann gibt relative_to einen ValueError.
    try:
        path_str = str(info.path.relative_to(project_root))
    except ValueError:
        path_str = f"<library>/{info.name}"
    return {
        "name": info.name,
        "path": path_str,
        "source": info.source,
        "has_runner": info.has_runner,
        "has_readme": info.has_readme,
        "readme_excerpt": info.readme_excerpt,
        "last_modified": info.last_modified,
        "run_count": info.run_count,
    }


def _run_info_to_dict(run) -> dict:
    return {
        "id": run.id,
        "flow_name": run.flow_name,
        "title": run.title,
        "status": run.status,
        "worker_pid": run.worker_pid,
        "config": run.config,
        "total_items": run.total_items,
        "done_items": run.done_items,
        "failed_items": run.failed_items,
        "skipped_items": run.skipped_items,
        "total_cost_eur": run.total_cost_eur,
        "total_tokens_in": run.total_tokens_in,
        "total_tokens_out": run.total_tokens_out,
        "pause_requested": run.pause_requested,
        "cancel_requested": run.cancel_requested,
        "error": run.error,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


@app.get("/api/workspace/projects/{slug}/flows")
async def api_flows_list(slug: str):
    """Alle Flows im Projekt + ob ein Run gerade laeuft."""
    from ..flows import service as flow_service

    project_root, err = _resolve_project_path_or_error(slug)
    if err:
        return err
    flows = flow_service.list_flows(project_root)
    # Pro Flow zusaetzlich: gibt es einen laufenden Run?
    running_runs = flow_service.list_runs(project_root, status="running", limit=50)
    running_by_flow = {r.flow_name: r.id for r in running_runs}
    return {
        "flows": [
            {
                **_flow_info_to_dict(f, project_root),
                "running_run_id": running_by_flow.get(f.name),
            }
            for f in flows
        ],
        "total": len(flows),
    }


@app.get("/api/workspace/projects/{slug}/flows/{flow_name}")
async def api_flow_show(slug: str, flow_name: str):
    """Details zu einem Flow: README-Text, Runner-Info, letzte Runs."""
    from ..flows import service as flow_service

    project_root, err = _resolve_project_path_or_error(slug)
    if err:
        return err
    try:
        info = flow_service.get_flow(project_root, flow_name)
    except (KeyError, ValueError) as exc:
        return {"error": str(exc)}

    readme_path = info.path / "README.md"
    runner_path = info.path / "runner.py"
    readme_content = ""
    if readme_path.is_file():
        try:
            readme_content = readme_path.read_text(encoding="utf-8")
        except OSError as exc:
            readme_content = f"(Lesefehler: {exc})"

    runner_lines = 0
    if runner_path.is_file():
        try:
            runner_lines = sum(1 for _ in runner_path.open("r", encoding="utf-8", errors="replace"))
        except OSError:
            pass

    recent = flow_service.list_runs(project_root, flow_name=flow_name, limit=20)
    return {
        **_flow_info_to_dict(info, project_root),
        "readme_content": readme_content,
        "runner_lines": runner_lines,
        "recent_runs": [_run_info_to_dict(r) for r in recent],
    }


@app.post("/api/workspace/projects/{slug}/flows/{flow_name}/runs")
async def api_flow_run_start(slug: str, flow_name: str, payload: dict | None = None):
    """Startet einen neuen Run eines Flows. Body optional: {title, config}."""
    from ..flows import service as flow_service

    project_root, err = _resolve_project_path_or_error(slug)
    if err:
        return err
    body = payload or {}
    title = body.get("title")
    config = body.get("config")
    if config is not None and not isinstance(config, dict):
        return {"error": "config muss ein JSON-Objekt sein."}
    try:
        run = flow_service.create_run(
            project_root, flow_name, title=title, config=config
        )
        run = flow_service.start_run(project_root, run.id)
    except (KeyError, FileNotFoundError, ValueError, RuntimeError) as exc:
        return {"error": str(exc)}
    return _run_info_to_dict(run)


@app.get("/api/workspace/projects/{slug}/runs")
async def api_runs_list(
    slug: str,
    flow: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    """Runs im Projekt (neueste zuerst), optional nach flow/status gefiltert."""
    from ..flows import service as flow_service

    project_root, err = _resolve_project_path_or_error(slug)
    if err:
        return err
    effective_limit = max(1, min(int(limit or 50), 500))
    runs = flow_service.list_runs(
        project_root,
        flow_name=flow,
        status=status,
        limit=effective_limit,
    )
    return {
        "runs": [_run_info_to_dict(r) for r in runs],
        "total": len(runs),
    }


@app.get("/api/workspace/projects/{slug}/runs/{run_id}")
async def api_run_status(slug: str, run_id: int):
    """Status + Stats eines einzelnen Runs."""
    from ..flows import service as flow_service

    project_root, err = _resolve_project_path_or_error(slug)
    if err:
        return err
    try:
        run = flow_service.get_run(project_root, run_id)
    except KeyError as exc:
        return {"error": str(exc)}
    return _run_info_to_dict(run)


@app.get("/api/workspace/projects/{slug}/runs/{run_id}/items")
async def api_run_items(
    slug: str,
    run_id: int,
    status: str | None = None,
    limit: int = 100,
):
    """Items eines Runs (input_ref, status, output, Fehler)."""
    from ..flows import service as flow_service

    project_root, err = _resolve_project_path_or_error(slug)
    if err:
        return err
    effective_limit = max(1, min(int(limit or 100), 1000))
    items = flow_service.list_run_items(
        project_root, run_id, status=status, limit=effective_limit
    )
    return {"items": items, "total": len(items)}


@app.get("/api/workspace/projects/{slug}/runs/{run_id}/logs")
async def api_run_logs(slug: str, run_id: int, tail: int = 100):
    """Log-Zeilen eines Runs (log.txt + stderr.log)."""
    project_root, err = _resolve_project_path_or_error(slug)
    if err:
        return err

    effective_tail = max(1, min(int(tail or 100), 2000))
    log_dir = project_root / ".disco" / "flows" / "runs" / str(run_id)

    def _read_tail(path):
        if not path.is_file():
            return ""
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return f"(Lesefehler: {exc})"
        return "\n".join(lines[-effective_tail:])

    return {
        "run_id": run_id,
        "log_text": _read_tail(log_dir / "log.txt"),
        "stderr_text": _read_tail(log_dir / "stderr.log"),
        "log_dir_exists": log_dir.is_dir(),
    }


@app.post("/api/workspace/projects/{slug}/runs/{run_id}/pause")
async def api_run_pause(slug: str, run_id: int):
    """Signalisiert dem Worker: pausiere beim naechsten Item."""
    from ..flows import service as flow_service

    project_root, err = _resolve_project_path_or_error(slug)
    if err:
        return err
    try:
        run = flow_service.request_pause(project_root, run_id)
    except (KeyError, ValueError) as exc:
        return {"error": str(exc)}
    return _run_info_to_dict(run)


@app.get("/api/workspace/active-runs")
async def api_active_runs():
    """Alle aktiven Runs (running/paused) projekt-uebergreifend.

    Versorgt den Run-Streifen im Chat-Header. 3-Sekunden-Polling-freundlich:
    pro Projekt-DB eine kurze Query auf `agent_flow_runs WHERE status IN (...)`.
    Projekte ohne workspace.db oder unlesbare DBs werden still uebersprungen.
    """
    from ..flows import service as flow_service
    from ..workspace import list_workspace_projects

    runs_out: list[dict] = []
    try:
        projects = list_workspace_projects()
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": f"Projekt-Liste: {exc}", "runs": [], "total": 0}

    for proj in projects:
        if not proj.get("has_workspace_db"):
            continue
        project_root = Path(proj["path"])
        slug = proj["slug"]
        try:
            running = flow_service.list_runs(project_root, status="running", limit=50)
            paused = flow_service.list_runs(project_root, status="paused", limit=50)
        except Exception:
            # Projekt-DB nicht lesbar (z.B. Migrationen fehlen) — skip
            continue
        for run in [*running, *paused]:
            runs_out.append({
                **_run_info_to_dict(run),
                "project_slug": slug,
                "project_name": proj.get("name") or slug,
            })

    # Neueste zuerst (ueber Projekte hinweg)
    runs_out.sort(key=lambda r: (r.get("started_at") or r.get("created_at") or ""), reverse=True)
    return {"runs": runs_out, "total": len(runs_out)}


@app.post("/api/workspace/projects/{slug}/runs/{run_id}/cancel")
async def api_run_cancel(slug: str, run_id: int, payload: dict | None = None):
    """Signalisiert dem Worker: abbrechen. Mit force=true zusaetzlich SIGTERM."""
    from ..flows import service as flow_service

    project_root, err = _resolve_project_path_or_error(slug)
    if err:
        return err
    force = bool((payload or {}).get("force", False))
    try:
        if force:
            flow_service.kill_run(project_root, run_id)
        else:
            flow_service.request_cancel(project_root, run_id)
        run = flow_service.get_run(project_root, run_id)
    except (KeyError, ValueError) as exc:
        return {"error": str(exc)}
    return _run_info_to_dict(run)


# ---------------------------------------------------------------------------
# WebSocket: Chat-Agent (Foundry)
# ---------------------------------------------------------------------------

@app.websocket("/ws/chat")
async def ws_chat(
    websocket: WebSocket,
    project: str = Query(..., description="Projekt-Slug — der Chat ist an ein Projekt gebunden"),
):
    """Streamt Agent-Events fuer den persistenten Chat eines Projekts.

    Protokoll:
      Client -> Server:  {"text": "Nachricht vom Benutzer"}
      Server -> Client:  typisierte JSON-Events aus AgentService.run_turn
                         (text_delta, tool_call_start, tool_result,
                          code_interpreter, file_search, error, done).

    done-Event enthaelt total_token_estimate — die UI nutzt es fuer den
    Token-Counter + Warn-Badge (70/90 %).
    """
    from ..workspace import validate_slug

    await websocket.accept()

    try:
        project_slug = validate_slug(project)
    except ValueError as exc:
        await websocket.send_text(
            json.dumps({"type": "error", "message": f"Ungueltiger Slug: {exc}"})
        )
        await websocket.close(code=1008)
        return

    # Projekt-Existenz pruefen (Workspace-Ordner muss da sein)
    project_path = settings.projects_dir / project_slug
    if not project_path.is_dir():
        await websocket.send_text(
            json.dumps({
                "type": "error",
                "message": f"Projekt '{project_slug}' nicht im Workspace.",
            })
        )
        await websocket.close(code=1008)
        return

    # State sicherstellen (legt bei Bedarf an — kein separater Call noetig)
    chat_repo.get_or_create_state(project_slug)

    svc = get_agent_service()

    # Registry: damit flow_notifications.py System-Events in diesen Tab
    # pushen kann ("Disco meldet sich wegen Heartbeat"). De-Registrierung
    # im finally, damit nach WebSocketDisconnect keine Leiche bleibt.
    from . import ws_registry
    from ..agent.locks import project_lock
    await ws_registry.register(project_slug, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            user_text = (payload.get("text") or "").strip()
            if not user_text:
                continue

            # Lock pro Projekt: verhindert, dass ein System-Trigger-Turn
            # (flow_notifications) parallel zum User-Turn auf denselben
            # Foundry-Thread schreibt. Der Lock wird vom Event-Loop
            # gehalten, die Worker-Thread-Phase ist aus Loop-Sicht ein
            # langes await auf queue.get().
            lock = await project_lock(project_slug)
            async with lock:
                # sync-Generator aus AgentService in Worker-Thread laufen lassen,
                # Events via asyncio.Queue zurueck in den WebSocket-Loop bringen.
                loop = asyncio.get_running_loop()
                queue: asyncio.Queue = asyncio.Queue()
                SENTINEL = object()

                def _worker() -> None:
                    try:
                        for event in svc.run_turn(project_slug, user_text):
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
    finally:
        await ws_registry.unregister(project_slug, websocket)
