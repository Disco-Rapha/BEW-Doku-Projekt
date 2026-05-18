# Disco — Produktvision und Stand

**Stand:** 2026-05-09. Lebendes Dokument — wird bei
Architektur-Entscheidungen und Vision-Gesprächen fortgeschrieben.

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
- Erkenntnisse strukturiert ablegen — chronologisch in `NOTES.md`
  (Auto-Archivierung > 30 Tage), destilliert in `DISCO.md`
  (3-Schichten-Modell mit Marker + chapter-meta-Kapiteln + Trace-Log),
  Tabellen-Wissen in `agent_table_docs` per `table_doc_set`/`table_doc_get`

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
- **Cloud:** Azure OpenAI (GPT-5.x in Sweden Central, Deployment-Name in `.env`), Foundry Agent Service
- **Kein Framework-Overhead:** Kein React, kein npm, kein Docker

### Workspace-Trennung

```
<repo-root>/                   ← Code (GitHub-synced)
~/Disco/                       ← Daten (NIEMALS in Git)
```

Kundendaten verlassen nie den lokalen Rechner (außer an Azure EU für
LLM-Inferenz). Code-Repo enthält keine Daten.

### Agent-Architektur

- **Portal-Agent** ("disco-prod-agent" / "disco-dev-agent") im Foundry-Portal: System-Prompt,
  Tool-Schemas, Modell — zentral verwaltet, versioniert, per Portal
  editierbar
- **Runtime:** Azure OpenAI Responses API via `agent_reference`.
  Streaming über WebSocket. **41 Custom Functions + Code Interpreter**
  (Stand 2026-05-09).
- **Custom Functions** laufen lokal (im FastAPI-Server-Prozess oder
  als Subprocess bei run_python)

### Skills (Playbooks)

Kuratierte Markdown-Anleitungen für wiederkehrende Aufgaben. Der Agent
lädt sie bei Bedarf (lazy-loading, spart Tokens). Aktuell 12 Skills:

- `project-onboarding` — Session-Start-Routine inkl. 3-Schichten-Memory
- `sources-onboarding` — Quellen registrieren + Metadaten + Duplikate
- `context-onboarding` — Kontext-Dateien sichten + Manifest pflegen
- `excel-reporter` — Multi-Sheet-Excel via `build_xlsx_from_tables`
- `excel-formatter` — openpyxl-Detail-Spec
- `python-executor` — Skripte schreiben + ausführen + debuggen
- `flow-builder` — Massenverarbeitung gemeinsam aufbauen
- `flow-supervisor` — laufende Flows überwachen
- `pipeline-diagnostics` — Routing-/Extraktionsprobleme analysieren
- `report-builder` — HTML-Reports mit klickbaren Quellen
- `sdk-reference` — Azure-SDK-Snippets (DI + OpenAI)
- `planning` — mehrstufige Pläne in `.disco/plans/`

### Web-UI

Drei-Panel-Layout:
- **Links:** Projekt-Selector, Explorer-Tree, DB-Tabellen, Chat-Liste
- **Mitte:** Chat mit Disco (Markdown, Code-Highlighting, Tabellen,
  Tool-Call-Blöcke)
- **Rechts:** Viewer (Markdown, CSV, Excel, PDF, DB-Tabellen —
  paginiert, sortierbar)

---

## Aktueller Stand (Mai 2026)

### Was funktioniert

- ✅ Projekte anlegen, verwalten, wechseln
- ✅ Quelldateien registrieren mit Hash-basierter Delta-Erkennung
- ✅ Begleit-Metadaten aus Excel zuordnen (Pfad-Matching)
- ✅ Duplikate automatisch erkennen
- ✅ Excel/CSV-Daten in die Datenbank importieren
- ✅ Professionelle Multi-Sheet-Excel-Reports generieren
- ✅ PDF-/Excel-/DWG-/Bild-Text extrahieren (Multi-Format-Routing)
- ✅ Kontext-Dateien sichten und katalogisieren
- ✅ Python-Skripte lokal schreiben, ausführen, debuggen
- ✅ Freier SQL-Zugriff (read + write im Namespace)
- ✅ Multi-Thread-Chat mit Session-Persistenz
- ✅ Onboarding-Routine mit 3-Schichten-Memory (Schicht 1 + Kapitel-
  Index, on-demand-Kapitel, Tabellen-Doku, Trace-Log)
- ✅ Web-UI mit Chat + Explorer + Viewer (PDF, Excel, CSV, JSON,
  Markdown, **HTML mit Sandbox-iframe**, DXF, Bilder) plus
  📂-Open-in-OS-Button
- ✅ Massenverarbeitung über Flows (Subprocess, Resume, Cost-Cap,
  pausierbar)
- ✅ Volltext-Suche (`build_search_index` + `search_index`)
- ✅ DSGVO: alles in Azure Sweden Central (EU), Network-Egress-Policy
  in `docs/network-egress-policy.md`

### Was noch kommt (taktisch)

- ⏳ **Hybrid-Search** ausbauen — Embeddings + FTS5-Vorhandenes
  zusammenführen
- ⏳ **Frontend-Polish** — Editor in Tabellen, Settings-Pane, Drag&Drop
- ⏳ **Weitere Skills** — dokument-klassifikator, sql-analyst,
  soll-ist-abgleich
- ⏳ **Stable-Release v1.0** — nach Aufräumen Audit-Findings + Tests

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

---

## Strategische Vision — vom Dokumentenmanagement zum Projektbüro-Agent

**Status:** strategisch, nicht akut — Anker für künftige Vision-
Gespräche, nicht aktive Roadmap.

### Kern-These

Disco ist heute ein starkes **Dokumentenmanagement-Tool** für
technische Großprojekte. Die zugrundeliegende Architektur (Pipeline,
Skills, Flows, Search, Multi-Format-Routing, Excel-/HTML-Reports) ist
aber **bewusst generalistisch** angelegt. Damit hat Disco das Potenzial,
sich zu einem **vollwertigen Projektbüro-Agent** zu entwickeln — ein
KI-Tool, das die ganze Bandbreite an Projektbüro-Aufgaben systematisch
unterstützt.

### Themenfelder (heute live + Vision)

Heute live: **Dokumentenmanagement** — Quellen registrieren,
kanonisieren, extrahieren, indizieren, suchen, Reports bauen.

Geplant / als Vision:

1. **Legal / Contract Management** — Verträge mit Generalunternehmern
   strukturiert verwalten, Klauseln nachschlagen, Fristen tracken.
2. **Claim Management** — Nachforderungen und Mängelansprüche mit
   Beleg-Trail. Verknüpfung zwischen Vertragsklausel, Korrespondenz,
   Kostenfolge.
3. **Contract Communication** — bei FIDIC-Verträgen mit GUs läuft
   Kommunikation hochstrukturiert nach klausel-bezogenen Notification-
   Pflichten ab. Disco kann hier als Klausel-bewusster Schreib- und
   Recherche-Assistent fungieren.
4. **Qualitätsmanagement** — z. B. mechanische Endkontrollen bei BEW.
   Pflicht-Berichte, Checklisten, Konsistenz-Prüfung gegen Normen
   (VGB S 831 etc.).
5. **Terminplanung** — Schedule-Management, Verzugs-Analyse,
   Critical-Path-Verständnis.
6. **Weitere Projektbüro-Themen** — Risiko-Management, Reporting an
   Auftraggeber, Variation-Orders, Subcontractor-Koordination.

### Vision in einem Satz

> Disco ist das KI-gestützte Projektbüro für technische Großprojekte:
> es hält die Daten parat, verbindet die Themen, treibt die Prozesse,
> und hebt damit die Qualität der Projekt-Steuerung deutlich.

### Was technisch passt / was fehlt

**Passt schon heute:** Pipeline-Architektur ist projektagnostisch
(Registrierung → Anreicherung → Kanonik → Routing → Extraction →
Suchindex). Skills sind themen-spezifisch erweiterbar ohne Kern-
Eingriff. SQL-Tabellen + Lookup-Excels passen für Vertragsklausel-
Kataloge, Norm-Matrizen, QM-Vorgabe-Listen. Multi-Format-Routing
deckt PDF/Excel/DWG/Bild/HTML ab; DOCX/PPTX in Phase 2b.
Cost-Tracking ist in Place.

**Was für die Vision noch fehlt:**

- **Frist-Tracking / Date-Reasoning** — bei FIDIC-Notifications und
  Claim-Fristen ist „28 days from becoming aware" Pflicht. Disco
  müsste Datums-aware werden, Fristen aus Klauseln ableiten und
  proaktiv erinnern.
- **Cross-Document-Linkage explizit modellieren** — heute haben wir
  Duplikate strukturell als mehrere `agent_source_locations` pro Hash.
  Für Claim-Trail bräuchten wir reichere Relations: „antwortet auf",
  „bezieht sich auf Klausel", „belegt Cause für".
- **Workflow-Engine für Genehmigungs-Prozesse** — wer hat was wann
  unterschrieben, was steht aus.
- **E-Mail-/Kommunikations-Integration** — Outlook/MS365-Anbindung für
  Korrespondenz-Tracking. Heute alles File-basiert.
- **Domain-Skills pro Themenfeld** — Legal/QM/Terminplanung jeweils
  ein eigenes Skill-Set mit Trigger-Phrasen, Workflow-Templates,
  Pflicht-Checks.

### Empfehlung für die Reifung

- **Generalistisch bleiben hat Wert.** Disco wird in jedem Projekt
  nützlich. Aber jede neue Domäne erhöht System-Prompt-/Skill-/Tool-
  Komplexität. Saubere Skill-Trennung ist Pflicht.
- **Eine Domäne nach der anderen reifen lassen** — nicht alle 5
  parallel. Vorschlag-Reihenfolge: Legal/Contract zuerst (klare
  Strukturen, FIDIC-Standard hilft), dann QM, dann Termin.
  Claim-Management baut auf Legal auf.
- **Pipeline + Search + Reports bleiben generisch** — sind das
  Fundament. Domänen-spezifische Logik kommt rein über Skills +
  themen-spezifische Tools, nicht durch Eingriff in den Kern.
- **Kunden-Datenschutz wird kritischer** mit Legal-Inhalten. DSGVO,
  Anwaltsgeheimnis, Mandantentrennung — heute über Workspace-
  Isolation gelöst, müsste für Vertragsdaten ggf. nochmal verschärft
  werden (z. B. Foundry-Region-Pinning auf EU + Audit-Logs).

Konkret: Nach Stable-Release v1.0 wäre der natürliche Punkt, mit der
ersten Domain-Erweiterung (Vorschlag: Legal/FIDIC) zu starten.

---

## Lizenz / Status

Internes Entwicklungsprojekt von Discoverse (Raphael@discoverse.ai).
Kein Open-Source-Release geplant — Evaluierung als kommerzielles Produkt.
