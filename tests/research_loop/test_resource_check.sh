#!/bin/bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO/scripts/backends/_resource_check.sh"

fail() { echo "FAIL: $1" >&2; exit 1; }

[[ -f "$SCRIPT" ]] || fail "_resource_check.sh missing"
[[ -x "$SCRIPT" ]] || fail "_resource_check.sh not executable"

out=$(bash "$SCRIPT" free_gb)
[[ "$out" =~ ^[0-9]+$ ]] || fail "free_gb returned non-int: $out"

out=$(FREE_GB_OVERRIDE=0 bash "$SCRIPT" fit_count 4 2.5)
[[ "$out" == "0" ]] || fail "fit_count(0,4,2.5) expected 0 got $out"

out=$(FREE_GB_OVERRIDE=10 bash "$SCRIPT" fit_count 4 2.5)
[[ "$out" == "2" ]] || fail "fit_count(10,4,2.5) expected 2 got $out"

out=$(FREE_GB_OVERRIDE=100 bash "$SCRIPT" fit_count 4 2.5)
(( out >= 30 )) || fail "fit_count(100,4,2.5) expected >=30 got $out"

echo "ALL PASS (5 cases)"
