"""Markdown-Analyse-Tools fuer grosse Dokumente.

Wenn ein DI-Extrakt zu gross fuer den Chat-Kontext ist (> 50 KB),
kann Disco die Struktur extrahieren statt den Volltext zu lesen.
Das ergibt ein kompaktes Skelett-Dokument (~5-15 KB) das die
Kapitelstruktur, Tabellen-Header und Schluessel-Saetze enthaelt.
"""

from __future__ import annotations

import re
from typing import Any

from . import register
from .fs import _data_root, _resolve_under_data


@register(
    name="extract_markdown_structure",
    description=(
        "Extrahiert die STRUKTUR eines grossen Markdown-Dokuments: "
        "alle Ueberschriften, erster Satz je Abschnitt, Tabellen-Header, "
        "Seiten-Marker. Ergebnis ist ein kompaktes Skelett (~5-15 KB) "
        "das in den Chat-Kontext passt, auch wenn das Original 1+ MB ist.\n\n"
        "WANN NUTZEN: Wenn ein DI-Extrakt zu gross fuer fs_read ist "
        "(> 50 KB / > 12.000 Tokens). Statt den Volltext zu laden, "
        "erst die Struktur extrahieren, dann gezielt Abschnitte per "
        "fs_read mit offset nachladen.\n\n"
        "Liefert: Kapitel-Baum mit Seitenzahlen, Tabellen-Uebersicht, "
        "Gesamtstatistik (Zeichen, Woerter, Tabellen, Bilder)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad zur .md-Datei, relativ zum Projekt.",
            },
            "max_first_lines": {
                "type": "integer",
                "description": (
                    "Wie viele Zeilen nach jeder Ueberschrift als Vorschau "
                    "mitgenommen werden (Default 2)."
                ),
            },
            "include_table_headers": {
                "type": "boolean",
                "description": "Tabellen-Koepfe (erste Zeile) mit extrahieren (Default true).",
            },
        },
        "required": ["path"],
    },
    returns=(
        "{path, total_chars, total_lines, total_words, n_headings, "
        "n_tables, n_images, n_page_markers, structure_text, "
        "structure_chars, too_large_for_context}"
    ),
)
def _extract_markdown_structure(
    *,
    path: str,
    max_first_lines: int = 2,
    include_table_headers: bool = True,
) -> dict[str, Any]:
    target = _resolve_under_data(path)
    if not target.exists():
        raise ValueError(f"Datei nicht gefunden: {path!r}")

    text = target.read_text(encoding="utf-8")
    lines = text.split("\n")

    total_chars = len(text)
    total_lines = len(lines)
    total_words = len(text.split())

    # Seiten-Marker zaehlen (<!-- Seite N -->)
    page_markers = re.findall(r"<!-- Seite (\d+) -->", text)
    n_page_markers = len(page_markers)

    # Tabellen zaehlen (| ... | Muster, mindestens 2 Zeilen)
    n_tables = 0
    n_images = text.count("![")

    # Struktur extrahieren
    out_lines: list[str] = []
    out_lines.append(f"# Struktur: {target.name}")
    out_lines.append(f"# Gesamt: {total_chars:,} Zeichen, {total_lines:,} Zeilen, "
                     f"{total_words:,} Woerter")
    if n_page_markers:
        out_lines.append(f"# Seiten: {n_page_markers} (von Seite {page_markers[0]} bis {page_markers[-1]})")
    out_lines.append("")

    current_page = ""
    in_table = False
    table_header_captured = False
    lines_after_heading = 0
    capture_lines = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Seiten-Marker tracken
        page_match = re.match(r"<!-- Seite (\d+) -->", stripped)
        if page_match:
            current_page = f" [S.{page_match.group(1)}]"
            continue

        # Ueberschriften immer mitnehmen
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped.lstrip("#").strip()
            if heading_text:
                out_lines.append(f"{'#' * level} {heading_text}{current_page}")
                capture_lines = max_first_lines
                lines_after_heading = 0
                in_table = False
                table_header_captured = False
                continue

        # Erste N Zeilen nach Ueberschrift mitnehmen (Kontext)
        if capture_lines > 0 and stripped:
            if not stripped.startswith("|") and not stripped.startswith("---"):
                out_lines.append(f"  > {stripped[:200]}")
                capture_lines -= 1
                continue

        # Tabellen-Header erkennen und mitnehmen
        if include_table_headers and stripped.startswith("|"):
            if not in_table:
                in_table = True
                table_header_captured = False
                n_tables += 1
            if not table_header_captured:
                # Erste Zeile der Tabelle (Header)
                out_lines.append(f"  [Tabelle]{current_page} {stripped[:250]}")
                table_header_captured = True
                # Separator-Zeile ueberspringen
                continue
            # Rest der Tabelle ignorieren
            continue
        else:
            if in_table:
                in_table = False

    structure_text = "\n".join(out_lines)

    return {
        "path": path,
        "total_chars": total_chars,
        "total_lines": total_lines,
        "total_words": total_words,
        "n_headings": sum(1 for l in out_lines if l.startswith("#") and not l.startswith("# Gesamt") and not l.startswith("# Seiten") and not l.startswith("# Struktur")),
        "n_tables": n_tables,
        "n_images": n_images,
        "n_page_markers": n_page_markers,
        "structure_text": structure_text,
        "structure_chars": len(structure_text),
        "too_large_for_context": total_chars > 50_000,
    }
