"""PDF-Textextraktion mit pypdf.

Design:
  - Nur Dateien unter settings.data_dir.
  - Seiten-Range ist 1-basiert (menschenfreundlich).
  - Zeichen-Limit gegen Kontext-Explosion.
  - Keine OCR — pypdf kann nur eingebetteten Text extrahieren. Scan-PDFs
    liefern leeren Text. Wer OCR braucht, nutzt in Phase 2c den
    Azure-Document-Intelligence-Worker.
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
                "description": "Pfad zum PDF, relativ zu data/ (z.B. 'raw/vattenfall/foo.pdf').",
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
