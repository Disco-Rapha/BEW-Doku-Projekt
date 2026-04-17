---
name: context-onboarding
description: Neue Dateien in context/ sichten, klassifizieren, ins _manifest.md eintragen. Lookup-Tabellen optional als context_*-DB-Tabelle.
when_to_use: "neue Kontextdateien", "Norm abgelegt", "Richtlinie dazu", oder wenn context/ unkuratierte Dateien enthaelt.
---

# Skill: context-onboarding

Der Ordner `context/` enthaelt **Arbeitsgrundlagen** — Dokumentations-
standards, Normen, Referenzwerte, Lookup-Tabellen. Im Gegensatz zu
`sources/` (zu bearbeitendes Material) sind das *Referenzwerke*, die
Disco bei der Arbeit nachschlaegt.

## Wann dieser Skill laeuft

1. Benutzer sagt etwas wie "es gibt neue Kontextdateien" / "ich hab
   was in context/ abgelegt" / "bitte sichten".
2. Beim Session-Onboarding hast Du gemerkt, dass `context/_manifest.md`
   Dateien listet, die gar nicht mehr existieren (oder andersrum:
   Dateien in `context/` die nicht im Manifest stehen).

## Verbindlicher Workflow

### 1. Ist-Stand holen

```text
fs_list({"path": "context", "recursive": false, "limit": 200})
fs_read({"path": "context/_manifest.md"})
```

### 2. Diff bilden

Dateien im Ordner **minus** die bereits im Manifest aufgefuehrten
(das Manifest listet sie unter H3-Ueberschriften je Datei, siehe
Format unten). Arbeite nur mit dem Delta. `_manifest.md` selbst
ignorierst Du, das ist nicht die Arbeitsdatei.

### 3. Je neuer Datei: sichten + klassifizieren

Pro Datei:
- Typ erkennen anhand der Endung:
  - `.pdf` → Normative Doku / Handbuch → `pdf_extract_text` fuer erste
    1-2 Seiten (Titelseite + Inhaltsverzeichnis), um Titel, Version,
    Seitenzahl zu bestimmen.
  - `.xlsx`/`.xlsm` → `xlsx_inspect` fuer Sheet-Liste und Vorschau.
    Wenn eindeutig tabellarisch (Header-Zeile erkennbar) → **Lookup-
    Tabelle**. Sonst → **Unstrukturiertes Dokument**.
  - `.csv` → `fs_read` mit kleinem `max_bytes` (ca. 2000) fuer Header.
    Meist **Lookup-Tabelle**.
  - `.md`/`.txt` → `fs_read` (komplett, wenn < 50 KB). Meist
    **Richtlinie / Textsammlung**.
  - Alles andere → kurz im Manifest erwaehnen, Typ = `sonstige`.
- Klassifikation waehlen aus:
  - `norm` — offizielle Norm / Standard (VGB, DIN, IEC, ISO, ...)
  - `richtlinie` — firmen-/projektinterne Richtlinie
  - `lookup-tabelle` — strukturierte Nachschlagetabelle
  - `referenzwerte` — Zahlenwerke (Grenzwerte, Materialklassen)
  - `handbuch` — Hersteller-/Produkt-Doku
  - `sonstige`

### 4. Manifest fortschreiben

Nutze `fs_write` **im Append-Modus** (`append: true`). Pro neuer Datei
ein Block in diesem Format:

```markdown
---

### <dateiname>

- **Typ:** <klassifikation>
- **Groesse:** <menschenlesbar, z.B. "1.2 MB">
- **Seiten/Zeilen/Sheets:** <je nach Typ>
- **Relevant fuer:** <1 Satz: wann greift Disco darauf zurueck>
- **Kurz:** <2-3 Saetze Zusammenfassung in eigenen Worten>
- **Stand:** <YYYY-MM-DD> (heute)
```

### 5. Bei Lookup-Tabellen: DB-Import anbieten

Wenn Typ = `lookup-tabelle`:

- Erzaehle dem Benutzer in einem Satz, was die Tabelle enthaelt
  (Spalten, Zeilenzahl).
- Schlag vor: *"Soll ich das in eine `context_<name>`-Tabelle
  importieren? Dann kann ich spaeter per SQL darauf zugreifen."*
- Warte auf sein OK.
- Nach OK: `import_xlsx_to_table` oder `import_csv_to_table` mit
  Zieltabelle `context_<sprechender_name>` (z.B. `context_dcc`,
  `context_kks_katalog`, `context_materialklassen`).
- Im Manifest-Block die Zeile ergaenzen:
  `- **In DB:** ja, `context_<name>` (<n> Zeilen)`

### 6. Bei normativen Dokumenten ohne DB-Tauglichkeit

Nur Manifest-Eintrag, keine DB-Tabelle. Hinweis auf Nutzung:
*"Dieses PDF ist lang. Wenn Du konkrete Fragen dazu hast, rufe
`pdf_extract_text` mit einer Seitenspanne auf — Volltext-Suche kommt
spaeter (Phase 2c)."*

## Antwort an den Benutzer am Ende

Kurze Zusammenfassung (max. 5 Zeilen):

- Anzahl neuer Dateien
- Je Datei: Name + Typ + 1 Satz
- Wenn Importe offen: nenn sie zur Bestaetigung
- Wenn alles erledigt: "Manifest ist aktuell. Bereit zum Arbeiten."

## Was Du NICHT tun sollst

- **Nicht die ganze PDF lesen** nur fuer die Sichtung. Titelseite +
  TOC reichen. Der Rest kommt on-demand bei der Arbeit.
- **Keine Embedding-/Index-Operationen** — die kommen in Phase 2c
  (Hybrid-Search ueber Kontext + Quellen).
- **Keine Tabellen in `work_*` oder `agent_*` importieren** —
  Kontext-Daten gehoeren in `context_*`, damit der Namespace sauber
  bleibt.
