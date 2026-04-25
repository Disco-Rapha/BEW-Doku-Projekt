"""Generische Doc-Extraktion fuer die Pipeline.

Konzept:
  - Jedes unterstuetzte Format hat ein Modul unter `disco.docs.<format>`
    mit einer `extract(path, engine)`-Funktion.
  - Das Routing-Modul `disco.docs.routing` entscheidet pro Datei file_kind
    + Engine.
  - Der Extraktions-Flow (`flows/library/extraction/runner.py`) ruft
    `dispatch_extract(path, engine)` und schreibt das Ergebnis in
    `agent_doc_markdown`.

Engine-Naming-Konvention:
  <file_kind>-<engine_name>[-<variant>]

  pdf-azure-di          (Standard-OCR)
  pdf-azure-di-hr       (4x DPI High-Resolution)
  pdf-docling-standard  (lokal, MPS)
  excel-openpyxl        (Sheets als Markdown-Tabellen)
  excel-table-import    (Sheets direkt als SQL-Tabellen, fuer context/)
  dwg-ezdxf-local       (DXF/DWG via ezdxf, ODA File Converter fuer DWG)
  image-gpt5-vision     (Foundry GPT-5.1 multimodal)

Pipeline-Versionierung:
  Jedes Extraction-Result enthaelt `extractor_version` als String der Form
  "extraction-v<MAJOR>.<MINOR>:<engine>:<engine-version>".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

# Pipeline-Version — bei strukturellen Aenderungen am Output-Format hochzaehlen
EXTRACTION_PIPELINE_VERSION = "extraction-v3.0"

# file_kind aus Datei-Extension ableiten
_KIND_BY_EXT: dict[str, str] = {
    "pdf": "pdf",
    "xlsx": "excel",
    "xlsm": "excel",
    "xls": "excel",
    "dwg": "dwg",
    "dxf": "dwg",
    "jpg": "image",
    "jpeg": "image",
    "png": "image",
    "tif": "image",
    "tiff": "image",
    "webp": "image",
    "bmp": "image",
    "gif": "image",
}


def file_kind_from_path(path: Path | str) -> str:
    """'pdf' | 'excel' | 'dwg' | 'image' | 'other'."""
    p = Path(path)
    ext = p.suffix.lower().lstrip(".")
    return _KIND_BY_EXT.get(ext, "other")


# Engine-Listen pro file_kind — die Default-Engine steht jeweils zuerst.
ENGINES_BY_KIND: dict[str, list[str]] = {
    "pdf": ["pdf-azure-di", "pdf-azure-di-hr", "pdf-docling-standard"],
    "excel": ["excel-openpyxl", "excel-table-import"],
    "dwg": ["dwg-ezdxf-local"],
    "image": ["image-gpt5-vision"],
}


def all_known_engines() -> set[str]:
    out: set[str] = set()
    for engs in ENGINES_BY_KIND.values():
        out.update(engs)
    return out


def kind_for_engine(engine: str) -> str:
    """Welcher file_kind gehoert zu dieser Engine?"""
    for kind, engs in ENGINES_BY_KIND.items():
        if engine in engs:
            return kind
    raise ValueError(f"Unbekannte Engine: {engine!r}")


# ---------------------------------------------------------------------------
# Extractor-Dispatch
# ---------------------------------------------------------------------------

# Type-Alias fuer Extractor-Signatur
# (path, engine) -> (markdown, meta_dict)
ExtractorFn = Callable[[Path, str], tuple[str, dict[str, Any]]]


def dispatch_extract(path: Path, engine: str) -> tuple[str, dict[str, Any]]:
    """Ruft den passenden Extractor fuer die Engine auf.

    Returns: (markdown, meta) wobei meta mindestens enthaelt:
      - engine
      - n_units      (Seiten / Sheets / 1)
      - char_count
      - unit_offsets:list of {unit_num, unit_label, char_start, char_end}
      - estimated_cost_eur
      - extractor_version
      - file_kind
      - meta_json:dict (format-spezifisches)
    """
    kind = kind_for_engine(engine)

    if kind == "pdf":
        from . import pdf as _impl
    elif kind == "excel":
        from . import excel as _impl
    elif kind == "dwg":
        from . import dwg as _impl
    elif kind == "image":
        from . import image as _impl
    else:  # pragma: no cover
        raise ValueError(f"Kein Extractor fuer file_kind={kind!r}")

    md, meta = _impl.extract(path, engine)
    # Sicherstellen, dass die Pflicht-Felder gesetzt sind
    meta.setdefault("file_kind", kind)
    meta.setdefault("engine", engine)
    return md, meta


def build_provenance_header(
    *,
    file_id: int,
    rel_path: str,
    file_kind: str,
    engine: str,
    extracted_at: str,
    extractor_version: str,
) -> str:
    """Provenance-Block, der vor dem eigentlichen Markdown-Inhalt steht.

    HTML-Kommentar-Form: in Markdown-Renderern unsichtbar, aber im FTS
    indizierbar und vom LLM lesbar. Enthaelt den Ordnerpfad — wichtig
    fuer Reasoning, weil der Ordner haeufig Zustand mitgibt
    (z.B. 'Geprueft', 'Nicht_geprueft').
    """
    from pathlib import PurePosixPath

    p = PurePosixPath(rel_path)
    folder = str(p.parent) if str(p.parent) != "." else ""
    return (
        f"<!-- provenance\n"
        f"file_id: {file_id}\n"
        f"rel_path: {rel_path}\n"
        f"folder: {folder}\n"
        f"filename: {p.name}\n"
        f"file_kind: {file_kind}\n"
        f"engine: {engine}\n"
        f"extracted_at: {extracted_at}\n"
        f"extractor_version: {extractor_version}\n"
        f"-->\n\n"
    )


__all__ = [
    "EXTRACTION_PIPELINE_VERSION",
    "ENGINES_BY_KIND",
    "file_kind_from_path",
    "kind_for_engine",
    "all_known_engines",
    "dispatch_extract",
    "build_provenance_header",
]
