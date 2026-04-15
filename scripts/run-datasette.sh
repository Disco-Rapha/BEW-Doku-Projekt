#!/usr/bin/env bash
# Startet Datasette auf localhost:8001 und öffnet den Browser.
# Abbruch mit Ctrl+C.

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f db/bew.db ]; then
    echo "Datenbank db/bew.db fehlt. Bitte zuerst:"
    echo "  uv run bew db init"
    exit 1
fi

exec uv run datasette serve db/bew.db \
    --port 8001 \
    --open
