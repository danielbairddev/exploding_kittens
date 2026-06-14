#!/usr/bin/env bash
#
# Hands-off training for Zeus — the win-maximising twin of Hades.
#
# Single phase vs the competitive fleet + self-play, until the win-rate target is
# hit or training stalls. Crash-resilient (always --resume; auto-restarts on a
# non-zero exit). New bests auto-deploy to agents/zeus_weights.json. Self-stops
# and writes a DONE summary.
#
# NOTE: don't run this at the same time as the Hades full run on the same box —
# they'll fight for cores. Launch Zeus after Hades finishes (or lower workers).
#
# Usage:
#   training/zeus/run_full_training.sh
#   HADES_WORKERS=6 ZEUS_TARGET=0.45 training/zeus/run_full_training.sh
#
# Tunables (env vars / defaults):
#   ZEUS_WORKERS       parallel workers           (cpu count - 1)
#   ZEUS_GAMES         games per iter             (128)
#   ZEUS_EVAL_N        eval games per checkpoint  (2000)
#   ZEUS_EVAL_EVERY    iters between evals        (20)
#   ZEUS_MAX_ITERS     iteration cap              (3000)
#   ZEUS_TARGET        stop when win rate >= this (0.40)
#   ZEUS_PATIENCE      evals w/o improvement->stop(80)
#   ZEUS_MAX_RESTARTS  crash restarts             (50)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY="python3"; fi
if command -v nproc >/dev/null 2>&1; then NCPU="$(nproc)"; else NCPU="$(sysctl -n hw.ncpu 2>/dev/null || echo 2)"; fi
DEF_WORKERS=$(( NCPU > 1 ? NCPU - 1 : 1 ))

WORKERS="${ZEUS_WORKERS:-$DEF_WORKERS}"
GAMES="${ZEUS_GAMES:-128}"
EVAL_N="${ZEUS_EVAL_N:-2000}"
EVAL_EVERY="${ZEUS_EVAL_EVERY:-20}"
MAX_ITERS="${ZEUS_MAX_ITERS:-3000}"
TARGET="${ZEUS_TARGET:-0.40}"
PATIENCE="${ZEUS_PATIENCE:-80}"
MAX_RESTARTS="${ZEUS_MAX_RESTARTS:-50}"

LOG_DIR="$REPO/logs"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/zeus_full_train.log"
STATUS="$LOG_DIR/zeus_train_status.txt"
DONE_MARKER="$LOG_DIR/zeus_train_DONE.txt"
rm -f "$DONE_MARKER"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
status() { echo "$(ts)  $*" | tee -a "$STATUS"; }

status "=== Zeus full training started ==="
status "python=$PY workers=$WORKERS games=$GAMES eval_n=$EVAL_N target=${TARGET} max_iters=$MAX_ITERS"

status "preflight: gradcheck (shared Hades architecture)"
if ! "$PY" -m training.hades.gradcheck >> "$LOG" 2>&1; then
  status "ABORT: gradcheck failed (see $LOG)"
  echo "GRADCHECK FAILED" > "$DONE_MARKER"
  exit 1
fi
status "gradcheck PASSED"

restarts=0
while true; do
  status "launching train.py (attempt $((restarts+1)))"
  "$PY" -m training.zeus.train --resume --workers "$WORKERS" --games "$GAMES" \
        --eval_n "$EVAL_N" --eval_every "$EVAL_EVERY" --iters "$MAX_ITERS" \
        --patience "$PATIENCE" --target_winrate "$TARGET" >> "$LOG" 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then status "train.py completed cleanly"; break; fi
  restarts=$((restarts+1))
  status "train.py crashed (rc=$rc); restart $restarts/$MAX_RESTARTS in 10s"
  if [ $restarts -ge $MAX_RESTARTS ]; then
    status "giving up after $restarts restarts"; echo "FAILED after $restarts restarts" > "$DONE_MARKER"; exit 1
  fi
  sleep 10
done

status "final evaluation (n=$EVAL_N) ..."
FINAL="$("$PY" - <<PYEOF
import json, os
from training.zeus.rollout import evaluate
w = json.load(open(os.path.join("$REPO", "agents", "zeus_weights.json")))
print(round(evaluate(w, n=$EVAL_N) * 100, 2))
PYEOF
)"

{
  echo "Zeus training finished: $(ts)"
  echo "Final deployed win rate vs [Coyote,Rhino,Elephant,Sly2]: ${FINAL}%  (random baseline ~20%)"
  echo "Best history: training/zeus/bests.jsonl"
  echo "Deployed weights: agents/zeus_weights.json"
  echo "Enable ZeusAgent in web/dashboard_server.py + bump stats versions to put it live."
} | tee -a "$STATUS" > "$DONE_MARKER"

status "=== Zeus full training DONE (final win ${FINAL}%) ==="
exit 0
