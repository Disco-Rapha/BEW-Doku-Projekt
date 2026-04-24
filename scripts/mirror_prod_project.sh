#!/usr/bin/env bash
# Klont ein Prod-Projekt non-destruktiv in den Dev-Staging-Workspace
# zur Migrations-Probe.
#
# Quelle (~/Disco/projects/<slug>) wird ausschliesslich gelesen.
# Ziel (~/Disco-dev/staging/<slug>) wird auf exakte Kopie der Quelle
# gebracht (rsync --delete entfernt verwaiste Dateien im Ziel).
#
# Usage:
#   scripts/mirror_prod_project.sh <slug>
#   scripts/mirror_prod_project.sh --dry-run <slug>
#
# Env-Overrides:
#   PROD_WORKSPACE  (Default: ~/Disco)
#   STAGING_ROOT    (Default: ~/Disco-dev/staging)

set -euo pipefail

PROD_WORKSPACE="${PROD_WORKSPACE:-$HOME/Disco}"
STAGING_ROOT="${STAGING_ROOT:-$HOME/Disco-dev/staging}"

DRY_RUN=0
SLUG=""

print_help() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
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
  echo "Usage: $0 [--dry-run] <slug>" >&2
  exit 2
fi

SRC="$PROD_WORKSPACE/projects/$SLUG"
DST="$STAGING_ROOT/$SLUG"

if [ ! -d "$SRC" ]; then
  echo "Fehler: Quell-Projekt nicht gefunden: $SRC" >&2
  exit 1
fi

SRC_SIZE="$(du -sh "$SRC" | cut -f1)"

echo "Quelle : $SRC"
echo "Ziel   : $DST"
echo "Groesse: $SRC_SIZE"
echo ""

if [ -d "$DST" ]; then
  echo "Achtung: Ziel-Verzeichnis existiert bereits."
  echo "         rsync --delete bringt es auf exakte Kopie der Quelle"
  echo "         (alles was dort ist und nicht in der Quelle → wird geloescht)."
  if [ "$DRY_RUN" -eq 0 ]; then
    read -r -p "Fortfahren? [y/N] " REPLY
    if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
      echo "Abbruch."
      exit 0
    fi
  fi
  echo ""
fi

mkdir -p "$STAGING_ROOT"

RSYNC_ARGS=("-a" "--delete" "--stats")
if [ "$DRY_RUN" -eq 1 ]; then
  RSYNC_ARGS+=("--dry-run")
  echo "[DRY-RUN] Kein Schreibvorgang — zeigt nur, was rsync tun wuerde."
  echo ""
fi

rsync "${RSYNC_ARGS[@]}" "$SRC/" "$DST/"

echo ""
if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry-Run beendet. Fuer echten Mirror ohne --dry-run neu starten."
  exit 0
fi

echo "Mirror fertig: $DST"
echo ""
echo "--- Naechste Schritte: Migrations gegen die Staging-Kopie testen ---"
echo ""
echo "1) In einem neuen Terminal, Server gegen das Staging-Workspace starten:"
echo ""
echo "     cd \"$(cd "$(dirname "$0")/.." && pwd)\""
echo "     DISCO_WORKSPACE=\"$STAGING_ROOT\" \\"
echo "     uv run uvicorn disco.api.main:app --host 127.0.0.1 --port 8766 --reload"
echo ""
echo "   Port 8766 statt 8000/8765 — vermeidet Kollision mit Dev/Prod."
echo ""
echo "2) Im Browser http://127.0.0.1:8766 oeffnen, Projekt '$SLUG' auswaehlen."
echo "   Beim ersten Zugriff wendet Disco alle offenen Migrationen an."
echo "   Treten Fehler auf → im Server-Log sichtbar."
echo ""
echo "3) Staging-Kopie wieder loeschen, wenn fertig getestet:"
echo ""
echo "     rm -rf \"$DST\""
