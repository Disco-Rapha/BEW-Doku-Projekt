---
name: python-executor
description: Python-Skripte lokal auf dem Host schreiben, ausfuehren und debuggen. Fuer Bulk-Ops, grosse Dateien, komplexe Transformationen.
when_to_use: Datei > 1 MB verarbeiten, Bulk-Operation ueber viele Dateien, XML/JSON parsen, "nutze python", "schreib ein Skript", "parse das lokal".
---

# Skill: python-executor

Disco kann Python-Skripte lokal auf dem Host-Rechner ausfuehren.
Das ist der Weg fuer alles, was zu gross fuer den Chat-Kontext oder
den Azure-Code-Interpreter ist: 55 MB XML-Feeds, 10.000 PDFs hashen,
grosse CSV-Transformationen.

## Wann run_python statt anderer Tools?

| Aufgabe | Tool |
|---|---|
| SQL-Abfrage | `sqlite_query` |
| Kleine Datei lesen (< 1 MB) | `fs_read` |
| Excel erzeugen | `build_xlsx_from_tables` |
| Berechnung/Chart | Code Interpreter |
| **Grosse Datei** (> 1 MB) | **`run_python`** |
| **Bulk ueber viele Dateien** | **`run_python`** |
| **Komplexe Transformation** | **`run_python`** |

## Verbindlicher Workflow

### 1. Dateigrösse pruefen — BEVOR Du fs_read machst

```text
fs_list({"path": "sources", "recursive": true, "pattern": "*.xml"})
```

Wenn `size > 1_000_000` (1 MB): **Nicht** per `fs_read` in den Chat-
Kontext laden. Stattdessen ein Skript schreiben.

### 2. Skript schreiben (file-basiert, persistent)

```text
fs_mkdir({"path": "work/scripts"})
fs_write({"path": "work/scripts/parse_feed.py", "content": "<code>"})
```

Konventionen fuer das Skript:
- Schreibe Ergebnisse **in die Projekt-DB** (`data.db`), nicht auf stdout.
  stdout ist gekappt bei 50 KB und geht als Token-Last in den Kontext.
- Nutze `sqlite3.connect("data.db")` — Working-Dir ist das Projekt-Root.
- `print()` nur fuer **Status-Meldungen** ("1619 records parsed, 3 errors").
- Fehlerbehandlung: try/except, stderr fuer Tracebacks (wird captured).
- Idempotenz: `CREATE TABLE IF NOT EXISTS`, `INSERT OR REPLACE`.

Beispiel-Skelett:

```python
#!/usr/bin/env python3
"""Parse SharePoint XML-Feed → agent_sp_records."""
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

DB = "data.db"
SOURCE = "sources/Discoverse Prediction IST Dokumentenstand vollständig.txt"

def main():
    tree = ET.parse(SOURCE)
    root = tree.getroot()
    ns = {"a": "http://www.w3.org/2005/Atom",
          "d": "http://schemas.microsoft.com/ado/2007/08/dataservices"}

    entries = root.findall(".//a:entry", ns)
    print(f"Gefunden: {len(entries)} Eintraege")

    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_sp_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            dcc TEXT,
            bezugsobjekt TEXT,
            ersteller TEXT,
            pfad TEXT
        )
    """)
    conn.execute("DELETE FROM agent_sp_records")  # idempotent

    inserted = 0
    for entry in entries:
        props = entry.find(".//a:content/m:properties", {
            **ns, "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
        })
        if props is None:
            continue
        title = (props.findtext("d:Title", "", ns) or "").strip()
        dcc = (props.findtext("d:MasterDCC", "", ns) or "").strip()
        # ... weitere Felder
        conn.execute(
            "INSERT INTO agent_sp_records (title, dcc) VALUES (?, ?)",
            (title, dcc),
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f"Fertig: {inserted} Datensaetze in agent_sp_records geschrieben.")

if __name__ == "__main__":
    main()
```

### 3. Ausfuehren

```text
run_python({"path": "work/scripts/parse_feed.py"})
```

### 4. Ergebnis pruefen

- `exit_code == 0` → Erfolg. Lies stdout fuer die Zusammenfassung.
- `exit_code > 0` → Fehler. Lies stderr fuer den Traceback.
- `exit_code == null` → Timeout oder OS-Fehler. Lies `error` im Result.

Bei Erfolg: Daten stehen jetzt in der Projekt-DB. Pruefe per SQL:
```text
sqlite_query({"sql": "SELECT COUNT(*) FROM agent_sp_records"})
```

### 5. Debug-Loop (bei Fehler)

```text
fs_read({"path": "work/scripts/parse_feed.py"})   ← Skript lesen
# Fehler in stderr analysieren: Zeile, Exception, Ursache
fs_write({"path": "work/scripts/parse_feed.py", "content": "<fixed_code>"})
run_python({"path": "work/scripts/parse_feed.py"})  ← nochmal
```

Typische Fehler:
- `KeyError` → XML-Tag heisst anders als erwartet
- `FileNotFoundError` → Pfad relativ zum Projekt-Root pruefen
- `sqlite3.OperationalError` → Tabelle/Spalte existiert nicht
- `UnicodeDecodeError` → encoding-Parameter anpassen
- `MemoryError` → Datei stueckweise lesen (chunk-basiert)

### 6. Inline-Modus (fuer Quick-Checks)

```text
run_python({"code": "import os; print(sorted(os.listdir('sources/'))[:10])"})
run_python({"code": "open('sources/feed.txt','rb').read(200)"})
```

Inline-Code wird **nicht** persistent gespeichert (temporaere Datei,
wird bei Erfolg geloescht). Fuer echte Arbeit: immer file-basiert.

## Sicherheit

- Nur `.py`-Dateien. Kein Shell, kein Bash, kein eval.
- API-Keys (FOUNDRY_*, AZURE_*, etc.) sind im Environment des Skripts
  **nicht** verfuegbar. Das Skript kann keine API-Calls im Namen des
  Benutzers machen.
- Timeout: Default 5 Minuten, Max 30 Minuten.
- stdout/stderr: gekappt bei 50 KB im Tool-Result (volle Laenge in DB).

## Anti-Halluzination

Melde **nur dann** "Skript erfolgreich", wenn `exit_code == 0` im
Tool-Result steht. Bei `exit_code > 0` oder `exit_code == null`:
Fehler offen nennen, stderr zitieren, Debug-Loop anbieten.

## Best Practices

1. **Ergebnisse in die DB, nicht auf stdout.** stdout ist fuer Status.
2. **Skripte in `work/scripts/` ablegen** — persistent, wiederverwendbar.
3. **In NOTES oder memory festhalten**, welches Skript wofuer geschrieben
   wurde: `"work/scripts/parse_feed.py parst den SP-XML-Feed"`.
4. **Idempotent schreiben:** `CREATE TABLE IF NOT EXISTS` + `DELETE` vor
   `INSERT`, oder `INSERT OR REPLACE`.
5. **Bei 10k+ Dateien:** Fortschritt auf stdout alle 100 Dateien
   (`if i % 100 == 0: print(f"{i}/{total} ...")`), damit der Benutzer
   sieht, dass etwas passiert.
