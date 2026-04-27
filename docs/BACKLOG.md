# Disco — Backlog (gesammelte Punkte zur Umsetzung)

Hier landen Beobachtungen und Ideen aus dem Testen, die nicht sofort
umgesetzt werden, aber beim nächsten Iterationsschritt berücksichtigt
werden sollen.

---

## UI / Chat-Erlebnis

### UI-Awareness für Disco (Priorität: mittel)

Disco weiß aktuell nicht, wie das Frontend aussieht. Er soll:

- **Den User navigieren können**: "Klick links im Explorer auf
  `sources/Elektro/` um die Dateien zu sehen", "Schau Dir die
  Tabelle `agent_sources` links unter 'Datenbank-Tabellen' an"
- **Wissen, was der Viewer kann**: "Klick auf die Excel rechts im
  Viewer, dort siehst Du Sheet 2 mit der IBL"
- **Proaktive Hinweise geben** wenn der User nicht weiterweiss:
  "Du kannst im Explorer links auf eine Datei klicken, dann
  erscheint sie rechts im Viewer."

→ System-Prompt um eine kurze UI-Beschreibung ergänzen, damit Disco
  weiss welche Elemente wo sind.

### Klickbare Links im Chat → Viewer + Explorer (Priorität: hoch)

Wenn Disco im Chat eine Datei oder DB-Tabelle erwähnt, soll das ein
**klickbarer Link** sein. Klick öffnet:
- Datei im **Viewer** (rechts)
- Datei im **Explorer** (links, selektiert/aufgeklappt)

Beispiel im Chat:
> "Ich habe die Ergebnisse in [`exports/ibl_2026-04-17_v1.xlsx`](#) 
> gespeichert. Die Tabelle [`agent_sources`](#) enthält jetzt 1763 
> Einträge."

Klick auf den Excel-Link → Viewer öffnet die Excel rechts.
Klick auf den Tabellen-Link → Viewer zeigt die DB-Tabelle paginiert.

**Technisch:**
- Disco gibt im Markdown spezielle Links:
  `[dateiname](disco://file/exports/ibl.xlsx)` oder
  `[tabellenname](disco://table/agent_sources)`
- Frontend erkennt das `disco://`-Protokoll und routet entsprechend
- Alternativ: ein `data-`-Attribut im HTML das das Frontend abfängt

→ System-Prompt: "Wenn Du Dateien oder Tabellen im Chat erwähnst,
  verlinke sie, damit der Nutzer direkt draufklicken kann."

### Slash-Referenzen im Chat-Input (Priorität: hoch)

Der Nutzer will im Chat einfach auf **konkrete Ressourcen des aktiven
Projekts** verweisen können, ohne Dateipfade zu tippen oder zu
copy-pasten. Vorbild: Cursor/VS Code/Claude Code mit `@file`- bzw.
`/`-Mentions.

**Bedienung:**
- Im Chat-Input `/` tippen → Picker klappt auf
- Fuzzy-Search live während des Tippens
- Auswahl per Enter/Klick fügt einen Referenz-Chip in die Nachricht ein
- Beim Absenden bekommt Disco die Referenz als strukturierten Bezug,
  nicht nur als freien Text

**Was referenzierbar sein soll:**
- Dateien unter `sources/`, `context/`, `work/`, `exports/`
- DB-Tabellen (`agent_*`, `work_*`, `context_*`)
- NOTES-Einträge (chronologisch, letzte N)
- Optional: Skills als Slash-Kommando (`/sources-onboarding`,
  `/excel-reporter`)
- Optional: gespeicherte Abfragen oder Reports

**Beispiel:**
> User tippt: „Vergleich bitte /
> → Picker zeigt: `context/vgb-s-831.pdf`, `sources/Plan_A1.pdf`,
>   Tabelle `agent_sources`, …
> User wählt Datei + Tabelle
> Nachricht wird: „Vergleich bitte @context/vgb-s-831.pdf mit
> @agent_sources und sag mir, wo Lücken sind."

**Technische Optionen für die Übergabe an Disco:**
- a) Inline als Markdown-Link mit `disco://`-Protokoll (symmetrisch
     zu den klickbaren Links im Output — ein Protokoll für beide
     Richtungen)
- b) Separater Metadata-Block vor dem User-Text („Der Nutzer
     referenziert folgende Ressourcen: …")
- c) Frontend zieht pro Referenz einen kurzen Steckbrief (Dateigröße,
     erste N Zeilen, Tabellen-Schema, Zeilenzahl) und hängt ihn als
     strukturierten Kontext mit an

Empfohlen: **(a) + (c) kombiniert** — User-Text bleibt lesbar, Disco
bekommt gleichzeitig einen knackigen Steckbrief pro Referenz. Kein
blindes `fs_read` vorneweg nötig.

**Nebeneffekt:** Disco hört auf, am Anfang jedes Turns mit `fs_list`
oder `sqlite_query` blind Inventur zu machen — der Nutzer zeigt
explizit worauf er sich bezieht. Das spart Tool-Rounds und Kontext.

### Dateiinhalte im Preview öffnen (Priorität: Zukunft, nicht MVP)

Disco soll dem Frontend sagen können: "Öffne diese Datei im Viewer."
Technisch: ein spezielles Event im WebSocket-Stream, das das Frontend
interpretiert und den Viewer öffnet/scrollt.

Beispiel:
```json
{"type": "open_in_viewer", "path": "exports/ibl_2026-04-17_v1.xlsx", "sheet": "3-IBL"}
```

Das Frontend reagiert: Viewer öffnet sich rechts, zeigt Sheet 3-IBL.

→ Erst nach MVP, wenn die Viewer-Funktionalität stabil ist.

---

## Report-Format / Analyse-Ergebnisse

### Excel mit openpyxl auf Cowork-Niveau verwenden (Priorität: hoch)

Disco hat `run_python` + openpyxl an Bord und kann damit alles, was
Claude Cowork mit Excel macht — Formatierung lesen, Farben/Fonts/
Borders setzen, Merged Cells, Formeln, Hyperlinks, Bilder. Die
Infrastruktur steht.

**Was fehlt:** Der Reflex. Disco greift heute zu `import_xlsx_to_table`
(Tabelle in DB), weil das Tool bequem ist — und sieht dadurch keine
Formatierung. Wir brauchen:

- **Skill `excel-formatter.md`** mit den Patterns: `load_workbook`
  ohne `read_only`/`data_only`, Fills/Fonts/Borders-Rezepte, Merged-
  Cells-Handling, Formel-Preservation, `wb.save()`-Pflicht.
- **Trigger-Tabelle im System-Prompt:** „Excel-Formatierung lesen oder
  ändern, Farben, Formeln, Merges → Skill `excel-formatter` laden und
  `run_python` verwenden. Tabellen-Import in die DB nur, wenn
  Formatierung irrelevant ist."
- Optional: `xlsx_inspect_full` — Read-Tool, das Styles/Merges/Formeln
  strukturiert als JSON liefert, damit Disco fürs reine Anschauen
  nicht jedes Mal 15 Zeilen Python schreiben muss.

Ziel: Disco nutzt openpyxl routiniert wie Cowork — kein eigenes
„Formatierungs-Tool", sondern freies Python mit einem guten Playbook.

---

## Chat-Funktionalität

### Chat haengt nach Foundry `response.failed` (Bug, Priorität: hoch — aus UAT 2026-04-20)

**Symptom:** Waehrend ein Flow mit demselben Modell-Deployment lief
(`gpt-5.1_prod`, Flow #4 dcc_repredict_lagerhalle), brach ein Agent-
Turn mit "FEHLER: Foundry meldet Fehler: unbekannt" ab. Danach blieb
der Chat in "Disco denkt..." haengen — neue User-Nachrichten
liefen ins Leere, auch nach Browser-Reload (Cmd-R). Einziger Ausweg
war ein **Prozess-Neustart des Servers**.

**Vermutete Ursache:** Nach `response.failed` zeigt
`previous_response_id` noch auf die vergiftete Response; Foundry
kann die Chain nicht weiterbedienen, der Agent-Loop blockiert still
im naechsten Stream-Aufruf (kein 400, kein Timeout sichtbar). Der
Trigger-Fehler selbst war wahrscheinlich ein **429 / Quota-Limit**
durch den parallel laufenden Flow (siehe Eintrag "Getrennte Modell-
Deployments" unter Flows).

**Teil-Fix bereits in Dev:** Reichere Fehlermeldung in
`src/disco/agent/core.py` — statt "unbekannt" werden `code`, `type`
und `message` aus `event.response.error` extrahiert und geloggt.
Hilft beim Diagnostizieren, heilt aber den Hang nicht.

**Noch zu bauen:**
1. Nach `response.failed` die `previous_response_id` sofort auf NULL
   setzen (Chain abbrechen, frischer Start beim naechsten User-Input).
2. Server-seitigen WebSocket-Keepalive haerten: wenn der Agent-
   Turn-Generator haengt, nach Timeout (z. B. 5 min) abbrechen und
   dem Client ein Error-Event schicken, statt stumm zu blockieren.
3. Im UI: Wenn "Disco denkt..." laenger als z. B. 90 s, eine
   Hinweisbox mit "Neuen Turn starten"/"Verbindung ruecksetzen"
   anzeigen.

Schwesternbug zu "No tool output found" oben — gleicher Mechanismus
(verseuchte Chain), anderer Trigger (response.failed statt offener
Tool-Call).

---

## Modell-Einstellungen (Reasoning, Verbosity, …)

### Reasoning- und Modell-Parameter bewusst steuern (offen, kein konkreter Plan — Beobachtung 2026-04-21)

**Beobachtung Nutzer:** Wir rufen heute sowohl den Agent-Chat als auch
die Flows mit **Default-Modell-Parametern** auf. Das ist für einfache
Anfragen ok, aber wir hebeln damit einen Hebel nicht, den GPT-5.1
mitbringt.

- Bei **komplexen Chat-Anfragen** (Multi-Tool-Analyse, Cross-Source-
  Reasoning, SOLL/IST-Vergleich) würde ein höheres Reasoning-Budget
  (`reasoning.effort = "high"` statt Default) wahrscheinlich bessere
  Ergebnisse bringen — zu Lasten von Latenz + Kosten.
- Bei **Flow-Prompts** (DCC-Klassifikation pro Dokument, Metadaten-
  Extraktion, Duplikat-Check) ist die Frage anders: der Flow läuft
  N×1000 Mal, da zählt Kosten/Durchsatz pro Einzel-Call mehr als die
  letzten paar Qualitätsprozente. Dort ist evtl. `effort = "minimal"`
  oder `"low"` sinnvoll als Default.

**Parameter, die heute nicht gesteuert werden (aber evtl. sollten):**
- `reasoning.effort` (minimal / low / medium / high) — GPT-5/5.1
- `reasoning.summary` (auto / concise / detailed) — für Reasoning-
  Events im Live-Stream
- `text.verbosity` (low / medium / high) — kürzere/längere Antworten
- `max_output_tokens` — wir haben den Tool-Loop gedeckelt, aber nicht
  die Token-Antwortlänge pro Turn
- `temperature` / `top_p` — falls für deterministische Flows relevant

**Offene Designfragen:**
- **Chat:** „Deep-Mode"-Toggle im UI („für diese Frage bitte mit
  maximalem Reasoning"), oder soll Disco das selbst einschätzen?
  Vorbild Claude Cowork: „Extended Thinking"-Button.
- **Flow-SDK:** `FlowRun.model_params` pro Flow konfigurierbar machen
  (im Flow-README oder `runner.py`), mit sinnvollen Defaults je Flow-
  Typ (Klassifikation: low; komplexe Analyse: high).
- **Kostenmodell:** Reasoning-Tokens werden von Azure gesondert
  abgerechnet — bei `effort=high` können die Kosten pro Turn spürbar
  steigen. In den Kosten-Tracker einbauen.
- **Experimente:** Baseline vs. high-effort auf demselben Testset
  (z.B. 20 DCC-Klassifikationen aus `bew-dcc-optimizer`) — lohnt sich
  der Aufwand qualitativ?

**Wann angehen:** kein akuter Trigger, aber spätestens wenn Disco bei
komplexen Chat-Anfragen schwächelt oder Flow-Kosten höher sind als
nötig. Ursprung: Nutzer-Beobachtung 2026-04-21 bei Backlog-Review.

---

## Projekt-Template / Wissens-Dateien

### Projekt-Template radikal entrümpeln — nur README/DISCO/NOTES (Beobachtung 2026-04-21, noch nicht entscheiden)

**Status:** Beobachtung aus Prod-Projekt `bew-dcc-classification-optimizer`
(seit 20.04. aktiv). Noch **nicht umsetzen** — erst weiter beobachten,
ob sich das Bild bei anderen Projekten bestätigt.

**Befund:** Von den 9 Wissens-Orten, die das Projekt-Template heute
anlegt, werden **3 gelebt und 6 sind tot**:

| Datei / Ordner | Zustand | Schreibt rein |
|---|---|---|
| `DISCO.md` | **gut gepflegt** — Konventionen, 7-Schritt-Vorgehensmodell, aktueller Fokus | Disco |
| `NOTES.md` | **gut gepflegt** — chronologisch, Datum + Titel + Details | Disco |
| `README.md` | **tot** — Template-Platzhalter `*(Was soll am Ende...)*` stehen seit Anlage drin | Nutzer (theoretisch) |
| `context/_manifest.md` | **tot** — „leer — Disco füllt beim nächsten…", trotz 6 echter Kontextdateien | Disco (theoretisch) |
| `.disco/plans/` | **leer** | — |
| `.disco/sessions/` | **leer** | — |
| `.disco/context-extracts/` | **leer** (Extrakte landen in der DB, nicht im FS) | — |
| `.disco/context-summaries/` | **leer** | — |
| `.disco/local-skills/` | **leer** (Feature noch nicht gebaut) | — |

**Zwei strukturelle Fehler sichtbar:**

1. **Template-Skelette sehen zu „fertig" aus.** In DISCO.md stehen
   BEIDE Konventionen-Abschnitte parallel: der leere Template-Block
   UND der echte gefüllte Block, den Disco unten drangehängt hat.
   GPT-5.1 überschreibt Template-Platzhalter nicht, er ignoriert sie
   oder appended. Dasselbe Muster bei README und `_manifest.md`: das
   Modell sieht ein Skelett, denkt „ist ja schon strukturiert",
   schreibt nicht rein.

2. **Session-Start-Routine prüft Template-Füllstand nicht.** Die
   README bleibt seit 20.04. im Template-Zustand — Disco hat nie
   gefragt „Deine README ist leer, was ist das Projektziel?". Das war
   Teil der angedachten Memory-SOP, greift aber im Verhalten nicht.

**Richtung, wenn wir es irgendwann angehen:**

| Datei | Eigentümer | Zweck |
|---|---|---|
| `README.md` | **Nutzer** | Projektziel, Auftraggeber, Frist. Klein, stabil. |
| `DISCO.md` | **Disco** | Destilliertes Wissen: Konventionen, Vorgehen, Fokus, Lookup-Pfade, Glossar, Entscheidungen. Thematisch gegliedert, wachsend, überschreibbar. |
| `NOTES.md` | **Disco** | Chronologisches Logbuch. Append-only. |

**Raus aus dem Template:**
- `context/_manifest.md` — Inhalte als Abschnitt `§Kontext` in DISCO.md
- `.disco/plans/` — Pläne in NOTES pro Arbeitspaket oder DISCO „Aktueller Fokus"
- `.disco/sessions/` — erst anlegen, wenn Conversation-Compaction gebaut ist
- `.disco/context-extracts/` + `.disco/context-summaries/` — Extrakte leben in der DB (`agent_md_extracts` etc.)
- `.disco/local-skills/` — erst, wenn das Feature da ist

`.disco/` behielte nur `flows/` (Runtime-State für Flow-Worker). Alles
andere: weg.

**Template-Entscheidung (wenn wir ziehen):**
- Entweder **leere Dateien** (nur H1 + 1 Zeile Hinweis), damit Disco
  auf leerem Blatt anfängt zu schreiben statt Template-Lücken zu
  ignorieren.
- Oder **gar nicht initial anlegen** — DISCO.md / NOTES.md entstehen
  beim ersten Schreibzugriff.

**Session-Start-Regel (neu):** wenn README-Platzhalter noch drin sind
(`*(Was soll am Ende...)*`, `*(Welche Daten...)*`), muss Disco den
Nutzer aktiv nach Projektziel + Kontext fragen und die Antwort als
strukturierten Abschnitt in die README schreiben — **bevor** er mit
fachlicher Arbeit anfängt.

**Warum nicht jetzt:** Das Bild stammt aus einem einzigen Projekt.
Erst beobachten, ob
- andere Projekte denselben Pattern zeigen,
- ob `.disco/context-extracts/` bei einem Projekt mit aktiver
  Context-Onboarding-Routine vielleicht doch genutzt wird,
- ob die Template-Skelette in DISCO.md überschrieben werden, sobald
  die Session-Start-SOP schärfer ist (ohne das Template zu ändern).

**Offene Fragen für später:**
- Betrifft die Migration bestehende Projekte? → Auto-Migration beim
  Projekt-Open („leere Template-Stubs entfernen, wenn unberührt seit
  Projekt-Anlage")? Oder manuell-opt-in?
- Was passiert mit dem `_manifest.md`-Konzept in Projekten, die es
  doch gefüllt haben?
- Sollen die Stubs lazy angelegt werden (on-first-write), oder
  gar nicht?

Ursprung: UAT-Review 2026-04-21, Nutzer-Beobachtung: „Disco nutzt
einige Dateien nicht (manifest.md und pläne auch nicht). Ggs
brauchen wir auch diese Dokumente nicht und wir lassen disco das
ganze Wissen in einer Datei sammeln."

---

## UI / Layout

### ~~PDF-Viewer funktioniert noch nicht (Bug)~~ — gefixt 2026-04-21

Ursache war `pdfjs-dist@4.0.379`: ab 4.x ist pdf.js ESM-only.
`<script src="…pdf.min.js">` ohne `type="module"` scheitert mit
SyntaxError, `window.pdfjsLib` bleibt undefined → Viewer zeigt
"pdf.js nicht geladen".

Fix: auf `pdfjs-dist@3.11.174` gepinnt (letzte UMD-Version), in Dev
*und* Prod. Browser-Reload (Cmd+Shift+R), dann PDF erneut öffnen.

---

## Document Intelligence

### Kosten-Monitoring + Sicherheitsgrenzen (Priorität: hoch)

Alle externen Dienste kosten pro Call/Seite/Token. Risiko: ein
festgefahrener Loop oder ein zu großer Batch kann unerwartet hohe
Kosten verursachen.

**Was wir absichern müssen:**

1. **Agent-Calls (GPT-5):**
   - MAX_TOOL_ROUNDS ist auf 24 gedeckelt → schützt vor Endlos-Loops
   - Aber: Token-Kosten pro Turn sind nicht gedeckelt. Ein Turn mit
     20 Tool-Calls und großen Results kann leicht 50-100k Tokens
     fressen → 0.50-1.00 € pro Turn
   - → Kosten-Tracker pro Session: nach jedem Turn die kumulierten
     Tokens addieren, bei > X € warnen

2. **Document Intelligence:**
   - Pro Seite 0.00868 € (azure-di) bis 0.01389 € (azure-di-hr).
     Eine 800-Seiten-Norm = 7-11 €.
   - Risiko: User legt versehentlich 100 PDFs in context/ →
     Disco jagt alle durch DI → 500-1000 €
   - → Sicherheitsgrenze: max. N Seiten pro Context-Onboarding-Run
     (z.B. 500 Seiten), danach Rückfrage. Oder: max. N PDFs pro
     Run (z.B. 10), Rest manuell bestätigen.

3. **Pipelines (Zukunft):**
   - Pro Dokument ein LLM-Call = akkumulierte Kosten
   - → Kosten-Schätzung VOR dem Run, Budget-Limit WÄHREND des Runs

**Kurzfristig (jetzt):**
- Im Flow `pdf_to_markdown`: Budget-Check vor dem Run
  (Summe `estimated_cost_eur` aller gerouteten PDFs), bei > Limit
  Rückfrage / Dry-Run-Mode
- Im Context-Onboarding-Skill: nach > 5 PDFs oder > 300 Seiten
  kumuliert Rückfrage an den User
- Token-Zähler im Chat-Status-Bar unten (haben wir schon teilweise)

**Mittelfristig:**
- Kosten-Dashboard im UI (pro Projekt, pro Session, pro Tag)
- Budget-Limits in der Projekt-Config (README oder .disco/config.json)
- Alert wenn ein einzelner Turn > 1 € kostet

### Kostenlimit verifizieren — ziehen die existierenden Schutzmechanismen wirklich? (Priorität: hoch — aus UAT 2026-04-20)

Status: Kurz-Notiz aus Live-Test. Wir haben an mehreren Stellen Deckel
eingebaut (MAX_TOOL_ROUNDS, DI-Page-Check im Skill, Flow-Budget), aber
**noch nie überprüft, ob die auch wirklich greifen**, wenn Disco in
einen Kostenfresser hineinrennt.

**Test-Szenarien, die durchlaufen werden sollten:**

1. **Agent-Loop-Deckel:** Disco in eine Schleife schicken
   (z.B. "rufe list_skills 40× hintereinander auf") — bricht er bei
   Round 24 ab? Was sieht der Nutzer?
2. **DI-Page-Limit:** PDF mit > 200 Seiten durch Flow `pdf_to_markdown`
   (Engine `azure-di-hr`) jagen — kommt eine Warnung? Wird der Call
   trotzdem ausgeführt oder blockiert? (aktuell: weder Warnung noch
   Blockade — Policy muss erst definiert werden).
3. **Flow-Budget:** Flow-SDK hat `budget_eur`-Feld (siehe flows/sdk.py).
   Mini-Flow schreiben, der bewusst das Budget überschreiten würde —
   stoppt der Worker wirklich, oder läuft er einfach weiter?
4. **Context-Onboarding > 5 PDFs:** Context-Ordner mit 10 kleinen PDFs
   füllen — fragt Disco wirklich nach, oder schickt er alle auf
   einmal los?

**Ergebnis der Tests in Backlog nachtragen** und offene Lücken
(z.B. Flow-Budget zieht nicht) als separate Bug-Einträge aufmachen.

### DI-Kosten im Chat sichtbar machen (Priorität: hoch — aus UAT 2026-04-20)

Status: Nutzer-Beobachtung — "Bei DI sind keine Kosten sichtbar.
Müssen vielleicht vorher für bestimmte Parameter gesetzt werden."

**Was der Code aktuell tut** (`src/disco/pdf/markdown.py`):

- Der Engine-Dispatcher liefert `estimated_cost_eur` im `meta`-Dict
  (docling-standard = 0, azure-di = 0.00868 €/Seite (8,68 €/1000),
  azure-di-hr = 0.01389 €/Seite (13,89 €/1000) — in Konstanten
  `_AZURE_DI_LAYOUT_EUR_PER_PAGE` / `_AZURE_DI_LAYOUT_HR_EUR_PER_PAGE`).
- Der Flow `pdf_to_markdown` ruft `run.add_cost(eur=cost)` fuer jede
  Datei, damit das UI die akkumulierten Kosten anzeigt.

**Mögliche Gründe, warum der Nutzer nichts sieht:**

1. **UI rendert das Feld nicht prominent.** Flow-Run-Kacheln zeigen
   zwar die kumulierten Kosten, aber pro Dokument fehlt die Zahl.
   → im Run-Items-Block eigene Cost-Spalte, z.B. "≈ 0,12 € (12 Seiten)".
2. **Disco erwähnt Kosten nicht aktiv im Live-Kommentar.** System-Prompt
   hat keine Regel dazu. → Ergänzung: "Nach jedem DI-Flow-Run eine Zeile
   `≈ 0,XX € für N Seiten` in die Assistant-Message."
3. **Modell liefert `n_pages=0`.** Manche PDF-Varianten (gerenderte
   Bilder ohne Page-Metadaten) — dann ist Cost=0. → Fallback auf
   tatsächliche Seitenanzahl des Input-PDFs (PyMuPDF).

**Test + Fix in einem Rutsch:**

1. Bekanntes PDF (z.B. 20 Seiten) durch Flow `pdf_to_markdown` jagen
2. `agent_pdf_markdown` + Flow-Run-Kachel prüfen — kommt `estimated_cost_eur` sauber an?
3. Assistant-Message prüfen — erwähnt Disco die Kosten?
4. UI-Block prüfen — steht die Zahl irgendwo sichtbar?

Danach die Lücken gezielt schließen.

### PDF-Extraktion: 3-Tier-Pipeline (DONE 2026-04-22)

**Status:** Umgesetzt. Pipeline `pdf_routing_decision` → `pdf_to_markdown`
mit Engines `docling-standard` / `azure-di` / `azure-di-hr`. Agent liest
nur noch ueber `pdf_markdown_read` aus `agent_pdf_markdown`. Altes
`pdf_extract_text` (pypdf), `extract_pdf_to_markdown` (DI-Tool) und
VLM-Varianten (granite-mlx / smol-mlx) sind entfernt.

Alter Text gekuerzt — Entscheidungshistorie: Benchmark-Ergebnis zeigte
docling-standard ausreichend fuer Text + Tabellen, DI-HighRes (OCR-
HighResolution) unverzichtbar fuer vector-drawing + Plankoepfe.
VLM-Varianten waren zu langsam fuer Bulk-Runs und liefern keinen
Qualitaetsvorteil gegenueber docling-standard.

---

## Sicherheit / Projekt-Isolation

### Projekt-Lifecycle gehört dem Nutzer, nicht dem Agenten (Priorität: hoch — aus UAT 2026-04-20)

Disco lebt **innerhalb** eines Projekts und darf Projekte weder anlegen
noch löschen. Das ist eine bewusste Rollen-Trennung, nicht ein
Implementierungs-Detail:

- **Mensch:** entscheidet welche Projekte es gibt, wie sie heißen, wann
  sie weg dürfen. Mandantengrenze.
- **Disco:** arbeitet innerhalb der Sandbox des aktiven Projekts. Keine
  Projekt-übergreifende Manipulation.

Aktueller Zustand:
- Projekt-Anlage geht nur per CLI (`disco project init <slug>`). Im FE
  gibt es keinen Button dafür.
- Projekt-Löschung geht gar nicht — man muss den Ordner unter
  `~/Disco/projects/` manuell wegräumen, die DB-Zeile in `projects`
  bleibt liegen.
- Der Agent hat theoretisch Tools (`list_projects`), die ihm die
  Projekt-Existenz zeigen — er kann sie aber (zu Recht) nicht anlegen
  oder löschen. Diese Lücke darf er auch nie bekommen.

Umsetzung:

1. **FE:** Sidebar oben rechts neben dem Projekt-Dropdown zwei Buttons:
   - „+" → Modal „Neues Projekt anlegen" (slug, name, description,
     Checkbox „Sample-Dateien anlegen"). Ruft `POST /api/workspace/projects`.
   - „🗑" → bei ausgewähltem Projekt → Bestätigungsdialog mit Slug
     zum Abtippen (destructive confirm), dann `DELETE /api/workspace/projects/<slug>`.
     Löscht DB-Zeile + Verzeichnisbaum (vorher Backup in
     `~/Disco/.trash/<slug>-<timestamp>/`).

2. **Backend:**
   - `POST /api/workspace/projects` (neu) — ruft dieselbe
     `init_project()`-Routine wie die CLI.
   - `DELETE /api/workspace/projects/<slug>` (neu) — mit
     `move-to-trash`-Semantik, nicht sofort `rm -rf`.

3. **Agent-Tools bleiben so wie sie sind:**
   - `list_projects` darf nur lesen (und nach „Nicht ausgewählte
     Projekte dürfen unsichtbar sein" ggf. auch nicht mehr alle sehen).
   - Es wird KEIN `create_project`- oder `delete_project`-Tool geben.
     Wenn Disco im Chat fragt „soll ich ein neues Projekt anlegen?",
     ist die richtige Antwort: „Bitte leg es selbst über die Sidebar an,
     ich darf das nicht."

### `run_python` härten gegen Prompt-Injection (Priorität: mittel)

Heute ist `run_python` die einzige Tool-Klasse, bei der Disco den
Projekt-Ordner technisch verlassen KÖNNTE — nicht von sich aus,
aber über Prompt-Injection in einem Source-Dokument. Der
Subprocess läuft mit den vollen Rechten des Mac-Users, ohne
OS-Sandbox.

Aktuell bereits dicht:
- Skript-Pfad muss unter Projekt-Root liegen
- Working Directory = Projekt-Root
- API-Keys aus ENV gefiltert (`FOUNDRY_*`, `AZURE_*`, `OPENAI_*`,
  `ANTHROPIC_*`, `MSAL_*`)
- Audit-Log in `agent_script_runs`

Offene Lücken / Roadmap:

1. **User-Bestätigung vor `run_python`** als Default. Skript-Text +
   OK-Klick, bevor Subprocess startet. Opt-out als „Trust-Level"
   pro Projekt (z.B. nachdem Disco in dem Projekt mehrfach
   unauffällig gearbeitet hat).
2. **macOS-`sandbox-exec`-Profil** um den Python-Prozess: Schreiben
   nur auf Projekt-Ordner, Netzwerk nur Azure-/Graph-Hosts.
3. **Deny-Liste für sensible Pfade** (`~/.ssh`, `~/.aws`,
   `~/Library/Keychains`, `~/Library/Application Support/`) als
   zweite Schicht, falls `sandbox-exec` noch nicht steht — schon
   im `_filtered_env`-Umfeld prüfen oder per Wrapper-Script.

Nicht jetzt umsetzen, aber vor erstem produktiven Einsatz mit
echten sensiblen Quellen notwendig.

---

## Flows / Worker-System

### Cached-Input-Rabatt in Kostenberechnung (Priorität: mittel — 2026-04-22)

Aktuell rechnet [compute_cost_eur](../src/disco/flows/sdk.py:135) jeden
Input-Token zum Voll-Tarif ($1.38/1M bei GPT-5.1). Azure gewaehrt aber
einen Cached-Input-Rabatt von **90 %** ($0.138/1M) fuer Tokens, die im
Prompt-Cache gelandet sind (bleibt 5 Min warm).

**Warum das viel ausmacht:**
- Bei Flow-Loops (gleicher System-Prompt + Projekt-Kontext + Skill-Body
  ueber 1000 Items) bleibt ein grosser Prompt-Anteil konstant.
- Hitrate typisch 60–90 %, sprich: wir ueberschaetzen die Kosten aktuell
  um 50–80 %.
- Die echte Azure-Rechnung wird dann immer niedriger sein als unser
  Live-Tracker anzeigt — konservativ, aber irritierend.

**Was zu tun ist:**
1. **Verifizieren:** Foundry Responses API liefert bei GPT-5.1 das Feld
   `usage.input_tokens_details.cached_tokens`. Sobald ein Flow laeuft,
   einmal die JSON-Response loggen und bestaetigen.
2. **Signatur erweitern:** `compute_cost_eur(tokens_in, tokens_out, cached_in=0)`.
   Formel: `billable_in = (tokens_in - cached_in) * rate_in + cached_in * rate_in * 0.10`.
3. **Aufrufer umstellen:** In `FlowRun.add_cost_from_azure_response()`
   (`src/disco/flows/sdk.py`) die Cached-Tokens aus der Response ziehen
   und durchreichen. Auch im Agent-Core (chat-Turns, wo verfuegbar).
4. **Retroaktive Nachberechnung** fuer Runs in `agent_flow_runs`:
   nur moeglich, wenn wir Token-Counts granular in `agent_tool_calls`
   gespeichert haben. Falls ja — kleiner Migrations-Run. Falls nein,
   Historie stehen lassen.

Abhaengigkeit: Prompt-Cache-Hits lohnen sich nur, wenn der System-Prompt
+ Projekt-Kontext vor den variablen Teilen steht und > ca. 1024 Tokens
ist. Prompt-Aufbau mal auditieren, falls die Hitrate zu niedrig ist.

### Parallele Flow-Runs (Priorität: mittel — aus UAT 2026-04-19)

Aktuell faehrt Disco Flows strikt sequentiell: er startet einen Flow,
wartet bis er durch ist, dann den naechsten. Bei einem Projekt mit
mehreren unabhaengigen Pipelines (z.B. DCC-Klassifikation + Metadaten-
Extraktion + Excel-Export) wuerde paralleles Laufen die Wartezeit
spuerbar verkuerzen — v.a. weil die LLM-Flows je Dokument die meiste
Zeit auf Azure warten (I/O-bound).

Anforderung aus UAT-Session 2026-04-19:
> "merke dir noch, dass es die moeglichkeit geben soll mehrere flows
> gleichzeitig laufen zu lassen"

Offene Designpunkte:
- **Scope:** darf ein einzelner Flow parallel zu sich selbst laufen
  (2 Runs desselben Flows)? Oder nur unterschiedliche Flows?
- **Isolation:** jeder Flow hat eigenen Worker-Prozess — SQLite-Writes
  muessen WAL-Mode-tolerant sein (sollte bereits der Fall sein, pruefen).
- **UI:** Flow-Panel muss mehrere laufende Runs gleichzeitig anzeigen.
  Aktuell ist unklar, ob die Flow-Ansicht das rendert.
- **Budget-Tracking:** globales Kosten-Budget vs. per-Run?
- **Abhaengigkeiten:** darf ich Flow-B starten bevor Flow-A done ist,
  wenn Flow-B auf Daten von Flow-A liest? Vermutlich ja (der User weiss
  was er tut), aber Warnhinweis im Chat waere nett.

Test-Szenario: in `uat-2026-04-19` DCC-Klassifikation und Metadaten-
Extraktion gleichzeitig anwerfen — beide lesen aus `agent_md_extracts`,
schreiben in unterschiedliche Tabellen, keine Kollision.

### Standard-Flows fuer jedes Projekt (Priorität: mittel — aus UAT 2026-04-20)

Es sollte eine Menge von Standard-Flows geben, die in **jedem neu angelegten
Projekt automatisch vorhanden** sind (via Projekt-Template analog zu den
Template-Migrationen). Damit startet kein Projekt auf der gruenen Wiese —
die Basics liegen bereit, der Nutzer triggert sie nur.

Muss vor Umsetzung einmal gemeinsam diskutiert werden:

- **Welche Flows sind „Standard"?** Kandidaten:
  - `sources_scan_and_register` — Sources scannen, hashen, in `agent_sources`
    registrieren (heute Tool, koennte aber als Flow laufen fuer Audit-Trail)
  - `pdf_routing_decision` + `pdf_to_markdown` — bereits als Library-Flows
    umgesetzt (liegen unter `src/disco/flows/library/`), koennten aber per
    Default in jedem neu angelegten Projekt sichtbar sein
  - `dcc_classify_gpt5` — DCC-Klassifikation ueber Markdown-Extrakte
  - `duplicate_detect` — Duplikat-Analyse per Hash + Name + Inhalt
  - `context_manifest_refresh` — Kontext-Ordner neu indizieren
- **Template vs. generiertes Code-Skelett?** Tradeoff:
  - *Template-Kopie:* Runner + README als Datei-Template, wird beim
    `disco project init` ins Projekt kopiert. Flexibler bei Anpassung,
    aber Drift zwischen Projekten moeglich.
  - *Shared Runner:* ein globaler Runner in `src/bew/flows/standard/`,
    Projekt hat nur die README als Referenz. Weniger Drift, aber weniger
    anpassbar pro Projekt.
- **Aktualisierung:** wie bekommen bestehende Projekte einen neuen
  Standard-Flow (oder ein Update)? `disco flow sync` als neues Kommando?
- **Konfiguration pro Projekt:** Standard-Flows haben typische
  Default-Configs (Budget, Engine-Wahl), die pro Projekt ueberschreibbar
  sein muessen.
- **Discoverability:** neues UI-Element „Standard-Flows" im Flow-Panel,
  getrennt von projekt-spezifischen Flows.

Ziel: ein neues Projekt ist nach `disco project init` direkt
„produktionsbereit" — Sources registrieren, Markdown extrahieren,
DCC klassifizieren geht One-Click, ohne dass Disco fuer jedes neue
Projekt denselben Flow nochmal baut.

Ursprung: UAT-Session 2026-04-20, als waehrend eines laufenden
Extraction-Runs parallel eine zweite Engine-Variante als eigener Flow
nachgezogen wurde — dabei wurde klar, dass solche Arbeit fuer jedes
Projekt wiederholt wird, obwohl die Flows strukturell identisch sind.
Teil davon ist inzwischen ueber die Flow-Library (`src/disco/flows/library/`)
geloest, der Gesamt-Bootstrap steht aber noch aus.

### Overnight-Betrieb + Resume nach Sleep/Restart (Priorität: hoch — aus UAT 2026-04-20)

Bulk-Flows (`pdf_to_markdown`, DCC-Klassifikation, etc.) laufen
teils stundenlang. Der Nutzer moechte sie **ueber Nacht** laufen
lassen, auch wenn der Rechner gesperrt ist — und einen laufenden
Flow **nach Neustart** (Disco-Restart, Mac-Restart, Aufwachen aus
dem Sleep) wieder aufnehmen koennen, statt ihn komplett neu anzustossen.

Zwei Teilprobleme:

**1. Overnight (Rechner an, gesperrt, aber nicht im Sleep):**
- Mac-Default: Displayschlaf nach ~10 min, Systemschlaf je nach
  Energieprofil. Bei Netzteil typisch „Nie", bei Batterie schnell.
- Bei Mac im Systemschlaf stoppt der Worker-Subprozess — scheduler
  wird suspendiert, keine Azure-Calls, keine Fortschritte.
- Loesung: **`caffeinate -i` automatisch starten**, solange ein
  Flow `running` ist. Disco spawnt `caffeinate` als Child, killt
  ihn bei Flow-Ende. Damit bleibt der Mac wach, auch wenn der
  User das Display zumacht.
- Alternative: User muss manuell `caffeinate` oder „Ruhezustand
  verhindern" in den Energie-Einstellungen aktivieren. Unschoen.

**2. Resume nach Restart / Aufwachen:**
- Wenn der Worker-Subprozess weg ist (Mac neu gestartet, Disco
  gekillt), zeigt `agent_flow_runs.status` weiterhin `running`,
  obwohl nichts laeuft → „stale run".
- Nach Disco-Start muessten solche Runs:
  a) erkannt werden (`status=running` aber `worker_pid` existiert
     nicht mehr als Prozess)
  b) auf `paused` / `interrupted` gesetzt werden
  c) dem User im Run-Streifen mit Option „Resume" angezeigt werden
- Resume muss **idempotent** sein: Items mit `status=done` werden
  nicht neu verarbeitet, `status=pending` oder `status=failed` (je
  nach Policy) werden weiter gemacht. Das ist die Kern-Idempotenz-
  Zusage der SDK, muss aber pro Flow geprueft werden.
- Implementierung: neuer CLI-Befehl `disco flow resume <run_id>`
  oder Button im UI, der einen neuen Worker-Prozess auf bestehende
  `run_id` aufsetzt.

**Offene Designpunkte:**
- Soll Disco nach Start automatisch alle stale runs als „resumed"
  wieder aufnehmen? Oder dem User nur anbieten?
- Was passiert mit `next_heartbeat_at`, wenn ein Run 10h „gestanden"
  hat? Der Watcher wuerde sofort triggern — evtl. Flood. Bei Resume
  zuruecksetzen auf +1 min.
- Wie gehen wir mit Items um, die beim Crash mitten in `processing`
  waren? Status auf `pending` zuruecksetzen, neu einplanen.
- `caffeinate` klappt unter macOS — unter Linux (falls mal relevant)
  andere Mechanismen.

Ursprung: UAT-Session 2026-04-20, Nutzer-Frage nach Run #15:
> "Ich würde gerne klären ob die flows bereit sind über nacht
> weiter zu laufen, auch wenn der computer gesperrt ist. Dann
> wäre es super, wenn ein flow seine arbeit wieder aufnehmen kann
> nachdem disco neu gestartet wird bzw während des flows der
> computer ausgeschaltet (oder sleep) wurde"

### Getrennte Modell-Deployments fuer Agent vs. Flow (Priorität: hoch — aus UAT 2026-04-20)

**Beobachtung:** Solange der Agent-Chat (`gpt-5.1_prod`) und der
Flow-Worker (ebenfalls `gpt-5.1_prod`) auf **demselben Azure-
Deployment** laufen, teilen sie sich **dieselbe TPM/RPM-Quota**.
Waehrend Flow #4 mit ~27.600 TPM In lief, konnte der Agent parallel
keinen Chat-Turn mehr abschliessen — vermutlich weil Foundry
intern auf 429 lief und die Response verunglueckte (siehe Bug-
Eintrag "Chat haengt nach Foundry response.failed" oben).

**Wichtig zur Einordnung:** Modell-Deployment und Conversation-
History sind komplett unabhaengig — der Chat hat weiterhin seine
eigene `foundry_thread_id` und sein eigenes Context-Window.
**Das einzige**, was Agent und Flow sich teilen, wenn sie dasselbe
Deployment nutzen, ist die **Azure-seitige Rate-Limit-Quota** (und
die Abrechnung).

**Ziel:** Zweites Modell-Deployment in Foundry anlegen, exklusiv
fuer Flows. Damit der Agent-Chat reaktionsfaehig bleibt, waehrend
ein Flow an der Quota frisst.

**Vorschlag (Sweden Central):**

| Zweck | Deployment-Name | Verwendet von |
|---|---|---|
| Dev-Agent + Dev-Flows | `gpt-5.1` (bereits da) | Dev-Umgebung |
| Prod-Agent (interaktiv) | `gpt-5.1_prod` (bereits da) | `AgentService` |
| Prod-Flows (bulk) | `gpt-5.1_prod_flow` (neu) | Flow-Runner |

**Umsetzung:**
- Neues Deployment `gpt-5.1_prod_flow` im Foundry-Portal anlegen
  (Modell gpt-5.1, eigene TPM-Quota bekommen). Deployments kosten
  nichts extra — nur die tatsaechlichen Tokens.
- `config.py` um `foundry_flow_model_deployment: str | None` erweitern.
  Fallback auf `foundry_model_deployment`, wenn nicht gesetzt.
- Flow-SDK (`src/disco/flows/sdk.py`) liest neu dieses Feld.
- `.env.example` dokumentieren.
- Runner-Migration: bestehende `runner.py`-Dateien in Flow-Ordnern
  ziehen den Deployment-Namen aus `FlowRun` — entweder Property oder
  Env-Variable, die das SDK ihnen durchreicht.

**Parallel-Nebeneffekt:** Wenn mehrere Flows gleichzeitig laufen
(siehe "Parallele Flow-Runs" oben), teilen die sich weiterhin das
Flow-Deployment — das ist ok, da Bulk-Jobs inhaerent parallelisierbar
sind und die Quota gezielt auf Durchsatz auslegbar ist.

**Dev bleibt einfach:** In Dev reicht ein einziges Deployment,
weil Raphael dort selten Agent+Flow gleichzeitig fahren wird.

---

## Docling / MLX

### Hybride Markdown-Pipeline (DONE 2026-04-22)

**Status:** Umgesetzt als `pdf_routing_decision` (PyMuPDF-Heuristik pro
Seite → Engine pro Dokument, Strategie A: eine Engine je Datei) und
`pdf_to_markdown` (Engine-Dispatcher `src/disco/pdf/markdown.py`).
VLM-Varianten entfernt — docling-standard deckt Text + Tabellen,
azure-di A4-Scans, azure-di-hr Vector-Drawings / Plankoepfe ab.

Ursprung: UAT-Session 2026-04-20 (Granite too slow) → Beschluss
2026-04-22: VLM komplett raus, festes 3-Tier-Routing.

---

## Architektur

### Dashboards + Reports — Disco pflegt sie selbst (Priorität: mittel) — 2026-04-22

**Wunsch des Nutzers:** Disco soll Dashboards und Reports **selbständig
erstellen, konfigurieren und überarbeiten können**. Projekt-DB liefert die
Daten, Frontend zeigt Visualisierungen, alles versionierbar im Projektordner.

**Drei geprüfte Wege mit Trade-off:**

1. **Evidence.dev (Markdown + SQL → HTML):** Disco schreibt
   `dashboards/foo.md` mit SQL-Blöcken, Evidence rendert statische Seiten.
   MIT-Lizenz, SQLite nativ. Nachteil: Node-Stack + Build-Schritt kommen
   ins Projekt.
2. **Vega-Lite JSON-Specs + eigener Renderer (empfohlen):** Disco schreibt
   `dashboards/foo.json`, Frontend rendert im bestehenden Viewer-Panel mit
   Vega-Lite (~40 KB). Kein Fremd-Stack, max. Kontrolle, Dashboards sind
   einfache Files im Projekt. Nachteil: Dashboard-Verwaltung (Liste, Edit,
   Parameter) bauen wir selbst.
3. **Metabase lokal (Docker):** Industriestandard, REST-API zum Steuern.
   Nachteil: Docker-Dependency, Dashboards leben ausserhalb des Projekt-
   ordners (nicht git-/SharePoint-syncbar).

**Empfehlung: Variante 2** — passt zur lokalen Architektur und zur
chat-getriebenen Arbeitsweise. Reports (PDF/Excel) lassen sich aus denselben
Specs generieren (Renderer → Screenshot / Headless-Export), wobei wir fuer
Excel schon `build_xlsx_from_tables` haben.

**Skizze:**
- Neuer Projekt-Ordner `dashboards/` mit `.json`-Dateien (Vega-Lite oder
  erweiterte Disco-Spec mit SQL-Query + Layout-Metadaten).
- Neues Agent-Tool `dashboard_create/update/delete` plus `dashboard_render`
  (SQL-Query-Validation + Ergebnis → Vega-Lite-Bindings).
- Viewer-Panel erkennt `.json` im Dashboard-Ordner und rendert.
- Reports = Dashboard-Bundle + Markdown-Rahmen; Export-Pipeline baut
  PDF/Excel.

**Noch offen:** Dashboard-Parameter (Zeitfenster, Gewerke-Filter) — als
Form im Viewer, oder nur als Chat-Instruktion an Disco?

Ursprung: UAT-Session 2026-04-22, Feature-Wunsch des Nutzers.

---

### Tabellen-Katalog pro Projekt-DB (Priorität: mittel) — 2026-04-22

**Beobachtung:** In einem aktiven Projekt wachsen die Tabellen schnell
(Kern-Migrations-Tabellen + agent-erstellte `agent_*`/`work_*`). Man sieht
in der UI-Sidebar nur Name + Row-Count. Wer sie angelegt hat, wofür, ob sie
noch gebraucht wird — nirgends dokumentiert. Migrations-Files dokumentieren
nur die Template-Tabellen; alles, was Disco später selbst anlegt, bleibt
unbeschrieben.

**Vorschlag:**
- Neue Tabelle `agent_table_catalog(name PK, namespace, purpose TEXT,
  created_by_message_id, created_at, last_used_at, status: active|deprecated)`
  als weitere Projekt-DB-Template-Migration.
- Pflege-Pfade:
  - Automatisch: `sqlite_write` erkennt `CREATE TABLE` / `DROP TABLE` und
    aktualisiert den Katalog (Eintrag anlegen / status=deprecated).
  - Halbautomatisch: System-Prompt-Regel — „nach jedem `CREATE TABLE` muss
    `table_catalog_set(name, purpose)` aufgerufen werden".
- Template-Tabellen aus den Migrations-Files werden beim Projekt-Init
  direkt mit Purpose befüllt (aus Header-Kommentaren extrahiert).
- UI:
  - Tooltip auf Tabellennamen in der Sidebar zeigt `purpose`.
  - Filter „undokumentierte Tabellen" und „> N Tage ungenutzt" als
    Aufräum-Trigger.
- Abräum-Policy: `work_*` ohne Zugriff seit X Tagen → Disco schlägt Drop vor.

**Warum wichtig:** passt zur Observability-Linie (agent_tool_calls, Feedback).
Ohne Katalog wachsen Projekte unüberschaubar; mit Katalog wird das Projekt
selbsterklärend und Aufräumen planbar.

**Offene Fragen vor Umsetzung:**
- Wer trägt den Purpose ein — Disco beim CREATE (Pflicht-Parameter) oder
  in einem separaten Tool-Call? Ersteres ist strikter, letzteres flexibler.
- Sollen auch Column-Beschreibungen rein oder reicht Tabelle-Level fürs Erste?

---

### Architecture Review mit Claude (Priorität: mittel)

Sobald der MVP-Scope steht (Flows produktiv, 2+ reale Pipelines gelaufen),
ein gemeinsames Architecture-Review mit Claude durchfuehren. Mögliche
Themen:

- Workspace-Trennung (Code vs. Daten) — hält das auch bei Multi-User?
- Foundry-Portal-Agent vs. eigene Orchestrierung — Lock-in-Risiko?
- Projekt-DB (SQLite) vs. System-DB — skaliert das bei 20+ Projekten
  à 100k Dokumenten?
- Flow-SDK vs. Worker-Pool vs. Cloud-Scheduling — wann was?
- Skills-Katalog — wird er übersichtlich bleiben oder irgendwann
  unhaltbar gross?
- Offline-Policy — ist die Defence-in-Depth (Settings + Subprocess-Env)
  ausreichend, oder braucht es Egress-Firewall?
- Hybrid-Search (Phase 2c) — Embeddings wo? Index wo? Rebuild-Strategie?

Output: schriftliche Bilanz mit Ampelbewertung pro Bereich + konkreten
Nachbesserungs-Tickets im Backlog.

Ursprung: UAT-Session 2026-04-20, Wunsch des Nutzers.

---

## Release / DevOps

### Dev/Prod — Folgefragen (Priorität: mittel)

Minimal Viable Split laeuft seit 2026-04-20: dev-Branch + zwei
Checkouts, Workspaces `~/Disco/` + `~/Disco-dev/`, Ports 8765/8766,
eigener Foundry-Agent pro Env (`disco-prod-agent` / `disco-dev-agent`).
Offen sind:

- **Release-Cut-Kommando:** `disco agent release` — Dev-Agent-Version
  nach Prod pushen. Heute: manueller Git-Merge + `disco agent setup`
  in Prod-Checkout.
- **Migrations-Check beim Release:** automatisch warnen, wenn Dev
  Migrationen hat, die in der Prod-DB noch nicht angewandt sind.
- **Skill / system\_prompt-Versionierung:** heute Git-versioniert wie
  Code. Bedarf evaluieren, ob Skills zwischen Env ohne Branch-Merge
  kopierbar sein sollen.
- **Daten-Migration Prod ← Dev:** UAT-gereiftes Projekt von Dev nach
  Prod uebernehmen — heute manuell per `rsync`, ggf. Disco-Kommando.
- **CI/CD:** Tests auf dev-PR, Deploy auf Merge nach main — lohnt erst
  bei mehreren Entwicklern.

---

## Technische Schuld + Setup-Probleme (aus Cleanup-Review 2026-04-22)

Gesammelt direkt nach der PDF-Pipeline-Umstellung (Routing-Flow +
pdf_to_markdown + agent_pdf_markdown). Geordnet nach Risiko, nicht
nach Aufwand.

### Setup-Fallstrick: Offline-Default vs. frischer HF-Cache (Priorität: hoch)

Default in `.env.example` + `src/disco/config.py` ist
`HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1 / HF_DATASETS_OFFLINE=1`.
Die `docling-standard`-Engine braucht aber beim ersten Gebrauch die
Modelle (DocLayNet + TableFormer + EasyOCR) lokal im
`~/.cache/huggingface/` — auf einer frischen Maschine laeuft der erste
`pdf_to_markdown`-Run mit Offline-Flags ins Leere.

Heute: Erst-Priming haendisch dokumentiert (config.py-Docstring,
.env.example) — User muss einmalig `HF_HUB_OFFLINE=0 ...` fahren.

Offen: sauberes `disco models prime`-Kommando (oder Check beim ersten
Flow-Start: "Cache fehlt, soll ich die Modelle jetzt ziehen?"). Ohne
das wird jeder neue Entwickler einmal stolpern.

### Keine automatisierten Tests fuer die PDF-Pipeline (Priorität: hoch)

`tests/` existiert nur als leeres Gerüst (`tests/uat/`), keine
pytest-Suite, kein CI. Die neue Pipeline (`src/disco/pdf/markdown.py`,
`pdf_markdown_read`, beide Library-Flows) ist nur via 30-Dok-Manuallauf
validiert — Regressions-Schutz gleich null.

Mindest-Ausstattung, die fuer Ruhe sorgen wuerde:
- Unit-Tests fuer Engine-Dispatcher (Mock-DI + 1-Seiten-PDF-Fixture fuer
  docling-standard).
- Integrations-Test fuer `pdf_markdown_read` mit einer
  vorgefuellten In-Memory-SQLite (agent_pdf_markdown).
- Ein Smoke-Test fuer den Routing-Flow (3-PDF-Fixture, eine pro Engine-Bucket).

Ohne Tests faellt jeder Umbau an der Pipeline erst im UAT auf. Das
sollte vor weiteren groesseren Flow-Bauten adressiert werden.

### Flow-Scaffold (`flow_create`) hinterlaesst TODOs im Runner-Template (Priorität: niedrig)

`src/disco/agent/functions/flows.py:114,122` hat zwei `TODO`-Marker im
Runner-Skelett. Ist Absicht — Disco soll die Stellen mit dem Nutzer
zusammen fuellen. Aber: keine Fixme-Pruefung verhindert, dass ein
halbfertiger Flow im Library-Verzeichnis landet.

Vorschlag: bei `flow_create` den Template-Header explizit als
"// SCAFFOLD: bitte process_item und Input-Query anpassen, dann
Kommentare entfernen" markieren, damit ein halbfertiger Runner beim
Code-Review auffaellt.

### Portal-Agent-Rollout bei Tool-Aenderungen (Priorität: mittel)

Wenn sich die Custom-Function-Signaturen aendern (wie jetzt bei der
Pipeline-Umstellung: `pdf_extract_text` raus, `pdf_markdown_read`
rein), muss `disco agent setup` fuer Prod + Dev laufen, sonst kennt
der Portal-Agent die Tools nicht. Heute manuell.

Vorschlag: Beim `disco agent setup` automatisch gegen
`get_tool_schemas()` diffen und bei Aenderungen eine Versionsnummer
hochzaehlen, damit man im Portal-Log sieht, welche Tool-Version
gerade registriert ist.

### `duration_ms`-Schema inkonsistent zwischen Engine-Dispatcher und DB (Priorität: niedrig)

`src/disco/pdf/markdown.py` liefert `duration_ms` als `float` (gerundet
auf 1 Nachkommastelle). `agent_pdf_markdown.duration_ms` ist `REAL`
— kompatibel, aber der Runner persistiert den Wert ohne weitere
Konversion, was in der UI zu `"7088.0"`-Anzeigen fuehren kann.
Kosmetisch, nicht funktional.

---

*Letzte Aktualisierung: 2026-04-22*

---

## Pipeline-Vollstaendigkeits-Sicht (Prioritaet: hoch)

Heute zerfaellt der Pipeline-Status auf vier Tabellen:

- `ds.agent_sources` — registriert
- `work_extraction_routing` — Engine entschieden
- `ds.agent_doc_markdown` — extrahiert
- `ds.agent_search_docs` — im FTS-Index

Der User hat keinen einfachen Weg zu sehen "ist alles durchgelaufen?".
Bei vielen Files (>100) wird das schnell unuebersichtlich.

**Drei Ausbaustufen, kann inkrementell:**

1. **Status-View pro Datei (V1, niedriger Aufwand)** — eine SQL-View
   ueber die vier Tabellen, zeigt pro Datei vier Boolean-Spalten:
   ```
   rel_path | registered | routed | extracted | indexed | last_step_at
   ```
   Disco kann das per `sqlite_query` jederzeit zeigen, UI-seitig als
   Ampel-Spalte in der Sidebar denkbar. Genau bei kleinen-bis-mittleren
   Projekten ausreichend.

2. **Lifecycle-Tabelle (V2, wenn V1 zu viele LEFT JOINs hat)** — eine
   zentrale `agent_pipeline_status` mit einer Zeile pro Datei, Status
   explizit gespeichert. Plus: bessere Filter wie "alle deren
   Extraction aelter als die letzte Source-Hash-Aenderung". Kostet
   Migration + Sync-Logik in jedem Pipeline-Schritt.

3. **Hintergrund-Sync (V3, optional)** — `sources_register` triggert
   automatisch `routing` + `extraction` + `indexing` als Flow-Chain.
   "Self-healing" Pipeline. Caveat: weniger Kontrolle, hoehere Cloud-
   Kosten ohne explizites Go vom User.

**Empfehlung:** mit (1) starten. Bei Bedarf (2) drauflegen, (3) als
opt-in fuer Standard-Workflows.

User-Quote (2026-04-25): *"Wir werden uns darüber Gedanken machen
müssen, wie wir wissen ob alle dateien registriert, geroutet,
extrahiert und indexiert sind. Ich weiß nicht ob das demnächst
einfach eine Hintergrundaktivität werden sollte, oder ob es ein
Ampel-System gibt oder sowas."*

---

## Flow-UI im Chat-Fenster (DONE 2026-04-25)

*Erledigt: Commits 829fd65 + 6200002 + 0e04dc9 + 77f71ea. Alle vier Punkte umgesetzt — auffaelligeres Strip, finished-Runs bleiben mit Status-Badge + X-Button, Klick auf ganze Zeile, Runs im Flow-Detail nach oben. Plus Bonus: schnelle Runs (<3s) per recent_finished-API eingefangen, done-with-failures als Pseudo-Status (orange).*

Beobachtungen aus dem Pipeline-Fulltest 2026-04-25 — kleine UX-
Verbesserungen am Run-Strip oben im Chat:

1. **Auffaelligkeit erhoehen** — die Run-Indikatoren oben im Chat-
   Fenster sind heute leise. Wenn ein Flow laeuft, soll man das mit
   einem Blick sehen (Hintergrund, Animation, Farbe).

2. **Nach Ende sichtbar bleiben** — heute verschwindet ein Run aus
   dem Strip, sobald er fertig ist. Soll: mit finalem Status (done /
   failed / cancelled) **oben stehen bleiben, bis der User es weg-
   klickt** (X-Button). So merkt man auch ueber Lange Pausen, dass
   ein Flow durchgelaufen ist.

3. **Klick auf Run-Indikator** soll:
   - falls man nicht im richtigen Projekt ist: ins Projekt des
     Flows springen, dann
   - den Run selbst im Viewer oeffnen (gleiche View wie wenn man
     im Flow → Liste-aller-Runs auf den Run klickt).

4. **Run-Liste im Viewer (Flow-Detailansicht)** — die Runs eines
   Flows sollen **oben** stehen (neueste zuerst), nicht unten am Ende
   der Seite. Aktuell muss man zum Flow-Detailview scrollen.

Quelle: User-Feedback waehrend Pipeline-Fulltest 2026-04-25.

---

## Office-Formate in die Extraction-Pipeline (Prioritaet: hoch)

Vergessen: **PowerPoint (.pptx)** und **Word (.docx)** muessen auch
durch die Extraction-Pipeline. Heute wuerden sie:
- in `agent_sources` registriert (extension wird gespeichert)
- aber im `extraction_routing_decision`-Flow als `file_kind='other'` →
  Routing-Engine `'skip'` → keine Extraktion, kein Suchindex

Heisst: Word- und PowerPoint-Dateien sind heute fuer Disco unsichtbar.

### Was zu tun ist

**Engines:**
- `docx-python-docx` — mit [python-docx](https://github.com/python-openxml/python-docx) (MIT). Ueberschriften, Absaetze, Tabellen, Listen → Markdown.
- `pptx-python-pptx` — mit [python-pptx](https://github.com/scanny/python-pptx) (MIT). Pro Slide ein Markdown-Block: Titel + Body-Text + Notes + Tabellen.
- Ggf. ein DOCX-Konverter ueber **mammoth** (MIT) als 2. Engine fuer komplexeres Markup.

**Schema:**
- Erweiterung `disco/docs/__init__.py`:
  - `_KIND_BY_EXT` um `'docx': 'office'`, `'pptx': 'office'`
  - oder `'docx': 'docx'`, `'pptx': 'pptx'` als eigene Kinds
  - `ENGINES_BY_KIND` entsprechend erweitern
- Routing in `disco/docs/routing.py`: `_decide_office()` (oder pro Format)
- Neue Module `disco/docs/docx.py`, `disco/docs/pptx.py` analog zu `excel.py` / `dwg.py`
- INDEXABLE_EXTENSIONS in `search.py` um `.docx`, `.pptx` erweitern, in `_FROM_DOC_MARKDOWN_EXTS` (lesen aus agent_doc_markdown)

**Unit-Modell:**
- DOCX: pro Section (Heading-1) ein unit, oder ganzes Dokument als unit_label='document'
- PPTX: pro Slide ein unit (label = Slide-Titel oder "slide-N")

**Cost:** lokal, 0 EUR. Bei DOCX mit eingebetteten Bildern spaeter ggf. Bilder per VLM-Engine extrahieren (Phase 2).

**Auswirkung auf bestehende Projekte:** keine breaking changes. Bestand-Files mit `file_kind='other'` werden bei naechstem Routing-Run als `docx` / `pptx` neu klassifiziert.

User-Quote (2026-04-25): *"Power Point, und Word Dateien haben wir total vergessen :D Die muessen auch noch in die Pipeline."*

---

## Extraction nur auf kanonische Dateien (Prioritaet: hoch)

Heute extrahiert die Pipeline **alle** aktiven `agent_sources`-Eintraege —
auch Duplikate (gleicher Hash, anderer Pfad), abgeloeste Vorgaenger
(`replaces`/`replaced-by`-Relation) und Format-Konversionen
(`format-conversion-of`). Das verschwendet Cost und macht den Suchindex
mehrdeutig.

**Soll-Zustand:** Extraction laeuft nur auf den **kanonischen** Repraesentanten.
Disco weiss das und der Routing-Flow filtert entsprechend.

### Was "kanonisch" konkret heisst

Eine Datei ist kanonisch, wenn fuer ihren Inhalt kein anderer Eintrag
in `agent_source_relations` mit groesserer "Praeferenz" existiert:

- **NICHT** `duplicate-of` einer anderen aktiven Datei (dann ist die andere kanonisch)
- **NICHT** `replaces`-Source eines anderen Eintrags (dann ist die neuere kanonisch)
- **NICHT** `format-conversion-of` (z.B. PDF aus DWG konvertiert — wenn die Original-DWG da ist, ist das DWG kanonisch)
- Status `active`

### Was zu tun ist

1. **Routing-Filter**: Im `extraction_routing_decision`-Item-Loader Sub-Query
   gegen `agent_source_relations` einbauen, nicht-kanonische Files skippen.
2. **System-Prompt**: Disco-Regel dass er bei Pipeline-Vorschlaegen auf die
   Kanonik-Logik hinweist ("ich extrahiere nur die kanonischen N Dateien
   von M registrierten").
3. **Heuristik fuer "neueste Revision"**: bei `replaces`-Ketten den Endknoten
   nehmen. Bei `format-conversion-of` Mehrfachkanten klar definieren
   (z.B. DWG-Original > PDF-Plot > JPEG-Screenshot).
4. **Pipeline-Vollstaendigkeits-Sicht** (V1, anderer Backlog-Eintrag) muss
   das beruecksichtigen: "registriert" vs "kanonisch" vs "extrahiert".

### Auswirkung

- Spart Cost (Schaetzung: 20-40% bei Projekten mit Revisions-Historie)
- Sauberer Suchindex (keine doppelten Treffer auf identischem Inhalt)
- Reasoning-Sicherheit (keine Verwirrung welche Version "die richtige" ist)

### Begriffsklaerung (2026-04-26)

Drei Counts pro Projekt — alle nuetzlich, leicht zu verwechseln:

| Begriff | Definition | SQL |
|---|---|---|
| **registered** | aktive Eintraege in `agent_sources` | `COUNT(*) WHERE status='active'` |
| **unique** / **distinct** | Anzahl eindeutiger sha256-Hashes | `COUNT(DISTINCT sha256)` |
| **kanonisch** | bevorzugter Repraesentant nach Konsolidierung von Duplikaten + Versionen + Format-Konversionen | gefiltert ueber `agent_source_relations` |

**Heute (Stand 2026-04-26):** `sources_detect_duplicates` schreibt nur
`kind='duplicate-of'` (sha256-Gruppen). `replaces` und
`format-conversion-of` sind im Schema vorgesehen, werden aber von keinem
Tool gefuellt. Damit ist heute **kanonisch == unique-by-hash**, eine
echte Konsolidierung ueber Versionen passiert nicht.

Auswirkung auf den Filter: heute reicht ein Filter auf `duplicate-of`
um den 80%-Effekt zu erreichen (siehe rea-denox: 5963 → 1883 Files,
68% Reduktion). Sobald `replaces`/`format-conversion-of` gefuellt
werden, wird der Filter strenger und reduziert nochmal.

---

User-Quote (2026-04-25): *"Extraction machen wir nur auf kanonische
dateien. Das sollte disco wissen."*

---

## Public-Workspace fuer Cross-Projekt-Reuse (Prioritaet: mittel)

Heute ist jedes Projekt streng sandboxed (contextvars-basierte
Mandantentrennung in `disco.agent.context`). Disco kann nicht
zwischen Projekten zugreifen. Das ist sicher, verhindert aber
Cross-Projekt-Reuse.

**Idee:** ein **Public-Workspace** auf gleicher Ebene wie `projects/`,
sichtbar fuer alle Projekte, schreib-zugreifbar via dedizierte Tools.

```
~/Disco/                       (analog ~/Disco-dev/)
├── system.db
├── _public/                   ← NEU
│   ├── flows/                 — geteilte Flow-Definitionen
│   ├── reports/               — projekt-uebergreifende Reports (z.B. Cross-Projekt-Stats)
│   ├── exports/               — fertige Lieferungen, Templates
│   └── data.db                — eigene SQLite fuer geteilte Lookup-Tabellen
└── projects/
    └── <slug>/
```

### Use-Cases

- **Geteilte Flow-Library** — DCC-Klassifikations-Flow einmal entwickeln, in allen Projekten nutzen. Heute muesste man pro Projekt forken.
- **Cross-Projekt-Reports** — Dashboard ueber alle Projekte (PDF-Anzahl, Routing-Verteilung, Cost). Heute schwer.
- **Standard-Templates** — HTML-Report-Skelette, Excel-Vorlagen, DCC-Referenzlisten.
- **Norm-Bibliothek** — eine `VGB_S_831.pdf` reicht im Public, kein Duplikat in 10 Projekten.

### Architektur-Optionen

**Option A — Spezial-Pfad im Filesystem-Sandbox:**
- `fs_*`-Tools erkennen `_public/...` und erlauben Cross-Projekt-Zugriff
- Pro: minimal-invasiv, vorhandene Tools bleiben
- Con: leicht versehentlich Cross-Read; keine klare Eigentuemer-Markierung

**Option B — Eigene Public-Tools (mein Favorit):**
- Neue Tools `fs_public_list/read/write`, `sqlite_public_query/write`
- Klare Trennung im Tool-Inventar — Disco entscheidet bewusst "ich lege das ins Public"
- System-Prompt-Regel: vor Public-Write Bestaetigung beim User holen
- Con: Tool-Anzahl waechst (heute 49, dann ~55)

**Option C — Public als Pseudo-Projekt mit Sondermodus:**
- `~/Disco/projects/_public/` als reservierter Slug
- Switch-Tool `use_public_workspace()`: hebt die Sandbox temporaer auf
- Pro: konsistent zur Projekt-Logik
- Con: User-Confusion; Sandbox-Aufhebung kontraintuitiv

### Sicherheits-Design (egal welche Option)

- **Schreibzugriff erfordert explizite Geste** — nicht aus Versehen ins Public schreiben
- **Audit-Trail** — agent_script_runs/agent_tool_calls protokollieren Public-Operationen besonders
- **Egress-Policy unveraendert** — Public ist immer noch lokal, kein neuer Cloud-Endpoint
- **Symlink-Schutz** — Public-Dateien duerfen nicht aus dem Public-Tree rauszeigen

### Migration / Stufung

1. **Stufe 1**: read-only Public-Workspace, nur Disco kann lesen, der User kuratiert per File-Manager. Reicht fuer geteilte Templates + Norm-Bibliothek.
2. **Stufe 2**: `fs_public_write` + Schutz-Konvention im System-Prompt. Disco kann selbst Reports/Exports ablegen.
3. **Stufe 3**: shared `_public/data.db` mit Lookup-Tabellen, in Projekten via `ATTACH DATABASE` lesbar (analog `ds`).

User-Quote (2026-04-25): *"einen public folder, in dem disco flows,
Reports und exports ablegen kann. Der Ordner kann von allen Projekte
gesehen und bearbeitet werden"*

---

## Run-Strip Bugs (Prioritaet: niedrig)

Beobachtet 2026-04-25 nach den Run-Strip-Updates (Commits 829fd65,
6200002, 0e04dc9, 77f71ea):

### Bug 1: gleicher Run wird doppelt angezeigt

Beobachtet: `#3 extraction_routing_decision` erscheint zweimal im
Strip (einmal mit slug-Badge `bew-rsd-lager-halle`, einmal ohne).

Vermutete Ursache: derselbe Run-Eintrag liegt sowohl in
`state._runStripFinished` (lokal, localStorage-persisted) als auch in
`data.recent_finished` (Backend-Antwort). `_runStripAddFinished` hat
einen Dedup-Lookup ueber `${project_slug}:${id}`, aber wenn das
project_slug-Feld in einer der zwei Quellen fehlt oder anders
formatiert ist (z.B. leer vs. richtiger slug), wird der Lookup nicht
matchen und der Eintrag landet zweimal.

**Fix-Ansatz**: 
- Dedup robuster machen: nicht nur Key vergleichen, sondern bei leerem
  slug auf `flow_name + id` fallback
- Im Backend sicherstellen, dass `project_slug` in `recent_finished`
  immer gefuellt ist (heute haben wir das via Slug-Resolution, sollte
  klappen — Logging im Backend bei NULL)

### Bug 2: Counter springt nicht auf 100% (1720/1721 bleibt)

Beobachtet: Run mit `done · 1 failed`, total=1721 zeigt Counter
`1720/1721 (100%)` statt `1721/1721 (100%)`.

Ursache: ich hatte den **pct** auf `processed/total` umgestellt
(Commit 77f71ea), aber das **Template** rendert weiter `${done}/${total}`
— die linke Zahl ist also weiterhin `done_items`, nicht
`processed_items`. Inkonsistent: 100% Prozentsatz aber 1720/1721
absolut.

**Fix**: in `runStripRenderRow` Template-String anpassen:
```js
// alt:
<span class="run-counts">${done}/${total} (${pct}%)${failedStr}</span>
// neu:
<span class="run-counts">${processed}/${total} (${pct}%)${failedStr}</span>
```

Zwei Zeilen Code, keine API-Aenderung.

User-Quote (2026-04-25): *"Es werden zwei Flows doppelt angezeigt und
1720 / 1721 das haette auf 1721 / 1721 springen sollen, wenn der flow
durch ist. Der failed soll ja mitgezaehlt werden."*

---

## Cost-Tracking fuer GPT-5.1-Vision-Aufrufe (Prioritaet: hoch)

Heute: `disco/docs/image.py` setzt `estimated_cost_eur = 0.0`
hardcoded und speichert nur die Token-Counts in `meta_json`. Damit
zeigen `agent_flow_runs.total_cost_eur` und der Run-Strip fuer
Bild-Engines immer 0,00 €, obwohl jeder Vision-Call Foundry-Tokens
verbraucht.

Bestand-Beispiel (pipeline-fulltest, 3 Bilder):
- ~3 151 prompt + 708 completion = **3 859 Tokens**, aber 0 EUR
  ausgewiesen.

### Was zu tun ist

1. **Pricing-Modul**: `disco/pricing.py` mit zentraler Definition pro
   Foundry-Modell. Beispiel-Struktur:
   ```python
   FOUNDRY_PRICING_EUR_PER_1M_TOKENS = {
       "gpt-5.1": {"input": ..., "cached_input": ..., "output": ...},
       "gpt-5":   {...},
   }
   ```
   Mit Audit-Datum + EUR/USD-Wechselkurs-Annahme im Modul-Doc.
2. **In `image.py`** Cost berechnen:
   ```python
   cost = (prompt_tokens * P["input"] + completion_tokens * P["output"]) / 1_000_000
   meta["estimated_cost_eur"] = round(cost, 5)
   ```
3. **Cached-Input-Tokens beruecksichtigen**: Foundry liefert in der
   Usage `cached_tokens`. Cached zaehlt zu reduziertem Preis. Bei
   wiederholtem Vision-Call auf identisches System-Prompt-Praefix
   greift der Cache stark.
4. **System-Prompt-Cache nutzen** (Backlog-Querverweis): wenn wir
   Foundry-Cache-Hits drueben haben, koennen wir die System-Prompt-
   Bytes als Cache-Praefix markieren — drastische Cost-Reduktion bei
   Bulk-Vision-Laeufen ueber 100+ Bilder.

### Auswirkung auf andere Engines

- `pdf-azure-di` / `pdf-azure-di-hr`: rechnen heute korrekt mit
  `_AZURE_DI_LAYOUT_EUR_PER_PAGE` (= 8,68 / 13,89 EUR pro 1000 p).
- `pdf-docling-standard` / `excel-*` / `dwg-*`: 0 EUR ist korrekt
  (lokal, keine Cloud).
- `image-gpt5-vision`: hier sind wir schief.

### Folge: Bestand korrigieren?

Pro betroffenem Run koennten wir nachtraeglich aus `meta_json`
(prompt_tokens / completion_tokens) den EUR-Betrag rechnen und in
`agent_flow_runs.total_cost_eur` per Update korrigieren. Klein, aber
historische Daten stimmen wieder.

User-Quote (2026-04-25): *"tracken wir eigentlich schon was uns der
gpt aufruf mit den bildern kostet im flow?"*

---

## Anhaltspunkte fuer `replaces` und `format-conversion-of` (Vertiefung)

Konkrete Erkennungs-Patterns als Implementierungs-Vorlage fuer den
Filter "Extraction nur auf kanonische Dateien". Stufung von schnell
(Filename-Heuristik, kein Inhalt) zu maechtig (Embeddings, LLM).

### Replaces — Versionsketten

**Stufe 1 — Filename-Versions-Suffixe** (deterministisch, lokal, schnell):

| Pattern | Reihenfolge | In rea-denox-Pool gefunden |
|---|---|---|
| `_R0A_V00` / `_R0B_V00` / `_R0C_V00` | A→B→C | ja, sehr haeufig (Tekla/CAD-Konvention) |
| `_R00_V00` / `_R00_V01` / `_R00_V03` | nu­merisch | ja (Statik-Berechnungen) |
| `_R0A_V00` / `_R0A_V01` / `_R0A_V02` | nu­merisch | ja (Mehrfach-Iteration auf Rev.A) |
| `_v1` / `_v2` / `_v2.0` | nu­merisch | ja (`_V01`, `_V02`) |
| `_RevA` / `_RevB` | alpha­be­tisch | gelegentlich |
| `_alt` / `_old` / `_obsolet` / `_neu` / `_aktuell` | semantisch | ja (`_obsolet!`-Suffix klar) |
| ` (1)` / ` (2)` / ` (3)` | nu­merisch | ja (Windows-Copy-Suffix — meist Hash-Duplikat) |
| ISO-Datum `_2024-09-19` / `_240919` | chrono­logisch | ja (`240607_`, `240816_`, `240919_` Praefixe) |

**Vorgehen:**
1. Stamm-Stem-Normalisierung: alle bekannten Suffixe entfernen
2. Im selben Ordner gruppieren (Cross-Ordner ist riskant)
3. Suffix-Reihenfolge → "neueste" gewinnt
4. Schreibe `replaces`-Relations: alle alten verweisen auf die neueste

**Stufe 2 — Pfad-Hinweise:**
- Subordner `/archiv/`, `/alt/`, `/Rev_A/`, `/superseded/` → Datei darin ist nicht-kanonisch
- GU-spezifische Konventionen ggf. via Projekt-Konfig

**Stufe 3 — Begleit-Excel (sources_attach_metadata):**
- GU-Lieferindex-Spalte "Revision", "ersetzt durch", "Status"
- Ergibt explizite Relations ohne Heuristik

**Stufe 4 — PDF-Inhalt (Schriftfeld):**
- pypdf/PyMuPDF: `/ModDate`, `/Title` aus PDF-Metadata
- LLM-Extraktion aus dem Schriftfeld: "Index/Revision: B"
- Zeitlich-juengste Rev gewinnt

**Stufe 5 — Embedding-Aehnlichkeit (Phase 2c):**
- Bei Markdown-Embedding-Cosine >= 0.92 zwischen zwei Files mit
  unterschiedlichem Hash, gleicher Top-Level-Domain (DCC-Code o.ae.):
  Versions-Kandidat fuer LLM-Bestaetigung

### Format-conversion-of

**Stufe 1 — Stem + andere Extension** (Heuristik, sehr verlaesslich):

In rea-denox live gefunden:
- `VGB-S-831 Anlage_A1_IBL_Begleitdokumentation` als `.pdf` + `.xlsx`
- `Errichterbescheinigung` als `.docx` + `.pdf`
- `Uebersichtsliste Sicherung` als `.xlsx` + `.pdf`
- `Handover_Takeover_Plan_V01` als `.docx` + `.pdf`

**Hierarchie (was gewinnt):**

| Original | Konversion | Begruendung |
|---|---|---|
| `.dwg` | `.pdf` | DWG ist editierbar, PDF ist Plot |
| `.docx` | `.pdf` | Original > Export |
| `.xlsx` | `.pdf` | Daten > Snapshot |
| `.dwg` | `.dxf` | DWG ist Master, DXF ist Austauschformat |

Bei Mehrdeutigkeit (z.B. `.docx` + `.xlsx` mit gleichem Stem): heute
nicht typisch, ggf. via Projekt-Konfig.

**Stufe 2 — PDF-Producer-Tag** (sehr verlaesslich, lokal):
- pypdf: `reader.metadata["/Producer"]`
- Patterns:
  - `"AutoCAD"`, `"Bluebeam Revu"` -> DWG-Plot
  - `"Microsoft Word"`, `"Adobe PDF Library Word"` -> DOCX-Export
  - `"Microsoft Excel"` -> XLSX-Export
- Wenn Producer auf Originalformat hinweist UND ein File mit gleichem
  Stem in dem Format existiert: starker `format-conversion-of`-Hinweis

**Stufe 3 — Inhaltsabgleich:**
- Schriftfeld-Texte aus DWG (libredwg) vs. PDF-OCR
- >= 80 % der DWG-Schriftfeld-Texte im PDF wiederfindbar -> bestaetigt

### Implementierungs-Plan

1. **Stamm-Stem-Funktion** in `disco/docs/canonik.py` (oder als Teil der
   sources-Logik). Liste der Suffix-Patterns konfigurierbar.
2. **`sources_detect_replaces`-Tool** analog zu `sources_detect_duplicates`:
   gruppiert nach Stamm-Stem, schreibt `replaces`-Relations.
3. **`sources_detect_format_conversions`-Tool**: Stem + andere
   Extension finden, PDF-Producer-Tag pruefen, schreibt
   `format-conversion-of`-Relations.
4. **Filter im `extraction_routing_decision`-Item-Loader** (Backlog-
   Eintrag oben): Items skippen, die nicht-kanonisch sind.
5. **Optional: re-run-Mode**: bei neu detektierten Relations laesst
   sich die Pipeline auf den (jetzt) kanonischen Files re-run.

User-Quote (2026-04-26): *"Welche anhaltspunkte haetten wir um
replaces und format_converson-of zu ermitteln?"*


## Relevance-Score / Document-Scoring (Prioritaet: mittel)

Ueber `kanonisch` (= mechanisch dedupliziert) hinaus wollen wir eine
zweite, projektspezifische Achse: **Wie relevant ist dieses Dokument
fuer das Projekt-Ziel?** Heute hat jedes Dokument im Pool denselben
Wert; tatsaechlich ist eine Stahlbau-Statik fuer einen
SOLL/IST-Abgleich gegen VGB S 831 hochrelevant, ein internes
Besprechungs-Foto eher nicht.

**Zwei Spielarten:**

1. **Lifecycle-Score** (deterministisch, billig):
   `final | review | draft | archived | scratch`. Aus Pfad-Hinweisen
   (`/archiv/`, `/draft/`, `/superseded/`), Begleit-Excel-Status-Spalten
   und Versions-Suffixen ableitbar. Kein LLM noetig.

2. **Topical-Score** (LLM-basiert, teurer):
   Wie inhaltlich nah ist das Dokument am Projekt-Ziel? Aus
   `README.md` (Projekt-Ziel) + Markdown-Extrakt + Embedding-Distance
   oder LLM-Klassifikation. Skala 0-100 oder Buckets (high/medium/low).

**Use-Cases:**
- Suchergebnisse priorisieren (final > draft, hoher Topical-Score zuerst)
- Bulk-Flows nur auf relevanter Teilmenge laufen lassen
   (Token-Budget schonen)
- Reports filtern ("zeige nur high-relevance-Dokumente fuer den
  SOLL/IST-Abgleich")

**Offene Fragen** (zu klaeren bevor implementiert):
- Wer schreibt den Score: Disco automatisch beim Source-Onboarding,
  oder explizit per Skill/Flow?
- Eine Score-Spalte oder mehrere (lifecycle/topical/manual)?
- Persistiert in `agent_sources` oder eigene Tabelle `agent_source_scores`?

User-Quote (2026-04-26): *"Ich wuerde auch gerne noch sowas wie einen
relevance score einfuehren oder sowas..."*

Bezug: braucht `Anhaltspunkte fuer replaces und format-conversion-of`
fuer den Lifecycle-Score; profitiert spaeter von OpenAI Evals (s.u.)
fuer die Kalibrierung der LLM-basierten Topical-Klassifikation.


## OpenAI Evals / Azure AI Foundry Evaluations (Prioritaet: niedrig, aber strategisch)

Sobald Disco LLM-basierte Klassifikationen oder Scores produziert
(Topical-Relevance, DCC-Klassifikation, SOLL/IST-Match), brauchen wir
**systematische Qualitaetsmessung** — nicht "passt schon", sondern
reproduzierbare Eval-Runs gegen ein Goldstandard-Set.

**Was es ist:**

- **OpenAI Evals**: zwei Dinge — (a) Open-Source-Framework
  `openai/evals` (MIT) zum Bauen eigener Eval-Suiten,
  (b) Platform-Produkt `platform.openai.com/evals` mit UI, Datasets
  und gemanagten Runs.
- **Azure AI Foundry Evaluations** ist das Microsoft-Aequivalent:
  - **SDK**: `azure-ai-evaluation` (Python, MIT) — heute NICHT in
    unserem `pyproject.toml`, koennte mit `uv add azure-ai-evaluation`
    nachgezogen werden.
  - **Foundry Portal UI**: Evaluations-Tab pro Projekt fuer Runs,
    Vergleiche und Dataset-Verwaltung.
- **Built-in Evaluators** (Sweden Central verfuegbar):
  `RelevanceEvaluator`, `GroundednessEvaluator`, `CoherenceEvaluator`,
  `FluencyEvaluator`, `SimilarityEvaluator`. Alle nehmen Query +
  Response (+ optional Context) und liefern einen 1-5-Score plus
  Begruendung.
- **Custom Evaluators**: eigene Python-Klassen mit `__call__(query,
  response, ground_truth, ...) -> dict` lassen sich registrieren und
  in Eval-Runs mischen.

**Fuer Disco relevant in:**

1. **Kalibrierung der Relevance-Score-Rubrik** (s.o.): bevor wir auf
   3.000 Dokumente loslassen, ein 50-er-Goldstandard mit
   Human-Labels bauen, drei Prompt-Varianten gegen den Goldstandard
   evaluieren, beste Variante in Prod.
2. **A/B-Tests bei Prompt-Aenderungen**: System-Prompt-Update auf dem
   Portal-Agent — vorher/nachher-Eval ueber dasselbe Goldstandard-Set,
   damit Regressions nicht erst dem User auffallen.
3. **Klassifikator-Qualitaet**: DCC-/Gewerks-Klassifikation,
   SOLL/IST-Match — alles Use-Cases mit klarer Wahrheit, ideal fuer
   Evals.

**Vermutete Kosten** (Sweden Central Listpreise):
- Built-in-Evaluators sind LLM-Calls gegen GPT-4-Klasse-Modell, also
  ~$0.01-0.05 pro Eval-Run-Item, Goldstandard-Set 50 Items + 3
  Prompt-Varianten ~ 1-3 EUR pro Kalibrierungs-Zyklus. Vernachlaessigbar.

**Implementierungs-Skizze** (wenn wir es angehen):

1. `uv add azure-ai-evaluation`
2. Goldstandard-Set bauen: `~/Disco/projects/<slug>/evals/goldstandard.jsonl`
   mit `{"document_id": ..., "expected_relevance": "high", "rationale": "..."}`.
3. Eval-Skript in `scripts/evals/relevance_eval.py`: laedt Goldstandard,
   ruft Disco-Klassifikator pro Item, vergleicht mit Built-in
   `RelevanceEvaluator` + Custom-Evaluator (exact-match auf
   high/medium/low).
4. Run via `uv run python scripts/evals/relevance_eval.py` ergibt
   einen JSONL-Eval-Report; bei Aenderung des System-Prompts oder
   Modell-Deployments einfach erneut ausfuehren.
5. **Optional Phase 2**: Eval-Runs auch im Foundry-Portal sichtbar
   machen ueber `azure.ai.evaluation.evaluate(target=..., evaluators=...,
   azure_ai_project=...)` — zentrales Dashboard fuer alle Eval-Runs.

**Warum jetzt nicht implementieren:**
- Solange wir keine LLM-basierten Scores in Prod haben, gibt's nichts
  zu evaluieren.
- Sobald Topical-Relevance oder DCC-Klassifikation aktiv sind, wird
  Eval-Setup vor Skalierung Pflicht.

User-Quote (2026-04-26): *"Ne, das thema ist noch zu frueh aber
brauchen wir. Kommt auf die BL bitte"*


## Stabilitaets-Bugs aus FTS5-Deadlock 2026-04-26 (Prioritaet: hoch)

Beim Aufbau eines FTS5-Suchindex auf bew-rsd-lager-halle ist der
Prod-Server gehangen — Diagnose live durchgefuehrt. Eine Kette von
verbundenen Bugs, die alle einzeln in den Backlog wollen:

### 1. FTS5-Indexer blockiert Prod-Server (HAUPT-BUG)

**Symptom**: User triggert "baue Suchindex auf lager-halle". Aufgabe
laeuft als `multiprocessing.spawn`-Subprocess vom Uvicorn (PID 57812
im Live-Vorfall). Nach kurzem normalem Lauf bleibt der Subprocess in
einer FTS5-Sync-Endlosschleife stehen — Stack zeigt
`fts5SyncMethod → fts5IndexFlush → fts5DataRead → blobReadWrite`,
100% CPU auf einem Core, **kein Wachstum** der `datastore.db` oder
`datastore.db-wal` ueber Minuten.

**Folge-Schaden**: Subprocess teilt sich einen
`multiprocessing.Manager`-Lock-Server mit zwei laufenden Flow-Runner-
Children (campus-reuter Run #4, rea-denox Run #15). Beide Children
stehen sofort still, sobald sie den naechsten Status-Update an den
Parent abschicken wollen — Stack zeigt
`pysqlite_connection_commit_impl → unixSync → __psynch_cvwait`. Der
gesamte Flow-Subsystem ist eingefroren.

**Folge zwei**: Uvicorn-Hauptprozess (PID 57710) hat in seinem
`--reload`-Watchfiles-Thread einen `pthread_mutex_lock` auf einer
Mutex die ein toter Thread haelt — Server antwortet nicht mehr auf
`/api/health` (5s timeout). SIGTERM wirkungslos, SIGKILL noetig.

**Was zu tun ist**:
1. **FTS5-Sync-Hang reproduzieren** — herausfinden, welche
   Markdown-Einheit das ausloest. Verdacht: ein einziger sehr grosser
   Markdown-Block (mehrere MB), den FTS5 nicht inkrementell flushen
   kann. Mitigation: Markdown-Inputs vor dem FTS5-Insert chunken
   (max 200KB pro Row) — passt eh zur Hybrid-Search-Phase 2c-Strategie
   (~500-800-Tokens-Chunks).
2. **Indexer als isolierter Subprocess, nicht
   `multiprocessing.spawn` vom Uvicorn**. Statt dessen: separater
   Worker-Prozess (analog zu Flow-Runner via `runner_host`), der NUR
   ueber DB-Status mit dem Service kommuniziert — kein
   `multiprocessing.Manager` zwischen Web-Server und Indexer.
3. **Indexer interruptible**: User-Klick auf "Cancel" muss die Sync-
   Operation sauber abbrechen koennen, auch wenn FTS5 in einem Loop
   steckt. Heute: nur SIGKILL hilft.
4. **Watchfiles-Reload weniger gefahrlich machen**: wenn ein
   Subprocess-Crash detected wird, sollte Uvicorn den Reload-Cycle
   nicht im Hauptprozess synchron abschliessen, sondern lazy
   restartet werden.

### 2. Counter-Update-Bug nach unsauberem Shutdown

**Symptom**: Beim Restart eines Flow-Runs nach dem Crash zaehlt
`agent_flow_runs.done_items` nicht hoch, obwohl
`agent_doc_markdown` korrekt befuellt wird. Beobachtet bei
campus-reuter Run #5 — `done_items=0`, aber 14 Markdown-Records mit
`run_id=5`. Discrepancy bleibt waehrend des gesamten Run-Verlaufs
bestehen, nicht nur am Anfang.

**Verdacht**: workspace.db hat aus dem Crash eine Stale-Lock-Page
oder ein Transaktions-State, der den UPDATE-Pfad fuer `done_items`
blockiert (oder still verschluckt). Inserts in datastore.db gehen
durch, weil das eine andere DB ist.

**Was zu tun ist**:
1. **Reproduzieren** im Dev: Flow-Run starten → SIGKILL → neuen Run
   starten → checken ob done_items mitwaechst.
2. **WAL-Checkpoint beim Service-Start**: vor dem ersten Open der
   workspace.db ein `PRAGMA wal_checkpoint(TRUNCATE)` ausfuehren.
3. **Stale-Run-Recovery beim Service-Start**: `agent_flow_runs` mit
   `status='running'` und `worker_pid` der nicht mehr existiert
   automatisch auf `status='failed'` setzen mit
   `error='killed during shutdown'`. Heute: bleibt manuell zu
   bereinigen.

### 3. Azure-DI HighRes: max_retries zu niedrig

**Symptom**: HR-Endpoint liefert vereinzelt `(InternalServerError)
An unexpected error occurred.` zurueck. Bei `max_retries=1` (heute)
ist das Item sofort als failed markiert. Beobachtet: 7 von 14
versuchten HR-Items in campus-reuter Run #5 (50%!) gefailt mit
diesem Fehler. Andere HR-Items kommen normal durch.

**Was zu tun ist**:
1. **`max_retries=3` mit Exponential-Backoff** (300ms, 1s, 3s) fuer
   die Engines pdf-azure-di, pdf-azure-di-hr, image-gpt5-vision —
   alles Engines die gegen Azure laufen.
2. **HR→Standard-Fallback** als Option: nach N HR-Failures auf
   demselben Item, einmal mit pdf-azure-di-Standard versuchen. Verlust
   an Qualitaet (bei Plaenen schlechter), aber besser als kein
   Output. Konfigurierbar.

### 4. LibreDWG SIGABRT bei bestimmten DWGs (bekannt, aber Anteil hoch)

**Symptom**: `dwg2dxf` killed sich mit SIGABRT bei manchen DWGs.
Beobachtet 18 SIGABRT-Cases + 4 "Invalid handle 0" + 2
"Expected DXF entity" + 2 "'MODEL'"-KeyError = **26 von 35 DWGs
gefailt** in campus-reuter Run #5 (74%!). Der LibreDWG-Code (GPL-3,
OSS) hat Probleme mit AutoCAD-2018+-Features oder bestimmten
Tekla-/CAD-Konventionen.

**Was zu tun ist**:
1. **Fallback auf einen zweiten Konverter**: ezdxf hat selbst einen
   experimentellen DWG-Reader (in C, ueber `cadtool` oder
   `pyodadrx` — closed-source aber lokal). Oder: DWGs die libredwg
   nicht kann, **skippen mit klarer Markierung** und manuell
   nachverarbeiten.
2. **Fehler-Klassifikation**: in `disco/docs/dwg.py` die
   LibreDWG-Crashes von ezdxf-Read-Errors trennen — heute kommen
   beide als "DXF-Read nach LibreDWG-Konvertierung fehlgeschlagen"
   raus, was die Statistik unscharf macht.
3. **Pool-Curation**: bei ~74% LibreDWG-Failrate auf Stahlbau-DWGs
   ist der Outsource-Tool-Markt vielleicht der falsche. Bei Bedarf:
   ODA File Converter wieder reaktivieren (closed-source, aber
   lizenzfrei, deutlich stabiler) — Risiko: Konvention 9 (Network
   Egress) muss neu geprueft werden, weil ODA-Updates online
   geholt werden.

User-Beobachtung 2026-04-26: *"jetzt habe ich die flows neu
gestartet aber im hintergrund failed alles"* — die echten
Erfolgsraten waren ~26% (counter falsch) bzw. ~45% wenn man
LibreDWG-Bugs als bekannt rausrechnet.

Bezug zur "Hybrid-Search Phase 2c"-Sektion in CLAUDE.md ("Was als
Naechstes kommt"): Der hier beschriebene FTS5-Indexer ist offenbar
ein laengst angefangener Code-Pfad, kein offizieller Phase 2c-
Indexer. Vor weiterer Arbeit: aufraeumen und planen, statt
inkrementell weiter zu erweitern.


## Disco-Prozess-Management fuer den User (Prioritaet: hoch)

Heute ist Claude die einzige Instanz, die den Disco-Server (Dev +
Prod) starten, ueberwachen und beenden kann. Der User hat keine
Uebersicht und keine eigenen Tools — er muss bei jedem Hagel
("Server haengt", "Flows failen", "Restart noetig") fragen, statt
selbst eingreifen zu koennen. Das ist ein UX-Defizit, nicht zuletzt,
weil der User Disco jeden Tag laufen hat und Claude *nicht* immer
gleich verfuegbar ist.

**Was der User heute (un-)kann:**

| Aktivitaet | Heute | Pain |
|---|---|---|
| Server starten (Dev/Prod) | langer `cd ... && DISCO_WORKSPACE=... uv run uvicorn ...` aus CLAUDE.md kopieren | hoch — er macht das selten, vergisst die Flags |
| Sehen, ob Server laeuft | `lsof -i :8765` oder Browser-Probe | mittel |
| Sehen, was an Subprocesses haengt | nur via Activity-Monitor (Mac), keine Disco-Sicht | hoch — er sieht "Python-Prozess mit 100% CPU" und weiss nicht, was es ist |
| Server stoppen | `pkill -f "port 8765"` oder `kill <PID>` von Hand | mittel, leicht falsch zu machen |
| Hangenden Subprocess killen (wie heute der FTS5-Spinner) | gar nicht — er ruft Claude | hoch |
| Flow-Runs ueberwachen | UI-Run-Strip + Logs lesen | OK fuer normale Faelle, schwach bei Stale-States |
| Stale "running"-Flow-Runs aufraeumen | gar nicht — bleibt manuell | mittel |

### Was wir bauen sollten

**1. `disco service`-CLI** (existiert noch nicht):

```bash
disco service status           # Was laeuft? Dev-Server? Prod-Server? Welche Flow-Runner? PIDs, CPU, Uptime
disco service start dev        # Dev-Server hochfahren (Port 8766, ~/Disco-dev)
disco service start prod       # Prod-Server hochfahren (Port 8765, ~/Disco)
disco service stop dev|prod    # Sauber stoppen (SIGTERM, dann ggf. SIGKILL)
disco service restart dev|prod # Kombi: stop + start, mit Health-Check
disco service logs dev|prod [--tail N]  # Live-Tail oder letzte N Zeilen vom Server
disco service kill <pid>       # einen Subprocess mit Sicherheitsabfrage killen
```

Implementierung: dünner Wrapper um `lsof`/`ps`/`kill`, plus Disco-
Wissen ueber Process-Markers (z.B. "uvicorn fuer Port 8765 mit
DISCO_WORKSPACE=~/Disco" = Prod-Server). Speichert PID-Files unter
`~/Disco/.disco/server.prod.pid` — dann ist die Identifikation
robust auch wenn das `--reload` den Worker-Prozess tauscht.

**2. `disco doctor`-Diagnose-Command**:

Bei einem haengenden Server: User ruft `disco doctor` auf, kriegt
eine Zusammenfassung:
- Welche Disco-Prozesse laufen (Server + Subprocesses)
- Welche davon hoch-CPU oder lang-laufend sind
- Welche WAL-Files >10MB sind (Hinweis auf nicht-committete
  Transaktionen)
- Welche Stale "running"-Flow-Runs in der DB stehen
- Empfohlene Aktion ("Subprocess 12345 spinning seit 30min — kann
  mit `disco service kill 12345` beendet werden")

Im Wesentlichen das, was Claude in der heutigen Session live mit
einer Mischung aus `ps`, `lsof`, `sample` und SQLite-Queries gebaut
hat — automatisiert.

**3. UI-Sicht "Server-Status"**:

In der Web-UI (Sidebar oder Settings-Pane) eine kleine
Process-Anzeige: "Dev-Server :8766 ✓ (PID 12345, Uptime 2h 15min,
3 Flow-Runner aktiv)". Bei Hang: "⚠ Subprocess 12345 spinning seit
30min — Details anzeigen".

**4. Operations-Manual** (`docs/operations.md`):

Ein kurzer User-Leitfaden:
- Wie starte/stoppe ich Server?
- Was tun bei "Server antwortet nicht"?
- Was bedeuten die Run-Strip-Status (running/done/failed/stale)?
- Wie kille ich einen haengenden Subprocess sicher?
- Wann brauche ich Claude vs. wann kann ich selbst handeln?

### Reihenfolge

Schritt 1 ist `disco service status` + `start` + `stop` + `restart`
+ ein erstes `docs/operations.md`. Das deckt 80% der Faelle ab und
macht den User unabhaengig fuer den Alltag. Schritte 2-3 (doctor,
UI-Sicht) sind nice-to-have.

User-Quote (2026-04-26): *"Wir muessen einmal darueber sprechen wie
ich die processe von disco selbstaendig starten ueberwachen und
beenden kann. Aktuell lasse ich dich das immer machen und habe
selbst keine Uebersicht."*

**Zu diskutieren** bevor wir bauen:
- Soll `disco service` auch Caffeinate ein/aus nehmen?
- Sollen Dev + Prod gemeinsam gestartet werden ("`disco service start
  all`") oder bewusst getrennt?
- PID-File-Strategie: pro Workspace (~/Disco/.disco/server.pid) oder
  zentral (~/.disco/services.json)?
- Wie verhalten wir uns bei `--reload`-Worker-Tausch (PID-Wechsel)?


## Sidebar-Navigation skaliert nicht (Prioritaet: hoch)

**Beobachtung 2026-04-27 in lager-halle**: die Sidebar listet 12
datastore.db-Tabellen, ~60+ workspace.db-Tabellen (vor allem
`context_*`-Tabellen wie `context_armatur_regel__armatur_b_reg`,
`context_batterie__batterie_b`, ...) und 2 Flows. Insgesamt > 80
Eintraege in einer endlosen, flachen Scroll-Liste. Die Tabellen-
namen sind so lang, dass sie haeufig abgeschnitten dargestellt
werden ("context_armatur_rueckschlag__armatur..." mit "..."-
Truncation).

Mit jedem context-Excel-Import werden 5-10 weitere Tabellen
angelegt (z.B. VGB-S-831-Anlagen-Tabellen). Bei mehreren grossen
Projekten oder beim sources-Onboarding mit Begleit-Excels wird
die Sidebar in Zukunft eher 200+ Eintraege haben.

### User-Anforderung (Minimum)

> "Sollte mindestens expandable sein."

Also: jede Gruppe (datastore.db / workspace.db / Flows) und jede
Untergruppe (context_armatur_regel, context_batterie, ...) muss
einklappbar sein. Default-State waere "alles eingeklappt ausser
das was kuerzlich geoeffnet war".

### Vorschlaege fuer den Polish darueber hinaus

1. **Gruppierung nach Namespace-Praefix**:
   - `agent_*` als Gruppe (immer aufgeklappt — Kern-Tabellen)
   - `work_*` als Gruppe (Arbeitstabellen, oft ad-hoc)
   - `context_*` mit Sub-Gruppierung am `__`-Separator
     (z.B. alle `context_armatur_regel__*` unter einer Section
     "context_armatur_regel" zusammenfassen)

2. **DB-File als oberste Hierarchie-Ebene** (Datastore vs.
   Workspace bleibt wichtige Unterscheidung — Read-only-Status
   ist heute nur Text-Annotation, koennte ein Icon werden).

3. **Filter-/Suchfeld** ueber der Liste: tippe "armatur" → nur
   passende Tabellen sichtbar.

4. **Pin-Funktion**: haeufig benutzte Tabellen oben, manuell
   pinbar (sticky pro Projekt im LocalStorage).

5. **Leere Tabellen ausblenden** als Toggle: in lager-halle hat
   `agent_source_metadata` 0 Rows, `agent_source_relations` 0,
   `agent_sharepoint_docs` ist da aber wird nicht aktiv genutzt.
   Default-Modus "verstecke leere" reduziert das Listing oft
   um 30%.

6. **Row-Count-Spalte besser nutzen**: heute steht der Count
   rechts neben dem Namen — bei Truncation des Namens unklar
   welcher Count zu welchem Namen gehoert. Ggf. besser als
   Tooltip oder unter dem Namen.

7. **Flows-Bereich aehnlich**: aktuell flach, aber bei vielen
   Flows kommt das gleiche Problem. Gruppierung nach Status
   (running / done / failed / scheduled) oder nach Flow-Name
   waere sinnvoll.

### Implementierungs-Reihenfolge

Schritt 1 — **Expandable** (User-Minimum):
  - Pro Top-Level-Section (datastore.db, workspace.db, Flows)
    ein Disclosure-Triangle (`<details>` reicht im einfachsten
    Fall). State im LocalStorage, pro Projekt.

Schritt 2 — **Namespace-Gruppierung**:
  - Bei context_*-Tabellen: split am ersten `__`, Untergruppen
    bilden. Gruppe einklappbar, Default eingeklappt wenn > 5
    Tabellen pro Gruppe.

Schritt 3 — **Filter-Feld**:
  - Eine kleine `<input>`-Box oben mit Echtzeit-Filter ueber
    den Tabellenname. Reduziert die meisten Such-Use-Cases.

Schritte 4-7 sind Polish, koennen iterativ kommen.

User-Quote (2026-04-27): *"Mit steigender menge an flows und
Datentabellen wird die Navigationseite sehr unuebersichtlich.
Hier muessen wir uns was einfallen lassen. Sollte mindestens
expandable sein."*


## Extraction-Pipeline-UX: Ampelsystem, Auto-Pipeline, Batch-Mode (Prioritaet: hoch)

**Heutige Realitaet** (live durchgelitten 2026-04-26/27): die
Pipeline von "Datei in sources/ kopiert" bis "im FTS5-Suchindex
findbar" funktioniert grundsaetzlich, aber jeder Schritt muss
einzeln vom User angestossen werden, jeder Zwischenstand kann
ohne klare Anzeige drift­en, und Fehlermeldungen kommen ad-hoc
("Datei nicht in agent_doc_markdown", "context_length_exceeded",
"Pfad ohne Prefix"). Disco kann zwar alle Schritte ausfuehren,
aber das Bild "wo stehen wir gerade pro Datei" ist nicht sichtbar.

Heutige Schritt-Sequenz pro Paket neuer Dateien:

1. Files in `sources/` kopieren (manuell)
2. `sources_register` aufrufen → Hash, Groesse, Eintrag in
   `agent_sources`
3. Optional `sources_attach_metadata` (Begleit-Excel)
4. Optional `sources_detect_duplicates`
5. Flow `extraction_routing_decision` starten (entscheidet
   pro File welche Engine) → schreibt in `work_extraction_routing`
6. Flow `extraction` starten → liest Routing, ruft Engine an,
   schreibt in `agent_doc_markdown`
7. `build_search_index` aufrufen → liest `agent_doc_markdown`,
   baut FTS5-Index

Zwischen jedem Schritt: User muss explizit triggern oder Disco
darum bitten. Bei einem Restart oder Crash: kein einfaches
"mach weiter wo ich war".

### User-Anforderungen (2026-04-27)

> "Da müssen wir ran:
> - ganz klar strukturierter Ablauf mit Ampelsystem
> - Vollstaendiger Durchlauf neuer Files sollte der Standard sein
> - Batchprocessing ueber Nacht ueberlegung? (Kosten sparen moeglich)"

### 1. Ampelsystem — pro Datei ein klarer Status

Vorschlag: 4-Stufen-Status in `agent_sources` als zusaetzliche
Spalte `pipeline_state`:

| State | Bedeutung | DB-Indikator |
|---|---|---|
| 🔴 `registered` | Hash + Eintrag, sonst nichts | nur in `agent_sources` |
| 🟠 `routed` | Routing-Engine entschieden | + in `work_extraction_routing` |
| 🟡 `extracted` | Markdown vorhanden | + in `agent_doc_markdown` |
| 🟢 `searchable` | im FTS5-Index | + in `agent_search_docs` |

Anzeige: Ampel-Icon in Web-UI-Explorer neben jedem Filename.
Tooltip mit Details (Engine, Cost, letzter Run, etc.). Ein
Dashboard-Widget oben zeigt das Aggregat: "1708 von 1806 sind
🟡, 0 sind 🟢". Klick → Filter auf "alle nicht-grünen".

Plus eine fuenfte Stufe ⚫ `error` mit letzter Error-Message,
wenn ein Schritt fehlgeschlagen ist (z.B. LibreDWG-SIGABRT).

### 2. Vollstaendiger Durchlauf als Standard

Heute muss der User vier Tools/Flows nacheinander triggern. Ziel:
**ein Klick / ein Befehl** macht alles fuer neue Files.

Vorschlaege:

a) **Neuer Flow `pipeline`**, der intern register → routing →
   extract → index orchestriert. Items sind Files (nicht Engine-
   Aufrufe), pro Item laeuft die ganze Pipeline durch. Status
   pro Item zeigt den aktuellen Schritt. Bei Fehler in einem
   Schritt: Item failed mit klarer Phase ("failed: extraction
   step on engine pdf-azure-di-hr").

b) **Auto-Trigger beim Source-Onboarding**: `sources_register`
   bekommt eine Option `auto_pipeline=true` (Default true), die
   die Pipeline-Stufen direkt nach dem Registrieren startet.

c) **Inotify/FS-Watcher** (Phase 2): Disco watch `sources/`-Folder,
   erkennt neue Files automatisch, triggert Pipeline. Kein
   manuelles Eingreifen mehr.

Variante (a) ist der pragmatische Einstieg. (b) und (c) sind
Komfort obendrauf.

### 3. Batchprocessing ueber Nacht (Kosten-Reduktion)

Azure-DI und Azure OpenAI bieten **Batch-APIs** mit ~50% Rabatt
gegenueber den Real-time-Endpoints — Gegenleistung: bis zu 24h
Bearbeitungszeit, kein Streaming.

**Ueberschlagsrechnung** fuer ein typisches Onboarding-Paket:
- 2000 PDFs × 0.014 EUR (Standard-Real-time-DI) = 28 EUR
- mit Batch-API: ~14 EUR
- Pro Onboarding-Tag also ~14 EUR Einsparung

Bei 10 Projekten/Jahr mit grossen Paketen: ~140 EUR/Jahr. Nicht
huge, aber sauber.

**Implementation:**

- Neue Engines `pdf-azure-di-batch`, `pdf-azure-di-hr-batch`,
  `image-gpt5-vision-batch` parallel zu den Real-time-Engines.
- Routing-Decision bekommt einen `prefer_batch=true|false`-Mode.
  Default `false` (Real-time), `true` aktivierbar im Flow-Start
  ("Diesen Run als Nacht-Batch laufen lassen").
- Neue Tabelle `agent_batch_jobs` mit submit-Zeit, externem
  Job-ID, Status, Result-Download-URL.
- Neuer Flow `batch_poll`: laeuft alle ~30 min, fragt offene
  Jobs ab, schreibt fertige Results in `agent_doc_markdown`,
  closed Jobs in `agent_batch_jobs`.
- UI: Batch-Run sieht aus wie ein normaler Flow-Run, aber mit
  Statusangabe "Submitted, expected by 06:00".

**Zu klaeren** vor Implementation:
- Welche Items lohnen sich fuer Batch (klar: PDFs ueber Real-time
  $$$, weniger klar: einzelne grosse Excels)?
- Fallback wenn Batch-Job failed (Real-time-Re-Run?)
- Wie verhalten wir uns bei einem Batch-Run, der teilweise da
  ist (z.B. 1500 von 2000 Items fertig nach 18h)?

### Weiteres aus der heutigen Schmerz-Session, was passend hier rein gehoert:

- **Counter-Update-Bug nach Crash** (siehe Eintrag "Stabilitaets-
  Bugs aus FTS5-Deadlock" oben): Pipeline-Status-Anzeige darf nicht
  von Counter-Update-Bugs abhaengen — Source of Truth muss die
  echte Daten-Existenz sein (z.B. COUNT von `agent_doc_markdown`
  statt `agent_flow_runs.done_items`).
- **Vorbedingungs-Pruefung**: heute prueft `build_search_index`
  pro File ob `agent_doc_markdown` einen Eintrag hat. Bei 1500
  Misses gibt's 1500 Errors. Das Pipeline-Konzept oben loest
  das, weil Files erst in der Pipeline-Phase "extracted" sind
  bevor sie indiziert werden.
- **lager-halle Pfad-Bug** (siehe Vorgeschichte): hatte mit dem
  Race zwischen Migration 009 und parallel laufendem alten
  Extraktor zu tun. Pipeline mit klarem State-Modell verhindert,
  dass solche Inkonsistenzen still untergehen.

### 4. Retry-Strategie und Permanent-Fail-Markierung

**User-Anforderung 2026-04-27**: *"Die Dateien die beim
extraction failen sollen gleich 2 mal neu versucht werden und
dann markiert und beim naechsten durchlauf nicht neu versucht
werden."*

Heute ist `max_retries=1` (Logs zeigen "Attempt 1/1 FEHLER" —
ein Versuch, sofort als failed markiert). Aenderung:

| Versuch | Verhalten |
|---|---|
| Attempt 1 | normal versuchen |
| Attempt 2 | retry mit Exponential-Backoff (z.B. 30s, 2min) |
| Attempt 3 | letzter retry |
| Nach 3× failed | Item bekommt `pipeline_state='extraction_failed'` mit Timestamp + last_error + n_attempts |

**Beim naechsten `pipeline`/`extraction`-Run**:
- Items mit `pipeline_state='extraction_failed'` werden DEFAULT
  geskippt (`reason="permanent_failed"`).
- Force-Override via Flow-Config: `force_retry_failed=true`
  (z.B. wenn LibreDWG ein Update hatte und man schauen will
  ob die Files jetzt durchgehen).
- UI zeigt diese Items als ⚫ (separates Icon vom 🔴 "noch nichts
  passiert"-State), Tooltip zeigt last_error + Datum.
- `agent_sources` bekommt zusaetzliche Spalten: `last_attempt_at`,
  `attempt_count`, `last_error_message` (~250 chars truncated).

**Differenzierung transient vs. permanent**:
- Azure-DI `InternalServerError` → transient, retries lohnen sich
- LibreDWG `SIGABRT` → permanent (Datei ist kaputt), retries
  helfen nicht
- pypdf-CID → permanent (jetzt aber nicht mehr relevant da v2)
- Heuristik: nach 3× demselben Error-Pattern hintereinander
  → als permanent markieren, sonst noch transient. Das verhindert
  endloses Retry bei klar persistenten Bugs.

**Querverweis zu "Stabilitaets-Bugs aus FTS5-Deadlock 2026-04-26"
Section 3** ("Azure-DI HighRes: max_retries zu niedrig") — das
hier ist die strukturierte User-Sicht-Variante davon und sollte
zusammen umgesetzt werden.

### Implementierungs-Reihenfolge

1. **`pipeline_state`-Spalte** in `agent_sources` + Backfill-
   Migration (idempotent, leitet aus existierenden Tabellen ab).
   States: `registered`, `routed`, `extracted`, `searchable`,
   `extraction_failed`. Plus Retry-Spalten (`attempt_count`,
   `last_attempt_at`, `last_error_message`).
2. **Web-UI-Explorer**: Ampel-Icon neben Filename, Aggregat-
   Widget oben, separates ⚫-Icon fuer permanent-failed.
3. **Flow `extraction`**: max_retries=3 mit Backoff, bei finalem
   Fail Status auf `extraction_failed` setzen.
4. **Flow `pipeline`**: orchestriert die 4 Schritte als One-Click,
   skipped permanent-failed by default.
5. **Auto-Trigger** in `sources_register`.
6. **Batch-API-Engines** als optionaler Mode (Phase 2).
7. **FS-Watcher** (Phase 3).

User-Quote (2026-04-27): *"Die gesamte extraction pipeline von
registrierung bis hin zum fertigen suchindex funktioniert
grundsetzlich, ist aber grade extrem! muehsam. Da muessen wir
ran ..."*


## File-Internal-Metadata bei Registrierung extrahieren (Prioritaet: hoch)

**Beobachtung 2026-04-27**: PDFs, Excels, DWGs, JPEGs tragen
**reichhaltige Metadaten in der Datei selbst** — Author, Creator-
App, Erstell-/Aenderungsdatum, Custom-Properties (z.B. KKS-Tags
im DWG-Schriftfeld), EXIF-GPS bei Fotos. Diese Daten sind:

- **kostenlos** (lokal mit pypdf/openpyxl/ezdxf/Pillow lesbar — kein Cloud-Call)
- **portable** (bleiben beim Kopieren erhalten — anders als FS-mtime)
- **bleibend** (im File-Bytestream, vom Filesystem unabhaengig)

**Heutige Disco-Nutzung: praktisch nichts.** Disco kennt nur
sha256, Groesse und Pfad. Ein riesiger ungenutzter Datenkanal.

### Stichprobe aus lager-halle (live, 2026-04-27)

**PDF (`/Info` + XMP):**
```
Anleitung zur Nutzung.pdf:
  /Author        = Anastasia Schmitke
  /CreationDate  = 2024-11-19 09:40:35 +01:00
  /ModDate       = 2025-01-07 12:53:15 +01:00
  /Creator       = Microsoft® Word für Microsoft 365
  /Producer      = Microsoft® Word für Microsoft 365

BE0497 Fachbauleitererklärung.pdf:
  /Producer      = Foxit PhantomPDF Printer 9.3.0  ← Hinweis: Print-Output
  /PXCViewerInfo = PDF-XChange Viewer 2.5.322       ← jemand hat annotiert
  /CreationDate  = 2021-11-19  /ModDate = 2025-11-25 ← 4 Jahre alt, kuerzlich
                                                       editiert
```

**Excel (DocProps `core.xml`):**
```
U-Wert-BE0497a-BTL50200.xlsx:
  creator        = openpyxl     ← KEIN User! Programmatisch erzeugt
  created        = 2025-06-20   modified = 2025-06-20
```

**DWG (`$HEADER`-Section):**
```
BE0497-5-OP-LA-XX-00100.dwg:
  $ACADVER       = AC1024       ← AutoCAD 2010-Format
  $TDCREATE      = JulianDate   $TDUPDATE = JulianDate
  $DWGCODEPAGE   = ANSI_1252
```

**JPEG (EXIF — bei Fotos voll, bei Skizzen leer):**
```
1b.jpg: nur Resolution-Tags  (Skizze, kein Foto)
echtes-Baustellenfoto.jpg: Make, Model, DateTime, GPSLatitude,
                            GPSLongitude, Orientation, ISO, ...
```

### Warum das wichtig ist (Use-Cases)

| Metadatum | Use-Case | Welcher anderer Backlog-Eintrag profitiert |
|---|---|---|
| `/ModDate` ueber Stamm-Stem | Versions-Erkennung ohne Filename-Heuristik | "replaces / format-conversion-of" Stufe 4 |
| `/Producer = "AutoCAD"` | DWG → PDF Plot erkennen | "format-conversion-of" Stufe 2 |
| `/CreationDate` (alt) | Lifecycle-Score (alte Dokumente weniger relevant) | "Relevance-Score / Document-Scoring" |
| Excel `creator = openpyxl` | Auto-Erkennung Begleit-Excel vs. User-Excel | "Pipeline-UX" Routing |
| DWG `$ACADVER` | LibreDWG-Kompatibilitaet vorab pruefen (Failrate-Reduktion) | "Stabilitaets-Bugs" Section 4 |
| DWG `$CUSTOMPROPERTY` | KKS-Tags direkt aus Schriftfeld, ohne OCR | "Objekt-Inhalt-Modell" |
| `/Author`, `lastModifiedBy` | Provenance-Header in Markdown, Verantwortliche tracken | "Provenance" |
| EXIF `GPS` | Foto-Dokumentation auf Anlagenplan verorten | (neu) |
| EXIF `DateTime` | Baustellen-Fortschritt zeitlich ordnen | (neu) |
| `/Producer = "PDF-XChange Viewer"` | Annotations-Hinweis: Datei wurde manuell bearbeitet | (neu — Provenance) |

### DB-Schema-Vorschlag

Erweitere `agent_sources` mit "first-class"-Spalten fuer haeufig
abgefragte Felder + JSON-Spalte fuer den Rest:

```sql
ALTER TABLE agent_sources ADD COLUMN file_author TEXT;
ALTER TABLE agent_sources ADD COLUMN file_creation_date TEXT;  -- ISO 8601
ALTER TABLE agent_sources ADD COLUMN file_modification_date TEXT;  -- ISO 8601
ALTER TABLE agent_sources ADD COLUMN file_creator_app TEXT;    -- z.B. "Microsoft Word"
ALTER TABLE agent_sources ADD COLUMN file_producer_app TEXT;   -- z.B. "Foxit PhantomPDF"
ALTER TABLE agent_sources ADD COLUMN file_title TEXT;
ALTER TABLE agent_sources ADD COLUMN file_format_version TEXT; -- z.B. "AC1024", "PDF-1.4"
ALTER TABLE agent_sources ADD COLUMN file_metadata_json TEXT;  -- Rest als JSON (XMP, EXIF, $CUSTOM)
```

Vorteile:
- Common Queries (Author, Datum, App) gehen ueber Spalten — schnell, indizierbar
- Spezial-Felder (z.B. EXIF-GPS, PDF-XMP-Document-ID) bleiben in JSON erreichbar via `json_extract()`
- Rueckwaertskompatibel: bestehende Spalten bleiben unangetastet

### Implementierungs-Reihenfolge

1. **Migration** datastore/010 mit den Spalten + JSON. Idempotent
   via `CREATE TABLE IF NOT EXISTS` und `ALTER TABLE ADD COLUMN`
   in einer Transaktion.

2. **Extractor-Modul** `src/disco/sources/file_metadata.py`:
   ```python
   def extract_file_metadata(abs_path: Path, file_kind: str) -> dict:
       """Liefert dict mit den first-class-Feldern + 'extra'-JSON."""
       if file_kind == 'pdf': return _extract_pdf(abs_path)
       if file_kind == 'excel': return _extract_excel(abs_path)
       if file_kind == 'dwg': return _extract_dwg(abs_path)
       if file_kind == 'image': return _extract_image(abs_path)
       return {}
   ```
   Pro Engine eine Funktion. Errors silent (best-effort, blockiert
   Registrierung nicht).

3. **Hook in `sources_register`**: bei jedem neuen/geaenderten
   File auch `extract_file_metadata` aufrufen, Ergebnis in
   `agent_sources` schreiben. Bei Re-Register (sha256 unveraendert)
   nicht erneut extrahieren.

4. **Backfill-Script** `scripts/backfill_file_metadata.py` fuer
   Bestandsprojekte: liest alle `agent_sources`-Eintraege mit
   `file_author IS NULL`, extrahiert Metadata, schreibt zurueck.
   Idempotent.

5. **Verfuegbar machen** in:
   - `doc_markdown_read`: Provenance-Header mit Author/Datum
   - `search_index`: Filter nach `file_author`, `file_creator_app`
   - Web-UI Explorer: Tooltip mit Metadaten beim Hover

6. **Routing-Decision-Erweiterung**: `_decide_dwg` prueft `$ACADVER`
   — bei AC1032+ Fallback auf eine andere Engine oder direkt skippen
   (LibreDWG-SIGABRT vermeiden).

7. **`format-conversion-of`-Detection** Stufe 2 (siehe entsprechender
   Backlog): nutzt `/Producer` und `/Creator` aus den jetzt
   verfuegbaren Spalten.

User-Quote (2026-04-27): *"Da sind ja viele wichtige Daten dabei,
die wir gleich bei der registrierung mit extrahieren koennten.
Die sollten dann auch verfuegbar sein."*


## Cost-Tracking: Chat + Monatliche Gesamtsicht (Prioritaet: hoch)

**Heutiger Stand (2026-04-27, system.db Stichprobe):**

- `chat_messages` hat bereits `tokens_input`, `tokens_output`,
  `token_count`-Spalten — **aber keine `cost_eur`-Spalte**.
- Nur **737 von 2026 Rows** (~36 %) haben Token-Counts erfasst —
  Erfassung greift offenbar nicht zuverlaessig.
- Aggregat ueber das was da ist: **72 Mio Input-Tokens**, **485k
  Output-Tokens** ueber den Lebenszyklus aller Disco-Chats.
- Bei GPT-5.1-Listpreisen ($2.50/$1.25/$10 pro 1M Input/cached/output)
  und USD_TO_EUR=0.92: Lifetime-Chat-Kosten **ca. 140-170 EUR**
  (je nach cache-hit-Rate).
- `cached_tokens` wird heute gar nicht erfasst — Foundry-Cache spart
  ~50 % auf Input, das geht in der Kostenrechnung verloren.

**Bestehende Cost-Erfassung (bereits da):**

- `agent_doc_markdown.estimated_cost_eur` (pro extrahiertes File via
  GPT-5.1 Vision).
- `agent_flow_runs.total_cost_eur` (pro Flow-Run aggregiert).
- `disco/pricing.py` zentral mit `FOUNDRY_PRICING`-Dict.

**Was fehlt:**

1. **Chat-Kosten pro Message erfassen** — Token-Counts zuverlaessig,
   plus `cached_tokens`, plus berechneter `cost_eur`.
2. **Azure-DI-Kosten erfassen** — DI hat heute keine zentrale
   Cost-Spur. PDFs werden via `pdf-azure-di`/`pdf-azure-di-hr`
   verarbeitet und Disco hat Listpreise (ca. $1.50 pro 1000 Pages
   Standard, $5 pro 1000 Pages HighRes), aber nicht in der Pipeline
   erfasst.
3. **Monatliche Aggregat-Sicht** ueber alle Quellen.

### User-Anforderungen (2026-04-27)

> "Ich moechte auch die Disco-agent chat-kosten erfassen. Dann
> moechte ich die montlichen gesamtkosten fuer gpt5 und DI sehen
> koennen."

### 1. Chat-Kosten erfassen

**DB-Schema** (system.db Migration):

```sql
ALTER TABLE chat_messages ADD COLUMN cached_tokens INTEGER;
ALTER TABLE chat_messages ADD COLUMN model_deployment TEXT;
ALTER TABLE chat_messages ADD COLUMN cost_eur REAL;
```

**Code-Hook** in `disco/agent/core.py`-AgentService:
- Bei jedem OpenAI/Foundry-Response: extract_token_usage (existiert
  bereits in pricing.py) → schreibe alle 4 Token-Felder.
- Berechne cost_eur via `get_foundry_price(deployment).cost_eur(...)`.
- Default-Deployment "gpt-5.1" wenn nicht aus Response extrahierbar.

**Bug fixen**: warum sind heute nur 36 % der Messages mit
Token-Counts erfasst? Vermutlich werden Streaming-Responses oder
Tool-Result-Messages nicht durchlaufen. Ursache identifizieren
und fixen, sonst ist die ganze Statistik schief.

### 2. Azure-DI-Kosten erfassen

`disco/docs/pdf.py` (Azure-DI-Engine) ergaenzt das Result-Dict um
`estimated_cost_eur` analog zu image.py:

```python
DI_PRICE_PER_1K_PAGES = {
    'pdf-azure-di':    1.50 * USD_TO_EUR,    # USD-listpreis * EUR
    'pdf-azure-di-hr': 5.00 * USD_TO_EUR,    # HighRes ist ~3x teurer
}
cost_eur = round(n_pages / 1000 * DI_PRICE_PER_1K_PAGES[engine], 6)
```

DI-Listpreise sollten in `disco/pricing.py` zentralisiert werden,
analog zu `FOUNDRY_PRICING`. Quelle-Hinweis (regelmaessig pruefen):
https://azure.microsoft.com/de-de/pricing/details/ai-document-intelligence/

### 3. Monatliche Gesamt-Sicht

**SQL-View** (oder Materialized Table fuer Performance):

```sql
CREATE VIEW v_cost_by_month AS
-- Chat-Kosten aus system.db
SELECT
  strftime('%Y-%m', created_at) AS month,
  COALESCE(model_deployment, 'gpt-5.1') AS service,
  'chat' AS category,
  SUM(cost_eur) AS cost_eur,
  COUNT(*) AS n_calls
FROM chat_messages
WHERE cost_eur IS NOT NULL
GROUP BY 1, 2
UNION ALL
-- Extraction-Kosten aus jeder Projekt-DB (UNION ALL ueber alle Projekte)
-- ... pro Projekt: agent_doc_markdown.estimated_cost_eur
-- aggregiert nach engine + month;
```

Die Cross-Database-Aggregation ist tricky (system.db fuer Chats,
projektspezifische datastore.dbs fuer Extraction). Loesungs-Optionen:

a) **Aggregator-Skript** `disco cost-report --month 2026-04` das
   alle Projekt-DBs durchgeht und ein Aggregat in
   `system.db.cost_aggregates` schreibt.

b) **Rolling-Sync**: bei jedem Flow-Run-Abschluss schreibt der
   `total_cost_eur` zentral in `system.db.cost_aggregates`
   (denormalisiert, schneller fuer Reporting).

c) **Federated SQL**: SQLite kann via `ATTACH DATABASE` mehrere
   DBs joinen. Ein Reporting-Tool koennte alle Projekt-DBs
   attachen und live aggregieren. Kompliziert.

Pragmatisch: **(a)** als CLI-Befehl + spaeter UI-Endpoint der
das Aggregat lebt.

### UI-Vorschlag

Neuer Settings-Pane-Tab "Kosten" in der Web-UI:

- **Chart 1**: Stacked-Bar pro Monat, gestapelt nach service
  (gpt-5.1 chat, gpt-5.1 vision, pdf-azure-di, pdf-azure-di-hr)
- **Tabelle**: Detail pro Monat × Service × n_calls × cost_eur
- **Filter**: nach Projekt einschraenkbar
- **Aktueller Monat** prominent oben: "April 2026: 23.45 EUR (47 Chats, 1517 PDFs)"
- **Lifetime-Total** als Summe

### Implementierungs-Reihenfolge

1. **system.db-Migration**: cached_tokens, model_deployment, cost_eur
   in chat_messages
2. **Bug-Fix**: warum nur 36 % der Messages Tokens haben (in
   AgentService nachschauen)
3. **DI-Cost-Tracking** in pdf.py + zentral in pricing.py
4. **Aggregator-CLI**: `disco cost-report --month YYYY-MM`
5. **UI-Tab "Kosten"** mit Chart + Tabelle (Phase 2)

### Cost-Quellen — Vollstaendigkeitscheck

Damit nichts vergessen wird:

| Quelle | Status heute | Was fehlt |
|---|---|---|
| Disco-Chat (GPT-5.1 + Tools) | Token teilweise | cost_eur, cached_tokens, 64% Messages ohne Token |
| Image-Extraction (GPT-5.1 Vision) | cost_eur in agent_doc_markdown | nichts (gut!) |
| PDF-Extraction (Azure-DI Standard + HR) | nichts | cost_eur in agent_doc_markdown + zentrale Preise |
| Excel-Extraction (openpyxl) | n/a (kostenlos) | n/a |
| DWG-Extraction (libredwg + ezdxf) | n/a (kostenlos) | n/a |
| Embeddings (Phase 2c) | nicht da | parallel mitdenken bei Implementation |

User-Quote (2026-04-27): *"Ich moechte auch die Disco-agent chat-
kosten erfassen. Dann moechte ich die montlichen gesamtkosten
fuer gpt5 und DI sehen koennen."*

Belastbare Schaetzung Lifetime-Chat-Kosten (heute aus 36%-Stichprobe
hochgerechnet): **ca. 140-170 EUR**. Real wahrscheinlich hoeher,
weil cached_tokens-Discount nicht korrekt eingerechnet ist.


## Data-Lineage / Tracing fuer abgeleitete Artefakte (Prioritaet: hoch)

**Idee 2026-04-27**: Jedes Artefakt, das Disco erzeugt — Tabellen,
Excel-Exports, Reports, Charts, Markdown-Zusammenfassungen — soll
fuer Disco selbst und den User **nachvollziehbar dokumentiert**
sein:

- **Wo kommen die Daten her?** (Source-Tabellen, Source-Files)
- **Mit welcher Abfrage / Logik wurden sie erzeugt?** (SQL, Python-
  Skript, ggf. Tool-Call-Sequenz)
- **Zu welchem Zweck?** (Business-Begruendung in einem Satz)

Heute hat Disco kein zentrales Lineage-Register. Eine Tabelle
`work_canonical_report` existiert, aber niemand weiss aus dem Stand
heraus: wann wurde die erstellt, mit welchem SQL, welche Sources?
Disco wuerde das Skript suchen muessen oder im Chat-History
zurueckscrollen — beides fragil.

### User-Anforderung (2026-04-27)

> "Wir bauen ein Data-tracing auf. D.h. fuer jede Tabelle, bericht
> etc die erstellt werden, soll fuer disco nachvollziehbar dokumentiert
> werden wo die daten her kommen, mit welcher Abfrage die Daten zu
> welchem Zweck erzeugt wurden."

### DB-Schema-Vorschlag

Neue Tabelle in workspace.db:

```sql
CREATE TABLE agent_data_lineage (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_type   TEXT NOT NULL,    -- 'table' | 'export' | 'report' | 'chart' | 'markdown'
    artifact_name   TEXT NOT NULL,    -- 'work_canonical_report' | 'exports/Soll-Ist-2026.xlsx'
    artifact_db     TEXT,             -- 'workspace.db' | 'datastore.db' | 'fs'
    purpose         TEXT NOT NULL,    -- 1-2 Saetze, vom Erzeuger geschrieben
    sources_json    TEXT,             -- JSON-Array: [{"type":"table","name":"agent_sources"},
                                      --              {"type":"file","path":"context/vgb-s831.pdf"}]
    query_sql       TEXT,             -- ausgefuehrtes SQL (NULL fuer Python-only-Artefakte)
    code_snippet    TEXT,             -- Python-Code-Snippet wenn nicht via SQL
    n_rows          INTEGER,          -- Result-Groesse
    schema_json     TEXT,             -- Spalten der Result-Tabelle als JSON
    created_by      TEXT,             -- 'disco-agent' | 'flow:extraction:run-12' | 'user'
    chat_message_id INTEGER,          -- optional: Link zur Chat-Nachricht
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(artifact_type, artifact_name)  -- pro Artefakt der LETZTE Erzeugungs-Eintrag
);
CREATE INDEX idx_lineage_artifact ON agent_data_lineage(artifact_type, artifact_name);
CREATE INDEX idx_lineage_created  ON agent_data_lineage(created_at);
```

UNIQUE-Constraint auf `(artifact_type, artifact_name)`: pro
Artefakt **eine** Zeile, die bei Re-Erzeugung via UPSERT
ueberschrieben wird. Fuer Historie waere eine `agent_data_lineage_history`
denkbar — Phase 2.

### Wer schreibt — Hook-Punkte

1. **`sqlite_write`** (Disco-Tool fuer DDL/DML): bei `CREATE TABLE`,
   `CREATE TABLE AS SELECT`, `INSERT INTO ... SELECT` automatisch
   einen Lineage-Eintrag schreiben. Sources werden aus dem
   geparsten SQL extrahiert (FROM-/JOIN-Tabellen). Purpose muss
   als Pflichtparameter mitgegeben werden ("Warum schreibst du
   diese Tabelle?").

2. **`build_xlsx_from_tables`** (Excel-Export): bei jedem Export
   einen Eintrag mit den Source-Tabellen, ausgefuehrtem
   Multi-Sheet-Spec und Purpose.

3. **`import_xlsx_to_table` / `import_csv_to_table`**: Eintrag
   mit Source-File-Pfad, Schema, Row-Count.

4. **`run_python`**: bei DB-Schreibungen aus dem Skript heraus —
   das Skript muss per Helper-Funktion `disco.lineage.record(...)`
   einen Eintrag schreiben. Konvention im python-executor-Skill
   verankert.

5. **Flows** (z.B. extraction): pro Run einen Eintrag fuer das
   produzierte agent_doc_markdown-Subset. Kann via
   `chat_message_id`-Feld auch verknuepfen.

### Wie Disco das nutzt

**Neues Tool `data_lineage`**:

```python
@register
def data_lineage(artifact_type: str, artifact_name: str) -> dict:
    """Lineage einer Tabelle, eines Files oder Reports. Liefert:
    - purpose, sources, query_sql/code_snippet, n_rows, schema, created_by, created_at"""
```

Bei Disco-Tool-Aufrufen wie `sqlite_query` auf einer fremden
Tabelle, koennte der Tool-Wrapper optional eine
"Lineage-Hint"-Section anhaengen ("Diese Tabelle wurde erzeugt am
... aus ... mit dem Zweck ..."), wenn das die Antwort verbessert.

System-Prompt-Erweiterung: in der Agent-Instruktion eine kurze
Regel "Wenn Du Tabellen anlegst (sqlite_write CREATE TABLE),
schreibe einen Lineage-Eintrag mit klarem Purpose".

### Use-Cases

1. **Re-Run einer Auswertung**: User fragt "kannst du den
   SOLL/IST-Report nochmal erstellen, aber gefiltert auf
   Bautechnik?". Disco liest Lineage von
   `work_canonical_report`, sieht das Original-SQL, modifiziert
   es um den Filter, fuehrt aus.
2. **Audit / Impact-Analyse**: User aendert eine Source-Tabelle.
   `data_lineage` rueckwaerts fuehrt: "welche Reports basieren
   auf agent_doc_markdown?" → 5 Tabellen + 3 Excel-Exports
   muessten neu generiert werden.
3. **Disco-Debugging**: "warum sind in dieser Tabelle nur 47
   Rows obwohl in der Quelle 1500 sind?" → Lineage zeigt das
   SQL → "ah, da war ein WHERE date > 2024 drin".
4. **Cross-Session-Continuity**: Disco kommt nach Pause zurueck
   und sieht eine `work_*`-Tabelle, die er nicht mehr im
   Kontext hat. Ueber Lineage versteht er, was sie ist und
   wofuer.

### Implementierungs-Reihenfolge

1. **Migration** workspace/006_data_lineage (oder naechste Nummer):
   Tabelle anlegen.
2. **Helper-Modul** `disco/lineage.py` mit `record(...)`-Funktion.
3. **Hook in `sqlite_write`**: parsst SQL, ruft `record(...)`. Pflicht-
   Parameter `purpose` hinzufuegen — Disco muss begruenden was er
   schreibt. Bei fehlendem Purpose: Fehler.
4. **Hook in `build_xlsx_from_tables`**, **import-Tools**: dito mit
   Pflicht-Parameter `purpose`.
5. **Tool `data_lineage`** registrieren.
6. **System-Prompt**: kurze Regel hinzufuegen "Lineage dokumentieren".
7. **UI**: Tabelle anklicken im Sidebar → Lineage-Panel mit
   Purpose, Sources, SQL, Created.

### Verbindungen zu anderen Backlog-Eintraegen

- **File-Internal-Metadata**: das ist eingebettete Source-File-
  Provenance (woher kommt das Original?). Lineage hier ist
  abgeleitete Artefakt-Provenance (was wurde DARAUS gemacht?).
  Beide ergaenzen sich.
- **Pipeline-UX (pipeline_state)**: Lineage ergaenzt das fuer
  abgeleitete Daten — pipeline_state ist pro Source, Lineage
  ist pro abgeleitetem Artefakt.
- **Cost-Tracking**: Lineage-Eintrag koennte ein `cost_eur`-Feld
  haben → "diese Tabelle hat 0.34 EUR gekostet zu erzeugen".
- **Relevance-Score**: Tabellen mit vielen Konsumenten (Lineage-
  Inverse-Lookup) sind relevanter.
- **Public-Workspace**: bei Cross-Projekt-Reuse von Tools/Skripten
  kann Lineage zeigen "dieses Skript hat in Projekt X eine Tabelle
  Y erzeugt — gleiche Logik anwendbar?".

User-Quote (2026-04-27): *"Wir bauen ein Data-tracing auf. D.h.
fuer jede Tabelle, bericht etc die erstellt werden, soll fuer
disco nachvollziehbar dokumentiert werden wo die daten her
kommen, mit welcher Abfrage die Daten zu welchem Zweck erzeugt
wurden."*


## User-Feedback-Cluster aus 24 bad-Reactions (Prioritaet: hoch)

**Quelle**: `chat_message_feedback`-Tabelle in system.db. Zeitraum
22.04.–27.04.2026. **24 bad** + 7 good Reactions, davon 23 mit
Kommentar. Direkter, validierter User-Pain — nicht spekulativ.

13 Themen-Cluster, einige bestaetigen bereits geplante Backlog-
Eintraege, andere sind neu.

---

### Cluster A — Foundry-/Stream-Fehler unverstaendlich (4 Reactions)

**Quotes:**
- *"Der Fehler kommt an und an. Weiß nicht was das sein soll: 'Founrdy melde Fehle keien Details von Foundry'"* (msg 1105)
- *"Fehler ohne Angabe weiter unten"* (msg 1115)
- *"Wieder foundry fehler"* (msg 1296)
- *"Fehler: input exceed the context window. Obwohl oben steht dass context window sei nur zu 13k tokens gefüllt. Da stimmt was nicht"* (msg 1202)

**Verbesserung:**
1. **Error-Messages strukturiert**: bei Foundry-Errors HTTP-Status,
   Response-Body und ggf. Tool-Call-Snapshot in einer Block-Struktur
   anzeigen (heute oft kryptische String-Konkat).
2. **Context-Window-Anzeige korrigieren**: die Anzeige (oben rechts
   `153k / 200k · 76 %`) stimmt nicht mit dem tatsaechlichen
   Foundry-Limit ueberein — vermutlich werden Tool-Definitions/Skills
   beim Token-Count nicht eingerechnet. **Bug**: bei context_length-
   exceeded sieht User "13k benutzt", die Realitaet ist deutlich
   mehr.
3. **Error-Klassifikation**: transient (retry-bar), permanent
   (Code-Bug), Quota (config-Issue) als drei sichtbare Klassen, mit
   passendem Vorschlag was zu tun ist.

---

### Cluster B — Flow-Bedienung schwer (4 Reactions)

**Quotes:**
- *"Disco kann die pdf flows nicht starten. Was ist da los?"* (msg 1286)
- *"Ich kann mit den flows nicht arbeiten und sie nutzten. Hier brauchen wir noch eine lösung"* (msg 1293)
- *"Möchte den flow individueller bestücken und laufen lassen können"* (msg 1440)
- *"BUG! Der Flow muss laufen"* (msg 1792)

**Verbesserung:**
1. **Flow-Lifecycle-Klarheit**: User sagt "starte Flow X", Disco
   bestaetigt Start mit Run-ID + erwartetem Verlauf. Heute oft
   uneindeutig ob ein Run wirklich laeuft oder nur als geplant in
   der DB steht.
2. **Flow-Parametrisierung im Chat**: "starte Flow X mit limit=10
   und only_kind=pdf" muss zuverlaessig vom Foundry-Agent verstanden
   und als config_json an den Runner uebergeben werden.
3. **Flow-Pre-Check**: vor Run-Start zeigt Disco die geplante
   Run-Konfig (Items-Anzahl, Kosten-Schaetzung, Engines) und der
   User bestaetigt — verhindert ungewollte 200-EUR-Runs.

Bezug: passt mit "Extraction-Pipeline-UX" und "Disco-Prozess-
Management"-Eintraegen zusammen.

---

### Cluster C — Stille falsche Annahmen, falsche Resultate (2 Reactions)

**Quotes:**
- *"Disco konnte bestimmte dateien nicht finden, obwohl sie da waren. Das ist fatal und müssen wir vermeiden."* (msg 1474)
- *"Bei sowas müssen wir sauber arbeiten. Solche fehler führen am Ende zu komplett falschen auswertungen denke ich"* (msg 1831)

**Verbesserung:**
1. **Sanity-Checks bei Diff-Aussagen**: wenn Disco sagt "X nicht
   gefunden", muss er vorher mindestens 2 Such-Strategien probiert
   haben (z.B. Path-Match + Filename-Match + Hash-Match) und das
   Ergebnis in der Antwort transparent machen ("ich habe via X, Y, Z
   gesucht, alle 3 leer").
2. **"Done"/"Abgeschlossen"-Aussagen sind teurer als "Versuch":**
   Skill-/Prompt-Regel ergaenzen: bevor Disco ein Ergebnis als
   final reportet, muss er die Datenquelle der Wahrheit
   (`agent_doc_markdown`-Counts, FS-Match) zitieren — nicht nur
   einen Zaehler aus einer abgeleiteten Tabelle.

---

### Cluster D — Unicode-Normalisierung in Queries (1 Reaction, konzeptionell)

**Quote:**
- *"Disco findet den fehler. Unterschiedliche unicodes. Das haben wir noch gar nicht betrachtet. Sollten wir konzeptionel drauf hinweisen, damit die queries funktionieren."* (msg 1477)

**Verbesserung:**
1. **NFC-Normalisierung als Standard** in den SQL-Helper-Funktionen
   bei String-Vergleichen — z.B. `WHERE rel_path = ?` mit `?`
   vor-NFC-normalisiert. Aufgrund OS X (Filesystem nutzt NFD) vs.
   Excel/SharePoint (oft NFC) kommt es zu unsichtbaren Mismatches.
2. **System-Prompt / Skill-Hinweis**: bei String-Joins zwischen
   Filesystem und User-Input immer NFC-normalisieren (oder
   `unicodedata.normalize` im Python-Vergleich).
3. **SQL-Helper `WHERE rel_path = NORMALIZE_NFC(?)`** als gemeinsame
   Wrapper-Funktion in den disco-Tools.

---

### Cluster E — Reasoning-Failures: Disco macht etwas anderes als gefragt (3 Reactions)

**Quotes:**
- *"Jetzt hätte disco es eigentlich hin bekommen müssen"* (msg 1492)
- *"Was ist denn hier passiert? Er wollte mir doch ein flow bauen jetzt hat er doch einfach die tabelle geändert?"* (msg 2092)
- *"Was soll das? DAs ist doch wohl klar, dass disco hier die tabelle ausfüllen sollte"* (msg 2273)

**Verbesserung:**
1. **Plan-Bestaetigung vor Aktion bei "fett"-Aufgaben**: bei
   Aufgaben mit > 1 Tool-Call oder > 1 Min Laufzeit zeigt Disco
   einen Plan ("ich werde A, B, C tun in dieser Reihenfolge")
   und wartet auf User-OK, bevor er ausfuehrt. Heute springt er
   manchmal direkt los, dann passt's nicht.
2. **Strategy-Switch sichtbar machen**: wenn Disco zwischen "Flow
   bauen" und "Tabelle direkt aendern" wechselt, muss er die
   Aenderung explizit ankuendigen ("ich aendere meinen Plan auf
   X, weil Y").
3. **System-Prompt Triggertabelle erweitern** — User hatte schon
   konkrete Regeln gegeben (Memory-Eintrag "imperativ statt soft"),
   aber bei komplexeren Aufgaben fehlt's noch.

---

### Cluster F — Context-File-Behandlung (3 Reactions, eng verzahnt)

**Quotes:**
- *"Information zu spezifischen Dateien sollten wir gleich an den Dateien speichern. Context files: kurz sagen was das für eine datei ist wo die her kommt und was wir damit machen wollen. Sollte sich zuverlässig gemerkt werden"* (msg 1620)
- *"Bug: die context dateien wollen wir ja genau so registrieren und einlesen."* (msg 1668)
- *"Disco fängt an links zu verwenden, das ist gut und genau da will ich auch hin - nur funktioniert dieser noch nicht."* (msg 1601)

**Verbesserung:**
1. **Context-Files in agent_sources registrieren** mit `kind='context'`
   (heute teilweise: 88 Rows in lager-halle als context). Voll
   gleichberechtigt zu sources: Hash, Metadaten, Pipeline-State.
2. **File-Notes-Tabelle** `agent_source_notes` (oder Spalten in
   agent_sources):
   ```sql
   purpose      TEXT  -- "Norm fuer SOLL/IST-Abgleich"
   origin       TEXT  -- "vom GU geliefert 2026-04-15"
   usage_intent TEXT  -- "Nachschlagewerk bei Klassifikation"
   ```
   Beim context-Onboarding-Skill werden diese 3 Felder ad-hoc gefragt.
   Persistent in der DB statt im Memory-Markdown.
3. **Hyperlink-Fix in Excel-Exports**: SharePoint-Pfad-Konvention
   sauber implementieren in `build_xlsx_from_tables`. User beobachtet:
   Disco verlinkt, Pfade funktionieren aber nicht im Excel.

Bezug: ergaenzt File-Internal-Metadata-Eintrag (eingebettete Metadaten)
um User-erstellte File-Annotations.

---

### Cluster G — Pipeline-Disziplin (3 Reactions) — *bereits im Backlog*

**Quotes:**
- *"Reihenfolge: Registrieren → Duplikate erkennen → nur mit kanonischen → Routing → Extraction"* (msg 1708)
- *"Extraction immer nur auf kanonischen Dateien durchführen. Das müssen wir klären."* (msg 2068)
- *"Status hängt nicht am echten process und wird von disco fehlinterpretiert."* (msg 2098)

**Status:** abgedeckt durch:
- "Extraction nur auf kanonische Dateien" (BL)
- "Extraction-Pipeline-UX: Ampelsystem, Auto-Pipeline" (BL)
- "Stabilitaets-Bugs aus FTS5-Deadlock" Section "Counter-Update-Bug"

→ Hier nur **Bestaetigung**, kein neuer Eintrag noetig.

---

### Cluster H — Failed-Files markieren — *bereits im Backlog*

**Quote:**
- *"Vielleicht sollten wir in die md der datei schreiben lassen, wenn die extraction failed? Dann versuchen wir die nicht immer wieder und sehen die auch nicht dauerhaft als Diff"* (msg 2071)

**Status:** abgedeckt durch "Extraction-Pipeline-UX" Section 4
("Retry-Strategie und Permanent-Fail-Markierung"). Bestaetigt.

---

### Cluster I — Flow-Abbruch bei wegfallender Bedingung (1 Reaction)

**Quote:**
- *"Dann soll Disco den Flow auch abbrechen. Das wäre ein valider grund gewesen."* (msg 2079)

**Verbesserung:**
1. **Flow-Selbstdiagnose**: bei Run-Start prueft der Runner, ob
   die Items noch mit der Routing-Tabelle uebereinstimmen. Wenn
   z.B. waehrend `extraction_routing_decision` lief, parallel der
   sources-Set sich geaendert hat (oder die Routing-Tabelle leer
   ist) → Run sofort als `aborted_invalid_state` beenden mit klarer
   Begruendung.
2. **Disco soll selbst Flow-Cancel nutzen koennen** wenn er
   mid-Run merkt, dass die Bedingung weggefallen ist (ohne dass
   der User es explizit anstoesst).

---

### Cluster J — PDF-Fokus statt alle Dateiformate (1 Reaction)

**Quote:**
- *"Wir haben irgendwo noch ein PDF Fokus drin. Wenn ich nach Dateien frage möchte ich ja eine Aussage über alle Dateiformate im Projekt haben und nicht nur über PDF"* (msg 2022)

**Verbesserung:**
1. **Tool-/Skill-Audit**: alle Stellen finden, wo "PDF"
   hardcoded ist (z.B. `agent_pdf_inventory` heisst noch so,
   `pdf_classify`-Tool). Auf "file" oder "doc" generalisieren
   wo sinnvoll. Bestand: agent_pdf_inventory (noch da, wird vom
   Such-Index nicht mehr genutzt).
2. **Skill-Sprache anpassen**: in disco/system_prompt.md /
   Skills, wenn von "Dokumenten" gesprochen wird, soll die
   Antwort alle file_kinds umfassen. Default "Dateien" =
   alles, nicht nur PDFs.
3. **Cleanup veralteter Tabellen**: agent_pdf_inventory könnte
   entfernt werden, wenn nichts mehr darauf liest. Migration.

---

### Cluster K — Memory-Schreibung zuverlaessig (1 Reaction)

**Quote:**
- *"Trotz der deutlichen Aufforderung sich den Link zu merken, wurde nichts ins memory geschrieben. Dafür war eine zweite Aufforderung nötig."* (msg 2326)

**Verbesserung:**
1. **System-Prompt-Regel**: bei expliziten Memory-Aufforderungen
   ("merk dir das", "behalte im hinterkopf", "bitte ins memory")
   muss Disco SOFORT `project_notes_append` oder ein vergleichbares
   Tool aufrufen — nicht aufschieben.
2. **Bestaetigungs-Pattern**: Disco antwortet mit "✓ gemerkt" und
   zeigt den NOTES-Eintrag, statt nur zu sagen "ok".
3. **Trigger-Phrasen** in der bestehenden Triggertabelle des
   System-Prompts erweitern.

---

### Cluster L — SharePoint-Links / Excel-Hyperlinks (1 Reaction)

**Quote:**
- *"Disco fängt an links zu verwenden, das ist gut und genau da will ich auch hin - nur funktioniert dieser noch nicht."* (msg 1601)

**Verbesserung:**
1. **build_xlsx_from_tables**: Hyperlink-Spalten korrekt mit
   `=HYPERLINK("...","...")` formel-ifizieren statt nur Plain-Text.
2. **SharePoint-URL-Konvention**: aus `agent_sharepoint_docs.FileServerRelativeUrl`
   den vollen SharePoint-URL bauen (Tenant + Site + relative Url).
   Heute fehlt der Praefix ggf.
3. **URL-Encoding**: Umlaute und Spaces korrekt kodieren — Excel
   ist da pingelig.

---

### Cluster M — kleine Cluster und Einzelpunkte

- **msg 2092**: Disco wechselt zwischen "Flow bauen" und
  "Tabelle direkt aendern" ohne anzukuendigen — Doppel-Erwaehnung
  bei E (Reasoning) und I (Strategy-Switch).

---

### Implementierungs-Priorisierung

**Quick wins** (1-2h Aufwand, hoher User-Impact):
- Cluster K (Memory-Pflicht) — System-Prompt-Regel
- Cluster L (SharePoint-Hyperlinks) — bug-fix in build_xlsx
- Cluster D (Unicode NFC) — Helper-Funktion

**Mittel** (Tagesarbeit):
- Cluster A (Error-UX) — Foundry-Error-Wrapper
- Cluster F (Context-File-Notes) — Migration + Skill-Update
- Cluster I (Flow-Selbstdiagnose) — Runner-Hook

**Groß** (mehrere Tage, mit anderen Eintraegen verzahnt):
- Cluster B (Flow-Bedienung) — Teil von Pipeline-UX
- Cluster C (Sanity-Checks) — Skill/Prompt-Architektur
- Cluster E (Reasoning) — schwer, iterativ
- Cluster J (PDF-Fokus-Cleanup) — Audit-Aufgabe

User-Quote (2026-04-27): *"Schaue Dir die sachverhalte mal an
entwickle Verbesserungsvorschlaege und uebernehme ins BL. Also
noch nicht umsetzten."*
