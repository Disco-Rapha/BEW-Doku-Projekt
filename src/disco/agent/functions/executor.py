"""Lokale Python-Ausfuehrung fuer Disco — Skripte schreiben, ausfuehren, debuggen.

Kern-Pattern: Der Agent (GPT-5 in Azure) hat keinen lokalen Filesystem-
Zugriff. Aber er kann ueber dieses Tool Python-Skripte auf dem Host
ausfuehren — genau wie Claude Code seinen Bash-Tool nutzt.

Architektur:
  - Das Tool startet einen subprocess.run() mit dem Python-Interpreter
    aus dem venv.
  - Working-Directory ist das Projekt-Root (ueber den Sandbox-Kontext).
  - stdout/stderr werden captured und (gekappt) zurueckgegeben.
  - Jede Ausfuehrung wird in agent_script_runs protokolliert.

Sicherheit:
  - Nur .py-Dateien (kein Shell-Exec, kein Bash, kein eval).
  - Path-Traversal-Schutz: Skript muss unter dem Projekt-Root liegen.
  - Environment wird gefiltert: FOUNDRY_API_KEY, AZURE_OPENAI_KEY etc.
    werden NICHT an den Subprocess weitergegeben.
  - Timeout hart enforced via subprocess.run(timeout=...).
  - stdout/stderr gekappt bei 50 KB fuer das Tool-Result (volle Laenge
    steht in stdout_bytes/stderr_bytes).

Zwei Modi:
  - path="work/scripts/foo.py"  → file-basiert (persistent, debugbar)
  - code="print('hello')"       → inline (temporaer, fuer Quick-Checks)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from . import register
from .data import _connect as db_connect
from .fs import _data_root


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_S = 300          # 5 Minuten
MAX_TIMEOUT_S = 1800             # 30 Minuten
STDOUT_CAPTURE_LIMIT = 50_000    # 50 KB — mehr wird gekappt im Tool-Result
STDERR_CAPTURE_LIMIT = 50_000
DB_PREVIEW_LIMIT = 2_000         # fuer die DB-Audit-Tabelle kuerzere Vorschau

# Umgebungsvariablen, die NICHT an den Subprocess weitergegeben werden.
# Schutz: selbst wenn Disco ein Skript schreibt das os.environ liest,
# bekommt es keine API-Keys zu sehen.
ENV_BLOCKLIST_PREFIXES = (
    "FOUNDRY_",
    "AZURE_OPENAI_",
    "AZURE_DOC_INTEL_",
    "ANTHROPIC_",
    "OPENAI_",
    "MSAL_",
)


def _python_executable() -> str:
    """Python-Interpreter aus dem aktuellen venv."""
    return sys.executable


def _filtered_env() -> dict[str, str]:
    """Umgebung ohne API-Keys / Secrets."""
    return {
        k: v
        for k, v in os.environ.items()
        if not any(k.startswith(prefix) for prefix in ENV_BLOCKLIST_PREFIXES)
    }


def _resolve_script_path(root: Path, path: str) -> Path:
    """Resolved + validiert einen Skript-Pfad unter dem Projekt-Root."""
    if not path:
        raise ValueError("path ist erforderlich (oder code= fuer Inline).")
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError(f"Skript-Pfad ausserhalb des Projekts: {path!r}")
    if not candidate.exists():
        raise ValueError(f"Skript nicht gefunden: {path!r}")
    if not candidate.is_file():
        raise ValueError(f"Pfad ist keine Datei: {path!r}")
    if candidate.suffix.lower() != ".py":
        raise ValueError(
            f"Nur .py-Dateien erlaubt, nicht '{candidate.suffix}'. "
            f"Sicherheitsrestriktion."
        )
    return candidate


def _log_run(
    conn,
    script_path: str | None,
    inline_hash: str | None,
    mode: str,
    args: list[str] | None,
    exit_code: int | None,
    duration_s: float,
    stdout_full: str,
    stderr_full: str,
    error: str | None,
    triggered_by: str,
) -> int:
    """Schreibt einen Eintrag in agent_script_runs. Gibt die Run-ID zurueck."""
    truncated = (
        len(stdout_full) > DB_PREVIEW_LIMIT
        or len(stderr_full) > DB_PREVIEW_LIMIT
    )
    cur = conn.execute(
        """
        INSERT INTO agent_script_runs
            (script_path, inline_hash, mode, args, exit_code, duration_s,
             stdout_preview, stderr_preview, stdout_bytes, stderr_bytes,
             truncated, error, triggered_by, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            script_path,
            inline_hash,
            mode,
            json.dumps(args) if args else None,
            exit_code,
            round(duration_s, 3),
            stdout_full[:DB_PREVIEW_LIMIT],
            stderr_full[:DB_PREVIEW_LIMIT],
            len(stdout_full.encode("utf-8", errors="replace")),
            len(stderr_full.encode("utf-8", errors="replace")),
            1 if truncated else 0,
            error,
            triggered_by,
        ),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# run_python — das Tool
# ---------------------------------------------------------------------------


@register(
    name="run_python",
    description=(
        "Fuehrt ein Python-Skript LOKAL auf dem Host-Rechner aus. Zwei Modi:\n"
        "\n"
        "File-basiert (empfohlen, persistent, debugbar):\n"
        "  1) Schreibe das Skript per fs_write nach .disco/scripts/<name>.py\n"
        "  2) run_python(path='.disco/scripts/<name>.py')\n"
        "  3) Bei Fehler: fs_read, fix, fs_write, erneut run_python\n"
        "\n"
        "Inline (fuer Einzeiler / Quick-Checks):\n"
        "  run_python(code='import os; print(len(os.listdir(\"sources/\")))')\n"
        "\n"
        "Das Skript laeuft im Projekt-Verzeichnis als Working Directory.\n"
        "Es hat Zugriff auf sources/, context/, exports/, datastore.db, workspace.db.\n"
        "Alle installierten Python-Packages sind verfuegbar (openpyxl, ezdxf, etc.).\n"
        "API-Keys sind NICHT im Environment (Sicherheit).\n"
        "\n"
        "PDF-Lesen NICHT direkt: pypdf ist zwar installiert, aber Disco nutzt\n"
        "fuer PDF-Inhalt ausschliesslich `doc_markdown_read` — das liest die\n"
        "sauberen Azure-DI-Markdowns aus `agent_doc_markdown` (gleiche Pipeline\n"
        "wie auch der FTS-Indexer und die Web-UI). Direkter pypdf-Aufruf fuehrt\n"
        "zu CID-Encoding-Schrott und umgeht die Provenance-Spur.\n"
        "\n"
        "WANN NUTZEN:\n"
        "- Dateien > 1 MB verarbeiten (XML, CSV, PDF-Bulk)\n"
        "- Bulk-Operationen ueber viele Dateien (hash, parse, konvertiere)\n"
        "- Komplexe Transformationen die im Code Interpreter keinen FS-Zugriff haetten\n"
        "- Wiederverwendbare Skripte fuer wiederkehrende Aufgaben\n"
        "\n"
        "WANN NICHT NUTZEN:\n"
        "- Einfache SQL-Abfragen → sqlite_query\n"
        "- Kleine Dateien lesen → fs_read\n"
        "- Excel-Export → build_xlsx_from_tables\n"
        "- Berechnungen ohne FS → Code Interpreter"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Pfad zum .py-Skript, relativ zum Projekt-Root. "
                    "Typisch: '.disco/scripts/<name>.py'. "
                    "Mutually exclusive mit 'code'."
                ),
            },
            "code": {
                "type": "string",
                "description": (
                    "Python-Code als String (fuer Inline-Ausfuehrung). "
                    "Wird in temporaere Datei geschrieben und ausgefuehrt. "
                    "Mutually exclusive mit 'path'."
                ),
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optionale CLI-Argumente fuer das Skript (sys.argv).",
            },
            "timeout": {
                "type": "integer",
                "description": (
                    f"Timeout in Sekunden (Default {DEFAULT_TIMEOUT_S}, "
                    f"Max {MAX_TIMEOUT_S})."
                ),
            },
        },
        "required": [],
    },
    returns=(
        "{run_id, mode, script_path, exit_code, duration_s, "
        "stdout, stderr, truncated_stdout, truncated_stderr, "
        "hint}"
    ),
)
def _run_python(
    *,
    path: str | None = None,
    code: str | None = None,
    args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    if not path and not code:
        raise ValueError(
            "Entweder 'path' (Skript-Datei) oder 'code' (Inline-Python) "
            "ist erforderlich."
        )
    if path and code:
        raise ValueError(
            "Nur 'path' ODER 'code' angeben, nicht beides."
        )

    root = _data_root()
    timeout = max(5, min(int(timeout or DEFAULT_TIMEOUT_S), MAX_TIMEOUT_S))
    cli_args = list(args or [])

    # --- Modus bestimmen ---
    tmp_script: Path | None = None
    inline_hash: str | None = None

    if path:
        mode = "file"
        script_abs = _resolve_script_path(root, path)
        script_display = path
    else:
        mode = "inline"
        script_display = "(inline)"
        inline_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
        # Temporaere Datei in .disco/tmp/
        tmp_dir = root / ".disco" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_script = tmp_dir / f"inline_{inline_hash}.py"
        tmp_script.write_text(code, encoding="utf-8")
        script_abs = tmp_script

    # --- Subprocess ausfuehren ---
    python = _python_executable()
    cmd = [python, str(script_abs)] + cli_args
    env = _filtered_env()

    t_start = time.monotonic()
    exit_code: int | None = None
    stdout_full = ""
    stderr_full = ""
    error: str | None = None

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(root),
            env=env,
            timeout=timeout,
        )
        exit_code = result.returncode
        stdout_full = result.stdout or ""
        stderr_full = result.stderr or ""
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        stdout_full = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr_full = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        error = f"Timeout nach {timeout}s"
        logger.warning("run_python timeout: %s (%ds)", script_display, timeout)
    except OSError as exc:
        exit_code = None
        error = f"OS-Fehler: {exc}"
        logger.error("run_python OS-Fehler: %s — %s", script_display, exc)
    except Exception as exc:
        exit_code = None
        error = f"Unerwarteter Fehler: {exc}"
        logger.exception("run_python unerwarteter Fehler: %s", script_display)

    duration = time.monotonic() - t_start

    # --- Inline-Temp aufräumen (nur bei Erfolg; bei Fehler behalten zum Debuggen) ---
    if tmp_script and exit_code == 0:
        try:
            tmp_script.unlink(missing_ok=True)
        except OSError:
            pass

    # --- Audit-Log in DB ---
    run_id = None
    try:
        conn = db_connect()
        try:
            # Pruefen ob agent_script_runs existiert (Migration 003)
            has_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_script_runs'"
            ).fetchone()
            if has_table:
                run_id = _log_run(
                    conn,
                    script_path=path,
                    inline_hash=inline_hash,
                    mode=mode,
                    args=cli_args or None,
                    exit_code=exit_code,
                    duration_s=duration,
                    stdout_full=stdout_full,
                    stderr_full=stderr_full,
                    error=error,
                    triggered_by="agent",
                )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("run_python: Audit-Log fehlgeschlagen: %s", exc)

    # --- Tool-Result zusammenbauen ---
    truncated_stdout = len(stdout_full) > STDOUT_CAPTURE_LIMIT
    truncated_stderr = len(stderr_full) > STDERR_CAPTURE_LIMIT

    out: dict[str, Any] = {
        "run_id": run_id,
        "mode": mode,
        "script_path": script_display,
        "exit_code": exit_code,
        "duration_s": round(duration, 2),
        "stdout": stdout_full[:STDOUT_CAPTURE_LIMIT],
        "stderr": stderr_full[:STDERR_CAPTURE_LIMIT],
        "truncated_stdout": truncated_stdout,
        "truncated_stderr": truncated_stderr,
    }
    if stdout_full and truncated_stdout:
        out["stdout_total_bytes"] = len(stdout_full.encode("utf-8", errors="replace"))
    if stderr_full and truncated_stderr:
        out["stderr_total_bytes"] = len(stderr_full.encode("utf-8", errors="replace"))
    if error:
        out["error"] = error

    # Hint fuer den Agent — kontextabhaengig
    if exit_code == 0:
        out["hint"] = (
            "Skript erfolgreich. Ergebnisse stehen in stdout und/oder in der "
            "Projekt-DB (workspace.db fuer Reasoning-Ergebnisse, datastore.db "
            "fuer Registry/Content). Falls das Skript DB-Tabellen beschrieben "
            "hat, kannst Du sie per sqlite_query abfragen."
        )
    elif exit_code is not None and exit_code > 0:
        out["hint"] = (
            "Skript ist fehlgeschlagen. Lies stderr fuer den Traceback. "
            "Typischer Debug-Loop: fs_read des Skripts → Fehler fixen → "
            "fs_write mit Korrektur → nochmal run_python."
        )
    elif error and "Timeout" in error:
        out["hint"] = (
            f"Timeout nach {timeout}s. Moegliche Abhilfe: "
            "Daten vorher filtern/reduzieren, oder timeout= erhoehen "
            f"(max {MAX_TIMEOUT_S}s)."
        )

    return out
