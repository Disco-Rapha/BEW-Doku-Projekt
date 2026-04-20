"""Claude-Agent mit Tool Use für das Dokumentenmanagementsystem.

Der Agent hat Zugriff auf:
- Projektliste und -details
- Quellen und Sync-Status
- Dokumente (suchen, listen, Details)
- Task-Ausführung (Sync starten)
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import anthropic

from ..config import settings
from ..db import connect
from ..projects import list_projects, get_project, count_documents as project_doc_count
from ..sources import list_sources, get_source, count_documents as source_doc_count, parse_config

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """Du bist ein intelligenter Dokumentenmanagement-Assistent für das BEW Doku Projekt.

Du hilfst dem Nutzer dabei:
- Projekte und Dokumentenquellen zu verwalten
- Dokumente zu durchsuchen und zu analysieren
- Synchronisationen zu starten und zu überwachen
- Aufgaben und Analysen zu koordinieren

Du hast direkten Zugriff auf die Projektdatenbank über deine Tools.
Nutze sie aktiv, um dem Nutzer konkrete, datenbasierte Antworten zu geben.
Antworte immer auf Deutsch. Sei präzise und handlungsorientiert.

Wenn der Nutzer eine Aufgabe beschreibt, führe sie proaktiv aus — frag nicht nach
Erlaubnis für offensichtliche Schritte."""

# ---------------------------------------------------------------------------
# Tool-Definitionen
# ---------------------------------------------------------------------------

TOOLS: list[anthropic.types.ToolParam] = [
    {
        "name": "list_projects",
        "description": "Listet alle Projekte auf mit Anzahl der Dokumente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_archived": {
                    "type": "boolean",
                    "description": "Auch archivierte Projekte anzeigen (default: false)",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_project_details",
        "description": "Gibt Details zu einem Projekt inkl. Quellen und Dokumentenanzahl.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Projekt-ID"}
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "search_documents",
        "description": "Durchsucht Dokumente nach Name oder Pfad.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchbegriff"},
                "project_id": {
                    "type": "integer",
                    "description": "Einschränken auf Projekt (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max. Anzahl Ergebnisse (default: 20)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_database_stats",
        "description": "Gibt Statistiken über die gesamte Datenbank (Projekte, Quellen, Dokumente, Status-Verteilung).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_documents",
        "description": "Listet Dokumente eines Projekts oder einer Quelle auf.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "source_id": {"type": "integer", "description": "Optional: auf Quelle einschränken"},
                "status": {
                    "type": "string",
                    "description": "Optional: Filter nach Status (registered/parsed/enriched/failed)",
                },
                "limit": {"type": "integer", "description": "Max. Ergebnisse (default: 30)"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "start_sync",
        "description": "Startet die Synchronisation einer SharePoint-Quelle. Läuft im Hintergrund.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "integer", "description": "Quellen-ID"}
            },
            "required": ["source_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool-Ausführung
# ---------------------------------------------------------------------------

def execute_tool(name: str, inputs: dict) -> str:
    """Führt ein Tool aus und gibt das Ergebnis als JSON-String zurück."""
    try:
        if name == "list_projects":
            return _list_projects(inputs)
        elif name == "get_project_details":
            return _get_project_details(inputs)
        elif name == "search_documents":
            return _search_documents(inputs)
        elif name == "get_database_stats":
            return _get_database_stats()
        elif name == "list_documents":
            return _list_documents(inputs)
        elif name == "start_sync":
            return _start_sync(inputs)
        else:
            return json.dumps({"error": f"Unbekanntes Tool: {name}"})
    except Exception as exc:
        logger.exception("Tool-Fehler: %s", name)
        return json.dumps({"error": str(exc)})


def _list_projects(inputs: dict) -> str:
    include_archived = inputs.get("include_archived", False)
    projects = list_projects(include_archived=include_archived)
    result = []
    for p in projects:
        count = project_doc_count(p["id"])
        result.append({
            "id": p["id"],
            "name": p["name"],
            "description": p.get("description"),
            "status": p["status"],
            "dokumente": count,
            "erstellt": p["created_at"][:10],
        })
    return json.dumps(result, ensure_ascii=False)


def _get_project_details(inputs: dict) -> str:
    pid = inputs["project_id"]
    p = get_project(pid)
    sources = list_sources(pid)
    doc_count = project_doc_count(pid)
    return json.dumps({
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
    }, ensure_ascii=False)


def _search_documents(inputs: dict) -> str:
    query = inputs["query"]
    project_id = inputs.get("project_id")
    limit = inputs.get("limit", 20)
    conn = connect()
    try:
        params: list = [f"%{query}%", f"%{query}%"]
        where = "(d.original_name LIKE ? OR d.source_path LIKE ?)"
        if project_id:
            where += " AND d.project_id = ?"
            params.append(project_id)
        rows = conn.execute(
            f"SELECT d.id, d.original_name, d.status, d.size_bytes, d.source_path, "
            f"d.project_id, d.source_id FROM documents d WHERE {where} "
            f"ORDER BY d.original_name LIMIT ?",
            params + [limit],
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)
    finally:
        conn.close()


def _get_database_stats() -> str:
    conn = connect()
    try:
        stats = {}
        stats["projekte"] = conn.execute("SELECT COUNT(*) FROM projects WHERE status='active'").fetchone()[0]
        stats["quellen"] = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        stats["dokumente_gesamt"] = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM documents GROUP BY status"
        ).fetchall()
        stats["nach_status"] = {r["status"]: r["n"] for r in rows}
        stats["ordner"] = conn.execute("SELECT COUNT(*) FROM source_folders").fetchone()[0]
        return json.dumps(stats, ensure_ascii=False)
    finally:
        conn.close()


def _list_documents(inputs: dict) -> str:
    project_id = inputs["project_id"]
    source_id = inputs.get("source_id")
    status = inputs.get("status")
    limit = inputs.get("limit", 30)
    conn = connect()
    try:
        params: list = [project_id]
        where = "d.project_id = ?"
        if source_id:
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
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)
    finally:
        conn.close()


def _start_sync(inputs: dict) -> str:
    """Startet einen Sync — gibt sofort zurück, läuft in Hintergrundthread."""
    import threading
    from ..sharepoint.auth import MSALTokenManager
    from ..sharepoint.graph import GraphClient
    from ..sharepoint.sync import SharePointSyncer

    source_id = inputs["source_id"]
    if not settings.msal_tenant_id or not settings.msal_client_id:
        return json.dumps({"error": "MSAL_TENANT_ID / MSAL_CLIENT_ID nicht konfiguriert."})

    try:
        source = get_source(source_id)
    except KeyError:
        return json.dumps({"error": f"Quelle {source_id} nicht gefunden."})

    def run():
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

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return json.dumps({
        "status": "gestartet",
        "source_id": source_id,
        "source_name": source["name"],
        "hinweis": "Sync läuft im Hintergrund. Status über get_project_details abrufbar.",
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Streaming-Agent
# ---------------------------------------------------------------------------

async def stream_response(
    messages: list[dict],
) -> AsyncGenerator[str, None]:
    """Streamt eine Claude-Antwort als Server-Sent-Events (text/delta chunks).

    Yields:
        JSON-kodierte Strings: {"type": "text", "text": "..."} oder
                               {"type": "tool_use", "name": "...", "result": "..."} oder
                               {"type": "done"}
    """
    if not settings.anthropic_api_key:
        yield json.dumps({"type": "error", "text": "ANTHROPIC_API_KEY nicht konfiguriert."})
        return

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Agenten-Schleife: Tool Use kann mehrere Runden erfordern
    current_messages = list(messages)

    while True:
        with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=current_messages,
        ) as stream:
            full_response = stream.get_final_message()

        # Text-Inhalte streamen
        for block in full_response.content:
            if block.type == "text":
                yield json.dumps({"type": "text", "text": block.text})

        # Abbruch wenn kein Tool Use
        if full_response.stop_reason != "tool_use":
            yield json.dumps({"type": "done"})
            break

        # Tool Use ausführen
        tool_results = []
        for block in full_response.content:
            if block.type == "tool_use":
                yield json.dumps({
                    "type": "tool_use",
                    "name": block.name,
                    "input": block.input,
                })
                result = execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        # Nächste Runde mit Tool-Ergebnissen
        current_messages = current_messages + [
            {"role": "assistant", "content": full_response.content},
            {"role": "user", "content": tool_results},
        ]
