# Stage 2 Day 3 — Kundur CVS Gate 1 Verdict (30 s zero-action stability)

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE 1 — 30 s zero-action stability (no SAC, no disturbance)
**Predecessors:**
- Stage 2 plan §1 D3 + §4 Gate 1 — `quality_reports/gates/2026-04-25_kundur_cvs_stage2_readiness_plan.md`
- D2 NR IC verdict — `quality_reports/gates/2026-04-26_kundur_cvs_p4_d2_nr_ic.md`
- D1 topology verdict — `quality_reports/gates/2026-04-26_kundur_cvs_p4_d1_topology.md`

**Model under test:** `kundur_cvs.slx` at HEAD `5b269d1` (post-D2)
**IC under test:** `kundur_ic_cvs.json` at HEAD `5b269d1` (NR converged 5 iter, max_mismatch 3.56e-15 pu)

---

## Verdict: PASS

5 strict criteria all green over the full 30 s window. NR initial condition
holds the swing-equation at exact equilibrium — every state is constant to
floating-point precision.

---

## Artifacts

| File | Role |
|---|---|
| `probes/kundur/gates/p4_d3_gate1_30s_zero_action.py` | NEW — 30 s gate orchestrator + 5-criterion check |
| `results/cvs_gate1/20260425T182524/omega_ts_<i>.npz` (×4) | Per-VSG ω timeseries (gitignored, worktree-local) |
| `results/cvs_gate1/20260425T182524/delta_ts_<i>.npz` (×4) | Per-VSG δ timeseries (gitignored) |
| `results/cvs_gate1/20260425T182524/Pe_ts_<i>.npz` (×4) | Per-VSG Pe timeseries (gitignored) |
| `results/cvs_gate1/20260425T182524/summary.json` | Numeric summary (gitignored per plan §4) |
| `quality_reports/gates/2026-04-26_kundur_cvs_p4_d3_gate1.md` | This verdict |

`results/` is gitignored (`.gitignore` entries for `results/**/*.json` and
`results/**/*.npz`) per plan §4 — only the verdict report and the probe are
promoted into the branch.

Plan §1 D3 / §4 Gate 1 strict ban honored:
- ❌ no SAC / no RL training entry
- ❌ no disturbance (D4 / Gate 2 scope)
- ❌ no `engine/simulink_bridge.py` change
- ❌ no `slx_helpers/vsg_bridge/*` change (NE39 共享层)
- ❌ no NE39 / legacy / `scenarios/contract.py::KUNDUR` change
- ❌ no threshold relaxation (verdict reflects raw measurement)
- ❌ no model rebuild on FAIL (didn't FAIL — would have stopped at diagnosis)

---

## Gate 1 Pass Criteria — all PASS

| # | Criterion | Threshold | Result | Verdict |
|---|---|---|---|---|
| 1 | ω in [0.999, 1.001] full 30 s, per agent | strict band | VSG1..4 ω∈[1.000000, 1.000000] | PASS |
| 2 | \|δ\| < π/2 - 0.05 full 30 s, per agent | < 1.5208 rad | VSG1/2 \|δ\|max = 0.2939; VSG3/4 \|δ\|max = 0.1107 | PASS |
| 3 | Pe within ±5 % of Pm₀ full 30 s, per agent | rel ∈ [-5 %, +5 %] | VSG1..4 Pe∈[0.5000, 0.5000], max_rel=0.00 % | PASS |
| 4 | ω never touches [0.7, 1.3] hard clip | strict | clip_touch = False (all 4) | PASS |
| 5 | inter-agent sync, tail 5 s | spread < 1e-3 | tail_means = [1.000000]×4, spread = 0.000e+00 | PASS |

Sim wall-clock: 0.38 s for 30 s of model time (variable-step ode23t coalesces
to a near-zero step count because the system is at exact equilibrium).

---

## Per-agent dump (from `summary.json`)

| VSG | ω_min | ω_max | \|δ\|max (rad) | Pe_min | Pe_max | Pm₀ |
|---|---|---|---|---|---|---|
| VSG1 | 1.000000000 | 1.000000000 | 0.293922 | 0.5000−5e-16 | 0.5000−5e-16 | 0.5 |
| VSG2 | 1.000000000 | 1.000000000 | 0.293922 | 0.5000+3e-16 | 0.5000+3e-16 | 0.5 |
| VSG3 | 1.000000000 | 1.000000000 | 0.110666 | 0.5000+2e-16 | 0.5000+2e-16 | 0.5 |
| VSG4 | 1.000000000 | 1.000000000 | 0.110666 | 0.5000−1e-16 | 0.5000−1e-16 | 0.5 |

Pe deviation from Pm = 5e-16 → exact agreement at floating-point precision.
This validates that the D2 NR IC + Pe_scale convention (1.0/Sbase) is the
true equilibrium of the swing-equation closure under zero action.

---

## Why a "trivially flat" PASS is the correct outcome

This gate intentionally tests the static IC, not dynamics. Once the NR IC
puts the swing-equation at exact equilibrium, the ode23t variable-step
solver detects no state derivative change and advances large steps with
zero drift. Any drift would indicate an IC inconsistency (and would have
shown up at D2 already).

Plan §1 D3 says explicitly that this gate's purpose is to confirm the NR
IC holds without dynamics — disturbance perturbation is reserved for D4 /
Gate 2. Therefore "ω = 1 to floating-point precision over 30 s" is the
expected outcome under the strict reading of the plan, and is recorded
here as PASS.

---

## Reproduction

```bash
# From the worktree root, with MCP MATLAB shared session running:
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  probes/kundur/gates/p4_d3_gate1_30s_zero_action.py
```

Pre-condition: `matlab.engine.shareEngine('mcp_shared')` was issued in MATLAB.

Expected output: `OVERALL: PASS` with 5 PASS lines; timeseries +
`summary.json` written under `results/cvs_gate1/<timestamp>/`.

---

## Hashes (commit `5b269d1`)

| Artifact | SHA-256 |
|---|---|
| `scenarios/kundur/simulink_models/kundur_cvs.slx` | `0a7114de…38194d` |
| `scenarios/kundur/kundur_ic_cvs.json` | `4850f784…9d9b0b` |
| `scenarios/kundur/matlab_scripts/compute_kundur_cvs_powerflow.m` | `5338ef3b…41541a` |

(Hashes from D2 verdict; unchanged at D3.)

---

## Next gate

**D4 — Gate 2 disturbance sweep** (Stage 2 plan §1 D4 + §5):
- Sweep `dist_amp ∈ {0.05, 0.1, 0.2, 0.3, 0.5} pu × 3 seeds = 15 runs × 30 s`
- Injection path: base-ws `Pm_step_t` / `Pm_step_amp` (FR-tunable, **not**
  TripLoad) — to be implemented in D4 (currently absent from
  `build_kundur_cvs.m`; will be added as a new base-ws gated Pm input).
- Pass criteria: max_freq_dev linearity R² > 0.9; settle ≤ 5 s; peak/steady
  ≤ 1.5; no ω clip touch; max_freq_dev ≤ 5 Hz at 0.5 pu.
- Outputs: `results/cvs_gate2/<timestamp>/{trace_dist_<amp>_seed<s>.npz, summary.json}`.

D4 starts only on user authorization after this D3 verdict is reviewed and
committed.
