"""PDF-Tools: Text-Extraktion (pypdf) + Seiten-Klassifikation (PyMuPDF).

Design:
  - Nur Dateien unter settings.data_dir.
  - Seiten-Range ist 1-basiert (menschenfreundlich).
  - Zeichen-Limit gegen Kontext-Explosion.
  - pdf_extract_text: pypdf, nur eingebetteter Text, keine OCR.
  - pdf_classify: PyMuPDF-Heuristik pro Seite (kind, chars, n_paths,
    vector/text/image_coverage). Grundlage fuer die Router-Entscheidung
    im Markdown-Extraktions-Flow. Keine Extraktion, nur Signale.
"""

from __future__ import annotations

import logging
from typing import Any

from . import register
from .fs import _resolve_under_data, _data_root


logger = logging.getLogger(__name__)


DEFAULT_MAX_CHARS = 50_000
MAX_MAX_CHARS = 500_000


@register(
    name="pdf_extract_text",
    description=(
        "Extrahiert Text aus einem PDF unter data/. Seitenangaben 1-basiert. "
        "Ohne page_start/end: das ganze Dokument. Der Text wird bei max_chars "
        "abgeschnitten (truncated=true). Nur eingebetteter Text — Scan-PDFs "
        "liefern leeren Text, dafuer braucht es Azure Document Intelligence."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad zum PDF, relativ zu data/ (z.B. 'raw/dokumente/foo.pdf').",
            },
            "page_start": {
                "type": "integer",
                "description": "Erste zu extrahierende Seite (1-basiert). Default 1.",
            },
            "page_end": {
                "type": "integer",
                "description": "Letzte Seite, inklusive. Default: letzte Seite.",
            },
            "max_chars": {
                "type": "integer",
                "description": f"Maximale Zeichenzahl (Default {DEFAULT_MAX_CHARS}, Max {MAX_MAX_CHARS}).",
            },
        },
        "required": ["path"],
    },
    returns=(
        "{path, total_pages, page_start, page_end, pages_extracted, "
        "text, char_count, truncated}"
    ),
)
def _pdf_extract_text(
    *,
    path: str,
    page_start: int = 1,
    page_end: int | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    if not path:
        raise ValueError("path ist erforderlich.")

    target = _resolve_under_data(path)
    if not target.exists():
        raise ValueError(f"PDF nicht gefunden: {path!r}")
    if not target.is_file():
        raise ValueError(f"Pfad ist keine Datei: {path!r}")
    if target.suffix.lower() != ".pdf":
        raise ValueError(f"Keine PDF-Datei: {target.suffix!r}")

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf fehlt — `uv sync` laufen lassen.") from exc

    try:
        reader = PdfReader(str(target))
    except Exception as exc:
        raise ValueError(f"PDF konnte nicht geoeffnet werden: {exc}") from exc

    total = len(reader.pages)
    if total == 0:
        return {
            "path": str(target.relative_to(_data_root())),
            "total_pages": 0,
            "page_start": 0,
            "page_end": 0,
            "pages_extracted": 0,
            "text": "",
            "char_count": 0,
            "truncated": False,
        }

    start = max(1, int(page_start or 1))
    end = int(page_end) if page_end else total
    end = min(total, max(start, end))

    effective_limit = max(1000, min(int(max_chars or DEFAULT_MAX_CHARS), MAX_MAX_CHARS))

    parts: list[str] = []
    total_chars = 0
    truncated = False
    pages_done = 0

    for page_num in range(start, end + 1):
        try:
            page = reader.pages[page_num - 1]
            page_text = page.extract_text() or ""
        except Exception as exc:
            logger.warning("PDF-Seite %d Extraktion fehlgeschlagen: %s", page_num, exc)
            page_text = ""

        header = f"\n\n--- Seite {page_num} ---\n"
        chunk = header + page_text

        if total_chars + len(chunk) > effective_limit:
            remaining = effective_limit - total_chars
            if remaining > 0:
                parts.append(chunk[:remaining])
                total_chars += remaining
            truncated = True
            pages_done += 1
            break

        parts.append(chunk)
        total_chars += len(chunk)
        pages_done += 1

    return {
        "path": str(target.relative_to(_data_root())),
        "total_pages": total,
        "page_start": start,
        "page_end": end,
        "pages_extracted": pages_done,
        "text": "".join(parts).lstrip(),
        "char_count": total_chars,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# pdf_classify — Seiten-Heuristik mit PyMuPDF
# ---------------------------------------------------------------------------

# Standard-Schwellen fuer die Kind-Entscheidung.
# Basis-Kalibrierung 2026-04-21 an echten PDFs (Schaltplan, Geraeteliste,
# Datenblatt, Montageanleitung). Finale Kalibrierung folgt am Gold-Standard.
#
# Kernprinzip: text_coverage + chars vetoen vector-drawing.
# Tabellen haben viele duenne Rahmen-Pfade, aber geringe vector_coverage
# (< 0.05) und hohe text_coverage (> 0.3). Echte Zeichnungen haben wenig
# Text und grosse Vektorflaechen (vec_cov > 0.4).
_KIND_EMPTY_MAX_CHARS = 20
_KIND_SCAN_MAX_CHARS = 50
_KIND_SCAN_MIN_IMAGE_COV = 0.5
_KIND_TEXT_DOMINANT_MIN_CHARS = 1000
_KIND_TEXT_DOMINANT_MIN_TEXT_COV = 0.30
_KIND_MIXED_IN_TEXT_VEC_COV = 0.25
_KIND_MIXED_IN_TEXT_IMG_COV = 0.15
_KIND_VECTOR_MIN_COV = 0.40
_KIND_VECTOR_MAX_CHARS = 500
_KIND_MIXED_MIN_CHARS = 100
_KIND_MIXED_MIN_VECTOR_COV = 0.10

_PAGE_LIMIT_DEFAULT = 200
_PAGE_LIMIT_MAX = 1000


@register(
    name="pdf_classify",
    description=(
        "Klassifiziert jede Seite eines PDF anhand von PyMuPDF-Heuristiken "
        "(Text-Laenge, Anzahl Vektor-Pfade, Bild-/Vektor-/Text-Flaechen). "
        "Liefert pro Seite kind ∈ {text, mixed, vector-drawing, scan, empty} "
        "und eine Empfehlung fuer die passende Extraktions-Engine. Keine "
        "Extraktion selbst — nur Signale. Schnell (etwa 10-50 ms/Seite). "
        "Grundlage fuer den Markdown-Extraktions-Flow, der danach pro Seite "
        "entscheidet, welche Engine (pypdf / docling-smol / docling-granite "
        "/ azure-di) laeuft."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad zum PDF, relativ zu data/.",
            },
            "page_start": {
                "type": "integer",
                "description": "Erste zu klassifizierende Seite (1-basiert). Default 1.",
            },
            "page_end": {
                "type": "integer",
                "description": "Letzte Seite, inklusive. Default: letzte Seite.",
            },
            "max_pages": {
                "type": "integer",
                "description": (
                    f"Obergrenze fuer analysierte Seiten (Default {_PAGE_LIMIT_DEFAULT}, "
                    f"Max {_PAGE_LIMIT_MAX}). Schutz vor riesigen Response-JSONs."
                ),
            },
        },
        "required": ["path"],
    },
    returns=(
        "{path, total_pages, page_start, page_end, pages_analyzed, truncated, "
        "pages: [{page, kind, chars, n_words, n_paths, n_images, text_coverage, "
        "vector_coverage, image_coverage, width_pt, height_pt}], "
        "summary: {kind_counts, dominant_kind, recommended_engine}}"
    ),
)
def _pdf_classify(
    *,
    path: str,
    page_start: int = 1,
    page_end: int | None = None,
    max_pages: int = _PAGE_LIMIT_DEFAULT,
) -> dict[str, Any]:
    if not path:
        raise ValueError("path ist erforderlich.")

    target = _resolve_under_data(path)
    if not target.exists():
        raise ValueError(f"PDF nicht gefunden: {path!r}")
    if not target.is_file():
        raise ValueError(f"Pfad ist keine Datei: {path!r}")
    if target.suffix.lower() != ".pdf":
        raise ValueError(f"Keine PDF-Datei: {target.suffix!r}")

    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF fehlt — `uv add pymupdf` laufen lassen."
        ) from exc

    try:
        doc = fitz.open(str(target))
    except Exception as exc:
        raise ValueError(f"PDF konnte nicht geoeffnet werden: {exc}") from exc

    try:
        total = doc.page_count
        if total == 0:
            return {
                "path": str(target.relative_to(_data_root())),
                "total_pages": 0,
                "page_start": 0,
                "page_end": 0,
                "pages_analyzed": 0,
                "truncated": False,
                "pages": [],
                "summary": {
                    "kind_counts": {},
                    "dominant_kind": None,
                    "recommended_engine": "pypdf",
                },
            }

        start = max(1, int(page_start or 1))
        end = int(page_end) if page_end else total
        end = min(total, max(start, end))

        limit = max(1, min(int(max_pages or _PAGE_LIMIT_DEFAULT), _PAGE_LIMIT_MAX))
        planned = end - start + 1
        truncated = planned > limit
        last = start + min(planned, limit) - 1

        pages_info: list[dict[str, Any]] = []
        kind_counts: dict[str, int] = {}

        for page_num in range(start, last + 1):
            try:
                page = doc.load_page(page_num - 1)
                info = _classify_page(page)
            except Exception as exc:
                logger.warning(
                    "PDF-Seite %d Klassifikation fehlgeschlagen: %s", page_num, exc
                )
                info = {
                    "page": page_num,
                    "kind": "error",
                    "error": str(exc),
                }
            pages_info.append(info)
            kind = info.get("kind", "error")
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

        dominant_kind = (
            max(kind_counts.items(), key=lambda kv: kv[1])[0] if kind_counts else None
        )
        recommended = _recommend_engine(kind_counts)

        return {
            "path": str(target.relative_to(_data_root())),
            "total_pages": total,
            "page_start": start,
            "page_end": last,
            "pages_analyzed": len(pages_info),
            "truncated": truncated,
            "pages": pages_info,
            "summary": {
                "kind_counts": kind_counts,
                "dominant_kind": dominant_kind,
                "recommended_engine": recommended,
            },
        }
    finally:
        doc.close()


def _classify_page(page: Any) -> dict[str, Any]:
    """Extrahiert Signale einer Seite und entscheidet den kind."""
    rect = page.rect
    page_area = float(rect.width) * float(rect.height) or 1.0

    # Text
    text = page.get_text() or ""
    text_stripped = text.strip()
    chars = len(text_stripped)
    n_words = len(text_stripped.split())

    # Text-Coverage ueber Bloecke
    text_cov_area = 0.0
    try:
        for block in page.get_text("blocks"):
            x0, y0, x1, y1 = block[:4]
            text_cov_area += max(0.0, (x1 - x0) * (y1 - y0))
    except Exception:
        pass
    text_coverage = min(1.0, text_cov_area / page_area)

    # Vektor-Pfade
    try:
        drawings = page.get_drawings()
    except Exception as exc:
        logger.debug("get_drawings fehlgeschlagen: %s", exc)
        drawings = []
    n_paths = len(drawings)

    vec_cov_area = 0.0
    for draw in drawings:
        r = draw.get("rect")
        if r is None:
            continue
        try:
            clipped = r & rect
            w = float(clipped.width)
            h = float(clipped.height)
            if w > 0 and h > 0:
                vec_cov_area += w * h
        except Exception:
            continue
    vector_coverage = min(1.0, vec_cov_area / page_area)

    # Eingebettete Bilder
    try:
        images = page.get_image_info()
    except Exception as exc:
        logger.debug("get_image_info fehlgeschlagen: %s", exc)
        images = []
    n_images = len(images)

    img_cov_area = 0.0
    for img in images:
        bbox = img.get("bbox")
        if not bbox:
            continue
        try:
            x0, y0, x1, y1 = bbox
            img_cov_area += max(0.0, (x1 - x0) * (y1 - y0))
        except Exception:
            continue
    image_coverage = min(1.0, img_cov_area / page_area)

    kind = _decide_kind(
        chars=chars,
        vector_coverage=vector_coverage,
        image_coverage=image_coverage,
        text_coverage=text_coverage,
        n_paths=n_paths,
    )

    return {
        "page": page.number + 1,
        "kind": kind,
        "chars": chars,
        "n_words": n_words,
        "n_paths": n_paths,
        "n_images": n_images,
        "text_coverage": round(text_coverage, 3),
        "vector_coverage": round(vector_coverage, 3),
        "image_coverage": round(image_coverage, 3),
        "width_pt": round(float(rect.width), 1),
        "height_pt": round(float(rect.height), 1),
    }


def _decide_kind(
    *,
    chars: int,
    vector_coverage: float,
    image_coverage: float,
    text_coverage: float,
    n_paths: int,
) -> str:
    """Entscheidet den Seiten-Typ auf Basis der Signale.

    Regel-Hierarchie:
      1. empty      — kaum Inhalt
      2. scan       — wenig Text, viel Bildflaeche (OCR-Kandidat)
      3. Text-Dominanz (chars + text_coverage hoch) ueberstimmt paths:
         - mit relevanter Grafik (vec oder img)  → mixed
         - sonst                                 → text
      4. vector-drawing — grosse Vektorflaeche UND wenig Text
      5. mixed      — Text + nennenswerter Vektor-Anteil
      6. text       — Default
    """
    if chars < _KIND_EMPTY_MAX_CHARS and n_paths == 0 and image_coverage < 0.1:
        return "empty"
    if chars < _KIND_SCAN_MAX_CHARS and image_coverage > _KIND_SCAN_MIN_IMAGE_COV:
        return "scan"

    # Text-Dominanz — Tabellen/Listen/Textseiten schuetzen
    if (
        chars >= _KIND_TEXT_DOMINANT_MIN_CHARS
        and text_coverage >= _KIND_TEXT_DOMINANT_MIN_TEXT_COV
    ):
        if (
            vector_coverage > _KIND_MIXED_IN_TEXT_VEC_COV
            or image_coverage > _KIND_MIXED_IN_TEXT_IMG_COV
        ):
            return "mixed"
        return "text"

    # Echte Zeichnung: grosse Vektorflaeche, wenig Text
    if vector_coverage > _KIND_VECTOR_MIN_COV and chars < _KIND_VECTOR_MAX_CHARS:
        return "vector-drawing"

    if chars >= _KIND_MIXED_MIN_CHARS and vector_coverage > _KIND_MIXED_MIN_VECTOR_COV:
        return "mixed"
    return "text"


def _recommend_engine(kind_counts: dict[str, int]) -> str:
    """Heuristische Engine-Empfehlung fuer ein ganzes Dokument.

    Abgestufte Empfehlung nach Anteilen (nicht nach Existenz einzelner
    Seiten). Bei gemischten Dokumenten ist Docling granite die sicherste
    Wahl; pure Text-Dokumente laufen billig mit pypdf.
    """
    total = sum(kind_counts.values())
    if total == 0:
        return "pypdf"
    vec_scan_share = (
        kind_counts.get("vector-drawing", 0) + kind_counts.get("scan", 0)
    ) / total
    mixed_share = kind_counts.get("mixed", 0) / total

    if vec_scan_share > 0.30:
        return "azure-di"
    if mixed_share > 0.40:
        return "docling-granite-mlx"
    if mixed_share > 0 or vec_scan_share > 0:
        return "docling-smol-mlx"
    return "pypdf"
