"""Planning-Tools: strukturierte Pläne im aktiven Projekt.

Pläne liegen unter `.disco/plans/<YYYY-MM-DD>_<slug>.md` im Projekt-
Verzeichnis. Jeder Plan hat ein einheitliches Format mit YAML-artigem
Header (Status/Erstellt/Updated), Ziel, Schritt-Checklist und einem
chronologischen Notizen-Log.

Warum eigene Tools statt nur fs_write:
  - Konsistentes Format — der Agent erfindet nicht jedes Mal eine
    neue Struktur.
  - `plan_list` kann Status, Titel und Datum aus den Header-Metadaten
    lesen, ohne jeden Plan komplett reinzulesen.
  - Dedizierte Tools signalisieren dem Agenten, dass Pläne ein
    eigenes Konzept sind — nicht irgendeine Markdown-Datei.

Alle Pfade werden wie in fs.py gegen den Projekt-Root resolved, d.h.
die Sandbox greift automatisch. Kein Zugriff ausserhalb des aktiven
Projekts.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import register
from .fs import _data_root, _is_under

logger = logging.getLogger(__name__)


PLANS_DIR = ".disco/plans"

# Erlaubte Status-Werte — der Agent soll sich an diese halten
ALLOWED_STATUS = {"open", "in-progress", "done", "abandoned", "blocked"}

# Regex fuer den Header-Block am Datei-Anfang
_HEADER_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(\S+)", re.MULTILINE)
_HEADER_CREATED_RE = re.compile(r"^\*\*Erstellt:\*\*\s*(.+)$", re.MULTILINE)
_HEADER_UPDATED_RE = re.compile(r"^\*\*Letztes Update:\*\*\s*(.+)$", re.MULTILINE)
_HEADER_TITLE_RE = re.compile(r"^#\s+Plan:\s*(.+)$", re.MULTILINE)

_SLUG_NONALNUM = re.compile(r"[^a-z0-9]+")
_SLUG_DASHES = re.compile(r"-{2,}")


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------


def _plans_dir() -> Path:
    """Gibt `.disco/plans/` im aktiven Projekt zurueck (legt an falls noetig)."""
    root = _data_root()
    plans = root / PLANS_DIR
    plans.mkdir(parents=True, exist_ok=True)
    return plans


def _resolve_plan(filename: str) -> Path:
    """Resolved Dateinamen sicher unter `.disco/plans/`.

    Akzeptiert 'my-plan' und 'my-plan.md'. Verhindert Traversal
    (keine Slashes im Namen erlaubt).
    """
    if not filename or not filename.strip():
        raise ValueError("filename ist erforderlich.")

    name = filename.strip()
    # Kein Traversal, keine Unterordner
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(
            f"Ungueltiger Plan-Name {filename!r}: keine Pfadtrenner oder fuehrenden Punkte."
        )
    if not name.endswith(".md"):
        name = f"{name}.md"

    candidate = (_plans_dir() / name).resolve(strict=False)
    if not _is_under(candidate, _plans_dir().resolve()):
        raise ValueError(f"Pfad ausserhalb von {PLANS_DIR} nicht erlaubt: {filename!r}")
    return candidate


def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = _SLUG_NONALNUM.sub("-", s)
    s = _SLUG_DASHES.sub("-", s)
    s = s.strip("-")
    return s[:50] or "plan"


def _generate_filename(title: str) -> str:
    """Erzeugt einen sortierbaren Dateinamen: YYYY-MM-DD_<slug>.md."""
    date = datetime.now().strftime("%Y-%m-%d")
    return f"{date}_{_slugify(title)}.md"


def _render_plan_markdown(
    *,
    title: str,
    status: str,
    created: str,
    updated: str,
    goal: str,
    steps: list[str],
    notes_block: str = "",
) -> str:
    """Rendert einen Plan als einheitlich aufgebautes Markdown-Dokument."""
    parts: list[str] = []
    parts.append(f"# Plan: {title.strip()}\n")
    parts.append(f"\n**Status:** {status}")
    parts.append(f"\n**Erstellt:** {created}")
    parts.append(f"\n**Letztes Update:** {updated}\n")
    parts.append("\n## Ziel\n\n")
    parts.append(goal.strip() or "*(noch nicht formuliert)*")
    parts.append("\n\n## Schritte\n\n")
    if steps:
        for step in steps:
            step_text = step.strip()
            if not step_text:
                continue
            # Der Agent darf "[x] " am Anfang schreiben, um erledigte Schritte
            # direkt als erledigt anzulegen. Sonst default [ ].
            if step_text.startswith("[x]") or step_text.startswith("[X]"):
                parts.append(f"- [x] {step_text[3:].strip()}\n")
            elif step_text.startswith("[ ]"):
                parts.append(f"- {step_text}\n")
            else:
                parts.append(f"- [ ] {step_text}\n")
    else:
        parts.append("*(keine Schritte definiert)*\n")
    parts.append("\n## Notizen\n")
    if notes_block.strip():
        parts.append(f"\n{notes_block.rstrip()}\n")
    return "".join(parts)


def _parse_header(content: str) -> dict[str, str]:
    """Liest Titel/Status/Erstellt/Updated aus dem Plan-Kopf."""
    title_m = _HEADER_TITLE_RE.search(content)
    status_m = _HEADER_STATUS_RE.search(content)
    created_m = _HEADER_CREATED_RE.search(content)
    updated_m = _HEADER_UPDATED_RE.search(content)
    return {
        "title": title_m.group(1).strip() if title_m else "",
        "status": status_m.group(1).strip() if status_m else "unknown",
        "created": created_m.group(1).strip() if created_m else "",
        "updated": updated_m.group(1).strip() if updated_m else "",
    }


# ---------------------------------------------------------------------------
# plan_list
# ---------------------------------------------------------------------------


@register(
    name="plan_list",
    description=(
        "Listet alle Plaene des aktiven Projekts auf (.disco/plans/*.md). "
        "Fuer jeden Plan werden Titel, Status (open/in-progress/done/abandoned/"
        "blocked), Erstellungs-Datum und letztes Update aus dem Kopf gelesen, "
        "ohne die kompletten Inhalte zu laden. Gute erste Anlaufstelle am "
        "Session-Start: 'gibt es einen offenen Plan aus der letzten Session?'"
    ),
    parameters={
        "type": "object",
        "properties": {
            "status_filter": {
                "type": "string",
                "description": (
                    "Optional: nur Plaene mit diesem Status zeigen "
                    "(open/in-progress/done/abandoned/blocked)."
                ),
            },
        },
        "required": [],
    },
    returns="{plans: [{filename, title, status, created, updated, size_bytes}], total, plans_dir}",
)
def _plan_list(*, status_filter: str | None = None) -> dict[str, Any]:
    plans_dir = _plans_dir()
    root = _data_root()

    plans: list[dict[str, Any]] = []
    for p in sorted(plans_dir.glob("*.md")):
        try:
            content = p.read_text(encoding="utf-8")
        except OSError:
            continue
        meta = _parse_header(content)
        if status_filter and meta["status"] != status_filter:
            continue
        plans.append(
            {
                "filename": p.name,
                "title": meta["title"] or p.stem,
                "status": meta["status"],
                "created": meta["created"],
                "updated": meta["updated"],
                "size_bytes": p.stat().st_size,
            }
        )

    # Sortierung: offene / in-progress zuerst, dann nach Datum absteigend
    status_rank = {
        "in-progress": 0,
        "blocked": 1,
        "open": 2,
        "done": 3,
        "abandoned": 4,
        "unknown": 5,
    }
    plans.sort(
        key=lambda pl: (status_rank.get(pl["status"], 99), pl["updated"] or pl["created"]),
        reverse=False,
    )

    return {
        "plans": plans,
        "total": len(plans),
        "plans_dir": str(plans_dir.relative_to(root)),
    }


# ---------------------------------------------------------------------------
# plan_read
# ---------------------------------------------------------------------------


@register(
    name="plan_read",
    description=(
        "Liest einen Plan vollstaendig. Filename wie von plan_list zurueckgegeben "
        "(z.B. '2026-04-17_ibl-klassifikation.md'). Liefert den ganzen "
        "Markdown-Text plus geparste Header-Felder. Fuer grobe Uebersichten "
        "lieber plan_list nutzen — erst dann gezielt plan_read."
    ),
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Dateiname des Plans (mit oder ohne .md).",
            },
        },
        "required": ["filename"],
    },
    returns="{filename, title, status, created, updated, content, size_bytes}",
)
def _plan_read(*, filename: str) -> dict[str, Any]:
    target = _resolve_plan(filename)
    if not target.exists():
        raise ValueError(f"Plan nicht gefunden: {filename!r}")
    if not target.is_file():
        raise ValueError(f"Pfad ist keine Datei: {filename!r}")

    content = target.read_text(encoding="utf-8")
    meta = _parse_header(content)

    return {
        "filename": target.name,
        "title": meta["title"] or target.stem,
        "status": meta["status"],
        "created": meta["created"],
        "updated": meta["updated"],
        "content": content,
        "size_bytes": target.stat().st_size,
    }


# ---------------------------------------------------------------------------
# plan_write
# ---------------------------------------------------------------------------


@register(
    name="plan_write",
    description=(
        "Legt einen neuen Plan an oder ueberschreibt einen bestehenden. "
        "Pflicht: title, goal, steps. Optional: status (Default 'open'), "
        "filename (wenn leer: YYYY-MM-DD_<slug>.md wird generiert). "
        "Vorhandene Notizen werden bei Ueberschreibung UEBERNOMMEN, damit der "
        "Logbuch-Teil nicht verloren geht."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Kurzer Titel des Plans (eine Zeile).",
            },
            "goal": {
                "type": "string",
                "description": "Das Ziel in 1-3 Saetzen — was soll am Ende stehen?",
            },
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Liste der Schritte. Standard ist offen (Checkbox [ ]). "
                    "Praefix '[x]' markiert einen Schritt direkt als erledigt."
                ),
            },
            "status": {
                "type": "string",
                "description": (
                    "Plan-Status. Default 'open'. Erlaubt: open, in-progress, "
                    "done, abandoned, blocked."
                ),
            },
            "filename": {
                "type": "string",
                "description": (
                    "Optional: Dateiname (mit oder ohne .md). Wenn leer, wird "
                    "automatisch YYYY-MM-DD_<slug>.md erzeugt."
                ),
            },
        },
        "required": ["title", "goal", "steps"],
    },
    returns="{filename, full_path, bytes_written, created, notes_preserved}",
)
def _plan_write(
    *,
    title: str,
    goal: str,
    steps: list[str],
    status: str = "open",
    filename: str | None = None,
) -> dict[str, Any]:
    if not title or not title.strip():
        raise ValueError("title darf nicht leer sein.")
    if status not in ALLOWED_STATUS:
        raise ValueError(
            f"status={status!r} ist nicht erlaubt. Gueltig: {sorted(ALLOWED_STATUS)}"
        )
    if not isinstance(steps, list):
        raise ValueError("steps muss eine Liste sein.")

    # Dateiname bestimmen
    if filename and filename.strip():
        target = _resolve_plan(filename)
    else:
        target = _resolve_plan(_generate_filename(title))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created_at = now
    notes_block = ""
    already_existed = target.exists()

    # Bestehenden Plan: Erstellungs-Datum + Notizen uebernehmen
    if already_existed:
        try:
            existing = target.read_text(encoding="utf-8")
            meta = _parse_header(existing)
            if meta["created"]:
                created_at = meta["created"]
            # Notizen-Sektion herauslesen (alles nach "## Notizen")
            notes_idx = existing.find("## Notizen")
            if notes_idx >= 0:
                after = existing[notes_idx + len("## Notizen"):].lstrip("\n")
                notes_block = after.rstrip()
        except OSError:
            pass

    rendered = _render_plan_markdown(
        title=title,
        status=status,
        created=created_at,
        updated=now,
        goal=goal,
        steps=steps,
        notes_block=notes_block,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = rendered.encode("utf-8")
    with target.open("wb") as fh:
        fh.write(encoded)

    root = _data_root()
    return {
        "filename": target.name,
        "full_path": str(target.relative_to(root)),
        "bytes_written": len(encoded),
        "created": not already_existed,
        "notes_preserved": bool(notes_block),
    }


# ---------------------------------------------------------------------------
# plan_append_note
# ---------------------------------------------------------------------------


@register(
    name="plan_append_note",
    description=(
        "Haengt eine Notiz mit Timestamp an die Notizen-Sektion eines "
        "bestehenden Plans an. Genau dafuer gedacht, Fortschritt im Plan "
        "festzuhalten: 'Schritt 2 erledigt, Tabelle hat 47 Zeilen', "
        "'Schritt 3 blockiert weil...', 'Stand um 15:20: ...'. "
        "Ueberschreibt nichts, aendert auch den Status nicht — dafuer plan_write."
    ),
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Dateiname des Plans (mit oder ohne .md).",
            },
            "note": {
                "type": "string",
                "description": "Die Notiz als Markdown-Text. Wird mit Zeitstempel-Praefix angehaengt.",
            },
        },
        "required": ["filename", "note"],
    },
    returns="{filename, appended_bytes, total_bytes}",
)
def _plan_append_note(*, filename: str, note: str) -> dict[str, Any]:
    if not note or not note.strip():
        raise ValueError("note darf nicht leer sein.")

    target = _resolve_plan(filename)
    if not target.exists():
        raise ValueError(
            f"Plan nicht gefunden: {filename!r}. Erst mit plan_write anlegen."
        )

    content = target.read_text(encoding="utf-8")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_note = f"\n**{now}** — {note.strip()}\n"

    # Sicherstellen, dass die Notizen-Sektion existiert
    if "## Notizen" not in content:
        content = content.rstrip() + "\n\n## Notizen\n"

    # "Letztes Update"-Feld auf jetzt setzen
    if _HEADER_UPDATED_RE.search(content):
        content = _HEADER_UPDATED_RE.sub(f"**Letztes Update:** {now}", content, count=1)

    new_content = content.rstrip() + new_note

    encoded = new_content.encode("utf-8")
    with target.open("wb") as fh:
        fh.write(encoded)

    return {
        "filename": target.name,
        "appended_bytes": len(new_note.encode("utf-8")),
        "total_bytes": len(encoded),
    }
