# CLAUDE.md — Projektkontext für Claude Code

## Was ist das?

Lokale Python-Applikation zur Verarbeitung **zehntausender PDF-Dokumentationen** eines Kunden. Ersetzt einen bisherigen Power-Automate-Flow in SharePoint. Die KI-Arbeit läuft über **Azure Document Intelligence** (PDF → Markdown) und **Azure OpenAI** (Metadaten, Summary, VGB-S-831-Abgleich); Orchestrierung und Datenhaltung sind **lokal**.

Der Nutzer ist **kein Programmierer**, aber technisch versiert. Er entscheidet Architekturfragen aktiv mit, will aber nicht tief in den Code einsteigen. Antworten auf **Deutsch**. Vor größeren Änderungen am Schema oder an der Modulstruktur: **fragen**, nicht annehmen.

## Stack (Stand Phase 0)

- Python 3.11+, `uv` als Paketmanager
- SQLite (`db/bew.db`) mit FTS5 — zusätzliche Tabellen/Indexe via neuer Migration, **nie** die DB manuell bearbeiten
- Datasette als Read-only-Browser auf `localhost:8001`
- Streamlit kommt später (Kuratier-Workflows)

## Verzeichnisse

| Pfad | Zweck |
|------|-------|
| `src/bew/` | Anwendungscode (CLI, DB, später Azure-Clients) |
| `migrations/` | SQL-Dateien `NNN_name.sql`, streng aufsteigend |
| `db/bew.db` | SQLite-Datei (gitignored) |
| `data/raw/` | Input-PDFs (gitignored) |
| `data/markdown/` | Von Azure extrahiertes Markdown (gitignored) |
| `data/exports/` | Generierte Export-Pakete (gitignored) |
| `notebooks/` | Freie Analysen — darf Claude Code frei nutzen |

## Konventionen

1. **Secrets niemals committen.** Alles Sensible gehört in `.env` (gitignored). `.env.example` bleibt aktuell.
2. **Schema-Änderungen nur über neue Migrationen.** Neue Datei `migrations/NNN_beschreibung.sql`, Eintrag in `schema_version`. Bestehende Migrationen sind immutable.
3. **Daten liegen als Dateien, DB hält Pfade.** PDFs und Markdown nicht in BLOBs packen.
4. **Pipeline-Schritte idempotent.** Jeder Schritt prüft Status und kann neu aufgesetzt werden — wichtig bei 10k+ Dokumenten und Azure-Rate-Limits.
5. **Nachvollziehbarkeit.** Jeder Azure-Aufruf wird in `processing_events` geloggt (Tokens, Dauer, Fehler, Payload).
6. **Vor neuen Features fragen:** In welches der drei Module gehört das (Ingest, VGB-S-831, Export) — oder ist es Fundament?

## Aktuelles Schema (v1)

- `documents` — Stammtabelle: `id, sha256, original_name, relative_path, size_bytes, mime_type, status, created_at, updated_at`
- `processing_events` — Verarbeitungs-Log: `id, document_id, step, status, tokens_used, duration_ms, error_message, payload_json, created_at`
- `schema_version` — aktuell `1`

Erweiterungen (Metadaten, VGB-Zuordnungen) kommen in späteren Migrationen.

## Häufige Kommandos

```bash
uv sync                        # Abhängigkeiten installieren/aktualisieren
uv run bew db init             # DB anlegen / Migrationen anwenden
uv run bew db status           # Zeigt Schema-Version und Tabellen
bash scripts/run-datasette.sh  # Datasette auf localhost:8001
```

## Was NICHT tun

- Keine Azure-Calls ohne Logging in `processing_events`.
- Keine Tabellen ohne Migration anlegen.
- Kein `git add -A` bei Unsicherheit — die `.gitignore` ist wichtig, aber besser einzeln stagen.
- Keine eigenmächtige Migration auf Postgres — das wäre eine Architekturentscheidung, vorher mit dem Nutzer besprechen.
