#!/bin/bash
# Research Loop Daemon. Tick loop: pending -> fit check -> launch -> monitor -> done.
# per spec section 5 + section 11.5 (RAM AND CPU dual constraints).
#
# Env:
#   STATE_FILE=<path>          default: quality_reports/research_loop/state.json
#   DAEMON_LOG=<path>          default: /tmp/rloop_daemon.log
#   TICK_S=60                  tick interval seconds
#   MAX_TICKS=0                0=infinite; use small number for tests
#   FREE_GB_OVERRIDE=<n>       mock free RAM GB (tests only)
#   ANDES_CPU_DRY_RUN=1        mock backend (tests only, forwarded to backends)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-/home/wya/andes_venv/bin/python}"
TICK_PY="$REPO/scripts/research_loop/_tick.py"
STATE_FILE="${STATE_FILE:-$REPO/quality_reports/research_loop/state.json}"
DAEMON_LOG="${DAEMON_LOG:-/tmp/rloop_daemon.log}"
TICK_S="${TICK_S:-60}"
MAX_TICKS="${MAX_TICKS:-0}"
LOCK_FILE="${LOCK_FILE:-/tmp/rloop_daemon.lock}"

log() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$DAEMON_LOG"
}

# Single-instance lock via flock
exec 200>"$LOCK_FILE"
flock -n 200 || { echo "another daemon already running" >&2; exit 1; }

tick=0
log "daemon=START state=$STATE_FILE tick_s=$TICK_S max_ticks=$MAX_TICKS"

while true; do
    tick=$((tick + 1))

    if (( MAX_TICKS > 0 )) && (( tick > MAX_TICKS )); then
        log "daemon=END max_ticks=$MAX_TICKS reached"
        break
    fi

    if [[ ! -f "$STATE_FILE" ]]; then
        log "tick=$tick state_file missing, halt"
        break
    fi

    # Free RAM: env override (tests) takes precedence over real check
    if [[ -n "${FREE_GB_OVERRIDE:-}" ]]; then
        free_gb="$FREE_GB_OVERRIDE"
    else
        free_gb=$(bash "$REPO/scripts/backends/_resource_check.sh" free_gb)
    fi

    # Run tick logic via separate Python script (avoids bash heredoc nesting issues)
    "$PY" "$TICK_PY" "$STATE_FILE" "$free_gb" "$tick" "$REPO" >> "$DAEMON_LOG" 2>&1 || true

    sleep "$TICK_S"
done

log "daemon=EXIT"
