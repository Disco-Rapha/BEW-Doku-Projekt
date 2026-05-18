"""Workspace-Validity-Check (Pipeline-Reform v2, Phase C).

Aktuell: `verify_workspace_validity()` — pro work_*/agent_*-Tabelle
in workspace.db (die `source_id`/`file_id` + `source_sha256_pinned`
führt) wird der Validity-Status der Auswertungen bestimmt:

  - valid           — Pin matcht den aktuellen Hash, Source aktiv
  - stale_replaced  — Pin != aktueller Hash (neue Version der Datei)
  - stale_deleted   — Source.status='deleted' (Datei nicht mehr da)
  - no_pin          — pin IST NULL (Bestand vor Phase-C-Migration oder Orphan)
  - orphan          — Source existiert nicht mal in pre_migration

Nützlich für Disco's Reasoning: "Reports auf welcher Datenbasis
gerade valide sind, und welche stale-Annotationen Re-Run brauchen".
"""
from __future__ import annotations

import sqlite3
from typing import Any

from ..context import get_datastore_db_path, get_workspace_db_path
from . import register


SOURCE_REF_COLUMNS = ("source_id", "file_id")


def _connect() -> sqlite3.Connection:
    ws = get_workspace_db_path()
    ds = get_datastore_db_path()
    if ws is None or ds is None:
        raise ValueError("Kein aktives Projekt — kann Validity nicht prüfen.")
    conn = sqlite3.connect(str(ws), timeout=3.0)
    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE '{ds}' AS ds")
    return conn


def _find_pin_tables(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Findet work_*/agent_*-Tabellen mit (source_id|file_id) UND source_sha256_pinned."""
    tables = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' "
            "AND (name LIKE 'work_%' OR name LIKE 'agent_%') "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_disco%'"
        ).fetchall()
    ]
    out: list[tuple[str, str]] = []
    for tbl in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{tbl}')").fetchall()]
        if "source_sha256_pinned" not in cols:
            continue
        ref = next((c for c in cols if c in SOURCE_REF_COLUMNS), None)
        if ref is None:
            continue
        out.append((tbl, ref))
    return out


@register(
    name="verify_workspace_validity",
    description=(
        "Prüft pro Workspace-Tabelle, ob die referenzierten datastore-"
        "Inhalte noch dem Stand zum Auswertungs-Zeitpunkt entsprechen. "
        "Liest alle work_*/agent_*-Tabellen mit den Pflicht-Spalten "
        "source_id (oder file_id) + source_sha256_pinned (Pipeline-Reform "
        "v2 Konvention) und liefert pro Tabelle die Verteilung:\n\n"
        "- valid           — Pin matcht aktuellen Hash, Source aktiv\n"
        "- stale_replaced  — Hash hat sich geändert (neue Version)\n"
        "- stale_deleted   — Source ist deleted\n"
        "- no_pin          — pin IS NULL (Bestand vor Phase-C oder Orphan)\n"
        "- orphan          — Source existiert gar nicht mehr in agent_sources\n\n"
        "Ergebnis ist BEWUSST kompakt — bei Bedarf kann der Caller die "
        "Detail-Zeilen per sqlite_query ziehen."
    ),
    parameters={
        "type": "object",
        "properties": {
            "table": {
                "type": "string",
                "description": (
                    "Optional: nur diese eine Tabelle prüfen. Sonst alle "
                    "pinnbaren work_*/agent_*-Tabellen."
                ),
            },
        },
        "required": [],
    },
    returns=(
        "{tables: [{name, source_ref_column, total, valid, stale_replaced, "
        "stale_deleted, no_pin, orphan}], summary: {n_tables, total, "
        "total_valid, total_stale, total_no_pin}}"
    ),
)
def _verify_workspace_validity(*, table: str | None = None) -> dict[str, Any]:
    conn = _connect()
    try:
        tables = _find_pin_tables(conn)
        if table is not None:
            tables = [(t, c) for (t, c) in tables if t == table]
            if not tables:
                return {
                    "error": f"Tabelle {table!r} hat keine "
                    "(source_id|file_id) + source_sha256_pinned-Spalten."
                }

        results = []
        sum_total = sum_valid = sum_stale = sum_no_pin = sum_orphan = 0
        for tbl, ref in tables:
            row = conn.execute(f"""
                SELECT
                  COUNT(*) AS total,
                  SUM(CASE
                    WHEN t.source_sha256_pinned IS NULL THEN 0
                    WHEN s.id IS NULL THEN 0
                    WHEN s.status = 'deleted' THEN 0
                    WHEN s.sha256 != t.source_sha256_pinned THEN 0
                    ELSE 1 END) AS n_valid,
                  SUM(CASE
                    WHEN t.source_sha256_pinned IS NULL THEN 0
                    WHEN s.id IS NULL THEN 0
                    WHEN s.status != 'deleted' AND s.sha256 != t.source_sha256_pinned THEN 1
                    ELSE 0 END) AS n_stale_replaced,
                  SUM(CASE
                    WHEN t.source_sha256_pinned IS NULL THEN 0
                    WHEN s.id IS NOT NULL AND s.status = 'deleted' THEN 1
                    ELSE 0 END) AS n_stale_deleted,
                  SUM(CASE
                    WHEN t.source_sha256_pinned IS NULL THEN 1
                    ELSE 0 END) AS n_no_pin,
                  SUM(CASE
                    WHEN t.source_sha256_pinned IS NOT NULL AND s.id IS NULL THEN 1
                    ELSE 0 END) AS n_orphan
                FROM {tbl} t
                LEFT JOIN ds.agent_sources s ON s.id = t.{ref}
            """).fetchone()
            total = int(row["total"] or 0)
            n_valid = int(row["n_valid"] or 0)
            n_stale_replaced = int(row["n_stale_replaced"] or 0)
            n_stale_deleted = int(row["n_stale_deleted"] or 0)
            n_no_pin = int(row["n_no_pin"] or 0)
            n_orphan = int(row["n_orphan"] or 0)
            results.append({
                "name": tbl,
                "source_ref_column": ref,
                "total": total,
                "valid": n_valid,
                "stale_replaced": n_stale_replaced,
                "stale_deleted": n_stale_deleted,
                "no_pin": n_no_pin,
                "orphan": n_orphan,
            })
            sum_total += total
            sum_valid += n_valid
            sum_stale += n_stale_replaced + n_stale_deleted
            sum_no_pin += n_no_pin
            sum_orphan += n_orphan

        return {
            "tables": results,
            "summary": {
                "n_tables": len(results),
                "total_rows": sum_total,
                "total_valid": sum_valid,
                "total_stale": sum_stale,
                "total_no_pin": sum_no_pin,
                "total_orphan": sum_orphan,
            },
        }
    finally:
        conn.close()
