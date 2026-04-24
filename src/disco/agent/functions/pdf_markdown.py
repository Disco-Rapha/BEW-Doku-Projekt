"""Agent-Tool: pdf_markdown_read.

Liest den Markdown-Inhalt einer PDF aus `agent_pdf_markdown`. Das ist
ab der Pipeline-Umstellung (2026-04-22) der einzige Weg, wie Disco an
PDF-Inhalte kommt — nicht mehr ueber pypdf / DI / Docling direkt.

Vorbedingung: die PDF wurde bereits per Flow `pdf_to_markdown` nach
Markdown konvertiert. Fehlt der Eintrag, liefert das Tool einen
klaren Hinweis, wie der Flow nachgezogen werden kann.

Seiten-Lookups (ab 2026-04-25):
  - `page=N`               : nur Seite N lesen (Seitenindex erforderlich).
  - `page_range="3-7"`     : Seiten 3..7 zusammenhaengend.
  - Faellt der Seitenindex leer (z.B. Docling vor per-Seite-Export),
    wird ein klarer Fehler mit Hinweis zurueckgegeben.
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

_PAGE_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


@register(
    name="pdf_markdown_read",
    description=(
        "Liest den extrahierten Markdown-Inhalt einer PDF aus "
        "`agent_pdf_markdown`. Das ist der einzige zulaessige Weg fuer "
        "Inhaltsfragen zu PDFs — Disco ruft NICHT mehr pypdf / Azure DI / "
        "Docling direkt auf.\n\n"
        "Vorbedingung: PDF muss bereits per Flow `pdf_to_markdown` nach "
        "Markdown konvertiert worden sein. Fehlt der Eintrag, bitte den "
        "Flow starten (`disco flow run pdf_to_markdown`), ggf. vorher "
        "`pdf_routing_decision`.\n\n"
        "Identifikation wahlweise ueber `rel_path` (Pfad relativ zum "
        "Projekt-Root, wie in agent_pdf_inventory.rel_path) oder `file_id`.\n\n"
        "Seiten-Lookups: `page=N` fuer eine einzelne Seite, "
        "`page_range=\"3-7\"` fuer einen Bereich. Beides nutzt den "
        "Seitenindex in `agent_pdf_page_offsets` (wird beim pdf_to_markdown-"
        "Flow mitgeschrieben). Ohne Seitenparameter liefert das Tool das "
        "ganze Dokument paginiert via offset/max_chars."
    ),
    parameters={
        "type": "object",
        "properties": {
            "rel_path": {
                "type": "string",
                "description": (
                    "Pfad zur PDF, relativ zum Projekt-Root "
                    "(z.B. 'sources/paket-2026-04/.../foo.pdf')."
                ),
            },
            "file_id": {
                "type": "integer",
                "description": "Alternativ: file_id aus agent_pdf_inventory.id.",
            },
            "page": {
                "type": "integer",
                "description": (
                    "Nur diese Seite zurueckgeben (1-basiert). Erfordert "
                    "einen Seitenindex in agent_pdf_page_offsets. Nicht "
                    "zusammen mit page_range verwenden."
                ),
            },
            "page_range": {
                "type": "string",
                "description": (
                    "Seitenbereich, z.B. '3-7' fuer Seite 3 bis Seite 7 "
                    "zusammenhaengend. Erfordert einen Seitenindex. Nicht "
                    "zusammen mit page verwenden."
                ),
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
                    "(Default 0). Fuer gezieltes Weiterlesen nach einem "
                    "truncated=true. Bezieht sich auf den gewaehlten "
                    "Ausschnitt (ganzes Dokument oder Seitenbereich)."
                ),
            },
        },
        "required": [],
    },
    returns=(
        "{file_id, rel_path, engine, char_count, content_offset, "
        "content_length, truncated, markdown, created_at, extractor_version, "
        "page, page_range, page_char_start, page_char_end}"
    ),
)
def _pdf_markdown_read(
    *,
    rel_path: str | None = None,
    file_id: int | None = None,
    page: int | None = None,
    page_range: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    offset: int = 0,
) -> dict[str, Any]:
    if not rel_path and not file_id:
        raise ValueError("Entweder rel_path oder file_id angeben.")
    if page is not None and page_range:
        raise ValueError(
            "page und page_range duerfen nicht zusammen gesetzt werden."
        )

    # Offset/Limit defensiv normalisieren
    effective_offset = max(0, int(offset or 0))
    effective_limit = max(1000, min(int(max_chars or DEFAULT_MAX_CHARS), MAX_MAX_CHARS))

    page_from: int | None = None
    page_to: int | None = None
    if page is not None:
        page_int = int(page)
        if page_int < 1:
            raise ValueError("page muss >= 1 sein.")
        page_from = page_to = page_int
    elif page_range:
        m = _PAGE_RANGE_RE.match(page_range)
        if not m:
            raise ValueError(
                f"page_range={page_range!r} ungueltig. Format: 'N-M', z.B. '3-7'."
            )
        page_from, page_to = int(m.group(1)), int(m.group(2))
        if page_from < 1 or page_to < 1:
            raise ValueError("page_range: beide Werte muessen >= 1 sein.")
        if page_from > page_to:
            raise ValueError(
                f"page_range: Start {page_from} > Ende {page_to}."
            )

    db_path = get_datastore_db_path()
    if db_path is None:
        raise RuntimeError(
            "Kein aktives Projekt — pdf_markdown_read nur im Projekt-Kontext."
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
                "SELECT file_id, rel_path, engine, md_content, char_count, "
                "       created_at, extractor_version "
                "FROM agent_pdf_markdown WHERE file_id = ?",
                (int(file_id),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT file_id, rel_path, engine, md_content, char_count, "
                "       created_at, extractor_version "
                "FROM agent_pdf_markdown WHERE rel_path = ?",
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
                    "Bitte zuerst den Flow `pdf_to_markdown` laufen lassen "
                    "(ggf. vorher `pdf_routing_decision` fuer die Engine-Wahl)."
                ),
            }

        md_full = row["md_content"] or ""
        total_chars = len(md_full)
        effective_file_id = int(row["file_id"])

        # Seiten-Lookup (wenn angefordert)
        page_char_start: int | None = None
        page_char_end: int | None = None
        source_text = md_full
        source_offset_in_doc = 0  # Offset des Ausschnitts im Gesamtdokument

        if page_from is not None and page_to is not None:
            offsets = conn.execute(
                "SELECT page_num, char_start, char_end "
                "FROM agent_pdf_page_offsets "
                "WHERE file_id = ? AND page_num BETWEEN ? AND ? "
                "ORDER BY page_num",
                (effective_file_id, page_from, page_to),
            ).fetchall()

            if not offsets:
                # Pruefen ob ueberhaupt Offsets fuer die Datei existieren,
                # damit der Fehler verstaendlich ist.
                any_exists = conn.execute(
                    "SELECT 1 FROM agent_pdf_page_offsets "
                    "WHERE file_id = ? LIMIT 1",
                    (effective_file_id,),
                ).fetchone()
                if any_exists is None:
                    return {
                        "error": (
                            f"Kein Seitenindex fuer file_id={effective_file_id} "
                            f"(rel_path={row['rel_path']!r}) vorhanden. "
                            "Das Dokument wurde vor der Seitenindex-Einfuehrung "
                            "(Migration 007, 2026-04-25) extrahiert oder von "
                            "einer Engine ohne Seiten-Offsets. Ohne page/"
                            "page_range-Parameter weiter nutzbar — fuer "
                            "Seiten-Lookups Flow `pdf_to_markdown` mit "
                            "force_rerun oder Backfill-Skript "
                            "`scripts/backfill_pdf_page_offsets.py` laufen lassen."
                        ),
                        "file_id": effective_file_id,
                        "rel_path": row["rel_path"],
                    }
                return {
                    "error": (
                        f"Keine Seiten {page_from}..{page_to} fuer "
                        f"file_id={effective_file_id} gefunden. "
                        f"Dokument hat moeglicherweise weniger Seiten."
                    ),
                    "file_id": effective_file_id,
                    "rel_path": row["rel_path"],
                }

            page_char_start = int(offsets[0]["char_start"])
            page_char_end = int(offsets[-1]["char_end"])
            # Gueltig clampen (Schutz vor Index-Drift)
            page_char_start = max(0, min(page_char_start, total_chars))
            page_char_end = max(page_char_start, min(page_char_end, total_chars))
            source_text = md_full[page_char_start:page_char_end]
            source_offset_in_doc = page_char_start
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
        "engine": row["engine"],
        "char_count": row["char_count"],
        "content_offset": start + source_offset_in_doc,
        "content_length": len(chunk),
        "truncated": truncated,
        "markdown": chunk,
        "created_at": row["created_at"],
        "extractor_version": row["extractor_version"],
    }
    if page_from is not None and page_to is not None:
        result["page"] = page_from if page_from == page_to else None
        result["page_range"] = (
            None if page_from == page_to else f"{page_from}-{page_to}"
        )
        result["page_char_start"] = page_char_start
        result["page_char_end"] = page_char_end
    return result
