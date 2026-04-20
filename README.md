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
- **SQLite** — system.db (zentral) + data.db (pro Projekt)
- **FastAPI + WebSocket** fuer Web-UI (`src/disco/api/`)
- **Foundry Agent Service** (Portal-Agent mit `agent_reference`)
- **Azure OpenAI** (Sweden Central) — Modell GPT-5.1
- **Azure Document Intelligence** fuer PDF-OCR
- **openpyxl**, **pypdf** fuer lokale Datei-Operationen

## Workspace-Trennung

```
<repo-root>/                   ← Code-Repo (dev, GitHub-synced)
├── src/, skills/, migrations/, scripts/

~/Disco/                       ← Daten-Workspace Prod (NIEMALS in Git)
~/Disco-dev/                   ← Daten-Workspace Dev
├── system.db
├── logs/
└── projects/<slug>/           ← Ein Projekt je Ordner
    ├── README.md, NOTES.md, DISCO.md    (3-Datei-Memory)
    ├── sources/, context/, work/, exports/
    ├── data.db                (Projekt-DB)
    └── .disco/                (plans, sessions, extracts)
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

Details zu Architektur, Skills, Flows: siehe `CLAUDE.md`.

## Lizenz

Intern. Nicht fuer externe Verteilung.
