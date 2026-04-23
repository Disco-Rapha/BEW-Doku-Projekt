# Projekt-DB-Migrationen — `datastore.db`

Diese Migrationen landen in **`<projekt>/datastore.db`** (Ebene 1 + 2
der Architektur, siehe `docs/architektur-ebenen.md`).

- **Ebene 1 — Provenance:** Herkunfts-Register (`agent_sources`,
  `agent_source_metadata`, `agent_source_relations`,
  `agent_source_scans`).
- **Ebene 2 — Content:** extrahierter Inhalt (`agent_pdf_markdown`,
  `agent_pdf_inventory`, `work_pdf_routing`), Volltext-Suchindex
  (`agent_search_*`, FTS5).

Aus Chat-Sicht ist `datastore.db` **read-only**. Geschrieben wird
nur durch:

- Registry-Tools (`sources_register`, `sources_attach_metadata`,
  `sources_detect_duplicates`).
- Pipelines/Flows (`pdf_routing_decision`, `pdf_to_markdown`,
  `build_search_index`).

Im Agent-SQL-Kontext ist die DB als `ATTACH DATABASE ... AS ds`
eingehaengt; der Agent liest Registry und Inhalt via `ds.<tabelle>`.

## Nummerierung

Wird **von 001 an** weitergezählt, unabhängig vom `workspace/`-Zweig.
Jede Datei ist idempotent (`CREATE IF NOT EXISTS`). Bestehende
Migrationen sind immutable — Änderungen gehen als neue Migration.
