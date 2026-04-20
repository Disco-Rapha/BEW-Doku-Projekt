"""Registry fuer offene WebSocket-Verbindungen pro Projekt.

Hintergrund
-----------
Der WebSocket-Chat `/ws/chat?project=<slug>` ist pro Projekt-Slug
gebunden. Damit der System-Trigger-Watcher (flow_notifications.py)
Events in die offene Oberflaeche pushen kann, muessen wir wissen,
welche Connection(s) gerade zu welchem Projekt gehoeren.

Anforderungen
-------------
- Mehrere Tabs zum selben Projekt erlaubt (N WebSockets pro Slug).
- Registrierung/De-Registrierung ist async-safe — gleiche
  `asyncio.Lock` schuetzt die Slug -> Set[WebSocket]-Map.
- Broadcast ist "best effort": wenn eine WebSocket-send fehlschlaegt
  (z.B. Verbindung zugemacht), wird sie entfernt, aber die anderen
  bekommen trotzdem ihr Event.
- Keine Imports aus anderen App-Modulen — damit sowohl `api.main`
  als auch `flow_notifications` diese Registry benutzen koennen,
  ohne Zirkular-Import.

Verwendung
----------
```
from disco.api.ws_registry import register, unregister, broadcast

async def ws_chat(...):
    await websocket.accept()
    await register(project_slug, websocket)
    try:
        ...
    finally:
        await unregister(project_slug, websocket)
```

Der Watcher-Loop ruft::

    await broadcast(project_slug, {"type": "flow_notification", ...})

und die Event-JSON landet bei allen offenen Tabs fuer diesen Slug.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket


logger = logging.getLogger(__name__)


# Slug -> Set offener WebSocket-Objekte
_connections: dict[str, set[WebSocket]] = {}
_lock = asyncio.Lock()


async def register(project_slug: str, websocket: WebSocket) -> None:
    """Traegt eine neu akzeptierte WebSocket fuer ein Projekt ein."""
    async with _lock:
        _connections.setdefault(project_slug, set()).add(websocket)
    logger.debug(
        "WS-Registry: %s registered (total for slug: %d)",
        project_slug,
        len(_connections.get(project_slug, [])),
    )


async def unregister(project_slug: str, websocket: WebSocket) -> None:
    """Entfernt eine (typischerweise gerade geschlossene) WebSocket."""
    async with _lock:
        bucket = _connections.get(project_slug)
        if bucket is None:
            return
        bucket.discard(websocket)
        if not bucket:
            _connections.pop(project_slug, None)
    logger.debug(
        "WS-Registry: %s unregistered (remaining: %d)",
        project_slug,
        len(_connections.get(project_slug, [])),
    )


def has_listeners(project_slug: str) -> bool:
    """Schneller Check ohne Lock — approximate, aber gut genug fuer
    die Watcher-Entscheidung `kann ich den User live anzeigen?`.

    Wenn False zurueckkommt, heisst das: zum aktuellen Zeitpunkt ist
    kein Tab fuer dieses Projekt offen. Der Watcher kann den System-
    Turn trotzdem ausloesen — die Ergebnisse landen in `chat_messages`,
    beim naechsten Oeffnen sieht der User sie in der History.
    """
    return bool(_connections.get(project_slug))


async def broadcast(project_slug: str, event: dict[str, Any]) -> int:
    """Sendet ein Event-Dict an alle offenen WebSockets fuer dieses Projekt.

    Returns die Anzahl erfolgreich benachrichtigter Connections.

    Fehlerfall: wenn `send_json` auf einer WebSocket wirft (Verbindung
    zugemacht, Netzwerk-Timeout), wird die WebSocket entfernt und das
    Event an die naechste geschickt. Das Event selbst wird beim Fehler
    NICHT erneut gesendet — der Watcher ist idempotent (Notification
    bleibt mit processed_at=NULL, wird beim naechsten Tick versucht).

    Idee: Die Registry ist nicht die einzige Persistenz-Ebene. Der
    chat_messages-Mirror enthaelt alles, was die UI beim Reconnect
    erneut laden muss.
    """
    async with _lock:
        targets = list(_connections.get(project_slug, ()))

    if not targets:
        return 0

    sent = 0
    dead: list[WebSocket] = []
    for ws in targets:
        try:
            await ws.send_json(event)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("Broadcast an WebSocket fehlgeschlagen: %s", exc)
            dead.append(ws)

    if dead:
        async with _lock:
            bucket = _connections.get(project_slug)
            if bucket is not None:
                for ws in dead:
                    bucket.discard(ws)
                if not bucket:
                    _connections.pop(project_slug, None)

    return sent


def snapshot() -> dict[str, int]:
    """Debug-Hilfe: gibt pro Slug die Anzahl offener Verbindungen zurueck.

    Kein Lock — das ist nur fuer Ad-hoc-Introspektion gedacht und
    darf leicht „off by one" sein.
    """
    return {slug: len(conns) for slug, conns in _connections.items()}
