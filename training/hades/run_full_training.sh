#!/usr/bin/env bash
#
# Hands-off full ian_folder for Hades (HADES_PLAN.md curriculum).
#
# Runs the complete curriculum with zero intervention:
#   Phase 1 (bootstrap): learn to self-destruct vs the winner fleet.
#   Phase 2 (crucible):  out-lose the loser fleet + self-play, until the
#                        survival target is hit or ian_folder stalls.
#
# Crash-resilient: every phase auto-resumes from ian_folder/hades/checkpoint.json
# (always --resume, which is safe and avoids clobbering deployed weights). New
# bests auto-deploy to agents/hades_weights.json. Self-terminating: stops on
# target survival, patience stall, or the iter cap — then writes a DONE summary.
#
# Usage:
#   ian_folder/hades/run_full_training.sh
#   HADES_WORKERS=6 HADES_TARGET=0.02 ian_folder/hades/run_full_training.sh
#
# Tunables (env vars, with defaults):
#   HADES_WORKERS         parallel rollout workers          (cpu count - 1)
#   HADES_GAMES           games per iteration               (128)
#   HADES_EVAL_N          eval games per checkpoint         (2000)
#   HADES_EVAL_EVERY      iters between evals               (20)
#   HADES_BOOT_ITERS      phase-1 iteration budget          (120)
#   HADES_CRUCIBLE_ITERS  phase-2 iteration cap             (3000)
#   HADES_TARGET          stop when survival <= this        (0.02)
#   HADES_PATIENCE        phase-2 evals w/o improvement->stop(80)
#   HADES_MAX_RESTARTS    crash restarts per phase          (50)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

# --- python: prefer repo venv, else python3 ---
if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY="python3"; fi

# --- cpu count (linux + macos) ---
if command -v nproc >/dev/null 2>&1; then NCPU="$(nproc)"; else NCPU="$(sysctl -n hw.ncpu 2>/dev/null || echo 2)"; fi
DEF_WORKERS=$(( NCPU > 1 ? NCPU - 1 : 1 ))

WORKERS="${HADES_WORKERS:-$DEF_WORKERS}"
GAMES="${HADES_GAMES:-128}"
EVAL_N="${HADES_EVAL_N:-2000}"
EVAL_EVERY="${HADES_EVAL_EVERY:-20}"
BOOT_ITERS="${HADES_BOOT_ITERS:-120}"
CRUCIBLE_ITERS="${HADES_CRUCIBLE_ITERS:-3000}"
TARGET="${HADES_TARGET:-0.02}"
PATIENCE="${HADES_PATIENCE:-80}"
MAX_RESTARTS="${HADES_MAX_RESTARTS:-50}"

LOG_DIR="$REPO/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/hades_full_train.log"
STATUS="$LOG_DIR/hades_train_status.txt"
DONE_MARKER="$LOG_DIR/hades_train_DONE.txt"
rm -f "$DONE_MARKER"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
status() { echo "$(ts)  $*" | tee -a "$STATUS"; }
log()    { echo "$(ts)  $*" >> "$LOG"; }

status "=== Hades full training started ==="
status "python=$PY workers=$WORKERS games=$GAMES eval_n=$EVAL_N target=${TARGET} boot_iters=$BOOT_ITERS crucible_iters=$CRUCIBLE_ITERS"
log    "=== run_full_training.sh started: workers=$WORKERS games=$GAMES ==="

# --- preflight: architecture/backprop must be correct before a long run ---
status "preflight: gradcheck"
if ! "$PY" -m ian_folder.hades.gradcheck >> "$LOG" 2>&1; then
  status "ABORT: gradcheck failed (see $LOG)"
  echo "GRADCHECK FAILED" > "$DONE_MARKER"
  exit 1
fi
status "gradcheck PASSED"

# run_phase <label> <extra train.py args...>
# retries on non-zero exit (crash); train.py exits 0 on normal stop/target/stall.
run_phase() {
  local label="$1"; shift
  local restarts=0
  while true; do
    status "[$label] launching train.py (attempt $((restarts+1)))"
    log "[$label] args: $*"
    "$PY" -m ian_folder.hades.train "$@" >> "$LOG" 2>&1
    local rc=$?
    if [ $rc -eq 0 ]; then
      status "[$label] completed cleanly"
      return 0
    fi
    restarts=$((restarts+1))
    status "[$label] train.py crashed (rc=$rc); restart $restarts/$MAX_RESTARTS in 10s"
    if [ $restarts -ge $MAX_RESTARTS ]; then
      status "[$label] giving up after $restarts restarts"
      return 1
    fi
    sleep 10
  done
}

COMMON=(--resume --workers "$WORKERS" --games "$GAMES" --eval_n "$EVAL_N" --eval_every "$EVAL_EVERY")

# --- Phase 1: bootstrap (fixed budget; patience high so it runs the full budget) ---
run_phase bootstrap --phase bootstrap --iters "$BOOT_ITERS" --patience 1000000 "${COMMON[@]}"

# --- Phase 2: crucible (until target survival, stall, or iter cap) ---
run_phase crucible --phase crucible --iters "$CRUCIBLE_ITERS" \
          --patience "$PATIENCE" --target_survival "$TARGET" "${COMMON[@]}"

# --- final eval + summary ---
status "final evaluation (n=$EVAL_N) ..."
FINAL="$("$PY" - <<PYEOF
import json, os
from ian_folder.hades.rollout import evaluate
w = json.load(open(os.path.join("$REPO", "agents", "hades_weights.json")))
print(round(evaluate(w, n=$EVAL_N) * 100, 2))
PYEOF
)"

{
  echo "Hades training finished: $(ts)"
  echo "Final deployed survival vs [Ian3,Ian3,Perdition2,Gabriel]: ${FINAL}%  (target $(echo "$TARGET*100" | bc 2>/dev/null || echo "${TARGET}x100")%)"
  echo "Best history: training/hades/bests.jsonl"
  echo "Deployed weights: agents/hades_weights.json"
  echo "If survival is low enough, enable HadesAgent in web/dashboard_server.py and bump stats versions."
} | tee -a "$STATUS" > "$DONE_MARKER"

status "=== Hades full training DONE (final survival ${FINAL}%) ==="
exit 0
