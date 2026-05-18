"""Dateisystem-Tools: streng auf settings.data_dir beschraenkt.

Sicherheits-Design:
  - Alle Pfade werden gegen `settings.data_dir` resolved und muessen
    **unterhalb** davon liegen (Path-Traversal-Schutz).
  - Relative Pfade sind bequem; absolute Pfade werden akzeptiert, aber nur,
    wenn sie unter `data_dir` liegen.
  - Symlinks werden aufgeloest; zielt der Symlink aus `data_dir` heraus,
    wird er abgelehnt.
  - `fs_read` liefert NUR Text. Binaerdateien (PDFs, Bilder, Excel) werden
    erkannt und mit einem klaren Hinweis abgelehnt — PDF-Inhalte laufen
    ausschliesslich ueber `pdf_markdown_read` (siehe Pipeline `pdf_to_markdown`).
  - Hardlimits: Verzeichnisse max. 500 Eintraege, Dateien max. 200 KB
    (beide ueberschreibbar per Parameter, aber mit Obergrenzen).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ...config import settings
from . import register


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

DEFAULT_LIST_LIMIT = 200          # bewusst klein — gegen Context-Bloat (Feedback 14.05)
MAX_LIST_LIMIT = 5000
# Output-Byte-Cap zusaetzlich zum Item-Cap. Wenn die JSON-Repraesentation
# darueber wuerde, koennen wir vorzeitig abbrechen.
MAX_LIST_BYTES = 8000             # ~2000 Token — passt in einen normalen Tool-Result

DEFAULT_READ_BYTES = 12_000       # 12 KB ≈ 3 k Tokens — Sockel-schonend (Audit 14.05)
MAX_READ_BYTES = 2_000_000        # 2 MB Text — harte Obergrenze gegen Kontext-Explosion
MAX_READ_BYTES_BINARY = 5_000_000 # 5 MB Binaer (base64-Output ist ~33% groesser)
# Hinweis fuer Disco: bei truncated=True kann er mit max_bytes=N gezielt
# mehr lesen oder die Datei in Teilen verarbeiten.

# Schreib-Limits (Agent soll eher viele kleine Files anlegen als wenige riesige)
MAX_WRITE_BYTES = 10_000_000      # 10 MB

# Endungen, die der Agent NIEMALS schreiben darf — Schutz vor versehentlicher
# DB/Secret-Ueberschreibung
FORBIDDEN_WRITE_SUFFIXES = {".db", ".db-wal", ".db-shm", ".sqlite", ".env"}

# Heuristik: diese Suffixe sind fuer fs_read verboten, weil binaer.
# Fuer PDFs existiert pdf_markdown_read (liest aus agent_pdf_markdown,
# wird vom Flow `pdf_to_markdown` gefuellt); fuer Excel/Images gibt es
# spezielle Tools in spaeteren Phasen.
BINARY_SUFFIXES = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".ico",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".sqlite", ".db", ".db-wal", ".db-shm",
    ".exe", ".dll", ".so", ".dylib", ".bin",
}


# ---------------------------------------------------------------------------
# fs_list
# ---------------------------------------------------------------------------


@register(
    name="fs_list",
    description=(
        "Listet Dateien und Unterordner unter einem Pfad relativ zu data/. "
        "Nutze leeren Pfad oder '.' fuer das Wurzel-data-Verzeichnis. "
        "Optional rekursiv und mit Glob-Pattern (z.B. '*.pdf'). "
        "Output ist BEWUSST kompakt (max ~200 items, ~8KB) — bei groesseren "
        "Verzeichnissen filter via pattern oder recursive=false. "
        "Kein Zugriff ausserhalb von data/."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad relativ zu data/ (oder leer fuer data/ selbst).",
            },
            "recursive": {
                "type": "boolean",
                "description": "Rekursiv alle Unterordner durchsuchen (Default: false).",
            },
            "pattern": {
                "type": "string",
                "description": "Optionales Glob-Muster (z.B. '*.pdf', '*.md').",
            },
            "limit": {
                "type": "integer",
                "description": f"Max. Eintraege (Default {DEFAULT_LIST_LIMIT}, Max {MAX_LIST_LIMIT}).",
            },
            "include_canonical_path": {
                "type": "boolean",
                "description": (
                    "Wenn true, wird pro Entry zusaetzlich canonical_path (NFC + '/') "
                    "geliefert. Default: false (rel_path reicht meistens; ein "
                    "canonical_path-Lookup geht via sqlite_query auf agent_sources)."
                ),
            },
        },
        "required": [],
    },
    returns="{root, path, entries: [{name, type, size, modified, rel_path[, canonical_path]}], total, truncated, truncation_reason}",
)
def _fs_list(
    *,
    path: str = "",
    recursive: bool = False,
    pattern: str | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
    include_canonical_path: bool = False,
) -> dict[str, Any]:
    root = _data_root()
    target = _resolve_under_data(path or ".")

    if not target.exists():
        raise ValueError(f"Pfad existiert nicht: {path!r}")
    if not target.is_dir():
        raise ValueError(f"Pfad ist keine Ordner: {path!r}")

    effective_limit = max(1, min(int(limit or DEFAULT_LIST_LIMIT), MAX_LIST_LIMIT))

    # Kandidaten sammeln
    if recursive:
        it = target.rglob(pattern) if pattern else target.rglob("*")
    else:
        it = target.glob(pattern) if pattern else target.iterdir()

    entries: list[dict[str, Any]] = []
    total_seen = 0
    bytes_running = 100  # grobe Initial-Schaetzung fuer JSON-Wrapper
    truncation_reason: str | None = None

    # Resolver einmalig holen (statt pro Entry)
    from disco.fs.path_resolver import get_resolver
    resolver = get_resolver()

    for p in it:
        total_seen += 1
        if len(entries) >= effective_limit:
            if truncation_reason is None:
                truncation_reason = f"item_limit={effective_limit}"
            continue
        if bytes_running >= MAX_LIST_BYTES:
            if truncation_reason is None:
                truncation_reason = f"byte_limit={MAX_LIST_BYTES}"
            continue

        # Symlink-Schutz: aufloesen und pruefen, dass das Ziel unter data_dir bleibt
        try:
            resolved = p.resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        if not _is_under(resolved, root):
            continue

        try:
            stat = p.stat()
        except OSError:
            continue

        # rel_path = FS-actual (mit Mac-Quirks); canonical_path nur on-demand.
        # Default-Output bewusst schlank — Disco kann fuer canonical-Form
        # gezielt sqlite_query auf agent_sources nutzen.
        fs_rel = str(p.relative_to(root))
        entry: dict[str, Any] = {
            "name": resolver.to_canonical(p.name),
            "type": "dir" if p.is_dir() else "file",
            "size": stat.st_size if p.is_file() else None,
            "modified": _fmt_mtime(stat.st_mtime),
            "rel_path": fs_rel,
        }
        if include_canonical_path:
            entry["canonical_path"] = resolver.to_canonical(fs_rel)
        entries.append(entry)
        # Approx-Byte-Tracking: name + rel_path + JSON-Wrapper-Overhead
        bytes_running += len(entry["name"]) + len(fs_rel) + 80

    # Sort: Ordner zuerst, dann alphabetisch
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))

    return {
        "root": str(root),
        "path": str(target.relative_to(root)) or ".",
        "entries": entries,
        "total": total_seen,
        "truncated": total_seen > len(entries),
        "truncation_reason": truncation_reason,
    }


# ---------------------------------------------------------------------------
# fs_read
# ---------------------------------------------------------------------------


@register(
    name="fs_read",
    description=(
        "Liest eine Textdatei unter data/. Fuer PDFs bitte doc_markdown_read "
        "verwenden (extrahierter Markdown). "
        "Default-Limit ist 12 KB (~3k Tokens) — Sockel-schonend. "
        "WICHTIG: Wenn truncated=true im Response, ist die Datei groesser "
        "als das Default-Limit. Du kannst dann ohne Qualitaetsverlust einen "
        "zweiten Call mit hoeherem max_bytes machen (z.B. max_bytes=50000 "
        "oder den vollen size_bytes-Wert aus der ersten Response), wenn der "
        "Inhalt fuer die Aufgabe wirklich relevant ist. Du verlierst keinen "
        "Kontext durch das Default — nur Tokens, falls Du den Rest nicht "
        "brauchst. size_bytes im Response verraet die Original-Groesse. "
        "Kein Zugriff ausserhalb von data/."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad relativ zu data/ (z.B. 'markdown/123.md').",
            },
            "max_bytes": {
                "type": "integer",
                "description": (
                    f"Max. Bytes, die gelesen werden (Default {DEFAULT_READ_BYTES}, "
                    f"Max {MAX_READ_BYTES}). Bei truncated=true ohne Qualitaetsverlust "
                    f"einen zweiten Call mit hoeherem Wert machen."
                ),
            },
            "encoding": {
                "type": "string",
                "description": "Zeichenkodierung (Default 'utf-8').",
            },
        },
        "required": ["path"],
    },
    returns="{path, text, bytes_read, size_bytes, truncated, encoding}",
)
def _fs_read(
    *,
    path: str,
    max_bytes: int = DEFAULT_READ_BYTES,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    if not path:
        raise ValueError("path ist erforderlich.")

    target = _resolve_under_data(path)
    if not target.exists():
        raise ValueError(f"Datei nicht gefunden: {path!r}")
    if not target.is_file():
        raise ValueError(f"Pfad ist keine Datei: {path!r}")

    # Binaer-Blocker
    if target.suffix.lower() in BINARY_SUFFIXES:
        raise ValueError(
            f"Binaere Datei '{target.suffix}' nicht lesbar via fs_read. "
            f"Fuer PDFs pdf_markdown_read verwenden."
        )

    effective_max = max(1, min(int(max_bytes or DEFAULT_READ_BYTES), MAX_READ_BYTES))
    size = target.stat().st_size

    try:
        with target.open("rb") as fh:
            raw = fh.read(effective_max + 1)
    except OSError as exc:
        raise ValueError(f"Lesefehler: {exc}") from exc

    truncated = len(raw) > effective_max
    if truncated:
        raw = raw[:effective_max]

    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Datei ist nicht als {encoding!r} lesbar (vermutlich binaer): {exc}"
        ) from exc

    root = _data_root()
    return {
        "path": str(target.relative_to(root)),
        "text": text,
        "bytes_read": len(raw),
        "size_bytes": size,
        "truncated": truncated,
        "encoding": encoding,
    }


# ---------------------------------------------------------------------------
# fs_search — Volltextsuche in Text-Dateien
# ---------------------------------------------------------------------------


# Ordner, die bei fs_search grundsaetzlich uebersprungen werden
_SEARCH_SKIP_DIRS = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

# Max. Bytes, die pro Datei eingelesen werden (sonst Speicher-Explosion).
# Wir lesen die ganze Datei ein, um Zeilen-Kontext zu kennen.
_SEARCH_MAX_FILE_BYTES = 2_000_000  # 2 MB pro Datei

# Max. Zeichen pro ausgegebener Zeile — gegen Riesen-Zeilen (minified JSON etc.)
_SEARCH_LINE_MAX = 400


@register(
    name="fs_search",
    description=(
        "Sucht einen Text/Regex in allen Text-Dateien unter data/ (bzw. im "
        "aktiven Projekt). Aehnelt 'grep -rn'. Binaerdateien (PDF, Excel, "
        "Bilder, ...) werden uebersprungen — fuer PDF-Inhalt ist "
        "pdf_markdown_read zustaendig (gefuellt vom Flow `pdf_to_markdown`). "
        "Liefert pro Treffer Dateiname, Zeilennummer, Zeile und optional "
        "Kontext-Zeilen vorher/nachher. Standardmaessig case-insensitive "
        "literale Suche; mit regex=true ist das Pattern ein Python-Regex."
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Zu suchender Text oder (bei regex=true) Python-Regex-Pattern.",
            },
            "path": {
                "type": "string",
                "description": (
                    "Unterordner zum Durchsuchen (relativ zu data/). Leer = "
                    "ganzes Projekt. Beispiele: 'context', 'sources/Elektro', '.disco/plans'."
                ),
            },
            "glob": {
                "type": "string",
                "description": (
                    "Optionales Datei-Muster, z.B. '*.md', '*.py', '*.json'. "
                    "Leer = alle Text-Dateien."
                ),
            },
            "regex": {
                "type": "boolean",
                "description": "True = pattern als Python-Regex. Default false (literale Suche).",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Gross-/Kleinschreibung beachten. Default false.",
            },
            "context_lines": {
                "type": "integer",
                "description": (
                    "Wie viele Zeilen vor/nach dem Treffer mitliefern (Default 0). "
                    "Max 3 — darueber hinaus lieber fs_read mit offset."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Max. Anzahl Treffer. Default 50, Max 500.",
            },
        },
        "required": ["pattern"],
    },
    returns=(
        "{query: {pattern, path, glob, regex, case_sensitive, context_lines}, "
        "matches: [{file, line_number, line, before, after}], "
        "files_searched, files_skipped, truncated}"
    ),
)
def _fs_search(
    *,
    pattern: str,
    path: str = "",
    glob: str | None = None,
    regex: bool = False,
    case_sensitive: bool = False,
    context_lines: int = 0,
    max_results: int = 50,
) -> dict[str, Any]:
    import re as _re

    if not pattern:
        raise ValueError("pattern ist erforderlich.")

    ctx = max(0, min(int(context_lines or 0), 3))
    limit = max(1, min(int(max_results or 50), 500))

    root = _data_root()
    target = _resolve_under_data(path or ".")

    if not target.exists():
        raise ValueError(f"Pfad existiert nicht: {path!r}")
    if not target.is_dir():
        # Auch Einzel-Datei erlauben: Suche nur in dieser Datei
        if not target.is_file():
            raise ValueError(f"Pfad ist weder Ordner noch Datei: {path!r}")

    # Pattern kompilieren
    try:
        if regex:
            flags = 0 if case_sensitive else _re.IGNORECASE
            compiled = _re.compile(pattern, flags)
        else:
            flags = 0 if case_sensitive else _re.IGNORECASE
            compiled = _re.compile(_re.escape(pattern), flags)
    except _re.error as exc:
        raise ValueError(f"Ungueltiges Regex-Pattern: {exc}") from exc

    # Dateien sammeln
    candidates: list[Path] = []
    if target.is_file():
        candidates = [target]
    else:
        # Rekursiv durchgehen, mit Skip-Liste
        for p in target.rglob(glob or "*"):
            if not p.is_file():
                continue
            # Skip-Verzeichnisse ueberspringen (relativ zum target)
            rel_parts = p.relative_to(target).parts
            if any(part in _SEARCH_SKIP_DIRS for part in rel_parts):
                continue
            # Binaerdateien anhand Endung ausschliessen
            if p.suffix.lower() in BINARY_SUFFIXES:
                continue
            # Symlinks nur zulassen, wenn Ziel unter root bleibt
            try:
                resolved = p.resolve(strict=False)
            except (OSError, RuntimeError):
                continue
            if not _is_under(resolved, root):
                continue
            candidates.append(p)

    matches: list[dict[str, Any]] = []
    files_searched = 0
    files_skipped = 0
    truncated = False

    for file_path in candidates:
        if len(matches) >= limit:
            truncated = True
            break
        try:
            stat = file_path.stat()
        except OSError:
            files_skipped += 1
            continue
        if stat.st_size > _SEARCH_MAX_FILE_BYTES:
            files_skipped += 1
            continue

        try:
            with file_path.open("rb") as fh:
                raw = fh.read(_SEARCH_MAX_FILE_BYTES + 1)
        except OSError:
            files_skipped += 1
            continue

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            # Vielleicht latin-1? Im Zweifel fuer echte Binaer-Files skip.
            try:
                text = raw.decode("latin-1")
            except UnicodeDecodeError:
                files_skipped += 1
                continue

        files_searched += 1
        lines = text.splitlines()

        for idx, line in enumerate(lines):
            if not compiled.search(line):
                continue

            entry: dict[str, Any] = {
                "file": str(file_path.relative_to(root)),
                "line_number": idx + 1,
                "line": _truncate(line, _SEARCH_LINE_MAX),
            }
            if ctx > 0:
                before = lines[max(0, idx - ctx): idx]
                after = lines[idx + 1: idx + 1 + ctx]
                entry["before"] = [_truncate(line_b, _SEARCH_LINE_MAX) for line_b in before]
                entry["after"] = [_truncate(line_a, _SEARCH_LINE_MAX) for line_a in after]
            matches.append(entry)

            if len(matches) >= limit:
                truncated = True
                break

    return {
        "query": {
            "pattern": pattern,
            "path": str(target.relative_to(root)) or ".",
            "glob": glob or "",
            "regex": bool(regex),
            "case_sensitive": bool(case_sensitive),
            "context_lines": ctx,
        },
        "matches": matches,
        "files_searched": files_searched,
        "files_skipped": files_skipped,
        "total_matches": len(matches),
        "truncated": truncated,
    }


def _truncate(text: str, maxlen: int) -> str:
    if len(text) <= maxlen:
        return text
    return text[:maxlen] + "…"


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------


def _data_root() -> Path:
    """Kanonischer, aufgeloester Schreibraum-Pfad.

    - Wenn ein Projekt-Kontext aktiv ist (Disco arbeitet im Sandbox-Modus
      eines Threads): der Projekt-Verzeichnis-Pfad.
    - Sonst (kein Projekt-Kontext): der globale Workspace-Root —
      Disco sieht dann alle Projekte (Admin-/CLI-Modus).

    Wird einmal pro Tool-Aufruf bestimmt.
    """
    from ..context import get_project_root  # lazy, vermeidet Zirkular-Imports

    project_root = get_project_root()
    if project_root is not None:
        project_root.mkdir(parents=True, exist_ok=True)
        return project_root.resolve()

    root = settings.data_dir.resolve()
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_under_data(path: str) -> Path:
    """Resolved `path` gegen data_dir; wirft ValueError bei Traversal.

    Mit Unicode-/Pfad-Resolver-Fallback: wenn der direkte Pfad nicht existiert
    und der Pfad relativ ist, wird der PathResolver gefragt ob er eine
    FS-Variante findet (NFC→NFD auf macOS, ' : '-Substitution etc.). Damit
    kann Disco mit kanonischen Pfaden arbeiten, auch wenn das Filesystem
    eine andere Repraesentation speichert (Mac-NFD-Quirk).
    """
    root = _data_root()
    p = Path(path)
    candidate = p if p.is_absolute() else (root / p)
    resolved = candidate.resolve(strict=False)
    if not _is_under(resolved, root):
        raise ValueError(
            f"Pfad ausserhalb von data/ nicht erlaubt: {path!r}"
        )

    # Unicode-/Encoding-Fallback fuer Lese-/Stat-Operationen:
    # Wenn der direkte Pfad nicht existiert, ist er evtl. in der falschen
    # Encoding-Form (Disco gibt canonical NFC, FS speichert NFD auf macOS)
    # oder hat einen OneDrive-Folder-Slash-Quirk. Strategie:
    # 1. Schau in agent_source_locations nach (Hash-zentriertes Modell,
    #    Pipeline-Reform v2): canonical_path → rel_path mapping.
    # 2. Falls (1) nicht hilft: PathResolver versucht NFC/NFD-Varianten.
    if not resolved.exists() and not p.is_absolute():
        # 1. DB-basierter Mapping-Lookup
        scope_prefix = ""
        relative_part = path
        for prefix in ("sources/", "context/"):
            if path.startswith(prefix):
                scope_prefix = prefix
                relative_part = path[len(prefix):]
                break
        try:
            from .data import _connect as db_connect
            conn = db_connect()
            try:
                # Erst neues Modell: agent_source_locations
                has_locations = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='agent_source_locations'"
                ).fetchone() is not None
                if has_locations and relative_part:
                    row = conn.execute(
                        "SELECT rel_path FROM agent_source_locations "
                        "WHERE canonical_path = ? AND status = 'active' LIMIT 1",
                        (relative_part,),
                    ).fetchone()
                    if row and row[0]:
                        mapped = (root / scope_prefix / row[0]).resolve(strict=False)
                        if mapped.exists() and _is_under(mapped, root):
                            return mapped
                # Fallback (alte Bestandsdaten ohne Migration)
                if not has_locations:
                    cols = [c[1] for c in conn.execute("PRAGMA table_info(agent_sources)").fetchall()]
                    if "canonical_path" in cols and relative_part:
                        row = conn.execute(
                            "SELECT rel_path FROM agent_sources "
                            "WHERE canonical_path = ? AND status = 'active' LIMIT 1",
                            (relative_part,),
                        ).fetchone()
                        if row and row[0]:
                            mapped = (root / scope_prefix / row[0]).resolve(strict=False)
                            if mapped.exists() and _is_under(mapped, root):
                                return mapped
            finally:
                conn.close()
        except Exception:
            pass
        # 2. PathResolver-Fallback (NFC/NFD-Permutation)
        from disco.fs.path_resolver import get_resolver
        resolver_path = get_resolver().to_fs_resolved(path, root)
        if resolver_path.exists():
            resolved = resolver_path.resolve(strict=False)
            if not _is_under(resolved, root):
                raise ValueError(
                    f"Pfad ausserhalb von data/ nicht erlaubt: {path!r}"
                )
    return resolved


def _is_under(p: Path, root: Path) -> bool:
    """True, wenn p == root oder p unterhalb root."""
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def _fmt_mtime(epoch: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def _check_writable(target: Path) -> None:
    """Wirft ValueError, wenn die Endung verboten ist."""
    if target.suffix.lower() in FORBIDDEN_WRITE_SUFFIXES:
        raise ValueError(
            f"Endung '{target.suffix}' nicht erlaubt zum Schreiben "
            f"(Schutz fuer DB/Secrets). Erlaubte Beispiele: .md, .csv, .json, "
            f".txt, .xlsx, .png, ..."
        )


# ---------------------------------------------------------------------------
# fs_write (Text)
# ---------------------------------------------------------------------------


@register(
    name="fs_write",
    description=(
        "Schreibt eine Textdatei unter data/. Legt fehlende Ordner automatisch "
        "an. Append=true haengt an eine bestehende Datei an statt zu ueberschreiben. "
        "Fuer Binaerdaten (Excel) bitte build_xlsx_from_tables verwenden. "
        "Kein Zugriff ausserhalb von data/. DB-Dateien/.env sind gesperrt."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad relativ zu data/ (z.B. 'work/report.md').",
            },
            "content": {
                "type": "string",
                "description": "Text-Inhalt. Max 10 MB.",
            },
            "encoding": {
                "type": "string",
                "description": "Zeichenkodierung (Default 'utf-8').",
            },
            "append": {
                "type": "boolean",
                "description": "True = ans Ende anhaengen, False = ueberschreiben (Default).",
            },
        },
        "required": ["path", "content"],
    },
    returns="{path, bytes_written, total_size, mode}",
)
def _fs_write(
    *,
    path: str,
    content: str,
    encoding: str = "utf-8",
    append: bool = False,
) -> dict[str, Any]:
    if not path:
        raise ValueError("path ist erforderlich.")

    target = _resolve_under_data(path)
    _check_writable(target)

    # Ordner anlegen falls fehlt
    target.parent.mkdir(parents=True, exist_ok=True)

    encoded = content.encode(encoding)
    if len(encoded) > MAX_WRITE_BYTES:
        raise ValueError(
            f"Content {len(encoded)} Bytes ueberschreitet Limit {MAX_WRITE_BYTES}."
        )

    mode = "ab" if append else "wb"
    with target.open(mode) as fh:
        fh.write(encoded)

    root = _data_root()
    return {
        "path": str(target.relative_to(root)),
        "bytes_written": len(encoded),
        "total_size": target.stat().st_size,
        "mode": "append" if append else "overwrite",
    }


# ---------------------------------------------------------------------------
# fs_mkdir
# ---------------------------------------------------------------------------


@register(
    name="fs_mkdir",
    description=(
        "Legt einen (ggf. verschachtelten) Ordner unter data/ an. Idempotent: "
        "wenn der Ordner schon existiert, passiert nichts. Kein Zugriff "
        "ausserhalb von data/."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Ordner-Pfad relativ zu data/ (z.B. 'work/analyse-2026-04').",
            },
        },
        "required": ["path"],
    },
    returns="{path, created}",
)
def _fs_mkdir(*, path: str) -> dict[str, Any]:
    if not path:
        raise ValueError("path ist erforderlich.")

    target = _resolve_under_data(path)
    root = _data_root()
    created = not target.exists()
    target.mkdir(parents=True, exist_ok=True)

    return {
        "path": str(target.relative_to(root)),
        "created": created,
    }


# ---------------------------------------------------------------------------
# fs_delete
# ---------------------------------------------------------------------------


@register(
    name="fs_delete",
    description=(
        "Loescht eine Datei oder einen LEEREN Ordner unter data/. "
        "Rekursives Loeschen ist NICHT moeglich (Sicherheit) — loesche die Dateien "
        "einzeln oder melde dem Benutzer, dass Du einen ganzen Baum loeschen willst."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad relativ zu data/.",
            },
        },
        "required": ["path"],
    },
    returns="{path, kind, existed}",
)
def _fs_delete(*, path: str) -> dict[str, Any]:
    if not path:
        raise ValueError("path ist erforderlich.")

    target = _resolve_under_data(path)
    root = _data_root()

    # Sicherheit: Root und Top-Level-Standard-Ordner nicht loeschen
    if target == root:
        raise ValueError("Root-Ordner data/ kann nicht geloescht werden.")

    if not target.exists():
        return {
            "path": str(target.relative_to(root)),
            "kind": "missing",
            "existed": False,
        }

    if target.is_file():
        target.unlink()
        return {
            "path": str(target.relative_to(root)),
            "kind": "file",
            "existed": True,
        }

    if target.is_dir():
        try:
            target.rmdir()  # wirft OSError wenn nicht leer
        except OSError as exc:
            raise ValueError(
                f"Ordner '{path}' ist nicht leer — rekursives Loeschen "
                f"bewusst deaktiviert. Erst Dateien einzeln entfernen. ({exc})"
            ) from exc
        return {
            "path": str(target.relative_to(root)),
            "kind": "dir",
            "existed": True,
        }

    raise ValueError(f"Unbekannter Pfadtyp: {path!r}")
