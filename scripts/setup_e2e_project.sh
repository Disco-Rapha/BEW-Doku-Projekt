#!/usr/bin/env bash
# Setzt ein Disco-E2E-Test-Projekt im Dev-Workspace auf.
#
# Vorgehen:
#   1) Pool-Files aus ~/Disco-dev/.test-fixtures/ pruefen (gegen MANIFEST.md)
#   2) Optional: vorhandenes Projekt archivieren statt loeschen
#   3) `disco project init <slug>` (idempotent)
#   4) Pool-Files in <slug>/sources/ und <slug>/context/ spiegeln
#   5) Status-Report: was vorhanden, was fehlt
#
# Fehlende Pool-Files sind kein Hard-Stop — die zugehoerigen Szenarien
# werden in der E2E-Suite spaeter automatisch geskipped.
#
# Usage:
#   scripts/setup_e2e_project.sh <slug>
#   scripts/setup_e2e_project.sh --archive-existing <slug>
#   scripts/setup_e2e_project.sh --help
#
# Env-Overrides:
#   DEV_WORKSPACE   (Default: ~/Disco-dev)
#   FIXTURE_ROOT    (Default: $DEV_WORKSPACE/.test-fixtures)
#   ARCHIVE_ROOT    (Default: $DEV_WORKSPACE/.test-archive)

set -euo pipefail

DEV_WORKSPACE="${DEV_WORKSPACE:-$HOME/Disco-dev}"
FIXTURE_ROOT="${FIXTURE_ROOT:-$DEV_WORKSPACE/.test-fixtures}"
ARCHIVE_ROOT="${ARCHIVE_ROOT:-$DEV_WORKSPACE/.test-archive}"

ARCHIVE_EXISTING=0
SLUG=""

print_help() {
  sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
  case "$arg" in
    --archive-existing) ARCHIVE_EXISTING=1 ;;
    --help|-h) print_help; exit 0 ;;
    -*)
      echo "Unbekanntes Flag: $arg" >&2
      echo "(Hilfe: $0 --help)" >&2
      exit 2
      ;;
    *)
      if [ -z "$SLUG" ]; then
        SLUG="$arg"
      else
        echo "Nur ein Slug erlaubt, zweites Argument: $arg" >&2
        exit 2
      fi
      ;;
  esac
done

if [ -z "$SLUG" ]; then
  echo "Fehler: Slug fehlt." >&2
  echo "Usage: $0 [--archive-existing] <slug>" >&2
  exit 2
fi

SOURCES_POOL="$FIXTURE_ROOT/sources-pool"
CONTEXT_POOL="$FIXTURE_ROOT/context-pool"
PROJECT_DIR="$DEV_WORKSPACE/projects/$SLUG"

if [ ! -d "$SOURCES_POOL" ] || [ ! -d "$CONTEXT_POOL" ]; then
  echo "Fehler: Pool-Verzeichnis nicht gefunden unter $FIXTURE_ROOT" >&2
  echo "        Erst 'uv run python scripts/generate_test_fixtures.py' laufen lassen." >&2
  exit 1
fi

# Erwartete Slot-Liste (siehe MANIFEST.md). Pflicht-Pool = synthetische Files,
# manueller Pool = aus Prod beschaffen, fehlend = Szenario skipped.
SOURCE_SLOTS_SYNTH=(
  "01_datenblatt.pdf"
  "03_scan_protokoll.pdf"
  "04_kks_schild.jpg"
  "05_lieferindex.xlsx"
  "08_leeres_dokument.pdf"
  "11_duplikat_von_01.pdf"
  "14a_bericht_kurzversion.pdf"
  "14b_bericht_langversion.pdf"
)

SOURCE_SLOTS_MANUAL=(
  "02_schaltplan_a3.pdf"
  "07_grundriss.dwg"
  "09_korruptes_dokument.pdf"
  "10_korruptes_zeichnung.dwg"
  "12_bericht.docx"
  "13_praesentation.pptx"
)

CONTEXT_SLOTS=(
  "06_dcc_katalog.xlsx"
)

echo "=== Disco E2E-Setup: $SLUG ==="
echo "Workspace : $DEV_WORKSPACE"
echo "Pool      : $FIXTURE_ROOT"
echo "Projekt   : $PROJECT_DIR"
echo ""

# ---- 1) Pool-Verfuegbarkeit pruefen --------------------------------

echo "--- Pool-Verfuegbarkeit ---"

MISSING_SYNTH=()
for f in "${SOURCE_SLOTS_SYNTH[@]}"; do
  if [ -f "$SOURCES_POOL/$f" ]; then
    echo "  ✓ $f (synthetisch)"
  else
    echo "  ✗ $f FEHLT (synthetisch — generieren mit scripts/generate_test_fixtures.py)"
    MISSING_SYNTH+=("$f")
  fi
done

MISSING_MANUAL=()
for f in "${SOURCE_SLOTS_MANUAL[@]}"; do
  if [ -f "$SOURCES_POOL/$f" ]; then
    echo "  ✓ $f (manuell)"
  else
    echo "  - $f fehlt (manuell aus Prod — Szenarien werden geskipped)"
    MISSING_MANUAL+=("$f")
  fi
done

for f in "${CONTEXT_SLOTS[@]}"; do
  if [ -f "$CONTEXT_POOL/$f" ]; then
    echo "  ✓ $f (context)"
  else
    echo "  ✗ $f FEHLT (context-pool, synthetisch)"
    MISSING_SYNTH+=("$f")
  fi
done

if [ "${#MISSING_SYNTH[@]}" -gt 0 ]; then
  echo ""
  echo "Fehler: Synthetische Pool-Files fehlen — Setup abgebrochen." >&2
  echo "Loesung: scripts/generate_test_fixtures.py laufen lassen." >&2
  exit 1
fi

# ---- 2) Optional: bestehendes Projekt archivieren ------------------

if [ -d "$PROJECT_DIR" ]; then
  echo ""
  echo "--- Bestehendes Projekt gefunden ---"
  if [ "$ARCHIVE_EXISTING" -eq 1 ]; then
    TS="$(date +%Y%m%d-%H%M%S)"
    ARCHIVE_DIR="$ARCHIVE_ROOT/$TS/$SLUG"
    mkdir -p "$(dirname "$ARCHIVE_DIR")"
    echo "Archiviere $PROJECT_DIR nach $ARCHIVE_DIR ..."
    mv "$PROJECT_DIR" "$ARCHIVE_DIR"
    echo "  ✓ archiviert"
  else
    echo "Hinweis: Projekt existiert bereits. Lauf erneut mit --archive-existing,"
    echo "         um es nach .test-archive/ zu verschieben."
    echo "         Pool-Files werden ueberschrieben (Hash-identisch -> No-op)."
  fi
fi

# ---- 3) Projekt initialisieren -------------------------------------

echo ""
echo "--- Projekt initialisieren ---"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
DISCO_WORKSPACE="$DEV_WORKSPACE" \
  uv run disco project init "$SLUG" \
    --name "E2E-Test: $SLUG" \
    --description "E2E-Test-Projekt, gesetzt durch setup_e2e_project.sh" \
  >/dev/null

echo "  ✓ disco project init"

# ---- 4) Pool-Files spiegeln ----------------------------------------

echo ""
echo "--- Pool-Files in Projekt spiegeln ---"

mkdir -p "$PROJECT_DIR/sources" "$PROJECT_DIR/context"

COPIED_SOURCES=0
for f in "${SOURCE_SLOTS_SYNTH[@]}" "${SOURCE_SLOTS_MANUAL[@]}"; do
  if [ -f "$SOURCES_POOL/$f" ]; then
    cp -p "$SOURCES_POOL/$f" "$PROJECT_DIR/sources/$f"
    COPIED_SOURCES=$((COPIED_SOURCES + 1))
  fi
done

COPIED_CONTEXT=0
for f in "${CONTEXT_SLOTS[@]}"; do
  if [ -f "$CONTEXT_POOL/$f" ]; then
    cp -p "$CONTEXT_POOL/$f" "$PROJECT_DIR/context/$f"
    COPIED_CONTEXT=$((COPIED_CONTEXT + 1))
  fi
done

echo "  sources/ : $COPIED_SOURCES Files kopiert"
echo "  context/ : $COPIED_CONTEXT Files kopiert"

# ---- 5) Status-Report ----------------------------------------------

echo ""
echo "=== Setup fertig ==="
echo ""
echo "Projekt    : $PROJECT_DIR"
echo "Sources    : $COPIED_SOURCES Files (in sources/)"
echo "Context    : $COPIED_CONTEXT Files (in context/)"
if [ "${#MISSING_MANUAL[@]}" -gt 0 ]; then
  echo ""
  echo "Skipped-Slots (manuell zu beschaffen — siehe MANIFEST.md):"
  for f in "${MISSING_MANUAL[@]}"; do
    echo "  - $f"
  done
fi
echo ""
echo "Naechste Schritte:"
echo "  1) Dev-Server starten (Port 8766, Workspace: $DEV_WORKSPACE)"
echo "  2) Im Browser http://127.0.0.1:8766 oeffnen, Projekt '$SLUG' auswaehlen"
echo "  3) Test-Szenario aus tests/e2e/scenarios/ folgen"
echo ""
