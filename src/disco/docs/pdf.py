"""PDF-Extractor — duenner Adapter ueber disco.pdf.markdown.

Die eigentliche Engine-Logik (azure-di, azure-di-hr, docling-standard) lebt
unter `disco.pdf.markdown.extract_markdown`. Hier ist der einheitliche
Wrapper fuer die generische Pipeline-Schnittstelle.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import EXTRACTION_PIPELINE_VERSION


# Engine-Versions (bei Aenderung am Engine-Output bumpen)
_ENGINE_VERSIONS: dict[str, str] = {
    "pdf-azure-di": "1.0",
    "pdf-azure-di-hr": "1.0",
    "pdf-docling-standard": "1.0",
}

# Mapping unsere generischen Engine-IDs auf die alte Bezeichnung in disco.pdf
_LEGACY_ENGINE_MAP: dict[str, str] = {
    "pdf-azure-di": "azure-di",
    "pdf-azure-di-hr": "azure-di-hr",
    "pdf-docling-standard": "docling-standard",
}


def extract(path: Path, engine: str) -> tuple[str, dict[str, Any]]:
    if engine not in _LEGACY_ENGINE_MAP:
        raise ValueError(f"Unbekannte PDF-Engine: {engine!r}")

    legacy_engine = _LEGACY_ENGINE_MAP[engine]
    from disco.pdf import extract_markdown

    md, legacy_meta = extract_markdown(path, legacy_engine)

    n_pages = legacy_meta.get("n_pages", 0)
    char_count = legacy_meta.get("char_count", len(md))
    page_offsets = legacy_meta.get("page_offsets", []) or []

    # Generic unit_offsets aus PDF page_offsets ableiten
    unit_offsets = [
        {
            "unit_num": po["page_num"],
            "unit_label": f"p{po['page_num']}",
            "char_start": po["char_start"],
            "char_end": po["char_end"],
        }
        for po in page_offsets
    ]

    engine_version = _ENGINE_VERSIONS.get(engine, "1.0")

    meta: dict[str, Any] = {
        "file_kind": "pdf",
        "engine": engine,
        "n_units": n_pages,
        "char_count": char_count,
        "unit_offsets": unit_offsets,
        "estimated_cost_eur": float(legacy_meta.get("estimated_cost_eur", 0.0)),
        "extractor_version": (
            f"{EXTRACTION_PIPELINE_VERSION}:{engine}:{engine_version}"
        ),
        "meta_json": {
            "n_pages": n_pages,
            "duration_ms": legacy_meta.get("duration_ms"),
            "legacy_extractor_version": legacy_meta.get("extractor_version"),
        },
    }
    return md, meta


__all__ = ["extract"]
