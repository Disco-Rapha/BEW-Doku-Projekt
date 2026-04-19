# Szenario: Dokumente klassifizieren nach Kunden-Schema

**Gold-Standard v1 — Stand 2026-04-18**

**Worum geht es?**

Ein typischer Einsatz von Disco im Grossprojekt: Ein Kunde liefert eine
Sammlung technischer Dokumente (PDFs — Zeichnungen, Anleitungen, Zeugnisse)
zusammen mit seinem eigenen Klassifikations-Schema (5-stellige Codes mit
Vorzugs- und Alternativ-Bezeichnungen, DE/EN). Disco soll die Dokumente
lesen, verstehen und pro Dokument ein strukturiertes Klassifikations-
Ergebnis liefern, das am Ende mit einer bestehenden Fremd-Loesung
(z.B. MS Flow) verglichen werden kann.

Das hier ist die **abstrahierte Variante** des UAT, das am 2026-04-18 im
Projekt `doku-klassifikation-pilot` durchgespielt wurde. Die konkreten
Dokumente werden sich aendern — das Verfahren bleibt.

## Was Disco am Ende autonom koennen muss

Bei einem frisch angelegten Projekt, das der `fixture-spec.md` entspricht,
fuehrt Disco den kompletten Prozess durch — **ohne Zwischen-Nudges**, ohne
Korrektur-Stubse, ohne "leg los, ich warte". Der Nutzer sendet nur die
Kernnachrichten aus Abschnitt "Ablauf" und wartet jeweils die Antwort ab.

## Vorbedingungen (Fixture)

Das Projekt im Workspace hat:

- `README.md` mit Kontext (Kunde, Bauprojekt, Ziel)
- `sources/` mit einer Handvoll technischer PDFs (mind. drei verschiedene
  Dokumenttypen, z.B. Werkszeugnis + Manual + Schaltungsbuch)
- `context/` mit einem Klassifikations-Katalog (Excel/CSV mit 5-stelligen
  Codes + Vorzugsbezeichnung DE + ggf. Alternativbezeichnungen) und einem
  Klassifikations-Prompt (Markdown)

Details siehe `fixture-spec.md`.

## Ablauf — die Kernnachrichten

Disco erhaelt nacheinander diese Messages. Zwischen jeder Message: warten
bis Disco fertig geantwortet hat, dann naechste senden. Keine Nudges.

### Phase 1 — Projekt-Onboarding

**User:** *"Ich habe gerade ein neues Projekt angelegt. Guck dir an, worum
es geht, sichte die Quellen und den Kontext und leg los mit der
Vorbereitung."*

Erwartung: Disco sollte `project-onboarding` + `sources-onboarding` +
`context-onboarding` Skills triggern, `README.md` lesen, `sources/`
registrieren, `context/` sichten und den Klassifikations-Katalog in die
Projekt-DB importieren.

### Phase 2 — PDF → Markdown Flow bauen und laufen lassen

**User:** *"Als Naechstes brauchen wir aus jedem PDF ein sauberes Markdown
per Document Intelligence (High-Resolution). Bau das als echten Flow, mach
einen kleinen Test-Lauf ueber 2-3 Dokumente, und wenn das passt, lass den
vollen Lauf durchziehen."*

Erwartung:
- `flow-builder`-Skill wird geladen, **vor** dem ersten DI-Call auch
  `sdk-reference`.
- Flow-Ordner `flows/di-extract-markdown/` (oder aehnlich) wird angelegt,
  mit **echtem Runner-Code** (kein TODO-Stub).
- Mini-Run ueber 2-3 Items via `flow_run(config={'limit': 3})`. Nicht via
  `run_python`.
- Disco prueft die Ergebnisse selbst (Markdowns existieren, Seiten- und
  Zeichen-Kennzahlen plausibel), dann Full-Run.
- Keine Runde mit halluzinierten Imports oder falschen DI-Parametern.

### Phase 3 — Klassifikations-Flow bauen und laufen lassen

**User:** *"Jetzt der eigentliche Klassifikator: nimm den Prompt aus dem
Kontext, schick pro Dokument das Markdown durch GPT-5 mit strukturiertem
JSON-Output, speicher das Ergebnis pro Dokument in eine neue
agent_*-Tabelle. Erst wieder kleiner Test, dann voll."*

Erwartung:
- `sdk-reference` fuer `response_format={"type": "json_schema"}`.
- Schema kommt aus dem Klassifikations-Prompt (Felder exakt wie dort
  spezifiziert).
- Markdowns werden vor dem Call vernuenftig getrimmt (Kontext-Budget).
- Mini-Run mit `limit=3`, Sichtkontrolle, dann Full-Run.

### Phase 4 — Ergebnisse exportieren

**User:** *"Bau mir bitte eine Excel, die die Klassifikations-Ergebnisse
pro Dokument schoen zum Durchgucken aufbereitet. Ich will das mit der
MS-Flow-Variante vergleichen koennen."*

Erwartung: `excel-reporter`-Skill triggert, `build_xlsx_from_tables` mit
Multi-Sheet und passender Formatierung liefert die Datei unter
`exports/` ab.

## Was NICHT Teil des Szenarios ist

- Der Abgleich mit der MS-Flow-Loesung (separate Uebung, passiert ausserhalb
  von Disco).
- Upload nach SharePoint, Excel-Download durch den Nutzer.
- Reklassifikation nach Prompt-Aenderung (spaeteres Szenario).

## Bekannte Fallstricke (aus dem UAT 2026-04-18)

Diese Bugs wurden im ersten Durchlauf entdeckt und in Portal-v26 gefixt.
Der Gold-Standard ist **erst dann erfuellt**, wenn keiner davon wieder
auftritt:

- Flow-Huelle mit Template-Stub statt echtem Runner-Code (UAT-Bug #1)
- Ankuendigung "ich starte jetzt..." ohne Tool-Call im gleichen Turn (#2)
- `'FlowRun' object has no attribute 'title'` (#3)
- Halluzinierte Imports aus `bew.services.*` oder geratene DI-Parameter (#4)
- Flow-Subprocess kennt Azure-Credentials nicht (#5)

Akzeptanzkriterien siehe `acceptance.md`.

## Historie

- 2026-04-18 — v1 initial: abgeleitet aus dem ersten UAT-Lauf
  `doku-klassifikation-pilot`. Bis Phase 2 (Markdown-Extraktion) mit
  Disco durchgespielt, aber mit mehreren Nudges. Phase 3+4 noch offen.
  Bugs #1-#5 im Anschluss behoben.
