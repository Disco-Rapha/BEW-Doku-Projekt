"""Flow: extraction_routing_decision.

Generischer Routing-Flow. Liest alle aktiven Dateien aus
ds.agent_sources und entscheidet pro Datei file_kind + Engine. Schreibt
das Ergebnis nach work_extraction_routing.

Heuristiken pro file_kind sind in disco.docs.routing.decide() gekapselt.

Default: Skip bereits geroutete file_ids (Resume-Semantik).
Rerun-Mode (config rerun_where_engine): nur die file_ids, die heute
einer bestimmten Engine zugewiesen sind, neu routen — fuer Rollouts
neuer Heuristiken.

Ebenen-Hinweis:
  - ds.agent_sources       → Ebene 1, datastore.db (read-only)
  - work_extraction_routing → Ebene 3, workspace.db (main, schreibbar)
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from disco.docs.routing import ROUTER_VERSION, decide
from disco.flows.sdk import FlowRun, run_context


def load_items(
    run: FlowRun,
    *,
    limit: int | None,
    rerun_where_engine: str | None = None,
) -> List[Dict]:
    """PDF / Excel / DWG / Bild aus agent_sources fuer Routing waehlen.

    Filter:
      - Status='active' (nicht missing/superseded)
      - Extension in {pdf, xlsx, xlsm, xls, dwg, dxf, jpg, jpeg, png,
                      tif, tiff, webp, bmp, gif}
    """
    if rerun_where_engine:
        sql = (
            "SELECT s.id AS file_id, s.rel_path, s.kind AS file_role, s.extension "
            "FROM ds.agent_sources s "
            "JOIN work_extraction_routing w ON w.file_id = s.id "
            "WHERE w.engine = ? AND s.status='active' "
            "ORDER BY RANDOM()"
        )
        rows = run.db.query(sql, [rerun_where_engine])
        items: List[Dict] = list(rows)
        if limit is not None:
            items = items[:limit]
        run.log(
            f"Routing-Input (Rerun-Mode engine={rerun_where_engine!r}): "
            f"{len(items)} Dateien werden neu geroutet."
        )
        return items

    # Default: Resume — skip bereits geroutete
    processed_rows = run.db.query("SELECT file_id FROM work_extraction_routing")
    processed_ids = {r["file_id"] for r in processed_rows}

    rows = run.db.query(
        "SELECT id AS file_id, rel_path, kind AS file_role, extension "
        "FROM ds.agent_sources "
        "WHERE status='active' "
        "  AND lower(extension) IN ("
        "    'pdf','xlsx','xlsm','xls','dwg','dxf',"
        "    'jpg','jpeg','png','tif','tiff','webp','bmp','gif'"
        "  ) "
        "ORDER BY id"
    )

    items = []
    for row in rows:
        if row["file_id"] in processed_ids:
            continue
        items.append(row)
        if limit is not None and len(items) >= limit:
            break

    run.log(
        f"Routing-Input: {len(items)} offene Dateien "
        f"(limit={limit if limit is not None else 'none'}, "
        f"bereits geroutet={len(processed_ids)})"
    )
    return items


def process_item(run: FlowRun, row: Dict) -> Dict:
    file_id = int(row["file_id"])
    rel_path = str(row["rel_path"])
    file_role = str(row.get("file_role") or "source")

    # rel_path in agent_sources ist relativ zum Rollen-Wurzelordner
    # (sources/ bzw. context/), NICHT zum Projekt-Root. Praefix
    # entsprechend der file_role voranstellen.
    role_prefix = "context" if file_role == "context" else "sources"
    fs_rel_path = Path(role_prefix) / rel_path
    abs_path = (run.project_root / fs_rel_path).resolve()
    if not abs_path.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {fs_rel_path}")

    t0 = time.monotonic()
    decision = decide(rel_path=rel_path, abs_path=abs_path, file_role=file_role)
    duration_ms = (time.monotonic() - t0) * 1000.0

    file_kind = decision["file_kind"]
    engine = decision["engine"]
    reason = decision["reason"]
    heuristics = decision["heuristics"]

    # PDF-spezifische Felder belasen wir gefuellt fuer Backward-Compat,
    # andere Formate bekommen NULL.
    n_pages = heuristics.get("n_pages")
    kind_counts = heuristics.get("kind_counts")
    n_scan = heuristics.get("n_scan_pages")
    n_vdraw = heuristics.get("n_vdrawing_pages")
    n_text = heuristics.get("n_text_pages")
    n_mixed = heuristics.get("n_mixed_pages")
    max_w = heuristics.get("max_page_width_pt")
    n_big_img = heuristics.get("n_large_image_pages")

    share = None
    if (n_scan is not None or n_vdraw is not None) and n_pages:
        share = ((n_scan or 0) + (n_vdraw or 0)) / max(n_pages, 1)

    run.db.insert_row(
        "work_extraction_routing",
        {
            "file_id": file_id,
            "rel_path": rel_path,
            "file_kind": file_kind,
            "engine": engine,
            "reason": reason,
            "router_version": decision["router_version"],
            "heuristics_json": json.dumps(heuristics, ensure_ascii=False),
            # PDF-Legacy-Felder (NULL wenn nicht-PDF)
            "n_pages": n_pages,
            "kind_counts_json": (
                json.dumps(kind_counts, ensure_ascii=False) if kind_counts else None
            ),
            "n_scan_pages": n_scan,
            "n_vdrawing_pages": n_vdraw,
            "n_text_pages": n_text,
            "n_mixed_pages": n_mixed,
            "share_scan_or_vdrawing": share,
            "max_page_width_pt": max_w,
            "n_large_image_pages": n_big_img,
            # Run-Metadaten
            "duration_ms": duration_ms,
            "run_id": run.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="replace",
    )

    run.log(
        f"[routing] file_id={file_id}, kind={file_kind}, engine={engine}, "
        f"role={file_role}, duration={duration_ms:.1f}ms"
    )

    return {
        "file_id": file_id,
        "rel_path": rel_path,
        "file_kind": file_kind,
        "engine": engine,
        "reason": reason,
        "duration_ms": duration_ms,
    }


def main() -> None:
    with run_context(FlowRun.from_env()) as run:
        run.log(
            f"Flow {run.flow_name} gestartet (run_id={run.run_id}, "
            f"router_version={ROUTER_VERSION})"
        )

        cfg = run.config or {}
        limit = cfg.get("limit")
        if isinstance(limit, str):
            try:
                limit = int(limit)
            except ValueError:
                limit = None
        elif isinstance(limit, (int, float)):
            limit = int(limit)
        else:
            limit = None

        rerun_where_engine = cfg.get("rerun_where_engine")
        if rerun_where_engine is not None and not isinstance(rerun_where_engine, str):
            rerun_where_engine = str(rerun_where_engine)
        if rerun_where_engine == "":
            rerun_where_engine = None

        items = load_items(
            run,
            limit=limit,
            rerun_where_engine=rerun_where_engine,
        )
        run.set_total(len(items))

        if not items:
            run.log("Keine offenen Dateien fuer Routing – nichts zu tun.")
            return

        for row in items:
            file_id = row["file_id"]

            def work(it=row) -> Dict:
                return process_item(run, it)

            run.process(
                input_ref=f"file:{file_id}",
                fn=work,
                max_retries=1,
            )


if __name__ == "__main__":
    main()
