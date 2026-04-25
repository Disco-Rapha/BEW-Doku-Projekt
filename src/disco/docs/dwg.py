"""DWG/DXF-Extractor — ezdxf basierter Markdown-Renderer.

Engine:
  - dwg-ezdxf-local — DXF direkt, DWG via libredwg `dwg2dxf` + Sanitizer.
                      LibreDWG ist GPL-3 und wird als externes CLI-Tool
                      per Subprocess aufgerufen ("mere aggregation").

Output-Format:
  ## Schriftfeld
  | Feld | Wert |
  |---|---|
  | Zeichnungsnummer | ... |
  | Titel | ... |

  ## Texte auf der Zeichnung (insgesamt N)
  ### Layer BESCHRIFTUNG (47)
  - "T1 - 630 kVA"
  - ...

Strategie:
  - Schriftfeld = INSERT mit ATTRIBs > 3 (heuristisch)
  - Texte = TEXT/MTEXT-Entities, gruppiert nach Layer
  - Bemassungs-Texte aus DIMENSION-Entities mit dim_text
  - DWG-Pfad: libredwg dwg2dxf → DXF-Sanitizer → ezdxf.recover
  - DXF-Pfad: direkt ezdxf

Setup:
  - DXF allein: nichts noetig (ezdxf builtin).
  - DWG: libredwg installieren via `bash scripts/install-libredwg.sh`.
    Siehe docs/dwg-setup.md.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import EXTRACTION_PIPELINE_VERSION

logger = logging.getLogger(__name__)

_ENGINE_VERSIONS: dict[str, str] = {
    "dwg-ezdxf-local": "1.0",
}

# Heuristik: Block-Insertions mit >= dieser Anzahl ATTRIBs gelten als
# potenzielles Schriftfeld
_TITLEBLOCK_MIN_ATTRIBS = 4


def extract(path: Path, engine: str) -> tuple[str, dict[str, Any]]:
    if engine not in _ENGINE_VERSIONS:
        raise ValueError(f"Unbekannte DWG-Engine: {engine!r}")

    import ezdxf
    from ezdxf import recover

    suffix = path.suffix.lower()
    if suffix == ".dwg":
        # DWG → DXF via libredwg, dann Sanitizer fuer ezdxf-Strict-Quirks
        from . import _dwg_libredwg as _lib
        import tempfile

        tmp_dir = Path(tempfile.gettempdir()) / "disco-dwg-extract"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        # Eindeutiger Tmp-Name pro Source (Hash-frei reicht hier)
        tmp_dxf = tmp_dir / f"{path.stem}.{abs(hash(str(path))) & 0xFFFFFFFF:08x}.dxf"
        try:
            _lib.convert_dwg_to_dxf(path, tmp_dxf)
        except _lib.LibreDwgNotInstalled as exc:
            raise RuntimeError(str(exc)) from exc

        # Sanitize gegen Sort-Handle-Bug
        cleaned_dxf = _lib.sanitize_libredwg_dxf(tmp_dxf)
        try:
            doc, audit = recover.readfile(str(cleaned_dxf))
        except Exception as exc:
            raise RuntimeError(
                f"DXF-Read nach LibreDWG-Konvertierung fehlgeschlagen. "
                f"Original-Fehler: {exc}"
            ) from exc
    elif suffix == ".dxf":
        doc = ezdxf.readfile(str(path))
    else:
        raise ValueError(f"DWG-Engine erwartet .dwg oder .dxf, bekam {suffix}")

    msp = doc.modelspace()

    # 1) Titleblock-Kandidaten finden (INSERT mit ATTRIBs)
    titleblock_attribs: list[tuple[str, str]] = []
    titleblock_block_name = ""
    best_attrib_count = 0
    for entity in msp.query("INSERT"):
        attribs = list(entity.attribs) if hasattr(entity, "attribs") else []
        if len(attribs) >= _TITLEBLOCK_MIN_ATTRIBS and len(attribs) > best_attrib_count:
            best_attrib_count = len(attribs)
            titleblock_block_name = getattr(entity, "name", "") or getattr(entity.dxf, "name", "")
            titleblock_attribs = [
                (
                    str(getattr(a.dxf, "tag", "?")).strip(),
                    str(getattr(a.dxf, "text", "")).strip(),
                )
                for a in attribs
            ]

    # 2) TEXT/MTEXT-Entities nach Layer gruppieren
    text_by_layer: dict[str, list[str]] = defaultdict(list)
    for entity in msp.query("TEXT MTEXT"):
        layer = str(getattr(entity.dxf, "layer", "0"))
        text = ""
        if entity.dxftype() == "MTEXT":
            text = entity.plain_text() if hasattr(entity, "plain_text") else str(getattr(entity.dxf, "text", ""))
        else:
            text = str(getattr(entity.dxf, "text", ""))
        text = text.strip()
        if text:
            text_by_layer[layer].append(text)

    # 3) DIMENSION-Texte (best-effort)
    dim_texts: list[str] = []
    for entity in msp.query("DIMENSION"):
        try:
            dt = str(getattr(entity.dxf, "text", "")).strip()
        except Exception:
            dt = ""
        if dt and dt not in ("<>", ""):
            dim_texts.append(dt)

    # 4) TABLE-Entities (DIN-A-Schriftfeld als TABLE seit AC 2005)
    table_blocks: list[list[list[str]]] = []
    try:
        for entity in msp.query("ACAD_TABLE"):
            tab_rows: list[list[str]] = []
            n_rows = getattr(entity, "n_rows", None) or getattr(entity.dxf, "n_rows", 0)
            n_cols = getattr(entity, "n_cols", None) or getattr(entity.dxf, "n_cols", 0)
            for r in range(int(n_rows or 0)):
                row_vals: list[str] = []
                for c in range(int(n_cols or 0)):
                    try:
                        cell = entity.get_cell_text(r, c) or ""
                    except Exception:
                        cell = ""
                    row_vals.append(str(cell).strip())
                tab_rows.append(row_vals)
            if tab_rows:
                table_blocks.append(tab_rows)
    except Exception:
        pass  # ACAD_TABLE nicht in jedem ezdxf-Setup verfuegbar

    # --- Markdown rendern + Offsets ---
    md_parts: list[str] = []
    unit_offsets: list[dict[str, Any]] = []
    cursor = 0

    def _add_unit(label: str, content: str) -> None:
        nonlocal cursor
        char_start = cursor
        if md_parts:
            md_parts.append("\n")
            cursor += 1
            char_start = cursor
        md_parts.append(content)
        cursor += len(content)
        unit_offsets.append({
            "unit_num": len(unit_offsets) + 1,
            "unit_label": label,
            "char_start": char_start,
            "char_end": cursor,
        })

    if titleblock_attribs:
        lines = [f"## Schriftfeld",
                 f"_(Block: `{_md_escape(titleblock_block_name) or 'unbenannt'}`, "
                 f"{len(titleblock_attribs)} Attribute)_", "",
                 "| Feld | Wert |", "|---|---|"]
        for tag, value in titleblock_attribs:
            lines.append(f"| {_md_escape(tag)} | {_md_escape(value)} |")
        _add_unit("Schriftfeld", "\n".join(lines) + "\n")

    if text_by_layer:
        n_total = sum(len(v) for v in text_by_layer.values())
        lines = [f"## Texte auf der Zeichnung (insgesamt {n_total})", ""]
        # Layer mit den meisten Texten zuerst
        for layer in sorted(text_by_layer, key=lambda k: -len(text_by_layer[k])):
            texts = text_by_layer[layer]
            lines.append(f"### Layer {_md_escape(layer)} ({len(texts)})")
            for t in texts:
                lines.append(f"- {_md_escape(t)}")
            lines.append("")
        _add_unit("Texte", "\n".join(lines) + "\n")

    if dim_texts:
        lines = [f"## Bemassungs-Texte ({len(dim_texts)})", ""]
        for t in dim_texts:
            lines.append(f"- {_md_escape(t)}")
        _add_unit("Bemassungen", "\n".join(lines) + "\n")

    if table_blocks:
        for i, rows in enumerate(table_blocks, start=1):
            lines = [f"## Tabelle {i}"]
            if rows:
                lines.append("| " + " | ".join(_md_escape(c) for c in rows[0]) + " |")
                lines.append("|" + "|".join(["---"] * len(rows[0])) + "|")
                for r in rows[1:]:
                    lines.append("| " + " | ".join(_md_escape(c) for c in r) + " |")
            _add_unit(f"Tabelle{i}", "\n".join(lines) + "\n")

    if not md_parts:
        # Leerer DWG/DXF — wenigstens Hinweis
        _add_unit("leer", "_(keine Texte / kein Schriftfeld erkannt)_\n")

    md = "".join(md_parts)
    char_count = len(md)

    engine_version = _ENGINE_VERSIONS.get(engine, "1.0")
    meta: dict[str, Any] = {
        "file_kind": "dwg",
        "engine": engine,
        "n_units": len(unit_offsets),
        "char_count": char_count,
        "unit_offsets": unit_offsets,
        "estimated_cost_eur": 0.0,
        "extractor_version": (
            f"{EXTRACTION_PIPELINE_VERSION}:{engine}:{engine_version}"
        ),
        "meta_json": {
            "titleblock_block_name": titleblock_block_name,
            "n_titleblock_attribs": len(titleblock_attribs),
            "n_text_layers": len(text_by_layer),
            "n_text_entities": sum(len(v) for v in text_by_layer.values()),
            "n_dim_entities": len(dim_texts),
            "n_acad_tables": len(table_blocks),
            "format": suffix.lstrip("."),
        },
    }
    return md, meta


def _md_escape(s: Any) -> str:
    if s is None:
        return ""
    s = str(s)
    s = s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    return s.strip()


__all__ = ["extract"]
