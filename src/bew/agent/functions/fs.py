"""Dateisystem-Tools: streng auf settings.data_dir beschraenkt.

Sicherheits-Design:
  - Alle Pfade werden gegen `settings.data_dir` resolved und muessen
    **unterhalb** davon liegen (Path-Traversal-Schutz).
  - Relative Pfade sind bequem; absolute Pfade werden akzeptiert, aber nur,
    wenn sie unter `data_dir` liegen.
  - Symlinks werden aufgeloest; zielt der Symlink aus `data_dir` heraus,
    wird er abgelehnt.
  - `fs_read` liefert NUR Text. Binaerdateien (PDFs, Bilder, Excel) werden
    erkannt und mit einem klaren Hinweis abgelehnt — dafuer gibt es
    `pdf_extract_text` und spaeter weitere Extraktoren.
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

DEFAULT_LIST_LIMIT = 500
MAX_LIST_LIMIT = 5000

DEFAULT_READ_BYTES = 200_000      # 200 KB
MAX_READ_BYTES = 2_000_000        # 2 MB Text — Schutz vor Kontext-Explosion
MAX_READ_BYTES_BINARY = 5_000_000 # 5 MB Binaer (base64-Output ist ~33% groesser)

# Schreib-Limits (Agent soll eher viele kleine Files anlegen als wenige riesige)
MAX_WRITE_BYTES = 10_000_000      # 10 MB

# Endungen, die der Agent NIEMALS schreiben darf — Schutz vor versehentlicher
# DB/Secret-Ueberschreibung
FORBIDDEN_WRITE_SUFFIXES = {".db", ".db-wal", ".db-shm", ".sqlite", ".env"}

# Heuristik: diese Suffixe sind fuer fs_read verboten, weil binaer.
# Fuer PDFs existiert pdf_extract_text; fuer Excel/Images gibt es
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
        },
        "required": [],
    },
    returns="{root, path, entries: [{name, type, size, modified, rel_path}], total, truncated}",
)
def _fs_list(
    *,
    path: str = "",
    recursive: bool = False,
    pattern: str | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
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
    for p in it:
        total_seen += 1
        if len(entries) >= effective_limit:
            continue  # weiterzaehlen fuer total, aber nicht mehr sammeln

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

        entries.append(
            {
                "name": p.name,
                "type": "dir" if p.is_dir() else "file",
                "size": stat.st_size if p.is_file() else None,
                "modified": _fmt_mtime(stat.st_mtime),
                "rel_path": str(p.relative_to(root)),
            }
        )

    # Sort: Ordner zuerst, dann alphabetisch
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))

    return {
        "root": str(root),
        "path": str(target.relative_to(root)) or ".",
        "entries": entries,
        "total": total_seen,
        "truncated": total_seen > len(entries),
    }


# ---------------------------------------------------------------------------
# fs_read
# ---------------------------------------------------------------------------


@register(
    name="fs_read",
    description=(
        "Liest eine Textdatei unter data/. Fuer PDFs bitte pdf_extract_text "
        "verwenden. Bei zu grossen Dateien wird der Inhalt auf max_bytes "
        "gekuerzt (truncated=true). Kein Zugriff ausserhalb von data/."
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
                "description": f"Max. Bytes, die gelesen werden (Default {DEFAULT_READ_BYTES}, Max {MAX_READ_BYTES}).",
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
            f"Fuer PDFs pdf_extract_text verwenden."
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
# Helfer
# ---------------------------------------------------------------------------


def _data_root() -> Path:
    """Kanonischer, aufgeloester data-Pfad. Wird einmal pro Call bestimmt."""
    root = settings.data_dir.resolve()
    if not root.exists():
        # Zur Sicherheit anlegen — sollte normalerweise durch bew db init
        # schon passieren, aber wir brechen nicht wegen eines fehlenden
        # Ordners ab.
        root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_under_data(path: str) -> Path:
    """Resolved `path` gegen data_dir; wirft ValueError bei Traversal."""
    root = _data_root()
    p = Path(path)
    candidate = p if p.is_absolute() else (root / p)
    resolved = candidate.resolve(strict=False)
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
# fs_read_bytes (Binaer als base64)
# ---------------------------------------------------------------------------


@register(
    name="fs_read_bytes",
    description=(
        "Liest eine BINAERE Datei (Excel, PDF, PNG, ZIP, etc.) unter data/ und "
        "gibt sie base64-kodiert zurueck. Genau dafuer gedacht, um Excel-/Bild-/"
        "PDF-Inhalte in den Code Interpreter zu uebergeben: dort dann "
        "`base64.b64decode(content_base64)` aufrufen und z.B. nach /tmp/x.xlsx "
        "schreiben. Der Code-Interpreter-Sandbox hat KEINEN direkten Zugriff "
        "auf data/, dieser Tool-Call ist die Bruecke. "
        "Limit: 5 MB pro Datei (groesser bitte aufteilen oder Worker-Job)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad relativ zu data/ (z.B. 'raw/ibl-reference/kks_lagerhalle.xlsx').",
            },
            "max_bytes": {
                "type": "integer",
                "description": f"Max. Bytes (Default {DEFAULT_READ_BYTES}, Hard-Max {MAX_READ_BYTES_BINARY}).",
            },
        },
        "required": ["path"],
    },
    returns="{path, content_base64, bytes_read, size_bytes, truncated}",
)
def _fs_read_bytes(
    *,
    path: str,
    max_bytes: int = DEFAULT_READ_BYTES,
) -> dict[str, Any]:
    import base64

    if not path:
        raise ValueError("path ist erforderlich.")

    target = _resolve_under_data(path)
    if not target.exists():
        raise ValueError(f"Datei nicht gefunden: {path!r}")
    if not target.is_file():
        raise ValueError(f"Pfad ist keine Datei: {path!r}")

    effective_max = max(1, min(int(max_bytes or DEFAULT_READ_BYTES), MAX_READ_BYTES_BINARY))
    size = target.stat().st_size

    try:
        with target.open("rb") as fh:
            raw = fh.read(effective_max + 1)
    except OSError as exc:
        raise ValueError(f"Lesefehler: {exc}") from exc

    truncated = len(raw) > effective_max
    if truncated:
        raw = raw[:effective_max]

    return {
        "path": str(target.relative_to(_data_root())),
        "content_base64": base64.b64encode(raw).decode("ascii"),
        "bytes_read": len(raw),
        "size_bytes": size,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# fs_write (Text)
# ---------------------------------------------------------------------------


@register(
    name="fs_write",
    description=(
        "Schreibt eine Textdatei unter data/. Legt fehlende Ordner automatisch "
        "an. Append=true haengt an eine bestehende Datei an statt zu ueberschreiben. "
        "Fuer Binaerdaten (Excel, PNG) bitte fs_write_bytes mit base64 verwenden. "
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
# fs_write_bytes (Binaer via base64)
# ---------------------------------------------------------------------------


@register(
    name="fs_write_bytes",
    description=(
        "Schreibt eine Binaerdatei (Excel, PNG, PDF, ...) unter data/ aus einem "
        "base64-kodierten Content-String. Typischer Use-Case: der Code Interpreter "
        "erzeugt ein xlsx im Sandbox-Filesystem, liest es als bytes, encoded es "
        "per base64 und schickt es hier rein — so landet es auf dem Host unter "
        "data/exports/. DB-Dateien/.env gesperrt."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Pfad relativ zu data/ (z.B. 'exports/report_2026-04-16.xlsx').",
            },
            "content_base64": {
                "type": "string",
                "description": "Datei-Inhalt base64-kodiert.",
            },
        },
        "required": ["path", "content_base64"],
    },
    returns="{path, bytes_written, total_size}",
)
def _fs_write_bytes(*, path: str, content_base64: str) -> dict[str, Any]:
    import base64

    if not path:
        raise ValueError("path ist erforderlich.")

    target = _resolve_under_data(path)
    _check_writable(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        raw = base64.b64decode(content_base64, validate=False)
    except Exception as exc:
        raise ValueError(f"base64-Decoding fehlgeschlagen: {exc}") from exc

    if len(raw) > MAX_WRITE_BYTES:
        raise ValueError(
            f"Decoded content {len(raw)} Bytes ueberschreitet Limit {MAX_WRITE_BYTES}."
        )

    with target.open("wb") as fh:
        fh.write(raw)

    root = _data_root()
    return {
        "path": str(target.relative_to(root)),
        "bytes_written": len(raw),
        "total_size": target.stat().st_size,
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
