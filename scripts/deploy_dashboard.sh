#!/bin/bash
set -euo pipefail

SERVER="${SERVER:-root@162.243.161.27}"
PORT="${PORT:-8767}"
APP_DIR="${APP_DIR:-/opt/ek-arena}"

# Files shipped via rsync on legacy (non-git) servers. Git-based servers sync
# via fetch+reset instead; this list still matters before setup_auto_deploy.
RSYNC_PATHS=(
  web scripts smoke_test.py
  game agents protocol
)

# --------------------------------------------------------------------------
# Guard: never deploy code that isn't committed and pushed to GitHub, so the
# repo always reflects what's actually running. Bypass with ALLOW_DIRTY=1.
# --------------------------------------------------------------------------
if [ "${ALLOW_DIRTY:-0}" != "1" ]; then
  branch=$(git rev-parse --abbrev-ref HEAD)
  if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: uncommitted changes — commit & push before deploying (or ALLOW_DIRTY=1):"
    git status --short
    exit 1
  fi
  upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)
  if [ -z "$upstream" ]; then
    echo "ERROR: branch '$branch' has no upstream. Push it first: git push -u origin $branch"
    exit 1
  fi
  git fetch -q origin "$branch" 2>/dev/null || true
  if [ "$(git rev-parse HEAD)" != "$(git rev-parse "$upstream")" ]; then
    echo "ERROR: local '$branch' differs from '$upstream' — push your commits first (or ALLOW_DIRTY=1)."
    echo "  local : $(git rev-parse --short HEAD)"
    echo "  remote: $(git rev-parse --short "$upstream")"
    exit 1
  fi
  echo "Git check OK: $branch @ $(git rev-parse --short HEAD) matches $upstream"
fi

FULL_SHA=$(git rev-parse HEAD)
SHA=$(git rev-parse --short HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
BY=$(git config user.name 2>/dev/null || echo "${USER:-unknown}")
AT=$(TZ="America/Los_Angeles" date +"%Y-%m-%d %H:%M %Z")
# Embed in the remote script (not positional args — BY/AT contain spaces).
_esc_sq() { printf '%s' "$1" | sed "s/'/'\\\\''/g"; }
BY_Q=$(_esc_sq "$BY")
AT_Q=$(_esc_sq "$AT")

echo "Deploying Live Arena dashboard to $SERVER:$PORT  (as '$BY' @ $SHA)..."

# logs/ is intentionally NOT deleted — it holds the persisted stats snapshot.
ssh "$SERVER" "mkdir -p $APP_DIR"

# Legacy boxes: rsync. Git boxes: skip rsync (sync happens in the remote step).
if ssh "$SERVER" "[ ! -d '$APP_DIR/.git' ]"; then
  echo "Legacy sync: rsync -> $APP_DIR"
  rsync -az \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
    "${RSYNC_PATHS[@]}" \
    "$SERVER:$APP_DIR/"
fi

ssh "$SERVER" bash -s "$APP_DIR" "$PORT" "$FULL_SHA" "$BRANCH" <<REMOTE
set -euo pipefail
APP_DIR="\$1" PORT="\$2" FULL_SHA="\$3" BRANCH="\$4"
SHA='$SHA'
BY='$BY_Q'
AT='$AT_Q'

if [ -d "$APP_DIR/.git" ]; then
  echo "Git sync: origin/$BRANCH @ $SHA"
  git -C "$APP_DIR" fetch -q origin "$BRANCH"
  git -C "$APP_DIR" reset --hard "$FULL_SHA"
  chmod +x "$APP_DIR/scripts/auto_deploy.sh" "$APP_DIR/scripts/arena_restart.sh" 2>/dev/null || true
  if [ "$BRANCH" != "main" ] && pgrep -f "auto_deploy.sh" >/dev/null 2>&1; then
    echo "Stopping auto-deploy poller (tracks main; you deployed $BRANCH)"
    pkill -f "auto_deploy.sh" 2>/dev/null || true
  fi
else
  echo "Rsync sync (no .git in $APP_DIR)"
  chmod +x "$APP_DIR/arena_restart.sh" 2>/dev/null || true
fi

export APP_DIR PORT EK_DEPLOY_SHA="$SHA" EK_DEPLOY_BY="$BY" EK_DEPLOY_AT="$AT"
exec "$APP_DIR/scripts/arena_restart.sh"
REMOTE

echo "Dashboard running (continuous simulation, no auto-teardown)"
