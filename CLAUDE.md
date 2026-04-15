# CLAUDE.md — Projektkontext für Claude Code

## Was ist das?

Lokales **agentisches Dokumenten-Management-System** für technische Kunden­dokumentationen. Zielgröße: Zehntausende bis Hunderttausende Dokumente pro Kunde. KI-Arbeit läuft über **Azure Document Intelligence** (PDF → Markdown) und **Azure OpenAI** (Indexierung, Klassifikation, Reports); Synchronisation mit SharePoint läuft über **Microsoft Graph API**; **Orchestrierung und Datenhaltung sind lokal** in SQLite. Ein **Claude-API-Agent** im Web-UI steuert Tasks (Dokumente suchen, DB-Abfragen, Sync auslösen).

Der Nutzer ist **kein Programmierer**, aber technisch versiert. Er entscheidet Architekturfragen aktiv mit, will aber nicht tief in den Code einsteigen. **Antworten auf Deutsch.** Vor größeren Änderungen am Schema oder an der Modulstruktur: **fragen**, nicht annehmen.

## Aktueller Stand

- **Schema-Version: v3** (siehe `migrations/`)
- **Phase 1 (in Arbeit):** SharePoint-Connector mit Metadaten-Snapshot + Delta-Sync. Keine Dateidownloads — nur Metadaten.
- **Phase 2 (offen):** Dokumenten-Download + Azure Document Intelligence (PDF → Markdown) + Azure OpenAI (Metadaten, Klassifikation).
- **Phase 3 (offen):** Export-Pipeline zurück nach SharePoint.

## Architektur (laut `project_direction.md`)

**3-Panel-Web-UI** (à la VS Code):
- **Links:** Explorer (Projekte → Quellen → Ordner → Dokumente als Baum).
- **Mitte:** Dokument-Viewer, Task-Ergebnisse, Dashboard.
- **Rechts:** Chat mit Claude-API-Agent (claude-sonnet-4-6, Tool Use).

Der Agent ist **Operator, nicht nur Assistent** — er führt Tasks aus, startet Syncs, fragt DB ab.

## Stack

- Python 3.11+, `uv` als Paketmanager
- **SQLite** (`db/bew.db`) — keine manuellen Schema-Änderungen, nur via Migration
- **FastAPI + WebSocket** für das Haupt-UI (`src/bew/api/`)
- **Streamlit** als Fallback-UI (`src/bew/ui/`)
- **Datasette** als Read-only-DB-Browser auf `localhost:8001`
- **MSAL** für OAuth2 Device-Flow gegen Microsoft Entra ID
- **httpx** für Microsoft Graph API
- **anthropic** Python-SDK für den Agent

## Modulstruktur

| Pfad | Zweck |
|------|-------|
| `src/bew/cli.py` | CLI mit Gruppen `db`, `project`, `source`, `sync`, `auth`, `sp` |
| `src/bew/db.py` | SQLite-Verbindung und Migrations-Runner |
| `src/bew/config.py` | Settings aus `.env` via pydantic-settings |
| `src/bew/projects.py` | CRUD für `projects` |
| `src/bew/sources.py` | CRUD für `sources` und `source_folders` |
| `src/bew/sharepoint/auth.py` | `MSALTokenManager` — Device-Flow-Login, Token-Cache |
| `src/bew/sharepoint/graph.py` | `GraphClient` — thin wrapper um Graph-API |
| `src/bew/sharepoint/sync.py` | `SharePointSyncer` — Snapshot + Delta, Einstieg `.run()` |
| `src/bew/sharepoint/import_json.py` | `SharePointJSONImporter` — Fallback aus REST/XML-Exporten |
| `src/bew/api/main.py` | FastAPI-App, REST-Endpoints, WebSocket-Chat |
| `src/bew/api/agent.py` | Claude-API-Agent mit Tool Use (6 Tools) |
| `src/bew/api/static/index.html` | 3-Panel-Frontend (HTML/CSS/JS, kein Framework) |
| `src/bew/ui/` | Streamlit-Fallback mit Seiten `projects`, `sources`, `documents` |
| `migrations/001_initial.sql` | documents, processing_events, schema_version |
| `migrations/002_projects_sources_sharepoint.sql` | projects, sources, source_folders, documents-FKs |
| `migrations/003_sp_metadata_snapshot.sql` | documents nullable sha256 + SP-Metadaten, document_sp_fields, sp_delta_link |

## Schema (v3, verkürzt)

```
projects  (id, name, description, status)
sources   (id, project_id, name, source_type, config_json, status, last_synced_at, sp_delta_link)
source_folders (id, source_id, parent_id, sp_item_id, name, sp_path, sp_web_url)
documents (id, sha256, original_name, size_bytes, mime_type, status,
           sp_modified_at, sp_created_at, sp_modified_by, sp_created_by,
           sp_web_url, sp_quick_xor_hash, sp_content_type, sp_list_item_id,
           selected_for_indexing,
           project_id, source_id, source_item_id, source_path, markdown_path)
document_sp_fields (id, document_id, field_name, field_value)
processing_events  (id, document_id, step, status, tokens_used, duration_ms,
                    error_message, payload_json)
```

Dokument-Lebenszyklus (`documents.status`):
`discovered` → (Download) → `downloaded` → (Azure) → `indexed` | `needs_reindex` | `deleted` | `failed`.

## Konventionen

1. **Secrets niemals committen.** Alles Sensible in `.env` (gitignored). `.env.example` bleibt aktuell.
2. **Schema-Änderungen nur über neue Migrationen** `migrations/NNN_name.sql`. Bestehende Migrationen sind immutable.
3. **Daten liegen als Dateien, DB hält Pfade** (PDFs in `data/raw/`, Markdown in `data/markdown/`).
4. **Kundendaten niemals in Git.** `Sharepoint Download/` und Token-Caches sind gitignored.
5. **Pipeline-Schritte idempotent** — bei 10k+ Dokumenten und Graph-/Azure-Rate-Limits essenziell.
6. **Nachvollziehbarkeit.** Jeder Azure-Aufruf wird in `processing_events` geloggt.
7. **Einstiegspunkt Sync:** `SharePointSyncer.run()` wählt Snapshot (erster Lauf) oder Delta (folgende) automatisch.
8. **Vor neuen Features fragen:** in welche Phase gehört das — oder ist es Fundament?

## Häufige Kommandos

```bash
uv sync                                    # Abhängigkeiten installieren/aktualisieren
uv run bew db init                         # DB anlegen / Migrationen anwenden
uv run bew db status                       # Schema-Version + Tabellen

uv run bew project list                    # Alle aktiven Projekte
uv run bew project create --name "…"       # Neues Projekt
uv run bew source add --project N --name "…" --site-url https://… --library "…"
uv run bew source list --project N
uv run bew source show --id N
uv run bew sync run --source N             # Smart Sync (snapshot oder delta)

uv run bew auth login                      # Microsoft 365 Device-Flow
uv run bew auth status

uv run bew sp import-json --source N <datei>   # Fallback aus XML/JSON-Export

bash scripts/run-datasette.sh              # Datasette auf localhost:8001
uv run streamlit run src/bew/ui/app.py     # Streamlit-UI (Fallback)
# Haupt-UI: uv run bew-server               (FastAPI — nach Fertigstellung)
```

## Was NICHT tun

- Keine Azure-/Graph-Calls ohne Logging in `processing_events`.
- Keine Tabellen ohne Migration anlegen.
- Kein `git add -A` bei Unsicherheit — die `.gitignore` ist wichtig, aber besser einzeln stagen.
- Kein Wechsel auf Postgres ohne Architektur-Gespräch mit dem Nutzer.
- Keine Commits, die `data/`, `Sharepoint Download/`, `.env` oder Token-Caches enthalten.
