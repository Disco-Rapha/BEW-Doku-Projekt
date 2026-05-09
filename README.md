# Disco

Agentischer Reasoning-Assistent fuer Projektmitarbeiter in technischen
Grossprojekten. Liest, verknuepft und wertet tausende Dokumente, Excel-
Metadaten und Datenbanken aus. Laeuft lokal auf dem Nutzer-Rechner,
Rechenleistung via Microsoft Azure (Sweden Central, DSGVO/EU).

## Kernfaehigkeit

Cross-Source-Reasoning — Disco versteht Dokumente und zieht Schluesse,
statt sie nur zu verwalten. Kombiniert Dateisystem, SQL-Auswertungen,
PDF-Inhalte und Normen zu einer Sicht.

## Stack

- Python 3.11+, verwaltet mit [`uv`](https://docs.astral.sh/uv/)
- **SQLite** — `system.db` (zentral) + `datastore.db` + `workspace.db`
  (pro Projekt, Ebenen-Trennung Read-only / Read-write)
- **FastAPI + WebSocket** fuer Web-UI (`src/disco/api/`)
- **Foundry Agent Service** (Portal-Agent mit `agent_reference`)
- **Azure OpenAI** (Sweden Central) — GPT-5.x, Deployment-Name in `.env`
- **Azure Document Intelligence** fuer PDF-OCR
- **openpyxl**, **pypdf**, **ezdxf** fuer lokale Datei-Operationen

## Workspace-Trennung

```
<repo-root>/                   ← Code-Repo (dev, GitHub-synced)
├── src/, skills/, migrations/, scripts/, docs/

~/Disco/                       ← Daten-Workspace Prod (NIEMALS in Git)
~/Disco-dev/                   ← Daten-Workspace Dev
├── system.db
├── logs/
└── projects/<slug>/           ← Ein Projekt je Ordner
    ├── README.md, NOTES.md, DISCO.md    (3-Schichten-Memory)
    ├── sources/, context/, work/, exports/
    ├── datastore.db            (Ebene 1+2, read-only)
    ├── workspace.db            (Ebene 3, read/write, inkl. agent_table_docs)
    └── .disco/                 (plans, sessions, memory-access.log,
                                  notes-archive)
```

Kundendaten verlassen nie das Repo. `.gitignore` schuetzt als
Sicherheitsnetz.

## Erste Schritte

```bash
# Dependencies
uv sync

# .env anlegen
cp .env.example .env
# Azure-/Foundry-Keys in .env eintragen

# System-DB initialisieren
disco db init

# Server starten
uv run uvicorn disco.api.main:app --host 127.0.0.1 --port 8000 --reload
```

## Doku-Pointer

- **Produktvision + Roadmap:** [`docs/PRODUCT.md`](docs/PRODUCT.md)
- **Konventionen, Pipeline, Tools, Skills:** [`CLAUDE.md`](CLAUDE.md)
- **Architektur-Ebenen:** [`docs/architektur-ebenen.md`](docs/architektur-ebenen.md)
- **Architektur-Entscheidungen (ADRs):** [`docs/architecture-decisions.md`](docs/architecture-decisions.md)
- **Operations / Deploy / Rollback:** [`docs/operations-runbook.md`](docs/operations-runbook.md)
- **Backlog:** [`docs/BACKLOG.md`](docs/BACKLOG.md)
- **Historische Konzepte / Audits:** [`docs/archive/`](docs/archive/)

## Lizenz

Intern. Nicht fuer externe Verteilung.
