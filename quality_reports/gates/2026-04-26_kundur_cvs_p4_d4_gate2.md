# Stage 2 D4 + D4.1 — Kundur CVS Gate 2 Verdict (FAIL) + Diagnosis

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE 2 — disturbance sweep (5 amp × 3 seeds × 30 s) + diagnostic-only follow-up
**Predecessors:**
- Stage 2 plan §1 D4 + §5 Gate 2 — `quality_reports/gates/2026-04-25_kundur_cvs_stage2_readiness_plan.md`
- D3 Gate 1 PASS — `quality_reports/gates/2026-04-26_kundur_cvs_p4_d3_gate1.md`

---

## TL;DR

- **Gate 2 verdict: FAIL** (3 / 5 PASS)
- 1 of the 2 FAIL criteria (`peak_to_steady`) is **pure metric pathology** —
  not a physical issue
- 1 of the 2 FAIL criteria (`settle ≤ 5 s`) is a **hard physical FAIL** caused
  by ζ = 0.0077 (D = 3, M = 12). A relative 5%-of-peak band still requires
  ~24 s — metric redefinition alone does **not** save this criterion.
- **Recommendation: C — DEFER.** Stop Stage 2. Ask plan author whether
  D = 3 is the paper-baseline value or a P2/P3 spike artefact, before any
  damping change is considered.
- **No model / parameter / threshold change applied.** D4 mandate held.

---

## Per-criterion Gate 2 result

| # | Criterion | Threshold | Result | Verdict |
|---|---|---|---|---|
| 1 | `linearity_R2` (mean max_freq_dev vs amp) | R² > 0.9 | R² = 0.999995 | **PASS** |
| 2 | `max_freq_dev` at 0.5 pu | ≤ 5 Hz | 0.2397 Hz (×21 margin) | **PASS** |
| 3 | `peak_to_steady` ratio | ≤ 1.5 | 21.97 (amp=0.5, seed∈{1,2}) | **FAIL** (metric pathology) |
| 4 | `settle_time` after step | ≤ 5 s | up to 15.45 s (amp=0.5) | **FAIL** (physical) |
| 5 | ω hard clip [0.7, 1.3] | strict | 0 violations | **PASS** |

---

## D4 sweep envelope

5 amplitudes × 3 seeds (target VSG ∈ {1,2,3}), 30 s each, t_step = 5 s,
disturbance via base-ws `Pm_step_amp_<i>` (FR-tunable Constant +
Clock + Relational + Cast + Product + Sum chain). FastRestart on. Sweep
wall-clock ≈ 3 s.

| amp (pu) | mean max_freq_dev (Hz) | settle (s, amp=seed1) | clip touch |
|---|---|---|---|
| 0.05 | 0.0207 | 0.00 (already in band) | False |
| 0.10 | 0.0415 | 4.83 | False |
| 0.20 | 0.0830 | 10.66 | False |
| 0.30 | 0.1247 | 13.62 | False |
| 0.50 | 0.2086 | 15.45 | False |

Linearity R² = 0.99999, slope 0.42 Hz / pu. At 0.5 pu the response is
**21× below** the 5 Hz `max_freq_dev` ceiling — no frequency-band saturation
anywhere.

---

## D4.1 — Diagnostic-only follow-up (no resim, no model touch)

`probes/kundur/gates/p4_d4p1_diagnose.py` reads the 15 npz traces produced by
the sweep and classifies each FAIL.

### Analytic predictions (linearised swing equation per VSG)

| Quantity | Formula | Value |
|---|---|---|
| Envelope decay rate σ_th | `D / (2M)` | 0.1250 / s |
| Natural freq ω_n | `√(K_lin · ω_s / M)` with K_lin = 1/X_v = 10 | 16.18 rad/s |
| Damping ratio ζ | `D / (2 √(K_lin · ω_s · M))` | **0.0077** (extreme under-damping) |
| Envelope τ | `1 / σ_th = 2M / D` | 8.0 s |
| Time to envelope ≤ 5e-4 pu @ amp=0.5 (peak ≈ 5e-3 pu) | `ln(peak / 5e-4) / σ_th` | ≈ 18 s |
| Time to envelope ≤ 5 % of peak | `ln(20) / σ_th` | ≈ 24 s |
| Required σ for settle ≤ 5 s to 5e-4 pu band | `ln(5e-3 / 5e-4) / 5` | ≈ 0.46 / s |
| Required D for the above σ | `2 M σ` | **≈ 11.1** (vs current 3) |

### Empirical envelope match

Per-run least-squares fit of `|ω-1|_envelope ≈ A · exp(-σ·t)` on local maxima:

| Quantity | Mean | Min | Max |
|---|---|---|---|
| `σ_hat / σ_th` | **0.996** | 0.883 | 1.117 |

Empirical envelope decay matches the analytical D/(2M) within 12 % across all
15 runs. **The system is settling exponentially, exactly as the linearised
swing equation predicts; nothing is wrong with the dynamics or the IC.**

### ω returns to 1.0 in all 15 runs

Tail-window mean of `|ω-1|` (last 5 s of each 30 s sim) is < 5e-4 pu in
all 15 runs. The system is type-0 (no integral state) — the new equilibrium
for ω after a Pm step **is the same ω = 1**, with the new equilibrium
captured entirely in δ. There is no "new steady-state ω" to compare a peak
against.

### Classification of the 2 FAILs

| Criterion | Class | Why |
|---|---|---|
| `peak_to_steady` | **metric pathology** | ω returns to 1 (type-0); `steady` ≈ 1e-4 is residual decay tail, not a meaningful steady-state offset; ratio undefined for an asymptotically-stable open-loop system whose steady ≡ 0 |
| `settle ≤ 5 s` | **hard physical FAIL** | ζ = 0.0077 fixed by D=3, M=12. Even a 5%-of-peak relative band requires ~24 s. Any "≤ 5 s settle" criterion needs σ ≥ 0.46 / s → D ≥ 11.1 |

### Critical correction vs the first-pass D4 verdict

The first-pass verdict suggested re-defining settle as "≤ 5 % of peak"
might fix criterion 4 with no model change. **D4.1 disproves this**:

```
[d4.1] settle to 5%-of-peak (relative band) max = inf
[d4.1] settle_to_5pct_peak_all_pass_5s: False
```

The relative band is ALSO unreachable in 5 s for amp ≥ 0.1, because the
envelope itself takes 24 s to decay to 5 %. **Metric redefinition alone
does not flip criterion 4 to PASS.** Only a damping increase, or a re-scoping
of plan §5 settle target, can.

---

## Did D4 expand scope?

**No.** Worktree dirty inventory after D4 + D4.1, line-by-line:

| File | Change | Authorised? |
|---|---|---|
| `scenarios/kundur/simulink_models/build_kundur_cvs.m` | added `Pm_step_t_<i>` / `Pm_step_amp_<i>` defaults + 1 global Clock + 4 × {`Pm_step_t_c`, `Pm_step_amp_c`, `GE`, `Cast`, `PmStepMul`, `PmTotal`} blocks; replaced `Pm_<i>_c → SwingSum/1` line with `Pm_<i>_c + step_pulse → SwingSum/1` | ✅ D4 sweep authorisation + plan §2 E5 |
| `scenarios/kundur/simulink_models/kundur_cvs.slx` | rebuilt | ✅ build artefact |
| `scenarios/kundur/kundur_ic_cvs.json` | timestamp only (NR result identical) | ✅ NR re-run on rebuild path |
| `probes/kundur/gates/p4_d4_gate2_dist_sweep.py` | NEW — 15-run sweep + 5-criterion gate | ✅ D4 sweep authorisation |
| `probes/kundur/gates/p4_d4p1_diagnose.py` | NEW — diagnostic-only trace analyser | ✅ user-authorised D4.1 |
| `quality_reports/gates/2026-04-26_kundur_cvs_p4_d4_gate2.md` | this verdict | ✅ |
| `results/cvs_gate2/<ts>/{traces, summary.json, diagnose.json}` | gitignored | ✅ |

**Verified untouched (per all prior boundary mandates):**
- `engine/simulink_bridge.py` — UNCHANGED
- `slx_helpers/vsg_bridge/*` — UNCHANGED
- `scenarios/contract.py::KUNDUR` — UNCHANGED
- NE39 anything — UNCHANGED
- legacy `compute_kundur_powerflow.m`, `kundur_ic.json`, `build_kundur_sps.m`,
  `build_powerlib_kundur.m`, `kundur_vsg.slx`, `kundur_vsg_sps.slx` — UNCHANGED
- `agents/`, `config.py`, reward / observation / action — UNCHANGED
- `M`, `D`, `Pm0`, `X_v`, `X_tie`, `X_inf` numeric values — UNCHANGED (still
  M=12, D=3, Pm0=0.5, X_v=0.10, X_tie=0.30, X_inf=0.05)
- D1 / D2 / D3 verdict reports — UNCHANGED on disk
- thresholds in plan §5 — UNCHANGED in any code

`git diff --name-only HEAD ^HEAD~3` (D2 → present) confirms only the files
above. The D4 disturbance path is the **minimum** new infrastructure
required to do the sweep; it is gated by `Pm_step_amp_<i> = 0` (default),
making the D4 model exactly equivalent to D3 when no sweep is active.

---

## Recommendation — **C: DEFER**

**Do:**
- Record this verdict (FAIL) on disk
- Commit D4 + D4.1 artefacts as an **isolated diagnostic baseline**
- Stop at Stage 2 boundary

**Do not:**
- Enter Gate 3 / SAC / RL
- Change `M`, `D`, `Pm0`, or any swing-equation parameter
- Relax / redefine plan §5 thresholds in code
- Extend disturbance scope beyond Pm_step base-ws path

**Open questions for plan author (the only path forward):**
1. **Is `D = 3` the paper-baseline value or a P2/P3 spike artefact?**
   Yang Sec.IV-B states `ΔD ∈ [-200, 600]` (training action range), which
   strongly implies the baseline `D` is **on the order of hundreds**, not 3.
   If the paper baseline is e.g. D = 50, ζ rises to 0.10 and settle to a
   relative band drops below 5 s. (criterion 4 likely PASSes; criterion 3
   would still need redefinition.)
2. **Is plan §5 "settle ≤ 5 s" paper-grounded or a control-engineering
   rule of thumb?** The paper does not specify a settle-time target for
   the dynamic-validation gate; the value was inherited from the readiness
   plan. If the bound is loose, criterion 4 needs revision regardless of D.
3. **Should `peak_to_steady` be replaced or removed for type-0 systems?**
   The metric is provably ill-defined when `steady → 0`; either drop it or
   replace by overshoot-vs-linear-prediction.

Three options on the table, in order of preference per D4.1 evidence:

| ID | Action | Risk | Outcome |
|---|---|---|---|
| **C** | Defer; ask plan author | none | D4 stays FAIL; Stage 2 stops here |
| A | After authorisation: change D to paper baseline (≥ ~50) | mutates swing dynamics; needs paper-fidelity check | criterion 4 PASS; criterion 3 still FAIL until redefined |
| B | Drop / redefine `peak_to_steady` only | partial (criterion 4 still FAIL) | Gate 2 still FAIL on settle |

---

## Reproduction

```bash
# Sweep (re-runs NR + rebuild + 15 runs; wall-clock ~3 s):
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  probes/kundur/gates/p4_d4_gate2_dist_sweep.py

# Diagnose (trace-only, no MATLAB engine, ~1 s):
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  probes/kundur/gates/p4_d4p1_diagnose.py
```

Pre-condition for the sweep: `matlab.engine.shareEngine('mcp_shared')`
in MATLAB. Diagnostic does not need MATLAB.

---

## Next gate (gated on disposition)

**Gate 3 / 50 ep baseline training is NOT authorised.** Gate 2 must PASS
(or be re-scoped with explicit plan amendment) first. No SAC / no RL is
attempted in this branch until then.
