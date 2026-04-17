# Disco — Produktvision und Stand

## Was ist Disco?

Disco ist ein agentisches Desktop-System für die Verarbeitung technischer
Dokumentation in Großprojekten. Es läuft lokal auf dem Rechner des
Nutzers, mit Anbindung an Sprachmodelle und AI-Services aus Microsoft
Azure (Region: Sweden Central, DSGVO-konform innerhalb der EU).

## Für wen?

Projektmitarbeiter in **Großprojekten** — Kraftwerke, Industrieanlagen,
Infrastruktur. Menschen, die täglich mit Zehntausenden technischen
Dokumenten aus verschiedenen Quellen umgehen müssen: PDFs, Excels,
Zeichnungen (DWG), Sharepoint-Exporte, Hersteller-Doku.

Der typische Nutzer ist **kein Programmierer**, aber technisch versiert
und mit den Inhalten der Dokumente vertraut. Disco ersetzt nicht das
Fachwissen — es macht die Arbeit handhabbar.

## Das Problem

In einem typischen Großprojekt liefert der Generalunternehmer
kontinuierlich Dokumente über Monate. Die Realität:
- Dokumente werden kopiert, überarbeitet, versioniert, geforkt
- Aus DWG werden PDF, ein Dokument wird kommentiert
- Verschiedene Quellen (SharePoint, E-Mail, USB) mit unterschiedlichen
  Ordnerstrukturen und Benennungskonventionen
- Begleit-Metadaten kommen separat als Excel
- Dokumentationsstandards (VGB, DIN) müssen eingehalten werden
- Am Ende muss ein SOLL/IST-Abgleich stehen: was ist da, was fehlt?

**Das Ergebnis: Dokumenten-Chaos.** Ohne systematische Unterstützung
verbringen Mitarbeiter Wochen mit manueller Sortierung und Zuordnung.

## Die Lösung: Disco

### Kern-Idee

Disco ist ein **Agent, der die Arbeit selbst ausführt** — nicht nur
berät. Der Nutzer formuliert Aufgaben in natürlicher Sprache, Disco
plant, führt aus, debuggt, iteriert. Vorbild: Claude Cowork (Anthropic),
aber gezielt auf technische Dokumentation zugeschnitten.

### Wie es funktioniert

#### 1. Projekt anlegen

Jedes Projekt hat einen konkreten Zweck:
- "1619 Dokumente gegen VGB S 831 klassifizieren"
- "Dokumenten-Index aufbauen mit Hersteller-/Typ-Zuordnung"
- "Dokumentation dreier Quellen in einheitliche Ordnerstruktur überführen"

Ein Projekt ist ein isolierter Workspace mit fester Verzeichnisstruktur
und eigener Datenbank. Kein Projekt sieht Daten eines anderen
(Mandantentrennung).

#### 2. Quellen anbinden

Quelldateien werden als Paket in den Workspace geladen (manuell oder
via SharePoint-Sync). Disco **registriert** jede Datei:
- SHA-256-Hash für Change-Detection
- Begleit-Metadaten aus Excel zuordnen
- Duplikate automatisch erkennen
- Bei neuem Paket: Delta-Erkennung (neu/geändert/gelöscht)

#### 3. Kontext aufbauen

Arbeitsgrundlagen — nicht zu bearbeitende Dateien, sondern
Nachschlagewerke (Normen, Kataloge, Richtlinien, Referenztabellen).
Disco analysiert, zusammenfasst und indiziert sie. Lookup-Tabellen
werden in die Datenbank importiert.

#### 4. LLM-ready machen

Bevor ein LLM über die Daten "reasonen" kann:
- Excel → Datenbank-Tabellen
- PDF → Text-Extraktion
- Index aufbauen (geplant: Hybrid-Search mit Embeddings + Volltext)
- Semantische Suche ermöglichen

#### 5. Disco arbeitet

Der Agent hat **echten Zugriff** auf das Projekt-Filesystem und die
Datenbank. Er kann:
- Dateien lesen, schreiben, verschieben
- Datenbank-Tabellen anlegen, füllen, joinen, auswerten
- **Python-Skripte schreiben und lokal ausführen** (für große Dateien,
  Bulk-Operationen)
- Professionelle Excel-Reports generieren (Multi-Sheet, Formatierung,
  Status-Farben, Hyperlinks)
- Erkenntnisse festhalten (NOTES, Memory)

Disco **kündigt an, was er tut, führt es aus, und meldet das Ergebnis.**
Keine Halluzination — das Tool-Ergebnis ist die Wahrheit.

#### 6. Pipelines (in Entwicklung)

Für Heavy-Lifting-Aufgaben über Tausende Dokumente:
- Pro Dokument ein LLM-Call (Klassifikation, Zusammenfassung, Extraktion)
- Disco baut die Pipeline auf, überprüft sie, überwacht den Durchlauf
- Separater Worker-Prozess, Job-Queue, Status-Tracking
- Der Agent koordiniert, das "Arbeitstier" (direktes Modell-Deployment)
  arbeitet

---

## Technische Architektur

### Stack

- **Lokal:** Python 3.11+, SQLite, FastAPI, Vanilla-JS
- **Cloud:** Azure OpenAI (GPT-5, Sweden Central), Foundry Agent Service
- **Kein Framework-Overhead:** Kein React, kein npm, kein Docker

### Workspace-Trennung

```
~/Claude/BEW Doku Projekt/    ← Code (GitHub-synced)
~/Disco/                       ← Daten (NIEMALS in Git)
```

Kundendaten verlassen nie den lokalen Rechner (außer an Azure EU für
LLM-Inferenz). Code-Repo enthält keine Daten.

### Agent-Architektur

- **Portal-Agent** ("bew-doku-agent") im Foundry-Portal: System-Prompt,
  Tool-Schemas, Modell — zentral verwaltet, versioniert, per Portal
  editierbar
- **Runtime:** Azure OpenAI Responses API via agent_reference.
  Streaming über WebSocket. 28 Custom Functions + Code Interpreter.
- **Custom Functions** laufen lokal (im FastAPI-Server-Prozess oder
  als Subprocess bei run_python)

### Skills (Playbooks)

Kuratierte Markdown-Anleitungen für wiederkehrende Aufgaben. Der Agent
lädt sie bei Bedarf (lazy-loading, spart Tokens). Aktuell:
- `project-onboarding` — Session-Start-Routine
- `sources-onboarding` — Quellen registrieren
- `context-onboarding` — Kontext-Dateien sichten
- `excel-reporter` — Excel-Reports bauen
- `python-executor` — Skripte schreiben + ausführen + debuggen

### Web-UI

Drei-Panel-Layout:
- **Links:** Projekt-Selector, Explorer-Tree, DB-Tabellen, Chat-Liste
- **Mitte:** Chat mit Disco (Markdown, Code-Highlighting, Tabellen,
  Tool-Call-Blöcke)
- **Rechts:** Viewer (Markdown, CSV, Excel, PDF, DB-Tabellen —
  paginiert, sortierbar)

---

## Aktueller Stand (April 2026)

### Was funktioniert

- ✅ Projekte anlegen, verwalten, wechseln
- ✅ Quelldateien registrieren mit Hash-basierter Delta-Erkennung
- ✅ Begleit-Metadaten aus Excel zuordnen (Pfad-Matching)
- ✅ Duplikate automatisch erkennen
- ✅ Excel/CSV-Daten in die Datenbank importieren
- ✅ Professionelle Multi-Sheet-Excel-Reports generieren
- ✅ PDF-Text extrahieren
- ✅ Kontext-Dateien sichten und katalogisieren
- ✅ Python-Skripte lokal schreiben, ausführen, debuggen
- ✅ Freier SQL-Zugriff (read + write im Namespace)
- ✅ Multi-Thread-Chat mit Session-Persistenz
- ✅ Onboarding-Routine (README + NOTES + Memory + Context-Manifest)
- ✅ Web-UI mit Chat + Explorer + Viewer
- ✅ DSGVO: alles in Azure Sweden Central (EU)

### Was noch kommt

- ⏳ **Pipelines** — Bulk-LLM-Aufgaben über Tausende Dokumente
- ⏳ **Hybrid-Search** — Embeddings + FTS5 über Sources + Context
- ⏳ **Frontend-Polish** — Editor in Tabellen, Settings-Pane, Drag&Drop
- ⏳ **Weitere Skills** — dokument-klassifikator, sql-analyst, soll-ist-abgleich
- ⏳ **SharePoint-Live-Sync** (Phase 1 Infrastruktur steht, Integration in Disco-Workflow noch offen)

---

## Schlüssel-Erkenntnisse

1. **Der Agent muss die Arbeit so gestalten, dass er nicht ans Token-Limit stößt.**
   Große Dateien: lokal parsen via `run_python`. Excel-Export: serverseitiges Tool
   statt Code-Interpreter+base64. Bulk-Ops: Skript, nicht 1000× Tool-Call.

2. **Skills sind effektiver als freie Improvisation.** Kuratierte Playbooks
   mit konkreten Tool-Call-Sequenzen liefern zuverlässigere Ergebnisse als
   "GPT-5, improvisiere mal".

3. **Mandantentrennung muss physisch sein, nicht nur logisch.** Eigene
   Projekt-DB + Sandbox-Context statt globaler Tabellen mit Projekt-FK.

4. **Portal-Agent als Single Source of Truth** für den System-Prompt.
   Code referenziert per ID, Portal-Edits wirken sofort. Kein Code-Deploy
   für Prompt-Tuning.

5. **Anti-Halluzination ist eine System-Eigenschaft, nicht nur ein Prompt-Hint.**
   Tool-Result = Wahrheit. "Fertig" erst nach erfolgreichem Tool-Call. Abort-
   Handling für offene Function-Calls.

---

## Lizenz / Status

Internes Entwicklungsprojekt von Discoverse (Raphael@discoverse.ai).
Kein Open-Source-Release geplant — Evaluierung als kommerzielles Produkt.
