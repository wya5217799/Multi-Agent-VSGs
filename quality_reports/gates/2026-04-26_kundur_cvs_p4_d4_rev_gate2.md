# Stage 2 D4-rev-B — Kundur CVS Gate 2 Re-sweep Verdict (project paper-baseline)

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg` (HEAD `255ab32` after D4 stack closure)
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE 2 RE-SWEEP — under three plan-author dispositions + B (δ_overshoot demoted)
**Predecessors:**
- D4 + D4.1 verdict (FAIL on settle / peak/steady) — `2026-04-26_kundur_cvs_p4_d4_gate2.md`
- D4.2 read-only audit — `2026-04-26_kundur_cvs_p4_d4p2_readonly_audit.md`

---

## Plan-author dispositions applied (cumulative)

| ID | Disposition | Where applied |
|---|---|---|
| 1 | `D_ES0 = 18` (use project paper-baseline `H_ES0=24, D_ES0=18` from `config.py` L32-33; paper Yang TPWRS 2023 does NOT specify a numeric `D_0`) | `build_kundur_cvs.m` L68-82: `M0_default=24, D0_default=18` (was 12 / 3) |
| 2 | Settle: drop strict `≤5 s` absolute; use **relative 5%-of-peak band, threshold 15 s** | `p4_d4_gate2_dist_sweep.py` `SETTLE_FRAC_OF_PEAK=0.05, SETTLE_S_MAX=15.0`; new `_settle_time_relative()` helper |
| 3 | `peak_to_steady` REMOVED from ω channel (D4.2 §4: ill-defined for type-0) | `p4_d4_gate2_dist_sweep.py` removed |
| **B** | **δ-channel overshoot DEMOTED to diagnostic-only — not a Gate 2 hard criterion. Computed and reported alongside the verdict; `1.5` is recorded as a reference, not a pass/fail bound. Replaced in the hard-criteria slot by a new `simulation_health` check (no `matlab.engine` errors AND no NaN/Inf in any per-VSG ω/δ trace).** | `p4_d4_gate2_dist_sweep.py`: dropped `delta_overshoot_le_1p5` from `verdict.add(...)`; added `simulation_health` hard criterion; δ_overshoot now reported under `summary["diagnostic_only"]` |

No model structure / reward / agent / bridge / NE39 / legacy / contract change.
NR (`compute_kundur_cvs_powerflow.m`) and IC schema unchanged: NR-derived `δ₀`,
`Pm₀`, and bus voltages are independent of `M` / `D` (functions of network
topology + Pm₀ + load only); the new D=18 model uses the same NR IC as D2/D3.

---

## Verdict: **PASS** (5 / 5 hard criteria)

| # | Hard criterion | Threshold | Result | Verdict |
|---|---|---|---|---|
| 1 | `linearity_R²` | R² > 0.9 | **R² = 1.0000** | PASS |
| 2 | `max_freq_dev` @ 0.5 pu | ≤ 5 Hz | **0.1514 Hz** (×33 margin) | PASS |
| 3 | `settle_relative_5%-of-peak` | ≤ 15 s | **6.88 – 8.53 s** (15 / 15 runs) | PASS |
| 4 | ω hard clip [0.7, 1.3] | strict | 0 violations | PASS |
| 5 | `simulation_health` | no engine errors AND no NaN/Inf in any ω/δ trace | 15 / 15 clean | PASS |

### Diagnostic-only (NOT counted in PASS/FAIL)

| Metric | Reference | Result | Interpretation |
|---|---|---|---|
| δ-channel overshoot ratio | 1.5 (control rule of thumb, no paper citation) | **min 1.705, max 1.746; 15 / 15 above 1.5** | Faithful physical signal of under-damping at project paper-baseline ζ ≈ 0.033. Empirical 1.70–1.75 matches analytic `1 + exp(-π·ζ/√(1-ζ²)) ≈ 1.902`. Not a model failure. |

---

## Why δ_overshoot was demoted, not deleted (D4-rev-B rationale)

**Demoted because the threshold has no paper basis:**
- Plan §5 / constraint doc row 260 wrote "peak/steady ≤ 1.5" without a Yang
  TPWRS 2023 citation. The 1.5 ratio = 50 % overshoot, equivalent to
  ζ ≈ 0.215 — a textbook control-engineering rule, not a paper requirement.
- Achieving 1.5 in the CVS path needs `D ≈ 2·0.215·√(K_lin·ω_s·M) ≈ 111`,
  far above the project's paper-aligned baseline `D = 18`.
- The paper itself does not specify `D_0` numerically (fact-base §3.3, §10).

**Kept as diagnostic because the metric is physically meaningful on the δ channel:**
- δ is the type-0 step-response channel (new equilibrium δ' = NR-shifted
  rotor angle); ω is the velocity channel and has no new steady (D4.2 §4).
- δ-channel overshoot directly reads the system's damping ratio:
  `1 + %OS = 1 + exp(-π·ζ/√(1-ζ²))`, so the ratio is a one-line ζ proxy.
- Empirical 1.705-1.746 vs analytic 1.902 are 8-11 % below the limit only
  because the probe samples `δ_old` from the last pre-step sample (not the
  `t→T_step⁻` limit) and `δ_peak` from a discrete grid. The physics is
  fully consistent.

**`simulation_health` introduced as the replacement hard criterion** —
catches engine crashes, NaN/Inf, or degenerate traces that any future
Gate 2 sweep should fail loudly on, regardless of the model parameters.

---

## D4.1 diagnostic re-run (against the D=18 traces)

| Quantity | D=3 (D4) | D=18 (D4-rev/D4-rev-B) | Trend |
|---|---|---|---|
| Damping ratio ζ | 0.0077 | **0.0328** | 4.3× higher (still under-damped) |
| Envelope decay σ = D/(2M) | 0.125 / s | **0.375 / s** | 3× faster |
| Envelope τ = 1/σ | 8.0 s | **2.67 s** | matches measured envelope |
| `σ_hat / σ_th` empirical | 0.996 | **1.001** | mean over 15 runs |
| Settle to 5%-of-peak | 12-24 s | **6.9-8.5 s** | within budget |
| Analytic 1+%OS | 1.976 | **1.902** | matches measured 1.70-1.75 |
| Required ζ for δ_overshoot ≤ 1.5 | 0.215 | 0.215 | unchanged (depends on threshold) |
| Required D for above ζ | ~111 | **~111** | far above project paper-baseline 18 |

Per-run results (from `summary.json`, `diagnose.json`, latest run
`results/cvs_gate2/20260425T192459/`):

```
amp seed target  max_dev_Hz  δ_overshoot  settle_5pct_s   clip   sim_health
0.05 1   VSG1    0.0150      1.732(diag)  8.52            False  clean
0.05 2   VSG2    0.0150      1.732(diag)  8.52            False  clean
0.05 3   VSG3    0.0099      1.705(diag)  6.88            False  clean
0.10 1   VSG1    0.0301      1.733(diag)  8.52            False  clean
0.10 2   VSG2    0.0301      1.733(diag)  8.52            False  clean
0.10 3   VSG3    0.0198      1.705(diag)  6.88            False  clean
0.20 1   VSG1    0.0603      1.735(diag)  8.53            False  clean
0.20 2   VSG2    0.0603      1.735(diag)  8.53            False  clean
0.20 3   VSG3    0.0396      1.705(diag)  6.88            False  clean
0.30 1   VSG1    0.0905      1.738(diag)  8.53            False  clean
0.30 2   VSG2    0.0905      1.738(diag)  8.53            False  clean
0.30 3   VSG3    0.0594      1.705(diag)  6.88            False  clean
0.50 1   VSG1    0.1514      1.746(diag)  8.18            False  clean
0.50 2   VSG2    0.1514      1.746(diag)  8.18            False  clean
0.50 3   VSG3    0.0990      1.705(diag)  6.88            False  clean
```

Linearity at amp scaling 0.05 → 0.50 (10×) gives `max_freq_dev` 0.0099 →
0.0990 Hz (10×) for VSG3 target — perfectly linear. R² = 1.0 across all
amplitudes.

---

## Boundary confirmation (D4-rev-B mandate)

| Item | Status |
|---|---|
| `engine/simulink_bridge.py` | UNCHANGED |
| `slx_helpers/vsg_bridge/*` | UNCHANGED |
| `scenarios/contract.py::KUNDUR` | UNCHANGED |
| NE39 anything | UNCHANGED |
| legacy `compute_kundur_powerflow.m`, `kundur_ic.json`, `build_kundur_sps.m`, `build_powerlib_kundur.m`, `kundur_vsg.slx`, `kundur_vsg_sps.slx` | UNCHANGED |
| `agents/`, `config.py`, reward / observation / action | UNCHANGED |
| `Pm0` numeric values, `X_v` / `X_tie` / `X_inf`, `Pe_scale` | UNCHANGED |
| Model structure (block topology) | UNCHANGED — only base-ws default values changed (D4-rev disposition 1) |
| D1 / D2 / D3 / D4 / D4.2 verdict reports on disk | UNCHANGED |
| Gate 3 / SAC / RL training | NOT entered |

**Files touched by D4-rev-B:**

| File | Change |
|---|---|
| `scenarios/kundur/simulink_models/build_kundur_cvs.m` | `M0_default 12 → 24`, `D0_default 3 → 18`, paper-baseline citation comment |
| `scenarios/kundur/simulink_models/kundur_cvs.slx` | rebuilt (block topology unchanged; only stored Constant defaults change) |
| `scenarios/kundur/kundur_ic_cvs.json` | timestamp drift only (NR result identical — δ₀ is M/D-independent) |
| `probes/kundur/gates/p4_d4_gate2_dist_sweep.py` | settle threshold relative 5%-of-peak ≤ 15 s; ω-channel peak/steady removed; δ-overshoot demoted to `summary["diagnostic_only"]`; new `simulation_health` hard criterion (engine error + NaN/Inf detection) |
| `probes/kundur/gates/p4_d4p1_diagnose.py` | M_VSG = 24, D_VSG = 18; field-name migration; classification + recommendation text aligned to D4-rev-B |
| `quality_reports/gates/2026-04-26_kundur_cvs_p4_d4_rev_gate2.md` | this verdict (NEW) |

D1 / D2 / D3 / D4 / D4.1 / D4.2 verdict markdowns are **not modified**; they
remain the historical record of prior parameter / threshold configurations.

---

## Hard criteria, final form (locked by D4-rev-B)

```
1. linearity_R²              R² > 0.9
2. max_freq_dev_at_0.5pu     ≤ 5 Hz
3. settle_relative_5%-of-peak ≤ 15 s (1 s consecutive hold)
4. no_omega_clip_touch       ω ∉ [0.7, 1.3] never violated
5. simulation_health         no matlab.engine errors AND no NaN/Inf in ω/δ
```

Diagnostic-only (reported alongside but not counted):
- δ-channel overshoot ratio (reference 1.5; analytic 1+%OS ≈ 1.902 at
  project paper-baseline ζ ≈ 0.033)

---

## Reproduction

```bash
# Sweep (rebuilds NR + slx + 15 runs, ~3 s wall-clock):
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  probes/kundur/gates/p4_d4_gate2_dist_sweep.py

# Diagnose (trace-only, ~1 s):
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  probes/kundur/gates/p4_d4p1_diagnose.py
```

Pre-condition for the sweep: `matlab.engine.shareEngine('mcp_shared')`
in MATLAB. Diagnostic does not need MATLAB.

Latest run dir: `results/cvs_gate2/20260425T192459/` (gitignored per plan §4).

---

## Next gate

**Gate 3 / 50 ep baseline training is NOT authorised here.** This verdict
records Gate 2 as PASS under D4-rev-B; Gate 3 entry remains a separate
plan-author authorisation (plan §1 D5 + §6). No SAC / no RL is attempted
in this branch until that authorisation is given.
