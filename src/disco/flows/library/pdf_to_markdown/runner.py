"""Flow: pdf_to_markdown.

Liest work_pdf_routing (workspace.db), ruft den Engine-Dispatcher und
schreibt das Markdown-Ergebnis nach ds.agent_pdf_markdown (datastore.db).
JOIN gegen ds.agent_pdf_inventory fuer den Quell-Hash.

Ebenen-Hinweis (Stufe 1 Architektur):
  - work_pdf_routing   → Ebene 3, in workspace.db als `main` → ohne Praefix.
  - agent_pdf_inventory → Ebene 2, in datastore.db (ATTACH `ds`) → `ds.`-Praefix.
  - agent_pdf_markdown  → Ebene 2, in datastore.db → `ds.`-Praefix.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from disco.flows.sdk import FlowRun, run_context
from disco.pdf import ENGINES, extract_markdown


ALLOWED_ENGINES = set(ENGINES)


def load_items(
    run: FlowRun,
    *,
    limit: int | None,
    only_engine: str | None,
    force_rerun: bool,
) -> List[Dict]:
    """Lade zu extrahierende PDFs aus work_pdf_routing + agent_pdf_inventory.

    Default: Zeilen mit unveraendertem source_hash werden uebersprungen.
    force_rerun=True ignoriert die Skip-Logik.
    """
    where = ["w.engine IS NOT NULL", "w.engine != ''"]
    params: list = []

    if only_engine:
        if only_engine not in ALLOWED_ENGINES:
            raise ValueError(
                f"only_engine={only_engine!r} unbekannt. "
                f"Erlaubt: {sorted(ALLOWED_ENGINES)}"
            )
        where.append("w.engine = ?")
        params.append(only_engine)

    if not force_rerun:
        where.append(
            "NOT EXISTS ("
            "  SELECT 1 FROM ds.agent_pdf_markdown m "
            "  WHERE m.file_id = w.file_id "
            "    AND m.source_hash IS NOT NULL "
            "    AND m.source_hash = a.sha256"
            ")"
        )

    sql = (
        "SELECT w.file_id AS file_id, w.rel_path AS rel_path, "
        "       w.engine AS engine, a.sha256 AS source_hash "
        "FROM work_pdf_routing w "
        "JOIN ds.agent_pdf_inventory a ON a.id = w.file_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY w.file_id"
    )

    rows = run.db.query(sql, params)
    items: List[Dict] = list(rows)
    if limit is not None:
        items = items[:limit]

    run.log(
        f"Extraktions-Input: {len(items)} PDFs "
        f"(only_engine={only_engine!r}, force_rerun={force_rerun}, "
        f"limit={limit if limit is not None else 'none'})"
    )
    return items


def process_item(run: FlowRun, row: Dict) -> Dict:
    file_id = int(row["file_id"])
    rel_path = str(row["rel_path"])
    engine = str(row["engine"])
    source_hash = row.get("source_hash")

    if engine not in ALLOWED_ENGINES:
        raise ValueError(
            f"file_id={file_id}: engine={engine!r} ungueltig. "
            f"Erwartet {sorted(ALLOWED_ENGINES)}."
        )

    abs_path = (run.project_root / rel_path).resolve()
    if not abs_path.is_file():
        raise FileNotFoundError(f"PDF nicht gefunden: {rel_path}")

    md, meta = extract_markdown(abs_path, engine)

    run.db.insert_row(
        "ds.agent_pdf_markdown",
        {
            "file_id": file_id,
            "rel_path": rel_path,
            "engine": engine,
            "md_content": md,
            "char_count": meta["char_count"],
            "source_hash": source_hash,
            "duration_ms": meta["duration_ms"],
            "run_id": run.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="replace",
    )

    cost = float(meta.get("estimated_cost_eur", 0.0))
    if cost > 0:
        run.add_cost(eur=cost)

    run.log(
        f"[markdown] file_id={file_id}, engine={engine}, "
        f"pages={meta['n_pages']}, chars={meta['char_count']}, "
        f"duration={meta['duration_ms']:.0f}ms, "
        f"cost={cost:.4f} EUR"
    )

    return {
        "file_id": file_id,
        "rel_path": rel_path,
        "engine": engine,
        "n_pages": meta["n_pages"],
        "char_count": meta["char_count"],
        "duration_ms": meta["duration_ms"],
        "estimated_cost_eur": cost,
    }


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ja"}
    return False


def main() -> None:
    with run_context(FlowRun.from_env()) as run:
        run.log(f"Flow {run.flow_name} gestartet (run_id={run.run_id})")

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

        only_engine = cfg.get("only_engine")
        if only_engine is not None and not isinstance(only_engine, str):
            only_engine = str(only_engine)
        if only_engine == "":
            only_engine = None

        force_rerun = _parse_bool(cfg.get("force_rerun"))

        items = load_items(
            run,
            limit=limit,
            only_engine=only_engine,
            force_rerun=force_rerun,
        )
        run.set_total(len(items))

        if not items:
            run.log("Keine offenen PDFs fuer Markdown-Extraktion – nichts zu tun.")
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
