#!/bin/bash
# Pull latest training weights for all active bots, bump stats_version, commit, push.
#
# Usage: ./scripts/deploy_weights.sh [--dry-run]
#
# Bots and their sources:
#   Rhino      <- server: training/rhino/best_policy.json    -> agents/rhino_weights.json
#   Gorilla    <- server: training/gorilla/best_policy.json  -> agents/orangutan2_weights.json
#   Elephant   <- local:  training/elephant/best_policy.json -> agents/elephant_weights.json
set -euo pipefail

SERVER="root@162.243.161.27"
APP_DIR="/opt/ek-arena"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

changed=()

echo "=== Fetching weights ==="

fetch_server() {
  local name="$1" src="$2" dst="$3"
  local tmp; tmp=$(mktemp)
  scp -q "$SERVER:$APP_DIR/$src" "$tmp"
  if ! cmp -s "$tmp" "$REPO/$dst"; then
    if $DRY_RUN; then
      echo "  $name: would update (changed)"
    else
      cp "$tmp" "$REPO/$dst"
      echo "  $name: updated"
      changed+=("$dst")
    fi
  else
    echo "  $name: unchanged"
  fi
  rm "$tmp"
}

fetch_local() {
  local name="$1" src="$2" dst="$3"
  if ! cmp -s "$REPO/$src" "$REPO/$dst"; then
    if $DRY_RUN; then
      echo "  $name: would update (changed)"
    else
      cp "$REPO/$src" "$REPO/$dst"
      echo "  $name: updated"
      changed+=("$dst")
    fi
  else
    echo "  $name: unchanged"
  fi
}

fetch_server  "Rhino"      "training/rhino/best_policy.json"   "agents/rhino_weights.json"
fetch_server  "Orangutan2" "training/gorilla/best_policy.json" "agents/orangutan2_weights.json"
fetch_local   "Elephant"   "training/elephant/best_policy.json" "agents/elephant_weights.json"

echo ""
echo "=== Training log snippets ==="
ssh "$SERVER" 'grep "new best" /tmp/rhino_train.log 2>/dev/null | tail -1 | sed "s/^/  Rhino:  /"' || true
ssh "$SERVER" 'grep "new best" /tmp/gorilla_train.log 2>/dev/null | tail -1 | sed "s/^/  Gorilla: /"' || true
grep "new best" /tmp/elephant_train.log 2>/dev/null | tail -1 | sed 's/^/  Elephant: /' || true

if $DRY_RUN; then
  echo ""
  echo "(dry-run — nothing written)"
  exit 0
fi

echo ""
echo "=== Bumping stats_version ==="

# Find current version (pick from any agent file)
current=$(grep -h "stats_version" "$REPO"/agents/*.py | grep -v ian | grep -o "[0-9]*" | sort -n | tail -1)
next=$((current + 1))
echo "  $current -> $next"

sed -i '' "s/\"stats_version\": $current/\"stats_version\": $next/g" "$REPO"/agents/*.py
sed -i '' "s/'stats_version': $current/'stats_version': $next/g" "$REPO"/agents/*.py

echo ""
echo "=== Committing ==="

cd "$REPO"
git add agents/

# Build commit message listing what changed
weight_list=$(printf '%s\n' "${changed[@]}" | sed 's|agents/||;s|_weights.json||' | paste -sd ', ' -)
if [[ -z "$weight_list" ]]; then
  weight_list="no weight changes"
fi

git commit -m "Deploy weights (${weight_list}); bump stats_version to ${next}.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git push
echo ""
echo "Done. Auto-deploy will pick it up within 60s."
