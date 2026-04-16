"""Domain-Tools des BEW-Agenten — portiert aus src/bew/api/agent.py.

Diese 6 Functions bildeten den alten Claude-Agent. Sie werden jetzt als
Foundry-Custom-Functions registriert. Logik unveraendert, nur Verpackung
als Registry-Eintrag mit JSON-Schema.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from ...config import settings
from ...db import connect
from ...projects import (
    count_documents as project_doc_count,
    get_project,
    list_projects,
)
from ...sources import (
    count_documents as source_doc_count,
    get_source,
    list_sources,
    parse_config,
)
from . import register


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. list_projects
# ---------------------------------------------------------------------------


@register(
    name="list_projects",
    description=(
        "Listet alle Projekte mit Dokumentenanzahl auf. "
        "Nuetzlich als Einstieg, wenn der Benutzer nicht spezifiziert, "
        "welches Projekt gemeint ist."
    ),
    parameters={
        "type": "object",
        "properties": {
            "include_archived": {
                "type": "boolean",
                "description": "Auch archivierte Projekte einschliessen (Default: false).",
            }
        },
        "required": [],
    },
    returns="Liste von {id, name, description, status, dokumente, erstellt}",
)
def _list_projects(*, include_archived: bool = False) -> list[dict[str, Any]]:
    projects = list_projects(include_archived=include_archived)
    result: list[dict[str, Any]] = []
    for p in projects:
        count = project_doc_count(p["id"])
        result.append(
            {
                "id": p["id"],
                "name": p["name"],
                "description": p.get("description"),
                "status": p["status"],
                "dokumente": count,
                "erstellt": p["created_at"][:10],
            }
        )
    return result


# ---------------------------------------------------------------------------
# 2. get_project_details
# ---------------------------------------------------------------------------


@register(
    name="get_project_details",
    description=(
        "Liefert Details zu einem Projekt: alle Quellen, Dokumentenanzahl, "
        "Sync-Status je Quelle."
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "integer", "description": "Projekt-ID"}
        },
        "required": ["project_id"],
    },
    returns="{id, name, description, status, dokumente_gesamt, quellen: [...]}",
)
def _get_project_details(*, project_id: int) -> dict[str, Any]:
    p = get_project(project_id)
    sources = list_sources(project_id)
    doc_count = project_doc_count(project_id)
    return {
        "id": p["id"],
        "name": p["name"],
        "description": p.get("description"),
        "status": p["status"],
        "dokumente_gesamt": doc_count,
        "quellen": [
            {
                "id": s["id"],
                "name": s["name"],
                "typ": s["source_type"],
                "status": s["status"],
                "letzter_sync": s["last_synced_at"],
                "dokumente": source_doc_count(s["id"]),
                "config": parse_config(s),
            }
            for s in sources
        ],
    }


# ---------------------------------------------------------------------------
# 3. search_documents
# ---------------------------------------------------------------------------


@register(
    name="search_documents",
    description=(
        "Durchsucht Dokumente nach Name oder Pfad (SQL LIKE). "
        "Optional auf ein Projekt einschraenken. "
        "Fuer komplexere Suchen spaeter FTS5 oder File Search verwenden."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Suchbegriff (LIKE-Muster)."},
            "project_id": {
                "type": "integer",
                "description": "Optional: auf dieses Projekt einschraenken.",
            },
            "limit": {
                "type": "integer",
                "description": "Max. Anzahl Ergebnisse (Default: 20).",
            },
        },
        "required": ["query"],
    },
    returns="Liste von {id, original_name, status, size_bytes, source_path, project_id, source_id}",
)
def _search_documents(
    *,
    query: str,
    project_id: int | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    conn = connect()
    try:
        params: list[Any] = [f"%{query}%", f"%{query}%"]
        where = "(d.original_name LIKE ? OR d.source_path LIKE ?)"
        if project_id is not None:
            where += " AND d.project_id = ?"
            params.append(project_id)
        rows = conn.execute(
            f"SELECT d.id, d.original_name, d.status, d.size_bytes, d.source_path, "
            f"d.project_id, d.source_id FROM documents d WHERE {where} "
            f"ORDER BY d.original_name LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 4. get_database_stats
# ---------------------------------------------------------------------------


@register(
    name="get_database_stats",
    description=(
        "Zaehlt Projekte, Quellen, Dokumente und gibt die Status-Verteilung zurueck. "
        "Gut fuer Gesamtuebersicht."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    returns="{projekte, quellen, dokumente_gesamt, nach_status, ordner}",
)
def _get_database_stats() -> dict[str, Any]:
    conn = connect()
    try:
        stats: dict[str, Any] = {}
        stats["projekte"] = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status='active'"
        ).fetchone()[0]
        stats["quellen"] = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        stats["dokumente_gesamt"] = conn.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM documents GROUP BY status"
        ).fetchall()
        stats["nach_status"] = {r["status"]: r["n"] for r in rows}
        stats["ordner"] = conn.execute(
            "SELECT COUNT(*) FROM source_folders"
        ).fetchone()[0]
        return stats
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 5. list_documents
# ---------------------------------------------------------------------------


@register(
    name="list_documents",
    description=(
        "Listet Dokumente eines Projekts, optional nach Quelle und Status gefiltert."
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "integer"},
            "source_id": {
                "type": "integer",
                "description": "Optional: auf eine Quelle einschraenken.",
            },
            "status": {
                "type": "string",
                "description": (
                    "Optional: Status-Filter "
                    "(discovered|downloaded|indexed|needs_reindex|deleted|failed)."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max. Ergebnisse (Default: 30).",
            },
        },
        "required": ["project_id"],
    },
    returns="Liste von {id, original_name, status, size_bytes, source_path, created_at}",
)
def _list_documents(
    *,
    project_id: int,
    source_id: int | None = None,
    status: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    conn = connect()
    try:
        params: list[Any] = [project_id]
        where = "d.project_id = ?"
        if source_id is not None:
            where += " AND d.source_id = ?"
            params.append(source_id)
        if status:
            where += " AND d.status = ?"
            params.append(status)
        rows = conn.execute(
            f"SELECT d.id, d.original_name, d.status, d.size_bytes, "
            f"d.source_path, d.created_at FROM documents d "
            f"WHERE {where} ORDER BY d.original_name LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 6. start_sync
# ---------------------------------------------------------------------------


@register(
    name="start_sync",
    description=(
        "Startet die Synchronisation einer SharePoint-Quelle im Hintergrund. "
        "Gibt sofort zurueck; der Fortschritt laesst sich spaeter via "
        "get_project_details oder ueber die Datenbank pruefen."
    ),
    parameters={
        "type": "object",
        "properties": {
            "source_id": {"type": "integer", "description": "Quellen-ID"}
        },
        "required": ["source_id"],
    },
    returns="{status, source_id, source_name, hinweis} oder {error}",
)
def _start_sync(*, source_id: int) -> dict[str, Any]:
    from ...sharepoint.auth import MSALTokenManager
    from ...sharepoint.graph import GraphClient
    from ...sharepoint.sync import SharePointSyncer

    if not settings.msal_tenant_id or not settings.msal_client_id:
        return {"error": "MSAL_TENANT_ID / MSAL_CLIENT_ID nicht konfiguriert."}

    try:
        source = get_source(source_id)
    except KeyError:
        return {"error": f"Quelle {source_id} nicht gefunden."}

    def run() -> None:
        conn = connect()
        try:
            mgr = MSALTokenManager(settings.msal_tenant_id, settings.msal_client_id)
            graph = GraphClient(mgr)
            syncer = SharePointSyncer(conn, graph, source)
            result = syncer.run()
            logger.info("Sync %d abgeschlossen: %s", source_id, result)
        except Exception as exc:
            logger.error("Sync %d fehlgeschlagen: %s", source_id, exc)
        finally:
            conn.close()

    threading.Thread(target=run, daemon=True).start()

    return {
        "status": "gestartet",
        "source_id": source_id,
        "source_name": source["name"],
        "hinweis": (
            "Sync laeuft im Hintergrund. Status ueber get_project_details "
            "oder die sources-Tabelle abrufbar."
        ),
    }
