---
name: flow-builder
description: Gemeinsam mit dem Nutzer einen Flow aufbauen, testen, starten und überwachen — für Massenverarbeitungen mit 10, 100 oder 10.000 Items.
when_to_use: "bulk", "10.000 Dokumente", "alle Dateien klassifizieren", "Flow bauen", "Pipeline aufsetzen", "verarbeite alle", wenn eine Aufgabe über mehr als ~10 Items geht ODER wenn sie über mehrere Minuten laufen würde.
---

# Skill: flow-builder

Dieser Skill ist Dein Leitfaden, um **mit dem Nutzer zusammen** einen
Flow zu entwickeln: vom Zweck-Gespräch bis zum überwachten Full-Run
über Stunden. Flows sind für Aufgaben da, die:

- **viele Items** haben (> 10, oft hunderte bis tausende)
- **lang laufen** (über 2 Minuten)
- **pro Item einen gleichartigen Arbeitsschritt** machen
- **idempotent** sein sollen (Resume-fähig)

**Wann NICHT Flow:** einzelne Analysen, einmalige Berechnungen,
schnelle Checks — dafür reichen `run_python` oder direkte SQL.

## Die fünf Phasen

| Phase | Wer treibt | Was passiert |
|---|---|---|
| 1. Zweck | Du + Nutzer | Klären, was der Flow tun soll und was raus muss |
| 2. Bau | Du (Nutzer review) | flow_create → README + runner.py konkret ausarbeiten |
| 3. Test | Du | Test-Run mit `limit=5`, Ergebnisse prüfen |
| 4. Optimieren | Du + Nutzer | Prompt/Code anpassen bis Stichprobe passt |
| 5. Full-Run | Du startest, überwachst | Run mit Budget-Limit, periodischer Status-Check |

## Phase 1 — Zweck klären

Bevor Du `flow_create` rufst, klär mit dem Nutzer **konkret**:

1. **Was ist der Input?**
   - Welche Tabelle (meist `agent_sources`)?
   - Welcher Filter? (z. B. „alle PDFs mit fehlender Klassifikation")
   - Welches Feld enthält den Inhalt? (Datei? Markdown-Extrakt?)

2. **Was ist der Output?**
   - Welche Felder pro Item? (z. B. DCC-Code, Konfidenz, Begründung)
   - Wohin? (generisches `output_json` reicht meist — typisierte
     Tabelle kann Disco später per SQL ableiten)

3. **Externe Dienste?**
   - Pure Python (0 €)? Azure DI (~0,01 €/Seite)? LLM?
   - Wenn LLM: welches Modell, welcher Prompt-Kern?

4. **Fehlerbehandlung?**
   - Was bei einzelnen fehlgeschlagenen Items — Retry, Skip, Abort?
   - Bei welcher Fehlerrate soll der Run pausieren?

5. **Kostenschätzung (bei externen Diensten pflicht)?**
   - Pro Item: X € geschätzt
   - Gesamt: Y € bei N Items
   - Hart-Limit: Z € — bei Überschreitung pausiert der Worker

**Frage gezielt**, nicht offen. Beispiel:

> „Bevor ich den Flow anlege, vier Punkte:
> 1. Input ist `agent_sources` mit `flow_trigger_dcc=1` — korrekt?
> 2. Output soll DCC-Code, Alternative, Bereich, Begründung als JSON —
>    reicht Dir das, oder willst Du zusätzlich Konfidenz?
> 3. Bei Timeout pro Item: 3× Retry oder gleich skippen?
> 4. Budget-Limit für den Test-Run: 2 €, für den Full-Run: 15 € —
>    passt das?"

## Phase 2 — Flow bauen

```text
flow_create(flow_name='<sluggen>')
```

Der Ordner + Skelett-Dateien entstehen. Dann lese und passe an:

```text
fs_read({"path": "flows/<name>/README.md"})
```

→ Schreibe die README um, so dass sie **dem gemeinsamen Gespräch
entspricht**: alle Punkte aus Phase 1 rein, plus den Abschnitt
„Entscheidungen" mit den konkreten Abstimmungen („am YYYY-MM-DD:
Nutzer entschied X"). Danach:

```text
fs_write({"path": "flows/<name>/README.md", "content": "..."})
```

Dann den `runner.py`:

```text
fs_read({"path": "flows/<name>/runner.py"})
fs_write({"path": "flows/<name>/runner.py", "content": "..."})
```

**Tipps für den Runner:**
- Input-Query ist flow-spezifisch — wenn der Nutzer eine Queue-Logik
  will (z. B. Spalte `flow_trigger_dcc`), baue die direkt ins SQL.
- Für LLM-Calls: nutze `response_format=json_schema` — dann entfällt
  eigenes JSON-Parsing.
- Pro Item: `run.add_cost(eur=..., tokens_in=..., tokens_out=...)`
  aufrufen, damit Budget-Limit greift.
- Bei Datei-Operationen: `run.read_file(rel_path)` bleibt im Projekt.

## Phase 3 — Test-Run

**Immer** mit kleiner Stichprobe beginnen:

```text
flow_run(flow_name='<name>', title='Test-Run 5 Items', config={'limit': 5, 'budget_eur': 2})
```

Dann warten (1-2 Sekunden), Status prüfen:

```text
flow_status(run_id=<id>)
flow_items(run_id=<id>, limit=5)
```

**Akzeptanzkriterien** aus der README durchgehen:
- Sind alle 5 Items `done`? (Kein `failed`/`skipped` erwartet?)
- Stichprobe 1-2 Items: passt der Output zum erwarteten Schema?
- Für LLM-Flows: ist die Antwort **plausibel** (nicht „lorem ipsum",
  nicht halluziniert)? Korreliert Begründung zum Input?
- Waren die Kosten im erwarteten Rahmen?

Zeige dem Nutzer **konkrete Beispiele** aus den Test-Items:

> „Bei `Elektro/Schaltplan_A1.pdf` hat der Flow DCC=`FA010` mit
> Konfidenz 0,87 ermittelt, Begründung: 'Übersichtsschaltplan mit
> Schaltschrank-Symbolen'. Bei `Bauwerk/Statik.pdf` kam `TB040`
> (Konfidenz 0,72) — wirkt beides richtig. Soll ich Full-Run starten?"

## Phase 4 — Optimieren

Wenn der Test nicht gut läuft:

- **Schlechte Klassifikation:** Prompt präziser formulieren
  (mehr Beispiele, klarere Kategorien, Negativ-Beispiele). README
  + runner.py anpassen, neuen Test-Run starten.
- **Hohe Fehlerrate:** Logs ansehen (`flow_logs`), Exception-Typ
  bestimmen. Retry-Strategie anpassen oder Input filtern.
- **Zu teuer:** Markdown stärker trimmen, kleineres Modell,
  günstigere API.
- **Zu langsam:** parallele Worker (nicht MVP), oder
  Pre-Processing extrahieren (DI einmal, dann viele LLM-Calls
  auf cached Markdown).

**Nach jeder Anpassung eine neue „Entscheidung"-Zeile in die README.**
Das ist Protokoll, kein Kommentar.

Danach: **neuer Test-Run mit anderem Titel**. Nicht den alten Run
nochmal starten — der würde ja done-Items überspringen und die
Änderung nicht testen.

## Phase 5 — Full-Run + Überwachung

Wenn der Nutzer „grünes Licht" gibt:

```text
flow_run(flow_name='<name>', title='Full-Run 2026-04-18',
         config={'budget_eur': 15})
```

Der Worker läuft jetzt im Hintergrund. Du kehrst zurück in den Chat.

**Während des Laufs:**

1. Periodisch `flow_status(run_id=...)` abfragen (nicht öfter als
   alle 30 Sekunden — der Nutzer will keine Ticker-Sicht).
2. Wenn der Nutzer fragt „wie weit?": ein kompakter Statusbericht:

> „Run 12, Full-Run DCC-Klassifikation. 342/493 Items durch
> (69 %), 4 failed, bisher 5,80 € Kosten. Geschätzt noch ~45 min.
> Keine Anomalien."

3. **Bei Anomalien aktiv alarmieren:**
   - Fehlerrate > 10 %: `flow_pause(run_id=...)`, dann dem Nutzer
     die letzten Fehler aus `flow_items(run_id=..., status='failed')`
     zeigen und Vorschlag machen.
   - Kosten eskalieren schneller als erwartet: pause, nachrechnen.
   - Output-Verteilung ist sehr einseitig (90 % eine Kategorie):
     pause, Stichprobe zeigen, Plausibilität mit Nutzer prüfen.

4. **Bei Abschluss:**
   - Status = `done` melden.
   - Kompakte Zusammenfassung mit SQL-Aggregation (aus README):
     Anteile pro Kategorie, Fehlerquote, Kosten.
   - Nächsten Schritt anbieten (z. B. Excel-Export über
     `build_xlsx_from_tables`, oder Review der failed-Items).

## Fehlerfälle

| Symptom | Vorgehen |
|---|---|
| `flow_create` sagt „bereits existiert" | OK, idempotent. `flow_show` → pass ggf. README an. |
| Test-Run sofort failed | `flow_logs` → Exception lesen → Code fixen |
| Worker reagiert nicht auf pause | Kann passieren, wenn ein Item gerade lang rechnet. Warte ~2 Sekunden. Wenn immer noch: `flow_cancel(..., force=true)` |
| Resume nach Crash | Einfach neuen Full-Run starten mit gleichem `flow_name`. Done-Items werden übersprungen. |

## Wichtig — was Du NICHT machst

- **Keine 10.000 Items per `run_python`.** Das killt den Chat-Turn.
  Sobald es mehr als ~10 Items werden → Flow.
- **Keine LLM-Bulk-Klassifikation im Chat-Turn.** Tool-Rundungen sind
  auf 48 begrenzt; ab 100 Items bist Du schnell am Limit.
- **Kein Full-Run ohne Test-Run**. Selbst bei einfachen Datentransforms:
  erst 5 Items probeln, dann alle.
- **Kein LLM-Flow ohne Budget-Limit.** Das ist die Sicherung gegen
  Runaway-Kosten.
