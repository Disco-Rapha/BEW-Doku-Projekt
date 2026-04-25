# DWG-Setup (ODA File Converter)

Disco verarbeitet **DXF-Dateien direkt** (Text-Format, von ezdxf gelesen).
Fuer **DWG-Dateien** (Autodesks proprietaeres Binaerformat) wird der
**ODA File Converter** als externes CLI-Tool gebraucht. Er konvertiert
DWG → DXF und wird sowohl von der Extraction-Pipeline (`dwg-ezdxf-local`-
Engine) als auch vom UI-Viewer (DXF-Viewer im Viewer-Pane) genutzt.

ODA File Converter ist ein **kostenloses Tool** der Open Design Alliance,
fuer nicht-kommerzielle Nutzung frei. Lizenz ist projektabhaengig — bei
Verwendung in einem kommerziellen Projekt eigene Lizenzbedingungen pruefen.

## Installation auf macOS

1. ODA File Converter herunterladen:
   <https://www.opendesign.com/guestfiles/oda_file_converter>
2. Das `.dmg` oeffnen und die App nach `/Applications/` ziehen.
3. Pfad zur ausfuehrbaren Binary ermitteln, in der Regel:
   ```
   /Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter
   ```
4. **In `$PATH` aufnehmen** ODER explizit ueber Env Var setzen:

   **Option A** — Symlink in `/usr/local/bin` (oder `~/.local/bin`):
   ```bash
   ln -s "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter" \
         /usr/local/bin/ODAFileConverter
   ```
   `ezdxf.addons.odafc` findet die Binary dann automatisch.

   **Option B** — explizit in `.env`:
   ```
   ODAFC_EXEC=/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter
   ```

## Test

```bash
cd "/Users/BEW/Claude/BEW Doku Projekt"
uv run python -c "
from ezdxf.addons import odafc
print(odafc.is_installed())
"
```

Sollte `True` ausgeben. Wenn `False`: Pfad pruefen, evtl. `xattr -cr` auf
die App anwenden, falls macOS Gatekeeper blockt.

## Caching

Konvertierte DXF-Dateien werden pro Projekt gecached unter:

```
<projekt>/.disco/dxf-cache/<sha256>.dxf
```

Cache-Bust passiert automatisch ueber Datei-Groesse + mtime — wenn die
DWG sich aendert, wird neu konvertiert.

## Troubleshooting

- **Frontend zeigt "Konvertierung fehlgeschlagen — meist fehlt der ODA
  File Converter":** Installation wie oben pruefen.
- **macOS sagt "App ist beschaedigt":** Gatekeeper blockt unsignierte
  Tools. Workaround: `sudo xattr -cr /Applications/ODAFileConverter.app`.
- **Konvertierung dauert ungewoehnlich lang:** Bei sehr grossen DWGs
  (>100 MB) braucht ODA gerne 30-60 Sekunden. Cache greift beim zweiten
  Aufruf.
- **DXF-Dateien gehen weiter, DWG nicht:** ODA noch nicht installiert.
  Fuer DXF allein ist nichts zu tun.
