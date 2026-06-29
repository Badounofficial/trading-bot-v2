#!/bin/bash
# =============================================================================
# Backup Script — Trading Bot v2
# =============================================================================
# Usage:
#   bash scripts/backup.sh                 # backup with default message
#   bash scripts/backup.sh "Session 3 — OB detection complete"
#
# What this does:
#   1. Git status check (warn if uncommitted changes)
#   2. Git add + commit with timestamp + message
#   3. Create ZIP backup in backups/ folder (datestamped)
#   4. List recent backups
#   5. Reminder for external disk backup
# =============================================================================

set -e  # Exit on error

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get project root (one level up from this script)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
cd "$PROJECT_ROOT"

# Default message
DEFAULT_MSG="Auto-backup $(date +%Y-%m-%d_%H:%M)"
MSG="${1:-$DEFAULT_MSG}"

echo -e "${BLUE}====================================================================${NC}"
echo -e "${BLUE}  Trading Bot v2 — Backup Script${NC}"
echo -e "${BLUE}====================================================================${NC}"
echo ""
echo -e "  Project: ${PROJECT_ROOT}"
echo -e "  Time:    $(date +'%Y-%m-%d %H:%M:%S')"
echo -e "  Message: ${MSG}"
echo ""

# =============================================================================
# Step 1: Verify we're in a git repo (or init)
# =============================================================================
if [ ! -d ".git" ]; then
    echo -e "${YELLOW}⚠ No Git repo detected. Initializing...${NC}"
    git init -q
    git branch -M main 2>/dev/null || true
    echo -e "${GREEN}✓ Git initialized${NC}"
fi

# =============================================================================
# Step 2: Git commit
# =============================================================================
echo -e "${BLUE}── Step 1/4: Git commit ──${NC}"
git add .
N_CHANGES=$(git status --porcelain | wc -l | tr -d ' ')

if [ "$N_CHANGES" -eq "0" ]; then
    echo -e "  ${YELLOW}No changes to commit${NC}"
else
    git commit -m "$MSG" -q
    echo -e "  ${GREEN}✓ Committed $N_CHANGES change(s): \"$MSG\"${NC}"
fi
echo ""

# =============================================================================
# Step 3: Create ZIP backup
# =============================================================================
echo -e "${BLUE}── Step 2/4: ZIP backup ──${NC}"
mkdir -p backups
TIMESTAMP=$(date +%Y%m%d_%H%M)
BACKUP_NAME="trading-bot-v2_${TIMESTAMP}.zip"
BACKUP_PATH="backups/${BACKUP_NAME}"

# Create ZIP excluding the heavy cache files (they're 500MB+)
zip -r -q "$BACKUP_PATH" \
    . \
    -x "cache/*" \
    -x "backups/*" \
    -x "venv/*" \
    -x "__pycache__/*" \
    -x "*/__pycache__/*" \
    -x ".git/*" \
    -x ".DS_Store"

SIZE=$(du -h "$BACKUP_PATH" | cut -f1)
echo -e "  ${GREEN}✓ Created ${BACKUP_PATH} (${SIZE})${NC}"
echo ""

# =============================================================================
# Step 4: List recent backups
# =============================================================================
echo -e "${BLUE}── Step 3/4: Recent backups ──${NC}"
ls -lht backups/ | head -6 | awk 'NR>1 {printf "  %s  %s\n", $5, $9}'
echo ""

# =============================================================================
# Step 5: Reminder for external disk
# =============================================================================
echo -e "${BLUE}── Step 4/4: External backup reminder ──${NC}"
echo -e "  ${YELLOW}⚠ Don't forget to copy this backup to your external drive!${NC}"
echo -e ""
echo -e "  Suggested command:"
echo -e "    cp ${BACKUP_PATH} /Volumes/<your-external>/trading-bot-backups/"
echo -e ""

# =============================================================================
# Summary
# =============================================================================
echo -e "${GREEN}====================================================================${NC}"
echo -e "${GREEN}  ✓ BACKUP COMPLETE${NC}"
echo -e "${GREEN}====================================================================${NC}"
echo ""

# Optional: show file count and total size
N_FILES=$(find . -type f \
    -not -path "./.git/*" \
    -not -path "./cache/*" \
    -not -path "./backups/*" \
    -not -path "./venv/*" \
    -not -path "*/__pycache__/*" \
    | wc -l | tr -d ' ')
echo -e "  Project file count: $N_FILES files (excluding cache/venv/backups)"
echo -e "  Git log (last 5):"
git log --oneline -5 2>/dev/null | sed 's/^/    /'
echo ""
