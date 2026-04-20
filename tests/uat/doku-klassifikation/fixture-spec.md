# Fixture-Spec — Dokumente klassifizieren nach Kunden-Schema

**Zum Szenario:** siehe `scenario.md`. Dies hier beschreibt, wie eine
**passende Test-Fixture** aussehen muss, ohne die konkreten Dokumente
vorzuschreiben. Das Verfahren ist der Gold-Standard, die Dokumente sind
austauschbar.

## Projekt-Gestalt

```
~/Disco/projects/<test-slug>/
├── README.md                ← Kunde, Bauprojekt, Ziel
├── sources/
│   └── <mindestens 3 PDFs mit verschiedenen Typen>
├── context/
│   ├── <Klassifikations-Katalog>.xlsx (oder .csv)
│   └── <Klassifikations-Prompt>.md
└── data.db                  ← leer, nur Template-Migrationen
```

## README-Mindestinhalt

- Kunde / Bauvorhaben (plausible Angabe, reicht ein Satz)
- Ziel: "Klassifikation aller technischen Dokumente nach dem Schema
  des Kunden". Idealerweise erwaehnt, dass es einen Vergleich gegen
  eine bestehende Fremd-Loesung gibt.
- "Konventionen fuer Disco"-Block (wie in Workspace-Template).

## sources/ — Mindestens diese PDF-Varietaet

Damit das Szenario realistisch ist, brauchen wir verschiedene
Dokumenttypen. Mindestens drei Kategorien mit je 1-2 PDFs:

| Kategorie | Beispiel | Was es testet |
|---|---|---|
| Textlastig | Bedienungsanleitung, Handbuch | Standard-OCR + Layout |
| Tabellenlastig | Werkszeugnis, Pruefbericht | Tabellen-Erkennung durch DI |
| Zeichnung / Schaltplan | Technische Zeichnung mit Kopf-Block | HighRes-OCR, "Zeichenkopf-Erkennung" im Prompt |

Ideal: 10-30 PDFs insgesamt — genug, dass ein Mini-Run (3) und ein
Full-Run nicht trivial identisch sind, aber klein genug, dass der Test
in < 30 Minuten durchlaeuft.

## context/ — zwei Artefakte

### Klassifikations-Katalog

Excel oder CSV mit mindestens diesen Spalten:

| Spalte | Typ | Beispiel |
|---|---|---|
| Code | str (5-stellig) | `FA010` |
| Vorzugsbezeichnung DE | str | `Uebersichtsschaltplan` |
| Alternativbezeichnungen | str (semikolon-separiert) | `Blockschaltbild; Circuit overview` |

Greifbare Groesse: 50-500 Eintraege. Wenig genug, dass das Modell sie
ueberblickt, viel genug, dass echte Auswahl noetig ist.

### Klassifikations-Prompt

Markdown mit:

- Anweisung an das Modell (Du-Form)
- Liste der zu extrahierenden Felder (z.B. Master-Code, Alternativen,
  Confidence, "ist Zusammenstellung Ja/Nein", Gewerk, Kommentar)
- Expliziter Hinweis, dass der Katalog unten angehaengt wird
- Ausgabeformat-Beschreibung (JSON mit genauen Feldnamen)
- Platzhalter `---BEGIN DOCUMENT (MARKDOWN)--- ... ---END DOCUMENT---`
  fuer den zu klassifizierenden Text

## data.db

Nach `disco project init` existiert sie mit den Template-Migrationen
(agent_sources, agent_source_metadata, agent_source_relations,
agent_source_scans, agent_script_runs, agent_flow_runs,
agent_flow_run_items) — keine Kunden-Tabellen.

## Was in der Fixture NICHT sein darf

- Vorberechnete Markdowns unter `.disco/source-extracts/` — dann ueberspringt
  Disco Phase 2 komplett.
- Vorhandene `agent_flow_runs`-Eintraege — Disco koennte denken, es sei
  schon was gelaufen.
- `context_<tabelle>` mit dem Katalog bereits importiert — Phase 1 wird
  nicht realistisch getestet.
- Eingangs-Nachrichten in `chat_messages` — Disco soll "frisch" starten.

## Reset zwischen Laeufen

Um das Szenario wiederholt zu testen, reicht es, diese Artefakte im
Test-Projekt zu entfernen:

```
rm -rf <projekt>/.disco/source-extracts/
rm -rf <projekt>/.disco/flows/
# optional: data.db wegwerfen und neu migrieren:
rm <projekt>/data.db
disco project init <slug>  # initialisiert data.db neu
```

Die Quell-PDFs und der context bleiben unberuehrt.

## Aktuelle Referenz-Fixture (fuer Entwickler)

Das Projekt `doku-klassifikation-pilot` im Workspace dient aktuell als
konkrete Referenz-Fixture. Seine Daten (Beispiel-Anlage, DCC-Katalog
mit 395 Codes, 20 PDFs) sind **nicht** Teil des Gold-Standards — sie sind
Beispiel-Input, der sich aendern darf.
