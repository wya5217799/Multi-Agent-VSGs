# Warmstart Pilot Plan — Shared-Param Init + Per-Agent Fine-Tune
**Date:** 2026-05-04  
**Status:** RUNNING (3 background processes launched 2026-05-04T02:43Z)

---

## Hypothesis

Current DDIC Phase 4 (4 independent SAC actors):
- a1 locks to ~56% share by ep 100 → init-driven, not training-emergent [FACT: ckpt trajectory]
- Cross-seed variance std = 0.265 [FACT: Tier-A n=5 verdict 2026-05-04]

Prediction: initializing all 4 actors from the SAME pre-trained shared-param actor → same starting point across seeds → lower seed-to-seed variance + more balanced agent dominance.

---

## Method

**Warmstart source:** `results/andes_phase9_shared_seed42_500ep/agent_shared_final.pt`
- 3-seed × 500ep shared-param SAC, mean cum_rf -1.069 paper-grade [FACT: eval_paper_grade_v2.json]
- Per-seed: 42→-1.356, 43→-0.924, 44→-0.927

**Warmstart mode:** `actor_only` — shared actor weights loaded into each of 4 per-agent actors; critics start fresh (random init) to allow per-agent value specialization.

**Script:** `scenarios/kundur/train_andes_warmstart.py` (new file, train_andes.py not modified)

**Hyperparameters:** identical to Phase 4
- `comm_fail_prob=0.1`
- `HIDDEN_SIZES`, `LR`, `GAMMA`, `TAU_SOFT`, `BUFFER_SIZE`, `BATCH_SIZE` from `config.py`
- 500 episodes, N_EPOCH=10 per episode
- Seeds: 42 / 43 / 44 (same as DDIC baseline)

---

## Expected Metrics

| Metric | DDIC Phase 4 baseline (n=5) | Warmstart target |
|---|---|---|
| Mean cum_rf | -1.156 | better than -1.156 |
| Std cum_rf | 0.265 | < 0.15 |
| a1 action share | 50–74% | < 50% |

---

## Falsification Gates

- **WARMSTART_BETTER**: cum_rf improves AND std < 0.15 AND a1 share < 50% → warmstart hypothesis confirmed, recommend production adoption
- **WARMSTART_NEUTRAL**: cum_rf within 5% of baseline AND std unchanged → no value from shared init, abandon this line
- **WARMSTART_WORSE**: cum_rf worse than baseline → shared init was a bad starting point, abandon

Gate verdict requires n=3 seeds evaluated via `_eval_paper_grade_andes_one.py` + aggregation.

---

## File References

- Script: `scenarios/kundur/train_andes_warmstart.py`
- Output dirs: `results/andes_warmstart_seed{42,43,44}/`
- Logs: `results/andes_warmstart_seed{42,43,44}.log`
- Warmstart ckpt: `results/andes_phase9_shared_seed42_500ep/agent_shared_final.pt`
- DDIC baseline verdict: `quality_reports/audits/2026-05-04_andes_tier_a_n5_verdict.md`

---

## Next-Session Continuation Block

### PIDs (WSL, launched 2026-05-04T02:43Z)

| Seed | PID |
|---|---|
| 42 | 7860 |
| 43 | 7862 |
| 44 | 7863 |

**Expected completion:** ~2026-05-04T05:43Z (+3h from launch, matches plain Phase 4 wall time)

### Post-Training Workflow

1. Verify runs completed:
   ```bash
   wsl bash -c "tail -5 results/andes_warmstart_seed42.log results/andes_warmstart_seed43.log results/andes_warmstart_seed44.log"
   ```

2. Evaluate each seed with paper-grade eval script:
   ```bash
   for SEED in 42 43 44; do
     python3 _eval_paper_grade_andes_one.py \
       --controller ddic_warmstart_seed${SEED} \
       --ckpt-dir results/andes_warmstart_seed${SEED} \
       --save results/andes_warmstart_seed${SEED}/eval_paper_grade.json
   done
   ```
   (Extend `_eval_paper_grade_andes_one.py` with `--ckpt-dir` arg if not present; agent file pattern: `agent_{i}_final.pt`)

3. Aggregate n=3 warmstart results and compare to DDIC n=5 baseline:
   ```bash
   python3 _aggregate_eval_results.py \
     results/andes_warmstart_seed42/eval_paper_grade.json \
     results/andes_warmstart_seed43/eval_paper_grade.json \
     results/andes_warmstart_seed44/eval_paper_grade.json \
     --label warmstart_n3
   ```

4. Apply falsification gates (WARMSTART_BETTER / NEUTRAL / WORSE) and write verdict to `quality_reports/audits/2026-05-04_warmstart_pilot_verdict.md`.

5. If WARMSTART_BETTER: proceed to n=5 warmstart sweep for A3 gate closure.
