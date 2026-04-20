"""Memory-Bank-Tools: strukturiertes Projekt-Gedaechtnis.

Pro Projekt existiert ein Ordner `<projekt>/.disco/memory/` mit dem
Cline-inspirierten Memory-Bank-Schema (MEMORY.md als Index, activeContext.md
und progress.md als Working-Triad, systemPatterns/techContext/glossary
on-demand, decisions/ADR-NNN-*.md append-only).

Diese Tools sind die **einzige** Schreib-API fuer diese Dateien — fs_write
darf hier nicht hinein. Damit ist das Memory-Protokoll (Read-before-Write,
Snapshot vs. Append, ADR-Disziplin) verifizierbar.

Sandbox:
  - Alle Operationen arbeiten auf dem aktiven Projekt (context.get_project_root()).
  - Pfad-Traversal ist ausgeschlossen: relative Pfade mit .. oder absolute
    Pfade werden abgelehnt.
  - Nur .md-Dateien und das `decisions/`-Unterverzeichnis sind erlaubt.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..context import get_project_root
from . import register


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# Erlaubte Dateien in .disco/memory/ (ausserhalb decisions/)
MEMORY_FILES: tuple[str, ...] = (
    "MEMORY.md",
    "activeContext.md",
    "progress.md",
    "systemPatterns.md",
    "techContext.md",
    "glossary.md",
)

# Dateien, die NICHT ueber memory_write ueberschrieben werden duerfen.
# decisions/ sind append-only (nur memory_append_adr), ADR-001 ist
# Geschichte und bleibt unveraenderlich.
WRITE_PROTECTED: tuple[str, ...] = (
    # nichts global — die decisions/-Policy wird ueber Pfad-Prefix erzwungen
)

MEMORY_SUBDIR = ".disco/memory"
DECISIONS_SUBDIR = "decisions"

_ADR_FILENAME_RE = re.compile(r"ADR-(\d{3})-[a-z0-9-]+\.md$")
_SLUG_NONALNUM = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# Helfer: Pfad-Aufloesung + Sicherheit
# ---------------------------------------------------------------------------


def _require_project_root() -> Path:
    """Gibt das aktive Projekt-Root zurueck, wirft sonst RuntimeError."""
    root = get_project_root()
    if root is None:
        raise RuntimeError(
            "Kein aktives Projekt — Memory-Tools arbeiten nur in einer "
            "Projekt-Sandbox. Stelle sicher, dass die Chat-Session an "
            "ein Projekt gebunden ist."
        )
    return root


def _memory_root() -> Path:
    """Absoluter Pfad zu <projekt>/.disco/memory/."""
    return _require_project_root() / MEMORY_SUBDIR


def _resolve_memory_path(rel: str) -> Path:
    """Normalisiert einen relativen Pfad unterhalb .disco/memory/.

    Schutzmassnahmen:
      - Keine absoluten Pfade
      - Keine '..'-Komponenten (Traversal)
      - Muss eine .md-Datei sein
      - Resolved-Pfad muss unter memory_root bleiben
    """
    if not rel or not isinstance(rel, str):
        raise ValueError("file darf nicht leer sein.")

    # Absolut-Pfade, Windows-Backslashes, parent-Traversal alle raus
    if rel.startswith("/") or rel.startswith("\\"):
        raise ValueError(
            f"Absolute Pfade nicht erlaubt: {rel!r}. Gib einen Pfad relativ "
            "zu .disco/memory/ an (z.B. 'activeContext.md' oder "
            "'decisions/ADR-007-xyz.md')."
        )
    rel_norm = rel.replace("\\", "/")
    parts = [p for p in rel_norm.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise ValueError(f"'..' im Pfad nicht erlaubt: {rel!r}.")

    if not rel_norm.endswith(".md"):
        raise ValueError(f"Nur .md-Dateien erlaubt: {rel!r}.")

    root = _memory_root()
    full = (root / rel_norm).resolve()

    # Nach resolve() muss full noch unter root bleiben.
    try:
        full.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Pfad zeigt ausserhalb .disco/memory/: {rel!r}"
        ) from exc

    return full


def _is_decision_path(rel: str) -> bool:
    rel_norm = rel.replace("\\", "/")
    return rel_norm.startswith(f"{DECISIONS_SUBDIR}/")


# ---------------------------------------------------------------------------
# memory_read
# ---------------------------------------------------------------------------


@register(
    name="memory_read",
    description=(
        "Liest eine Memory-Datei aus dem aktiven Projekt (.disco/memory/). "
        "Erlaubt sind MEMORY.md, activeContext.md, progress.md, "
        "systemPatterns.md, techContext.md, glossary.md, sowie Dateien unter "
        "decisions/ADR-NNN-*.md. Wenn die Datei nicht existiert, wird "
        "exists=false zurueckgegeben."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": (
                    "Relativer Pfad unterhalb .disco/memory/, z.B. "
                    "'activeContext.md' oder 'decisions/ADR-003-sandbox.md'."
                ),
            },
        },
        "required": ["file"],
    },
    returns="{file, exists, content, size_bytes, line_count}",
)
def _memory_read(*, file: str) -> dict[str, Any]:
    path = _resolve_memory_path(file)
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
        "Schreibt/ueberschreibt eine Memory-Datei im aktiven Projekt. "
        "NUR erlaubt fuer MEMORY.md, activeContext.md, progress.md, "
        "systemPatterns.md, techContext.md, glossary.md. Dateien unter "
        "decisions/ sind append-only und muessen ueber memory_append_adr "
        "angelegt werden. "
        "WICHTIG: Vorher memory_read aufrufen — Blind-Overwrites sind verboten."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": (
                    "Relativer Pfad, z.B. 'activeContext.md'. Keine "
                    "decisions/-Pfade (dafuer memory_append_adr)."
                ),
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

    if _is_decision_path(file):
        raise ValueError(
            "decisions/-Dateien sind append-only. Nutze memory_append_adr "
            "fuer neue ADRs. Bestehende ADRs bleiben unveraenderlich."
        )

    # Nur die whitelisted Flat-Dateien erlauben
    rel_norm = file.replace("\\", "/")
    if rel_norm not in MEMORY_FILES:
        raise ValueError(
            f"memory_write erlaubt nur die Standard-Dateien {list(MEMORY_FILES)}. "
            f"Fuer ADRs nutze memory_append_adr."
        )

    path = _resolve_memory_path(file)
    created = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomisch schreiben: erst in tmp, dann rename. Verhindert halbe
    # Dateien bei Crash mitten im write().
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)

    return {
        "file": file,
        "bytes_written": len(content.encode("utf-8")),
        "created": created,
    }


# ---------------------------------------------------------------------------
# memory_list
# ---------------------------------------------------------------------------


@register(
    name="memory_list",
    description=(
        "Listet alle Dateien unter .disco/memory/ des aktiven Projekts "
        "(inkl. decisions/ADR-*.md). Liefert Pfad, Groesse, Zeilenzahl "
        "und letzte Aenderung — ideal als Uebersicht nach Kompression "
        "oder beim Session-Start."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    returns="{files: [{path, size_bytes, line_count, modified_at}], next_adr_number}",
)
def _memory_list() -> dict[str, Any]:
    root = _memory_root()
    if not root.exists():
        return {"files": [], "next_adr_number": 1}

    files: list[dict[str, Any]] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root).as_posix()
        st = p.stat()
        content = p.read_text(encoding="utf-8")
        files.append({
            "path": rel,
            "size_bytes": st.st_size,
            "line_count": content.count("\n") + (0 if content.endswith("\n") else 1),
            "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(
                timespec="seconds"
            ),
        })

    # Naechste ADR-Nummer berechnen (max existierend + 1)
    max_num = 0
    decisions_dir = root / DECISIONS_SUBDIR
    if decisions_dir.exists():
        for p in decisions_dir.glob("ADR-*.md"):
            m = _ADR_FILENAME_RE.search(p.name)
            if m:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num

    return {
        "files": files,
        "next_adr_number": max_num + 1,
    }


# ---------------------------------------------------------------------------
# memory_append_adr
# ---------------------------------------------------------------------------


@register(
    name="memory_append_adr",
    description=(
        "Legt eine neue ADR-Datei in .disco/memory/decisions/ an. "
        "Append-only: einmal geschrieben, bleibt sie unveraendert. "
        "Die naechste ADR-Nummer wird automatisch vergeben. "
        "Nutze das Tool fuer jede wesentliche Architektur-Entscheidung."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": (
                    "Kurztitel der Entscheidung, 3-10 Worte. Wird zum "
                    "Datei-Slug (lowercase, dash-separated) umgewandelt."
                ),
            },
            "context": {
                "type": "string",
                "description": (
                    "Kontext: welche Situation, welche Constraints, was "
                    "war der Ausloeser der Entscheidung?"
                ),
            },
            "decision": {
                "type": "string",
                "description": "Was wurde entschieden? Konkrete Formulierung.",
            },
            "consequences": {
                "type": "string",
                "description": (
                    "Folgen — positive wie negative. Was wird dadurch moeglich? "
                    "Welche Trade-offs wurden akzeptiert?"
                ),
            },
        },
        "required": ["title", "context", "decision", "consequences"],
    },
    returns="{path, number, created_at}",
)
def _memory_append_adr(
    *,
    title: str,
    context: str,
    decision: str,
    consequences: str,
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise ValueError("title darf nicht leer sein.")

    # Slug aus Titel
    slug = _SLUG_NONALNUM.sub("-", title.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = "untitled"

    # Naechste Nummer finden
    decisions_dir = _memory_root() / DECISIONS_SUBDIR
    decisions_dir.mkdir(parents=True, exist_ok=True)

    max_num = 0
    for p in decisions_dir.glob("ADR-*.md"):
        m = _ADR_FILENAME_RE.search(p.name)
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num
    next_num = max_num + 1

    filename = f"ADR-{next_num:03d}-{slug}.md"
    target = decisions_dir / filename
    if target.exists():
        # Praktisch unmoeglich durch Nummern-Berechnung, aber defensiv.
        raise RuntimeError(f"ADR existiert bereits: {filename}")

    body = (
        f"# ADR-{next_num:03d} — {title}\n"
        f"\n"
        f"**Datum:** {datetime.now().strftime('%Y-%m-%d')}\n"
        f"\n"
        f"## Context\n"
        f"\n"
        f"{context.strip()}\n"
        f"\n"
        f"## Decision\n"
        f"\n"
        f"{decision.strip()}\n"
        f"\n"
        f"## Consequences\n"
        f"\n"
        f"{consequences.strip()}\n"
    )
    target.write_text(body, encoding="utf-8")

    rel = target.relative_to(_memory_root()).as_posix()
    return {
        "path": rel,
        "number": next_num,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
