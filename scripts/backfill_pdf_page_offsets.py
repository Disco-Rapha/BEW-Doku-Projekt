#!/usr/bin/env python
"""Backfill: agent_pdf_page_offsets aus Bestandsmarkdown rekonstruieren.

Hintergrund:
    Bis Migration 007 (2026-04-25) standen Seitenangaben nur als
    `<!-- Seite N -->`-HTML-Kommentare im Markdown-Text (durch
    _extract_azure_di eingefuegt). Ab Migration 007 wird ein expliziter
    Offset-Index in `agent_pdf_page_offsets` geschrieben — aber nur
    fuer Neuextraktionen.

    Dieses Skript liest die Bestandsmarkdown-Zeilen (extractor_version
    IS NULL) und rekonstruiert die Seiten-Offsets:

      - Azure-DI-Rows mit Markern: Offsets aus Markerpositionen ableiten.
      - Azure-DI-Rows ohne Marker (einseitige PDFs): eine Offset-Zeile
        (Seite 1, 0..len(md)).
      - Docling-Rows: legacy ohne Seitentrennung — nur extractor_version
        markieren, keine Offsets.

    Idempotent: Rows mit extractor_version IS NOT NULL werden uebersprungen.
    Keine DI-Kosten, keine Re-Extraktion.

Usage:
    # Alle Projekte im aktuellen Workspace (DISCO_WORKSPACE)
    uv run scripts/backfill_pdf_page_offsets.py

    # Nur ein Projekt
    uv run scripts/backfill_pdf_page_offsets.py --project bew-rsd-campus-reuter

    # Dry-Run (zeigt nur, was passieren wuerde)
    uv run scripts/backfill_pdf_page_offsets.py --dry-run

    # Alternatives Workspace
    DISCO_WORKSPACE=~/Disco-dev \\
      uv run scripts/backfill_pdf_page_offsets.py --project mein-slug
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Projekt-Wurzel in sys.path (kein uv-Package-Install noetig)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from disco.config import settings  # noqa: E402
from disco.workspace import apply_project_db_migrations  # noqa: E402


BACKFILL_VERSION_TAG = "backfill-2026-04-25"

# Marker-Pattern wie von _extract_azure_di vor 2026-04-25 eingefuegt:
# immer "\n\n<!-- Seite N -->\n\n". Regex ist bewusst tolerant bei den
# inneren Whitespaces, aber strikt bei den umschliessenden "\n\n".
_LEGACY_MARKER_RE = re.compile(r"\n\n<!--\s*Seite\s+(\d+)\s*-->\n\n")


def compute_offsets_from_markers(md: str) -> list[dict[str, int]]:
    """Leitet Seiten-Offsets aus `<!-- Seite N -->`-Markern ab.

    Seite 1 hat keinen Marker (beginnt bei Offset 0); Seiten 2..N
    werden durch ihre Marker markiert. Rueckgabe leer, wenn keine
    Marker gefunden (typisch fuer einseitige PDFs oder Docling-Legacy —
    Aufrufer entscheidet separat).
    """
    matches = list(_LEGACY_MARKER_RE.finditer(md))
    if not matches:
        return []

    offsets: list[dict[str, int]] = [
        {
            "page_num": 1,
            "char_start": 0,
            "char_end": matches[0].start(),
        }
    ]
    for i, m in enumerate(matches):
        page_num = int(m.group(1))
        char_start = m.end()
        char_end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        offsets.append(
            {
                "page_num": page_num,
                "char_start": char_start,
                "char_end": char_end,
            }
        )
    return offsets


def process_project(
    project_path: Path,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Backfill fuer ein einzelnes Projekt.

    Wendet erst die ausstehenden Datastore-Migrationen an (idempotent —
    Migration 007 legt agent_pdf_page_offsets an, falls noch nicht da).
    Anschliessend werden alle agent_pdf_markdown-Rows mit NULL-Version
    verarbeitet.
    """
    datastore_db = project_path / "datastore.db"
    if not datastore_db.exists():
        return {
            "slug": project_path.name,
            "skipped_reason": "datastore.db fehlt",
            "rows_total": 0,
            "rows_updated": 0,
            "rows_already_versioned": 0,
            "rows_with_markers": 0,
            "rows_single_page": 0,
            "rows_docling_legacy": 0,
            "pages_written": 0,
        }

    # Migrationen anwenden (idempotent). Im Dry-Run ueberspringen — dann
    # kann die Tabelle noch fehlen, das melden wir sauber.
    migrations_applied: list[str] = []
    if not dry_run:
        try:
            applied = apply_project_db_migrations(project_path)
            migrations_applied = applied.get("datastore", [])
        except Exception as exc:  # noqa: BLE001
            return {
                "slug": project_path.name,
                "skipped_reason": f"Migration fehlgeschlagen: {exc}",
                "rows_total": 0,
                "rows_updated": 0,
                "rows_already_versioned": 0,
                "rows_with_markers": 0,
                "rows_single_page": 0,
                "rows_docling_legacy": 0,
                "pages_written": 0,
            }

    conn = sqlite3.connect(str(datastore_db))
    try:
        conn.row_factory = sqlite3.Row

        # Hat das Datastore agent_pdf_markdown + agent_pdf_page_offsets?
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "agent_pdf_markdown" not in tables:
            return {
                "slug": project_path.name,
                "skipped_reason": "agent_pdf_markdown fehlt (Pipeline noch nicht initialisiert)",
                "rows_total": 0,
                "rows_updated": 0,
                "rows_already_versioned": 0,
                "rows_with_markers": 0,
                "rows_single_page": 0,
                "rows_docling_legacy": 0,
                "pages_written": 0,
            }
        has_offsets_table = "agent_pdf_page_offsets" in tables
        if not has_offsets_table and not dry_run:
            return {
                "slug": project_path.name,
                "skipped_reason": (
                    "agent_pdf_page_offsets fehlt trotz Migration — "
                    "bitte Server einmal starten und Projekt oeffnen, "
                    "dann Skript nochmal"
                ),
                "rows_total": 0,
                "rows_updated": 0,
                "rows_already_versioned": 0,
                "rows_with_markers": 0,
                "rows_single_page": 0,
                "rows_docling_legacy": 0,
                "pages_written": 0,
            }

        # Schema-Pruefung: gibt es die extractor_version-Spalte?
        schema_cols = {
            r["name"]
            for r in conn.execute(
                "PRAGMA table_info(agent_pdf_markdown)"
            ).fetchall()
        }
        has_version_col = "extractor_version" in schema_cols

        # Rows auswaehlen: im Dry-Run ggf. ohne Version-Spalte (alles als
        # Kandidat behandeln), sonst nur NULL-Version.
        if has_version_col:
            rows = conn.execute(
                "SELECT file_id, rel_path, engine, md_content, char_count "
                "FROM agent_pdf_markdown "
                "WHERE extractor_version IS NULL"
            ).fetchall()
            already_versioned = conn.execute(
                "SELECT COUNT(*) FROM agent_pdf_markdown "
                "WHERE extractor_version IS NOT NULL"
            ).fetchone()[0]
        else:
            rows = conn.execute(
                "SELECT file_id, rel_path, engine, md_content, char_count "
                "FROM agent_pdf_markdown"
            ).fetchall()
            already_versioned = 0

        stats = {
            "slug": project_path.name,
            "migrations_applied": migrations_applied,
            "skipped_reason": None,
            "rows_total": len(rows),
            "rows_updated": 0,
            "rows_already_versioned": already_versioned,
            "rows_with_markers": 0,
            "rows_single_page": 0,
            "rows_docling_legacy": 0,
            "pages_written": 0,
        }

        for row in rows:
            file_id = int(row["file_id"])
            engine = (row["engine"] or "").strip()
            md = row["md_content"] or ""
            md_len = len(md)

            offsets = compute_offsets_from_markers(md)
            if offsets:
                category = "with_markers"
                stats["rows_with_markers"] += 1
            elif engine.startswith("azure-di") and md_len > 0:
                # Einseitige PDF bei Azure-DI: eine Offset-Zeile.
                offsets = [
                    {
                        "page_num": 1,
                        "char_start": 0,
                        "char_end": md_len,
                    }
                ]
                category = "single_page"
                stats["rows_single_page"] += 1
            else:
                # Docling-Legacy oder leerer Content — keine Offsets,
                # nur Versions-Stempel setzen.
                offsets = []
                category = "docling_legacy"
                stats["rows_docling_legacy"] += 1

            if dry_run:
                print(
                    f"  [DRY] file_id={file_id} engine={engine:<16} "
                    f"category={category:<15} pages={len(offsets):>3}  "
                    f"{row['rel_path']}"
                )
                stats["rows_updated"] += 1
                stats["pages_written"] += len(offsets)
                continue

            # DELETE (idempotent) und neu schreiben
            conn.execute(
                "DELETE FROM agent_pdf_page_offsets WHERE file_id = ?",
                (file_id,),
            )
            if offsets:
                conn.executemany(
                    "INSERT INTO agent_pdf_page_offsets "
                    "(file_id, page_num, char_start, char_end) VALUES (?, ?, ?, ?)",
                    [
                        (file_id, o["page_num"], o["char_start"], o["char_end"])
                        for o in offsets
                    ],
                )

            # Version-Stempel setzen. Dieser unterscheidet Backfill-
            # Rows von echten Neuextraktionen (EXTRACTOR_VERSION in
            # markdown.py) und hilft beim spaeteren Re-Extract-Zielen.
            conn.execute(
                "UPDATE agent_pdf_markdown "
                "SET extractor_version = ? WHERE file_id = ?",
                (BACKFILL_VERSION_TAG, file_id),
            )

            stats["rows_updated"] += 1
            stats["pages_written"] += len(offsets)

        if not dry_run:
            conn.commit()

    finally:
        conn.close()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill: agent_pdf_page_offsets aus Bestandsmarkdown ableiten."
    )
    parser.add_argument(
        "--project",
        help=(
            "Slug eines einzelnen Projekts. Ohne --project: alle Projekte "
            "im Workspace."
        ),
    )
    parser.add_argument(
        "--workspace",
        help=(
            "Workspace-Pfad (ueberschreibt DISCO_WORKSPACE). "
            "Default: Settings-Value."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nichts schreiben, nur Plan anzeigen.",
    )
    args = parser.parse_args()

    if args.workspace:
        os.environ["DISCO_WORKSPACE"] = str(Path(args.workspace).expanduser())
        # settings neu laden wuerde den Import-Cache umgehen; einfacher:
        # projects_dir manuell ueberschreiben.
        from disco import config as _cfg
        _cfg.settings.workspace_root = Path(args.workspace).expanduser()
        _cfg.settings.projects_dir = _cfg.settings.workspace_root / "projects"

    projects_dir = settings.projects_dir
    if not projects_dir.exists():
        print(f"[FEHLER] Projects-Verzeichnis existiert nicht: {projects_dir}")
        sys.exit(1)

    if args.project:
        target = projects_dir / args.project
        if not target.is_dir():
            print(f"[FEHLER] Projekt nicht gefunden: {target}")
            sys.exit(1)
        candidates = [target]
    else:
        candidates = [p for p in sorted(projects_dir.iterdir()) if p.is_dir()]

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"=== Backfill pdf_page_offsets — {mode} ===")
    print(f"Workspace: {projects_dir.parent}")
    print(f"Projekte : {len(candidates)}")
    print()

    total = {
        "projects_ok": 0,
        "projects_skipped": 0,
        "rows_updated": 0,
        "rows_already_versioned": 0,
        "rows_with_markers": 0,
        "rows_single_page": 0,
        "rows_docling_legacy": 0,
        "pages_written": 0,
    }

    for project_path in candidates:
        print(f"--- Projekt: {project_path.name}")
        try:
            stats = process_project(project_path, dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001
            print(f"  [FEHLER] {exc!r}")
            total["projects_skipped"] += 1
            continue

        if stats.get("skipped_reason"):
            print(f"  [SKIP] {stats['skipped_reason']}")
            total["projects_skipped"] += 1
            continue

        total["projects_ok"] += 1
        total["rows_updated"] += stats["rows_updated"]
        total["rows_already_versioned"] += stats["rows_already_versioned"]
        total["rows_with_markers"] += stats["rows_with_markers"]
        total["rows_single_page"] += stats["rows_single_page"]
        total["rows_docling_legacy"] += stats["rows_docling_legacy"]
        total["pages_written"] += stats["pages_written"]

        if stats.get("migrations_applied"):
            print(f"  Migrationen: {', '.join(stats['migrations_applied'])}")
        print(
            f"  Rows: {stats['rows_updated']} aktualisiert, "
            f"{stats['rows_already_versioned']} bereits versioniert "
            f"(uebersprungen)"
        )
        print(
            f"  Kategorien: markers={stats['rows_with_markers']}, "
            f"single-page={stats['rows_single_page']}, "
            f"docling-legacy={stats['rows_docling_legacy']}"
        )
        print(f"  Offset-Zeilen geschrieben: {stats['pages_written']}")
        print()

    print("=== Gesamt ===")
    print(f"Projekte OK       : {total['projects_ok']}")
    print(f"Projekte SKIP     : {total['projects_skipped']}")
    print(f"Rows aktualisiert : {total['rows_updated']}")
    print(f"Rows schon fertig : {total['rows_already_versioned']}")
    print(f"  davon markers   : {total['rows_with_markers']}")
    print(f"  davon single    : {total['rows_single_page']}")
    print(f"  davon docling   : {total['rows_docling_legacy']}")
    print(f"Offset-Zeilen     : {total['pages_written']}")
    if args.dry_run:
        print()
        print("Dry-Run beendet. Ohne --dry-run nochmal starten fuer echten Lauf.")


if __name__ == "__main__":
    main()
