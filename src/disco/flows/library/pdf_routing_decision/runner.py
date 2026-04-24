"""Flow: pdf_routing_decision.

3-Tier-Routing pro PDF auf Basis einer PyMuPDF-Seitenanalyse:
  - docling-standard  — reine Text-/Vektor-Dokumente, 0 EUR
  - azure-di          — Scans auf Normalformat, Standard-OCR reicht
  - azure-di-hr       — Vektor-Zeichnungen, Plan-Format (A3+),
                        oder Grossbild-Seiten → 4x DPI-OCR noetig
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import fitz  # PyMuPDF

from disco.flows.sdk import FlowRun, run_context


# --- Datenstrukturen ---------------------------------------------------------------


@dataclass
class PageStats:
    chars: int
    n_paths: int
    text_coverage: float
    vector_coverage: float
    image_coverage: float
    n_images: int
    width_pt: float
    kind: str


# --- 3-Tier-Schwellen --------------------------------------------------------------

# Max-Seitenbreite > 1000 pt fängt A3-Landscape (1191 pt) und grösser.
# A4-Landscape ist 842 pt und soll NICHT getriggert werden.
_PLAN_FORMAT_MIN_WIDTH_PT = 1000.0

# Seiten mit image_coverage > 0.6 gelten als "Grossbild-Seite" —
# typisch: eingeklebtes Foto, Explosionszeichnung, Fein-Skizze.
_LARGE_IMAGE_MIN_COVERAGE = 0.60


# --- Seitenanalyse mit PyMuPDF -----------------------------------------------------


def analyze_page(page: fitz.Page) -> PageStats:
    """Ermittle Basis-Signale und Seiten-kind für eine Seite."""

    # Geometrie
    rect = page.rect
    page_area = float(rect.width * rect.height) if rect.width and rect.height else 0.0

    # Text
    text = page.get_text("text") or ""
    chars = len(text)

    text_area = 0.0
    try:
        blocks = page.get_text("blocks") or []
    except Exception:
        blocks = []
    for b in blocks:
        # b: (x0, y0, x1, y1, text, block_no, block_type, ...)
        if len(b) >= 5 and isinstance(b[4], str) and b[4].strip():
            x0, y0, x1, y1 = b[0], b[1], b[2], b[3]
            text_area += max(0.0, float(x1 - x0) * float(y1 - y0))

    # Vektorpfade
    n_paths = 0
    vector_area = 0.0
    try:
        drawings = page.get_drawings() or []
    except Exception:
        drawings = []
    for d in drawings:
        items = d.get("items") or []
        n_paths += len(items)
        rect_d = d.get("rect")
        if rect_d is not None:
            vector_area += float(rect_d.width * rect_d.height)

    # Bilder
    image_area = 0.0
    n_images = 0
    try:
        images = page.get_images(full=True) or []
    except Exception:
        images = []
    for img in images:
        xref = img[0]
        try:
            r = page.get_image_bbox(xref)
        except Exception:
            continue
        n_images += 1
        image_area += float(r.width * r.height)

    if page_area > 0:
        text_coverage = min(text_area / page_area, 1.0)
        vector_coverage = min(vector_area / page_area, 1.0)
        image_coverage = min(image_area / page_area, 1.0)
    else:
        text_coverage = vector_coverage = image_coverage = 0.0

    kind = decide_kind(
        chars=chars,
        n_paths=n_paths,
        text_coverage=text_coverage,
        vector_coverage=vector_coverage,
        image_coverage=image_coverage,
        n_images=n_images,
    )

    return PageStats(
        chars=chars,
        n_paths=n_paths,
        text_coverage=text_coverage,
        vector_coverage=vector_coverage,
        image_coverage=image_coverage,
        n_images=n_images,
        width_pt=float(rect.width) if rect.width else 0.0,
        kind=kind,
    )


def decide_kind(
    chars: int,
    n_paths: int,
    text_coverage: float,
    vector_coverage: float,
    image_coverage: float,
    n_images: int,
) -> str:
    """Neue Seiten-kind-Hierarchie gemäß Spezifikation."""

    # 1) empty
    if chars < 20 and n_paths == 0 and image_coverage < 0.10:
        return "empty"

    # 2) klassischer Scan
    if chars < 50 and image_coverage > 0.50:
        return "scan"

    # 3) Scan mit OCR-Layer (NEU)
    if (
        (vector_coverage + image_coverage) > 0.50
        and text_coverage < 0.40
        and chars < 3500
    ):
        return "scan"

    # 4) Text-Dominanz
    if chars >= 1000 and text_coverage >= 0.30:
        # Viel Grafik?
        has_heavy_graphics = (
            vector_coverage > 0.25
            or image_coverage > 0.15
            or n_paths > 50
            or n_images > 1
        )
        if has_heavy_graphics:
            return "mixed"
        return "text"

    # 5) Vektorzeichnung
    if vector_coverage > 0.40 and chars < 500:
        return "vector-drawing"

    # 6) Rest
    if chars >= 100 and vector_coverage > 0.10:
        return "mixed"

    return "text"


# --- Item-Loader -------------------------------------------------------------------

# Schema von `work_pdf_routing` liegt in `migrations/project/007_pdf_pipeline_tables.sql`;
# der Runner-Host (flows/service.py) wendet alle Projekt-Migrationen vor jedem Run an,
# daher braucht dieser Runner keinen eigenen CREATE/ALTER-Fallback mehr.


def load_items(
    run: FlowRun,
    limit: int | None,
    rerun_where_engine: str | None = None,
) -> List[Dict]:
    """Lade PDF-Items aus agent_pdf_inventory.

    Default: skip bereits geroutete file_ids (Resume-Semantik).
    Rerun-Mode (``rerun_where_engine`` gesetzt): waehle genau die file_ids,
    die in ``work_pdf_routing`` aktuell mit dieser engine markiert sind,
    und route sie mit der aktuellen Heuristik neu.
    """

    if rerun_where_engine:
        sql = (
            "SELECT a.id AS file_id, a.rel_path "
            "FROM agent_pdf_inventory a "
            "JOIN work_pdf_routing w ON w.file_id = a.id "
            "WHERE w.engine = ? "
            "ORDER BY RANDOM()"
        )
        rows = run.db.query(sql, [rerun_where_engine])
        items: List[Dict] = list(rows)
        if limit is not None:
            items = items[:limit]
        run.log(
            f"Routing-Input (Rerun-Mode engine={rerun_where_engine!r}): "
            f"{len(items)} PDFs werden mit neuer Heuristik neu geroutet "
            f"(limit={limit if limit is not None else 'none'})."
        )
        return items

    # Default: Resume — skip bereits verarbeitete.
    processed_rows = run.db.query("SELECT file_id FROM work_pdf_routing")
    processed_ids = {r["file_id"] for r in processed_rows}

    rows = run.db.query(
        """
        SELECT id AS file_id, rel_path
        FROM agent_pdf_inventory
        ORDER BY id
        """
    )

    items = []
    for row in rows:
        if row["file_id"] in processed_ids:
            continue
        items.append(row)
        if limit is not None and len(items) >= limit:
            break

    run.log(
        f"Routing-Input: {len(items)} offene PDFs "
        f"(limit={limit if limit is not None else 'none'}, "
        f"bereits geroutet={len(processed_ids)})"
    )
    return items


# --- Pro-Item-Logik ----------------------------------------------------------------


def process_item(run: FlowRun, row: Dict) -> Dict:
    file_id = row["file_id"]
    rel_path = row["rel_path"]
    pdf_path = Path(rel_path)

    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF nicht gefunden: {rel_path}")

    t0 = time.monotonic()
    doc = fitz.open(pdf_path)
    page_stats: List[PageStats] = [analyze_page(page) for page in doc]
    doc.close()
    duration_ms = (time.monotonic() - t0) * 1000.0

    n_pages = len(page_stats)
    kind_counts: Dict[str, int] = {
        "empty": 0,
        "scan": 0,
        "vector-drawing": 0,
        "mixed": 0,
        "text": 0,
    }
    for ps in page_stats:
        if ps.kind in kind_counts:
            kind_counts[ps.kind] += 1
        else:
            kind_counts[ps.kind] = kind_counts.get(ps.kind, 0) + 1

    n_scan_pages = kind_counts.get("scan", 0)
    n_vdrawing_pages = kind_counts.get("vector-drawing", 0)
    n_text_pages = kind_counts.get("text", 0)
    n_mixed_pages = kind_counts.get("mixed", 0)

    if n_pages > 0:
        share_scan_or_vdrawing = (n_scan_pages + n_vdrawing_pages) / n_pages
    else:
        share_scan_or_vdrawing = 0.0

    # Neue Signale fuer 3-Tier-Routing.
    max_page_width_pt = max((ps.width_pt for ps in page_stats), default=0.0)
    n_large_image_pages = sum(
        1 for ps in page_stats if ps.image_coverage > _LARGE_IMAGE_MIN_COVERAGE
    )
    is_plan_format = max_page_width_pt > _PLAN_FORMAT_MIN_WIDTH_PT

    # 3-Tier-Routing (Sticky-Rules, strikte Reihenfolge).
    if n_vdrawing_pages > 0:
        engine = "azure-di-hr"
        reason = (
            f"{n_vdrawing_pages} vector-drawing-Seite(n) von {n_pages} "
            f"→ KKS-Labels/Zeichnungskopf brauchen HR"
        )
    elif is_plan_format:
        engine = "azure-di-hr"
        reason = (
            f"Plan-Format (max Seitenbreite {max_page_width_pt:.0f} pt > "
            f"{_PLAN_FORMAT_MIN_WIDTH_PT:.0f}) → feine Schriften brauchen HR"
        )
    elif n_large_image_pages > 0:
        engine = "azure-di-hr"
        reason = (
            f"{n_large_image_pages} Seite(n) mit image_coverage > "
            f"{_LARGE_IMAGE_MIN_COVERAGE:.2f} → Detail-OCR braucht HR"
        )
    elif n_scan_pages > 0:
        engine = "azure-di"
        reason = (
            f"{n_scan_pages} A4-Scan-Seite(n) von {n_pages} ohne "
            f"Plan/Grossbild/Vektorzeichnung → DI-Standard-OCR reicht"
        )
    else:
        # INTERIM (2026-04-24, User-Entscheid): Standard-Fallback temporaer
        # von 'docling-standard' auf 'azure-di' umgestellt, solange die
        # Docling-Qualitaet nicht ueberzeugt. Die Engine 'docling-standard'
        # bleibt im System erhalten (ALLOWED_ENGINES, bestehende
        # work_pdf_routing/agent_pdf_markdown-Eintraege, Rerun-Mode) —
        # nur neue Routing-Entscheidungen waehlen sie nicht mehr.
        # Zurueckrollen: einfach diesen else-Block wieder auf
        # engine = "docling-standard" setzen.
        engine = "azure-di"
        reason = (
            f"{n_pages} Seiten ohne Scan/Vector-Drawing "
            f"(text={n_text_pages}, mixed={n_mixed_pages}) → "
            f"azure-di (interim, ersetzt docling-standard)"
        )

    run.log(
        f"[routing] file_id={file_id}, pages={n_pages}, "
        f"scan={n_scan_pages}, vdraw={n_vdrawing_pages}, "
        f"maxw={max_page_width_pt:.0f}pt, bigimg={n_large_image_pages}, "
        f"engine={engine}, duration={duration_ms:.1f}ms"
    )

    # Ergebnis in DB (Upsert via REPLACE auf PRIMARY KEY file_id)
    run.db.insert_row(
        "work_pdf_routing",
        {
            "file_id": file_id,
            "rel_path": rel_path,
            "n_pages": n_pages,
            "kind_counts_json": json.dumps(kind_counts, ensure_ascii=False),
            "n_scan_pages": n_scan_pages,
            "n_vdrawing_pages": n_vdrawing_pages,
            "n_text_pages": n_text_pages,
            "n_mixed_pages": n_mixed_pages,
            "share_scan_or_vdrawing": share_scan_or_vdrawing,
            "engine": engine,
            "reason": reason,
            "duration_ms": duration_ms,
            "run_id": run.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "max_page_width_pt": max_page_width_pt,
            "n_large_image_pages": n_large_image_pages,
        },
        on_conflict="replace",
    )

    return {
        "file_id": file_id,
        "rel_path": rel_path,
        "n_pages": n_pages,
        "kind_counts": kind_counts,
        "n_scan_pages": n_scan_pages,
        "n_vdrawing_pages": n_vdrawing_pages,
        "n_text_pages": n_text_pages,
        "n_mixed_pages": n_mixed_pages,
        "share_scan_or_vdrawing": share_scan_or_vdrawing,
        "max_page_width_pt": max_page_width_pt,
        "n_large_image_pages": n_large_image_pages,
        "engine": engine,
        "reason": reason,
        "duration_ms": duration_ms,
    }


# --- main --------------------------------------------------------------------------


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
        if isinstance(limit, (int, float)):
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
            run.log("Keine offenen PDFs für Routing – nichts zu tun.")
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
