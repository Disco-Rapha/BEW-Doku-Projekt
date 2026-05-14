"""PDF/DWG → PNG-Renderer + Convenience-Wrapper fuer multimodale Vision-Calls.

Ergaenzt die bestehende Vision-Engine `disco.docs.image.extract`, die PNG-/JPG-/
TIFF-Bild-Dateien akzeptiert, aber selbst weder PDFs noch DWGs rendern kann.
Mit diesem Modul kann Disco eine technische Zeichnung (PDF oder DWG) in einen
Vision-tauglichen PNG verwandeln und an die multimodale Engine schicken.

Verwendung:

    from disco.docs.render import classify_drawing
    result = classify_drawing(
        abs_path=Path(".../plan.pdf"),
        engine="image-gpt5-vision",
    )
    # result enthaelt: markdown, meta (estimated_cost_eur, usage, ...)

Oder Schritt fuer Schritt:

    from disco.docs.render import pdf_to_png, dwg_to_png
    from disco.docs import image
    png_path = pdf_to_png(plan_pdf)
    markdown, meta = image.extract(png_path, engine="image-gpt5-vision")
    print(meta["estimated_cost_eur"])

Cost-Visibility ist `out of the box`: `image.extract()` returnt
`estimated_cost_eur` im meta_dict. Der Wert kommt aus `disco.pricing` mit dem
real-Time-Foundry-Preis fuer das verwendete Deployment.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Default-Aufloesung fuer den PNG-Render. 2048px lange Kante ist ein guter
# Trade-off zwischen Schaerfe (Plan-Symbole lesbar) und Vision-Token-Kosten
# (die image-gpt5-vision-Engine resized intern auf max_long_edge=1568 fuer
# detail=high, siehe disco.docs.image._MAX_LONG_EDGE_PX).
DEFAULT_RENDER_MAX_EDGE_PX = 2048

# Welche PDF-Seite rendern wir? Bei technischen Zeichnungen ist die erste Seite
# fast immer der Plan-Inhalt (Schriftfeld + Layout). Bei mehrseitigen Plaenen
# (z.B. Plan-Sets mit Inhaltsverzeichnis) kann der Caller eine andere Seite
# anfordern.
DEFAULT_PDF_PAGE_INDEX = 0


def pdf_to_png(
    abs_path: Path,
    *,
    page_index: int = DEFAULT_PDF_PAGE_INDEX,
    max_long_edge: int = DEFAULT_RENDER_MAX_EDGE_PX,
    out_path: Path | None = None,
) -> Path:
    """Rendert eine PDF-Seite als PNG.

    Args:
        abs_path: absoluter Pfad zur PDF-Datei.
        page_index: 0-basierter Seitenindex (Default 0 = erste Seite).
        max_long_edge: maximale Pixel-Kantenlaenge des Outputs (Default 2048).
                       Das resultierende Bild ist proportional skaliert, sodass
                       die laengere Kante diese Groesse hat.
        out_path: optional, wohin die PNG geschrieben werden soll. Default:
                  temporaere Datei (vom Caller zu loeschen).

    Returns:
        Pfad zur erzeugten PNG-Datei.
    """
    import fitz  # PyMuPDF

    if not abs_path.is_file():
        raise FileNotFoundError(f"PDF nicht gefunden: {abs_path}")

    doc = fitz.open(abs_path)
    try:
        if page_index < 0 or page_index >= doc.page_count:
            raise ValueError(
                f"page_index={page_index} ausserhalb 0..{doc.page_count - 1}"
            )
        page = doc[page_index]

        # Render-Skala so waehlen, dass die lange Kante max_long_edge erreicht.
        # page.rect ist in PDF-Points (1pt = 1/72 inch). Faktor 1.0 → 72 DPI.
        rect = page.rect
        long_edge_pt = max(rect.width, rect.height)
        # Mindestfaktor 1.0 (= nicht kleiner als das Original-PDF-Resolution).
        scale = max(1.0, max_long_edge / long_edge_pt) if long_edge_pt > 0 else 1.0
        matrix = fitz.Matrix(scale, scale)

        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        png_bytes = pixmap.tobytes("png")
    finally:
        doc.close()

    if out_path is None:
        fd, tmp = tempfile.mkstemp(prefix=f"disco-render-{abs_path.stem}-", suffix=".png")
        out_path = Path(tmp)
        import os as _os
        _os.close(fd)
    out_path.write_bytes(png_bytes)
    logger.debug(
        "pdf_to_png: %s page=%d → %s (%.1f KB, scale=%.2f)",
        abs_path.name, page_index, out_path, len(png_bytes) / 1024, scale,
    )
    return out_path


def dwg_to_png(
    abs_path: Path,
    *,
    max_long_edge: int = DEFAULT_RENDER_MAX_EDGE_PX,
    out_path: Path | None = None,
) -> Path:
    """Rendert eine DWG-Datei als PNG (via DXF + ezdxf-matplotlib-Backend).

    Pipeline:
      DWG → DXF (libredwg `dwg2dxf`)
        → DXF mit ezdxf laden (+ Sanitizer, weil libredwg manchmal kaputten DXF
          produziert)
        → ezdxf.addons.drawing.matplotlib.qsave als PNG

    Args:
        abs_path: absoluter Pfad zur DWG-Datei.
        max_long_edge: maximale Pixel-Kantenlaenge des Outputs (Default 2048).
        out_path: optional, wohin die PNG geschrieben werden soll. Default:
                  temporaere Datei.

    Returns:
        Pfad zur erzeugten PNG-Datei.

    Raises:
        FileNotFoundError: DWG nicht da
        RuntimeError: libredwg nicht installiert oder DWG kaputt
    """
    if not abs_path.is_file():
        raise FileNotFoundError(f"DWG nicht gefunden: {abs_path}")

    from disco.docs._dwg_libredwg import convert_dwg_to_dxf, sanitize_libredwg_dxf

    # 1) DWG → DXF (vorhandener Pfad mit Sanitizer)
    with tempfile.TemporaryDirectory(prefix="disco-dwg-render-") as tmpdir:
        tmp_dxf = Path(tmpdir) / (abs_path.stem + ".dxf")
        convert_dwg_to_dxf(abs_path, tmp_dxf)
        # Sanitizer entfernt SORTENTSTABLE etc. (libredwg-Quirks)
        tmp_dxf = sanitize_libredwg_dxf(tmp_dxf)

        # 2) DXF → matplotlib-Rendering → PNG
        import ezdxf
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        import matplotlib
        matplotlib.use("Agg")  # headless
        import matplotlib.pyplot as plt

        try:
            # `recover.readfile` ist robuster bei libredwg-Quirks im DXF —
            # `ezdxf.readfile` strict, `recover` auditiert + repariert.
            from ezdxf import recover
            doc, _audit = recover.readfile(str(tmp_dxf))
        except Exception as exc:
            raise RuntimeError(f"DXF nicht lesbar nach DWG-Konvertierung: {exc}") from exc

        msp = doc.modelspace()
        # Bild-DPI so, dass die lange Kante max_long_edge erreicht.
        # matplotlib-Figure ist in inches; Faustregel: DPI 150 + figsize 12
        # ergibt ~1800px-Kante. Wir nehmen 200 DPI + skaliertes figsize.
        dpi = 200
        fig_inches = max_long_edge / dpi
        fig, ax = plt.subplots(figsize=(fig_inches, fig_inches), dpi=dpi)
        ctx = RenderContext(doc)
        backend = MatplotlibBackend(ax)
        try:
            Frontend(ctx, backend).draw_layout(msp, finalize=True)
        except Exception as exc:
            plt.close(fig)
            raise RuntimeError(f"DXF-Rendering fehlgeschlagen: {exc}") from exc

        if out_path is None:
            fd, tmp = tempfile.mkstemp(prefix=f"disco-render-{abs_path.stem}-", suffix=".png")
            out_path = Path(tmp)
            import os as _os
            _os.close(fd)
        # tight bbox + transparenter Hintergrund nicht — Vision-Modell
        # bevorzugt sauberen weissen Hintergrund.
        ax.set_facecolor("white")
        fig.patch.set_facecolor("white")
        fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    logger.debug(
        "dwg_to_png: %s → %s (%.1f KB)",
        abs_path.name, out_path, out_path.stat().st_size / 1024,
    )
    return out_path


def classify_drawing(
    abs_path: Path,
    *,
    engine: str = "image-gpt5-vision",
    pdf_page_index: int = DEFAULT_PDF_PAGE_INDEX,
    max_long_edge: int = DEFAULT_RENDER_MAX_EDGE_PX,
    model_deployment: str | None = None,
    cleanup_tmp: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Vereinheitlichter Vision-Pfad fuer PDF UND DWG.

    Rendert die Quelldatei zu PNG, ruft die multimodale Vision-Engine, und
    gibt (markdown, meta) zurueck. meta enthaelt:

      - estimated_cost_eur: float
      - usage: {prompt_tokens, completion_tokens, cached_tokens}
      - source_file: str (Pfad zur Quelldatei)
      - render_format: 'pdf' | 'dwg'
      - rendered_png: str (temp-PNG-Pfad, falls cleanup_tmp=False)

    Cost-Visibility: estimated_cost_eur wird vom Foundry-Pricing-Modul
    (`disco.pricing`) basierend auf den real angefallenen Tokens + dem
    aktuellen Preis fuer das Deployment berechnet.

    Args:
        abs_path: PDF oder DWG zum Klassifizieren.
        engine: Vision-Engine-ID (Default `image-gpt5-vision`).
        pdf_page_index: bei PDFs welche Seite (Default 0 = erste).
        max_long_edge: PNG-Auflosung Long-Edge (Default 2048).
        model_deployment: optional Foundry-Deployment-Override.
        cleanup_tmp: wenn True (Default), wird der Render-PNG nach dem Call
                     geloescht. Bei False bleibt er fuer Debugging in /tmp.

    Returns:
        (markdown_response, meta_dict)
    """
    from disco.docs import image as image_engine

    suffix = abs_path.suffix.lower()
    if suffix == ".pdf":
        render_format = "pdf"
        png_path = pdf_to_png(
            abs_path, page_index=pdf_page_index, max_long_edge=max_long_edge
        )
    elif suffix == ".dwg":
        render_format = "dwg"
        png_path = dwg_to_png(abs_path, max_long_edge=max_long_edge)
    elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".tif"):
        # Schon ein Bild — direkt durch.
        render_format = "image"
        png_path = abs_path
    else:
        raise ValueError(
            f"classify_drawing: unsupported extension {suffix!r} fuer {abs_path}"
        )

    try:
        markdown, meta = image_engine.extract(
            png_path, engine=engine, model_deployment=model_deployment
        )
        meta = dict(meta)
        meta["source_file"] = str(abs_path)
        meta["render_format"] = render_format
        if render_format != "image":
            meta["rendered_png"] = str(png_path)
        return markdown, meta
    finally:
        if cleanup_tmp and render_format != "image":
            try:
                png_path.unlink(missing_ok=True)
            except OSError:
                pass
