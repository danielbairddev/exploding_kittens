#!/bin/bash
# Restart the Live Arena dashboard (run on the server).
# Env: APP_DIR, PORT, EK_DEPLOY_SHA, EK_DEPLOY_BY, EK_DEPLOY_AT
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ek-arena}"
PORT="${PORT:-8767}"

pkill -f "dashboard_server.py" 2>/dev/null || true
for _ in $(seq 1 10); do
  ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q "$PORT" || break
  sleep 1
done

cd "$APP_DIR"
export EK_DEPLOY_SHA="${EK_DEPLOY_SHA:-dev}"
export EK_DEPLOY_BY="${EK_DEPLOY_BY:-unknown}"
export EK_DEPLOY_AT="${EK_DEPLOY_AT:-}"
nohup python3 web/dashboard_server.py "$PORT" > /tmp/ek-arena.log 2>&1 </dev/null &

sleep 2
if ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q "$PORT"; then
  echo "Live Arena up at http://0.0.0.0:$PORT ($EK_DEPLOY_SHA by $EK_DEPLOY_BY)"
  exit 0
fi
echo "ERROR: server didn't start. Check /tmp/ek-arena.log"
tail -20 /tmp/ek-arena.log || true
exit 1
