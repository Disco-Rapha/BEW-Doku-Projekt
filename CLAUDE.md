# CLAUDE.md — Disco: Produktvision, Stand, Konventionen

## Was ist Disco?

**Disco** ist ein agentischer **Reasoning-Assistent** für Projekt-
mitarbeiter in **technischen Großprojekten** (Kraftwerke, Industrie-
anlagen, Infrastruktur). Er läuft lokal auf dem Rechner des Nutzers,
Rechenleistung aus Microsoft Azure (Sweden Central, DSGVO/EU).

### Mission

Aus **großen Mengen technischer Information** Erkenntnisse gewinnen —
durch Lesen, Extrahieren, Verknüpfen und systematisches Durcharbeiten
von Dokumenten *und* Datenbanken. Dokumentenmanagement ist *ein*
Anwendungsfall, nicht der Zweck.

**Skala:** hundert bis einige zehntausend Dateien pro Projekt.
Typisch: Generalunternehmer liefert über Monate Paket für Paket
Dokumente (PDFs, Excels, Zeichnungen, Messwerte, Protokolle) —
Duplikate, Revisionen, Format-Konversionen (DWG→PDF) inklusive.
Disco hält Ordnung und ermöglicht Auswertung.

### Kern-Fähigkeit: Cross-Source-Reasoning

Disco verwaltet Dokumente nicht nur — er **versteht sie und zieht
Schlüsse**. Der eigentliche Wert liegt darin, Excel-Metadaten,
PDF-Content, SQL-Auswertungen und Normen zu **einer** Sicht zu
verknüpfen. Das ist der Unterschied zu jedem Standard-DMS.

### Rolle: Assistent, nicht Werkzeug

Disco ist ein **Kollege, kein Hammer**. Er:
- pflegt ein **persistentes Projekt-Gedächtnis** zwischen Sessions,
- schlägt proaktiv vor, kündigt Aktionen an, berichtet transparent zurück,
- arbeitet **lokal** (Kundendaten verlassen den Rechner nicht),
  EU-Cloud für LLM-Calls (Sweden Central),
- lässt den Nutzer Entscheider sein.

Vorbild: Claude Cowork (Anthropic), gezielt auf "große Mengen
technischer Information managen und auswerten" zugeschnitten.

### Drei Instrumente

| Instrument | Wann | Typisches Beispiel |
|---|---|---|
| **Dateiexplorer** | Einzel-Ops, kleine Paketgrößen | Dokumente sichten, neu sortieren, Ordner anlegen |
| **SQL-Datenbank** | strukturierte Auswertung | Verteilung über 1.800 Dokumente, Top-N, Joins Excel × DB |
| **Flow-Engine** | Massenverarbeitung (>10 Items / >2 Min) | 10.000 PDFs klassifizieren, PDF→Markdown-Bulk, SOLL/IST-Lauf |

Explorer + SQL arbeiten synchron im Chat-Turn. Flows laufen als
eigener Subprocess — resumable, pausierbar, mit Budget-Limit. Disco
kann damit seinen eigenen Agent-Loop aus dem Chat-Turn in die
Massenverarbeitung verlagern.

### Drei Paradebeispiele

1. **Dokumenten-Klassifikation über 1.800 PDFs** — Disco liest pro
   Dokument den Inhalt, klassifiziert nach Gewerk + Dokumenttyp,
   schreibt das Ergebnis strukturiert in Tabelle und Excel-Report.
2. **Versions-Chaos auflösen** — In einem Pool mit Duplikaten,
   Revisionen und Format-Konversionen findet Disco die aktuellste
   Version jedes Dokuments (Hash + Inhalt + Namens-Konvention).
3. **SOLL/IST-Abgleich gegen VGB S 831** — Disco gleicht die
   tatsächlich gelieferte Dokumentation gegen die Norm-Vorgabe ab
   und meldet Lücken inkl. Excel-Report mit Hyperlinks und
   Farb-Codierung.

### Nutzer

Projektingenieure, Doku-Verantwortliche, Projektleiter.
**Technisch versiert, aber keine Programmierer.** Wollen Ergebnisse
in Excel oder strukturiert abgelegt, nicht SQL-Queries selbst
schreiben. Entscheiden Architekturfragen aktiv mit, wollen aber
nicht tief in den Code einsteigen. **Antworten auf Deutsch.** Vor
größeren Änderungen am Schema oder an der Modulstruktur: **fragen**,
nicht annehmen.

---

## Wie Disco funktioniert

### 1. Projekt erstellen

Ein Disco-Projekt hat einen konkreten Zweck, z. B.:
- "Aus 3 Datenquellen Dokumente anhand ihres Inhalts klassifizieren
  und in eine neue Ordnerstruktur überführen"
- "SOLL/IST-Abgleich der technischen Dokumentation gegen VGB S 831"
- "Dokumenten-Index aufbauen mit Hersteller-/Typ-Zuordnung"

Das Projekt lebt als Verzeichnis im Workspace (`~/Disco/projects/<slug>/`)
mit fester Struktur:

```
<projekt>/
├── README.md          ← Nutzer pflegt: Projektziel, Kontext
├── NOTES.md           ← Disco führt fort: chronologisches Logbuch
├── sources/           ← Quelldokumente (IST-Bestand)
│   └── _meta/         ← Begleit-Metadaten (Excel/CSV)
├── context/           ← Arbeitsgrundlagen (Normen, Kataloge)
│   └── _manifest.md   ← Agent-gepflegte Übersicht
├── work/              ← Discos freier Arbeitsraum + Skripte
├── exports/           ← Endprodukte für den Nutzer
├── data.db            ← Projekt-DB (work_*/agent_*/context_*)
└── .disco/            ← Discos "Hirn" (memory, plans, sessions)
```

### 2. Quellen anbinden

Quelldateien werden als Paket in `sources/` abgelegt (manuell oder
später via SharePoint-Sync). Disco registriert sie in einer **Registry**
(`agent_sources`): Pfad, SHA-256-Hash, Größe, Status, Begleit-Metadaten.
Bei jedem neuen Paket erkennt er Delta (neu/geändert/gelöscht) automatisch
über Hash-Vergleich.

Typische Realität: Generalunternehmer liefert kontinuierlich neue
Dokumente. Duplikate, Revisionen, Format-Konversionen (DWG→PDF),
kommentierte Kopien — ein Dokumenten-Chaos über Monate. Disco hält
Ordnung über die Registry + Relations-Tabelle (`duplicate-of`,
`replaces`, `derived-from`, etc.).

### 3. Kontext aufbauen

Im `context/`-Ordner liegen Arbeitsgrundlagen — nicht zu bearbeitende
Dateien, sondern Nachschlagewerke:
- Dokumentationsstandards (VGB S 831, DIN-Normen)
- Zielordnerstrukturen (wohin was einsortiert wird)
- Referenztabellen (DCC-Katalog, KKS-Hierarchie)
- Richtlinien (Standard-Dokumentensatz)

Disco analysiert, zusammenfasst und indiziert den Kontext automatisch.
Lookup-Tabellen werden in die Projekt-DB importiert (`context_*`).
Das Manifest (`context/_manifest.md`) listet alles auf und erklärt,
wann welche Datei relevant ist.

**Wichtig — context/ klein halten** (Arbeitsweise-Regel, 2026-04-27):
`sources/` darf gross sein (Tausende von Projektdokumenten); `context/`
ist demgegenueber bewusst eng kuratiert — **nur das, was zur konkreten
Bearbeitung des Projekts wirklich gebraucht wird**. Analogie: wie eine
kleine Dateisammlung im Arbeitsordner einer Cowork-Session, mit der
aktiv gearbeitet wird. Disco soll context/ NICHT vollladen "weil's
relevant sein koennte" — Faustregel: fragen vor Aufnahme, prefer
weniger und scharf statt mehr und unscharf. Wenn ein Dokument doch
spaeter relevant wird, kann es jederzeit nachtraeglich rein.

### 4. LLM-ready machen

Bevor ein LLM über die Daten "reasonen" kann, müssen sie aufbereitet
werden:
- Excel → Tabellen in der Projekt-DB
- PDF → Text extrahieren (pypdf lokal, Azure Document Intelligence
  für OCR bei Scan-PDFs)
- Index aufbauen (später: Hybrid-Search mit Embeddings + FTS5)
- Semantische Suche ermöglichen

### 5. Disco arbeitet

Der Agent (Foundry-Portal-Agent — `disco-prod-agent` in Prod,
`disco-dev-agent` in Dev, Modell GPT-5.1 in Sweden Central) hat
**echten Schreibzugriff** auf das Projekt:
- Dateien lesen, schreiben, verschieben
- DB-Tabellen anlegen, auswerten, joinen
- **Python-Skripte schreiben und lokal ausführen** (für große Dateien
  und Bulk-Ops — genau wie Claude Code seinen Bash-Tool nutzt)
- Excel-Reports mit professioneller Formatierung generieren
- Erkenntnisse in NOTES und Memory festhalten

Arbeitsweise: **proaktiv, transparent, selbstkritisch.** Disco kündigt
an was er tut, führt es aus, und meldet das Ergebnis — mit echtem
Tool-Result als Wahrheitsquelle, keine Halluzination.

### 6. Flows — Massenverarbeitung als Projekt-Artefakt

Ein **Flow** ist ein projektinterner Verarbeitungs-Auftrag mit eigenem
Ordner `<projekt>/flows/<flow_name>/` (README + runner.py), eigenem
Subprocess, eigenem Status in der Projekt-DB. Flows decken alles von
0-EUR-Daten-Transformationen über DI-PDF-Extraktion bis
LLM-Klassifikationen ab.

- Disco **baut** den Flow mit dem Nutzer zusammen (README + runner.py)
- Disco **testet** ihn (Mini-Läufe mit `--config '{"limit": 5}'`)
- Disco **startet + überwacht** den Full-Run (auch über 10 Stunden)
- Disco **reagiert** bei Anomalien (Pause, Nachjustieren, Resume)

Framework-Bausteine: `src/bew/flows/sdk.py` (FlowRun/FlowDB für
Autoren), `runner_host.py` (Subprocess-Lifecycle), `service.py`
(CLI-/Agent-API), Migration `004_agent_flows.sql`.

Siehe `src/bew/flows/README.md` für das Entwickler-Howto.

---

## Was bereits gebaut ist (Stand 2026-04-17)

### Infrastruktur
- [x] **Workspace-Trennung**: Code-Repo (GitHub) ↔ Daten-Workspace (`~/Disco/`)
- [x] **Foundry-Agent**: Portal-Agent mit agent_reference
      (Prod: `disco-prod-agent`, Dev: `disco-dev-agent`), tunebarer
      System-Prompt, versioniert, Rollback möglich
- [x] **Projekt-Sandbox**: fs_*/sqlite_*-Tools arbeiten nur innerhalb des
      aktiven Projekts (contextvars-basiert, echte Mandantentrennung)
- [x] **Projekt-DB pro Projekt**: `data.db` mit Template-Migrationen
      (agent_sources, agent_source_metadata, agent_source_relations,
      agent_source_scans, agent_script_runs)
- [x] **CLI**: `disco project init/list/show`, `disco agent chat --project`,
      `disco agent setup/threads` (`bew` als Alias)
- [x] **Web-UI**: 3-Panel-Layout (Sidebar + Chat + Viewer), Chat mit
      Markdown/Code/Tabellen-Rendering, Explorer-Tree, DB-Tabellen-Browser,
      Viewer für MD/CSV/JSON/Excel/PDF

### Agent-Tools (28 Custom Functions + Code Interpreter)
- [x] **Dateisystem**: fs_list/read/write/mkdir/delete, fs_read_bytes/write_bytes
- [x] **Datenbank**: sqlite_query (READ-ONLY), sqlite_write (work_*/agent_*/context_* Namespace)
- [x] **Import**: xlsx_inspect, import_xlsx_to_table, import_csv_to_table
- [x] **Export**: build_xlsx_from_tables (Multi-Sheet, Header-Style, AutoFilter, Status-Farben)
- [x] **Sources-Registry**: sources_register (Hash-basierte Delta-Detection),
      sources_attach_metadata (Begleit-Excel, Option-C-Matching),
      sources_detect_duplicates (sha256-Gruppen → duplicate-of-Relations)
- [x] **PDF**: pdf_classify (PyMuPDF-Diagnose), pdf_markdown_read (liest `agent_pdf_markdown`, gefuellt vom Flow `pdf_to_markdown` mit Engines docling-standard / azure-di / azure-di-hr)
- [x] **Lokale Python-Ausführung**: run_python (file-basiert + inline, Audit-Trail,
      Env-Filtering, Timeout). Disco schreibt Skripte, führt sie lokal aus, debuggt.
- [x] **Skills**: list_skills/load_skill (lazy-loaded Playbooks)
- [x] **Projekt-Gedächtnis**: project_notes_read/append
- [x] **Domain**: list_projects, get_project_details, search_documents, etc.

### Skills (kuratierte Playbooks)
- [x] `project-onboarding` — Session-Start-Routine (README + NOTES + memory + context)
- [x] `sources-onboarding` — Quellen registrieren + Metadaten + Duplikate
- [x] `context-onboarding` — Kontext-Dateien sichten + Manifest pflegen
- [x] `excel-reporter` — Multi-Sheet-Excel via build_xlsx_from_tables
- [x] `python-executor` — Skripte schreiben, ausführen, debuggen

### Erkenntnisse aus der Entwicklung

1. **Code Interpreter-Sandbox ≠ Host-Filesystem.** Der Azure-CI hat
   keinen Zugriff auf `data/`. Lösung: server-seitige Tools für
   Import/Export (statt base64-Bridging), run_python für lokale Ausführung.

2. **GPT-5 Output-Limit für Tool-Arguments.** Base64-Strings > ~50 KB
   werden beim Transfer CI → Tool-Argument abgeschnitten.
   Lösung: `build_xlsx_from_tables` (Spec → Server baut), kein CI+base64.

3. **MAX_TOOL_ROUNDS.** Skill-getriebene Workflows brauchen 12+ Rounds.
   Von 12 auf 24 erhöht. Abort-Handling: offene Function-Calls werden
   mit synthetischem Output geschlossen, damit die Conversation nicht hängt.

4. **Große Dateien (> 1 MB) dürfen NICHT per fs_read in den Chat-Kontext.**
   Sprengt das Token-Limit. Lösung: run_python für lokales Parsing,
   Ergebnisse in die DB, nicht in den Chat.

5. **Portal-Agent als Single Source of Truth** für System-Prompt + Tools.
   Code referenziert per `agent_reference`, Portal-Edits wirken sofort.
   Versioniert (v1…v16), Rollback möglich.

6. **Skills > freie Improvisation.** GPT-5 arbeitet zuverlässiger wenn
   ein kuratiertes Playbook den Workflow vorgibt, statt frei zu improvisieren.
   Trigger-Tabelle im System-Prompt leitet Disco zum richtigen Skill.

7. **Tabellen-Namespace sauber trennen:** work_* (temporär), agent_*
   (dauerhaft), context_* (Lookup-Tabellen). Keine Schreibzugriffe auf
   Kern-Tabellen ohne explizite Whitelist.

---

## Stack

- Python 3.11+, `uv` als Paketmanager
- **SQLite** — system.db (zentral) + data.db (pro Projekt)
- **FastAPI + WebSocket** für Web-UI (`src/bew/api/`)
- **Azure OpenAI Responses API** (via Foundry-Projekt-Endpoint + API-Key)
- **Foundry Agent Service** — Portal-Agent mit agent_reference
- **openpyxl** — Excel lesen/schreiben
- **pypdf** — PDF-Text-Extraktion
- **markdown-it + highlight.js + DOMPurify** — Chat-Rendering (CDN)
- **SheetJS + pdf.js + PapaParse** — Viewer-Rendering (CDN)
- **MSAL** — OAuth2 Device-Flow für SharePoint (Phase 1)
- **httpx** — Microsoft Graph API

## Modulstruktur

| Pfad | Zweck |
|------|-------|
| `src/bew/cli.py` | CLI: `disco project/agent/db` (+ `bew` als Alias) |
| `src/bew/db.py` | SQLite-Verbindung + Migrations-Runner (system.db) |
| `src/bew/config.py` | Settings: DISCO_WORKSPACE, Foundry, Azure |
| `src/bew/workspace.py` | Projekt-Lifecycle: init, list, show, seed_sample |
| `src/bew/agent/core.py` | AgentService: Foundry Responses API + Tool-Loop |
| `src/bew/agent/context.py` | Projekt-Sandbox via contextvars |
| `src/bew/agent/system_prompt.md` | Discos Persönlichkeit + Regeln |
| `src/bew/agent/functions/` | 28 Custom Functions (data, fs, imports, executor, sources, skills, ...) |
| `src/bew/chat/repo.py` | Thread- + Message-Persistenz |
| `src/bew/api/main.py` | FastAPI: REST + WebSocket + Workspace-API |
| `src/bew/api/static/index.html` | Web-UI (Vanilla-JS, 3-Panel) |
| `skills/` | Kuratierte Playbooks (Markdown) |
| `migrations/` | System-DB-Migrationen (001–005) |
| `migrations/project/` | Projekt-DB-Template-Migrationen (001–003) |
| `scripts/foundry_setup.py` | Portal-Agent-Registrierung (REST + API-Key) |

## Workspace-Trennung

```
<repo-root>/                   ← Code-Repo (GitHub-synced)
├── src/, skills/, migrations/, scripts/

~/Disco/                       ← Daten-Workspace (NIEMALS in Git)
├── system.db                  ← zentrale DB (Threads, Projekte)
├── logs/
└── projects/
    ├── anlage-musterstadt/    ← ein Projekt (z. B. 1764 Dateien)
    ├── kraftwerk-nord/
    └── ...
```

Kundendaten verlassen nie das Repo. `.gitignore` schützt als Sicherheitsnetz.

## Konventionen

1. **Secrets niemals committen.** `.env` ist gitignored.
2. **Schema-Änderungen nur über Migrationen** — system.db: `migrations/NNN_*.sql`,
   Projekt-DB: `migrations/project/{datastore|workspace}/NNN_*.sql`.
   Bestehende Migrationen sind immutable.
3. **Kundendaten niemals in Git.** Alles unter `~/Disco/` bleibt lokal.
4. **Idempotenz.** Tools, Scans, Imports müssen bei Wiederholung dasselbe
   Ergebnis liefern.
5. **Nachvollziehbarkeit.** Jeder Scan → `agent_source_scans`, jedes
   Skript → `agent_script_runs`, jeder Chat → `chat_messages`.
6. **Vor neuen Features fragen:** in welche Phase gehört das?
7. **Prod-Migrierbarkeit (gilt ab 2026-04-24).** Seit Produktivbetrieb auf
   `~/Disco/projects/` gelten Bestandsdaten als unveränderlich. Jede
   Änderung an Schema, Filesystem-Layout, Memory-Format, Flow-Runner-
   Contract oder Config-Schema MUSS eine Migration mitliefern, die
   bestehende Projekte ohne Datenverlust überführt. Konkret:
   - **Neue Tabellen / Spalten:** `CREATE TABLE IF NOT EXISTS` bzw.
     `ALTER TABLE ADD COLUMN` in einer neuen Migration.
   - **Umbenennungen / Drops:** 3-Schritt (neu anlegen, Daten kopieren,
     Code umziehen, altes in einer späteren Migration droppen). **Kein
     direkter DROP** auf Tabellen mit Prod-Daten.
   - **FS-Layout-Änderungen:** Migrations-Script (Python, idempotent),
     das Bestandsprojekte ohne Datenverlust anpasst.
   - **Harte Cutover verboten** (wie der `data.db` → `datastore.db/workspace.db`-
     Split am 2026-04-23). Ausnahme nur mit expliziter User-Genehmigung
     im Chat + dokumentiertem Export-Pfad.
   - **Vor Prod-Anwendung:** Migration gegen eine rsync-Kopie eines
     echten Prod-Projekts testen, nicht nur gegen frisch-initialisierte.
8. **Entwicklungs-Pipeline (gilt ab 2026-04-24, Zyklus-Update 2026-04-24).**
   Trunk-Based-Setup mit genau **zwei Branches**: `main` (Prod) und `dev`
   (Arbeit). Keine Feature-/Hotfix-Branches, **keine Pull-Requests auf
   github.com als Gate** — fuer ein Zwei-Personen-Team (User + Claude)
   ist der PR-Zyklus Overhead ohne Nutzen. **GitHub ist Backup, nicht
   Gate.** Claude macht die lokale Versionsverwaltung inklusive Deploy,
   der User bestaetigt in jedem Zyklus explizit im Chat und pusht bei
   Gelegenheit zu origin als Remote-Backup.

   **Filesystem-Layout — zwei Worktrees desselben Repos:**
   - `~/Claude/BEW Doku Projekt/` → gepinnt auf `dev`. Claudes Arbeitskopie.
   - `~/Claude/BEW Doku Prod/` → gepinnt auf `main`. Prod-Deployment.

   Weil beide Worktrees dasselbe `.git/` teilen, sind Refs (`refs/heads/dev`,
   `refs/heads/main`) sofort in beiden Worktrees sichtbar, sobald sie lokal
   aktualisiert werden. Der Deploy-Schritt ist deshalb eine reine
   Working-Tree-Aktualisierung — kein Netz-Pull noetig.

   **Zwei Server laufen parallel (je in eigenem Terminal):**
   - **Dev**: `http://127.0.0.1:8766`, `DISCO_WORKSPACE=~/Disco-dev`,
     gestartet aus `BEW Doku Projekt`, mit `--reload`.
   - **Prod**: `http://127.0.0.1:8765`, `DISCO_WORKSPACE=~/Disco`,
     gestartet aus `BEW Doku Prod`, **ebenfalls mit `--reload`** — so
     greift ein Deploy ohne manuellen Server-Restart sofort (uvicorn
     laedt geaenderte Module nach dem `git reset --hard` automatisch
     neu; Flow-Subprocesses sind eh frische Python-Starts und ziehen
     den neuen Code vom Disk).

   **Zyklus pro Aenderung:**
   1. Claude committet inkrementell auf `dev` in `BEW Doku Projekt`.
   2. User testet am Dev-Server (:8766) und gibt Feedback im Chat.
   3. Wenn freigegeben: **Claude fragt** *"Soll ich auf Prod ziehen?"* —
      Prod wird **nie** ohne explizite Chat-Bestaetigung angefasst.
   4. Nach "ja" fuehrt Claude den Deploy lokal aus — **ein Command im
      Prod-Worktree, kein PR**:
      ```bash
      cd "/Users/BEW/Claude/BEW Doku Prod" && git merge --ff-only dev
      ```
      Da `main` im Prod-Worktree bereits ausgecheckt ist (und wegen
      Worktree-Lock nirgends sonst parallel ausgecheckt werden kann),
      wandert mit diesem einen Merge sowohl der `main`-Ref als auch der
      Working-Tree auf den Dev-Stand. `--ff-only` garantiert: Main
      uebernimmt exakt den Dev-Stand. Waere Main gegen Dev divergiert,
      bricht der Merge ab und Claude meldet das dem User, statt
      Geschichte zu ueberschreiben.
   5. Prod-Server uebernimmt den neuen Code automatisch via uvicorn
      `--reload`. Projekt-DB-Migrationen werden beim ersten Zugriff auf
      das jeweilige Projekt angewendet.
   6. User pusht `dev` + `main` via GitHub Desktop zu origin, **wenn es
      ihm passt** — als Remote-Backup, nicht als Deploy-Voraussetzung.
      Nicht blockierend fuer den Zyklus.

   **GitHub-Backup: kein PR-Merge mehr.** Der User pusht jetzt direkt
   beide Branches, statt PRs zu mergen. Grund: wenn `origin/main` einen
   Merge-Commit aus einem PR bekommt, divergiert es von der linearen
   lokalen `main`-History nach unseren ff-Deploys. Einmalige Bereinigung
   nach Umstellung: `git push --force-with-lease origin main` (in GitHub
   Desktop "Force push"). Danach pusht man normal ohne Force, weil alles
   ff bleibt.

   **Rollback:**
   ```bash
   # im Prod-Worktree auf den vorherigen Main-Commit:
   git reset --hard <commit-hash>
   # im Dev-Worktree, falls ganz zurueckgenommen werden soll:
   git checkout main && git reset --hard <commit-hash> && git checkout dev
   ```
   Reflog (`git reflog`) zeigt alle Stände der letzten Tage — nichts geht
   verloren. GitHub-Backup hilft zusaetzlich, wenn lokal etwas schief geht.

   **Safety-Netze:**
   - Claude fasst den Prod-Worktree **nur mit expliziter Chat-Bestaetigung**
     an. Kein automatisches Ziehen nach jedem Dev-Commit.
   - Nur `--ff-only` Merges. Bei Divergenz bricht der Deploy ab.
   - Claude pusht NICHT zu origin (osxkeychain blockiert Subprocess-
     Credentials). GitHub-Backup bleibt User-Aufgabe via GitHub Desktop.

   **Dev-Workspace (`~/Disco-dev`) ist bewusst getrennt von Prod
   (`~/Disco`)** — Dev-Code darf auf Prod-Daten NICHT rummachen. Fuer
   realistische Tests kopieren wir bei Bedarf ein echtes Prod-Projekt
   per `scripts/mirror_prod_project.sh <slug>` ins Dev-Workspace.

9. **Network-Egress strikt kontrolliert (gilt ab 2026-04-25).** Disco
   ist lokal-first. Externe Verbindungen gibt es ausschliesslich zu
   einer abschliessend aufgelisteten Menge (Azure Foundry / Sweden
   Central, Azure DI / Sweden Central) — siehe
   `docs/network-egress-policy.md`. **Neue externe Verbindungen
   (Cloud-API, NPM-Registry, CDN, Tracker, Telemetrie) werden vor der
   Implementierung im Chat begruendet und genehmigt**, dann in der
   Egress-Tabelle ergaenzt. Insbesondere in Prod werden keine neuen
   Verbindungen ungeplant hinzugefuegt — auch nicht "nur kurz fuer
   einen Test". JS-Libraries werden lokal gebundlet (siehe
   `src/disco/api/static/lib/`), kein CDN-Direkt-Import.

## Häufige Kommandos

```bash
uv sync                                        # Dependencies
disco project list                             # Alle Projekte
disco project init <slug> --name "..." [--sample]  # Neues Projekt
disco project show <slug>                      # Details
disco agent chat --project <slug>              # CLI-Chat im Sandbox
disco agent setup                              # Portal-Agent-Version pushen
disco agent threads                            # Alle Threads
disco db init                                  # System-DB-Migrationen
disco db status                                # Schema-Version

# Flows (Massenverarbeitung)
disco flow list --project <slug>                       # Alle Flows im Projekt
disco flow show <name> --project <slug>                # Details + letzte Runs
disco flow run <name> --project <slug> [--wait]        # Neuen Run starten
disco flow status <run_id> --project <slug>            # Laufender Status
disco flow pause <run_id> --project <slug>             # Pause-Signal
disco flow cancel <run_id> --project <slug> [--force]  # Cancel-Signal
disco flow items <run_id> --project <slug>             # Items mit Output
disco flow logs <run_id> --project <slug> [--tail N]   # Run-Logs

# Dev-Server (Claude-Arbeitskopie, Port 8766, eigener Workspace, Live-Reload):
cd "/Users/BEW/Claude/BEW Doku Projekt" && \
  DISCO_WORKSPACE=~/Disco-dev \
  uv run uvicorn disco.api.main:app --host 127.0.0.1 --port 8766 --reload

# Prod-Server (Prod-Arbeitskopie, Port 8765, echtes Workspace, Live-Reload):
cd "/Users/BEW/Claude/BEW Doku Prod" && \
  DISCO_WORKSPACE=~/Disco \
  uv run uvicorn disco.api.main:app --host 127.0.0.1 --port 8765 --reload
```

## Was als Nächstes kommt

### Flow-Integration für Disco (Phase 2c — laufend)
- Agent-Tools: flow_list, flow_show, flow_create, flow_run_start,
  flow_run_status, flow_run_pause, flow_run_cancel
- Skill `flow-builder` — Playbook für das gemeinsame Entwickeln
  und Testen eines Flows mit dem Nutzer
- Erster echter Flow (DCC-Klassifikation, SOLL/IST oder Excel-Report —
  entscheidet der Nutzer, sobald Framework integriert ist)
- Fundament steht: SDK, Worker, Migration 004, CLI, Test-Flow
  `flow-smoketest/file-stats` grün

### Portal-Agent für Flows erweitern
- System-Prompt-Regeln: wann Flow statt run_python
- Trigger-Tabelle: „10.000 Dokumente klassifizieren" → Flow-Builder-Skill

### Hybrid-Search (Phase 2c)
- Ein Suchdienst pro Projekt über alle Dateien (sources + context)
- Sparse (FTS5 / BM25) + Dense (Azure OpenAI Embeddings)
- Chunk-basiert (~500-800 Tokens), mit Metadaten (Pfad, Seite, Kind)
- `.disco/search-index/chunks.db`

### Frontend-Polish
- Viewer: Editor-Modus für Tabellen (Filter, Sort, Edit)
- Settings-Pane (Modell, Foundry-Endpoint)
- Drag&Drop Files in Explorer
- Excel-Download direkt aus dem Chat

### Weitere Skills
- `dokument-klassifikator` — DCC-/Gewerks-Klassifikation
- `sql-analyst` — Ad-hoc-SQL-Analysen mit Visualisierung
- `soll-ist-abgleich` — SOLL/IST-Vergleich gegen Informationsbedarfsliste

## Was NICHT tun

- Keine Kundendaten ins Repo committen.
- Keine Tabellen ohne Namespace-Prefix (work_*/agent_*/context_*).
- Kein `git add -A` — die `.gitignore` ist wichtig, aber einzeln stagen ist sicherer.
- Kein Wechsel auf Postgres ohne Architektur-Gespräch.
- Keine Azure-/Graph-Calls ohne Logging.
