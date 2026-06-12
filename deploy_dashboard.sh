#!/bin/bash
set -e

SERVER="root@162.243.161.27"
PORT=8767
APP_DIR="/opt/ek-arena"

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

# Identity stamp so we can tell who deployed what (shown on the site, top-right).
SHA=$(git rev-parse --short HEAD)
BY=$(git config user.name 2>/dev/null || echo "${USER:-unknown}")
AT=$(date -u +"%Y-%m-%d %H:%M UTC")

echo "Deploying Live Arena dashboard to $SERVER:$PORT  (as '$BY' @ $SHA)..."

# The dashboard imports the game engine + agent packages, so ship those too.
# logs/ is intentionally NOT deleted — it holds the persisted stats snapshot.
ssh "$SERVER" "mkdir -p $APP_DIR"
rsync -az \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
  dashboard_server.py dashboard_page.py play.py play_page.py game agents protocol \
  "$SERVER:$APP_DIR/"

ssh "$SERVER" bash <<REMOTE
set -e
pkill -f "dashboard_server.py" 2>/dev/null || true
for i in \$(seq 1 10); do
  ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q "$PORT" || break
  sleep 1
done

cd $APP_DIR
EK_DEPLOY_SHA='$SHA' EK_DEPLOY_BY='$BY' EK_DEPLOY_AT='$AT' \
  nohup python3 dashboard_server.py $PORT > /tmp/ek-arena.log 2>&1 </dev/null &

sleep 2
if ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q "$PORT"; then
  echo "Live Arena up at http://162.243.161.27:$PORT"
else
  echo "ERROR: server didn't start. Check /tmp/ek-arena.log"
  tail -20 /tmp/ek-arena.log || true
  exit 1
fi

echo "Dashboard running (continuous simulation, no auto-teardown)"
REMOTE
