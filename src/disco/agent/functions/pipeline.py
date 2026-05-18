"""Pipeline-Diagnose-Tools.

Aktuell: `pipeline_file_status(rel_path)` — Wrapper ueber die 4
Pipeline-Tabellen, liefert pro Datei den Status aller 6 Schritte.

Zugehöriger Skill: `pipeline-diagnostics` (Reparatur-Workflows,
Failure-Routing-Tabelle, Status-Vokabular).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..context import (
    connect_datastore_rw,
    get_datastore_db_path,
    get_workspace_db_path,
)
from . import register


def _connect_for_pipeline_status() -> sqlite3.Connection:
    """workspace.db oeffnen + datastore.db als 'ds' attachen."""
    ws_path = get_workspace_db_path()
    ds_path = get_datastore_db_path()
    if ws_path is None or ds_path is None:
        raise ValueError("Kein aktives Projekt — kann Pipeline-Status nicht ermitteln.")
    conn = sqlite3.connect(str(ws_path), timeout=3.0)
    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE '{ds_path}' AS ds")
    return conn


@register(
    name="pipeline_file_status",
    description=(
        "Liefert den Pipeline-Status einer einzelnen Datei ueber alle 6 "
        "Schritte (Registrierung, Externe Anreicherung, Kanonik, Routing, "
        "Extraction, Suchindex). Ergebnis ist ein Dict mit pro Schritt: "
        "status (done/pending/failed/done_empty/skipped_unsupported/"
        "skipped_upstream/na) plus diagnostische Detail-Info "
        "(error-Text, engine, retry_count, char_count, ...).\n"
        "\n"
        "Ist Discos erste Anlaufstelle bei Fragen wie 'warum wurde X "
        "nicht extrahiert', 'ist Y im Suchindex', 'hat Z gefailt'. "
        "Detaillierte Reparatur-Workflows + Failure-Routing-Tabelle "
        "stehen im Skill `pipeline-diagnostics`."
    ),
    parameters={
        "type": "object",
        "properties": {
            "rel_path": {
                "type": "string",
                "description": (
                    "Relativ-Pfad zur Datei. Im Hash-zentrierten Modell "
                    "(Pipeline-Reform v2) wird über agent_source_locations "
                    "gesucht. Akzeptiert: (a) relativ zum Rollen-Wurzelordner "
                    "(z.B. 'Elektro/foo.pdf'), (b) mit sources/-/context/-"
                    "Praefix. Tool versucht beide."
                ),
            },
        },
        "required": ["rel_path"],
    },
    returns=(
        "{rel_path, file_id, kind, "
        "step_1_registered: {status, ...}, "
        "step_2_enriched: {status, ...}, "
        "step_3_canonical: {status, ...}, "
        "step_4_routed: {status, engine, error, retry_count, ...}, "
        "step_5_extracted: {status, char_count, error, retry_count, ...}, "
        "step_6_indexed: {status, error, ...}}"
    ),
)
def _pipeline_file_status(*, rel_path: str) -> dict[str, Any]:
    if not rel_path:
        raise ValueError("rel_path ist erforderlich.")

    rel_path = rel_path.strip()
    # Normieren: agent_sources.rel_path ist relativ zum Rollen-Wurzelordner.
    # Wenn der User mit sources/- oder context/-Praefix kommt, abschneiden.
    sources_rel = rel_path
    if rel_path.startswith("sources/"):
        sources_rel = rel_path[len("sources/"):]
    elif rel_path.startswith("context/"):
        sources_rel = rel_path[len("context/"):]

    conn = _connect_for_pipeline_status()
    try:
        # 1. Source via Location finden (Hash-zentriertes Modell):
        #    rel_path lebt in agent_source_locations, source-Identität
        #    in agent_sources.
        row = conn.execute(
            "SELECT s.id, s.kind, l.rel_path AS loc_rel_path, "
            "       s.status AS source_status, l.status AS loc_status, "
            "       s.sha256, s.size_bytes "
            "FROM ds.agent_source_locations l "
            "JOIN ds.agent_sources s ON s.id = l.source_id "
            "WHERE l.rel_path = ? "
            "ORDER BY CASE WHEN l.status='active' THEN 0 ELSE 1 END LIMIT 1",
            (sources_rel,),
        ).fetchone()
        if row is None and rel_path != sources_rel:
            row = conn.execute(
                "SELECT s.id, s.kind, l.rel_path AS loc_rel_path, "
                "       s.status AS source_status, l.status AS loc_status, "
                "       s.sha256, s.size_bytes "
                "FROM ds.agent_source_locations l "
                "JOIN ds.agent_sources s ON s.id = l.source_id "
                "WHERE l.rel_path = ? "
                "ORDER BY CASE WHEN l.status='active' THEN 0 ELSE 1 END LIMIT 1",
                (rel_path,),
            ).fetchone()

        if row is None:
            return {
                "rel_path": rel_path,
                "file_id": None,
                "found": False,
                "step_1_registered": {
                    "status": "pending",
                    "reason": (
                        f"Keine agent_source_locations fuer rel_path={rel_path!r}. "
                        f"Datei ist nicht registriert. Ggf. sources_register laufen lassen."
                    ),
                },
            }

        file_id = int(row["id"])
        kind = row["kind"]
        active = row["source_status"] == "active" and row["loc_status"] == "active"
        sources_rel_actual = row["loc_rel_path"]
        # Projekt-relativer Pfad (mit sources/- oder context/-Praefix)
        role_prefix = "context" if kind == "context" else "sources"
        # Falls die Location schon den Präfix enthält (Bestandsdaten):
        if sources_rel_actual.startswith(f"{role_prefix}/"):
            project_rel = sources_rel_actual
        else:
            project_rel = f"{role_prefix}/{sources_rel_actual}"

        result: dict[str, Any] = {
            "rel_path": project_rel,
            "file_id": file_id,
            "kind": kind,
            "found": True,
        }

        # Schritt 1 — Registrierung
        result["step_1_registered"] = {
            "status": "done" if active else "pending",
            "agent_sources_status": row["status"],
            "sha256_short": (row["sha256"] or "")[:12] if row["sha256"] else None,
            "size_bytes": row["size_bytes"],
        }

        # Schritt 2 — Externe Anreicherung
        # (SharePoint-Connector ist 2026-05-08 entfernt — nur noch
        # agent_source_metadata aus Begleit-Excel.)
        meta_count = conn.execute(
            "SELECT COUNT(*) AS c FROM ds.agent_source_metadata WHERE source_id = ?",
            (file_id,),
        ).fetchone()["c"]
        if meta_count == 0:
            # Ohne Begleit-Excel im Projekt gibt es keinen externen
            # Anreicherungspfad — Schritt 2 ist 'na'.
            enrich_status = "na"
        else:
            enrich_status = "done"
        result["step_2_enriched"] = {
            "status": enrich_status,
            "metadata_rows": meta_count,
        }

        # Schritt 3 — Kanonik (im Hash-Modell strukturell trivial)
        # Jede agent_sources-Zeile IST kanonisch — sie repräsentiert genau
        # einen Inhalt. Mehrere Pfade derselben Datei sind als zusätzliche
        # Locations sichtbar, nicht als Duplikate.
        n_locations = conn.execute(
            "SELECT COUNT(*) AS c FROM ds.agent_source_locations "
            "WHERE source_id = ? AND status = 'active'",
            (file_id,),
        ).fetchone()["c"]
        result["step_3_canonical"] = {
            "status": "done",
            "is_canonical": True,
            "n_active_locations": n_locations,
        }
        is_canonical = True  # Im Hash-Modell immer True

        # Schritt 4 — Routing
        if not is_canonical:
            result["step_4_routed"] = {"status": "skipped_upstream"}
        else:
            r = conn.execute(
                "SELECT engine, reason, error, retry_count "
                "FROM work_extraction_routing WHERE file_id = ?",
                (file_id,),
            ).fetchone()
            if r is None:
                result["step_4_routed"] = {"status": "pending"}
            elif r["error"]:
                result["step_4_routed"] = {
                    "status": "failed",
                    "error": r["error"],
                    "retry_count": r["retry_count"],
                    "engine": r["engine"],
                }
            elif not r["engine"]:
                result["step_4_routed"] = {
                    "status": "skipped_unsupported",
                    "reason": r["reason"],
                    "retry_count": r["retry_count"],
                }
            else:
                result["step_4_routed"] = {
                    "status": "done",
                    "engine": r["engine"],
                    "reason": r["reason"],
                    "retry_count": r["retry_count"],
                }

        # Schritt 5 — Extraction
        if not is_canonical:
            result["step_5_extracted"] = {"status": "skipped_upstream"}
        elif result["step_4_routed"]["status"] in ("skipped_unsupported", "failed"):
            result["step_5_extracted"] = {"status": "skipped_upstream"}
        else:
            d = conn.execute(
                "SELECT engine, char_count, error, retry_count "
                "FROM ds.agent_doc_markdown WHERE file_id = ?",
                (file_id,),
            ).fetchone()
            if d is None:
                result["step_5_extracted"] = {"status": "pending"}
            elif d["error"]:
                result["step_5_extracted"] = {
                    "status": "failed",
                    "error": d["error"],
                    "retry_count": d["retry_count"],
                    "engine": d["engine"],
                }
            elif not d["char_count"]:
                result["step_5_extracted"] = {
                    "status": "done_empty",
                    "engine": d["engine"],
                    "char_count": 0,
                    "retry_count": d["retry_count"],
                }
            else:
                result["step_5_extracted"] = {
                    "status": "done",
                    "engine": d["engine"],
                    "char_count": d["char_count"],
                    "retry_count": d["retry_count"],
                }

        # Schritt 6 — Suchindex
        if result["step_5_extracted"]["status"] not in ("done",):
            result["step_6_indexed"] = {"status": "skipped_upstream"}
        else:
            idx = conn.execute(
                "SELECT n_chunks, indexed_at, error "
                "FROM ds.agent_search_docs WHERE rel_path = ?",
                (project_rel,),
            ).fetchone()
            if idx is None:
                result["step_6_indexed"] = {"status": "pending"}
            elif idx["error"]:
                result["step_6_indexed"] = {
                    "status": "failed",
                    "error": idx["error"],
                }
            else:
                result["step_6_indexed"] = {
                    "status": "done",
                    "n_chunks": idx["n_chunks"],
                    "indexed_at": idx["indexed_at"],
                }

        return result
    finally:
        conn.close()
