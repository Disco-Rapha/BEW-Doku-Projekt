#!/usr/bin/env bash
# Startet Datasette auf localhost:8001 und öffnet den Browser.
# Abbruch mit Ctrl+C.

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f db/disco.db ]; then
    echo "Datenbank db/disco.db fehlt. Bitte zuerst:"
    echo "  uv run bew db init"
    exit 1
fi

exec uv run datasette serve db/disco.db \
    --port 8001 \
    --open
