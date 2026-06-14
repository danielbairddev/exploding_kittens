#!/bin/bash
# Restart the Live Arena dashboard (run on the server).
# Env: APP_DIR, PORT, EK_DEPLOY_SHA, EK_DEPLOY_BY, EK_DEPLOY_AT
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ek-arena}"
PORT="${PORT:-8767}"
PORT2="${PORT2:-6767}"


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
nohup python3 web/dashboard_server.py "$PORT2" "skulls"  > /tmp/skulls-arena.log 2>&1 < /dev/null &

deployed_ek=false
deployed_skulls=false
for i in $(seq 1 60); do
  sleep 1
  if ! $deployed_ek || ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q "$PORT"; then
    echo "Live Exploding Arena up at http://0.0.0.0:$PORT ($EK_DEPLOY_SHA by $EK_DEPLOY_BY)"
    deployed_ek=true
  elif ! $deployed_skulls || ss -tlnp "sport = :$PORT2" 2>/dev/null | grep -q "$PORT2"; then
    echo "Live Skulls Arena up at http://0.0.0.0:$PORT2 ($EK_DEPLOY_SHA by $EK_DEPLOY_BY)"
    deployed_skulls=true
  elif $deployed_ek && $deployed_skulls; then
   break
fi

done
if $deployed_ek && $deployed_skulls; then
   exit 0
fi

if ! $deployed_ek; then
   echo "ERROR: server didn't start. Check /tmp/ek-arena.log"
   tail -20 /tmp/ek-arena.log || true
fi

if ! $deployed_skulls; then
   echo "ERROR: server didn't start. Check /tmp/ek-arena.log"
   tail -20  /tmp/skulls-arena.log || true
fi
exit 1
