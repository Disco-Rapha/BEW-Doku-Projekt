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


# Default-Cap fuer memory_read. README/NOTES/DISCO.md wachsen ueber
# Sessions auf zig KB an — bei jedem Session-Start die ganze Datei in den
# LLM-Kontext zu laden ist Verschwendung. Standard liefert nur die ersten
# 8 KB; mit headings_only=True bekommt Disco eine Kapitel-Uebersicht und
# kann via section/tail/max_bytes gezielt nachladen.
#
# Die Memory-Architektur-Reform (BACKLOG TOP-2) wird das Modell weiter
# verfeinern (Schicht 1 immer geladen + Kapitel-Index). Bis dahin ist
# dies der Pragmatismus-Schritt.
DEFAULT_MEMORY_MAX_BYTES = 8000


@register(
    name="memory_read",
    description=(
        "Liest eine der drei Memory-Dateien des aktiven Projekts: "
        "README.md (Projekt-Briefing des Nutzers), NOTES.md (chronologisches "
        "Logbuch) oder DISCO.md (destilliertes Arbeitsgedaechtnis). "
        "\n\n"
        "**Default ist gekuerzt** (max_bytes=8000) — fuer Onboarding "
        "reicht der Kopf der Datei. Wenn Du gezielt mehr brauchst, gibt "
        "es vier Modi: \n"
        "  - headings_only=True: nur die Kapitel-Liste (H2/H3) als "
        "    Index, ohne Body. Ideal fuer Orientierung.\n"
        "  - section='<Heading>': nur dieses Kapitel (case-insensitive, "
        "    matcht den ersten H2 oder H3).\n"
        "  - tail=N: nur die letzten N Zeilen — fuer NOTES.md das "
        "    sinnvollste, weil chronologisch.\n"
        "  - max_bytes=<N>: explizites Bytelimit (oder 0 fuer komplett).\n"
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
            "max_bytes": {
                "type": "integer",
                "description": (
                    "Maximale Bytes des content-Felds. Default 8000. "
                    "0 = unlimitiert (volle Datei). Bei Truncation wird "
                    "truncated=True gesetzt und total_bytes verraet die "
                    "Original-Groesse."
                ),
            },
            "tail": {
                "type": "integer",
                "description": (
                    "Wenn gesetzt: gibt die letzten N Zeilen statt des "
                    "Datei-Anfangs zurueck. Sinnvoll fuer NOTES.md "
                    "(chronologisches Logbuch — neueste Eintraege unten)."
                ),
            },
            "section": {
                "type": "string",
                "description": (
                    "Wenn gesetzt: liefert nur den Inhalt des ersten "
                    "passenden H2- oder H3-Kapitels (case-insensitive, "
                    "Substring-Match auf Heading-Text). Beispiel: "
                    "section='Aktuelle Aufgabe' findet '## Aktuelle "
                    "Aufgabe', '### Aktuelle Aufgabe', '## 2026-04-25 "
                    "Aktuelle Aufgabe' usw. Wenn nicht gefunden, "
                    "kommt section_found=False zurueck."
                ),
            },
            "headings_only": {
                "type": "boolean",
                "description": (
                    "Wenn True: liefert nur die Kapitel-Struktur "
                    "(H1/H2/H3-Headings) als Index, ohne Body. Ideal fuer "
                    "Orientierung in einer grossen DISCO.md/NOTES.md."
                ),
            },
        },
        "required": ["file"],
    },
    returns=(
        "{file, exists, content, size_bytes, line_count, total_bytes, "
        "truncated, mode, section_found?}"
    ),
)
def _memory_read(
    *,
    file: str,
    max_bytes: int | None = None,
    tail: int | None = None,
    section: str | None = None,
    headings_only: bool = False,
) -> dict[str, Any]:
    path = _resolve(file, allowed=READABLE_FILES)
    if not path.exists():
        return {
            "file": file,
            "exists": False,
            "content": "",
            "size_bytes": 0,
            "line_count": 0,
            "total_bytes": 0,
            "truncated": False,
            "mode": "default",
        }

    full = path.read_text(encoding="utf-8")
    total_bytes = len(full.encode("utf-8"))

    # Mode-Auswahl mit klarer Praezedenz:
    #   1. headings_only — nur Index
    #   2. section — nur ein Kapitel
    #   3. tail — letzte N Zeilen
    #   4. default — Kopf der Datei mit max_bytes-Cap
    if headings_only:
        index = _extract_headings(full)
        content = index
        truncated = False
        mode = "headings_only"
        result_extra: dict[str, Any] = {}
    elif section:
        body, found = _extract_section(full, section)
        content = body
        truncated = False
        mode = "section"
        result_extra = {"section_found": found}
    elif tail is not None and tail > 0:
        lines = full.splitlines()
        content = "\n".join(lines[-tail:])
        if not full.endswith("\n") and lines:
            pass
        else:
            content = content + "\n" if content else ""
        truncated = len(lines) > tail
        mode = "tail"
        result_extra = {}
    else:
        cap = DEFAULT_MEMORY_MAX_BYTES if max_bytes is None else max_bytes
        if cap and total_bytes > cap:
            content = full.encode("utf-8")[:cap].decode("utf-8", errors="ignore")
            truncated = True
        else:
            content = full
            truncated = False
        mode = "default"
        result_extra = {}

    return {
        "file": file,
        "exists": True,
        "content": content,
        "size_bytes": len(content.encode("utf-8")),
        "line_count": content.count("\n") + (
            0 if content.endswith("\n") or not content else 1
        ),
        "total_bytes": total_bytes,
        "truncated": truncated,
        "mode": mode,
        **result_extra,
    }


# ---------------------------------------------------------------------------
# Helfer fuer headings_only / section
# ---------------------------------------------------------------------------


def _extract_headings(text: str) -> str:
    """Liefert die Heading-Struktur als Markdown-Index.

    Pro H1/H2/H3-Zeile eine Eintrag mit Zeilen-Nummer als Hint, damit
    Disco bei Bedarf gezielt mit `tail`/`max_bytes` nachladen kann.
    """
    lines = text.splitlines()
    out: list[str] = []
    for n, line in enumerate(lines, start=1):
        s = line.lstrip()
        if s.startswith("# ") or s.startswith("## ") or s.startswith("### "):
            out.append(f"L{n:>5}: {s}")
    if not out:
        return "(keine Headings gefunden)"
    return "\n".join(out)


def _extract_section(text: str, name: str) -> tuple[str, bool]:
    """Sucht das erste H2/H3-Kapitel, dessen Heading `name` enthaelt.

    Liefert (body, found). Body inkludiert den Heading selbst und alles
    bis zum naechsten gleich- oder hoeher-rangigen Heading.
    """
    needle = name.strip().lower()
    if not needle:
        return ("", False)
    lines = text.splitlines()
    n = len(lines)
    start_idx: int | None = None
    start_level: int = 0
    for i, raw in enumerate(lines):
        s = raw.lstrip()
        for level, prefix in ((2, "## "), (3, "### ")):
            if s.startswith(prefix):
                heading_text = s[len(prefix):].lower()
                if needle in heading_text:
                    start_idx = i
                    start_level = level
                    break
        if start_idx is not None:
            break

    if start_idx is None:
        return ("", False)

    end_idx = n
    for j in range(start_idx + 1, n):
        s = lines[j].lstrip()
        # Stop bei gleich- oder hoeher-rangigem Heading
        if (start_level >= 2 and s.startswith("# ")) or \
           (start_level >= 2 and s.startswith("## ")) or \
           (start_level == 3 and s.startswith("### ")):
            end_idx = j
            break

    body = "\n".join(lines[start_idx:end_idx]).rstrip() + "\n"
    return (body, True)


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
