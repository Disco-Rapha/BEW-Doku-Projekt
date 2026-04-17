"""Disco-Flows — Massenverarbeitung von Items im Projekt-Kontext.

Ein **Flow** ist ein projektinterner Verarbeitungs-Auftrag, der in einem
eigenen Python-Prozess laeuft und eine typischerweise grosse Menge
gleichartiger Items abarbeitet:

  - Rein lokale Daten-Transformation (0 EUR)
  - Bulk-PDF → Markdown via Document Intelligence
  - Dokument-Klassifikation via LLM
  - Excel-Report aus Tabellen-Joins
  - ... was immer der Flow-Autor braucht.

Jeder Flow ist ein Ordner unter `<projekt>/flows/<flow_name>/` mit
mindestens:

    flows/<flow_name>/
    ├── README.md          ← Anweisung fuer Disco + Nutzer
    ├── runner.py          ← Python-Code, der die Items verarbeitet
    └── runs/              ← pro Run ein Unterordner mit log.txt usw.

Lifecycle:
    1. `disco flow run <name>` (CLI oder Agent) erzeugt einen Eintrag
       in agent_flow_runs und startet `runner_host.py` als detachten
       Subprocess.
    2. `runner_host.py` oeffnet eine Projekt-DB-Verbindung, instanziiert
       `FlowRun`, laedt dann `flows/<name>/runner.py` via runpy.
    3. Das User-Skript nutzt `FlowRun` um Items zu verarbeiten —
       `run.process(...)` kuemmert sich um Idempotenz, Retry, Pause,
       Cancel, Kostenzaehlung.
    4. Bei normalem Exit setzt `runner_host` den Status auf 'done';
       bei Exception auf 'failed' mit Traceback.

Die zentralen Bausteine dieses Pakets:

    sdk.py           — `FlowRun`, `FlowDB`: die API fuer Flow-Autoren
    service.py       — Business-Logik: create_run, start_detached,
                       pause, cancel, list_runs, list_flows
    runner_host.py   — Wrapper, der ein Flow-runner.py im Lifecycle
                       eines Runs ausfuehrt
"""

from __future__ import annotations

__all__ = ["FlowRun", "FlowDB"]

from .sdk import FlowDB, FlowRun  # noqa: E402,F401
