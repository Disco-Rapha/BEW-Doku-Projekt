"""Thread-lokaler Projekt-Kontext fuer Disco-Tools.

Seit Migration 006 ist jeder Chat an genau ein Projekt gebunden
(`project_chat_state.project_slug`). Wenn ein Turn laeuft, wird der Slug
hier per ContextVar gesetzt — Tools lesen ihn ab und scopen ihren Zugriff
auf dieses Projekt (Verzeichnis, DBs, Memory-Dateien im Projekt-Root).

Die Projekt-Daten liegen seit dem 4-Ebenen-Refactor in **zwei** DBs
(siehe `docs/architektur-ebenen.md`):

  - ``datastore.db`` — Ebene 1+2 (Provenance + Content). Read-only aus
    Chat-Sicht. Schreibzugriff nur durch Registry-Tools + Pipelines.
  - ``workspace.db`` — Ebene 3 (Reasoning). Vollzugriff per sqlite_write.

Implementierung via `contextvars.ContextVar`, damit parallele AgentService-
Aufrufe (z.B. zwei Browser-Tabs gleichzeitig) sich gegenseitig nicht stoeren.

Tools fragen ab:
    from .context import get_project_root, get_datastore_db_path, get_workspace_db_path
    root  = get_project_root()          # Path oder None (= Workspace-Root)
    ds_db = get_datastore_db_path()     # Path zur datastore.db oder None
    ws_db = get_workspace_db_path()     # Path zur workspace.db oder None
"""

from __future__ import annotations

import contextvars
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..config import settings
from ..workspace import validate_slug


# Aktiver Projekt-Slug pro async/thread-Kontext.
# None = global (kein Sandbox-Modus, alte Semantik).
_current_project: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "disco_current_project", default=None
)

# Wurde der Turn vom System getriggert (flow_notifications) statt vom User?
# Wird von AgentService.run_system_turn fuer die Dauer des Turns auf True
# gesetzt. Tools, die irreversible/teure Aktionen ausloesen (flow_run-Start),
# duerfen bei True ablehnen — siehe CLAUDE.md „Asymmetric Auto-Action":
# Disco darf autonom cancel/pause, aber NIEMALS neue Runs starten.
_is_system_triggered: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "disco_is_system_triggered", default=False
)


def get_current_project_slug() -> str | None:
    """Gibt den Slug des aktiven Projekts zurueck, oder None."""
    return _current_project.get()


def is_system_triggered() -> bool:
    """True, wenn der aktive Turn vom System (nicht vom User) gestartet wurde."""
    return _is_system_triggered.get()


def get_project_root() -> Path | None:
    """Pfad des aktiven Projekt-Verzeichnisses, oder None."""
    slug = _current_project.get()
    if not slug:
        return None
    return settings.projects_dir / slug


def get_datastore_db_path() -> Path | None:
    """Pfad der aktiven ``datastore.db`` (Ebene 1+2), oder None."""
    root = get_project_root()
    if root is None:
        return None
    return root / "datastore.db"


def get_workspace_db_path() -> Path | None:
    """Pfad der aktiven ``workspace.db`` (Ebene 3), oder None."""
    root = get_project_root()
    if root is None:
        return None
    return root / "workspace.db"


def connect_datastore_rw() -> sqlite3.Connection:
    """Oeffnet die ``datastore.db`` des aktiven Projekts read/write.

    Nur fuer Registry-Tools und Pipelines, die neue Provenance- oder
    Content-Eintraege in Ebene 1+2 anlegen duerfen. Aus dem Chat-Pfad
    (sqlite_query / sqlite_write) bleibt die Datei read-only — dort
    wird sie als ATTACH-DB mit ``mode=ro`` eingebunden.

    Raises:
        RuntimeError: Kein aktives Projekt.
    """
    ds_path = get_datastore_db_path()
    if ds_path is None:
        raise RuntimeError(
            "Kein aktives Projekt — datastore.db nur im Projekt-Kontext erreichbar."
        )
    ds_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ds_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def use_project(slug: str | None) -> Iterator[None]:
    """Context-Manager fuer einen Tool-Block in einem Projekt-Sandbox.

    Beispiel:
        with use_project("anlage-musterstadt"):
            # alle Tool-Aufrufe sind jetzt projekt-scoped
            ...

    slug=None loescht den Kontext (zurueck auf global).
    """
    if slug is not None:
        slug = validate_slug(slug)
    token = _current_project.set(slug)
    try:
        yield
    finally:
        _current_project.reset(token)
