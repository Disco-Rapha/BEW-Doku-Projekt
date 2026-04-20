"""Lokale PDF -> Markdown via Docling.

Drei Engines, alle laufen LOKAL (kein Internet, keine Cloud-Kosten):

  - granite-mlx (Default): Granite-Docling-258M-MLX, beste Layout-/Tabellen-
    Erkennung, optimiert fuer Apple Silicon (M1/M2/M3) ueber MLX. Speziell
    fuer Docling-Konvertierung trainiert (IBM, 2025).
  - smol-mlx: SmolDocling-256M-MLX, schneller Bruder, etwas weniger genau.
  - standard: klassische Docling-Pipeline (DocLayNet + TableFormer ACCURATE
    + EasyOCR). Schneller, aber bei Plantitelblock/komplexen Tabellen
    schwaecher.

Modell-Quelle: Disco laeuft per Default OFFLINE (HF_HUB_OFFLINE=1).
Die Modelle liegen lokal im Cache:
  - granite-mlx / smol-mlx: ~/.cache/huggingface/hub/models--.../
  - standard: ~/.cache/docling/ (DocLayNet + TableFormer)
Einmalig per `uv run python scripts/download_models.py` vorladen
(einzige legitime Online-Phase). Fehlt das Modell im Cache, bricht
der Aufruf mit OfflineModeIsEnabled ab — NICHT still nachladen.

Speicherort:
  - Default: <projekt>/.disco/markdown-extracts/<engine>/<dateiname>.md
  - Optional via output_path ueberschreibbar (muss innerhalb des Projekts
    liegen).

Vergleich mit Azure DI:
  - Granite-Docling-MLX ist gegenueber DI ein lokaler Ersatz. Erfahrungs-
    werte zeigen: bei den meisten Doc-Typen vergleichbare Markdown-
    Qualitaet, kostenlos, dafuer langsamer (~10-30s/Seite vs. DI's 1-3s/
    Seite Cloud).
  - Bei sehr komplexen Plantitelblocks und handschriftlichen Anteilen
    bleibt DI im Vorteil — fuer den Bulk-Pfad ist Granite-Docling-MLX
    aber meist die richtige Wahl.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from . import register
from .fs import _data_root, _resolve_under_data


logger = logging.getLogger(__name__)


# Mapping engine_name -> friendly description (fuer Fehler/Output)
_ENGINE_LABELS = {
    "granite-mlx": "Granite-Docling-258M (MLX, Apple Silicon)",
    "smol-mlx": "SmolDocling-256M (MLX, Apple Silicon)",
    "standard": "Docling-Standard (DocLayNet + TableFormer + EasyOCR)",
}


@register(
    name="markdown_extract",
    description=(
        "Konvertiert eine PDF lokal in Markdown via Docling — KEINE Cloud, "
        "kostenlos. Drei Engines:\n\n"
        "  - 'granite-mlx' (DEFAULT): Granite-Docling-258M-MLX. Beste "
        "Qualitaet auf M1/M2/M3 Macs. ~10-30s pro Seite. Speziell fuer "
        "Docling trainiert (IBM 2025). Erste Verwendung laedt ~500MB Modell.\n"
        "  - 'smol-mlx': SmolDocling-256M-MLX. Schneller, etwas weniger "
        "genau. Gut fuer simple Layouts.\n"
        "  - 'standard': klassische Docling-Pipeline (DocLayNet + "
        "TableFormer ACCURATE + EasyOCR). Schnellste Variante. Schwach "
        "bei komplexen Plantitelblocks.\n\n"
        "WANN NUTZEN: Fuer einzelne PDFs aus dem Chat heraus. Fuer Bulk "
        "(>10 PDFs) IMMER einen Flow nutzen — der Tool-Aufruf blockiert "
        "den Chat-Turn (kann pro Doc Minuten dauern).\n\n"
        "Ergebnis wird als .md unter .disco/markdown-extracts/<engine>/ "
        "abgelegt (oder unter output_path)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Pfad zur PDF, relativ zum Projekt "
                    "(z.B. 'sources/PV-Anlage_Datenblatt.pdf')."
                ),
            },
            "output_path": {
                "type": "string",
                "description": (
                    "Optionaler Zielpfad fuer das Markdown, relativ zum "
                    "Projekt. Default: '.disco/markdown-extracts/"
                    "<engine>/<dateiname>.md'."
                ),
            },
            "engine": {
                "type": "string",
                "enum": ["granite-mlx", "smol-mlx", "standard"],
                "description": (
                    "Konvertierungs-Engine. Default 'granite-mlx' "
                    "(beste Qualitaet auf Apple Silicon)."
                ),
            },
            "page_range": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Optional: nur Seiten [from, to] (1-indexiert, "
                    "inklusive Grenzen). Default: alle Seiten. "
                    "Nuetzlich fuer dicke Plaene zum Schnell-Test "
                    "der Engine."
                ),
            },
        },
        "required": ["path"],
    },
    returns=(
        "{path, output_path, engine, pages, markdown_chars, duration_s, "
        "device, model_repo}"
    ),
)
def _markdown_extract(
    *,
    path: str,
    output_path: str | None = None,
    engine: str = "granite-mlx",
    page_range: list[int] | None = None,
) -> dict[str, Any]:
    if engine not in _ENGINE_LABELS:
        raise ValueError(
            f"Unbekannte engine: {engine!r}. "
            f"Erlaubt: {sorted(_ENGINE_LABELS)}"
        )

    # Quell-PDF aufloesen + validieren
    root = _data_root()
    source = _resolve_under_data(path)
    if not source.exists():
        raise ValueError(f"PDF nicht gefunden: {path!r}")
    if source.suffix.lower() != ".pdf":
        raise ValueError(f"Keine PDF-Datei: {source.suffix!r}")

    # Zielpfad bestimmen
    if output_path:
        target = (root / output_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:  # noqa: BLE001
            raise ValueError(
                f"output_path ausserhalb des Projekts: {output_path!r}"
            ) from exc
    else:
        target = (
            root / ".disco" / "markdown-extracts" / engine / f"{source.stem}.md"
        )
    target.parent.mkdir(parents=True, exist_ok=True)

    # page_range validieren
    pr_tuple: tuple[int, int] | None = None
    if page_range:
        if (
            not isinstance(page_range, (list, tuple))
            or len(page_range) != 2
            or not all(isinstance(p, int) for p in page_range)
        ):
            raise ValueError(
                "page_range muss [from, to] mit 2 Ganzzahlen sein "
                "(1-indexiert, inklusive Grenzen)."
            )
        from_p, to_p = int(page_range[0]), int(page_range[1])
        if from_p < 1 or to_p < from_p:
            raise ValueError(
                f"page_range ungueltig: {page_range!r} "
                f"(beide >= 1 und from <= to)."
            )
        pr_tuple = (from_p, to_p)

    # Konvertierung starten
    t_start = time.monotonic()
    try:
        if engine == "granite-mlx":
            md, n_pages, model_repo, device = _convert_vlm_mlx(
                source, kind="granite", page_range=pr_tuple
            )
        elif engine == "smol-mlx":
            md, n_pages, model_repo, device = _convert_vlm_mlx(
                source, kind="smol", page_range=pr_tuple
            )
        else:  # standard
            md, n_pages, model_repo, device = _convert_standard(
                source, page_range=pr_tuple
            )
    except ImportError as exc:
        raise ValueError(
            f"Engine {engine!r} nicht verfuegbar: {exc}. "
            "Bei MLX-Engines: bitte sicherstellen, dass mlx-vlm installiert ist "
            "('uv sync' im Repo-Root)."
        ) from exc

    duration = time.monotonic() - t_start

    # Header mit Metadaten voranstellen (gleiche Konvention wie docint.py)
    header = (
        f"<!-- Extrahiert aus: {path} -->\n"
        f"<!-- Engine: {engine} ({_ENGINE_LABELS[engine]}) -->\n"
        f"<!-- Modell: {model_repo} | Device: {device} | Seiten: {n_pages} | "
        f"{len(md)} Zeichen | Dauer: {duration:.1f}s -->\n"
        f"<!-- Extrahiert am: {time.strftime('%Y-%m-%d %H:%M:%S')} -->\n\n"
    )
    md_full = header + md
    target.write_text(md_full, encoding="utf-8")

    rel_output = str(target.relative_to(root))

    return {
        "path": path,
        "output_path": rel_output,
        "engine": engine,
        "engine_label": _ENGINE_LABELS[engine],
        "pages": n_pages,
        "page_range": list(pr_tuple) if pr_tuple else None,
        "markdown_chars": len(md_full),
        "duration_s": round(duration, 1),
        "seconds_per_page": (
            round(duration / n_pages, 1) if n_pages else None
        ),
        "device": device,
        "model_repo": model_repo,
        "hint": (
            f"Markdown gespeichert unter {rel_output}. "
            f"Lies ihn mit fs_read fuer die inhaltliche Analyse, "
            f"oder vergleiche mit anderen Engines."
        ),
    }


# ---------------------------------------------------------------------------
# Engine-Implementierungen
# ---------------------------------------------------------------------------


# Modul-Level-Cache fuer VLM-Converter.
#
# Warum: Ein frischer DocumentConverter laedt die ~500-600 MB MLX-Weights
# aus dem HF-Cache in den RAM — Cold-Start ~25-40 s. Ohne diesen Cache
# passiert das bei jedem markdown_extract-Aufruf neu, also pro PDF.
# Mit Cache: 1x Cold-Start pro Python-Prozess, danach warme Inferenz.
#
# Pro Prozess: Chat-Agent und Flow-Worker haben jeweils eigene Python-
# Prozesse, also auch eigene Cache-Instanzen — das ist OK so, der Cache
# hilft *innerhalb* eines Prozesses bei Bulk-Ops.
#
# Thread-Safety: Agent/Worker sind single-threaded. Wir brauchen keinen Lock.
_VLM_CONVERTER_CACHE: dict[str, tuple[Any, Any]] = {}


def _get_vlm_converter(kind: str) -> tuple[Any, Any]:
    """Liefert (DocumentConverter, vlm_options) fuer `kind` aus dem Cache.

    Beim ersten Aufruf wird der Converter gebaut und die MLX-Weights aus
    dem lokalen HF-Cache in den RAM geladen (~25-40 s — nur Datei I/O,
    kein Netzwerk, Disco ist offline). Danach ist er im Modul-Cache und
    kommt sofort zurueck.
    """
    cached = _VLM_CONVERTER_CACHE.get(kind)
    if cached is not None:
        return cached

    # Lazy-Imports: Docling ist optional und schwer — nur laden wenn gebraucht.
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import VlmPipelineOptions
    from docling.datamodel.vlm_model_specs import (
        GRANITEDOCLING_MLX,
        SMOLDOCLING_MLX,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.pipeline.vlm_pipeline import VlmPipeline

    if kind == "granite":
        vlm_options = GRANITEDOCLING_MLX
    elif kind == "smol":
        vlm_options = SMOLDOCLING_MLX
    else:
        raise ValueError(f"Unbekannte VLM-MLX-Engine: {kind!r}")

    pipeline_options = VlmPipelineOptions(vlm_options=vlm_options)
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=VlmPipeline,
                pipeline_options=pipeline_options,
            )
        }
    )
    _VLM_CONVERTER_CACHE[kind] = (converter, vlm_options)
    return converter, vlm_options


def _convert_vlm_mlx(
    source: Path,
    *,
    kind: str,
    page_range: tuple[int, int] | None,
) -> tuple[str, int, str, str]:
    """Granite-Docling-258M-MLX oder SmolDocling-256M-MLX via VlmPipeline.

    Returns (markdown, n_pages, model_repo, device).
    """
    converter, vlm_options = _get_vlm_converter(kind)

    convert_kwargs: dict[str, Any] = {}
    if page_range:
        convert_kwargs["page_range"] = page_range

    result = converter.convert(str(source), **convert_kwargs)
    md = result.document.export_to_markdown()
    n_pages = len(result.pages) if hasattr(result, "pages") and result.pages else 0
    if not n_pages and hasattr(result.document, "pages"):
        # Fallback: aus dem Dokument-Objekt zaehlen
        try:
            n_pages = len(result.document.pages)
        except Exception:
            n_pages = 0

    return md, n_pages, vlm_options.repo_id, "MPS (MLX)"


def _convert_standard(
    source: Path,
    *,
    page_range: tuple[int, int] | None,
) -> tuple[str, int, str, str]:
    """Klassische Docling-Pipeline (DocLayNet + TableFormer + EasyOCR).

    Returns (markdown, n_pages, model_repo, device).
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
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=opts)
        }
    )

    convert_kwargs: dict[str, Any] = {}
    if page_range:
        convert_kwargs["page_range"] = page_range

    result = converter.convert(str(source), **convert_kwargs)
    md = result.document.export_to_markdown()
    n_pages = 0
    if hasattr(result, "pages") and result.pages:
        n_pages = len(result.pages)
    elif hasattr(result.document, "pages"):
        try:
            n_pages = len(result.document.pages)
        except Exception:
            n_pages = 0

    return (
        md,
        n_pages,
        "DocLayNet + TableFormer ACCURATE + EasyOCR",
        "MPS (PyTorch)",
    )
