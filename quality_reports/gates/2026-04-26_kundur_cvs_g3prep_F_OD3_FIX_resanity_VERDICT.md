# G3-prep F OD-F-3 FIX — 5-ep Re-Sanity Verdict

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` @ `83846dd`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE — 5-ep CVS plumbing re-run via `train_simulink.py` to confirm OD-F-3 FIX is end-to-end live through the env entry point.
**Predecessors:** OD3-FIX impl + verdict — commit `83846dd`

---

## Verdict: PASS

All 6 user-mandated checks pass. The Pm-step disturbance fix end-to-end works: env-side `apply_disturbance` reaches the CVS .slx, omega responds, r_f becomes non-trivial, schema is intact, SAC stays in warmup as expected, no NaN/Inf/clip/crash.

---

## 1. Run identifiers

| Field | Value |
|---|---|
| `run_id` | `kundur_simulink_20260425_231740` |
| Wall-clock | 65.9 s (1.1 min) total, **13.16 s/ep mean** (vs pre-fix 13.52, post-instr 13.52) |
| Output dir | `results/sim_kundur/runs/kundur_simulink_20260425_231740/` (gitignored) |
| Seed | 42 (same as prior 5-ep) |
| Exit code | 0 |
| Episodes | 5 |

---

## 2. Six user-mandated checks

| # | Check | Result | Verdict |
|---|---|---|---|
| 1 | console output goes via `[Kundur-Simulink-CVS] Pm step ...` (NOT legacy `Load reduction`) | 5/5 ep print the new line; magnitudes ±0.123 to ±0.393, per-VSG amps ±0.031 to ±0.098 pu | PASS |
| 2 | `max_freq_dev_hz` non-zero and reasonable order | per-ep [0.0423, 0.0929, 0.0349, 0.0219, 0.0705] Hz (mean 0.052 Hz, in verdict §4 prediction band O(1e-2)–O(1e-1)) | PASS |
| 3 | `r_f` non-zero (vs OD3-pre-fix `-7.9e-24`) | per-ep [-0.0005, -0.0012, -0.0002, -0.0001, -0.0006] (~10²¹× larger than pre-fix; still small relative to r_h+r_d under random policy) | PASS |
| 4 | `omega_trace` shows real response (vs pre-fix 5e-14 epsilon noise) | per-agent std 1.1e-4 to 4.2e-4 (~10¹⁰× pre-fix); ep1 trace[0]=1.0 → trace[2]=0.9993 (visible jump at t=0.5s post-warmup, then settling oscillation) | PASS |
| 5 | console NOT touch `[Kundur-Simulink]` legacy load lines | 0 occurrences of legacy line in 5-ep log | PASS |
| 6 | NaN / Inf / clip / crash / SAC update | NaN=0, Inf=0, ω∈[0.998366, 1.001859] far from [0.7, 1.3] clip, no crash, alphas/critic/policy losses arrays len=0 (warmup gating, 5×50=250 « 2000 expected) | PASS |

---

## 3. Per-ep numerics

| Ep | ep_reward | max_freq_dev_hz | mean_freq_dev_hz | settled | r_f | r_h | r_d | r_sum vs ep_reward |
|---|---|---|---|---|---|---|---|---|
| 1 | -298.26 | 0.0423 | 0.0178 | True | -0.0005 | -211.33 | -86.93 | -298.26 ✅ |
| 2 | -303.45 | 0.0929 | 0.0285 | True | -0.0012 | -232.70 | -70.75 | -303.45 ✅ |
| 3 | -453.71 | 0.0349 | 0.0136 | True | -0.0002 | -359.55 | -94.16 | -453.71 ✅ |
| 4 | -384.85 | 0.0219 | 0.0095 | True | -0.0001 | -282.48 | -102.37 | -384.85 ✅ |
| 5 | -437.94 | 0.0705 | 0.0245 | True | -0.0006 | -348.31 | -89.63 | -437.94 ✅ |
| **mean** | **-375.64** | **0.0525** | **0.0188** | True | **-0.0005** | **-286.87** | **-88.77** | exact |

Reward decomposition consistent: r_f + r_h + r_d reproduces ep_reward bit-for-bit (as expected — instrumentation patch in `6d46c75` reads from the existing `ep_components` accumulator, no new computation).

---

## 4. Omega trace fingerprint (ep1)

```
trace[0]   = [1.000000000000057, 1.0000000000000573, 1.000000000000033, 1.000000000000033]
trace[2]   = [0.9993043457512654, 0.9992945864035210, 0.9995730890590131, 0.9997381442013189]
trace[10]  = [1.0001745243715119, 1.0000995580205052, 1.0002455645353312, 1.0001506244764946]
trace[-1]  = [0.9999976893165414, 0.9999976925516111, 1.0000285028683389, 1.000031417468605]
per-agent range = [1.685e-3, 1.666e-3, 6.724e-4, 5.007e-4]
per-agent std   = [4.054e-4, 4.160e-4, 1.412e-4, 1.157e-4]
```

Visible interpretation:
- step 0 (warmup end, pre-disturbance): ω = 1.0 ± 6e-14 (machine precision; consistent with pre-fix CVS NR-IC stiff stability)
- step 2 (just after `apply_disturbance` fires at t=0.5s post-warmup): ω drops to ~0.9993 (per-VSG amp = -0.0625 pu × N=4 = -0.25 pu total, net Pm decrease → mechanical deficit → ω falls — sign consistent with V-FIX-3 verdict)
- step 10 (≈ 2s simulation, oscillation after damping): ω overshoots above 1.0 (transient response with M=24 / D=18)
- step 49 (end): ω settles within 3e-5 of 1.0 (damping settled per `settled = True` flag)

VSG3/4 (range 5e-4 to 6.7e-4) shows smaller response than VSG1/2 (range 1.7e-3) — consistent with the CVS topology where the inter-area tie reactance asymmetry distributes the per-VSG-equal Pm injection unevenly into observed ω trajectories.

---

## 5. Boundary check (post-resanity)

Tracked tree (CVS worktree):
```
?? results/sim_kundur/runs/kundur_simulink_20260425_231740/   (gitignored, this run)
?? quality_reports/patches/                                    (pre-existing)
?? results/sim_*/runs/...                                      (gitignored, prior runs)
```

Source files: 0 modified. The re-sanity is read-only on the codebase.

---

## 6. What this verdict does NOT do

- Does NOT enter Gate 3 / SAC training / 50-ep / 2000-ep
- Does NOT modify any source
- Does NOT recommend disturbance magnitude tuning
- Does NOT compare against NE39 or legacy SPS quantitatively
- Does NOT claim learning success (SAC stayed at α=1.0 initial entropy throughout)

---

## 7. Status snapshot

```
HEAD:                  83846dd  feat(cvs-g3prep-F-OD3-fix): CVS Pm-step disturbance routing
G3-prep-F spec:        committed 1c328fc
F instrumentation:     committed 6d46c75
OD-F-3 verdict:        committed a62c1e9
OD3-FIX design:        committed 710aa3f
OD3-FIX impl+verify:   committed 83846dd
OD3-FIX re-sanity:     PASS — this report
50-ep observation:     NOT RUN, awaits user authorisation
Gate 3 / SAC / 2000-ep:  LOCKED
```

---

## 8. Next step (gated on user)

| Choice | Effect |
|---|---|
| Authorise 50-ep observation smoke (per spec `1c328fc`) | runs ~14 min; 5 dimensions of spec answered with non-trivial dynamics |
| Hold | no further run; commit this verdict and pause |

Halts here. Gate 3 / SAC / 2000-ep / NE39 modifications all remain LOCKED.
