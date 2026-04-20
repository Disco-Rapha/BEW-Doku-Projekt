"""Memory-Tools: Discos Projekt-Gedaechtnis (README + NOTES + DISCO).

Drei Dateien im Projekt-Root bilden das vollstaendige Langzeit-Gedaechtnis:

    <projekt>/
    ├── README.md   ← Der Nutzer pflegt den Projekt-Kontext. Disco darf
    │                 ergaenzen/korrigieren (mit Ansage), aber die Inhalte
    │                 "gehoeren" dem Nutzer.
    ├── NOTES.md    ← Discos chronologisches Logbuch. Append-only mit
    │                 Timestamp-Headern. Wird NIE ueberschrieben.
    └── DISCO.md    ← Discos destilliertes Arbeitsgedaechtnis. Konventionen,
                      Tabellen-Namen, Lookup-Pfade, Entscheidungen, Begriffe.
                      Darf gezielt gepflegt werden (write oder append).

Warum diese drei und nicht mehr? Der Cline-inspirierte Bank-Ansatz mit
sechs Dateien plus ADR-Verzeichnis war zu formal — der Nutzer schrieb
Wissen doppelt (in Notes UND in Memory-Bank) oder es verteilte sich so,
dass Disco nach einer Kompression nicht mehr wusste wo was steht. Drei
klare Rollen (User-Briefing / Chronik / Destillat) sind eindeutig und
folgen dem CLAUDE.md-Muster von Claude Code.

Sandbox:
  - Alle Operationen arbeiten auf dem aktiven Projekt-Root
    (context.get_project_root()).
  - Whitelist erzwungen: Nur README.md, NOTES.md, DISCO.md sind
    adressierbar. fs_write auf diese Pfade bleibt technisch moeglich,
    aber die Memory-Tools sind der dokumentierte Weg mit
    Atomic-Write-Garantie und Append-Semantik.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..context import get_project_root
from . import register


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------

# Alle drei sind lesbar
READABLE_FILES: tuple[str, ...] = ("README.md", "NOTES.md", "DISCO.md")

# README und DISCO duerfen ueberschrieben werden (Snapshot-Charakter).
# NOTES ist append-only — es ist das chronologische Logbuch.
WRITABLE_FILES: tuple[str, ...] = ("README.md", "DISCO.md")

# NOTES und DISCO koennen angehaengt werden. README wird nicht angehaengt
# (dort pflegt der Nutzer eine strukturierte Seite, Anhaengen zerstoert die Form).
APPENDABLE_FILES: tuple[str, ...] = ("NOTES.md", "DISCO.md")


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------


def _require_project_root() -> Path:
    """Liefert das aktive Projekt-Root, sonst RuntimeError."""
    root = get_project_root()
    if root is None:
        raise RuntimeError(
            "Kein aktives Projekt — Memory-Tools arbeiten nur in einer "
            "Projekt-Sandbox. Stelle sicher, dass die Chat-Session an "
            "ein Projekt gebunden ist."
        )
    return root


def _resolve(file: str, *, allowed: tuple[str, ...]) -> Path:
    """Normalisiert einen Dateinamen gegen die Whitelist.

    Nur reine Dateinamen (keine Pfade, keine '..'). Die Whitelist bildet
    die Sandbox — wir muessen also nicht zusaetzlich resolve() gegen das
    Root pruefen, solange der Name aus der Whitelist stammt.
    """
    if not file or not isinstance(file, str):
        raise ValueError("file darf nicht leer sein.")
    name = file.strip()
    # Keine Pfad-Komponenten erlaubt
    if "/" in name or "\\" in name or ".." in name or name.startswith("."):
        raise ValueError(
            f"Nur reine Dateinamen erlaubt, keine Pfade: {file!r}. "
            f"Erlaubt: {list(allowed)}."
        )
    if name not in allowed:
        raise ValueError(
            f"Datei nicht in der Whitelist fuer diese Operation: {file!r}. "
            f"Erlaubt: {list(allowed)}."
        )
    return _require_project_root() / name


def _atomic_write(target: Path, content: str) -> None:
    """Schreibt atomar via tmp+rename — keine halben Dateien bei Crash."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)


# ---------------------------------------------------------------------------
# memory_read
# ---------------------------------------------------------------------------


@register(
    name="memory_read",
    description=(
        "Liest eine der drei Memory-Dateien des aktiven Projekts: "
        "README.md (Projekt-Briefing des Nutzers), NOTES.md (chronologisches "
        "Logbuch) oder DISCO.md (destilliertes Arbeitsgedaechtnis). "
        "Existiert die Datei nicht, wird exists=false zurueckgegeben."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "enum": list(READABLE_FILES),
                "description": (
                    "Dateiname im Projekt-Root. README.md, NOTES.md oder DISCO.md."
                ),
            },
        },
        "required": ["file"],
    },
    returns="{file, exists, content, size_bytes, line_count}",
)
def _memory_read(*, file: str) -> dict[str, Any]:
    path = _resolve(file, allowed=READABLE_FILES)
    if not path.exists():
        return {
            "file": file,
            "exists": False,
            "content": "",
            "size_bytes": 0,
            "line_count": 0,
        }
    content = path.read_text(encoding="utf-8")
    return {
        "file": file,
        "exists": True,
        "content": content,
        "size_bytes": len(content.encode("utf-8")),
        "line_count": content.count("\n") + (0 if content.endswith("\n") else 1),
    }


# ---------------------------------------------------------------------------
# memory_write
# ---------------------------------------------------------------------------


@register(
    name="memory_write",
    description=(
        "Ueberschreibt README.md oder DISCO.md des aktiven Projekts "
        "vollstaendig (atomar, tmp+rename). NOTES.md kann NICHT "
        "ueberschrieben werden — es ist das chronologische Logbuch, "
        "dafuer memory_append nutzen. "
        "WICHTIG: Vorher memory_read aufrufen — Blind-Overwrites sind "
        "verboten. Bei README.md: nur nach Ruecksprache mit dem Nutzer "
        "ueberschreiben, das ist primaer seine Datei."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "enum": list(WRITABLE_FILES),
                "description": "README.md oder DISCO.md.",
            },
            "content": {
                "type": "string",
                "description": "Vollstaendiger Datei-Inhalt (Markdown).",
            },
        },
        "required": ["file", "content"],
    },
    returns="{file, bytes_written, created}",
)
def _memory_write(*, file: str, content: str) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ValueError("content muss ein String sein.")
    path = _resolve(file, allowed=WRITABLE_FILES)
    created = not path.exists()
    _atomic_write(path, content)
    return {
        "file": file,
        "bytes_written": len(content.encode("utf-8")),
        "created": created,
    }


# ---------------------------------------------------------------------------
# memory_append
# ---------------------------------------------------------------------------


@register(
    name="memory_append",
    description=(
        "Haengt einen Abschnitt an NOTES.md oder DISCO.md an. "
        "NOTES.md: automatischer '## YYYY-MM-DD HH:MM:SS'-Header wird "
        "vorangestellt (chronologisches Logbuch). "
        "DISCO.md: falls heading gesetzt, wird '## <heading>' vorangestellt; "
        "sonst wird der Text direkt angehaengt. "
        "Legt Datei an, falls sie noch nicht existiert."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "enum": list(APPENDABLE_FILES),
                "description": "NOTES.md oder DISCO.md.",
            },
            "content": {
                "type": "string",
                "description": "Markdown-Text, der angehaengt werden soll.",
            },
            "heading": {
                "type": "string",
                "description": (
                    "Optionale H2-Ueberschrift (ohne '## '). Nur fuer "
                    "DISCO.md relevant — bei NOTES.md wird immer ein "
                    "Timestamp-Header gesetzt, heading wird dort "
                    "zusaetzlich als H3 unter dem Timestamp eingefuegt."
                ),
            },
        },
        "required": ["file", "content"],
    },
    returns="{file, appended_bytes, total_bytes, created}",
)
def _memory_append(
    *,
    file: str,
    content: str,
    heading: str | None = None,
) -> dict[str, Any]:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("content darf nicht leer sein.")

    path = _resolve(file, allowed=APPENDABLE_FILES)
    created = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)

    if created:
        # Leere Template-Zeile, damit die erste Append-Blase sauber sitzt.
        # Beim NOTES-Fall kuemmert sich der Append-Code um den Header.
        if file == "NOTES.md":
            initial = "# Projekt-Notizen\n\n"
        elif file == "DISCO.md":
            initial = "# DISCO.md\n\n"
        else:
            initial = ""
        path.write_text(initial, encoding="utf-8")

    block = _build_append_block(file=file, content=content, heading=heading)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(block)

    return {
        "file": file,
        "appended_bytes": len(block.encode("utf-8")),
        "total_bytes": path.stat().st_size,
        "created": created,
    }


def _build_append_block(
    *,
    file: str,
    content: str,
    heading: str | None,
) -> str:
    """Erzeugt den anzuhaengenden Textblock.

    NOTES.md: immer Timestamp-H2, heading optional als H3 darunter.
    DISCO.md: heading optional als H2, Text direkt.
    """
    body = content.rstrip() + "\n"
    if file == "NOTES.md":
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"\n\n---\n\n## {ts}"]
        if heading and heading.strip():
            parts.append(f"\n\n### {heading.strip()}")
        parts.append(f"\n\n{body}")
        return "".join(parts)

    # DISCO.md (weitere APPENDABLE_FILES koennten hier aehnlich behandelt werden)
    if heading and heading.strip():
        return f"\n\n## {heading.strip()}\n\n{body}"
    return f"\n\n{body}"
