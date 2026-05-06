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

### Excel mit openpyxl auf Cowork-Niveau verwenden (DONE Routing-Teil 2026-05-05)

Disco hat `run_python` + openpyxl an Bord und kann damit alles, was
Claude Cowork mit Excel macht — Formatierung lesen, Farben/Fonts/
Borders setzen, Merged Cells, Formeln, Hyperlinks, Bilder. Die
Infrastruktur steht.

**Erledigt 2026-05-05:**
- ✅ Skill `excel-formatter.md` deckt jetzt Editor-Modus UND
  Custom-Generator-Modus ab (komplexer Report von Grund auf neu bauen).
- ✅ Trigger-Tabelle im System-Prompt: „schoene Excel", „aufwendig",
  „komplex", „Charts dazu", „Pivot", „Conditional Formatting",
  „individuell formatiert" → direkt `excel-formatter`, nicht erst
  `build_xlsx_from_tables`.
- ✅ Tool-Description von `build_xlsx_from_tables` listet explizit, was
  es NICHT kann + verweist auf den richtigen Pfad. Damit sieht der LLM
  die Grenze schon im Schema.

**Optional, nicht entschieden:** `xlsx_inspect_full` — Read-Tool, das
Styles/Merges/Formeln strukturiert als JSON liefert, damit Disco fuers
reine Anschauen nicht jedes Mal 15 Zeilen Python schreiben muss.

---

### build_xlsx_from_tables erweitern (Prioritaet: mittel — zurueckgestellt 2026-05-05)

Heute deckt das Tool nur den Standard-Look ab (Header-Style, Zebra,
AutoFilter, Status-Farben, Hyperlinks). Sobald der Nutzer mehr will
(Conditional Formatting, Number-Formats pro Spalte, Multi-Level-
Header, Cell Comments, gezielte Freeze-Pane-Position), greift Disco
korrekt zu `excel-formatter` + run_python — aber das kostet Tokens
und ist langsamer als ein Spec-Tool.

**Vorgeschlagene v2-Spec-Felder pro Sheet:**
- `number_formats` — `{column_key: "#,##0.00" | "0.00%" | "yyyy-mm-dd"}`
- `conditional_formatting` — Liste von Regeln pro Spalte (greater_than,
  contains, older_than_days etc. → fill/font_bold)
- `cell_comments` — `{column_key: "Tooltip"}` fuer Header oder Werte
- `freeze_pane` — explizit setzbar (Default A2)
- `multi_header` — zwei Header-Zeilen mit Spalten-Gruppen
- `widen_columns` / `fix_column_width` — Override gegen Auto-Breite

Bewusst NICHT in v2: Charts, Pivot-Tables. Die bleiben im
`excel-formatter`-Pfad (zu spezifisch fuer Spec-Tool).

**Status:** Entwurf steht. Wartet auf User-Praxis-Feedback nach den
Routing-Aenderungen — wenn der openpyxl-Pfad in der Praxis bequem
genug ist, koennen wir die Spec-Erweiterung evtl. ganz sparen.

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

## Pipeline-Vollstaendigkeits-Sicht — DONE 2026-05-04

Konsolidiert ins ★-EXTRACTION-PIPELINE-OVERHAUL (siehe unten).
Phase 1 (View + Sidebar-UI) live seit 2026-05-04, Phase-6-Schaerfung
(Maßstab pro Schritt + Schema-Bug + Unsupported-Klasse) live seit
2026-05-05/06.

## Flow-UI im Chat-Fenster — DONE 2026-04-25

Erledigt: Commits 829fd65 + 6200002 + 0e04dc9 + 77f71ea. Run-Strip
auffaelliger, finished-Runs bleiben mit Status-Badge, Klick auf
ganze Zeile oeffnet Run, schnelle Runs <3s via recent_finished-API.

---

## Office-Formate in die Extraction-Pipeline (Prioritaet: hoch)

Konsolidiert ins ★-EXTRACTION-PIPELINE-OVERHAUL Phase 2 (siehe unten).
DOCX/PPTX brauchen Engines (`python-docx`/`python-pptx`, MIT, lokal,
0 EUR). Heute fallen sie als `file_kind='other'` durchs Raster.

User-Quote (2026-04-25): *"Power Point, und Word Dateien haben wir
total vergessen :D Die muessen auch noch in die Pipeline."*

## Extraction nur auf kanonische Dateien — DONE 2026-05-05

Erledigt: `extraction_routing_decision/runner.py` filtert seit
Commit c9b6374 Files mit `duplicate-of`-Relation (from-Seite) aus
dem Input. Effekt rea-denox: 5790 → 1775 kanonische Routings.

`replaces` und `format-conversion-of` sind im Schema vorgesehen,
aber noch nicht gefuellt — bleibt als Phase-3 in ★-Konsolidat.

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

### Bug 1: gleicher Run wird doppelt angezeigt — **GEFIXT 2026-05-05** (Commit 15ee0c2)

Ursache: Field-Inkonsistenz zwischen `/api/workspace/active-runs`
(recent_finished mit `project_slug`) und `/api/workspace/projects/{slug}/runs/{id}`
(`project_slug=None`). Der Frontend-Dedup-Key ueber
`${project_slug}:${id}` matchte daher 'null:25' nicht mit
'bew-rsd-rea-denox:25' → derselbe Run landete zweimal im finished-Strip.

Behoben mit Backend-Fix (`api_run_status` faellt auf URL-Parameter
zurueck) + Frontend-Defensiv-Patch (`runStripFetchFinal` traegt Slug
aus prev nach).

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

## Cost-Tracking fuer GPT-5.1-Vision-Aufrufe — DONE 2026-05-06

Erledigt:
- Zentrales `disco/pricing.py` mit Sweden-Central-Data-Zone-Standard-
  EUR-Listpreisen (2026-05-06 von User gegen Microsoft-Pricing-Seite
  verifiziert).
- `disco/docs/image.py` rechnet seit Commit 7f33a8f mit echten
  Tokens × Tarif.
- `flows/sdk._extract_usage` extrahiert seit Commit dbbd725 auch
  `cached_tokens` aus der Foundry-Antwort und reicht sie an
  `compute_cost_eur` weiter — Cached-Input-Discount greift jetzt.
- gpt-5.1-Tarife auf User-Verifikation (1.18/0.12/9.41) korrigiert
  (Commit 84d68fe), gpt-5.4-prod aus Global-Tarif extrapoliert
  (2.36/0.24/14.10, Commit 25f1c3b).

Bestand-Korrektur: nicht durchgefuehrt (cached_tokens sind nicht
historisch persistiert). Neue Flow-Runs rechnen ab sofort korrekt.

User-Quote (2026-04-25): *"tracken wir eigentlich schon was uns der
gpt aufruf mit den bildern kostet im flow?"*

---

## Anhaltspunkte fuer `replaces` und `format-conversion-of` (Vertiefung)

Konsolidiert ins ★-EXTRACTION-PIPELINE-OVERHAUL Phase 3. Detail-
Patterns (Filename-Versions-Suffixe `_R0A`/`_R0B`, Pfad-Hinweise
`/archiv/`, PDF-Producer-Tag, Stem-Match ueber Extensions) bleiben
als Implementierungs-Vorlage erhalten — siehe Git-History dieser
Datei vor 2026-05-06.

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


## Extraction-Pipeline-UX: Ampelsystem, Auto-Pipeline, Batch-Mode — TEILWEISE DONE 2026-05-04/05/06

Konsolidiert ins ★-EXTRACTION-PIPELINE-OVERHAUL. Erledigt:
- ✅ Ampelsystem in Sidebar (Phase 1, Commits ab 2026-05-04)
- ✅ Schaerfung (Maßstab pro Schritt, Schema-Bug, Unsupported-Klasse,
  Routing-Filter auf Kanonik) — Commits c7287e7 + c9b6374, heutige
  Phase-2-Commits 4b086f7 + 67d5207 + 9fd053e
- Offen: Auto-Pipeline-Trigger nach `sources_register` (Disco fragt
  proaktiv), Batch-API-Engines, FS-Watcher (Phase 3)

User-Quote (2026-04-27): *"Die gesamte extraction pipeline von
registrierung bis hin zum fertigen suchindex funktioniert
grundsetzlich, ist aber grade extrem! muehsam."*


## File-Internal-Metadata bei Registrierung extrahieren — siehe ★-Konsolidat

Konsolidiert ins ★-EXTRACTION-PIPELINE-OVERHAUL Phase 2. Ungenutzter
Datenkanal: PDF/Excel/DWG/JPEG tragen Author, Creator-App, Custom-
Properties (KKS-Tags im DWG-Schriftfeld), EXIF-GPS — alles kostenlos
lokal lesbar, von Disco aktuell nicht ausgewertet.

User-Quote (2026-04-27): "PDFs, Excels und DWGs haben Metadaten, die
wir noch nicht nutzen — Autor, Custom-Properties, KKS-Tags. Lokal
gratis lesbar."

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


## Datenverarbeitung auf Ebene 3 strukturieren (Diskussion 2026-04-28)

**User-Beobachtung 2026-04-27 abends**: *"Ich brauche eine Loesung
wie man die Datenverarbeitung auf Ebene 3 organisiert. Nach einigen
Arbeits- und Analyseschritten wird die Datenhaltung chaotisch und
Disco verzettelt sich mit den Daten, berechtigterweise."*

**Diskussion am 2026-04-28** — dieser Eintrag bereitet die Optionen vor.

### Problem (live in lager-halle beobachtet)

Workspace.db enthaelt heute > 80 Tabellen, viele davon Disco-erzeugte
work_*-Varianten ohne erkennbares Lifecycle-Konzept:

```
work_canonical_report
work_canonical_rsd_report
work_canonical_sources
work_extraction_routing
work_extraction_routing_backup           ← Versions-Suffix
work_extraction_routing_noncanonical
work_pdf_canonical
work_duplicate_file_ids
work_all_sources_report
work_rsd_nicht_benoetigt
work_rsd_pruefung_betrieb
agent_sp_mek_doku
agent_sp_mek_norm
agent_sp_zueblin_enddoku
agent_sp_zueblin_norm
context_armatur_regel__armatur_b_reg     ← context-Excel-Imports
context_armatur_regel__armatur_f_reg     ← x60+ aus VGB S 811
... (60+ context_*-Tabellen)
```

**Konkrete Symptome:**

1. **Versions-Chaos**: `work_extraction_routing` + `_backup` +
   `_noncanonical` — welche ist aktuell? Welche darf weg?
2. **Variant-Sprawl**: fuer jede leichte Abwandlung einer Analyse
   eine neue Tabelle (`work_canonical_*` × 3, `work_rsd_*` × 2).
3. **Kein Lifecycle**: alte Tabellen aus Voruntersuchungen
   bleiben, niemand raeumt auf.
4. **Disco verliert Ueberblick**: bei naechstem Aufruf weiss er
   nicht sicher, welche der 80 Tabellen die aktuelle Wahrheit ist.
   Re-Berechnung haeufiger als Wiederverwendung.
5. **Mental-Load fuer User**: Sidebar (selbst nach Collapsible-Fix)
   zeigt eine Wand von Namen. Was wovon abgeleitet ist, sieht man
   nur, wenn man die Skripte aus dem Chat-Verlauf rekonstruiert.

### Loesungs-Dimensionen (Diskussions-Optionen)

#### A) **Workspace-Slugs als semantische Klammer**

User definiert ein Arbeits-Set explizit: *"wir arbeiten jetzt am
SOLL/IST-Vergleich VGB S 831"*. Disco haengt allen erzeugten
Tabellen einen Slug-Praefix an:

```
work_soll_ist__canonical_sources
work_soll_ist__match_results
work_soll_ist__report
```

Vorteile: visuelle Gruppierung, einfaches Cleanup ("loesche alle
work_soll_ist__*"), Sidebar zeigt natuerliche Sub-Gruppen.

Nachteile: Naming wird laenger; User muss "Workspace" als Konzept
verstehen.

#### B) **Stages innerhalb eines Workspaces** (input → working → output)

Im Workspace gibt es drei Phasen:
- **input/**: aus DB-Quellen abgeleitete Snapshots (read-once,
  unveraenderlich nach Import)
- **working/**: Analyse-Zwischentabellen (gilt als
  wegwerfbar, Disco darf neu erstellen)
- **output/**: bestaetigtes Endergebnis (geht in `agent_*`,
  bleibt persistent)

Naming: `work_<slug>__in__sources`, `work_<slug>__wk__joined`,
`agent_<slug>__out__report`.

Vorteile: klare Lebenszyklus-Erwartung pro Tabelle.

Nachteile: noch laengere Namen, Mehraufwand bei jeder Tabelle.

#### C) **Auto-Discovery vor Create**

Bevor Disco eine neue work_*-Tabelle erzeugt, ruft er ein neues
Tool `find_similar_tables(purpose)` auf, das in der Lineage-Tabelle
(siehe Backlog "Data-Lineage") nach Tabellen mit aehnlichem Purpose
sucht. Trefferliste mit kurzem Match-Score wird Disco vorgelegt:

```
- work_canonical_report (purpose: "Liste aller kanonischen
  Dateien fuer SOLL/IST", 1517 rows, 2 days old)
- work_canonical_sources (purpose: "Kanonische Sources mit
  Hash-Map", 1708 rows, 1 day old)
```

Disco entscheidet dann: wiederverwenden vs. neu erstellen.

Vorteile: senkt Variant-Sprawl massiv. Setzt Lineage-Backlog
voraus.

Nachteile: nur so gut wie die `purpose`-Beschreibungen.

#### D) **Cleanup-Skill / -Tool: "raeum auf"**

Neuer Skill `workspace-cleanup`:
1. Listet alle work_*-Tabellen mit Lineage (last_used_at,
   row_count, purpose).
2. Schlaegt vor, was weg kann (Stale-Detection: > N Tage nicht
   mehr referenziert).
3. User bestaetigt pro Cluster (oder global "alle stale weg").

Vorteile: explizit, transparent.

Nachteile: User muss daran denken zu starten.

#### E) **Auto-Stale-Detection + Markierung**

Tabelle die seit 7+ Tagen nicht mehr in Lineage als Source referenziert
wurde UND nicht selbst Sources hat, die sich geaendert haben → automatisch
als `stale=1` in der Lineage markiert. UI zeigt sie ausgegraut. Nach 14
Tagen `stale=1` → Auto-Drop (mit Audit-Trail).

Vorteile: passiv, keine User-Interaktion noetig.

Nachteile: Risiko von Daten-Loss wenn Lineage unvollstaendig.

#### F) **TTL beim Create (opt-in)**

Disco-Tool `sqlite_write` bekommt optionalen Parameter
`expires_in_days=7`. Nach Ablauf wird die Tabelle automatisch
gedroppt. Gut fuer offensichtlich-temporaere Tabellen
(Test-Auswertungen, Daten-Exploration).

Vorteile: simple, opt-in, kein Mental-Load fuer Nicht-temp-Faelle.

Nachteile: User/Disco muss daran denken den Parameter zu setzen.

#### G) **UI-Hilfen** (siehe Sidebar-Backlog)

- Filter-Feld ueber der Tabellen-Liste
- Sortierung nach last_used_at
- Sub-Gruppierung an `__`-Separator (passt mit A zusammen)
- Lineage-Panel beim Anklicken einer Tabelle

#### H) **Output-Zone strikt trennen**

Konvention: bestaetigte Reports/Endergebnisse landen in `agent_*`
oder in `exports/` als File. work_* darf jederzeit weg, der User
und Disco verlassen sich darauf nicht. Disco-System-Prompt-Regel:
"work_* ist Wegwerf-Zone. Persistente Outputs gehen nach agent_*
oder exports/".

Vorteile: klare semantische Trennung, einfacher Cleanup.

Nachteile: Disziplin-Frage; muss in Skills/Prompts verankert sein.

### Querverweise zu existierenden Backlog-Eintraegen

- **Data-Lineage** ist die **Voraussetzung** fuer C, D, E (alle
  brauchen ein purpose-Feld und last_used_at).
- **Sidebar-Navigation** profitiert von A (Slug-Sub-Groups) und
  G (Filter-Feld).
- **File-Internal-Metadata** ist Quell-Provenance, hier ist's
  Ableitungs-Provenance — beides zusammen = vollstaendiges
  Datenbild.
- **Pipeline-UX** (pipeline_state) ist die Quell-Datei-Sicht;
  hier ist die Werkstatt-Daten-Sicht.

### Mein Strawman-Vorschlag fuer das Gespraech

Stufenplan, Aufwand niedrig zu hoch:

1. **Quick win — Output-Zone-Konvention (H) klarstellen**
   im System-Prompt: 1h Aufwand. Sofort wirksam fuer neue
   Tabellen.
2. **Lineage-Tabelle einfuehren** (separater BL-Eintrag,
   Voraussetzung fuer alles weitere): 3-5h.
3. **Workspace-Slug-Konzept (A)** als Ordnungsprinzip etablieren:
   in Skills/Prompts verankert, kein Code-Change noetig. 2-3h.
4. **Cleanup-Skill (D)** auf Lineage-Basis: 4-6h.
5. **Auto-Stale (E) + UI-Hilfen (G)** in einem Schwung: 1 Tag.

B (Stages), C (Auto-Discovery), F (TTL) sind eher Optional-
Features fuer eine zweite Iteration, wenn 1-5 nicht ausreichen.

### Offene Fragen fuer das Gespraech

- Wie klar wollen wir das semantische Modell machen? Hart
  durchgesetzt (Schema-Constraint) vs. Konvention im Skill?
- Wie viele Workspace-Slugs koexistieren typisch — einer
  pro Projekt-Aufgabe? Oder ein "default"-Slug + Sonder-Slugs?
- Was passiert bei Mehrfach-Konsumenten einer Tabelle (Soll
  ein gemeinsamer Output mehrere Slugs haben?).
- Soll der User Slugs explizit ankuendigen *("wir wechseln
  jetzt auf Aufgabe X")* oder soll Disco sie selbst aus dem
  Gespraech ableiten?
- Wo zeichnen wir die Linie zwischen `work_*` (Wegwerf) und
  `agent_*` (persistent)? Heute fliesst manches `work_*`
  faktisch persistent ein.

User-Quote (2026-04-27): *"Ich brauche eine Loesung wie man die
Datenverarbeitung auf Ebene 3 organisiert. Nach einigen Arbeits-
und Analyseschritten wird die Datenhaltung chaotisch und Disco
verzettelt sich mit den Daten, berechtigterweise."*


## Klickbare Links + bewusste Thumbnails im Chat — TEILWEISE DONE 2026-05-04

Erledigt:
- ✅ Phase 1: `disco-file://` und `disco-table://` als Custom-URL-
  Schemas im Frontend, Click-Handler oeffnet Viewer/Tabelle
  (Commit fd99728).

Offen Phase 2:
- ❌ `disco-preview://`-Thumbnails im Chat. Backend-Endpoint
  `/api/projects/{slug}/thumbnail?path=...&page=1` mit PDF-Rendern
  via PyMuPDF, Cache unter `<projekt>/.disco/thumbnails/`. Aufwand
  ~3h. User will Thumbnails bewusst (nicht jeder Link automatisch
  als Bild — verhindert Bilder-Flut bei Listen).

Offen Phase 3 (kein konkreter Auftrag):
- DOCX/XLSX → LibreOffice-CLI → PDF → Thumbnail
- DWG-`THUMBNAILIMAGE`-Section parsen

User-Quote (2026-04-29): *"Disco soll die vorschau bewusst
praesentieren wenn passend. Nicht einfach dass jedes zitat vom
backend gerendert wird."*


## ★ EXTRACTION-PIPELINE OVERHAUL — Konsolidiertes Konzept (Prio: hoch, in Umsetzung 2026-04-30)

Konsolidiert die folgenden Backlog-Eintraege in EIN Konzept:
- "Pipeline-Vollstaendigkeits-Sicht" (Zeile ~980)
- "Office-Formate in die Extraction-Pipeline" (~1056)
- "Extraction nur auf kanonische Dateien" (~1094)
- "Anhaltspunkte fuer replaces / format-conversion-of" (~1338) — Stufe 1+2
- "Stabilitaets-Bugs aus FTS5-Deadlock" Section 2+3 (Counter + max_retries)
- "Extraction-Pipeline-UX: Ampelsystem, Auto-Pipeline, Batch-Mode" (~1858)
- "File-Internal-Metadata bei Registrierung extrahieren" (~2057)

Alte Eintraege bleiben als Vertiefung stehen, der Konsolidations-Eintrag
hier ist die Plan-Quelle.

### Konzept

**6 Pipeline-Schritte** mit Step-Aggregat-Ampel in der Sidebar:

| # | Schritt | DB-Quelle | Status |
|---|---|---|---|
| 1 | Registrierung (inkl. File-Internal-Metadata) | `agent_sources` | 🟢/🟡/🔴 |
| 2 | Externe Anreicherung (Begleit-Excel + SharePoint) | `agent_source_metadata`, `agent_sharepoint_docs` | 🟢/🟡/🔴/⚪ (n.a.) |
| 3 | Kanonik (Duplikate, Replaces, Format-Konversionen) | `agent_source_relations` | 🟢/🟡/🔴 |
| 4 | Routing | `work_extraction_routing` | 🟢/🟡/🔴 |
| 5 | Extraction | `agent_doc_markdown` | 🟢/🟡/🔴 |
| 6 | Suchindex | `agent_search_docs` | 🟢/🟡/🔴 |

**Status-Definition:**
- 🟢 alle done, 0 failed, 0 pending
- 🟡 alle abgehakt (done + failed = total), aber failed > 0
- 🔴 pending > 0 (Files warten auf Verarbeitung)
- ⚪ Schritt n.a. (z.B. Anreicherung wenn keine externe Quelle)

### User-Entscheidungen (2026-04-30)

1. **State-Berechnung**: SQL-View, live aus den 4 Tabellen abgeleitet
   (drift-frei, kein Sync-Code in jedem Pipeline-Schritt noetig).
   Wenn bei 5000+ Files Performance-Problem → spaeter persistierte
   Spalte als V2.

2. **Auto-Pipeline-Default**: NEIN. Pipeline laeuft nicht automatisch
   durch. ABER: Disco soll proaktiv anbieten *"Soll ich den ganzen
   Pipeline-Durchlauf machen?"* nach `sources_register`. Plus
   einzelne Schritte wiederholbar mit ggf. anderer Config — nicht zu
   kompliziert designen.

3. **State-Erzwingung**: Pragmatisch. Tools warnen im Result wenn
   Vorbedingung nicht erfuellt, lassen aber durch (kein Hard-Block).
   System-Prompt-Regel fuer Disco's Verhalten.

4. **File-Status pro Datei in Explorer-Spalte**: Phase 2, jetzt nicht.
   Phase 1 = Step-Aggregat in Sidebar reicht.

### UI-Vorschlag

Expandable Section unter `FLOWS` in der Sidebar:

```
▼ PIPELINE-STATUS                  ↻
  🟢  1. Registrierung        1837 / 1837
  ⚪  2. Externe Anreicherung  n.a.
  🟢  3. Kanonik              1708 → 1517 kanonisch
  🔴  4. Routing                 0 / 1517
  🔴  5. Extraction              0 / 1517
  🔴  6. Suchindex               0 / 1517
```

**Klick auf Schritt:**
- 🔴 → Modal "X Files warten. Jetzt anstossen?" mit Cost-Schaetzung +
       Buttons `[Test mit limit=10] [Full-Run]`
- 🟡 → Detail-Liste der failed Files (Phase 2)
- 🟢/⚪ → kein Effekt oder Statistik-Popup

### n_total-Maßstab pro Schritt

- Schritt 1-3: alle aktiven sources
- Ab Schritt 4 (Routing): nur kanonische Files (Disco extrahiert nie
  Duplikate/Replaces)

### Migrierbarkeit

- View-Migration ist trivial: `CREATE VIEW IF NOT EXISTS v_pipeline_status`
- Keine Schema-Aenderung an Bestand-Tabellen
- Bei Bedarf View droppen + neu anlegen, kein Datenverlust
- Idempotent
- Bestandsprojekte (campus-reuter, lager-halle, rea-denox) profitieren
  sofort: View liest live aus existierenden Tabellen

### Implementierungs-Phasen

**Phase 1 (heute) — View + Sidebar-UI + manueller Trigger**
- Migration 010 datastore: `v_pipeline_status` View
- Backend-Endpoint `GET /api/projects/{slug}/pipeline-status`
- Frontend: neue Sidebar-Section unter Flows, mit Polling-Refresh
- Klick-Modal mit Cost-Schaetzung + Test/Full-Buttons
- System-Prompt-Regel (1-2 Zeilen): proaktiv nach `sources_register`
  fragen ob ganzer Durchlauf

**Phase 2 (spaeter) — File-Internal-Metadata + Office-Formate**
- DOCX/PPTX-Engines (eigener Backlog-Eintrag, jetzt zugeordnet)
- File-Internal-Metadata-Extraktor (`disco/sources/file_metadata.py`)
- Schema-Erweiterung `agent_sources` mit den 7 first-class-Spalten
- Backfill-Script fuer Bestand
- View beruecksichtigt das ggf. fuer Schritt 1-Detail

**Phase 3 (spaeter) — Retry-Strategie + Failed-Markierung**
- max_retries=3 mit Exponential-Backoff
- `extraction_failed`-State in agent_sources
- Skip beim Re-Run, force_retry_failed=true als Override
- LibreDWG-Permanent-Fail-Detection (siehe Backlog FTS5-Deadlock S.4)

**Phase 4 (spaeter) — Counter-Konsistenz-Bugfixes**
- Stale-Run-Detection beim Service-Start
- Counter-Update-Bug nach Crash (workspace.db WAL-Recovery)

**Phase 5 (spaeter) — File-Status-Pille im Explorer**
- Pro Datei eine Status-Pille (Datei-Ebene zusaetzlich zum Step-Aggregat)

User-Quote (2026-04-30): *"Ich haette das ampelsystem aber gerne
praktisch auf extraction pipeline step ebene. Eine art process ampel
fuer jeden prozessschritt."*

### Phase 6 (Pipeline-Status-Schaerfung) — TEILWEISE GEFIXT 2026-05-05

Erledigt am 2026-05-05 (Commits c7287e7 + c9b6374):
- ✅ **Schema-Bug** in n_canonical-SQL (`r.source_id` →
  `r.from_source_id`) — Schritt 3 zeigte immer "→ 0 kanonisch", jetzt
  korrekt (rea-denox: 5790 → 1775).
- ✅ **Maßstab pro Schritt** statt einheitlich n_registered:
  Schritt 4 = kanonisch, Schritt 5 = kanonisch − unsupported,
  Schritt 6 = bereits extrahierte Files. Duplikate fallen aus
  Pendings raus.
- ✅ **Unsupported-Klasse** sichtbar: Files mit engine NULL/leer
  zaehlen als n_unsupported (eigener Bucket), nicht als pending.
- ✅ **Tooltip-Aufschluesselung** im Frontend: done · pending ·
  failed · ohne Engine.
- ✅ **Routing-Flow** filtert Duplikate beim Input
  (extraction_routing_decision/runner.py).

Offen (Phase B):
- ❌ **Failed vs Pending in Schritt 4 + 5.** `work_extraction_routing`
  und `agent_doc_markdown` haben keine error-Spalte. Failed
  Routings/Extractions tauchen einfach nicht auf → werden als pending
  (rot) gezaehlt. Nur Schritt 6 (Suchindex) kann ehrlich gelb werden.
  Erfordert Schema-Migration (error TEXT + retry_count INTEGER) und
  Code-Aenderungen in beiden Flows zum Befuellen. Damit dann auch
  🟡 in Schritt 4 + 5 moeglich.
