#!/bin/bash
# Server-side auto-deploy poller for the Live Arena dashboard.
#
# Every INTERVAL seconds: git fetch origin/main; if it moved, smoke-test the
# new commit in a detached worktree, then pull + restart only on success.
# A failed smoke test leaves the currently running version untouched.
#
# Run once on the box (see setup_auto_deploy.sh), or manually:
#   APP_DIR=/opt/ek-arena nohup ./auto_deploy.sh &
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ek-arena}"
PORT="${PORT:-8767}"
BRANCH="${BRANCH:-main}"
INTERVAL="${INTERVAL:-60}"
LOG="${LOG:-/tmp/ek-auto-deploy.log}"
WORKTREE="${WORKTREE:-/tmp/ek-arena-smoke}"

log() { echo "$(TZ="America/Los_Angeles" date +"%Y-%m-%d %H:%M:%S %Z") $*" | tee -a "$LOG"; }

cleanup_worktree() {
  git -C "$APP_DIR" worktree remove --force "$WORKTREE" 2>/dev/null || rm -rf "$WORKTREE"
}

smoke_test() {
  local ref="$1"
  cleanup_worktree
  git -C "$APP_DIR" worktree add --detach "$WORKTREE" "$ref"
  if (cd "$WORKTREE" && python3 smoke_test.py); then
    cleanup_worktree
    return 0
  fi
  cleanup_worktree
  return 1
}

restart_dashboard() {
  local sha at
  sha=$(git -C "$APP_DIR" rev-parse --short HEAD)
  at=$(TZ="America/Los_Angeles" date +"%Y-%m-%d %H:%M %Z")
  if APP_DIR="$APP_DIR" PORT="$PORT" \
     EK_DEPLOY_SHA="$sha" EK_DEPLOY_BY="auto-deploy" EK_DEPLOY_AT="$at" \
     "$APP_DIR/scripts/arena_restart.sh" >>"$LOG" 2>&1; then
    log "live @ $sha"
    return 0
  fi
  log "ERROR: dashboard failed to start @ $sha"
  return 1
}

log "poller start branch=$BRANCH interval=${INTERVAL}s app=$APP_DIR"

while true; do
  if ! git -C "$APP_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    log "ERROR: $APP_DIR is not a git repo"
    sleep "$INTERVAL"
    continue
  fi

  if ! git -C "$APP_DIR" fetch -q origin "$BRANCH" 2>>"$LOG"; then
    log "WARN: git fetch failed"
    sleep "$INTERVAL"
    continue
  fi

  local_sha=$(git -C "$APP_DIR" rev-parse HEAD)
  remote_sha=$(git -C "$APP_DIR" rev-parse "origin/$BRANCH")

  if [ "$local_sha" != "$remote_sha" ]; then
    short_local=$(git -C "$APP_DIR" rev-parse --short "$local_sha")
    short_remote=$(git -C "$APP_DIR" rev-parse --short "$remote_sha")
    log "origin/$BRANCH moved: $short_local -> $short_remote"
    if smoke_test "$remote_sha"; then
      log "smoke ok; pulling"
      git -C "$APP_DIR" checkout -- agents/ 2>/dev/null || true
      git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
      restart_dashboard || log "WARN: restart failed"
    else
      log "smoke FAILED — keeping $short_local running"
    fi
  fi

  sleep "$INTERVAL"
done
