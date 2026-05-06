#!/bin/bash
# SAC GPU backend (research-loop). Wraps andes_cpu.sh with CUDA env injected.
# Per 2026-05-07 user override (memory: feedback_gpu_policy_optional.md):
#   GPU SAC is OPTIONAL not REJECTED. spec section 11.5 throughput verdict measured
#   ROI weak at 256-256 hidden, but compatibility is fine. Researcher may schedule
#   GPU candidates freely; this backend is the dispatch hook.
#
# Usage (called by daemon, identical surface to andes_cpu.sh):
#   sac_gpu.sh launch --id <id> --cmd <cmd> --out-dir <dir> --log <path>
#
# The cmd MUST itself export DEVICE=cuda for the SAC agents to actually use GPU.
# This wrapper only ensures CUDA_VISIBLE_DEVICES is set.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
exec "$HERE/andes_cpu.sh" "$@"
