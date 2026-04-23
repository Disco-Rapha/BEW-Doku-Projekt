"""Volltextsuche mit SQLite FTS5 (Phase 0 der Suchinfrastruktur).

Zwei Tools:

- `build_search_index` — indiziert Dateien unter sources/ und context/
  seitenweise (PDFs) bzw. komplett (Markdown/Text). Idempotent ueber
  sha256-Hash: unveraenderte Dateien werden uebersprungen. Bei Aenderung
  werden die alten Chunks geloescht und neu geschrieben.

- `search_documents` — FTS5-Query mit BM25-Ranking, optional gefiltert
  nach kind (sources/context/...). Liefert pro Treffer Snippet, Score,
  Dokumentpfad, Seitenzahl.

Granularitaet: ein Chunk = eine Seite (PDF) oder die ganze Datei
(Markdown/TXT). Jeder Chunk bekommt eine Kontext-Praeambel mit
Dateiname, Seitenzahl und naechstgelegener Ueberschrift — das pusht
das BM25-Ranking ohne Extra-Infrastruktur.

Phase 1 (Embeddings via sqlite-vec) wird spaeter parallele Vektoren
auf dieselben Chunks legen; die Struktur hier bleibt identisch.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from . import register
from ..context import connect_datastore_rw
from .fs import _data_root, _resolve_under_data


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

INDEXER_VERSION = "v1"

# Dateitypen, die wir indizieren. Alles andere wird still uebersprungen.
INDEXABLE_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}

# Oberes Limit pro Seite — wenn ein PDF eine extrem lange Seite hat
# (z.B. grosser Anhang ohne Seitenumbruch), schuetzt uns das vor
# FTS5-Index-Explosion. Truncation wird im Chunk vermerkt.
MAX_CHARS_PER_CHUNK = 30_000

# Default-Wurzeln, wenn der Aufrufer nichts vorgibt.
DEFAULT_ROOTS = ("sources", "context")

# Such-Defaults
DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 50
DEFAULT_SNIPPET_TOKENS = 20

# FTS5-Syntax-Hilfe: Tokens, die nur aus diesen Zeichen bestehen, duerfen
# unquoted in die Query. Alles andere wird automatisch in Anfuehrungs-
# zeichen gesetzt, damit "3.1" oder "EN 10204" oder "1.1.PAC10.AP001"
# nicht zum Syntax-Fehler fuehren.
_FTS_OPERATORS = {"AND", "OR", "NOT", "NEAR"}
_FTS_TOKEN_SAFE = re.compile(r"^[A-Za-z0-9äöüÄÖÜß_*]+$")


def _fts_safe_query(query: str) -> str:
    """Macht eine User-Query FTS5-sicher, ohne Semantik zu aendern.

    - Bereits gequotete Phrasen bleiben unangetastet.
    - Bare Tokens mit Sonderzeichen (z.B. '3.1', 'P-101') werden
      in Anfuehrungszeichen gewickelt.
    - Operatoren (AND/OR/NOT/NEAR) und Klammern bleiben erhalten.
    - Prefix-Stern (schall*) bleibt erhalten.
    """
    q = query.strip()
    if not q:
        return q
    out: list[str] = []
    i = 0
    n = len(q)
    while i < n:
        c = q[i]
        if c.isspace():
            out.append(c)
            i += 1
            continue
        if c == '"':
            # Bereits gequotete Phrase: bis zum naechsten " uebernehmen
            j = q.find('"', i + 1)
            if j == -1:
                # Unmatched quote — verwerfen, um FTS5-Syntax-Fehler zu vermeiden
                i += 1
                continue
            out.append(q[i : j + 1])
            i = j + 1
            continue
        if c in "(),":
            out.append(c)
            i += 1
            continue
        # Token bis Whitespace / Quote / Klammer / Komma
        j = i
        while j < n and not q[j].isspace() and q[j] not in '(),"':
            j += 1
        tok = q[i:j]
        upper = tok.upper()
        if upper in _FTS_OPERATORS:
            out.append(upper)
        elif _FTS_TOKEN_SAFE.match(tok):
            out.append(tok)
        else:
            esc = tok.replace('"', '""')
            out.append(f'"{esc}"')
        i = j
    return "".join(out).strip()


# ---------------------------------------------------------------------------
# build_search_index
# ---------------------------------------------------------------------------


@register(
    name="build_search_index",
    description=(
        "Baut den Volltext-Such-Index (FTS5) fuer das aktive Projekt. "
        "Indiziert PDFs seitenweise und Markdown/TXT als Ganzes. "
        "Idempotent: unveraenderte Dateien werden anhand ihres sha256-Hash "
        "uebersprungen. Default: alle Dateien unter sources/ und context/. "
        "Am Ende steht ein kurzer Report mit indizierten/uebersprungenen/"
        "fehlerhaften Dateien."
    ),
    parameters={
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional: Liste von Pfaden oder Ordnern relativ zum "
                    "Projekt. Default: ['sources','context']."
                ),
            },
            "force_reindex": {
                "type": "boolean",
                "description": (
                    "Wenn true, werden auch unveraenderte Dateien neu "
                    "indiziert (Chunks werden geloescht und neu geschrieben). "
                    "Default: false."
                ),
            },
            "max_files": {
                "type": "integer",
                "description": (
                    "Optional: harte Obergrenze fuer verarbeitete Dateien — "
                    "fuer Testlaeufe."
                ),
            },
        },
        "required": [],
    },
    returns=(
        "{indexed:[{path,pages,chunks}], skipped:[...], errors:[...], "
        "total_files, total_chunks, total_pages}"
    ),
)
def _build_search_index(
    *,
    paths: list[str] | None = None,
    force_reindex: bool = False,
    max_files: int | None = None,
) -> dict[str, Any]:
    roots = _resolve_indexing_roots(paths)
    files = _collect_indexable_files(roots)
    if max_files is not None and max_files > 0:
        files = files[: max_files]

    conn = connect_datastore_rw()
    _ensure_schema(conn)

    indexed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    total_chunks = 0
    total_pages = 0

    try:
        for abs_path in files:
            rel = _rel_to_data(abs_path)
            kind = _kind_from_rel(rel)
            ext = abs_path.suffix.lower().lstrip(".")
            try:
                digest, size = _hash_and_size(abs_path)
            except Exception as exc:
                logger.warning("Hash fehlgeschlagen fuer %s: %s", rel, exc)
                errors.append({"path": rel, "error": f"hash: {exc}"})
                continue

            # Bestehenden Eintrag suchen
            existing = conn.execute(
                "SELECT id, sha256, n_chunks FROM agent_search_docs "
                "WHERE rel_path = ?",
                (rel,),
            ).fetchone()

            if existing and existing["sha256"] == digest and not force_reindex:
                skipped.append({
                    "path": rel,
                    "reason": "unchanged",
                    "chunks": existing["n_chunks"],
                })
                continue

            # Extraktion
            try:
                chunks = _extract_chunks(abs_path, ext)
            except Exception as exc:
                logger.warning("Extraktion fehlgeschlagen fuer %s: %s", rel, exc)
                errors.append({"path": rel, "error": f"extract: {exc}"})
                continue

            # UPSERT des Dokuments
            if existing:
                doc_id = existing["id"]
                # alte Chunks loeschen
                conn.execute(
                    "DELETE FROM agent_search_chunks_fts WHERE doc_id = ?",
                    (doc_id,),
                )
                conn.execute(
                    "UPDATE agent_search_docs SET "
                    "sha256=?, size_bytes=?, total_pages=?, n_chunks=?, "
                    "indexed_at=datetime('now'), indexer_version=?, error=NULL "
                    "WHERE id = ?",
                    (
                        digest,
                        size,
                        len(chunks),
                        len(chunks),
                        INDEXER_VERSION,
                        doc_id,
                    ),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO agent_search_docs "
                    "(rel_path, kind, filename, extension, sha256, size_bytes, "
                    " total_pages, n_chunks, indexer_version) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        rel,
                        kind,
                        abs_path.name,
                        ext,
                        digest,
                        size,
                        len(chunks),
                        len(chunks),
                        INDEXER_VERSION,
                    ),
                )
                doc_id = cur.lastrowid

            # neue Chunks einfuegen
            for ch in chunks:
                preamble = _preamble(abs_path.name, ch["page_num"], ch["heading"])
                body = (preamble + "\n" + ch["text"]).strip()
                if len(body) > MAX_CHARS_PER_CHUNK:
                    body = body[:MAX_CHARS_PER_CHUNK]
                conn.execute(
                    "INSERT INTO agent_search_chunks_fts "
                    "(text, heading, doc_id, doc_path, kind, page_num) "
                    "VALUES (?,?,?,?,?,?)",
                    (body, ch["heading"] or "", doc_id, rel, kind, ch["page_num"]),
                )

            conn.commit()
            indexed.append({
                "path": rel,
                "pages": len(chunks),
                "chunks": len(chunks),
            })
            total_chunks += len(chunks)
            total_pages += len(chunks)

    finally:
        conn.close()

    return {
        "indexed": indexed,
        "skipped": skipped,
        "errors": errors,
        "total_files": len(indexed),
        "total_chunks": total_chunks,
        "total_pages": total_pages,
        "force_reindex": force_reindex,
    }


# ---------------------------------------------------------------------------
# search_documents
# ---------------------------------------------------------------------------


@register(
    name="search_index",
    description=(
        "Volltext-Suche im Projekt-Index (FTS5, BM25-Ranking). Die Query "
        "ist FTS5-Syntax: Woerter werden UND-verknuepft, Phrasen in "
        "\"Anfuehrungszeichen\", Prefix mit Sternchen (z.B. 'schall*'), "
        "Boolesche Operatoren AND/OR/NOT, NEAR(a b, 5). Rueckgabe: Liste "
        "von Treffern mit Dokumentpfad, Seitenzahl, Snippet und Score. "
        "Optional einschraenken auf kind=sources oder kind=context."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "FTS5-Query. Beispiele: 'pumpe schallschutz', "
                    "'\"Druckprobe 10 bar\"', 'schall* NOT elektro', "
                    "'NEAR(pumpe leistung, 5)'."
                ),
            },
            "limit": {
                "type": "integer",
                "description": f"Max. Treffer (Default {DEFAULT_SEARCH_LIMIT}, Max {MAX_SEARCH_LIMIT}).",
            },
            "kind": {
                "type": "string",
                "description": (
                    "Optional: nur in einem Teilbereich suchen. Gueltig: "
                    "'sources', 'context', 'exports', 'work'."
                ),
            },
        },
        "required": ["query"],
    },
    returns=(
        "{query, hits:[{path, page, kind, heading, snippet, score}], "
        "n_hits, total_matches}"
    ),
)
def _search_index(
    *,
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    kind: str | None = None,
) -> dict[str, Any]:
    if not query or not query.strip():
        raise ValueError("query darf nicht leer sein.")

    limit = max(1, min(int(limit or DEFAULT_SEARCH_LIMIT), MAX_SEARCH_LIMIT))

    if kind is not None and kind not in {"sources", "context", "exports", "work"}:
        raise ValueError(
            f"Ungueltiges kind: {kind!r}. Erlaubt: sources, context, exports, work."
        )

    # FTS5 lehnt nackte Tokens mit Sonderzeichen ab ('3.1' -> syntax error).
    # Wir sanitizen die User-Query, protokollieren aber das Original.
    user_query = query
    fts_query = _fts_safe_query(query)

    conn = connect_datastore_rw()
    try:
        _ensure_schema(conn)

        # Vorab: gibt es ueberhaupt einen Index?
        n_docs = conn.execute(
            "SELECT COUNT(*) AS n FROM agent_search_docs"
        ).fetchone()["n"]
        if n_docs == 0:
            return {
                "query": user_query,
                "fts_query": fts_query,
                "hits": [],
                "n_hits": 0,
                "total_matches": 0,
                "note": (
                    "Index ist leer. Zuerst build_search_index aufrufen."
                ),
            }

        sql = (
            "SELECT "
            "  doc_id, doc_path, kind, page_num, heading, "
            "  snippet(agent_search_chunks_fts, 0, '[[', ']]', ' … ', ?) AS snippet, "
            "  bm25(agent_search_chunks_fts) AS score "
            "FROM agent_search_chunks_fts "
            "WHERE agent_search_chunks_fts MATCH ? "
        )
        params: list[Any] = [DEFAULT_SNIPPET_TOKENS, fts_query]

        if kind is not None:
            sql += "  AND kind = ? "
            params.append(kind)

        sql += "ORDER BY score LIMIT ?"
        params.append(limit)

        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            return {
                "query": user_query,
                "fts_query": fts_query,
                "hits": [],
                "n_hits": 0,
                "total_matches": 0,
                "error": f"FTS5-Syntax: {exc}",
            }

        hits = [
            {
                "path": r["doc_path"],
                "page": r["page_num"],
                "kind": r["kind"],
                "heading": r["heading"] or None,
                "snippet": _clean_snippet(r["snippet"]),
                "score": round(r["score"], 4),
            }
            for r in rows
        ]

        # Gesamttrefferanzahl, falls limit getroffen
        count_sql = (
            "SELECT COUNT(*) AS n FROM agent_search_chunks_fts "
            "WHERE agent_search_chunks_fts MATCH ?"
        )
        count_params: list[Any] = [fts_query]
        if kind is not None:
            count_sql += " AND kind = ?"
            count_params.append(kind)
        try:
            total = conn.execute(count_sql, count_params).fetchone()["n"]
        except sqlite3.OperationalError:
            total = len(hits)

        return {
            "query": user_query,
            "fts_query": fts_query,
            "hits": hits,
            "n_hits": len(hits),
            "total_matches": total,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Intern: Schema-Absicherung
# ---------------------------------------------------------------------------


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Sicherheitsnetz fuer Bestands-Projekte, die die 006er-Migration
    noch nicht gesehen haben — sollte nach `apply_project_db_migrations`
    ein No-Op sein."""
    existing = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall()
    }
    if "agent_search_docs" in existing and "agent_search_chunks_fts" in existing:
        return

    # Minimal-Schema nachziehen (identisch zu 006_search_index.sql)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_search_docs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            rel_path        TEXT NOT NULL UNIQUE,
            kind            TEXT NOT NULL,
            filename        TEXT NOT NULL,
            extension       TEXT,
            sha256          TEXT,
            size_bytes      INTEGER NOT NULL DEFAULT 0,
            total_pages     INTEGER NOT NULL DEFAULT 0,
            n_chunks        INTEGER NOT NULL DEFAULT 0,
            indexed_at      TEXT NOT NULL DEFAULT (datetime('now')),
            indexer_version TEXT NOT NULL DEFAULT 'v1',
            error           TEXT,
            CHECK (kind IN ('sources','context','exports','work'))
        );
        CREATE INDEX IF NOT EXISTS idx_search_docs_kind
            ON agent_search_docs(kind);
        CREATE INDEX IF NOT EXISTS idx_search_docs_sha
            ON agent_search_docs(sha256);
        CREATE VIRTUAL TABLE IF NOT EXISTS agent_search_chunks_fts USING fts5(
            text,
            heading,
            doc_id UNINDEXED,
            doc_path UNINDEXED,
            kind UNINDEXED,
            page_num UNINDEXED,
            tokenize = 'unicode61 remove_diacritics 2',
            prefix = '2 3 4'
        );
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Intern: Datei-Discovery
# ---------------------------------------------------------------------------


def _resolve_indexing_roots(paths: list[str] | None) -> list[Path]:
    """Welche absoluten Pfade indizieren wir?"""
    root = _data_root()
    if not paths:
        paths = list(DEFAULT_ROOTS)

    resolved: list[Path] = []
    for p in paths:
        try:
            target = _resolve_under_data(p)
        except ValueError:
            logger.warning("Pfad ausserhalb data/: %r — ignoriert", p)
            continue
        if not target.exists():
            continue
        resolved.append(target)
    return resolved


def _collect_indexable_files(roots: list[Path]) -> list[Path]:
    """Sammelt alle indizierbaren Dateien unter den Wurzeln."""
    files: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root.is_file():
            if root.suffix.lower() in INDEXABLE_EXTENSIONS and root not in seen:
                files.append(root)
                seen.add(root)
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            if p.name.startswith("."):
                continue
            if p.suffix.lower() not in INDEXABLE_EXTENSIONS:
                continue
            if p in seen:
                continue
            files.append(p)
            seen.add(p)
    return files


def _rel_to_data(abs_path: Path) -> str:
    """Pfad relativ zu data/ als string mit Forward-Slashes."""
    return str(abs_path.relative_to(_data_root())).replace("\\", "/")


def _kind_from_rel(rel: str) -> str:
    first = rel.split("/", 1)[0]
    if first in {"sources", "context", "exports", "work"}:
        return first
    return "work"


# ---------------------------------------------------------------------------
# Intern: Hash + Extraktion
# ---------------------------------------------------------------------------


def _hash_and_size(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return h.hexdigest(), size


def _extract_chunks(path: Path, ext: str) -> list[dict[str, Any]]:
    """Liefert eine Liste {page_num, heading, text} pro Chunk."""
    if ext == "pdf":
        return _extract_pdf_chunks(path)
    if ext in {"md", "markdown"}:
        return _extract_markdown_chunks(path)
    if ext == "txt":
        return _extract_text_chunks(path)
    raise ValueError(f"Nicht unterstuetzte Endung: .{ext}")


def _extract_pdf_chunks(path: Path) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf fehlt — `uv sync` laufen lassen.") from exc

    reader = PdfReader(str(path))
    chunks: list[dict[str, Any]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            logger.warning("PDF-Seite %d Extraktion fehlgeschlagen (%s): %s",
                           i, path.name, exc)
            text = ""
        text = text.strip()
        if not text:
            # Leere Seiten trotzdem als Chunk aufnehmen, damit doc.total_pages
            # stimmt. Der FTS-Index ignoriert sie natuerlich effektiv.
            chunks.append({
                "page_num": i,
                "heading": "",
                "text": "",
            })
            continue
        heading = _first_line_as_heading(text)
        chunks.append({
            "page_num": i,
            "heading": heading,
            "text": text,
        })
    return chunks


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def _extract_markdown_chunks(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    # Fuer MVP: ganze Datei = ein Chunk. Heading = erster #-Heading im Text.
    match = _HEADING_RE.search(text)
    heading = match.group(2).strip() if match else ""
    return [{
        "page_num": 1,
        "heading": heading,
        "text": text.strip(),
    }]


def _extract_text_chunks(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [{
        "page_num": 1,
        "heading": "",
        "text": text.strip(),
    }]


def _first_line_as_heading(text: str) -> str:
    """Heuristik fuer PDF-Seite: die erste nicht-leere Zeile, wenn sie
    kurz genug ist (< 120 Zeichen), sonst leer."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) > 120:
            return ""
        return line
    return ""


# ---------------------------------------------------------------------------
# Intern: Praeambel + Snippet-Cleanup
# ---------------------------------------------------------------------------


def _preamble(filename: str, page_num: int, heading: str) -> str:
    """Kontext-Zeilen die wir jedem FTS-Chunk voranstellen.

    Der Dokumentname und die naechstliegende Ueberschrift werden mit
    tokenisiert, was BM25-Treffer bei Dateiname- oder Ueberschriften-
    Keywords deutlich praeziser macht.
    """
    parts = [f"Dokument: {filename}", f"Seite: {page_num}"]
    if heading:
        parts.append(f"Abschnitt: {heading}")
    return " | ".join(parts)


_SNIPPET_WS_RE = re.compile(r"\s+")


def _clean_snippet(snippet: str | None) -> str:
    if not snippet:
        return ""
    return _SNIPPET_WS_RE.sub(" ", snippet).strip()
