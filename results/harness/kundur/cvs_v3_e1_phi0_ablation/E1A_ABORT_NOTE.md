# E1a PHI=0 Ablation — Aborted (NOT a Training Failure)

**Date:** 2026-04-30 02:24 UTC+8
**Run ID:** kundur_simulink_20260430_015448
**Status at abort:** ep 150/200 (~75% complete, ~3.5h wall)
**Reason:** Pre-empted to free MATLAB engine + .slx file lock for Probe B
            measurement-layer falsification experiment.

---

## Why aborted

This is NOT a training failure. The training was healthy and progressing:

- ep 139: r_f composition 100% (PHI=0 ablation working as intended)
- per-agent action mu within reasonable range, std ≈ 0.5 (proper exploration)
- 0/10 TDS failures, freq peak 0.39-0.45 Hz (numerically stable)
- last_eval_reward = -703 (weak signal but non-zero)

E1a was answering R3 (RL improvement causality) by removing r_h/r_d
regularization. It had ~3 hours left (~50 episodes) when 2026-04-30
fresh-context falsification audit (see commit deb43e5) surfaced a
HIGHER-PRIORITY question: **whether per-agent omega measurements are
electrically separated, or aliased to a single signal.**

Probe B (sign-pair experiment driver, probes/kundur/probe_b_sign_pair.py)
is the falsification probe. It needs the MATLAB engine + .slx file lock
to run two paper_eval subprocesses (~10-15 min wall). It cannot run
concurrently with E1a because both compete for the same .slxc compile
cache + .slx file lock.

If Probe B confirms measurement collapse, ALL trace-based reasoning
(including E1a's results when finished) become suspect — there's no
point waiting for E1a to finish before knowing whether the diagnostic
data layer is sound.

If Probe B passes (4 distinct measurements per agent), E1a can be
resumed from `checkpoints/ep100.pt` (snapshot below) with `--resume`.

---

## Snapshot

Full snapshot at:
  `results/harness/kundur/cvs_v3_e1_phi0_ablation/aborted_run_snapshot/kundur_simulink_20260430_015448/`

Contains:
- run_meta.json (git_hash 0cf7d05, full args, env-vars at launch)
- training_status.json (heartbeat: ep 150, last_reward, last_eval_reward)
- checkpoints/ep50.pt, checkpoints/ep100.pt, checkpoints/best.pt
- logs/ (training_log.json, latest_state.json)
- tb/ (tensorboard event files)
- e1a_train_stdout.log, e1a_train_stderr.log (full subprocess logs)

---

## Resume command (if Probe B passes)

```bash
unset KUNDUR_DIST_MAX
KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus \
KUNDUR_PHI_H=0.0 \
KUNDUR_PHI_D=0.0 \
PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 \
  /c/Users/27443/miniconda3/envs/andes_env/python.exe \
  scenarios/kundur/train_simulink.py \
    --mode simulink --episodes 200 --seed 42 \
    --resume results/harness/kundur/cvs_v3_e1_phi0_ablation/aborted_run_snapshot/kundur_simulink_20260430_015448/checkpoints/ep100.pt
```

(Resume from ep100 not ep150 because ep150 not yet checkpointed; ep100
is the latest ckpt available. Loses ~50 episodes of training; total
re-run wall ~5h to reach ep 200.)

## Decision rule

- **Probe B PASS** (4 agents distinct, sign-asymmetric response, distinct
  r_f_local) → measurement layer is sound. Resume E1a from ep100 ckpt
  to complete R3 ablation.
- **Probe B FAIL** (collapse or alias) → measurement layer is broken.
  Do NOT resume E1a — its r_f signal is computed on potentially aliased
  data and would not falsify anything. Switch to fixing measurement
  layer (build script wiring of W_omega_<sname> ToWorkspace blocks) BEFORE
  any further RL training.
