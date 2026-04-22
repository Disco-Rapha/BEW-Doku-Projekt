"""Runner-Host — laedt `flows/<flow_name>/runner.py` im Kontext eines Runs.

Dieser Host ist das Bindeglied zwischen:
  - **dem Service** (`service.py`), der einen Run in der DB anlegt und
    einen Subprocess startet; und
  - **dem User-Runner** (`flows/<name>/runner.py`), der die eigentliche
    Arbeit macht.

Aufruf (vom Service via subprocess.Popen, detached):

    python -m disco.flows.runner_host <run_id> --project-root <path>

Was der Host garantiert:

  - Working-Directory ist der Projekt-Root.
  - Environment `DISCO_FLOW_*` ist gesetzt, damit `FlowRun.from_env()`
    funktioniert.
  - Am Ende ist der Run-Status **immer** ein Endstatus (done/failed/
    paused/cancelled) — nie bleibt ein Run auf 'running' haengen, wenn
    der Prozess normal endet.
  - Exceptions aus dem User-Runner werden mit Traceback in
    `agent_flow_runs.error` festgehalten.

Was der Host **nicht** tut:
  - Er filtert keine API-Keys aus der Umgebung. Flows sind explizite
    Akte — der Flow-Autor muss ggf. Azure-/OpenAI-Keys erreichen. (Das
    ist der Unterschied zu `run_python`, das Keys bewusst blockiert.)
  - Er erzwingt keinen Timeout auf den Run selbst — ein 10h-Flow ist
    erlaubt. Pro-Item-Timeouts implementiert das SDK (nicht der Host).

Credentials und .env:
  Der Host ruft beim Start `load_dotenv(REPO_ROOT/.env)` auf, damit
  Runner-Autoren sowohl `os.getenv('AZURE_DOC_INTEL_ENDPOINT')` als
  auch `from disco.config import settings` nutzen koennen. Ohne diesen
  Schritt wuerden die Keys nur in der Pydantic-Settings-Instanz liegen,
  der Subprocess `os.environ` aber leer bleiben (siehe UAT-Bug #5).
"""

from __future__ import annotations

import argparse
import logging
import os
import runpy
import sqlite3
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv

from disco.config import REPO_ROOT
from disco.flows.sdk import (
    ENV_FLOW_DIR,
    ENV_PROJECT_DB,
    ENV_PROJECT_ROOT,
    ENV_RUN_ID,
    FlowStopped,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PAUSED,
)

# .env aus dem Code-Repo in os.environ laden. Subprocess erbt os.environ nicht
# automatisch mit den Pydantic-Settings — Runner-Autoren sollen aber ohne
# Gedanken an Framework-Details `os.getenv(...)` oder `settings.*` nutzen
# koennen.
load_dotenv(REPO_ROOT / ".env")


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB-Helfer (eigene Verbindung, unabhaengig vom SDK)
# ---------------------------------------------------------------------------


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def _fetch_flow_name(db_path: Path, run_id: int) -> tuple[str, str]:
    """Liest (flow_name, status) aus agent_flow_runs."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT flow_name, status FROM agent_flow_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Run {run_id} nicht in agent_flow_runs gefunden.")
        return row[0], row[1]
    finally:
        conn.close()


def _set_status(
    db_path: Path,
    run_id: int,
    status: str,
    *,
    error: str | None = None,
    only_if_running: bool = False,
) -> None:
    """Setzt den Endstatus. Mit only_if_running wird der Update nur
    durchgefuehrt, wenn der aktuelle Status 'running' ist — damit man
    einen vom SDK bereits gesetzten Endstatus nicht ueberschreibt.
    """
    conn = _connect(db_path)
    try:
        sql = """
            UPDATE agent_flow_runs
               SET status = ?,
                   error = COALESCE(?, error),
                   finished_at = datetime('now')
             WHERE id = ?
        """
        params: tuple = (status, error, run_id)
        if only_if_running:
            sql += " AND status = 'running'"
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Haupt-Entry
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="disco.flows.runner_host",
        description="Fuehrt einen Flow-Run aus, indem das User-runner.py geladen wird.",
    )
    parser.add_argument("run_id", type=int, help="ID aus agent_flow_runs.")
    parser.add_argument(
        "--project-root",
        required=True,
        help="Absoluter Pfad zum Projekt-Verzeichnis.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(
            f"FEHLER: Projekt-Root existiert nicht: {project_root}",
            file=sys.stderr,
        )
        return 2

    db_path = project_root / "data.db"
    if not db_path.exists():
        print(
            f"FEHLER: Projekt-DB fehlt: {db_path}",
            file=sys.stderr,
        )
        return 2

    run_id = args.run_id

    # -------------------------------------------------------------------
    # 1) Run-Metadaten pruefen
    # -------------------------------------------------------------------
    try:
        flow_name, status = _fetch_flow_name(db_path, run_id)
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2

    if status in (STATUS_DONE, STATUS_CANCELLED, STATUS_FAILED):
        print(
            f"FEHLER: Run {run_id} ist bereits abgeschlossen (status={status}).",
            file=sys.stderr,
        )
        return 2

    # -------------------------------------------------------------------
    # 2) User-Runner-Pfad aufloesen: Projekt-lokal gewinnt, Library als
    #    Fallback. Dadurch sind Library-Flows in jedem Projekt verfuegbar,
    #    ohne dass Projekt-Ordner existieren muessen.
    # -------------------------------------------------------------------
    from disco.flows.service import resolve_flow_dir

    flow_dir = resolve_flow_dir(project_root, flow_name)
    if flow_dir is None:
        local = project_root / "flows" / flow_name
        msg = (
            f"runner.py nicht gefunden: weder projekt-lokal ({local}) "
            f"noch in der Flow-Library. Flow '{flow_name}' existiert nicht."
        )
        _set_status(db_path, run_id, STATUS_FAILED, error=msg)
        print(f"FEHLER: {msg}", file=sys.stderr)
        return 2
    user_runner = flow_dir / "runner.py"

    # -------------------------------------------------------------------
    # 3) Umgebung fuer FlowRun.from_env() vorbereiten
    # -------------------------------------------------------------------
    os.environ[ENV_RUN_ID] = str(run_id)
    os.environ[ENV_PROJECT_ROOT] = str(project_root)
    os.environ[ENV_PROJECT_DB] = str(db_path)
    os.environ[ENV_FLOW_DIR] = str(flow_dir)

    # Working Directory auf Projekt-Root (wie bei run_python)
    try:
        os.chdir(project_root)
    except OSError as exc:
        msg = f"chdir({project_root}) fehlgeschlagen: {exc}"
        _set_status(db_path, run_id, STATUS_FAILED, error=msg)
        print(f"FEHLER: {msg}", file=sys.stderr)
        return 2

    # sys.path so, dass der Flow-Ordner eigene Module mitbringen kann
    if str(flow_dir) not in sys.path:
        sys.path.insert(0, str(flow_dir))

    print(
        f"runner_host: starte Flow '{flow_name}' als Run {run_id} "
        f"(pid={os.getpid()}, cwd={project_root})",
        file=sys.stderr,
    )

    # -------------------------------------------------------------------
    # 4) User-Runner ausfuehren — mit konsistentem Status-Handling
    # -------------------------------------------------------------------
    try:
        runpy.run_path(str(user_runner), run_name="__main__")

    except FlowStopped as stopped:
        reason = str(stopped) or "stopped"
        final = STATUS_CANCELLED if "cancel" in reason else STATUS_PAUSED
        _set_status(db_path, run_id, final, error=None, only_if_running=True)
        print(
            f"runner_host: Flow pausiert/abgebrochen ({reason}) → status={final}",
            file=sys.stderr,
        )
        return 0  # ordentlicher Abbruch ist KEIN Fehler

    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code == 0:
            _set_status(db_path, run_id, STATUS_DONE, only_if_running=True)
            return 0
        err = f"runner.py rief sys.exit({code})"
        _set_status(db_path, run_id, STATUS_FAILED, error=err)
        print(f"runner_host: {err}", file=sys.stderr)
        return code

    except BaseException as exc:
        err = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        _set_status(db_path, run_id, STATUS_FAILED, error=err)
        print(f"runner_host: UNBEHANDELTE EXCEPTION — {exc}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return 1

    # -------------------------------------------------------------------
    # 5) Normales Ende — Status 'done' setzen, wenn der User-Runner
    #    ihn nicht schon selbst gesetzt hat.
    # -------------------------------------------------------------------
    _set_status(db_path, run_id, STATUS_DONE, only_if_running=True)
    print(
        f"runner_host: Flow '{flow_name}' Run {run_id} beendet.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
