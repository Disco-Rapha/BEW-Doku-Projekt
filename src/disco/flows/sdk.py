"""Flow-SDK: API fuer runner.py-Autoren.

Ein Flow-Autor (meist Disco im Dialog mit dem Nutzer) schreibt eine
Datei `flows/<name>/runner.py` mit ungefaehr diesem Aufbau:

    from disco.flows.sdk import FlowRun

    def analyze(item: dict) -> dict:
        # eigene Logik pro Item
        return {"result": "..."}

    def main() -> None:
        run = FlowRun.from_env()
        run.log("Flow gestartet")

        items = run.db.query(
            "SELECT id, rel_path FROM agent_sources WHERE status='active'"
        )
        run.set_total(len(items))

        for item in items:
            run.process(
                input_ref=f"source:{item['id']}",
                fn=analyze,
                args=(item,),
            )

        run.finish()

    if __name__ == "__main__":
        main()

Das SDK nimmt dem Autor alles Lifecycle-nahe ab:
  - Idempotenz: wenn `input_ref` bereits als 'done' existiert, skip.
  - Retry: bei Exception im Callback bis max_retries mit Backoff.
  - Control-Signale: vor jedem Item wird geprueft, ob pausiert/
    abgebrochen werden soll.
  - Budget: `add_cost(...)` pruefen gegen `config.budget_eur`; bei
    Ueberschreitung wird automatisch pausiert.
  - Statistik: done/failed/skipped-Zaehler werden atomar aktualisiert.
  - Logging: `log(msg)` schreibt in `runs/<run_id>/log.txt`.

Der runner.py-Autor muss **nicht** mit subprocess, psutil, DB-Locks
oder Thread-Sicherheit hantieren — das ist Aufgabe des SDKs.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator


logger = logging.getLogger(__name__)


# Environment-Variablen, die der runner_host beim Start setzt
ENV_RUN_ID = "DISCO_FLOW_RUN_ID"
ENV_PROJECT_ROOT = "DISCO_FLOW_PROJECT_ROOT"
ENV_PROJECT_DB = "DISCO_FLOW_PROJECT_DB"
ENV_FLOW_DIR = "DISCO_FLOW_DIR"


# Status-Konstanten (spiegeln das Schema in 004_agent_flows.sql)
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

ITEM_STATUS_PENDING = "pending"
ITEM_STATUS_RUNNING = "running"
ITEM_STATUS_DONE = "done"
ITEM_STATUS_FAILED = "failed"
ITEM_STATUS_SKIPPED = "skipped"


# Notification-Arten (siehe migrations/project/005_flow_notifications.sql).
# Werden vom Backend-Watcher (`disco.flow_notifications`) abgegriffen, der
# daraus System-Trigger-Turns fuer Disco baut.
NOTIFICATION_FIRST_ITEM = "first_item"
NOTIFICATION_SECOND_ITEM = "second_item"
NOTIFICATION_HALF = "half"
NOTIFICATION_HEARTBEAT = "heartbeat"
NOTIFICATION_STATUS_CHANGE = "status_change"
NOTIFICATION_DONE = "done"
NOTIFICATION_FAILED = "failed"

# Heartbeat-Backoff: Start bei 1 min, jedes Mal verdoppeln, Cap bei 4 h.
# Idee: Anfangs viel Aufmerksamkeit (systematische Fehler fallen sofort
# auf), spaeter sporadisch (Token-Sparsamkeit). Stimmt mit der Spalte
# `last_heartbeat_interval_sec DEFAULT 60` aus Migration 005 ueberein.
HEARTBEAT_INITIAL_SEC = 60
HEARTBEAT_MAX_SEC = 14400  # 4 h


# ---------------------------------------------------------------------------
# Pricing — Stand 2026-04 fuer GPT-5 in Sweden Central, API-Version 2025-11-01
# ---------------------------------------------------------------------------
# Quelle: Azure-Preisliste (USD/1M Tokens). Wird von
# FlowRun.add_cost_from_azure_response() genutzt, wenn der Runner keinen
# expliziten EUR-Betrag uebergibt.
#
# Wichtig: Das sind Naeherungen. Fuer rechtssichere Abrechnungen bitte
# weiterhin aus dem Azure-Portal exportieren. Hier geht es um Live-Budget-
# Anzeige im UI, nicht um die Finanzbuchhaltung.
# ---------------------------------------------------------------------------

USD_TO_EUR = 1.09  # grober Stand 2026-04

MODEL_PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    # GPT-5 Familie (default fuer Portal-Agent "bew-doku-agent")
    "gpt-5": {"input": 5.0, "output": 15.0},
    "gpt-5-mini": {"input": 0.5, "output": 2.0},
    "gpt-5-nano": {"input": 0.1, "output": 0.4},
    # GPT-4.1-Familie (noch in Migration)
    "gpt-4.1": {"input": 2.5, "output": 10.0},
    "gpt-4.1-mini": {"input": 0.25, "output": 1.0},
    # Embeddings (fuer spaetere Hybrid-Search-Flows)
    "text-embedding-3-large": {"input": 0.13, "output": 0.0},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


def compute_cost_eur(model: str, tokens_in: int, tokens_out: int) -> float:
    """Berechnet EUR-Kosten fuer einen API-Call.

    Nimmt den Modellnamen wie er im Deployment steht (z.B. 'gpt-5',
    'gpt-5-mini'). Deployment-Aliase mit Suffixen wie 'gpt-5-2025-08-07'
    werden automatisch auf das Basis-Modell zurueckgefuehrt.

    Unbekannte Modelle → 0.0 EUR + Warnung im Log (spaeter: Exception).
    """
    base = _normalize_model_name(model)
    pricing = MODEL_PRICING_USD_PER_MTOK.get(base)
    if pricing is None:
        logger.warning(
            "Unbekanntes Modell fuer Cost-Berechnung: %r (base=%r) — 0 EUR",
            model, base,
        )
        return 0.0
    usd = (
        (tokens_in / 1_000_000.0) * pricing["input"]
        + (tokens_out / 1_000_000.0) * pricing["output"]
    )
    return usd * USD_TO_EUR


def _normalize_model_name(model: str) -> str:
    """Reduziert 'gpt-5-2025-08-07' auf 'gpt-5', 'gpt-4.1-mini-abc' auf 'gpt-4.1-mini'.

    Sucht den laengsten Key in MODEL_PRICING_USD_PER_MTOK, der ein Prefix
    des gegebenen Modellnamens ist. So gewinnt 'gpt-5-mini' vor 'gpt-5'.
    """
    if not model:
        return ""
    m = model.lower().strip()
    # laengster passender Prefix gewinnt (damit 'gpt-5-mini' nicht auf 'gpt-5' fallback)
    best = ""
    for key in MODEL_PRICING_USD_PER_MTOK:
        if m == key or m.startswith(key + "-") or m.startswith(key):
            if len(key) > len(best):
                best = key
    return best or m


# ===========================================================================
# FlowDB — Convenience-Wrapper um sqlite3
# ===========================================================================


class FlowDB:
    """Projekt-DB-Wrapper mit komfortablen Methoden.

    Jeder FlowDB haelt eine **eigene** sqlite3-Verbindung (nicht shared),
    damit parallel-laufender Worker-Code keine Lock-Konflikte bekommt.
    Der Autor muss nicht manuell `close()` rufen — FlowRun schliesst am
    Ende automatisch.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")  # parallele Reader/Writer
        conn.row_factory = sqlite3.Row
        self._conn = conn

    @property
    def path(self) -> Path:
        return self._db_path

    @property
    def conn(self) -> sqlite3.Connection:
        """Raw sqlite3-Verbindung — wenn die Convenience-Methoden nicht reichen."""
        return self._conn

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        """SELECT → Liste von dicts."""
        cur = self._conn.execute(sql, tuple(params))
        cols = [d[0] for d in (cur.description or [])]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        """INSERT/UPDATE/DELETE — commit automatisch nach jedem Call."""
        cur = self._conn.execute(sql, tuple(params))
        self._conn.commit()
        return cur

    def executemany(self, sql: str, param_seq: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        cur = self._conn.executemany(sql, [tuple(p) for p in param_seq])
        self._conn.commit()
        return cur

    def insert_row(
        self,
        table: str,
        data: dict[str, Any],
        *,
        on_conflict: str | None = None,
    ) -> int | None:
        """INSERT ueber dict → automatisch aus Schema generierte Spaltenliste.

        Verhindert die Klasse Bugs wie 'N values for M columns', weil die
        Tupel-Position nicht mehr mit der DDL uebereinstimmt. Der Autor
        schreibt::

            run.db.insert_row("agent_dcc_results", {
                "source_id": 42,
                "rel_path": "...",
                "Master DCC": "MAA10",
                "Conf.score DCC (Master)": 0.92,
                ...
            })

        Parameter
        ---------
        table : str
            Name der Ziel-Tabelle. Muss existieren.
        data : dict
            Keys = Spaltennamen (genau wie in der DDL, inkl. Umlaute/
            Sonderzeichen). Keys die nicht zur Tabelle gehoeren → ValueError
            (schuetzt vor Tippfehlern).
        on_conflict : str | None
            - None (Default): plain INSERT. Bei Conflict → Exception.
            - 'replace'     : `INSERT OR REPLACE`.
            - 'ignore'      : `INSERT OR IGNORE`.
            - 'update:col1,col2,...': `ON CONFLICT(col1) DO UPDATE SET ...`
              fuer alle uebrigen Keys (Upsert-Muster).

        Returns
        -------
        int | None
            Die neue rowid (lastrowid) bei echtem INSERT, None bei IGNORE
            ohne Wirkung.
        """
        if not data:
            raise ValueError("insert_row: data-dict ist leer.")

        # Schema einlesen (gecached waere schoener, aber PRAGMA ist billig)
        cols_rows = self.query(f'PRAGMA table_info("{table}")')
        if not cols_rows:
            raise ValueError(f"insert_row: Tabelle {table!r} existiert nicht.")
        schema_cols = {r["name"] for r in cols_rows}

        # Validieren: alle Keys muessen in der Tabelle existieren
        unknown = [k for k in data.keys() if k not in schema_cols]
        if unknown:
            raise ValueError(
                f"insert_row: Unbekannte Spalten fuer Tabelle {table!r}: {unknown}. "
                f"Bekannt: {sorted(schema_cols)}"
            )

        keys = list(data.keys())
        # Spaltennamen in "..." quoten (erlaubt Sonderzeichen/Leerzeichen)
        col_list = ", ".join(f'"{k}"' for k in keys)
        placeholders = ", ".join("?" for _ in keys)
        values = [data[k] for k in keys]

        if on_conflict is None:
            sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'
        elif on_conflict == "replace":
            sql = f'INSERT OR REPLACE INTO "{table}" ({col_list}) VALUES ({placeholders})'
        elif on_conflict == "ignore":
            sql = f'INSERT OR IGNORE INTO "{table}" ({col_list}) VALUES ({placeholders})'
        elif on_conflict.startswith("update:"):
            conflict_cols = [c.strip() for c in on_conflict[len("update:"):].split(",") if c.strip()]
            if not conflict_cols:
                raise ValueError(
                    "insert_row: on_conflict='update:...' benoetigt mindestens "
                    "eine Conflict-Spalte, z.B. 'update:source_id'."
                )
            update_keys = [k for k in keys if k not in conflict_cols]
            if not update_keys:
                raise ValueError(
                    "insert_row: on_conflict='update:...' sinnvoll nur wenn "
                    "es neben den Conflict-Spalten weitere Spalten gibt."
                )
            set_clause = ", ".join(f'"{k}" = excluded."{k}"' for k in update_keys)
            conflict_list = ", ".join(f'"{c}"' for c in conflict_cols)
            sql = (
                f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) '
                f'ON CONFLICT({conflict_list}) DO UPDATE SET {set_clause}'
            )
        else:
            raise ValueError(
                f"insert_row: on_conflict={on_conflict!r} ungueltig. "
                "Erlaubt: None, 'replace', 'ignore', 'update:col1,col2,...'."
            )

        cur = self._conn.execute(sql, values)
        self._conn.commit()
        return cur.lastrowid

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


# ===========================================================================
# FlowRun — der Haupt-Einstiegspunkt fuer runner.py
# ===========================================================================


@dataclass
class _RunMeta:
    """In-Memory-Kopie der agent_flow_runs-Zeile (wird periodisch refresht)."""
    id: int
    flow_name: str
    title: str | None
    status: str
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


class FlowStopped(Exception):
    """Wird geworfen, wenn der Flow via pause/cancel abgebrochen wird.

    Der runner_host faengt diese Exception und setzt den Status korrekt
    auf 'paused' oder 'cancelled' — ohne sie als Fehler zu werten.
    """


class FlowRun:
    """Zentraler Einstiegspunkt fuer Flow-runner.py.

    Instanziierung:
      - Normal via `FlowRun.from_env()` — liest alles aus DISCO_FLOW_*-Env
        (von `runner_host` gesetzt).
      - Fuer Tests via `FlowRun(run_id=..., project_root=..., ...)`.

    Lifecycle-Disziplin:
      - Genau EIN FlowRun pro Worker-Prozess.
      - Vor dem ersten `process()` automatisch `start()` (status running).
      - Am Ende `finish()` oder eine Exception (runner_host kuemmert sich).
    """

    # Wie oft (in Sekunden) wir den Meta-Stand aus der DB nachladen.
    # Weniger = schneller auf pause/cancel reagieren, aber mehr DB-Load.
    _META_REFRESH_SECONDS = 2.0

    def __init__(
        self,
        *,
        run_id: int,
        project_root: Path,
        db_path: Path,
        flow_dir: Path | None = None,
    ) -> None:
        self._run_id = int(run_id)
        self._project_root = Path(project_root).resolve()
        self._db_path = Path(db_path).resolve()
        self._flow_dir = Path(flow_dir).resolve() if flow_dir else None

        self._db = FlowDB(self._db_path)
        self._meta = self._load_meta()
        self._last_refresh = time.monotonic()

        # Log-Datei unter .disco/flows/runs/<run_id>/log.txt oeffnen.
        # Bewusst nicht im Flow-Ordner selbst — der Flow-Ordner ist fuer
        # Code (README, runner.py); Runtime-Artefakte liegen in .disco/.
        # Der gleiche Ort wird von service.start_run() fuer stdout/stderr
        # genutzt, und vom `disco flow logs`-Command abgefragt.
        self._log_dir = (
            self._project_root / ".disco" / "flows" / "runs" / f"{self._run_id}"
        )
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._log_dir / "log.txt"

        self._started = False

    # ------------------------------------------------------------------
    # Konstruktion aus Env
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "FlowRun":
        """Baut einen FlowRun aus den DISCO_FLOW_*-Environment-Variablen.

        Wird vom `runner_host` gesetzt. Wirft RuntimeError wenn unvollstaendig.
        """
        try:
            run_id = int(os.environ[ENV_RUN_ID])
            project_root = os.environ[ENV_PROJECT_ROOT]
            db_path = os.environ[ENV_PROJECT_DB]
        except KeyError as exc:
            raise RuntimeError(
                f"FlowRun.from_env benoetigt {ENV_RUN_ID}, {ENV_PROJECT_ROOT}, "
                f"{ENV_PROJECT_DB} — fehlt: {exc.args[0]}. "
                f"Flows werden normalerweise ueber `disco flow run` gestartet."
            ) from exc
        flow_dir = os.environ.get(ENV_FLOW_DIR)
        return cls(
            run_id=run_id,
            project_root=Path(project_root),
            db_path=Path(db_path),
            flow_dir=Path(flow_dir) if flow_dir else None,
        )

    # ------------------------------------------------------------------
    # Public Properties
    # ------------------------------------------------------------------

    @property
    def run_id(self) -> int:
        return self._run_id

    @property
    def flow_name(self) -> str:
        return self._meta.flow_name

    @property
    def title(self) -> str | None:
        """Menschenlesbarer Titel des Runs (aus agent_flow_runs.title).

        Wird beim `flow_run`-Start gesetzt (z.B. 'Mini-Run 3 PDFs'). Kann
        `None` sein, wenn der Starter keinen Titel uebergab.
        """
        return self._meta.title

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def flow_dir(self) -> Path | None:
        """Pfad zum Flow-Ordner `flows/<flow_name>/`, falls bekannt."""
        return self._flow_dir

    @property
    def db(self) -> FlowDB:
        return self._db

    @property
    def config(self) -> dict[str, Any]:
        """Die Parameter, mit denen der Run gestartet wurde."""
        return dict(self._meta.config)

    @property
    def total_cost_eur(self) -> float:
        return self._meta.total_cost_eur

    # ------------------------------------------------------------------
    # Start / Finish — Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Markiert den Run als `running`. Idempotent."""
        if self._started:
            return
        old_status = self._meta.status
        # Heartbeat-Spalten werden defensiv gesetzt — falls die Migration 005
        # noch nicht angewendet wurde, faellt _set_heartbeat_after_start auf
        # einen ohne-Heartbeat-Pfad zurueck und der Flow laeuft trotzdem.
        self._db.execute(
            """
            UPDATE agent_flow_runs
               SET status = ?, started_at = COALESCE(started_at, datetime('now')),
                   worker_pid = ?
             WHERE id = ?
            """,
            (STATUS_RUNNING, os.getpid(), self._run_id),
        )
        self._set_heartbeat_after_start()
        self._started = True
        self._refresh_meta(force=True)
        self.log(f"Run gestartet (pid={os.getpid()}, flow={self.flow_name})")
        # Notification: Disco soll Bescheid wissen, dass der Run jetzt laeuft.
        # Wenn die Notifications-Tabelle noch nicht existiert, schluckt
        # _emit_notification das still — der Flow laeuft trotzdem weiter.
        self._emit_notification(
            NOTIFICATION_STATUS_CHANGE,
            extra_context={"old_status": old_status, "new_status": STATUS_RUNNING},
        )

    def finish(self, status: str = STATUS_DONE) -> None:
        """Schliesst den Run ab.

        Default: 'done'. Der runner_host setzt bei Exception 'failed',
        bei FlowStopped 'paused' oder 'cancelled'.
        """
        if status not in (STATUS_DONE, STATUS_FAILED, STATUS_PAUSED, STATUS_CANCELLED):
            raise ValueError(f"Ungueltiger Finish-Status: {status!r}")
        old_status = self._meta.status
        self._db.execute(
            """
            UPDATE agent_flow_runs
               SET status = ?, finished_at = datetime('now')
             WHERE id = ?
            """,
            (status, self._run_id),
        )
        # Heartbeat ausschalten (Run ist beendet — kein Heartbeat noetig).
        self._clear_heartbeat()
        self.log(f"Run abgeschlossen: status={status}")
        # Meta noch einmal nachladen, damit die Notification den finalen
        # Stand der Counter sieht.
        self._refresh_meta(force=True)
        # Passende Notification feuern. Watcher entscheidet, was er damit
        # anfaengt (Disco anpingen, Bubble updaten, etc.).
        if status == STATUS_DONE:
            self._emit_notification(
                NOTIFICATION_DONE,
                extra_context={"old_status": old_status, "new_status": status},
            )
        elif status in (STATUS_FAILED, STATUS_CANCELLED):
            self._emit_notification(
                NOTIFICATION_FAILED,
                extra_context={"old_status": old_status, "new_status": status},
            )
        else:  # STATUS_PAUSED
            self._emit_notification(
                NOTIFICATION_STATUS_CHANGE,
                extra_context={"old_status": old_status, "new_status": status},
            )
        self._db.close()

    def fail(self, error_msg: str) -> None:
        """Markiert den Run als gescheitert."""
        old_status = self._meta.status
        self._db.execute(
            """
            UPDATE agent_flow_runs
               SET status = ?, finished_at = datetime('now'), error = ?
             WHERE id = ?
            """,
            (STATUS_FAILED, error_msg, self._run_id),
        )
        self._clear_heartbeat()
        self.log(f"Run FAILED: {error_msg}")
        self._refresh_meta(force=True)
        self._emit_notification(
            NOTIFICATION_FAILED,
            extra_context={
                "old_status": old_status,
                "new_status": STATUS_FAILED,
                "error": error_msg[:500] if error_msg else None,
            },
        )

    # ------------------------------------------------------------------
    # Item-Verwaltung
    # ------------------------------------------------------------------

    def set_total(self, n: int) -> None:
        """Setzt die erwartete Gesamtzahl der Items (rein informativ fuer die UI)."""
        self._db.execute(
            "UPDATE agent_flow_runs SET total_items = ? WHERE id = ?",
            (int(n), self._run_id),
        )
        self._meta.total_items = int(n)

    def enqueue(self, input_refs: Iterable[str]) -> int:
        """Fuegt Items als 'pending' hinzu. Idempotent (UNIQUE-Index).

        Gibt die Anzahl der tatsaechlich neu eingefuegten Items zurueck.
        """
        refs = list(input_refs)
        if not refs:
            return 0
        before = self._db.query_one(
            "SELECT COUNT(*) AS n FROM agent_flow_run_items WHERE run_id = ?",
            (self._run_id,),
        )
        self._db.executemany(
            """
            INSERT OR IGNORE INTO agent_flow_run_items (run_id, input_ref)
            VALUES (?, ?)
            """,
            [(self._run_id, ref) for ref in refs],
        )
        after = self._db.query_one(
            "SELECT COUNT(*) AS n FROM agent_flow_run_items WHERE run_id = ?",
            (self._run_id,),
        )
        new = (after["n"] if after else 0) - (before["n"] if before else 0)
        # total_items aktualisieren, falls der Autor nicht explizit set_total gerufen hat
        if new > 0:
            self._db.execute(
                """
                UPDATE agent_flow_runs
                   SET total_items = (
                     SELECT COUNT(*) FROM agent_flow_run_items WHERE run_id = ?
                   )
                 WHERE id = ?
                """,
                (self._run_id, self._run_id),
            )
        return new

    def process(
        self,
        *,
        input_ref: str,
        fn: Callable[..., dict | None],
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        max_retries: int = 3,
        retry_backoff_s: float = 2.0,
    ) -> bool:
        """Fuehrt `fn(*args, **kwargs)` fuer ein Item aus.

        Ablauf:
          1. Vor dem Call: Pause/Cancel checken → FlowStopped werfen.
          2. Wenn der Eintrag schon 'done' ist: skip, return True.
          3. Status auf 'running' setzen, started_at setzen.
          4. fn aufrufen. Rueckgabe muss JSON-serialisierbar sein
             (dict/list/scalar) oder None.
          5. Bei Erfolg: output_json = json(result), status='done',
             done_items++ im Run.
          6. Bei Exception: attempts++, error=traceback, ggf. Retry
             mit Backoff. Nach max_retries: status='failed',
             failed_items++.

        Returns True bei done (auch bei bereits done), False bei failed.

        Wirft FlowStopped wenn pause/cancel gesetzt ist.
        """
        if not self._started:
            self.start()

        # Control-Signale (ohne DB-Traffic wenn moeglich)
        self._refresh_meta()
        if self._meta.cancel_requested:
            raise FlowStopped("cancel_requested")
        if self._meta.pause_requested:
            raise FlowStopped("pause_requested")

        # Idempotenz: Eintrag sichern
        existing = self._db.query_one(
            """
            SELECT id, status, attempts FROM agent_flow_run_items
             WHERE run_id = ? AND input_ref = ?
            """,
            (self._run_id, input_ref),
        )
        if existing is None:
            self._db.execute(
                """
                INSERT INTO agent_flow_run_items
                    (run_id, input_ref, status, started_at)
                VALUES (?, ?, 'running', datetime('now'))
                """,
                (self._run_id, input_ref),
            )
            item_id = self._db.query_one(
                "SELECT id FROM agent_flow_run_items WHERE run_id = ? AND input_ref = ?",
                (self._run_id, input_ref),
            )["id"]
            # total_items synchron halten — aber NUR wenn der Autor
            # weder set_total() noch enqueue() genutzt hat. Der SDK-User
            # darf erwarten, dass `total_items` seine gesetzte Obergrenze
            # ist und nicht durch process() ueberschrieben wird.
            cur_total = self._db.query_one(
                "SELECT total_items FROM agent_flow_runs WHERE id = ?",
                (self._run_id,),
            )
            cur_done_failed_skipped = self._db.query_one(
                """
                SELECT COUNT(*) AS n FROM agent_flow_run_items
                 WHERE run_id = ? AND status IN ('done','failed','skipped','running')
                """,
                (self._run_id,),
            )
            # Wenn die aktuelle bereits-gesehen-Anzahl das gesetzte
            # total_items uebersteigt, ziehen wir total_items nach.
            # Damit bleibt set_total/enqueue respektiert, aber bei
            # Autoren, die weder set_total noch enqueue nutzen, wird
            # total_items waehrend des Laufs hochgezaehlt.
            if cur_done_failed_skipped["n"] > (cur_total["total_items"] if cur_total else 0):
                self._db.execute(
                    "UPDATE agent_flow_runs SET total_items = ? WHERE id = ?",
                    (cur_done_failed_skipped["n"], self._run_id),
                )
        else:
            item_id = existing["id"]
            if existing["status"] == ITEM_STATUS_DONE:
                return True  # schon erledigt, idempotent skip
            if existing["status"] == ITEM_STATUS_SKIPPED:
                return True  # bewusst uebersprungen — nicht erneut versuchen
            self._db.execute(
                """
                UPDATE agent_flow_run_items
                   SET status = 'running',
                       started_at = COALESCE(started_at, datetime('now'))
                 WHERE id = ?
                """,
                (item_id,),
            )

        # Ausfuehren mit Retries
        kwargs = kwargs or {}
        last_error: str | None = None
        for attempt in range(1, max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                # None wird als leeres dict gespeichert (output-Feld ist NULLable)
                payload = None if result is None else json.dumps(
                    result, ensure_ascii=False, default=str
                )
                self._db.execute(
                    """
                    UPDATE agent_flow_run_items
                       SET status = 'done',
                           output_json = ?,
                           attempts = ?,
                           finished_at = datetime('now'),
                           error = NULL
                     WHERE id = ?
                    """,
                    (payload, attempt, item_id),
                )
                self._db.execute(
                    "UPDATE agent_flow_runs SET done_items = done_items + 1 WHERE id = ?",
                    (self._run_id,),
                )
                # Nach jedem done-Item: pruefen, ob Trigger faellig sind
                # (first_item/second_item/half/heartbeat). Dies ist die
                # einzige Stelle, an der die Counter-basierten Trigger
                # feuern koennen — skip() ruft dieselbe Funktion, damit
                # auch reine Skip-Runs Heartbeats bekommen.
                self._check_progress_notifications()
                return True
            except FlowStopped:
                # Aufrufer will abbrechen — Item als pending zurueckgeben (nicht done, nicht failed)
                self._db.execute(
                    """
                    UPDATE agent_flow_run_items
                       SET status = 'pending', attempts = ?, started_at = NULL
                     WHERE id = ?
                    """,
                    (attempt, item_id),
                )
                raise
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                self.log(f"Item '{input_ref}' Attempt {attempt}/{max_retries} FEHLER: {exc}")
                if attempt < max_retries:
                    time.sleep(retry_backoff_s * attempt)
                    continue
        # Alle Retries erschoepft → failed
        self._db.execute(
            """
            UPDATE agent_flow_run_items
               SET status = 'failed',
                   attempts = ?,
                   finished_at = datetime('now'),
                   error = ?
             WHERE id = ?
            """,
            (max_retries, last_error, item_id),
        )
        self._db.execute(
            "UPDATE agent_flow_runs SET failed_items = failed_items + 1 WHERE id = ?",
            (self._run_id,),
        )
        # Fehlgeschlagene Items zaehlen fuer first_item/second_item/half/
        # heartbeat mit — ein fruehes Failed-Item ist vielleicht sogar der
        # wichtigste Trigger (systematischer Fehler sichtbar machen).
        self._check_progress_notifications()
        return False

    def skip(self, input_ref: str, reason: str = "") -> None:
        """Markiert ein Item explizit als `skipped`. Idempotent.

        Beispiel-Use-Case: „Datei existiert nicht mehr" oder „Filter
        trifft nicht mehr zu" — kein Fehler, aber auch kein done.
        """
        self._db.execute(
            """
            INSERT INTO agent_flow_run_items (run_id, input_ref, status, error, finished_at)
            VALUES (?, ?, 'skipped', ?, datetime('now'))
            ON CONFLICT(run_id, input_ref) DO UPDATE SET
                status = 'skipped',
                error = excluded.error,
                finished_at = datetime('now')
            WHERE status != 'done'
            """,
            (self._run_id, input_ref, reason or None),
        )
        self._db.execute(
            "UPDATE agent_flow_runs SET skipped_items = skipped_items + 1 WHERE id = ?",
            (self._run_id,),
        )
        # Auch skip() zaehlt als Fortschritt — sonst wuerde ein Run, der
        # ausschliesslich skipped-Items produziert, nie Heartbeats feuern.
        self._check_progress_notifications()

    # ------------------------------------------------------------------
    # Kosten + Budget
    # ------------------------------------------------------------------

    def add_cost(self, eur: float = 0.0, tokens_in: int = 0, tokens_out: int = 0) -> None:
        """Kosten eines Items registrieren. Prueft automatisch das Budget.

        Wenn `config.budget_eur` gesetzt und nach Addition ueberschritten,
        wird `pause_requested = 1` gesetzt — der naechste Item-Call wirft
        dann FlowStopped('pause_requested').
        """
        if eur <= 0 and tokens_in <= 0 and tokens_out <= 0:
            return
        self._db.execute(
            """
            UPDATE agent_flow_runs
               SET total_cost_eur = total_cost_eur + ?,
                   total_tokens_in = total_tokens_in + ?,
                   total_tokens_out = total_tokens_out + ?
             WHERE id = ?
            """,
            (float(eur), int(tokens_in), int(tokens_out), self._run_id),
        )
        # Meta refreshen fuer Budget-Check
        self._refresh_meta(force=True)
        budget = self._meta.config.get("budget_eur")
        if budget is not None and self._meta.total_cost_eur > float(budget):
            self.log(
                f"Budget ueberschritten: {self._meta.total_cost_eur:.4f} EUR > "
                f"{float(budget):.2f} EUR Limit — Pause angefordert."
            )
            self._db.execute(
                "UPDATE agent_flow_runs SET pause_requested = 1 WHERE id = ?",
                (self._run_id,),
            )
            self._meta.pause_requested = True

    def add_cost_from_azure_response(
        self,
        response: Any,
        *,
        model: str | None = None,
    ) -> tuple[int, int, float]:
        """Extrahiert usage aus einer Azure-OpenAI-Antwort und bucht die Kosten.

        Ersetzt das wiederkehrende Muster::

            usage = response.usage
            tokens_in = getattr(usage, "prompt_tokens", 0) if usage else 0
            tokens_out = getattr(usage, "completion_tokens", 0) if usage else 0
            # ... (Kostenberechnung vergessen) ...

        Unterstuetzte Response-Formate:
          - openai.types.chat.ChatCompletion (response.usage.prompt_tokens, ...)
          - dict-artige Objekte mit 'usage': {'prompt_tokens': ..., 'completion_tokens': ...}
          - Responses-API mit 'usage': {'input_tokens': ..., 'output_tokens': ...}

        Parameter
        ---------
        response : Any
            Die Antwort vom Azure-OpenAI-Client.
        model : str | None
            Modellname fuer die Preisberechnung. Wenn None, versucht die
            Funktion `response.model` zu lesen. Fallback: 'gpt-5'.

        Returns
        -------
        tuple[int, int, float]
            (tokens_in, tokens_out, eur) — fuer Per-Item-Logging falls der
            Runner das in seine Ergebnis-Tabelle schreiben will.
        """
        tokens_in, tokens_out = _extract_usage(response)
        used_model = model or getattr(response, "model", None) or "gpt-5"
        eur = compute_cost_eur(used_model, tokens_in, tokens_out)
        self.add_cost(eur=eur, tokens_in=tokens_in, tokens_out=tokens_out)
        return tokens_in, tokens_out, eur

    # ------------------------------------------------------------------
    # Control-Signale
    # ------------------------------------------------------------------

    def should_stop(self) -> bool:
        """True wenn pause oder cancel angefordert ist."""
        self._refresh_meta()
        return self._meta.pause_requested or self._meta.cancel_requested

    def is_cancel_requested(self) -> bool:
        self._refresh_meta()
        return self._meta.cancel_requested

    def is_pause_requested(self) -> bool:
        self._refresh_meta()
        return self._meta.pause_requested

    # ------------------------------------------------------------------
    # Datei-I/O (auf das Projekt beschraenkt)
    # ------------------------------------------------------------------

    def read_file(self, rel_path: str, encoding: str = "utf-8") -> str:
        """Liest eine Textdatei relativ zum Projekt-Root."""
        path = self._resolve_in_project(rel_path)
        return path.read_text(encoding=encoding)

    def read_bytes(self, rel_path: str) -> bytes:
        path = self._resolve_in_project(rel_path)
        return path.read_bytes()

    def write_file(
        self,
        rel_path: str,
        content: str,
        encoding: str = "utf-8",
        append: bool = False,
    ) -> Path:
        """Schreibt eine Textdatei relativ zum Projekt-Root. Ordner werden angelegt."""
        path = self._resolve_in_project(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with path.open(mode, encoding=encoding) as fh:
            fh.write(content)
        return path

    def _resolve_in_project(self, rel_path: str) -> Path:
        candidate = (self._project_root / rel_path).resolve()
        # Traversal-Schutz
        try:
            candidate.relative_to(self._project_root)
        except ValueError:
            raise ValueError(
                f"Pfad ausserhalb des Projekt-Roots: {rel_path!r}"
            )
        return candidate

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, msg: str) -> None:
        """Schreibt eine Log-Zeile nach `runs/<run_id>/log.txt` und stderr."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}\n"
        try:
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass
        # zusaetzlich stderr, damit man beim interaktiven Start live zuschauen kann
        sys.stderr.write(line)
        sys.stderr.flush()

    # ------------------------------------------------------------------
    # Interne Helfer
    # ------------------------------------------------------------------

    def _load_meta(self) -> _RunMeta:
        row = self._db.query_one(
            """
            SELECT id, flow_name, title, status, config_json,
                   total_items, done_items, failed_items, skipped_items,
                   total_cost_eur, total_tokens_in, total_tokens_out,
                   pause_requested, cancel_requested
              FROM agent_flow_runs
             WHERE id = ?
            """,
            (self._run_id,),
        )
        if row is None:
            raise RuntimeError(
                f"Flow-Run {self._run_id} nicht in agent_flow_runs gefunden."
            )
        try:
            config = json.loads(row["config_json"]) if row["config_json"] else {}
        except json.JSONDecodeError:
            config = {}
        return _RunMeta(
            id=row["id"],
            flow_name=row["flow_name"],
            title=row["title"],
            status=row["status"],
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
        )

    def _refresh_meta(self, force: bool = False) -> None:
        """Laedt den Meta-Stand aus der DB nach, wenn das TTL abgelaufen ist.

        Dient vor allem dazu, pause_requested/cancel_requested nicht bei
        jedem Item nachzuschlagen (zu viel DB-Traffic), aber auch nicht
        ewig zu verpassen.
        """
        now = time.monotonic()
        if not force and (now - self._last_refresh) < self._META_REFRESH_SECONDS:
            return
        self._meta = self._load_meta()
        self._last_refresh = now

    # ------------------------------------------------------------------
    # Notifications (Migration 005)
    # ------------------------------------------------------------------
    #
    # Drei Helfer, die das Worker-SDK kennt, der Runner-Autor aber nicht
    # direkt aufruft:
    #
    #   _emit_notification        — INSERT in agent_flow_notifications
    #   _check_progress_notifications — Trigger-Logik pro Item (first_item,
    #                                   second_item, half, heartbeat)
    #   _set_heartbeat_after_start    — initialen next_heartbeat_at setzen
    #   _clear_heartbeat              — next_heartbeat_at = NULL beim Finish
    #
    # Alle Methoden sind defensive: wenn Migration 005 in der Projekt-DB
    # noch nicht angewendet wurde (next_heartbeat_at-Spalte fehlt, Tabelle
    # fehlt), schlucken sie die sqlite3.Error und der Flow laeuft weiter.

    def _emit_notification(
        self,
        kind: str,
        extra_context: dict[str, Any] | None = None,
    ) -> None:
        """Legt eine Notification in agent_flow_notifications an.

        context_json enthaelt einen minimalen Snapshot (Counter, Status,
        Kosten). Der Backend-Watcher reichert beim Trigger-Bau mit
        Live-Daten an (letzte Items, Logs, Flow-README).

        Niemals crashen — Notifications sind Best-Effort.
        """
        try:
            ctx: dict[str, Any] = {
                "done": self._meta.done_items,
                "total": self._meta.total_items,
                "failed": self._meta.failed_items,
                "skipped": self._meta.skipped_items,
                "status": self._meta.status,
                "cost_eur": round(self._meta.total_cost_eur, 6),
                "tokens_in": self._meta.total_tokens_in,
                "tokens_out": self._meta.total_tokens_out,
            }
            if extra_context:
                ctx.update(extra_context)
            self._db.execute(
                """
                INSERT INTO agent_flow_notifications (run_id, kind, context_json)
                VALUES (?, ?, ?)
                """,
                (
                    self._run_id,
                    kind,
                    json.dumps(ctx, ensure_ascii=False, default=str),
                ),
            )
        except sqlite3.Error as exc:
            # Tabelle fehlt oder andere DB-Stoerung — Flow darf nicht
            # crashen. Fehler in die Log-Datei, aber stumm.
            try:
                self.log(f"Notification '{kind}' konnte nicht gespeichert werden: {exc}")
            except Exception:
                pass

    def _check_progress_notifications(self) -> None:
        """Feuert Trigger nach jedem verarbeiteten Item.

        Vier Trigger-Arten:
          - first_item  : sobald 1 Item fertig ist (done/failed/skipped)
          - second_item : sobald 2 Items fertig sind
          - half        : ab total_items >= 5 und completed >= total/2
          - heartbeat   : wenn next_heartbeat_at erreicht ist

        Jeder Counter-Trigger feuert genau einmal pro Run — die Methode
        fragt bestehende Notifications ab, um Dopplung zu vermeiden.
        Heartbeats sind rekurrent mit exponentiellem Backoff
        (HEARTBEAT_INITIAL_SEC -> Cap HEARTBEAT_MAX_SEC).
        """
        try:
            self._refresh_meta(force=True)
            completed = (
                self._meta.done_items
                + self._meta.failed_items
                + self._meta.skipped_items
            )
            total = self._meta.total_items

            # Bereits gefeuerte Counter-Trigger fuer diesen Run
            existing = self._db.query(
                """
                SELECT kind FROM agent_flow_notifications
                 WHERE run_id = ?
                   AND kind IN ('first_item','second_item','half')
                """,
                (self._run_id,),
            )
            kinds_seen = {row["kind"] for row in existing}

            if completed >= 1 and NOTIFICATION_FIRST_ITEM not in kinds_seen:
                self._emit_notification(NOTIFICATION_FIRST_ITEM)
                kinds_seen.add(NOTIFICATION_FIRST_ITEM)

            if completed >= 2 and NOTIFICATION_SECOND_ITEM not in kinds_seen:
                self._emit_notification(NOTIFICATION_SECOND_ITEM)
                kinds_seen.add(NOTIFICATION_SECOND_ITEM)

            # 'half' nur bei ausreichend grossen Runs sinnvoll — sonst
            # ueberlappt es mit first/second (bei total=2: half = first).
            if (
                total >= 5
                and completed * 2 >= total
                and NOTIFICATION_HALF not in kinds_seen
            ):
                self._emit_notification(NOTIFICATION_HALF)

            # Heartbeat-Faelligkeit pruefen
            hb_row = self._db.query_one(
                """
                SELECT next_heartbeat_at, last_heartbeat_interval_sec
                  FROM agent_flow_runs
                 WHERE id = ?
                """,
                (self._run_id,),
            )
            if not hb_row or not hb_row.get("next_heartbeat_at"):
                return

            # Vergleich als ISO-String ist lexikografisch korrekt, solange
            # beide Seiten das Format 'YYYY-MM-DD HH:MM:SS' haben.
            now_row = self._db.query_one("SELECT datetime('now') AS now")
            now_iso = now_row["now"] if now_row else None
            if not now_iso or now_iso < hb_row["next_heartbeat_at"]:
                return

            # Heartbeat ist faellig: Backoff verdoppeln, next_heartbeat_at
            # aktualisieren, DANN Notification feuern. Reihenfolge wichtig:
            # falls wir zwischen UPDATE und INSERT crashen, verpassen wir
            # einen Heartbeat (besser als doppelt feuern).
            current_interval = int(
                hb_row.get("last_heartbeat_interval_sec") or HEARTBEAT_INITIAL_SEC
            )
            new_interval = min(current_interval * 2, HEARTBEAT_MAX_SEC)
            self._db.execute(
                """
                UPDATE agent_flow_runs
                   SET last_heartbeat_interval_sec = ?,
                       next_heartbeat_at = datetime('now', ?)
                 WHERE id = ?
                """,
                (new_interval, f"+{new_interval} seconds", self._run_id),
            )
            self._emit_notification(
                NOTIFICATION_HEARTBEAT,
                extra_context={
                    "interval_sec": current_interval,
                    "next_interval_sec": new_interval,
                },
            )
        except sqlite3.Error as exc:
            # Progress-Check ist Best-Effort. Alte Projekt-DB ohne
            # Migration 005 → still schlucken, Flow laeuft weiter.
            try:
                self.log(f"Progress-Notification-Check scheiterte: {exc}")
            except Exception:
                pass

    def _set_heartbeat_after_start(self) -> None:
        """Legt den ersten Heartbeat-Tick fest (now + HEARTBEAT_INITIAL_SEC).

        Defensive Variante: wenn die neue Spalte fehlt (Migration 005
        nicht angewendet), wird der Fehler stumm geschluckt — der Run
        laeuft dann ohne Heartbeat, aber ohne Abbruch.
        """
        try:
            self._db.execute(
                """
                UPDATE agent_flow_runs
                   SET next_heartbeat_at = datetime('now', ?),
                       last_heartbeat_interval_sec = ?
                 WHERE id = ?
                """,
                (
                    f"+{HEARTBEAT_INITIAL_SEC} seconds",
                    HEARTBEAT_INITIAL_SEC,
                    self._run_id,
                ),
            )
        except sqlite3.Error:
            pass

    def _clear_heartbeat(self) -> None:
        """Schaltet next_heartbeat_at aus (Run ist beendet/pausiert)."""
        try:
            self._db.execute(
                """
                UPDATE agent_flow_runs
                   SET next_heartbeat_at = NULL
                 WHERE id = ?
                """,
                (self._run_id,),
            )
        except sqlite3.Error:
            pass


# ===========================================================================
# Usage-Extraktion — tolerant gegenueber verschiedenen SDK-Versionen
# ===========================================================================


def _extract_usage(response: Any) -> tuple[int, int]:
    """Holt (prompt_tokens, completion_tokens) aus einer Azure-OpenAI-Antwort.

    Unterstuetzt:
      - openai-Python-SDK >=1.x: response.usage.prompt_tokens / .completion_tokens
      - Responses-API (preview): response.usage.input_tokens / .output_tokens
      - Rohes dict aus REST-Aufrufen: {'usage': {...}}

    Gibt (0, 0) zurueck, wenn kein usage-Feld gefunden wird — dann werden
    0 EUR gebucht (besser als Abbruch mitten im Flow).
    """
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return 0, 0

    # Variante 1: Chat Completions (prompt_tokens / completion_tokens)
    t_in = _get_attr_or_key(usage, "prompt_tokens")
    t_out = _get_attr_or_key(usage, "completion_tokens")
    if t_in is not None or t_out is not None:
        return int(t_in or 0), int(t_out or 0)

    # Variante 2: Responses API (input_tokens / output_tokens)
    t_in = _get_attr_or_key(usage, "input_tokens")
    t_out = _get_attr_or_key(usage, "output_tokens")
    if t_in is not None or t_out is not None:
        return int(t_in or 0), int(t_out or 0)

    return 0, 0


def _get_attr_or_key(obj: Any, name: str) -> Any:
    """Liefert obj.name (SDK-Objekt) oder obj[name] (dict) oder None."""
    val = getattr(obj, name, None)
    if val is not None:
        return val
    if isinstance(obj, dict):
        return obj.get(name)
    return None


# ===========================================================================
# Kontext-Manager fuer Flow-freundliches Pause-Handling
# ===========================================================================


@contextmanager
def run_context(run: FlowRun) -> Iterator[FlowRun]:
    """Optionaler Kontext-Manager fuer runner.py-Autoren.

    Beispiel:
        with run_context(FlowRun.from_env()) as run:
            ...

    Der Kontext-Manager uebernimmt:
      - automatisches `start()`
      - sauberes `finish()` am Ende
      - Sonderbehandlung fuer FlowStopped → status='paused'/'cancelled'
      - bei anderen Exceptions → status='failed' mit Traceback

    Wer das nicht nutzt, muss `start()`/`finish()` selbst rufen
    (bzw. `runner_host` kuemmert sich, wenn das Skript via runpy laeuft).
    """
    try:
        run.start()
        yield run
        run.finish(STATUS_DONE)
    except FlowStopped as stopped:
        reason = str(stopped) or "stopped"
        status = STATUS_CANCELLED if "cancel" in reason else STATUS_PAUSED
        run.finish(status)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        run.fail(err)
        raise
