"""Per-Projekt-asyncio.Lock fuer Turn-Koordination.

Warum
-----
Ein Projekt hat **genau einen aktiven Chat-Thread** (Migration 006: eine
`foundry_response_id` pro Projekt). Wenn zwei Turns gleichzeitig gegen
diesen Thread laufen, zerschiesst sich die Conversation-Kette (zwei
Parallel-Turns mit demselben `previous_response_id` -> Foundry-Fehler
'No tool output found for function call ...').

Dieses Modul gibt Code-Pfaden, die einen Turn starten wollen, einen
gemeinsamen Lock pro Slug:

  - Der User-WebSocket-Handler haelt ihn waehrend seines run_turn.
  - Der Notification-Watcher haelt ihn waehrend seines run_system_turn.

Ergebnis: wenn der User gerade tippt, wartet der System-Trigger bis
sein Turn fertig ist. Wenn ein System-Trigger laeuft, wartet ein frisch
eintreffender User-Input bis der System-Turn fertig ist.

Implementation notes
--------------------
- asyncio.Lock ist event-loop-gebunden. In FastAPI-unter-uvicorn gibt
  es einen Loop pro Prozess; alle WebSocket-Handler + die Lifespan-Tasks
  laufen auf diesem Loop. Damit funktioniert die Koordination.
- Der WebSocket-Handler startet `run_turn` in einem Worker-Thread — der
  Lock wird aber vom Event-Loop gehalten (vor dem Thread-Start) und
  erst nach Thread-Ende freigegeben. So sehen Threads vom Loop aus wie
  ein langes await.
"""

from __future__ import annotations

import asyncio
import logging


logger = logging.getLogger(__name__)


_locks: dict[str, asyncio.Lock] = {}
# Dict-Zugriff selbst ist nicht async-thread-safe — wir schuetzen die
# Lazy-Erzeugung mit einem Meta-Lock. asyncio.Lock() muss zudem im Loop
# konstruiert werden (seit Py 3.10 darf man es ausserhalb bauen, aber
# der Meta-Lock laeuft dann auch im Loop und alles passt).
_meta_lock = asyncio.Lock()


async def project_lock(project_slug: str) -> asyncio.Lock:
    """Liefert den Lock fuer dieses Projekt (erstellt ihn bei Bedarf).

    Verwendung::

        lock = await project_lock("anlage-musterstadt")
        async with lock:
            ...  # mein Turn laeuft, andere Turns fuer dasselbe Projekt warten
    """
    async with _meta_lock:
        lock = _locks.get(project_slug)
        if lock is None:
            lock = asyncio.Lock()
            _locks[project_slug] = lock
    return lock


def drop_project_lock(project_slug: str) -> None:
    """Entfernt den Lock (nur fuer Tests/Cleanup).

    Im normalen Produktionsbetrieb wird der Lock nie entfernt — das
    ist ok, weil pro Projekt maximal ein Lock-Objekt im Speicher liegt
    und das Ding <1kB ist.
    """
    _locks.pop(project_slug, None)
