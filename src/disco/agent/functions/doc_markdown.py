"""Agent-Tool: doc_markdown_read.

Liest den extrahierten Markdown-Inhalt einer Datei (PDF/Excel/DWG/Bild)
aus `agent_doc_markdown`. Einheitlicher Lesepfad fuer alle Formate seit
der Pipeline-Generalisierung 2026-04-25.

Vorbedingung: Datei wurde bereits per Flow `extraction` nach Markdown
konvertiert. Fehlt der Eintrag, liefert das Tool einen klaren Hinweis.

Unit-Lookups (PDF: Seite, Excel: Sheet, DWG: Sektion, Bild: 1):
  - `unit=N`               : nur Unit N lesen (Unit-Index erforderlich).
  - `unit_range="3-7"`     : Units 3..7 zusammenhaengend.
  - `unit_label="Sheet1"`  : Lookup nach Label-String (z.B. Sheet-Name).
  - `page=N` / `page_range="3-7"`: Aliase fuer Unit-Lookup (PDF-Convenience).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any

from . import register
from ..context import get_datastore_db_path


logger = logging.getLogger(__name__)


DEFAULT_MAX_CHARS = 50_000
MAX_MAX_CHARS = 500_000

_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


@register(
    name="doc_markdown_read",
    description=(
        "Liest den extrahierten Markdown-Inhalt einer Datei aus "
        "`agent_doc_markdown` (Ebene 2). Einheitlicher Lesepfad fuer "
        "PDF, Excel, DWG und Bild — Disco ruft KEINE Engine-spezifischen "
        "Reader (pypdf, openpyxl, ezdxf, …) direkt auf.\n\n"
        "Vorbedingung: Datei muss per Flow `extraction` nach Markdown "
        "konvertiert worden sein. Fehlt der Eintrag, bitte den Flow "
        "starten (`disco flow run extraction`), ggf. vorher "
        "`extraction_routing_decision`.\n\n"
        "Identifikation wahlweise ueber `rel_path` (Pfad relativ zum "
        "Projekt-Root) oder `file_id` (aus agent_sources.id).\n\n"
        "Unit-Lookups: `unit=N` fuer eine einzelne Unit, "
        "`unit_range=\"3-7\"` fuer einen Bereich, `unit_label=\"Sheet1\"` "
        "fuer Lookup nach Label. PDF-Aliase `page` und `page_range` "
        "funktionieren weiterhin. Ohne Unit-Parameter liefert das Tool "
        "das ganze Dokument paginiert via offset/max_chars."
    ),
    parameters={
        "type": "object",
        "properties": {
            "rel_path": {
                "type": "string",
                "description": (
                    "Pfad zur Datei, relativ zum Projekt-Root "
                    "(z.B. 'sources/Geprueft/foo.pdf')."
                ),
            },
            "file_id": {
                "type": "integer",
                "description": "Alternativ: file_id aus agent_sources.id.",
            },
            "unit": {
                "type": "integer",
                "description": (
                    "Nur diese Unit zurueckgeben (1-basiert). PDF: Seite, "
                    "Excel: Sheet-Index, DWG: Sektion, Bild: nur 1."
                ),
            },
            "unit_range": {
                "type": "string",
                "description": (
                    "Unit-Bereich, z.B. '3-7' fuer Unit 3 bis 7 "
                    "zusammenhaengend."
                ),
            },
            "unit_label": {
                "type": "string",
                "description": (
                    "Lookup ueber Label-String. Beispiel: 'Sheet1' bei "
                    "Excel, 'Schriftfeld' bei DWG, 'p3' bei PDF."
                ),
            },
            "page": {
                "type": "integer",
                "description": "Alias fuer unit (PDF-Convenience).",
            },
            "page_range": {
                "type": "string",
                "description": "Alias fuer unit_range (PDF-Convenience).",
            },
            "max_chars": {
                "type": "integer",
                "description": (
                    f"Max Zeichen (Default {DEFAULT_MAX_CHARS}, "
                    f"Hard-Cap {MAX_MAX_CHARS}). Bei Ueberschreitung wird "
                    f"gekuerzt und truncated=true gesetzt."
                ),
            },
            "offset": {
                "type": "integer",
                "description": (
                    "0-basierter Zeichen-Offset ab dem gelesen wird "
                    "(Default 0)."
                ),
            },
        },
        "required": [],
    },
    returns=(
        "{file_id, rel_path, file_kind, engine, char_count, content_offset, "
        "content_length, truncated, markdown, created_at, extractor_version, "
        "unit, unit_range, unit_label, unit_char_start, unit_char_end}"
    ),
)
def _doc_markdown_read(
    *,
    rel_path: str | None = None,
    file_id: int | None = None,
    unit: int | None = None,
    unit_range: str | None = None,
    unit_label: str | None = None,
    page: int | None = None,
    page_range: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    offset: int = 0,
) -> dict[str, Any]:
    if not rel_path and not file_id:
        raise ValueError("Entweder rel_path oder file_id angeben.")

    # PDF-Aliase auf generische Parameter mappen
    if unit is None and page is not None:
        unit = page
    if unit_range is None and page_range:
        unit_range = page_range

    n_unit_args = sum(1 for x in (unit, unit_range, unit_label) if x is not None and x != "")
    if n_unit_args > 1:
        raise ValueError(
            "unit / unit_range / unit_label sind exklusiv — bitte nur einen Parameter setzen."
        )

    # Offset/Limit defensiv normalisieren
    effective_offset = max(0, int(offset or 0))
    effective_limit = max(1000, min(int(max_chars or DEFAULT_MAX_CHARS), MAX_MAX_CHARS))

    unit_from: int | None = None
    unit_to: int | None = None
    if unit is not None:
        u_int = int(unit)
        if u_int < 1:
            raise ValueError("unit muss >= 1 sein.")
        unit_from = unit_to = u_int
    elif unit_range:
        m = _RANGE_RE.match(unit_range)
        if not m:
            raise ValueError(
                f"unit_range={unit_range!r} ungueltig. Format: 'N-M', z.B. '3-7'."
            )
        unit_from, unit_to = int(m.group(1)), int(m.group(2))
        if unit_from < 1 or unit_to < 1:
            raise ValueError("unit_range: beide Werte muessen >= 1 sein.")
        if unit_from > unit_to:
            raise ValueError(
                f"unit_range: Start {unit_from} > Ende {unit_to}."
            )

    db_path = get_datastore_db_path()
    if db_path is None:
        raise RuntimeError(
            "Kein aktives Projekt — doc_markdown_read nur im Projekt-Kontext."
        )
    if not db_path.exists():
        raise RuntimeError(
            f"datastore.db fehlt ({db_path}) — erst Projekt initialisieren."
        )
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        if file_id is not None:
            row = conn.execute(
                "SELECT file_id, rel_path, file_kind, engine, md_content, "
                "       char_count, n_units, created_at, extractor_version "
                "FROM agent_doc_markdown WHERE file_id = ?",
                (int(file_id),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT file_id, rel_path, file_kind, engine, md_content, "
                "       char_count, n_units, created_at, extractor_version "
                "FROM agent_doc_markdown WHERE rel_path = ?",
                (str(rel_path),),
            ).fetchone()

        if row is None:
            ident = (
                f"file_id={file_id}" if file_id is not None
                else f"rel_path={rel_path!r}"
            )
            return {
                "error": (
                    f"Kein Markdown-Eintrag fuer {ident}. "
                    "Bitte zuerst den Flow `extraction` laufen lassen "
                    "(ggf. vorher `extraction_routing_decision`)."
                ),
            }

        md_full = row["md_content"] or ""
        total_chars = len(md_full)
        effective_file_id = int(row["file_id"])

        # Unit-Lookup (wenn angefordert)
        unit_char_start: int | None = None
        unit_char_end: int | None = None
        unit_label_used: str | None = None
        source_text = md_full
        source_offset_in_doc = 0

        if unit_label:
            o = conn.execute(
                "SELECT unit_num, unit_label, char_start, char_end "
                "FROM agent_doc_unit_offsets "
                "WHERE file_id = ? AND unit_label = ? "
                "ORDER BY unit_num",
                (effective_file_id, unit_label),
            ).fetchone()
            if not o:
                return _missing_unit_error(
                    conn, effective_file_id, row["rel_path"],
                    f"label={unit_label!r}",
                )
            unit_char_start = int(o["char_start"])
            unit_char_end = int(o["char_end"])
            unit_label_used = o["unit_label"]
            unit_from = unit_to = int(o["unit_num"])
        elif unit_from is not None and unit_to is not None:
            offsets = conn.execute(
                "SELECT unit_num, unit_label, char_start, char_end "
                "FROM agent_doc_unit_offsets "
                "WHERE file_id = ? AND unit_num BETWEEN ? AND ? "
                "ORDER BY unit_num",
                (effective_file_id, unit_from, unit_to),
            ).fetchall()
            if not offsets:
                return _missing_unit_error(
                    conn, effective_file_id, row["rel_path"],
                    f"unit={unit_from}..{unit_to}",
                )
            unit_char_start = int(offsets[0]["char_start"])
            unit_char_end = int(offsets[-1]["char_end"])
            if len(offsets) == 1:
                unit_label_used = offsets[0]["unit_label"]

        if unit_char_start is not None and unit_char_end is not None:
            unit_char_start = max(0, min(unit_char_start, total_chars))
            unit_char_end = max(unit_char_start, min(unit_char_end, total_chars))
            source_text = md_full[unit_char_start:unit_char_end]
            source_offset_in_doc = unit_char_start
    finally:
        conn.close()

    total_source_chars = len(source_text)
    start = min(effective_offset, total_source_chars)
    end = min(start + effective_limit, total_source_chars)
    chunk = source_text[start:end]
    truncated = end < total_source_chars

    result: dict[str, Any] = {
        "file_id": effective_file_id,
        "rel_path": row["rel_path"],
        "file_kind": row["file_kind"],
        "engine": row["engine"],
        "char_count": row["char_count"],
        "n_units": row["n_units"],
        "content_offset": start + source_offset_in_doc,
        "content_length": len(chunk),
        "truncated": truncated,
        "markdown": chunk,
        "created_at": row["created_at"],
        "extractor_version": row["extractor_version"],
    }
    if unit_from is not None and unit_to is not None:
        result["unit"] = unit_from if unit_from == unit_to else None
        result["unit_range"] = (
            None if unit_from == unit_to else f"{unit_from}-{unit_to}"
        )
        result["unit_label"] = unit_label_used
        result["unit_char_start"] = unit_char_start
        result["unit_char_end"] = unit_char_end
    return result


def _missing_unit_error(
    conn: sqlite3.Connection,
    file_id: int,
    rel_path: str,
    selector: str,
) -> dict[str, Any]:
    """Klare Fehlermeldung wenn Unit-Lookup leer ist."""
    any_exists = conn.execute(
        "SELECT 1 FROM agent_doc_unit_offsets "
        "WHERE file_id = ? LIMIT 1",
        (file_id,),
    ).fetchone()
    if any_exists is None:
        return {
            "error": (
                f"Kein Unit-Index fuer file_id={file_id} "
                f"(rel_path={rel_path!r}). Vermutlich vor dem "
                "Pipeline-Umbau (Migration 008, 2026-04-25) extrahiert. "
                "Flow `extraction` mit force_rerun starten, oder "
                "Backfill-Skript nutzen."
            ),
            "file_id": file_id,
            "rel_path": rel_path,
        }
    return {
        "error": (
            f"Kein Treffer fuer {selector} in file_id={file_id}. "
            f"Dokument hat moeglicherweise weniger Units."
        ),
        "file_id": file_id,
        "rel_path": rel_path,
    }
