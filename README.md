# BEW Doku Projekt

Lokale Applikation zur strukturierten Aufbereitung von PDF-Dokumentationen mit Azure KI-Services (Document Intelligence, OpenAI) und SQLite-basierter Datenhaltung.

## Stack

- **Python 3.11+**, verwaltet mit [`uv`](https://docs.astral.sh/uv/)
- **SQLite** als lokale Datenbank (`db/bew.db`)
- **Datasette** als Browser-UI (Lesezugriff, Filter, Suche)
- **Azure Document Intelligence** für PDF → Markdown
- **Azure OpenAI** für Metadaten und Abgleich gegen VGB-S-831
- **Claude Code** als Entwicklungs- und Analyseumgebung (siehe `CLAUDE.md`)

## Ordnerstruktur

```
data/raw/         Input-PDFs (gitignored)
data/markdown/    Generiertes Markdown (gitignored)
data/exports/     Export-Pakete (gitignored)
db/bew.db         SQLite-Datenbank (gitignored)
migrations/       SQL-Schema-Dateien
src/bew/          Python-Anwendungscode
scripts/          Hilfsskripte (z.B. Datasette-Start)
notebooks/        Analysen, Experimente
```

## Erste Schritte

```bash
# 1. Abhängigkeiten installieren
uv sync

# 2. .env anlegen (von Vorlage)
cp .env.example .env
# Dann in .env die Azure-Keys eintragen

# 3. Datenbank initialisieren
uv run bew db init

# 4. Datasette starten (Browser öffnet sich)
bash scripts/run-datasette.sh
```

## Mit Claude Code arbeiten

Im Projektordner `claude` starten. Claude liest `CLAUDE.md` und kennt damit Struktur, DB-Schema und Konventionen.

## Projektphasen

- **Phase 0 (aktuell):** Fundament — Projektgerüst, DB, Datasette, Claude-Integration.
- **Phase 1:** Ingest-Pipeline (PDF → Azure → Markdown + Metadaten in DB).
- **Phase 2:** VGB-S-831 Informationsbedarfsliste, N:N-Abgleich via Azure OpenAI.
- **Phase 3:** Exporte und Rückspielung nach SharePoint.
