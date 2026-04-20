"""Markdown-Canvas als persistentes Projekt-Gedaechtnis.

Pro Projekt gibt es eine Datei `data/projects/<slug>/NOTES.md`. Der Agent
kann sie:
  - lesen, um Erkenntnisse aus frueheren Sessions wiederzufinden
  - ergaenzen, um neue Befunde zu speichern

Der Slug wird stabil aus dem Projektnamen abgeleitet (lowercase,
Sonderzeichen → '-'). Bei Umbenennung eines Projekts bleibt der alte
Slug — die Notes-Datei folgt also nicht automatisch. Das ist bewusst:
lieber manuell migrieren als Daten verlieren.

append ist idempotent-freundlich: der neue Block bekommt einen
Zeitstempel-Header, damit spaetere Anhaenge ohne Textverlust moeglich sind.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ...config import settings
from ...projects import get_project
from . import register


# ---------------------------------------------------------------------------
# project_notes_read
# ---------------------------------------------------------------------------


@register(
    name="project_notes_read",
    description=(
        "Liest die Markdown-Notizen eines Projekts (data/projects/<slug>/NOTES.md). "
        "Nuetzlich als erster Schritt in einer neuen Session: was haben wir "
        "in diesem Projekt schon festgehalten? Existiert die Datei nicht, "
        "wird exists=false und content='' zurueckgegeben."
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "integer", "description": "Projekt-ID."},
        },
        "required": ["project_id"],
    },
    returns="{project_id, project_name, slug, notes_path, exists, content, size_bytes}",
)
def _project_notes_read(*, project_id: int) -> dict[str, Any]:
    project = get_project(project_id)
    slug = _project_slug(project["name"])
    notes_path = _notes_path_for_slug(slug)

    if not notes_path.exists():
        return {
            "project_id": project_id,
            "project_name": project["name"],
            "slug": slug,
            "notes_path": str(notes_path.relative_to(settings.data_dir.resolve())),
            "exists": False,
            "content": "",
            "size_bytes": 0,
        }

    content = notes_path.read_text(encoding="utf-8")
    return {
        "project_id": project_id,
        "project_name": project["name"],
        "slug": slug,
        "notes_path": str(notes_path.relative_to(settings.data_dir.resolve())),
        "exists": True,
        "content": content,
        "size_bytes": len(content.encode("utf-8")),
    }


# ---------------------------------------------------------------------------
# project_notes_append
# ---------------------------------------------------------------------------


@register(
    name="project_notes_append",
    description=(
        "Haengt einen neuen Eintrag an die Projekt-Notizen an "
        "(data/projects/<slug>/NOTES.md). Legt Datei und Ordner an, falls "
        "noch nicht vorhanden. Erzeugt automatisch einen Timestamp-Header, "
        "damit spaetere Anhaenge getrennt bleiben. Der Text selbst darf "
        "Markdown enthalten."
    ),
    parameters={
        "type": "object",
        "properties": {
            "project_id": {"type": "integer", "description": "Projekt-ID."},
            "content": {
                "type": "string",
                "description": "Markdown-Text, der angehaengt werden soll.",
            },
            "section_title": {
                "type": "string",
                "description": (
                    "Optionaler Abschnitts-Titel, erscheint als H3 ueber dem "
                    "Eintrag. Wenn leer, wird nur der Timestamp-Header gesetzt."
                ),
            },
        },
        "required": ["project_id", "content"],
    },
    returns="{project_id, project_name, notes_path, appended_bytes, total_bytes, created}",
)
def _project_notes_append(
    *,
    project_id: int,
    content: str,
    section_title: str | None = None,
) -> dict[str, Any]:
    if not content or not content.strip():
        raise ValueError("content darf nicht leer sein.")

    project = get_project(project_id)
    slug = _project_slug(project["name"])
    notes_path = _notes_path_for_slug(slug)
    notes_path.parent.mkdir(parents=True, exist_ok=True)

    created = not notes_path.exists()
    if created:
        header = (
            f"# Projekt-Notizen: {project['name']}\n\n"
            f"Automatisch gepflegt vom BEW-Agent. Jeder Eintrag hat einen "
            f"Zeitstempel-Header.\n"
        )
        notes_path.write_text(header, encoding="utf-8")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block_parts: list[str] = []
    block_parts.append(f"\n\n---\n\n## {timestamp}")
    if section_title and section_title.strip():
        block_parts.append(f"\n\n### {section_title.strip()}")
    block_parts.append(f"\n\n{content.rstrip()}\n")
    block = "".join(block_parts)

    with notes_path.open("a", encoding="utf-8") as fh:
        fh.write(block)

    total_size = notes_path.stat().st_size
    return {
        "project_id": project_id,
        "project_name": project["name"],
        "notes_path": str(notes_path.relative_to(settings.data_dir.resolve())),
        "appended_bytes": len(block.encode("utf-8")),
        "total_bytes": total_size,
        "created": created,
    }


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------


_SLUG_NONALNUM = re.compile(r"[^a-z0-9]+")
_SLUG_DASHES = re.compile(r"-{2,}")


def _project_slug(name: str) -> str:
    """Stabiler Slug aus einem Projektnamen."""
    s = (name or "").strip().lower()
    s = _SLUG_NONALNUM.sub("-", s)
    s = _SLUG_DASHES.sub("-", s)
    s = s.strip("-")
    return s or "unnamed"


def _notes_path_for_slug(slug: str) -> Path:
    root = settings.data_dir.resolve()
    return root / "projects" / slug / "NOTES.md"
