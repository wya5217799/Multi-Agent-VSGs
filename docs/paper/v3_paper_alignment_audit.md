# Kundur CVS v3 vs Yang TPWRS 2023 — Paper Alignment Audit

> **Generated:** 2026-04-26
> **State of v3 audited:** commit `a5bc173` (Phase 3 P3.4 PASS) + working tree (Phase 4 plan only).
> **Paper fact base:** [`docs/paper/yang2023-fact-base.md`](yang2023-fact-base.md)
> **Scope:** Cross-check every modeling, algorithmic, and experimental knob in v3 against the paper. Mark each as `MATCH`, `DIVERGENCE-DOCUMENTED`, `DIVERGENCE-UNDOCUMENTED`, `PAPER-SILENT-PROJECT-DECIDED`, or `OPEN`.

---

## 0. Executive summary

v3 is **structurally aligned** with the paper on the load-bearing pieces — observation, action, reward, network architecture, SAC hyperparameters, agent independence — but has **5 known divergences**, **3 paper-silent project decisions**, and **2 outstanding paper-side ambiguities**. None are model defects; none have been hidden.

| Class | Count | Examples |
|---|---|---|
| MATCH | 14 | r_f formula, r_h/r_d formula (`-(mean Δ)²`), φ_f=100, obs dim 7, act dim 2, n_agents=4, fn=50, dt=0.2, m=2 neighbors, SAC LR 3e-4, γ=0.99, batch 256, M=50 steps, replay 10000, independent learners |
| DIVERGENCE-DOCUMENTED | 5 | (D1) Kron reduction NOT applied — full 16-bus electrical model; (D2) replay buffer NOT cleared per episode (Algorithm 1 vs Table I conflict, project follows Table I); (D3) parameter sharing variants exist but Simulink path uses independent learners ✓ paper; (D4) PHI_H=PHI_D=1e-4 in current Kundur config (paper says 1.0); (D5) single-VSG asymmetric Pm-step disturbance instead of bus-localised load step at Bus 7/9 |
| PAPER-SILENT-PROJECT-DECIDED | 3 | (S1) ESS Pm0 = −0.369 sys-pu (charging baseline; paper gives no Pm0); (S2) 3 SG governor droop R=0.05 (paper-implicit); (S3) wind farms as const-power PVS, no Type-3/4 dynamics |
| OPEN paper-side ambiguities | 2 | (Q7) H_es dimensionality unresolved; M=2H mapping is project inference, not paper fact (V3 uses M0=24 → H=12 if paper-second convention). (Q2) ΔH_avg / ΔD_avg computation — global vs neighbor mean — paper does not specify protocol |

**Bottom line:** v3 reproduces the paper's RL contract faithfully. Topology fidelity is HIGHER than what the paper formally requires (Kron-reduced classical swing model). Reward weights need a Phase 4 sweep to recover paper r_f% balance.

---

## 1. RL contract — observation, action, reward (Sec.III-A, Eq.11–18)

### 1.1 Observation vector — MATCH

| Item | Paper (Eq.11) | v3 |
|---|---|---|
| Form | `(ΔP_es, Δω, Δω̇, Δω^c_1..m, Δω̇^c_1..m)` | ✓ same shape |
| Dim | `3 + 2m` | `obs_dim = 7` for `m=2` (`scenarios/contract.py:74`) |
| Comm-fail handling | `Δω^c_j = 0`, `Δω̇^c_j = 0` when `η_j = 0` | ✓ implemented in `simulink_vsg_env.py:469-475` (`fail = rng.random() < comm_fail_prob`) |
| Comm-delay handling | not used in training; tested off-line at 0.2 s (Sec.IV-E) | ✓ `comm_delay_steps=0` default; `simulink_vsg_env.py:88` exposes the knob for off-line eval |

**Verdict: MATCH.**

### 1.2 Action vector — MATCH (with documented Q7 ambiguity)

| Item | Paper (Eq.12-13, Sec.IV-B) | v3 |
|---|---|---|
| Action | `(ΔH_es, ΔD_es)` | `(ΔM, ΔD)` with project convention `M = 2H` |
| ΔH range | [−100, 300] (Sec.IV-B) | DM_MIN/DM_MAX derived from paper via Q7 mapping; `M_LO=22.5, M_HI=28.5` for v3 (`scenarios/kundur/config_simulink.py` derived from base) |
| ΔD range | [−200, 600] | DD_MIN/DD_MAX = [-1.5, +4.5]; `D_LO=3.0, D_HI=9.0` |
| Update rule | `H_t = H_0 + ΔH_t`, `D_t = D_0 + ΔD_t` | ✓ |

**Note:** v3 numerical ranges are NOT paper's [-100, 300] / [-200, 600] face-value — they are scaled per project Q7 working-hypothesis (`H_paper = 2·H_code`, both rescaled to a workable VSG-base pu band). See `docs/paper/yang2023-fact-base.md §2.1 Q7` and `scenarios/kundur/NOTES.md`. **Verdict: MATCH on shape/semantics, OPEN on absolute scale (Q7 unresolved at paper level).**

### 1.3 Reward — MATCH (formula) + DIVERGENCE-DOCUMENTED (weights)

| Term | Paper (Eq.14-18) | v3 implementation (`env/simulink/_base.py:191-247`) |
|---|---|---|
| `r_f` | `-(Δω_i − ω̄_i)² − Σ_j η_j (Δω^c_j − ω̄_i)²` | ✓ identical, `Δω` in p.u. (`omega - 1.0`) per `_base.py:201-204` |
| `ω̄_i` | local-weighted with active neighbors (Eq.16) | ✓ |
| `r_h` | `−(ΔH̄)²` (mean-then-square, Eq.17) | ✓ `r_h_val = delta_H_mean ** 2` then `-PHI_H * r_h_val` (`_base.py:236-239`) |
| `r_d` | `−(ΔD̄)²` (Eq.18) | ✓ same pattern |
| Total | `φ_f r_f + φ_h r_h + φ_d r_d` | ✓ |
| `φ_f` | 100 (Sec.IV-B) | **100** ✓ (`_base.py:83`) |
| `φ_h` | 1 (Sec.IV-B) | **1e-4** for `kundur` profile (`scenarios/kundur/config_simulink.py:93`); 1.0 in `_base.py:84` default |
| `φ_d` | 1 (Sec.IV-B) | **1e-4** for `kundur` profile; 1.0 default |

**φ_h / φ_d divergence (D4):** v3 Kundur config uses `PHI_H = PHI_D = 1e-4` (B1 baseline locked at commit `de5a11c`). The override comment explains: at v3 H/D dimensionality (project Q7 working hypothesis × VSG-base convention), the paper's `1.0` weight overwhelms `r_f` so `r_f% ≈ 0`. P2.5c explicitly recommends asymmetric `PHI_H > PHI_D` for v3 because H authority dominates; B1 is symmetric. **Phase 4 P4.1 will sweep PHI candidates** to recover paper-aligned `r_f%` balance (target 3-8 % per paper §IV-B implication).

**Q2 ambiguity:** The paper does not specify whether `ΔH̄ / ΔD̄` are global mean (`mean_i ΔH_i`) or neighbor mean. v3 uses **global mean** (`_base.py:237: delta_H_mean = ΔM_mean / 2`). Paper Sec.III-A says "distributed average estimators" but gives no protocol. **OPEN.**

---

## 2. System model — VSG dynamics + network (Sec.II-A, II-B, IV-A)

### 2.1 Per-VSG swing equation — MATCH (control-form), with Q7 caveat

| Item | Paper Eq.1 | v3 build (`build_kundur_cvs_v3.m:267-308`) |
|---|---|---|
| Form | `H Δω̇ + D Δω = Δu − ΔP_es` | ✓ identical control-form (no `2`, no `ω_s`) — see project Q7 derivation in `yang2023-fact-base.md §2.1` |
| Implementation | abstract | M·dω/dt = (Pm_total − Pe − D·(ω−1)); δ-integrator: dδ/dt = ω_n·(ω−1) |
| `H_es,0` for ESS | not given (only Δ ranges) | `M0 = 24` (= H=12 by project convention M=2H) |
| `D_es,0` for ESS | not given | `D0 = 4.5` (post-promotion 2026-04-26 from 18; see `build_kundur_cvs_v3.m:83-87` rationale) |

**Verdict: MATCH on formula, project-decided on absolute baseline values (paper gives only deltas).**

### 2.2 Kron reduction — DIVERGENCE-DOCUMENTED (D1)

> **Paper Sec.II-A Remark 1:** "Buses without energy storage are eliminated through Kron reduction, leaving an N-bus reduced network."

v3 implements the **full 16-bus network** with Kron reduction NOT applied:
- 15 active buses (Bus 13 skipped per paper Fig.3 numbering)
- 4 ESS buses (12, 16, 14, 15) — would be retained under Kron
- 3 SG buses (1, 2, 3) — would be retained as well (synchronous machines have inertia)
- 2 wind buses (4, 11) — should be reduced if treated as const-power injection
- 6 passive nodes (5, 6, 7-load, 8, 9-load, 10) — these are the targets of Kron reduction

**Why v3 keeps the full 16-bus model:** the paper-fact-base Q5 + Phase 0 audit found that **paper-faithful network** (correct line lengths, parallels, shunt caps) is the spec choice; Kron reduction is a paper-mathematical convenience for the proposition proof, not a mandate. The full 16-bus is *more* faithful — it preserves the Pi-line losses (37.4 MW = 1.37 % of load) and the inter-area mode physics that paper Sec.II-B's Proposition 1 references but does NOT actually use in implementation. Phase 2 H/D sensitivity (P2.5a 4.86×) confirms the full model produces the paper-predicted behavior.

**Documented in:** `quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md §1, §4`. Verdict: **DIVERGENCE-DOCUMENTED, fidelity-positive.**

### 2.3 Network parameters — MATCH (paper-derived)

| Item | Paper / Yang Sec.IV-A | v3 |
|---|---|---|
| Topology | "modified Kundur two-area" with G4 → wind farm + 100 MW at Bus 8 | ✓ implemented; bus indices 1-16 minus 13 |
| f_nominal | 50 Hz | 50 Hz (`scenarios/contract.py:71`) |
| S_base | implicit 100 MVA (Kundur convention) | 100 MVA (`build_kundur_cvs_v3.m:64`) |
| V_base | 230 kV (Kundur convention) | 230 kV (`build_kundur_cvs_v3.m:65`) |
| 3 SG (G1/G2/G3) at Bus 1/2/3 | 700 / 700 / 719 MW (paper P0) | ✓ identical (`build_powerlib_kundur.m:91-98`, copied into v3 build) |
| H_SG | G1/G2 = 6.5 s, G3 = 6.175 s | ✓ |
| D_SG | 5.0 (gen-base pu) | ✓ |
| R_droop | 0.05 (gen-base pu, paper-implicit) | 0.05 (S2 — see §3 below) |
| W1 at Bus 4 | 700 MW const-power | ✓ |
| W2 at Bus 11 | 100 MW const-power | ✓ |
| 4 ESS at Bus 12/16/14/15 connected via Bus 7/8/10/9 | paper says "different areas", `build_powerlib_kundur.m:201` documents | ✓ |
| Loads | 967 MW @ Bus 7, 1767 MW @ Bus 9 | ✓ |
| Shunt caps | 200 Mvar @ Bus 7, 350 Mvar @ Bus 9 | ✓ |
| Inter-area tie | 110 km × 3 parallel between Bus 7/8 | ✓ |
| All other lines | paper Sec.IV-A indirectly via [49] Kundur original | ✓ verbatim from `build_powerlib_kundur.m:241-267` |

**Verdict: MATCH** on the SG / wind / load / line layer.

---

## 3. Paper-silent project decisions (S-class)

### S1. ESS dispatch (Pm0) = −0.369 sys-pu per ESS (charging baseline)

Paper does NOT give ESS Pm0 anywhere. v3 derives it from **paper-faithful global P-balance**:
- ΣP_gen_paper = 700 + 700 + 719 = 2119 MW (3 SG at paper P0)
- ΣP_wind_paper = 700 + 100 = 800 MW
- ΣP_load = 967 + 1767 = 2734 MW
- Lossless surplus = 2919 − 2734 = 185 MW
- 4 ESS absorb that minus 37.4 MW Π-line losses → −36.91 MW each (`kundur_ic_cvs_v3.json::p_es_each_mw`)

**Implication:** v3 ESS operate at NR steady **absorbing** ~37 MW each (negative Pm0). Paper experiments are silent; if paper assumed Pm0 = 0 or +0.05 sys-pu (typical), the operating point differs. P2.5c finding ("SG damping floor dominates the modal damping") is a paper-consistent prediction, not a v3 artifact.

**Documented in:** topology spec §3.1 (DECISION-Q1=(a) preserve paper dispatch; ESS group absorbs surplus), Phase 1.1 verdict.

### S2. 3 SG governor droop R = 0.05 (paper-implicit)

Paper Sec.II-A Eq.1 has **no governor term** — only the swing equation `H Δω̇ + D Δω = Δu − ΔP`. The paper's classical model assumes Δu encapsulates all external coupling. v3 build (`build_kundur_cvs_v3.m:268-302`) **adds a governor droop term** `−(1/R)(ω−1)` to the SG `Pm_total` — taken from `build_powerlib_kundur.m:91-98` Kundur-original `R = 0.05`. This is paper-implicit because the Kundur reference [49] provides it.

**Verdict:** S2 is project-decided fidelity-positive. Without governor droop, ω never returns to 1 in steady — δ-integrator alone does it but slowly. Phase 2.1 zero-action passed because the governor + δ jointly drive ω → 1.0.

### S3. Wind farms as const-power PVS

Paper says "wind farm replaces G4" + "100 MW at Bus 8" with no further detail. v3 models both as ee_lib **AC Voltage Source** (constant amplitude × `WindAmp_w` workspace knob, fixed phase from NR). No Type-3 (DFIG) or Type-4 (full converter) dynamics, no slip, no frequency-droop wind control.

**Limitation:** P2.4 wind-trip probe surfaced that the const-power PVS model produces a nonphysical "near-short" effect when WindAmp → 0 (W2 case), because V_PVS → 0 grounds Bus 11 through the L_wind 1 µH internal impedance. In a Type-3/4 model, a trip would disconnect the converter cleanly. **Verdict: DIVERGENCE-MINOR; sufficient for paper test scenarios that don't model wind disconnect physics; surface in Phase 5 if baseline mismatch traces here.**

---

## 4. Algorithm (Sec.III-B, III-C, IV-A — Algorithm 1 + Table I)

### 4.1 SAC architecture — MATCH

| Item | Paper Table I | v3 (`agents/sac.py`, `agents/networks.py`) |
|---|---|---|
| Actor | 4-layer FC, 128 hidden | ✓ `GaussianActor`, `hidden_sizes` from `config_simulink_base` (default 128) |
| Critic | 4-layer FC, 128 hidden | ✓ `DoubleQCritic` (twin Q networks, paper-standard SAC variant) |
| Actor LR | 3e-4 | ✓ `LR=3e-4` |
| Critic LR | 3e-4 | ✓ |
| α LR | 3e-4 | ✓ |
| γ | 0.99 | ✓ |
| Batch | 256 | ✓ Kundur uses 256 (`config_simulink.py:185`) |
| Replay | 10000 | ✓ default; Kundur override 100000 (`config_simulink.py:186`) for v2 reasons — D2 below |
| M (steps/ep) | 50 | ✓ `STEPS_PER_EPISODE = 50` (`config_simulink.py:57`) |
| Episodes | 2000 | ✓ (`config_simulink.py:60`) — Phase 5 will run this; not yet started |
| Independent learners | 4 separate (φ_i, θ_i) per agent | ✓ `agents/ma_manager.py:18-28` instantiates 4 SACAgent — independent buffers, independent gradient updates |
| Centralized SAC variant | Sec.IV-F has it for comparison | ✓ exists at `agents/centralized_sac.py` for separate experiments |

### 4.2 Replay buffer clearing — DIVERGENCE-DOCUMENTED (D2)

| | Paper Algorithm 1 line 16 | Paper Table I | v3 |
|---|---|---|---|
| Buffer policy | `Clear D_i` after each episode's gradient step | size=10000, batch=256, M=50 (would be unfeasible if cleared) | **NOT cleared** |

The paper has an internal Algorithm 1 vs Table I conflict (50 samples/ep can't fill batch=256 from a cleared buffer). v3 follows Table I (= standard off-policy SAC). Documented in `docs/decisions/2026-04-10-paper-baseline-contract.md`.

**Verdict: DIVERGENCE-DOCUMENTED, paper-internal-contradiction-resolved.**

### 4.3 SAC variant — twin-Q + auto α (paper-standard)

Paper says "soft actor-critic, max-entropy RL" but doesn't pin down twin-Q or fixed-α. v3 uses Haarnoja 2018b twin-Q + auto-α (`target_entropy = -action_dim`). This is the SAC default; paper's "SAC" is consistent with this. **Verdict: MATCH.**

---

## 5. Experiment setup (Sec.IV-A, IV-B)

### 5.1 Sim engine — MATCH

| Item | Paper | v3 |
|---|---|---|
| Engine | MATLAB-Simulink | ✓ Phasor mode, ode23t variable-step |
| Python control | Yes | ✓ via `engine/simulink_bridge.py` + `slx_helpers/vsg_bridge/` |
| Step DT | 0.2 s | ✓ |
| T_episode | 10 s (M=50) | ✓ |

### 5.2 Datasets — DIVERGENCE-MINOR + OPEN

| Item | Paper | v3 |
|---|---|---|
| Train: 100 random scenarios | "randomly generated" — fixed-vs-resampled unclear (Q1) | v3 uses **per-ep resampling** of disturbance magnitude (`DIST_MIN=0.1`, `DIST_MAX=0.5`) on a fixed bus pattern. NOT a fixed 100-scenario set. |
| Test: 50 random scenarios | same | not yet implemented for v3 (Phase 4 / 5) |
| Disturbance position | random across "negligible-conducting buses" | v3 currently single-VSG[0] asymmetric Pm-step per ep (B1 baseline at commit `de5a11c`) |
| Disturbance magnitude | random | random sign × uniform [DIST_MIN, DIST_MAX] |
| Comm fail | random per-link | ✓ `comm_fail_prob = COMM_FAIL_PROB` per ep |

**D5 — Disturbance form divergence:** Paper test scenarios are "load step at Bus 7" and "load step at Bus 9" (Sec.IV-C names them "load step 1 / 2"). v3 currently uses **Pm-step on a single VSG** instead of bus-localised load step. This was a B1 baseline workaround — the symmetric Pm-step on all 4 ESS made `r_f ≡ 0` (all nodes move together). The asymmetric single-VSG hack restores `r_f` signal at the cost of paper-form fidelity.

**Phase 4 fix:** P4.1 should switch to the v3-built `LoadStep7` / `LoadStep9` blocks (already wired in `build_kundur_cvs_v3.m`) for paper-faithful disturbance. P2.3-L1 confirmed they produce a measurable transient. Currently the env predicate (`kundur_simulink_env.py:699`) only routes Pm-step.

### 5.3 Hardware / wall-time — informational

| Item | Paper | v3 |
|---|---|---|
| CPU | Intel Core i7-11370 | (not measured) |
| GPU | NVIDIA MX 450 | (`device='cpu'` default) |
| Wall time per ep | not reported | P3.4 smoke 14 s/ep (50 step + warmup) — extrapolated 50-ep ≈ 12 min, 2000-ep ≈ 8 hr |

---

## 6. Open paper-side ambiguities (Q-class)

These are blockers in the paper itself, not v3 defects.

### Q7 — H_es dimensionality

Paper Eq.1 uses lump-form `H Δω̇` with no `2` and no `ω_s`. Project derives M = 2H to match Simulink generator-model conventions. If paper used H in a different convention, v3 H/D ranges would shift by a factor of 2 or `ω_s`. **All v3 P2.5 H-sensitivity results scale linearly with this assumption.** Resolution requires paper-side clarification or empirical match against paper Fig.4-7 (Phase 5 work).

### Q2 — ΔH̄ / ΔD̄ computation (global vs neighbor mean)

Paper Sec.III-A says "distributed average estimators" but no protocol. v3 uses global mean. If paper used neighbor mean (m=2 each), the r_h / r_d penalty has different value — typically smaller because variance across neighbors is smaller than across all 4 ESS. Phase 4 r_f% gate will indirectly test this.

---

## 7. Cross-cut diff table (one-line summary per item)

| # | Item | Status | Where to look |
|---|---|---|---|
| 1 | r_f formula | MATCH | `_base.py:212-234` ↔ Eq.15-16 |
| 2 | r_h formula | MATCH | `_base.py:236-239` ↔ Eq.17 |
| 3 | r_d formula | MATCH | `_base.py:241-244` ↔ Eq.18 |
| 4 | φ_f = 100 | MATCH | `_base.py:83`; `config_simulink.py:77` |
| 5 | φ_h, φ_d (Kundur v3) | DIVERGENCE-DOCUMENTED (D4) | `config_simulink.py:93-94` (1e-4 vs paper 1.0) — Phase 4 sweep planned |
| 6 | obs dim 7, m=2 | MATCH | `contract.py:74` ↔ Eq.11 |
| 7 | act dim 2 | MATCH | `contract.py:75` |
| 8 | n_agents=4 | MATCH | `contract.py:70` ↔ Sec.IV-A |
| 9 | fn=50 | MATCH | `contract.py:71` |
| 10 | dt=0.2 | MATCH | `contract.py:72` |
| 11 | M=50 | MATCH | `config_simulink.py:57` |
| 12 | episodes=2000 | MATCH (target; not yet run) | `config_simulink.py:60` |
| 13 | LR/γ/τ | MATCH | `config_simulink_base` |
| 14 | batch=256 | MATCH | `config_simulink.py:185` |
| 15 | replay=100000 (Kundur) | MATCH on principle (Table I 10000; Kundur override fits same family); D2 buffer-clear | `config_simulink.py:186` |
| 16 | independent learners | MATCH | `ma_manager.py:18` |
| 17 | comm-fail in training | MATCH | `simulink_vsg_env.py:469` |
| 18 | comm-delay only off-line | MATCH | `simulink_vsg_env.py:88` (default 0) |
| 19 | Network: 16-bus full (no Kron) | DIVERGENCE-DOCUMENTED (D1) — fidelity-positive | topology spec §1, §4 |
| 20 | SG H/D/R | MATCH (paper-implicit S2) | `build_kundur_cvs_v3.m:80-83` |
| 21 | Wind = const-power PVS | PAPER-SILENT-PROJECT-DECIDED (S3) | `build_kundur_cvs_v3.m:619-655` |
| 22 | ESS Pm0 = −0.369 sys-pu | PAPER-SILENT-PROJECT-DECIDED (S1) | `kundur_ic_cvs_v3.json::vsg_pm0_pu` |
| 23 | Disturbance: single-VSG Pm-step | DIVERGENCE-DOCUMENTED (D5) | `kundur_simulink_env.py:699-729` |
| 24 | T_WARMUP = 10 s | DIVERGENCE-MINOR (paper does no warmup) | `config_simulink.py:46` |
| 25 | LoadStep / WindTrip mid-sim | NOT YET ROUTED through env | Phase 4/5 work |
| 26 | Buffer clear/no-clear | DIVERGENCE-DOCUMENTED (D2) | `paper-baseline-contract.md` |
| 27 | Test eval = global r_f | MATCH on principle (not yet implemented) | Phase 5 work |
| 28 | Q7 H_es dim | OPEN (paper-side) | `yang2023-fact-base.md §2.1 Q7` |
| 29 | Q2 ΔH̄ / ΔD̄ protocol | OPEN (paper-side) | `yang2023-fact-base.md §8 Q2` |

---

## 8. Recommendations (no actions taken in this audit)

| Priority | Action | Phase |
|---|---|---|
| P1 | Sweep `(PHI_H, PHI_D)` with the v3 model to recover paper r_f% balance (close D4) — already planned | P4.1-P4.3 |
| P1 | Switch primary disturbance from single-VSG Pm-step to bus-localised LoadStep7/9 (close D5) — env predicate change | early Phase 4 / Phase 5 |
| P2 | Implement test-set with fixed 50 scenarios + **global** r_f evaluation per Sec.IV-C (close §5.2 gap) | Phase 5 |
| P2 | Wind-trip via paper-faithful disconnect (close S3 / D-minor) — build edit | Phase 5 if paper baseline mismatch |
| P3 | Resolve Q7 / Q2 either by author contact or by empirical fit against paper Fig.4-7 numerical values | post-Phase-5 |
| P3 | Optionally implement Kron-reduced classical model variant (close D1 in the *paper-strict* direction) | research-grade follow-up |

None of these are model defects; they are alignment refinements. v3 as-is can run Phase 4 and Phase 5 against the current contract.

---

## 9. Files cited in this audit (all read during audit, all unchanged)

- `docs/paper/yang2023-fact-base.md` (paper truth, OCR + manual core)
- `scenarios/contract.py`
- `scenarios/kundur/config_simulink.py`
- `scenarios/kundur/kundur_ic_cvs_v3.json`
- `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m`
- `scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m`
- `scenarios/kundur/model_profiles/kundur_cvs_v3.json`
- `env/simulink/_base.py`
- `env/simulink/simulink_vsg_env.py`
- `env/simulink/kundur_simulink_env.py`
- `agents/sac.py`, `agents/networks.py`, `agents/ma_manager.py`, `agents/replay_buffer.py`, `agents/centralized_sac.py`
- `quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md`
- `quality_reports/plans/2026-04-26_kundur_cvs_v3_plan.md`
- Phase 2 / 3 verdicts under `results/harness/kundur/`

---

## 10. Audit boundary

This document is **read-only** — no code, model, IC, NR, env, profile, SAC, training, v2, NE39 file modified by the audit itself. Findings are evidence; implementation work is gated to Phase 4 / Phase 5 plans.
