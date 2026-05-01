# ODE Paper-Alignment Deviations — D1/D2/D3 (2026-05-02)

status: documented
**Date:** 2026-05-02
**Owner:** Project main line (ODE track)
**Plan:** `quality_reports/plans/2026-05-02_ode_paper_alignment.md`
**Scope:** KD (Kundur 4-agent) ODE training environment
**Sibling docs:** `action-range-mapping-deviation.md` (Simulink-side action range)

> **Reminder (PAPER-ANCHOR LOCK 2026-04-30):** A `status: documented` deviation
> cannot be cited as supporting evidence for any paper-class claim.
> Project偏差 ≠ paper alignment. See `quality_reports/paper_compliance/README.md`.

---

## Purpose

This document registers three project-side deviations from the boundary
document `docs/paper/python_ode_env_boundary_cn.md` (which is itself a
project-self-imposed contract, not paper text). Each deviation is justified
on either (a) physical infeasibility of paper-literal numbers, or
(b) misclassification of gymnasium engineering convention as paper invariant.

**These are NOT deviations from paper Eq.1-23, Algorithm 1, or any paper
section. The paper itself does not specify return signatures, integrator
choice, or H0 baselines.** Deviations from paper PRIMARY content live in
sibling docs (`action-range-mapping-deviation.md` etc.).

---

## D1 · ODE-side action range — keep `[-16.1, 72] / [-14, 54]`

### D1.1 Paper PRIMARY
- Sec.IV-B (paper line 938-939): "ΔH ∈ [−100, +300], ΔD ∈ [−200, +600]"
- Paper does **not** state H0 baseline value.

### D1.2 ODE implementation state
- `config.py:32-33`: `H_ES0 = [24, 24, 24, 24]`, `D_ES0 = [18, 18, 18, 18]`
- `config.py:49-50`: `DH_MIN, DH_MAX = -16.1, 72.0`; `DD_MIN, DD_MAX = -14.0, 54.0`
- Floor clamps: `H≥8`, `D≥0.1` (env line 162-163)

### D1.3 The deviation
| Param | Paper-literal | ODE | Ratio |
|---|---|---|---|
| ΔH | [−100, +300] | [−16.1, +72] | ~6× narrower |
| ΔD | [−200, +600] | [−14, +54] | ~14× narrower |

### D1.4 Why not adopt paper-literal
- ΔH = -100 → H_target = 24 - 100 = -76 → physically impossible
- Floor clamp would mask 87% of action space (parallel to Phase C verdict
  for Simulink side; see `action-range-mapping-deviation.md` §4.1)
- **Alternative reading**: paper expresses the range as multipliers of an
  unspecified H0; under H0=24, paper "−100 to +300" maps to "−4×H0 to
  +12×H0", which exceeds physical bounds even with project-flexible H0
- Project chooses: `[+72] = 3×H0`, `[-16.1] ≈ -2/3×H0` — interprets paper
  ranges as **mechanism-aligned (allow H redistribution)** not
  **number-aligned (literal MW values)**

### D1.5 Disclaimer
This is a **project inference**, not a paper fact. Cite as project assumption.

### D1.6 Status
**Documented deviation.** ODE uses ΔH=[−16.1, +72] / ΔD=[−14, +54] (~6× /
~14× narrower than paper-literal). Distinct from Simulink-side deviation
(33× / 133×, see `action-range-mapping-deviation.md` for Simulink case).

---

## D2 · ODE env interface — additive extension, not gymnasium-style break

### D2.1 Boundary doc PRIMARY (project-self-imposed)
`docs/paper/python_ode_env_boundary_cn.md`:
- §13: `obs, info = env.reset(scenario=Scenario(...))`
- §14: `obs_next, reward, terminated, truncated, info = env.step(action)`
- Action shape: `(N, 2)` ndarray
- Distinct `terminated` (numerical/safety failure) vs `truncated` (50-step limit)

### D2.2 Why this is NOT paper-anchored
- Paper §III/§IV makes **no statement** about return signatures.
- The form above is gymnasium ≥0.26 single-agent convention.
- This project is multi-agent; PettingZoo / MARLlib conventions use
  dict-keyed actions/obs.
- `(terminated, truncated)` distinction has no information content here:
  episodes are exactly 50 steps, no early termination by design.

### D2.3 Project decision (D2 = Option C "additive extension")
Keep current signature:
- `obs = env.reset(*, scenario=ODEScenario(...) | None, delta_u=... | None)`
  - **new** `scenario=` kwarg (additive)
  - **legacy** `delta_u=` kwarg retained
- `obs, rewards, done, info = env.step(actions: dict[int, np.ndarray])`
  - 4-tuple preserved
  - `dict` actions preserved (matches `MultiAgentManager.select_actions`)
- Numerical/safety failure → `done=True` + `info["termination_reason"]`
- Clip event → `info["action_clip"]` dict

### D2.4 Cost analysis (why C beats full-break)
| Path | Caller diff | Manager diff | Test diff | Future Simulink bridge |
|---|---|---|---|---|
| C (additive) | 0 lines | 0 lines | 0 lines | unchanged |
| Full break | ~25 sites in 6 files | dict→ndarray ripple | breaks 2 ode tests | unchanged |

C delivers all paper-relevant alignment (fixed scenario set, train/eval reward split,
NaN/clip logging) without touching caller signatures.

### D2.5 Boundary doc reconciliation
The boundary doc § 13/§14 should be re-classified as
**"gym-style engineering preference, NOT paper invariant"**. A banner is
added to that doc's top in Stage 0 of this plan.

### D2.6 Status
**Documented deviation from boundary doc §13/§14.** Paper-relevant
requirements (§16 fixed scenario, §15 safety, §11 train/eval split) are
satisfied additively.

---

## D3 · Integrator choice — fixed RK4 (substeps=20) instead of adaptive RK45

### D3.1 Boundary doc PRIMARY (project-self-imposed)
- §12: "建议第一版使用固定步长 RK4; ode_dt = 0.005 s 或 0.01 s; substeps = control_dt / ode_dt"

### D3.2 Current ODE implementation state
- `env/ode/power_system.py:227-235`: `solve_ivp(method='RK45', rtol=1e-6, atol=1e-8, max_step=dt/10)`
- Adaptive timestep → non-deterministic substep count → non-byte-reproducible across runs

### D3.3 Project decision (D3 = adopt RK4)
- Replace `solve_ivp(RK45)` with self-implemented fixed-step RK4
- `dt_substep = 0.01s`, `n_substeps = round(control_dt / dt_substep) = 20`
- Removes `scipy.integrate.solve_ivp` dependency for ODE step path

### D3.4 Why this is NOT a paper deviation
- Paper does not specify integrator. RL training requires byte-level
  reproducibility (§16 paper alignment) → adaptive solver disqualified
  on engineering grounds, not paper grounds.

### D3.5 Trade-off
- Lose: adaptive accuracy (RK45 with rtol=1e-6 is ~10x more precise per substep)
- Gain: deterministic timing, exact reproducibility, simpler debug surface
- Mitigation: substeps=20 with RK4 4th-order accuracy → per-substep error
  O(dt^5) = O(10^-10) on smooth dynamics, well below RL signal noise floor

### D3.6 Status
**Documented deviation from current code (RK45) toward boundary doc §12 (RK4).**
Will be implemented in Stage 1 of this plan.

---

## Cross-references

### Plan
- `quality_reports/plans/2026-05-02_ode_paper_alignment.md`

### Code anchors (to be modified by Stage 1-4)
- `env/ode/power_system.py` (D3 integrator)
- `env/ode/multi_vsg_env.py` (D2 reset signature, info dict)
- `config.py` (D1 — UNCHANGED, comment only)
- `scenarios/kundur/train_ode.py`, `scenarios/kundur/evaluate_ode.py` (D2 caller migration)

### Paper PRIMARY
- `docs/paper/kd_4agent_paper_facts.md` §1 (Eq.1), §6 (Sec.IV-A), §13 (Q-A H 量纲)

### Sibling deviation docs
- `action-range-mapping-deviation.md` — Simulink-side action range (different ratios, different rationale)
- `eval-disturbance-protocol-deviation.md`
- `disturbance-protocol-mismatch-fix-report.md`
- `kundur-cvs-loadstep-minimal-physical-fix.md`

### Boundary doc (project-self-imposed contract, not paper text)
- `docs/paper/python_ode_env_boundary_cn.md` — see §13/§14 reclassification banner

---

## Maintenance

Update this file when:
1. D1 paper-literal range becomes physically tractable (e.g., if H0 is
   re-anchored — no current trigger)
2. D2 boundary doc §13/§14 is rewritten or removed
3. D3 RK4 numerical accuracy is verified insufficient (would require
   substep increase or RK45 fallback with seed control)

---

*End of ode_paper_alignment_deviations.md*
