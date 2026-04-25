"""LibreDWG-Wrapper: DWG → DXF Konvertierung + DXF-Sanitizer.

LibreDWG (GNU, GPL-3, https://www.gnu.org/software/libredwg/) ist die
OSS-Variante zum DWG-Lesen. Wir rufen sie als externes CLI-Tool
(`dwg2dxf`) per Subprocess auf — "mere aggregation", unser Code bleibt
unter eigener Lizenz.

Setup: Build-Skript unter `scripts/install-libredwg.sh` installiert nach
`~/.local/libredwg/bin/`. Override per env-Var `LIBREDWG_DWG2DXF`.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


_DEFAULT_LOCAL_BIN = Path.home() / ".local" / "libredwg" / "bin" / "dwg2dxf"


def find_dwg2dxf() -> Path | None:
    """Sucht das `dwg2dxf`-Binary in env-var, PATH oder Default-User-Install."""
    # 1. Explizit per env-Var (z.B. fuer dev-Builds)
    env = os.environ.get("LIBREDWG_DWG2DXF")
    if env:
        p = Path(env)
        if p.is_file() and os.access(p, os.X_OK):
            return p
    # 2. Im PATH
    which = shutil.which("dwg2dxf")
    if which:
        return Path(which)
    # 3. Default User-Install
    if _DEFAULT_LOCAL_BIN.is_file() and os.access(_DEFAULT_LOCAL_BIN, os.X_OK):
        return _DEFAULT_LOCAL_BIN
    return None


def is_installed() -> bool:
    return find_dwg2dxf() is not None


class LibreDwgNotInstalled(RuntimeError):
    """Geworfen wenn dwg2dxf nicht gefunden wurde."""


def convert_dwg_to_dxf(src_dwg: Path, dst_dxf: Path) -> None:
    """Konvertiert eine DWG-Datei nach DXF via libredwg `dwg2dxf`.

    Schreibt nach `dst_dxf`. Wirft `LibreDwgNotInstalled` wenn das Tool
    fehlt, oder `subprocess.CalledProcessError` wenn die Konvertierung
    fehlschlaegt.
    """
    binary = find_dwg2dxf()
    if binary is None:
        raise LibreDwgNotInstalled(
            "dwg2dxf nicht gefunden. Installation: "
            "`bash scripts/install-libredwg.sh` (siehe docs/dwg-setup.md)."
        )

    dst_dxf.parent.mkdir(parents=True, exist_ok=True)

    # -y: overwrite existing output without asking
    # -v0: minimal output
    result = subprocess.run(
        [str(binary), "-y", "-v0", str(src_dwg), "-o", str(dst_dxf)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )
    if not dst_dxf.is_file():
        raise RuntimeError(
            f"dwg2dxf lief ohne Fehler, aber {dst_dxf} existiert nicht. "
            f"stderr: {result.stderr[:500]}"
        )


# ---------------------------------------------------------------------------
# DXF-Sanitizer: bereinigt LibreDWG-Output fuer ezdxf
# ---------------------------------------------------------------------------


def sanitize_libredwg_dxf(dxf_path: Path) -> Path:
    """Entfernt SORTENTSTABLE-Eintraege aus LibreDWG-DXF-Output.

    LibreDWG schreibt SORTENTSTABLE-Objekte mit Group-Code 331 fuer Sort-
    Handles, wo ezdxf strict Code 5 erwartet ("Invalid sort handle code
    331, expected 5"). SORTENTSTABLE ist eine optionale DXF-Sektion (nur
    fuer Render-Reihenfolge), die wir komplett wegwerfen koennen, ohne
    Inhalt zu verlieren.

    Schreibt eine bereinigte Kopie unter `<dxf_path>.cleaned` und gibt
    den Pfad zurueck. Falls schon sauber: `dxf_path` direkt zurueck.
    """
    text = dxf_path.read_text(encoding="cp1252", errors="replace")
    if "SORTENTSTABLE" not in text:
        return dxf_path

    cleaned, n_stripped = _strip_sortentstable(text)
    if n_stripped == 0:
        return dxf_path

    out_path = dxf_path.with_suffix(dxf_path.suffix + ".cleaned")
    out_path.write_text(cleaned, encoding="cp1252", errors="replace")
    logger.info(
        "DXF-Sanitizer: %d SORTENTSTABLE-Block(s) aus %s entfernt (%s)",
        n_stripped, dxf_path.name, out_path.name,
    )
    return out_path


def _strip_sortentstable(text: str) -> tuple[str, int]:
    """Entfernt alle '0/SORTENTSTABLE'-Bloecke bis zum naechsten '0/<type>'.

    DXF-Format: Group-Code-Zeile + Wert-Zeile in Pairs. Ein OBJECTS-
    Eintrag startet mit '0\\nSORTENTSTABLE'. Wir skippen alle Pairs bis
    zum naechsten '0\\n<anything-not-SORTENTSTABLE>'.
    """
    out: list[str] = []
    lines = text.splitlines(keepends=True)
    i = 0
    skipping = False
    n_stripped = 0
    while i < len(lines):
        line = lines[i]
        if skipping:
            # Auf naechsten Object-Begin warten
            if line.strip() == "0" and i + 1 < len(lines):
                next_type = lines[i + 1].strip()
                if next_type and next_type != "SORTENTSTABLE":
                    skipping = False
                    out.append(line)
                    i += 1
                    continue
            i += 1
            continue
        # Suche Begin von SORTENTSTABLE
        if line.strip() == "0" and i + 1 < len(lines):
            next_type = lines[i + 1].strip()
            if next_type == "SORTENTSTABLE":
                skipping = True
                n_stripped += 1
                i += 2
                continue
        out.append(line)
        i += 1
    return "".join(out), n_stripped


__all__ = [
    "find_dwg2dxf",
    "is_installed",
    "convert_dwg_to_dxf",
    "sanitize_libredwg_dxf",
    "LibreDwgNotInstalled",
]
