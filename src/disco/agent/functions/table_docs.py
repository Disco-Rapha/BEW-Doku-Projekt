"""Schicht 3 der Memory-Reform — Tabellen-Wissen am Tabellen-Objekt.

Disco pflegt zu jeder Projekt-Tabelle (`work_*`/`agent_*`/`context_*`)
eine kurze Beschreibung in `agent_table_docs` (workspace.db, Migration
008). Damit:

- bleibt DISCO.md frei von Tabellen-Listen, die nach jeder
  Schema-Änderung händisch nachgepflegt werden müssten,
- kann Disco gezielt per SQL nach Tabellen-Beschreibungen suchen
  (`SELECT * FROM agent_table_docs WHERE description LIKE '%KKS%'`),
- haben wir ein Update-Trail (`updated_at`).

Zwei Tools:

- `table_doc_set` — Upsert pro Tabelle
- `table_doc_get` — Single-Row-Lookup

System-Prompt-Regel: Beim Anlegen einer neuen Reasoning-Tabelle pflegt
Disco direkt `table_doc_set`. Beim Reasoning auf einer bestehenden
Tabelle prüft er mit `table_doc_get`, was drinsteht, bevor er rät.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from ..context import get_workspace_db_path
from . import register


_VALID_LAYERS = ("workspace", "datastore", "context")


def _connect_workspace() -> sqlite3.Connection:
    ws_path = get_workspace_db_path()
    if ws_path is None:
        raise RuntimeError(
            "Kein aktives Projekt — table_doc-Tools brauchen einen "
            "Projekt-Kontext mit workspace.db."
        )
    conn = sqlite3.connect(str(ws_path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Defensive Schema-Erstellung — falls Migration 008 noch nicht
    durchlaufen ist (z.B. in frischen Test-Projekten ohne Migrations-
    Run). Idempotent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_table_docs (
            table_name      TEXT PRIMARY KEY,
            layer           TEXT NOT NULL
                            CHECK (layer IN ('workspace', 'datastore', 'context')),
            description     TEXT NOT NULL,
            schema_summary  TEXT,
            example_query   TEXT,
            source_files    TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_table_docs_layer ON agent_table_docs(layer)"
    )


# ---------------------------------------------------------------------------
# table_doc_set
# ---------------------------------------------------------------------------


@register(
    name="table_doc_set",
    description=(
        "Upsert für agent_table_docs — pflegt Beschreibung + Schema + "
        "Beispiel-Query + Quell-Files zu einer Projekt-Tabelle.\n\n"
        "**Wann nutzen:** Beim Anlegen einer neuen Reasoning-Tabelle "
        "(work_*/agent_*/context_*) — direkt im selben Schritt. Beim "
        "Update einer Tabelle, wenn sich Schema oder typische Verwendung "
        "ändert.\n\n"
        "Idempotent: re-call mit gleichen Werten überschreibt sich "
        "selbst. `created_at` bleibt erhalten beim Update; nur "
        "`updated_at` wandert."
    ),
    parameters={
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": (
                    "Name der Tabelle, z.B. 'agent_dcc_results'. Muss "
                    "Prefix work_/agent_/context_ haben (Konvention)."
                ),
            },
            "layer": {
                "type": "string",
                "enum": list(_VALID_LAYERS),
                "description": (
                    "'workspace' (in workspace.db), 'datastore' (in "
                    "datastore.db, read-only), oder 'context' (Lookup-"
                    "Tabelle aus context/-Excel)."
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "1-3 Zeilen, was steht drin. Beispiel: 'DCC-"
                    "Klassifikation pro Source-File mit Konfidenz und "
                    "Master-Code. Output des dcc-classify-Flows.'"
                ),
            },
            "schema_summary": {
                "type": "string",
                "description": (
                    "Optionale Schema-Übersicht. Nicht das volle CREATE "
                    "TABLE, sondern eine kompakte Zeile: "
                    "'source_id INTEGER PK, master_dcc TEXT, conf_score REAL'."
                ),
            },
            "example_query": {
                "type": "string",
                "description": (
                    "Optionaler typischer SELECT, der zeigt wie die "
                    "Tabelle abgefragt wird. Hilft Disco bei Folge-"
                    "Sessions, das richtige SQL zu schreiben."
                ),
            },
            "source_files": {
                "type": "string",
                "description": (
                    "Optional: Quelle der Tabelle, z.B. 'imported from "
                    "sources/_meta/ibl-2026.xlsx via import_xlsx_to_table'."
                ),
            },
        },
        "required": ["table_name", "layer", "description"],
    },
    returns="{table_name, layer, created (bool), updated_at}",
)
def _table_doc_set(
    *,
    table_name: str,
    layer: str,
    description: str,
    schema_summary: str | None = None,
    example_query: str | None = None,
    source_files: str | None = None,
) -> dict[str, Any]:
    if not table_name or not isinstance(table_name, str):
        raise ValueError("table_name ist Pflicht.")
    if layer not in _VALID_LAYERS:
        raise ValueError(
            f"layer muss einer aus {_VALID_LAYERS} sein, war: {layer!r}"
        )
    if not description or not description.strip():
        raise ValueError("description darf nicht leer sein.")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = _connect_workspace()
    try:
        _ensure_schema(conn)
        existing = conn.execute(
            "SELECT created_at FROM agent_table_docs WHERE table_name = ?",
            (table_name,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE agent_table_docs
                SET layer = ?, description = ?, schema_summary = ?,
                    example_query = ?, source_files = ?, updated_at = ?
                WHERE table_name = ?
                """,
                (
                    layer, description.strip(), schema_summary,
                    example_query, source_files, now, table_name,
                ),
            )
            created = False
        else:
            conn.execute(
                """
                INSERT INTO agent_table_docs
                  (table_name, layer, description, schema_summary,
                   example_query, source_files, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    table_name, layer, description.strip(), schema_summary,
                    example_query, source_files, now, now,
                ),
            )
            created = True
        conn.commit()
        return {
            "table_name": table_name,
            "layer": layer,
            "created": created,
            "updated_at": now,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# table_doc_get
# ---------------------------------------------------------------------------


@register(
    name="table_doc_get",
    description=(
        "Liefert die Beschreibung einer Projekt-Tabelle aus "
        "agent_table_docs. Nutze das, BEVOR Du auf einer Dir nicht "
        "geläufigen Tabelle SQL schreibst — statt blind zu SELECT * und "
        "raten.\n\n"
        "Liefert {found: false} wenn nicht dokumentiert. In dem Fall: "
        "Du schreibst die Doku gerne mit `table_doc_set` nach, sobald "
        "Du verstanden hast was die Tabelle enthält."
    ),
    parameters={
        "type": "object",
        "properties": {
            "table_name": {
                "type": "string",
                "description": "Name der Tabelle, z.B. 'agent_dcc_results'.",
            },
        },
        "required": ["table_name"],
    },
    returns=(
        "{found, table_name, layer?, description?, schema_summary?, "
        "example_query?, source_files?, created_at?, updated_at?}"
    ),
)
def _table_doc_get(*, table_name: str) -> dict[str, Any]:
    if not table_name or not isinstance(table_name, str):
        raise ValueError("table_name ist Pflicht.")
    conn = _connect_workspace()
    try:
        _ensure_schema(conn)
        row = conn.execute(
            """
            SELECT table_name, layer, description, schema_summary,
                   example_query, source_files, created_at, updated_at
            FROM agent_table_docs
            WHERE table_name = ?
            """,
            (table_name,),
        ).fetchone()
        if row is None:
            return {"found": False, "table_name": table_name}
        return {"found": True, **dict(row)}
    finally:
        conn.close()
