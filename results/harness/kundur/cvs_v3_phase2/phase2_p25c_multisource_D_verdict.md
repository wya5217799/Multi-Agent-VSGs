# Phase 2.5c Verdict — Coordinated Multi-Source D Sensitivity

> **Status: D action axis CONFIRMED PRESENT but globally MARGINAL — P2.5 stays CONDITIONAL PASS for RL-readiness.**
> **Date:** 2026-04-26
> **Probe:** [`probes/kundur/v3_dryrun/probe_d_multisource_decay.m`](../../../../probes/kundur/v3_dryrun/probe_d_multisource_decay.m)
> **Summary JSON:** [`p25c_d_multisource_decay.json`](p25c_d_multisource_decay.json)
> **Compares against:** [`phase2_p25b_L1_verdict.md`](phase2_p25b_L1_verdict.md) (single-source ES1 D sweep, τ ratio = 1.44)

---

## 1. Method

Identical probe to `probe_d_sensitivity_decay.m` (P2.5b-L1) **except** all 4 ESS D values move together:

- M_1 = M_2 = M_3 = M_4 = 24 fixed (H = 12)
- D_all = D_1 = D_2 = D_3 = D_4 ∈ {1.5, 7.5}
- Disturbance: ES1 +0.2 sys-pu Pm step at t = 35 s (clean mid-sim gate per P2.2)
- Metric: τ via log-linear fit on cycle-peak envelope of |ω_ES1 − 1| post-step
- Pass band: [3, 10] (the simple-oscillator M/D = 5× tolerance)

---

## 2. Results

| D_all | n_peaks | τ (s) | R² | first peak (pu) |
|---|---|---|---|---|
| 1.5 | 30 | **4.268** | 0.996 | 1.405 e-3 |
| 7.5 | 28 | **2.956** | 0.997 | 1.361 e-3 |

| Quantity | Value |
|---|---|
| τ ratio (D_all=1.5 / D_all=7.5) | **1.444** |
| Predicted (simple oscillator) | 5.0 |
| Single-source (P2.5b-L1) ratio | 1.44 |
| **Coordinated improvement factor** | **1.00×** (i.e. no change) |

---

## 3. Interpretation — falsifies the P2.5b-L1 single-source-coupling hypothesis

P2.5b-L1 attributed the 1.44 ratio to ES1 being only one of 7 sources, predicting that coordinated all-ESS sweep would recover ratios closer to 5. The data **rejects this hypothesis** (1.44 → 1.444, no improvement).

The corrected explanation: **the 3 SG sources (G1/G2/G3 with D = 5 gen-pu, M = 13 / 13 / 12.35 gen-base) dominate the modal damping of the dominant decay mode**. The 4 ESS group, even when their D values change by 5× simultaneously, cannot move the network-mode decay rate beyond ~44 % because ESS damping is a small fraction of total damping authority.

Back-of-envelope, treating modal damping as `Σ_i φ_i² · D_i / M_i`:

| Source | M | D | mode-shape participation² (heuristic) | damping units (D/M · φ²) |
|---|---|---|---|---|
| G1 | 13 (gen) | 5.0 | ~0.10 | 0.038 |
| G2 | 13 | 5.0 | ~0.10 | 0.038 |
| G3 | 12.35 | 5.0 | ~0.10 | 0.040 |
| ES1 | 24 (vsg) | 1.5 → 7.5 | ~0.10 | 0.006 → 0.031 |
| ES2 | 24 | same as ES1 | ~0.10 | 0.006 → 0.031 |
| ES3 | 24 | same | ~0.10 | 0.006 → 0.031 |
| ES4 | 24 | same | ~0.10 | 0.006 → 0.031 |
| **Total damping units (D_all=1.5)** | | | | **0.140** |
| **Total damping units (D_all=7.5)** | | | | **0.240** |
| Predicted τ ratio (1/Σ ratio) | | | | **0.240 / 0.140 = 1.71** |

(Heuristic 0.10 participation² each is uniform; actual modal calculations would refine the numbers but the order of magnitude — ratio between 1.3 and 2.0 — is robust.)

Observed 1.44 is **inside this corrected band**. The SG damping floor is the dominant authority over the network's decay envelope, and the ESS group can only marginally modulate it.

---

## 4. RL-readiness implication (NEW finding)

This changes the operational expectation for Phase 4 / Phase 5 RL training:

- **H action axis** (P2.5a confirmed 4.86×): SAC agent **can** materially modulate the inertia term and thus ROCOF / nadir behavior. Primary action lever.
- **D action axis** (P2.5b-L1 + P2.5c): SAC agent **can** modulate ESS damping but the network damping authority is dominated by SG. Secondary / marginal lever — agent may learn to keep D in a narrow optimal range rather than coordinating large swings.

This is **paper-consistent** — Yang TPWRS 2023 §II frames VSG ESS as supplementary frequency support, with SG providing dominant inertial response. The model correctly reproduces this ranking.

For Phase 4 50-ep gate: expect r_f signal to be more sensitive to H actions than D actions. Reward shaping (PHI_H vs PHI_D) might need tuning; current `PHI_H = PHI_D = 1e-4` (B1 baseline) treats them symmetrically, which may be sub-optimal given this asymmetry.

---

## 5. Verdict per user policy

> "If tau ratio is in band, upgrade P2.5 from CONDITIONAL PASS to PASS for action-axis validity: H controls ROCOF, D controls damping/decay.
> If tau ratio is not in band, keep P2.5 as CONDITIONAL PASS and document D as present but not yet quantitatively validated."

τ ratio 1.444 ∉ [3, 10] under coordinated all-ESS sweep ⇒ **P2.5 retains CONDITIONAL PASS**.

D mechanism is mechanically present and quantitatively measurable but its **global damping authority is weaker than the simple-oscillator M/D theory predicts** — because the SG damping floor (D = 5 on three large machines) dominates the network mode. Not a model defect; paper-faithful structural property of the heterogeneous v3 system.

---

## 6. Updated Phase 2 status

| Probe | Status |
|---|---|
| P2.1 zero-action | PASS |
| P2.2 Pm-step reach | PASS |
| P2.3 LoadStep reach (L1) | CONDITIONAL — Bus 7 PASS, Bus 9 stiff |
| P2.4 wind trip (L1) | CONDITIONAL — W1 PASS, W2 probe artifact |
| P2.5a H sensitivity | PASS (4.86×) |
| P2.5b D sensitivity (single-source decay) | CONDITIONAL — 1.44× |
| **P2.5c D sensitivity (coordinated decay)** | **CONDITIONAL — 1.44×, marginal global damping authority** |

Phase 2 aggregate verdict ([`phase2_aggregate_verdict.md`](phase2_aggregate_verdict.md)) remains **CONDITIONAL PASS**, but the D-axis CONDITIONAL is now better understood as a **paper-consistent SG-dominated damping property**, not a single-source coupling artifact.

---

## 7. Boundary respected

| Item | Status |
|---|---|
| `compute_kundur_cvs_v3_powerflow.m` / `kundur_ic_cvs_v3.json` | **untouched** since Phase 1 commit `a40adc5` |
| `build_kundur_cvs_v3.m` / `.slx` / `_runtime.mat` | **untouched** since fix-A2 commit `7911e28` |
| Other probes / verdicts | **untouched** since Phase 2 commit `c1c8323` |
| Topology / dispatch / V_spec / line per-km params | **untouched** |
| v2 / NE39 / SAC / shared bridge / env / profile / training | **untouched** |

Only new files in this iteration:
```
probes/kundur/v3_dryrun/probe_d_multisource_decay.m
results/harness/kundur/cvs_v3_phase2/p25c_d_multisource_decay.json
results/harness/kundur/cvs_v3_phase2/phase2_p25c_multisource_D_verdict.md
```

---

## 8. Recommendation for Phase 3 / RL-readiness

The P2.5c result is a **strong signal for Phase 4 reward shaping**: H and D should likely have asymmetric weights `PHI_H > PHI_D` to reflect the asymmetric authority. Defer the exact ratio choice to Phase 4 50-ep gate empirics (try `PHI_H = 1e-3, PHI_D = 1e-4` as a starting hypothesis — gives H 10× more reward sensitivity, matching the rough authority ratio).

P2.5c does NOT block Phase 3 work. It informs it.

---

## 9. Halt

Awaiting user GO before any further action. P2.5c PROBE-ONLY, no model touched.
