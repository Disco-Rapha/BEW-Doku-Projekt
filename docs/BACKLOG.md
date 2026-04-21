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
   - Pro Seite ~0.01 €. Eine 800-Seiten-Norm = 8 €.
   - Risiko: User legt versehentlich 100 PDFs in context/ →
     Disco jagt alle durch DI → 500+ €
   - → Sicherheitsgrenze: max. N Seiten pro Context-Onboarding-Run
     (z.B. 500 Seiten), danach Rückfrage. Oder: max. N PDFs pro
     Run (z.B. 10), Rest manuell bestätigen.

3. **Pipelines (Zukunft):**
   - Pro Dokument ein LLM-Call = akkumulierte Kosten
   - → Kosten-Schätzung VOR dem Run, Budget-Limit WÄHREND des Runs

**Kurzfristig (jetzt):**
- Im `extract_pdf_to_markdown`-Tool: Warnung wenn PDF > 200 Seiten
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
2. **DI-Page-Limit:** PDF mit > 200 Seiten durch `extract_pdf_to_markdown`
   jagen — kommt die Warnung? Wird der Call trotzdem ausgeführt oder
   blockiert (aktuell: nur Warnung, keine Blockade).
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

**Was der Code aktuell tut** (`functions/docint.py`):

- `extract_pdf_to_markdown` liefert `estimated_cost_eur` im Tool-Result
  zurück (0.01 €/Seite für `prebuilt-layout`, 0.005 €/Seite sonst — hardcoded).
- Berechnung: `n_pages * cost_per_page`.

**Mögliche Gründe, warum der Nutzer nichts sieht:**

1. **UI rendert das Feld nicht prominent.** Tool-Result-Block zeigt JSON,
   aber `estimated_cost_eur` geht in der Masse unter. → im Tool-Call-Block
   (index.html) eigene Cost-Zeile / Badge, z.B. "≈ 0,12 € (12 Seiten)".
2. **Disco erwähnt Kosten nicht aktiv im Live-Kommentar.** System-Prompt
   hat keine Regel dazu. → Ergänzung: "Nach jedem DI-Call eine Zeile
   `≈ 0,XX € für N Seiten` in die Assistant-Message."
3. **Andere DI-Nutzungsstellen haben keine Kostenrückgabe.**
   z.B. Context-Onboarding, Flow-Worker, wenn sie DI direkt aufrufen
   statt über das Tool. → Einheitlicher Helper (`_di_cost(pages, model)`)
   und konsequente Propagation.
4. **Modell liefert `n_pages=0`.** Manche PDF-Varianten (gerenderte
   Bilder ohne Page-Metadaten) — dann ist Cost=0. → Fallback auf
   tatsächliche Seitenanzahl des Input-PDFs (pypdf).

**Test + Fix in einem Rutsch:**

1. Bekanntes PDF (z.B. 20 Seiten) durch `extract_pdf_to_markdown` jagen
2. Tool-Result prüfen — kommt `estimated_cost_eur` sauber an?
3. Assistant-Message prüfen — erwähnt Disco die Kosten?
4. UI-Block prüfen — steht die Zahl irgendwo sichtbar?

Danach die Lücken gezielt schließen.

### PDF-Extraktion: User wählt Engine selbst (Priorität: mittel)

Aktuell gibt es zwei Engines (`pdf_extract_text` = pypdf,
`extract_pdf_to_markdown` = Azure DI). Der User soll selbst wählen
können welche Engine pro Datei oder global genutzt wird.

**Geplante Engines (3+1):**

| Engine | Wo | Kosten | Qualität | Use-Case |
|---|---|---|---|---|
| **pypdf** | lokal | kostenlos | niedrig (kein OCR, keine Tabellen) | Quick-Check, Source-Bulk |
| **Azure DI Standard** | Azure EU | ~0.01 €/Seite | hoch (OCR, Tabellen, Struktur) | Context-PDFs (Default) |
| **Azure DI High-Res** | Azure EU | ~0.02+ €/Seite | sehr hoch (komplexe Layouts) | Schwierige Scans |
| **Lokale OSS-Engine** | lokal (GPU) | kostenlos | hoch (mit GPU) | Datenschutz-sensitiv, offline |

**Lokale OSS-Engine: MinerU** (https://opendatalab.github.io/MinerU/)
- Apache 2.0 Lizenz (+ zusätzliche Bedingungen)
- Unterstützt Apple Silicon GPU (MPS), CUDA, auch pure CPU
- OCR mit 109 Sprachen, Tabellen → HTML, Formeln → LaTeX
- Multi-Column, komplexe Layouts, Header/Footer-Entfernung
- Output: Markdown + JSON
- Lokal, offline, 0 €/Seite — ideal für Datenschutz + Bulk
- Installation: Python-Paket (`magic-pdf`), Modelle ~einige GB Download
- Qualitätsvergleich mit Azure DI: muss getestet werden
  (insbesondere technische Normen mit komplexen Tabellen)

**Benchmark-Ergebnis (10 diverse PDFs, 2026-04-17):**
- docling und DI High-Res liefern vergleichbare Qualität
- docling besser bei: Schaltplänen (+51%), Scans (+82%)
- DI besser bei: Formularen, Datenblättern, handschriftlichen Teilen
- Performance: docling 72s (10 PDFs, CPU-only), DI ~5-10s (Cloud)
- Kosten: docling 0 €, DI ~1 € für 10 PDFs (102 Seiten)

**Max-Quality-Durchlauf (images_scale=2.0, MPS, ACCURATE):**
- Gesamt 89s für 10 PDFs auf Mac Silicon
- **Schwäche bei technischen Zeichnungen:** Plankopf wird als
  Fließtext extrahiert, nicht als Tabelle. DI baut den Plankopf
  korrekt als Tabelle mit Nr/Blatt/Maßstab/Zeichner/Datum/Status.
  Für SOLL/IST-Abgleiche über Planköpfe bleibt DI unverzichtbar.
- docling ersetzt DI also NICHT, sondern ergänzt es für Bulk-Text
  und Scans.

**Architektur-Entscheidung:**
- Default-Engine wird **docling** (kostenlos, lokal, MIT-Lizenz)
- DI bleibt als Premium-Option (wenn User höchste Qualität bei
  Formularen braucht oder Apple Silicon zu langsam ist)
- pypdf bleibt für Quick-Checks (1 Seite, nur Text)

**Umsetzung:**
- `extract_pdf_to_markdown` bekommt einen Parameter `engine`:
  `"docling"` (Default), `"di-standard"`, `"di-highres"`, `"pypdf"`
- Im UI/CLI: Projekt-Setting für Default-Engine
- Im Skill: Engine-Empfehlung je nach Dateityp
- Kosten-Transparenz: pro Engine die geschätzten Kosten anzeigen
- docling mit GPU/MPS testen für weitere Beschleunigung

**ToDo — Docling produktiv verfuegbar machen** (aus UAT-Session 2026-04-19):
- Dependency ist bereits in `pyproject.toml` (`docling>=2.90.0`), aber
  **kein Produkt-Pfad nutzt sie aktuell** — nur ad-hoc Benchmark-Skripte
  in einem Testprojekt.
- **Option A (Tool):** neue Custom Function
  `markdown_extract_docling(pdf_path, engine_options)` in
  `src/bew/agent/functions/` — nutzt lokales docling, schreibt Markdown
  zurueck oder in Tabelle.
- **Option B (Skill/Flow):** Skill `markdown-extractor` mit Engine-Auswahl
  + generischer Flow `markdown-extract` der pro Item die gewaehlte Engine
  aufruft (docling/di-standard/di-highres/pypdf).
- Im UAT-Projekt `uat-2026-04-19` hat der User Flow 1 mit DI-HighRes gewaehlt
  (DI ist der erprobte Pfad), aber Docling soll als **gleichwertige Option**
  zur Verfuegung stehen — bewusste Entscheidung pro Projekt/Lauf.
- Nicht bloss installieren — auch **aufrufbar** vom Agent/Flow aus.

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
  - `md_extract_granite` / `md_extract_smol` / `md_extract_di` — die drei
    Engines als fertige Flows
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

Ursprung: UAT-Session 2026-04-20, waehrend Run #15 (md_extract_granite
auf uat-2026-04-19) lief und Disco parallel einen zweiten Flow
`md_extract_smol` gebaut hat — wurde deutlich, dass solche Arbeit
fuer jedes Projekt wiederholt wird, obwohl die Flows strukturell
identisch sind.

### Overnight-Betrieb + Resume nach Sleep/Restart (Priorität: hoch — aus UAT 2026-04-20)

Bulk-Flows (md_extract_granite, DCC-Klassifikation, etc.) laufen
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

### Hybride Markdown-Pipeline — DI ↔ VLM ↔ Standard (Priorität: hoch)

**Problem:** Granite-Docling-MLX läuft auf M1 zu langsam für produktive
Bulk-Extraktion (Run #15: 20 Dokumente in ~55 min, grosse PDFs zogen
einzeln 10-14 min). Selbst mit SmolDocling-MLX (schneller, weniger
Parameter) ist das kein Ersatz fuer 1000+-Dokument-Läufe.

Gleichzeitig sind die drei Engines **nicht austauschbar**:

| Engine | Kosten | Qualitaet | Durchlaufzeit | Ideal fuer |
|---|---|---|---|---|
| `standard` (DocLayNet + TableFormer) | 0 EUR | gut bei Text-PDFs, schwach bei Scans/Layout | schnell (CPU) | einfache Text-PDFs |
| `granite-mlx` / `smol-mlx` (VLM) | 0 EUR (lokal) | sehr gut bei komplexem Layout, Tabellen, schlechten Scans | sehr langsam (M1) | Einzelstuecke, wo Qualitaet zaehlt |
| Azure Document Intelligence | ~0.015 EUR/Seite | Profi-Qualitaet, Spaltenerkennung, Formeln, OCR | schnell (Cloud, parallel) | grosse Scan-Volumen, mehrspaltige Plaene |

**Idee: Hybrid-Router, der pro Dokument die passende Engine waehlt.**
Entscheidungskriterien (erste Skizze, noch nicht final):

- Seitenzahl < 3 + textbasiert (kein Scan) → `standard`
- Seitenzahl 3-20 + Layout komplex (Tabellen, Plaene) → `granite-mlx`
  oder DI je nach Zeitbudget
- Seitenzahl > 20 oder Scan-PDF → **Azure DI** (lokal zu langsam,
  Qualitaet bei Scans entscheidend)
- Handzeichnungen / stark gescannte Plaene → DI + custom prompt

Dafuer muss Disco pro Dokument erst **eine schnelle Inspektion**
machen (Seitenzahl, Text-vs-Scan-Heuristik, Dateigroesse, ggf. Thumbnail
der ersten Seite ueber VLM-Klassifikator) und dann die Engine routen.
Das ist selbst ein kleiner Flow.

**Offene Fragen:**
- Wer entscheidet? Fester Router (Regeln) vs LLM-Router (GPT-5 guckt
  1. Seite an und waehlt) — LLM-Router kostet Token, Regel-Router ist
  schneller und billiger, aber brittle.
- Kosten-Budget pro Run? z.B. „max 5 EUR DI-Kosten fuer den ganzen
  Projekt-Sync", und Router faellt dann auf Standard/VLM zurueck
- Qualitaets-Check nach der Extraktion — wenn das Markdown zu duenn
  ist (z.B. < 200 Zeichen fuer ein 10-Seiten-PDF), automatisch Engine
  hochstufen und neu versuchen (Retry-Ladder: standard → granite → DI)

**Wann angehen:** erst nach Auswertung Granite-Run #15 + Smol-Run.
Sobald wir belastbare Zahlen zu Qualitaet + Zeit pro Engine haben
(am gleichen Dokument-Set), kann man den Router sinnvoll designen.

Ursprung: UAT-Session 2026-04-20, nach Run #15 (Granite too slow).

---

## Architektur

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

*Letzte Aktualisierung: 2026-04-20*
