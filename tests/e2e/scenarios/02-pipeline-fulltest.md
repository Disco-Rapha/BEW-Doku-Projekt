# Szenario 02 — Pipeline-Vollauslauf + Reasoning + Reports

**Ziel:** Pipeline durchlaufen lassen (Routing → Extraktion → Suchindex),
dann Cross-Source-Reasoning testen, einen Excel-Report bauen, Failure-
Tracking durch Retry validieren.

**Voraussetzung:** Szenario 01 ist durchgelaufen — Sources sind
registriert (15 active), Duplikat erkannt, PDF-Pipeline-Vorschlag
liegt vor.

## Drehbuch + Beobachtungen

### Schritt 5 — Pipeline starten

User-Prompt:

> Top. Lass die ganze Pipeline jetzt komplett durchlaufen — Routing,
> Extraktion, Suchindex. Sag mir Bescheid, wenn was schiefgeht.

**Beobachtung:**
- Disco lädt `pipeline-diagnostics`-Skill, ruft `flow_run` für
  `extraction_routing_decision`, dann `extraction`, beobachtet via
  `flow_status` + `flow_logs`.
- Routing: 12 Items in 1s, 0 failed.
- Extraktion: 12 Items, 9 ok, 3 failed, 0.0545 EUR (Cost-Tracking).
- Suchindex baut automatisch nach: 9 search_docs.
- Disco meldet sauber: *„Run #2 (Extraktion) ist fertig: 9/12
  erfolgreich, 3 Fehler, 0.0545 EUR. Das Bild ist plausibel — die
  zwei DWGs sind lokal im dwg2dxf gecrasht, und ein PDF
  (sources/09_korruptes_dokument.pdf) ist bei Azure DI mit
  InternalServerError ausgestiegen."*
- **Pass.** Disco hat selbständig den Status verfolgt und einen
  knackigen Abschluss-Report geliefert.

**Routing-Entscheidungen verifiziert:**

| Slot | Engine | Erwartung |
|---|---|---|
| 02_schaltplan_a3.pdf | pdf-azure-di | erwartet pdf-azure-di-hr ⚠️ |
| 03_scan_protokoll.pdf | pdf-azure-di | ✓ |
| 04_kks_schild.jpg | image-gpt5-vision | ✓ |
| 05_lieferindex.xlsx | excel-openpyxl | ✓ |
| 06_dcc_katalog.xlsx | excel-openpyxl | ✓ |
| 07_grundriss.dwg | dwg-ezdxf-local | ✓ |
| 08_leeres_dokument.pdf | pdf-azure-di | ✓ |
| 09_korruptes_dokument.pdf | pdf-azure-di-hr | ✓ |
| 10_korruptes_zeichnung.dwg | dwg-ezdxf-local | ✓ |
| 11_duplikat_von_01.pdf | pdf-azure-di | ✓ (kanonisches Duplikat) |
| 14a/14b_bericht.pdf | pdf-azure-di | ✓ |

**Befund:** A3-Plan wurde mit `pdf-azure-di` (nicht HighRes) geroutet —
bei A3-Großformat sollte HR triggern. Routing-Heuristik prüfen.

### Schritt 6 — Reasoning auf einzelnem File

User-Prompt:

> Was steht eigentlich auf dem KKS-Schild drauf?

**Beobachtung:**
- Disco ruft `doc_markdown_read` für 04_kks_schild.jpg.
- Liefert Inhalt: Y0SBD32 / AA501, Armatur, PN16/DN50, BEW Lagerhalle.
- **Selbständig erkennt Cross-Source-Verbindung:** *„Das passt direkt
  zu einem Eintrag aus der Lieferindex-Excel — dort gibt es ebenfalls
  Y0SBD32 AA501."*
- **Pass.** Cross-Source-Reasoning genau wie in CLAUDE.md spezifiziert.

### Schritt 7 — Cross-Source-Abgleich

User-Prompt:

> Ja gerne, gleich mal alles gegeneinander ab. Mich interessiert: zu
> welchen Geräten aus der Liste haben wir auch ein Datenblatt im
> Projekt?

**Beobachtung:**
- Disco macht 4× `search_index` (KKS-Codes), 5× `doc_markdown_read`.
- Erstellt Tabelle: 5 Geräte aus Liefer-Excel × Datenblatt-Status
  pro KKS-Code.
- Nur 1 Treffer: Y0SBD32 AA501 → Datenblatt in 11_duplikat_von_01.pdf.
- **Erkennt OCR-Quirk:** *„Die erste Zeichenfolge ist im PDF einmal
  als YOSBD32 statt Y0SBD32 erkannt"* — Disco-eigene Beobachtung,
  nicht in Skill vorgegeben.
- **Erkennt Pipeline-Quirk:** *„Das scheinbar ‚eigentliche' PDF
  01_datenblatt.pdf hat keinen eigenen Markdown-Eintrag, obwohl sein
  Duplikat 11_duplikat_von_01.pdf extrahiert wurde."* — sehr scharfe
  Selbstbeobachtung.
- **Pass.** Disco-Verhalten exakt wie das CLAUDE.md-Paradebeispiel
  „Cross-Source-Reasoning".

### Schritt 8 — Excel-Report bauen

User-Prompt:

> Ja, bau mir bitte die SOLL/IST-Tabelle als Excel — pro Gerät eine
> Zeile mit Datenblatt / Statusnachweis / Schild / Berichtserwaehnung
> als Spalten. Mit gruener Markierung wo vorhanden, rot wo nicht.

**Beobachtung:**
- Disco lädt `excel-reporter`-Skill.
- Erstellt `work_soll_ist_geraete` als SQLite-Tabelle.
- Ruft `build_xlsx_from_tables` mit 3 Sheets (Übersicht / Uebersicht /
  Details).
- Datei landet in `exports/soll_ist_geraete_2026-05-07_v1.xlsx`.

**Geprüfter Excel-Inhalt:**
- Sheet 0-Übersicht: 5 Kennzahlen (Geräte total, mit Datenblatt etc.)
- Sheet 1-Uebersicht: 5 Geräte × 6 Spalten (KKS-Code, Bezeichnung +
  4 Statusspalten)
- Sheet 2-Details: 5 Geräte × 14 Spalten (inkl. Hersteller, Typ, DN,
  PN + 4 Beleg-Spalten mit Quelldateien)

**Befund:** Standard-Reporter färbt nur **eine** Statusspalte
(„Datenblatt") rot/grün — die anderen drei (Statusnachweis, Schild,
Berichtserwähnung) bleiben farblos. Disco hat das transparent
kommuniziert: *„Wenn Du wirklich willst, dass alle vier Spalten
jeweils grün/rot eingefärbt werden, nehme ich den Custom-Weg über
openpyxl"*. Sauber gemeldet, aber Bedarf besteht: Excel-Reporter
sollte `n` Statusspalten unterstützen.

**Pass mit Befund.** Multi-Spalten-Status ist Teil der CLAUDE.md-
Vision (SOLL/IST-Reports gegen Norm).

### Schritt 9 — Failure-Tracking + Retry

User-Prompt:

> Wir hatten ja drei Files die in der Extraktion gefailt sind —
> kannst Du die mal kurz zusammenfassen mit Grund, und dann probier
> sie nochmal?

**Beobachtung:**
- Disco ruft `pipeline_file_status` 3× (das neue Tool aus Block J).
- Räumt failed-Einträge auf, startet Routing+Extraktion neu mit
  `only_file_ids`.
- Run #3 (Routing) inkludiert alle 3 Files (07/09/10).
- Run #4 (Extraktion) inkludiert **nur die zwei DWGs** (07/10),
  nicht 09 (Azure-DI-PDF).
- Beide DWGs failen sofort wieder mit `dwg2dxf-SIGABRT`.
- Disco-Fazit: *„Das ist kein transienter Fehler mehr, sondern ein
  systematischer DWG-Pfad."*

**Befund A:** User-Frage „die" (drei) wurde von Disco interpretiert
als „die mit demselben Failure-Pfad" — er hat den 09-PDF-Server-
Fehler vom DWG-Cluster getrennt und nur die DWGs retried. Inhaltlich
nicht falsch (ein Server-Fehler retryt sich anders als ein
Engine-Crash), aber User-Erwartung war alle drei.

**Befund B:** User-Wunsch „kannst Du die mal kurz zusammenfassen mit
Grund" wurde nicht in Tabellenform geliefert — Disco ist direkt zur
Retry-Aktion gesprungen. In früheren Bubbles waren tabellarische
Übersichten — hier nur Fließtext.

### Schritt 10 — Pipeline-Status-Ampel

**Beobachtung im UI (Sidebar):**
- 1. Registrierung: 16/16
- 2. Externe Anreicherung: n.a.
- 3. Kanonik: 15→14 kanonisch
- 4. Routing: 12/16
- 5. Extraktion: 8/14 (3 Fehler)
- 6. Suchindex: 9/9

**Befund — Counts inkonsistent:**

| Schritt | Ampel | DB-Wahrheit | Differenz |
|---|---|---|---|
| Registrierung | 16/16 | 15 active sources | +1 (was zählt das Extra?) |
| Routing | 12/16 | 12 von 12 routebaren | Nenner falsch |
| Extraktion | 8/14 | 9 von 12 ok | beide Werte falsch |
| Suchindex | 9/9 | 9 search_docs | ✓ |

**Pass-Kriterium NICHT erfüllt.** Die Pipeline-Ampel-Endpoint-Logik
braucht ein Audit. Hauptverdacht: Nenner mischt agent_sources mit
agent_pdf_inventory mit etwas drittem; Zähler bei Extraktion zählt
done ohne replaces-Quirk vom Duplikat 11.

## Pass-Kriterien (Gesamt)

- [x] Routing-Flow läuft, Engine-Wahl plausibel (1 Heuristik-Befund: 02 A3)
- [x] Extraktion-Flow läuft mit Cost-Tracking
- [x] Failed-Tracking funktioniert (3 Errors mit retry_count + error in DB)
- [x] Suchindex baut automatisch nach
- [x] Cross-Source-Reasoning liefert OCR-tolerantes Matching
- [x] Excel-Report mit Multi-Sheet + Status-Farben (eine Spalte)
- [x] `pipeline_file_status`-Tool wird vom Skill genutzt
- [⚠️] Multi-Spalten-Status im Excel-Reporter: Bedarf identifiziert
- [⚠️] Retry-Verhalten: Disco trennt Failure-Modes selbständig (gut),
      aber User-„alle" wurde implizit auf „gleicher Pfad" reduziert
- [✗] Pipeline-Status-Ampel: Counts stimmen nicht mit DB überein

## Befunde — Backlog-Kandidaten

1. **Routing-Heuristik:** A3-PDFs sollten `pdf-azure-di-hr` triggern,
   nicht `pdf-azure-di`. Schwellenwert prüfen
   (`max_page_width_pt > X` → HR).
2. **Excel-Reporter:** Multi-Statusspalten-Färbung als Standard-Feature
   (oder Doku im Skill, wann openpyxl-Custom nötig).
3. **Failure-Triage-Verhalten:** Sollte Disco bei „retry alle failed"
   immer alle Failure-Modes anpacken, oder weiterhin nach Failure-
   Cluster gruppieren? — System-Prompt-Diskussion.
4. **Pipeline-Status-Ampel:** Nenner und Zähler im Endpoint
   `pipeline_status` reviewen. Aktuell zeigt UI 16/16, 12/16, 8/14
   — DB sagt 15, 12/12, 9/12. Wahrscheinlichster Bug: alte
   Annahme über `agent_sources` × `agent_pdf_inventory` × Duplikat-
   Replacement.
5. **DWG-Engine 07:** Sollte laut MANIFEST eine generische
   parseable DWG sein. libredwg failt aber auch hier — entweder
   DWG-Format (DWG2018?) zu modern für libredwg, oder Datei-Inhalt
   doch problematisch. Nicht E2E-Test-Stopper, aber Pool-Slot
   austauschen oder libredwg-Version fixen.

## Was als Nächstes folgt

- Befunde 1–5 in BACKLOG ablegen (TOP-3 System-Prompt + Skill +
  Tool Review-Session ergänzen).
- Test-Archiv: `~/Disco-dev/.test-archive/<timestamp>/e2e-smoke-01/`
  — Projekt + DBs + Excel-Report werden für Forensik dort hin
  verschoben (passiert bei nächstem Setup mit `--archive-existing`).
