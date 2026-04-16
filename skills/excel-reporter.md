---
name: excel-reporter
description: Erstellt eine professionell formatierte Multi-Sheet-Excel direkt server-seitig via build_xlsx_from_tables — Header-Style, AutoFilter, Freeze Panes, Status-Zellfarben, Hyperlinks zwischen Sheets.
when_to_use: Wann immer der Benutzer eine Excel als Output braucht — Reports, Auswertungen, IBL-Exports, Komponentenlisten, alles mit mehreren Sheets oder formatierten Tabellen.
---

# Skill: excel-reporter

**Kein eigener Python-Code im Code Interpreter, keine base64-Bridges.**

Stattdessen: Du baust eine **Spec** und uebergibst sie an
`build_xlsx_from_tables`. Der Server kuemmert sich um openpyxl,
Header-Formatierung (dunkles Blau), Spaltenbreiten, AutoFilter,
Freeze Panes, Status-Zellfarben und Hyperlinks. Ein einziger Tool-Call,
beliebig grosse Excel.

## Verbindlicher Workflow

1. **Daten sichten** — kurzer `sqlite_query` oder `xlsx_inspect`,
   damit Du weisst welche Spalten Du in der Excel haben willst.
2. **Spec bauen** — siehe Beispiele unten.
3. **`build_xlsx_from_tables(...)` aufrufen** mit der Spec.
4. **Erst nach erfolgreichem Tool-Result** "Fertig" melden,
   mit dem Pfad aus dem Result. Tool-Result = Wahrheit.

## Datei-Naming

`<thema>_YYYY-MM-DD_v<N>.xlsx` z.B. `ibl_lagerhalle_2026-04-16_v1.xlsx`.
Mehrfach am selben Tag → `_v2`, `_v3`. **Niemals ueberschreiben** —
wenn die Datei existiert, gibt das Tool einen Fehler.

## Spec-Aufbau

```json
{
  "target_path": "exports/<dateiname>.xlsx",
  "title": "Report-Titel oben in der Übersicht",
  "overview_rows": [
    ["Kennzahl 1", 322],
    ["Kennzahl 2", 72]
  ],
  "sheets": [
    {
      "name": "1-Komponenten",
      "sql": "SELECT id, kks, ebene FROM work_components ORDER BY kks",
      "column_renames": {"id": "ID", "kks": "KKS", "ebene": "Ebene"}
    },
    {
      "name": "2-IBL",
      "sql": "SELECT id, kks, dcc, dokumentenart, status FROM work_ibl ORDER BY kks",
      "column_renames": {"id": "Lfd.", "dokumentenart": "Dokumentenart", "status": "Status"},
      "status_column": "status"
    },
    {
      "name": "3-Quellen",
      "rows": [
        {"art": "KKS", "anzahl": 322},
        {"art": "DCC", "anzahl": 395}
      ],
      "column_renames": {"art": "Datenquelle", "anzahl": "Anzahl"}
    }
  ]
}
```

## Sheet-Optionen

Jedes Sheet ist ein Objekt mit:
- `name` (str, max 31 Zeichen) — Sheet-Name in der Excel
- **Genau eines** von:
  - `sql` (str, READ-ONLY SELECT) → Server fuehrt das SELECT aus,
    nimmt das Ergebnis als Datenzeilen
  - `rows` (Liste von dicts) → fertige Daten, Du baust sie selbst
- `select_columns` (optional, Liste) — **Reihenfolge** und Auswahl der Spalten;
  Default = alle Spalten aus dem ersten Datensatz
- `column_renames` (optional, Map) — `{original_key: angezeigter_header}`;
  alles nicht aufgefuehrte bleibt wie es ist
- `status_column` (optional, str) — der Spalten-Schluessel, dessen Wert
  `"Erfuellt"`/`"Erfüllt"`/`"Teilweise"`/`"Fehlend"`/`"Pruefen"`/`"Prüfen"`
  zur Zellfarbe (gruen/gelb/rot/blau) gemappt wird
- `hyperlink_column` (optional, str) — Spalte mit Werten im Format
  `"Anzeige|#ZielSheet!A1"`. Wird zu klickbarem Hyperlink.

## Status-Zellfarben (typisch für SOLL/IST-Reports)

Wenn Du eine Status-Spalte mit den Werten `Erfüllt` / `Teilweise` / `Fehlend`
hast, gib ihren Schluessel als `status_column` mit:

```json
{
  "name": "3-IBL",
  "sql": "SELECT id, kks, dcc, status, bewertung FROM work_ibl",
  "status_column": "status"
}
```

→ Zellen werden automatisch eingefaerbt.

## Hyperlinks zwischen Sheets

Werte im Format `"Anzeige|#Ziel-Sheet!Zelle"`. Beispiel:

```json
{"name": "3-IBL",
 "sql": "SELECT id, kks, ('siehe ' || dok_id || '|#Dokumente!A' || (dok_row+1)) AS doc_link FROM ...",
 "hyperlink_column": "doc_link"}
```

Das wird zu `siehe DOK-123` mit Klick auf Sheet `Dokumente`, Zeile `dok_row+1`.

## Beispiel: kompletter IBL-Export

```text
build_xlsx_from_tables(
  target_path="exports/ibl_lagerhalle_2026-04-16_v1.xlsx",
  title="IBL Lagerhalle Reuter — Prototyp",
  overview_rows=[
    ["Komponenten total", 322],
    ["KKS-Systeme", 12],
    ["IBL-Einträge", 72],
    ["DCC-Codes", 395]
  ],
  sheets=[
    {
      "name": "1-Komponenten",
      "sql": "SELECT id, kks, ebene, parent_kks, anlagenteil, disziplin FROM work_components ORDER BY ebene, kks",
      "column_renames": {"id":"ID","kks":"KKS","ebene":"Ebene","parent_kks":"Parent KKS","anlagenteil":"Anlagenteil","disziplin":"Disziplin"}
    },
    {
      "name": "2-IBL",
      "sql": "SELECT id, kks, dcc, dokumentenart, prioritaet FROM work_ibl ORDER BY kks, dcc",
      "column_renames": {"id":"Lfd.","kks":"KKS","dcc":"DCC","dokumentenart":"Dokumentenart","prioritaet":"Priorität"}
    },
    {
      "name": "3-DCC-Referenz",
      "sql": "SELECT dcc, vorzugsbezeichnung_de FROM work_dcc WHERE dcc IN (SELECT DISTINCT dcc FROM work_ibl) ORDER BY dcc",
      "column_renames": {"dcc":"DCC","vorzugsbezeichnung_de":"Vorzugsbezeichnung DE"}
    }
  ]
)
```

→ liefert `{path, total_size, sheets:[{sheet_name, row_count, column_count, headers}, ...]}`

## Was Du NICHT machen sollst

- **Kein Code Interpreter mit openpyxl + base64-Bridge.** Das ist langsam,
  unzuverlaessig und der base64-String wird bei groesseren Excels truncated.
- **Kein `fs_write_bytes` mit selbst-generierten xlsx-Bytes.** Schon gar nicht.
- **Kein "Fertig" ohne Tool-Result.** Das Tool gibt Pfad + Dateigroesse
  zurueck. Erst danach melden.
