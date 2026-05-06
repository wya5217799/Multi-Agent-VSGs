#!/bin/bash
# V2 hetero env + PHI_D=0.05 + 5 seed × 500 ep 全训 (2026-05-06).
# WSL 内执行: bash scenarios/kundur/_run_v2_5seed.sh
set -euo pipefail

REPO="/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
PY="/home/wya/andes_venv/bin/python"

cd "$REPO"

for seed in 42 43 44 45 46; do
    OUT="results/andes_v2_balanced_seed${seed}"
    LOG="${OUT}.train.log"
    echo "=== START seed ${seed} at $(date) -> ${OUT} ==="
    "$PY" scenarios/kundur/train_andes_v2.py \
        --episodes 500 \
        --seed "${seed}" \
        --phi-d 0.05 \
        --save-dir "${OUT}" \
        > "${LOG}" 2>&1
    echo "=== END seed ${seed} at $(date) ==="
done

echo "ALL_DONE_$(date)"
