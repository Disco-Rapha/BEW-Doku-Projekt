# Disco — Backlog (gesammelte Punkte zur Umsetzung)

Hier landen Beobachtungen und Ideen aus dem Testen, die nicht sofort
umgesetzt werden, aber beim nächsten Iterationsschritt berücksichtigt
werden sollen.

---

## UI / Chat-Erlebnis

### Chat als Haupt-Arbeitsfläche (Priorität: hoch)

Disco steht in der Bildschirm-Mitte, weil sich hier das Wichtigste
abspielt. Konsequenz: **Disco soll proaktiv visuelle Inhalte im Chat
liefern** — nicht nur auf Nachfrage:

- Tabellarische Quick-Analysen direkt im Chat (Markdown-Tabellen,
  nicht nur Fließtext)
- Bei Registrierung/Scan: sofort eine kompakte Übersichts-Tabelle
  (Ordner × Dateizahl, Top-Extensions, Duplikat-Anteil)
- Bei SQL-Ergebnissen: Tabelle statt "es sind 493 Dokumente"
- Bei Excel-Export: kurze Vorschau der ersten 5 Zeilen inline

→ System-Prompt anpassen: "Bevorzuge Markdown-Tabellen und kompakte
  Visualisierungen im Chat, statt nur Text-Zusammenfassungen."

### Beispiele zu Vorschlägen und Ergebnissen (Priorität: hoch)

Disco soll dem Nutzer bei Vorschlägen und Ergebnissen **immer konkrete
Beispiele** mitgeben — nicht abstrakt erklären, sondern zeigen:

- Bei "Soll ich die Quellen registrieren?" → gleich 2-3 Beispiel-
  Dateinamen aus dem aktuellen sources/ nennen
- Bei Klassifikations-Vorschlägen → "z.B. `Schaltplan_A1.pdf` → DCC
  FA010 (Übersichtsschaltplan), `Konformitaet_SMA.pdf` → QC010"
- Bei SQL-Ergebnissen → nicht nur "322 Zeilen", sondern die ersten
  3-5 Zeilen als Tabelle dazu
- Bei Fehlern → konkretes Beispiel zeigen was schiefging und warum

→ System-Prompt: "Gib bei Vorschlägen und Ergebnissen immer 2-3
  konkrete Beispiele aus den aktuellen Daten. Nicht abstrakt, sondern
  greifbar."

### Projektbeschreibung / Projektziel im Onboarding (Priorität: hoch)

Aktuell ist `README.md` im Projekt ein leeres Template. Der Agent
hat dadurch keinen Kontext **wofür** das Projekt da ist — er weiss
nicht ob er klassifizieren, abgleichen oder sortieren soll.

Zwei Ansätze:
- **a) Disco fragt beim ersten Onboarding aktiv nach:** "Ich sehe,
  dass README.md noch leer ist. Was ist das Ziel dieses Projekts?
  Ich trage es für Dich ein." → Dann füllt Disco das README mit
  den Antworten des Nutzers.
- **b) Guided Project Setup als eigener Skill:** `project-setup.md`
  mit Fragen wie: Projektziel? Welche Quellen? Welche Standards?
  Erwartetes Ergebnis? Frist? → Disco schreibt ein strukturiertes
  README + setzt memory.md-Grundlagen.

→ Umsetzung: Skill `project-setup` bauen + im Onboarding-Skill
  prüfen ob README.md nur Template-Text enthält → wenn ja, Setup
  vorschlagen.

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

### Excel = Input/Output, nicht Arbeitsformat (Priorität: hoch)

Intern arbeitet Disco mit Datenbanken. Der Nutzer braucht aber
**nachvollziehbare Analyse-Ergebnisse**: Tabellen, Graphen, Matching-
Ergebnisse mit Agent-Kommentaren, alles verlinkt.

**Anforderungen:**
- Agent baut den Report selbständig auf und kann ihn bearbeiten
- Tabellen mit Highlighting (z.B. Status-Farben)
- Einfache Graphen (Balken, Torte) für Verteilungen
- Agent-Kommentare pro Sektion ("bei 12 Dokumenten war...")
- Links (auf andere Reports, Dateien, DB-Einträge)
- Im Viewer direkt lesbar

**Empfohlener Weg (MVP):** Neues Tool `build_report` — Agent gibt
eine Spec (Sektionen: Text/Tabelle/Chart mit SQL), Server baut ein
HTML mit eingebettetem Chart.js. Liegt in `exports/` oder `work/`.
Konsistent mit `build_xlsx_from_tables`-Pattern.

**Später:** Evidence.dev (Markdown+SQL→Reports, Open Source, Node.js)
oder Live-Dashboard-View im Viewer (DB-gesteuert, interaktiv).

### Disco stellt sich zu oft vor (Bug, Priorität: hoch)

Disco sagt häufig "Ich bin Disco, Dein Dokumentations-Co-Pilot" —
auch mitten in einer laufenden Session, nicht nur beim ersten Kontakt.
Das nervt und wirkt unprofessionell.

Ursache: Im System-Prompt steht "Wenn jemand fragt wer Du bist,
sagst Du knapp: ..." — aber GPT-5 interpretiert das zu aggressiv
und platziert die Vorstellung auch ungefragt.

Fix im System-Prompt:
- "Stell Dich NUR vor wenn der Benutzer EXPLIZIT fragt 'wer bist du?'
  oder es die allererste Nachricht in einem Thread ist. In allen
  anderen Faellen: einfach arbeiten, keine Vorstellung."

### Inhalt statt Tool-Talk (Priorität: kritisch)

Disco redet zu viel darüber welche Tools er aufgerufen hat und wie
das technisch gelaufen ist. Der Nutzer interessiert sich nicht für
"ich habe fs_read aufgerufen und 42 KB gelesen" — er will wissen:

- **Was steht in den Dokumenten?** Was ist interessant, auffällig,
  relevant für das Projektziel?
- **Was schlägt Disco als nächstes vor?** Konkrete Handlungsoptionen
  basierend auf dem was er gefunden hat.

Beispiel SCHLECHT:
> "Ich habe extract_pdf_to_markdown aufgerufen (112 Seiten, 267 KB,
> 6.4s). Dann fs_read mit max_bytes=30000. Dann
> extract_markdown_structure mit 189 Headings..."

Beispiel GUT:
> "Die VGB S 831 definiert 395 Dokumentenklassen (DCC). Für Dein
> Projekt sind die Anhänge A.2 (Systemzuordnung, S. 67-120) und
> A.3 (Bauteil-DCC-Matrizen, S. 121-200) am wichtigsten — daraus
> leiten wir die SOLL-Liste ab. Auffällig: A.4 enthält 642
> Sachmerkmale, die könnten wir für die Qualitätsprüfung nutzen.
> Sollen wir mit dem SOLL-Gerüst aus A.2/A.3 anfangen?"

→ System-Prompt: "Rede NICHT über Deine Tool-Calls. Rede über die
  INHALTE die Du gefunden hast und was sie fuer das Projektziel
  bedeuten. Tool-Details sieht der Nutzer im aufklappbaren Block —
  Dein Text soll Erkenntnisse und Vorschlaege liefern."

### Zusammenfassung am Ende jedes Turns (Priorität: hoch)

Disco macht viele Tool-Calls pro Turn, aber am Ende fehlt dem Nutzer
oft eine **klare Zusammenfassung**: Was ist jetzt passiert? Was ist
das Ergebnis? Was muss ich wissen? Was kommt als Nächstes?

Vorbild: Claude Code — nach einer Reihe von Aktionen gibt es immer
einen kompakten Abschluss-Block mit den wichtigsten Punkten.

Disco soll am Ende jedes größeren Turns:
- **Was gemacht wurde** (2-3 Sätze)
- **Ergebnis/Zahlen** (kompakt, ggf. Tabelle)
- **Was jetzt wichtig ist** (Auffälligkeiten, Fehler, offene Fragen)
- **Nächster Schritt** (konkreter Vorschlag)

→ System-Prompt: "Beende jeden Turn mit einer kompakten Zusammenfassung
  fuer den Nutzer — nicht die Tool-Call-Details wiederholen, sondern
  das Ergebnis auf den Punkt bringen. Was muss der Nutzer wissen?"

### Faktenbasiertes Arbeiten — kein Raten (Priorität: kritisch)

Disco muss **strikt faktenbasiert** arbeiten. Keine Annahmen, kein
Raten, keine "könnte sein"-Aussagen ohne Beleg. Alles muss
nachvollziehbar auf Kontext und Dateiinhalten basieren.

Konkret:
- Wenn Disco eine Klassifikation vorschlägt → muss er sagen **woher**
  er das hat (welche Datei, welche Seite, welcher Kontext-Eintrag)
- Wenn Disco unsicher ist → offen sagen "das kann ich aus den
  vorliegenden Daten nicht sicher ableiten" statt zu raten
- Wenn Disco eine Zuordnung macht → Quelle zitieren
  (z.B. "laut VGB A.3, Seite 134: Bauteiltyp VGBK_A1 → DCC-Set ...")
- Wenn Disco Ergebnisse zusammenfasst → auf die Tool-Results
  verweisen, nicht auf eigenes "Wissen"

Das ist verwandt mit Anti-Halluzination, aber geht weiter: nicht nur
"kein Fertig ohne Tool-Call", sondern "keine Aussage ohne Beleg".

→ System-Prompt: "Du arbeitest ausschliesslich faktenbasiert. Jede
  Aussage, Klassifikation oder Zuordnung muss auf konkreten Daten
  beruhen (Tool-Result, Dateiinhalt, DB-Eintrag, Kontext-Dokument).
  Wenn Du etwas nicht sicher weisst: sag es offen. Raten ist verboten."

---

## Chat-Funktionalität

### Kontext-Komprimierung / Conversation-Compaction (Priorität: hoch)

Bei langen Sessions wächst der Conversation-Kontext (alle bisherigen
Messages + Tool-Results). Irgendwann stösst GPT-5 ans Context-Window
(272k Tokens) oder die Antworten werden langsam/teuer.

Claude Cowork macht regelmässig eine **Compaction**: fasst den
bisherigen Verlauf zusammen, ersetzt alte Messages durch eine
kompakte Zusammenfassung, behält die wichtigsten Fakten.

Disco sollte das auch können:
- **Automatisch** wenn der Kontext > X% des Windows erreicht
- **Oder manuell** wenn der User sagt "fass zusammen"
- Die Zusammenfassung geht in `.disco/sessions/<datum>.md`
  (für spätere Referenz)
- Im Chat bleibt nur die komprimierte Version + die letzten N Turns

Technisch: Die Responses API hat `previous_response_id` — wir können
einen neuen Response starten mit einer komprimierten Zusammenfassung
als Input, statt der ganzen Conversation-Kette. Oder die API bietet
selbst ein `compact`-Feature (prüfen: `client.responses.compact()`
existiert im SDK).

→ Umsetzung: SDK-Feature prüfen, sonst selbst bauen (Zusammenfassungs-
  Prompt → neuer Response-Anker → alte Chain verwerfen).

### "No tool output found" nach Crash/Stop (Bug, Priorität: hoch)

Wenn ein Turn crasht oder per Stop-Button abgebrochen wird, bleibt
die Foundry-Conversation mit einem offenen Function-Call hängen.
Der nächste Turn im selben Thread scheitert dann mit:
"No tool output found for function call call_xxx"

**Aktueller Workaround:** foundry_thread_id auf NULL setzen (frische
Chain). Das verliert den bisherigen Multi-Turn-Kontext.

**Richtiger Fix:** Bei Stop/Crash:
1. Prüfen ob offene Function-Calls in der letzten Response sind
2. Synthetische "aborted"-Outputs senden (haben wir beim
   MAX_TOOL_ROUNDS-Limit schon gebaut)
3. Erst DANN foundry_thread_id auf die bereinigte Response setzen

Alternative: Beim nächsten Turn automatisch erkennen dass die Chain
kaputt ist (400-Fehler abfangen), dann selbst heilen (NULL setzen
+ Retry).

### Antwort unterbrechen / Stop-Button (Priorität: hoch — umgesetzt v20)

Aktuell lässt sich eine laufende Disco-Antwort nicht abbrechen. Wenn
Disco einen langen Turn fährt (viele Tool-Calls, falscher Ansatz),
muss der User warten.

Lösung: **Stop-Button** im Chat-Input-Bereich, der:
- Den WebSocket schließt (oder ein Cancel-Signal sendet)
- Den aktuellen AgentService-Turn abbricht
- Die bisherige Teil-Antwort im Chat stehen lässt
- Status auf "Abgebrochen" setzt

Vorbild: Claude.ai, ChatGPT — alle haben einen Stop-Button während
des Streamings.

---

## UI / Layout

### Explorer/Viewer zeigt veraltete Dateien (Bug, Priorität: hoch)

Wenn Disco eine Datei ändert (z.B. README.md aktualisiert), zeigt
der Explorer/Viewer noch den alten Stand. Der User sieht veralteten
Inhalt und denkt, Disco hat nichts gemacht.

Ursache: Explorer-Tree und Viewer werden nach Disco-Turns zwar
refresht (loadExplorer + loadDbTables), aber der **Viewer-Inhalt
selbst wird nicht neu geladen** wenn dieselbe Datei schon offen ist.

Fix:
- Nach jedem `done`-Event im Chat: wenn eine Datei im Viewer offen
  ist, automatisch neu laden (fetch + re-render)
- Oder: Viewer zeigt einen "Aktualisieren"-Button wenn die Datei
  sich seit dem letzten Laden geändert hat

### Splitter Chat ↔ Viewer frei verschiebbar (Bug/Feature)

Der Trenner zwischen Chat (Mitte) und Viewer (rechts) soll **frei
verschiebbar** sein — manchmal braucht man einen größeren Viewer
(z.B. für breite Excel-Tabellen oder PDF-Seiten).

Status: Splitter-Code ist da (`splitter-right`), aber möglicherweise
funktioniert das Drag nicht sauber. Prüfen + fixen.

### PDF-Viewer funktioniert noch nicht (Bug)

pdf.js-Integration ist im Code vorhanden, aber beim User-Test
funktioniert der PDF-Viewer nicht. Mögliche Ursachen:
- pdf.js CDN-Bundle lädt nicht (CORS, Version)
- Canvas-Rendering scheitert
- Pfad-Problem beim Abruf der PDF über die File-API

→ Debuggen: Dev-Tools → Console öffnen, PDF im Explorer klicken,
  Fehlermeldung lesen.

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

### Batch-Aufgaben GRUNDSÄTZLICH über Pipeline (Priorität: kritisch)

Aktuell läuft die DI-Extraktion von Context-PDFs als Tool-Call
im Chat-Turn. Bei vielen/großen PDFs (16 PDFs, 1000+ Seiten) dauert
das 10-20 Minuten — der Turn kann in ein Timeout laufen und der
User sieht "Disco denkt..." ohne Fortschritt.

**Langzeit-Lösung:** DI-Extraktion als **Pipeline-Job** auslagern:
- Disco triggert: `start_job(type="di-extract", target="context")`
- Worker läuft im Hintergrund, extrahiert PDF für PDF
- Fortschritt sichtbar (z.B. "7/16 PDFs fertig")
- Bei Fehler: einzelne PDF als gescheitert markieren, Rest weiter
- Am Ende: Disco wird benachrichtigt, schreibt Summaries

**Grundsatz:** Alles was über mehr als ~5 Dateien iteriert oder
mehr als 2 Minuten dauert, gehört in eine Pipeline — nicht in einen
Chat-Turn. Das betrifft:
- DI-Extraktion (16 PDFs = 10-20 Min)
- Context-Summaries schreiben (16 Dateien = 48+ Tool-Calls)
- Sources-Registrierung bei 1000+ Dateien
- Jede Form von Bulk-LLM-Klassifikation

Im Chat-Turn soll Disco nur: Pipeline **definieren**, **starten**,
**Fortschritt abfragen**, **Ergebnis zusammenfassen**. Die eigentliche
Arbeit läuft im Worker-Prozess.

Das ist Teil des größeren Pipeline-Features (Phase 2c) und der
wichtigste nächste Baustein für den MVP. Solange Pipelines nicht
gebaut sind: MAX_TOOL_ROUNDS=48 + Timeout 30 Min als Quick-Fix.

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

### High-Resolution-Modus für DI (Teil der Engine-Auswahl oben)

Azure Document Intelligence unterstützt verschiedene Qualitätsstufen.
Aktuell nutzen wir `prebuilt-layout` im Standard-Modus. Für besonders
komplexe PDFs (mehrspaltige technische Zeichnungen, kleine Schrift,
komplexe Tabellen-Layouts) gibt es einen High-Resolution-Modus.

Umsetzen: Parameter `high_resolution: bool = false` im Tool
`extract_pdf_to_markdown` ergänzen. Wenn true: DI-API mit
`features=["ocrHighResolution"]` aufrufen. Kostet mehr pro Seite,
liefert aber bessere Ergebnisse bei schwierigen Scans.

Aktuell: Standard-Qualität reicht für unsere Normen/Richtlinien.
High-Res erst einbauen wenn wir auf Qualitätsprobleme stossen.

---

## Sicherheit / Projekt-Isolation

### Aktives Projekt eindeutig erkennen (Priorität: hoch)

Disco fragt aktuell zu oft „In welchem Projekt arbeiten wir?",
obwohl das Projekt über die UI bereits ausgewählt ist und die
Sandbox (contextvars) es auch kennt. Der Agent sieht die Projekt-
Info offenbar nicht deutlich genug.

**Ursache (vermutet):**
- Projekt-Slug + Projekt-Name + Projektziel stehen nicht oder nur
  schwach im System-Prompt / im ersten Turn-Kontext
- Disco greift auf `list_projects` zurück statt auf die
  Sandbox-Info

**Umsetzung:**
- Beim WebSocket-Connect den aktiven Projekt-Kontext (slug, name,
  Ziel aus README) als erste System-Message oder als stabile
  Prompt-Ergänzung einspeisen
- System-Prompt-Regel: „Das aktive Projekt ist Dir aus dem Kontext
  bekannt. Frage den Nutzer NUR dann, wenn gar kein Projekt
  ausgewählt ist."
- Im `project-onboarding`-Skill: erste Zeile soll das aktive
  Projekt bestätigen, nicht erfragen

### Nicht ausgewählte Projekte dürfen unsichtbar sein (Priorität: hoch)

Aktuell sieht Disco über `list_projects` ALLE Projekte im Workspace
— auch die, in denen gerade nicht gearbeitet wird. Das verletzt
die Mandantentrennungs-Idee, auf der Disco aufgebaut ist.

**Ziel:** Wenn ein Projekt aktiv ist, existieren die anderen für
Disco schlicht nicht. Kein `list_projects`-Leak, keine Möglichkeit
per Umweg auf Fremd-Projekte zu joinen.

**Umsetzung:**
- `list_projects` in Sandbox-Modus: gibt nur das aktive Projekt
  zurück (oder verschwindet ganz aus der Tool-Liste sobald ein
  Projekt gesetzt ist)
- `get_project_details` ebenfalls gescoped: nur aktives Projekt
- Prüfen: haben andere Domain-Tools (search_documents, etc.) den
  Scope sauber dicht, oder gibt es noch Lücken?
- Projekt-Auswahl darf dann nur noch über die UI (Kommandozeile
  oder Sidebar) passieren, nicht durch Disco selbst

**Eröffnung eines Nachbar-Projekts:** nur mit expliziter User-
Bestätigung in der UI — nie vom Agenten aus.

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

*Letzte Aktualisierung: 2026-04-17*
