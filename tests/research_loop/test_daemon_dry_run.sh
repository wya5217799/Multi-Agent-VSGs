#!/bin/bash
# Daemon dry-run integration: 5 tick, mock training (echo hello), verify state transitions.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DAEMON="$REPO/scripts/research_loop_daemon.sh"
PY="/home/wya/andes_venv/bin/python"

fail() { echo "FAIL: $1" >&2; exit 1; }

[[ -x "$DAEMON" ]] || fail "daemon script not executable"

tmpdir=$(mktemp -d)
state_file="$tmpdir/state.json"
log_file="$tmpdir/daemon.log"

# Queue state with 1 mock pending run
"$PY" -c "
import json, sys
sys.path.insert(0, '$REPO')
from scripts.research_loop.state_io import default_empty_state, write_state
s = default_empty_state()
s['pending'].append({
    'id': 'mock_run01', 'backend': 'andes_cpu',
    'cmd': 'echo hello && sleep 1',
    'out_dir': '$tmpdir/run01',
    'log': '$tmpdir/run01.log',
    'expected_hr': 0.001, 'ram_gb': 0.1, 'priority': 5,
    'rationale': 'dry-run smoke', 'queued_by': 'test'
})
write_state('$state_file', s)
print('queued')
"

# Run daemon dry-run: 5 ticks, 1s each, ANDES_CPU_DRY_RUN=1, override free RAM to 20GB
TICK_S=1 MAX_TICKS=5 ANDES_CPU_DRY_RUN=1 FREE_GB_OVERRIDE=20 \
    STATE_FILE="$state_file" DAEMON_LOG="$log_file" \
    bash "$DAEMON" || fail "daemon exited non-0"

# Assertion 1: done count = 1
done_count=$("$PY" -c "
import json
s = json.load(open('$state_file'))
print(len(s['done']))
")
[[ "$done_count" == "1" ]] || fail "done count expected 1 got $done_count"

# Assertion 2: daemon log has tick lines
tick_lines=$(grep -c "tick=" "$log_file" || true)
(( tick_lines >= 3 )) || fail "tick lines < 3 got $tick_lines"

# Assertion 3: _done.json exists with exit_code 0
[[ -f "$tmpdir/run01/_done.json" ]] || fail "_done.json missing"
grep -q '"exit_code": *0' "$tmpdir/run01/_done.json" || fail "_done.json wrong exit_code"

rm -rf "$tmpdir"
echo "ALL PASS (3 assertions)"
