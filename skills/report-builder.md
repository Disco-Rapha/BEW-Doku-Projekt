---
name: report-builder
description: HTML-Reports zum Weitergeben bauen — Single-File-Output, klickbare Quellen, wiederverwendbarer Bauplan im Projekt.
when_to_use: "HTML-Report", "Report bauen", "Auswertung als HTML", "Report zum Weitergeben", "SOLL/IST-Report (HTML)", "IBL-Report", "Management-Report". Für formatierte Excel-Exports → stattdessen `excel-reporter`.
---

# Skill: report-builder

**Für lesbare HTML-Reports**, die der Nutzer im Browser öffnet und
per Mail weitergibt. Kein Excel, kein Dashboard, kein Live-System.
Ein einziger `.html`-Snapshot pro Report-Run, mit klickbaren Quellen
und einer Sources-Sektion am Ende.

**Für formatierte Tabellen-Exports** (AutoFilter, Status-Farben,
Hyperlinks zwischen Sheets) → stattdessen Skill `excel-reporter`.

## Eiserne Regeln

1. **Single-File-HTML.** CSS, JS, Daten — alles **inline** in einer
   `.html`-Datei. Per Doppelklick öffenbar oder als Mail-Anhang
   versendbar, ohne Server, ohne externe Assets.
2. **Python-Skript baut das HTML, nicht Du im Chat.** Du schreibst
   ein `build_<slug>.py`, `run_python` führt es aus. Bauplan
   reproduzierbar, Chat-Kontext klein.
3. **Wiederverwendung zuerst.** Vor dem Schreiben eines neuen
   Skripts: in `exports/reports/` prüfen, ob ein ähnlicher Report
   schon existiert. Wenn ja: Skript kopieren, Queries + Texte
   anpassen — nicht bei Null anfangen. Look bleibt einheitlich.
4. **Traceability ist nicht optional.** Jeder Report endet mit
   *„Quellen & Methodik"*. Jede wesentliche Aussage (KPI-Zahl,
   Narrative mit Dokumenten) hat einen klickbaren Anker.
5. **Tool-Result = Wahrheit.** „Fertig" meldest Du erst, wenn
   `run_python` mit `exit_code == 0` zurückkommt und
   `report.html` real existiert.

## Pfad-Konvention

```
<projekt>/exports/reports/<slug>/
  build_<slug>.py       ← das Bau-Skript (der "Bauplan")
  report.html           ← letztes Ergebnis (wird überschrieben)
  data/                 ← optional: generierte Zwischendaten
```

**Slug-Naming:** `<thema>-<variante>`, keine Datumsstempel im Slug.
Beispiele: `ibl-soll-ist`, `dcc-verteilung`, `dokumenten-lieferstatus`.
Datum + Version stehen **im Report-Inhalt** (Titelzeile), nicht im
Pfad. Default ist Überschreiben — die Reproduzierbarkeit liegt im
Skript, nicht in Snapshots. Wenn vorherige Version aufgehoben werden
soll: vor Re-Lauf nach `v<N>/report.html` kopieren.

## Die drei Phasen

| Phase | Wer treibt | Was passiert |
|---|---|---|
| 1. Auftrag | Du + Nutzer | Ziel, Daten, Kernaussagen, Zielpublikum klären |
| 2. Bau | Du (Nutzer review) | Skript schreiben (Vorlage kopieren wenn möglich), iterieren |
| 3. Abnahme | Du + Nutzer | HTML im Browser sichten, Traceability prüfen |

## Phase 1 — Auftrag klären

Bevor Du ein Skript schreibst, **frag gezielt** — nicht offen. Vier
Fragen, die jeder Report beantworten muss:

1. **Worüber?** Ein Satz: *„SOLL/IST-Abgleich der gelieferten
   Dokumentation gegen die IBL"*. Bei schwammiger Antwort konkret
   nachbohren.
2. **Welche Daten?** Welche Tabellen in `workspace.db` / `ds.*`,
   welche Dateien in `sources/` oder `context/`, welche Filter.
   Wenn Daten noch nicht importiert sind: **erst importieren**, dann
   Report.
3. **Welche Kernaussagen?** 3-5 Dinge, die der Report **muss**
   zeigen. Beispiel IBL-SOLL-IST: Erfüllungsgrad gesamt, Offene
   nach Gewerk, Top-Lücken mit Verantwortlichen.
4. **Zielpublikum.** Management (Executive-Summary, Zahlen groß,
   wenig Technik) vs. Fach (Tabellen, konkrete Dokumentennummern)?
   Bestimmt Text-Ton + Detail-Tiefe.

## Phase 2 — Bau

### 2.1 Wiederverwendung prüfen

```text
fs_list({"path": "exports/reports"})
```

Wenn ein passender Slug existiert: dessen `build_*.py` lesen,
Struktur übernehmen. Dem Nutzer sagen *„Es gibt schon
`dcc-verteilung` mit ähnlicher Struktur — ich kopier das Skript,
pass Queries + Texte an, Look bleibt gleich. Ok?"*

Wenn **nichts Passendes** da ist: neuer Report, Skelett aus dem
Template-Doc holen:

```text
fs_read("docs/report-builder-template.md", section="Skript-Skelett")
```

Das liefert ein vollständiges `build_<slug>.py` mit Header, Datenbank-
Helper, KPI-Kacheln, Tabelle, Quellen-Sektion und sauberer CSS-
Baseline. Kopieren, anpassen.

### 2.2 Slug festlegen + Ordner anlegen

```text
fs_mkdir({"path": "exports/reports/<slug>"})
```

### 2.3 Skript schreiben — Konventionen

- **Liest** aus `workspace.db` (`ds.*` für Provenance/Content,
  lokal für Reasoning). Kein `fs_read` auf PDFs — Inhalt aus
  `ds.agent_doc_markdown`.
- **Schreibt** genau eine Datei: `report.html` neben sich selbst.
- **Stdout** für Status (*„Rendered report.html (23 KB,
  4 Sektionen, 12 Quellen-Anker)"*) — nicht für Content.
- **Idempotent** — wiederholter Lauf mit gleichen DB-Daten liefert
  byte-identisches HTML (keine Zeitstempel inline, außer im Titel).

Volles Skelett mit CSS, KPI-Kacheln, Sources-Sektion siehe
[`docs/report-builder-template.md`](../docs/report-builder-template.md).

### 2.4 Ausführen + iterieren

```text
run_python({"path": "exports/reports/<slug>/build_<slug>.py"})
```

Bei Fehler: stderr lesen, Skript fixen, erneut starten. Bei Erfolg:
HTML-Pfad nennen und um Sichtprobe bitten.

## Phase 3 — Abnahme

1. HTML im Browser öffnen lassen:
   > *„Öffne den Report: `open exports/reports/<slug>/report.html`"*
2. Drei Punkte gezielt abfragen:
   - Stimmen die KPIs? (Plausibilität)
   - Sind die wesentlichen Aussagen belegt? Klick in die Sources-
     Sektion — führen die Verweise zu echten Quellen?
   - Fehlt was?
3. Nach Korrekturen: Skript anpassen, erneut rendern.

## Traceability — vier Faustregeln

1. **Jede Zahl in einer KPI-Kachel** → Quellen-Anker (welche Query,
   wieviele Zeilen). Bei mehreren KPIs aus derselben Query reicht
   ein gemeinsamer Anker.
2. **Jede Narrative-Aussage mit konkreten Dokumenten** → Deep-Link
   auf das Dokument (relativ zum Projekt-Root). Bei PDF-Seiten:
   `sources/pdf/xyz.pdf#page=12` (Chrome/Safari/Edge).
3. **Detail-Tabellen >20 Zeilen** → kein Pflicht-Link pro Zeile,
   aber **Aggregat-Verweis** in der Sources-Sektion (*„Grundlage:
   Query X mit N Zeilen aus Tabelle Y"*).
4. **Executive Summary** → jede Aussage hat mindestens einen
   Drilldown-Anker im Report selbst (z.B. `<a href="#offen">`).

**Nicht** linken: jede Tabellenzeile einzeln (Lärm), interne
Reasoning-Schritte (Nutzer will Quelle, nicht Gedankengang).

## Quellen-Sektion (Pflicht-Aufbau)

Jeder Report hat am Ende `<section id="quellen">` mit drei Unter-
Abschnitten:

1. **Datenquellen** — welche Tabellen/Dateien, Zeilenanzahlen,
   Import-Zeitpunkt wenn relevant.
2. **Zuordnung / Methodik** — wie wurden Relationen gebaut
   (Pattern-Matching, Joins, Filter). Ein Absatz reicht.
3. **Queries** — wesentliche SQL-Snippets als kollabierbare
   `<details>`-Blöcke (nicht alle, nur die hinter KPIs/Narrative).

## Was Du NICHT machst

- **Kein Markdown-Report** als Endprodukt — der Nutzer will HTML.
- **Keine externen Assets** (CDN-CSS, externe JS, HTTP-Images).
  SVG inline, keine CDN.
- **Keine 3000+ Zeilen Detail-Daten im HTML** — Top-N + Aggregat,
  oder CSV daneben (`data.csv` im selben Ordner) und verlinken.
- **Kein „Fertig"** ohne erfolgreichen `run_python`-Exit + reale
  `report.html`.
- **Keine Datumsstempel im Slug** oder Dateinamen. Datum im Titel,
  Slug ist Plan-Name.
- **Kein `build_xlsx_from_tables`-Aufruf von hier aus** — wenn
  Excel parallel nötig: getrennt über `excel-reporter`.

## Größenordnungen

- **Klein** (1-5 KPIs, 1 Detail-Tabelle <200 Zeilen): 50-150 KB
  HTML, baut in <5 s.
- **Mittel** (5-10 KPIs, 3-5 Tabellen, inline SVG-Charts):
  200-800 KB, baut in <15 s.
- **Groß** (>500 KB HTML): kritisch prüfen, ob Detail-Tabellen
  wirklich rein sollen, oder besser CSV-Anhang.
