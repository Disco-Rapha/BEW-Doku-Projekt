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

### Memory-Funktion härten — Disco verliert alles bei Chat-Reset (Priorität: hoch — aus UAT 2026-04-20)

Beobachtung beim Chat-Reset in Prod (nach Modellwechsel gpt-5 →
gpt-5.1_prod): sobald die Conversation-History leer ist, weiß Disco
praktisch nichts mehr über das Projekt. Disco-alt (bew-doku-agent:29)
hat über Monate Gespräche nichts in `.disco/memory/` hinterlassen —
die einzigen dauerhaften Fakten sind in `README.md` / `NOTES.md`,
und das auch nur wenn der User sie dort abgelegt hat.

Folge: Chat-Reset = Amnesie. Das widerspricht der CLAUDE.md-Zusage,
dass `.disco/` das „Hirn" des Projekts ist.

Ursachen (zu prüfen):
- Skill `project-onboarding` ruft `memory_read` nur passiv ab, schreibt
  aber nichts zurück, wenn Disco etwas Wichtiges dazulernt.
- Es gibt kein implizites „merk Dir das" — Disco muss explizit
  `memory_write`/`memory_append` aufrufen, und der System-Prompt
  fordert das nicht genug ein.
- Kein automatischer Snapshot am Session-Ende, der den Gesprächs-
  Verlauf destilliert (ähnlich Conversation-Compaction oben, aber
  mit Ziel „persistentes Projekt-Gedächtnis" statt „Kontext kürzen").

Umsetzung (zu entwerfen):
1. System-Prompt-Regel „Wenn Du eine Entscheidung triffst, eine neue
   Tabelle baust, einen Hersteller/Typen lernst, eine Konvention
   festlegst — **schreibe es in `.disco/memory/MEMORY.md`** mit
   Datum und Kontext."
2. Am Ende jedes Turns (oder alle N Turns) ein implizites
   `memory_compact`: Agent fasst zusammen, was gelernt wurde,
   und hängt einen Eintrag an MEMORY.md an.
3. NOTES.md wird vom Skill `project-onboarding` automatisch
   fortgeschrieben (nicht nur gelesen) — mit Session-Header,
   Datum, Stichwort-Liste der Aktivitäten.
4. Bei Chat-Reset: User sollte gefragt werden „Soll Disco vorher
   die aktuelle Session in MEMORY.md destillieren?" (analog zum
   Compaction-Feature).

Abgrenzung: Conversation-Compaction (oben) ist für den
Kontext-Fenster-Druck. Memory (hier) ist für die **Projekt-
Persistenz** über Sessions hinweg. Technisch ähnlich, Zweck
unterschiedlich — möglicherweise gemeinsame Pipeline.

### Iterativer, gesprächiger Tool-Loop wie Claude Code (Priorität: hoch)

**Beobachtung des Nutzers:** Disco macht viele Tool-Calls hintereinander
stillschweigend und gibt erst am Ende einen großen Text-Block heraus.
Was wir wollen: Frage → Tool → **Ergebnis analysieren** → nächstes
Tool (mit sichtbaren Gedanken dazwischen), bis die Anfrage erledigt ist.

**Stand heute:**
- Das Framework ist iterativ: `core.py` hat `MAX_TOOL_ROUNDS = 48`,
  pro Runde Response → Tools → Results → nächste Runde, bis das Modell
  keine Tool-Calls mehr macht.
- Das Modell-Verhalten ist das Problem: GPT-5 batcht gerne mehrere
  Tool-Calls pro Runde (parallel) und schweigt zwischen den Runden
  („reine Denk-Runden" ohne Text-Output).
- Claude Code macht's anders: Claude schreibt aktiv Gedanken zwischen
  Tool-Calls („Ich schaue mir X an, dann Y"). Das ist Modell-Verhalten,
  nicht Infrastruktur.

**Was fehlt, um Disco-Runs gesprächiger und länger zu machen:**

1. **System-Prompt-Regel „Narrate-while-acting":** explizit fordern,
   dass nach jedem wichtigen Tool-Result ein kurzer Satz kommt, was
   das Ergebnis bedeutet und was als Nächstes getan wird. Nicht am
   Ende alles auf einmal, sondern laufend.

2. **Reasoning-Events streamen:** GPT-5 hat `reasoning` als
   Response-Type (zwischen Tool-Calls passiert „inneres Denken").
   Aktuell nicht live im UI sichtbar — wenn wir es als Text darstellen,
   sieht der Nutzer, was Disco gerade überlegt.

3. **Selbst-Überprüfung nach jedem Meilenstein:** Regel im
   System-Prompt: „Nach N Tool-Calls: kurz innehalten und prüfen,
   ob Du dem Ziel näher kommst. Falls nein: anderen Ansatz wählen
   oder beim Nutzer rückfragen."

4. **Adaptive Tool-Rundungen:** `MAX_TOOL_ROUNDS=48` ist generous
   für normale Anfragen, aber für umfassende Analysen (10k Dokumente)
   reicht es nicht. Diese Klasse an Aufgaben gehört ohnehin in einen
   **Flow**, nicht in einen Chat-Turn. System-Prompt-Regel:
   „Bei > N Items: Flow empfehlen, nicht selbst durchgehen."

5. **UI-Feedback für lange Runs:** Progressbar oder Live-Zähler
   „Runde 7/48, 3 Tool-Calls bisher". Damit der Nutzer sieht, dass
   Disco arbeitet, nicht hängt.

**Ziel:** Disco soll lange Agent-Runs fahren können (Datenanalysen über
mehrere Minuten, mit 20+ Tool-Calls), und dabei die ganze Zeit sichtbar
und nachvollziehbar arbeiten — wie Claude Code. Der Fallback für
richtig große Läufe (10k Items, Stunden) ist der Flow.

→ Umsetzung: System-Prompt-Regeln (Abschnitt "Arbeitsstil" erweitern),
  Reasoning-Events im `core.py` streamen + im Frontend als dezente
  „Gedanken"-Zeilen rendern, Tool-Call-Zähler in den Status-Bar.

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

**ToDo — Docling produktiv verfuegbar machen** (aus UAT-Session 2026-04-19):
- Dependency ist bereits in `pyproject.toml` (`docling>=2.90.0`), aber
  **kein Produkt-Pfad nutzt sie aktuell** — nur ad-hoc Benchmark-Skripte
  im `ibl-lagerhalle`-Projekt.
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

### Flow-Stoppen-Button im Frontend — UMGESETZT 2026-04-19 (spaet) als Run-Streifen

**Geloest** durch persistenten Run-Streifen unter dem Chat-Header
(`#run-strip` in `index.html`, neuer Endpoint `/api/workspace/active-runs`):

- Streifen zeigt projekt-uebergreifend alle Runs in Status `running`/`paused`,
  Polling 3 s.
- Pro Run eine Zeile: Status-Punkt, #ID, Flow-Name, Projekt-Tag, Progress-Bar,
  done/total, ⏱ Laufzeit, 💶 Kosten (mit Budget-Anzeige + over-budget-Highlight),
  `[⏸ Pause]` und `[✕ Cancel]`.
- Cancel zeigt Bestaetigungs-Modal („Done-Items bleiben"). Force-Variante
  bewusst NICHT im Streifen — nur ueber Run-Detail-Panel zugaenglich.
- Bei Status-Wechsel zu `done`/`failed`/`cancelled` → Toast unten rechts
  mit Final-Stats und Direkt-Link „Details oeffnen".
- Klick auf #ID oder „Details oeffnen" wechselt Projekt (falls noetig)
  und oeffnet den Run im Viewer.

Optionaler Folge-Slot (sobald Bedarf):
- WebSocket-Push statt Polling (heute 1 GET/3 s, fuer 1-3 parallele
  Runs voellig unkritisch).
- Resume-Button mit echter Funktion (heute zeigt der Button bei pause
  einen Hinweis, manueller Resume ueber „Neuen Run starten" + Idempotenz).

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

---

## Docling / MLX

### SmolDocling-MLX HuggingFace-Cache-Erkennung (Priorität: mittel)

`markdown_extract(engine="smol-mlx")` schlägt fehl, weil das HF-Hub-SDK
den **manuell** aufgebauten Cache-Ordner nicht erkennt:

```
LocalEntryNotFoundError: Cannot find an appropriate cached snapshot folder
for the specified revision on the local disk and outgoing traffic has
been disabled.
```

Hintergrund: Die Modelle (Granite-MLX + Smol-MLX) wurden manuell per
`curl --continue-at -` aus dem HF-Hub geladen, weil `huggingface_hub`
und `hf_transfer` aus Python heraus auf diesem Mac TCP-Hänger zur HF-CDN
haben (`curl` selbst funktioniert dort einwandfrei). Granite hat
funktioniert, weil `huggingface_hub` initial den Cache schon halb
angelegt hatte (refs/main + Symlinks), bevor es dann hängenblieb. Smol
ist dagegen komplett von Hand aufgebaut — und dabei fehlt offenbar ein
Marker, den HF-Hub für die Cache-Validierung erwartet.

**Workaround heute:** Granite ist Default-Engine und läuft. Smol nicht
verfügbar.

**Saubere Lösung (TODO):** `_convert_vlm_mlx` in
`src/bew/agent/functions/markdown.py` umbauen, sodass es:
1. Erst prüft, ob unter `~/.cache/huggingface/hub/models--<repo>/snapshots/<sha>/`
   die `model.safetensors` als gültiger Symlink liegt (Größe > 100 MB).
2. Falls ja → `mlx_vlm.utils.load(snapshot_path)` direkt mit lokalem
   Pfad aufrufen und HF-Hub komplett umgehen.
3. Falls nein → wie bisher den `repo_id`-Pfad gehen
   (mit der Wahrscheinlichkeit, dass der Download wieder hängt).

Alternative: vor dem Granite-/Smol-Default-Cache-Aufruf einmalig
`HF_HUB_DOWNLOAD_TIMEOUT=10` setzen + `try/except`, sodass HF-Hub
nicht ewig hängt, sondern schnell auf den lokalen Cache zurückfällt.

Ursprung: UAT-Session 2026-04-19, Docling-Integration. Granite-Smoke-Test
hat funktioniert (16s/Seite), Smol-Test scheiterte am HF-Cache-Lookup.

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

### Dev- und Prod-Umgebung parallel betreiben (Priorität: hoch — aus UAT 2026-04-20)

Aktueller Zustand: Raphael und Claude arbeiten **direkt gegen `main`**.
Jede Aenderung (Code, Skills, System-Prompt, Migrationen) wirkt sofort
auf genau die Disco-Instanz, mit der Raphael produktiv arbeiten will.
Das bremst sowohl das Entwickeln (nichts traut sich, kaputt zu gehen)
als auch das echte Nutzen (bei Dev-Aktivitaet ist die Instanz instabil).

**Ziel:** Parallel-Betrieb einer stabilen Prod- und einer volatilen
Dev-Umgebung auf demselben Rechner — Raphael kann produktiv arbeiten,
waehrend Claude am Code schraubt.

Muss vor Umsetzung gemeinsam diskutiert werden. Baustellen:

- **Git-Flow:**
  - `main` = Prod, `dev` = laufende Entwicklung
  - PR von `dev` nach `main` nach Verifikation (manueller Release-Cut)
  - Keine direkten Pushes auf `main` mehr (Branch Protection Rule?)
- **Zwei Installations-Pfade:**
  - `~/Claude/BEW Doku Projekt/` (dev, wo wir jetzt arbeiten)
  - `~/Claude/BEW Doku Projekt – PROD/` (neuer Checkout auf `main`)
  - Jeweils eigenes `.venv/`, eigene `.env`
- **Zwei Workspaces:**
  - `~/Disco-dev/` (bestehender `~/Disco/` wird umbenannt)
  - `~/Disco/` (Prod — neue Daten, die Raphael ernsthaft pflegt)
  - `.env`-Variable `DISCO_WORKSPACE` pro Installation anders gesetzt
- **Zwei Ports:**
  - Dev: `127.0.0.1:8765` (wie heute, Claude Preview)
  - Prod: `127.0.0.1:8000` (Standard-Port aus CLAUDE.md)
  - Beide gleichzeitig an, Raphael arbeitet in Prod, schaut bei Bedarf
    in Dev
- **Foundry-Agent:**
  - Option A: eine Agent-Version fuer beides (Prod faehrt die
    gleiche Version, Dev-Pushes ueberschreiben sie = nicht gut)
  - Option B: zwei Agent-Deployments (`bew-doku-agent` = Prod,
    `bew-doku-agent-dev` = Dev) mit eigenem `FOUNDRY_AGENT_ID`
  - Option C: `disco agent setup` pusht nur in Dev; Release-Cut auf
    Prod braucht `disco agent release` (Agent neu erstellen / Version
    bumpen)
  - **Vermutlich B** — klare Trennung, keine Ueberraschungen in Prod
- **Migrationen:**
  - Dev wendet neue Migrationen sofort an — Prod-DB bekommt sie erst
    beim Release-Cut. Schema-Drift-Risiko.
  - Pruefschritt beim Release: „gibt es Migrationen in dev, die in
    prod noch nicht angewandt sind? Dann erst migrate, dann switch."
- **Logs / Observability:**
  - Getrennte Log-Verzeichnisse pro Workspace (DISCO_LOGS_DIR)
  - UAT-Watcher heute zeigt nur eine Workspace-DB — muss entweder
    parametrisierbar werden oder es braucht zwei parallele Watcher
- **Model-Cache:**
  - `~/.cache/huggingface/` ist systemweit geteilt, unkritisch
  - `~/.cache/docling/`, `~/.cache/EasyOCR/` dito
  - Keine Parallelisierung noetig, beide Instanzen lesen denselben Cache
- **Daten-Migration Prod ← Dev:**
  - Wenn ein Projekt in Dev „gereift" ist (z. B. UAT-Tests bestanden),
    sollte es nach Prod wanderbar sein. Manuell per `rsync` oder
    Disco-Kommando?

**Minimal Viable Split:**
1. `git checkout -b dev` und ab jetzt nur noch dort pushen
2. Zweiter Clone auf `main` unter neuem Pfad
3. Zweiter Workspace `~/Disco-prod/` oder analog
4. `.env` pro Installation, `DISCO_WORKSPACE` trennen
5. Zwei Uvicorn-Instanzen gleichzeitig auf unterschiedlichen Ports
6. Foundry-Agent zunaechst geteilt, spaeter Split

**Offene Fragen:**
- Single-Machine-Setup reicht, oder braucht es eine zweite Hardware
  fuer „echte" Prod-Trennung (DSGVO, Datenabschottung)?
- Sind Skills und system_prompt.md Teil von „Code" (also per Git
  versioniert) oder sollen sie zwischen dev und prod kopierbar sein
  ohne Branch-Merge?
- Ab wann lohnt CI/CD (Tests auf dev-PR, deploy auf Merge nach main)?

Ursprung: UAT-Session 2026-04-20, direkter Wunsch des Nutzers — heute
ist der Schmerz das erste Mal konkret geworden, weil waehrend eines
laufenden 20-Dokument-Flows parallel ein zweiter Flow gebaut wurde
und der System-Prompt zweimal geaendert wurde.

---

*Letzte Aktualisierung: 2026-04-20*
