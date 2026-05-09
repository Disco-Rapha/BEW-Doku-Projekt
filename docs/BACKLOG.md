# Disco — Backlog (gesammelte Punkte zur Umsetzung)

Hier landen Beobachtungen und Ideen aus dem Testen, die nicht sofort
umgesetzt werden, aber beim nächsten Iterationsschritt berücksichtigt
werden sollen.

---

## TOP-Roadmap (Stand 2026-05-08)

Re-Priorisierung nach Phase-2-Aufräumen. Echte „brennen-jetzt"-Items:

1. **★ Kundendaten-Trennung Software ↔ Repo** (User-Beobachtung
   2026-05-08, prio HOCH — DSGVO-relevant)

   **Symptom**: User hat an anderem Rechner Claude Code via GitHub
   auf das Repo gelassen — Claude wusste sofort von den Prod-
   Projekten („Lagerhalle", „Rea Denox" usw.). Das heisst: irgendwo
   im Code/Doku des oeffentlich klonbaren Repos stehen
   Kundendaten-Slugs. Verstoesst gegen die CLAUDE.md-Regel
   *„Kundendaten niemals in Git"*.

   **Identifizierte Lecks (Stand 2026-05-08, Quick-Scan):**

   | Quelle | Treffer | Beispiel |
   |---|---:|---|
   | `docs/BACKLOG.md` | 10+ | Symptom-Beschreibungen ("Symptom 2026-05-07 (lager-halle, Prod):"), Run-IDs, Bug-Fixe pro Projekt |
   | `docs/architecture-decisions.md` | 2 | „In der Praxis (rea-denox, lager-halle, campus-reuter)" |
   | `scripts/backfill_pdf_page_offsets.py` | 1 | Beispiel-Aufruf im Docstring: `--project bew-rsd-campus-reuter` |
   | **Commit-Bodies (Git-History)** | **26 Treffer** | Pipeline-Bug-Fixes, Diagnose-Commits — **liest jeder GitHub-Browser** |
   | Commit-Subjects | 0 | sauber |
   | `CLAUDE.md`, `system_prompt.md`, Skills | 0 | sauber |

   **Aktion — Sofort (going forward, vor naechstem Commit):**

   - Doku-Schreib-Konvention: **Pseudonyme** statt echter Slugs
     verwenden. Vorschlag: `prod-A`, `prod-B`, `prod-C` mit
     Mapping-Notiz **NUR** im lokalen Workspace
     (`~/Disco/.repo-pseudonyms.txt`, gitignored), nicht im Repo.
     Alternative: generische Begriffe wie „ein 1819-Datei-Projekt"
     statt „lager-halle".

   - **CLAUDE.md ergaenzen**: explizite Regel, dass Slugs aus
     `~/Disco/projects/` weder in Code noch in Doku noch in
     Commit-Messages auftauchen duerfen. Mit Pseudonym-Mapping-
     Verweis.

   - **Pre-Commit-Check** (klein, leicht): `git diff --cached`
     gegen eine Liste bekannter Prod-Slugs greppen, bei Treffern
     blockieren mit Hinweis aufs Pseudonym.

   **Aktion — Repo-Cleanup (mittelfristig, eigene Session):**

   - Bestehende Doku-Stellen anonymisieren: BACKLOG.md (10+) und
     architecture-decisions.md (2) per Suchen/Ersetzen auf
     Pseudonyme umstellen, scripts/backfill_pdf_page_offsets.py
     analog. Bestand: noch alle Slugs einzeln abrufbar in dieser
     Liste, wenn migriert in Pseudonym-Mapping.

   - **Git-History-Rewrite (heikel)**: 26 Commit-Bodies enthalten
     Slugs. BFG / git-filter-repo kann die History rewriten,
     aber: alle Klone (auch User auf anderen Rechnern) muessen
     dann frisch geklont werden, plus Force-Push auf origin.
     Risiko abwaegen vs Nutzen — wenn Slugs harmlos
     (Stadtteil-Namen ohne weitere Inhalte) ggf. on-going-forward
     reicht.

   **Aktion — Konvention dauerhaft:**

   - **Phase-2-/Phase-3-Block 'Pseudonymisierung':** als eigener
     Aufraeum-Block im Stil der bisherigen Bloecke (A-K), klar
     abgeschlossen. Inkludiert die Doku-Migration, das
     Pre-Commit-Hook, den CLAUDE.md-Eintrag.

   - **Pruefung der Vergangenheit**: gibt es noch andere
     Kundendaten-Spuren, die nicht Slugs sind? z.B.
     KKS-Codes (Y0SBD32 AA501 etc.), Hersteller-Namen,
     Personennamen aus Test-Output. Quick-Scan in eigener Session.

   **Risikobewertung:**

   - **DSGVO**: Slugs alleine sind keine personenbezogenen Daten,
     aber sie verraten welche Kunden-Projekte BEW betreut.
     Mandantenschutz-Argument.
   - **Wettbewerbsrelevant**: Liste der bearbeiteten Projekte ist
     vertrauliche Geschaeftsinformation.
   - **Technisch riskant**: Git-History-Rewrite ist destruktiv,
     wenn fehlerhaft.

   **Vorschlag-Reihenfolge**: erst CLAUDE.md-Regel + Pre-Commit-
   Hook (1h), dann Doku-Anonymisierung in dev-Branch (2h), dann
   Entscheidung ueber History-Rewrite separat.

2. **★ EXTRACTION-PIPELINE OVERHAUL** — Phase 2 (Office-Formate
   DOCX/PPTX + File-Internal-Metadata) und Phase 3 (Failed-Tracking
   für 🟡-Status) sind die nächsten großen Brocken. Heute Nachmittag
   geplant.
3. **★ Memory-Architektur: Zwei-Schicht-Modell + Tabellen-Wissen
   bei Tabellen** — User-Beobachtung 2026-05-07 (lager-halle):
   `DISCO.md` (45 KB) und `NOTES.md` (28 KB) wachsen unkontrolliert,
   werden bei jedem Session-Start komplett gelesen → ~18 k Tokens
   Sockel pro Onboarding. Auch Tabellen-Schema-Wissen liegt heute
   in DISCO.md statt am Tabellen-Objekt selbst.

   **Konzept-Skizze (Stand 2026-05-07, vor Diskussion):**

   - **Schicht 1 — IMMER laden:** kleine Kern-Datei mit
     Projekt-Identität, aktivem Thema, kritischen Konventionen.
     Maxima ~5 KB. Wird bei jedem `memory_read` ohne Argumente
     geliefert.

   - **Schicht 2 — Kapitel-Index:** Liste aller Kapitel-Titel
     (z.B. „PDF-Pipeline-Kalibrierung", „Excel-Reporter-Anpassungen",
     „SOLL/IST gegen VGB S 831"). Disco bekommt nur den Index als
     Default. Bei thematischer Passung lädt er ein konkretes
     Kapitel via `memory_read({chapter: "..."})`.

   - **Tabellen-Wissen wandert weg von DISCO.md** — pro Tabelle
     ein eigenes Beschreibungs-Objekt: was steht drin, wie ist das
     Schema entstanden, welche Konventionen, welche typischen
     Joins. Speicherung-Kandidaten: SQL-Comments (CREATE TABLE
     ... -- Kommentar), oder eine `agent_table_docs`-Tabelle, oder
     pro Tabelle eine `_doc.md` im Projekt. Diskussion offen.

   - **NOTES.md** als chronologisches Logbuch — pro Eintrag mit
     Datum + Kapitel-Tag. Kapitel-Tag macht NOTES kompatibel zur
     Kapitel-Index-Logik aus Schicht 2.

   - **Auto-Archivierung** — Hebel 4 aus der Context-Analyse vom
     2026-05-07. NICHT separat machen, sondern als Teil dieser
     Memory-Architektur-Reform: alte Kapitel landen in
     `.disco/memory-archive/<date>.md` und sind dort wieder per
     Index/Suche abrufbar.

   - **Skills-State im Handover** — Hebel 5 aus der Context-
     Analyse: nach Compaction soll Disco wissen, welche Skills
     im aktuellen Thema aktiv waren. Gehoert konzeptionell zu
     dieser Memory-Reform.

   **Heute schon teilweise umgesetzt** (2026-05-07): Hebel 1
   (memory_read max_bytes-Default + section-Filter), Hebel 2
   (fs_read max_bytes-Default), Hebel 3 (Compaction v3 mit
   Tool-Output-Truncation). Die Anpassungen sollen mit der
   Memory-Reform spaeter nochmal verfeinert werden.

   **Zu klaeren in der Diskussion:**
   - Wo liegt Schicht 1 physisch — DISCO.md (umfunktioniert) oder
     neue Datei?
   - Kapitel-Index: separate Datei oder Headings-Scan?
   - Tabellen-Wissen-Speicherort: SQL-Comment / `agent_table_docs` /
     `_doc.md`?
   - Migration der bestehenden DISCO.md/NOTES.md: automatisch
     zerlegen oder manuell vom Nutzer pro Projekt?

4. **★ Data-Lineage + Daten-Architektur Ebene 3** — Konzept-Diskussion
   mit User offen. Disco verzettelt sich in `work_*`-Tabellen ohne
   Lifecycle. Konsolidiert aus zwei Themen 2026-05-07.
5. **★ System-Prompt + Skill + Tool Review-Session** — gemeinsamer
   Walkthrough mit User: System-Prompt (782 Zeilen, 41 Sections, viel
   Doppelung) + alle 11 Skills (besonders `report-builder` mit nur
   1× Nutzung) + alle 42 Tools auf Sinn / Doppelung / Unklarheit
   prüfen. Ergebnis: gestraffter Prompt + bewusstere Skill-Liste +
   ggf. weitere Tool-Streichungen. User liest mit, ich liefere
   Material. **Material liegt: `docs/review-session-2026-05-08.md`**.
6. **Stabilitäts-Bugs aus FTS5-Deadlock** — 4 Bugs (FTS5 blockiert
   Server, Counter-Update nach Crash, DI-HighRes max_retries,
   LibreDWG SIGABRT). Eigene Bug-Fixing-Session geplant.
7. **User-Feedback-Cluster aus 24 bad-Reactions** — 13 Cluster aus
   echtem User-Pain. Drei Cluster (A/G/H) sind durch Phase 2
   erledigt, F+J teilweise. Rest gezielt abarbeiten.

**Mittel** (heute nicht TOP, aber im Blickfeld): Office-Formate (Teil
des ★), File-Internal-Metadata (Teil des ★), Cost-Tracking
Chat+Monatlich, Disco-Prozess-Management, M03 (run_python prompt-
injection härten), H06 (DI-Kosten im Chat sichtbar), H11
(Tests), M01 (UI-Awareness), M08 (Tabellen-Katalog), M10 (Dev/Prod-
Folgefragen), M11 (Portal-Agent-Rollout), N02 (duration_ms-Schema).

**Niedrig**: H02 (Slash-Referenzen), N01 (Flow-Scaffold-TODOs),
Run-Strip Bug 2 (Counter-100%-Anzeige).

**Architektur-Entscheidung F15 SharePoint-Connector — DONE 2026-05-09**:
User-Entscheidung *„raus damit"*. Komplett-Streichung im Rahmen
der Tools-Review-Session: Modul `src/disco/sharepoint/` (4 Files,
~1085 SLOC) geloescht; `domain.py` (4 Tools: get_project_details,
search_documents [Doppelung mit search_index], get_database_stats,
start_sync) geloescht; `sources.py` geloescht (war SP-CRUD-Schicht);
CLI-Subcommands `sync`/`auth`/`sp` plus `source` weg; api/main.py-
Endpoints (`/api/sources/.../snapshot|delta|import-json|sp-fields|
sync-status`) weg; config-Felder `msal_*` weg. Tool-Count 43→39.
**Offen fuer eigene Migration**: Tabellen `documents`,
`source_folders`, `document_sp_fields`, `sources`, `processing_events`
in `system.db` plus `agent_sharepoint_docs` in einigen Projekt-DBs —
gehoeren zur Datenseite, werden separat gedroppt wenn die Daten in
den Prod-Projekten nicht mehr referenziert werden.

---

## UI / Chat-Erlebnis

### IDEE: Live-WYSIWYG-Editing im Viewer fuer Reports/Tabellen/Text (Vision, prio MITTEL)

**Stand 2026-05-09 — User-Idee, noch zu diskutieren.**

**Kerngedanke:** Wenn Disco an einem HTML-Report, einer Excel-Tabelle
oder einem Text-/Word-Dokument arbeitet, aktualisiert der Viewer im
rechten Panel sofort live mit. So entsteht ein iterativer
Schreib-Loop — *„Disco schreibt → ich sehe sofort was rauskommt → ich
sage was anders soll → Disco aendert"* — der Viewer wird vom passiven
Anzeiger zum aktiven Co-Working-Space.

**Use-Case-Beispiel:** Ergebnisbericht fuer den Kunden. Statt
Build-Run-Reload-Schleife schreibt Disco direkt im Builder, der Viewer
zeigt den neuen Stand sofort, der Nutzer kommentiert was angepasst
werden soll, naechste Iteration.

**Was waere noetig:**

- **WebSocket-Push** vom Server an den Viewer, sobald eine relevante
  Datei geschrieben wird (`memory_write`, `fs_write`, Builder-Run).
  Heute schon vorhanden fuer Chat — auf Datei-Events erweitern.
- **Pro Format ein Sub-Workflow:**
  - **HTML-Reports:** schon heute schoen rendern (Sandbox-iframe).
    Live-Reload braucht nur: Datei-Watcher + iframe-`location.reload()`.
    Builder-Pattern (`build_*.py` → `report.html`) passt perfekt rein.
  - **Excel-Tabellen:** schwieriger. SheetJS rendert read-only,
    Write-Back muesste ueber Zwischenformat (CSV, SQLite, MD-Tabelle).
    Pragmatischer Pfad: Disco editiert eine Tabelle in der DB
    (`work_*` oder `agent_*`), der Viewer rendert die Tabelle live —
    Excel kommt erst beim Export ueber `build_xlsx_from_tables`.
    „Live-Excel" ist eigentlich „Live-DB-Tabelle plus on-demand-Export".
  - **Text-/Markdown-Dateien:** simpel — gleiche Live-Reload-Logik wie
    HTML, der Markdown-Viewer rendert frisch.
  - **Word (.docx):** schwierig in der Live-Schleife. Realistisch:
    Disco schreibt in Markdown, exportiert per python-docx
    on-demand. Vollwertiges WYSIWYG fuer .docx waere ein eigenes
    Sub-Projekt (LibreOffice-Headless? OnlyOffice-Embedded?).
    Erstmal raus aus dem MVP.

**Architektur-Skizze (grob):**

1. Datei-Watcher im FastAPI-Server (`watchdog`-Lib) horcht auf
   `<projekt>/exports/**/*.html`, `<projekt>/exports/**/*.md`,
   `<projekt>/data.db`-Aenderungs-Events.
2. WebSocket-Topic `viewer-update` mit Payload `{path, kind, ts}`.
3. Frontend abonniert das Topic, prueft ob `state._viewerOpenFile`
   matched, dann `openFileInViewer(...)` neu aufrufen.
4. Optional Soft-Reload-Animation, damit der User sieht „da ist gerade
   was Neues angekommen".

**Offene Fragen fuer die Diskussion:**

- Wie umgehen mit Race-Conditions, wenn der Builder mitten im Schreiben
  ist und der Watcher schon triggert? (Debounce? Atomic-Rename-Trigger?)
- Soll Disco bewusst in einen *Edit-Modus* fuer eine Datei wechseln
  koennen, oder ist jeder `fs_write` ein Trigger? Ersteres ist
  vorhersagbarer, zweites braucht weniger neue Tools.
- Token-Frage: jeder Disco-Edit-Zyklus kostet — bei einem Bericht-Bau
  mit 20 Iterationen schnell 50k Tokens. Lohnt sich nur, wenn die
  Iteration billiger als ein voller Builder-Run ist (also: kleine
  gezielte Aenderungen, keine Voll-Rewrites).
- HTML-Report-Builder-Pattern bevorzugen: kleine Edit-Tools fuer den
  Builder (`patch_block`, `add_section`) statt Voll-Rewrite, damit
  Disco gezielt aendern kann.

**Anschluss an bestehende Bausteine:**

- HTML-Viewer mit Sandbox-iframe ist seit 2026-05-09 da.
- Builder-Pattern (`build_<slug>.py` + Snapshots `report_YYYY-MM-DD_vN.html`)
  ist im `report-builder`-Skill etabliert.
- WebSocket-Infrastruktur existiert (`api/main.py`, Chat-Streaming).

**Naechste Schritte (wenn entschieden):**

1. Erstmal nur HTML-Live-Reload bauen (kleinster Aufwand, groesster
   Wow-Effekt fuer die Demo) — Schaetzung 3–5 h.
2. Markdown-Live-Reload als Bonus (~2 h, gleiches Pattern).
3. DB-Tabelle live im Viewer (DB-Tabelle ist schon da, braucht nur
   den Push-Trigger) — ~3 h.
4. Excel-Live als „Export on demand" (kein WYSIWYG, aber Klick-zum-
   Aktualisieren) — ~4 h.
5. Word/.docx zurueckstellen, eigenes Sub-Projekt.

---

**Alternative Spur fuer Office-Formate: Office-Add-In statt Render
(User-Idee 2026-05-09).**

Statt Excel/Word **in Disco zu rendern** koennten wir Disco **als
Office-Add-In in Excel/Word reinstecken**. Excel selbst wird zum
Viewer — Fidelity per Definition perfekt, native UX, keine
Render-Krueke.

**Architektur:** Manifest + Taskpane (HTML/JS, gleiche Stack-DNA wie
unsere Web-UI). Office.js-API steuert Zellen, Formate, Sheets, Charts,
Pivots, conditional Formatting, named Ranges, aktuelle Auswahl.
Taskpane spricht ueber `localhost:8765` mit dem laufenden Disco-
FastAPI. Free SDK, laeuft auf Windows + Mac + Office-Web.

**Pro:**

- Perfekte Excel-/Word-Fidelity (es ist Excel/Word)
- User-Workflow bleibt nativ — keine zweite UI lernen
- Word + PowerPoint kommen mit demselben Pattern
- Keine Cloud-Abhaengigkeit (Office.js laeuft im lokalen Excel)
- BEW-Kunde hat eh Office

**Contra:**

- Distribution-Frage: Sideload trivial fuer Dev, fuer Kunden entweder
  Sideload-Anleitung pro Rechner / AppSource-Veroeffentlichung / oder
  zentrales M365-Admin-Deployment im Vattenfall-Tenant
- UX-Split: Web-UI fuer Doku-Pipeline, Taskpane fuer Office-Arbeit
- Auth: Taskpane → localhost-Disco. Dev easy, Prod braucht
  HTTPS-Cert + Origin-Check

**Aufwand:**

- MVP-Sideload (Manifest + Taskpane mit Chat-Iframe + 5
  Office.js-Befehle): 3–5 Tage
- Solider Stand (Pivot/Chart/Formel + Auth-Hardening + Selektion-
  Sync): 1–2 weitere Wochen
- Distribution: separat verhandelbar mit Kunden-IT

**Empfehlung:** Office-Add-In ist fuer Office-Formate die saubere
Architektur. Die Render-Spuren (LibreOffice→PDF, xlsx2html) bleiben
trotzdem sinnvoll als Inline-Preview im Disco-Web-Viewer, damit man
nicht jedes Mal Excel oeffnen muss, nur um eine Tabelle anzusehen.
Beides parallel: Inline-Preview fuer „kurz reinschauen", Office-Add-
In fuer „aktiv mit Disco an einem Bericht arbeiten".

---

### BUG: Disco vorgaukelt Chat-Compaction obwohl er sie nicht ausloesen kann (Prio: hoch)

**User-Beobachtung 2026-05-08, lager-halle:** User schreibt im Chat
*"Bitte komprimiere jetzt den Chat. Schritt 1: memory_append mit
chronologischem Eintrag …"*. Disco fuehrt `memory_append` auf
NOTES.md aus und antwortet: *"✅ Komprimiert: NOTES ergaenzt, DISCO
war bereits auf Stand"*. **Tatsaechlich wurde der Chat NICHT
komprimiert** — `last_compaction_at` blieb auf altem Wert,
`is_compacted=0` fuer 40 Messages, `token_estimate` weiterhin bei
148k. Erst der gelbe „Komprimieren"-Button oben rechts oder ein
`/compact`-Slash-Command ruft den echten Backend-Mechanismus
(`run_compaction_with_handover()`).

**Auswirkung**:
- User glaubt, der Chat sei komprimiert, sieht aber UI weiterhin auf
  90 % + → denkt der Sockel-Reduktions-Hebel sei wirkungslos.
- Token-Limit-Crash droht, weil keine echte Compaction passiert.
- Disco verbraucht trotzdem Tokens fuer den `memory_append`-Lauf.

**Ursache**: Disco hat keinen Tool-Zugriff auf die Compaction-API.
Im System-Prompt-Section *Dein Gedaechtnis* + *Wie Du mit dem
Nutzer arbeitest* fehlt die Regel, dass *"komprimiere den Chat"*
ein User-UI-Aktion ist, kein Disco-Tool-Aufruf.

**Fix-Vorschlaege:**

1. **System-Prompt-Regel ergaenzen** (kleinste Aenderung): bei
   User-Wunsch *"komprimiere"* / *"compact"* soll Disco zuerst die
   Session-Zusammenfassung in NOTES anlegen, **dann** explizit
   sagen: *"Damit der Chat technisch komprimiert wird, klick bitte
   den 'Komprimieren'-Button oben rechts (oder schicke `/compact`).
   Ich kann den Schritt selbst nicht ausloesen."* Kein Vortaeuschen
   einer Compaction.

2. **UI-Hint im Chat-Render**: wenn Disco-Antwort den String
   *"Komprimiert"* / *"komprimieren"* enthaelt UND keine Compaction
   in den letzten 60 sec stattgefunden hat, blendet das Frontend
   einen kleinen Hint ein: *„Hinweis: Disco hat den Chat nicht
   technisch komprimiert. Klick hier zum echten /compact"*.

3. **Tool fuer Disco** (gross, eher fuer Skill-Library-Aera): ein
   `chat_compact()`-Tool, das die Compaction selbst ausloest mit
   User-Bestaetigung. Bedingt: das Tool muss explizit User-OK
   einholen, sonst koennte Disco aus Versehen frueh komprimieren
   und damit Kontext verlieren.

**Empfohlene Reihenfolge**: Fix #1 (System-Prompt-Regel) jetzt im
Rahmen der TOP-5 Review-Session. Fix #2 als kleines UI-Patch
danach. Fix #3 nur wenn nach Skill-Library-Aera der Bedarf
besteht.

**User-Quote 2026-05-08**: *"Trotzdem ist der kontext use bei 198k.
Ahh ok ich muss im chat noch den cut machen. Ok, ja das ist nicht
sauber gelöst, aber für mich jetzt erst mal funktional. Bitte als
BUG ins BL"*.

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

### IDEE: DCC-Klassifikation per Embedding-Klassifikator (User-Idee 2026-05-09, prio MITTEL)

**Stand:** strategisch, nicht akut. Vorbedingung: Korrekturlieferung
DCC-Predictions von Sascha/Peter/Roman muss vorliegen — sonst lernt
der Klassifikator GPT-5-Fehler.

**Kerngedanke:** Statt jedem Dokument einen LLM-Call mit DCC-Referenz-
liste-CSV im Prompt zu geben, bauen wir ein **gelabeltes Trainings-Set
und einen k-NN/Centroid-Klassifikator in Embedding-Space**. Pro DCC
sammeln wir die Embeddings aller bestaetigten Beispiel-Dokumente; bei
einer neuen Klassifikation berechnen wir das Document-Embedding und
finden den DCC mit geringstem aggregiertem Abstand.

**Architektur:**

```
TRAINING (offline, einmalig + bei Updates):
  Pro gelabeltes Dokument:
    Markdown laden -> in Sections splitten (~512 Tokens, 128 Overlap)
    Pro Section: Embedding via Azure text-embedding-3-large (oder -small)
    Speichern in agent_dcc_training_embeddings
      (file_id, section_idx, master_dcc, vector_blob, label_quality)

PREDICTION (online, pro Dokument):
  1. Markdown -> Sections -> Embeddings
  2. Pro DCC c: aggregate(distances zwischen query_sections und
                          training_vectors_of_class_c)
  3. Top-3 DCCs nach Score, plus Margin als Konfidenz
  4. margin < threshold -> "unsicher" -> LLM-Fallback
```

**Architektur-Entscheidungen die zu treffen sind:**

- **Centroid (1 Mean-Vektor pro DCC) vs. k-NN (alle Trainings-Vektoren):**
  k-NN gewinnt wegen Erklaerbarkeit ("die 5 aehnlichsten Trainings-
  Dokumente haben DCC=X"), Speicher ist mit ~30 MB irrelevant.
- **Section-basiert vs. Whole-Document:** Section-basiert + Min-
  Aggregation, weil DCC oft in einem Teil des Dokuments codiert ist
  (Stempel, Inhaltsverzeichnis, Header).
- **Embedding-Modell:** `text-embedding-3-small` fuer Pilot (5x billiger
  als large, fuer strukturierte technische Texte oft ausreichend).
- **Off-Distribution-Detection:** wenn min-distance > T fuer alle
  Klassen → Fallback auf LLM. Wichtig: das System soll nicht
  zwanghaft eine Klasse zurueckgeben, wenn das Dokument einen
  ungesehenen DCC hat.

**Knackpunkte (ehrlich):**

- **Trainings-Daten-Qualitaet** — die Korrekturlieferung ist die
  Pflicht-Vorbedingung. Bootstrap mit GPT-5-high-conf-Predictions
  ist nur fuer P0/P1-Eval verwendbar, niemals als Default.
- **Class Imbalance** — bei 410 DCCs werden in 1.500 Predictions oft
  nur ~100 abgedeckt. Die anderen 310 braucht der LLM-Fallback.
- **Long-Tail** — DCCs mit < 5 Beispielen sind k-NN-instabil; als
  "nicht trainiert" markieren und Fallback.

**Phasen (5 Tage Gesamtaufwand):**

| Phase | Was | Aufwand |
|---|---|---|
| **P0 — Daten-Audit** | Class-Distribution der vorhandenen Predictions; reicht das fuer einen Pilot? | 0,5 Tag |
| **P1 — Pipeline** | text-embedding-3-* deployen, agent_dcc_training_embeddings, Section-Splitter (`build_search_index`-Logik wiederverwenden), Bootstrap-Flow | 1 Tag |
| **P2 — Eval** | 5-Fold-Cross-Validation auf den Trainings-Daten; Top-1/Top-3-Accuracy pro DCC; Confusion-Matrix-Light | 0,5 Tag |
| **P3 — Inference-Flow** | `dcc_prediction_v3_embedding` mit margin-Threshold + LLM-Fallback; schreibt in `agent_dcc_prediction` mit `predictor_version='embed_v1'` | 1 Tag |
| **P4 — A/B-Test** | 200 Dokumente parallel via v1 (LLM) und v3 (Embedding+Fallback); Diff in Excel-Report | 0,5 Tag |
| **P5 — Active Learning** | Bei `margin < T` Flag in UI; Sascha entscheidet; Entscheidung fliesst zurueck ins Trainings-Set | 1 Tag |

**Vor- vs. Nach-Korrekturlieferung-Schwenk:**

- **Vor:** P0–P2 mit Bootstrap-Daten (high-conf-GPT-5-Predictions);
  A/B-Vergleich gegen den heutigen Flow zeigt Setup-Tauglichkeit.
  **Niemals als Default schalten** — wir lernen sonst GPT-5-Fehler.
- **Nach:** Bootstrap-Wahrheit durch echte Reviews ersetzen, Re-Train,
  neue Eval. Wenn Top-1-Accuracy ≥ heutiger LLM-Qualitaet: produktiv
  schalten als Default, LLM bleibt Fallback.

**Erwartete Effekte:**

| Metrik | Heute (LLM) | Embedding-System |
|---|---|---|
| Kosten pro Inferenz | ~1–3 ¢ | ~0,001 ¢ (1000× billiger) |
| Latenz pro Inferenz | 5–15 s | ~100 ms (50× schneller) |
| Vollscan rea-denox (1.500 Dok.) | ~30 €, ~3 h | ~5 ¢, ~3 Min |
| Reproduzierbarkeit | Modell-Drift moeglich | deterministisch |
| Erklaerbarkeit | "Modell hat entschieden" | "Diese 5 aehnlichsten Trainings-Dokumente sind DCC=X" |

**Anschluss an bestehende Bausteine:**

- Section-Splitter existiert in `src/disco/agent/functions/search.py`
  (`build_search_index` macht Chunks à 500–800 Tokens) — wiederverwendbar.
- Azure-OpenAI-Client + Sweden-Central-Setup ist da, fehlt nur die
  Embedding-Deployment-Konfiguration.
- `agent_dcc_prediction` als Ziel-Tabelle bleibt — Feld
  `predictor_version` ergaenzen, damit v1 (LLM) und v3 (Embedding)
  parallel laufen koennen.
- SQLite mit BLOB-Spalte fuer Vektoren reicht; numpy-In-Memory-
  Cosine fuer 5k Vektoren ist Mikrosekunden-schnell.

**Wann starten:** wenn die Korrekturlieferung kommt. Vorher kein Default-
Schalter, max. P0–P2 als Setup-Pilot.

---

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

## ★ System-Prompt + Skill + Tool Review-Session (Prio: TOP — geplant 2026-05-07)

**User-Anforderung 2026-05-07**: gemeinsamer Walkthrough durch
System-Prompt, alle Skills und alle Tools. Ziel: kritisch prüfen,
was wirklich gebraucht wird, was redundant ist, was unklar
formuliert ist. Ergebnis ist eine deutlich gestraffte Disco-
Persönlichkeit ohne Funktionsverlust.

### Vorbereitung (von Disco vor der Session)

**1. System-Prompt-Mapping** — `src/disco/agent/system_prompt.md`,
heute 38 KB / 782 Zeilen / 41 Sections:
- Pro Section: Zweck, Länge, getriggerte Use-Cases der letzten 30 Tage
- Doppelungen markieren (Audit hat schon: Verzeichnisstruktur ↔
  Architektur-Ebenen, drei Persönlichkeits-Sektionen, Pipeline-Hinweis
  zweimal, Anti-Halluzination + Faktenbasiert + kein Raten)
- Tool-Detail-Sektionen: stehen schon im Tool-Schema, hier redundant?

**2. Skill-Inventur** — `skills/*.md`, heute 11 Skills:
- Pro Skill: Trigger-Phrasen aktuell, Aufruf-Häufigkeit (30d), letzter
  Update, Frontmatter-Konsistenz
- Audit hat: `report-builder` nur 1× geladen → Streichung oder
  Trigger-Schärfung?
- `excel-formatter` vs `excel-reporter` Überschneidung?
- `flow-builder` vs `flow-supervisor` Abgrenzung klar?

**3. Tool-Inventur** — alle 42 registrierten Tools:
- Pro Tool: Aufruf-Häufigkeit (30d), Description-Länge, last-touched,
  Doppelungen (z.B. mehrere `flow_*`-Tools mit ähnlicher Funktion)
- Tool-Schemas: Pflicht-Felder konsistent? Beispiele aktuell?
- Was kann konsolidiert werden ohne Funktionsverlust?

### Format der Session

User liest mit, Disco bringt Material in **kompakten Tabellen** pro
Bereich. Pro Item: User-Entscheidung in einem Wort
(behalten / straffen / streichen / mergen-mit-X).

Danach Umsetzung als eigener Block, ähnlich wie Phase-2-Blöcke:
einzelne Streichungen + Neuformulierungen + agent-setup-Push.

### Erwartete Effekte

- System-Prompt-Volumen: -25 bis -30 % (Audit-Schätzung)
- Skill-Liste: -1 bis -3 Skills (oder konsolidiert)
- Tool-Liste: -3 bis -5 Tools (Doppelungen + tote Pfade)
- Klarere Trigger-Tabelle, weniger Konflikte zwischen Skills

### Erfolgs-Kriterien

- Dev-Chat-Smoketest: typische Use-Cases (sources_register,
  flow_run, excel-report) laufen weiterhin sauber
- Token-Verbrauch pro Turn sinkt mit kürzerem Prompt
- Subjektiv: Disco wirkt fokussierter, weniger ablenkbar

### E2E-Test-Befunde (aus Full-Test 2026-05-07, Szenarien 01+02)

Aus dem ersten gemeinsamen Full-Test (User schaut zu, Claude
fuehrt Disco im Browser) sind folgende Material-Punkte fuer die
Review-Session entstanden. Siehe `tests/e2e/scenarios/01-source-onboarding.md`
und `tests/e2e/scenarios/02-pipeline-fulltest.md` fuer Drehbuch
und Beobachtungen.

**Befund 1 — Skill `project-onboarding`, FS-Inhalt unsichtbar:**
Bei "kurz orientieren" macht Disco `fs_list` nur top-level (sieht
sources/ und context/ als dirs). Wenn `agent_sources` leer ist,
schliesst er falsch auf "leer" — obwohl FS gefuellt sein kann (vor
Erst-Scan ist Registry IMMER leer). Skill ergaenzen: vor Bericht
ueber Quellen/Kontext rekursives `fs_list` machen, oder explizit
"noch nicht registriert" sagen statt "leer".

**Befund 2 — System-Prompt, Register zaghaft:**
Auf "Ja, leg mal los. Was haben wir denn fuer Dateien?" hat Disco
nur gelistet, nicht registriert — fragt nochmal. Erst auf "Ja, mach
mal." kommt das `sources_register`. `list_skills` ja,
`load_skill('sources-onboarding')` aber nicht. Trigger schaerfen:
"User sagt 'los/leg los/mach mal' + sources/ enthaelt unregistrierte
Files → direkt sources-onboarding-Skill laden + sources_register".

**Befund 3 — Routing-Heuristik bei A3-Plaenen:**
`02_schaltplan_a3.pdf` (727 KB, A3) wurde mit `pdf-azure-di`
geroutet, nicht `pdf-azure-di-hr`. A3-Grossformate sollten HR
triggern. Schwellenwert in `src/disco/docs/routing.py` pruefen
(`max_page_width_pt > X` → HR). Liegt am Rand, koennte Tunable sein.

**Befund 4 — Excel-Reporter, nur eine Statusspalte einfaerbbar:**
`build_xlsx_from_tables` faerbt im Standard-Modus genau eine Spalte
rot/gruen. SOLL/IST-Reports brauchen oft mehrere Statusspalten
(z.B. Datenblatt / Statusnachweis / Schild / Berichtserwaehnung).
Disco kommuniziert das transparent und bietet openpyxl-Custom-Pfad
an. Reporter-Skill um `n` Statusspalten erweitern, oder im
`excel-reporter`-Skill klar dokumentieren wann Custom-Weg.

**Befund 5 — Failure-Triage, "alle" wird auf "gleicher Pfad" reduziert:**
Bei 3 failed Files (07/10 DWG-libredwg, 09 Azure-DI-PDF) hat Disco
auf "retry sie nochmal" nur die 2 DWGs angefasst, das PDF nicht.
Inhaltlich nachvollziehbar (Server-Fehler retryt sich anders als
Engine-Crash), aber User-"alle" wurde implizit gefiltert.
System-Prompt-Diskussion: bei Mehrfach-Failure-Modi soll Disco
explizit fragen oder alle anpacken?

**Befund 6 — Failure-Zusammenfassung nicht in Tabelle:**
Auf "kannst Du die mal kurz zusammenfassen mit Grund" kam keine
Tabelle, sondern direkt die Retry-Aktion + Fliesstext-Bilanz. Bei
anderen Reasoning-Aufgaben gibt Disco saubere Tabellen aus. Skill
`pipeline-diagnostics` ergaenzen: Failure-Liste **immer** als
`rel_path / engine / retry_count / Grund`-Tabelle vor jeder Aktion.

**Befund 7 — DWG 07 (generische DWG aus Prod) failt mit libredwg:**
Laut MANIFEST sollte 07_grundriss.dwg parseable sein (open verfuegbare
DWG). libredwg crasht aber mit `dwg2dxf-SIGABRT`. Entweder DWG-
Format zu modern (DWG2018+?) fuer libredwg, oder Datei doch korrupt.
Nicht E2E-Stopper (Skipped wuerde sauber laufen), aber Pool-Slot
austauschen oder libredwg-Version updaten. Gehoert nicht in die
Review-Session — separater Engine-Pfad-Befund.

**Befund 8 — Indexer-Race: `build_search_index` waehrend Extraction:**
Beim Pipeline-Vollauslauf hat Disco `build_search_index` getriggert,
**bevor** der `extraction`-Flow alle Items abgearbeitet hatte. Folge:
6 von 9 ok-extrahierten Files landeten im Index, 3 (08/11/14a) fehlen
weil ihr `agent_doc_markdown`-Eintrag zum Index-Zeitpunkt noch nicht
existierte. Ein zweiter Indexer-Lauf wuerde sie nachziehen. Heute hilft
nur ein zweiter Indexer-Aufruf. Loesungsvorschlaege:
1. **Skill `pipeline-diagnostics`-Erweiterung:** wenn
   Suchindex-Status < extracted-canonical, dann automatisch re-index
   anbieten ("3 Files fehlen im Index, soll ich nachindizieren?").
2. **Hard-Sync in Disco-System-Prompt:** `build_search_index` darf
   erst nach `flow_status==done` des laufenden `extraction`-Runs
   gerufen werden.
3. **Indexer-Selbst-Aware:** `build_search_index` koennte am Anfang
   pruefen, ob ein `extraction`-Run aktiv laeuft, und auf das Ende
   warten oder warnen.
Ampel-Endpoint zeigt die Inkonsistenz jetzt korrekt an (vorher hatte
er 07/10 mit char_count=0 als "indexed" mitgezaehlt — Fix:
n_indexed_canonical filtert auf `error IS NULL AND char_count > 0`,
siehe Commit am 2026-05-07).

---

## Release / DevOps

### Foundry-Chain-Invalidation bei Code-Update (Prio: hoch — gilt fuer naechsten Pipeline-Code-Change)

**Symptom 2026-05-07 (lager-halle, Prod):** Nach Deploy von
Compaction-v3 (`e7e5382` — Tool-Output-Truncation in
`build_responses_api_input`) crashte der naechste User-Turn mit
Foundry-Fehler `400: No tool output found for function call
call_<id>`. Alle DB-Eintraege waren sauber gepaart; Ursache war der
Foundry-Server-State unter `previous_response_id`, der noch das alte
volle Output-Format erwartete und beim neuen truncated Format aus
unserem Input nicht matchte.

**Reparatur damals**: per Hand SQL-Update auf `project_chat_state`
auf Prod **und** Dev — `foundry_response_id`,
`measured_context_tokens`, `measured_at`, `measured_model`,
`measured_cached_tokens` auf NULL fuer alle Projekte mit aktiver
Chain (8 Prod, 12 Dev). Naechster Turn lief Stateless durch, Foundry
hat frische response_id vergeben, alles sauber.

**Was aufzubauen ist:**

- **Format-Version-Tracker:** im Code von `build_responses_api_input`
  eine Konstante `INPUT_FORMAT_VERSION` halten. Bei strukturellen
  Aenderungen am Input-Format (Truncation-Logik, neue Item-Types,
  geaenderte Reihenfolge) wird die hochgezaehlt.
- **DB-Spalte `project_chat_state.input_format_version`** — wird beim
  Schreiben einer `foundry_response_id` mitgespeichert.
- **Lese-Zeit-Check:** wenn `input_format_version != INPUT_FORMAT_VERSION`,
  wird `foundry_response_id` ignoriert (Stateless-Modus erzwingen) und
  beim naechsten erfolgreichen Turn neu gesetzt.

**Alternativ einfacher** (Migration-Hook): jede Migration, die
`build_responses_api_input` oder die Persistenz-Schicht aendert,
laesst ein `UPDATE project_chat_state SET foundry_response_id=NULL`
mitlaufen. Weniger elegant, aber sicher.

**Wichtig**: Nicht in der Naehe der Memory-Architektur-Reform (TOP-2)
liegen lassen — die wird vermutlich auch Persistenz-Format
veraendern und triggert sonst denselben Crash. Vor der Memory-Reform
fertig haben.

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

## Skill-Library mit Daten-Paket — projektuebergreifend (Prioritaet: mittel, strategisch)

**User-Idee 2026-05-08:** Skills sollen vom *Workflow-Playbook*
(heute Markdown) zum *Workflow + Daten-Paket* werden. Eine Norm wie
**VGB S 831** lebt nicht nur als „so pruefst Du gegen die Norm"-
Anleitung, sondern bringt die Norm-Tabellen (DCC-Codes,
Anforderungen, Klassen) gleich mit. Skills werden so zur
projektuebergreifenden Wissens-Library — einmal pflegen, in jedem
Projekt einheitlich nutzen.

**Use-Cases (User-Vision-Doku 2026-05-07 verweist):**

- `vgb-s-831` — Dokumentations-Standard, DCC-Codes + Anforderungen
- `kks-rds-pp` — KKS-/RDS-PP-Hierarchie fuer Kraftwerks-Klassifikation
- `din-ibl` — DIN-Informations-Bedarfs-Listen
- `legal-fidic` — FIDIC-Klauseln + Notification-Pflichten
- `qm-endkontrolle` — QM-Checklisten
- `claim-trail` — Klausel-bezogene Korrespondenz-Strukturen

### Architektur-Skizze (zur Diskussion, nicht final)

Skills werden vom Single-File zum Verzeichnis:

```
skills/vgb-s-831/
├── SKILL.md              ← Frontmatter + Workflow-Anweisungen
├── data/
│   ├── vgb_dcc_codes.csv
│   ├── vgb_anforderungen.csv
│   └── vgb_klassen.csv
└── docs/
    └── normbezug.md      ← Quellen, Versionen, Aenderungshistorie
```

Frontmatter erweitert um `provides`-Block:

```yaml
name: vgb-s-831
version: 1.2.0
description: VGB S 831 — Dokumentations-Anforderungen
provides:
  tables:
    - name: context_skill_vgb_s_831_dcc_codes
      source: data/vgb_dcc_codes.csv
      schema: { dcc_code: text, beschreibung: text, gewerk: text }
    - name: context_skill_vgb_s_831_anforderungen
      source: data/vgb_anforderungen.csv
```

`load_skill` macht dann mehr als Markdown-Read:

1. Schaut in der Projekt-DB nach `context_skill_<skill>_<table>`.
2. Wenn fehlt → importiert aus `data/`.
3. Wenn da, aber Skill-Version niedriger als verfuegbar → fragt User
   („Update auf 1.2.0?").
4. Liefert Markdown + Tabellen-Hint (aktueller Tabellen-Stand,
   Beispielzeilen).

### Verbindung zu bestehenden Themen

- **Memory-Architektur-Reform (TOP-3)** — der „Tabellen-Wissen-bei-
  Tabellen"-Punkt steckt direkt drin. Wenn jede Tabelle ihre eigene
  Beschreibung mitbringt (Schema-Comment / `agent_table_docs` /
  `_doc.md`), ist eine Skill-mitgelieferte Tabelle mit ihrer eigenen
  Doku natuerlich konsistent. **Memory-Reform ist Voraussetzung.**
- **Public-Workspace (oben)** — Skill-Library als konkrete
  Anwendung. Skill-Daten koennen entweder pro Projekt importiert
  werden (heute-naehe) oder aus `_public/data.db` per ATTACH gelesen
  (Public-Workspace-Stufe 3).
- **Vision-Doku** — die fuenf neuen Domain-Bereiche (Legal/Claim/
  Contract/QM/Termin) sind genau dieses Muster: Domain-Skill mit
  Klausel- bzw. Norm-Tabelle.

### Risiken / offene Fragen

| # | Frage | Klaerungsweg |
|---|---|---|
| 1 | **Lizenz/Copyright** bei VGB S 831 + DIN. Auszuege (DCC-Codes, Klassen) vermutlich vertretbar, **Volltext** der Anforderungen kritisch. Pro Skill abklopfen. | rechtliche Pruefung pro geplantem Skill, **bevor** wir Inhalte committen |
| 2 | **Daten-Groesse + Repo-Bloat** — viele Skills à 10 MB schwellen das Repo. | Groessen-Limit setzen (z.B. < 5 MB pro Skill); grosse Skills aus `_public/`-Workspace laden statt aus Repo |
| 3 | **Update-Strategie** — bei Norm-Aenderung von v1.1 → v1.2 in laufenden Projekten. Drei Optionen: manuell, automatisch, Pinning. | mit User entscheiden; **Pinning + User-Frage bei Diff** ist Default-Vorschlag |
| 4 | **Cross-Skill-Daten-Konflikte** — zwei Skills wollen `context_kks` belegen. | Tabellen-Prefix `context_skill_<skill>_<table>` Pflicht |
| 5 | **Projekt-Override** — Kunde hat angepasste Norm-Tabelle. | Skill-Tabellen sind read-only nach Import; Projekt darf eigene `context_<table>` daneben pflegen, hat Vorrang in Queries |
| 6 | **Egress-Policy** (CLAUDE.md) — wenn Skills aus externer Cloud nachgeladen werden, neue Egress-Verbindung. Heute lokal-first. | Default: alles im Repo. Externe Quellen nur mit explizitem User-OK + Egress-Policy-Update. |
| 7 | **Test-Aufwand** — pro Skill Migrations-Test + Daten-Validierungstest. | lohnt erst ab ~3-5 datentragenden Skills; vorher nur ein Pilot. |

### Vorgehen (vorgeschlagene Reihenfolge)

1. **Memory-Architektur-Reform (TOP-3) zuerst** — denn Tabellen-Doku-
   Format wird dort entschieden.
2. **Pilot-Skill `vgb-s-831`** — ein Skill bauen, einbauen, an einem
   Projekt validieren. Lizenz vorher klaeren.
3. **`load_skill`-Tool erweitern** um Daten-Import + Versions-Check.
4. **Standardisierung als Block** (analog Phase-2-Bloecke) erst
   nach erfolgreichem Pilot.

### Klaerungsbedarf an User (vor finaler Spezifikation)

- Lizenz-Status VGB S 831 + DIN-Normen — eigene Pruefung oder Auszug
  reicht?
- Update-Strategie: Pinning per Default oder Auto-Upgrade-Frage?
- Erwartete Anzahl Skills (3, 10, 30+?) — beeinflusst stark, ob
  „internes Skill-Verzeichnis" reicht oder Plugin-System noetig.
- Memory-Reform vs Skill-Library zeitlich getrennt oder zusammen?

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


## ★ Data-Lineage + Daten-Architektur Ebene 3 (TOP — Konzept-Diskussion offen, konsolidiert 2026-05-07)

**Konsolidiert 2026-05-07** — diese zwei Themen sind eng verflochten und
werden gemeinsam bearbeitet:

1. **Lineage** (woher kommen Artefakte, mit welcher Logik, wozu)
2. **Schichten-Architektur** (Ebene 1 Provenance, Ebene 2 Content, Ebene 3 Auswertung)

Disco verzettelt sich nach mehreren Arbeitsschritten in der Datenhaltung,
weil `work_*`-Tabellen ohne Lifecycle-Konzept akkumulieren und Lineage
(Source → Transform → Output) nicht zentral festgehalten ist. Nächster
Schritt: gemeinsame Konzept-Session mit User.

---

### Teil A — Data-Lineage / Tracing fuer abgeleitete Artefakte

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


---

### Teil B — Datenverarbeitung auf Ebene 3 strukturieren

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


## User-Feedback-Cluster aus 24 bad-Reactions (Prioritaet: hoch)

**Quelle**: `chat_message_feedback`-Tabelle in system.db. Zeitraum
22.04.–27.04.2026. **24 bad** + 7 good Reactions, davon 23 mit
Kommentar. Direkter, validierter User-Pain — nicht spekulativ.

13 Themen-Cluster, einige bestaetigen bereits geplante Backlog-
Eintraege, andere sind neu.

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
- *"Bug: die context dateien wollen wir ja genau so registrieren und einlesen."* (msg 1668) — ✅ **GEFIXT 2026-05-05** (Commit 03eaf9d, sources_register Default-Scope `both`)
- *"Disco fängt an links zu verwenden, das ist gut und genau da will ich auch hin - nur funktioniert dieser noch nicht."* (msg 1601) — ✅ **GEFIXT 2026-05-04** (Klickbare Links Phase 1, Commit fd99728)

**Verbesserung (offen):**
1. **File-Notes-Tabelle** `agent_source_notes` (oder Spalten in
   agent_sources):
   ```sql
   purpose      TEXT  -- "Norm fuer SOLL/IST-Abgleich"
   origin       TEXT  -- "vom GU geliefert 2026-04-15"
   usage_intent TEXT  -- "Nachschlagewerk bei Klassifikation"
   ```
   Beim context-Onboarding-Skill werden diese 3 Felder ad-hoc gefragt.
   Persistent in der DB statt im Memory-Markdown.
2. **Hyperlink-Fix in Excel-Exports** — siehe Cluster L (offen).

Bezug: ergaenzt File-Internal-Metadata-Eintrag (eingebettete Metadaten)
um User-erstellte File-Annotations.

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
1. ✅ **Teilweise erledigt 2026-05-07**: `pdf_classify`-Tool entfernt
   (Phase 2 Block A, Commit 4b086f7). `agent_pdf_inventory` wird
   im Pipeline-Status-Endpoint nicht mehr referenziert (Bugfix
   2026-05-05, Commit 15ee0c2). Cleanup der Tabelle bleibt offen
   — geht ins ★-Konsolidat Phase 3.
2. **Skill-Sprache anpassen**: in disco/system_prompt.md /
   Skills, wenn von "Dokumenten" gesprochen wird, soll die
   Antwort alle file_kinds umfassen. Default "Dateien" =
   alles, nicht nur PDFs.

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
