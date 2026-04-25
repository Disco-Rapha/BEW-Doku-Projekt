# DWG-Setup (libredwg)

Disco verarbeitet **DXF-Dateien direkt** (Text-Format, von ezdxf gelesen).
Fuer **DWG-Dateien** (Autodesks Binaerformat) wird der lokale
**libredwg**-Konverter `dwg2dxf` gebraucht. Er konvertiert DWG → DXF
und wird sowohl von der Extraction-Pipeline (`dwg-ezdxf-local`-Engine)
als auch vom UI-Viewer (DXF-Viewer im Viewer-Pane) genutzt.

**libredwg** ist ein **GNU-Projekt unter GPL-3.0**, voll Open Source.
Wir nutzen es als externes CLI-Tool per Subprocess ("mere aggregation"),
unser Code bleibt unter eigener Lizenz.

## Installation auf macOS

Komfort-Skript:

```bash
bash scripts/install-libredwg.sh
```

Was das Skript tut:

1. Prueft `autoconf`, `automake`, `pkg-config`, `make` im PATH (sonst
   abbrechen mit Hinweis).
2. Laedt `libredwg-0.13.4.tar.xz` von GitHub Releases.
3. Baut mit `./configure --prefix=$HOME/.local/libredwg --disable-bindings`,
   `make -j<cpus>`, `make install`.
4. Smoke-Test: `dwg2dxf --version`.

Disco findet die Binary automatisch unter
`$HOME/.local/libredwg/bin/dwg2dxf`. Override per env-Var:

```bash
export LIBREDWG_DWG2DXF=/custom/path/to/dwg2dxf
```

### Voraussetzung: Build-Tools

Wenn Homebrew system-wide unter `/opt/homebrew/` installiert ist und
Du Schreib-Rechte hast:

```bash
brew install autoconf automake pkg-config
```

Falls die Permissions nicht stimmen (typisch bei Multi-User-Macs), nimm
ein **user-lokales Brew**:

```bash
git clone --depth=1 https://github.com/Homebrew/brew ~/homebrew
export PATH=~/homebrew/bin:$PATH
brew install autoconf automake pkg-config
```

Danach `bash scripts/install-libredwg.sh`.

## Verifikation

```bash
~/.local/libredwg/bin/dwg2dxf --version
```

Sollte `dwg2dxf 0.13.4` (oder neuer) ausgeben.

Disco-seitig:

```bash
cd "/Users/BEW/Claude/BEW Doku Projekt"
uv run python -c "
from disco.docs._dwg_libredwg import is_installed, find_dwg2dxf
print('installed:', is_installed())
print('binary:', find_dwg2dxf())
"
```

## Wie Disco libredwg nutzt

```
DWG (sources/)
   │  dwg2dxf  (libredwg, lokal)
   ▼
DXF im Cache <projekt>/.disco/dxf-cache/<sha256>.dxf
   │
   ├─→ Browser-Viewer (dxf-viewer JS)        — Use-Case 2
   │
   └─→ DXF-Sanitizer + ezdxf.recover.readfile — Use-Case 1
        (Sanitizer entfernt LibreDWG-spezifische SORTENTSTABLE-Eintraege,
         die ezdxf-Strict-Mode triggert)
```

Cache-Bust passiert automatisch ueber Datei-Groesse + mtime — wenn die
DWG sich aendert, wird neu konvertiert.

## DXF-Sanitizer-Hintergrund

Manche DWGs schreibt libredwg in DXF mit einer SORTENTSTABLE-Sektion
(Render-Reihenfolge), die einen Sort-Handle mit Group-Code 331 enthaelt.
ezdxf erwartet hier strict Code 5 und bricht mit
`Invalid sort handle code 331, expected 5` ab. Die Sektion ist
**optional fuer Inhalt** — nur fuer Rendering-Z-Order. Wir entfernen sie
in `disco.docs._dwg_libredwg.sanitize_libredwg_dxf` komplett, der Browser-
Viewer macht das implizit (toleranter Parser).

## Lizenz-Notiz

libredwg ist GPL-3.0. Disco ruft `dwg2dxf` als externes CLI-Tool auf
(Subprocess). Das ist nach gaengiger GPL-Auslegung **mere aggregation**
— unser Code bleibt unter eigener Lizenz.

## Troubleshooting

- **"libredwg ist nicht installiert"**: Skript laufen lassen, dann
  `which dwg2dxf` pruefen.
- **Konvertierungs-Timeout (>5 min)**: bei sehr grossen DWGs (>100 MB)
  evtl. Timeout in `_dwg_libredwg.convert_dwg_to_dxf` (heute 300s)
  hochsetzen.
- **DXF-Read-Fehler trotz Sanitizer**: Datei mit `recover.audit()` zu
  pruefen. Bei mehr als ~50 Audit-Errors kommt der Output meist nicht
  mehr brauchbar an — dann ist das DWG-Format selbst zu kaputt fuer
  libredwg, nicht reparierbar von unserer Seite.
- **Cache-Probleme**: `<projekt>/.disco/dxf-cache/` einfach loeschen,
  beim naechsten Aufruf wird neu konvertiert.
