# Akzeptanzkriterien — Dokumente klassifizieren nach Kunden-Schema

**Zum Szenario:** siehe `scenario.md`.

**Lesen als Checkliste:** Jede Phase hat harte und weiche Kriterien. Harte
Kriterien muessen alle erfuellt sein, sonst ist die Phase nicht bestanden.
Weiche Kriterien sind Hinweise auf Qualitaet — eine Haeufung ist ein Signal,
dass Disco nicht "genug" autonom ist, auch wenn die harten Kriterien formal
passen.

**Automatisierungs-Hinweis:** Jedes Kriterium ist so geschrieben, dass es
per SQL-Query, `fs_list`, Log-Inspektion oder JSON-Validation maschinell
geprueft werden kann. Die Hinweise in Klammern `→ Check: ...` zeigen den
vorgesehenen Pruefweg.

## Kriterien ueber alle Phasen (Gesamtbedingungen)

**Hart:**

- [ ] Keine UAT-Bugs #1-#5 treten wieder auf.
  → Check: neuer Eintrag in `~/Disco/uat-bug-log.md` mit Datum > 2026-04-18.
- [ ] Keine User-Nudge-Messages waehrend des Laufs (z.B. "leg los",
  "warum hast du nicht...?", "weiter").
  → Check: `chat_messages` im Thread nach Keyword-Pattern scannen.
- [ ] Keine offenen Tool-Calls am Ende — jeder Tool-Call hat einen
  dazugehoerigen Tool-Result.
  → Check: SQL auf `chat_messages.tool_calls_json` vs `tool_results_json`.

**Weich:**

- Disco bringt den Nutzer mit unter ~4 Messages pro Phase ans Ziel.
- Zwischen-Stati (vor laenger laufenden Flows) von sich aus gemeldet.

## Phase 1 — Projekt-Onboarding

**Hart:**

- [ ] `project-onboarding` Skill wurde geladen.
  → Check: `load_skill` mit `name='project-onboarding'` in den Tool-Calls
  des Threads.
- [ ] Alle PDFs unter `sources/` sind in `agent_sources` registriert.
  → Check: `SELECT COUNT(*) FROM agent_sources WHERE status='active' AND
  extension='pdf'` == Anzahl Dateien im Ordner.
- [ ] Klassifikations-Katalog ist als `context_*`-Tabelle in der Projekt-DB.
  → Check: `SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND
  name LIKE 'context_%'` >= 1 und die Tabelle hat plausible Zeilenzahl
  (grob: fuer DCC etwa 300-500 Codes).
- [ ] `.disco/memory/activeContext.md` oder `NOTES.md` hat einen Eintrag
  zum aktuellen Stand (Next Steps genannt).
  → Check: `fs_read` und prueft auf Datum-Header.

**Weich:**

- Disco zaehlt dem Nutzer in der Antwort Anzahl PDFs + Anzahl Katalog-Zeilen
  auf — nicht nur "ist erledigt".
- `context/_manifest.md` oder Aehnliches ist gepflegt.

## Phase 2 — PDF → Markdown Flow

**Hart:**

- [ ] `sdk-reference`-Skill wurde **vor** dem ersten DI-Call geladen.
  → Check: `load_skill('sdk-reference')` in Tool-Calls, Timestamp vor erstem
  Flow-Item.
- [ ] `runner.py` enthaelt echten Code, keinen TODO-Stub.
  → Check: `fs_read` des Runners, dann Regex-Suche: kein Vorkommen von
  `# TODO` im Block der DI-Logik; `begin_analyze_document` ist tatsaechlich
  aufgerufen; import ist `from azure.ai.documentintelligence import
  DocumentIntelligenceClient`.
- [ ] Mini-Run ist ueber `flow_run(...)` gestartet, **nicht** ueber
  `run_python(...)`.
  → Check: `SELECT COUNT(*) FROM agent_flow_runs WHERE flow_name LIKE
  '%markdown%'` >= 1; und keine `run_python`-Calls mit DI-Code im Thread.
- [ ] Keine Halluzinations-Imports im Runner.
  → Check: Runner enthaelt NIE `from disco.services`, `from disco.utils.di` o.ae.
- [ ] Voll-Run ist erfolgreich abgeschlossen (`status='done'`), keine
  `failed` Items ausser erklaerbaren Ausnahmen.
  → Check: `SELECT status, failed_items FROM agent_flow_runs ORDER BY id
  DESC LIMIT 1`.
- [ ] Markdown-Dateien existieren fuer jede PDF.
  → Check: `fs_list` auf Output-Verzeichnis (`.disco/source-extracts/` o.ae.)
  ergibt eine Datei pro registrierter PDF.

**Weich:**

- Disco berichtet Kennzahlen (Seiten/Chars) nach Mini-Run, nicht nur
  "fertig".
- Kein `pages=null` in den Item-Outputs (Disco liest `result.pages`
  korrekt).
- Kostenschaetzung vor Full-Run genannt.

## Phase 3 — Klassifikations-Flow

**Hart:**

- [ ] Klassifikator nutzt `response_format={"type": "json_schema", ...}`
  mit `strict: True`.
  → Check: Runner-Code enthaelt `"json_schema"` und `"strict": True`.
- [ ] Schema-Felder matchen den Klassifikations-Prompt aus `context/`
  (Feldnamen, Enum-Werte).
  → Check: Prompt-Parser extrahiert die Feldliste; Runner-Schema deckt
  alle Pflichtfelder.
- [ ] Ergebnis landet in einer `agent_*`-Tabelle, eine Zeile pro Dokument,
  UNIQUE per `rel_path`/`source_id`.
  → Check: `SELECT COUNT(DISTINCT source_id) FROM agent_<tabelle>` ==
  `SELECT COUNT(*) FROM agent_sources WHERE status='active' AND
  extension='pdf'`.
- [ ] Budget-Limit war gesetzt, Full-Run hat es nicht ueberschritten.
  → Check: `agent_flow_runs.total_cost_eur <= config_json.budget_eur`.

**Weich:**

- Konfidenz-Score ist nicht uniform (0.8 bei allem) — Disco trifft
  differenzierte Entscheidungen.
- Mini-Run-Beispiele wurden dem Nutzer inhaltlich gezeigt (nicht nur
  Statistik).

## Phase 4 — Excel-Export

**Hart:**

- [ ] `excel-reporter`-Skill wurde geladen.
  → Check: `load_skill('excel-reporter')` in Tool-Calls.
- [ ] Excel-Datei existiert unter `exports/`, Dateiname mit Datum.
  → Check: `fs_list('exports/')` ergibt `.xlsx` mit heutigem Datum.
- [ ] Mindestens zwei Sheets (z.B. "Klassifikation" + "Uebersicht") oder
  sinnvolle Multi-Sheet-Struktur.
  → Check: openpyxl oeffnet, `wb.sheetnames` hat >= 2 Eintraege.
- [ ] Header formatiert (fett), AutoFilter aktiv.
  → Check: openpyxl prueft `ws.auto_filter.ref` und Header-Styles.

**Weich:**

- Farbcodierung nach Konfidenz oder Gewerk (wie im IBL-Vorbild).
- Hyperlinks von der Uebersicht in die Detail-Sheets oder zu den
  Ursprungs-PDFs.

## Nicht-Funktional — Durchlaufzeit + Ressourcen

**Hart:**

- [ ] Keine Item in der DB haengt auf `running` nach Ende des Gesamtlaufs.
  → Check: `SELECT COUNT(*) FROM agent_flow_run_items WHERE status='running'`
  == 0.
- [ ] Kein Worker-Prozess als Zombie im System.
  → Check: `ps aux | grep runner_host` ergibt nur den aktiven (falls ein
  Run laeuft) oder nichts.

**Weich:**

- Gesamt-Laufzeit liegt in der Groessenordnung, die aus den Mini-Run-Daten
  extrapoliert wurde (Faktor <2).

## Versionen

- v1 — 2026-04-18 — initiale Fassung, abgeleitet aus erstem UAT.
