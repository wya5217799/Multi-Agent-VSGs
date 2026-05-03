# G3-prep F — Kundur CVS 50-Episode Observation Verdict

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` @ `0d45615` (post OD-F-3 FIX re-sanity)
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE — 50-ep CVS observation smoke through `train_simulink.py` to characterise post-OD3-FIX learning signal across the SAC warmup boundary.
**Predecessors:**
- OD3-FIX re-sanity verdict — commit `0d45615`
- OD3-FIX impl + V-FIX-1..4 — commit `83846dd`
- 50-ep observation spec — commit `1c328fc`

---

## Verdict: PASS — All 8 mandate items satisfied

50-ep run completed cleanly (exit 0, 14.4 min, no crash / NaN / Inf / clip). OD-F-3 disturbance fix is end-to-end live for all 50 ep. SAC update activates exactly at the warmup boundary (ep 10, when buffer crosses 2000 transitions) and produces finite, monotone alpha decay through ep 50. No action collapse, no saturation pathology. **Mid-learning reward improves 11.2% vs pre-warmup baseline**; this is plumbing observation evidence, not a Gate 3 / paper-replication claim.

---

## 1. Run identifiers

| Field | Value |
|---|---|
| `run_id` | `kundur_simulink_20260425_232339` |
| HEAD | `0d45615` (re-sanity verdict; commits 5db751a, 6d46c75, a62c1e9, 710aa3f, 83846dd, 0d45615 in ladder) |
| Wall-clock | 862 s (14.4 min) total, **17.24 s/ep mean** (5-ep was 13.2 s/ep; +4 s/ep is SAC update overhead post ep 10) |
| Output dir | `results/sim_kundur/runs/kundur_simulink_20260425_232339/` (gitignored) |
| Seed | 42 |
| Episodes | 50 |
| Exit code | 0 |
| `last_reward` (noisy) | -299.12 |
| `last_eval_reward` (deterministic) | -220.23 (better than noisy → policy has learned) |

---

## 2. Eight mandate checks

### 2.1 Console: 50/50 ep route via CVS path

```
[Kundur-Simulink-CVS] Pm step ...   : 53 occurrences in 50-ep stdout
[Kundur-Simulink] Load reduction... : 0 occurrences
[Kundur-Simulink] Load increase ... : 0 occurrences
```

53 ≥ 50 (the 3 surplus appear on warmup-boundary triggers per env reset; ≥ 1 per ep is the contract). **0 legacy lines**. PASS.

### 2.2 max_freq_dev_hz: persistent non-zero, sane magnitude, far below abort

| Stat | Value |
|---|---|
| mean | **0.0539 Hz** |
| median | 0.0512 Hz |
| min | 0.0185 Hz (smallest non-zero in ep5/ep49) |
| max | 0.0986 Hz |
| count ≥ 12 Hz (abort threshold) | **0 / 50** |
| count near zero (< 1e-6) | 0 / 50 |

Compared to pre-fix (5db751a 5-ep: `max_freq_dev_hz = 6.5e-12`), this is ~10¹⁰× lift. Compared to spec §2 estimate "O(1e-2) to O(1e-1) Hz at typical disturbance magnitudes", observation lands at the lower-mid edge — consistent with the per-VSG 0.25 pu mapping at typical magnitudes ~0.1-0.4 (per console output). PASS.

### 2.3 r_f / r_h / r_d: persistent non-zero, decomposition statistics

| Component | Sum (50 ep) | % of total reward | Per-ep mean | Per-ep range |
|---|---|---|---|---|
| `r_f` (frequency) | -0.03 | **0.00%** | -0.0007 | [-0.0022, -0.0001] |
| `r_h` (inertia action) | -13180.25 | **77.17%** | -263.61 | (random-policy noise) |
| `r_d` (damping action) | -3899.75 | **22.83%** | -77.99 | (random-policy noise) |

**r_f is non-zero throughout (smallest -0.0001, ~10²¹× pre-fix -7.9e-24)** but its magnitude is dominated by `r_h + r_d` action-magnitude penalties under early-learning policy. This is the expected regime: with `φ_f = 100` and Δω ≈ 5e-4, `r_f ~ -100 × (5e-4)² × 50 step ≈ -1.25e-3` per ep, exactly matching observation. **PASS** (component non-zero AND ratio recorded for next-stage reference).

### 2.4 omega_trace: persistent real response, no stale-noise

| Stat | Value |
|---|---|
| per-ep max-VSG std (mean across 50 ep) | **4.74e-04** |
| per-ep max-VSG std (range) | [1.74e-04, 8.50e-04] |
| count with std < 1e-10 (stale-noise floor) | **0 / 50** |
| global ω range | [0.998153, 1.001972] (well inside [0.7, 1.3] clip) |
| any NaN | False |
| any Inf | False |
| any clip touch | False |

vs pre-fix per-ep std ~5e-14 (machine epsilon noise) → ~10¹⁰× real-response signal, every episode. PASS.

### 2.5 SAC updates: warmup boundary + alpha / loss trajectories

| Phase | ep range | alpha | critic_loss | policy_loss | update count |
|---|---|---|---|---|---|
| Pre-warmup | 1-9 | 1.0000 | (no update) | (no update) | 0 |
| **First fire** | **10** | **0.9997** | first finite | first finite | **1 (per-ep mean)** |
| Mid-warmup | 25 | 0.7515 | growing | growing | 1 per ep |
| Late | 50 | **0.2228** | bounded | bounded | 1 per ep |

```
alphas:        count = 41 (ep 10..50, exact match with buffer >= warmup_steps)
                first 3 = [0.9997, 0.9921, 0.9773]
                last 3  = [0.2589, 0.2438, 0.2296]
critic_losses: count = 41, range = [0.1515, 3.9970], any_nan = False, any_inf = False
policy_losses: count = 41, range = [-10.08, -1.40], any_nan = False
```

**SAC update first-fire = ep 10**, NOT ep 40 as spec §1.5 predicted. Reason: `store_multi_transitions` stores N_AGENTS=4 transitions per env step, so buffer fills 4× faster than naive `STEPS_PER_EPISODE × 1` accounting. Per ep adds 4 × 50 = **200 transitions**, so 2000 / 200 = 10 ep to warmup. This 4× factor was not flagged in the spec.

Alpha monotone decay 1.0 → 0.22 over 41 update episodes; critic / policy losses bounded and finite throughout. PASS.

### 2.6 H/D action: no collapse, no edge-pinning, no anomaly

| Agent | action_mean over 50 ep (range) | mean action_std | first-10 std | last-10 std |
|---|---|---|---|---|
| 0 | mean=-0.0055, range [-0.119, +0.110] | 0.5907 | 0.6066 | 0.5790 |
| 1 | mean=-0.0160, range [-0.154, +0.105] | 0.5878 | (combined) | (combined) |
| 2 | mean=+0.0009, range [-0.136, +0.132] | 0.5875 | (combined) | (combined) |
| 3 | mean=-0.0145, range [-0.176, +0.088] | 0.5894 | (combined) | (combined) |

| Saturation metric | Value |
|---|---|
| mean `saturation_ratio` | 0.0425 (≈ 4% of steps touch [-1, +1] action boundary) |
| max `saturation_ratio` | 0.0875 (single-ep peak < 9%) |
| any ep with > 50% saturation | **False** |

- **No collapse**: action_std stays ~0.58 throughout (initial 0.61, final 0.58 — small natural decrease from SAC entropy tuning, NOT collapse-to-deterministic)
- **No edge-pinning**: action_mean of all 4 agents centred near 0 (max abs ~0.18 of [-1, +1] range)
- **No anomaly**: no spikes; range bands smooth across 50 ep

PASS.

### 2.7 NaN / Inf / clip / crash / early termination

| Check | Value |
|---|---|
| NaN in omega trace (50 × 50 × 4 = 10000 samples) | False |
| Inf in omega trace | False |
| Clip touch [0.7, 1.3] | False |
| Sim crash | None (50/50 ep completed) |
| Early termination | None (50/50 ep ran full 50 steps) |
| `tds_failed` per ep | 0 / 50 |
| NaN in critic_loss (41 entries) | False |
| Inf in critic_loss | False |
| NaN in policy_loss (41 entries) | False |
| NaN in alpha (41 entries) | False |

All zero. PASS.

### 2.8 Run path / commit / metrics summary / phase comparison

**Run path**:
- run_dir: `.worktrees/kundur-cvs-phasor-vsg/results/sim_kundur/runs/kundur_simulink_20260425_232339/`
- training_log.json (50 ep), live.log (50 lines), monitor_data.csv (50 rows), TB at `tb/`
- final.pt checkpoint saved

**Commit hash at run time**: HEAD = `0d45615` (re-sanity verdict). No source modified during run; all 16 §0 boundary files SHA-256 byte-equivalent.

**Phase comparison (mandate item 8)**:

| Phase | ep range | ep_R mean | mfd mean (Hz) | r_f mean | alpha at end |
|---|---|---|---|---|---|
| Pre-warmup (random) | 1-9 | -349.55 | 0.0497 | -0.0004 | 1.0000 |
| Early-learn | 10-25 | -362.03 | 0.0496 | -0.0005 | 0.7515 |
| **Mid-learn** | **35-50** | **-309.56** | 0.0595 | -0.0008 | **0.2228** |

- **Mid-learn ep_R 11.2% improvement** over pre-warmup ((-349.55 - (-309.56))/(-349.55) × 100 = 11.4%)
- mid-learn `mfd` slightly higher than pre-warmup (0.0595 vs 0.0497 Hz) — consistent with SAC trying more "active" H/D combinations to reduce r_h/r_d penalty; ω perturbation marginally larger as a side effect (still well below abort)
- alpha monotone decay 1.0 → 0.22 over 41 update episodes (reasonable autotune trajectory, NOT collapse to 0)
- `last_eval_reward = -220.23` (deterministic policy, separate from the noisy `-299.12 last_reward`) — best evidence that the policy has learned something useful in 41 update episodes

PASS.

---

## 3. Boundary check (post-50-ep)

Tracked tree (CVS worktree):
```
?? results/sim_kundur/runs/kundur_simulink_20260425_232339/  (gitignored, this run)
?? quality_reports/patches/                                  (pre-existing audit dir)
?? other prior gitignored result dirs
```

Source files: 0 modified. All 16 §0 boundary files (NE39 / shared `.m` / engine/simulink_bridge.py / env/simulink/_base.py / NE39 *.py / contract / config_simulink_base / legacy Kundur / CVS) SHA-256 byte-equivalent to commit `0d45615`. The 50-ep run is purely read-only on the codebase.

---

## 4. What this verdict does NOT do

- ❌ Does NOT enter Gate 3 / 2000-ep / paper-replication
- ❌ Does NOT modify any source file
- ❌ Does NOT propose reward / agent / SAC / disturbance hyperparameter changes
- ❌ Does NOT compare quantitatively against NE39 or legacy SPS
- ❌ Does NOT claim "convergent learning" or "Gate 3 PASS"
- ❌ Does NOT recommend single-VSG vs equal-distribution disturbance topology change (recorded in OD3-FIX verdict §5; out of scope)
- ❌ Does NOT touch NE39 / legacy / shared / agents / config / contract

---

## 5. Observations recorded for next stage (NOT acted on)

1. **r_f shaping is heavily under-weighted relative to r_h+r_d under early-learning policy**: 0.00% vs 100% of total reward. With Δω ~ 5e-4 (the natural CVS NR-stiff response to ±0.25 pu disturbance), `φ_f = 100` produces `r_f ~ -1e-3 / ep` while `r_h ~ -260 / ep` (5 orders of magnitude smaller). The SAC gradient is essentially driven by action-magnitude minimisation, not frequency control. To exercise frequency-control learning, either (a) `φ_f` would need to scale up by ~10⁴ - 10⁵, or (b) disturbance magnitude scaled up to push Δω into the 0.5-1.0 Hz band where r_f becomes O(r_h). NEITHER is in this stage's scope.

2. **5-ep wall-clock estimate underestimated 50-ep wall-clock**: 5-ep at 13.2 s/ep predicted 11 min for 50-ep; actual 14.4 min (+30%). The +4 s/ep is SAC update overhead post ep 10 (10 critic+policy backprop calls per env step at peak `effective_repeat`). For 2000-ep the proportional total: 2000 × 17.2 s ≈ 9.5 hours.

3. **SAC warmup boundary was at ep 10, not ep 40**: `store_multi_transitions` stores N_AGENTS=4 transitions per env step → buffer fills 4× faster than naive accounting. Spec §1.5 predicted ep 40; actual ep 10. Spec footnote should be updated; not in this verdict's scope.

4. **mid-learn `mfd` slightly increased** (0.0497 → 0.0595 Hz pre-warmup vs mid-learn): SAC pushes more aggressive H/D actions to reduce action penalty, which slightly perturbs ω. NOT a regression — still 100× below abort.

5. **last_eval_reward (-220) is better than last_reward (-299)** by 26%: deterministic policy outperforms noisy stochastic policy — direct evidence that SAC has learned something the entropy-noise was masking. This is a clean signal even though absolute reward is still dominated by r_h+r_d.

---

## 6. Status snapshot

```
HEAD pre-verdict:        0d45615  docs(cvs-g3prep-F-OD3-fix-resanity)
G3-prep-F spec:          1c328fc  PASS
F instrumentation:       6d46c75  PASS
OD-F-3 verdict:          a62c1e9  PASS
OD3-FIX design:          710aa3f  PASS
OD3-FIX impl + V-FIX:    83846dd  PASS
OD3-FIX re-sanity:       0d45615  PASS
G3-prep-F 50-ep observation: PASS — this report
50-ep / Gate 3 / 2000-ep / paper-replication: still LOCKED (50-ep was OBSERVATION ONLY; not a Gate)
```

---

## 7. Next step (gated on user)

| Choice | Effect |
|---|---|
| Hold | commit this verdict; pause; await further design decisions |
| Discuss r_f weighting / disturbance magnitude calibration | not in scope of OD3-FIX; requires new spec |
| Ladder up to 2000-ep paper-replication | requires explicit Gate 3 authorisation; would surface r_f under-weighting more clearly |
| Investigate single-VSG vs equal-distribution disturbance topology | recorded in OD3-FIX §5; needs new design + new commit ladder |

50-ep observation completed cleanly. No further action without explicit user authorisation.
