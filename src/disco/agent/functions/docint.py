"""Azure Document Intelligence — PDF zu Markdown Extraktion.

Nutzt den prebuilt-layout-Analysator fuer hochwertige Extraktion:
  - OCR fuer gescannte PDFs
  - Tabellen bleiben als Markdown-Tabellen erhalten
  - Kapitel-Header (H1/H2/H3) werden erkannt
  - Seitenzuordnung ist verfuegbar

Ergebnis wird als .md-Datei unter .disco/context-extracts/ gespeichert
(bei context/) oder an einem beliebigen Zielpfad.

Kosten: ~0.01 EUR pro Seite (prebuilt-layout, Stand 2026).
Kontext-PDFs (wenige, wichtig, einmalig) → sinnvoll.
Source-PDFs (viele, Bulk) → besser via Pipeline/Worker.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from . import register
from .fs import _data_root, _resolve_under_data


logger = logging.getLogger(__name__)


@register(
    name="extract_pdf_to_markdown",
    description=(
        "Extrahiert eine PDF-Datei per Azure Document Intelligence in "
        "hochwertiges Markdown (OCR, Tabellen, Kapitel-Header). "
        "Ergebnis wird als .md-Datei gespeichert. "
        "Kosten: ~0.01 EUR pro Seite. Fuer Context-PDFs (wenige, wichtig) "
        "empfohlen. Fuer Bulk (1000+ PDFs) besser Pipeline nutzen.\n\n"
        "Wenn kein output_path angegeben: speichert automatisch unter "
        ".disco/context-extracts/<dateiname>.md"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Pfad zur PDF, relativ zum Projekt "
                    "(z.B. 'context/vgb-s-831.pdf')."
                ),
            },
            "output_path": {
                "type": "string",
                "description": (
                    "Optionaler Zielpfad fuer das Markdown. "
                    "Default: .disco/context-extracts/<dateiname>.md"
                ),
            },
            "model_id": {
                "type": "string",
                "description": (
                    "DI-Modell. Default 'prebuilt-layout' (Tabellen+Struktur). "
                    "Alternative: 'prebuilt-read' (nur Text, billiger)."
                ),
            },
        },
        "required": ["path"],
    },
    returns=(
        "{path, output_path, pages, tables, markdown_chars, "
        "duration_s, estimated_cost_eur, model_id}"
    ),
)
def _extract_pdf_to_markdown(
    *,
    path: str,
    output_path: str | None = None,
    model_id: str = "prebuilt-layout",
) -> dict[str, Any]:
    from ...config import settings

    # Pruefen ob DI konfiguriert ist
    if not settings.azure_doc_intel_endpoint or not settings.azure_doc_intel_key:
        raise ValueError(
            "Azure Document Intelligence nicht konfiguriert. "
            "Bitte AZURE_DOC_INTEL_ENDPOINT und AZURE_DOC_INTEL_KEY in "
            ".env eintragen."
        )

    # Quell-PDF aufloesen
    root = _data_root()
    source = _resolve_under_data(path)
    if not source.exists():
        raise ValueError(f"PDF nicht gefunden: {path!r}")
    if source.suffix.lower() != ".pdf":
        raise ValueError(f"Keine PDF-Datei: {source.suffix!r}")

    # Ziel-Pfad bestimmen
    if output_path:
        target = (root / output_path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError(f"output_path ausserhalb des Projekts: {output_path!r}")
    else:
        stem = source.stem
        target = root / ".disco" / "context-extracts" / f"{stem}.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    # DI-Client erstellen
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    client = DocumentIntelligenceClient(
        endpoint=settings.azure_doc_intel_endpoint,
        credential=AzureKeyCredential(settings.azure_doc_intel_key),
    )

    # Extraktion starten
    t_start = time.monotonic()
    with source.open("rb") as f:
        poller = client.begin_analyze_document(
            model_id=model_id,
            body=f,
            content_type="application/pdf",
            output_content_format="markdown",
        )
    result = poller.result()
    duration = time.monotonic() - t_start

    md_content = result.content or ""
    n_pages = len(result.pages) if result.pages else 0
    n_tables = len(result.tables) if result.tables else 0

    # Seiten-Marker einfuegen fuer spaetere Referenz
    # DI liefert page-Offsets — wir fuegen "--- Seite N ---" ein
    if result.pages and len(result.pages) > 1:
        # Seiten-Grenzen aus den Spans ableiten
        page_offsets: list[tuple[int, int]] = []
        for page in result.pages:
            if page.spans:
                start = page.spans[0].offset
                page_offsets.append((start, page.page_number))

        # Rueckwaerts einfuegen damit Offsets nicht verrutschen
        for offset, page_num in reversed(page_offsets[1:]):  # erste Seite braucht keinen Marker
            marker = f"\n\n<!-- Seite {page_num} -->\n\n"
            md_content = md_content[:offset] + marker + md_content[offset:]

    # Header mit Metadaten voranstellen
    header = (
        f"<!-- Extrahiert aus: {path} -->\n"
        f"<!-- Modell: {model_id} | Seiten: {n_pages} | "
        f"Tabellen: {n_tables} | {len(md_content)} Zeichen -->\n"
        f"<!-- Extrahiert am: {time.strftime('%Y-%m-%d %H:%M:%S')} -->\n\n"
    )
    md_content = header + md_content

    # Speichern
    target.write_text(md_content, encoding="utf-8")

    # Kosten-Schaetzung (prebuilt-layout ~0.01 EUR/Seite)
    cost_per_page = 0.01 if model_id == "prebuilt-layout" else 0.005
    estimated_cost = round(n_pages * cost_per_page, 2)

    rel_output = str(target.relative_to(root))

    return {
        "path": path,
        "output_path": rel_output,
        "pages": n_pages,
        "tables": n_tables,
        "markdown_chars": len(md_content),
        "duration_s": round(duration, 1),
        "estimated_cost_eur": estimated_cost,
        "model_id": model_id,
        "hint": (
            f"Markdown gespeichert unter {rel_output}. "
            f"Lies ihn mit fs_read fuer die inhaltliche Analyse."
        ),
    }
