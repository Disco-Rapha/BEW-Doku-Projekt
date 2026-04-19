"""Flow-Service — Business-Logik fuer CLI und (spaeter) Agent.

Diese Schicht vermittelt zwischen externen Aufrufern (CLI, Agent-Tools,
WebSocket-UI) und den beiden Grund-Artefakten eines Flows:

  - **Filesystem**: `<projekt>/flows/<flow_name>/README.md` und
    `runner.py`.
  - **Datenbank**: `agent_flow_runs` und `agent_flow_run_items`.

Das Service kennt die Datenmodelle, validiert Eingaben und kuemmert sich
um Subprocess-Start und Signal-Handling (`pause_requested`,
`cancel_requested`). Es ruft **nicht** direkt `runner_host`, sondern
startet ihn als detachten Subprocess — damit der aufrufende CLI-Call
(oder spaeter der WebSocket-Handler) nicht blockiert.
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


FLOWS_SUBDIR = "flows"
README_FILENAME = "README.md"
RUNNER_FILENAME = "runner.py"

_FLOW_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


# ===========================================================================
# Datenmodelle
# ===========================================================================


@dataclass
class FlowInfo:
    """Beschreibung eines Flow-Ordners (ohne Laufzeit-Info)."""
    name: str
    path: Path
    has_runner: bool
    has_readme: bool
    readme_excerpt: str | None   # erster Absatz der README, fuer die UI
    last_modified: str | None    # ISO-Timestamp der neuesten Datei
    run_count: int               # Anzahl bisheriger Runs in der DB


@dataclass
class RunInfo:
    """Laufzeit-Info eines einzelnen Runs."""
    id: int
    flow_name: str
    title: str | None
    status: str
    worker_pid: int | None
    config: dict[str, Any]
    total_items: int
    done_items: int
    failed_items: int
    skipped_items: int
    total_cost_eur: float
    total_tokens_in: int
    total_tokens_out: int
    pause_requested: bool
    cancel_requested: bool
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


# ===========================================================================
# Helfer
# ===========================================================================


def _validate_flow_name(name: str) -> str:
    if not _FLOW_NAME_RE.match(name or ""):
        raise ValueError(
            f"Ungueltiger Flow-Name {name!r}. "
            f"Erlaubt: a-z, 0-9, '-', '_', max 63 Zeichen, "
            f"muss mit Buchstabe/Zahl beginnen."
        )
    return name


def _flows_dir(project_root: Path) -> Path:
    return project_root / FLOWS_SUBDIR


def _flow_dir(project_root: Path, flow_name: str) -> Path:
    _validate_flow_name(flow_name)
    return _flows_dir(project_root) / flow_name


def _connect(db_path: Path):
    import sqlite3
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_runinfo(row) -> RunInfo:
    try:
        config = json.loads(row["config_json"]) if row["config_json"] else {}
    except (json.JSONDecodeError, TypeError):
        config = {}
    return RunInfo(
        id=row["id"],
        flow_name=row["flow_name"],
        title=row["title"],
        status=row["status"],
        worker_pid=row["worker_pid"],
        config=config,
        total_items=row["total_items"],
        done_items=row["done_items"],
        failed_items=row["failed_items"],
        skipped_items=row["skipped_items"],
        total_cost_eur=float(row["total_cost_eur"]),
        total_tokens_in=row["total_tokens_in"],
        total_tokens_out=row["total_tokens_out"],
        pause_requested=bool(row["pause_requested"]),
        cancel_requested=bool(row["cancel_requested"]),
        error=row["error"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


# ===========================================================================
# Flow-Listing
# ===========================================================================


def list_flows(project_root: Path) -> list[FlowInfo]:
    """Listet alle Unterordner in `<projekt>/flows/` als FlowInfo auf.

    Gibt auch unvollstaendige Flows zurueck (ohne runner.py oder README),
    damit die UI anzeigen kann, was fehlt.
    """
    flows_dir = _flows_dir(project_root)
    if not flows_dir.is_dir():
        return []

    db_path = project_root / "data.db"
    run_counts: dict[str, int] = {}
    if db_path.exists():
        conn = _connect(db_path)
        try:
            for row in conn.execute(
                "SELECT flow_name, COUNT(*) AS n FROM agent_flow_runs GROUP BY flow_name"
            ):
                run_counts[row["flow_name"]] = row["n"]
        except Exception as exc:
            logger.warning("Konnte run_counts nicht laden: %s", exc)
        finally:
            conn.close()

    out: list[FlowInfo] = []
    for p in sorted(flows_dir.iterdir()):
        if not p.is_dir():
            continue
        name = p.name
        # Validierung der Namen — ungueltige Ordner stillschweigend skippen
        if not _FLOW_NAME_RE.match(name):
            continue
        runner = p / RUNNER_FILENAME
        readme = p / README_FILENAME
        excerpt = None
        last_mod = None
        if readme.exists():
            try:
                txt = readme.read_text(encoding="utf-8", errors="replace")
                excerpt = _first_paragraph(txt)
            except OSError:
                pass
        try:
            mtimes = [q.stat().st_mtime for q in p.rglob("*") if q.is_file()]
            if mtimes:
                from datetime import datetime
                last_mod = datetime.fromtimestamp(max(mtimes)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
        except OSError:
            pass
        out.append(
            FlowInfo(
                name=name,
                path=p,
                has_runner=runner.is_file(),
                has_readme=readme.is_file(),
                readme_excerpt=excerpt,
                last_modified=last_mod,
                run_count=run_counts.get(name, 0),
            )
        )
    return out


def _first_paragraph(markdown: str, max_chars: int = 400) -> str:
    """Erster nicht-leerer Paragraph einer README (ohne H1-Ueberschrift)."""
    lines = markdown.splitlines()
    # H1 ueberspringen
    idx = 0
    while idx < len(lines) and (not lines[idx].strip() or lines[idx].lstrip().startswith("#")):
        idx += 1
    paragraph_lines: list[str] = []
    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            if paragraph_lines:
                break
        else:
            paragraph_lines.append(line.strip())
        idx += 1
    text = " ".join(paragraph_lines)
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text


def get_flow(project_root: Path, flow_name: str) -> FlowInfo:
    """Detail-Info zu einem Flow. Wirft KeyError wenn der Ordner nicht existiert."""
    _validate_flow_name(flow_name)
    for info in list_flows(project_root):
        if info.name == flow_name:
            return info
    raise KeyError(f"Flow '{flow_name}' nicht unter {_flows_dir(project_root)}")


# ===========================================================================
# Run-Management — Create, Start, Status, Pause, Cancel
# ===========================================================================


def create_run(
    project_root: Path,
    flow_name: str,
    *,
    title: str | None = None,
    config: dict[str, Any] | None = None,
) -> RunInfo:
    """Legt einen neuen Run in der DB an (status='pending').

    Startet den Worker NICHT — das macht `start_run` separat. Die
    Trennung erlaubt es, vor dem Start noch Items per enqueue
    vorzubereiten (z.B. fuer Test-Runs mit limitiertem Item-Set).
    """
    _validate_flow_name(flow_name)
    # Pruefen, dass der Flow-Ordner + runner.py existiert
    info = get_flow(project_root, flow_name)
    if not info.has_runner:
        raise FileNotFoundError(
            f"Flow '{flow_name}' hat kein {RUNNER_FILENAME} unter {info.path}"
        )

    db_path = project_root / "data.db"
    # Sicherheitsnetz: Template-Migrationen anwenden, falls neue dazu-
    # gekommen sind (z.B. 005_flow_notifications). Der Server-Lifespan
    # macht das beim Start auch — aber CLI-Aufrufe laufen ohne Lifespan,
    # und wir wollen nicht riskieren, dass ein Runner in eine DB mit
    # veraltetem Schema schreibt.
    try:
        from ..workspace import apply_project_db_migrations

        apply_project_db_migrations(db_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Projekt-Migrationen fuer %s konnten nicht angewendet werden: %s",
            db_path,
            exc,
        )
    conn = _connect(db_path)
    try:
        cfg_json = json.dumps(config, ensure_ascii=False) if config else None
        cur = conn.execute(
            """
            INSERT INTO agent_flow_runs (flow_name, title, config_json)
            VALUES (?, ?, ?)
            """,
            (flow_name, title, cfg_json),
        )
        conn.commit()
        run_id = cur.lastrowid
        return get_run(project_root, run_id)
    finally:
        conn.close()


def start_run(project_root: Path, run_id: int) -> RunInfo:
    """Startet den runner_host als detachten Subprocess.

    Der Subprocess laeuft unabhaengig vom aufrufenden Prozess weiter —
    CLI-Aufrufe kehren sofort zurueck, der Worker laeuft im Hintergrund.

    Wenn der Run-Status bereits 'running' ist und der Prozess noch
    lebt, wird KEIN neuer gestartet (Idempotenz). Ist der alte Worker
    tot (PID existiert nicht mehr), gilt der Run als resume-faehig.
    """
    run = get_run(project_root, run_id)
    if run.status == "running" and run.worker_pid and _pid_alive(run.worker_pid):
        raise RuntimeError(
            f"Run {run_id} laeuft bereits (pid={run.worker_pid}). "
            f"Zum Abbrechen: cancel_run({run_id})."
        )
    if run.status in ("done", "cancelled"):
        raise RuntimeError(
            f"Run {run_id} ist bereits abgeschlossen (status={run.status}). "
            f"Fuer einen neuen Durchlauf bitte create_run(...)."
        )

    # Reset-Fall: failed oder paused → wir duerfen nochmal.
    # Wir setzen Kontroll-Signale zurueck, aber LASSEN die Items —
    # resume ueberspringt 'done' automatisch.
    db_path = project_root / "data.db"
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            UPDATE agent_flow_runs
               SET status = 'pending',
                   worker_pid = NULL,
                   pause_requested = 0,
                   cancel_requested = 0,
                   error = NULL,
                   finished_at = NULL
             WHERE id = ?
            """,
            (run_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Subprocess starten — detached, stdout/stderr in logs/
    log_dir = project_root / ".disco" / "flows" / "runs" / str(run_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    out_log = log_dir / "stdout.log"
    err_log = log_dir / "stderr.log"

    cmd = [
        sys.executable,
        "-m",
        "bew.flows.runner_host",
        str(run_id),
        "--project-root",
        str(project_root),
    ]
    # Detached starten: start_new_session (Posix) bzw. DETACHED (Windows).
    popen_kwargs: dict[str, Any] = {
        "stdout": out_log.open("ab"),
        "stderr": err_log.open("ab"),
        "stdin": subprocess.DEVNULL,
        "cwd": str(project_root),
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )

    proc = subprocess.Popen(cmd, **popen_kwargs)
    logger.info("Flow-Run %d gestartet als PID %d", run_id, proc.pid)
    # Der Worker setzt self worker_pid in start() — aber wir schreiben
    # hier schon einmal den Subprocess-PID, damit pause/cancel sofort geht.
    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE agent_flow_runs SET worker_pid = ? WHERE id = ?",
            (proc.pid, run_id),
        )
        conn.commit()
    finally:
        conn.close()
    return get_run(project_root, run_id)


def get_run(project_root: Path, run_id: int) -> RunInfo:
    db_path = project_root / "data.db"
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT id, flow_name, title, status, worker_pid, config_json,
                   total_items, done_items, failed_items, skipped_items,
                   total_cost_eur, total_tokens_in, total_tokens_out,
                   pause_requested, cancel_requested, error,
                   created_at, started_at, finished_at
              FROM agent_flow_runs
             WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Run {run_id} nicht in agent_flow_runs.")
        return _row_to_runinfo(row)
    finally:
        conn.close()


def list_runs(
    project_root: Path,
    *,
    flow_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[RunInfo]:
    """Listet Runs in einem Projekt (neueste zuerst).

    Gibt eine leere Liste zurueck, wenn das Projekt keine data.db hat
    oder die Flow-Migration (004) noch nicht angewendet wurde.
    """
    import sqlite3

    db_path = project_root / "data.db"
    if not db_path.exists():
        return []
    conn = _connect(db_path)
    try:
        # Phase-1-Projekte ohne Flow-Migration → leer statt 500
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_flow_runs'"
        ).fetchone()
        if not has_table:
            return []
        sql = """
            SELECT id, flow_name, title, status, worker_pid, config_json,
                   total_items, done_items, failed_items, skipped_items,
                   total_cost_eur, total_tokens_in, total_tokens_out,
                   pause_requested, cancel_requested, error,
                   created_at, started_at, finished_at
              FROM agent_flow_runs
        """
        params: list[Any] = []
        conds: list[str] = []
        if flow_name:
            conds.append("flow_name = ?")
            params.append(flow_name)
        if status:
            conds.append("status = ?")
            params.append(status)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(int(limit))
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [_row_to_runinfo(r) for r in rows]
    finally:
        conn.close()


def request_pause(project_root: Path, run_id: int) -> RunInfo:
    """Signalisiert dem Worker: pausiere beim naechsten Item.

    Falls der Worker bereits tot ist (Zombie-Run mit status='running'/'paused'
    aber worker_pid nicht mehr im System), wird der Run **nicht** auf
    'cancelled' oder 'failed' gesetzt — eine Pause-Anfrage ist semantisch
    defensiv und soll keinen Status-Uebergang erzwingen. Das Cleanup ist
    Aufgabe von `request_cancel` / `kill_run`.
    """
    _set_control(project_root, run_id, "pause_requested", 1)
    return get_run(project_root, run_id)


def request_cancel(project_root: Path, run_id: int) -> RunInfo:
    """Signalisiert dem Worker: brich beim naechsten Item ab.

    Wenn der Worker-Prozess nicht mehr laeuft (Zombie-Run), wird der Run
    **direkt** auf Status 'cancelled' gesetzt — sonst wuerde `cancel_requested=1`
    auf einer leeren Seite stehen und der Run liefe in der UI ewig weiter.
    """
    run = get_run(project_root, run_id)
    _set_control(project_root, run_id, "cancel_requested", 1)

    # Zombie-Erkennung: Status noch aktiv, aber Worker tot
    active_status = run.status in ("running", "paused", "pending")
    worker_dead = (not run.worker_pid) or (not _pid_alive(run.worker_pid))
    if active_status and worker_dead:
        db_path = project_root / "data.db"
        conn = _connect(db_path)
        try:
            conn.execute(
                """UPDATE agent_flow_runs
                      SET status = 'cancelled',
                          finished_at = COALESCE(finished_at, datetime('now')),
                          error = COALESCE(error, ?)
                    WHERE id = ? AND status NOT IN ('done','cancelled','failed')""",
                (
                    "Cancel auf bereits beendeten Worker — Status-Cleanup.",
                    run_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    return get_run(project_root, run_id)


def _set_control(project_root: Path, run_id: int, col: str, value: int) -> None:
    if col not in ("pause_requested", "cancel_requested"):
        raise ValueError(f"Unbekannte Control-Spalte: {col}")
    db_path = project_root / "data.db"
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            f"UPDATE agent_flow_runs SET {col} = ? WHERE id = ?",
            (int(value), run_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise KeyError(f"Run {run_id} nicht gefunden.")
    finally:
        conn.close()


def list_run_items(
    project_root: Path,
    run_id: int,
    *,
    status: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    db_path = project_root / "data.db"
    conn = _connect(db_path)
    try:
        sql = """
            SELECT id, run_id, input_ref, status, attempts, output_json,
                   error, tokens_in, tokens_out, cost_eur,
                   created_at, started_at, finished_at
              FROM agent_flow_run_items
             WHERE run_id = ?
        """
        params: list[Any] = [run_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id LIMIT ?"
        params.append(int(limit))
        rows = conn.execute(sql, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            if d.get("output_json"):
                try:
                    d["output"] = json.loads(d["output_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            out.append(d)
        return out
    finally:
        conn.close()


# ===========================================================================
# Prozess-Kontrolle (nur Posix + ad-hoc)
# ===========================================================================


def _pid_alive(pid: int) -> bool:
    """True, wenn ein Prozess mit dieser PID aktiv ist."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Prozess existiert, gehoert aber einem anderen User — zaehlt als lebt.
        return True
    except OSError:
        return False


def kill_run(project_root: Path, run_id: int) -> bool:
    """Killt den Worker-Prozess hart (SIGTERM → SIGKILL).

    NUR als Fallback, wenn der Worker auf cancel_requested nicht reagiert.
    Setzt danach den Status auf 'cancelled' + error='force killed'.

    Returns True wenn ein Prozess signalisiert wurde.
    """
    run = get_run(project_root, run_id)
    if not run.worker_pid or not _pid_alive(run.worker_pid):
        _set_control(project_root, run_id, "cancel_requested", 1)
        # Status aufraeumen
        db_path = project_root / "data.db"
        conn = _connect(db_path)
        try:
            conn.execute(
                """UPDATE agent_flow_runs
                      SET status = 'cancelled',
                          finished_at = COALESCE(finished_at, datetime('now')),
                          error = COALESCE(error, 'Worker-Prozess nicht mehr am Leben.')
                    WHERE id = ? AND status NOT IN ('done','cancelled','failed')""",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()
        return False

    # Zuerst Cancel-Flag setzen, damit der Worker bei naechster Pruefung
    # weiss, dass er terminieren soll. Wichtig fuer den Fall, dass der
    # Worker gerade in einem pausierten Sleep-Loop steckt und der SIGTERM-
    # Handler die DB nicht mehr aktualisieren kann.
    _set_control(project_root, run_id, "cancel_requested", 1)

    try:
        os.kill(run.worker_pid, signal.SIGTERM)
    except OSError as exc:
        logger.warning("SIGTERM fehlgeschlagen: %s", exc)

    # Kurz warten, dass der Worker sauber runterfaehrt (eigener
    # SIGTERM-Handler setzt dann status='cancelled'). Zusaetzlich per
    # waitpid reapen, damit ein Zombie-Prozess nicht als "aktiv" zaehlt.
    terminated = False
    for _ in range(20):
        try:
            reaped_pid, _status = os.waitpid(run.worker_pid, os.WNOHANG)
            if reaped_pid == run.worker_pid:
                terminated = True
                break
        except ChildProcessError:
            # Prozess gehoert nicht zu uns (anderer Uvicorn-Worker?)
            # — per kill(0)-Probe pruefen.
            if not _pid_alive(run.worker_pid):
                terminated = True
                break
        except OSError:
            break
        time.sleep(0.1)

    if not terminated and not _pid_alive(run.worker_pid):
        terminated = True

    # Zombie-Schutz: Wenn der Prozess weg ist, der DB-Status aber nicht
    # mehr aktualisiert wurde (z. B. weil der Worker im Sleep stand),
    # ziehen wir hier auf 'cancelled' nach.
    if terminated:
        db_path = project_root / "data.db"
        conn = _connect(db_path)
        try:
            conn.execute(
                """UPDATE agent_flow_runs
                      SET status = 'cancelled',
                          finished_at = COALESCE(finished_at, datetime('now')),
                          error = COALESCE(error, 'Worker per SIGTERM beendet.')
                    WHERE id = ? AND status NOT IN ('done','cancelled','failed')""",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()
    return True
