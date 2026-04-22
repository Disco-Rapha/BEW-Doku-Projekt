---
name: excel-formatter
description: Bestehende Excels mit Formatierung lesen oder ändern (Strike, Farben, Merges, Formeln, Kommentare) via run_python + openpyxl.
when_to_use: Du sollst eine bestehende Excel-Datei lesen ODER ändern, bei der Formatierung zählt — durchgestrichene Zellen, Farbcodierungen, Merged Cells, Formeln, Template-Befüllung, Kommentare.
---

# Skill: excel-formatter

Für **bestehende** Excels, bei denen Formatierung zählt. Du öffnest die
Datei mit **openpyxl** im Voll-Modus (nicht `read_only`, nicht `data_only`),
liest/änderst, speicherst zurück. Ausführung über `run_python` — Skript
schreiben, ausführen, Ergebnis in die DB oder als neue Datei.

## Abgrenzung zu den anderen Excel-Werkzeugen

| Situation | Richtiges Werkzeug |
|---|---|
| Werte aus Excel in die DB importieren, Formatierung egal | `import_xlsx_to_table` (direkt, kein Skill) |
| Excel schnell anschauen (Sheets + Header + 3 Zeilen) | `xlsx_inspect` (direkt, kein Skill) |
| Neuen Multi-Sheet-Report von Grund auf bauen | Skill `excel-reporter` + `build_xlsx_from_tables` |
| **Bestehende Excel lesen mit Format, oder ändern, oder Template befüllen** | **dieser Skill** |

Wenn Du unsicher bist: der Bauch-Test — hängt die Bedeutung der Daten an
der Formatierung (Strike = verworfen, Farbe = Status, Merged = Gruppe)?
Dann hier. Geht's nur um nackte Werte? Dann `import_xlsx_to_table`.

## Verbindlicher Workflow

1. **Sichten** — erst `xlsx_inspect(path=...)` für die groben Dimensionen
   (Sheets, max_row, max_col, Header). Wenn die Datei viele Zeilen hat
   (> 10k), plane `read_only=False` nur für das, was Du wirklich brauchst.
2. **Skript schreiben** — Python-Datei unter `work/scripts/excel_<thema>.py`
   mit den Patterns unten. Inline-Code (`run_python(code="...")`) nur für
   echte Einzeiler.
3. **Ausführen** — `run_python(path="work/scripts/excel_<thema>.py")`.
4. **Ergebnis verarbeiten** — Findings in eine `work_*`- oder `agent_*`-
   Tabelle schreiben (nicht auf stdout — stdout wird bei 50 KB gekappt).
5. **Erst nach erfolgreichem Tool-Result melden.** Tool-Result = Wahrheit.

## Die openpyxl-Modi — **das musst Du wissen**

```python
from openpyxl import load_workbook

# VOLL — Styles + Formeln sichtbar, was wir hier brauchen
wb = load_workbook("datei.xlsx")

# STREAMING — schnell bei großen Files, ABER kein Zugriff auf Font/Fill/Borders
wb = load_workbook("datei.xlsx", read_only=True)   # NICHT für diesen Skill

# CACHED — Formel-Ergebnisse statt Formel-Text (nur wenn Excel die Datei
# schon mal geöffnet und gespeichert hat — sonst sind Ergebnisse None)
wb = load_workbook("datei.xlsx", data_only=True)
```

Merke: Formeln bleiben beim Schreiben mit `wb.save()` als **Formel-Text**
erhalten — Excel rechnet sie beim nächsten Öffnen neu aus. Du rechnest
nichts aus. openpyxl hat keine Berechnungs-Engine.

## Pattern: Durchgestrichene Einträge finden (Strike-Font)

Typisches Szenario: Document Controller markiert verworfene Kandidaten
mit Strike-Durchstreichung.

```python
# work/scripts/excel_find_strikes.py
import sqlite3
from pathlib import Path
from openpyxl import load_workbook

PROJECT_ROOT = Path(".")  # run_python läuft mit cwd = Projekt-Root
XLSX = PROJECT_ROOT / "context/KI-Durchlauf Lagerhalle.xlsx"
DB = PROJECT_ROOT / "data.db"

wb = load_workbook(XLSX)
ws = wb["Sheet1"]

strikes = []
for row in ws.iter_rows(min_row=2):
    for cell in row:
        if cell.value is None:
            continue
        font = cell.font
        if font and font.strike:
            strikes.append(
                (cell.row, cell.column_letter, str(cell.value))
            )

# In eine work_-Tabelle schreiben, nicht auf stdout drucken
con = sqlite3.connect(DB)
con.execute("""
    CREATE TABLE IF NOT EXISTS work_strike_cells (
        row INTEGER, col TEXT, value TEXT
    )
""")
con.execute("DELETE FROM work_strike_cells")
con.executemany(
    "INSERT INTO work_strike_cells VALUES (?, ?, ?)", strikes
)
con.commit()
print(f"{len(strikes)} Strike-Zellen gefunden, in work_strike_cells abgelegt.")
```

## Pattern: Merged Cells respektieren

Merged Cells speichern den Wert nur in der **oberen linken** Zelle. Wenn
Du iterierst, sind die anderen Zellen des Bereichs leer.

```python
from openpyxl import load_workbook
from openpyxl.utils import range_boundaries

wb = load_workbook("datei.xlsx")
ws = wb.active

# Lookup: welche Zelle gehört zu welchem Merge-Bereich
merge_lookup = {}  # (row, col) -> (anchor_row, anchor_col)
for merged_range in ws.merged_cells.ranges:
    min_col, min_row, max_col, max_row = range_boundaries(str(merged_range))
    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            merge_lookup[(r, c)] = (min_row, min_col)

# Wert einer Zelle holen, auch wenn sie gemerged ist
def get_value(ws, row, col):
    anchor = merge_lookup.get((row, col), (row, col))
    return ws.cell(row=anchor[0], column=anchor[1]).value
```

## Pattern: Formeln lesen ohne sie kaputt zu machen

```python
from openpyxl import load_workbook

# Variante A: Formel-Text sehen (z.B. fürs Debugging)
wb_formulas = load_workbook("datei.xlsx")  # default: data_only=False
cell = wb_formulas["Sheet1"]["D5"]
print(cell.value)  # => "=SUMME(B2:B4)"

# Variante B: Formel-Ergebnis sehen (was Excel zuletzt gerechnet hat)
wb_values = load_workbook("datei.xlsx", data_only=True)
cell = wb_values["Sheet1"]["D5"]
print(cell.value)  # => 142.5  (None, falls Excel nie geöffnet/gespeichert hat)
```

**Vorsicht:** Wenn Du `data_only=True` nutzt und dann `wb.save()` aufrufst,
sind die Formeln im Workbook-Objekt verloren — gespeichert werden dann die
Cached-Werte als reine Zahlen. Für Lese-mit-Änderung: **immer** mit der
Standard-Variante (ohne `data_only`) laden, Formeln bleiben erhalten.

## Pattern: Zellen einfärben (Status-Highlight)

```python
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font

GRUEN   = PatternFill("solid", fgColor="C6EFCE")  # Excel "good"
GELB    = PatternFill("solid", fgColor="FFEB9C")  # Excel "neutral"
ROT     = PatternFill("solid", fgColor="FFC7CE")  # Excel "bad"
FETT    = Font(bold=True)

wb = load_workbook("report.xlsx")
ws = wb["Prüfung"]

for row in ws.iter_rows(min_row=2):
    status_cell = row[4]   # Spalte E = Status
    if status_cell.value == "Erfüllt":
        status_cell.fill = GRUEN
    elif status_cell.value == "Teilweise":
        status_cell.fill = GELB
    elif status_cell.value == "Fehlend":
        status_cell.fill = ROT
        status_cell.font = FETT

wb.save("exports/report_gefaerbt_2026-04-21_v1.xlsx")
```

## Pattern: Bestehendes Template befüllen

Der Kunde hat eine Excel-Vorlage mit Logo, Spaltenköpfen, formatierter
Auswertungs-Zeile unten. Du sollst nur die Datenzeilen einfüllen —
ohne Layout zu zerstören.

```python
from openpyxl import load_workbook

wb = load_workbook("context/Kunden-Template.xlsx")  # Original NICHT verändern
ws = wb["Daten"]

# Annahme: Datenzeilen ab Zeile 4, Spalten A–F
rows = [
    ("DOK-001", "QC020", "Werkszeugnis", "2026-04-01", "geprüft", "BEW"),
    ("DOK-002", "DC010", "Planung",       "2026-04-03", "offen",   "BEW"),
]
for i, data in enumerate(rows, start=4):
    for j, value in enumerate(data, start=1):
        ws.cell(row=i, column=j, value=value)

wb.save("exports/Kunden-Report_2026-04-21_v1.xlsx")  # neue Datei, Original bleibt
```

**Regel:** Immer in `exports/` mit Versions-Suffix speichern, niemals das
Original unter `context/` oder `sources/` überschreiben.

## Pattern: Kommentare und Hyperlinks setzen

```python
from openpyxl.comments import Comment
from openpyxl import load_workbook

wb = load_workbook("datei.xlsx")
ws = wb.active

# Kommentar
ws["B5"].comment = Comment("Peter hat das am 2026-04-18 geprüft", "Disco")

# Hyperlink (externe URL oder internes Sheet)
ws["A10"].hyperlink = "exports/detail_dok-123.xlsx"
ws["A10"].value = "Detail ansehen"
ws["A11"].hyperlink = "#Detail!A1"  # internes Ziel
ws["A11"].value = "siehe Detail-Sheet"

wb.save("exports/mit_anmerkungen_2026-04-21_v1.xlsx")
```

## Dateinamen-Konvention

Wie bei `build_xlsx_from_tables`: `<thema>_YYYY-MM-DD_v<N>.xlsx`.
Niemals das Original überschreiben — immer in `exports/` mit neuem Namen.

## Was Du **nicht** machen sollst

- **Kein `read_only=True` bei diesem Skill.** Damit verlierst Du die Styles,
  die Du hier brauchst.
- **Kein `data_only=True` beim Speichern.** Das killt die Formeln.
- **Kein Überschreiben von Dateien in `context/` oder `sources/`.**
  Immer nach `exports/` mit Versions-Suffix.
- **Keine Ergebnisse auf stdout drucken, die größer als ein paar KB sind.**
  Ergebnis in eine `work_*`- oder `agent_*`-Tabelle, dann `sqlite_query`.
- **Keine Formeln „selbst ausrechnen".** openpyxl kann das nicht. Entweder
  Excel öffnen lassen (cached value), oder Du rechnest im Python-Skript und
  schreibst das Zahlen-Ergebnis rein (statt Formel).

## Troubleshooting

- **`cell.font.strike` ist None statt False:** Zelle hat nie einen Font
  gesetzt bekommen. `if font and font.strike:` statt `if font.strike:`.
- **Merged-Cells-Werte sind None:** Nur die obere linke Zelle hat den Wert,
  siehe Merged-Cells-Pattern oben.
- **Formel-Zelle zeigt None bei `data_only=True`:** Excel hat die Datei nie
  geöffnet, der cached value ist leer. Ohne `data_only` laden und Formel-
  Text sehen, oder Excel einmal kurz öffnen + speichern lassen.
- **Workbook groß + Style-Zugriff langsam:** kein Vermeiden ohne
  `read_only=True` — dann aber Verzicht auf Styles. Wenn Du unbedingt
  beides brauchst, in zwei Durchgängen arbeiten (erst Streaming-Read für
  Werte-Vorauswahl, dann Voll-Load nur für die interessanten Zeilen).
