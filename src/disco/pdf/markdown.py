"""Engine-Dispatcher: PDF -> Markdown.

Einstiegspunkt fuer den Bulk-Flow `pdf_to_markdown`. Nimmt eine PDF und
einen Engine-Namen, liefert (markdown, meta) zurueck. Kein Schreiben in
die DB, kein Caching — das uebernimmt der Runner.

Drei Engines (muessen mit `work_pdf_routing.engine` und dem Routing-Flow
uebereinstimmen):

  docling-standard  — Lokal, 0 EUR, ~10-30s/Seite auf M1/M2/M3 (MPS).
  azure-di          — Cloud, 0.00130 EUR/Seite (1.30 EUR / 1000), ~1-3s/Seite.
  azure-di-hr       — Cloud, 0.00651 EUR/Seite (6.51 EUR / 1000), ~1-3s/Seite.

meta enthaelt immer:
  engine          : gewaehlter Engine-Name
  n_pages         : Seitenzahl (0 wenn nicht ermittelbar)
  duration_ms     : gemessene Extraktionsdauer in ms
  estimated_cost_eur : Euro-Schaetzung (0.0 fuer docling-standard)
  char_count      : len(markdown)

Leere Markdown-Ausgabe wird NICHT als Fehler behandelt — der Aufrufer
darf leere Strings persistieren (Entscheid 2026-04-22).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


ENGINES = ("docling-standard", "azure-di", "azure-di-hr")


def extract_markdown(path: Path, engine: str) -> tuple[str, dict[str, Any]]:
    """Extrahiert PDF nach Markdown ueber die gewaehlte Engine.

    Args:
        path: Absoluter Pfad zur PDF.
        engine: 'docling-standard' | 'azure-di' | 'azure-di-hr'.

    Returns:
        Tupel (markdown, meta). markdown kann leer sein. meta enthaelt
        engine/n_pages/duration_ms/estimated_cost_eur/char_count.

    Raises:
        ValueError: Engine-Name unbekannt oder PDF-Pfad ungueltig.
        RuntimeError: Extraktion schlaegt fehl (Aufrufer entscheidet
            ueber Retry).
    """
    if engine not in ENGINES:
        raise ValueError(
            f"Unbekannte Engine {engine!r}. "
            f"Erlaubt: {', '.join(ENGINES)}"
        )

    source = Path(path)
    if not source.exists():
        raise ValueError(f"PDF nicht gefunden: {source}")
    if source.suffix.lower() != ".pdf":
        raise ValueError(f"Keine PDF-Datei: {source.suffix!r}")

    t_start = time.monotonic()

    if engine == "docling-standard":
        md, n_pages = _extract_docling_standard(source)
        cost = 0.0
    elif engine == "azure-di":
        md, n_pages = _extract_azure_di(source, high_resolution=False)
        cost = round(n_pages * (1.30 / 1000), 5)
    else:  # azure-di-hr
        md, n_pages = _extract_azure_di(source, high_resolution=True)
        cost = round(n_pages * (6.51 / 1000), 5)

    duration_ms = (time.monotonic() - t_start) * 1000.0

    meta = {
        "engine": engine,
        "n_pages": n_pages,
        "duration_ms": round(duration_ms, 1),
        "estimated_cost_eur": cost,
        "char_count": len(md),
    }
    return md, meta


# ----------------------------------------------------------------
# docling-standard
# ----------------------------------------------------------------

def _extract_docling_standard(source: Path) -> tuple[str, int]:
    """DocLayNet + TableFormer ACCURATE + EasyOCR auf MPS."""
    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableFormerMode,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = True
    opts.do_table_structure = True
    opts.table_structure_options.mode = TableFormerMode.ACCURATE
    opts.table_structure_options.do_cell_matching = True
    opts.images_scale = 2.0
    opts.accelerator_options = AcceleratorOptions(
        num_threads=4,
        device=AcceleratorDevice.MPS,
    )

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    result = converter.convert(str(source))
    md = result.document.export_to_markdown() or ""

    n_pages = 0
    if hasattr(result, "pages") and result.pages:
        n_pages = len(result.pages)
    elif hasattr(result.document, "pages"):
        try:
            n_pages = len(result.document.pages)
        except Exception:
            n_pages = 0

    return md, n_pages


# ----------------------------------------------------------------
# azure-di / azure-di-hr
# ----------------------------------------------------------------

def _extract_azure_di(source: Path, *, high_resolution: bool) -> tuple[str, int]:
    """Azure DI prebuilt-layout (optional + ocrHighResolution)."""
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    from ..config import settings

    if not settings.azure_doc_intel_endpoint or not settings.azure_doc_intel_key:
        raise RuntimeError(
            "Azure Document Intelligence nicht konfiguriert. "
            "AZURE_DOC_INTEL_ENDPOINT und AZURE_DOC_INTEL_KEY in .env setzen."
        )

    client = DocumentIntelligenceClient(
        endpoint=settings.azure_doc_intel_endpoint,
        credential=AzureKeyCredential(settings.azure_doc_intel_key),
    )

    analyze_kwargs: dict[str, Any] = {
        "model_id": "prebuilt-layout",
        "content_type": "application/pdf",
        "output_content_format": "markdown",
    }
    if high_resolution:
        analyze_kwargs["features"] = ["ocrHighResolution"]

    with source.open("rb") as f:
        poller = client.begin_analyze_document(body=f, **analyze_kwargs)
    result = poller.result()

    md = result.content or ""
    n_pages = len(result.pages) if result.pages else 0

    # Seiten-Marker einfuegen (rueckwaerts, damit Offsets stabil bleiben)
    if result.pages and len(result.pages) > 1:
        page_offsets: list[tuple[int, int]] = []
        for page in result.pages:
            if page.spans:
                start = page.spans[0].offset
                page_offsets.append((start, page.page_number))
        for offset, page_num in reversed(page_offsets[1:]):
            marker = f"\n\n<!-- Seite {page_num} -->\n\n"
            md = md[:offset] + marker + md[offset:]

    return md, n_pages
