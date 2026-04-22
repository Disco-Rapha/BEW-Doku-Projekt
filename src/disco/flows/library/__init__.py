"""Flow-Library — wiederverwendbare Flows, die in jedem Projekt laufen.

Flows in diesem Verzeichnis sind **globale** Bausteine: sie werden einmal
im Repo gepflegt und stehen danach in jedem Projekt automatisch zur
Verfuegung, ohne dass sie pro Projekt kopiert werden muessen.

Aufloesungsreihenfolge (siehe `disco.flows.runner_host` + `service`):

  1. `<projekt>/flows/<name>/runner.py`     — Projekt-lokaler Override
  2. `disco/flows/library/<name>/runner.py` — globale Library

Ein Projekt-lokaler Ordner gewinnt immer, damit ein Nutzer einen
Bibliotheks-Flow forken und anpassen kann.

Voraussetzungen fuer einen Library-Flow:

- Keine Abhaengigkeit auf projekt-spezifische Dateien ausserhalb der
  Projekt-Sandbox (keine absoluten Pfade, kein fest verdrahteter Slug).
- Die benoetigten Tabellen (z.B. `agent_pdf_inventory`) werden ueber
  Template-Migrationen unter `migrations/project/` angelegt, so dass
  sie beim Projekt-Init oder per `apply_project_db_migrations()` in
  jedem Projekt existieren.
- Der Runner darf `run.db.execute(...)` aufrufen, um `work_*`-Tabellen
  selbst anzulegen (analog zu ad-hoc run_python-Skripten).
"""
