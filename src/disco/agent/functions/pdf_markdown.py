"""Agent-Tool: pdf_markdown_read.

Liest den Markdown-Inhalt einer PDF aus `agent_pdf_markdown`. Das ist
ab der Pipeline-Umstellung (2026-04-22) der einzige Weg, wie Disco an
PDF-Inhalte kommt — nicht mehr ueber pypdf / DI / Docling direkt.

Vorbedingung: die PDF wurde bereits per Flow `pdf_to_markdown` nach
Markdown konvertiert. Fehlt der Eintrag, liefert das Tool einen
klaren Hinweis, wie der Flow nachgezogen werden kann.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from . import register
from ..context import get_project_db_path


logger = logging.getLogger(__name__)


DEFAULT_MAX_CHARS = 50_000
MAX_MAX_CHARS = 500_000


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
        "Projekt-Root, wie in agent_pdf_inventory.rel_path) oder `file_id`."
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
                    "truncated=true."
                ),
            },
        },
        "required": [],
    },
    returns=(
        "{file_id, rel_path, engine, char_count, content_offset, "
        "content_length, truncated, markdown, created_at}"
    ),
)
def _pdf_markdown_read(
    *,
    rel_path: str | None = None,
    file_id: int | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    offset: int = 0,
) -> dict[str, Any]:
    if not rel_path and not file_id:
        raise ValueError("Entweder rel_path oder file_id angeben.")

    # Offset/Limit defensiv normalisieren
    effective_offset = max(0, int(offset or 0))
    effective_limit = max(1000, min(int(max_chars or DEFAULT_MAX_CHARS), MAX_MAX_CHARS))

    db_path = get_project_db_path()
    if db_path is None:
        raise RuntimeError(
            "Kein aktives Projekt — pdf_markdown_read nur im Projekt-Kontext."
        )
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        if file_id is not None:
            row = conn.execute(
                "SELECT file_id, rel_path, engine, md_content, char_count, "
                "       created_at "
                "FROM agent_pdf_markdown WHERE file_id = ?",
                (int(file_id),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT file_id, rel_path, engine, md_content, char_count, "
                "       created_at "
                "FROM agent_pdf_markdown WHERE rel_path = ?",
                (str(rel_path),),
            ).fetchone()
    finally:
        conn.close()

    if row is None:
        ident = f"file_id={file_id}" if file_id is not None else f"rel_path={rel_path!r}"
        return {
            "error": (
                f"Kein Markdown-Eintrag fuer {ident}. "
                "Bitte zuerst den Flow `pdf_to_markdown` laufen lassen "
                "(ggf. vorher `pdf_routing_decision` fuer die Engine-Wahl)."
            ),
        }

    md_full = row["md_content"] or ""
    total_chars = len(md_full)

    start = min(effective_offset, total_chars)
    end = min(start + effective_limit, total_chars)
    chunk = md_full[start:end]
    truncated = end < total_chars

    return {
        "file_id": row["file_id"],
        "rel_path": row["rel_path"],
        "engine": row["engine"],
        "char_count": row["char_count"],
        "content_offset": start,
        "content_length": len(chunk),
        "truncated": truncated,
        "markdown": chunk,
        "created_at": row["created_at"],
    }
