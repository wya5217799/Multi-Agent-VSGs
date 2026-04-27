# R2 Verdict — PHI re-sweep with paper-style gate — ALL 3 CANDIDATES FAILED

> **Status:** FAIL — all 3 PHI candidates produce DDIC cum_unnorm WORSE than zero-action no-control. Combined with P5.1 (`phi_b1` also WORSE), 4/4 PHI configurations exhibit the same regression. PHI tuning alone cannot fix this. Root cause analysis points to **Pm-step proxy disturbance topology**, not reward weights.
> **Date:** 2026-04-27
> **Predecessor:** R1 audit (formula correct), P5.1 evaluator (DDIC `phi_b1` −19 % WORSE).
> **Wall:** 53 min total (3 train+eval pairs sequential).

---

## 1. Sweep result

Fixed gate: DDIC `cum_unnorm` **>** no-control `cum_unnorm = −7.4838` (less freq deviation = less negative reward).

| Tag | PHI_H | PHI_D | PHI_F | train wall | eval wall | DDIC cum_unnorm | vs no_ctrl | PASS? |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| (P5.1) `phi_b1` | 1e-4 | 1e-4 | 100 | (overnight) | 7.7 min | **−8.902** | −19 % | ❌ |
| `phi_h_d_lower` | 1e-5 | 1e-5 | 100 | 9.9 min | 7.8 min | **−7.965** | **−6 %** (best of 4) | ❌ |
| `phi_f_500` | 1e-4 | 1e-4 | 500 | 10.0 min | 7.8 min | **−8.979** | −20 % | ❌ |
| `phi_paper_scaled` | 1e-2 | 1e-2 | 100 | 9.8 min | 7.7 min | **−8.922** | −19 % | ❌ |

`phi_h_d_lower` is the best of the four (1e-5 PHI_H/D pushes r_h share from ~70 % toward ~7 %), but still **6 % worse** than doing nothing.

---

## 2. Root cause analysis

PHI tuning produced ~1 dB of variation across 4 orders of magnitude in PHI_H/D and 5× in PHI_F. The ceiling is **structural**, not reward-shape.

**Hypothesis (Pm-step proxy leverage gap):**

- **v3 Path (C) Pm-step proxy** injects the disturbance directly into the **ESS internal Pm signal** (`Pm_step_amp_<i>`). Disturbance enters the swing equation **before** the H, D parameters apply.
- Math: `H · d²δ/dt² + D · dδ/dt = ΔPm_disturbance + ΔPe_external`. Changing H, D modulates the **dynamics of THIS source** but does NOT **buffer an external perturbation** from elsewhere on the network.
- The ESS's H, D have leverage over the system frequency only when an **external** perturbation hits another node and propagates through the network — paper's case (LoadStep at Bus 7/9, perturbation enters via load bus, propagates through line + transformer + ESS interface, where H, D can shape the response).
- v3 Pm-step proxy at the ESS terminal: any H, D adjustment by RL is roughly equivalent to "shape my own Pm response" — almost no system-frequency benefit. Hence trained DDIC is no better than no-control, and stochastic actor noise makes it slightly worse.

**Supporting evidence:**

- v3 no_control = −7.48 vs paper no_control = −15.20 → v3's Pm-step proxy at DIST ∈ [0.1, 0.5] sys-pu = 10-50 MW per ESS produces **half** the frequency deviation that paper's 248/188 MW LoadStep does. The reward signal is genuinely weaker.
- The 4-PHI plateau at ~ −8 to −9 (range 13 %) is consistent with policy drift around an effectively flat reward surface.
- All 4 trainings completed numerically clean — no NaN/Inf, no monitor stop, no tds_failed.
- `phi_h_d_lower` (smallest PHI_H, weakest r_h dominance) edges out the others by being closest to "let the policy do whatever, all roads lead to ~no_control" — confirms r_h pull was actively HARMFUL but not the dominant constraint.

---

## 3. Three forward paths

Authorized scope so far excludes: build / .slx / IC / runtime.mat / bridge / helper / LoadStep wiring / NE39 / 2000-ep training. The user-authorized P4.1 Path (C) covers env-side disturbance dispatch and config knobs.

### Z1 — Switch disturbance from ESS-Pm to SG-Pm proxy (RECOMMENDED, in P4.1 Path C scope)

Re-dispatch the same Pm-step trick onto **SG sources** (G1, G2, G3) instead of ESS sources (ES1..ES4). SG-side workspace vars **already exist in runtime.mat** (Phase 4.1a-v2 added `PmgStep_t_<g>` / `PmgStep_amp_<g>` for g=1..3). Same `apply_workspace_var` mechanism. New disturbance type names:

- `pm_step_proxy_g1_g2_g3` — uniform random pick of G1, G2, G3
- `pm_step_proxy_g1` / `pm_step_proxy_g2` / `pm_step_proxy_g3` — fixed per scenario

Expected effect: SG sources are at **buses 1, 2, 3** (not ESS terminals); their Pm step propagates through the network to the ESS, simulating paper's "external perturbation enters via non-ESS source, propagates to ESS" pattern. ESS H/D adjustments now have system-level leverage.

Surface: env dispatch table extension (4 new entries) + config enum + new probe to verify routing. ~50 LOC env, ~50 LOC probe. Same workspace push mechanism as Path C v3 already proven.

Wall: ~30 min implement + 30 min routing probe + ~28 min train+eval per PHI candidate.

### Z2 — LoadStep wiring (Path A scope-expansion)

Edit `build_kundur_cvs_v3.m` LoadStep R-block to read workspace `1/G_perturb_<k>_S` (currently hardcoded `'1e9'`). Re-emit `.slx` + `_runtime.mat`. Then enable `pm_step_proxy_bus7` / `bus9` to actually toggle LoadStep R values mid-episode.

Pros: paper-faithful disturbance topology (Sec.IV-C "Load Step 1/2" at Bus 14/15 ↔ our Bus 7/9). Magnitude up to 248 MW.

Cons: violates §0 lock on `build_kundur_cvs_v3.m` + `.slx`. Requires explicit user authorization. Risk: build edit may surface other latent issues (the LoadStep workspace path was DEAD per Phase 4.0 §R2-Blocker1; re-enabling it has not been tested at runtime).

Wall: ~2-4 hr (build edit + regen + cold-start verify + dispatch wiring + probe + 50-ep train + paper_eval).

### Z3 — Accept Pm-step proxy ceiling; ship with caveat

Document that v3 cannot beat zero-action baseline under Pm-step proxy disturbance topology. Pick `phi_h_d_lower` as the v3 default (best of 4). Phase 5 verdict notes the discrepancy from paper.

Pros: zero further code change. All artifacts already exist.

Cons: Phase 5 conclusion would say "v3 trained policy is statistically indistinguishable from no-control" — not a paper-replication outcome.

---

## 4. Recommendation

**Z1 first**, because:
- (a) Stays within authorized P4.1 Path (C) scope (env dispatch + config only).
- (b) `PmgStep_*` workspace vars were already plumbed in P4.1a-v2 cold-start fix; only env-side dispatch wiring is new.
- (c) Cheap to implement (~1 hr) and cheap to test (~30 min routing probe + 1× 50-ep + eval ≈ 1.5 hr).
- (d) Decisive: if SG-Pm proxy fails too, Pm-step approach as a class is exhausted and Z2 becomes the only remaining technical path; if it passes, Phase 5 can advance without Z2's scope risk.

If Z1 fails, escalate to **Z2** with explicit user authorization on build / .slx / runtime.mat unlock.

Z3 reserved for if both Z1 and Z2 fail.

---

## 5. Boundary check (R2)

- `env/simulink/_base.py`, `env/simulink/kundur_simulink_env.py`: untouched ✓
- `agents/`, `scenarios/contract.py`, `scenarios/config_simulink_base.py`: untouched ✓
- `engine/simulink_bridge.py`, `slx_helpers/vsg_bridge/*`: untouched ✓
- `build_kundur_cvs_v3.m`, `kundur_cvs_v3.slx`, `kundur_ic_cvs_v3.json`, `kundur_cvs_v3_runtime.mat`: untouched ✓
- LoadStep wiring: untouched ✓
- NE39: untouched ✓
- Single edit: [`scenarios/kundur/config_simulink.py`](../../../../scenarios/kundur/config_simulink.py) `PHI_F` line gained env-var override (default 100.0 = paper-faithful) — same pattern as PHI_H/D in P4.2.
- No 2000-ep training launched ✓ (3× 50-ep gate runs only).

---

## 6. Artifacts

```
scenarios/kundur/config_simulink.py        (EDITED: PHI_F env-var override)
probes/kundur/v3_dryrun/_r2_phi_sweep_with_paper_gate.py    (NEW: orchestrator)

results/harness/kundur/cvs_v3_phase4/
├── phase5_r1_reward_audit_verdict.md           (R1 audit — no bug)
├── phase5_r2_phi_sweep_verdict.md              (this file)
├── r2_aggregate_metrics.json                   (machine-readable)
├── r2_phi_h_d_lower_train_stdout.txt + train_stderr.txt
├── r2_phi_h_d_lower_eval_metrics.json + eval_stdout.txt + eval_stderr.txt
├── r2_phi_f_500_*.{txt,json}
├── r2_phi_paper_scaled_*.{txt,json}
├── r2_runner_stdout.txt + r2_runner_stderr.txt

results/sim_kundur/runs/
├── kundur_simulink_<TS-1>/  (phi_h_d_lower)
├── kundur_simulink_<TS-2>/  (phi_f_500)
└── kundur_simulink_<TS-3>/  (phi_paper_scaled)
```

---

## 7. Decision point

**Choose Z1 / Z2 / Z3 to advance.** R2 sweep terminated cleanly with no PASS; no further runs queued.
