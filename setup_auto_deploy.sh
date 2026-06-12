#!/bin/bash
# One-time bootstrap: git-clone the arena on the server and start auto_deploy.sh.
#
# Replaces the rsync-based layout in /opt/ek-arena with a git checkout that
# auto_deploy.sh keeps synced to origin/main. Existing logs/ are preserved.
set -euo pipefail

SERVER="${SERVER:-root@162.243.161.27}"
APP_DIR="${APP_DIR:-/opt/ek-arena}"
PORT="${PORT:-8767}"
REPO_URL="${REPO_URL:-https://github.com/danielbairddev/exploding_kittens.git}"
BRANCH="${BRANCH:-main}"

echo "Setting up auto-deploy on $SERVER ($APP_DIR -> origin/$BRANCH)..."

ssh "$SERVER" bash -s "$APP_DIR" "$PORT" "$REPO_URL" "$BRANCH" <<'REMOTE'
set -euo pipefail
APP_DIR="$1"
PORT="$2"
REPO_URL="$3"
BRANCH="$4"

if [ ! -d "$APP_DIR/.git" ]; then
  echo "Converting $APP_DIR to a git checkout (preserving logs/)..."
  backup=""
  if [ -d "$APP_DIR/logs" ]; then
    backup=$(mktemp -d)
    cp -a "$APP_DIR/logs" "$backup/"
  fi
  if [ -d "$APP_DIR" ]; then
    mv "$APP_DIR" "${APP_DIR}.bak.$(date +%s)"
  fi
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  if [ -n "$backup" ]; then
    cp -a "$backup/logs" "$APP_DIR/"
    rm -rf "$backup"
  fi
else
  echo "Already a git repo — pulling latest $BRANCH"
  git -C "$APP_DIR" fetch -q origin "$BRANCH"
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
fi

chmod +x "$APP_DIR/auto_deploy.sh" "$APP_DIR/arena_restart.sh"

# Stop any previous poller, then start the dashboard.
pkill -f "auto_deploy.sh" 2>/dev/null || true

sha=$(git -C "$APP_DIR" rev-parse --short HEAD)
at=$(TZ="America/Los_Angeles" date +"%Y-%m-%d %H:%M %Z")
export APP_DIR PORT EK_DEPLOY_SHA="$sha" EK_DEPLOY_BY="setup" EK_DEPLOY_AT="$at"
"$APP_DIR/arena_restart.sh"
echo "Dashboard up @ $sha"

nohup "$APP_DIR/auto_deploy.sh" >/dev/null 2>&1 &
sleep 1
if pgrep -f "auto_deploy.sh" >/dev/null; then
  echo "Auto-deploy poller running (logs: /tmp/ek-auto-deploy.log)"
else
  echo "ERROR: poller didn't start"
  exit 1
fi
REMOTE

echo "Done. Arena: http://162.243.161.27:$PORT"
