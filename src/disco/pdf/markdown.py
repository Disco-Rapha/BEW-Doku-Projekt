"""Engine-Dispatcher: PDF -> Markdown.

Einstiegspunkt fuer den Bulk-Flow `pdf_to_markdown`. Nimmt eine PDF und
einen Engine-Namen, liefert (markdown, meta) zurueck. Kein Schreiben in
die DB, kein Caching — das uebernimmt der Runner.

Drei Engines (muessen mit `work_pdf_routing.engine` und dem Routing-Flow
uebereinstimmen):

  docling-standard  — Lokal, 0 EUR, ~10-30s/Seite auf M1/M2/M3 (MPS).
  azure-di          — Cloud, prebuilt-layout (Standard):
                      0,00868 EUR/Seite (8,68 EUR / 1000), ~1-3 s/Seite.
  azure-di-hr       — Cloud, prebuilt-layout + ocrHighResolution:
                      0,01389 EUR/Seite (13,89 EUR / 1000), ~1-3 s/Seite.

Preise gemaess Azure Document Intelligence Listpreis Sweden Central
(Stand 2026-04-24, aus User-Rechnung verifiziert).

meta enthaelt immer:
  engine             : gewaehlter Engine-Name
  n_pages            : Seitenzahl (0 wenn nicht ermittelbar)
  duration_ms        : gemessene Extraktionsdauer in ms
  estimated_cost_eur : Euro-Schaetzung (0.0 fuer docling-standard)
  char_count         : len(markdown)
  page_offsets       : Liste[{page_num, char_start, char_end}] —
                       Offsets pro Seite im finalen Markdown-Blob.
                       Leere Liste wenn die Engine keine Offsets liefert.
  extractor_version  : Kennzeichen der Extraktor-Code-Version
                       (siehe EXTRACTOR_VERSION unten).

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

# Azure Document Intelligence — Listpreise Sweden Central (2026-04-24).
# prebuilt-layout = 8,68 EUR / 1000 Seiten.
# prebuilt-layout + ocrHighResolution = 13,89 EUR / 1000 Seiten.
# Quelle: Azure-Rechnung, vom User am 2026-04-24 bestaetigt.
_AZURE_DI_LAYOUT_EUR_PER_PAGE = 8.68 / 1000
_AZURE_DI_LAYOUT_HR_EUR_PER_PAGE = 13.89 / 1000

# ----------------------------------------------------------------
# Extraktor-Code-Version
# ----------------------------------------------------------------
# Kennzeichen der Extraktor-Code-Version. Wandert als extractor_version
# in agent_pdf_markdown. Bump wenn sich das Extraktionsverhalten aendert
# (neue Engine-Option, anderes Post-Processing, Bugfix an Offsets oder
# Marker-Handling, geaendertes Seitennummer-Matching etc.) — so sind
# Rows mit veralteter Extraktion per SQL auffindbar und koennen
# gezielt re-extrahiert werden.
#
# Format: Datum (YYYY-MM-DD), bei mehreren Bumps am gleichen Tag mit
# Buchstaben-Suffix (z.B. "2026-04-24", "2026-04-24b").
EXTRACTOR_VERSION = "2026-04-25"


def extract_markdown(path: Path, engine: str) -> tuple[str, dict[str, Any]]:
    """Extrahiert PDF nach Markdown ueber die gewaehlte Engine.

    Args:
        path: Absoluter Pfad zur PDF.
        engine: 'docling-standard' | 'azure-di' | 'azure-di-hr'.

    Returns:
        Tupel (markdown, meta). markdown kann leer sein. meta enthaelt
        engine/n_pages/duration_ms/estimated_cost_eur/char_count/
        page_offsets/extractor_version.

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

    page_offsets: list[dict[str, int]]
    if engine == "docling-standard":
        md, n_pages, page_offsets = _extract_docling_standard(source)
        cost = 0.0
    elif engine == "azure-di":
        md, n_pages, page_offsets = _extract_azure_di(source, high_resolution=False)
        cost = round(n_pages * _AZURE_DI_LAYOUT_EUR_PER_PAGE, 5)
    else:  # azure-di-hr
        md, n_pages, page_offsets = _extract_azure_di(source, high_resolution=True)
        cost = round(n_pages * _AZURE_DI_LAYOUT_HR_EUR_PER_PAGE, 5)

    duration_ms = (time.monotonic() - t_start) * 1000.0

    meta = {
        "engine": engine,
        "n_pages": n_pages,
        "duration_ms": round(duration_ms, 1),
        "estimated_cost_eur": cost,
        "char_count": len(md),
        "page_offsets": page_offsets,
        "extractor_version": EXTRACTOR_VERSION,
    }
    return md, meta


# ----------------------------------------------------------------
# docling-standard
# ----------------------------------------------------------------

def _extract_docling_standard(source: Path) -> tuple[str, int, list[dict[str, int]]]:
    """DocLayNet + TableFormer ACCURATE + EasyOCR auf MPS.

    Rendert den Markdown seiten-weise per `export_to_markdown(page_no=N)`
    und schreibt dabei die Zeichenbereiche pro Seite in page_offsets mit.
    Zwischen Seiten steht ein `\\n\\n`-Separator (nicht Teil eines
    page_offset-Bereichs).

    Offene Fragen fuer spaeter (wenn Docling wieder im Einsatz ist):
      - Cross-Page-Tables: Docling modelliert seiten-uebergreifende
        Tabellen als ein Objekt; wie genau das per-page-Export damit
        umgeht (aufteilen / duplizieren / auf Primary-Seite rendern)
        ist ohne Messung an echten PDFs unbestimmt. Azure-DI stitcht
        solche Tabellen im Rohresultat zusammen, dort ist die Anchor-
        Seite die erste Seite des Tabellen-Blocks. Format-Normalisierung
        zwischen beiden Engines ist ein separates Thema.
      - Seiten ohne erkannten Content liefern leeren Markdown — bleibt
        trotzdem als Eintrag im Offset-Index (char_start == char_end).
    """
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
    document = result.document

    # Seitenzahl ermitteln (zwei Pfade, fallback-robust)
    n_pages = 0
    if hasattr(result, "pages") and result.pages:
        n_pages = len(result.pages)
    elif hasattr(document, "pages"):
        try:
            n_pages = len(document.pages)
        except Exception:
            n_pages = 0

    if n_pages <= 0:
        # Kein Seiten-Split moeglich — Fallback auf einen Big-Blob-Export
        md = document.export_to_markdown() or ""
        return md, n_pages, []

    # Seiten-weise rendern und Offsets mitschreiben
    md_parts: list[str] = []
    page_offsets: list[dict[str, int]] = []
    cursor = 0
    separator = "\n\n"

    for page_num in range(1, n_pages + 1):
        if page_num > 1:
            md_parts.append(separator)
            cursor += len(separator)

        try:
            page_md = document.export_to_markdown(page_no=page_num) or ""
        except Exception as exc:  # pragma: no cover — defensive, Docling-API-Instabilitaet
            logger.warning(
                "Docling per-Seite-Export fuer page_no=%d fehlgeschlagen: %s",
                page_num,
                exc,
            )
            page_md = ""

        char_start = cursor
        char_end = cursor + len(page_md)
        page_offsets.append(
            {"page_num": page_num, "char_start": char_start, "char_end": char_end}
        )
        md_parts.append(page_md)
        cursor = char_end

    md = "".join(md_parts)
    return md, n_pages, page_offsets


# ----------------------------------------------------------------
# azure-di / azure-di-hr
# ----------------------------------------------------------------

def _extract_azure_di(
    source: Path, *, high_resolution: bool
) -> tuple[str, int, list[dict[str, int]]]:
    """Azure DI prebuilt-layout (optional + ocrHighResolution).

    Azure-DI liefert `result.content` als **fertig konkatenierten**
    Markdown-Blob aller Seiten (inkl. bereits gestitchter cross-page
    Tabellen). `result.pages[i].spans[0].offset` ist der Zeichen-Offset
    im `result.content`, an dem Seite i beginnt. Wir nutzen genau diese
    Offsets direkt als Seiten-Index — keine Marker-Einfuegung, keine
    Nachberechnung noetig.

    Rueckgabe:
      md          : result.content unveraendert (keine eingefuegten Marker).
      n_pages     : Anzahl Seiten.
      page_offsets: Liste[{page_num, char_start, char_end}] sortiert
                    nach Seite. char_end ist exklusiv; letzte Seite
                    geht bis len(md).
    """
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

    # Seiten-Offsets direkt aus den DI-Spans ableiten — ohne Marker-
    # Einfuegung, der Blob bleibt markerfrei.
    page_offsets: list[dict[str, int]] = []
    if result.pages:
        raw: list[tuple[int, int]] = []  # (page_num, char_start)
        for page in result.pages:
            if page.spans:
                raw.append((page.page_number, page.spans[0].offset))
        # Falls DI aus irgendeinem Grund ungeordnete Seiten liefert —
        # nach Offset sortieren (Seitennummer folgt strikt den Offsets).
        raw.sort(key=lambda x: x[1])

        for idx, (page_num, char_start) in enumerate(raw):
            char_end = raw[idx + 1][1] if idx + 1 < len(raw) else len(md)
            page_offsets.append(
                {
                    "page_num": page_num,
                    "char_start": char_start,
                    "char_end": char_end,
                }
            )

    return md, n_pages, page_offsets
