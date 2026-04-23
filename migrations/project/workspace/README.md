# Projekt-DB-Migrationen — `workspace.db`

Diese Migrationen landen in **`<projekt>/workspace.db`** (Ebene 3
der Architektur, siehe `docs/architektur-ebenen.md`).

- **Ebene 3 — Knowledge / Workspace:** Reasoning-Ergebnisse,
  Flow-State, Audit-Trails des Agents — alles, was Disco
  *selbst erzeugt*.

Aus Chat-Sicht ist `workspace.db` **read/write**. Der Agent darf
ueber `sqlite_write` im Namespace `work_*`/`agent_*`/`context_*`
frei arbeiten. Tabellen ohne Praefix sind gesperrt.

Im Agent-SQL-Kontext ist `workspace.db` die **main**-Datenbank; alle
Tabellen werden ohne Praefix angesprochen. Zusaetzlich haengt der
Tool-Layer `datastore.db` als `ds` an — so erreichbar:
`SELECT ... FROM agent_dcc_classification JOIN ds.agent_sources ...`.

## Nummerierung

Wird **von 001 an** weitergezählt, unabhängig vom `datastore/`-Zweig.
Jede Datei ist idempotent (`CREATE IF NOT EXISTS`). Bestehende
Migrationen sind immutable — Änderungen gehen als neue Migration.
