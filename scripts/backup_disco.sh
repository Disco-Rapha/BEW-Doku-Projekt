#!/usr/bin/env bash
# Disco Backup-Skript
# ===================
# Erzeugt einen Timestamp-Snapshot von:
#   - ~/Disco/                              (Prod-Workspace)
#   - ~/Disco-dev/                          (Dev-Workspace)
#   - ~/Claude/BEW Doku Projekt/            (Worktree dev)
#   - ~/Claude/BEW Doku Prod/               (Worktree main)
#   - git bundle aller Branches             (kompakt, alle Refs + Reflog)
#
# Output unter ${BACKUP_ROOT}/<YYYY-MM-DD_HH-MM-SS>/
#
# Usage:
#   bash scripts/backup_disco.sh
# Environment:
#   BACKUP_ROOT  (Default: /Volumes/Raphal My Passport/disco-backup)

set -euo pipefail

# ----------------------------------------------------------------------------
# Konfiguration
# ----------------------------------------------------------------------------
BACKUP_ROOT="${BACKUP_ROOT:-/Volumes/Raphal My Passport/disco-backup}"
TS="$(date +%Y-%m-%d_%H-%M-%S)"
DEST="${BACKUP_ROOT}/${TS}"

DISCO_PROD="${HOME}/Disco"
DISCO_DEV="${HOME}/Disco-dev"
WORKTREE_DEV="${HOME}/Claude/BEW Doku Projekt"
WORKTREE_PROD="${HOME}/Claude/BEW Doku Prod"

EXCLUDES=(
  --exclude=.DS_Store
  --exclude=__pycache__
  --exclude='*.pyc'
  --exclude=.venv
  --exclude=node_modules
)

# Mindest-freier-Speicher in GB (32 GB Disco + Worktrees + Buffer)
MIN_FREE_GB=50

# ----------------------------------------------------------------------------
# Sanity Checks
# ----------------------------------------------------------------------------
# Pruefe das Volume-Mount (Eltern-Pfad), nicht das Backup-Subdir — das
# legen wir gleich an. Wir gehen vom uebergeordneten Pfad bis hoch, bis
# wir einen existierenden Pfad finden.
PARENT="$BACKUP_ROOT"
while [ ! -d "$PARENT" ] && [ "$PARENT" != "/" ]; do
  PARENT="$(dirname "$PARENT")"
done
if [ ! -d "$PARENT" ] || [ "$PARENT" = "/" ]; then
  echo "FEHLER: kein Pfad zu $BACKUP_ROOT existiert (Volume nicht gemountet?)" >&2
  exit 1
fi
mkdir -p "$BACKUP_ROOT"

FREE_KB=$(df -k "$BACKUP_ROOT" | awk 'NR==2 {print $4}')
FREE_GB=$((FREE_KB / 1024 / 1024))
if [ "$FREE_GB" -lt "$MIN_FREE_GB" ]; then
  echo "FEHLER: Nur ${FREE_GB} GB frei auf $BACKUP_ROOT (mind. ${MIN_FREE_GB} GB noetig)." >&2
  echo "Bitte alte Snapshots loeschen oder anderes Backup-Ziel waehlen." >&2
  exit 1
fi

mkdir -p "$DEST"
LOG="${DEST}/backup.log"

# Alle Folgenden Outputs gehen ins Log UND auf stdout
exec > >(tee -a "$LOG") 2>&1

echo "==== Disco Backup ${TS} ===="
echo "Ziel:      $DEST"
echo "Free:      ${FREE_GB} GB"
echo "Host:      $(hostname)"
echo "macOS:     $(sw_vers -productVersion)"
echo ""

# ----------------------------------------------------------------------------
# 1) Disco Prod-Workspace
# ----------------------------------------------------------------------------
echo "==== 1/5 rsync ~/Disco -> Disco/ ===="
START=$(date +%s)
rsync -aH "${EXCLUDES[@]}" \
  --stats \
  "${DISCO_PROD}/" "${DEST}/Disco/"
DUR=$(($(date +%s) - START))
echo "  → fertig in ${DUR}s"
echo ""

# ----------------------------------------------------------------------------
# 2) Disco Dev-Workspace
# ----------------------------------------------------------------------------
echo "==== 2/5 rsync ~/Disco-dev -> Disco-dev/ ===="
START=$(date +%s)
rsync -aH "${EXCLUDES[@]}" \
  --stats \
  "${DISCO_DEV}/" "${DEST}/Disco-dev/"
DUR=$(($(date +%s) - START))
echo "  → fertig in ${DUR}s"
echo ""

# ----------------------------------------------------------------------------
# 3) Code-Worktrees (komplett inkl. .git/)
# ----------------------------------------------------------------------------
echo "==== 3/5 rsync code worktrees -> worktrees/ ===="
mkdir -p "${DEST}/worktrees"
START=$(date +%s)
rsync -aH "${EXCLUDES[@]}" --stats \
  "${WORKTREE_DEV}/" "${DEST}/worktrees/BEW-Doku-Projekt-dev/"
rsync -aH "${EXCLUDES[@]}" --stats \
  "${WORKTREE_PROD}/" "${DEST}/worktrees/BEW-Doku-Prod/"
DUR=$(($(date +%s) - START))
echo "  → fertig in ${DUR}s"
echo ""

# ----------------------------------------------------------------------------
# 4) Git Bundle (alle Refs in einer Datei)
# ----------------------------------------------------------------------------
echo "==== 4/5 git bundle ===="
mkdir -p "${DEST}/git-bundle"
( cd "$WORKTREE_DEV" && \
  git bundle create "${DEST}/git-bundle/disco-all.bundle" --all && \
  git bundle verify "${DEST}/git-bundle/disco-all.bundle" )
echo ""

# ----------------------------------------------------------------------------
# 5) Manifest + Stichproben-Hashes
# ----------------------------------------------------------------------------
echo "==== 5/5 manifest + sample hashes ===="
{
  echo "Disco Backup Manifest"
  echo "Timestamp: $TS"
  echo "Host: $(hostname)"
  echo "User: $(whoami)"
  echo "macOS: $(sw_vers -productVersion)"
  echo "Backup-Root: $BACKUP_ROOT"
  echo ""
  echo "==== Sizes ===="
  du -sh "${DEST}"/* 2>/dev/null
  echo ""
  echo "==== Source vs Target (Top-Level) ===="
  printf "  source ~/Disco:        %s\n" "$(du -sh "${DISCO_PROD}" 2>/dev/null | awk '{print $1}')"
  printf "  target Disco:          %s\n" "$(du -sh "${DEST}/Disco" 2>/dev/null | awk '{print $1}')"
  printf "  source ~/Disco-dev:    %s\n" "$(du -sh "${DISCO_DEV}" 2>/dev/null | awk '{print $1}')"
  printf "  target Disco-dev:      %s\n" "$(du -sh "${DEST}/Disco-dev" 2>/dev/null | awk '{print $1}')"
} > "${DEST}/MANIFEST.txt"
cat "${DEST}/MANIFEST.txt"
echo ""

# Stichproben-Validation: 50 zufaellige Files aus Disco/, beide Seiten
# hashen und vergleichen.
# Hinweis: `find ... | sort -R | head` kann SIGPIPE (Exit 141) werfen, weil
# head early closed. Stattdessen: find komplett einlesen, dann awk-rand-shuffle,
# dann head — alles in einer Pipe-Stufe ohne Early-Close.
echo "==== Sample-Validation (50 random files aus ~/Disco) ===="
PASS=0
FAIL=0
MISSING=0
SAMPLE=$(find "${DISCO_PROD}" -type f 2>/dev/null \
          | awk 'BEGIN{srand()} {print rand() " " $0}' \
          | sort -k1,1n \
          | awk 'NR<=50 {sub(/^[^ ]+ /, ""); print}')
while IFS= read -r SRC; do
  [ -z "$SRC" ] && continue
  REL="${SRC#${DISCO_PROD}/}"
  DST="${DEST}/Disco/${REL}"
  if [ ! -f "$DST" ]; then
    MISSING=$((MISSING+1))
    echo "  MISSING: $REL"
    continue
  fi
  SRC_HASH=$(shasum -a 256 "$SRC" 2>/dev/null | awk '{print $1}')
  DST_HASH=$(shasum -a 256 "$DST" 2>/dev/null | awk '{print $1}')
  if [ "$SRC_HASH" = "$DST_HASH" ] && [ -n "$SRC_HASH" ]; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
    echo "  HASH-MISMATCH: $REL"
  fi
done <<< "$SAMPLE"

echo ""
echo "Sample-Validation: ${PASS} PASS, ${FAIL} HASH-MISMATCH, ${MISSING} MISSING"
echo ""

# ----------------------------------------------------------------------------
# Final Summary
# ----------------------------------------------------------------------------
TOTAL_SIZE=$(du -sh "$DEST" | awk '{print $1}')
echo "==== FINAL ===="
echo "Snapshot:  $DEST"
echo "Groesse:   $TOTAL_SIZE"
echo ""
if [ "$FAIL" -eq 0 ] && [ "$MISSING" -eq 0 ]; then
  echo "✅ BACKUP OK — ${TS}"
  exit 0
else
  echo "❌ BACKUP HAT FEHLER (siehe oben)"
  exit 1
fi
