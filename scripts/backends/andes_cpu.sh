#!/bin/bash
# ANDES TDS launcher. daemon calls this to start a single ANDES training run.
# Usage:
#   andes_cpu.sh launch --id <run_id> --cmd <cmd> --out-dir <dir> --log <path>
#   andes_cpu.sh --help
# Env (required reading):
#   ANDES_CPU_DRY_RUN=1   do not actually launch ANDES, run cmd literally (async, writes done.json)
#   OMP_NUM_THREADS, MKL_NUM_THREADS -- daemon injects these, default fallback=4
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'HELPEOF'
ANDES CPU backend. Spawns one training process via nohup.

Usage:
  andes_cpu.sh launch --id <id> --cmd <cmd> --out-dir <dir> --log <path>

Output (stdout): "pid=<pid>"
Side effect: when process finishes, writes <out-dir>/_done.json (exit_code, finished_at_utc).

Env:
  ANDES_CPU_DRY_RUN=1   test mode (no disown, async subshell, still writes done.json)
  OMP_NUM_THREADS=4     BLAS thread count (per spec section 11.5, fallback 4)
  MKL_NUM_THREADS=4     same
HELPEOF
    exit 0
fi

[[ "${1:-}" == "launch" ]] || { echo "first arg must be launch or --help" >&2; exit 2; }
shift

run_id=""; cmd=""; out_dir=""; log_path=""
while (( $# > 0 )); do
    case "$1" in
        --id)      run_id="$2"; shift 2 ;;
        --cmd)     cmd="$2"; shift 2 ;;
        --out-dir) out_dir="$2"; shift 2 ;;
        --log)     log_path="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
done

[[ -n "$run_id"   ]] || { echo "--id required"      >&2; exit 2; }
[[ -n "$cmd"      ]] || { echo "--cmd required"     >&2; exit 2; }
[[ -n "$out_dir"  ]] || { echo "--out-dir required" >&2; exit 2; }
[[ -n "$log_path" ]] || { echo "--log required"     >&2; exit 2; }

mkdir -p "$out_dir" "$(dirname "$log_path")"
done_json="$out_dir/_done.json"

# OMP fallback default (per spec section 11.5, ANDES throughput verdict)
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"

# Capture values into locals so subshell inherits them correctly
_run_id="$run_id"
_done_json="$done_json"
_log_path="$log_path"
_cmd="$cmd"

if [[ "${ANDES_CPU_DRY_RUN:-}" == "1" ]]; then
    # test mode: async subshell (no disown), still writes done.json
    (
        bash -c "$_cmd" > "$_log_path" 2>&1
        ec=$?
        printf '{"id":"%s","exit_code":%d,"finished_at_utc":"%s"}
'             "$_run_id" "$ec" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$_done_json"
    ) &
    pid=$!
    echo "pid=$pid"
else
    # production: background subshell, disown so daemon exit does not kill it
    (
        bash -c "$_cmd" > "$_log_path" 2>&1
        ec=$?
        printf '{"id":"%s","exit_code":%d,"finished_at_utc":"%s"}
'             "$_run_id" "$ec" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$_done_json"
    ) &
    pid=$!
    disown $pid 2>/dev/null || true
    echo "pid=$pid"
fi
