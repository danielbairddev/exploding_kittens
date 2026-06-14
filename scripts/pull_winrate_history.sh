#!/usr/bin/env bash
# Pull the server's winrate_history.tsv and commit it to git.
#
# Usage:
#   ./scripts/pull_winrate_history.sh              # one-shot pull
#   watch -n 60 ./scripts/pull_winrate_history.sh  # poll every minute
#
# Requires: curl, git. No special credentials — the endpoint is public.
set -euo pipefail

SERVER_URL="${EK_SERVER_URL:-http://162.243.161.27:8767}"
DEST="logs/winrate_history.tsv"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$REPO_ROOT"

# Ensure logs/ directory is tracked.
mkdir -p logs

echo "[pull_winrate] fetching from $SERVER_URL/api/winrate_history ..."
curl -fsSL "$SERVER_URL/api/winrate_history" -o "$DEST"

LINE_COUNT=$(wc -l < "$DEST" | tr -d ' ')
echo "[pull_winrate] $LINE_COUNT rows in $DEST"

# Only commit if there are actual changes.
if git diff --quiet "$DEST" 2>/dev/null && git ls-files --error-unmatch "$DEST" &>/dev/null; then
    echo "[pull_winrate] no changes — nothing to commit"
    exit 0
fi

git add "$DEST"
git commit -m "chore: update winrate history snapshot ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
echo "[pull_winrate] committed. Run 'git push' to push upstream."
