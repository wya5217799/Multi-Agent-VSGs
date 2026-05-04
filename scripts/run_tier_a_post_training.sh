#!/usr/bin/env bash
# Full Tier A post-training pipeline: verify convergence, run probes, eval, aggregate, update predraft
# Run from WSL after BOTH seeds 45 and 46 training_log.json files exist:
#   source ~/andes_venv/bin/activate
#   cd '/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs'
#   bash scripts/run_tier_a_post_training.sh 2>&1 | tee results/tier_a_post_training.log

set -e
PROJ="/mnt/c/Users/27443/Desktop/Multi-Agent  VSGs"
cd "$PROJ"

echo "=== Tier A Post-Training Pipeline ==="
echo "$(date)"

# Step 1: Verify convergence for both seeds
echo ""
echo "--- Step 1: Convergence verification ---"
for SEED in 45 46; do
    echo "Seed $SEED:"
    python3 scripts/verify_seed_convergence.py --seed $SEED || echo "WARNING: Convergence check failed for seed $SEED"
done

# Step 2: agent_state probe (phases A1/A2/A3)
echo ""
echo "--- Step 2: agent_state probes ---"
for SEED in 45 46; do
    CKPT_DIR="results/andes_phase4_noPHIabs_seed${SEED}"
    echo "Seed ${SEED}: agent_state probe"
    python3 -m probes.kundur.agent_state \
        --ckpt-dir "$CKPT_DIR" \
        --ckpt-kind final \
        --run-id "phase4ext_seed${SEED}_final"
done

# Step 3: Paper-grade eval (50 episodes each)
echo ""
echo "--- Step 3: Paper-grade eval ---"
for SEED in 45 46; do
    echo "Seed ${SEED}: paper-grade eval (50 eps)"
    python3 scenarios/kundur/_eval_paper_grade_andes_one.py \
        --controller "ddic_seed${SEED}" \
        --out-json "results/andes_eval_paper_grade/ddic_seed${SEED}_final.json" \
        --n-eps 50
done

# Step 4: Aggregate n=5 statistics
echo ""
echo "--- Step 4: n=5 aggregate statistics ---"
python3 scripts/aggregate_n5_stats.py

# Step 5: Update predraft
echo ""
echo "--- Step 5: Update predraft ---"
python3 scripts/update_predraft_n5.py

# Step 6: Update plan Tier A actuals
echo ""
echo "--- Step 6: Plan file update summary ---"
echo "Review n5_aggregate.json and predraft_n5.md, then manually update plan status."
echo ""
echo "=== Done ==="
echo "$(date)"
echo ""
echo "Key output files:"
echo "  results/andes_eval_paper_grade/ddic_seed45_final.json"
echo "  results/andes_eval_paper_grade/ddic_seed46_final.json"
echo "  results/andes_eval_paper_grade/n5_aggregate.json"
echo "  results/andes_eval_paper_grade/n5_summary.md"
echo "  results/harness/kundur/agent_state/agent_state_phase4ext_seed45_final.json"
echo "  results/harness/kundur/agent_state/agent_state_phase4ext_seed46_final.json"
echo "  quality_reports/replications/2026-05-03_andes_ddic_honest_results_predraft_n5.md"
