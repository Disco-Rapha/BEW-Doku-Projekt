"""Backend-seitige Verarbeitung von Flow-Notifications.

Das Zusammenspiel im Ueberblick
-------------------------------

1. **Worker** (disco/flows/sdk.py) legt Notifications in
   `agent_flow_notifications` ab, wenn der Run seinen Status wechselt
   (pending → running, running → done/failed) oder ein Heartbeat/Item-
   Fortschritt fuer interne Zwecke markiert werden soll.

2. **Watcher-Loop** hier wird vom FastAPI-Lifespan periodisch (alle 3 s)
   gerufen (`process_pending_notifications`). Pro Projekt:
     a) Offene Notifications aus `agent_flow_notifications` einsammeln
        (processed_at IS NULL).
     b) `_plan_notifications` entscheidet pro Run, ob ein Turn ausgeloest
        wird (Start / End / silence — siehe Trigger-Modell-Kommentar
        weiter unten).
     c) Zeitbasierte Zwischen-Checks fuer laufende Runs
        (`_check_scheduled_checkpoints`) — feuert synthetische Turns
        nach einem festen Plan, unabhaengig von Worker-Events.

3. **AgentService.run_system_turn** fuehrt jeden Turn aus; Events landen
   via `ws_registry.broadcast(slug, event)` bei allen offenen Tabs fuer
   dieses Projekt. Wenn kein Tab offen ist, wird der Turn trotzdem aus-
   gefuehrt und die Nachricht ist beim naechsten Oeffnen in der History.

4. Nach erfolgreichem (oder fehlgeschlagenem) Turn wird die jeweilige
   DB-Notification als `processed_at = datetime('now')` markiert.
   Synthetische Zwischen-Checks haben keine DB-Zeile — der Zaehler
   lebt in `_checkpoint_idx` im Prozess-Speicher.

Idempotenz
----------
- Notifications werden VOR dem Turn auf processed_at gesetzt — so
  passiert ein System-Turn auch bei Crash zwischen processed_at und
  run_system_turn nicht doppelt. Der Preis: wenn der Turn selbst
  scheitert, wird die Notification trotzdem als erledigt markiert.
  Das End-Event kommt bei done/failed nur genau einmal — der Fehler
  muss im Log gesucht werden.
- Gleichzeitige Verarbeitung derselben Notification durch zwei
  Prozesse: UPDATE processed_at WHERE processed_at IS NULL garantiert,
  dass nur einer gewinnt.

Was der Watcher NICHT tut
-------------------------
- Kein fein-granulares Error-Handling pro Projekt. Wenn ein Projekt
  hakt, wird das gelogged und der naechste Iteration geht trotzdem
  weiter.
- Kein Broadcast an User, der das Projekt nicht geoffnet hat. Der Chat
  liegt in chat_messages, er sieht die System-Turn-Zusammenfassung beim
  naechsten Oeffnen.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings


logger = logging.getLogger(__name__)


# Maximale Anzahl Notifications, die pro Iteration pro Projekt abgearbeitet
# werden — schuetzt vor Storm-Situationen. Mehrere Hundert Notifications
# am Stueck sind ein Bug im Runner, kein legitimer Zustand.
_MAX_NOTIFICATIONS_PER_TICK = 20


# Einfaches Trigger-Modell (Stand April 2026)
# -------------------------------------------
# Disco kriegt pro Run genau drei Sorten von Turns:
#
#   1. START  — genau EIN Turn, wenn der Run in "running" wechselt. Mit
#               _INITIAL_GRACE_SEC Verzoegerung, damit Schnell-Runs (die
#               in < 8 s fertig werden) nur das END-Event sehen, nicht
#               START + END separat.
#
#   2. ZWISCHEN-CHECKS — nach einem festen Zeitplan (siehe _CHECKPOINT_…),
#               gerechnet ab `started_at` des Runs. Wird vom Watcher als
#               synthetische Notification (kind="scheduled_check") emittiert,
#               landet NICHT in der DB, nur im Turn.
#
#   3. END    — Terminal-Notification (done/failed). Immer sofort,
#               silenced alle anderen pending Events der gleichen Gruppe.
#
# Alle anderen Notifications (first_item, second_item, half, heartbeat)
# werden stumm als processed markiert — kein Turn, kein UI-Event. Die
# entsprechende Information ist in den Zwischen-Checks bzw. im End-Turn
# mit drin (Disco liest den aktuellen Run-Status live aus der DB).
_TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled"})
_TERMINAL_KINDS = frozenset({"done", "failed"})

# Initial-Grace-Period: Bevor der Start-Turn fuer einen neuen Run gefeuert
# wird, muss der aelteste pending status_change-Event mindestens so alt
# sein. Ziel: schnelle Runs (z.B. 4 s von status_change bis done) sollen
# EINEN Turn am Ende ausloesen, statt zwei (start + end). Terminal-Events
# ignorieren diese Wartezeit (siehe Regel 3 oben).
_INITIAL_GRACE_SEC = 8.0

# Zeitplan fuer Zwischen-Checks — Intervalle ab `started_at` des Runs:
#   Check 1: bei  60 s (nach 1 min)
#   Check 2: bei 360 s (nach +5 min → insgesamt 6 min)
#   Check 3: bei 960 s (nach +10 min → insgesamt 16 min)
#   Check 4: bei 2160 s (nach +20 min → insgesamt 36 min)
#   Check 5: bei 4560 s (nach +40 min → insgesamt 76 min)
#   danach : jede Stunde (3600 s zusaetzlich)
_CHECKPOINT_INTERVALS_SEC: tuple[float, ...] = (60.0, 300.0, 600.0, 1200.0, 2400.0)
_HOURLY_INTERVAL_SEC = 3600.0

# In-Memory-State — ueberlebt keinen Prozess-Restart. Das ist ok: bei einem
# Restart wird ein laufender Run beim naechsten Checkpoint-Tick "adoptiert"
# (siehe _check_scheduled_checkpoints), d.h. wir ueberspringen die verpassten
# Checkpoints und rechnen ab dem aktuellen Alter weiter.
_start_turn_done: set[int] = set()
_checkpoint_idx: dict[int, int] = {}


async def process_pending_notifications() -> None:
    """Eine Iteration des Watcher-Loops.

    Iteriert alle Projekte mit data.db, verarbeitet bis zu
    _MAX_NOTIFICATIONS_PER_TICK offene Notifications pro Projekt.
    """
    projects_dir = settings.projects_dir
    if not projects_dir.exists():
        return

    for project_path in sorted(projects_dir.iterdir()):
        if not project_path.is_dir():
            continue
        db_path = project_path / "data.db"
        if not db_path.exists():
            continue
        try:
            await _process_project(project_path.name, db_path)
        except Exception:  # noqa: BLE001
            # Ein fehlerhaftes Projekt darf den Watcher nicht stoppen —
            # andere Projekte sollen weiter bedient werden.
            logger.exception(
                "Notification-Processing fuer Projekt %s fehlgeschlagen",
                project_path.name,
            )


async def _process_project(project_slug: str, db_path: Path) -> None:
    """Holt offene Notifications aus einem Projekt und verarbeitet sie.

    Ablauf:
      1. Pending Notifications holen, pro run_id gruppieren und durch
         `_plan_notifications` auf Start/End/silence reduzieren
         (siehe dortige Doc).
      2. Plan abarbeiten: primary-Notifications feuern Turns, silenced
         werden stumm als processed markiert.
      3. Zusaetzlich: Checkpoint-Loop fuer laufende Runs
         (`_check_scheduled_checkpoints`). Emittiert synthetische
         scheduled_check-Events nach dem festen Zeitplan.
    """
    pending = _fetch_pending_notifications(db_path, limit=_MAX_NOTIFICATIONS_PER_TICK)
    if pending:
        plan = _plan_notifications(db_path, pending)

        for entry in plan:
            primary = entry["primary"]
            silenced = entry["silenced"]

            # Silenced Notifications stumm als processed markieren — kein
            # Turn, kein UI-Event. Ihre Info ist entweder obsolet (Run
            # bereits terminal) oder wird durch End-Turn bzw. Checkpoint-
            # Turn spaeter ohnehin abgedeckt (Disco liest live).
            for sq in silenced:
                claimed_sq = _claim_notification(db_path, sq["id"])
                if claimed_sq:
                    logger.info(
                        "Notification %s (kind=%s, run_id=%s) silenced "
                        "(plan: primary=%s)",
                        sq["id"],
                        sq.get("kind"),
                        sq.get("run_id"),
                        primary.get("kind") if primary else "none",
                    )

            if primary is None:
                continue

            claimed = _claim_notification(db_path, primary["id"])
            if not claimed:
                continue

            try:
                await _handle_notification(project_slug, db_path, primary)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Notification %s (kind=%s, run_id=%s) fuer Projekt %s fehlgeschlagen",
                    primary["id"],
                    primary.get("kind"),
                    primary.get("run_id"),
                    project_slug,
                )

    # Zwischen-Checks: laufen unabhaengig von pending Notifications, nur
    # zeitbasiert. Auch aufgerufen wenn keine pending Notifications da
    # sind — sonst wuerden Runs ohne Worker-Events (lange stille Phase)
    # kein Checkpoint abbekommen.
    try:
        await _check_scheduled_checkpoints(project_slug, db_path)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Scheduled-Checkpoint-Check fuer Projekt %s fehlgeschlagen",
            project_slug,
        )


def _plan_notifications(
    db_path: Path,
    pending: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Entscheidet pro Run, welcher pending Event einen Turn ausloest.

    Schema (siehe _CHECKPOINT_INTERVALS_SEC-Kommentar):
      - END  (done/failed in der Gruppe) → primary=End, silence Rest.
        `_start_turn_done` und `_checkpoint_idx` werden fuer den Run
        aufgeraeumt.
      - Run ist laut DB schon terminal, aber kein End-Event pending →
        alle Events der Gruppe silencen (der End-Turn wurde in einem
        frueheren Tick schon gefahren, Zwischenstaende sind obsolet).
      - START  (`_start_turn_done` enthaelt den Run nicht, status_change
        in der Gruppe, aeltester Event ≥ _INITIAL_GRACE_SEC alt) →
        primary=status_change, silence Rest, Run als "gestartet" markiert,
        `_checkpoint_idx[run_id]=0`.
      - START noch in Grace-Period → warten, Events bleiben pending.
      - Alles andere (first_item/second_item/half/heartbeat/Folge-
        status_change) → silence. Kein Turn.

    Returns:
        Liste von {"primary": notif | None, "silenced": [notifs]}.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    by_run: dict[int, list[dict[str, Any]]] = {}
    for n in pending:
        rid = n.get("run_id")
        if rid is None:
            continue
        by_run.setdefault(int(rid), []).append(n)

    run_statuses = _fetch_run_statuses(db_path, list(by_run.keys()))

    plan: list[dict[str, Any]] = []
    for run_id, notifs in by_run.items():
        # 1) Gibt es einen End-Event? Dann gewinnt er — immer und sofort.
        end_event = _find_first(notifs, _TERMINAL_KINDS)
        if end_event is not None:
            silenced = [n for n in notifs if n is not end_event]
            plan.append({"primary": end_event, "silenced": silenced})
            _start_turn_done.discard(run_id)
            _checkpoint_idx.pop(run_id, None)
            continue

        # 2) Run ist laut DB schon terminal (cancelled/done/failed von
        #    einem frueheren Tick), pending sind nur noch Zwischen-Events
        #    → alles silencen, State aufraeumen.
        if run_statuses.get(run_id) in _TERMINAL_STATUSES:
            plan.append({"primary": None, "silenced": notifs})
            _start_turn_done.discard(run_id)
            _checkpoint_idx.pop(run_id, None)
            continue

        # 3) Run laeuft noch. Start-Turn schon gefahren?
        if run_id in _start_turn_done:
            # Ja → alles silencen, Checkpoints macht der Checkpoint-Loop.
            plan.append({"primary": None, "silenced": notifs})
            continue

        # 4) Noch kein Start-Turn. Haben wir einen status_change in der
        #    Gruppe? Ohne den feuern wir nichts — wir warten auf ihn.
        start_event = _find_first_by_kind(notifs, "status_change")
        if start_event is None:
            plan.append({"primary": None, "silenced": notifs})
            continue

        # 5) Grace-Period: aeltester pending Event (nicht nur der
        #    status_change) muss alt genug sein. So kriegen Schnell-Runs,
        #    die innerhalb <8 s durchlaufen, ihr END-Event eingeschleust
        #    (greift dann Regel 1 im naechsten Tick).
        oldest_age = _oldest_age_sec(notifs, now)
        if oldest_age < _INITIAL_GRACE_SEC:
            logger.debug(
                "Run %s: Start-Grace aktiv (aeltester Event %.1fs von %.1fs)",
                run_id, oldest_age, _INITIAL_GRACE_SEC,
            )
            continue

        # 6) Start-Turn fuer diesen Run.
        silenced = [n for n in notifs if n is not start_event]
        plan.append({"primary": start_event, "silenced": silenced})
        _start_turn_done.add(run_id)
        _checkpoint_idx[run_id] = 0

    return plan


async def _check_scheduled_checkpoints(project_slug: str, db_path: Path) -> None:
    """Emittiert zeitbasierte Zwischen-Checks fuer laufende Runs.

    Der Plan (siehe _CHECKPOINT_INTERVALS_SEC) tickt ab `started_at`.
    Fuer jeden Run wird in `_checkpoint_idx` gespeichert, wie viele
    Checkpoints schon gefahren wurden. Wenn das Alter (now - started_at)
    das fuer den naechsten Index faellige Alter ueberschreitet, feuern
    wir einen synthetischen scheduled_check-Event (nicht in der DB —
    direkt in `_handle_notification`).

    Recovery nach Watcher-Restart: Runs ohne `_start_turn_done`-Eintrag
    werden "adoptiert", d.h. der erste Eintrag wird auf den letzten
    bereits verstrichenen Index gesetzt — verpasste Checkpoints werden
    nicht nachgeholt, der naechste faellige Check wird normal gefeuert.
    """
    running = _fetch_running_runs(db_path)
    running_ids = {rid for rid, _ in running}

    # Aufraeumen: Runs, die wir noch tracken, aber die laut DB nicht mehr
    # laufen (done/failed/cancelled), aus dem Memory-State entfernen. Das
    # passiert normalerweise schon in `_plan_notifications`, aber wenn ein
    # Run ohne Terminal-Notification in einen terminalen Zustand wechselt
    # (z.B. externer Cancel ohne failed-Notif), koennten die Eintraege
    # sonst zombie bleiben.
    orphans = (set(_start_turn_done) | set(_checkpoint_idx.keys())) - running_ids
    for orphan in orphans:
        _start_turn_done.discard(orphan)
        _checkpoint_idx.pop(orphan, None)

    if not running:
        return
    now = datetime.now(timezone.utc)

    for run_id, started_at_str in running:
        started_at = _parse_created_at(started_at_str)
        if started_at is None:
            continue
        age = (now - started_at).total_seconds()

        if run_id not in _start_turn_done:
            # Kein Start-Turn-Flag: zwei moegliche Gruende.
            #
            #  (a) Pending status_change-Notif existiert noch und
            #      _plan_notifications haelt sie in der Grace-Period.
            #      Dann NICHT adoptieren — wir warten auf den normalen
            #      Start-Turn, damit der User ihn im Chat sieht.
            #
            #  (b) Watcher-Neustart: Run laeuft schon, aber die
            #      Start-Notif ist langst processed. Dann adoptieren
            #      und verpasste Checkpoints ueberspringen.
            if _has_pending_status_change(db_path, run_id):
                continue
            _start_turn_done.add(run_id)
            _checkpoint_idx[run_id] = _idx_for_age(age)
            logger.info(
                "Run %s adoptiert (age=%.0fs, startIdx=%d)",
                run_id, age, _checkpoint_idx[run_id],
            )
            continue

        idx = _checkpoint_idx.get(run_id, 0)
        next_due_age = _checkpoint_age_for_idx(idx + 1)
        if age < next_due_age:
            continue

        # Checkpoint faellig — synthetische Notification bauen und
        # direkt an _handle_notification uebergeben. Landet nicht in
        # der DB (id=None), also auch kein _claim_notification noetig.
        synth = {
            "id": None,
            "run_id": run_id,
            "kind": "scheduled_check",
            "context_json": None,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "context": {
                "checkpoint_idx": idx + 1,
                "age_sec": age,
            },
        }
        _checkpoint_idx[run_id] = idx + 1
        logger.info(
            "Run %s: scheduled_check #%d (age=%.0fs)",
            run_id, idx + 1, age,
        )
        try:
            await _handle_notification(project_slug, db_path, synth)
        except Exception:  # noqa: BLE001
            logger.exception(
                "scheduled_check fuer Run %s in Projekt %s fehlgeschlagen",
                run_id, project_slug,
            )


def _checkpoint_age_for_idx(idx: int) -> float:
    """Alter (in Sekunden ab started_at) ab dem Checkpoint #idx faellig ist.

    idx ist 1-basiert.
      idx=1 →   60 s
      idx=2 →  360 s
      idx=3 →  960 s
      idx=4 → 2160 s
      idx=5 → 4560 s
      idx=k (k≥6) → 4560 + (k-5) * 3600
    """
    if idx <= 0:
        return 0.0
    cum = 0.0
    for i in range(min(idx, len(_CHECKPOINT_INTERVALS_SEC))):
        cum += _CHECKPOINT_INTERVALS_SEC[i]
    if idx > len(_CHECKPOINT_INTERVALS_SEC):
        cum += (idx - len(_CHECKPOINT_INTERVALS_SEC)) * _HOURLY_INTERVAL_SEC
    return cum


def _idx_for_age(age_sec: float) -> int:
    """Hoechster Checkpoint-Index, der fuer diesen age_sec bereits erreicht ist.

    Gegenstueck zu `_checkpoint_age_for_idx`: wenn der Run schon 400 s
    laeuft, ist Checkpoint 1 (60 s) erreicht, aber Checkpoint 2 (360 s)
    auch — also gibt die Funktion 2 zurueck. Wird beim Watcher-Restart
    benutzt, um verpasste Checkpoints nicht retroaktiv zu feuern.
    """
    if age_sec <= 0:
        return 0
    idx = 0
    while _checkpoint_age_for_idx(idx + 1) <= age_sec:
        idx += 1
        # Safety: falls _HOURLY_INTERVAL_SEC 0 oder negativ wird (Defekt).
        if idx > 10_000:
            break
    return idx


def _find_first(notifs: list[dict[str, Any]], kinds: frozenset[str]) -> dict[str, Any] | None:
    """Ersten Event finden, dessen kind in `kinds` enthalten ist (None sonst)."""
    for n in notifs:
        if n.get("kind") in kinds:
            return n
    return None


def _find_first_by_kind(notifs: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    """Ersten Event mit genau diesem kind finden (None sonst)."""
    for n in notifs:
        if n.get("kind") == kind:
            return n
    return None


def _parse_created_at(s: str | None) -> datetime | None:
    """Parst eine SQLite-`datetime('now')`-Zeichenkette als UTC-datetime.

    SQLite liefert `YYYY-MM-DD HH:MM:SS` ohne Zeitzone (ist aber UTC).
    Wir legen die Zeitzone explizit drauf, damit Arithmetik mit
    `datetime.now(timezone.utc)` konsistent bleibt.
    """
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("T", " "))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _oldest_age_sec(notifs: list[dict[str, Any]], now: datetime) -> float:
    """Alter (in Sekunden) des aeltesten Events aus einer Notifications-Gruppe.

    Liefert 0.0, wenn kein created_at parsebar ist — dann laeuft die
    Grace-Period leer und der Event wird normal behandelt.
    """
    ages: list[float] = []
    for n in notifs:
        created = _parse_created_at(n.get("created_at"))
        if created is not None:
            ages.append((now - created).total_seconds())
    return max(ages) if ages else 0.0


def _fetch_run_statuses(db_path: Path, run_ids: list[int]) -> dict[int, str]:
    """Liest den aktuellen Status der angegebenen Runs aus der Projekt-DB."""
    if not run_ids:
        return {}
    conn = _connect(db_path)
    try:
        placeholders = ",".join("?" * len(run_ids))
        rows = conn.execute(
            f"SELECT id, status FROM agent_flow_runs WHERE id IN ({placeholders})",
            run_ids,
        ).fetchall()
        return {int(r["id"]): r["status"] for r in rows}
    finally:
        conn.close()


def _has_pending_status_change(db_path: Path, run_id: int) -> bool:
    """Prueft, ob eine unprocessed status_change-Notif fuer den Run existiert.

    Wird beim Adoptions-Entscheid genutzt (`_check_scheduled_checkpoints`):
    solange eine pending Start-Notif da ist, wartet der Checkpoint-Loop,
    damit `_plan_notifications` den normalen Start-Turn fahren kann.
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT 1 FROM agent_flow_notifications
             WHERE run_id = ? AND kind = 'status_change'
               AND processed_at IS NULL
             LIMIT 1
            """,
            (int(run_id),),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _fetch_running_runs(db_path: Path) -> list[tuple[int, str]]:
    """Liste aller aktuell laufenden Runs — (id, started_at) pro Eintrag.

    Returns []:
      - wenn agent_flow_runs nicht existiert (alte Projekt-DB)
      - wenn kein Run auf `running` steht
    """
    conn = _connect(db_path)
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_flow_runs'"
        ).fetchone()
        if not has_table:
            return []
        rows = conn.execute(
            """
            SELECT id, started_at
              FROM agent_flow_runs
             WHERE status = 'running' AND started_at IS NOT NULL
            """
        ).fetchall()
        return [(int(r["id"]), r["started_at"]) for r in rows]
    finally:
        conn.close()


async def _handle_notification(
    project_slug: str,
    db_path: Path,
    notif: dict[str, Any],
) -> None:
    """Baut Trigger-Kontext, startet System-Turn, streamt Events."""
    run_id = notif["run_id"]
    kind = notif["kind"]

    # Trigger-Kontext zusammenschnueren — Live-Daten, nicht nur die
    # Snapshot-Werte aus der Notification-Zeile.
    context = _build_trigger_context(db_path, run_id, notif)
    if context is None:
        logger.info(
            "Notification %s (run_id=%s, kind=%s) ohne Kontext — uebersprungen",
            notif.get("id"),
            run_id,
            kind,
        )
        return

    # Summary fuer chat_messages (role='system') + Foundry-Developer-Block
    summary = _build_summary(kind, context)
    context_text = _render_context_as_text(context)

    # Per-Projekt-Lock: waechst aus agent/locks.py. Wenn der User gerade
    # tippt, warten wir bis sein Turn fertig ist.
    from .agent.core import get_agent_service
    from .agent.locks import project_lock
    from .api import ws_registry

    lock = await project_lock(project_slug)
    async with lock:
        svc = get_agent_service()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        SENTINEL = object()

        def _worker() -> None:
            try:
                for event in svc.run_system_turn(
                    project_slug=project_slug,
                    trigger_kind=kind,
                    trigger_summary=summary,
                    trigger_context=context_text,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, event.to_dict())
            except Exception as exc:  # noqa: BLE001
                logger.exception("run_system_turn gescheitert")
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "type": "error",
                        "message": f"System-Turn-Fehler: {exc}",
                    },
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

        # Worker-Thread starten — die sync-AgentService-Iteration laeuft
        # dort, der Event-Loop konsumiert die Queue asynchron.
        import threading
        threading.Thread(target=_worker, daemon=True).start()

        # Banner an offene WebSockets: zeigt der UI, dass jetzt ein
        # System-Trigger-Turn kommt (fuer optische Abgrenzung von User-Turns).
        await ws_registry.broadcast(
            project_slug,
            {
                "type": "system_trigger_start",
                "kind": kind,
                "run_id": run_id,
                "summary": summary,
            },
        )

        while True:
            ev = await queue.get()
            if ev is SENTINEL:
                break
            # Die gleichen Event-Typen wie bei User-Turns — die UI nutzt
            # denselben Renderer.
            await ws_registry.broadcast(project_slug, ev)

        await ws_registry.broadcast(
            project_slug,
            {"type": "system_trigger_end", "kind": kind, "run_id": run_id},
        )


# -------------------------------------------------------------------------
# DB-Helfer
# -------------------------------------------------------------------------


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_pending_notifications(db_path: Path, limit: int) -> list[dict[str, Any]]:
    """Holt offene Notifications aus einem Projekt.

    Returns []:
      - wenn agent_flow_notifications nicht existiert (alte Projekt-DB)
      - wenn nichts offen ist
    """
    conn = _connect(db_path)
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_flow_notifications'"
        ).fetchone()
        if not has_table:
            return []
        rows = conn.execute(
            """
            SELECT id, run_id, kind, context_json, created_at
              FROM agent_flow_notifications
             WHERE processed_at IS NULL
             ORDER BY created_at, id
             LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("context_json"):
                try:
                    d["context"] = json.loads(d["context_json"])
                except (json.JSONDecodeError, TypeError):
                    d["context"] = {}
            else:
                d["context"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def _claim_notification(db_path: Path, notif_id: int) -> bool:
    """Markiert die Notification als verarbeitet.

    Returns True, wenn WIR sie bekommen haben (Update hat genau eine Zeile
    getroffen). False, wenn ein anderer Watcher schneller war.
    """
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            UPDATE agent_flow_notifications
               SET processed_at = datetime('now')
             WHERE id = ? AND processed_at IS NULL
            """,
            (int(notif_id),),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


# -------------------------------------------------------------------------
# Trigger-Kontext-Bau
# -------------------------------------------------------------------------


def _build_trigger_context(
    db_path: Path,
    run_id: int,
    notif: dict[str, Any],
) -> dict[str, Any] | None:
    """Sammelt Live-Daten fuer den Trigger-Kontext.

    Output-Struktur (wird als JSON an Foundry geschickt, plus human-readable
    Fassung):

        {
            "run": { ... Run-Info ... },
            "notification": {"kind": ..., "created_at": ..., "context": ...},
            "recent_items": [ ... letzte N Items mit output_json ... ],
            "recent_logs": "letzte 20 Log-Zeilen",
            "flow_readme": "Ausschnitt der README"  (optional),
        }

    Returns None, wenn der Run nicht gefunden wird (wurde geloescht o.ae.).
    """
    conn = _connect(db_path)
    try:
        run_row = conn.execute(
            """
            SELECT id, flow_name, title, status, config_json,
                   total_items, done_items, failed_items, skipped_items,
                   total_cost_eur, total_tokens_in, total_tokens_out,
                   pause_requested, cancel_requested, error,
                   created_at, started_at, finished_at,
                   next_heartbeat_at, last_heartbeat_interval_sec
              FROM agent_flow_runs
             WHERE id = ?
            """,
            (int(run_id),),
        ).fetchone()
        if run_row is None:
            return None
        run = dict(run_row)
        try:
            run["config"] = json.loads(run.pop("config_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            run["config"] = {}

        # Letzte Items (done/failed) — gibt Disco ein Gefuehl dafuer, was
        # der Runner gerade produziert. 5 ist genug fuer „passt der Output
        # zu meiner Erwartung?".
        recent_items_rows = conn.execute(
            """
            SELECT id, input_ref, status, attempts, output_json, error,
                   created_at, started_at, finished_at
              FROM agent_flow_run_items
             WHERE run_id = ? AND status IN ('done','failed','skipped')
             ORDER BY id DESC
             LIMIT 5
            """,
            (int(run_id),),
        ).fetchall()
        recent_items: list[dict[str, Any]] = []
        for r in recent_items_rows:
            d = dict(r)
            raw = d.pop("output_json", None)
            if raw:
                try:
                    d["output"] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    d["output"] = {"_raw": raw[:500]}
            recent_items.append(d)
        # Chronologisch anzeigen: aeltestes zuerst
        recent_items.reverse()

        # Flow-README-Excerpt (erklaert Disco, was dieser Flow tun sollte)
        flow_readme = _load_flow_readme(db_path.parent, run["flow_name"])

        # Die letzten ~20 Log-Zeilen aus dem Worker-Log (sehr hilfreich, um
        # Fehler ohne Context-Switch zu sehen).
        recent_logs = _load_recent_logs(db_path.parent, int(run_id), max_lines=20)

        return {
            "run": run,
            "notification": {
                "kind": notif.get("kind"),
                "created_at": notif.get("created_at"),
                "snapshot": notif.get("context") or {},
            },
            "recent_items": recent_items,
            "recent_logs": recent_logs,
            "flow_readme": flow_readme,
        }
    finally:
        conn.close()


def _load_flow_readme(project_root: Path, flow_name: str) -> str | None:
    """Lade die ersten ~60 Zeilen der Flow-README (wenn vorhanden)."""
    readme = project_root / "flows" / flow_name / "README.md"
    if not readme.is_file():
        return None
    try:
        lines = readme.read_text(encoding="utf-8", errors="replace").splitlines()
        excerpt = "\n".join(lines[:60])
        if len(lines) > 60:
            excerpt += f"\n... (+{len(lines) - 60} weitere Zeilen in der README)"
        return excerpt
    except OSError:
        return None


def _load_recent_logs(project_root: Path, run_id: int, max_lines: int) -> str | None:
    """Lade die letzten N Zeilen des Worker-Logs fuer diesen Run."""
    log_file = project_root / ".disco" / "flows" / "runs" / str(run_id) / "log.txt"
    if not log_file.is_file():
        return None
    try:
        # Kleine Datei, einfacher read_text. Fuer grosse Logs waere tail
        # effizienter; in der Praxis sind Worker-Logs bei uns << 1 MB.
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-max_lines:] if len(lines) > max_lines else lines
        return "\n".join(tail)
    except OSError:
        return None


# -------------------------------------------------------------------------
# Rendering: Summary + Foundry-Input-Text
# -------------------------------------------------------------------------


def _build_summary(kind: str, context: dict[str, Any]) -> str:
    """Kurze Headline fuer die UI-Bubble (role='system')."""
    run = context.get("run", {})
    run_id = run.get("id")
    flow = run.get("flow_name", "?")
    done = run.get("done_items", 0)
    failed = run.get("failed_items", 0)
    total = run.get("total_items", 0)
    status = run.get("status", "?")

    if kind == "status_change":
        snap = context.get("notification", {}).get("snapshot", {})
        old = snap.get("old_status", "?")
        new = snap.get("new_status", status)
        return f"Run #{run_id} gestartet ({flow}): {old} -> {new}"
    if kind == "scheduled_check":
        snap = context.get("notification", {}).get("snapshot", {})
        age = snap.get("age_sec")
        if age:
            age_txt = _format_age(age)
            return f"Zwischenstand Run #{run_id} ({flow}, {done}/{total}) — laeuft {age_txt}"
        return f"Zwischenstand Run #{run_id} ({flow}, {done}/{total})"
    if kind == "done":
        return f"Run #{run_id} fertig ({flow}, {done}/{total}, failed={failed})"
    if kind == "failed":
        return f"Run #{run_id} FEHLGESCHLAGEN ({flow}, {done}/{total}, failed={failed})"
    # Legacy-Kinds (first_item/second_item/half/heartbeat) sollten im
    # neuen Trigger-Modell stumm silenced werden. Falls sie doch hier
    # aufschlagen (z.B. alter Code-Pfad), liefern wir eine sinnvolle
    # Fallback-Headline statt leerer Ausgabe.
    if kind == "first_item":
        return f"Erstes Item fertig — Run #{run_id} ({flow}, {done}/{total})"
    if kind == "second_item":
        return f"Zweites Item fertig — Run #{run_id} ({flow}, {done}/{total})"
    if kind == "half":
        return f"Halbzeit — Run #{run_id} ({flow}, {done}/{total})"
    if kind == "heartbeat":
        snap = context.get("notification", {}).get("snapshot", {})
        interval = snap.get("interval_sec")
        hint = f" (Intervall {interval}s)" if interval else ""
        return f"Heartbeat Run #{run_id} ({flow}, {done}/{total}{hint})"
    return f"System-Trigger {kind} — Run #{run_id}"


def _format_age(age_sec: float) -> str:
    """Menschliche Dauer-Darstellung: '45 s', '3 min', '1 h 12 min'."""
    age = max(0.0, float(age_sec))
    if age < 60:
        return f"{int(age)} s"
    if age < 3600:
        return f"{int(age // 60)} min"
    h = int(age // 3600)
    m = int((age % 3600) // 60)
    return f"{h} h {m} min" if m else f"{h} h"


def _render_context_as_text(context: dict[str, Any]) -> str:
    """Formatiert den Trigger-Kontext als Textblock fuer die Foundry-API.

    Wichtig: das landet als `user_text` im run_turn-Call — aber persistiert
    wird in `chat_messages` nur die kurze Summary (role='system'). Der
    volle Text ist nur im Foundry-Turn sichtbar, nicht in der DB.
    """
    run = context.get("run", {})
    notif = context.get("notification", {})
    recent_items = context.get("recent_items") or []
    recent_logs = context.get("recent_logs")
    readme = context.get("flow_readme")

    parts = ["SYSTEM-TRIGGER — Du wurdest vom Flow-Run-Watcher aufgeweckt.", ""]

    parts.append(f"Trigger-Art: {notif.get('kind')}")
    parts.append(f"Erzeugt: {notif.get('created_at')}")

    parts.append("")
    parts.append(
        f"Run #{run.get('id')} ({run.get('flow_name')} — \"{run.get('title') or '-'}\")"
    )
    parts.append(f"  Status      : {run.get('status')}")
    parts.append(
        f"  Items       : total={run.get('total_items')} done={run.get('done_items')} "
        f"failed={run.get('failed_items')} skipped={run.get('skipped_items')}"
    )
    parts.append(f"  Kosten      : {run.get('total_cost_eur'):.4f} EUR")
    parts.append(
        f"  Tokens      : in={run.get('total_tokens_in')} out={run.get('total_tokens_out')}"
    )
    if run.get("config"):
        parts.append(f"  Config      : {json.dumps(run.get('config'), ensure_ascii=False)}")
    if run.get("error"):
        parts.append(f"  Error       : {run.get('error')[:300]}")

    # Erwartung bei Start (aus config, falls der Flow das exponiert)
    expect = run.get("config", {}).get("_expectation") if isinstance(run.get("config"), dict) else None
    if expect:
        parts.append("")
        parts.append(f"Urspruengliche Erwartung:\n  {expect}")

    # Letzte Items
    if recent_items:
        parts.append("")
        parts.append("Letzte verarbeitete Items:")
        for it in recent_items:
            ref = it.get("input_ref")
            st = it.get("status")
            out = it.get("output")
            err = it.get("error")
            head = f"  - [{st}] {ref}"
            parts.append(head)
            if out is not None:
                try:
                    out_txt = json.dumps(out, ensure_ascii=False)
                except TypeError:
                    out_txt = str(out)
                if len(out_txt) > 500:
                    out_txt = out_txt[:500] + "..."
                parts.append(f"      output: {out_txt}")
            if err:
                err_txt = err if len(err) < 300 else err[:300] + "..."
                parts.append(f"      error:  {err_txt}")

    if recent_logs:
        parts.append("")
        parts.append("Letzte Log-Zeilen:")
        parts.append(recent_logs)

    if readme:
        parts.append("")
        parts.append(f"Flow-README (Ausschnitt):\n{readme}")

    parts.append("")
    parts.append(
        "Deine Aufgabe: kurz pruefen, ob das Bild sinnvoll aussieht. "
        "Wenn ja: 1-2 Saetze Status-Update im Chat. Wenn nein: beschreiben "
        "was Dir auffaellt und ggf. flow_pause/flow_cancel aufrufen. "
        "flow_run ist fuer Dich gesperrt — Empfehlung statt Aktion."
    )
    return "\n".join(parts)
