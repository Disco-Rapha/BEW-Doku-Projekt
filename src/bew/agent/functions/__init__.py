"""Registry aller Custom Functions fuer den Foundry-Agent.

Pattern:
  - Jede Function wird ueber `@register(...)` dekoriert und automatisch in
    die globale `FUNCTIONS`-Registry eingetragen.
  - `get_tool_schemas()` liefert die Liste im OpenAI-Function-Calling-Format,
    das `azure-ai-projects` erwartet.
  - `dispatch(name, arguments_json)` fuehrt eine Function aus und gibt das
    Ergebnis als JSON-String zurueck.
  - Fehler werden immer als `{"error": "..."}` serialisiert statt Exceptions
    zu werfen, damit Foundry das Ergebnis dem Modell weiterreichen kann.

Registrierung findet per Side-Effect beim Modul-Import statt. Deshalb
importieren wir unten alle Submodule, damit alle Functions verfuegbar sind.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class FunctionSpec:
    """Metadaten + Implementierung einer Custom Function."""

    name: str
    description: str
    parameters: dict[str, Any]            # JSON Schema (OpenAI-Function-Calling-Style)
    handler: Callable[..., Any]           # sync oder async, nimmt **kwargs
    returns: str = "JSON-Objekt"          # freie Beschreibung fuer den System-Prompt

    def schema(self) -> dict[str, Any]:
        """Tool-Schema fuer die OpenAI Responses API.

        Wichtig: die Responses API erwartet ein FLACHES Schema
            {type: "function", name, description, parameters, strict}
        NICHT das verschachtelte Chat-Completions-Format
            {type: "function", function: {name, description, parameters}}
        """
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": False,
        }


# Globale Registry — wird durch `@register` beim Modul-Import gefuellt
FUNCTIONS: dict[str, FunctionSpec] = {}


def register(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    returns: str = "JSON-Objekt",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Dekorator zum Registrieren einer Custom Function.

    Beispiel:
        @register(
            name="list_projects",
            description="Listet alle Projekte auf.",
            parameters={"type": "object", "properties": {...}, "required": []},
        )
        def list_projects(*, include_archived: bool = False) -> list[dict]:
            ...

    Wichtig:
      - Handler-Argumente werden als Keyword-Arguments uebergeben.
      - Handler sollte JSON-serialisierbare Python-Objekte zurueckgeben.
      - Bei Fehlern einfach eine Exception werfen — `dispatch()` faengt sie.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if name in FUNCTIONS:
            raise ValueError(f"Custom Function '{name}' ist bereits registriert.")
        FUNCTIONS[name] = FunctionSpec(
            name=name,
            description=description,
            parameters=parameters,
            handler=fn,
            returns=returns,
        )
        return fn

    return decorator


def get_tool_schemas() -> list[dict[str, Any]]:
    """Gibt alle registrierten Functions als Liste von Tool-Schemas zurueck.

    Dieses Format wird sowohl vom Foundry Agent Service als auch von
    Azure OpenAI Responses API direkt akzeptiert.
    """
    return [spec.schema() for spec in FUNCTIONS.values()]


def dispatch(name: str, arguments: dict[str, Any] | str | None) -> str:
    """Fuehrt eine registrierte Function aus und gibt JSON zurueck.

    Args:
        name:      Function-Name, wie vom Modell im tool_call angegeben.
        arguments: Entweder bereits geparstes dict, oder JSON-String vom Modell,
                   oder None fuer Functions ohne Parameter.

    Returns:
        JSON-String — entweder das Ergebnis oder `{"error": "..."}`.
        Nie None, nie Exception (ausser bei katastrophalen Fehlern im
        JSON-Encoding selbst, was nicht passieren sollte).
    """
    spec = FUNCTIONS.get(name)
    if spec is None:
        logger.warning("Custom Function nicht gefunden: %s", name)
        return json.dumps({"error": f"Unbekannte Function: {name}"}, ensure_ascii=False)

    # Argumente in dict konvertieren
    kwargs: dict[str, Any]
    if arguments is None:
        kwargs = {}
    elif isinstance(arguments, str):
        try:
            kwargs = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as exc:
            logger.warning("Ungueltiges JSON in tool-arguments fuer %s: %s", name, exc)
            return json.dumps(
                {"error": f"Ungueltiges JSON in arguments: {exc}"},
                ensure_ascii=False,
            )
    else:
        kwargs = dict(arguments)

    try:
        result = spec.handler(**kwargs)
        return json.dumps(result, ensure_ascii=False, default=_json_fallback)
    except TypeError as exc:
        # Typisch: falsche / fehlende Parameter
        logger.warning("Tool-Signatur-Fehler %s: %s", name, exc)
        return json.dumps({"error": f"Parameter-Fehler: {exc}"}, ensure_ascii=False)
    except Exception as exc:
        logger.exception("Tool-Ausfuehrung fehlgeschlagen: %s", name)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _json_fallback(obj: Any) -> Any:
    """Letzter Ausweg fuer Dinge wie Path, datetime, Decimal etc."""
    # Standard-Konvertierung: alles was str() kann
    return str(obj)


# ---------------------------------------------------------------------------
# Eager-Import aller Function-Module, damit deren @register-Dekoratoren laufen
# ---------------------------------------------------------------------------
from . import domain  # noqa: E402,F401
from . import data    # noqa: E402,F401 — sqlite_query, sqlite_write
from . import fs      # noqa: E402,F401 — fs_list/read/write/mkdir/delete + bytes
from . import pdf     # noqa: E402,F401 — pdf_extract_text
from . import notes   # noqa: E402,F401 — project_notes_read, project_notes_append
from . import plans   # noqa: E402,F401 — plan_list, plan_read, plan_write, plan_append_note
from . import imports  # noqa: E402,F401 — xlsx_inspect, import_xlsx_to_table, import_csv_to_table
from . import skills   # noqa: E402,F401 — list_skills, load_skill
from . import sources   # noqa: E402,F401 — sources_register, attach_metadata, detect_duplicates
from . import executor  # noqa: E402,F401 — run_python
from . import docint         # noqa: E402,F401 — extract_pdf_to_markdown
from . import markdown_tools # noqa: E402,F401 — extract_markdown_structure
