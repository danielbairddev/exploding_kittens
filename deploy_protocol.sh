#!/bin/bash
set -e

SERVER="root@206.189.177.24"
PORT=8766
APP_DIR="/opt/ek-protocol"

echo "Deploying protocol docs to $SERVER:$PORT..."

cat protocol_server.py | ssh "$SERVER" "mkdir -p $APP_DIR && cat > $APP_DIR/protocol_server.py"

ssh "$SERVER" bash <<REMOTE
pkill -f "protocol_server.py" 2>/dev/null || true
for i in \$(seq 1 10); do
  ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q "$PORT" || break
  sleep 1
done

nohup python3 $APP_DIR/protocol_server.py $PORT > /tmp/ek-protocol.log 2>&1 </dev/null &

sleep 1
if ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q "$PORT"; then
  echo "Protocol docs live at http://206.189.177.24:$PORT"
else
  echo "ERROR: server didn't start. Check /tmp/ek-protocol.log"
  exit 1
fi

echo "Protocol server running (no auto-teardown)"
REMOTE
