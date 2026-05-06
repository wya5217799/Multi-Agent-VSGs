#!/bin/bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO/scripts/backends/andes_cpu.sh"

fail() { echo "FAIL: $1" >&2; exit 1; }

[[ -x "$SCRIPT" ]] || fail "andes_cpu.sh not executable"

# T1: --help works
bash "$SCRIPT" --help >/dev/null 2>&1 || fail "--help exited non-0"

# T2: launch with ANDES_CPU_DRY_RUN=1, mock cmd echoes hello
tmpdir=$(mktemp -d)
out_dir="$tmpdir/run01"
log="$tmpdir/run01.log"
ANDES_CPU_DRY_RUN=1 bash "$SCRIPT" launch     --id mock_run01     --cmd "echo hello"     --out-dir "$out_dir"     --log "$log"     > "$tmpdir/launch.out" 2>&1
pid=$(grep -oE 'pid=[0-9]+' "$tmpdir/launch.out" | head -1 | cut -d= -f2)
[[ -n "$pid" ]] || fail "launch did not output pid"

# Wait for mock process to finish (echo + write done.json)
sleep 2
kill -0 "$pid" 2>/dev/null && fail "mock process should be dead by now"

# T3: log file should have hello
grep -q hello "$log" || fail "log missing hello"

# T4: _done.json should exist with exit_code 0
[[ -f "$out_dir/_done.json" ]] || fail "_done.json missing"
grep -q '"exit_code": *0' "$out_dir/_done.json" || fail "_done.json wrong exit_code"

rm -rf "$tmpdir"
echo "ALL PASS (4 cases)"
