#!/bin/bash
set -e

SERVER="root@162.243.161.27"
PORT=8767
APP_DIR="/opt/ek-arena"

echo "Deploying Live Arena dashboard to $SERVER:$PORT..."

# The dashboard imports the game engine + agent packages, so ship those too.
# logs/ is intentionally NOT deleted — it holds the persisted stats snapshot.
ssh "$SERVER" "mkdir -p $APP_DIR"
rsync -az \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' \
  dashboard_server.py dashboard_page.py game agents protocol \
  "$SERVER:$APP_DIR/"

ssh "$SERVER" bash <<REMOTE
set -e
pkill -f "dashboard_server.py" 2>/dev/null || true
for i in \$(seq 1 10); do
  ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q "$PORT" || break
  sleep 1
done

cd $APP_DIR
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
