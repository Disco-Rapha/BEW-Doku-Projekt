"""Thread-lokaler Projekt-Kontext fuer Disco-Tools.

Wenn ein Chat-Thread an ein Projekt gebunden ist (`chat_threads.project_id`),
sollen alle Tool-Aufrufe innerhalb dieses Turns auf die Sandbox des Projekts
zugreifen — und nicht auf den globalen Workspace.

Implementierung via `contextvars.ContextVar`, damit parallele AgentService-
Aufrufe (z.B. zwei Browser-Tabs gleichzeitig) sich gegenseitig nicht stoeren.

Tools fragen ab:
    from .context import get_project_root, get_project_db_path
    root = get_project_root()        # Path oder None (= Workspace-Root)
    db   = get_project_db_path()     # Path zur Projekt-data.db oder None
"""

from __future__ import annotations

import contextvars
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


def get_current_project_slug() -> str | None:
    """Gibt den Slug des aktiven Projekts zurueck, oder None."""
    return _current_project.get()


def get_project_root() -> Path | None:
    """Pfad des aktiven Projekt-Verzeichnisses, oder None."""
    slug = _current_project.get()
    if not slug:
        return None
    return settings.projects_dir / slug


def get_project_db_path() -> Path | None:
    """Pfad der aktiven Projekt-DB (data.db), oder None."""
    root = get_project_root()
    if root is None:
        return None
    return root / "data.db"


@contextmanager
def use_project(slug: str | None) -> Iterator[None]:
    """Context-Manager fuer einen Tool-Block in einem Projekt-Sandbox.

    Beispiel:
        with use_project("vattenfall-reuter"):
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
