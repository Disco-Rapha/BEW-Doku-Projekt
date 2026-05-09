"""Memory-Tools: Discos Projekt-Gedächtnis (README + NOTES + DISCO).

Drei Dateien im Projekt-Root bilden das Langzeit-Gedächtnis:

    <projekt>/
    ├── README.md   ← Der Nutzer pflegt den Projekt-Kontext.
    ├── NOTES.md    ← Discos chronologisches Logbuch (append-only).
    └── DISCO.md    ← Discos destilliertes Arbeitsgedächtnis.

**Memory-Reform 2026-05-09 — Drei-Schichten-Modell für DISCO.md:**

    Schicht 1 (always-loaded, max 3,5 KB):
        Projekt-Identität / Aktueller Fokus / Konventionen / Lookup-Pfade
        + Kapitel-Index (Liste der Schicht-2-Titel)

    Schicht 2 (on-demand-Kapitel):
        Wissens-Sammelstellen, chronologische Sessions, Glossar etc.
        Disco lädt nur per `memory_read({chapter: "..."})`.

    Schicht 3 (Tabellen-Wissen):
        In `agent_table_docs`-Tabelle, getrennt von DISCO.md.

Die zwei Schichten in DISCO.md werden physisch durch den Marker
`<!-- DISCO-LAYER-1-END -->` getrennt. Wenn der Marker fehlt
(Projekte vor der Reform), läuft der Default-Modus wie früher
(8-KB-Kopf) — abwärtskompatibel.

Pro Kapitel ein chapter-meta-Block direkt unter dem H2:

    ## Bautechnik IBL Roh-Stand
    <!-- chapter-meta:
      tags: [bautechnik, ibl, soll-ist]
      created: 2026-05-06
      last_referenced: 2026-05-08
      status: current
    -->

    [Body bis zum nächsten H2 ...]

Sandbox:
- Alle Operationen arbeiten auf dem aktiven Projekt-Root
  (context.get_project_root()).
- Whitelist erzwungen: Nur README.md, NOTES.md, DISCO.md.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..context import get_project_root
from . import register


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

READABLE_FILES: tuple[str, ...] = ("README.md", "NOTES.md", "DISCO.md")
WRITABLE_FILES: tuple[str, ...] = ("README.md", "DISCO.md")
APPENDABLE_FILES: tuple[str, ...] = ("NOTES.md", "DISCO.md")

# Marker, der Schicht 1 (oben) von Schicht 2 (unten) in DISCO.md trennt.
# Wenn der Marker fehlt, wird die Datei als Vor-Reform-DISCO.md behandelt
# (Default-Modus liefert die ersten 8 KB wie früher).
LAYER_MARKER = "<!-- DISCO-LAYER-1-END -->"

# Default-Limits (Bytes).
LAYER_1_MAX_BYTES = 3_500          # Hartes Soll-Limit für Schicht 1
DEFAULT_LEGACY_MAX_BYTES = 8_000   # Fallback für DISCO.md ohne Marker
DEFAULT_README_MAX_BYTES = 0       # README: voll laden (klein, vom User gepflegt)
NOTES_DEFAULT_TAIL_LINES = 0       # NOTES: kompletter aktueller (nicht-archivierter) Stand

# Trace-Log unter <project>/.disco/memory-access.log (TSV, append-only).
TRACE_LOG_REL_PATH = ".disco/memory-access.log"
TRACE_LOG_HEADER = (
    "ts\tmode\tfile\tchapter_query\thit_type\t"
    "matched_title\tbytes\treference_count_after\n"
)


# ---------------------------------------------------------------------------
# Helfer — Sandbox + Atomic-Write
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
    """Normalisiert einen Dateinamen gegen die Whitelist."""
    if not file or not isinstance(file, str):
        raise ValueError("file darf nicht leer sein.")
    name = file.strip()
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
    """Atomares Schreiben via tmp+rename — keine halben Dateien bei Crash."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)


# ---------------------------------------------------------------------------
# Helfer — Marker + chapter-meta-Block
# ---------------------------------------------------------------------------


def _split_at_layer_marker(text: str) -> tuple[str, str | None]:
    """Splittet DISCO.md am Marker.

    Returns:
        (layer1, layer2). layer2 ist None, wenn kein Marker da ist
        (alte DISCO.md ohne Reform-Format).
    """
    idx = text.find(LAYER_MARKER)
    if idx < 0:
        return text, None
    layer1 = text[:idx].rstrip() + "\n"
    # Marker selbst wird übersprungen, layer2 beginnt nach dem Marker.
    after_marker = text[idx + len(LAYER_MARKER):]
    # Führende Newlines abschneiden für sauberen Body
    layer2 = after_marker.lstrip("\n")
    return layer1, layer2


# Regex: findet einen chapter-meta-Block direkt nach einer H2-Heading-Zeile.
# Format:  <!-- chapter-meta:
#            <key>: <value>
#            ...
#          -->
_CHAPTER_META_PATTERN = re.compile(
    r"^<!--\s*chapter-meta:\s*\n"
    r"(?P<body>.*?)\n"
    r"\s*-->\s*$",
    re.DOTALL | re.MULTILINE,
)


def _parse_chapter_meta(meta_text: str) -> dict[str, Any]:
    """Parst einen chapter-meta-Block-Body (Mini-YAML, sehr lax).

    Format:
        tags: [bautechnik, ibl]
        created: 2026-05-06
        last_referenced: 2026-05-08
        status: current

    Unbekannte Keys werden mit übernommen. Tippfehler sind tolerierbar
    (parser fällt auf raw-string zurück).

    Returns:
        Dict mit tags (list[str]), status (str), created (str|None),
        last_referenced (str|None), reference_count (int), und allen
        weiteren Keys als raw-string.
    """
    out: dict[str, Any] = {
        "tags": [],
        "status": "current",
        "created": None,
        "last_referenced": None,
        "reference_count": 0,
    }
    for raw_line in meta_text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "tags":
            # Format: [a, b, c]  oder  a, b, c
            stripped = value.strip("[]")
            tags = [t.strip().strip("'\"") for t in stripped.split(",") if t.strip()]
            out["tags"] = tags
        elif key == "reference_count":
            try:
                out["reference_count"] = int(value)
            except ValueError:
                out["reference_count"] = 0
        elif key in ("created", "last_referenced", "status"):
            out[key] = value or None
        else:
            out[key] = value
    return out


def _format_chapter_meta(meta: dict[str, Any]) -> str:
    """Serialisiert chapter-meta zurueck in den Markdown-Block-Text.

    Erzeugt das Format, das `_parse_chapter_meta` lesen kann. Pflichtfelder
    immer dabei, optionale dazu wenn nicht-leer.
    """
    lines = ["<!-- chapter-meta:"]
    tags = meta.get("tags") or []
    if tags:
        lines.append(f"  tags: [{', '.join(tags)}]")
    if meta.get("created"):
        lines.append(f"  created: {meta['created']}")
    if meta.get("last_referenced"):
        lines.append(f"  last_referenced: {meta['last_referenced']}")
    if meta.get("status"):
        lines.append(f"  status: {meta['status']}")
    rc = int(meta.get("reference_count") or 0)
    if rc > 0:
        lines.append(f"  reference_count: {rc}")
    lines.append("-->")
    return "\n".join(lines)


def _iter_chapters(layer2_text: str) -> list[dict[str, Any]]:
    """Parst Schicht-2-Text in Kapitel.

    Jeder H2 startet ein neues Kapitel. Direkt darauf folgender
    chapter-meta-Block (HTML-Kommentar) wird geparst. Body geht bis
    zum nächsten H2.

    Returns:
        Liste von Kapitel-Dicts:
          {
            title: str,
            heading_line_idx: int,        # 0-based, in layer2_text
            meta_block_start: int|None,   # Zeichen-Offset in layer2_text
            meta_block_end: int|None,
            body_start: int,              # Zeichen-Offset (nach meta-Block)
            body_end: int,                # Zeichen-Offset
            tags: list[str],
            status: str,
            created: str|None,
            last_referenced: str|None,
            reference_count: int,
          }
    """
    chapters: list[dict[str, Any]] = []
    # H2-Zeilen finden (kein H3, kein H1)
    h2_iter = list(re.finditer(r"^## (.+?)\s*$", layer2_text, re.MULTILINE))
    for i, m in enumerate(h2_iter):
        title = m.group(1).strip()
        heading_start = m.start()
        heading_end = m.end()
        # Block bis zum nächsten H2 (oder Datei-Ende)
        chapter_end = h2_iter[i + 1].start() if i + 1 < len(h2_iter) else len(layer2_text)
        # chapter-meta-Block direkt nach Heading?
        rest = layer2_text[heading_end:chapter_end]
        meta_match = _CHAPTER_META_PATTERN.search(rest)
        meta = {
            "tags": [],
            "status": "current",
            "created": None,
            "last_referenced": None,
            "reference_count": 0,
        }
        meta_block_start: int | None = None
        meta_block_end: int | None = None
        body_start = heading_end
        if meta_match and meta_match.start() < 200:
            # Meta muss direkt unter dem Heading stehen (nur Whitespace dazwischen)
            between = rest[: meta_match.start()].strip()
            if not between:
                meta = {**meta, **_parse_chapter_meta(meta_match.group("body"))}
                meta_block_start = heading_end + meta_match.start()
                meta_block_end = heading_end + meta_match.end()
                body_start = meta_block_end
        chapters.append({
            "title": title,
            "heading_line_idx": layer2_text[:heading_start].count("\n"),
            "heading_start": heading_start,
            "meta_block_start": meta_block_start,
            "meta_block_end": meta_block_end,
            "body_start": body_start,
            "body_end": chapter_end,
            **meta,
        })
    return chapters


def _format_chapter_index(chapters: list[dict[str, Any]]) -> str:
    """Erzeugt die Markdown-Liste der verfügbaren Kapitel für den
    Default-Antwort-Anhang."""
    if not chapters:
        return ""
    lines = ["", "---", "", "# Verfügbare Kapitel (Schicht 2)", ""]
    for c in chapters:
        if c.get("status") == "deprecated":
            continue
        title = c["title"]
        tags = c.get("tags") or []
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        status = c.get("status") or "current"
        marker = "" if status == "current" else f" *(status: {status})*"
        lines.append(f"- \"{title}\"{tag_str}{marker}")
    lines.extend([
        "",
        "# Hinweis",
        "Lade konkretes Kapitel mit `memory_read({chapter: \"Titel-Substring\"})`.",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helfer — Hit-Strategy (chapter-Match)
# ---------------------------------------------------------------------------


def _find_chapter(
    chapters: list[dict[str, Any]],
    query: str,
) -> tuple[dict[str, Any] | None, str]:
    """Sucht ein Kapitel nach Query mit mehrstufiger Heuristik.

    Reihenfolge: exact → substring → tag → body → miss.

    Returns:
        (chapter_dict | None, hit_type_str). hit_type ist einer aus
        'exact', 'substring', 'substring-multi', 'tag', 'body', 'miss'.
    """
    q = query.lower().strip()
    if not q or not chapters:
        return None, "miss"

    # 1) Exakter Title-Match
    for c in chapters:
        if c["title"].lower() == q:
            return c, "exact"

    # 2) Substring im Title
    matches = [c for c in chapters if q in c["title"].lower()]
    if len(matches) == 1:
        return matches[0], "substring"
    if len(matches) > 1:
        # Bei mehreren: kürzester Title gewinnt (heuristisch der
        # spezifischste Hit). Status 'current' bevorzugt vor archived.
        matches.sort(key=lambda c: (c.get("status") != "current", len(c["title"])))
        return matches[0], "substring-multi"

    # 3) Tag-Match
    matches = [
        c for c in chapters
        if q in [t.lower() for t in (c.get("tags") or [])]
    ]
    if matches:
        matches.sort(key=lambda c: c.get("status") != "current")
        return matches[0], "tag"

    # 4) Body-Volltext (last resort)
    for c in chapters:
        # body_text inline holen (begrenzt durch end), tolerant ggü Hits
        # in Meta. Der Aufrufer entscheidet ob das Kapitel "passt".
        # body_start/body_end auf voller Datei nicht hier verfügbar — wir
        # nehmen den abgespeckten body_preview, falls gesetzt.
        body = c.get("_body_preview") or ""
        if q in body.lower():
            return c, "body"

    return None, "miss"


# ---------------------------------------------------------------------------
# Helfer — Side-Effect: last_referenced + reference_count aktualisieren
# ---------------------------------------------------------------------------


def _update_chapter_meta_after_hit(
    file_path: Path,
    full_text: str,
    chapter: dict[str, Any],
    layer2_offset: int,
) -> int:
    """Aktualisiert last_referenced + reference_count des getroffenen
    Kapitels in der Datei.

    Atomar via tmp+rename. Idempotent (re-run am gleichen Tag setzt das
    gleiche Datum).

    Args:
        file_path: Pfad zur DISCO.md.
        full_text: kompletter Datei-Inhalt (vor dem Update).
        chapter: gematchtes Kapitel-Dict aus _iter_chapters.
        layer2_offset: Offset des layer2-Bereichs in full_text (= Position
            unmittelbar nach dem Marker).

    Returns:
        Neuer reference_count.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_count = int(chapter.get("reference_count") or 0) + 1
    new_meta = {
        "tags": chapter.get("tags") or [],
        "status": chapter.get("status") or "current",
        "created": chapter.get("created"),
        "last_referenced": today,
        "reference_count": new_count,
    }
    new_meta_text = _format_chapter_meta(new_meta)

    if chapter.get("meta_block_start") is not None:
        # Existierenden Meta-Block ersetzen.
        ms = layer2_offset + chapter["meta_block_start"]
        me = layer2_offset + chapter["meta_block_end"]
        new_text = full_text[:ms] + new_meta_text + full_text[me:]
    else:
        # Kein Meta-Block — neu nach dem Heading einfügen.
        # Heading-Ende suchen und Newline einfügen.
        h_start = layer2_offset + chapter["heading_start"]
        # Heading ist die ganze Zeile; finde Zeilenende
        line_end = full_text.find("\n", h_start)
        if line_end < 0:
            line_end = len(full_text)
        insert_at = line_end + 1  # nach dem Heading-Zeilenumbruch
        block = new_meta_text + "\n\n"
        new_text = full_text[:insert_at] + block + full_text[insert_at:]

    try:
        _atomic_write(file_path, new_text)
    except Exception as exc:
        # Side-Effect darf den Read nicht crashen — wir loggen und
        # geben den alten count zurück.
        logger.warning(
            "memory_read: meta-update failed for %s '%s': %s",
            file_path.name, chapter.get("title"), exc,
        )
        return int(chapter.get("reference_count") or 0)
    return new_count


# ---------------------------------------------------------------------------
# Helfer — Trace-Log
# ---------------------------------------------------------------------------


def _log_memory_access(
    *,
    mode: str,
    file: str,
    chapter_query: str | None = None,
    hit_type: str | None = None,
    matched_title: str | None = None,
    bytes_returned: int = 0,
    reference_count_after: int | None = None,
) -> None:
    """Schreibt eine TSV-Zeile in <project>/.disco/memory-access.log.

    Idempotent + best-effort: ein Schreib-Fehler darf den Read nicht
    crashen — dann nur ins logger geloggt.
    """
    try:
        root = get_project_root()
        if root is None:
            return
        log_path = root / TRACE_LOG_REL_PATH
        log_path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not log_path.exists()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cells = [
            ts,
            mode,
            file,
            chapter_query or "-",
            hit_type or "-",
            matched_title or "-",
            str(bytes_returned),
            "-" if reference_count_after is None else str(reference_count_after),
        ]
        line = "\t".join(c.replace("\t", " ") for c in cells) + "\n"
        with log_path.open("a", encoding="utf-8") as fh:
            if new_file:
                fh.write(TRACE_LOG_HEADER)
            fh.write(line)
    except Exception as exc:
        logger.debug("memory-access.log write failed: %s", exc)


# ---------------------------------------------------------------------------
# Helfer — Headings-Outline + Tail
# ---------------------------------------------------------------------------


def _extract_headings_outline(text: str) -> str:
    """Liefert die Heading-Struktur als Markdown-Index mit Layer-Hinweis,
    falls Marker vorhanden."""
    layer1, layer2 = _split_at_layer_marker(text)
    out: list[str] = []
    if layer2 is not None:
        out.append("# Schicht 1 (always-loaded)")
        for n, line in enumerate(layer1.splitlines(), start=1):
            s = line.lstrip()
            if s.startswith("# ") or s.startswith("## ") or s.startswith("### "):
                out.append(f"  L{n:>5}: {s}")
        out.append("")
        out.append("# Schicht 2 (on-demand-Kapitel)")
        layer2_offset_line = layer1.count("\n") + 1
        for c in _iter_chapters(layer2):
            real_line = layer2_offset_line + c["heading_line_idx"]
            tags = c.get("tags") or []
            tag_str = f"  [{', '.join(tags)}]" if tags else ""
            status = c.get("status") or "current"
            status_str = "" if status == "current" else f"  *{status}*"
            out.append(f"  L{real_line:>5}: ## {c['title']}{tag_str}{status_str}")
    else:
        # Vor-Reform-DISCO.md: einfache Outline
        for n, line in enumerate(text.splitlines(), start=1):
            s = line.lstrip()
            if s.startswith("# ") or s.startswith("## ") or s.startswith("### "):
                out.append(f"L{n:>5}: {s}")
    if not out:
        return "(keine Headings gefunden)"
    return "\n".join(out)


# ---------------------------------------------------------------------------
# memory_read — das neue Tool
# ---------------------------------------------------------------------------


@register(
    name="memory_read",
    description=(
        "Liest eine der drei Memory-Dateien des aktiven Projekts: "
        "README.md (Projekt-Briefing des Nutzers), NOTES.md (chronologisches "
        "Logbuch) oder DISCO.md (destilliertes Arbeitsgedächtnis).\n\n"
        "**DISCO.md hat zwei Schichten** — getrennt durch den Marker "
        "`<!-- DISCO-LAYER-1-END -->`:\n"
        "- **Schicht 1** (always-loaded, max 3,5 KB): Projekt-Identität, "
        "Aktueller Fokus, Konventionen, Lookup-Pfade — plus der **Kapitel-"
        "Index** der Schicht-2-Inhalte.\n"
        "- **Schicht 2** (on-demand-Kapitel): Wissens-Sammelstellen, "
        "Glossar, Sessions etc. — wird nur per `chapter`-Parameter "
        "geladen.\n\n"
        "**Default-Verhalten:**\n"
        "- DISCO.md mit Marker → Schicht 1 + Kapitel-Index (typisch ~3 KB).\n"
        "- DISCO.md ohne Marker (Vor-Reform) → erste 8 KB (Fallback).\n"
        "- README.md → komplett (klein).\n"
        "- NOTES.md → kompletter aktueller Stand.\n\n"
        "**Modi (mit Präzedenz):**\n"
        "1. `chapter=\"Titel-Substring\"` — sucht Schicht-2-Kapitel über "
        "exact/substring/tag/body. Bei Hit: Body + Meta. Bei Miss: "
        "{found: false} mit Liste verfügbarer Titel.\n"
        "2. `headings_only=True` — nur Outline, ohne Body.\n"
        "3. `tail=N` — letzte N Zeilen (gut für NOTES).\n"
        "4. `max_bytes=N` (>0) — explizites Bytelimit. `max_bytes=0` = "
        "komplett.\n\n"
        "**Faustregel:** Beim Onboarding zuerst Default → wenn Du ein "
        "konkretes Thema brauchst, gezielt mit `chapter` nachladen. Nicht "
        "blind alles lesen."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "enum": list(READABLE_FILES),
                "description": (
                    "Dateiname im Projekt-Root: README.md, NOTES.md oder DISCO.md."
                ),
            },
            "chapter": {
                "type": "string",
                "description": (
                    "Schicht-2-Kapitel-Lookup (nur DISCO.md). Sucht über "
                    "exact-match, substring im Title, Tag-Match, Body-"
                    "Volltext (in dieser Reihenfolge). Beispiel: "
                    "chapter='Bautechnik IBL' findet '## Bautechnik IBL "
                    "Roh-Stand'. Bei Hit: result.found=True, mit Body + "
                    "Meta. Bei Miss: result.found=False + chapter_index "
                    "(Liste verfügbarer Titel)."
                ),
            },
            "headings_only": {
                "type": "boolean",
                "description": (
                    "Wenn True: liefert nur die Heading-Struktur "
                    "(H1/H2/H3 in Schicht 1 + alle Schicht-2-Kapitel-"
                    "Titel mit Tags), kein Body. Ideal für Orientierung."
                ),
            },
            "tail": {
                "type": "integer",
                "description": (
                    "Wenn gesetzt: letzte N Zeilen statt Kopf. "
                    "Sinnvoll für NOTES.md (chronologisch — neueste "
                    "Einträge unten)."
                ),
            },
            "max_bytes": {
                "type": "integer",
                "description": (
                    "Explizites Bytelimit. 0 = komplett (volle Datei). "
                    "Bei DISCO.md mit Marker überschreibt diesen das "
                    "Schicht-1-Limit nicht — für Volltext explizit "
                    "max_bytes=0."
                ),
            },
        },
        "required": ["file"],
    },
    returns=(
        "{file, exists, mode, content, size_bytes, line_count, total_bytes, "
        "truncated, has_layer_marker?, chapter_index_count?, "
        "found?, hit_type?, matched_title?, chapter_meta?, chapter_index?}"
    ),
)
def _memory_read(
    *,
    file: str,
    chapter: str | None = None,
    headings_only: bool = False,
    tail: int | None = None,
    max_bytes: int | None = None,
    # Backward-compat: alter Name `section` mappt auf chapter
    section: str | None = None,
) -> dict[str, Any]:
    if section and not chapter:
        chapter = section
    path = _resolve(file, allowed=READABLE_FILES)
    if not path.exists():
        _log_memory_access(mode="default", file=file, bytes_returned=0)
        return {
            "file": file,
            "exists": False,
            "mode": "default",
            "content": "",
            "size_bytes": 0,
            "line_count": 0,
            "total_bytes": 0,
            "truncated": False,
        }

    full = path.read_text(encoding="utf-8")
    total_bytes = len(full.encode("utf-8"))

    # ----- Modus-Präzedenz -----
    if chapter and file == "DISCO.md":
        return _handle_chapter(file, path, full, total_bytes, chapter)
    if chapter and file != "DISCO.md":
        # Auf README/NOTES sucht 'chapter' wie ein einfacher Section-Match
        # (kein Meta-Block-System, einfach H2-Substring).
        return _handle_section_legacy(file, full, total_bytes, chapter)
    if headings_only:
        return _handle_headings_only(file, full, total_bytes)
    if tail is not None and tail > 0:
        return _handle_tail(file, full, total_bytes, tail)
    if max_bytes is not None:
        return _handle_max_bytes(file, full, total_bytes, max_bytes)

    # ----- Default -----
    return _handle_default(file, full, total_bytes)


# ---------------------------------------------------------------------------
# Modus-Handler
# ---------------------------------------------------------------------------


def _handle_default(file: str, full: str, total_bytes: int) -> dict[str, Any]:
    """Default: Schicht 1 + Kapitel-Index für DISCO.md mit Marker;
    sonst Fallback auf Legacy-8KB-Cap (DISCO.md) bzw. komplett (README/NOTES).
    """
    if file == "DISCO.md":
        layer1, layer2 = _split_at_layer_marker(full)
        if layer2 is not None:
            chapters = _iter_chapters(layer2)
            index_md = _format_chapter_index(chapters)
            content = layer1 + index_md
            truncated = len(layer1.encode("utf-8")) > LAYER_1_MAX_BYTES
            payload: dict[str, Any] = {
                "file": file,
                "exists": True,
                "mode": "default",
                "content": content,
                "size_bytes": len(content.encode("utf-8")),
                "line_count": content.count("\n") + (
                    0 if content.endswith("\n") or not content else 1
                ),
                "total_bytes": total_bytes,
                "truncated": truncated,
                "has_layer_marker": True,
                "chapter_index_count": len(
                    [c for c in chapters if c.get("status") != "deprecated"]
                ),
            }
            _log_memory_access(
                mode="default", file=file,
                bytes_returned=payload["size_bytes"],
            )
            return payload
        # Kein Marker → Legacy-Verhalten
        cap = DEFAULT_LEGACY_MAX_BYTES
        truncated = total_bytes > cap
        content = (
            full.encode("utf-8")[:cap].decode("utf-8", errors="ignore")
            if truncated else full
        )
        payload = {
            "file": file,
            "exists": True,
            "mode": "default",
            "content": content,
            "size_bytes": len(content.encode("utf-8")),
            "line_count": content.count("\n") + (
                0 if content.endswith("\n") or not content else 1
            ),
            "total_bytes": total_bytes,
            "truncated": truncated,
            "has_layer_marker": False,
        }
        _log_memory_access(
            mode="default", file=file,
            bytes_returned=payload["size_bytes"],
        )
        return payload

    # README.md / NOTES.md → komplett (sind klein bzw. werden auto-archiviert)
    payload = {
        "file": file,
        "exists": True,
        "mode": "default",
        "content": full,
        "size_bytes": total_bytes,
        "line_count": full.count("\n") + (0 if full.endswith("\n") or not full else 1),
        "total_bytes": total_bytes,
        "truncated": False,
    }
    _log_memory_access(mode="default", file=file, bytes_returned=total_bytes)
    return payload


def _handle_chapter(
    file: str,
    path: Path,
    full: str,
    total_bytes: int,
    query: str,
) -> dict[str, Any]:
    """Chapter-Lookup nur in Schicht 2 von DISCO.md."""
    layer1, layer2 = _split_at_layer_marker(full)
    if layer2 is None:
        # Vor-Reform: kein Schicht-Modell. Fallback auf Heading-Substring-Match.
        return _handle_section_legacy(file, full, total_bytes, query)

    chapters = _iter_chapters(layer2)
    # Body-Preview für Body-Volltextsuche befüllen (begrenzt)
    for c in chapters:
        c["_body_preview"] = layer2[c["body_start"]:c["body_end"]][:8_000]

    matched, hit_type = _find_chapter(chapters, query)

    if matched is None:
        # Miss — Liste der verfügbaren Titel zurückliefern
        index = [
            {"title": c["title"], "tags": c.get("tags") or [], "status": c.get("status") or "current"}
            for c in chapters if c.get("status") != "deprecated"
        ]
        _log_memory_access(
            mode="chapter", file=file, chapter_query=query,
            hit_type="miss", bytes_returned=0,
        )
        return {
            "file": file,
            "exists": True,
            "mode": "chapter",
            "found": False,
            "hit_type": "miss",
            "chapter_query": query,
            "chapter_index": index,
            "content": "",
            "size_bytes": 0,
            "line_count": 0,
            "total_bytes": total_bytes,
            "truncated": False,
        }

    # Hit — Body extrahieren (Heading-Zeile + Meta-Block + Body)
    title_line = f"## {matched['title']}\n"
    body = layer2[matched["body_start"]:matched["body_end"]].rstrip() + "\n"
    # Meta-Block in der Antwort als kompakter Hinweis (nicht der raw HTML-Kommentar)
    chapter_meta_compact = {
        "tags": matched.get("tags") or [],
        "status": matched.get("status") or "current",
        "created": matched.get("created"),
        "last_referenced": matched.get("last_referenced"),
        "reference_count": matched.get("reference_count", 0),
    }
    content = title_line + body

    # Side-Effect: last_referenced + reference_count im File aktualisieren.
    layer1_len = full.find(LAYER_MARKER) + len(LAYER_MARKER)
    # nach Marker bis zum ersten Newline überspringen — das ist der layer2_offset
    layer2_offset = layer1_len
    while layer2_offset < len(full) and full[layer2_offset] in ("\n", "\r"):
        layer2_offset += 1
    new_count = _update_chapter_meta_after_hit(path, full, matched, layer2_offset)

    payload = {
        "file": file,
        "exists": True,
        "mode": "chapter",
        "found": True,
        "hit_type": hit_type,
        "chapter_query": query,
        "matched_title": matched["title"],
        "chapter_meta": {**chapter_meta_compact, "reference_count": new_count},
        "content": content,
        "size_bytes": len(content.encode("utf-8")),
        "line_count": content.count("\n") + (0 if content.endswith("\n") or not content else 1),
        "total_bytes": total_bytes,
        "truncated": False,
    }
    _log_memory_access(
        mode="chapter", file=file, chapter_query=query,
        hit_type=hit_type, matched_title=matched["title"],
        bytes_returned=payload["size_bytes"],
        reference_count_after=new_count,
    )
    return payload


def _handle_section_legacy(
    file: str, full: str, total_bytes: int, query: str,
) -> dict[str, Any]:
    """Fallback für DISCO.md ohne Marker oder für README/NOTES:
    findet erste H2/H3 mit `query` als Substring."""
    needle = query.strip().lower()
    if not needle:
        return _handle_default(file, full, total_bytes)
    lines = full.splitlines()
    n = len(lines)
    start_idx: int | None = None
    start_level: int = 0
    for i, raw in enumerate(lines):
        s = raw.lstrip()
        for level, prefix in ((2, "## "), (3, "### ")):
            if s.startswith(prefix) and needle in s[len(prefix):].lower():
                start_idx = i
                start_level = level
                break
        if start_idx is not None:
            break
    if start_idx is None:
        _log_memory_access(
            mode="chapter", file=file, chapter_query=query,
            hit_type="miss", bytes_returned=0,
        )
        return {
            "file": file,
            "exists": True,
            "mode": "chapter",
            "found": False,
            "hit_type": "miss",
            "chapter_query": query,
            "content": "",
            "size_bytes": 0,
            "line_count": 0,
            "total_bytes": total_bytes,
            "truncated": False,
        }
    end_idx = n
    for j in range(start_idx + 1, n):
        s = lines[j].lstrip()
        if (s.startswith("# ") or s.startswith("## ")
                or (start_level == 3 and s.startswith("### "))):
            end_idx = j
            break
    body = "\n".join(lines[start_idx:end_idx]).rstrip() + "\n"
    matched_title = lines[start_idx].lstrip().lstrip("#").strip()
    payload = {
        "file": file,
        "exists": True,
        "mode": "chapter",
        "found": True,
        "hit_type": "substring-legacy",
        "chapter_query": query,
        "matched_title": matched_title,
        "content": body,
        "size_bytes": len(body.encode("utf-8")),
        "line_count": body.count("\n") + (0 if body.endswith("\n") or not body else 1),
        "total_bytes": total_bytes,
        "truncated": False,
    }
    _log_memory_access(
        mode="chapter", file=file, chapter_query=query,
        hit_type="substring-legacy", matched_title=matched_title,
        bytes_returned=payload["size_bytes"],
    )
    return payload


def _handle_headings_only(file: str, full: str, total_bytes: int) -> dict[str, Any]:
    content = _extract_headings_outline(full)
    payload = {
        "file": file,
        "exists": True,
        "mode": "headings_only",
        "content": content,
        "size_bytes": len(content.encode("utf-8")),
        "line_count": content.count("\n") + (0 if content.endswith("\n") or not content else 1),
        "total_bytes": total_bytes,
        "truncated": False,
    }
    _log_memory_access(mode="headings_only", file=file, bytes_returned=payload["size_bytes"])
    return payload


def _handle_tail(
    file: str, full: str, total_bytes: int, tail: int,
) -> dict[str, Any]:
    lines = full.splitlines()
    content = "\n".join(lines[-tail:])
    if full.endswith("\n") or not content:
        content = content + ("\n" if content else "")
    truncated = len(lines) > tail
    payload = {
        "file": file,
        "exists": True,
        "mode": "tail",
        "content": content,
        "size_bytes": len(content.encode("utf-8")),
        "line_count": content.count("\n") + (0 if content.endswith("\n") or not content else 1),
        "total_bytes": total_bytes,
        "truncated": truncated,
    }
    _log_memory_access(mode="tail", file=file, bytes_returned=payload["size_bytes"])
    return payload


def _handle_max_bytes(
    file: str, full: str, total_bytes: int, max_bytes: int,
) -> dict[str, Any]:
    if max_bytes <= 0 or total_bytes <= max_bytes:
        content = full
        truncated = False
    else:
        content = full.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        truncated = True
    payload = {
        "file": file,
        "exists": True,
        "mode": "max_bytes",
        "content": content,
        "size_bytes": len(content.encode("utf-8")),
        "line_count": content.count("\n") + (0 if content.endswith("\n") or not content else 1),
        "total_bytes": total_bytes,
        "truncated": truncated,
    }
    _log_memory_access(mode="max_bytes", file=file, bytes_returned=payload["size_bytes"])
    return payload


# ---------------------------------------------------------------------------
# memory_write
# ---------------------------------------------------------------------------


@register(
    name="memory_write",
    description=(
        "Überschreibt README.md oder DISCO.md des aktiven Projekts "
        "vollständig (atomar, tmp+rename). NOTES.md kann NICHT "
        "überschrieben werden — es ist das chronologische Logbuch, "
        "dafür memory_append nutzen.\n\n"
        "**WICHTIG:** Vorher memory_read aufrufen — Blind-Overwrites sind "
        "verboten. Bei DISCO.md mit Schicht-1/Schicht-2-Marker: "
        "`<!-- DISCO-LAYER-1-END -->` muss erhalten bleiben, sonst "
        "verliert das Projekt sein Reform-Format. Bei README.md: nur "
        "nach Rücksprache mit dem Nutzer überschreiben."
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
                "description": "Vollständiger Datei-Inhalt (Markdown).",
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
        "Hängt einen Abschnitt an NOTES.md oder DISCO.md an.\n"
        "- NOTES.md: automatischer '## YYYY-MM-DD HH:MM:SS'-Header. "
        "Append-only Logbuch.\n"
        "- DISCO.md: heading optional als H2 vorangestellt. **Wenn das "
        "Projekt das Reform-Format nutzt** (Marker vorhanden), landet "
        "der Append in Schicht 2 (unten). Beim Anlegen neuer Kapitel "
        "wird ein chapter-meta-Block mit angefügt, wenn `tags` oder "
        "`status` gesetzt sind.\n\n"
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
                "description": "Markdown-Text, der angehängt werden soll.",
            },
            "heading": {
                "type": "string",
                "description": (
                    "Optionale H2-Überschrift (ohne '## '). Bei NOTES.md: "
                    "als H3 unter Timestamp. Bei DISCO.md: als H2-Kapitel."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Nur DISCO.md: optionale Tags für den chapter-meta-"
                    "Block (lower-case empfohlen). Wenn gesetzt + heading "
                    "gesetzt + Reform-Format aktiv: Disco fügt einen "
                    "chapter-meta-Block direkt unter dem Heading ein."
                ),
            },
            "status": {
                "type": "string",
                "enum": ["current", "archived", "deprecated"],
                "description": (
                    "Nur DISCO.md, optional. Default 'current'. Setzt "
                    "den status im chapter-meta-Block."
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
    tags: list[str] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("content darf nicht leer sein.")

    path = _resolve(file, allowed=APPENDABLE_FILES)
    created = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)

    if created:
        if file == "NOTES.md":
            initial = "# Projekt-Notizen\n\n"
        elif file == "DISCO.md":
            initial = "# DISCO.md\n\n"
        else:
            initial = ""
        path.write_text(initial, encoding="utf-8")

    block = _build_append_block(
        file=file, content=content, heading=heading, tags=tags, status=status,
    )
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
    tags: list[str] | None = None,
    status: str | None = None,
) -> str:
    body = content.rstrip() + "\n"
    if file == "NOTES.md":
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"\n\n---\n\n## {ts}"]
        if heading and heading.strip():
            parts.append(f"\n\n### {heading.strip()}")
        parts.append(f"\n\n{body}")
        return "".join(parts)

    # DISCO.md: bei heading + tags/status zusätzlich chapter-meta-Block.
    parts: list[str] = []
    if heading and heading.strip():
        parts.append(f"\n\n## {heading.strip()}\n")
        if (tags is not None) or (status is not None):
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            meta = {
                "tags": tags or [],
                "status": status or "current",
                "created": today,
                "last_referenced": today,
                "reference_count": 0,
            }
            parts.append(_format_chapter_meta(meta))
            parts.append("\n")
        parts.append(f"\n{body}")
    else:
        parts.append(f"\n\n{body}")
    return "".join(parts)
