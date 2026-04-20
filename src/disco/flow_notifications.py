"""Backend-seitige Verarbeitung von Flow-Notifications.

Das Zusammenspiel im Ueberblick
-------------------------------

1. **Worker** (bew/flows/sdk.py) legt Notifications in `agent_flow_notifications`
   ab, sobald das erste/zweite/halbe Item fertig ist, Heartbeat faellig ist,
   oder der Run Status wechselt (start/done/failed).

2. **Watcher-Loop** hier wird vom FastAPI-Lifespan periodisch (alle 3s)
   gerufen. Er iteriert alle Projekte, holt offene Notifications
   (processed_at IS NULL), baut fuer jede einen Trigger-Kontext und
   startet einen System-Turn gegen den AgentService — pro Projekt unter
   dem gleichen asyncio.Lock wie ein User-Turn, damit beide sich nicht
   ueberholen.

3. **AgentService.run_system_turn** fuehrt den Turn aus; Events landen
   via `ws_registry.broadcast(slug, event)` bei allen offenen Tabs fuer
   dieses Projekt. Wenn kein Tab offen ist, wird der Turn trotzdem aus-
   gefuehrt und die Nachricht ist beim naechsten Oeffnen in der History.

4. Nach erfolgreichem Turn (oder ueber-springbarem No-Op-Fall) wird die
   Notification als processed_at = datetime('now') markiert.

Idempotenz
----------
- Notifications werden VOR dem Turn auf processed_at gesetzt — so
  passiert ein System-Turn auch bei Crash zwischen processed_at und
  run_system_turn nicht doppelt. Der Preis: wenn der Turn selbst scheitert,
  wird die Notification trotzdem als erledigt markiert. Das ist ok —
  der Heartbeat kommt eh in 1 min wieder.
- Gleichzeitige Verarbeitung derselben Notification durch zwei Prozesse:
  UPDATE processed_at WHERE processed_at IS NULL garantiert, dass nur
  einer gewinnt.

Was der Watcher NICHT tut
-------------------------
- Kein fein-granulares Error-Handling pro Projekt. Wenn ein Projekt
  hakt, wird das gelogged und der naechste Iteration geht trotzdem weiter.
- Kein Broadcast an User, der das Projekt nicht geoffnet hat. Der Chat
  liegt in chat_messages, er sieht ihn beim naechsten Oeffnen.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from .config import settings


logger = logging.getLogger(__name__)


# Maximale Anzahl Notifications, die pro Iteration pro Projekt abgearbeitet
# werden — schuetzt vor Storm-Situationen. Mehrere Hundert Notifications
# am Stueck sind ein Bug im Runner, kein legitimer Zustand.
_MAX_NOTIFICATIONS_PER_TICK = 5


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
    """Holt offene Notifications aus einem Projekt und verarbeitet sie."""
    pending = _fetch_pending_notifications(db_path, limit=_MAX_NOTIFICATIONS_PER_TICK)
    if not pending:
        return

    for notif in pending:
        notif_id = notif["id"]
        # Notification sofort als verarbeitet markieren (CLAIM). Verhindert
        # Doppel-Verarbeitung, falls zwei Watcher laufen oder der Turn
        # scheitert und wir re-triggern.
        claimed = _claim_notification(db_path, notif_id)
        if not claimed:
            # Hat schon ein anderer Watcher gegriffen — weiter
            continue

        try:
            await _handle_notification(project_slug, db_path, notif)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Notification %s (kind=%s, run_id=%s) fuer Projekt %s fehlgeschlagen",
                notif_id,
                notif.get("kind"),
                notif.get("run_id"),
                project_slug,
            )


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
    if kind == "status_change":
        snap = context.get("notification", {}).get("snapshot", {})
        old = snap.get("old_status", "?")
        new = snap.get("new_status", status)
        return f"Status-Wechsel Run #{run_id} ({flow}): {old} -> {new}"
    if kind == "done":
        return f"Run #{run_id} fertig ({flow}, {done}/{total}, failed={failed})"
    if kind == "failed":
        return f"Run #{run_id} FEHLGESCHLAGEN ({flow}, {done}/{total}, failed={failed})"
    return f"System-Trigger {kind} — Run #{run_id}"


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
