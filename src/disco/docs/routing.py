"""Generische Routing-Logik fuer den extraction_routing_decision-Flow.

Entscheidet pro Datei (egal welches Format) eine Engine. Heuristiken sind
pro file_kind organisiert; PDF nutzt die bewaehrte 3-Tier-Logik aus dem
alten pdf_routing_decision-Runner.

Output: (engine, reason, heuristics_dict)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import file_kind_from_path

logger = logging.getLogger(__name__)

ROUTER_VERSION = "router-v3.0"


# ---------------------------------------------------------------------------
# Top-Level: pro Datei eine Routing-Entscheidung
# ---------------------------------------------------------------------------


def decide(rel_path: str, abs_path: Path, file_role: str = "source") -> dict[str, Any]:
    """Routing-Entscheidung fuer eine Datei.

    Args:
      rel_path: Pfad relativ zum Projekt-Root (z.B. "sources/Geprueft/foo.pdf")
      abs_path: absoluter Filesystem-Pfad
      file_role: "source" oder "context" (aus agent_sources.kind)

    Returns: dict mit
      file_kind: 'pdf' | 'excel' | 'dwg' | 'image' | 'other'
      engine:    konkrete Engine-ID (z.B. 'pdf-azure-di-hr')
      reason:    Klartext-Begruendung
      heuristics: format-spezifische Heuristik-Werte
      router_version
    """
    file_kind = file_kind_from_path(abs_path)

    if file_kind == "pdf":
        engine, reason, heur = _decide_pdf(abs_path)
    elif file_kind == "excel":
        engine, reason, heur = _decide_excel(abs_path, file_role)
    elif file_kind == "dwg":
        engine, reason, heur = _decide_dwg(abs_path)
    elif file_kind == "image":
        engine, reason, heur = _decide_image(abs_path)
    else:
        engine, reason, heur = "skip", f"unsupported file_kind={file_kind}", {}

    return {
        "file_kind": file_kind,
        "engine": engine,
        "reason": reason,
        "heuristics": heur,
        "router_version": ROUTER_VERSION,
    }


# ---------------------------------------------------------------------------
# PDF-Routing — Sticky-Rules wie pdf_routing_decision-Runner
# ---------------------------------------------------------------------------

# Diese Konstanten spiegeln die heutige Pipeline (Stand 2026-04-25)
_PLAN_FORMAT_MIN_WIDTH_PT = 1000.0
_LARGE_IMAGE_MIN_COVERAGE = 0.60


def _decide_pdf(abs_path: Path) -> tuple[str, str, dict[str, Any]]:
    """3-Tier-Routing aus PyMuPDF-Seitenanalyse."""
    import fitz  # PyMuPDF
    from disco.flows.library.pdf_routing_decision.runner import analyze_page

    doc = fitz.open(abs_path)
    stats = [analyze_page(p) for p in doc]
    doc.close()

    n_pages = len(stats)
    kind_counts: dict[str, int] = {
        "empty": 0, "scan": 0, "vector-drawing": 0, "mixed": 0, "text": 0,
    }
    for ps in stats:
        kind_counts[ps.kind] = kind_counts.get(ps.kind, 0) + 1

    n_scan = kind_counts.get("scan", 0)
    n_vdraw = kind_counts.get("vector-drawing", 0)
    n_text = kind_counts.get("text", 0)
    n_mixed = kind_counts.get("mixed", 0)
    max_w = max((ps.width_pt for ps in stats), default=0.0)
    n_big_img = sum(1 for ps in stats if ps.image_coverage > _LARGE_IMAGE_MIN_COVERAGE)
    is_plan = max_w > _PLAN_FORMAT_MIN_WIDTH_PT

    # Sticky-Rules wie heute (Stand 2026-04-25, Bench-bestaetigt):
    if n_vdraw > 0:
        engine = "pdf-azure-di-hr"
        reason = f"{n_vdraw} vector-drawing-Seite(n) → KKS-Labels brauchen HR"
    elif is_plan:
        engine = "pdf-azure-di-hr"
        reason = f"plan-format max_w={max_w:.0f}pt > {_PLAN_FORMAT_MIN_WIDTH_PT:.0f}"
    elif n_big_img > 0:
        engine = "pdf-azure-di-hr"
        reason = f"{n_big_img} Seite(n) mit image_coverage > {_LARGE_IMAGE_MIN_COVERAGE:.2f}"
    elif n_scan > 0:
        engine = "pdf-azure-di"
        reason = f"{n_scan} A4-Scan-Seite(n) ohne Plan/Grossbild"
    else:
        # Bench 2026-04-25 hat bestaetigt: docling halluziniert auf
        # ~4% der Text-PDFs. Default bleibt deshalb azure-di.
        engine = "pdf-azure-di"
        reason = (
            f"text-dominant ({n_text}t/{n_mixed}m) → azure-di "
            f"(Default seit Bench-Entscheid 2026-04-25)"
        )

    heur = {
        "n_pages": n_pages,
        "kind_counts": kind_counts,
        "n_scan_pages": n_scan,
        "n_vdrawing_pages": n_vdraw,
        "n_text_pages": n_text,
        "n_mixed_pages": n_mixed,
        "max_page_width_pt": max_w,
        "n_large_image_pages": n_big_img,
    }
    return engine, reason, heur


# ---------------------------------------------------------------------------
# Excel-Routing
# ---------------------------------------------------------------------------


def _decide_excel(abs_path: Path, file_role: str) -> tuple[str, str, dict[str, Any]]:
    """Excel: in context/ → table-import, in sources/ → openpyxl-Markdown.

    Beide Engines liefern Markdown; bei excel-table-import erzeugt der
    Extraction-Flow zusaetzlich SQL-Tabellen unter context_<slug>.
    """
    if file_role == "context":
        engine = "excel-table-import"
        reason = "context-Excel → automatischer SQL-Tabellen-Import + Markdown"
    else:
        engine = "excel-openpyxl"
        reason = "sources-Excel → Markdown-Extraktion fuer Suche/LLM"

    # Quick-Inspect fuer heuristics_json
    heur: dict[str, Any] = {"file_role": file_role}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(abs_path, read_only=True, data_only=True)
        heur["sheet_names"] = list(wb.sheetnames)
        heur["n_sheets"] = len(wb.sheetnames)
        wb.close()
    except Exception as exc:
        heur["inspect_error"] = str(exc)

    return engine, reason, heur


# ---------------------------------------------------------------------------
# DWG-Routing — heute eine Engine
# ---------------------------------------------------------------------------


def _decide_dwg(abs_path: Path) -> tuple[str, str, dict[str, Any]]:
    suffix = abs_path.suffix.lower()
    engine = "dwg-ezdxf-local"
    if suffix == ".dxf":
        reason = "DXF (Text-Format) → ezdxf direkt"
    else:
        reason = "DWG → ezdxf via ODA File Converter"
    return engine, reason, {"format": suffix.lstrip(".")}


# ---------------------------------------------------------------------------
# Image-Routing — heute eine Engine
# ---------------------------------------------------------------------------


def _decide_image(abs_path: Path) -> tuple[str, str, dict[str, Any]]:
    engine = "image-gpt5-vision"
    reason = "Bild → GPT-5.1 Vision (Beschreibung + OCR + strukturierte Erkennung)"

    heur: dict[str, Any] = {}
    try:
        from PIL import Image
        with Image.open(abs_path) as img:
            heur["width"] = img.size[0]
            heur["height"] = img.size[1]
            heur["mode"] = img.mode
    except Exception as exc:
        heur["inspect_error"] = str(exc)
    heur["size_bytes"] = abs_path.stat().st_size

    return engine, reason, heur


__all__ = ["decide", "ROUTER_VERSION"]
