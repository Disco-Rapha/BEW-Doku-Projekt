#!/usr/bin/env bash
# Combined-Wrapper für die Pipeline-Reform-v2-Migration eines Projekts.
#
# Macht in einem Rutsch:
#   1. Backup der zwei DBs (datastore.db + workspace.db)
#   2. Schema-Migration datastore  (scripts/migrate_pipeline_v2.py)
#   3. Verify datastore             (scripts/migrate_pipeline_v2.py verify)
#   4. Workspace-Pin-Migration      (scripts/migrate_workspace_pin.py)
#   5. Re-Verify
#
# Usage:
#     scripts/migrate_to_pipeline_v2.sh <project-path>
#
# Beispiel:
#     scripts/migrate_to_pipeline_v2.sh ~/Disco/projects/vgb-referenzlisten
#
# Idempotent: bricht ab wenn datastore schon migriert ist.

set -euo pipefail

PROJECT_PATH="${1:-}"
if [ -z "$PROJECT_PATH" ]; then
  echo "Usage: $0 <project-path>" >&2
  exit 2
fi
if [ ! -d "$PROJECT_PATH" ]; then
  echo "ERROR: Projekt-Verzeichnis existiert nicht: $PROJECT_PATH" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SLUG="$(basename "$PROJECT_PATH")"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$HOME/Disco-backup-pipeline-v2-rollout/${SLUG}_${TIMESTAMP}"

echo "==================== Migration zu Pipeline-Reform v2 ===================="
echo "Projekt: $SLUG"
echo "Pfad   : $PROJECT_PATH"
echo "Backup : $BACKUP_DIR"
echo

# 1. Backup (nur DBs)
echo "--- 1/5: Backup ---"
mkdir -p "$BACKUP_DIR"
cp "$PROJECT_PATH/datastore.db" "$BACKUP_DIR/" 2>/dev/null && echo "  ✓ datastore.db"
cp "$PROJECT_PATH/workspace.db" "$BACKUP_DIR/" 2>/dev/null && echo "  ✓ workspace.db"
echo

# 2. Datastore-Migration
echo "--- 2/5: Datastore-Migration ---"
cd "$REPO_ROOT"
uv run python scripts/migrate_pipeline_v2.py migrate "$PROJECT_PATH"
echo

# 3. Verify Datastore
echo "--- 3/5: Verify Datastore ---"
uv run python scripts/migrate_pipeline_v2.py verify "$PROJECT_PATH" || {
  echo "✗ Verify-Fehler! Rollback per:" >&2
  echo "   cp $BACKUP_DIR/datastore.db $PROJECT_PATH/datastore.db" >&2
  exit 3
}
echo

# 4. Workspace-Pin-Migration
echo "--- 4/5: Workspace-Pin-Migration ---"
uv run python scripts/migrate_workspace_pin.py migrate "$PROJECT_PATH"
echo

# 5. Re-Verify Datastore (sanity)
echo "--- 5/5: Final Verify ---"
uv run python scripts/migrate_pipeline_v2.py verify "$PROJECT_PATH" || {
  echo "✗ Final-Verify-Fehler! Bitte manuell prüfen." >&2
  exit 3
}
echo

echo "==================== ✓ Migration abgeschlossen: $SLUG ===================="
echo
echo "Backup liegt unter: $BACKUP_DIR"
echo
echo "Rollback bei Problemen:"
echo "  cp $BACKUP_DIR/datastore.db $PROJECT_PATH/datastore.db"
echo "  cp $BACKUP_DIR/workspace.db $PROJECT_PATH/workspace.db"
echo "  rm -rf $PROJECT_PATH/datastore.db-shm $PROJECT_PATH/datastore.db-wal"
echo "  rm -rf $PROJECT_PATH/workspace.db-shm $PROJECT_PATH/workspace.db-wal"
echo
echo "Nach 30 Tagen ohne Probleme: agent_sources_pre_migration + _migration_source_id_map"
echo "droppen + Backup-Ordner löschen."
