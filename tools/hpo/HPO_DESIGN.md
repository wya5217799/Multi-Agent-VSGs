# HPO Integration Design — Kundur CVS v3

**Status:** DRAFT (2026-04-29). Not committed to project core. For review during P0' anchor (run_id `kundur_simulink_20260429_205832`) wall.

**Scope:** Optuna-based hyperparameter sweep over the SAC training-stack
旋钮，with all physical/protocol/reward layers held LOCKED at the
post-credibility-close + post-phi-resweep-v2 contract. **Not for
exploring physics or reward formula**.

---

## 1. What is FIXED (HPO does NOT search)

| Layer | Constants | Source of lock |
|---|---|---|
| Physical model | v3 profile, .slx, IC, runtime.mat, all build-script outputs | commits 623a10d / a9ad2ea / 81a1205 |
| Bridge | step_strategy=`cvs_signal`, IC dispatch via cfg | commit 81a1205 |
| Profile guard | DEFAULT_KUNDUR_MODEL_PROFILE → v3, fail-fast on legacy | commit 88abd64 |
| Reward formula | Eq.14-18 paper-faithful, `_PHI_F * r_f - _PHI_H * (ΔH)² - _PHI_D * (ΔD)²` | locked at env._SimVsgBase |
| Reward weights | PHI_F=100, **PHI_H=PHI_D=5e-4** (post v2 sweep) | commit 1a8ce30 |
| Disturbance | DIST_MIN=0.1 / DIST_MAX=1.0 sys-pu, `pm_step_proxy_random_bus` default | commit a9ad2ea + 1a8ce30 |
| Warmup | T_WARMUP=10.0 s | commit a9ad2ea |
| Episode | M=50 step, DT=0.2 s, T_episode=10 s | paper-faithful |
| Network | 4×128 hidden actor + critic | paper Table I |
| Discount | GAMMA=0.99 | paper Table I |
| Agents | 4 independent SAC (G6) | commit b6039d8 |

If a trial wants to vary any of these, it is OUT OF SCOPE.

---

## 2. What HPO SEARCHES

Search space — 6 旋钮, log-uniform / categorical:

| Param | Type | Range | Default (paper / current) | Justification |
|---|---|---|---|---|
| `lr` | log-uniform | [3e-5, 3e-3] | 3e-4 (paper Table I) | actor + critic + α share lr |
| `tau_soft` | log-uniform | [1e-3, 5e-2] | 5e-3 (project default) | soft-update target rate |
| `batch_size` | categorical | {128, 256, 512} | 256 (paper Table I) | mini-batch size |
| `update_repeat` | categorical | {1, 5, 10, 20} | 10 (project default) | grad steps per env step |
| `per_agent_buffer_size` | categorical | {1000, 2500, 5000, 10000} | 2500 (locked default = 10000/4) | independent-buffer experiment |
| `per_agent_warmup_steps` | categorical | {100, 500, 1000, 2000} | 500 (locked default = 2000/4) | per-agent warmup |

Notes:
- Discount γ=0.99 NOT searched (paper-fixed)
- HIDDEN_SIZES NOT searched (paper-fixed)
- alpha_max / alpha_min NOT searched (entropy auto-tune handled by SAC internal)
- α learning rate tied to `lr` (single knob)

---

## 3. Objective function

**Primary objective (to MINIMIZE):**

```
objective = - (eval cum_unnorm under pm_step_proxy_random_bus, 50 scenarios, seed=42)
```

Higher is better in raw cum_unnorm (less negative = better policy). Optuna
minimizes by convention, so flip sign.

**Why eval objective, not training reward**:
- Training reward magnitude depends on PHI which is locked, but absolute
  reward values vary trial-to-trial due to action exploration noise.
- Eval cum_unnorm under fixed scenario set is the cleanest comparable
  signal: same 50 scenarios, same seed, same disturbance distribution.
- Aligns with what HPO is supposed to optimize: out-of-distribution
  generalization to a fixed eval suite.

**Secondary observable (logged but not part of objective)**:
- Train reward last-100 mean (sanity check)
- max\|Δf\| eval mean / std
- r_f / r_h / r_d decomposition
- training wall-clock time (for cost-aware analysis)

---

## 4. Trial budget plan

| Phase | Episodes / trial | Trials | Wall (h) | Pruning |
|---|---:|---:|---:|---|
| **Pilot** | 200 | 6 | ~3 h | manual review |
| **Search** | 500 | 20 | ~25 h | MedianPruner @ ep 200 |
| **Final** | 2000 | 1 (best config) | ~7 h | none |

Total: ~35 h MATLAB engine wall (single engine, serial).

Pruning strategy: MedianPruner with n_warmup_steps=100 ep, n_startup_trials=4.
A trial whose intermediate reward at ep 100/200/300 falls below the median
of completed trials' same-ep reward gets pruned. Saves ~30-40% wall.

Sampler: Optuna TPE (default) — Tree-structured Parzen Estimator. Good
for low-budget HPO with ≤30 trials. CMA-ES alternative if continuous
space dominates.

---

## 5. Architecture

Single MATLAB engine constraint dictates trial isolation strategy:

**Choice: each trial runs as subprocess invocation of `scenarios/kundur/train_simulink.py`**

Reasons:
1. Subprocess gets its own MATLAB engine cold start (~20 s) — guarantees
   no workspace var contamination from prior trial
2. P1 banner + run_meta auto-stamps each trial with the param config
3. Existing run_protocol heartbeat / training_status.json infrastructure
   gives Optuna a clean way to read intermediate metrics
4. No need to thread Optuna state into MultiAgentSACManager / env

**Cost**: 20 s engine cold start × 26 trials = 9 min total overhead. Acceptable.

**Driver flow**:

```
optuna_driver.py
  ├── for each trial:
  │     ├── trial.suggest_X(...)  → param dict
  │     ├── env-vars: KUNDUR_MODEL_PROFILE, KUNDUR_DISTURBANCE_TYPE
  │     ├── CLI args: train_simulink.py with {lr, tau, batch, update-repeat,
  │     │              per-agent-buffer-size, per-agent-warmup-steps,
  │     │              episodes=trial_eps}
  │     ├── subprocess.run(...)  (blocks, single engine)
  │     ├── parse training_status.json + run_meta.json for intermediate report
  │     ├── if not pruned: run paper_eval.py 50-scenario on trial's best.pt
  │     └── return -cum_unnorm  (Optuna minimizes)
  └── persist study to optuna_study.db
```

Resume: `optuna.create_study(study_name='kundur_v3_hpo_v1', storage='sqlite:///...db', load_if_exists=True)`.
Crash-safe: SQLite storage means trial state survives Python crashes.

---

## 6. Constraints / safeguards

**Hard guards (driver-side)**:

1. Refuse to run if `KUNDUR_MODEL_PROFILE` env-var is unset or not `kundur_cvs_v3.json`
2. Refuse to run if `KUNDUR_DISTURBANCE_TYPE` env-var unset (paper_eval would default to weak-signal)
3. Refuse to run if `git status` has tracked-M files (snapshot drift risk)
4. Verify P0' anchor exists and last_eval_reward > anchor before starting search phase (sanity check)
5. Pin `seed=42` for all trials (only HP varies, env stochasticity controlled)

**Trial-level fail-fast**:

1. If any trial reports `tds_failed > 0` for >5% of episodes, mark as FAIL
   (NOT prune — this is a physics issue, not a HP issue, and shouldn't
   confuse Optuna's TPE belief)
2. If any trial reports `omega_saturated > 5%` of episodes, mark as FAIL
3. Wall-clock limit: trial > 2× expected duration → kill + mark FAIL

**Resource guards**:

1. Disk: each trial writes `results/sim_kundur/runs/<run_id>/` — auto-rotate / archive after 30 trials
2. Memory: MATLAB engine retains state across sim() chunks; subprocess isolation prevents cross-trial leakage

---

## 7. Files to ship (when user approves)

```
tools/hpo/
  HPO_DESIGN.md            ← THIS FILE (committed for review)
  optuna_driver.py         ← main entry point (Python, ~150 LoC)
  hpo_objective.py         ← objective function: trial → train + eval → score
  hpo_helpers.py           ← env-var / CLI param translation helpers
  hpo_constraints.py       ← pre-flight guards
  README.md                ← user-facing usage guide
```

No edits to:
- `scenarios/kundur/train_simulink.py` (already has all CLI knobs needed,
  per commits ec07e1d / 88abd64)
- `evaluation/paper_eval.py` (already env-var-driven per commit 32c7511)
- Any env / bridge / config / reward / SAC / NE39 file

---

## 8. Open decisions to resolve before launch

1. **Anchor reference**: P0' (run_id `kundur_simulink_20260429_205832`) eval
   result — needed as sanity baseline for the search phase. **Block: anchor
   not done yet**.

2. **Test-set determinism**: paper_eval uses seed-based random scenario
   generation (n=50, seed=42). Should HPO use the same seed every trial?
   YES (deterministic comparison).

3. **Pilot phase trial count**: 6 vs 10? More pilots = more TPE warmup
   data but more wall. Recommend 6.

4. **Final 2000-ep run**: do we need it after search? Or trust the best
   500-ep trial config and run a fresh 2000-ep with it? Recommend: run
   2000-ep with best config, even if 500-ep version exists, to get a
   clean "post-HPO production" anchor.

5. **What if no trial beats P0' anchor?** Possible if PHI=5e-4 isn't
   actually the right value, or if paper_eval -19/-21 ceiling under
   pm_step_proxy is genuinely the project's ceiling. Plan: report
   honestly, recommend reverting to default config + investigating
   reward landscape.

---

## 9. STOP — review gate

This file is the design only. To proceed:

1. User reviews HPO_DESIGN.md
2. User confirms search space + objective + trial budget
3. After P0' anchor completes (~6 h from launch 20:58 UTC+8), evaluate
   anchor's eval cum_unnorm → confirm it's better than P0 (-19.09) under
   PHI=5e-4
4. If anchor evaluation passes: ship optuna_driver.py + helpers as a
   single commit; user runs `python tools/hpo/optuna_driver.py --pilot`
   to start

**Until P0' anchor evaluation passes, no Optuna code is written or run.**
